from datetime import date
from decimal import Decimal

import httpx

from app.services.fx.cache import FxRateCache
from app.services.fx.ecb import EcbFxProvider


def _client(handler) -> httpx.Client:
    """An httpx.Client whose requests are served by `handler` (no network)."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ecb_usd_is_one(tmp_path):
    provider = EcbFxProvider(
        FxRateCache(tmp_path / "fx.csv"),
        client=_client(lambda r: httpx.Response(500)),
    )
    assert provider.get_rate("USD", date(2026, 1, 15)) == Decimal("1")


def test_ecb_fetches_rate(tmp_path):
    def handler(request):
        return httpx.Response(
            200, json={"base": "EUR", "date": "2026-01-15", "rates": {"USD": 1.08}}
        )

    provider = EcbFxProvider(FxRateCache(tmp_path / "fx.csv"), client=_client(handler))
    assert provider.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_ecb_second_call_uses_cache_no_http(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(
            200, json={"base": "EUR", "date": "2026-01-15", "rates": {"USD": 1.08}}
        )

    provider = EcbFxProvider(FxRateCache(tmp_path / "fx.csv"), client=_client(handler))
    provider.get_rate("EUR", date(2026, 1, 15))
    provider.get_rate("EUR", date(2026, 1, 15))  # second call

    assert len(calls) == 1  # only the first call hit HTTP


def test_ecb_returns_none_when_response_lacks_usd(tmp_path):
    def handler(request):
        return httpx.Response(
            200, json={"base": "EUR", "date": "2026-01-15", "rates": {}}
        )

    provider = EcbFxProvider(FxRateCache(tmp_path / "fx.csv"), client=_client(handler))
    assert provider.get_rate("EUR", date(2026, 1, 15)) is None
