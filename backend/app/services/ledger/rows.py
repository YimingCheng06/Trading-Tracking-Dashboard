"""Pydantic models for one row of each CSV ledger file.

Field declaration order IS the CSV column order; `source` / `import_batch`
lead every file. `dedup_key` returns the hashable identity used to skip
re-importing a row that is already in the ledger.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    OpenClose,
    OptionType,
    RecordSource,
    TradeSide,
)


class LedgerInstrument(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    symbol: str
    asset_class: AssetClass
    currency: str
    exchange: str | None = None
    name: str | None = None
    conid: str | None = None
    underlying_symbol: str | None = None
    option_type: OptionType | None = None
    strike: Decimal | None = None
    expiry: date | None = None
    multiplier: int = 1

    @property
    def dedup_key(self) -> tuple:
        return (
            self.symbol,
            self.asset_class,
            self.strike,
            self.expiry,
            self.option_type,
        )


class LedgerTrade(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    trade_id: str
    instrument: str
    side: TradeSide
    open_close: OpenClose | None = None
    quantity: Decimal
    price: Decimal
    currency: str
    fx_rate_to_usd: Decimal
    proceeds_orig: Decimal
    proceeds_usd: Decimal
    commission_orig: Decimal = Decimal("0")
    commission_usd: Decimal = Decimal("0")
    realized_pnl_ibkr: Decimal | None = None
    executed_at: datetime

    @property
    def dedup_key(self) -> tuple:
        return (self.trade_id,)


class LedgerCashFlow(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    flow_type: CashFlowType
    instrument: str | None = None
    currency: str
    fx_rate_to_usd: Decimal
    amount_orig: Decimal
    amount_usd: Decimal
    description: str | None = None
    external_id: str | None = None
    occurred_at: datetime

    @property
    def dedup_key(self) -> tuple:
        if self.external_id not in (None, ""):
            return (self.external_id,)
        return (self.flow_type, self.occurred_at, self.amount_orig)


class LedgerCorporateAction(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    instrument: str
    action_type: CorporateActionType
    ex_date: date
    ratio: Decimal | None = None
    description: str | None = None
    external_id: str | None = None

    @property
    def dedup_key(self) -> tuple:
        return (self.instrument, self.action_type, self.ex_date)


class LedgerAccount(BaseModel):
    """Mirrors account.toml — account metadata, no CSV / dedup."""

    broker_account_id: str
    name: str
    base_currency: str
    broker: str = "IBKR"
