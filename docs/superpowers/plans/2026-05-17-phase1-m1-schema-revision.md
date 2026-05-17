# Phase 1 M1 — Schema 调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已建的 Phase 1.1 core schema 按设计 spec 第 4.5 节调整到位 —— 溯源列、USD 货币列、命名修正,并重新生成 Alembic migration。

**Architecture:** 6 张表的 SQLAlchemy 2.0 typed-`Mapped` 模型在 `backend/app/db/models.py`。`trades / cash_flows / instruments / corporate_actions` 加溯源列;`*_base` 货币列改名 `*_usd` 并在 trades/cash_flows 上设 NOT NULL;`positions_snapshot` 的 `*_usd` 保持可空。

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic, pytest, uv, ruff。命令从 `backend/` 目录运行,`uv run --no-sync` 前缀。

**参考:** 设计 spec `docs/superpowers/specs/2026-05-17-phase1-data-architecture-pnl-design.md`(第 4 节)。

---

### Task 1: 提交 Phase 1.1 schema 基线

worktree 里已有一版通过 13 个测试的 schema 代码尚未提交。先把它作为基线提交,后续任务在其上做 TDD 改动。

**Files:**
- Commit(均已存在,未提交):`backend/app/db/models.py`, `backend/tests/conftest.py`, `backend/tests/test_models.py`, `backend/alembic/env.py`, `backend/pyproject.toml`

- [ ] **Step 1: 确认测试与 lint 全绿**

Run(从 `backend/`):`uv run --no-sync pytest -q && uv run --no-sync ruff check .`
Expected: `13 passed`,ruff `All checks passed!`

- [ ] **Step 2: 提交基线**

```bash
cd backend
git add app/db/models.py tests/conftest.py tests/test_models.py alembic/env.py pyproject.toml
git commit -m "Add Phase 1.1 core database schema (6 tables, 13 tests)"
```

注:`backend/data/` 与 `app.db` 已 gitignored,不会进提交。migration 尚未生成(Task 5 统一生成)。

---

### Task 2: 溯源列 source / import_batch

给 `trades / cash_flows / instruments / corporate_actions` 各加 `source`(枚举 `RecordSource`)和 `import_batch`(可空字符串)。`accounts` 与 `positions_snapshot` 不加。

**Files:**
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_models.py` 末尾追加:

```python
# --- provenance -----------------------------------------------------------


def test_trade_source_defaults_to_parsed(db_session, account, instrument):
    trade = _make_trade(account, instrument)
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    assert trade.source == models.RecordSource.PARSED
    assert trade.import_batch is None


def test_instrument_can_be_marked_manual(db_session):
    inst = models.Instrument(
        symbol="MSFT",
        asset_class=models.AssetClass.STOCK,
        currency="USD",
        source=models.RecordSource.MANUAL,
        import_batch="manual",
    )
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)

    assert inst.source == models.RecordSource.MANUAL
    assert inst.import_batch == "manual"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run --no-sync pytest tests/test_models.py::test_trade_source_defaults_to_parsed -v`
Expected: FAIL —— `AttributeError: 'Trade' object has no attribute 'source'`

- [ ] **Step 3: 实现**

在 `backend/app/db/models.py` 的枚举区(`CorporateActionType` 之后)加:

```python
class RecordSource(enum.Enum):
    PARSED = "PARSED"
    MANUAL = "MANUAL"
```

在 `TimestampMixin` 之后加 mixin:

```python
class ProvenanceMixin:
    """source / import_batch — 区分解析得来的行与用户手改/新增的行。"""

    source: Mapped[RecordSource] = mapped_column(default=RecordSource.PARSED)
    import_batch: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

把这 4 个类的声明加上 `ProvenanceMixin`(放在 `TimestampMixin` 前):

```python
class Instrument(ProvenanceMixin, TimestampMixin, Base):
class Trade(ProvenanceMixin, TimestampMixin, Base):
class CashFlow(ProvenanceMixin, TimestampMixin, Base):
class CorporateAction(ProvenanceMixin, TimestampMixin, Base):
```

`Account` 与 `PositionSnapshot` 的声明**不动**。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .`
Expected: `15 passed`,ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/db/models.py tests/test_models.py
git commit -m "Add source/import_batch provenance columns to ledger tables"
```

---

### Task 3: 货币列改名 *_base → *_usd 并设 NOT NULL

`trades` 与 `cash_flows`:`fx_rate_to_base`→`fx_rate_to_usd`、`proceeds_base`→`proceeds_usd`、`commission_base`→`commission_usd`、`amount_base`→`amount_usd`,且这些列改为 NOT NULL。`positions_snapshot`:`market_value_base`→`market_value_usd`、`unrealized_pnl_base`→`unrealized_pnl_usd`,**保持可空**。

**Files:**
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: 改测试(此即新规格)**

在 `backend/tests/test_models.py` 中,把 `_make_trade` 辅助函数整体替换为(USD 列现为必填):

```python
def _make_trade(account, instrument, **overrides):
    fields = dict(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_id="EXEC-001",
        side=models.TradeSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.25"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds=Decimal("-1502.50"),
        proceeds_usd=Decimal("-1502.50"),
        commission=Decimal("1.00"),
        commission_usd=Decimal("1.00"),
        executed_at=datetime(2026, 1, 5, 14, 30),
    )
    fields.update(overrides)
    return models.Trade(**fields)
```

把 `test_trade_round_trip_dual_currency` 整体替换为(用一笔 EUR 交易验证双币):

```python
def test_trade_round_trip_dual_currency(db_session, account, instrument):
    trade = _make_trade(
        account,
        instrument,
        currency="EUR",
        fx_rate_to_usd=Decimal("1.08"),
        proceeds=Decimal("-1390.00"),
        proceeds_usd=Decimal("-1501.20"),
    )
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    assert trade.id is not None
    assert trade.currency == "EUR"
    assert trade.proceeds == Decimal("-1390.00")
    assert trade.proceeds_usd == Decimal("-1501.20")
    assert trade.fx_rate_to_usd == Decimal("1.08")
```

把 `test_cash_flow_round_trip` 整体替换为:

```python
def test_cash_flow_round_trip(db_session, account, instrument):
    flow = models.CashFlow(
        account_id=account.id,
        instrument_id=instrument.id,
        flow_type=models.CashFlowType.DIVIDEND,
        amount=Decimal("22.00"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_usd=Decimal("22.00"),
        occurred_at=datetime(2026, 2, 14, 0, 0),
    )
    db_session.add(flow)
    db_session.commit()
    db_session.refresh(flow)

    assert flow.id is not None
    assert flow.flow_type == models.CashFlowType.DIVIDEND
    assert flow.instrument.symbol == "AAPL"
```

把 `test_cash_flow_deposit_without_instrument` 整体替换为:

```python
def test_cash_flow_deposit_without_instrument(db_session, account):
    flow = models.CashFlow(
        account_id=account.id,
        flow_type=models.CashFlowType.DEPOSIT,
        amount=Decimal("5000.00"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_usd=Decimal("5000.00"),
        occurred_at=datetime(2026, 1, 1, 0, 0),
    )
    db_session.add(flow)
    db_session.commit()
    db_session.refresh(flow)

    assert flow.instrument_id is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run --no-sync pytest tests/test_models.py::test_trade_round_trip_dual_currency -v`
Expected: FAIL —— `TypeError: 'fx_rate_to_usd' is an invalid keyword argument for Trade`

- [ ] **Step 3: 实现**

在 `backend/app/db/models.py` 的 `Trade` 类,把货币相关列替换为:

```python
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate_to_usd: Mapped[Decimal] = mapped_column(_FX)
    proceeds: Mapped[Decimal] = mapped_column(_MONEY)
    proceeds_usd: Mapped[Decimal] = mapped_column(_MONEY)
    commission: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    commission_usd: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
```

(原 `proceeds` / `commission` 行保留;删除 `proceeds_base` / `commission_base` / `fx_rate_to_base` 三行,换成上面的 `_usd` 版本。`Mapped[Decimal]` 非 Optional 即 NOT NULL。)

在 `CashFlow` 类,把货币相关列替换为:

```python
    amount: Mapped[Decimal] = mapped_column(_MONEY)
    currency: Mapped[str] = mapped_column(String(3))
    fx_rate_to_usd: Mapped[Decimal] = mapped_column(_FX)
    amount_usd: Mapped[Decimal] = mapped_column(_MONEY)
```

(删除 `fx_rate_to_base` / `amount_base`。)

在 `PositionSnapshot` 类,把两列改名(保持可空):

```python
    market_value_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    unrealized_pnl_usd: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
```

(`market_value` 与 `unrealized_pnl` 原始列保留不动;仅把 `market_value_base`→`market_value_usd`、`unrealized_pnl_base`→`unrealized_pnl_usd`。)

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .`
Expected: `15 passed`,ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/db/models.py tests/test_models.py
git commit -m "Rename currency columns to *_usd; require USD amounts on trades/cash_flows"
```

---

### Task 4: 重命名 realized_pnl → realized_pnl_ibkr

明确该列是 IBKR 报的已实现盈亏,与自研 P&L 引擎算出的区分。

**Files:**
- Modify: `backend/app/db/models.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_models.py` 的 trades 区追加:

```python
def test_trade_realized_pnl_ibkr_optional(db_session, account, instrument):
    trade = _make_trade(account, instrument)
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    assert trade.realized_pnl_ibkr is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run --no-sync pytest tests/test_models.py::test_trade_realized_pnl_ibkr_optional -v`
Expected: FAIL —— `AttributeError: 'Trade' object has no attribute 'realized_pnl_ibkr'`

- [ ] **Step 3: 实现**

在 `backend/app/db/models.py` 的 `Trade` 类,把:

```python
    realized_pnl: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
```

改为:

```python
    realized_pnl_ibkr: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .`
Expected: `16 passed`,ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/db/models.py tests/test_models.py
git commit -m "Rename Trade.realized_pnl to realized_pnl_ibkr"
```

---

### Task 5: 生成并验证 Alembic migration

schema 已定型,生成单个 migration 并验证可升降级。

**Files:**
- Create: `backend/alembic/versions/<hash>_phase1_core_schema.py`(autogenerate 生成)

- [ ] **Step 1: 确保 data 目录存在**

Run(从 `backend/`):`mkdir -p data`
说明:`alembic/env.py` 用 `settings.database_url`(`sqlite:///./data/app.db`),目录不存在会报 `unable to open database file`。

- [ ] **Step 2: 生成 migration**

Run: `uv run --no-sync alembic revision --autogenerate -m "phase1 core schema"`
Expected: 输出 `Detected added table` ×6(accounts / instruments / trades / cash_flows / positions_snapshot / corporate_actions),在 `alembic/versions/` 生成一个文件。

- [ ] **Step 3: 验证升级**

Run: `uv run --no-sync alembic upgrade head && uv run --no-sync alembic current`
Expected: `Running upgrade -> <hash>, phase1 core schema`;`current` 显示 `<hash> (head)`

- [ ] **Step 4: 验证可逆(降级再升级)**

Run: `uv run --no-sync alembic downgrade base && uv run --no-sync alembic upgrade head`
Expected: 先 `Running downgrade`,再 `Running upgrade`,均无报错。

- [ ] **Step 5: 全量验证**

Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .`
Expected: `16 passed`;ruff `All checks passed!`(`alembic/versions` 已在 `pyproject.toml` 的 `extend-exclude`)

- [ ] **Step 6: 提交**

```bash
git add alembic/versions/
git commit -m "Generate Alembic migration for Phase 1 core schema"
```

---

## Self-Review

- **Spec 覆盖(spec 第 4.5 节 6 项改动)**:删税 = 基线已含(Task 1);`*_base`→`*_usd` = Task 3;NOT NULL = Task 3;`realized_pnl`→`realized_pnl_ibkr` = Task 4;加 `source`/`import_batch` = Task 2;重新生成 migration = Task 5。全覆盖。
- **占位符**:无 TBD/TODO,每步含完整代码或确切命令。
- **类型一致性**:`RecordSource`、`ProvenanceMixin`、`fx_rate_to_usd`、`proceeds_usd`、`commission_usd`、`amount_usd`、`market_value_usd`、`unrealized_pnl_usd`、`realized_pnl_ibkr` 在各任务中命名一致。
- 测试计数:基线 13 → Task 2 后 15 → Task 4 后 16,与各步 Expected 一致。

## 范围说明

本计划只覆盖 M1(schema 调整)。M2(CSV 账本)、M3(projection builder)、M4(FX 层)、M5(P&L 引擎)在各里程碑开始时另写计划。M6(IBKR 解析器)需真实样本,另开 spec。
