"""Parse an IBKR Flex Query CSV into ledger row models.

A Flex export stacks three sections in one file — Trades, Corporate
Actions, Cash Transactions — each opening with its own header row whose
first cell is "ClientAccountID". `parse_flex_csv` splits the sections and
maps each to the M2 `Ledger*` row models; `import_statement` appends them
to an `AccountLedger`, deduplicated so re-importing a statement is a no-op.
No DB access — the M3 projection builder rebuilds the DB from the ledger.
"""

import csv
import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.db.enums import AssetClass, CashFlowType, CorporateActionType, OptionType, TradeSide
from app.services.fx.factory import build_fx_provider
from app.services.fx.provider import FxRateProvider
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import (
    LedgerCashFlow,
    LedgerCorporateAction,
    LedgerInstrument,
    LedgerTrade,
)
from app.services.ledger.table import AppendReport

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


# Cash Transaction `Type` -> CashFlowType. "Deposits/Withdrawals" is
# sign-dependent and handled separately. "Withholding Tax" maps to OTHER:
# CashFlowType.TAX was removed from scope; OTHER keeps the cash balance
# correct and the description preserves the original label.
_CASH_TYPE = {
    "Other Fees": CashFlowType.FEE,
    "Broker Interest Received": CashFlowType.INTEREST,
    "Dividends": CashFlowType.DIVIDEND,
    "Withholding Tax": CashFlowType.OTHER,
}


def _parse_cash(
    rows: list[dict[str, str]], fx_provider: FxRateProvider
) -> list[LedgerCashFlow]:
    """Map Cash Transactions rows to LedgerCashFlow.

    Non-USD amounts are converted to USD via `fx_provider`. Raises
    ValueError on an unknown `Type`.
    """
    flows: list[LedgerCashFlow] = []
    for row in rows:
        type_label = row["Type"]
        amount = Decimal(row["Amount"])
        if type_label == "Deposits/Withdrawals":
            flow_type = CashFlowType.DEPOSIT if amount > 0 else CashFlowType.WITHDRAWAL
        elif type_label in _CASH_TYPE:
            flow_type = _CASH_TYPE[type_label]
        else:
            raise ValueError(f"unknown cash Type {type_label!r}: {row}")

        currency = row["CurrencyPrimary"]
        occurred_at = _parse_dt(row["Date/Time"])
        if currency == "USD":
            rate = Decimal("1")
        else:
            rate = fx_provider.get_rate(currency, occurred_at.date())
            if rate is None:
                raise ValueError(f"no FX rate for {currency} on {occurred_at.date()}")
        flows.append(
            LedgerCashFlow(
                flow_type=flow_type,
                instrument=row["Symbol"] or None,
                currency=currency,
                fx_rate_to_usd=rate,
                amount_orig=amount,
                amount_usd=amount * rate,
                description=type_label,
                external_id=_content_hash(
                    type_label, row["Date/Time"], row["Amount"], row["Symbol"]
                ),
                occurred_at=occurred_at,
            )
        )
    return flows


def _parse_corp(rows: list[dict[str, str]]) -> list[LedgerCorporateAction]:
    """Map Corporate Actions rows to LedgerCorporateAction.

    Rows sharing a Date/Time form one event. The supported pattern is a
    symbol change: a `<ticker>.OLD` row (negative quantity) paired with
    the new ticker (positive quantity). Raises ValueError on any other
    shape — unrecognised corporate actions are surfaced, not guessed.
    """
    by_time: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_time.setdefault(row["Date/Time"], []).append(row)

    actions: list[LedgerCorporateAction] = []
    for when, group in by_time.items():
        old = [r for r in group if r["Symbol"].endswith(".OLD")]
        new = [r for r in group if not r["Symbol"].endswith(".OLD")]
        if len(old) != 1 or len(new) != 1:
            raise ValueError(f"unrecognised corporate action group: {group}")
        old_row, new_row = old[0], new[0]
        old_qty = abs(Decimal(old_row["Quantity"]))
        new_qty = abs(Decimal(new_row["Quantity"]))
        actions.append(
            LedgerCorporateAction(
                instrument=new_row["Symbol"],
                action_type=CorporateActionType.SYMBOL_CHANGE,
                ex_date=_parse_dt(when).date(),
                ratio=new_qty / old_qty,
                description=(
                    f"{old_row['Symbol']} → {new_row['Symbol']} "
                    f"({old_qty}:{new_qty})"
                ),
                external_id=_content_hash(
                    old_row["Symbol"], new_row["Symbol"], when
                ),
            )
        )
    return actions


@dataclass(frozen=True)
class ParsedStatement:
    account_id: str
    instruments: list[LedgerInstrument]
    trades: list[LedgerTrade]
    cash_flows: list[LedgerCashFlow]
    corporate_actions: list[LedgerCorporateAction]


def parse_flex_csv(
    path: Path, *, fx_provider: FxRateProvider | None = None
) -> ParsedStatement:
    """Parse an IBKR Flex Query CSV into a ParsedStatement.

    `fx_provider` overrides FX resolution (used by tests to stay offline).
    When omitted, the provider chains the statement's own forex rates
    first, then ECB rates — see `build_fx_provider`.
    """
    with path.open(newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"{path} is empty")

    trades_rows: list[dict[str, str]] = []
    cash_rows: list[dict[str, str]] = []
    corp_rows: list[dict[str, str]] = []
    for header, data in _split_sections(rows):
        dicts = [dict(zip(header, r, strict=False)) for r in data]
        if "Buy/Sell" in header:
            trades_rows = dicts
        elif "Type" in header:
            cash_rows = dicts
        else:
            corp_rows = dicts

    # Account id comes from any section's first data row (column
    # "ClientAccountID") — robust against blank lines between sections.
    first_data = trades_rows or corp_rows or cash_rows
    account_id = first_data[0].get("ClientAccountID", "") if first_data else ""

    instruments, trades, statement_rates = _parse_trades(trades_rows)
    provider = fx_provider or build_fx_provider(statement_rates)
    cash_flows = _parse_cash(cash_rows, provider)
    corporate_actions = _parse_corp(corp_rows)
    return ParsedStatement(
        account_id=account_id,
        instruments=instruments,
        trades=trades,
        cash_flows=cash_flows,
        corporate_actions=corporate_actions,
    )


@dataclass(frozen=True)
class ImportReport:
    instruments: AppendReport
    trades: AppendReport
    cash_flows: AppendReport
    corporate_actions: AppendReport


def import_statement(
    path: Path,
    ledger: AccountLedger,
    *,
    fx_provider: FxRateProvider | None = None,
) -> ImportReport:
    """Parse a Flex CSV and append every row to `ledger`.

    Each `LedgerTable.append` deduplicates on the row's `dedup_key`, so
    re-importing the same statement adds nothing and never overwrites a
    row the user edited by hand.
    """
    parsed = parse_flex_csv(path, fx_provider=fx_provider)
    return ImportReport(
        instruments=ledger.instruments.append(parsed.instruments),
        trades=ledger.trades.append(parsed.trades),
        cash_flows=ledger.cash_flows.append(parsed.cash_flows),
        corporate_actions=ledger.corporate_actions.append(parsed.corporate_actions),
    )
