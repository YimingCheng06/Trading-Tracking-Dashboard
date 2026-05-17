from datetime import datetime
from decimal import Decimal

from app.db.enums import TradeSide
from app.db.models import Trade
from app.services.pnl.engine import compute_positions, compute_realized_pnl


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
    db_session.add_all(
        [
            _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1)),
            _db_trade(account, instrument, TradeSide.SELL, 10, "1200",
                      trade_id="S1", executed_at=datetime(2026, 1, 2)),
        ]
    )
    db_session.commit()

    assert compute_realized_pnl(db_session, account) == Decimal("200")


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
