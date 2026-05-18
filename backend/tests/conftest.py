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


@pytest.fixture
def api_client(tmp_path):
    """A FastAPI TestClient on a temp-file SQLite DB and a temp accounts dir.

    Overrides the get_db and get_accounts_dir dependencies so API tests are
    fully isolated from the on-disk dev database and data directory.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.deps import get_accounts_dir
    from app.db.base import get_db
    from app.main import app

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False)
    accounts_dir = tmp_path / "accounts"
    accounts_dir.mkdir()

    def _get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_accounts_dir] = lambda: accounts_dir
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()
