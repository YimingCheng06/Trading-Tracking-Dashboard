"""M3 projection builder — CSV ledger -> SQLite projection."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    TradeSide,
)
from app.db.models import Account, Instrument
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import (
    LedgerAccount,
    LedgerCashFlow,
    LedgerCorporateAction,
    LedgerInstrument,
    LedgerTrade,
)
from app.services.projection import builder

# --- shared test helpers --------------------------------------------------


def _ledger(tmp_path, broker_account_id="U1", name="Main"):
    return AccountLedger.create(
        tmp_path,
        LedgerAccount(
            broker_account_id=broker_account_id, name=name, base_currency="USD"
        ),
    )


def _li(symbol="AAPL", asset_class=AssetClass.STOCK, **kw):
    return LedgerInstrument(
        symbol=symbol, asset_class=asset_class, currency="USD", **kw
    )


def _lt(trade_id="T1", instrument="AAPL", **kw):
    fields = dict(
        trade_id=trade_id,
        instrument=instrument,
        side=TradeSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.25"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds_orig=Decimal("-1502.50"),
        proceeds_usd=Decimal("-1502.50"),
        executed_at=datetime(2026, 1, 5, 14, 30),
    )
    fields.update(kw)
    return LedgerTrade(**fields)


def _lc(flow_type=CashFlowType.DIVIDEND, instrument="AAPL", **kw):
    fields = dict(
        flow_type=flow_type,
        instrument=instrument,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("22.00"),
        amount_usd=Decimal("22.00"),
        occurred_at=datetime(2026, 2, 14, 0, 0),
    )
    fields.update(kw)
    return LedgerCashFlow(**fields)


def _lca(instrument="AAPL", **kw):
    fields = dict(
        instrument=instrument,
        action_type=CorporateActionType.SPLIT,
        ex_date=date(2024, 6, 10),
        ratio=Decimal("10"),
    )
    fields.update(kw)
    return LedgerCorporateAction(**fields)


# --- upsert_account -------------------------------------------------------


def test_upsert_account_creates(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    account = builder.upsert_account(db_session, ledger.read_account())

    assert account.id is not None
    assert account.broker_account_id == "U1"
    assert db_session.scalar(select(func.count()).select_from(Account)) == 1


def test_upsert_account_updates_existing(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    builder.upsert_account(db_session, ledger.read_account())
    # Second upsert with a changed name must update, not duplicate.
    again = builder.upsert_account(
        db_session, LedgerAccount(broker_account_id="U1", name="Renamed", base_currency="USD")
    )

    assert again.name == "Renamed"
    assert db_session.scalar(select(func.count()).select_from(Account)) == 1


# --- instruments ----------------------------------------------------------


def test_upsert_instrument_creates(db_session):
    inst = builder.upsert_instrument(db_session, _li("MSFT"))

    assert inst.id is not None
    assert inst.symbol == "MSFT"
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1


def test_upsert_instrument_updates_existing(db_session):
    builder.upsert_instrument(db_session, _li("AAPL", name="Apple Inc."))
    again = builder.upsert_instrument(db_session, _li("AAPL", name="Apple Corrected"))

    assert again.name == "Apple Corrected"
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1


def test_project_instruments_returns_symbol_map(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL"), _li("MSFT")])

    mapping = builder.project_instruments(db_session, ledger)

    assert set(mapping) == {"AAPL", "MSFT"}
    assert mapping["AAPL"].id is not None
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 2
