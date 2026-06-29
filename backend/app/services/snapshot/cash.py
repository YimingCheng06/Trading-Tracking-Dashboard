"""Cumulative cash position helpers — extracted from build_day_points.

`compute_cash_at(session, account, day)` returns the USD cash balance at
end-of-day `day`: all deposits/withdrawals/dividends/fees up to that day,
plus the signed cash impact of every trade settled by that day. Both this
helper and `build_day_points` route through the same sequence-level
implementation so they cannot drift.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import TradeSide
from app.db.models import Account, CashFlow, Trade


def compute_cash_at_from_sequences(
    cash_flows: list[CashFlow], trades: list[Trade], day: date
) -> Decimal:
    """USD cash at end of `day`, given already-loaded cash_flows + trades."""
    cash = Decimal("0")
    for cf in cash_flows:
        if cf.occurred_at.date() <= day:
            cash += cf.amount_usd
    for t in trades:
        if t.executed_at.date() <= day:
            gross = abs(t.proceeds_usd)
            if t.side == TradeSide.BUY:
                cash -= gross + t.commission_usd
            else:
                cash += gross - t.commission_usd
    return cash


def compute_cash_at(session: Session, account: Account, day: date) -> Decimal:
    """USD cash at end of `day` — queries the DB for the account's flows."""
    cash_flows = list(
        session.scalars(
            select(CashFlow).where(CashFlow.account_id == account.id)
        ).all()
    )
    trades = list(
        session.scalars(
            select(Trade).where(Trade.account_id == account.id)
        ).all()
    )
    return compute_cash_at_from_sequences(cash_flows, trades, day)
