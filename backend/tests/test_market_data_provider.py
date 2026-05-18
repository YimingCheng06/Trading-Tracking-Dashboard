from datetime import date
from decimal import Decimal

import pytest

from app.services.providers.base import MarketDataProvider


def test_market_data_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        MarketDataProvider()


def test_market_data_provider_subclass_must_implement_both_methods():
    class Incomplete(MarketDataProvider):
        def get_daily_closes(self, symbol, start, end):
            return {}

    with pytest.raises(TypeError):
        Incomplete()  # get_latest_close still abstract


def test_market_data_provider_complete_subclass_works():
    class Complete(MarketDataProvider):
        def get_daily_closes(self, symbol, start, end):
            return {date(2026, 1, 2): Decimal("10")}

        def get_latest_close(self, symbol):
            return Decimal("10")

    provider = Complete()
    assert provider.get_latest_close("X") == Decimal("10")
