from datetime import date
from decimal import Decimal

import pytest

from app.services.providers.base import MarketDataProvider
from app.services.providers.yahoo import YahooFinanceProvider


def test_market_data_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        MarketDataProvider()


def test_market_data_provider_subclass_must_implement_all_methods():
    class Incomplete(MarketDataProvider):
        def get_daily_closes(self, symbol, start, end):
            return {}

        def get_latest_close(self, symbol):
            return None

    with pytest.raises(TypeError):
        Incomplete()  # get_latest_closes still abstract


def test_market_data_provider_complete_subclass_works():
    class Complete(MarketDataProvider):
        def get_daily_closes(self, symbol, start, end):
            return {date(2026, 1, 2): Decimal("10")}

        def get_latest_close(self, symbol):
            return Decimal("10")

        def get_latest_closes(self, symbols):
            return {s: Decimal("10") for s in symbols}

    provider = Complete()
    assert provider.get_latest_close("X") == Decimal("10")
    assert provider.get_latest_closes(["X", "Y"]) == {
        "X": Decimal("10"),
        "Y": Decimal("10"),
    }


def _fake_history(closes):
    """Build a history_fn that ignores dates and returns `closes`."""
    def history_fn(symbol, start, end):
        return dict(closes)
    return history_fn


def test_yahoo_get_daily_closes_delegates_to_history_fn():
    closes = {date(2026, 1, 2): Decimal("100"), date(2026, 1, 3): Decimal("101")}
    provider = YahooFinanceProvider(history_fn=_fake_history(closes))
    assert provider.get_daily_closes("AAPL", date(2026, 1, 1), date(2026, 1, 5)) == closes


def test_yahoo_get_latest_close_returns_most_recent():
    closes = {date(2026, 1, 2): Decimal("100"), date(2026, 1, 5): Decimal("103")}
    provider = YahooFinanceProvider(history_fn=_fake_history(closes))
    assert provider.get_latest_close("AAPL") == Decimal("103")


def test_yahoo_get_latest_close_none_when_empty():
    provider = YahooFinanceProvider(history_fn=_fake_history({}))
    assert provider.get_latest_close("AAPL") is None


def _fake_closes(by_symbol):
    """Build a closes_fn that returns the pre-baked {symbol: Decimal} dict."""
    def closes_fn(symbols):
        return {s: by_symbol[s] for s in symbols if s in by_symbol}
    return closes_fn


def test_yahoo_get_latest_closes_returns_one_per_symbol():
    provider = YahooFinanceProvider(
        closes_fn=_fake_closes(
            {"AAPL": Decimal("190.50"), "TSLA": Decimal("250.00")}
        )
    )
    result = provider.get_latest_closes(["AAPL", "TSLA"])
    assert result == {"AAPL": Decimal("190.50"), "TSLA": Decimal("250.00")}


def test_yahoo_get_latest_closes_skips_missing_symbols():
    provider = YahooFinanceProvider(
        closes_fn=_fake_closes({"AAPL": Decimal("190.50")})
    )
    result = provider.get_latest_closes(["AAPL", "UNKNOWN"])
    assert result == {"AAPL": Decimal("190.50")}
    assert "UNKNOWN" not in result


def test_yahoo_get_latest_closes_empty_list():
    provider = YahooFinanceProvider(closes_fn=_fake_closes({}))
    assert provider.get_latest_closes([]) == {}
