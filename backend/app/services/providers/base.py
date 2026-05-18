"""Market-data provider interface.

A MarketDataProvider answers price questions for a symbol. Implementations
(Yahoo now, IBKR later) sit behind this so the snapshot builder does not
care where prices come from. All prices are USD Decimals.
"""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal


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
