# Phase 1 M2 — CSV 账本子系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 CSV 账本子系统 —— 读取与「去重追加」每账户的账本文件(`data/accounts/<id>/*.csv` + `account.toml`),它是设计中「文件即真相源」的真相源载体。

**Architecture:** 新包 `app/services/ledger/`。账本行用 Pydantic 模型表示(读取用户手编的 CSV 时自带校验)。一个泛型 `LedgerTable` 负责单个 CSV 的读 + 去重追加;`AccountLedger` 把一个账户目录下的 4 张表 + `account.toml` 组合起来。本里程碑只做文件 I/O 与去重,不碰数据库(投影构建是 M3)、不碰解析器(M6)。

**Tech Stack:** Python 3.12, Pydantic v2, 标准库 `csv` / `tomllib` / `pathlib`, pytest, uv, ruff。命令从 `backend/` 运行,`uv run --no-sync` 前缀。

**参考:** 设计 spec `docs/superpowers/specs/2026-05-17-phase1-data-architecture-pnl-design.md` 第 3 节(CSV 账本格式)。

## File Structure

- `backend/app/db/enums.py` — **新建**。从 `models.py` 抽出的 7 个领域枚举,供 ORM 与账本层共用(账本层因此无需 import ORM)。
- `backend/app/db/models.py` — **修改**。改为从 `enums.py` import 枚举。
- `backend/app/services/ledger/__init__.py` — **新建**,空包标记。
- `backend/app/services/ledger/rows.py` — **新建**。5 个 Pydantic 账本行模型,各带 `dedup_key`。
- `backend/app/services/ledger/table.py` — **新建**。泛型 `LedgerTable`(读 / 去重追加)+ `AppendReport`。
- `backend/app/services/ledger/account_ledger.py` — **新建**。`AccountLedger`(组合 4 张表 + account.toml 读写)。
- `backend/tests/test_enums.py`、`test_ledger_rows.py`、`test_ledger_table.py`、`test_account_ledger.py` — **新建**测试。

---

### Task 1: 抽出领域枚举到 app/db/enums.py

账本层不应 import ORM。把 7 个纯枚举移到独立模块,`models.py` 与账本层都从这里 import。

**Files:** Create `backend/app/db/enums.py`; Modify `backend/app/db/models.py`; Test `backend/tests/test_enums.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_enums.py`:

```python
"""The 7 domain enums must be importable from app.db.enums without importing the ORM."""

from app.db import enums


def test_all_domain_enums_exposed():
    assert enums.AssetClass.STOCK.value == "STOCK"
    assert enums.OptionType.CALL.value == "CALL"
    assert enums.TradeSide.BUY.value == "BUY"
    assert enums.OpenClose.OPEN.value == "OPEN"
    assert enums.CashFlowType.DIVIDEND.value == "DIVIDEND"
    assert enums.CorporateActionType.SPLIT.value == "SPLIT"
    assert enums.RecordSource.PARSED.value == "PARSED"


def test_models_reexports_same_enum_objects():
    """models.py must re-export the identical enum objects, not redefine them."""
    from app.db import models

    assert models.AssetClass is enums.AssetClass
    assert models.RecordSource is enums.RecordSource
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_enums.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.db.enums'`

- [ ] **Step 3: 实现** — 新建 `backend/app/db/enums.py`,把 `models.py` 里这 7 个枚举类**原样**搬过来:

```python
"""Domain enums shared by the ORM models and the CSV ledger layer."""

import enum


class AssetClass(enum.Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    OPTION = "OPTION"


class OptionType(enum.Enum):
    CALL = "CALL"
    PUT = "PUT"


class TradeSide(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OpenClose(enum.Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"


class CashFlowType(enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    OTHER = "OTHER"


class CorporateActionType(enum.Enum):
    SPLIT = "SPLIT"
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    MERGER = "MERGER"
    SPINOFF = "SPINOFF"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"


class RecordSource(enum.Enum):
    PARSED = "PARSED"
    MANUAL = "MANUAL"
```

然后在 `backend/app/db/models.py`:删除那 7 个 `class ... (enum.Enum)` 定义,在文件顶部 import 区加:

```python
from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    OpenClose,
    OptionType,
    RecordSource,
    TradeSide,
)
```

注意:`models.py` 中其余代码继续用裸名 `AssetClass` 等,引用不变。若 `import enum` 在删除后已无其他用处,一并删掉该 import(用 `uv run --no-sync ruff check .` 会报 F401,据此判断)。

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `18 passed`(16 原有 + 2 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/db/enums.py app/db/models.py tests/test_enums.py
git commit -m "Extract domain enums to app/db/enums.py"
```

(提交信息**不要**加 `Co-Authored-By` trailer。)

---

### Task 2: 账本行模型 rows.py

5 个 Pydantic v2 模型,字段顺序即 CSV 列顺序(`source`、`import_batch` 居首)。每个交易类模型有 `dedup_key` 属性。

**Files:** Create `backend/app/services/ledger/__init__.py`, `backend/app/services/ledger/rows.py`; Test `backend/tests/test_ledger_rows.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_ledger_rows.py`:

```python
from datetime import date, datetime
from decimal import Decimal

from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    OptionType,
    RecordSource,
    TradeSide,
)
from app.services.ledger import rows


def test_trade_defaults_and_dedup_key():
    t = rows.LedgerTrade(
        trade_id="EXEC-1",
        instrument="AAPL",
        side=TradeSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.25"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds_orig=Decimal("-1502.50"),
        proceeds_usd=Decimal("-1502.50"),
        executed_at=datetime(2026, 1, 5, 14, 30),
    )
    assert t.source == RecordSource.PARSED
    assert t.import_batch is None
    assert t.commission_orig == Decimal("0")
    assert t.dedup_key == ("EXEC-1",)


def test_instrument_dedup_key_includes_option_fields():
    opt = rows.LedgerInstrument(
        symbol="AAPL 250117C00200000",
        asset_class=AssetClass.OPTION,
        currency="USD",
        option_type=OptionType.CALL,
        strike=Decimal("200"),
        expiry=date(2025, 1, 17),
    )
    assert opt.multiplier == 1
    assert opt.dedup_key == (
        "AAPL 250117C00200000",
        AssetClass.OPTION,
        Decimal("200"),
        date(2025, 1, 17),
        OptionType.CALL,
    )


def test_cash_flow_dedup_key_prefers_external_id():
    with_id = rows.LedgerCashFlow(
        flow_type=CashFlowType.DIVIDEND,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("22"),
        amount_usd=Decimal("22"),
        external_id="DIV-9",
        occurred_at=datetime(2026, 2, 14),
    )
    assert with_id.dedup_key == ("DIV-9",)


def test_cash_flow_dedup_key_falls_back_to_content_hash():
    no_id = rows.LedgerCashFlow(
        flow_type=CashFlowType.DEPOSIT,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("5000"),
        amount_usd=Decimal("5000"),
        occurred_at=datetime(2026, 1, 1),
    )
    assert no_id.dedup_key == (
        CashFlowType.DEPOSIT,
        datetime(2026, 1, 1),
        Decimal("5000"),
    )


def test_corporate_action_dedup_key():
    ca = rows.LedgerCorporateAction(
        instrument="AAPL",
        action_type=CorporateActionType.SPLIT,
        ex_date=date(2024, 6, 10),
        ratio=Decimal("10"),
    )
    assert ca.dedup_key == ("AAPL", CorporateActionType.SPLIT, date(2024, 6, 10))


def test_account_model():
    acct = rows.LedgerAccount(
        broker_account_id="U1", name="Main", base_currency="USD"
    )
    assert acct.broker == "IBKR"
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_ledger_rows.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.ledger'`

- [ ] **Step 3: 实现** — 新建空文件 `backend/app/services/ledger/__init__.py`(内容:`"""CSV ledger subsystem — the file-based source of truth."""`),再新建 `backend/app/services/ledger/rows.py`:

```python
"""Pydantic models for one row of each CSV ledger file.

Field declaration order IS the CSV column order; `source` / `import_batch`
lead every file. `dedup_key` returns the hashable identity used to skip
re-importing a row that is already in the ledger.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    OpenClose,
    OptionType,
    RecordSource,
    TradeSide,
)


class LedgerInstrument(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    symbol: str
    asset_class: AssetClass
    currency: str
    exchange: str | None = None
    name: str | None = None
    conid: str | None = None
    underlying_symbol: str | None = None
    option_type: OptionType | None = None
    strike: Decimal | None = None
    expiry: date | None = None
    multiplier: int = 1

    @property
    def dedup_key(self) -> tuple:
        return (
            self.symbol,
            self.asset_class,
            self.strike,
            self.expiry,
            self.option_type,
        )


class LedgerTrade(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    trade_id: str
    instrument: str
    side: TradeSide
    open_close: OpenClose | None = None
    quantity: Decimal
    price: Decimal
    currency: str
    fx_rate_to_usd: Decimal
    proceeds_orig: Decimal
    proceeds_usd: Decimal
    commission_orig: Decimal = Decimal("0")
    commission_usd: Decimal = Decimal("0")
    realized_pnl_ibkr: Decimal | None = None
    executed_at: datetime

    @property
    def dedup_key(self) -> tuple:
        return (self.trade_id,)


class LedgerCashFlow(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    flow_type: CashFlowType
    instrument: str | None = None
    currency: str
    fx_rate_to_usd: Decimal
    amount_orig: Decimal
    amount_usd: Decimal
    description: str | None = None
    external_id: str | None = None
    occurred_at: datetime

    @property
    def dedup_key(self) -> tuple:
        if self.external_id:
            return (self.external_id,)
        return (self.flow_type, self.occurred_at, self.amount_orig)


class LedgerCorporateAction(BaseModel):
    source: RecordSource = RecordSource.PARSED
    import_batch: str | None = None
    instrument: str
    action_type: CorporateActionType
    ex_date: date
    ratio: Decimal | None = None
    description: str | None = None
    external_id: str | None = None

    @property
    def dedup_key(self) -> tuple:
        return (self.instrument, self.action_type, self.ex_date)


class LedgerAccount(BaseModel):
    """Mirrors account.toml — account metadata, no CSV / dedup."""

    broker_account_id: str
    name: str
    base_currency: str
    broker: str = "IBKR"
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `24 passed`(18 + 6 新),ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/services/ledger/__init__.py app/services/ledger/rows.py tests/test_ledger_rows.py
git commit -m "Add Pydantic ledger row models"
```

---

### Task 3: 泛型 LedgerTable —— 读 + 去重追加

一个 CSV 文件的读写器:`read()` 返回行模型列表;`append()` 跳过去重键已存在的行(含本批次内部去重),只把新行追加到文件。

**Files:** Create `backend/app/services/ledger/table.py`; Test `backend/tests/test_ledger_table.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_ledger_table.py`:

```python
from datetime import datetime
from decimal import Decimal

from app.db.enums import TradeSide
from app.services.ledger.rows import LedgerTrade
from app.services.ledger.table import LedgerTable


def _trade(trade_id: str, **kw) -> LedgerTrade:
    fields = dict(
        trade_id=trade_id,
        instrument="AAPL",
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


def test_read_missing_file_returns_empty(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    assert table.read() == []


def test_append_then_read_round_trips(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    report = table.append([_trade("EXEC-1"), _trade("EXEC-2")])

    assert (report.added, report.skipped) == (2, 0)
    rows = table.read()
    assert [r.trade_id for r in rows] == ["EXEC-1", "EXEC-2"]
    assert rows[0].quantity == Decimal("10")
    assert rows[0].executed_at == datetime(2026, 1, 5, 14, 30)
    assert rows[0].open_close is None
    assert rows[0].realized_pnl_ibkr is None


def test_append_skips_keys_already_in_file(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    table.append([_trade("EXEC-1")])
    report = table.append([_trade("EXEC-1"), _trade("EXEC-3")])

    assert (report.added, report.skipped) == (1, 1)
    assert [r.trade_id for r in table.read()] == ["EXEC-1", "EXEC-3"]


def test_append_dedups_within_one_batch(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    report = table.append([_trade("EXEC-9"), _trade("EXEC-9")])

    assert (report.added, report.skipped) == (1, 1)
    assert len(table.read()) == 1


def test_csv_has_provenance_columns_first(tmp_path):
    path = tmp_path / "trades.csv"
    LedgerTable(path, LedgerTrade).append([_trade("EXEC-1")])
    header = path.read_text().splitlines()[0]
    assert header.startswith("source,import_batch,trade_id,")
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_ledger_table.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.ledger.table'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/ledger/table.py`:

```python
"""Generic reader/appender for one CSV ledger file.

`read()` parses every row through the Pydantic row model. `append()` writes
only rows whose `dedup_key` is not already present — in the file or earlier
in the same batch — so re-importing a statement never duplicates rows.
"""

import csv
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

RowT = TypeVar("RowT", bound=BaseModel)


class AppendReport(BaseModel):
    added: int
    skipped: int


class LedgerTable(Generic[RowT]):
    def __init__(self, path: Path, row_model: type[RowT]) -> None:
        self.path = path
        self.row_model = row_model

    def read(self) -> list[RowT]:
        if not self.path.exists():
            return []
        with self.path.open(newline="") as f:
            # csv gives "" for blank cells; treat blank as missing so Pydantic
            # applies field defaults / None instead of seeing an empty string.
            return [
                self.row_model.model_validate(
                    {k: (v if v != "" else None) for k, v in raw.items()}
                )
                for raw in csv.DictReader(f)
            ]

    def append(self, rows: list[RowT]) -> AppendReport:
        seen = {r.dedup_key for r in self.read()}
        fresh: list[RowT] = []
        for row in rows:
            if row.dedup_key in seen:
                continue
            seen.add(row.dedup_key)
            fresh.append(row)

        write_header = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(self.row_model.model_fields)
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            for row in fresh:
                writer.writerow(row.model_dump(mode="json"))

        return AppendReport(added=len(fresh), skipped=len(rows) - len(fresh))
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `29 passed`(24 + 5 新),ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/services/ledger/table.py tests/test_ledger_table.py
git commit -m "Add LedgerTable: CSV read and dedup-append"
```

---

### Task 4: AccountLedger —— 账户目录 + account.toml

把一个账户目录(`data/accounts/<broker_account_id>/`)下的 4 张 `LedgerTable` 与 `account.toml` 组合起来。

**Files:** Create `backend/app/services/ledger/account_ledger.py`; Test `backend/tests/test_account_ledger.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_account_ledger.py`:

```python
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount


def test_create_writes_account_toml_and_dir(tmp_path):
    acct = LedgerAccount(
        broker_account_id="U1234567", name="Main", base_currency="USD"
    )
    ledger = AccountLedger.create(tmp_path, acct)

    assert ledger.root == tmp_path / "U1234567"
    assert (ledger.root / "account.toml").exists()


def test_create_then_read_account_round_trips(tmp_path):
    acct = LedgerAccount(
        broker_account_id="U1234567",
        name="Roth IRA",
        base_currency="USD",
        broker="IBKR",
    )
    AccountLedger.create(tmp_path, acct)

    reloaded = AccountLedger(tmp_path / "U1234567").read_account()
    assert reloaded == acct


def test_exposes_four_named_tables(tmp_path):
    ledger = AccountLedger(tmp_path / "U1")
    assert ledger.instruments.path == tmp_path / "U1" / "instruments.csv"
    assert ledger.trades.path == tmp_path / "U1" / "trades.csv"
    assert ledger.cash_flows.path == tmp_path / "U1" / "cash_flows.csv"
    assert (
        ledger.corporate_actions.path
        == tmp_path / "U1" / "corporate_actions.csv"
    )
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_account_ledger.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.ledger.account_ledger'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/ledger/account_ledger.py`:

```python
"""One account's CSV ledger directory: 4 record tables + account.toml.

account.toml holds four flat string keys, so it is written by hand (the
standard library has a TOML reader but no writer) and read with tomllib.
"""

import tomllib
from pathlib import Path

from app.services.ledger.rows import (
    LedgerAccount,
    LedgerCashFlow,
    LedgerCorporateAction,
    LedgerInstrument,
    LedgerTrade,
)
from app.services.ledger.table import LedgerTable


class AccountLedger:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.instruments: LedgerTable[LedgerInstrument] = LedgerTable(
            root / "instruments.csv", LedgerInstrument
        )
        self.trades: LedgerTable[LedgerTrade] = LedgerTable(
            root / "trades.csv", LedgerTrade
        )
        self.cash_flows: LedgerTable[LedgerCashFlow] = LedgerTable(
            root / "cash_flows.csv", LedgerCashFlow
        )
        self.corporate_actions: LedgerTable[LedgerCorporateAction] = LedgerTable(
            root / "corporate_actions.csv", LedgerCorporateAction
        )

    @classmethod
    def create(cls, accounts_dir: Path, account: LedgerAccount) -> "AccountLedger":
        root = accounts_dir / account.broker_account_id
        root.mkdir(parents=True, exist_ok=True)
        lines = [
            f'broker_account_id = "{account.broker_account_id}"',
            f'name = "{account.name}"',
            f'base_currency = "{account.base_currency}"',
            f'broker = "{account.broker}"',
        ]
        (root / "account.toml").write_text("\n".join(lines) + "\n")
        return cls(root)

    def read_account(self) -> LedgerAccount:
        with (self.root / "account.toml").open("rb") as f:
            return LedgerAccount.model_validate(tomllib.load(f))
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `32 passed`(29 + 3 新),ruff 通过

- [ ] **Step 5: 提交**

```bash
git add app/services/ledger/account_ledger.py tests/test_account_ledger.py
git commit -m "Add AccountLedger: per-account ledger directory"
```

---

### Task 5: 子系统整体集成测试

一个贯穿整个子系统的测试:建账户 → 追加 trades/cash_flows → 重复追加被去重 → 读回数据完整。

**Files:** Test `backend/tests/test_account_ledger.py`(在 Task 4 文件末尾追加)

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_account_ledger.py` 末尾追加(顶部 import 区补上需要的名字):

```python
from datetime import datetime
from decimal import Decimal

from app.db.enums import CashFlowType, TradeSide
from app.services.ledger.rows import LedgerCashFlow, LedgerTrade


def test_full_ledger_workflow(tmp_path):
    acct = LedgerAccount(
        broker_account_id="U777", name="Main", base_currency="USD"
    )
    ledger = AccountLedger.create(tmp_path, acct)

    trade = LedgerTrade(
        trade_id="T1",
        instrument="AAPL",
        side=TradeSide.BUY,
        quantity=Decimal("5"),
        price=Decimal("100"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds_orig=Decimal("-500"),
        proceeds_usd=Decimal("-500"),
        executed_at=datetime(2026, 1, 2, 10, 0),
        import_batch="batch-1",
    )
    deposit = LedgerCashFlow(
        flow_type=CashFlowType.DEPOSIT,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("5000"),
        amount_usd=Decimal("5000"),
        occurred_at=datetime(2026, 1, 1, 0, 0),
        import_batch="batch-1",
    )

    assert ledger.trades.append([trade]).added == 1
    assert ledger.cash_flows.append([deposit]).added == 1

    # Re-importing the same statement adds nothing.
    second = ledger.trades.append([trade])
    assert (second.added, second.skipped) == (0, 1)

    read_trade = ledger.trades.read()[0]
    assert read_trade.trade_id == "T1"
    assert read_trade.import_batch == "batch-1"
    assert read_trade.proceeds_usd == Decimal("-500")
    assert ledger.cash_flows.read()[0].amount_usd == Decimal("5000")
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_account_ledger.py::test_full_ledger_workflow -v` — Expected: 测试本身存在但若有 import 错误先修正;预期最终是一个真实断言驱动的 PASS。先确认它运行(此任务无新生产代码,测试应直接 PASS,因为它只组合已实现的部件)。

  说明:此任务不写新生产代码 —— 它验证 Task 1–4 的部件协同工作。若该测试未通过,说明前序任务有缺陷,报告 BLOCKED 并指出具体失败。

- [ ] **Step 3: 跑全量验证** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `33 passed`(32 + 1 新),ruff 通过

- [ ] **Step 4: 提交**

```bash
git add tests/test_account_ledger.py
git commit -m "Add CSV ledger subsystem integration test"
```

---

## Self-Review

- **Spec 覆盖(spec 第 3 节)**:目录结构 = `AccountLedger`(Task 4);`account.toml` = Task 4;4 个 CSV + `source`/`import_batch` 居首列 = `LedgerTable` + 行模型(Task 2/3);去重键 = 各行模型 `dedup_key`(Task 2),trades 用 `trade_id`、cash_flows 用 `external_id` 否则内容 hash、instruments 用 symbol+资产类别+期权字段、corporate_actions 用 instrument+类型+除权日 —— 全覆盖;重导入不覆盖手改 = `append` 去重(Task 3/5 验证)。
- **占位符**:无 TBD/TODO;每个代码步骤含完整代码。
- **类型一致性**:`LedgerTrade/LedgerCashFlow/LedgerInstrument/LedgerCorporateAction/LedgerAccount`、`LedgerTable`、`AppendReport`、`dedup_key`、`AccountLedger.create/read_account`、属性 `instruments/trades/cash_flows/corporate_actions/root/path` 在各任务间命名一致。
- 测试计数:18 → 24 → 29 → 32 → 33,与各步 Expected 一致。
- **范围**:本计划只做 M2(账本文件 I/O + 去重)。不含 DB 投影(M3)、FX(M4)、P&L(M5)、IBKR 解析器(M6)。
