"""FIFO realized-P&L matching for one instrument's trades.

Processes a chronological list of trades, matching each SELL against the
oldest open BUY lots. Returns realized P&L plus the still-open position.
Phase 1 scope: long positions only (buy-to-open, sell-to-close).

`proceeds_usd` magnitude is taken via abs(), so the result is correct
whether a BUY's proceeds are stored negative (IBKR cash-flow convention)
or positive — the BUY/SELL direction comes solely from `Trade.side`.
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
    open_cost_basis: Decimal  # total USD cost of the open units (0 when flat)


@dataclass
class _Lot:
    qty: Decimal           # remaining unmatched quantity
    cost_per_unit: Decimal


def run_fifo(trades: list[Trade]) -> FifoResult:
    """Match SELLs against oldest BUYs (FIFO) for ONE instrument.

    `trades` must all be for a single instrument, sorted oldest-first.
    Raises ValueError if a trade has zero quantity, or if a SELL exceeds
    the open position — short positions are out of Phase 1 scope.
    """
    lots: deque[_Lot] = deque()
    realized = Decimal("0")
    for t in trades:
        if t.quantity == 0:
            raise ValueError(f"trade {t.trade_id} has zero quantity")
        if t.side == TradeSide.BUY:
            cost_per_unit = (abs(t.proceeds_usd) + t.commission_usd) / t.quantity
            lots.append(_Lot(t.quantity, cost_per_unit))
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
                matched = min(remaining, lot.qty)
                realized += matched * (proceeds_per_unit - lot.cost_per_unit)
                remaining -= matched
                lot.qty -= matched
                if lot.qty == 0:
                    lots.popleft()
    open_quantity = sum((lot.qty for lot in lots), Decimal("0"))
    open_cost_basis = sum(
        (lot.qty * lot.cost_per_unit for lot in lots), Decimal("0")
    )
    return FifoResult(realized, open_quantity, open_cost_basis)
