"""FX rate providers — convert a non-USD amount to USD.

A FxRateProvider answers: "what rate do I multiply an amount in `currency`
on `on_date` by to get USD?" USD is always 1. A provider returns None when
it has no rate, so providers can be chained by priority.
"""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal


class FxRateProvider(ABC):
    @abstractmethod
    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        """Rate to multiply a `currency` amount by to get USD, or None."""


class StatementFxProvider(FxRateProvider):
    """In-memory provider backed by a fixed {(currency, date): rate} map.

    The IBKR statement parser (a later milestone) seeds this with the FX
    rates the statement itself reports.
    """

    def __init__(self, rates: dict[tuple[str, date], Decimal]) -> None:
        self._rates = rates

    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        if currency == "USD":
            return Decimal("1")
        return self._rates.get((currency, on_date))
