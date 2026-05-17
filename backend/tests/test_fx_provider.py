from datetime import date
from decimal import Decimal

from app.services.fx.provider import StatementFxProvider


def test_statement_provider_returns_known_rate():
    provider = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    assert provider.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_statement_provider_usd_is_one():
    provider = StatementFxProvider({})
    assert provider.get_rate("USD", date(2026, 1, 15)) == Decimal("1")


def test_statement_provider_unknown_returns_none():
    provider = StatementFxProvider({})
    assert provider.get_rate("EUR", date(2026, 1, 15)) is None
