"""Rebuild the SQLite DB projection from one account's CSV ledger.

The ledger is the source of truth; the DB is a disposable query projection.
`rebuild_account` is a full rebuild of one account: account-scoped tables
(trades, cash_flows) are deleted and re-inserted, while global tables
(instruments, corporate_actions) are upserted by their natural key.
positions_snapshot is NOT projected here — it is derived from market data
in a later milestone.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount


def upsert_account(session: Session, ledger_account: LedgerAccount) -> Account:
    """Find the Account by broker_account_id, or create it; update its fields."""
    account = session.scalar(
        select(Account).where(
            Account.broker_account_id == ledger_account.broker_account_id
        )
    )
    if account is None:
        account = Account(broker_account_id=ledger_account.broker_account_id)
        session.add(account)
    account.name = ledger_account.name
    account.base_currency = ledger_account.base_currency
    account.broker = ledger_account.broker
    session.flush()
    return account


def rebuild_account(session: Session, ledger: AccountLedger) -> Account:
    """Full rebuild of one account's projection. Implemented incrementally."""
    return upsert_account(session, ledger.read_account())
