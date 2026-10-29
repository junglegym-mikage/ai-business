"""過去データ検証（ペーパートレードと同じ runner/broker で過去日を1日ずつ処理する）。

使い方:
    python -m trading.backtest --config config/paper.json --prereg config/preregistration.json \
        --data <取得済みCSVのフォルダ> --out <出力フォルダ> [--final --prereg-commit <SHA>]

- 日本・米国を別々に評価する（それぞれ模擬資金 5 万円から）
- 既定では holdout_start より前のデータしか読まない（データを切り詰めてから runner に渡す）
- --final は事前登録ファイルのコミットIDを指定したときだけ受け付け、ホールドアウト期間を評価する
- 停止条件（日次上限の連続到達・ルール違反）に当たった回数は記録し、検証用に翌営業日に自動解除して続ける
- 数値はすべてコードで計算し、results.json と report.md に書き出す
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import tempfile
from decimal import Decimal

from trading.runner import _markets, run
from trading.safety import assert_paper_mode


def _clip_csv(src: pathlib.Path, dst: pathlib.Path, start: dt.date | None, end: dt.date) -> None:
    with src.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        fields = rows[0].keys() if rows else ["date"]
    keep = [r for r in rows if _d(r["date"]) and _d(r["date"]) <= end and (start is None or _d(r["date"]) >= start)]
    with dst.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        w.writeheader()
        w.writerows(keep)


def _d(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def round_trips(trades: list[dict], open_marks: dict | None = None, end_date: str = "", cost_rate: Decimal = Decimal(0)) -> list[dict]:
    """約定記録を往復トレードにまとめる（新規は建玉ゼロからのみなので、買い→売りで1往復）。

    期末に残った建玉は open_marks（銘柄 → (数量, 平均取得価格, 評価価格)：円）で期末の評価額で決済したとみなし、
    想定決済コストを引いて成績に含める（含み損を無視して過大評価しないため）。
    """
    open_: dict[str, dict] = {}
    out = []
    for t in trades:
        s = t["symbol"]
        cost = Decimal(t["cost_jpy"])
        if t["side"] == "buy" and s not in open_:
            open_[s] = {"symbol": s, "entry": t["date"], "pnl": -cost, "qty": t["quantity"]}
            continue
        rt = open_.get(s)
        if rt is None:
            continue
        rt["pnl"] += Decimal(t["realized_jpy"]) - cost
        if t["side"] == "sell":
            rt["exit"] = t["date"]
            rt["reason"] = t["reason"]
            out.append(rt)
            del open_[s]
    for s, rt in open_.items():
        qty, avg, mark = (open_marks or {}).get(s, (0, Decimal(0), Decimal(0)))
        if qty:
            rt["pnl"] += (mark - avg) * qty - mark * abs(qty) * cost_rate
        rt["exit"] = end_date
        rt["reason"] = "期末評価（未決済）"
        out.append(rt)
    return out


def metrics(trips: list[dict], equity: list[tuple[str, Decimal]], capital: Decimal) -> dict:
    pnls = [t["pnl"] for t in trips]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    peak, max_dd = capital, Decimal(0)
    for _, e in equity:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak * 100)
    # 前半・後半は評価期間の中間日で分ける（取引件数で分けると頻度の偏りで後半の悪化を見落とす）
    if equity:
        d0, d1 = dt.date.fromisoformat(equity[0][0]), dt.date.fromisoformat(equity[-1][0])
        mid = (d0 + (d1 - d0) / 2).isoformat()
    else:
        mid = ""
    first = [t["pnl"] for t in trips if t["exit"] < mid]
    second = [t["pnl"] for t in trips if t["exit"] >= mid]
    by_year: dict[str, list[Decimal]] = {}
    for t in trips:
        by_year.setdefault(t["exit"][:4], []).append(t["pnl"])
    return {
        "trades": len(trips),
        "net_pnl_jpy": float(sum(pnls, Decimal(0))),
        "expectancy_jpy": float(sum(pnls, Decimal(0)) / len(pnls)) if pnls else 0.0,
        "win_rate_pct": round(len(wins) / len(pnls) * 100, 1) if pnls else 0.0,
        "profit_factor": round(float(sum(wins, Decimal(0)) / -sum(losses, Decimal(0))), 3) if losses and sum(losses) < 0 else None,
        "max_drawdown_pct": round(float(max_dd), 2),
        "final_equity_jpy": float(equity[-1][1]) if equity else float(capital),
        "expectancy_first_half_jpy": float(sum(first, Decimal(0)) / len(first)) if first else 0.0,
        "expectancy_second_half_jpy": float(sum(second, Decimal(0)) / len(second)) if second else 0.0,
        "by_year": {y: {"trades": len(v), "net_pnl_jpy": float(sum(v, Decimal(0)))} for y, v in sorted(by_year.items())},
        "period": [equity[0][0], equity[-1][0]] if equity else None,
    }


def judge(m: dict, crit: dict) -> dict:
    if m.get("invalid"):
        return {"checks": {"データ完全性": False}, "pass": False, "invalid": m["invalid"]}
    checks = {
        "取引回数": m["trades"] >= crit["min_trades"],
        "期待値プラス": m["expectancy_jpy"] > crit["expectancy_after_costs_jpy_gt"],
        "プロフィットファクター": (m["profit_factor"] or 0) >= crit["profit_factor_min"],
        "最大ドローダウン": m["max_drawdown_pct"] <= crit["max_drawdown_pct_max"],
        "前後半とも期待値プラス": m["expectancy_first_half_jpy"] > 0 and m["expectancy_second_half_jpy"] > 0,
    }
    return {"checks": checks, "pass": all(checks.values())}


def evaluate_market(cfg: dict, market: str, data_dir: pathlib.Path, start: dt.date, end: dt.date, work: pathlib.Path) -> dict:
    universe = [u for u, m in zip(cfg["universe"], _markets(cfg)) if m == market]
    missing = [u["symbol"] for u in universe if not (data_dir / f"{u['symbol']}.csv").exists()]
    if any(u["currency"] == "USD" for u in universe) and not (data_dir / "USDJPY.csv").exists():
        missing.append("USDJPY")
    sub = {**cfg, "universe": universe, "start_date": start.isoformat()}
    d = work / f"data_{market}"
    d.mkdir(parents=True, exist_ok=True)
    for u in universe:
        # 過去データは分割を遡って調整済みの一続きの系列なので、分割イベントは渡さない（凍結は運用時のみ必要）
        src = data_dir / f"{u['symbol']}.csv"
        if src.exists():
            _clip_csv(src, d / src.name, None, end)
    if (data_dir / "USDJPY.csv").exists():
        _clip_csv(data_dir / "USDJPY.csv", d / "USDJPY.csv", None, end)
    cfg_path = work / f"cfg_{market}.json"
    cfg_path.write_text(json.dumps(sub, ensure_ascii=False), encoding="utf-8")
    state = work / f"state_{market}"
    broker = run(cfg_path, d, state, auto_resume=True)
    equity = []
    with (state / "equity.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            equity.append((r["date"], Decimal(r["equity_jpy"])))
    marks = {s: (p.quantity, p.avg_price, p.mark_price) for s in broker.instruments if (p := broker.risk.position(s)).quantity}
    trips = round_trips(broker.trades, marks, equity[-1][0] if equity else "", Decimal(cfg["risk"]["est_cost_rate"]))
    m = metrics(trips, equity, Decimal(cfg["risk"]["capital_jpy"]))
    m["symbols"] = [u["symbol"] for u in universe]
    m["open_at_end"] = sorted(marks)
    if missing:
        m["invalid"] = f"データ欠損: {', '.join(missing)}"
    m["halted"] = broker.halted
    m["events"] = {k: sum(1 for e in broker.events if e.kind == k) for k in sorted({e.kind for e in broker.events})}
    shutil.copy(state / "trades.csv", work / f"trades_{market}.csv")
    return m


def verify_preregistration(prereg_path: pathlib.Path, commit: str) -> None:
    """指定コミットが実在し、その時点の事前登録ファイルが今読むファイルと完全に一致することを確かめる。"""
    if len(commit) < 7:
        raise SystemExit("--final には事前登録ファイルのコミットID（--prereg-commit）が必要")
    path = prereg_path.resolve()
    top = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=False)
    if top.returncode != 0:
        raise SystemExit("git リポジトリ内で実行してください")
    rel = path.relative_to(pathlib.Path(top.stdout.strip()))
    shown = subprocess.run(["git", "-C", top.stdout.strip(), "show", f"{commit}:{rel.as_posix()}"],
                           capture_output=True, text=True, check=False)
    if shown.returncode != 0:
        raise SystemExit(f"コミット {commit} に事前登録ファイルがない（コミットが存在しないか、ファイル未登録）")
    if shown.stdout != path.read_text(encoding="utf-8"):
        raise SystemExit("事前登録ファイルがコミット時点から変更されている。ホールドアウトは開けない")


def main() -> None:
    assert_paper_mode()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=pathlib.Path)
    ap.add_argument("--prereg", required=True, type=pathlib.Path)
    ap.add_argument("--data", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--final", action="store_true", help="ホールドアウト期間を評価する（事前登録コミットが必要）")
    ap.add_argument("--prereg-commit", default="")
    a = ap.parse_args()

    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    pre = json.loads(a.prereg.read_text(encoding="utf-8"))
    holdout = dt.date.fromisoformat(pre["holdout_start"])
    if a.final:
        verify_preregistration(a.prereg, a.prereg_commit)
        start, end, label = holdout, dt.date.today(), "holdout"
    else:
        start = dt.date.fromisoformat(pre["development_period"]["start"])
        end = min(dt.date.fromisoformat(pre["development_period"]["end"]), holdout - dt.timedelta(days=1))
        label = "development"

    a.out.mkdir(parents=True, exist_ok=True)
    results = {"label": label, "start": start.isoformat(), "end": end.isoformat(),
               "prereg_commit": a.prereg_commit or None, "markets": {}}
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        for market in pre["markets_evaluated_separately"]:
            m = evaluate_market(cfg, market, a.data, start, end, work)
            m["judgement"] = judge(m, pre["pass_criteria"])
            results["markets"][market] = m
            shutil.copy(work / f"trades_{market}.csv", a.out / f"trades_{label}_{market}.csv")
    (a.out / f"results_{label}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"# 過去データ検証（{label}）：{start} 〜 {end}", "",
             "模擬資金5万円・手数料0.1%・スリッページ0.05%・為替バッファ3%。ペーパートレードと同じエンジンで1日ずつ処理（先読みなし）。", ""]
    for market, m in results["markets"].items():
        j = m["judgement"]
        lines += [f"## {market}（{', '.join(m['symbols'])}）", "",
                  f"- 判定: **{'合格' if j['pass'] else '不合格'}**  " + " / ".join(f"{k}:{'○' if v else '×'}" for k, v in j["checks"].items()),
                  f"- 取引 {m['trades']} 回、勝率 {m['win_rate_pct']}%、期待値 {m['expectancy_jpy']:+.0f} 円/回、PF {m['profit_factor']}",
                  f"- 損益合計 {m['net_pnl_jpy']:+.0f} 円、最終評価額 {m['final_equity_jpy']:.0f} 円、最大DD {m['max_drawdown_pct']}%",
                  f"- 前半/後半の期待値 {m['expectancy_first_half_jpy']:+.0f} / {m['expectancy_second_half_jpy']:+.0f} 円",
                  f"- 停止: {m['halted'] or 'なし'}、イベント: {m['events']}", "", "| 年 | 取引 | 損益(円) |", "|---|---|---|"]
        lines += [f"| {y} | {v['trades']} | {v['net_pnl_jpy']:+.0f} |" for y, v in m["by_year"].items()]
        lines.append("")
    lines += ["再現: `python -m trading.backtest --config config/paper.json --prereg config/preregistration.json --data <data> --out <out>`",
              "データ: Yahoo Finance（無料・非公式）。上場廃止銘柄は含まない。配当は受取額を損益に含めない（保守的）。"]
    (a.out / f"report_{label}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
