"""Market-data provider interface.

A MarketDataProvider answers price questions for a symbol. Implementations
(Yahoo now, IBKR later) sit behind this so the snapshot builder does not
care where prices come from. All prices are USD Decimals.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class LiveQuotes:
    """Aggregate answer for one live-snapshot request."""

    closes: dict[str, Decimal]
    option_marks: dict[str, Decimal] = field(default_factory=dict)
    source: Literal["ibkr", "yahoo"] = "yahoo"


class MarketDataProvider(ABC):
    @abstractmethod
    def get_daily_closes(
        self, symbol: str, start: date, end: date
    ) -> dict[date, Decimal]:
        """Daily close prices for `symbol` over [start, end] inclusive.

        Non-trading days are simply absent from the result.
        """

    @abstractmethod
    def get_latest_close(self, symbol: str) -> Decimal | None:
        """The most recent close price, or None if unavailable."""

    @abstractmethod
    def get_latest_closes(self, symbols: list[str]) -> dict[str, Decimal]:
        """Latest close price for each symbol — one batch call.

        Symbols with no available data are simply absent from the result;
        the caller decides whether that is fatal.
        """

    def get_live_quotes(
        self, equity: dict[str, int | None], options: dict[str, int]
    ) -> LiveQuotes:
        """Live-path aggregate: equity closes + option marks + source label.

        `equity` maps symbol -> known IBKR conid (or None); `options` maps
        option symbol -> conid. Default implementation: latest closes from
        this provider, no option marks — delayed-data behaviour. The chained
        provider overrides this with the IBKR-first logic.
        """
        return LiveQuotes(closes=self.get_latest_closes(list(equity)))
