"""Phase 1.1 — core database schema.

Covers the six tables from the roadmap: accounts, instruments, trades,
cash_flows, positions_snapshot, corporate_actions.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import models

# --- accounts -------------------------------------------------------------


def test_account_round_trip(db_session):
    acct = models.Account(
        broker_account_id="U7654321", name="Roth IRA", base_currency="USD"
    )
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)

    assert acct.id is not None
    assert acct.broker_account_id == "U7654321"
    assert acct.created_at is not None


def test_account_broker_defaults_to_ibkr(account):
    assert account.broker == "IBKR"


def test_duplicate_broker_account_id_rejected(db_session, account):
    dup = models.Account(
        broker_account_id="U1234567", name="Clone", base_currency="USD"
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()


# --- instruments ----------------------------------------------------------


def test_instrument_stock_defaults(instrument):
    assert instrument.asset_class == models.AssetClass.STOCK
    assert instrument.multiplier == 1
    assert instrument.option_type is None
    assert instrument.strike is None


def test_instrument_option_fields(db_session):
    opt = models.Instrument(
        symbol="AAPL 250117C00200000",
        asset_class=models.AssetClass.OPTION,
        currency="USD",
        underlying_symbol="AAPL",
        option_type=models.OptionType.CALL,
        strike=Decimal("200.00"),
        expiry=date(2025, 1, 17),
        multiplier=100,
    )
    db_session.add(opt)
    db_session.commit()
    db_session.refresh(opt)

    assert opt.option_type == models.OptionType.CALL
    assert opt.strike == Decimal("200.00")
    assert opt.expiry == date(2025, 1, 17)
    assert opt.multiplier == 100


# --- trades ---------------------------------------------------------------


def _make_trade(account, instrument, **overrides):
    fields = dict(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_id="EXEC-001",
        side=models.TradeSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.25"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds=Decimal("-1502.50"),
        proceeds_usd=Decimal("-1502.50"),
        commission=Decimal("1.00"),
        commission_usd=Decimal("1.00"),
        executed_at=datetime(2026, 1, 5, 14, 30),
    )
    fields.update(overrides)
    return models.Trade(**fields)


def test_trade_round_trip_dual_currency(db_session, account, instrument):
    trade = _make_trade(
        account,
        instrument,
        currency="EUR",
        fx_rate_to_usd=Decimal("1.08"),
        proceeds=Decimal("-1390.00"),
        proceeds_usd=Decimal("-1501.20"),
    )
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    assert trade.id is not None
    assert trade.currency == "EUR"
    assert trade.proceeds == Decimal("-1390.00")
    assert trade.proceeds_usd == Decimal("-1501.20")
    assert trade.fx_rate_to_usd == Decimal("1.08")


def test_trade_relationships(db_session, account, instrument):
    db_session.add(_make_trade(account, instrument))
    db_session.commit()

    db_session.refresh(account)
    assert len(account.trades) == 1
    assert account.trades[0].instrument.symbol == "AAPL"
    assert account.trades[0].account is account


def test_duplicate_trade_id_rejected(db_session, account, instrument):
    db_session.add(_make_trade(account, instrument, trade_id="EXEC-DUP"))
    db_session.commit()

    db_session.add(_make_trade(account, instrument, trade_id="EXEC-DUP"))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --- cash_flows -----------------------------------------------------------


def test_cash_flow_round_trip(db_session, account, instrument):
    flow = models.CashFlow(
        account_id=account.id,
        instrument_id=instrument.id,
        flow_type=models.CashFlowType.DIVIDEND,
        amount=Decimal("22.00"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_usd=Decimal("22.00"),
        occurred_at=datetime(2026, 2, 14, 0, 0),
    )
    db_session.add(flow)
    db_session.commit()
    db_session.refresh(flow)

    assert flow.id is not None
    assert flow.flow_type == models.CashFlowType.DIVIDEND
    assert flow.instrument.symbol == "AAPL"


def test_cash_flow_deposit_without_instrument(db_session, account):
    flow = models.CashFlow(
        account_id=account.id,
        flow_type=models.CashFlowType.DEPOSIT,
        amount=Decimal("5000.00"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_usd=Decimal("5000.00"),
        occurred_at=datetime(2026, 1, 1, 0, 0),
    )
    db_session.add(flow)
    db_session.commit()
    db_session.refresh(flow)

    assert flow.instrument_id is None


# --- positions_snapshot ---------------------------------------------------


def _make_snapshot(account, instrument, **overrides):
    fields = dict(
        account_id=account.id,
        instrument_id=instrument.id,
        snapshot_date=date(2026, 3, 31),
        quantity=Decimal("10"),
        avg_cost=Decimal("150.25"),
        market_price=Decimal("172.00"),
    )
    fields.update(overrides)
    return models.PositionSnapshot(**fields)


def test_position_snapshot_round_trip(db_session, account, instrument):
    snap = _make_snapshot(account, instrument)
    db_session.add(snap)
    db_session.commit()
    db_session.refresh(snap)

    assert snap.id is not None
    assert snap.snapshot_date == date(2026, 3, 31)
    assert snap.quantity == Decimal("10")


def test_position_snapshot_unique_per_instrument_per_day(
    db_session, account, instrument
):
    db_session.add(_make_snapshot(account, instrument))
    db_session.commit()

    db_session.add(_make_snapshot(account, instrument))
    with pytest.raises(IntegrityError):
        db_session.commit()


# --- corporate_actions ----------------------------------------------------


def test_corporate_action_round_trip(db_session, instrument):
    action = models.CorporateAction(
        instrument_id=instrument.id,
        action_type=models.CorporateActionType.SPLIT,
        ex_date=date(2024, 6, 10),
        ratio=Decimal("10.0"),
        description="10-for-1 split",
    )
    db_session.add(action)
    db_session.commit()
    db_session.refresh(action)

    assert action.id is not None
    assert action.action_type == models.CorporateActionType.SPLIT
    assert action.ratio == Decimal("10.0")


def test_trade_realized_pnl_ibkr_optional(db_session, account, instrument):
    trade = _make_trade(account, instrument)
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    assert trade.realized_pnl_ibkr is None


# --- provenance -----------------------------------------------------------


def test_trade_source_defaults_to_parsed(db_session, account, instrument):
    trade = _make_trade(account, instrument)
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    assert trade.source == models.RecordSource.PARSED
    assert trade.import_batch is None


def test_instrument_can_be_marked_manual(db_session):
    inst = models.Instrument(
        symbol="MSFT",
        asset_class=models.AssetClass.STOCK,
        currency="USD",
        source=models.RecordSource.MANUAL,
        import_batch="manual",
    )
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)

    assert inst.source == models.RecordSource.MANUAL
    assert inst.import_batch == "manual"
