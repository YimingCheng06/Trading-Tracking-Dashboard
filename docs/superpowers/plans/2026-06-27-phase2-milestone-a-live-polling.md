# Phase 2 · Milestone A — Live Polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** /positions 和 /pnl 页面在浏览器里自动定时(默认 60s)从 Yahoo 拉最新价,持仓表的价/市值/未实现盈亏与 P&L 曲线尾部 + 累计 pct 跟着跳动,Settings 页可调频率与是否包含盘外。

**Architecture:** 后端加一个纯读端点 `GET /accounts/{id}/live-snapshot?mode=A|B`,一次调用同时返回 live positions 与重算的 curve 尾部(共享 Yahoo 单次批量拉取);失败语义 strict(任一 symbol 缺即 503)。前端通用 `useLivePolling` hook 被 /positions 与 /pnl 两个页面独立消费;市场时段判定 + 用户设置全部在浏览器 localStorage,后端不感知。SSR 路径不变(继续读 snapshot 表),hydration 后客户端孤岛接管 live 更新。

**Tech Stack:** Backend = Python 3.12 + FastAPI + SQLAlchemy 2.0 + pytest + uv;Frontend = Next.js 16 App Router + React 19.2 + TypeScript + Tailwind v4(无单元测试框架,前端验证靠浏览器手动冒烟,跟 M9 决策一致);市场数据 = yfinance(免费,~15–20 分钟延迟)。

**前置阅读:** `docs/superpowers/specs/2026-06-27-phase2-milestone-a-live-polling-design.md` —— 包含锁定决策、out-of-scope 清单、接口契约。

**常规执行约定(每个 backend 任务都按此跑):**
- 所有命令在仓库根目录;后端 pytest 走 `cd backend && uv run --no-sync pytest ...`,lint 走 `cd backend && uv run --no-sync ruff check .`
- 前端 lint 走 `cd frontend && npm run lint`,build 走 `cd frontend && npm run build`
- 提交信息**不要**加 `Co-Authored-By: Claude` 行(项目约定)
- 前端必须用 `localhost`(不要 `127.0.0.1`),否则 Next.js 16 dev server 拦截 hydration

---

## Task 1: Backend — `MarketDataProvider.get_latest_closes` 批量方法

**目标:** 给 provider 接口加一个批量"取最新收盘价"方法,Yahoo 用 `yfinance.download(...)` 单次拉多 symbol 实现;现有的 FakeProvider 测试 fixtures 补 stub。

**Files:**
- Modify: `backend/app/services/providers/base.py`
- Modify: `backend/app/services/providers/yahoo.py`
- Modify: `backend/tests/test_market_data_provider.py`
- Modify: `backend/tests/test_snapshot_builder.py:10-25`(`_FakeProvider`)
- Modify: `backend/tests/test_api_accounts.py:75-90`(`_FakeProvider`)

- [ ] **Step 1: 写失败的批量测试**

把以下两个测试**追加**到 `backend/tests/test_market_data_provider.py` 末尾:

```python
def _fake_closes(by_symbol):
    """Build a closes_fn that returns the pre-baked {symbol: Decimal} dict."""
    def closes_fn(symbols):
        return {s: by_symbol[s] for s in symbols if s in by_symbol}
    return closes_fn


def test_yahoo_get_latest_closes_returns_one_per_symbol():
    provider = YahooFinanceProvider(
        closes_fn=_fake_closes(
            {"AAPL": Decimal("190.50"), "TSLA": Decimal("250.00")}
        )
    )
    result = provider.get_latest_closes(["AAPL", "TSLA"])
    assert result == {"AAPL": Decimal("190.50"), "TSLA": Decimal("250.00")}


def test_yahoo_get_latest_closes_skips_missing_symbols():
    provider = YahooFinanceProvider(
        closes_fn=_fake_closes({"AAPL": Decimal("190.50")})
    )
    result = provider.get_latest_closes(["AAPL", "UNKNOWN"])
    assert result == {"AAPL": Decimal("190.50")}
    assert "UNKNOWN" not in result


def test_yahoo_get_latest_closes_empty_list():
    provider = YahooFinanceProvider(closes_fn=_fake_closes({}))
    assert provider.get_latest_closes([]) == {}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run --no-sync pytest tests/test_market_data_provider.py -v
```

预期:三条新测试 ERROR / FAIL —— `YahooFinanceProvider` 不接受 `closes_fn` 参数,且没有 `get_latest_closes` 方法。

- [ ] **Step 3: 接口加抽象方法**

编辑 `backend/app/services/providers/base.py`,在类里加抽象方法(放在 `get_latest_close` 之后):

```python
    @abstractmethod
    def get_latest_closes(self, symbols: list[str]) -> dict[str, Decimal]:
        """Latest close price for each symbol — one batch call.

        Symbols with no available data are simply absent from the result;
        the caller decides whether that is fatal.
        """
```

- [ ] **Step 4: Yahoo 批量实现**

把 `backend/app/services/providers/yahoo.py` **整文件替换为**:

```python
"""Yahoo Finance market data via yfinance (free, no API key, ~15-20 min delay).

The yfinance network calls are isolated in `_yfinance_history` and
`_yfinance_latest_closes` so the rest of the provider is pure and testable;
`YahooFinanceProvider` takes injectable `history_fn` / `closes_fn` so tests
run offline.
"""

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from app.services.providers.base import MarketDataProvider

HistoryFn = Callable[[str, date, date], dict[date, Decimal]]
ClosesFn = Callable[[list[str]], dict[str, Decimal]]


def _yfinance_history(symbol: str, start: date, end: date) -> dict[date, Decimal]:
    """Fetch daily closes from Yahoo via yfinance — the one real network call."""
    import yfinance

    # yfinance treats `end` as exclusive, so add a day to include it.
    frame = yfinance.Ticker(symbol).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=True,
    )
    closes: dict[date, Decimal] = {}
    for timestamp, close in frame["Close"].items():
        closes[timestamp.date()] = Decimal(str(close))
    return closes


def _yfinance_latest_closes(symbols: list[str]) -> dict[str, Decimal]:
    """One batched HTTP call: last 5d of closes per symbol, pick the most recent."""
    if not symbols:
        return {}
    import yfinance

    frame = yfinance.download(
        tickers=" ".join(symbols),
        period="5d",
        auto_adjust=True,
        group_by="ticker",
        progress=False,
        threads=False,
    )
    out: dict[str, Decimal] = {}
    if len(symbols) == 1:
        closes = frame["Close"].dropna()
        if not closes.empty:
            out[symbols[0]] = Decimal(str(closes.iloc[-1]))
    else:
        for s in symbols:
            try:
                closes = frame[s]["Close"].dropna()
            except (KeyError, AttributeError):
                continue
            if not closes.empty:
                out[s] = Decimal(str(closes.iloc[-1]))
    return out


class YahooFinanceProvider(MarketDataProvider):
    def __init__(
        self,
        history_fn: HistoryFn | None = None,
        closes_fn: ClosesFn | None = None,
    ) -> None:
        self._history_fn = history_fn or _yfinance_history
        self._closes_fn = closes_fn or _yfinance_latest_closes

    def get_daily_closes(
        self, symbol: str, start: date, end: date
    ) -> dict[date, Decimal]:
        return self._history_fn(symbol, start, end)

    def get_latest_close(self, symbol: str) -> Decimal | None:
        today = date.today()
        closes = self._history_fn(symbol, today - timedelta(days=7), today)
        return closes[max(closes)] if closes else None

    def get_latest_closes(self, symbols: list[str]) -> dict[str, Decimal]:
        return self._closes_fn(symbols)
```

- [ ] **Step 5: 更新 test_market_data_provider 已有测试**

编辑 `backend/tests/test_market_data_provider.py`,把 `test_market_data_provider_subclass_must_implement_both_methods` 和 `test_market_data_provider_complete_subclass_works` **替换为**(测试名也改,因为现在三方法):

```python
def test_market_data_provider_subclass_must_implement_all_methods():
    class Incomplete(MarketDataProvider):
        def get_daily_closes(self, symbol, start, end):
            return {}

        def get_latest_close(self, symbol):
            return None

    with pytest.raises(TypeError):
        Incomplete()  # get_latest_closes still abstract


def test_market_data_provider_complete_subclass_works():
    class Complete(MarketDataProvider):
        def get_daily_closes(self, symbol, start, end):
            return {date(2026, 1, 2): Decimal("10")}

        def get_latest_close(self, symbol):
            return Decimal("10")

        def get_latest_closes(self, symbols):
            return {s: Decimal("10") for s in symbols}

    provider = Complete()
    assert provider.get_latest_close("X") == Decimal("10")
    assert provider.get_latest_closes(["X", "Y"]) == {
        "X": Decimal("10"),
        "Y": Decimal("10"),
    }
```

- [ ] **Step 6: 给已有的两个 _FakeProvider 补 stub**

在 `backend/tests/test_snapshot_builder.py` 的 `_FakeProvider` 类里(在 `get_latest_close` 之后)追加方法:

```python
    def get_latest_closes(self, symbols):
        return {
            s: self._closes[s][max(self._closes[s])]
            for s in symbols
            if s in self._closes and self._closes[s]
        }
```

同样在 `backend/tests/test_api_accounts.py` 的 `_FakeProvider` 类里(在 `get_latest_close` 之后)追加:

```python
    def get_latest_closes(self, symbols):
        return {s: Decimal("100") for s in symbols}
```

- [ ] **Step 7: 跑全套测试**

```bash
cd backend && uv run --no-sync pytest -v
```

预期:全绿。新增 3 条 + 改名 1 条 + 全部既有 160 条。

- [ ] **Step 8: lint**

```bash
cd backend && uv run --no-sync ruff check .
```

预期:绿。

- [ ] **Step 9: 提交**

```bash
git add backend/app/services/providers/base.py backend/app/services/providers/yahoo.py backend/tests/test_market_data_provider.py backend/tests/test_snapshot_builder.py backend/tests/test_api_accounts.py
git commit -m "Phase2A: add MarketDataProvider.get_latest_closes batch method"
```

---

## Task 2: Backend — 抽取 `compute_cash_at`

**目标:** 把 `build_day_points` 里那段"算到某天的累计现金"抽成可复用的纯函数,放在 `app/services/snapshot/cash.py`;`build_day_points` 改成调用它;新接口可复用。

**Files:**
- Create: `backend/app/services/snapshot/cash.py`
- Modify: `backend/app/services/pnl/equity.py`
- Create: `backend/tests/test_snapshot_cash.py`

- [ ] **Step 1: 写失败的测试**

新建 `backend/tests/test_snapshot_cash.py`:

```python
from datetime import date, datetime
from decimal import Decimal

from app.db.enums import CashFlowType, TradeSide
from app.db.models import CashFlow, Trade
from app.services.pnl.equity import build_day_points
from app.services.snapshot.cash import (
    compute_cash_at,
    compute_cash_at_from_sequences,
)


def _cash_flow(account, flow_type, amount_usd, occurred_at):
    return CashFlow(
        account_id=account.id,
        flow_type=flow_type,
        currency="USD",
        fx_rate_to_usd=Decimal("1"),
        amount=Decimal(str(amount_usd)),
        amount_usd=Decimal(str(amount_usd)),
        occurred_at=occurred_at,
    )


def _buy(account, instrument, qty, proceeds_usd, executed_at, trade_id, commission=0):
    return Trade(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_id=trade_id,
        side=TradeSide.BUY,
        quantity=Decimal(str(qty)),
        price=Decimal("100"),
        currency="USD",
        fx_rate_to_usd=Decimal("1"),
        proceeds=Decimal(str(proceeds_usd)),
        proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal(str(commission)),
        executed_at=executed_at,
    )


def _sell(account, instrument, qty, proceeds_usd, executed_at, trade_id, commission=0):
    return Trade(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_id=trade_id,
        side=TradeSide.SELL,
        quantity=Decimal(str(qty)),
        price=Decimal("100"),
        currency="USD",
        fx_rate_to_usd=Decimal("1"),
        proceeds=Decimal(str(proceeds_usd)),
        proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal(str(commission)),
        executed_at=executed_at,
    )


def test_compute_cash_at_deposit_only(db_session, account):
    db_session.add(
        _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9))
    )
    db_session.commit()
    assert compute_cash_at(db_session, account, date(2026, 1, 5)) == Decimal("5000")


def test_compute_cash_at_excludes_future_flows(db_session, account):
    db_session.add_all(
        [
            _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9)),
            _cash_flow(account, CashFlowType.DEPOSIT, "1000", datetime(2026, 1, 10, 9)),
        ]
    )
    db_session.commit()
    # Jan 5 only sees the first deposit, not the Jan 10 one.
    assert compute_cash_at(db_session, account, date(2026, 1, 5)) == Decimal("5000")


def test_compute_cash_at_buy_decreases_cash(db_session, account, instrument):
    db_session.add(
        _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9))
    )
    db_session.add(
        _buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10),
             "B1", commission=2)
    )
    db_session.commit()
    # 5000 deposit - 1000 buy - 2 commission = 3998
    assert compute_cash_at(db_session, account, date(2026, 1, 5)) == Decimal("3998")


def test_compute_cash_at_sell_increases_cash(db_session, account, instrument):
    db_session.add(
        _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9))
    )
    db_session.add_all(
        [
            _buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1"),
            _sell(account, instrument, 10, "1100",
                  datetime(2026, 1, 5, 10), "S1", commission=1),
        ]
    )
    db_session.commit()
    # 5000 - 1000 + 1100 - 1 = 5099
    assert compute_cash_at(db_session, account, date(2026, 1, 6)) == Decimal("5099")


def test_compute_cash_at_matches_build_day_points(db_session, account, instrument):
    """Parity: build_day_points and compute_cash_at agree on the cash component."""
    from app.db.models import PositionSnapshot

    db_session.add(
        _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9))
    )
    db_session.add(
        _buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1")
    )
    db_session.add(
        PositionSnapshot(
            account_id=account.id,
            instrument_id=instrument.id,
            snapshot_date=date(2026, 1, 5),
            quantity=Decimal("10"),
            avg_cost=Decimal("100"),
            market_price=Decimal("110"),
            market_value=Decimal("1100"),
            market_value_usd=Decimal("1100"),
            unrealized_pnl=Decimal("100"),
            unrealized_pnl_usd=Decimal("100"),
        )
    )
    db_session.commit()
    points = build_day_points(db_session, account)
    last = points[-1]
    # cash = portfolio_value − holdings_value (which equals market_value_usd here)
    cash_from_build = last.portfolio_value - Decimal("1100")
    cash_from_helper = compute_cash_at(db_session, account, last.on_date)
    assert cash_from_build == cash_from_helper
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run --no-sync pytest tests/test_snapshot_cash.py -v
```

预期:全部 ERROR(模块 `app.services.snapshot.cash` 不存在)。

- [ ] **Step 3: 实现 `cash.py`**

新建 `backend/app/services/snapshot/cash.py`:

```python
"""Cumulative cash position helpers — extracted from build_day_points.

`compute_cash_at(session, account, day)` returns the USD cash balance at
end-of-day `day`: all deposits/withdrawals/dividends/fees up to that day,
plus the signed cash impact of every trade settled by that day. Both this
helper and `build_day_points` route through the same sequence-level
implementation so they cannot drift.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import TradeSide
from app.db.models import Account, CashFlow, Trade


def compute_cash_at_from_sequences(
    cash_flows: list[CashFlow], trades: list[Trade], day: date
) -> Decimal:
    """USD cash at end of `day`, given already-loaded cash_flows + trades."""
    cash = Decimal("0")
    for cf in cash_flows:
        if cf.occurred_at.date() <= day:
            cash += cf.amount_usd
    for t in trades:
        if t.executed_at.date() <= day:
            gross = abs(t.proceeds_usd)
            if t.side == TradeSide.BUY:
                cash -= gross + t.commission_usd
            else:
                cash += gross - t.commission_usd
    return cash


def compute_cash_at(session: Session, account: Account, day: date) -> Decimal:
    """USD cash at end of `day` — queries the DB for the account's flows."""
    cash_flows = list(
        session.scalars(
            select(CashFlow).where(CashFlow.account_id == account.id)
        ).all()
    )
    trades = list(
        session.scalars(
            select(Trade).where(Trade.account_id == account.id)
        ).all()
    )
    return compute_cash_at_from_sequences(cash_flows, trades, day)
```

- [ ] **Step 4: 把 `build_day_points` 改成调用新 helper**

编辑 `backend/app/services/pnl/equity.py`,在文件顶部 imports 区加:

```python
from app.services.snapshot.cash import compute_cash_at_from_sequences
```

把 `build_day_points` 函数体里的内部 `cash = Decimal("0") ... 那一整段(原文件 66-78 行附近)` **替换为**:

```python
        cash = compute_cash_at_from_sequences(list(cash_flows), list(trades), day)
```

注意函数顶部已经 `cash_flows = session.scalars(...).all()` 与 `trades = session.scalars(...).all()`(原文件 41-46 行附近),它们都是 sequence,直接 `list()` 强制成 list 给 helper 用。删除原来内部的 `cash = ... cash += ...` 整块循环。

完整修改后,equity.py 的 `build_day_points` 应该长这样:

```python
def build_day_points(session: Session, account: Account) -> list[DayPoint]:
    """..."""
    snapshots = session.scalars(
        select(PositionSnapshot).where(PositionSnapshot.account_id == account.id)
    ).all()
    cash_flows = list(
        session.scalars(
            select(CashFlow).where(CashFlow.account_id == account.id)
        ).all()
    )
    trades = list(
        session.scalars(
            select(Trade).where(Trade.account_id == account.id)
        ).all()
    )

    holdings_by_day: dict[date, Decimal] = {}
    for s in snapshots:
        holdings_by_day[s.snapshot_date] = (
            holdings_by_day.get(s.snapshot_date, Decimal("0")) + _holdings_value(s)
        )

    days = set(holdings_by_day)
    for cf in cash_flows:
        if cf.flow_type in (CashFlowType.DEPOSIT, CashFlowType.WITHDRAWAL):
            days.add(cf.occurred_at.date())
    if not days:
        return []

    points: list[DayPoint] = []
    holdings = Decimal("0")
    for day in sorted(days):
        if day in holdings_by_day:
            holdings = holdings_by_day[day]
        cash = compute_cash_at_from_sequences(cash_flows, trades, day)
        net_flow = Decimal("0")
        for cf in cash_flows:
            if cf.occurred_at.date() == day and cf.flow_type in (
                CashFlowType.DEPOSIT,
                CashFlowType.WITHDRAWAL,
            ):
                net_flow += cf.amount_usd
        points.append(
            DayPoint(
                on_date=day,
                portfolio_value=cash + holdings,
                net_flow=net_flow,
            )
        )
    return points
```

注意 `TradeSide` 这个 import 现在可能不再被 equity.py 直接用到 —— 如果是,删 import。检查后再决定。

- [ ] **Step 5: 运行新 + 已有测试确认全绿**

```bash
cd backend && uv run --no-sync pytest tests/test_snapshot_cash.py tests/test_pnl_equity.py -v
```

预期:新文件 5 条 + 已有 equity 测试全绿(行为应当不变)。

- [ ] **Step 6: 跑全套**

```bash
cd backend && uv run --no-sync pytest -v
```

预期:全绿。

- [ ] **Step 7: lint**

```bash
cd backend && uv run --no-sync ruff check .
```

- [ ] **Step 8: 提交**

```bash
git add backend/app/services/snapshot/cash.py backend/app/services/pnl/equity.py backend/tests/test_snapshot_cash.py
git commit -m "Phase2A: extract compute_cash_at helper from build_day_points"
```

---

## Task 3: Backend — `compute_live_snapshot`

**目标:** 用 Task 1 的批量 provider + Task 2 的现金 helper,组装 `compute_live_snapshot(session, account, provider, mode)` —— 拉一次 Yahoo + 套 live marks + 重算曲线尾部,strict 失败抛自定义异常。

**Files:**
- Create: `backend/app/services/snapshot/live.py`
- Create: `backend/tests/test_snapshot_live.py`

- [ ] **Step 1: 写失败的测试**

新建 `backend/tests/test_snapshot_live.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.db.enums import AssetClass, CashFlowType, TradeSide
from app.db.models import CashFlow, Instrument, Trade
from app.services.providers.base import MarketDataProvider
from app.services.snapshot.live import (
    LiveDataUnavailable,
    compute_live_snapshot,
)


class _FakeProvider(MarketDataProvider):
    """Provider with pre-baked latest closes; raises if asked for history."""

    def __init__(self, closes: dict[str, Decimal], raise_on_call: bool = False):
        self._closes = closes
        self._raise = raise_on_call

    def get_daily_closes(self, symbol, start, end):
        raise NotImplementedError

    def get_latest_close(self, symbol):
        return self._closes.get(symbol)

    def get_latest_closes(self, symbols):
        if self._raise:
            raise RuntimeError("yahoo down")
        return {s: self._closes[s] for s in symbols if s in self._closes}


def _buy(account, instrument, qty, proceeds_usd, executed_at, trade_id):
    return Trade(
        account_id=account.id, instrument_id=instrument.id, trade_id=trade_id,
        side=TradeSide.BUY, quantity=Decimal(str(qty)), price=Decimal("100"),
        currency="USD", fx_rate_to_usd=Decimal("1"),
        proceeds=Decimal(str(proceeds_usd)), proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal("0"), executed_at=executed_at,
    )


def _deposit(account, amount_usd, occurred_at):
    return CashFlow(
        account_id=account.id, flow_type=CashFlowType.DEPOSIT,
        currency="USD", fx_rate_to_usd=Decimal("1"),
        amount=Decimal(str(amount_usd)), amount_usd=Decimal(str(amount_usd)),
        occurred_at=occurred_at,
    )


def test_compute_live_snapshot_overlays_marks(db_session, account, instrument):
    # Deposit 5000; buy 10 AAPL @ 100 = 1000 cost.
    db_session.add(_deposit(account, "5000", datetime(2026, 1, 1, 9)))
    db_session.add(
        _buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1")
    )
    db_session.commit()
    provider = _FakeProvider({"AAPL": Decimal("120")})

    snap = compute_live_snapshot(db_session, account, provider, "B")

    assert len(snap.positions) == 1
    p = snap.positions[0]
    assert p.symbol == "AAPL"
    assert p.market_price == Decimal("120")
    assert p.market_value == Decimal("1200")  # 10 * 120
    assert p.unrealized_pnl == Decimal("200")  # 1200 - 1000
    # fetched_at is a real UTC datetime
    assert snap.fetched_at.tzinfo == timezone.utc
    # curve_tail date is today
    assert snap.curve_tail.on_date == date.today()


def test_compute_live_snapshot_strict_partial_missing(db_session, account, instrument):
    db_session.add(_deposit(account, "5000", datetime(2026, 1, 1, 9)))
    # Two open STOCK positions; provider only knows one.
    msft = Instrument(symbol="MSFT", asset_class=AssetClass.STOCK, currency="USD")
    db_session.add(msft)
    db_session.flush()
    db_session.add_all(
        [
            _buy(account, instrument, 10, "1000",
                 datetime(2026, 1, 2, 10), "B1"),
            _buy(account, msft, 5, "500", datetime(2026, 1, 2, 11), "B2"),
        ]
    )
    db_session.commit()
    provider = _FakeProvider({"AAPL": Decimal("120")})  # missing MSFT

    with pytest.raises(LiveDataUnavailable) as exc:
        compute_live_snapshot(db_session, account, provider, "B")
    assert exc.value.missing == ["MSFT"]


def test_compute_live_snapshot_provider_exception_propagates(
    db_session, account, instrument
):
    db_session.add(_deposit(account, "5000", datetime(2026, 1, 1, 9)))
    db_session.add(
        _buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1")
    )
    db_session.commit()
    provider = _FakeProvider({}, raise_on_call=True)

    with pytest.raises(RuntimeError):  # caller (endpoint) maps to 503
        compute_live_snapshot(db_session, account, provider, "B")


def test_compute_live_snapshot_options_pass_through(db_session, account, instrument):
    # AAPL stock + one AAPL option. Option has no Yahoo price, must NOT be
    # treated as "missing"; its PositionOut has mark/value/unrealized = None
    # and it does not contribute to live holdings.
    option = Instrument(
        symbol="AAPL  260116C00150000",
        asset_class=AssetClass.OPTION,
        currency="USD",
    )
    db_session.add(option)
    db_session.flush()
    db_session.add(_deposit(account, "5000", datetime(2026, 1, 1, 9)))
    db_session.add_all(
        [
            _buy(account, instrument, 10, "1000",
                 datetime(2026, 1, 2, 10), "B1"),
            _buy(account, option, 2, "600", datetime(2026, 1, 2, 11), "O1"),
        ]
    )
    db_session.commit()
    provider = _FakeProvider({"AAPL": Decimal("120")})  # NO option price

    snap = compute_live_snapshot(db_session, account, provider, "B")

    by_symbol = {p.symbol: p for p in snap.positions}
    assert by_symbol["AAPL"].market_value == Decimal("1200")
    assert by_symbol["AAPL  260116C00150000"].market_price is None
    assert by_symbol["AAPL  260116C00150000"].market_value is None


def test_compute_live_snapshot_mode_a_vs_b_differ(db_session, account, instrument):
    db_session.add(_deposit(account, "1000", datetime(2026, 1, 1, 9)))
    db_session.add(
        _buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1")
    )
    db_session.commit()
    provider = _FakeProvider({"AAPL": Decimal("120")})

    snap_a = compute_live_snapshot(db_session, account, provider, "A")
    snap_b = compute_live_snapshot(db_session, account, provider, "B")

    # Both have the same positions and cumulative_pnl; the pct differs by mode.
    assert snap_a.positions[0].market_value == snap_b.positions[0].market_value
    assert snap_a.curve_tail.cumulative_pnl == snap_b.curve_tail.cumulative_pnl
    assert snap_a.curve_tail.pct != snap_b.curve_tail.pct


def test_compute_live_snapshot_no_positions(db_session, account):
    db_session.add(_deposit(account, "1000", datetime(2026, 1, 1, 9)))
    db_session.commit()
    provider = _FakeProvider({})  # no open positions, no symbols asked

    snap = compute_live_snapshot(db_session, account, provider, "B")
    assert snap.positions == []
    # curve_tail still exists — derived from the cash-only day point series.
    assert snap.curve_tail is not None


def test_compute_live_snapshot_replaces_today_when_present(
    db_session, account, instrument
):
    """If build_day_points already produced a DayPoint for today (because a
    deposit / withdrawal landed today), the live tail replaces it rather
    than appending — otherwise the curve would have two same-day points."""
    today = date.today()
    db_session.add(
        _deposit(account, "1000", datetime(today.year, today.month, today.day, 9))
    )
    db_session.add(
        _buy(account, instrument, 10, "1000",
             datetime(today.year, today.month, today.day, 10), "B1")
    )
    db_session.commit()
    provider = _FakeProvider({"AAPL": Decimal("110")})

    snap = compute_live_snapshot(db_session, account, provider, "B")

    # cash_today = 1000 (deposit) - 1000 (buy) = 0
    # live_holdings = 10 * 110 = 1100
    # portfolio = 1100 ; cumulative_pnl = 1100 - 1000 = 100
    assert snap.curve_tail.on_date == today
    assert snap.curve_tail.cumulative_pnl == Decimal("100")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run --no-sync pytest tests/test_snapshot_live.py -v
```

预期:ImportError(`app.services.snapshot.live` 不存在)。

- [ ] **Step 3: 实现 `live.py`**

新建 `backend/app/services/snapshot/live.py`:

```python
"""Live-snapshot computation — read-only, no DB writes.

`compute_live_snapshot` fetches the latest price for every open priced
position via the provider, overlays those marks onto the position list, and
recomputes the equity-curve tail using the live holdings (instead of the
last-saved snapshot value). Strict failure semantics: any priced symbol
missing from the provider's response raises `LiveDataUnavailable`.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.db.enums import AssetClass
from app.db.models import Account, Instrument
from app.services.pnl.curve import CurvePoint, DayPoint, compute_equity_curve
from app.services.pnl.engine import compute_positions
from app.services.pnl.equity import build_day_points
from app.services.providers.base import MarketDataProvider
from app.services.snapshot.cash import compute_cash_at

_PRICED = (AssetClass.STOCK, AssetClass.ETF)


class LiveDataUnavailable(Exception):
    """Raised when one or more priced symbols have no current price."""

    def __init__(self, missing: list[str]):
        self.missing = list(missing)
        super().__init__(f"missing prices: {self.missing}")


@dataclass(frozen=True)
class LivePosition:
    symbol: str
    quantity: Decimal
    cost_basis: Decimal
    average_cost: Decimal
    market_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None


@dataclass(frozen=True)
class LiveSnapshot:
    fetched_at: datetime
    positions: list[LivePosition]
    curve_tail: CurvePoint


def compute_live_snapshot(
    session: Session,
    account: Account,
    provider: MarketDataProvider,
    mode: Literal["A", "B"],
) -> LiveSnapshot:
    """Build a live-overlay snapshot for the account; never writes the DB."""
    positions = compute_positions(session, account)
    # Look up asset class once — needed to decide which positions get Yahoo'd.
    instruments = {
        iid: session.get(Instrument, iid)
        for iid in {p.instrument_id for p in positions}
    }
    priced_symbols = [
        p.symbol for p in positions if instruments[p.instrument_id].asset_class in _PRICED
    ]
    closes = provider.get_latest_closes(priced_symbols)
    missing = [s for s in priced_symbols if closes.get(s) is None]
    if missing:
        raise LiveDataUnavailable(missing)

    live_positions: list[LivePosition] = []
    live_holdings_usd = Decimal("0")
    for p in positions:
        if instruments[p.instrument_id].asset_class in _PRICED:
            mark = closes[p.symbol]
            market_value = p.quantity * mark
            unrealized = market_value - p.cost_basis
            live_holdings_usd += market_value
            live_positions.append(
                LivePosition(
                    symbol=p.symbol,
                    quantity=p.quantity,
                    cost_basis=p.cost_basis,
                    average_cost=p.average_cost,
                    market_price=mark,
                    market_value=market_value,
                    unrealized_pnl=unrealized,
                )
            )
        else:
            live_positions.append(
                LivePosition(
                    symbol=p.symbol,
                    quantity=p.quantity,
                    cost_basis=p.cost_basis,
                    average_cost=p.average_cost,
                    market_price=None,
                    market_value=None,
                    unrealized_pnl=None,
                )
            )

    today = date.today()
    cash_today = compute_cash_at(session, account, today)
    day_points = build_day_points(session, account)
    live_tail = DayPoint(
        on_date=today,
        portfolio_value=cash_today + live_holdings_usd,
        net_flow=Decimal("0"),
    )
    if day_points and day_points[-1].on_date == today:
        day_points = day_points[:-1] + [live_tail]
    else:
        day_points = day_points + [live_tail]
    curve = compute_equity_curve(day_points, mode)

    return LiveSnapshot(
        fetched_at=datetime.now(timezone.utc),
        positions=live_positions,
        curve_tail=curve[-1],
    )
```

- [ ] **Step 4: 运行测试确认全绿**

```bash
cd backend && uv run --no-sync pytest tests/test_snapshot_live.py -v
```

预期:6 条全绿。

- [ ] **Step 5: 全套 + lint**

```bash
cd backend && uv run --no-sync pytest -v && uv run --no-sync ruff check .
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/snapshot/live.py backend/tests/test_snapshot_live.py
git commit -m "Phase2A: compute_live_snapshot — overlay live marks + recompute curve tail"
```

---

## Task 4: Backend — `/live-snapshot` 端点

**目标:** 把 Task 3 的 `compute_live_snapshot` 包成 FastAPI 端点;Pydantic 响应模型;`LiveDataUnavailable` 映射成 503;其它异常也 503。

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/accounts.py`
- Modify: `backend/tests/test_api_accounts.py`

- [ ] **Step 1: 写失败的端点测试**

把以下测试**追加**到 `backend/tests/test_api_accounts.py` 末尾(`_FakeProvider` 已经在 Task 1 补过 `get_latest_closes` —— 用它就行):

```python
class _MissingProvider(MarketDataProvider):
    """Provider whose batch call returns an empty dict — every symbol missing."""

    def get_daily_closes(self, symbol, start, end):
        return {}

    def get_latest_close(self, symbol):
        return None

    def get_latest_closes(self, symbols):
        return {}


class _RaisingProvider(MarketDataProvider):
    """Provider that blows up on the batch call."""

    def get_daily_closes(self, symbol, start, end):
        return {}

    def get_latest_close(self, symbol):
        return None

    def get_latest_closes(self, symbols):
        raise RuntimeError("yahoo down")


def _with_provider(provider_factory):
    """Helper: override the market-data provider dep for the test's duration."""
    from app.api.deps import get_market_data_provider
    from app.main import app

    app.dependency_overrides[get_market_data_provider] = provider_factory
    return get_market_data_provider


def test_live_snapshot_returns_overlaid_positions(api_client):
    _upload(api_client)
    key = _with_provider(lambda: _FakeProvider())
    try:
        response = api_client.get("/accounts/U0000000/live-snapshot")
    finally:
        from app.main import app
        del app.dependency_overrides[key]

    assert response.status_code == 200
    body = response.json()
    assert "fetched_at" in body
    assert "positions" in body
    assert "curve_tail" in body
    aapl = next(p for p in body["positions"] if p["symbol"] == "AAPL")
    # _FakeProvider returns 100 for every symbol — 6 shares left after sell.
    assert Decimal(str(aapl["market_price"])) == Decimal("100")
    assert Decimal(str(aapl["market_value"])) == Decimal("600")
    assert body["curve_tail"]["on_date"] is not None


def test_live_snapshot_strict_missing_returns_503(api_client):
    _upload(api_client)
    key = _with_provider(lambda: _MissingProvider())
    try:
        response = api_client.get("/accounts/U0000000/live-snapshot")
    finally:
        from app.main import app
        del app.dependency_overrides[key]

    assert response.status_code == 503
    assert "行情不可用" in response.json()["detail"]


def test_live_snapshot_provider_exception_returns_503(api_client):
    _upload(api_client)
    key = _with_provider(lambda: _RaisingProvider())
    try:
        response = api_client.get("/accounts/U0000000/live-snapshot")
    finally:
        from app.main import app
        del app.dependency_overrides[key]

    assert response.status_code == 503
    assert "行情不可用" in response.json()["detail"]


def test_live_snapshot_unknown_account_404(api_client):
    assert api_client.get("/accounts/UNKNOWN/live-snapshot").status_code == 404


def test_live_snapshot_rejects_bad_mode(api_client):
    _upload(api_client)
    assert (
        api_client.get("/accounts/U0000000/live-snapshot?mode=Z").status_code == 422
    )
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run --no-sync pytest tests/test_api_accounts.py -k live_snapshot -v
```

预期:全部 404(未注册路由)或 422,但 status 不对、body 没有期望字段。

- [ ] **Step 3: 加 Pydantic 响应模型**

在 `backend/app/api/schemas.py` 末尾追加:

```python
class CurveTailOut(BaseModel):
    on_date: date
    cumulative_pnl: Decimal
    pct: Decimal | None


class LiveSnapshotOut(BaseModel):
    fetched_at: datetime
    positions: list[PositionOut]
    curve_tail: CurveTailOut
```

(顶部已经 `from datetime import date, datetime`,无新 import。)

- [ ] **Step 4: 加端点**

在 `backend/app/api/accounts.py` 的 imports 区追加(顺序按字母):

```python
from dataclasses import asdict
from fastapi import HTTPException
from app.services.snapshot.live import LiveDataUnavailable, compute_live_snapshot
```

如果 `HTTPException` 已经从 fastapi import 过(本文件目前只有 `APIRouter, Depends` —— 没有),把 fastapi 那行改成:

```python
from fastapi import APIRouter, Depends, HTTPException
```

在文件末尾(`refresh_prices` 之后)追加端点:

```python
@router.get(
    "/accounts/{account_id}/live-snapshot",
    response_model=schemas.LiveSnapshotOut,
)
def get_live_snapshot(
    account: Account = Depends(get_account),
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
    mode: Literal["A", "B"] = "B",
) -> schemas.LiveSnapshotOut:
    """Live overlay of positions + equity-curve tail; pure read, no DB writes."""
    try:
        snap = compute_live_snapshot(db, account, provider, mode)
    except LiveDataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"行情不可用: {', '.join(exc.missing)}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="行情不可用") from exc
    return schemas.LiveSnapshotOut(
        fetched_at=snap.fetched_at,
        positions=[schemas.PositionOut(**asdict(p)) for p in snap.positions],
        curve_tail=schemas.CurveTailOut(
            on_date=snap.curve_tail.on_date,
            cumulative_pnl=snap.curve_tail.cumulative_pnl,
            pct=snap.curve_tail.pct,
        ),
    )
```

- [ ] **Step 5: 运行 live_snapshot 测试确认通过**

```bash
cd backend && uv run --no-sync pytest tests/test_api_accounts.py -k live_snapshot -v
```

预期:5 条全绿。

- [ ] **Step 6: 全套 + lint**

```bash
cd backend && uv run --no-sync pytest -v && uv run --no-sync ruff check .
```

预期:全绿。

- [ ] **Step 7: 提交**

```bash
git add backend/app/api/schemas.py backend/app/api/accounts.py backend/tests/test_api_accounts.py
git commit -m "Phase2A: GET /accounts/{id}/live-snapshot endpoint"
```

---

## Task 5: Frontend — `lib/settings.ts`

**目标:** localStorage 封装,Live Data 设置(频率 + 包含盘外)的读 / 写 / 订阅。

**Files:**
- Create: `frontend/lib/settings.ts`

- [ ] **Step 1: 写文件**

新建 `frontend/lib/settings.ts`:

```typescript
/**
 * Live data 设置 —— 浏览器 localStorage 单一存储。
 * 同一原点的多 tab 通过原生 `storage` 事件自动同步;同 tab 内手动派发
 * `livesettings` CustomEvent 让本 tab 也立刻响应。
 */

export type IntervalSeconds = 30 | 60 | 120 | null;

export type LiveSettings = {
  intervalSeconds: IntervalSeconds; // null = manual
  includeAfterHours: boolean;
};

const KEY = "liveDataSettings";
const EVENT = "livesettings";

const DEFAULTS: LiveSettings = {
  intervalSeconds: 60,
  includeAfterHours: false,
};

const VALID_INTERVALS = new Set<number | null>([30, 60, 120, null]);

function isLiveSettings(v: unknown): v is LiveSettings {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    (o.intervalSeconds === null || VALID_INTERVALS.has(o.intervalSeconds as number)) &&
    typeof o.includeAfterHours === "boolean"
  );
}

export function getLiveSettings(): LiveSettings {
  if (typeof window === "undefined") return { ...DEFAULTS };
  const raw = window.localStorage.getItem(KEY);
  if (!raw) return { ...DEFAULTS };
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (isLiveSettings(parsed)) return parsed;
  } catch {
    /* fall through to defaults — corrupted entry */
  }
  return { ...DEFAULTS };
}

export function setLiveSettings(next: LiveSettings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(next));
  // Same-tab listeners do not get the native `storage` event — dispatch a
  // custom one so polling hooks in the current tab pick up changes too.
  window.dispatchEvent(new CustomEvent(EVENT, { detail: next }));
}

export function subscribeLiveSettings(
  callback: (s: LiveSettings) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) callback(getLiveSettings());
  };
  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent<LiveSettings>).detail;
    callback(detail ?? getLiveSettings());
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(EVENT, onCustom);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(EVENT, onCustom);
  };
}
```

- [ ] **Step 2: lint + build 不碎**

```bash
cd frontend && npm run lint && npm run build
```

预期:绿(模块还没人 import,只是 TS 编译通过)。功能正确性留给 Task 12 的端到端冒烟一起验。

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/settings.ts
git commit -m "Phase2A: frontend Live Data settings store (localStorage)"
```

---

## Task 6: Frontend — `lib/market-hours.ts`

**目标:** 纯函数 `isUsMarketOpen(now: Date)` —— Mon–Fri 09:30–16:00 ET。

**Files:**
- Create: `frontend/lib/market-hours.ts`

- [ ] **Step 1: 写文件**

新建 `frontend/lib/market-hours.ts`:

```typescript
/**
 * 判定给定时刻是否在美股常规交易时段(US/Eastern Mon–Fri 09:30–16:00)。
 *
 * 用 Intl.DateTimeFormat 把 UTC Date 转 ET,避免引入 tz 库。无假日日历 —— US
 * holidays 当作交易日(MVP scope,会拉到 stale 价,徽章不标记)。
 */
export function isUsMarketOpen(now: Date): boolean {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = fmt.formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value ?? "";
  const hourStr = parts.find((p) => p.type === "hour")?.value ?? "00";
  const minStr = parts.find((p) => p.type === "minute")?.value ?? "00";

  if (weekday === "Sat" || weekday === "Sun") return false;

  // Intl returns "24" for midnight in some locales; normalize.
  const hour = Number(hourStr) % 24;
  const minute = Number(minStr);
  const minutes = hour * 60 + minute;
  const OPEN = 9 * 60 + 30; // 09:30 ET
  const CLOSE = 16 * 60;    // 16:00 ET
  return minutes >= OPEN && minutes < CLOSE;
}
```

- [ ] **Step 2: lint + build**

```bash
cd frontend && npm run lint && npm run build
```

功能正确性(Mon 10:00 ET 开盘、周末关闭、Mon 09:29 关闭)留给 Task 12 端到端冒烟一起验。

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/market-hours.ts
git commit -m "Phase2A: frontend US market-hours predicate"
```

---

## Task 7: Frontend — `lib/api.ts` 加 `liveSnapshot` 客户端

**目标:** API 客户端加 typed endpoint `api.liveSnapshot(accountId, mode)`。

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: 加类型 + 函数**

在 `frontend/lib/api.ts` 的 type 区(`export type CurveMode = "A" | "B";` 之前)追加:

```typescript
export type CurveTail = {
  on_date: string;
  cumulative_pnl: Num;
  pct: Num | null;
};

export type LiveSnapshot = {
  fetched_at: string;
  positions: Position[];
  curve_tail: CurveTail;
};
```

在文件末尾的 `api` 常量对象里(`refreshPrices` 之后,`uploadStatement` 之前)追加方法:

```typescript
  liveSnapshot: (id: string, mode: CurveMode = "B") =>
    apiGet<LiveSnapshot>(
      `/accounts/${encodeURIComponent(id)}/live-snapshot?mode=${mode}`,
    ),
```

- [ ] **Step 2: lint + build**

```bash
cd frontend && npm run lint && npm run build
```

预期:绿(没人 import 这个新方法还好;TypeScript 编译通过)。

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/api.ts
git commit -m "Phase2A: api.liveSnapshot client + LiveSnapshot/CurveTail types"
```

---

## Task 8: Frontend — `useLivePolling` 通用 hook

**目标:** 通用轮询 hook,被 /positions 与 /pnl 两页面消费。内部读 settings、判市场时段、document.hidden、setInterval、visibilitychange 切回立即触发、cleanup。

**Files:**
- Create: `frontend/lib/hooks/useLivePolling.ts`

- [ ] **Step 1: 新建文件夹 + 写文件**

新建 `frontend/lib/hooks/useLivePolling.ts`:

```typescript
"use client";

import { useEffect, useRef, useState } from "react";
import { getLiveSettings, subscribeLiveSettings } from "../settings";
import { isUsMarketOpen } from "../market-hours";

export type LivePollStatus =
  | "idle"
  | "polling"
  | "live"
  | "market-closed"
  | "manual"
  | "unavailable";

export type UseLivePollingArgs<T> = {
  /** 单次 fetch —— hook 不管错误类型,抛即视为 unavailable */
  fetcher: () => Promise<T>;
  /** 成功一次 → 把数据交给消费者 */
  onData: (data: T) => void;
};

export type UseLivePollingReturn = {
  status: LivePollStatus;
  /** 上次成功的服务器响应时间(从 fetched_at 取);初始 null */
  lastFetchedAt: Date | null;
  /** 把最近一次成功的时间打到这里(消费者从响应里挑) */
  reportFetchedAt: (when: Date) => void;
};

/**
 * 通用 live 轮询 hook。
 *
 * 调度逻辑:
 *  - settings.intervalSeconds = null  → status="manual",不调度
 *  - market closed & !includeAfterHours → status="market-closed",跳过 tick
 *  - document.hidden → 跳过 tick,但保留前一个 live/closed 状态
 *  - visibilitychange 切回 → 立即触发一次额外 tick
 *  - fetcher 抛 → status="unavailable",消费者已有数据保留
 *  - fetcher 成功 → 调 onData,status="live"
 */
export function useLivePolling<T>({
  fetcher,
  onData,
}: UseLivePollingArgs<T>): UseLivePollingReturn {
  const [status, setStatus] = useState<LivePollStatus>("idle");
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [settings, setSettings] = useState(() => getLiveSettings());
  const fetcherRef = useRef(fetcher);
  const onDataRef = useRef(onData);

  // 永远拿最新的 fetcher/onData 引用,避免每次重渲染重启 interval。
  useEffect(() => {
    fetcherRef.current = fetcher;
    onDataRef.current = onData;
  });

  useEffect(() => {
    const unsub = subscribeLiveSettings(setSettings);
    return unsub;
  }, []);

  useEffect(() => {
    if (settings.intervalSeconds === null) {
      setStatus("manual");
      return;
    }

    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.hidden) return;
      if (
        !settings.includeAfterHours &&
        !isUsMarketOpen(new Date())
      ) {
        setStatus("market-closed");
        return;
      }
      setStatus("polling");
      try {
        const data = await fetcherRef.current();
        if (cancelled) return;
        onDataRef.current(data);
        setStatus("live");
      } catch {
        if (cancelled) return;
        setStatus("unavailable");
      }
    };

    tick(); // immediate first call
    const interval = window.setInterval(tick, settings.intervalSeconds * 1000);

    const onVisibility = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [settings.intervalSeconds, settings.includeAfterHours]);

  return {
    status,
    lastFetchedAt,
    reportFetchedAt: (when: Date) => setLastFetchedAt(when),
  };
}
```

- [ ] **Step 2: lint + build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 3: 提交**

```bash
git add frontend/lib/hooks/useLivePolling.ts
git commit -m "Phase2A: useLivePolling generic hook (interval + visibility + market hours)"
```

---

## Task 9: Frontend — `LiveStatusBadge` 组件

**目标:** 共享小徽章组件,接收 `{ status, lastFetchedAt }`,渲染 dot + 文案。每秒重算 "X 秒前" 字符串。

**Files:**
- Create: `frontend/app/(workspace)/_components/LiveStatusBadge.tsx`

- [ ] **Step 1: 写组件**

新建 `frontend/app/(workspace)/_components/LiveStatusBadge.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import type { LivePollStatus } from "@/lib/hooks/useLivePolling";

type Variant = {
  text: string;
  dotClass: string;
  textClass: string;
};

function variantFor(
  status: LivePollStatus,
  lastFetchedAt: Date | null,
  nowMs: number,
): Variant {
  switch (status) {
    case "live": {
      const ago = lastFetchedAt
        ? Math.max(0, Math.floor((nowMs - lastFetchedAt.getTime()) / 1000))
        : 0;
      return {
        text: `Live · ${ago}s 前`,
        dotClass: "bg-up",
        textClass: "text-muted-strong",
      };
    }
    case "polling":
      return {
        text: "Live · 刷新中…",
        dotClass: "bg-up animate-pulse",
        textClass: "text-muted-strong",
      };
    case "market-closed":
      return {
        text: "Market closed",
        dotClass: "bg-muted",
        textClass: "text-muted",
      };
    case "manual":
      return {
        text: "Manual",
        dotClass: "bg-muted",
        textClass: "text-muted",
      };
    case "unavailable":
      return {
        text: "行情不可用",
        dotClass: "bg-down",
        textClass: "text-down",
      };
    case "idle":
    default:
      return {
        text: "等待中…",
        dotClass: "bg-muted",
        textClass: "text-muted",
      };
  }
}

/**
 * 右上角小徽章:dot + 状态文案。每秒自重渲染让 "X 秒前" 走起来(只在 live 时)。
 */
export function LiveStatusBadge({
  status,
  lastFetchedAt,
}: {
  status: LivePollStatus;
  lastFetchedAt: Date | null;
}) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (status !== "live") return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [status]);

  const v = variantFor(status, lastFetchedAt, nowMs);

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium ${v.textClass}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${v.dotClass}`} />
      {v.text}
    </span>
  );
}
```

- [ ] **Step 2: lint + build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 3: 提交**

```bash
git add 'frontend/app/(workspace)/_components/LiveStatusBadge.tsx'
git commit -m "Phase2A: LiveStatusBadge component"
```

---

## Task 10: Frontend — `LivePositionsTable` + /positions 集成

**目标:** /positions 表格部分换成 client 组件 `LivePositionsTable`,SSR 初值通过 props 传入,客户端 hook 接管 live。RefreshPricesButton 保留。

**Files:**
- Create: `frontend/app/(workspace)/positions/_components/LivePositionsTable.tsx`
- Modify: `frontend/app/(workspace)/positions/page.tsx`

- [ ] **Step 1: 写 client 表格组件**

新建 `frontend/app/(workspace)/positions/_components/LivePositionsTable.tsx`:

```typescript
"use client";

import { useState } from "react";
import { api, type Position } from "@/lib/api";
import { fmtMoney, fmtNum, pnlClass } from "@/lib/format";
import { useLivePolling } from "@/lib/hooks/useLivePolling";
import {
  DataTable,
  type Column,
} from "../../_components/DataTable";
import { LiveStatusBadge } from "../../_components/LiveStatusBadge";

const COLUMNS: Column[] = [
  { key: "symbol", label: "Symbol" },
  { key: "qty", label: "Qty", numeric: true },
  { key: "avg", label: "Avg Cost", numeric: true },
  { key: "cost", label: "Cost Basis", numeric: true },
  { key: "price", label: "Mkt Price", numeric: true },
  { key: "value", label: "Mkt Value", numeric: true },
  { key: "upnl", label: "Unrealized P&L", numeric: true },
];

export function LivePositionsTable({
  initial,
  accountId,
}: {
  initial: Position[];
  accountId: string;
}) {
  const [positions, setPositions] = useState<Position[]>(initial);

  const { status, lastFetchedAt, reportFetchedAt } = useLivePolling({
    fetcher: () => api.liveSnapshot(accountId, "B"),
    onData: (snap) => {
      setPositions(snap.positions);
      reportFetchedAt(new Date(snap.fetched_at));
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <LiveStatusBadge status={status} lastFetchedAt={lastFetchedAt} />
      </div>
      <DataTable
        columns={COLUMNS}
        rows={positions.map((p) => ({
          id: p.symbol,
          cells: [
            <span key="s" className="font-medium text-foreground">
              {p.symbol}
            </span>,
            fmtNum(p.quantity),
            fmtMoney(p.average_cost),
            fmtMoney(p.cost_basis),
            fmtMoney(p.market_price),
            fmtMoney(p.market_value),
            <span key="u" className={pnlClass(p.unrealized_pnl)}>
              {fmtMoney(p.unrealized_pnl)}
            </span>,
          ],
        }))}
      />
    </div>
  );
}
```

- [ ] **Step 2: 把 positions/page.tsx 切到新组件**

编辑 `frontend/app/(workspace)/positions/page.tsx`。imports 区把 `DataTable, type Column` 那行删了,改成 import 新组件:

```typescript
import { LivePositionsTable } from "./_components/LivePositionsTable";
```

把 `COLUMNS` 常量删除(已在 LivePositionsTable 里)。把渲染分支里的 `<DataTable ... />` 替换为:

```tsx
<LivePositionsTable initial={positions} accountId={accountId} />
```

修改后完整 page.tsx 应当类似:

```typescript
import { api, type Account, type Position } from "@/lib/api";
import { IconBriefcase } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { EmptyState } from "../_components/EmptyState";
import { RefreshPricesButton } from "../_components/RefreshPricesButton";
import { LivePositionsTable } from "./_components/LivePositionsTable";

export const dynamic = "force-dynamic";

export default async function PositionsPage({
  searchParams,
}: {
  searchParams: Promise<{ account?: string }>;
}) {
  const { account } = await searchParams;

  let accounts: Account[] = [];
  let offline = false;
  try {
    accounts = await api.accounts();
  } catch {
    offline = true;
  }
  const accountId = account ?? accounts[0]?.broker_account_id;

  let positions: Position[] = [];
  if (accountId && !offline) {
    try {
      positions = await api.positions(accountId);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Portfolio"
      title="Positions"
      subtitle="按 FIFO 重放得到的当前持仓;市值与未实现盈亏来自最近一次行情快照。"
      icon={IconBriefcase}
      action={accountId ? <RefreshPricesButton accountId={accountId} /> : null}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="后端离线"
          hint="无法连接 API。确认 backend 已在 :8000 运行。"
        />
      ) : !accountId ? (
        <EmptyState
          title="还没有账户"
          hint="先到 Upload 页导入一份 IBKR Flex 对账单。"
        />
      ) : positions.length === 0 ? (
        <EmptyState
          title="该账户暂无持仓"
          hint="导入对账单后,持仓会在这里出现。"
        />
      ) : (
        <LivePositionsTable initial={positions} accountId={accountId} />
      )}
    </PageShell>
  );
}
```

- [ ] **Step 3: lint + build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 4: 提交**

```bash
git add 'frontend/app/(workspace)/positions/_components/LivePositionsTable.tsx' 'frontend/app/(workspace)/positions/page.tsx'
git commit -m "Phase2A: /positions live polling via LivePositionsTable"
```

---

## Task 11: Frontend — `LivePnlTail` + /pnl 集成

**目标:** /pnl 的曲线 + 右上角 pct 包成 client 组件 `LivePnlTail`,SSR 初值通过 props 传入,每次 tick 替换/追加曲线最后一点 + 更新 pct。Mode toggle 和上面三张 Metric 卡片保持不变。

**Files:**
- Create: `frontend/app/(workspace)/pnl/_components/LivePnlTail.tsx`
- Modify: `frontend/app/(workspace)/pnl/page.tsx`

- [ ] **Step 1: 写 client 组件**

新建 `frontend/app/(workspace)/pnl/_components/LivePnlTail.tsx`:

```typescript
"use client";

import { useState } from "react";
import { api, type CurveMode, type CurvePoint, type CurveTail } from "@/lib/api";
import { fmtPct, pnlClass } from "@/lib/format";
import { useLivePolling } from "@/lib/hooks/useLivePolling";
import { EquityCurve } from "../../_components/EquityCurve";
import { CurveModeToggle } from "../../_components/CurveModeToggle";
import { LiveStatusBadge } from "../../_components/LiveStatusBadge";

const MODE_CAPTION: Record<CurveMode, string> = {
  A: "口径 Mode A · TWR —— 过去净值点冻结,入金不重算历史。",
  B: "口径 Mode B · 净入金 —— 累计盈亏 ÷ 当前累计净入金,入金重算整条曲线。",
};

function applyTail(curve: CurvePoint[], tail: CurveTail): CurvePoint[] {
  const next: CurvePoint = {
    on_date: tail.on_date,
    cumulative_pnl: tail.cumulative_pnl,
    pct: tail.pct,
  };
  if (curve.length > 0 && curve[curve.length - 1].on_date === tail.on_date) {
    return [...curve.slice(0, -1), next];
  }
  return [...curve, next];
}

export function LivePnlTail({
  initial,
  accountId,
  mode,
}: {
  initial: CurvePoint[];
  accountId: string;
  mode: CurveMode;
}) {
  const [curve, setCurve] = useState<CurvePoint[]>(initial);

  const { status, lastFetchedAt, reportFetchedAt } = useLivePolling({
    fetcher: () => api.liveSnapshot(accountId, mode),
    onData: (snap) => {
      setCurve((prev) => applyTail(prev, snap.curve_tail));
      reportFetchedAt(new Date(snap.fetched_at));
    },
  });

  const last = curve[curve.length - 1];

  return (
    <section>
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
            Equity Curve
          </h2>
          {last && (
            <span
              className={`tabular text-sm font-medium ${pnlClass(last.pct)}`}
            >
              {fmtPct(last.pct)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <LiveStatusBadge status={status} lastFetchedAt={lastFetchedAt} />
          <CurveModeToggle mode={mode} />
        </div>
      </div>
      <p className="mb-3 text-xs text-muted">{MODE_CAPTION[mode]}</p>
      <EquityCurve points={curve} />
    </section>
  );
}
```

- [ ] **Step 2: 改 /pnl/page.tsx**

把 `frontend/app/(workspace)/pnl/page.tsx` 的:
- 顶部 imports 把 `EquityCurve` 和 `CurveModeToggle` 删了
- 加 import `import { LivePnlTail } from "./_components/LivePnlTail";`
- 删 `MODE_CAPTION` 常量(已搬进 LivePnlTail)
- 把 `<section>...Equity Curve...</section>` 整块(原 117-144 行)替换为:

```tsx
{curve.length === 0 ? (
  <EmptyState
    title="暂无曲线数据"
    hint="净值曲线由成交与现金流计算得出 —— 先导入对账单。"
  />
) : (
  <LivePnlTail initial={curve} accountId={accountId} mode={mode} />
)}
```

修改后的完整 pnl/page.tsx:

```typescript
import {
  api,
  type Account,
  type CurveMode,
  type CurvePoint,
  type Pnl,
} from "@/lib/api";
import { fmtMoney, pnlClass } from "@/lib/format";
import { IconTrendingUp } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { EmptyState } from "../_components/EmptyState";
import { LivePnlTail } from "./_components/LivePnlTail";

export const dynamic = "force-dynamic";

function Metric({
  label,
  value,
  sublabel,
  valueClass,
}: {
  label: string;
  value: string;
  sublabel: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-6">
      <p className="text-xs uppercase tracking-[0.18em] text-muted">{label}</p>
      <p
        className={`tabular mt-3 text-3xl font-semibold tracking-tight ${
          valueClass ?? ""
        }`}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-muted">{sublabel}</p>
    </div>
  );
}

export default async function PnlPage({
  searchParams,
}: {
  searchParams: Promise<{ account?: string; mode?: string }>;
}) {
  const sp = await searchParams;
  const mode: CurveMode = sp.mode === "A" ? "A" : "B";

  let accounts: Account[] = [];
  let offline = false;
  try {
    accounts = await api.accounts();
  } catch {
    offline = true;
  }
  const accountId = sp.account ?? accounts[0]?.broker_account_id;

  let pnl: Pnl | null = null;
  let curve: CurvePoint[] = [];
  if (accountId && !offline) {
    try {
      [pnl, curve] = await Promise.all([
        api.pnl(accountId),
        api.curve(accountId, mode),
      ]);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Analysis"
      title="P&L"
      subtitle="已实现盈亏摘要与净值曲线。Mode A = IBKR/TWR;Mode B = 累计盈亏 ÷ 累计净入金。"
      icon={IconTrendingUp}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="后端离线"
          hint="无法连接 API。确认 backend 已在 :8000 运行。"
        />
      ) : !accountId || !pnl ? (
        <EmptyState
          title="还没有账户"
          hint="先到 Upload 页导入一份 IBKR Flex 对账单。"
        />
      ) : (
        <div className="space-y-8">
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Metric
              label="Realized P&L"
              value={fmtMoney(pnl.realized_pnl)}
              sublabel={pnl.base_currency}
              valueClass={pnlClass(pnl.realized_pnl)}
            />
            <Metric
              label="Open Positions"
              value={String(pnl.open_position_count)}
              sublabel="当前持仓数"
            />
            <Metric
              label="Base Currency"
              value={pnl.base_currency}
              sublabel="规范货币"
            />
          </section>

          {curve.length === 0 ? (
            <EmptyState
              title="暂无曲线数据"
              hint="净值曲线由成交与现金流计算得出 —— 先导入对账单。"
            />
          ) : (
            <LivePnlTail initial={curve} accountId={accountId} mode={mode} />
          )}
        </div>
      )}
    </PageShell>
  );
}
```

- [ ] **Step 3: lint + build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 4: 提交**

```bash
git add 'frontend/app/(workspace)/pnl/_components/LivePnlTail.tsx' 'frontend/app/(workspace)/pnl/page.tsx'
git commit -m "Phase2A: /pnl live tail polling via LivePnlTail"
```

---

## Task 12: Frontend — `LiveDataSettings` + /settings/preferences 接通

**目标:** /settings/preferences 页面替换 PlaceholderPage,加 Live Data 区块(radio 频率 + checkbox 包含盘外 + [取消] [保存] 按钮)。保存写 localStorage 并 dispatch 自定义事件。

**Files:**
- Create: `frontend/app/(workspace)/settings/preferences/_components/LiveDataSettings.tsx`
- Modify: `frontend/app/(workspace)/settings/preferences/page.tsx`

- [ ] **Step 1: 写 settings 表单组件**

新建 `frontend/app/(workspace)/settings/preferences/_components/LiveDataSettings.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import {
  getLiveSettings,
  setLiveSettings,
  type IntervalSeconds,
  type LiveSettings,
} from "@/lib/settings";

const INTERVAL_OPTIONS: {
  value: IntervalSeconds;
  label: string;
  hint: string;
}[] = [
  { value: 30, label: "30s", hint: "反馈最活,Yahoo 调用最频" },
  { value: 60, label: "60s", hint: "默认" },
  { value: 120, label: "120s", hint: "省网络" },
  { value: null, label: "Manual", hint: "不自动刷新" },
];

export function LiveDataSettings() {
  const [draft, setDraft] = useState<LiveSettings | null>(null);
  const [saved, setSaved] = useState<LiveSettings | null>(null);
  const [savedNote, setSavedNote] = useState(false);

  useEffect(() => {
    const initial = getLiveSettings();
    setDraft(initial);
    setSaved(initial);
  }, []);

  if (!draft || !saved) return null;

  const dirty =
    draft.intervalSeconds !== saved.intervalSeconds ||
    draft.includeAfterHours !== saved.includeAfterHours;

  function onSave() {
    setLiveSettings(draft!);
    setSaved(draft);
    setSavedNote(true);
    window.setTimeout(() => setSavedNote(false), 2000);
  }

  function onCancel() {
    setDraft(saved!);
  }

  return (
    <section className="rounded-2xl border border-border bg-surface/60 p-6">
      <h2 className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
        Live Data
      </h2>
      <p className="mt-1 text-xs text-muted">
        控制 /positions 与 /pnl 页面的自动刷新行为。
      </p>

      <fieldset className="mt-6">
        <legend className="text-sm font-medium text-foreground">
          Polling frequency
        </legend>
        <div className="mt-3 space-y-2">
          {INTERVAL_OPTIONS.map((opt) => {
            const id = `interval-${opt.value ?? "manual"}`;
            return (
              <label
                key={id}
                htmlFor={id}
                className="flex cursor-pointer items-center gap-3 text-sm text-foreground"
              >
                <input
                  id={id}
                  type="radio"
                  name="intervalSeconds"
                  checked={draft.intervalSeconds === opt.value}
                  onChange={() =>
                    setDraft({ ...draft, intervalSeconds: opt.value })
                  }
                  className="h-4 w-4"
                />
                <span className="font-medium">{opt.label}</span>
                <span className="text-xs text-muted">— {opt.hint}</span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <label className="mt-6 flex cursor-pointer items-start gap-3 text-sm text-foreground">
        <input
          type="checkbox"
          checked={draft.includeAfterHours}
          onChange={(e) =>
            setDraft({ ...draft, includeAfterHours: e.target.checked })
          }
          className="mt-0.5 h-4 w-4"
        />
        <span>
          Include after-hours / pre-market
          <span className="ml-2 text-xs text-muted">
            (默认关闭。打开后,周一至周五全天轮询;周末始终不轮询)
          </span>
        </span>
      </label>

      <div className="mt-6 flex items-center justify-end gap-3">
        {savedNote && (
          <span className="text-xs text-up">已保存</span>
        )}
        <button
          type="button"
          onClick={onCancel}
          disabled={!dirty}
          className="rounded-xl border border-border bg-surface px-4 py-2 text-sm text-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-rail-deep transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          保存
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: 把 /settings/preferences/page.tsx 换掉**

`frontend/app/(workspace)/settings/preferences/page.tsx` **整文件替换为**:

```typescript
import { IconSliders } from "../../_components/icons";
import { PageShell } from "../../_components/PageShell";
import { LiveDataSettings } from "./_components/LiveDataSettings";

export default function SettingsPreferencesPage() {
  return (
    <PageShell
      group="Settings"
      title="Preferences"
      subtitle="实时刷新、显示偏好等用户级设置。"
      icon={IconSliders}
    >
      <LiveDataSettings />
    </PageShell>
  );
}
```

- [ ] **Step 3: lint + build**

```bash
cd frontend && npm run lint && npm run build
```

- [ ] **Step 4: 提交**

```bash
git add 'frontend/app/(workspace)/settings/preferences/_components/LiveDataSettings.tsx' 'frontend/app/(workspace)/settings/preferences/page.tsx'
git commit -m "Phase2A: /settings/preferences page with Live Data settings"
```

---

## Task 13: 浏览器手动冒烟 + 进度文档更新

**目标:** 整体走一遍 9 条冒烟,通过后更新 README 进度段,可选更新 MEMORY 索引。

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 起服务**

```bash
make dev
```

确认 backend :8000 和 frontend :3000 都起来。

- [ ] **Step 2: 准备数据 —— 如果还没账户**

浏览器开 http://localhost:3000/upload(**localhost,不要 127.0.0.1**),上传一份 IBKR Flex CSV(用户私有数据,不在仓库;参考 M6 的 `~/Downloads/Tracking.csv` 真文件),然后到 /positions 点一次"刷新行情"按按钮建初始 snapshot。

- [ ] **Step 3: 冒烟 #1 —— /positions 自动刷新**

打开 http://localhost:3000/positions。徽章应当显示 `Live · 0s 前`(或盘外时 `Market closed`)。等 60 秒,徽章从 `Live · 0s 前` 走到 `Live · 60s 前`,价格列若有变化会更新。

DevTools 网络面板应当能看到约 60s 一次 `GET /accounts/.../live-snapshot?mode=B` 请求。

- [ ] **Step 4: 冒烟 #2 —— 切 tab 后切回立即触发**

打开 /positions 后切到别的 tab 等 1 分钟,切回。**不应该等满 60s** —— 应当立即触发一次 fetch,徽章 dot 短暂 pulse 然后回 `Live · 0s 前`。

- [ ] **Step 5: 冒烟 #3 —— Settings 改 30s 立即生效**

去 http://localhost:3000/settings/preferences,点 `30s` 单选,点"保存"。回 /positions —— 新一轮 polling 应当 30s 一次(网络面板验)。

- [ ] **Step 6: 冒烟 #4 —— Manual 模式**

回 settings,选 `Manual`,保存。回 /positions —— 徽章 `Manual`,网络面板再也不发 live-snapshot 请求。把模式调回 60s。

- [ ] **Step 7: 冒烟 #5 —— 盘外 + 不包含**

把 Mac 系统时钟改成"周末某日中午"或"周二凌晨 3 点 ET"(或者直接等真的盘外)。回 /positions —— 徽章 `Market closed`,网络面板不发请求。

- [ ] **Step 8: 冒烟 #6 —— 打开"包含盘外"**

回 settings 勾选"Include after-hours",保存。回 /positions —— 徽章变回 `Live`,网络面板恢复 60s 一次。**周末**情况下应当**仍然**是 `Market closed`(周六周日始终不轮询)。

- [ ] **Step 9: 冒烟 #7 —— 后端杀掉 → 行情不可用**

`Ctrl+C` 杀掉 backend(只杀 backend,保留 frontend)。回 /positions,等下一次 tick。徽章应当变 `行情不可用`(红),表格保留上次成功的数据(不清空)。重启 backend(`make dev-backend`),徽章下次 tick 恢复 `Live`。

- [ ] **Step 10: 冒烟 #8 —— /pnl 曲线尾部跳动**

打开 http://localhost:3000/pnl。徽章应当显示在右上角(Mode toggle 旁边)。等几次 tick,如果有今天的最新价波动,曲线末尾点 + 右上角 pct 应当更新。Mode A/B 切换后,polling 用新 mode 重启。

- [ ] **Step 11: 冒烟 #9 —— /positions 与 /pnl 双 tab 并发**

开两个 tab,一个 /positions 一个 /pnl。两边都自行轮询,互不干扰(网络面板能看到两个独立的 60s 周期)。

- [ ] **Step 12: 更新 README 进度段**

编辑 `README.md`,在 `#### 🔜 Phase 2 — Realtime data` 之前(以及对应的中文 `#### 🔜 Phase 2 —— 实时数据` 之前)插入新的"已完成"小节:

英文段落 —— 把 `🔜 Phase 2 — Realtime data` 改成 `🚧 Phase 2 — Realtime data (Milestone A done)`,把下面那段说明替换为:

```markdown
- **Milestone A** ✅ — Yahoo polling on `/positions` and `/pnl` (default 60s,
  configurable in `/settings/preferences`); pauses outside US market hours;
  `GET /accounts/{id}/live-snapshot` umbrella endpoint with strict failure
  semantics. Settings stored client-side in `localStorage`.
- **Milestone B** 🔜 — IBKR Client Portal real-time quotes + positions +
  order status (locked fallback chain `IBKRRealtime > IBKRClientPortal >
  IBKRFlexQuery > YahooFinance`).
```

中文段同理:把 `🔜 Phase 2 —— 实时数据` 改成 `🚧 Phase 2 —— 实时数据(Milestone A 已完成)`,下面说明:

```markdown
- **Milestone A** ✅ —— `/positions` 与 `/pnl` 接 Yahoo 自动轮询(默认 60s,
  `/settings/preferences` 可调);盘外暂停;后端 `GET /accounts/{id}/live-snapshot`
  伞形接口,strict 失败语义。Settings 存浏览器 `localStorage`。
- **Milestone B** 🔜 —— IBKR Client Portal 实时行情 + 持仓 + 订单状态
  (锁定回退链 `IBKRRealtime > IBKRClientPortal > IBKRFlexQuery > YahooFinance`)。
```

- [ ] **Step 13: 提交 README**

```bash
git add README.md
git commit -m "docs: Phase 2 Milestone A — live polling shipped"
```

- [ ] **Step 14: 完成 worktree —— 留给用户合并回 main**

`finishing-a-development-branch` skill 走合并流程。本地 commits 总览:

```bash
git log --oneline main..HEAD
```

预期约 9–10 条 commits(spec + 4 backend + 4 frontend + docs)。用户选 merge 还是 PR。

---

## 已完成状态

- 后端 pytest 全绿(约 165+ tests)
- 后端 ruff 全绿
- 前端 `npm run lint` 全绿
- 前端 `npm run build` 全绿
- 浏览器手动冒烟 9 条全过
- README 进度段反映 Milestone A 完成
- Worktree 分支待合并回 main(独立步骤)
