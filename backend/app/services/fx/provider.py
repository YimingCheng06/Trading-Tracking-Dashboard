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


class ChainedFxProvider(FxRateProvider):
    """Tries each provider in order, returning the first non-None rate."""

    def __init__(self, providers: list[FxRateProvider]) -> None:
        self._providers = providers

    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        for provider in self._providers:
            rate = provider.get_rate(currency, on_date)
            if rate is not None:
                return rate
        return None


def convert_to_usd(
    amount: Decimal,
    currency: str,
    on_date: date,
    provider: FxRateProvider,
) -> Decimal:
    """Convert `amount` in `currency` on `on_date` to USD.

    Raises ValueError if the provider has no rate for that currency/date.
    """
    rate = provider.get_rate(currency, on_date)
    if rate is None:
        raise ValueError(f"no FX rate for {currency} on {on_date.isoformat()}")
    return amount * rate
