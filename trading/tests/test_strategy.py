import datetime as dt
from decimal import Decimal as D

import pytest

from trading.broker import Bar
from trading.strategy import StrategyParams, atr, evaluate, required_history, sma

P = StrategyParams(trend_window=10, breakout_window=5, exit_window=5, atr_window=3)


def series(closes, spread=1):
    start = dt.date(2026, 1, 1)
    return [
        Bar(start + dt.timedelta(days=i), D(c), D(c) + spread, D(c) - spread, D(c)) for i, c in enumerate(closes)
    ]


def test_sma_and_atr():
    assert sma([D(1), D(2), D(3)], 2) == D("2.5")
    bars = series([10, 10, 10, 10])
    assert atr(bars, 3) == D(2)
    with pytest.raises(ValueError):
        sma([D(1)], 2)


def test_not_enough_history_gives_no_signal():
    assert evaluate(series(range(1, 10)), holding=False, p=P) is None
    assert required_history(P) == 10


def test_breakout_above_trend_enters_with_atr_stop():
    s = evaluate(series(range(1, 21)), holding=False, p=P)
    assert s is not None and s.action == "enter"
    assert s.stop_distance == D(2) * D(2)  # ATR 2（高安差 2）× 2


def test_no_entry_below_trend():
    assert evaluate(series(list(range(30, 10, -1))), holding=False, p=P) is None


def test_no_entry_without_breakout():
    closes = list(range(1, 20)) + [15]
    assert evaluate(series(closes), holding=False, p=P) is None


def test_exit_when_close_below_exit_average():
    closes = list(range(1, 20)) + [10]
    s = evaluate(series(closes), holding=True, p=P)
    assert s is not None and s.action == "exit"


def test_hold_while_above_exit_average():
    assert evaluate(series(range(1, 21)), holding=True, p=P) is None


def test_uses_only_past_data():
    """最終日より後のデータを渡さない限り、結果は最終日までのデータだけで決まる。"""
    full = series(list(range(1, 21)) + [5, 5, 5])
    assert evaluate(full[:20], holding=False, p=P) == evaluate(series(range(1, 21)), holding=False, p=P)
