# Phase 1 M5 — P&L 引擎 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现自研 P&L 引擎 —— FIFO 已实现盈亏、当前持仓(数量 + 成本基),以及净值曲线两种盈亏比口径(Mode A 时间加权 / Mode B 当前累计净入金)的算法。

**Architecture:** `app/services/pnl/` 三个模块。`fifo.py`:`run_fifo(trades)` 对单一标的的成交按 FIFO 撮合,返回已实现盈亏 + 未平仓量/成本。`engine.py`:`compute_realized_pnl` / `compute_positions` 读 DB 投影、按标的分组跑 FIFO。`curve.py`:`compute_equity_curve(points, mode)` 是纯函数,对每日序列算两种口径 —— 每日 `DayPoint` 由后续行情快照(Phase 1.4)喂入,本里程碑只做算法。全部 USD。

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, 标准库 `dataclasses`/`decimal`/`collections.deque`, pytest, uv, ruff。命令从 `backend/` 运行,`uv run --no-sync` 前缀。

**参考:** spec `docs/superpowers/specs/2026-05-17-phase1-data-architecture-pnl-design.md` 第 5 节(P&L 引擎)。依赖 M1 ORM、M3 projection builder。

**范围说明:** 本里程碑做 trades 单独可算的部分(已实现盈亏、持仓数量与成本)+ 曲线两种口径的**算法**(纯函数,合成数据测试)。市值 / 未实现盈亏 / 把曲线接真实每日组合价值,需要每日 `positions_snapshot`(行情快照,Phase 1.4),不在 M5。FIFO 仅做多头(buy 开 / sell 平);做空与多腿期权延后。

## File Structure

- `backend/app/services/pnl/fifo.py` — **新建**。`FifoResult` dataclass + `run_fifo`。
- `backend/app/services/pnl/engine.py` — **新建**。`Position` dataclass + `compute_realized_pnl` + `compute_positions`。
- `backend/app/services/pnl/curve.py` — **新建**。`DayPoint` / `CurvePoint` dataclass + `compute_equity_curve`。
- `backend/tests/test_pnl_fifo.py`、`test_pnl_engine.py`、`test_pnl_curve.py` — **新建**测试。
- `backend/app/services/pnl/__init__.py` — 已存在(空包标记),不动。

---

### Task 1: FIFO 撮合 —— run_fifo

对单一标的的成交按 FIFO 撮合:SELL 吃最老的 BUY 批次,得已实现盈亏;剩余批次即未平仓持仓。

**Files:** Create `backend/app/services/pnl/fifo.py`; Test `backend/tests/test_pnl_fifo.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_pnl_fifo.py`:

```python
from decimal import Decimal

import pytest

from app.db.enums import TradeSide
from app.db.models import Trade
from app.services.pnl.fifo import run_fifo


def _trade(side, quantity, proceeds_usd, commission_usd="0", trade_id="T"):
    """A minimal in-memory Trade — run_fifo reads only these 5 fields."""
    return Trade(
        trade_id=trade_id,
        side=side,
        quantity=Decimal(str(quantity)),
        proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal(str(commission_usd)),
    )


def test_fifo_realized_pnl_simple():
    # Buy 10 (gross 1000), sell 10 (gross 1200) -> realized 200.
    result = run_fifo(
        [_trade(TradeSide.BUY, 10, "-1000"), _trade(TradeSide.SELL, 10, "1200")]
    )
    assert result.realized_pnl == Decimal("200")
    assert result.open_quantity == Decimal("0")
    assert result.open_cost_basis == Decimal("0")


def test_fifo_realized_pnl_includes_commission():
    # cost/unit = (1000+5)/10 = 100.5 ; proceeds/unit = (1200-5)/10 = 119.5
    # realized = 10 * (119.5 - 100.5) = 190
    result = run_fifo(
        [
            _trade(TradeSide.BUY, 10, "-1000", "5"),
            _trade(TradeSide.SELL, 10, "1200", "5"),
        ]
    )
    assert result.realized_pnl == Decimal("190")


def test_fifo_partial_lot_match_across_two_buys():
    # Buy 10 @100, buy 10 @110, sell 15 @120.
    # 10*(120-100) + 5*(120-110) = 200 + 50 = 250 ; 5 units of lot2 remain.
    result = run_fifo(
        [
            _trade(TradeSide.BUY, 10, "-1000", trade_id="B1"),
            _trade(TradeSide.BUY, 10, "-1100", trade_id="B2"),
            _trade(TradeSide.SELL, 15, "1800", trade_id="S1"),
        ]
    )
    assert result.realized_pnl == Decimal("250")
    assert result.open_quantity == Decimal("5")
    assert result.open_cost_basis == Decimal("550")  # 5 units @110


def test_fifo_open_position_after_partial_sell():
    result = run_fifo(
        [_trade(TradeSide.BUY, 10, "-1000"), _trade(TradeSide.SELL, 4, "480")]
    )
    assert result.realized_pnl == Decimal("80")  # 4 * (120 - 100)
    assert result.open_quantity == Decimal("6")
    assert result.open_cost_basis == Decimal("600")  # 6 units @100


def test_fifo_sell_exceeding_position_raises():
    with pytest.raises(ValueError, match="exceeds open position"):
        run_fifo([_trade(TradeSide.SELL, 5, "600", trade_id="S9")])
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_pnl_fifo.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.pnl.fifo'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/pnl/fifo.py`:

```python
"""FIFO realized-P&L matching for one instrument's trades.

Processes a chronological list of trades, matching each SELL against the
oldest open BUY lots. Returns realized P&L plus the still-open position.
Phase 1 scope: long positions only (buy-to-open, sell-to-close).
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import TradeSide
from app.db.models import Trade


@dataclass(frozen=True)
class FifoResult:
    realized_pnl: Decimal     # USD, summed over all closed lots
    open_quantity: Decimal    # units still held
    open_cost_basis: Decimal  # total USD cost of the open units


def run_fifo(trades: list[Trade]) -> FifoResult:
    """Match SELLs against oldest BUYs (FIFO) for ONE instrument.

    `trades` must all be for a single instrument, sorted oldest-first.
    Raises ValueError if a SELL exceeds the open position — short
    positions are out of Phase 1 scope.
    """
    lots: deque[list[Decimal]] = deque()  # each entry: [remaining_qty, cost_per_unit]
    realized = Decimal("0")
    for t in trades:
        if t.side == TradeSide.BUY:
            cost_per_unit = (abs(t.proceeds_usd) + t.commission_usd) / t.quantity
            lots.append([t.quantity, cost_per_unit])
        else:  # SELL
            proceeds_per_unit = (abs(t.proceeds_usd) - t.commission_usd) / t.quantity
            remaining = t.quantity
            while remaining > 0:
                if not lots:
                    raise ValueError(
                        f"sell {t.trade_id} exceeds open position "
                        f"(short positions are out of Phase 1 scope)"
                    )
                lot = lots[0]
                matched = min(remaining, lot[0])
                realized += matched * (proceeds_per_unit - lot[1])
                remaining -= matched
                lot[0] -= matched
                if lot[0] == 0:
                    lots.popleft()
    open_quantity = sum((lot[0] for lot in lots), Decimal("0"))
    open_cost_basis = sum((lot[0] * lot[1] for lot in lots), Decimal("0"))
    return FifoResult(realized, open_quantity, open_cost_basis)
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `85 passed`(80 + 5 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/pnl/fifo.py tests/test_pnl_fifo.py
git commit -m "Add FIFO realized-P&L matching"
```

(提交信息**不要**加 `Co-Authored-By` trailer。)

---

### Task 2: 引擎 —— compute_realized_pnl + compute_positions

从 DB 投影读 trades,按标的分组跑 FIFO,得整账户已实现盈亏与当前持仓。

**Files:** Create `backend/app/services/pnl/engine.py`; Test `backend/tests/test_pnl_engine.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_pnl_engine.py`:

```python
from datetime import datetime
from decimal import Decimal

from app.db.enums import TradeSide
from app.db.models import Trade
from app.services.pnl.engine import compute_positions, compute_realized_pnl


def _db_trade(account, instrument, side, quantity, proceeds_usd, *, trade_id, executed_at):
    return Trade(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_id=trade_id,
        side=side,
        quantity=Decimal(str(quantity)),
        price=Decimal("100"),
        currency="USD",
        fx_rate_to_usd=Decimal("1"),
        proceeds=Decimal(str(proceeds_usd)),
        proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal("0"),
        executed_at=executed_at,
    )


def test_compute_realized_pnl_sums_across_instruments(db_session, account, instrument):
    db_session.add_all(
        [
            _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1)),
            _db_trade(account, instrument, TradeSide.SELL, 10, "1200",
                      trade_id="S1", executed_at=datetime(2026, 1, 2)),
        ]
    )
    db_session.commit()

    assert compute_realized_pnl(db_session, account) == Decimal("200")


def test_compute_positions_returns_open_holdings(db_session, account, instrument):
    db_session.add_all(
        [
            _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1)),
            _db_trade(account, instrument, TradeSide.SELL, 4, "480",
                      trade_id="S1", executed_at=datetime(2026, 1, 2)),
        ]
    )
    db_session.commit()

    positions = compute_positions(db_session, account)
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == Decimal("6")
    assert positions[0].cost_basis == Decimal("600")
    assert positions[0].average_cost == Decimal("100")


def test_compute_positions_omits_fully_closed(db_session, account, instrument):
    db_session.add_all(
        [
            _db_trade(account, instrument, TradeSide.BUY, 10, "-1000",
                      trade_id="B1", executed_at=datetime(2026, 1, 1)),
            _db_trade(account, instrument, TradeSide.SELL, 10, "1200",
                      trade_id="S1", executed_at=datetime(2026, 1, 2)),
        ]
    )
    db_session.commit()

    assert compute_positions(db_session, account) == []
```

(`account` 与 `instrument` 是 `conftest.py` 已提供的 fixture —— `account` 是一个 `Account`,`instrument` 是 symbol 为 `"AAPL"` 的 `Instrument`。)

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_pnl_engine.py::test_compute_realized_pnl_sums_across_instruments -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.pnl.engine'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/pnl/engine.py`:

```python
"""P&L engine — realized P&L and current positions, computed from trades.

Reads the DB projection (Trade rows), groups by instrument, runs FIFO.
All amounts are USD. Market value, unrealized P&L and the equity curve
need daily market prices (positions_snapshot) and arrive with the market-
data layer; this module covers everything computable from trades alone.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Instrument, Trade
from app.services.pnl.fifo import run_fifo


@dataclass(frozen=True)
class Position:
    instrument_id: int
    symbol: str
    quantity: Decimal      # open units
    cost_basis: Decimal    # total USD cost of the open units
    average_cost: Decimal  # cost_basis / quantity


def _trades_by_instrument(
    session: Session, account_id: int
) -> dict[int, list[Trade]]:
    """All of the account's trades, grouped by instrument, oldest-first."""
    rows = session.scalars(
        select(Trade)
        .where(Trade.account_id == account_id)
        .order_by(Trade.instrument_id, Trade.executed_at, Trade.id)
    ).all()
    grouped: dict[int, list[Trade]] = {}
    for trade in rows:
        grouped.setdefault(trade.instrument_id, []).append(trade)
    return grouped


def compute_realized_pnl(session: Session, account: Account) -> Decimal:
    """Total realized P&L (USD) across all of the account's instruments."""
    total = Decimal("0")
    for trades in _trades_by_instrument(session, account.id).values():
        total += run_fifo(trades).realized_pnl
    return total


def compute_positions(session: Session, account: Account) -> list[Position]:
    """Current open positions (quantity + cost basis) per instrument.

    Instruments fully closed out are omitted. Market value and unrealized
    P&L require market prices and are out of this milestone.
    """
    positions: list[Position] = []
    for instrument_id, trades in _trades_by_instrument(session, account.id).items():
        result = run_fifo(trades)
        if result.open_quantity == 0:
            continue
        instrument = session.get(Instrument, instrument_id)
        positions.append(
            Position(
                instrument_id=instrument_id,
                symbol=instrument.symbol,
                quantity=result.open_quantity,
                cost_basis=result.open_cost_basis,
                average_cost=result.open_cost_basis / result.open_quantity,
            )
        )
    return positions
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `88 passed`(85 + 3 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/pnl/engine.py tests/test_pnl_engine.py
git commit -m "Add P&L engine: compute_realized_pnl and compute_positions"
```

---

### Task 3: 净值曲线 Mode A —— 时间加权

`compute_equity_curve` 骨架 + `DayPoint`/`CurvePoint` + Mode A(TWR)。

**Files:** Create `backend/app/services/pnl/curve.py`; Test `backend/tests/test_pnl_curve.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_pnl_curve.py`:

```python
from datetime import date
from decimal import Decimal

from app.services.pnl.curve import DayPoint, compute_equity_curve


def test_mode_a_first_day_return_is_zero():
    points = [DayPoint(date(2026, 1, 1), Decimal("1000"), Decimal("1000"))]
    curve = compute_equity_curve(points, "A")
    assert curve[0].pct == Decimal("0")
    assert curve[0].cumulative_pnl == Decimal("0")


def test_mode_a_worked_example():
    # Spec worked example. Deposit 1000; drop to 900; deposit 9000 (V 9900);
    # drop to 9801. TWR: -10%, -10% (deposit doesn't move it), -10.9%.
    points = [
        DayPoint(date(2026, 1, 1), Decimal("1000"), Decimal("1000")),
        DayPoint(date(2026, 1, 5), Decimal("900"), Decimal("0")),
        DayPoint(date(2026, 1, 6), Decimal("9900"), Decimal("9000")),
        DayPoint(date(2026, 1, 10), Decimal("9801"), Decimal("0")),
    ]
    curve = compute_equity_curve(points, "A")

    assert curve[1].pct == Decimal("-0.1")
    assert curve[2].pct == Decimal("-0.1")  # the 9000 deposit does not distort
    assert curve[3].pct == Decimal("-0.109")


def test_unknown_mode_raises():
    import pytest

    with pytest.raises(ValueError, match="mode"):
        compute_equity_curve([], "Z")
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_pnl_curve.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.pnl.curve'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/pnl/curve.py`:

```python
"""Equity-curve math — two P&L-percentage modes.

Pure functions over a daily series. The daily portfolio values come from
positions_snapshot (the market-data layer); this module only does the math.

- Mode A (IBKR / time-weighted return): deposits do not distort past
  percentages; daily returns are chained.
- Mode B (capital-adjusted): every day's percentage is cumulative P&L
  divided by the *current* total net deposits, so the whole curve
  rescales when money is added.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class DayPoint:
    on_date: date
    portfolio_value: Decimal  # total account value at end of day, USD
    net_flow: Decimal         # external deposits minus withdrawals that day


@dataclass(frozen=True)
class CurvePoint:
    on_date: date
    cumulative_pnl: Decimal   # portfolio_value - cumulative net deposits
    pct: Decimal | None       # percentage for the chosen mode; None if undefined


def _cumulative(points: list[DayPoint]) -> list[tuple[Decimal, Decimal]]:
    """Per point: (cumulative net deposits, cumulative P&L)."""
    cum_deposits = Decimal("0")
    out: list[tuple[Decimal, Decimal]] = []
    for p in points:
        cum_deposits += p.net_flow
        out.append((cum_deposits, p.portfolio_value - cum_deposits))
    return out


def _mode_a(points: list[DayPoint]) -> list[CurvePoint]:
    """Time-weighted return: chain daily returns, excluding external flows."""
    curve: list[CurvePoint] = []
    cum_factor = Decimal("1")
    prev_value = Decimal("0")
    for p, (_, cum_pnl) in zip(points, _cumulative(points), strict=True):
        if prev_value > 0:
            daily_return = (p.portfolio_value - p.net_flow) / prev_value - 1
        else:
            daily_return = Decimal("0")
        cum_factor *= 1 + daily_return
        curve.append(CurvePoint(p.on_date, cum_pnl, cum_factor - 1))
        prev_value = p.portfolio_value
    return curve


def compute_equity_curve(
    points: list[DayPoint], mode: Literal["A", "B"]
) -> list[CurvePoint]:
    """Build the equity curve for `mode` over a chronological daily series."""
    if mode == "A":
        return _mode_a(points)
    raise ValueError(f"unknown equity-curve mode {mode!r}")
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `91 passed`(88 + 3 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/pnl/curve.py tests/test_pnl_curve.py
git commit -m "Add equity curve Mode A (time-weighted return)"
```

---

### Task 4: 净值曲线 Mode B —— 当前累计净入金

`compute_equity_curve` 加 Mode B:每天 % = 累计盈亏 ÷ 当前(序列末尾)累计净入金。

**Files:** Modify `backend/app/services/pnl/curve.py`; Test `backend/tests/test_pnl_curve.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_pnl_curve.py` 末尾追加:

```python
def test_mode_b_worked_example():
    # Same scenario; Mode B = cumulative P&L / final total net deposits (10000).
    # day5 -100/10000 = -1% ; day6 -100/10000 = -1% ; day10 -199/10000 = -1.99%
    points = [
        DayPoint(date(2026, 1, 1), Decimal("1000"), Decimal("1000")),
        DayPoint(date(2026, 1, 5), Decimal("900"), Decimal("0")),
        DayPoint(date(2026, 1, 6), Decimal("9900"), Decimal("9000")),
        DayPoint(date(2026, 1, 10), Decimal("9801"), Decimal("0")),
    ]
    curve = compute_equity_curve(points, "B")

    assert curve[1].pct == Decimal("-0.01")
    assert curve[2].pct == Decimal("-0.01")
    assert curve[3].pct == Decimal("-0.0199")


def test_mode_b_pct_is_none_when_net_deposits_not_positive():
    # All money withdrawn -> final net deposits 0 -> percentage undefined.
    points = [
        DayPoint(date(2026, 1, 1), Decimal("1000"), Decimal("1000")),
        DayPoint(date(2026, 1, 2), Decimal("0"), Decimal("-1000")),
    ]
    curve = compute_equity_curve(points, "B")
    assert curve[0].pct is None
    assert curve[1].pct is None
    # cumulative P&L is still reported even when the percentage is undefined
    assert curve[1].cumulative_pnl == Decimal("0")
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_pnl_curve.py::test_mode_b_worked_example -v` — Expected FAIL: `ValueError: unknown equity-curve mode 'B'`

- [ ] **Step 3: 实现** — 在 `backend/app/services/pnl/curve.py` 中,在 `_mode_a` 之后加 `_mode_b`:

```python
def _mode_b(points: list[DayPoint]) -> list[CurvePoint]:
    """Capital-adjusted: cumulative P&L over the final total net deposits."""
    cumulative = _cumulative(points)
    final_deposits = cumulative[-1][0] if cumulative else Decimal("0")
    curve: list[CurvePoint] = []
    for p, (_, cum_pnl) in zip(points, cumulative, strict=True):
        pct = cum_pnl / final_deposits if final_deposits > 0 else None
        curve.append(CurvePoint(p.on_date, cum_pnl, pct))
    return curve
```

并把 `compute_equity_curve` 改为也分派 Mode B:

```python
def compute_equity_curve(
    points: list[DayPoint], mode: Literal["A", "B"]
) -> list[CurvePoint]:
    """Build the equity curve for `mode` over a chronological daily series."""
    if mode == "A":
        return _mode_a(points)
    if mode == "B":
        return _mode_b(points)
    raise ValueError(f"unknown equity-curve mode {mode!r}")
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `93 passed`(91 + 2 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/pnl/curve.py tests/test_pnl_curve.py
git commit -m "Add equity curve Mode B (capital-adjusted)"
```

---

### Task 5: 引擎端到端集成测试

验证 P&L 引擎跑在「CSV 账本 → M3 projection builder → DB」之上 —— 真实数据通路。

**Files:** Test `backend/tests/test_pnl_engine.py`(末尾追加)

- [ ] **Step 1: 追加测试** — 在 `backend/tests/test_pnl_engine.py` 末尾追加。顶部 import 区补这几行(`TradeSide` 已导入;按字母序合并,保持 ruff-clean):`from app.db.enums import AssetClass` 加到现有 `from app.db.enums import TradeSide` 行(合并为 `from app.db.enums import AssetClass, TradeSide`);新增 `from app.services.ledger.account_ledger import AccountLedger`、`from app.services.ledger.rows import LedgerAccount, LedgerInstrument, LedgerTrade`、`from app.services.projection.builder import rebuild_account`:

```python
def test_engine_runs_on_projection_built_from_ledger(db_session, tmp_path):
    # Build a CSV ledger, project it into the DB (M3), then run the engine.
    ledger = AccountLedger.create(
        tmp_path,
        LedgerAccount(broker_account_id="U1", name="Main", base_currency="USD"),
    )
    ledger.instruments.append(
        [LedgerInstrument(symbol="AAPL", asset_class=AssetClass.STOCK, currency="USD")]
    )

    def _lt(trade_id, side, qty, proceeds_usd, when):
        return LedgerTrade(
            trade_id=trade_id,
            instrument="AAPL",
            side=side,
            quantity=Decimal(str(qty)),
            price=Decimal("100"),
            currency="USD",
            fx_rate_to_usd=Decimal("1"),
            proceeds_orig=Decimal(str(proceeds_usd)),
            proceeds_usd=Decimal(str(proceeds_usd)),
            executed_at=when,
        )

    ledger.trades.append(
        [
            _lt("B1", TradeSide.BUY, 10, "-1000", datetime(2026, 1, 1, 10)),
            _lt("S1", TradeSide.SELL, 4, "480", datetime(2026, 1, 2, 10)),
        ]
    )

    account = rebuild_account(db_session, ledger)

    assert compute_realized_pnl(db_session, account) == Decimal("80")
    positions = compute_positions(db_session, account)
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("6")
    assert positions[0].average_cost == Decimal("100")
```

说明:此任务不写新生产代码,验证 M3 → M5 数据通路 —— CSV 账本经 `rebuild_account` 投影进 DB,再由引擎读出。

- [ ] **Step 2: 跑测试** — Run: `uv run --no-sync pytest tests/test_pnl_engine.py::test_engine_runs_on_projection_built_from_ledger -v` — 此任务不写新生产代码,只组合 M3 + M5 已实现的部件,应直接 PASS。若未通过,报告 BLOCKED 并指出具体失败。

- [ ] **Step 3: 全量验证** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `94 passed`(93 + 1 新),ruff `All checks passed!`

- [ ] **Step 4: 提交**

```bash
git add tests/test_pnl_engine.py
git commit -m "Add P&L engine end-to-end integration test"
```

---

## Self-Review

- **Spec 覆盖(spec 第 5 节)**:FIFO 成本法 = `run_fifo`(Task 1);已实现盈亏(自研)= `compute_realized_pnl`(Task 2);持仓数量+成本 = `compute_positions`(Task 2);净值曲线 Mode A(TWR)= Task 3;Mode B(当前累计净入金)= Task 4;验算例 = Task 3/4 的 `worked_example` 测试。`realized_pnl_ibkr`(IBKR 报的值)由 M1 schema 保留,前端并排显示属前端范围。未实现盈亏 / 市值 / 曲线接真实数据 = 需 `positions_snapshot`(Phase 1.4),已在计划开头「范围说明」与代码 docstring 写明。
- **占位符**:无 TBD;每步含完整代码或确切命令。
- **类型一致性**:`FifoResult`(realized_pnl/open_quantity/open_cost_basis)、`run_fifo`、`Position`、`compute_realized_pnl`、`compute_positions`、`DayPoint`、`CurvePoint`、`compute_equity_curve` 的签名在各任务与测试间一致。
- 测试计数:80 → 85 → 88 → 91 → 93 → 94,与各步 Expected 一致。
- **范围**:只做 M5(trades 可算的 P&L + 曲线算法)。做空、多腿期权、未实现盈亏、市值、曲线接真实快照 —— 均不在 M5。
