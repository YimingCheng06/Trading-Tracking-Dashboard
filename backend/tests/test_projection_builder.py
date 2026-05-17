"""M3 projection builder — CSV ledger -> SQLite projection."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    TradeSide,
)
from app.db.models import Account, CashFlow, CorporateAction, Instrument, Trade
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


# --- trades ---------------------------------------------------------------


def test_project_trades_inserts(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.trades.append([_lt("T1"), _lt("T2")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_trades(db_session, account, ledger, instruments)

    trades = db_session.scalars(select(Trade)).all()
    assert {t.trade_id for t in trades} == {"T1", "T2"}
    t1 = next(t for t in trades if t.trade_id == "T1")
    assert t1.account_id == account.id
    assert t1.instrument_id == instruments["AAPL"].id
    assert t1.proceeds == Decimal("-1502.50")  # mapped from proceeds_orig


def test_project_trades_replaces_existing(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.trades.append([_lt("T1")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_trades(db_session, account, ledger, instruments)
    # Project again — must replace, not duplicate.
    builder.project_trades(db_session, account, ledger, instruments)

    assert db_session.scalar(select(func.count()).select_from(Trade)) == 1


def test_project_trades_unknown_instrument_raises(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.trades.append([_lt("T1", instrument="GHOST")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)  # empty

    with pytest.raises(ValueError, match="GHOST"):
        builder.project_trades(db_session, account, ledger, instruments)


# --- cash flows -----------------------------------------------------------


def test_project_cash_flows_inserts(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.cash_flows.append([_lc(external_id="DIV-1")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_cash_flows(db_session, account, ledger, instruments)

    flow = db_session.scalars(select(CashFlow)).one()
    assert flow.account_id == account.id
    assert flow.instrument_id == instruments["AAPL"].id
    assert flow.amount == Decimal("22.00")  # mapped from amount_orig


def test_project_cash_flows_deposit_without_instrument(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.cash_flows.append(
        [
            _lc(
                flow_type=CashFlowType.DEPOSIT,
                instrument=None,
                amount_orig=Decimal("5000"),
                amount_usd=Decimal("5000"),
                external_id="DEP-1",
            )
        ]
    )

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_cash_flows(db_session, account, ledger, instruments)

    flow = db_session.scalars(select(CashFlow)).one()
    assert flow.instrument_id is None
    assert flow.amount == Decimal("5000")


# --- corporate actions ----------------------------------------------------


def test_project_corporate_actions_upserts(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.corporate_actions.append([_lca()])

    instruments = builder.project_instruments(db_session, ledger)
    builder.project_corporate_actions(db_session, ledger, instruments)

    ca = db_session.scalars(select(CorporateAction)).one()
    assert ca.instrument_id == instruments["AAPL"].id
    assert ca.action_type == CorporateActionType.SPLIT
    assert ca.ratio == Decimal("10")


def test_project_corporate_actions_idempotent(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.corporate_actions.append([_lca()])

    instruments = builder.project_instruments(db_session, ledger)
    builder.project_corporate_actions(db_session, ledger, instruments)
    builder.project_corporate_actions(db_session, ledger, instruments)

    assert (
        db_session.scalar(select(func.count()).select_from(CorporateAction)) == 1
    )


def test_project_corporate_actions_unknown_instrument_raises(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.corporate_actions.append([_lca(instrument="GHOST")])

    instruments = builder.project_instruments(db_session, ledger)  # empty

    with pytest.raises(ValueError, match="GHOST"):
        builder.project_corporate_actions(db_session, ledger, instruments)


# --- rebuild_account ------------------------------------------------------


def _populate(ledger):
    ledger.instruments.append([_li("AAPL")])
    ledger.trades.append([_lt("T1"), _lt("T2")])
    ledger.cash_flows.append([_lc(external_id="DIV-1")])
    ledger.corporate_actions.append([_lca()])


def test_rebuild_account_full(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    _populate(ledger)

    account = builder.rebuild_account(db_session, ledger)

    assert account.broker_account_id == "U1"
    assert db_session.scalar(select(func.count()).select_from(Trade)) == 2
    assert db_session.scalar(select(func.count()).select_from(CashFlow)) == 1
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(CorporateAction)) == 1
    )


def test_rebuild_account_is_idempotent(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    _populate(ledger)

    builder.rebuild_account(db_session, ledger)
    builder.rebuild_account(db_session, ledger)  # second rebuild

    assert db_session.scalar(select(func.count()).select_from(Account)) == 1
    assert db_session.scalar(select(func.count()).select_from(Trade)) == 2
    assert db_session.scalar(select(func.count()).select_from(CashFlow)) == 1
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(CorporateAction)) == 1
    )
