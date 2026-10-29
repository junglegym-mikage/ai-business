import datetime as dt
import json
from decimal import Decimal as D

import pytest

from trading.broker import Bar, BrokerConfig, Instrument, PaperBroker, PendingOrder, size_position
from trading.risk import RiskLimits

JP = Instrument("1306.T", "JPY")
US = Instrument("SPLG", "USD")
D1, D2, D3, D4 = (dt.date(2026, 11, d) for d in (9, 10, 11, 12))


def broker(**cfg):
    limits = RiskLimits(est_cost_rate=D("0.001"))
    return PaperBroker([JP, US], limits, BrokerConfig(**cfg), start_day=dt.date(2026, 11, 6))


def bar(day, o, h=None, l=None, c=None):
    o = D(o)
    return Bar(day, o, D(h) if h else o, D(l) if l else o, D(c) if c else o)


def buy(cid="o1", sym="1306.T", qty=5, dist="40", reason="test"):
    return PendingOrder(cid, sym, "buy", qty, D(dist), reason)


def sell(cid="x1", sym="1306.T", qty=5, reason="exit"):
    return PendingOrder(cid, sym, "sell", qty, None, reason)


# --- 入口のガード ------------------------------------------------------
def test_live_mode_blocks_submit(monkeypatch):
    from trading.safety import LiveTradingForbiddenError

    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(LiveTradingForbiddenError):
        broker().submit(buy())


def test_duplicate_client_id_is_rejected():
    b = broker()
    assert b.submit(buy("dup"))[0]
    ok, reason = b.submit(buy("dup"))
    assert not ok and "重複" in reason
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    assert b.risk.position("1306.T").quantity == 5  # 二重約定しない


def test_entry_without_stop_is_rejected():
    ok, reason = broker().submit(PendingOrder("a", "1306.T", "buy", 1, None))
    assert not ok and "損切り" in reason


def test_no_stop_orders_available_blocks_entries():
    b = broker(stop_orders_available=False)
    ok, reason = b.submit(buy())
    assert not ok and "損切り注文を設定できない" in reason


def test_unknown_symbol_is_rejected():
    assert not broker().submit(buy(sym="XXXX"))[0]


# --- 約定（次の始値、スリッページ・コスト） ------------------------------
def test_fill_at_next_open_with_slippage_and_cost():
    b = broker()
    b.submit(buy(qty=5, dist="40"))
    assert b.risk.position("1306.T").quantity == 0  # まだ約定しない
    b.process_day(D1, {"1306.T": bar(D1, 3000, 3010, 2990, 3005)}, D(150))
    pos = b.risk.position("1306.T")
    assert pos.quantity == 5
    assert pos.avg_price == D("3001.5")  # 3000 × 1.0005
    notional = D("3001.5") * 5
    assert b.cash == D(50000) - notional - (notional * D("0.001")).quantize(D("0.01"))
    assert b.stops["1306.T"].stop_price == D("2961.5")


def test_order_waits_when_symbol_has_no_bar():
    b = broker()
    b.submit(buy())
    b.process_day(D1, {}, D(150))  # 休場
    assert len(b.pending) == 1
    b.process_day(D2, {"1306.T": bar(D2, 3000)}, D(150))
    assert b.risk.position("1306.T").quantity == 5


def test_insufficient_cash_cancels():
    b = broker()
    b.submit(buy(qty=8, dist="10"))  # 8 × 3,000 = 24,000 → OK
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    b.cash = D(1000)
    b.submit(buy("o2", qty=1, dist="10"))
    b.process_day(D2, {"1306.T": bar(D2, 3000)}, D(150))
    assert any(e.kind == "cancelled" and "現金不足" in e.detail for e in b.events)


def test_risk_rejection_at_fill_time_cancels():
    b = broker()
    b.submit(buy(qty=5, dist="300"))  # 損失 1,500 > 1,000
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    assert b.risk.position("1306.T").quantity == 0
    assert any(e.kind == "cancelled" and "リスク判定" in e.detail for e in b.events)


# --- 損切り執行 ---------------------------------------------------------
def test_stop_executes_at_stop_price_intraday():
    b = broker()
    b.submit(buy(qty=5, dist="40"))
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    b.process_day(D2, {"1306.T": bar(D2, 2990, 3000, 2950, 2960)}, D(150))
    assert b.risk.position("1306.T").quantity == 0
    assert "1306.T" not in b.stops
    t = b.trades[-1]
    assert t["reason"] == "stop" and D(t["price"]) == (D("2961.5") * D("0.9995")).quantize(D("0.0001"))
    assert not b.halted


def test_gap_down_fills_at_open_and_halts_on_violation():
    b = broker()
    b.submit(buy(qty=8, dist="100"))  # 想定損失 ≈ 800+コスト
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    b.process_day(D2, {"1306.T": bar(D2, 2800, 2820, 2790, 2810)}, D(150))  # 窓開けで損切りを飛び越える
    assert b.trades[-1]["reason"] == "stop_gap"
    assert any(e.kind == "rule_violation" for e in b.events)
    assert b.halted
    ok, reason = b.submit(buy("o9"))
    assert not ok and "停止中" in reason


def test_halted_still_allows_closing():
    b = broker()
    b.submit(buy(qty=5, dist="40"))
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    b.halted = "テスト"
    assert b.submit(sell(qty=5))[0]
    b.process_day(D2, {"1306.T": bar(D2, 3010)}, D(150))
    assert b.risk.position("1306.T").quantity == 0


def test_two_consecutive_daily_limit_days_halt():
    b = broker()
    b.process_day(D1, {}, D(150))
    b.risk.record_cost(D(2500))  # D1 の損失が日次上限に到達（模擬）
    b.process_day(D2, {}, D(150))
    assert not b.halted and b.limit_hit_streak == 1
    b.risk.record_cost(D(2500))
    b.process_day(D3, {}, D(150))
    assert b.halted and "2営業日連続" in b.halted


def test_streak_resets_after_normal_day():
    b = broker()
    b.process_day(D1, {}, D(150))
    b.risk.record_cost(D(2500))
    b.process_day(D2, {}, D(150))
    b.process_day(D3, {}, D(150))  # D2 は損失なし
    assert b.limit_hit_streak == 0 and not b.halted


def test_date_must_advance():
    b = broker()
    b.process_day(D1, {}, D(150))
    with pytest.raises(ValueError):
        b.process_day(D1, {}, D(150))


# --- 為替 ---------------------------------------------------------------
def test_usd_converted_to_jpy_with_fx_buffer():
    b = broker()
    b.submit(buy("u1", sym="SPLG", qty=1, dist="2"))
    b.process_day(D1, {"SPLG": bar(D1, 70)}, D(150))
    pos = b.risk.position("SPLG")
    assert pos.avg_price == D("70.035") * 150
    # リスク判定の損切り（円）は スリッページと為替 3% の不利を見込む
    assert pos.stop_price == D("68.035") * D("0.9995") * D(150) * D("0.97")


def test_usd_position_too_large_for_cap_is_cancelled():
    b = broker()
    b.submit(buy("u1", sym="SPLG", qty=3, dist="1"))  # 3 × 70 × 150 = 31,500 > 25,000
    b.process_day(D1, {"SPLG": bar(D1, 70)}, D(150))
    assert b.risk.position("SPLG").quantity == 0


# --- 保存と復元 ---------------------------------------------------------
def test_state_round_trip_through_json():
    b = broker()
    b.submit(buy(qty=5, dist="40"))
    b.process_day(D1, {"1306.T": bar(D1, 3000, 3010, 2990, 3005)}, D(150))
    b.submit(buy("o2", qty=2, dist="40"))
    data = json.loads(json.dumps(b.to_dict()))
    r = PaperBroker.from_dict(data, [JP, US], b.limits, b.config)
    assert r.cash == b.cash
    assert r.risk.position("1306.T").quantity == 5
    assert r.risk.position("1306.T").avg_price == b.risk.position("1306.T").avg_price
    assert r.stops["1306.T"].stop_price == b.stops["1306.T"].stop_price
    assert [p.client_id for p in r.pending] == ["o2"]
    assert not r.submit(buy("o1"))[0]  # 復元後も重複を検出
    r.process_day(D2, {"1306.T": bar(D2, 2990, 3000, 2950, 2960)}, D(150))  # 復元後も損切りが効く
    assert r.risk.position("1306.T").quantity == 0


def test_equity_includes_marked_positions():
    b = broker()
    b.submit(buy(qty=5, dist="40"))
    b.process_day(D1, {"1306.T": bar(D1, 3000, 3100, 2990, 3100)}, D(150))
    assert b.equity == b.cash + D(3100) * 5


# --- 株数の決め方 -------------------------------------------------------
@pytest.mark.parametrize(
    "budget,dist,price,cap,expected",
    [(500, 40, 3000, 25000, 8), (500, 10, 3000, 25000, 8), (500, 600, 3000, 25000, 0), (500, 0, 3000, 25000, 0)],
)
def test_size_position(budget, dist, price, cap, expected):
    assert size_position(D(budget), D(dist), D(price), D(cap)) == expected


# --- Codex レビュー指摘への対応 ----------------------------------------
def test_usd_fill_uses_fx_known_at_open_and_marks_with_close_fx():
    b = broker()
    b.submit(buy("u1", sym="SPLG", qty=1, dist="2"))
    b.process_day(D1, {"SPLG": bar(D1, 70)}, D(150), D(160))  # 約定は 150、評価は 160
    pos = b.risk.position("SPLG")
    assert pos.avg_price == D("70.035") * 150
    assert pos.mark_price == D(70) * 160


def test_violation_includes_entry_cost():
    # 小さな窓開け：価格差＋決済コストは上限以下だが、エントリーコストを足すと上限を超える
    b = broker(slippage_rate=D(0))
    b.submit(buy(qty=8, dist="118"))  # 事前判定 944 + 往復コスト 47 = 991 → 受付
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    assert b.entry_costs["1306.T"] == D("24.00")
    # 始値 2,878.75 が損切り 2,882 を下回る → 始値約定：価格差 970 + 決済 23.03 = 993.03、+ エントリー 24 = 1,017.03
    b.process_day(D2, {"1306.T": bar(D2, "2878.75", "2900", "2870", "2880")}, D(150))
    assert b.trades[-1]["reason"] == "stop_gap"
    assert any(e.kind == "rule_violation" for e in b.events) and b.halted
    assert "1306.T" not in b.entry_costs


def test_planned_stop_within_limit_is_not_a_violation():
    b = broker(slippage_rate=D(0))
    b.submit(buy(qty=8, dist="118"))
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    b.process_day(D2, {"1306.T": bar(D2, 2950, 2960, 2870, 2880)}, D(150))  # 損切り価格で約定
    assert b.trades[-1]["reason"] == "stop"
    assert not b.halted


def test_exit_fill_also_checked_for_violation():
    b = broker(slippage_rate=D(0))
    b.submit(buy(qty=8, dist="100"))
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    b.submit(sell(qty=8))
    # 手仕舞い注文が窓開けの始値 2,800 で約定（損切り判定より先）→ 実損失 1,600 超 → 違反
    b.process_day(D2, {"1306.T": bar(D2, 2800)}, D(150))
    assert b.risk.position("1306.T").quantity == 0
    assert b.halted


def test_entry_costs_survive_state_round_trip():
    b = broker()
    b.submit(buy(qty=5, dist="40"))
    b.process_day(D1, {"1306.T": bar(D1, 3000)}, D(150))
    r = PaperBroker.from_dict(json.loads(json.dumps(b.to_dict())), [JP, US], b.limits, b.config)
    assert r.entry_costs == b.entry_costs
