import csv
import datetime as dt
import json
import pathlib
import shutil

from trading.runner import load_bars, run

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config" / "paper.json"


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close"])
        w.writeheader()
        w.writerows(rows)


def make_data(tmp: pathlib.Path, days: int, last_close_drop: bool = False):
    """1306.T を右肩上がり（ブレイクアウトが出る）に、USDJPY を一定にした合成データ。"""
    data = tmp / "data"
    data.mkdir()
    start = dt.date(2026, 1, 1)
    rows, fx = [], []
    d = start
    i = 0
    while len(rows) < days:
        if d.weekday() < 5:
            c = 3000 + i * 2
            rows.append({"date": d.isoformat(), "open": c - 1, "high": c + 5, "low": c - 5, "close": c})
            fx.append({"date": d.isoformat(), "open": 150, "high": 150, "low": 150, "close": 150})
            i += 1
        d += dt.timedelta(days=1)
    write_csv(data / "1306.T.csv", rows)
    write_csv(data / "USDJPY.csv", fx)
    return data, [dt.date.fromisoformat(r["date"]) for r in rows]


def cfg_from(tmp: pathlib.Path, start: dt.date) -> pathlib.Path:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["start_date"] = start.isoformat()
    cfg["universe"] = [{"symbol": "1306.T", "currency": "JPY", "market": "JP"}]
    p = tmp / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def test_load_bars_skips_bad_rows(tmp_path):
    p = tmp_path / "x.csv"
    write_csv(p, [
        {"date": "2026-01-02", "open": 1, "high": 2, "low": 1, "close": 2},
        {"date": "bad", "open": 1, "high": 2, "low": 1, "close": 2},
        {"date": "2026-01-03", "open": 1, "high": 1, "low": 2, "close": 1},  # 高値 < 安値
        {"date": "2026-01-01", "open": 1, "high": 2, "low": 1, "close": 2},
    ])
    bars = load_bars(p)
    assert [b.date.isoformat() for b in bars] == ["2026-01-01", "2026-01-02"]


def test_run_enters_next_open_and_writes_outputs(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = cfg_from(tmp_path, dates[210])
    state = tmp_path / "state"
    b = run(cfg, data, state)
    assert b.last_date == dates[-1]
    assert b.trades, "ブレイクアウトで少なくとも1回は約定する"
    first = b.trades[0]
    assert first["side"] == "buy" and first["date"] == dates[211].isoformat()  # 判定日の翌営業日に約定
    for name in ("state.json", "trades.csv", "equity.csv", "report.md"):
        assert (state / name).exists()
    assert "実資金ではありません" in (state / "report.md").read_text(encoding="utf-8")


def test_rerun_is_idempotent_and_resumes(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = cfg_from(tmp_path, dates[210])
    state = tmp_path / "state"
    b1 = run(cfg, data, state)
    n = len(b1.trades)
    b2 = run(cfg, data, state)  # 新しいデータなし → 何も起きない
    assert len(b2.trades) == n and b2.last_date == b1.last_date
    lines = (state / "equity.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 + (len(dates) - 210)  # 見出し＋処理日数（重複なし）


def test_incremental_run_matches_single_run(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = cfg_from(tmp_path, dates[205])
    one = run(cfg, data, tmp_path / "one")
    # 途中までのデータで一度実行し、残りを後から足して再実行
    part = tmp_path / "part"
    shutil.copytree(data, part)
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    write_csv(part / "1306.T.csv", rows[:218])
    run(cfg, part, tmp_path / "inc")
    write_csv(part / "1306.T.csv", rows)
    inc = run(cfg, part, tmp_path / "inc")
    assert inc.trades == one.trades
    assert inc.cash == one.cash


def test_fills_use_unadjusted_prices_and_signals_use_adjusted(tmp_path):
    data, dates = make_data(tmp_path, 230)
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    # 調整済み終値を常に 1% 低くする（配当調整を模擬）。未調整の値動きは同じ
    for r in rows:
        r["adj_close"] = f"{float(r['close']) * 0.99:.6f}"
    with (data / "1306.T.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close", "adj_close"])
        w.writeheader()
        w.writerows(rows)
    cfg = cfg_from(tmp_path, dates[210])
    b = run(cfg, data, tmp_path / "state")
    first = b.trades[0]
    raw_open = [r for r in rows if r["date"] == first["date"]][0]["open"]
    from decimal import Decimal as D
    assert D(first["price"]) == (D(raw_open) * D("1.0005")).quantize(D("0.0001"))


def test_split_like_divergence_halts_when_holding(tmp_path):
    data, dates = make_data(tmp_path, 230)
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    for r in rows:
        r["adj_close"] = r["close"]
    # 最後の日だけ未調整価格が半分（2分割を模擬）、調整済みは連続
    for k in ("open", "high", "low", "close"):
        rows[-1][k] = f"{float(rows[-1][k]) / 2:.6f}"
    with (data / "1306.T.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close", "adj_close"])
        w.writeheader()
        w.writerows(rows)
    cfg = cfg_from(tmp_path, dates[210])
    b = run(cfg, data, tmp_path / "state")
    assert "企業行動" in b.halted and "1306.T" in b.frozen
    qty = b.risk.position("1306.T").quantity
    n_trades = len(b.trades)
    # 翌日以降も未調整価格（半値）が続いても、凍結中は損切りも評価も動かない
    nxt = dt.date.fromisoformat(rows[-1]["date"]) + dt.timedelta(days=3)
    rows.append({**rows[-1], "date": nxt.isoformat()})
    with (data / "1306.T.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close", "adj_close"])
        w.writeheader()
        w.writerows(rows)
    fx_rows = list(csv.DictReader((data / "USDJPY.csv").open(encoding="utf-8")))
    fx_rows.append({**fx_rows[-1], "date": nxt.isoformat()})
    write_csv(data / "USDJPY.csv", fx_rows)
    b2 = run(cfg, data, tmp_path / "state")
    assert b2.risk.position("1306.T").quantity == qty and len(b2.trades) == n_trades
    assert not any(e.kind == "rule_violation" for e in b2.events)


def test_stop_distance_is_converted_to_unadjusted_units(tmp_path):
    data, dates = make_data(tmp_path, 230)
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    for r in rows:
        r["adj_close"] = f"{float(r['close']) * 0.5:.6f}"  # 調整済みは実価格の半分（極端な例）
    with (data / "1306.T.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "open", "high", "low", "close", "adj_close"])
        w.writeheader()
        w.writerows(rows)
    cfg = cfg_from(tmp_path, dates[210])
    b = run(cfg, data, tmp_path / "state")
    from decimal import Decimal as D
    last_buy = [t for t in b.trades if t["side"] == "buy"][-1]
    # 実価格の ATR は 10（高安差 10）→ 損切り幅 20。調整済みのまま使うと 10 になってしまう
    assert b.stops["1306.T"].stop_price == D(last_buy["price"]) - D(20)


def test_split_event_freezes_held_symbol_even_if_prices_are_back_adjusted(tmp_path):
    """Yahoo は分割を遡って OHLC を調整するので、価格の乖離では検出できない。分割イベントで凍結する。"""
    data, dates = make_data(tmp_path, 230)
    cfg = cfg_from(tmp_path, dates[210])
    b = run(cfg, data, tmp_path / "state")
    assert b.risk.position("1306.T").quantity > 0
    nxt = dates[-1] + dt.timedelta(days=1 if dates[-1].weekday() < 4 else 3)
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    rows.append({**rows[-1], "date": nxt.isoformat()})
    write_csv(data / "1306.T.csv", rows)
    fx = list(csv.DictReader((data / "USDJPY.csv").open(encoding="utf-8")))
    fx.append({**fx[-1], "date": nxt.isoformat()})
    write_csv(data / "USDJPY.csv", fx)
    with (data / "1306.T.splits.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "numerator", "denominator"])
        w.writeheader()
        w.writerow({"date": nxt.isoformat(), "numerator": 2, "denominator": 1})
    b2 = run(cfg, data, tmp_path / "state")
    assert "1306.T" in b2.frozen and "分割" in b2.halted


def test_missing_data_for_held_symbol_aborts_without_advancing(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = json.loads(cfg_from(tmp_path, dates[210]).read_text(encoding="utf-8"))
    cfg["universe"].append({"symbol": "SPLG", "currency": "USD", "market": "US"})
    p = tmp_path / "cfg2.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    write_csv(data / "SPLG.csv", [{**r, "open": 50, "high": 50, "low": 50, "close": 50} for r in rows])
    b = run(p, data, tmp_path / "state")
    assert b.risk.position("1306.T").quantity > 0
    last = b.last_date
    # 次の実行で保有銘柄（1306.T）のファイルが取得できなかった
    (data / "1306.T.csv").unlink()
    nxt = dates[-1] + dt.timedelta(days=1 if dates[-1].weekday() < 4 else 3)
    srows = list(csv.DictReader((data / "SPLG.csv").open(encoding="utf-8")))
    srows.append({**srows[-1], "date": nxt.isoformat()})
    write_csv(data / "SPLG.csv", srows)
    b2 = run(p, data, tmp_path / "state")
    assert b2.last_date == last  # 日付を進めない
    assert any(e.kind == "run_aborted" and "1306.T" in e.symbol for e in b2.events)


def test_partial_delay_of_held_symbol_stops_before_that_day(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = json.loads(cfg_from(tmp_path, dates[210]).read_text(encoding="utf-8"))
    cfg["universe"].append({"symbol": "1475.T", "currency": "JPY", "market": "JP"})
    p = tmp_path / "cfg3.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    flat = [{**r, "open": 300, "high": 300, "low": 300, "close": 300} for r in rows]
    write_csv(data / "1475.T.csv", flat)
    write_csv(data / "1306.T.csv", rows[:-2])  # 保有予定の 1306.T だけ直近2日が未配信
    b = run(p, data, tmp_path / "state")
    assert b.risk.position("1306.T").quantity > 0
    assert b.last_date == dates[-3]  # 1306.T の足がない日には進まない
    assert any(e.kind == "run_aborted" for e in b.events)
    # 配信が追いついたら続きから処理される
    write_csv(data / "1306.T.csv", rows)
    b2 = run(p, data, tmp_path / "state")
    assert b2.last_date == dates[-1]


def test_market_holiday_for_held_symbol_does_not_abort(tmp_path):
    data, dates = make_data(tmp_path, 230)
    cfg = json.loads(cfg_from(tmp_path, dates[210]).read_text(encoding="utf-8"))
    cfg["universe"].append({"symbol": "SPLG", "currency": "USD", "market": "US"})
    p = tmp_path / "cfg4.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    us = [{**r, "open": 50, "high": 50, "low": 50, "close": 50} for r in rows]
    holiday = rows[-1]["date"]
    write_csv(data / "1306.T.csv", rows[:-1])  # 最終日は日本の休場、米国だけ取引
    write_csv(data / "SPLG.csv", us)
    b = run(p, data, tmp_path / "state")
    # 日本の休場日かどうかは、日本の次の足が届くまで確定できないので、その日はまだ処理しない
    assert b.last_date.isoformat() < holiday
    assert not any(e.kind == "run_aborted" for e in b.events)
    # 日本の翌営業日の足が届くと、休場日（日本の足なし）として処理され、損切り未判定の日は生じない
    nxt = (dt.date.fromisoformat(holiday) + dt.timedelta(days=1 if dt.date.fromisoformat(holiday).weekday() < 4 else 3)).isoformat()
    write_csv(data / "1306.T.csv", rows[:-1] + [{**rows[-1], "date": nxt}])
    write_csv(data / "SPLG.csv", us + [{**us[-1], "date": nxt}])
    fx = list(csv.DictReader((data / "USDJPY.csv").open(encoding="utf-8")))
    write_csv(data / "USDJPY.csv", fx + [{**fx[-1], "date": nxt}])
    b2 = run(p, data, tmp_path / "state")
    assert b2.last_date.isoformat() == nxt
    assert not any(e.kind == "run_aborted" for e in b2.events)


def test_whole_market_delay_for_held_market_waits(tmp_path):
    """保有している日本市場の全銘柄が未配信でも、米国の足だけで日付を進めない（休場と誤認しない）。"""
    data, dates = make_data(tmp_path, 230)
    cfg = json.loads(cfg_from(tmp_path, dates[210]).read_text(encoding="utf-8"))
    cfg["universe"].append({"symbol": "SPLG", "currency": "USD", "market": "US"})
    p = tmp_path / "cfg5.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    write_csv(data / "SPLG.csv", [{**r, "open": 50, "high": 50, "low": 50, "close": 50} for r in rows])
    write_csv(data / "1306.T.csv", rows[:-2])  # 日本市場（保有）の直近2日が丸ごと未配信
    b = run(p, data, tmp_path / "state")
    assert b.risk.position("1306.T").quantity > 0
    assert b.last_date == dates[-3]
    assert any(e.kind == "waiting_data" for e in b.events)
    # 日本の配信が追いつけば、1日も飛ばさずに処理される
    write_csv(data / "1306.T.csv", rows)
    b2 = run(p, data, tmp_path / "state")
    assert b2.last_date == dates[-1]
    eq = (tmp_path / "state" / "equity.csv").read_text(encoding="utf-8").strip().splitlines()[1:]
    assert [l.split(",")[0] for l in eq][-2:] == [d.isoformat() for d in dates[-2:]]


def test_market_is_required(tmp_path):
    import pytest

    data, dates = make_data(tmp_path, 230)
    cfg = json.loads(cfg_from(tmp_path, dates[210]).read_text(encoding="utf-8"))
    for bad in (None, "jp", "EU"):
        cfg["universe"][0].pop("market", None)
        if bad:
            cfg["universe"][0]["market"] = bad
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        with pytest.raises(ValueError):
            run(p, data, tmp_path / "state")


def test_pending_order_market_delay_waits(tmp_path):
    """米国の買い注文が未約定のまま米国の配信が遅れたら、日本の足だけで日付を進めない。"""
    data, dates = make_data(tmp_path, 230)
    cfg = json.loads(cfg_from(tmp_path, dates[210]).read_text(encoding="utf-8"))
    cfg["universe"] = [{"symbol": "SPLG", "currency": "USD", "market": "US"},
                       {"symbol": "1475.T", "currency": "JPY", "market": "JP"}]
    p = tmp_path / "cfg6.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    rows = list(csv.DictReader((data / "1306.T.csv").open(encoding="utf-8")))
    us = [{**r, "open": float(r["open"]) / 60, "high": float(r["high"]) / 60, "low": float(r["low"]) / 60,
           "close": float(r["close"]) / 60} for r in rows]
    write_csv(data / "1475.T.csv", [{**r, "open": 300, "high": 300, "low": 300, "close": 300} for r in rows])
    # 米国のブレイクアウトで最終日の前日に買い注文が出る位置まで → 最終日の米国足は未配信
    signal_day = None
    for k in range(211, 230):
        write_csv(data / "SPLG.csv", us[:k])
        st = tmp_path / f"s{k}"
        b = run(p, data, st)
        if b.pending:
            signal_day = k
            break
    assert signal_day is not None
    assert b.last_date == dates[signal_day - 1]  # 日本の足は先まであるが、米国の注文が約定するまで進まない
    assert any(e.kind == "waiting_data" for e in b.events)
    # 米国の配信が追いつくと、注文は予定どおり翌営業日の始値で約定する
    write_csv(data / "SPLG.csv", us)
    b2 = run(p, data, tmp_path / f"s{signal_day}")
    fill = [t for t in b2.trades if t["symbol"] == "SPLG"][0]
    assert fill["date"] == dates[signal_day].isoformat()
