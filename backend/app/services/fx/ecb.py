"""ECB daily FX rates via the Frankfurter API (free, no API key).

Frankfurter (https://api.frankfurter.app) serves ECB reference rates. We
request one day + currency pair, cache the result, and reuse the cache on
subsequent lookups. The httpx client is injectable so tests can mock it.
"""

from datetime import date
from decimal import Decimal

import httpx

from app.services.fx.cache import FxRateCache
from app.services.fx.provider import FxRateProvider

_BASE_URL = "https://api.frankfurter.app"


class EcbFxProvider(FxRateProvider):
    def __init__(
        self, cache: FxRateCache, client: httpx.Client | None = None
    ) -> None:
        self._cache = cache
        self._client = client or httpx.Client()

    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        if currency == "USD":
            return Decimal("1")
        cached = self._cache.get(currency, on_date)
        if cached is not None:
            return cached
        response = self._client.get(
            f"{_BASE_URL}/{on_date.isoformat()}",
            params={"base": currency, "symbols": "USD"},
        )
        response.raise_for_status()
        rates = response.json().get("rates", {})
        if "USD" not in rates:
            return None
        rate = Decimal(str(rates["USD"]))
        self._cache.put(currency, on_date, rate)
        return rate
