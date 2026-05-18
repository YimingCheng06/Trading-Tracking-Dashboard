"""Parse an IBKR Flex Query CSV into ledger row models.

A Flex export stacks three sections in one file — Trades, Corporate
Actions, Cash Transactions — each opening with its own header row whose
first cell is "ClientAccountID". `parse_flex_csv` splits the sections and
maps each to the M2 `Ledger*` row models; `import_statement` appends them
to an `AccountLedger`, deduplicated so re-importing a statement is a no-op.
No DB access — the M3 projection builder rebuilds the DB from the ledger.
"""

import hashlib
from datetime import date, datetime
from decimal import Decimal

from app.db.enums import AssetClass, OptionType, TradeSide
from app.services.ledger.rows import LedgerInstrument, LedgerTrade

_ASSET_CLASS = {"STK": AssetClass.STOCK, "OPT": AssetClass.OPTION}
_OPTION_TYPE = {"P": OptionType.PUT, "C": OptionType.CALL}


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


def _parse_trades(
    rows: list[dict[str, str]],
) -> tuple[list[LedgerInstrument], list[LedgerTrade], dict[tuple[str, date], Decimal]]:
    """Map Trades-section rows to instruments + trades + statement FX rates.

    `CASH` rows are forex conversions: they yield no trade, only a
    {(currency, date): rate} entry (CAD->USD rate = 1 / USD.CAD price).
    Raises ValueError on an unknown AssetClass.
    """
    instruments: dict[str, LedgerInstrument] = {}
    trades: list[LedgerTrade] = []
    fx_rates: dict[tuple[str, date], Decimal] = {}

    for row in rows:
        asset = row["AssetClass"]
        if asset == "CASH":
            left, right = row["Symbol"].split(".")
            price = Decimal(row["TradePrice"])
            on = date.fromisoformat(row["TradeDate"])
            if left == "USD":
                fx_rates[(right, on)] = Decimal("1") / price
            elif right == "USD":
                fx_rates[(left, on)] = price
            continue
        if asset not in _ASSET_CLASS:
            raise ValueError(f"unknown trade AssetClass {asset!r}: {row}")
        asset_class = _ASSET_CLASS[asset]
        symbol = row["Symbol"]
        is_option = asset_class is AssetClass.OPTION
        instruments.setdefault(
            symbol,
            LedgerInstrument(
                symbol=symbol,
                asset_class=asset_class,
                currency=row["CurrencyPrimary"],
                conid=row["Conid"] or None,
                underlying_symbol=symbol.split()[0] if is_option else None,
                option_type=_OPTION_TYPE[row["Put/Call"]] if is_option else None,
                strike=_dec(row["Strike"]) if is_option else None,
                expiry=date.fromisoformat(row["Expiry"]) if is_option else None,
                multiplier=100 if is_option else 1,
            ),
        )
        proceeds = abs(Decimal(row["TradeMoney"]))
        commission = abs(_dec(row["IBCommission"]) or Decimal("0"))
        trades.append(
            LedgerTrade(
                trade_id=row.get("IBExecID")
                or _content_hash(
                    row["Conid"],
                    row["DateTime"],
                    row["Quantity"],
                    row["TradePrice"],
                    row["TradeMoney"],
                    row["IBCommission"],
                ),
                instrument=symbol,
                side=TradeSide.BUY if row["Buy/Sell"] == "BUY" else TradeSide.SELL,
                quantity=abs(Decimal(row["Quantity"])),
                price=Decimal(row["TradePrice"]),
                currency=row["CurrencyPrimary"],
                fx_rate_to_usd=Decimal("1"),
                proceeds_orig=proceeds,
                proceeds_usd=proceeds,
                commission_orig=commission,
                commission_usd=commission,
                realized_pnl_ibkr=_dec(row["FifoPnlRealized"]),
                executed_at=_parse_dt(row["DateTime"]),
            )
        )
    return list(instruments.values()), trades, fx_rates
