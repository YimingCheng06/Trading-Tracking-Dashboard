"""Account-scoped HTTP endpoints."""

import logging
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import schemas
from app.api.deps import get_account, get_market_data_provider
from app.db.base import get_db
from app.db.models import Account, Instrument, PositionSnapshot, Trade
from app.services.pnl.engine import compute_positions, compute_realized_pnl
from app.services.pnl.equity import compute_account_curve
from app.services.providers.base import MarketDataProvider
from app.services.snapshot.builder import rebuild_snapshots
from app.services.snapshot.live import LiveDataUnavailable, compute_live_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=list[schemas.AccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[schemas.AccountOut]:
    accounts = db.scalars(
        select(Account).order_by(Account.broker_account_id)
    ).all()
    return [
        schemas.AccountOut(
            broker_account_id=a.broker_account_id,
            name=a.name,
            base_currency=a.base_currency,
            broker=a.broker,
        )
        for a in accounts
    ]


@router.get(
    "/accounts/{account_id}/positions",
    response_model=list[schemas.PositionOut],
)
def get_positions(
    account: Account = Depends(get_account),
    db: Session = Depends(get_db),
) -> list[schemas.PositionOut]:
    out: list[schemas.PositionOut] = []
    for p in compute_positions(db, account):
        latest = db.scalar(
            select(PositionSnapshot)
            .where(
                PositionSnapshot.account_id == account.id,
                PositionSnapshot.instrument_id == p.instrument_id,
            )
            .order_by(PositionSnapshot.snapshot_date.desc())
            .limit(1)
        )
        out.append(
            schemas.PositionOut(
                symbol=p.symbol,
                quantity=p.quantity,
                cost_basis=p.cost_basis,
                average_cost=p.average_cost,
                market_price=latest.market_price if latest else None,
                market_value=latest.market_value_usd if latest else None,
                unrealized_pnl=latest.unrealized_pnl_usd if latest else None,
            )
        )
    return out


@router.get(
    "/accounts/{account_id}/trades",
    response_model=list[schemas.TradeOut],
)
def get_trades(
    account: Account = Depends(get_account),
    db: Session = Depends(get_db),
) -> list[schemas.TradeOut]:
    rows = db.execute(
        select(Trade, Instrument.symbol)
        .join(Instrument, Trade.instrument_id == Instrument.id)
        .where(Trade.account_id == account.id)
        .order_by(Trade.executed_at.desc())
    ).all()
    return [
        schemas.TradeOut(
            trade_id=t.trade_id,
            symbol=symbol,
            side=t.side.value,
            quantity=t.quantity,
            price=t.price,
            proceeds_usd=t.proceeds_usd,
            commission_usd=t.commission_usd,
            realized_pnl_ibkr=t.realized_pnl_ibkr,
            executed_at=t.executed_at,
        )
        for t, symbol in rows
    ]


@router.get("/accounts/{account_id}/pnl", response_model=schemas.PnlOut)
def get_pnl(
    account: Account = Depends(get_account),
    db: Session = Depends(get_db),
) -> schemas.PnlOut:
    return schemas.PnlOut(
        realized_pnl=compute_realized_pnl(db, account),
        open_position_count=len(compute_positions(db, account)),
        base_currency=account.base_currency,
    )


@router.get(
    "/accounts/{account_id}/curve",
    response_model=list[schemas.CurvePointOut],
)
def get_curve(
    account: Account = Depends(get_account),
    db: Session = Depends(get_db),
    mode: Literal["A", "B"] = "B",
) -> list[schemas.CurvePointOut]:
    return [
        schemas.CurvePointOut(
            on_date=c.on_date, cumulative_pnl=c.cumulative_pnl, pct=c.pct
        )
        for c in compute_account_curve(db, account, mode)
    ]


@router.post(
    "/accounts/{account_id}/refresh-prices",
    response_model=schemas.RefreshResultOut,
)
def refresh_prices(
    account: Account = Depends(get_account),
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> schemas.RefreshResultOut:
    """Fetch market data and rebuild this account's positions_snapshot.

    The only endpoint that touches the network (Yahoo).
    """
    rows = rebuild_snapshots(db, account, provider)
    return schemas.RefreshResultOut(
        broker_account_id=account.broker_account_id, snapshot_rows=rows
    )


@router.get(
    "/accounts/{account_id}/live-snapshot",
    response_model=schemas.LiveSnapshotOut,
)
def get_live_snapshot(
    account: Account = Depends(get_account),
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
    mode: Literal["A", "B"] = "B",
) -> schemas.LiveSnapshotOut:
    """Live overlay of positions + equity-curve tail; pure read, no DB writes."""
    try:
        snap = compute_live_snapshot(db, account, provider, mode)
    except LiveDataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"行情不可用: {', '.join(exc.missing)}",
        ) from exc
    except Exception as exc:
        logger.exception(
            "live-snapshot computation failed for account %s",
            account.broker_account_id,
        )
        raise HTTPException(status_code=503, detail="行情不可用") from exc
    return schemas.LiveSnapshotOut(
        fetched_at=snap.fetched_at,
        positions=[schemas.PositionOut(**asdict(p)) for p in snap.positions],
        curve_tail=schemas.CurvePointOut(
            on_date=snap.curve_tail.on_date,
            cumulative_pnl=snap.curve_tail.cumulative_pnl,
            pct=snap.curve_tail.pct,
        ),
        source=snap.source,
    )
