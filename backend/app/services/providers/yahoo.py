"""Yahoo Finance market data via yfinance (free, no API key, ~15-20 min delay).

The yfinance network calls are isolated in `_yfinance_history` and
`_yfinance_latest_closes` so the rest of the provider is pure and testable;
`YahooFinanceProvider` takes injectable `history_fn` / `closes_fn` so tests
run offline.
"""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from app.services.providers.base import MarketDataProvider

HistoryFn = Callable[[str, date, date], dict[date, Decimal]]
ClosesFn = Callable[[list[str]], dict[str, Decimal]]


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


def _yfinance_latest_closes(symbols: list[str]) -> dict[str, Decimal]:
    """One batched HTTP call: last 5d of closes per symbol, pick the most recent."""
    if not symbols:
        return {}
    import yfinance

    frame = yfinance.download(
        tickers=" ".join(symbols),
        period="5d",
        auto_adjust=True,
        group_by="ticker",
        progress=False,
        threads=False,
    )
    out: dict[str, Decimal] = {}
    if len(symbols) == 1:
        closes = frame["Close"].dropna()
        if not closes.empty:
            out[symbols[0]] = Decimal(str(closes.iloc[-1]))
    else:
        for s in symbols:
            try:
                closes = frame[s]["Close"].dropna()
            except (KeyError, AttributeError):
                continue
            if not closes.empty:
                out[s] = Decimal(str(closes.iloc[-1]))
    return out


class YahooFinanceProvider(MarketDataProvider):
    def __init__(
        self,
        history_fn: HistoryFn | None = None,
        closes_fn: ClosesFn | None = None,
    ) -> None:
        self._history_fn = history_fn or _yfinance_history
        self._closes_fn = closes_fn or _yfinance_latest_closes

    def get_daily_closes(
        self, symbol: str, start: date, end: date
    ) -> dict[date, Decimal]:
        return self._history_fn(symbol, start, end)

    def get_latest_close(self, symbol: str) -> Decimal | None:
        today = date.today()
        closes = self._history_fn(symbol, today - timedelta(days=7), today)
        return closes[max(closes)] if closes else None

    def get_latest_closes(self, symbols: list[str]) -> dict[str, Decimal]:
        return self._closes_fn(symbols)
