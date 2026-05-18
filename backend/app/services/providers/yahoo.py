"""Yahoo Finance market data via yfinance (free, no API key, ~15-20 min delay).

The yfinance network call is isolated in `_yfinance_history` so the rest of
the provider is pure and testable; `YahooFinanceProvider` takes an injectable
`history_fn` so tests run offline.
"""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from app.services.providers.base import MarketDataProvider

HistoryFn = Callable[[str, date, date], dict[date, Decimal]]


def _yfinance_history(symbol: str, start: date, end: date) -> dict[date, Decimal]:
    """Fetch daily closes from Yahoo via yfinance — the one real network call."""
    import yfinance

    # yfinance treats `end` as exclusive, so add a day to include it.
    frame = yfinance.Ticker(symbol).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=True,
    )
    closes: dict[date, Decimal] = {}
    for timestamp, close in frame["Close"].items():
        closes[timestamp.date()] = Decimal(str(close))
    return closes


class YahooFinanceProvider(MarketDataProvider):
    def __init__(self, history_fn: HistoryFn | None = None) -> None:
        self._history_fn = history_fn or _yfinance_history

    def get_daily_closes(
        self, symbol: str, start: date, end: date
    ) -> dict[date, Decimal]:
        return self._history_fn(symbol, start, end)

    def get_latest_close(self, symbol: str) -> Decimal | None:
        today = date.today()
        closes = self._history_fn(symbol, today - timedelta(days=7), today)
        return closes[max(closes)] if closes else None
