# M8 — Backend HTTP API Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing service layer (import, projection, P&L, snapshot, curve) as FastAPI HTTP endpoints so the frontend can upload statements and read positions / trades / P&L / equity curve.

**Architecture:** Thin FastAPI routers in `app/api/` wrap the existing services — no business logic is rewritten. Endpoints use the `get_db` session dependency; account lookup, the accounts directory, and the market-data provider are FastAPI dependencies so tests can override them. Upload is local-only (parse + rebuild DB projection); price refresh is a separate network endpoint.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest + `fastapi.testclient.TestClient`, temp-file SQLite. Run tests: `cd backend && uv run --no-sync pytest`.

**Spec:** `docs/superpowers/specs/2026-05-18-m8-backend-api-design.md`

---

## File Structure

- Create: `backend/app/api/deps.py` — shared FastAPI dependencies (`get_accounts_dir`, `get_account`, `get_market_data_provider`).
- Create: `backend/app/api/schemas.py` — Pydantic response models (grown task by task).
- Create: `backend/app/api/accounts.py` — account router (`GET /accounts`, positions/trades/pnl/curve, refresh-prices).
- Create: `backend/app/api/statements.py` — `POST /statements/upload`.
- Modify: `backend/app/main.py` — include the two new routers.
- Modify: `backend/tests/conftest.py` — add the `api_client` fixture.
- Test: `backend/tests/test_api_accounts.py`, `backend/tests/test_api_statements.py`.

The `ibkr_flex_sample.csv` fixture in `backend/tests/fixtures/` (single account `U0000000`, from M6) is reused to seed API tests through the real upload endpoint.

---

## Task 1: Foundation — test harness, `GET /accounts`, router wiring

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/app/api/deps.py`, `backend/app/api/schemas.py`, `backend/app/api/accounts.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_accounts.py`

- [ ] **Step 1: Add the `api_client` fixture to conftest.py**

Append to `backend/tests/conftest.py`:

```python
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
```

(`Base` is already imported at the top of `conftest.py`.)

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_api_accounts.py`:

```python
def test_list_accounts_empty(api_client):
    response = api_client.get("/accounts")
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_api_accounts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.deps'` (raised inside the fixture).

- [ ] **Step 4: Create `deps.py`**

Create `backend/app/api/deps.py`:

```python
"""Shared FastAPI dependencies for the API layer."""

from pathlib import Path

from app.core.config import settings


def get_accounts_dir() -> Path:
    """The directory holding per-account CSV ledgers — overridable in tests."""
    accounts_dir = settings.data_dir / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)
    return accounts_dir
```

- [ ] **Step 5: Create `schemas.py` with `AccountOut`**

Create `backend/app/api/schemas.py`:

```python
"""Pydantic response models for the HTTP API."""

from pydantic import BaseModel


class AccountOut(BaseModel):
    broker_account_id: str
    name: str
    base_currency: str
    broker: str
```

- [ ] **Step 6: Create `accounts.py` with `GET /accounts`**

Create `backend/app/api/accounts.py`:

```python
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
```

- [ ] **Step 7: Wire the router in `main.py`**

In `backend/app/main.py`, add `accounts` to the import and include its router. The import line becomes:

```python
from app.api import accounts, health
```

And after `app.include_router(health.router)` add:

```python
app.include_router(accounts.router)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && uv run --no-sync pytest tests/test_api_accounts.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/tests/conftest.py backend/app/api/deps.py backend/app/api/schemas.py backend/app/api/accounts.py backend/app/main.py backend/tests/test_api_accounts.py
git commit -m "M8: API test harness + GET /accounts"
```

---

## Task 2: `POST /statements/upload`

**Files:**
- Modify: `backend/app/api/schemas.py`
- Create: `backend/app/api/statements.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api_statements.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_api_statements.py`:

```python
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "ibkr_flex_sample.csv"


def test_upload_statement_imports_and_lists_account(api_client):
    with FIXTURE.open("rb") as f:
        response = api_client.post(
            "/statements/upload", files={"file": ("statement.csv", f, "text/csv")}
        )
    assert response.status_code == 200
    body = response.json()
    accounts = {a["broker_account_id"]: a for a in body["accounts"]}
    assert "U0000000" in accounts
    # The synthetic fixture has 4 trades and 6 cash flows for U0000000.
    assert accounts["U0000000"]["trades"]["added"] == 4
    assert accounts["U0000000"]["cash_flows"]["added"] == 6

    # The imported account is now visible via GET /accounts.
    listed = api_client.get("/accounts").json()
    assert [a["broker_account_id"] for a in listed] == ["U0000000"]


def test_upload_statement_is_idempotent(api_client):
    with FIXTURE.open("rb") as f:
        api_client.post(
            "/statements/upload", files={"file": ("statement.csv", f, "text/csv")}
        )
    with FIXTURE.open("rb") as f:
        response = api_client.post(
            "/statements/upload", files={"file": ("statement.csv", f, "text/csv")}
        )
    body = response.json()
    accounts = {a["broker_account_id"]: a for a in body["accounts"]}
    assert accounts["U0000000"]["trades"]["added"] == 0  # all deduplicated


def test_upload_rejects_unparseable_file(api_client):
    response = api_client.post(
        "/statements/upload",
        files={"file": ("bad.csv", b"not,a,valid,flex,file\n", "text/csv")},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_api_statements.py -v`
Expected: FAIL — `404` for `/statements/upload` (route not registered).

- [ ] **Step 3: Add upload schemas to `schemas.py`**

Append to `backend/app/api/schemas.py`:

```python
class AppendCountOut(BaseModel):
    added: int
    skipped: int


class AccountImportOut(BaseModel):
    broker_account_id: str
    instruments: AppendCountOut
    trades: AppendCountOut
    cash_flows: AppendCountOut
    corporate_actions: AppendCountOut


class UploadReportOut(BaseModel):
    accounts: list[AccountImportOut]
```

- [ ] **Step 4: Create `statements.py`**

Create `backend/app/api/statements.py`:

```python
"""Statement-upload endpoint."""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api import schemas
from app.api.deps import get_accounts_dir
from app.db.base import get_db
from app.services.ledger.account_ledger import AccountLedger
from app.services.parsers.ibkr_flex import import_statement
from app.services.projection.builder import rebuild_account

router = APIRouter(tags=["statements"])


def _counts(report) -> dict[str, schemas.AppendCountOut]:
    """An ImportReport's four AppendReports as AppendCountOut models."""
    return {
        name: schemas.AppendCountOut(added=ar.added, skipped=ar.skipped)
        for name, ar in (
            ("instruments", report.instruments),
            ("trades", report.trades),
            ("cash_flows", report.cash_flows),
            ("corporate_actions", report.corporate_actions),
        )
    }


@router.post("/statements/upload", response_model=schemas.UploadReportOut)
def upload_statement(
    file: UploadFile,
    db: Session = Depends(get_db),
    accounts_dir: Path = Depends(get_accounts_dir),
) -> schemas.UploadReportOut:
    """Parse an uploaded IBKR Flex CSV, append to the ledger, rebuild the DB.

    Local only — no market-data fetch. Parse failures become HTTP 400.
    """
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        reports = import_statement(tmp_path, accounts_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    accounts_out: list[schemas.AccountImportOut] = []
    for account_id, report in reports.items():
        rebuild_account(db, AccountLedger(accounts_dir / account_id))
        accounts_out.append(
            schemas.AccountImportOut(broker_account_id=account_id, **_counts(report))
        )
    return schemas.UploadReportOut(accounts=accounts_out)
```

- [ ] **Step 5: Wire the router in `main.py`**

In `backend/app/main.py`, the import line becomes:

```python
from app.api import accounts, health, statements
```

And after `app.include_router(accounts.router)` add:

```python
app.include_router(statements.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run --no-sync pytest tests/test_api_statements.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/statements.py backend/app/main.py backend/tests/test_api_statements.py
git commit -m "M8: POST /statements/upload — import + rebuild projection"
```

---

## Task 3: Read endpoints — positions, trades, pnl

**Files:**
- Modify: `backend/app/api/deps.py`, `backend/app/api/schemas.py`, `backend/app/api/accounts.py`
- Test: `backend/tests/test_api_accounts.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api_accounts.py`. Put the new `import` lines at the **top** of the file with the existing imports (ruff `E402` rejects mid-file imports); the rest goes at the end:

```python
# --- add to the imports at the top of the file ---
from decimal import Decimal
from pathlib import Path

# --- add at the end of the file ---
FIXTURE = Path(__file__).parent / "fixtures" / "ibkr_flex_sample.csv"


def _upload(api_client):
    with FIXTURE.open("rb") as f:
        api_client.post(
            "/statements/upload", files={"file": ("statement.csv", f, "text/csv")}
        )


def test_get_positions_returns_open_holdings(api_client):
    _upload(api_client)
    response = api_client.get("/accounts/U0000000/positions")
    assert response.status_code == 200
    positions = response.json()
    # The fixture leaves AAPL stock open (bought 10, sold 4 → 6 held).
    aapl = next(p for p in positions if p["symbol"] == "AAPL")
    # A Numeric(20,6) Decimal serializes as a string like "6.000000";
    # parse it before comparing so the scale does not matter.
    assert Decimal(str(aapl["quantity"])) == Decimal("6")
    # No price refresh yet → market fields are null.
    assert aapl["market_value"] is None


def test_get_trades_returns_history(api_client):
    _upload(api_client)
    response = api_client.get("/accounts/U0000000/trades")
    assert response.status_code == 200
    trades = response.json()
    assert len(trades) == 4
    assert {t["side"] for t in trades} == {"BUY", "SELL"}


def test_get_pnl_returns_realized(api_client):
    _upload(api_client)
    response = api_client.get("/accounts/U0000000/pnl")
    assert response.status_code == 200
    body = response.json()
    assert "realized_pnl" in body
    assert body["base_currency"] == "USD"


def test_unknown_account_returns_404(api_client):
    assert api_client.get("/accounts/UNKNOWN/positions").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run --no-sync pytest tests/test_api_accounts.py -k "positions or trades or pnl or unknown_account" -v`
Expected: FAIL — `404` (routes not registered).

- [ ] **Step 3: Add the `get_account` dependency to `deps.py`**

Append to `backend/app/api/deps.py` (add the imports at the top):

```python
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Account
```

```python
def get_account(account_id: str, db: Session = Depends(get_db)) -> Account:
    """Resolve a path `account_id` (broker_account_id) to an Account, or 404."""
    account = db.scalar(
        select(Account).where(Account.broker_account_id == account_id)
    )
    if account is None:
        raise HTTPException(status_code=404, detail=f"account {account_id} not found")
    return account
```

- [ ] **Step 4: Add schemas to `schemas.py`**

Append to `backend/app/api/schemas.py` (add `from datetime import datetime` and `from decimal import Decimal` at the top):

```python
class PositionOut(BaseModel):
    symbol: str
    quantity: Decimal
    cost_basis: Decimal
    average_cost: Decimal
    market_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None


class TradeOut(BaseModel):
    trade_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    proceeds_usd: Decimal
    commission_usd: Decimal
    realized_pnl_ibkr: Decimal | None
    executed_at: datetime


class PnlOut(BaseModel):
    realized_pnl: Decimal
    open_position_count: int
    base_currency: str
```

- [ ] **Step 5: Add the three endpoints to `accounts.py`**

In `backend/app/api/accounts.py`, extend the imports:

```python
from app.api.deps import get_account
from app.db.models import Account, Instrument, PositionSnapshot, Trade
from app.services.pnl.engine import compute_positions, compute_realized_pnl
```

Append these endpoints to the router:

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run --no-sync pytest tests/test_api_accounts.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/schemas.py backend/app/api/accounts.py backend/tests/test_api_accounts.py
git commit -m "M8: GET positions / trades / pnl endpoints"
```

---

## Task 4: `GET /accounts/{account_id}/curve`

**Files:**
- Modify: `backend/app/api/schemas.py`, `backend/app/api/accounts.py`
- Test: `backend/tests/test_api_accounts.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api_accounts.py`:

```python
def test_get_curve_returns_points(api_client):
    _upload(api_client)
    response = api_client.get("/accounts/U0000000/curve")
    assert response.status_code == 200
    points = response.json()
    # Cash flows alone (no price refresh) still yield curve points on
    # deposit/withdrawal days.
    assert len(points) > 0
    assert {"on_date", "cumulative_pnl", "pct"} <= set(points[0])


def test_get_curve_rejects_bad_mode(api_client):
    _upload(api_client)
    assert api_client.get("/accounts/U0000000/curve?mode=Z").status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run --no-sync pytest tests/test_api_accounts.py -k curve -v`
Expected: FAIL — `404` (route not registered).

- [ ] **Step 3: Add `CurvePointOut` to `schemas.py`**

Append to `backend/app/api/schemas.py` (add `from datetime import date` to the datetime import):

```python
class CurvePointOut(BaseModel):
    on_date: date
    cumulative_pnl: Decimal
    pct: Decimal | None
```

- [ ] **Step 4: Add the curve endpoint to `accounts.py`**

In `backend/app/api/accounts.py`, extend the imports:

```python
from typing import Literal

from app.services.pnl.equity import compute_account_curve
```

Append the endpoint:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run --no-sync pytest tests/test_api_accounts.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/accounts.py backend/tests/test_api_accounts.py
git commit -m "M8: GET equity-curve endpoint"
```

---

## Task 5: `POST /accounts/{account_id}/refresh-prices`

**Files:**
- Modify: `backend/app/api/deps.py`, `backend/app/api/schemas.py`, `backend/app/api/accounts.py`
- Test: `backend/tests/test_api_accounts.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api_accounts.py`. Put the `import` line at the **top** of the file with the existing imports (ruff `E402`); the rest at the end. `Decimal` is already imported (Task 3).

```python
# --- add to the imports at the top of the file ---
from app.services.providers.base import MarketDataProvider

# --- add at the end of the file ---
class _FakeProvider(MarketDataProvider):
    """Returns a flat price for every symbol — keeps refresh tests offline."""

    def get_daily_closes(self, symbol, start, end):
        from datetime import timedelta

        day = start
        out = {}
        while day <= end:
            if day.weekday() < 5:  # weekdays only
                out[day] = Decimal("100")
            day += timedelta(days=1)
        return out

    def get_latest_close(self, symbol):
        return Decimal("100")


def test_refresh_prices_builds_snapshots(api_client):
    from app.api.deps import get_market_data_provider
    from app.main import app

    _upload(api_client)
    app.dependency_overrides[get_market_data_provider] = lambda: _FakeProvider()
    try:
        response = api_client.post("/accounts/U0000000/refresh-prices")
    finally:
        del app.dependency_overrides[get_market_data_provider]

    assert response.status_code == 200
    assert response.json()["snapshot_rows"] > 0


def test_refresh_prices_unknown_account_404(api_client):
    assert api_client.post("/accounts/UNKNOWN/refresh-prices").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run --no-sync pytest tests/test_api_accounts.py -k refresh -v`
Expected: FAIL — `404` (route not registered).

- [ ] **Step 3: Add the `get_market_data_provider` dependency to `deps.py`**

Append to `backend/app/api/deps.py` (add the imports at the top):

```python
from app.services.providers.base import MarketDataProvider
from app.services.providers.yahoo import YahooFinanceProvider
```

```python
def get_market_data_provider() -> MarketDataProvider:
    """The market-data provider — overridable in tests with a fake."""
    return YahooFinanceProvider()
```

- [ ] **Step 4: Add `RefreshResultOut` to `schemas.py`**

Append to `backend/app/api/schemas.py`:

```python
class RefreshResultOut(BaseModel):
    broker_account_id: str
    snapshot_rows: int
```

- [ ] **Step 5: Add the refresh endpoint to `accounts.py`**

In `backend/app/api/accounts.py`, extend the imports:

```python
from app.api.deps import get_account, get_market_data_provider
from app.services.providers.base import MarketDataProvider
from app.services.snapshot.builder import rebuild_snapshots
```

Append the endpoint:

```python
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
```

- [ ] **Step 6: Run the full suite and lint**

Run: `cd backend && uv run --no-sync pytest -q`
Expected: PASS — all existing tests plus the ~14 new M8 API tests.

Run: `cd backend && uv run --no-sync ruff check app/api/ tests/test_api_accounts.py tests/test_api_statements.py tests/conftest.py`
Expected: no errors. Fix any (line length 100; rules E,F,I,N,UP,B,SIM).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/schemas.py backend/app/api/accounts.py backend/tests/test_api_accounts.py
git commit -m "M8: POST refresh-prices — rebuild snapshots from market data"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 — `GET /accounts` + test harness + router wiring; Task 2 — `POST /statements/upload` (import + per-account `rebuild_account`, 400 on parse failure); Task 3 — positions (with latest-snapshot merge) / trades / pnl + `get_account` 404; Task 4 — curve with `Literal` mode (422 on bad mode); Task 5 — `refresh-prices` with overridable provider dependency. Every spec endpoint and error case maps to a task.
- **Type consistency:** `get_account` / `get_accounts_dir` / `get_market_data_provider` signatures are consistent between `deps.py` and every router use. Schemas are appended to one `schemas.py` and referenced as `schemas.X` throughout.
- **Decimal in JSON:** Pydantic v2 may serialize `Decimal` as a string or number; tests compare with string literals (e.g. `== "6"`) or use membership checks rather than numeric equality where the form is uncertain.
- **Offline tests:** the upload path uses `ibkr_flex_sample.csv`, whose CAD cash-flow dates are covered by the fixture's own forex rows — no ECB call. The refresh test overrides `get_market_data_provider` with `_FakeProvider`. The whole suite stays offline.
- **Out of scope (do NOT add):** frontend; cross-account aggregate views; pagination; auth; IBKR realtime.
