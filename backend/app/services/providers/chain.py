"""Chained market-data provider: IBKR CP Gateway first, Yahoo fallback.

Live path only — history always goes straight to Yahoo. The IBKR leg is
consulted per request (`available()` probes the Gateway's auth status); any
exception from the IBKR leg mid-flight falls back to the Yahoo path, so the
live-snapshot endpoint never breaks because the Gateway went away.
"""

import logging
from datetime import date
from decimal import Decimal

from app.services.providers.base import LiveQuotes, MarketDataProvider
from app.services.providers.ibkr_cp import IBKRClientPortalProvider
from app.services.providers.yahoo import YahooFinanceProvider

logger = logging.getLogger(__name__)


class ChainedMarketDataProvider(MarketDataProvider):
    def __init__(
        self, ibkr: IBKRClientPortalProvider, yahoo: YahooFinanceProvider
    ) -> None:
        self._ibkr = ibkr
        self._yahoo = yahoo

    # -- live path ---------------------------------------------------------

    def get_live_quotes(
        self, equity: dict[str, int | None], options: dict[str, int]
    ) -> LiveQuotes:
        if self._ibkr.available():
            try:
                return self._live_from_ibkr(equity, options)
            except Exception:
                logger.exception(
                    "IBKR live quotes failed mid-flight; falling back to Yahoo"
                )
        return LiveQuotes(closes=self._yahoo.get_latest_closes(list(equity)))

    def _live_from_ibkr(
        self, equity: dict[str, int | None], options: dict[str, int]
    ) -> LiveQuotes:
        symbol_conids = self._ibkr.resolve_equity_conids(equity)
        closes = self._ibkr.get_equity_closes(symbol_conids)
        missing = [s for s in equity if s not in closes]
        if missing:
            closes = {**closes, **self._yahoo.get_latest_closes(missing)}
        return LiveQuotes(
            closes=closes,
            option_marks=self._ibkr.get_option_marks(options),
            source="ibkr",
        )

    # -- history: always Yahoo ----------------------------------------------

    def get_daily_closes(
        self, symbol: str, start: date, end: date
    ) -> dict[date, Decimal]:
        return self._yahoo.get_daily_closes(symbol, start, end)

    def get_latest_close(self, symbol: str) -> Decimal | None:
        return self._yahoo.get_latest_close(symbol)

    def get_latest_closes(self, symbols: list[str]) -> dict[str, Decimal]:
        return self._yahoo.get_latest_closes(symbols)
