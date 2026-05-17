# Phase 1 M3 — Projection Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 projection builder —— 读取一个账户的 CSV 账本(M2 的 `AccountLedger`),把它全量重建成 SQLite 数据库投影(M1 的 ORM 模型)。

**Architecture:** 新包 `app/services/projection/`。`rebuild_account(session, ledger)` 编排:upsert `Account` → upsert 所有 `Instrument`(全局,按去重键 find-or-create)并建立 `symbol → Instrument` 映射 → 删除该账户的 `Trade`/`CashFlow` 行再从账本重插(账户级全量重建)→ upsert `CorporateAction`(全局,按 instrument+类型+除权日)。`positions_snapshot` 不由本里程碑投影(它由后续行情快照派生)。重建幂等。

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Pydantic v2, pytest, uv, ruff。命令从 `backend/` 运行,`uv run --no-sync` 前缀。

**参考:** spec `docs/superpowers/specs/2026-05-17-phase1-data-architecture-pnl-design.md` 第 2 节(数据流)。依赖 M1(`app/db/models.py` ORM)+ M2(`app/services/ledger/` 账本)。

## File Structure

- `backend/app/services/projection/__init__.py` — **新建**,包标记,re-export `rebuild_account`。
- `backend/app/services/projection/builder.py` — **新建**。projection builder:`upsert_account`、`upsert_instrument`、`project_instruments`、`project_trades`、`project_cash_flows`、`project_corporate_actions`、`rebuild_account`。
- `backend/tests/test_projection_builder.py` — **新建**测试。

## 字段映射(账本行模型 → ORM)

- `LedgerInstrument` → `Instrument`:同名字段 1:1(symbol/asset_class/currency/exchange/name/conid/underlying_symbol/option_type/strike/expiry/multiplier/source/import_batch)。
- `LedgerTrade` → `Trade`:`instrument`(symbol 文本键)→ 解析成 `instrument_id`;补 `account_id`;`proceeds_orig`→`proceeds`、`commission_orig`→`commission`;其余同名 1:1。
- `LedgerCashFlow` → `CashFlow`:`instrument`(可空 symbol)→ `instrument_id`(None→None);补 `account_id`;`amount_orig`→`amount`;其余 1:1。
- `LedgerCorporateAction` → `CorporateAction`:`instrument`→`instrument_id`;其余 1:1。

`instrument` 文本键 = `instruments.csv` 里某行的 `symbol`。trades/cash_flows/corporate_actions 引用一个不在 instruments.csv 的 symbol 时,projection builder 抛 `ValueError`(数据完整性检查)。

---

### Task 1: 测试脚手架 + upsert_account

建测试文件与共享 helper,实现按 `broker_account_id` find-or-create 的 `upsert_account`。

**Files:** Create `backend/app/services/projection/__init__.py`, `backend/app/services/projection/builder.py`; Test `backend/tests/test_projection_builder.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_projection_builder.py`:

```python
"""M3 projection builder — CSV ledger -> SQLite projection."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    OptionType,
    TradeSide,
)
from app.db.models import Account, CashFlow, CorporateAction, Instrument, Trade
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import (
    LedgerAccount,
    LedgerCashFlow,
    LedgerCorporateAction,
    LedgerInstrument,
    LedgerTrade,
)
from app.services.projection import builder


# --- shared test helpers --------------------------------------------------


def _ledger(tmp_path, broker_account_id="U1", name="Main"):
    return AccountLedger.create(
        tmp_path,
        LedgerAccount(
            broker_account_id=broker_account_id, name=name, base_currency="USD"
        ),
    )


def _li(symbol="AAPL", asset_class=AssetClass.STOCK, **kw):
    return LedgerInstrument(
        symbol=symbol, asset_class=asset_class, currency="USD", **kw
    )


def _lt(trade_id="T1", instrument="AAPL", **kw):
    fields = dict(
        trade_id=trade_id,
        instrument=instrument,
        side=TradeSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.25"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds_orig=Decimal("-1502.50"),
        proceeds_usd=Decimal("-1502.50"),
        executed_at=datetime(2026, 1, 5, 14, 30),
    )
    fields.update(kw)
    return LedgerTrade(**fields)


def _lc(flow_type=CashFlowType.DIVIDEND, instrument="AAPL", **kw):
    fields = dict(
        flow_type=flow_type,
        instrument=instrument,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("22.00"),
        amount_usd=Decimal("22.00"),
        occurred_at=datetime(2026, 2, 14, 0, 0),
    )
    fields.update(kw)
    return LedgerCashFlow(**fields)


def _lca(instrument="AAPL", **kw):
    fields = dict(
        instrument=instrument,
        action_type=CorporateActionType.SPLIT,
        ex_date=date(2024, 6, 10),
        ratio=Decimal("10"),
    )
    fields.update(kw)
    return LedgerCorporateAction(**fields)


# --- upsert_account -------------------------------------------------------


def test_upsert_account_creates(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    account = builder.upsert_account(db_session, ledger.read_account())

    assert account.id is not None
    assert account.broker_account_id == "U1"
    assert db_session.scalar(select(func.count()).select_from(Account)) == 1


def test_upsert_account_updates_existing(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    builder.upsert_account(db_session, ledger.read_account())
    # Second upsert with a changed name must update, not duplicate.
    again = builder.upsert_account(
        db_session, LedgerAccount(broker_account_id="U1", name="Renamed", base_currency="USD")
    )

    assert again.name == "Renamed"
    assert db_session.scalar(select(func.count()).select_from(Account)) == 1
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_projection_builder.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.projection'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/projection/__init__.py`:

```python
"""Projection builder — rebuilds the SQLite projection from a CSV ledger."""

from app.services.projection.builder import rebuild_account

__all__ = ["rebuild_account"]
```

新建 `backend/app/services/projection/builder.py`:

```python
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
```

(`rebuild_account` 在 `__init__.py` 里被 import —— 它将在 Task 6 实现。本任务先放一个占位实现以便 `__init__.py` 能 import:在 `builder.py` 末尾加临时函数,Task 6 替换。)

为避免 import 错误,在 `builder.py` 末尾加:

```python
def rebuild_account(session: Session, ledger: AccountLedger) -> Account:
    """Full rebuild of one account's projection. Implemented incrementally."""
    return upsert_account(session, ledger.read_account())
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `41 passed`(39 + 2 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/projection/ tests/test_projection_builder.py
git commit -m "Add projection package with account upsert"
```

(提交信息**不要**加 `Co-Authored-By` trailer。)

---

### Task 2: instrument upsert + project_instruments

按去重键 `(symbol, asset_class, strike, expiry, option_type)` find-or-create `Instrument`;`project_instruments` 投影所有证券并返回 `symbol → Instrument` 映射。

**Files:** Modify `backend/app/services/projection/builder.py`; Test `backend/tests/test_projection_builder.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_projection_builder.py` 末尾追加:

```python
# --- instruments ----------------------------------------------------------


def test_upsert_instrument_creates(db_session):
    inst = builder.upsert_instrument(db_session, _li("MSFT"))

    assert inst.id is not None
    assert inst.symbol == "MSFT"
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1


def test_upsert_instrument_updates_existing(db_session):
    builder.upsert_instrument(db_session, _li("AAPL", name="Apple Inc."))
    again = builder.upsert_instrument(db_session, _li("AAPL", name="Apple Corrected"))

    assert again.name == "Apple Corrected"
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1


def test_project_instruments_returns_symbol_map(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL"), _li("MSFT")])

    mapping = builder.project_instruments(db_session, ledger)

    assert set(mapping) == {"AAPL", "MSFT"}
    assert mapping["AAPL"].id is not None
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 2
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_projection_builder.py::test_upsert_instrument_creates -v` — Expected FAIL: `AttributeError: module 'app.services.projection.builder' has no attribute 'upsert_instrument'`

- [ ] **Step 3: 实现** — 在 `backend/app/services/projection/builder.py` 中:import 区加 `Instrument`、`LedgerInstrument`、`AccountLedger`(`AccountLedger` 可能已 import)。把 import 行改为:

```python
from app.db.models import Account, Instrument
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount, LedgerInstrument
```

在 `upsert_account` 之后加:

```python
def upsert_instrument(session: Session, li: LedgerInstrument) -> Instrument:
    """Find the Instrument by its natural key, or create it; update its fields."""
    inst = session.scalar(
        select(Instrument).where(
            Instrument.symbol == li.symbol,
            Instrument.asset_class == li.asset_class,
            Instrument.strike == li.strike,
            Instrument.expiry == li.expiry,
            Instrument.option_type == li.option_type,
        )
    )
    if inst is None:
        inst = Instrument(symbol=li.symbol, asset_class=li.asset_class)
        session.add(inst)
    inst.currency = li.currency
    inst.exchange = li.exchange
    inst.name = li.name
    inst.conid = li.conid
    inst.underlying_symbol = li.underlying_symbol
    inst.option_type = li.option_type
    inst.strike = li.strike
    inst.expiry = li.expiry
    inst.multiplier = li.multiplier
    inst.source = li.source
    inst.import_batch = li.import_batch
    session.flush()
    return inst


def project_instruments(
    session: Session, ledger: AccountLedger
) -> dict[str, Instrument]:
    """Upsert every instrument in the ledger; return a symbol -> Instrument map."""
    return {
        li.symbol: upsert_instrument(session, li)
        for li in ledger.instruments.read()
    }
```

说明:`Instrument.strike == li.strike` 等,当 `li.strike` 为 `None` 时 SQLAlchemy 自动生成 `IS NULL`,对股票(strike/expiry/option_type 均 None)的查询正确。

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `44 passed`(41 + 3 新),ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/services/projection/builder.py tests/test_projection_builder.py
git commit -m "Add instrument upsert and project_instruments"
```

---

### Task 3: project_trades

删除该账户的 `Trade` 行,从账本重插;解析 instrument symbol → instrument_id;引用未知 symbol 时抛 `ValueError`。

**Files:** Modify `backend/app/services/projection/builder.py`; Test `backend/tests/test_projection_builder.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_projection_builder.py` 末尾追加:

```python
# --- trades ---------------------------------------------------------------


def test_project_trades_inserts(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.trades.append([_lt("T1"), _lt("T2")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_trades(db_session, account, ledger, instruments)

    trades = db_session.scalars(select(Trade)).all()
    assert {t.trade_id for t in trades} == {"T1", "T2"}
    t1 = next(t for t in trades if t.trade_id == "T1")
    assert t1.account_id == account.id
    assert t1.instrument_id == instruments["AAPL"].id
    assert t1.proceeds == Decimal("-1502.50")  # mapped from proceeds_orig


def test_project_trades_replaces_existing(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.trades.append([_lt("T1")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_trades(db_session, account, ledger, instruments)
    # Project again — must replace, not duplicate.
    builder.project_trades(db_session, account, ledger, instruments)

    assert db_session.scalar(select(func.count()).select_from(Trade)) == 1


def test_project_trades_unknown_instrument_raises(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.trades.append([_lt("T1", instrument="GHOST")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)  # empty

    with pytest.raises(ValueError, match="GHOST"):
        builder.project_trades(db_session, account, ledger, instruments)
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_projection_builder.py::test_project_trades_inserts -v` — Expected FAIL: `AttributeError: module 'app.services.projection.builder' has no attribute 'project_trades'`

- [ ] **Step 3: 实现** — 在 `backend/app/services/projection/builder.py` 中,把 import 行扩展为:

```python
from app.db.models import Account, CashFlow, CorporateAction, Instrument, Trade
from app.services.ledger.rows import (
    LedgerAccount,
    LedgerCashFlow,
    LedgerCorporateAction,
    LedgerInstrument,
)
```

(本任务只用到 `Trade`,但一次把 import 补齐避免后续任务反复改;`CashFlow`/`CorporateAction`/`LedgerCashFlow`/`LedgerCorporateAction` 在 Task 4/5 用到。若 ruff 报 F401 未使用,先只 import 本任务需要的 `Trade`,Task 4/5 再加。)

在 `project_instruments` 之后加:

```python
def project_trades(
    session: Session,
    account: Account,
    ledger: AccountLedger,
    instruments: dict[str, Instrument],
) -> None:
    """Delete this account's trades, then re-insert them from the ledger."""
    session.query(Trade).filter_by(account_id=account.id).delete()
    for lt in ledger.trades.read():
        inst = instruments.get(lt.instrument)
        if inst is None:
            raise ValueError(
                f"trade {lt.trade_id} references unknown instrument "
                f"{lt.instrument!r} (not in instruments.csv)"
            )
        session.add(
            Trade(
                account_id=account.id,
                instrument_id=inst.id,
                trade_id=lt.trade_id,
                side=lt.side,
                open_close=lt.open_close,
                quantity=lt.quantity,
                price=lt.price,
                currency=lt.currency,
                fx_rate_to_usd=lt.fx_rate_to_usd,
                proceeds=lt.proceeds_orig,
                proceeds_usd=lt.proceeds_usd,
                commission=lt.commission_orig,
                commission_usd=lt.commission_usd,
                realized_pnl_ibkr=lt.realized_pnl_ibkr,
                executed_at=lt.executed_at,
                source=lt.source,
                import_batch=lt.import_batch,
            )
        )
    session.flush()
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `47 passed`(44 + 3 新),ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/services/projection/builder.py tests/test_projection_builder.py
git commit -m "Add project_trades"
```

---

### Task 4: project_cash_flows

删除该账户的 `CashFlow` 行,从账本重插;`amount_orig`→`amount`;instrument 可空(入金无标的)。

**Files:** Modify `backend/app/services/projection/builder.py`; Test `backend/tests/test_projection_builder.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_projection_builder.py` 末尾追加:

```python
# --- cash flows -----------------------------------------------------------


def test_project_cash_flows_inserts(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.cash_flows.append([_lc(external_id="DIV-1")])

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_cash_flows(db_session, account, ledger, instruments)

    flow = db_session.scalars(select(CashFlow)).one()
    assert flow.account_id == account.id
    assert flow.instrument_id == instruments["AAPL"].id
    assert flow.amount == Decimal("22.00")  # mapped from amount_orig


def test_project_cash_flows_deposit_without_instrument(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.cash_flows.append(
        [
            _lc(
                flow_type=CashFlowType.DEPOSIT,
                instrument=None,
                amount_orig=Decimal("5000"),
                amount_usd=Decimal("5000"),
                external_id="DEP-1",
            )
        ]
    )

    account = builder.upsert_account(db_session, ledger.read_account())
    instruments = builder.project_instruments(db_session, ledger)
    builder.project_cash_flows(db_session, account, ledger, instruments)

    flow = db_session.scalars(select(CashFlow)).one()
    assert flow.instrument_id is None
    assert flow.amount == Decimal("5000")
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_projection_builder.py::test_project_cash_flows_inserts -v` — Expected FAIL: `AttributeError: module 'app.services.projection.builder' has no attribute 'project_cash_flows'`

- [ ] **Step 3: 实现** — 在 `backend/app/services/projection/builder.py` 确保 `CashFlow` 已 import(见 Task 3 的 import 行),在 `project_trades` 之后加:

```python
def project_cash_flows(
    session: Session,
    account: Account,
    ledger: AccountLedger,
    instruments: dict[str, Instrument],
) -> None:
    """Delete this account's cash flows, then re-insert them from the ledger."""
    session.query(CashFlow).filter_by(account_id=account.id).delete()
    for lc in ledger.cash_flows.read():
        instrument_id = None
        if lc.instrument is not None:
            inst = instruments.get(lc.instrument)
            if inst is None:
                raise ValueError(
                    f"cash flow references unknown instrument "
                    f"{lc.instrument!r} (not in instruments.csv)"
                )
            instrument_id = inst.id
        session.add(
            CashFlow(
                account_id=account.id,
                instrument_id=instrument_id,
                flow_type=lc.flow_type,
                amount=lc.amount_orig,
                currency=lc.currency,
                fx_rate_to_usd=lc.fx_rate_to_usd,
                amount_usd=lc.amount_usd,
                description=lc.description,
                external_id=lc.external_id,
                occurred_at=lc.occurred_at,
                source=lc.source,
                import_batch=lc.import_batch,
            )
        )
    session.flush()
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `49 passed`(47 + 2 新),ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/services/projection/builder.py tests/test_projection_builder.py
git commit -m "Add project_cash_flows"
```

---

### Task 5: project_corporate_actions

`corporate_actions` 是全局表(按 instrument 关联,无 account_id)。按键 `(instrument_id, action_type, ex_date)` upsert。

**Files:** Modify `backend/app/services/projection/builder.py`; Test `backend/tests/test_projection_builder.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_projection_builder.py` 末尾追加:

```python
# --- corporate actions ----------------------------------------------------


def test_project_corporate_actions_upserts(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.corporate_actions.append([_lca()])

    instruments = builder.project_instruments(db_session, ledger)
    builder.project_corporate_actions(db_session, ledger, instruments)

    ca = db_session.scalars(select(CorporateAction)).one()
    assert ca.instrument_id == instruments["AAPL"].id
    assert ca.action_type == CorporateActionType.SPLIT
    assert ca.ratio == Decimal("10")


def test_project_corporate_actions_idempotent(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    ledger.instruments.append([_li("AAPL")])
    ledger.corporate_actions.append([_lca()])

    instruments = builder.project_instruments(db_session, ledger)
    builder.project_corporate_actions(db_session, ledger, instruments)
    builder.project_corporate_actions(db_session, ledger, instruments)

    assert (
        db_session.scalar(select(func.count()).select_from(CorporateAction)) == 1
    )
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_projection_builder.py::test_project_corporate_actions_upserts -v` — Expected FAIL: `AttributeError: module 'app.services.projection.builder' has no attribute 'project_corporate_actions'`

- [ ] **Step 3: 实现** — 在 `backend/app/services/projection/builder.py` 确保 `CorporateAction` 已 import,在 `project_cash_flows` 之后加:

```python
def project_corporate_actions(
    session: Session,
    ledger: AccountLedger,
    instruments: dict[str, Instrument],
) -> None:
    """Upsert corporate actions by (instrument, action_type, ex_date).

    corporate_actions is a global, instrument-scoped table — upserted rather
    than deleted-per-account, since the same action may appear in several
    accounts' ledgers.
    """
    for lca in ledger.corporate_actions.read():
        inst = instruments.get(lca.instrument)
        if inst is None:
            raise ValueError(
                f"corporate action references unknown instrument "
                f"{lca.instrument!r} (not in instruments.csv)"
            )
        ca = session.scalar(
            select(CorporateAction).where(
                CorporateAction.instrument_id == inst.id,
                CorporateAction.action_type == lca.action_type,
                CorporateAction.ex_date == lca.ex_date,
            )
        )
        if ca is None:
            ca = CorporateAction(
                instrument_id=inst.id,
                action_type=lca.action_type,
                ex_date=lca.ex_date,
            )
            session.add(ca)
        ca.ratio = lca.ratio
        ca.description = lca.description
        ca.external_id = lca.external_id
        ca.source = lca.source
        ca.import_batch = lca.import_batch
    session.flush()
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `51 passed`(49 + 2 新),ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/services/projection/builder.py tests/test_projection_builder.py
git commit -m "Add project_corporate_actions"
```

---

### Task 6: rebuild_account 编排 + 幂等集成测试

把 Task 1 末尾的占位 `rebuild_account` 替换为完整编排,并验证整套重建幂等。

**Files:** Modify `backend/app/services/projection/builder.py`; Test `backend/tests/test_projection_builder.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_projection_builder.py` 末尾追加:

```python
# --- rebuild_account ------------------------------------------------------


def _populate(ledger):
    ledger.instruments.append([_li("AAPL")])
    ledger.trades.append([_lt("T1"), _lt("T2")])
    ledger.cash_flows.append([_lc(external_id="DIV-1")])
    ledger.corporate_actions.append([_lca()])


def test_rebuild_account_full(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    _populate(ledger)

    account = builder.rebuild_account(db_session, ledger)

    assert account.broker_account_id == "U1"
    assert db_session.scalar(select(func.count()).select_from(Trade)) == 2
    assert db_session.scalar(select(func.count()).select_from(CashFlow)) == 1
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(CorporateAction)) == 1
    )


def test_rebuild_account_is_idempotent(db_session, tmp_path):
    ledger = _ledger(tmp_path)
    _populate(ledger)

    builder.rebuild_account(db_session, ledger)
    builder.rebuild_account(db_session, ledger)  # second rebuild

    assert db_session.scalar(select(func.count()).select_from(Account)) == 1
    assert db_session.scalar(select(func.count()).select_from(Trade)) == 2
    assert db_session.scalar(select(func.count()).select_from(CashFlow)) == 1
    assert db_session.scalar(select(func.count()).select_from(Instrument)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(CorporateAction)) == 1
    )
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_projection_builder.py::test_rebuild_account_full -v` — Expected FAIL: `AssertionError`(占位 `rebuild_account` 只做了 account,trades 计数为 0)

- [ ] **Step 3: 实现** — 在 `backend/app/services/projection/builder.py` 中,把 Task 1 末尾的占位 `rebuild_account` 整体替换为:

```python
def rebuild_account(session: Session, ledger: AccountLedger) -> Account:
    """Full rebuild of one account's DB projection from its CSV ledger.

    Account-scoped tables (trades, cash_flows) are deleted and re-inserted;
    global tables (instruments, corporate_actions) are upserted by key.
    Running this repeatedly is idempotent.
    """
    account = upsert_account(session, ledger.read_account())
    instruments = project_instruments(session, ledger)
    project_trades(session, account, ledger, instruments)
    project_cash_flows(session, account, ledger, instruments)
    project_corporate_actions(session, ledger, instruments)
    session.commit()
    return account
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `53 passed`(51 + 2 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/projection/builder.py tests/test_projection_builder.py
git commit -m "Add rebuild_account orchestration"
```

---

## Self-Review

- **Spec 覆盖(spec 第 2 节数据流)**:projection builder「读 CSV 账本 → 全量重建该账户 DB 行」= `rebuild_account`(Task 6);账户级表删+重插 = `project_trades`/`project_cash_flows`(Task 3/4);全局表 upsert = `project_instruments`/`project_corporate_actions`(Task 2/5);DB 可重建/幂等 = `test_rebuild_account_is_idempotent`(Task 6)。`positions_snapshot` 不投影 —— 已在计划与代码注释说明它由后续行情快照派生。
- **占位符**:无 TBD;每步含完整代码或确切命令。Task 1 的占位 `rebuild_account` 是有意的最小可 import 实现,Task 6 明确替换 —— 不是占位符红旗。
- **类型一致性**:`upsert_account`、`upsert_instrument`、`project_instruments`、`project_trades`、`project_cash_flows`、`project_corporate_actions`、`rebuild_account` 的签名在各任务与测试中一致;字段映射(`proceeds_orig`→`proceeds`、`commission_orig`→`commission`、`amount_orig`→`amount`、`instrument`→`instrument_id`)在 Task 3/4/5 与「字段映射」节一致。
- 测试计数:39 → 41 → 44 → 47 → 49 → 51 → 53,与各步 Expected 一致。
- **范围**:只做 M3(账本 → DB 投影)。不含 FX(M4)、P&L 引擎(M5)、IBKR 解析器(M6)、行情快照。
