from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services.fx.cache import FxRateCache
from app.services.fx.ecb import EcbFxProvider
from app.services.fx.provider import ChainedFxProvider, StatementFxProvider, convert_to_usd


def test_statement_provider_returns_known_rate():
    provider = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    assert provider.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_statement_provider_usd_is_one():
    provider = StatementFxProvider({})
    assert provider.get_rate("USD", date(2026, 1, 15)) == Decimal("1")


def test_statement_provider_unknown_returns_none():
    provider = StatementFxProvider({})
    assert provider.get_rate("EUR", date(2026, 1, 15)) is None


def test_chained_returns_first_non_none():
    primary = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    fallback = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("9.99")})
    chain = ChainedFxProvider([primary, fallback])

    assert chain.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_chained_falls_through_to_next_provider():
    primary = StatementFxProvider({})  # has nothing
    fallback = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    chain = ChainedFxProvider([primary, fallback])

    assert chain.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_chained_returns_none_when_no_provider_has_rate():
    chain = ChainedFxProvider([StatementFxProvider({}), StatementFxProvider({})])
    assert chain.get_rate("EUR", date(2026, 1, 15)) is None


def test_convert_to_usd_multiplies_by_rate():
    provider = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    usd = convert_to_usd(Decimal("100"), "EUR", date(2026, 1, 15), provider)
    assert usd == Decimal("108.00")


def test_convert_to_usd_raises_when_no_rate():
    provider = StatementFxProvider({})
    with pytest.raises(ValueError, match="EUR"):
        convert_to_usd(Decimal("100"), "EUR", date(2026, 1, 15), provider)


def _mock_ecb_client(rate: float):
    def handler(request):
        return httpx.Response(
            200, json={"base": "EUR", "date": "2026-01-15", "rates": {"USD": rate}}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_chain_prefers_statement_over_ecb(tmp_path):
    statement = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    ecb = EcbFxProvider(
        FxRateCache(tmp_path / "fx.csv"), client=_mock_ecb_client(9.99)
    )
    chain = ChainedFxProvider([statement, ecb])

    # Statement has the rate, so ECB's 9.99 is never used.
    assert chain.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_chain_falls_back_to_ecb_when_statement_lacks_rate(tmp_path):
    statement = StatementFxProvider({})  # no rates
    ecb = EcbFxProvider(
        FxRateCache(tmp_path / "fx.csv"), client=_mock_ecb_client(1.08)
    )
    chain = ChainedFxProvider([statement, ecb])

    usd = convert_to_usd(Decimal("100"), "EUR", date(2026, 1, 15), chain)
    assert usd == Decimal("108.00")
