import datetime as dt
from decimal import Decimal

import pytest

from trading.risk import Order, RiskLimits, RiskManager

DAY1 = dt.date(2026, 10, 29)
DAY2 = dt.date(2026, 10, 30)


def make(capital=50_000, **kw):
    return RiskManager(RiskLimits(capital_jpy=capital, **kw), trading_day=DAY1)


def buy(symbol="7203", qty=10, price=1000, stop=950):
    return Order(symbol, "buy", qty, Decimal(price), None if stop is None else Decimal(stop))


def sell(symbol="7203", qty=10, price=1000, stop=None):
    return Order(symbol, "sell", qty, Decimal(price), None if stop is None else Decimal(stop))


def lose(rm, amount, symbol="LOSS"):
    """amount 円の確定損失を模擬約定で発生させる。"""
    rm.record_fill(Order(symbol, "buy", amount, Decimal(10), Decimal(9)))
    rm.record_fill(Order(symbol, "sell", amount, Decimal(9)))


# --- 上限値 ----------------------------------------------------------
def test_default_limits_for_50k():
    rm = make()
    assert rm.max_loss_per_trade == Decimal(1000)
    assert rm.max_daily_loss == Decimal(2500)
    assert rm.max_position_value == Decimal(25000)


def test_limits_are_configurable():
    rm = make(capital=100_000, max_loss_per_trade_pct=Decimal("0.01"))
    assert rm.max_loss_per_trade == Decimal(1000)


@pytest.mark.parametrize(
    "kw",
    [
        {"capital_jpy": 0},
        {"capital_jpy": -1},
        {"max_loss_per_trade_pct": Decimal(0)},
        {"max_loss_per_trade_pct": Decimal("1.5")},
        {"max_daily_loss_pct": Decimal("NaN")},
        {"max_position_pct": Decimal("Infinity")},
    ],
)
def test_invalid_limits_are_rejected(kw):
    with pytest.raises(ValueError):
        RiskLimits(**kw)


# --- 1トレード損失・ポジション上限 ------------------------------------
def test_order_within_limits_is_accepted():
    assert make().check(buy(qty=10, price=1000, stop=950)).accepted


def test_loss_exactly_at_limit_is_accepted():
    assert make().check(buy(qty=20, price=1000, stop=950)).accepted  # 損失 1,000


def test_loss_over_limit_is_rejected():
    d = make().check(buy(qty=21, price=1000, stop=950))  # 損失 1,050
    assert not d.accepted and "1トレード" in d.reason


def test_position_exactly_at_limit_is_accepted():
    assert make().check(buy(qty=25, price=1000, stop=990)).accepted  # 25,000


def test_position_over_limit_is_rejected():
    d = make().check(buy(qty=26, price=1000, stop=990))
    assert not d.accepted and "ポジション" in d.reason


def test_existing_position_counts_toward_limit():
    rm = make()
    rm.record_fill(buy(qty=20, price=1000, stop=990))
    assert not rm.check(buy(qty=6, price=1000, stop=990)).accepted


def test_other_symbol_has_separate_position_limit():
    rm = make()
    rm.record_fill(buy(symbol="7203", qty=20, price=1000, stop=990))
    assert rm.check(buy(symbol="AAPL", qty=20, price=1000, stop=990)).accepted


def test_short_entry_uses_stop_above():
    assert make().check(sell("AAPL", 10, 1000, stop=1100)).accepted  # 損失 1,000


# --- 決済・ポジション管理（レビュー指摘1） -----------------------------
def test_closing_frees_position_for_reentry():
    rm = make()
    rm.record_fill(buy(qty=25, price=1000, stop=990))
    assert not rm.check(buy(qty=1, price=1000, stop=990)).accepted
    rm.record_fill(sell(qty=25, price=1000))
    assert rm.position("7203").quantity == 0
    assert rm.check(buy(qty=25, price=1000, stop=990)).accepted


def test_partial_close_reduces_position_and_realizes_pnl():
    rm = make()
    rm.record_fill(buy(qty=20, price=1000, stop=950))
    realized = rm.record_fill(sell(qty=5, price=1100))
    assert realized == Decimal(500)
    assert rm.position("7203").quantity == 15
    assert rm.daily_realized_pnl == Decimal(500)


def test_closing_order_needs_no_stop_and_is_accepted():
    rm = make()
    rm.record_fill(buy(qty=10, price=1000, stop=950))
    assert rm.check(sell(qty=10, price=900)).accepted


def test_short_close_realizes_pnl():
    rm = make()
    rm.record_fill(sell("AAPL", 10, 1000, stop=1050))
    assert rm.record_fill(buy("AAPL", 10, 1020, stop=None)) == Decimal(-200)


def test_flip_order_is_rejected():
    rm = make()
    rm.record_fill(buy(qty=10, price=1000, stop=950))
    d = rm.check(sell(qty=20, price=1000, stop=1100))
    assert not d.accepted and "反転" in d.reason
    with pytest.raises(ValueError):
        rm.record_fill(sell(qty=20, price=1000))


def test_average_price_on_add():
    rm = make()
    rm.record_fill(buy(qty=10, price=1000, stop=950))
    rm.record_fill(buy(qty=10, price=1100, stop=1050))
    assert rm.position("7203").avg_price == Decimal(1050)


def test_entry_without_stop_is_rejected():
    d = make().check(buy(stop=None))
    assert not d.accepted and "損切り" in d.reason


# --- 日次損失（レビュー指摘2） ----------------------------------------
def test_daily_loss_reached_blocks_new_orders():
    rm = make()
    lose(rm, 2500)  # ちょうど 5%
    d = rm.check(buy())
    assert not d.accepted and "1日" in d.reason


def test_daily_loss_below_limit_still_allows():
    rm = make()
    lose(rm, 2499)
    assert rm.check(buy()).accepted


def test_unrealized_loss_counts_toward_daily_limit():
    rm = make()
    rm.record_fill(buy("AAPL", qty=20, price=1000, stop=950))
    rm.update_mark("AAPL", Decimal(875))  # 含み損 2,500
    assert rm.unrealized_pnl == Decimal(-2500)
    assert not rm.check(buy()).accepted


def test_closing_allowed_even_after_daily_limit():
    rm = make()
    rm.record_fill(buy(qty=20, price=1000, stop=950))
    rm.update_mark("7203", Decimal(850))  # 含み損 3,000
    assert rm.check(sell(qty=20, price=850)).accepted


def test_costs_count_as_realized_loss():
    rm = make()
    lose(rm, 2400)
    rm.record_cost(Decimal(100))
    assert not rm.check(buy()).accepted


def test_daily_limit_persists_until_next_trading_day():
    rm = make()
    lose(rm, 3000)
    assert rm.start_new_day(DAY1) is False  # 同じ日ではリセットしない
    assert rm.start_new_day(dt.date(2026, 10, 28)) is False  # 過去の日もしない
    assert not rm.check(buy()).accepted
    assert rm.start_new_day(DAY2) is True
    assert rm.check(buy()).accepted


def test_profit_offsets_loss_within_day():
    rm = make()
    lose(rm, 3000)
    rm.record_fill(buy("GAIN", qty=10, price=1000, stop=950))
    rm.record_fill(sell("GAIN", qty=10, price=1100))  # +1,000 → 累計 -2,000
    assert rm.check(buy()).accepted


# --- 入力検証（任意提案1） ---------------------------------------------
@pytest.mark.parametrize(
    "order",
    [
        Order("7203", "buy", 0, Decimal(1000), Decimal(950)),
        Order("7203", "buy", -1, Decimal(1000), Decimal(950)),
        Order("7203", "buy", True, Decimal(1000), Decimal(950)),
        Order("7203", "buy", 1, Decimal(0), Decimal(0)),
        Order("7203", "buy", 1, Decimal("NaN"), Decimal(950)),
        Order("7203", "buy", 1, Decimal("Infinity"), Decimal(950)),
        Order("7203", "buy", 1, Decimal(1000), Decimal("NaN")),
        Order("7203", "buy", 1, Decimal(1000), Decimal(1000)),
        Order("7203", "buy", 1, Decimal(1000), Decimal(1100)),
        Order("7203", "sell", 1, Decimal(1000), Decimal(900)),
        Order("7203", "hold", 1, Decimal(1000), Decimal(900)),
        Order("", "buy", 1, Decimal(1000), Decimal(950)),
        Order("  ", "buy", 1, Decimal(1000), Decimal(950)),
    ],
)
def test_invalid_orders_are_rejected(order):
    assert not make().check(order).accepted


def test_invalid_cost_and_mark_are_rejected():
    rm = make()
    with pytest.raises(ValueError):
        rm.record_cost(Decimal(-1))
    with pytest.raises(ValueError):
        rm.update_mark("7203", Decimal("NaN"))


# --- 安全ガード ---------------------------------------------------------
def test_check_refuses_in_live_mode(monkeypatch):
    from trading.safety import LiveTradingForbiddenError

    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(LiveTradingForbiddenError):
        make().check(buy())
