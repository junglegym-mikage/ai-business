import pytest

from trading.safety import LiveTradingForbiddenError, assert_paper_mode, trading_mode


def test_default_is_paper(monkeypatch):
    monkeypatch.delenv("TRADING_MODE", raising=False)
    assert trading_mode() == "paper"
    assert_paper_mode()


@pytest.mark.parametrize("value", ["live", "LIVE", "real", "production", ""])
def test_anything_but_paper_is_rejected(monkeypatch, value):
    monkeypatch.setenv("TRADING_MODE", value)
    with pytest.raises(LiveTradingForbiddenError):
        assert_paper_mode()


def test_paper_with_whitespace_and_case(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "  Paper ")
    assert trading_mode() == "paper"
