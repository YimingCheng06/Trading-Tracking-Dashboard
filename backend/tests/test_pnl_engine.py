from datetime import datetime
from decimal import Decimal

import pytest

from app.db.enums import AssetClass, TradeSide
from app.db.models import Instrument, Trade
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount, LedgerInstrument, LedgerTrade
from app.services.pnl.engine import compute_positions, compute_realized_pnl
from app.services.projection.builder import rebuild_account


def _db_trade(account, instrument, side, quantity, proceeds_usd, *, trade_id, executed_at):
    return Trade(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_id=trade_id,
        side=side,
        quantity=Decimal(str(quantity)),
        price=Decimal("100"),
        currency="USD",
        fx_rate_to_usd=Decimal("1"),
        proceeds=Decimal(str(proceeds_usd)),
        proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal("0"),
        executed_at=executed_at,
    )


def test_compute_realized_pnl_sums_across_instruments(db_session, account, instrument):
    # A second instrument, so the test genuinely exercises cross-instrument summation.
    other = Instrument(symbol="MSFT", asset_class=AssetClass.STOCK, currency="USD")
    db_session.add(other)
    db_session.flush()

    db_session.add_all(
        [
            _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1)),
            _db_trade(account, instrument, TradeSide.SELL, 10, "1200",
                      trade_id="S1", executed_at=datetime(2026, 1, 2)),
            _db_trade(account, other, TradeSide.BUY, 5, "-500",
                      trade_id="B2", executed_at=datetime(2026, 1, 3)),
            _db_trade(account, other, TradeSide.SELL, 5, "650",
                      trade_id="S2", executed_at=datetime(2026, 1, 4)),
        ]
    )
    db_session.commit()

    # instrument: 1200-1000 = 200 ; other: 650-500 = 150 ; total = 350
    assert compute_realized_pnl(db_session, account) == Decimal("350")


def test_compute_positions_returns_open_holdings(db_session, account, instrument):
    db_session.add_all(
        [
            _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1)),
            _db_trade(account, instrument, TradeSide.SELL, 4, "480",
                      trade_id="S1", executed_at=datetime(2026, 1, 2)),
        ]
    )
    db_session.commit()

    positions = compute_positions(db_session, account)
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == Decimal("6")
    assert positions[0].cost_basis == Decimal("600")
    assert positions[0].average_cost == Decimal("100")


def test_compute_positions_omits_fully_closed(db_session, account, instrument):
    db_session.add_all(
        [
            _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1)),
            _db_trade(account, instrument, TradeSide.SELL, 10, "1200",
                      trade_id="S1", executed_at=datetime(2026, 1, 2)),
        ]
    )
    db_session.commit()

    assert compute_positions(db_session, account) == []


def test_compute_positions_raises_on_dangling_instrument(db_session, account, instrument):
    # A trade pointing at an instrument_id that does not exist (SQLite does
    # not enforce the FK) must fail loudly, not raise a cryptic AttributeError.
    trade = _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1))
    trade.instrument_id = 999999  # no such instrument
    db_session.add(trade)
    db_session.commit()

    with pytest.raises(LookupError, match="999999"):
        compute_positions(db_session, account)


def test_engine_runs_on_projection_built_from_ledger(db_session, tmp_path):
    # Build a CSV ledger, project it into the DB (M3), then run the engine.
    ledger = AccountLedger.create(
        tmp_path,
        LedgerAccount(broker_account_id="U1", name="Main", base_currency="USD"),
    )
    ledger.instruments.append(
        [LedgerInstrument(symbol="AAPL", asset_class=AssetClass.STOCK, currency="USD")]
    )

    def _lt(trade_id, side, qty, proceeds_usd, when):
        return LedgerTrade(
            trade_id=trade_id,
            instrument="AAPL",
            side=side,
            quantity=Decimal(str(qty)),
            price=Decimal("100"),
            currency="USD",
            fx_rate_to_usd=Decimal("1"),
            proceeds_orig=Decimal(str(proceeds_usd)),
            proceeds_usd=Decimal(str(proceeds_usd)),
            executed_at=when,
        )

    ledger.trades.append(
        [
            _lt("B1", TradeSide.BUY, 10, "-1000", datetime(2026, 1, 1, 10)),
            _lt("S1", TradeSide.SELL, 4, "480", datetime(2026, 1, 2, 10)),
        ]
    )

    account = rebuild_account(db_session, ledger)

    assert compute_realized_pnl(db_session, account) == Decimal("80")
    positions = compute_positions(db_session, account)
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("6")
    assert positions[0].average_cost == Decimal("100")
