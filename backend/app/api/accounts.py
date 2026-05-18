"""Account-scoped HTTP endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import schemas
from app.db.base import get_db
from app.db.models import Account

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
