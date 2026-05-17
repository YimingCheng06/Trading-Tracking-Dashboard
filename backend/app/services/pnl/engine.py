"""P&L engine — realized P&L and current positions, computed from trades.

Reads the DB projection (Trade rows), groups by instrument, runs FIFO.
All amounts are USD. Market value, unrealized P&L and the equity curve
need daily market prices (positions_snapshot) and arrive with the market-
data layer; this module covers everything computable from trades alone.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Instrument, Trade
from app.services.pnl.fifo import run_fifo


@dataclass(frozen=True)
class Position:
    instrument_id: int
    symbol: str
    quantity: Decimal      # open units
    cost_basis: Decimal    # total USD cost of the open units
    average_cost: Decimal  # cost_basis / quantity


def _trades_by_instrument(
    session: Session, account_id: int
) -> dict[int, list[Trade]]:
    """All of the account's trades, grouped by instrument, oldest-first."""
    rows = session.scalars(
        select(Trade)
        .where(Trade.account_id == account_id)
        .order_by(Trade.instrument_id, Trade.executed_at, Trade.id)
    ).all()
    grouped: dict[int, list[Trade]] = {}
    for trade in rows:
        grouped.setdefault(trade.instrument_id, []).append(trade)
    return grouped


def compute_realized_pnl(session: Session, account: Account) -> Decimal:
    """Total realized P&L (USD) across all of the account's instruments."""
    total = Decimal("0")
    for trades in _trades_by_instrument(session, account.id).values():
        total += run_fifo(trades).realized_pnl
    return total


def compute_positions(session: Session, account: Account) -> list[Position]:
    """Current open positions (quantity + cost basis) per instrument.

    Instruments fully closed out are omitted. Market value and unrealized
    P&L require market prices and are out of this milestone.
    """
    positions: list[Position] = []
    for instrument_id, trades in _trades_by_instrument(session, account.id).items():
        result = run_fifo(trades)
        if result.open_quantity == 0:
            continue
        instrument = session.get(Instrument, instrument_id)
        if instrument is None:
            raise LookupError(
                f"instrument {instrument_id} not found — DB projection may be corrupt"
            )
        positions.append(
            Position(
                instrument_id=instrument_id,
                symbol=instrument.symbol,
                quantity=result.open_quantity,
                cost_basis=result.open_cost_basis,
                average_cost=result.open_cost_basis / result.open_quantity,
            )
        )
    return positions
