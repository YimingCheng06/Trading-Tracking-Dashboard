"""Shared FastAPI dependencies for the API layer."""

from pathlib import Path

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import get_db
from app.db.models import Account


def get_accounts_dir() -> Path:
    """The directory holding per-account CSV ledgers — overridable in tests."""
    accounts_dir = settings.data_dir / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)
    return accounts_dir


def get_account(account_id: str, db: Session = Depends(get_db)) -> Account:
    """Resolve a path `account_id` (broker_account_id) to an Account, or 404."""
    account = db.scalar(
        select(Account).where(Account.broker_account_id == account_id)
    )
    if account is None:
        raise HTTPException(status_code=404, detail=f"account {account_id} not found")
    return account
