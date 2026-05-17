"""CSV cache of fetched FX rates — data/fx_rates.csv.

Columns: date, base, quote, rate. `quote` is always USD in Phase 1. The
cache only accelerates repeated lookups; it is never a source of truth —
the rate actually applied to a ledger row is recorded on that row.
"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

_FIELDNAMES = ["date", "base", "quote", "rate"]


class FxRateCache:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, currency: str, on_date: date) -> Decimal | None:
        if not self.path.exists():
            return None
        with self.path.open(newline="") as f:
            for row in csv.DictReader(f):
                if (
                    row["base"] == currency
                    and row["quote"] == "USD"
                    and row["date"] == on_date.isoformat()
                ):
                    return Decimal(row["rate"])
        return None

    def put(self, currency: str, on_date: date, rate: Decimal) -> None:
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerow(
                {
                    "date": on_date.isoformat(),
                    "base": currency,
                    "quote": "USD",
                    "rate": str(rate),
                }
            )
