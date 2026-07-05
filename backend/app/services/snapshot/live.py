"""Live-snapshot computation — read-only, no DB writes.

`compute_live_snapshot` fetches the latest price for every open priced
position via the provider, overlays those marks onto the position list, and
recomputes the equity-curve tail using the live holdings (instead of the
last-saved snapshot value). Strict failure semantics apply only to equity
(stock/ETF) symbols: any priced equity symbol missing from the provider's
response raises `LiveDataUnavailable`. Options are best-effort — a missing
mark leaves `market_* = None` on the position, but its `cost_basis` still
counts toward the curve tail so the tail never omits open option value.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.db.enums import AssetClass
from app.db.models import Account, Instrument
from app.services.pnl.curve import CurvePoint, DayPoint, compute_equity_curve
from app.services.pnl.engine import compute_positions
from app.services.pnl.equity import build_day_points
from app.services.providers.base import MarketDataProvider
from app.services.snapshot.cash import compute_cash_at

_PRICED = (AssetClass.STOCK, AssetClass.ETF)


class LiveDataUnavailable(Exception):  # noqa: N818
    """Raised when one or more priced symbols have no current price."""

    def __init__(self, missing: list[str]):
        self.missing = list(missing)
        super().__init__(f"missing prices: {self.missing}")


@dataclass(frozen=True)
class LivePosition:
    symbol: str
    quantity: Decimal
    cost_basis: Decimal
    average_cost: Decimal
    market_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None


@dataclass(frozen=True)
class LiveSnapshot:
    fetched_at: datetime
    positions: list[LivePosition]
    curve_tail: CurvePoint
    source: Literal["ibkr", "yahoo"]


def _int_conid(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def compute_live_snapshot(
    session: Session,
    account: Account,
    provider: MarketDataProvider,
    mode: Literal["A", "B"],
) -> LiveSnapshot:
    """Build a live-overlay snapshot for the account; never writes the DB."""
    positions = compute_positions(session, account)
    # Look up asset class once — needed to decide which positions get priced.
    instruments = {
        iid: session.get(Instrument, iid)
        for iid in {p.instrument_id for p in positions}
    }
    equity: dict[str, int | None] = {}
    options: dict[str, int] = {}
    for p in positions:
        inst = instruments[p.instrument_id]
        if inst.asset_class in _PRICED:
            equity[p.symbol] = _int_conid(inst.conid)
        elif inst.asset_class is AssetClass.OPTION:
            conid = _int_conid(inst.conid)
            if conid is not None:
                options[p.symbol] = conid
    quotes = provider.get_live_quotes(equity, options)
    closes = quotes.closes
    missing = [s for s in equity if closes.get(s) is None]
    if missing:
        raise LiveDataUnavailable(missing)

    live_positions: list[LivePosition] = []
    live_holdings_usd = Decimal("0")
    for p in positions:
        inst = instruments[p.instrument_id]
        if inst.asset_class in _PRICED:
            mark = closes[p.symbol]
            market_value = p.quantity * mark
            unrealized = market_value - p.cost_basis
            live_holdings_usd += market_value
            live_positions.append(
                LivePosition(
                    symbol=p.symbol,
                    quantity=p.quantity,
                    cost_basis=p.cost_basis,
                    average_cost=p.average_cost,
                    market_price=mark,
                    market_value=market_value,
                    unrealized_pnl=unrealized,
                )
            )
        elif p.symbol in quotes.option_marks:
            mark = quotes.option_marks[p.symbol]
            market_value = p.quantity * mark * inst.multiplier
            unrealized = market_value - p.cost_basis
            live_holdings_usd += market_value
            live_positions.append(
                LivePosition(
                    symbol=p.symbol,
                    quantity=p.quantity,
                    cost_basis=p.cost_basis,
                    average_cost=p.average_cost,
                    market_price=mark,
                    market_value=market_value,
                    unrealized_pnl=unrealized,
                )
            )
        else:
            # No live mark — the position still counts at cost in the curve
            # tail, matching `_holdings_value`'s cost fallback for history
            # points (fixes Milestone A omitting option value from the tail).
            live_holdings_usd += p.cost_basis
            live_positions.append(
                LivePosition(
                    symbol=p.symbol,
                    quantity=p.quantity,
                    cost_basis=p.cost_basis,
                    average_cost=p.average_cost,
                    market_price=None,
                    market_value=None,
                    unrealized_pnl=None,
                )
            )

    today = date.today()
    cash_today = compute_cash_at(session, account, today)
    day_points = build_day_points(session, account)
    # Preserve any deposits/withdrawals already booked for today so the
    # curve denominator (mode B) and TWR numerator (mode A) stay correct.
    today_net_flow = Decimal("0")
    if day_points and day_points[-1].on_date == today:
        today_net_flow = day_points[-1].net_flow
    live_tail = DayPoint(
        on_date=today,
        portfolio_value=cash_today + live_holdings_usd,
        net_flow=today_net_flow,
    )
    if day_points and day_points[-1].on_date == today:
        day_points = day_points[:-1] + [live_tail]
    else:
        day_points = day_points + [live_tail]
    curve = compute_equity_curve(day_points, mode)

    return LiveSnapshot(
        fetched_at=datetime.now(UTC),
        positions=live_positions,
        curve_tail=curve[-1],
        source=quotes.source,
    )
