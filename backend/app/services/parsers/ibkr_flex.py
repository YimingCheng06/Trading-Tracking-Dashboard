"""Parse an IBKR Flex Query CSV into ledger row models.

A Flex export stacks three sections in one file — Trades, Corporate
Actions, Cash Transactions — each opening with its own header row whose
first cell is "ClientAccountID". `parse_flex_csv` splits the sections and
maps each to the M2 `Ledger*` row models; `import_statement` appends them
to an `AccountLedger`, deduplicated so re-importing a statement is a no-op.
No DB access — the M3 projection builder rebuilds the DB from the ledger.
"""

import hashlib
from datetime import datetime
from decimal import Decimal


def _split_sections(
    rows: list[list[str]],
) -> list[tuple[list[str], list[list[str]]]]:
    """Split stacked CSV rows into (header, data_rows) groups.

    A header row is any row whose first cell is "ClientAccountID". Blank
    rows are dropped.
    """
    sections: list[tuple[list[str], list[list[str]]]] = []
    header: list[str] | None = None
    data: list[list[str]] = []
    for row in rows:
        if row and row[0] == "ClientAccountID":
            if header is not None:
                sections.append((header, data))
            header, data = row, []
        elif row:
            data.append(row)
    if header is not None:
        sections.append((header, data))
    return sections


def _parse_dt(value: str) -> datetime:
    """Parse an IBKR datetime: '2026-03-26;15:30:58 EDT' or '2025-11-21'.

    The timezone abbreviation is dropped — every timestamp in a statement
    is US/Eastern wall-clock, so naive datetimes order correctly.
    """
    value = value.strip()
    if ";" in value:
        date_part, rest = value.split(";", 1)
        time_part = rest.strip().split(" ")[0]
        return datetime.fromisoformat(f"{date_part}T{time_part}")
    return datetime.fromisoformat(value)


def _dec(value: str | None) -> Decimal | None:
    """Parse a CSV cell to Decimal; blank/None becomes None."""
    if value is None or value.strip() == "":
        return None
    return Decimal(value.strip())


def _content_hash(*parts: object) -> str:
    """Stable 16-hex-char id from the given parts (synthetic row id)."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]
