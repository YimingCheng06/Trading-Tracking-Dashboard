"""Phase 1 core ORM models.

Six tables back the import + P&L pipeline: accounts, instruments, trades,
cash_flows, positions_snapshot, corporate_actions.

Money is stored twice where it matters — once in the trade's own currency and
once converted to USD — so P&L can be reported in a single currency without
re-deriving FX after the fact.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    OpenClose,
    OptionType,
    RecordSource,
    TradeSide,
)

# Numeric column shapes. Amounts/prices/quantities share one shape; FX rates
# get extra scale because cross-rates carry more significant digits.
_MONEY = Numeric(20, 6)
_FX = Numeric(20, 10)


class TimestampMixin:
    """created_at / updated_at maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ProvenanceMixin:
    """source / import_batch — 区分解析得来的行与用户手改/新增的行。"""

    source: Mapped[RecordSource] = mapped_column(default=RecordSource.PARSED)
    import_batch: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker_account_id: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    base_currency: Mapped[str] = mapped_column(String(3))
    broker: Mapped[str] = mapped_column(String(32), default="IBKR")

    trades: Mapped[list["Trade"]] = relationship(back_populates="account")
    cash_flows: Mapped[list["CashFlow"]] = relationship(back_populates="account")
    snapshots: Mapped[list["PositionSnapshot"]] = relationship(
        back_populates="account"
    )


class Instrument(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64))
    asset_class: Mapped[AssetClass] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3))
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    conid: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Options-only fields, reserved per locked decision #1. Null for stocks/ETFs.
    underlying_symbol: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    option_type: Mapped[OptionType | None] = mapped_column(nullable=True)
    strike: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    expiry: Mapped[date | None] = mapped_column(nullable=True)
    multiplier: Mapped[int] = mapped_column(default=1)

    trades: Mapped[list["Trade"]] = relationship(back_populates="instrument")
    cash_flows: Mapped[list["CashFlow"]] = relationship(
        back_populates="instrument"
    )
    snapshots: Mapped[list["PositionSnapshot"]] = relationship(
        back_populates="instrument"
    )
    corporate_actions: Mapped[list["CorporateAction"]] = relationship(
        back_populates="instrument"
    )


class Trade(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "trades"
    # Same broker execution can never land twice for one account — the import
    # de-duplication guarantee, enforced at the database level.
    __table_args__ = (
        UniqueConstraint("account_id", "trade_id", name="uq_trade_account_exec"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))

    # Broker execution id — basis for import de-duplication.
    trade_id: Mapped[str] = mapped_column(String(64))
    side: Mapped[TradeSide] = mapped_column()
    open_close: Mapped[OpenClose | None] = mapped_column(nullable=True)

    quantity: Mapped[Decimal] = mapped_column(_MONEY)
    price: Mapped[Decimal] = mapped_column(_MONEY)
    # Realized P&L as reported by IBKR — kept for cross-checking against the
    # self-built P&L engine.
    realized_pnl_ibkr: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)

    # Original trade currency plus its conversion into USD
    # (decision #2 — dual-currency storage; USD amounts NOT NULL).
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate_to_usd: Mapped[Decimal] = mapped_column(_FX)
    proceeds: Mapped[Decimal] = mapped_column(_MONEY)
    proceeds_usd: Mapped[Decimal] = mapped_column(_MONEY)
    commission: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    commission_usd: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))

    executed_at: Mapped[datetime] = mapped_column(DateTime)

    account: Mapped[Account] = relationship(back_populates="trades")
    instrument: Mapped[Instrument] = relationship(back_populates="trades")


class CashFlow(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "cash_flows"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    # Dividends/interest link to an instrument; deposits/withdrawals do not.
    instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id"), nullable=True
    )

    flow_type: Mapped[CashFlowType] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(_MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate_to_usd: Mapped[Decimal] = mapped_column(_FX)
    amount_usd: Mapped[Decimal] = mapped_column(_MONEY)

    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)

    account: Mapped[Account] = relationship(back_populates="cash_flows")
    instrument: Mapped[Instrument | None] = relationship(
        back_populates="cash_flows"
    )


class PositionSnapshot(TimestampMixin, Base):
    __tablename__ = "positions_snapshot"
    # One row per instrument per account per day — keeps the P&L time series
    # free of accidental duplicate snapshots.
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "instrument_id",
            "snapshot_date",
            name="uq_snapshot_account_instrument_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))

    snapshot_date: Mapped[date] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(_MONEY)
    avg_cost: Mapped[Decimal] = mapped_column(_MONEY)
    market_price: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    market_value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    market_value_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    unrealized_pnl_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)

    account: Mapped[Account] = relationship(back_populates="snapshots")
    instrument: Mapped[Instrument] = relationship(back_populates="snapshots")


class CorporateAction(ProvenanceMixin, TimestampMixin, Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))

    action_type: Mapped[CorporateActionType] = mapped_column()
    ex_date: Mapped[date] = mapped_column()
    ratio: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    instrument: Mapped[Instrument] = relationship(
        back_populates="corporate_actions"
    )
