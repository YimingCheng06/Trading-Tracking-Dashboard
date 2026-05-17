"""Shared pytest fixtures.

`db_session` builds every table on a fresh in-memory SQLite database so model
tests are fully isolated and never touch the on-disk dev database.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import models  # noqa: F401  -- registers models on Base.metadata
from app.db.base import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def account(db_session):
    acct = models.Account(
        broker_account_id="U1234567", name="Main", base_currency="USD"
    )
    db_session.add(acct)
    db_session.commit()
    db_session.refresh(acct)
    return acct


@pytest.fixture
def instrument(db_session):
    inst = models.Instrument(
        symbol="AAPL",
        asset_class=models.AssetClass.STOCK,
        currency="USD",
        exchange="NASDAQ",
    )
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)
    return inst
