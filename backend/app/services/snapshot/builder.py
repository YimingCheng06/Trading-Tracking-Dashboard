"""Rebuild positions_snapshot — the daily market-value time series.

`positions_snapshot` is a rebuildable cache: for each market day an
instrument was held, this replays the FIFO position from trades and prices
it. Stocks/ETFs get carried-forward closes from a MarketDataProvider;
options have no reliable historical price, so they are recorded at cost
with market_* left NULL. Account-scoped delete + reinsert — idempotent.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.enums import AssetClass
from app.db.models import Account, Instrument, PositionSnapshot, Trade
from app.services.pnl.fifo import run_fifo
from app.services.providers.base import MarketDataProvider

_PRICED = (AssetClass.STOCK, AssetClass.ETF)


def rebuild_snapshots(
    session: Session, account: Account, provider: MarketDataProvider
) -> int:
    """Recompute `account`'s positions_snapshot rows; return the row count."""
    session.execute(
        delete(PositionSnapshot).where(PositionSnapshot.account_id == account.id)
    )

    trades = session.scalars(
        select(Trade)
        .where(Trade.account_id == account.id)
        .order_by(Trade.instrument_id, Trade.executed_at, Trade.id)
    ).all()
    by_instrument: dict[int, list[Trade]] = {}
    for t in trades:
        by_instrument.setdefault(t.instrument_id, []).append(t)
    if not by_instrument:
        session.commit()
        return 0

    today = date.today()
    instruments = {iid: session.get(Instrument, iid) for iid in by_instrument}

    # Pass 1: fetch closes for priced instruments; derive the market-day calendar.
    closes_by_id: dict[int, dict[date, Decimal]] = {}
    for iid, itrades in by_instrument.items():
        if instruments[iid].asset_class in _PRICED:
            first_day = min(t.executed_at.date() for t in itrades)
            closes_by_id[iid] = provider.get_daily_closes(
                instruments[iid].symbol, first_day, today
            )
    market_days = sorted({d for closes in closes_by_id.values() for d in closes})
    if not market_days:
        # Options-only account, or no price data — fall back to trade days.
        market_days = sorted({t.executed_at.date() for t in trades})

    # Pass 2: one snapshot row per instrument per market day held.
    written = 0
    for iid, itrades in by_instrument.items():
        first_day = min(t.executed_at.date() for t in itrades)
        instrument_closes = closes_by_id.get(iid, {})
        last_price: Decimal | None = None
        for day in market_days:
            if day < first_day or day > today:
                continue
            if day in instrument_closes:
                last_price = instrument_closes[day]
            up_to = [t for t in itrades if t.executed_at.date() <= day]
            result = run_fifo(up_to)
            if result.open_quantity == 0:
                continue
            avg_cost = result.open_cost_basis / result.open_quantity
            if last_price is not None:
                market_value = result.open_quantity * last_price
                unrealized = market_value - result.open_cost_basis
            else:
                market_value = None
                unrealized = None
            session.add(
                PositionSnapshot(
                    account_id=account.id,
                    instrument_id=iid,
                    snapshot_date=day,
                    quantity=result.open_quantity,
                    avg_cost=avg_cost,
                    market_price=last_price,
                    market_value=market_value,
                    market_value_usd=market_value,
                    unrealized_pnl=unrealized,
                    unrealized_pnl_usd=unrealized,
                )
            )
            written += 1
    session.commit()
    return written
