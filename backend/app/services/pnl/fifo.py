"""FIFO realized-P&L matching for one instrument's trades.

Processes a chronological list of trades, matching each SELL against the
oldest open BUY lots. Returns realized P&L plus the still-open position.
Phase 1 scope: long positions only (buy-to-open, sell-to-close).
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import TradeSide
from app.db.models import Trade


@dataclass(frozen=True)
class FifoResult:
    realized_pnl: Decimal     # USD, summed over all closed lots
    open_quantity: Decimal    # units still held
    open_cost_basis: Decimal  # total USD cost of the open units


def run_fifo(trades: list[Trade]) -> FifoResult:
    """Match SELLs against oldest BUYs (FIFO) for ONE instrument.

    `trades` must all be for a single instrument, sorted oldest-first.
    Raises ValueError if a SELL exceeds the open position — short
    positions are out of Phase 1 scope.
    """
    lots: deque[list[Decimal]] = deque()  # each entry: [remaining_qty, cost_per_unit]
    realized = Decimal("0")
    for t in trades:
        if t.side == TradeSide.BUY:
            cost_per_unit = (abs(t.proceeds_usd) + t.commission_usd) / t.quantity
            lots.append([t.quantity, cost_per_unit])
        else:  # SELL
            proceeds_per_unit = (abs(t.proceeds_usd) - t.commission_usd) / t.quantity
            remaining = t.quantity
            while remaining > 0:
                if not lots:
                    raise ValueError(
                        f"sell {t.trade_id} exceeds open position "
                        f"(short positions are out of Phase 1 scope)"
                    )
                lot = lots[0]
                matched = min(remaining, lot[0])
                realized += matched * (proceeds_per_unit - lot[1])
                remaining -= matched
                lot[0] -= matched
                if lot[0] == 0:
                    lots.popleft()
    open_quantity = sum((lot[0] for lot in lots), Decimal("0"))
    open_cost_basis = sum((lot[0] * lot[1] for lot in lots), Decimal("0"))
    return FifoResult(realized, open_quantity, open_cost_basis)
