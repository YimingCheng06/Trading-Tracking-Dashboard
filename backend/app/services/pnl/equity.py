"""Build the daily portfolio-value series and the equity curve.

Aggregates positions_snapshot (holdings value) with cash_flows and trades
(the cash balance) into the DayPoint series compute_equity_curve consumes.
A position with no market value (an option, or a stock with no price data)
is valued at cost — quantity * avg_cost.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import CashFlowType, TradeSide
from app.db.models import Account, CashFlow, PositionSnapshot, Trade
from app.services.pnl.curve import CurvePoint, DayPoint, compute_equity_curve


def _holdings_value(snapshot: PositionSnapshot) -> Decimal:
    """A snapshot row's contribution to portfolio value — market value when
    marked, otherwise cost (quantity * avg_cost)."""
    if snapshot.market_value_usd is not None:
        return snapshot.market_value_usd
    return snapshot.quantity * snapshot.avg_cost


def build_day_points(session: Session, account: Account) -> list[DayPoint]:
    """Aggregate snapshots + cash flows + trades into a daily DayPoint series."""
    snapshots = session.scalars(
        select(PositionSnapshot).where(PositionSnapshot.account_id == account.id)
    ).all()
    if not snapshots:
        return []

    holdings: dict[date, Decimal] = {}
    for s in snapshots:
        holdings[s.snapshot_date] = (
            holdings.get(s.snapshot_date, Decimal("0")) + _holdings_value(s)
        )

    cash_flows = session.scalars(
        select(CashFlow).where(CashFlow.account_id == account.id)
    ).all()
    trades = session.scalars(
        select(Trade).where(Trade.account_id == account.id)
    ).all()

    points: list[DayPoint] = []
    for day in sorted(holdings):
        cash = Decimal("0")
        for cf in cash_flows:
            if cf.occurred_at.date() <= day:
                cash += cf.amount_usd
        for t in trades:
            if t.executed_at.date() <= day:
                # proceeds_usd is stored as a gross magnitude; abs() keeps the
                # cash impact correct whatever sign convention produced it.
                gross = abs(t.proceeds_usd)
                if t.side == TradeSide.BUY:
                    cash -= gross + t.commission_usd
                else:
                    cash += gross - t.commission_usd
        net_flow = Decimal("0")
        for cf in cash_flows:
            if cf.occurred_at.date() == day and cf.flow_type in (
                CashFlowType.DEPOSIT,
                CashFlowType.WITHDRAWAL,
            ):
                net_flow += cf.amount_usd
        points.append(
            DayPoint(
                on_date=day,
                portfolio_value=cash + holdings[day],
                net_flow=net_flow,
            )
        )
    return points


def compute_account_curve(
    session: Session, account: Account, mode: Literal["A", "B"]
) -> list[CurvePoint]:
    """Build the equity curve for `account` — build_day_points then M5's math."""
    return compute_equity_curve(build_day_points(session, account), mode)
