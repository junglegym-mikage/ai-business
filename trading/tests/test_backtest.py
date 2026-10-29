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
             {"pnl": D(60), "exit": "2021-06-01"}, {"pnl": D(-20), "exit": "2022-01-01"}]
    eq = [("2020-01-01", D(50000)), ("2020-06-01", D(55000)), ("2021-01-01", D(52250)), ("2022-01-01", D(56000))]
    m = metrics(trips, eq, D(50000))
    assert m["trades"] == 4 and m["expectancy_jpy"] == 25.0
    assert m["profit_factor"] == round(160 / 60, 3)
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
