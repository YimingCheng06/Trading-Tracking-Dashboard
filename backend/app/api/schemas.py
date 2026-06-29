"""Pydantic response models for the HTTP API."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class AccountOut(BaseModel):
    broker_account_id: str
    name: str
    base_currency: str
    broker: str


class AppendCountOut(BaseModel):
    added: int
    skipped: int


class AccountImportOut(BaseModel):
    broker_account_id: str
    instruments: AppendCountOut
    trades: AppendCountOut
    cash_flows: AppendCountOut
    corporate_actions: AppendCountOut


class UploadReportOut(BaseModel):
    accounts: list[AccountImportOut]


class PositionOut(BaseModel):
    symbol: str
    quantity: Decimal
    cost_basis: Decimal
    average_cost: Decimal
    market_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None


class TradeOut(BaseModel):
    trade_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    proceeds_usd: Decimal
    commission_usd: Decimal
    realized_pnl_ibkr: Decimal | None
    executed_at: datetime


class PnlOut(BaseModel):
    realized_pnl: Decimal
    open_position_count: int
    base_currency: str


class CurvePointOut(BaseModel):
    on_date: date
    cumulative_pnl: Decimal
    pct: Decimal | None


class RefreshResultOut(BaseModel):
    broker_account_id: str
    snapshot_rows: int


class LiveSnapshotOut(BaseModel):
    fetched_at: datetime
    positions: list[PositionOut]
    curve_tail: CurvePointOut
