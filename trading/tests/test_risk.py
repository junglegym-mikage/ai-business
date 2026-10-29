from decimal import Decimal

import pytest

from trading.risk import Order, RiskLimits, RiskManager


def make(capital=50_000, **kw):
    return RiskManager(RiskLimits(capital_jpy=capital, **kw))


def buy(symbol="7203", qty=10, price=1000, stop=950):
    return Order(symbol=symbol, side="buy", quantity=qty, price=Decimal(price), stop_price=Decimal(stop))


def test_default_limits_for_50k():
    rm = make()
    assert rm.max_loss_per_trade == Decimal(1000)
    assert rm.max_daily_loss == Decimal(2500)
    assert rm.max_position_value == Decimal(25000)


def test_order_within_limits_is_accepted():
    d = make().check(buy(qty=10, price=1000, stop=950))  # 損失 500, ポジション 10,000
    assert d.accepted, d.reason


def test_loss_exactly_at_limit_is_accepted():
    d = make().check(buy(qty=20, price=1000, stop=950))  # 損失 1,000 ちょうど
    assert d.accepted, d.reason


def test_loss_over_limit_is_rejected():
    d = make().check(buy(qty=21, price=1000, stop=950))  # 損失 1,050
    assert not d.accepted
    assert "1トレード" in d.reason


def test_position_exactly_at_limit_is_accepted():
    d = make().check(buy(qty=25, price=1000, stop=990))  # ポジション 25,000 ちょうど, 損失 250
    assert d.accepted, d.reason


def test_position_over_limit_is_rejected():
    d = make().check(buy(qty=26, price=1000, stop=990))  # 26,000
    assert not d.accepted
    assert "ポジション" in d.reason


def test_existing_position_counts_toward_limit():
    rm = make()
    rm.record_fill(buy(qty=20, price=1000, stop=990))  # 既に 20,000
    d = rm.check(buy(qty=6, price=1000, stop=990))  # 合計 26,000
    assert not d.accepted


def test_other_symbol_has_separate_position_limit():
    rm = make()
    rm.record_fill(buy(symbol="7203", qty=20, price=1000, stop=990))
    d = rm.check(buy(symbol="AAPL", qty=20, price=1000, stop=990))
    assert d.accepted, d.reason


def test_daily_loss_reached_blocks_new_orders():
    rm = make()
    rm.record_realized_pnl(Decimal(-2500))  # ちょうど 5%
    d = rm.check(buy())
    assert not d.accepted
    assert "1日" in d.reason


def test_daily_loss_below_limit_still_allows():
    rm = make()
    rm.record_realized_pnl(Decimal(-2499))
    assert rm.check(buy()).accepted


def test_new_day_resets_daily_loss():
    rm = make()
    rm.record_realized_pnl(Decimal(-3000))
    rm.start_new_day()
    assert rm.check(buy()).accepted


def test_profit_offsets_loss_within_day():
    rm = make()
    rm.record_realized_pnl(Decimal(-3000))
    rm.record_realized_pnl(Decimal(1000))  # 累計 -2,000
    assert rm.check(buy()).accepted


def test_limits_are_configurable():
    rm = make(capital=100_000, max_loss_per_trade_pct=Decimal("0.01"))
    assert rm.max_loss_per_trade == Decimal(1000)


@pytest.mark.parametrize(
    "order",
    [
        Order("7203", "buy", 0, Decimal(1000), Decimal(950)),
        Order("7203", "buy", -1, Decimal(1000), Decimal(950)),
        Order("7203", "buy", 1, Decimal(0), Decimal(0)),
        Order("7203", "buy", 1, Decimal(1000), Decimal(1000)),  # 損切りがエントリーと同じ
        Order("7203", "buy", 1, Decimal(1000), Decimal(1100)),  # 買いで損切りが上
        Order("7203", "sell", 1, Decimal(1000), Decimal(900)),  # 売りで損切りが下
        Order("7203", "hold", 1, Decimal(1000), Decimal(900)),
    ],
)
def test_invalid_orders_are_rejected(order):
    assert not make().check(order).accepted


def test_sell_short_loss_uses_stop_above():
    d = make().check(Order("AAPL", "sell", 10, Decimal(1000), Decimal(1100)))  # 損失 1,000
    assert d.accepted, d.reason


def test_check_refuses_in_live_mode(monkeypatch):
    from trading.safety import LiveTradingForbiddenError

    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(LiveTradingForbiddenError):
        make().check(buy())
