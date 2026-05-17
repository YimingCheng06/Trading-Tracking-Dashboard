from datetime import date
from decimal import Decimal

from app.services.fx.factory import build_fx_provider
from app.services.fx.provider import ChainedFxProvider


def test_build_fx_provider_returns_a_chain():
    assert isinstance(build_fx_provider(), ChainedFxProvider)


def test_build_fx_provider_uses_statement_rates_first():
    # A supplied statement rate is used directly — no network, no ECB call.
    provider = build_fx_provider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    assert provider.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_build_fx_provider_usd_is_one():
    # USD short-circuits in the statement provider — no network.
    assert build_fx_provider().get_rate("USD", date(2026, 1, 15)) == Decimal("1")
