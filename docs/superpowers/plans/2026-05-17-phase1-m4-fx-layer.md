# Phase 1 M4 — FX 汇率层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 FX 汇率层 —— 把任意货币某日金额折算成 USD,汇率来源走 adapter 模式(IBKR 日报自带汇率优先,ECB 免费日频汇率兜底),并缓存。

**Architecture:** 新包 `app/services/fx/`。`FxRateProvider` 抽象接口:`get_rate(currency, on_date) -> Decimal | None`(无汇率返回 None,以便链式降级;USD 恒为 1)。`StatementFxProvider` 用内存 dict(M6 解析器会用日报汇率填充)。`EcbFxProvider` 通过 Frankfurter API 取 ECB 日频汇率并缓存进 `data/fx_rates.csv`。`ChainedFxProvider` 按优先级依次尝试。`convert_to_usd` 是折算 helper。

**Tech Stack:** Python 3.12, httpx(已是依赖), 标准库 `csv`/`abc`, pytest(`httpx.MockTransport` mock 网络), uv, ruff。命令从 `backend/` 运行,`uv run --no-sync` 前缀。

**参考:** spec `docs/superpowers/specs/2026-05-17-phase1-data-architecture-pnl-design.md` 第 6 节(货币与汇率)。

## File Structure

- `backend/app/services/fx/__init__.py` — **新建**,包标记。
- `backend/app/services/fx/provider.py` — **新建**。`FxRateProvider` 抽象基类、`StatementFxProvider`、`ChainedFxProvider`、`convert_to_usd`。
- `backend/app/services/fx/cache.py` — **新建**。`FxRateCache` —— `data/fx_rates.csv` 读写。
- `backend/app/services/fx/ecb.py` — **新建**。`EcbFxProvider` —— Frankfurter API + 缓存。
- `backend/tests/test_fx_provider.py`、`test_fx_cache.py`、`test_fx_ecb.py` — **新建**测试。

---

### Task 1: FxRateProvider 接口 + StatementFxProvider

抽象接口与内存 dict 实现。

**Files:** Create `backend/app/services/fx/__init__.py`, `backend/app/services/fx/provider.py`; Test `backend/tests/test_fx_provider.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_fx_provider.py`:

```python
from datetime import date
from decimal import Decimal

from app.services.fx.provider import StatementFxProvider


def test_statement_provider_returns_known_rate():
    provider = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    assert provider.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_statement_provider_usd_is_one():
    provider = StatementFxProvider({})
    assert provider.get_rate("USD", date(2026, 1, 15)) == Decimal("1")


def test_statement_provider_unknown_returns_none():
    provider = StatementFxProvider({})
    assert provider.get_rate("EUR", date(2026, 1, 15)) is None
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_fx_provider.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.fx'`

- [ ] **Step 3: 实现** — 新建空文件 `backend/app/services/fx/__init__.py`,内容为单行 docstring:

```python
"""FX rate layer — convert non-USD amounts to USD via pluggable providers."""
```

新建 `backend/app/services/fx/provider.py`:

```python
"""FX rate providers — convert a non-USD amount to USD.

A FxRateProvider answers: "what rate do I multiply an amount in `currency`
on `on_date` by to get USD?" USD is always 1. A provider returns None when
it has no rate, so providers can be chained by priority.
"""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal


class FxRateProvider(ABC):
    @abstractmethod
    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        """Rate to multiply a `currency` amount by to get USD, or None."""


class StatementFxProvider(FxRateProvider):
    """In-memory provider backed by a fixed {(currency, date): rate} map.

    The IBKR statement parser (a later milestone) seeds this with the FX
    rates the statement itself reports.
    """

    def __init__(self, rates: dict[tuple[str, date], Decimal]) -> None:
        self._rates = rates

    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        if currency == "USD":
            return Decimal("1")
        return self._rates.get((currency, on_date))
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `61 passed`(58 + 3 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/fx/__init__.py app/services/fx/provider.py tests/test_fx_provider.py
git commit -m "Add FxRateProvider interface and StatementFxProvider"
```

(提交信息**不要**加 `Co-Authored-By` trailer。)

---

### Task 2: ChainedFxProvider + convert_to_usd

优先级链与折算 helper。

**Files:** Modify `backend/app/services/fx/provider.py`; Test `backend/tests/test_fx_provider.py`

- [ ] **Step 1: 写失败测试** — 在 `backend/tests/test_fx_provider.py` 末尾追加(顶部 import 区补 `ChainedFxProvider`、`convert_to_usd`、`pytest`):

```python
def test_chained_returns_first_non_none():
    primary = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    fallback = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("9.99")})
    chain = ChainedFxProvider([primary, fallback])

    assert chain.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_chained_falls_through_to_next_provider():
    primary = StatementFxProvider({})  # has nothing
    fallback = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    chain = ChainedFxProvider([primary, fallback])

    assert chain.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_chained_returns_none_when_no_provider_has_rate():
    chain = ChainedFxProvider([StatementFxProvider({}), StatementFxProvider({})])
    assert chain.get_rate("EUR", date(2026, 1, 15)) is None


def test_convert_to_usd_multiplies_by_rate():
    provider = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    usd = convert_to_usd(Decimal("100"), "EUR", date(2026, 1, 15), provider)
    assert usd == Decimal("108.00")


def test_convert_to_usd_raises_when_no_rate():
    provider = StatementFxProvider({})
    with pytest.raises(ValueError, match="EUR"):
        convert_to_usd(Decimal("100"), "EUR", date(2026, 1, 15), provider)
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_fx_provider.py::test_chained_returns_first_non_none -v` — Expected FAIL: `ImportError: cannot import name 'ChainedFxProvider'`

- [ ] **Step 3: 实现** — 在 `backend/app/services/fx/provider.py` 末尾加:

```python
class ChainedFxProvider(FxRateProvider):
    """Tries each provider in order, returning the first non-None rate."""

    def __init__(self, providers: list[FxRateProvider]) -> None:
        self._providers = providers

    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        for provider in self._providers:
            rate = provider.get_rate(currency, on_date)
            if rate is not None:
                return rate
        return None


def convert_to_usd(
    amount: Decimal,
    currency: str,
    on_date: date,
    provider: FxRateProvider,
) -> Decimal:
    """Convert `amount` in `currency` on `on_date` to USD.

    Raises ValueError if the provider has no rate for that currency/date.
    """
    rate = provider.get_rate(currency, on_date)
    if rate is None:
        raise ValueError(f"no FX rate for {currency} on {on_date.isoformat()}")
    return amount * rate
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `66 passed`(61 + 5 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/fx/provider.py tests/test_fx_provider.py
git commit -m "Add ChainedFxProvider and convert_to_usd"
```

---

### Task 3: FxRateCache —— data/fx_rates.csv

获取到的汇率缓存进全局 CSV,避免重复请求。

**Files:** Create `backend/app/services/fx/cache.py`; Test `backend/tests/test_fx_cache.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_fx_cache.py`:

```python
from datetime import date
from decimal import Decimal

from app.services.fx.cache import FxRateCache


def test_get_returns_none_for_missing_file(tmp_path):
    cache = FxRateCache(tmp_path / "fx_rates.csv")
    assert cache.get("EUR", date(2026, 1, 15)) is None


def test_put_then_get_round_trips(tmp_path):
    cache = FxRateCache(tmp_path / "fx_rates.csv")
    cache.put("EUR", date(2026, 1, 15), Decimal("1.08"))

    assert cache.get("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_get_misses_on_different_currency_or_date(tmp_path):
    cache = FxRateCache(tmp_path / "fx_rates.csv")
    cache.put("EUR", date(2026, 1, 15), Decimal("1.08"))

    assert cache.get("GBP", date(2026, 1, 15)) is None
    assert cache.get("EUR", date(2026, 1, 16)) is None


def test_csv_header_columns(tmp_path):
    path = tmp_path / "fx_rates.csv"
    FxRateCache(path).put("EUR", date(2026, 1, 15), Decimal("1.08"))
    header = path.read_text().splitlines()[0]
    assert header == "date,base,quote,rate"
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_fx_cache.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.fx.cache'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/fx/cache.py`:

```python
"""CSV cache of fetched FX rates — data/fx_rates.csv.

Columns: date, base, quote, rate. `quote` is always USD in Phase 1. The
cache only accelerates repeated lookups; it is never a source of truth —
the rate actually applied to a ledger row is recorded on that row.
"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

_FIELDNAMES = ["date", "base", "quote", "rate"]


class FxRateCache:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, currency: str, on_date: date) -> Decimal | None:
        if not self.path.exists():
            return None
        with self.path.open(newline="") as f:
            for row in csv.DictReader(f):
                if row["base"] == currency and row["date"] == on_date.isoformat():
                    return Decimal(row["rate"])
        return None

    def put(self, currency: str, on_date: date, rate: Decimal) -> None:
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerow(
                {
                    "date": on_date.isoformat(),
                    "base": currency,
                    "quote": "USD",
                    "rate": str(rate),
                }
            )
```

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `70 passed`(66 + 4 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/fx/cache.py tests/test_fx_cache.py
git commit -m "Add FxRateCache for data/fx_rates.csv"
```

---

### Task 4: EcbFxProvider —— Frankfurter API

通过 Frankfurter API(封装 ECB,免费、无需 key)按日期取汇率,命中缓存则不发请求。

**Files:** Create `backend/app/services/fx/ecb.py`; Test `backend/tests/test_fx_ecb.py`

- [ ] **Step 1: 写失败测试** — 新建 `backend/tests/test_fx_ecb.py`:

```python
from datetime import date
from decimal import Decimal

import httpx

from app.services.fx.cache import FxRateCache
from app.services.fx.ecb import EcbFxProvider


def _client(handler) -> httpx.Client:
    """An httpx.Client whose requests are served by `handler` (no network)."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ecb_usd_is_one(tmp_path):
    provider = EcbFxProvider(FxRateCache(tmp_path / "fx.csv"), client=_client(lambda r: httpx.Response(500)))
    assert provider.get_rate("USD", date(2026, 1, 15)) == Decimal("1")


def test_ecb_fetches_rate(tmp_path):
    def handler(request):
        return httpx.Response(
            200, json={"base": "EUR", "date": "2026-01-15", "rates": {"USD": 1.08}}
        )

    provider = EcbFxProvider(FxRateCache(tmp_path / "fx.csv"), client=_client(handler))
    assert provider.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_ecb_second_call_uses_cache_no_http(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(
            200, json={"base": "EUR", "date": "2026-01-15", "rates": {"USD": 1.08}}
        )

    provider = EcbFxProvider(FxRateCache(tmp_path / "fx.csv"), client=_client(handler))
    provider.get_rate("EUR", date(2026, 1, 15))
    provider.get_rate("EUR", date(2026, 1, 15))  # second call

    assert len(calls) == 1  # only the first call hit HTTP


def test_ecb_returns_none_when_response_lacks_usd(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"base": "EUR", "date": "2026-01-15", "rates": {}})

    provider = EcbFxProvider(FxRateCache(tmp_path / "fx.csv"), client=_client(handler))
    assert provider.get_rate("EUR", date(2026, 1, 15)) is None
```

- [ ] **Step 2: 跑测试确认失败** — Run: `uv run --no-sync pytest tests/test_fx_ecb.py -v` — Expected FAIL: `ModuleNotFoundError: No module named 'app.services.fx.ecb'`

- [ ] **Step 3: 实现** — 新建 `backend/app/services/fx/ecb.py`:

```python
"""ECB daily FX rates via the Frankfurter API (free, no API key).

Frankfurter (https://api.frankfurter.app) serves ECB reference rates. We
request one day + currency pair, cache the result, and reuse the cache on
subsequent lookups. The httpx client is injectable so tests can mock it.
"""

from datetime import date
from decimal import Decimal

import httpx

from app.services.fx.cache import FxRateCache
from app.services.fx.provider import FxRateProvider

_BASE_URL = "https://api.frankfurter.app"


class EcbFxProvider(FxRateProvider):
    def __init__(
        self, cache: FxRateCache, client: httpx.Client | None = None
    ) -> None:
        self._cache = cache
        self._client = client or httpx.Client()

    def get_rate(self, currency: str, on_date: date) -> Decimal | None:
        if currency == "USD":
            return Decimal("1")
        cached = self._cache.get(currency, on_date)
        if cached is not None:
            return cached
        response = self._client.get(
            f"{_BASE_URL}/{on_date.isoformat()}",
            params={"base": currency, "symbols": "USD"},
        )
        response.raise_for_status()
        rates = response.json().get("rates", {})
        if "USD" not in rates:
            return None
        rate = Decimal(str(rates["USD"]))
        self._cache.put(currency, on_date, rate)
        return rate
```

说明:`httpx.MockTransport(handler)` 让测试不发真实网络请求 —— `handler` 收到 `httpx.Request`、返回 `httpx.Response`。生产环境 `client` 留空则用真实 `httpx.Client`。`Decimal(str(...))` 把 JSON 解析出的 float 安全转成 Decimal。

- [ ] **Step 4: 跑测试确认通过** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `74 passed`(70 + 4 新),ruff `All checks passed!`

- [ ] **Step 5: 提交**

```bash
git add app/services/fx/ecb.py tests/test_fx_ecb.py
git commit -m "Add EcbFxProvider using the Frankfurter API"
```

---

### Task 5: 集成测试 —— 优先级链端到端

验证 `ChainedFxProvider([StatementFxProvider, EcbFxProvider])`:日报汇率优先,缺失时落到 ECB。

**Files:** Test `backend/tests/test_fx_provider.py`(末尾追加)

- [ ] **Step 1: 追加测试** — 在 `backend/tests/test_fx_provider.py` 末尾追加(顶部 import 区补 `httpx`、`FxRateCache`、`EcbFxProvider`):

```python
def _mock_ecb_client(rate: float):
    def handler(request):
        return httpx.Response(
            200, json={"base": "EUR", "date": "2026-01-15", "rates": {"USD": rate}}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_chain_prefers_statement_over_ecb(tmp_path):
    statement = StatementFxProvider({("EUR", date(2026, 1, 15)): Decimal("1.08")})
    ecb = EcbFxProvider(
        FxRateCache(tmp_path / "fx.csv"), client=_mock_ecb_client(9.99)
    )
    chain = ChainedFxProvider([statement, ecb])

    # Statement has the rate, so ECB's 9.99 is never used.
    assert chain.get_rate("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_chain_falls_back_to_ecb_when_statement_lacks_rate(tmp_path):
    statement = StatementFxProvider({})  # no rates
    ecb = EcbFxProvider(
        FxRateCache(tmp_path / "fx.csv"), client=_mock_ecb_client(1.08)
    )
    chain = ChainedFxProvider([statement, ecb])

    usd = convert_to_usd(Decimal("100"), "EUR", date(2026, 1, 15), chain)
    assert usd == Decimal("108.00")
```

- [ ] **Step 2: 跑测试** — Run: `uv run --no-sync pytest tests/test_fx_provider.py -v` — 此任务不写新生产代码,只组合已实现的部件,两个测试应直接 PASS。若未通过,说明前序任务有缺陷,报告 BLOCKED 并指出具体失败。

- [ ] **Step 3: 全量验证** — Run: `uv run --no-sync pytest -q && uv run --no-sync ruff check .` — Expected: `76 passed`(74 + 2 新),ruff `All checks passed!`

- [ ] **Step 4: 提交**

```bash
git add tests/test_fx_provider.py
git commit -m "Add FX chained-provider integration test"
```

---

## Self-Review

- **Spec 覆盖(spec 第 6 节)**:USD 唯一规范货币 —— 所有 provider 对 USD 返回 1;`FxRateProvider` 接口(adapter 模式)= Task 1;`StatementFxProvider`(日报汇率优先)= Task 1;`EcbFxProvider`(Frankfurter 免费兜底)= Task 4;优先级链「statement > ECB」= `ChainedFxProvider`(Task 2)+ 集成测试(Task 5);`data/fx_rates.csv` 缓存 = `FxRateCache`(Task 3);折算 = `convert_to_usd`(Task 2)。
- **占位符**:无 TBD;每步含完整代码或确切命令。
- **类型一致性**:`FxRateProvider.get_rate(currency, on_date) -> Decimal | None`、`StatementFxProvider`、`ChainedFxProvider`、`EcbFxProvider`、`FxRateCache.get/put`、`convert_to_usd` 的签名在各任务与测试间一致。
- 测试计数:58 → 61 → 66 → 70 → 74 → 76,与各步 Expected 一致。
- **范围**:只做 M4(FX 折算能力)。`StatementFxProvider` 的内存 dict 由 M6 解析器填充;M4 不含解析器、不含 P&L 引擎(M5)。汇率层被 M6 在入库时调用,不修改现有代码。
