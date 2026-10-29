import csv
import datetime as dt
import json
import pathlib
from decimal import Decimal as D

import pytest

from trading.backtest import evaluate_market, judge, metrics, round_trips

CRIT = {"min_trades": 2, "expectancy_after_costs_jpy_gt": 0, "profit_factor_min": 1.2, "max_drawdown_pct_max": 10}


def t(date, side, sym="A", realized="0", cost="1"):
    return {"date": date, "symbol": sym, "side": side, "quantity": 1, "price": "1", "price_jpy": "1",
            "cost_jpy": cost, "realized_jpy": realized, "reason": "x"}


def test_round_trips_include_both_costs():
    trips = round_trips([t("2020-01-01", "buy"), t("2020-01-05", "sell", realized="100"),
                         t("2020-02-01", "buy"), t("2020-02-03", "sell", realized="-50")])
    assert [r["pnl"] for r in trips] == [D(98), D(-52)]
    assert trips[0]["exit"] == "2020-01-05"


def test_metrics_and_judgement():
    trips = [{"pnl": D(100), "exit": "2020-01-01"}, {"pnl": D(-40), "exit": "2021-01-01"},
             {"pnl": D(60), "exit": "2021-06-01"}, {"pnl": D(20), "exit": "2022-01-01"}]
    eq = [("2020-01-01", D(50000)), ("2020-06-01", D(55000)), ("2021-01-01", D(52250)), ("2022-01-01", D(56000))]
    m = metrics(trips, eq, D(50000))
    assert m["trades"] == 4 and m["expectancy_jpy"] == 35.0
    assert m["profit_factor"] == round(180 / 40, 3)
    assert m["max_drawdown_pct"] == 5.0  # 55,000 → 52,250
    assert m["by_year"]["2021"] == {"trades": 2, "net_pnl_jpy": 20.0}
    j = judge(m, CRIT)
    assert j["pass"]
    m2 = {**m, "expectancy_second_half_jpy": -1.0}
    assert not judge(m2, CRIT)["pass"]


def test_evaluate_market_never_reads_past_end(tmp_path):
    """end 以降の行は runner に渡らない（ホールドアウト保護）。"""
    data = tmp_path / "data"
    data.mkdir()
    start = dt.date(2020, 1, 1)
    rows, d, i = [], start, 0
    while len(rows) < 300:
        if d.weekday() < 5:
            c = 1000 + i
            rows.append({"date": d.isoformat(), "open": c, "high": c + 5, "low": c - 5, "close": c, "adj_close": c})
            i += 1
        d += dt.timedelta(days=1)
    for name in ("1306.T.csv", "USDJPY.csv"):
        with (data / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    cfg = json.loads((pathlib.Path(__file__).resolve().parents[1] / "config" / "paper.json").read_text(encoding="utf-8"))
    cfg["universe"] = [{"symbol": "1306.T", "currency": "JPY", "market": "JP"}]
    end = dt.date.fromisoformat(rows[250]["date"])
    m = evaluate_market(cfg, "JP", data, dt.date.fromisoformat(rows[210]["date"]), end, tmp_path / "w")
    assert m["period"][1] == end.isoformat()


def test_open_position_at_end_is_marked_into_results():
    trips = round_trips([t("2020-01-01", "buy", cost="10")], {"A": (10, D(100), D(90))}, "2020-12-31", D("0.001"))
    assert len(trips) == 1 and trips[0]["exit"] == "2020-12-31"
    assert trips[0]["pnl"] == D(-10) + D(-100) - D("0.9")  # エントリーコスト＋含み損＋想定決済コスト


def test_halves_split_by_date_not_count():
    trips = [{"pnl": D(10), "exit": f"2020-0{m}-01"} for m in range(1, 8)] + [{"pnl": D(-50), "exit": "2020-12-01"}]
    eq = [("2020-01-01", D(50000)), ("2020-12-31", D(50000))]
    m = metrics(trips, eq, D(50000))
    assert m["expectancy_second_half_jpy"] < 0  # 件数で二分すると後半もプラスに見えてしまう


def test_missing_symbol_data_invalidates_market(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    cfg = json.loads((pathlib.Path(__file__).resolve().parents[1] / "config" / "paper.json").read_text(encoding="utf-8"))
    cfg["universe"] = [{"symbol": "1306.T", "currency": "JPY", "market": "JP"}]
    m = evaluate_market(cfg, "JP", data, dt.date(2020, 1, 1), dt.date(2020, 12, 31), tmp_path / "w")
    j = judge(m, CRIT)
    assert not j["pass"] and "データ欠損" in j["invalid"]


def test_final_requires_matching_committed_preregistration(tmp_path):
    import subprocess

    from trading.backtest import verify_preregistration

    repo = tmp_path / "repo"
    repo.mkdir()
    run_ = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)
    run_("init", "-q")
    run_("config", "user.email", "t@example.com")
    run_("config", "user.name", "t")
    run_("config", "commit.gpgsign", "false")
    f = repo / "prereg.json"
    f.write_text('{"a": 1}\n', encoding="utf-8")
    run_("add", ".")
    run_("commit", "-qm", "prereg")
    sha = run_("rev-parse", "HEAD").stdout.strip()
    verify_preregistration(f, sha)  # 一致すれば通る
    with pytest.raises(SystemExit):
        verify_preregistration(f, "deadbeef")  # 存在しないコミット
    f.write_text('{"a": 2}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        verify_preregistration(f, sha)  # 登録後に変更


def _synthetic(tmp_path, n=300, gap_rows=()):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    rows, d, i = [], dt.date(2020, 1, 1), 0
    while len(rows) < n:
        if d.weekday() < 5:
            c = 1000 + i * 2
            rows.append({"date": d.isoformat(), "open": c, "high": c + 5, "low": c - 5, "close": c, "adj_close": c})
            i += 1
        d += dt.timedelta(days=1)
    cfg = json.loads((pathlib.Path(__file__).resolve().parents[1] / "config" / "paper.json").read_text(encoding="utf-8"))
    cfg["universe"] = [{"symbol": "1306.T", "currency": "JPY", "market": "JP"},
                       {"symbol": "1475.T", "currency": "JPY", "market": "JP"}]
    for name, rr in (("1306.T.csv", [r for k, r in enumerate(rows) if k not in gap_rows]),
                     ("1475.T.csv", [{**r, "open": 300, "high": 300, "low": 300, "close": 300, "adj_close": 300} for r in rows])):
        with (data / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rr)
    return cfg, data, rows


def test_equity_and_trip_pnl_are_consistent_with_open_position(tmp_path):
    cfg, data, rows = _synthetic(tmp_path)
    m = evaluate_market(cfg, "JP", data, dt.date.fromisoformat(rows[210]["date"]), dt.date.fromisoformat(rows[-1]["date"]), tmp_path / "w")
    assert m["open_at_end"] == ["1306.T"]  # 右肩上がりなので期末に保有が残る
    assert "invalid" not in m
    assert m["consistency_diff_jpy"] <= 30  # 差は想定決済コスト程度


def test_many_data_gaps_invalidate_market(tmp_path):
    cfg, data, rows = _synthetic(tmp_path, gap_rows=range(240, 250))
    m = evaluate_market(cfg, "JP", data, dt.date.fromisoformat(rows[210]["date"]), dt.date.fromisoformat(rows[-1]["date"]), tmp_path / "w")
    assert m["data_gaps"] > 5
    j = judge(m, CRIT)
    assert not j["pass"] and "欠損日" in j["invalid"]
