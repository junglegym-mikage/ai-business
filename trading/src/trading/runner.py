"""ペーパートレードの日次実行（通信はしない。データは CSV で受け取る）。

使い方:
    python -m trading.runner --config config/paper.json --data data --state state

- data/<銘柄>.csv（date,open,high,low,close＝未調整の実際の価格、adj_close＝分割・配当調整済み終値）と
  data/USDJPY.csv を読む。約定・損切り・損益は未調整価格、売買判定は調整済み価格で行う
- 米国株の約定は「前営業日の為替終値」（約定時点で分かっている値）、評価は当日の為替終値で円換算する
- 保有銘柄に分割イベント（data/<銘柄>.splits.csv）がある日、または価格と調整済み価格の動きが10%以上ずれた日は、
  その銘柄を凍結して全体を停止する（Yahoo の OHLC は分割を遡って調整するため、保存済みの数量・損切りと単位がずれる）
- state/state.json（なければ新規）を読み、前回処理日より後の営業日を古い順に 1 日ずつ処理する
- 各日：①ブローカーが始値約定・損切りを処理 ②その日の終値までで売買判定 ③翌始値の注文を出す
- state/state.json・trades.csv・equity.csv・report.md を書き出す
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
from decimal import Decimal

from trading.broker import Bar, BrokerConfig, Instrument, PaperBroker, PendingOrder, size_position
from trading.risk import RiskLimits
from trading.safety import assert_paper_mode
from trading.strategy import StrategyParams, evaluate


def load_bars(path: pathlib.Path, adjusted: bool = False) -> list[Bar]:
    """日足を読む。adjusted=True なら adj_close/close の比率を OHLC に掛けた調整済み足を返す。"""
    bars = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                o, h, l, c = (Decimal(row[k]) for k in ("open", "high", "low", "close"))
                f = Decimal(1)
                if adjusted and row.get("adj_close"):
                    f = Decimal(row["adj_close"]) / c
                b = Bar(dt.date.fromisoformat(row["date"]), o * f, h * f, l * f, c * f)
            except (KeyError, ValueError, ArithmeticError):
                continue
            if all(v.is_finite() and v > 0 for v in (b.open, b.high, b.low, b.close)) and b.low <= b.high:
                bars.append(b)
    bars.sort(key=lambda b: b.date)
    return bars


def load_config(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(cfg: dict) -> tuple[list[Instrument], RiskLimits, BrokerConfig, StrategyParams]:
    instruments = [Instrument(i["symbol"], i["currency"]) for i in cfg["universe"]]
    r = cfg["risk"]
    limits = RiskLimits(
        capital_jpy=int(r["capital_jpy"]),
        max_loss_per_trade_pct=Decimal(r["max_loss_per_trade_pct"]),
        max_daily_loss_pct=Decimal(r["max_daily_loss_pct"]),
        max_position_pct=Decimal(r["max_position_pct"]),
        est_cost_rate=Decimal(r["est_cost_rate"]),
    )
    b = cfg["broker"]
    bcfg = BrokerConfig(slippage_rate=Decimal(b["slippage_rate"]), fx_buffer=Decimal(b["fx_buffer"]))
    s = cfg["strategy"]
    params = StrategyParams(
        trend_window=int(s["trend_window"]), breakout_window=int(s["breakout_window"]),
        exit_window=int(s["exit_window"]), atr_window=int(s["atr_window"]), atr_multiple=Decimal(s["atr_multiple"]),
    )
    return instruments, limits, bcfg, params


def run(config_path: pathlib.Path, data_dir: pathlib.Path, state_dir: pathlib.Path) -> PaperBroker:
    assert_paper_mode()
    cfg = load_config(config_path)
    instruments, limits, bcfg, params = build(cfg)
    start = dt.date.fromisoformat(cfg["start_date"])
    risk_budget = Decimal(cfg["risk_budget_per_trade_jpy"])

    state_file = state_dir / "state.json"
    if state_file.exists():
        broker = PaperBroker.from_dict(json.loads(state_file.read_text(encoding="utf-8")), instruments, limits, bcfg)
    else:
        broker = PaperBroker(instruments, limits, bcfg, start_day=start - dt.timedelta(days=1))

    files = {i.symbol: data_dir / f"{i.symbol}.csv" for i in instruments if (data_dir / f"{i.symbol}.csv").exists()}
    history = {s: load_bars(p) for s, p in files.items()}  # 未調整（約定用）
    adjusted = {s: load_bars(p, adjusted=True) for s, p in files.items()}  # 調整済み（判定用）
    splits = {s: _load_split_dates(data_dir / f"{s}.splits.csv") for s in files}
    fx_bars = load_bars(data_dir / "USDJPY.csv") if (data_dir / "USDJPY.csv").exists() else []
    missing = [i.symbol for i in instruments if i.symbol not in history]
    for m in missing:
        broker._event("data_missing", m, "データファイルがない")

    after = broker.last_date or (start - dt.timedelta(days=1))
    days = sorted({b.date for bars in history.values() for b in bars if b.date > after and b.date >= start})
    equity_rows = []
    uses_usd = any(i.currency == "USD" for i in instruments)
    for day in days:
        fx_open = _fx_before(fx_bars, day)
        fx_close = _fx_on(fx_bars, day)
        if fx_open is None or fx_close is None:
            if uses_usd:
                broker._event("data_missing", "USDJPY", f"{day} の為替がないため処理を中断", day)
                break
            fx_open = fx_close = Decimal(1)
        todays = {s: b for s, bars in history.items() for b in bars if b.date == day}
        _detect_corporate_actions(broker, history, adjusted, splits, day)  # 検出した銘柄は凍結（以後の処理を止める）
        broker.process_day(day, todays, fx_open, fx_close)
        for inst in instruments:
            bars = [b for b in adjusted.get(inst.symbol, []) if b.date <= day]
            if not bars or bars[-1].date != day:
                continue
            raw_today = todays.get(inst.symbol)
            if raw_today is None:
                continue
            _decide(broker, inst, bars, raw_today, day, fx_close, params, risk_budget, bcfg)
        equity_rows.append({"date": str(day), "equity_jpy": str(broker.equity.quantize(Decimal("0.01"))),
                            "cash_jpy": str(broker.cash.quantize(Decimal("0.01"))), "halted": broker.halted})

    _write_outputs(broker, state_dir, equity_rows, cfg)
    return broker


def _fx_before(fx_bars: list[Bar], day: dt.date) -> Decimal | None:
    """day より前の直近の為替終値（その日の始値時点で分かっている値）。"""
    prior = [b for b in fx_bars if b.date < day]
    if not prior or (day - prior[-1].date).days > 5:
        return None
    return prior[-1].close


def _load_split_dates(path: pathlib.Path) -> set[dt.date]:
    if not path.exists():
        return set()
    out = set()
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out.add(dt.date.fromisoformat(row["date"]))
            except (KeyError, ValueError):
                continue
    return out


def _detect_corporate_actions(broker, raw: dict, adj: dict, splits: dict, day: dt.date) -> list[str]:
    found = []
    for s, bars in raw.items():
        if not broker.risk.position(s).quantity or s in broker.frozen:
            continue
        if day in splits.get(s, set()):
            broker.freeze(day, s, f"{day} に株式分割（保有数量・損切り価格の調整が必要）")
            found.append(s)
            continue
        r = [b for b in bars if b.date <= day][-2:]
        a = [b for b in adj.get(s, []) if b.date <= day][-2:]
        if len(r) < 2 or len(a) < 2 or r[-1].date != day:
            continue
        ratio = (r[-1].close / r[0].close) / (a[-1].close / a[0].close)
        if abs(ratio - 1) > Decimal("0.10"):
            broker.freeze(day, s, "分割などの企業行動の可能性（未調整と調整済みの値動きが乖離）")
            found.append(s)
    return found


def _fx_on(fx_bars: list[Bar], day: dt.date) -> Decimal | None:
    prior = [b for b in fx_bars if b.date <= day]
    if not prior or (day - prior[-1].date).days > 5:
        return None
    return prior[-1].close


def _decide(broker, inst, bars, raw_today, day, fx, params, risk_budget, bcfg) -> None:
    """bars は調整済み（判定用）、raw_today は当日の未調整足（約定・損切りの単位）。"""
    if inst.symbol in broker.frozen:
        return
    pos = broker.risk.position(inst.symbol)
    pending = any(p.symbol == inst.symbol for p in broker.pending)
    if pending:
        return
    sig = evaluate(bars, holding=pos.quantity > 0, p=params)
    if sig is None:
        return
    if sig.action == "exit" and pos.quantity > 0:
        broker.submit(PendingOrder(f"{day}-{inst.symbol}-exit", inst.symbol, "sell", pos.quantity, None, sig.note), fx)
    elif sig.action == "enter" and pos.quantity == 0:
        # 調整済み価格で求めた損切り幅を、未調整（実際に約定する価格）の単位に戻す
        to_raw = raw_today.close / bars[-1].close
        stop_distance = sig.stop_distance * to_raw
        to_jpy = fx * (1 + bcfg.fx_buffer) if inst.currency == "USD" else Decimal(1)
        price_jpy = raw_today.close * to_jpy
        qty = size_position(risk_budget, stop_distance * to_jpy, price_jpy, broker.risk.max_position_value)
        if qty <= 0:
            broker._event("skipped", inst.symbol, "1株でも上限・リスク予算を超えるため見送り", day)
            return
        broker.submit(PendingOrder(f"{day}-{inst.symbol}-enter", inst.symbol, "buy", qty, stop_distance, sig.note), fx)


def _write_outputs(broker: PaperBroker, state_dir: pathlib.Path, equity_rows: list[dict], cfg: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps(broker.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    with (state_dir / "trades.csv").open("w", newline="", encoding="utf-8") as fh:
        fields = ["date", "symbol", "side", "quantity", "price", "price_jpy", "cost_jpy", "realized_jpy", "reason"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(broker.trades)
    eq_path = state_dir / "equity.csv"
    new = not eq_path.exists()
    with eq_path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "equity_jpy", "cash_jpy", "halted"])
        if new:
            w.writeheader()
        w.writerows(equity_rows)

    capital = Decimal(cfg["risk"]["capital_jpy"])
    realized = sum((Decimal(t["realized_jpy"]) - Decimal(t["cost_jpy"]) for t in broker.trades), Decimal(0))
    closes = [t for t in broker.trades if t["side"] == "sell"]
    lines = [
        "# ペーパートレード日次レポート（模擬・実資金ではありません）",
        "",
        f"- 処理済みの最終営業日: {broker.last_date}",
        f"- 評価額: {broker.equity:.0f} 円（開始 {capital:.0f} 円、差 {broker.equity - capital:+.0f} 円）",
        f"- 現金: {broker.cash:.0f} 円",
        f"- 約定回数: {len(broker.trades)}（うち決済 {len(closes)}）",
        f"- 確定損益（コスト控除後の概算）: {realized:+.0f} 円",
        f"- 停止状態: {broker.halted or 'なし'}",
        "",
        "## 保有",
    ]
    for s in broker.instruments:
        p = broker.risk.position(s)
        if p.quantity:
            st = broker.stops.get(s)
            lines.append(f"- {s}: {p.quantity} 株、平均 {p.avg_price:.0f} 円、評価 {p.mark_price:.0f} 円、損切り {st.stop_price if st else '-'}")
    if len(lines) and lines[-1] == "## 保有":
        lines.append("- なし")
    lines += ["", "## 翌営業日の注文（始値で約定予定）"]
    lines += [f"- {o.side} {o.symbol} {o.quantity} 株（{o.reason}）" for o in broker.pending] or ["- なし"]
    lines += ["", "## 直近のイベント"]
    lines += [f"- {e.date} {e.kind} {e.symbol} {e.detail}" for e in broker.events[-15:]] or ["- なし"]
    (state_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=pathlib.Path)
    ap.add_argument("--data", required=True, type=pathlib.Path)
    ap.add_argument("--state", required=True, type=pathlib.Path)
    a = ap.parse_args()
    broker = run(a.config, a.data, a.state)
    print((a.state / "report.md").read_text(encoding="utf-8"))
    if broker.halted:
        print(f"::warning::ペーパートレードは停止中: {broker.halted}")


if __name__ == "__main__":
    main()
