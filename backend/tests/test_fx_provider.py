from datetime import date
from decimal import Decimal

import pytest

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
