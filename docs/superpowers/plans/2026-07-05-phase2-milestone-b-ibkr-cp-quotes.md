# Phase 2 · Milestone B — IBKR Client Portal 实时报价 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** live-snapshot 数据链升级为 IBKR CP Gateway 真实时报价(含期权 mark 定价),Gateway 不在线自动静默回落 Yahoo,徽章显示数据来源。

**Architecture:** 新增 `IBKRClientPortalClient`(薄 HTTP 层,注入式 transport)+ `IBKRClientPortalProvider`(普通类,链内件)+ `ChainedMarketDataProvider`(实现 `MarketDataProvider`,live 路径聚合入口 `get_live_quotes`,历史方法转发 Yahoo)。`compute_live_snapshot` 改调 `get_live_quotes`,期权按 mark×qty×multiplier 计市值,并顺手修 live 尾点漏计期权成本价值的 bug。前端只加 `source` 透传到徽章。

**Tech Stack:** Python 3.12 / FastAPI / httpx(已在依赖里)/ pytest;Next.js 16 / TypeScript。

**Spec:** `docs/superpowers/specs/2026-07-05-phase2-milestone-b-ibkr-cp-quotes-design.md`(先读一遍)

## Global Constraints

- 后端命令一律 `cd backend && $HOME/.local/bin/uv run --no-sync <cmd>`。
- ruff:line-length 100,规则 `E,F,I,N,UP,B,SIM`;pytest `asyncio_mode="auto"`。
- 所有价格是 USD `Decimal`;后端 Pydantic 把 Decimal 序列化成 JSON 字符串。
- 测试全离线:网络调用永远隔离在注入点后面(httpx 用 `httpx.MockTransport`)。
- 失败语义:股票/ETF strict(缺价 → `LiveDataUnavailable` → 503);期权
  best-effort(缺 mark → 该期权按成本,不报错)。
- `source` 语义:Gateway authenticated → `"ibkr"`(即使个别 symbol 由 Yahoo
  补洞),否则 `"yahoo"`。
- commit 信息**不加** `Co-Authored-By: Claude` trailer。
- 用户可见文案用英文(Phase2A 已全量英文化);代码注释风格与现有文件一致。

---

### Task 1: Settings + `IBKRClientPortalClient`(HTTP 层)

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/providers/ibkr_cp.py`
- Test: `backend/tests/test_ibkr_cp_client.py`

**Interfaces:**
- Consumes: `settings`(现有单例)
- Produces(后续 Task 依赖,签名精确如下):
  - `FIELD_LAST = "31"`、`FIELD_MARK = "7635"`(模块级常量)
  - `parse_price(raw: str | None) -> Decimal | None`
  - `IBKRClientPortalClient(http: httpx.Client | None = None)`
    - `.auth_ok() -> bool`
    - `.ensure_primed() -> None`
    - `.search_stock_conid(symbol: str) -> int | None`
    - `.snapshot(conids: list[int], fields: list[str]) -> dict[int, dict[str, str]]`

- [ ] **Step 1: 在 `config.py` 的 `Settings` 加两个字段**

在 `cors_origins` 行后加:

```python
    ibkr_gateway_url: str = "https://localhost:5000/v1/api"
    ibkr_gateway_timeout_seconds: float = 2.0
```

- [ ] **Step 2: 写失败测试**

创建 `backend/tests/test_ibkr_cp_client.py`:

```python
"""IBKRClientPortalClient tests — all offline via httpx.MockTransport."""

from decimal import Decimal

import httpx
import pytest

from app.services.providers.ibkr_cp import (
    FIELD_LAST,
    FIELD_MARK,
    IBKRClientPortalClient,
    parse_price,
)


def _client(handler) -> IBKRClientPortalClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://gw/v1/api")
    return IBKRClientPortalClient(http=http)


# -- parse_price -----------------------------------------------------------

def test_parse_price_plain():
    assert parse_price("123.45") == Decimal("123.45")


def test_parse_price_strips_status_prefix():
    # IBKR prefixes prices with status letters, e.g. C=prior close, H=halted.
    assert parse_price("C123.45") == Decimal("123.45")
    assert parse_price("H0.55") == Decimal("0.55")


def test_parse_price_negative_and_garbage():
    assert parse_price("-1.25") == Decimal("-1.25")
    assert parse_price("") is None
    assert parse_price(None) is None
    assert parse_price("N/A") is None


# -- auth_ok ---------------------------------------------------------------

def test_auth_ok_true_when_authenticated():
    def handler(request):
        assert request.url.path == "/v1/api/iserver/auth/status"
        return httpx.Response(200, json={"authenticated": True, "connected": True})

    assert _client(handler).auth_ok() is True


def test_auth_ok_false_when_not_authenticated():
    def handler(request):
        return httpx.Response(200, json={"authenticated": False})

    assert _client(handler).auth_ok() is False


def test_auth_ok_false_on_connect_error():
    def handler(request):
        raise httpx.ConnectError("gateway down")

    assert _client(handler).auth_ok() is False


def test_auth_ok_false_on_http_error():
    def handler(request):
        return httpx.Response(500)

    assert _client(handler).auth_ok() is False


# -- ensure_primed ---------------------------------------------------------

def test_ensure_primed_calls_accounts_once():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=[])

    client = _client(handler)
    client.ensure_primed()
    client.ensure_primed()
    assert calls == ["/v1/api/iserver/accounts"]


# -- search_stock_conid ----------------------------------------------------

def test_search_stock_conid_picks_stk_section():
    def handler(request):
        assert request.url.path == "/v1/api/iserver/secdef/search"
        assert request.url.params["symbol"] == "AAPL"
        return httpx.Response(
            200,
            json=[
                {"conid": "1111", "symbol": "AAPL", "sections": [{"secType": "IND"}]},
                {"conid": "265598", "symbol": "AAPL", "sections": [{"secType": "STK"}]},
            ],
        )

    assert _client(handler).search_stock_conid("AAPL") == 265598


def test_search_stock_conid_none_when_no_match():
    def handler(request):
        return httpx.Response(200, json=[])

    assert _client(handler).search_stock_conid("ZZZZ") is None


# -- snapshot --------------------------------------------------------------

def test_snapshot_returns_rows_keyed_by_conid():
    def handler(request):
        if request.url.path == "/v1/api/iserver/accounts":
            return httpx.Response(200, json=[])
        assert request.url.path == "/v1/api/iserver/marketdata/snapshot"
        assert request.url.params["conids"] == "265598,9999777"
        return httpx.Response(
            200,
            json=[
                {"conid": 265598, "31": "195.30"},
                {"conid": 9999777, "31": "4.20", "7635": "4.35"},
            ],
        )

    rows = _client(handler).snapshot([265598, 9999777], [FIELD_LAST, FIELD_MARK])
    assert rows[265598][FIELD_LAST] == "195.30"
    assert rows[9999777][FIELD_MARK] == "4.35"


def test_snapshot_retries_once_when_price_fields_absent():
    """IBKR 已知怪癖:首次 snapshot 常返回不含价格字段的部分响应。"""
    snapshot_calls = []

    def handler(request):
        if request.url.path == "/v1/api/iserver/accounts":
            return httpx.Response(200, json=[])
        snapshot_calls.append(1)
        if len(snapshot_calls) == 1:
            return httpx.Response(200, json=[{"conid": 265598}])  # no price yet
        return httpx.Response(200, json=[{"conid": 265598, "31": "195.30"}])

    rows = _client(handler).snapshot([265598], [FIELD_LAST])
    assert len(snapshot_calls) == 2
    assert rows[265598][FIELD_LAST] == "195.30"


def test_snapshot_empty_conids_no_network():
    def handler(request):
        raise AssertionError("no network call expected")

    assert _client(handler).snapshot([], [FIELD_LAST]) == {}
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_ibkr_cp_client.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.services.providers.ibkr_cp'`

- [ ] **Step 4: 实现 `ibkr_cp.py`(client 部分)**

创建 `backend/app/services/providers/ibkr_cp.py`:

```python
"""IBKR Client Portal Gateway client + live-quote provider.

The Gateway is IBKR's locally-run Java program (https://localhost:5000) that
the user starts and logs into manually (2FA). All network calls live in
`IBKRClientPortalClient`; it takes an injectable `httpx.Client` so tests run
offline. The Gateway serves a self-signed certificate, so the default client
disables TLS verification — localhost-only traffic.
"""

import logging
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# IBKR market-data snapshot field ids.
FIELD_LAST = "31"
FIELD_MARK = "7635"


def parse_price(raw: str | None) -> Decimal | None:
    """Parse an IBKR snapshot price, stripping status-letter prefixes.

    IBKR prefixes prices with letters like C (prior close) or H (halted).
    """
    if raw is None:
        return None
    text = raw.strip()
    while text and not (text[0].isdigit() or text[0] in "-."):
        text = text[1:]
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _default_http_client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.ibkr_gateway_url,
        verify=False,  # Gateway 自签名证书,仅 localhost 流量
        timeout=settings.ibkr_gateway_timeout_seconds,
    )


class IBKRClientPortalClient:
    """Thin HTTP wrapper over the CP Gateway REST API."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or _default_http_client()
        self._primed = False

    def auth_ok(self) -> bool:
        """True iff the Gateway is up and holds an authenticated session."""
        try:
            res = self._http.post("/iserver/auth/status")
            res.raise_for_status()
            return bool(res.json().get("authenticated"))
        except Exception:
            return False

    def ensure_primed(self) -> None:
        """Call /iserver/accounts once per process — required before snapshot."""
        if self._primed:
            return
        self._http.get("/iserver/accounts").raise_for_status()
        self._primed = True

    def search_stock_conid(self, symbol: str) -> int | None:
        res = self._http.get("/iserver/secdef/search", params={"symbol": symbol})
        res.raise_for_status()
        for entry in res.json() or []:
            if entry.get("symbol") != symbol:
                continue
            sections = {s.get("secType") for s in entry.get("sections", [])}
            if entry.get("secType") == "STK" or "STK" in sections:
                try:
                    return int(entry["conid"])
                except (KeyError, TypeError, ValueError):
                    continue
        return None

    def snapshot(
        self, conids: list[int], fields: list[str]
    ) -> dict[int, dict[str, str]]:
        """One quote row per conid; retries once if price fields are absent

        (known Gateway quirk: the first snapshot call after login often
        returns rows without price fields).
        """
        if not conids:
            return {}
        self.ensure_primed()
        rows = self._snapshot_once(conids, fields)
        incomplete = len(rows) < len(conids) or any(
            not any(f in row for f in fields) for row in rows.values()
        )
        if incomplete:
            rows = self._snapshot_once(conids, fields)
        return rows

    def _snapshot_once(
        self, conids: list[int], fields: list[str]
    ) -> dict[int, dict[str, str]]:
        res = self._http.get(
            "/iserver/marketdata/snapshot",
            params={
                "conids": ",".join(str(c) for c in conids),
                "fields": ",".join(fields),
            },
        )
        res.raise_for_status()
        rows: dict[int, dict[str, str]] = {}
        for row in res.json() or []:
            conid = row.get("conid")
            if conid is None:
                continue
            rows[int(conid)] = {k: str(v) for k, v in row.items() if k in fields}
        return rows
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_ibkr_cp_client.py -v`
Expected: 全部 PASS

- [ ] **Step 6: ruff + commit**

```bash
cd backend && $HOME/.local/bin/uv run --no-sync ruff check .
git add backend/app/core/config.py backend/app/services/providers/ibkr_cp.py backend/tests/test_ibkr_cp_client.py
git commit -m "Phase2B: IBKRClientPortalClient — Gateway HTTP layer + settings"
```

---

### Task 2: `IBKRClientPortalProvider`(链内件)

**Files:**
- Modify: `backend/app/services/providers/ibkr_cp.py`(追加)
- Test: `backend/tests/test_ibkr_cp_provider.py`

**Interfaces:**
- Consumes: Task 1 的 `IBKRClientPortalClient`、`parse_price`、`FIELD_LAST`、`FIELD_MARK`
- Produces:
  - `IBKRClientPortalProvider(client: IBKRClientPortalClient | None = None)`
    - `.available() -> bool`
    - `.resolve_equity_conids(equity: dict[str, int | None]) -> dict[str, int]`
    - `.get_equity_closes(symbol_conids: dict[str, int]) -> dict[str, Decimal]`
    - `.get_option_marks(symbol_conids: dict[str, int]) -> dict[str, Decimal]`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_ibkr_cp_provider.py`:

```python
"""IBKRClientPortalProvider tests — fake client, no network."""

from decimal import Decimal

from app.services.providers.ibkr_cp import (
    FIELD_LAST,
    FIELD_MARK,
    IBKRClientPortalProvider,
)


class _FakeClient:
    """Stands in for IBKRClientPortalClient — records calls, returns canned data."""

    def __init__(
        self,
        authenticated: bool = True,
        search_results: dict[str, int | None] | None = None,
        snapshot_rows: dict[int, dict[str, str]] | None = None,
    ):
        self.authenticated = authenticated
        self.search_results = search_results or {}
        self.snapshot_rows = snapshot_rows or {}
        self.search_calls: list[str] = []
        self.snapshot_calls: list[list[int]] = []

    def auth_ok(self) -> bool:
        return self.authenticated

    def search_stock_conid(self, symbol: str) -> int | None:
        self.search_calls.append(symbol)
        return self.search_results.get(symbol)

    def snapshot(self, conids, fields):
        self.snapshot_calls.append(list(conids))
        return {c: self.snapshot_rows[c] for c in conids if c in self.snapshot_rows}


def test_available_reflects_auth():
    assert IBKRClientPortalProvider(_FakeClient(authenticated=True)).available()
    assert not IBKRClientPortalProvider(_FakeClient(authenticated=False)).available()


def test_resolve_uses_db_conid_without_search():
    client = _FakeClient()
    provider = IBKRClientPortalProvider(client)
    resolved = provider.resolve_equity_conids({"AAPL": 265598})
    assert resolved == {"AAPL": 265598}
    assert client.search_calls == []


def test_resolve_falls_back_to_search_and_caches():
    client = _FakeClient(search_results={"MSFT": 272093})
    provider = IBKRClientPortalProvider(client)
    assert provider.resolve_equity_conids({"MSFT": None}) == {"MSFT": 272093}
    assert provider.resolve_equity_conids({"MSFT": None}) == {"MSFT": 272093}
    assert client.search_calls == ["MSFT"]  # 第二次命中缓存


def test_resolve_unresolvable_symbol_absent():
    client = _FakeClient(search_results={})
    provider = IBKRClientPortalProvider(client)
    assert provider.resolve_equity_conids({"ZZZZ": None}) == {}


def test_get_equity_closes_parses_and_skips_missing():
    client = _FakeClient(
        snapshot_rows={265598: {FIELD_LAST: "C195.30"}, 272093: {}}
    )
    provider = IBKRClientPortalProvider(client)
    closes = provider.get_equity_closes({"AAPL": 265598, "MSFT": 272093})
    assert closes == {"AAPL": Decimal("195.30")}


def test_get_option_marks_prefers_mark_falls_back_to_last():
    client = _FakeClient(
        snapshot_rows={
            1001: {FIELD_MARK: "4.35", FIELD_LAST: "4.20"},
            1002: {FIELD_LAST: "1.10"},
            1003: {},
        }
    )
    provider = IBKRClientPortalProvider(client)
    marks = provider.get_option_marks(
        {"OPT_A": 1001, "OPT_B": 1002, "OPT_C": 1003}
    )
    assert marks == {"OPT_A": Decimal("4.35"), "OPT_B": Decimal("1.10")}


def test_get_option_marks_zero_mark_does_not_fall_through():
    # Decimal("0") 是 falsy —— 确保实现用 `is None` 判断而不是 or 链。
    client = _FakeClient(snapshot_rows={1001: {FIELD_MARK: "0", FIELD_LAST: "9.99"}})
    provider = IBKRClientPortalProvider(client)
    assert provider.get_option_marks({"OPT_A": 1001}) == {"OPT_A": Decimal("0")}


def test_empty_inputs_no_snapshot_call():
    client = _FakeClient()
    provider = IBKRClientPortalProvider(client)
    assert provider.get_equity_closes({}) == {}
    assert provider.get_option_marks({}) == {}
    assert client.snapshot_calls == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_ibkr_cp_provider.py -v`
Expected: FAIL —— `ImportError: cannot import name 'IBKRClientPortalProvider'`

- [ ] **Step 3: 在 `ibkr_cp.py` 末尾追加 provider**

```python
class IBKRClientPortalProvider:
    """Live quotes from the CP Gateway.

    Deliberately NOT a MarketDataProvider — it cannot serve history, so it
    only exists as the IBKR leg inside ChainedMarketDataProvider.
    """

    def __init__(self, client: IBKRClientPortalClient | None = None) -> None:
        self._client = client or IBKRClientPortalClient()
        # symbol -> conid search results; conids never change, no expiry.
        self._search_cache: dict[str, int | None] = {}

    def available(self) -> bool:
        return self._client.auth_ok()

    def resolve_equity_conids(
        self, equity: dict[str, int | None]
    ) -> dict[str, int]:
        """DB conids pass through; the rest go through cached secdef search."""
        resolved: dict[str, int] = {}
        for symbol, conid in equity.items():
            if conid is None:
                if symbol not in self._search_cache:
                    self._search_cache[symbol] = self._client.search_stock_conid(
                        symbol
                    )
                conid = self._search_cache[symbol]
            if conid is not None:
                resolved[symbol] = conid
        return resolved

    def get_equity_closes(
        self, symbol_conids: dict[str, int]
    ) -> dict[str, Decimal]:
        if not symbol_conids:
            return {}
        rows = self._client.snapshot(list(symbol_conids.values()), [FIELD_LAST])
        closes: dict[str, Decimal] = {}
        for symbol, conid in symbol_conids.items():
            price = parse_price(rows.get(conid, {}).get(FIELD_LAST))
            if price is not None:
                closes[symbol] = price
        return closes

    def get_option_marks(
        self, symbol_conids: dict[str, int]
    ) -> dict[str, Decimal]:
        if not symbol_conids:
            return {}
        rows = self._client.snapshot(
            list(symbol_conids.values()), [FIELD_MARK, FIELD_LAST]
        )
        marks: dict[str, Decimal] = {}
        for symbol, conid in symbol_conids.items():
            row = rows.get(conid, {})
            price = parse_price(row.get(FIELD_MARK))
            if price is None:
                price = parse_price(row.get(FIELD_LAST))
            if price is not None:
                marks[symbol] = price
        return marks
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_ibkr_cp_provider.py -v`
Expected: 全部 PASS

- [ ] **Step 5: ruff + commit**

```bash
cd backend && $HOME/.local/bin/uv run --no-sync ruff check .
git add backend/app/services/providers/ibkr_cp.py backend/tests/test_ibkr_cp_provider.py
git commit -m "Phase2B: IBKRClientPortalProvider — conid resolution + equity/option quotes"
```

---

### Task 3: `LiveQuotes` + 基类默认实现 + `ChainedMarketDataProvider`

**Files:**
- Modify: `backend/app/services/providers/base.py`
- Create: `backend/app/services/providers/chain.py`
- Test: `backend/tests/test_provider_chain.py`

**Interfaces:**
- Consumes: Task 2 的 `IBKRClientPortalProvider`;现有 `YahooFinanceProvider`
- Produces:
  - `LiveQuotes`(frozen dataclass,`base.py`):`closes: dict[str, Decimal]`、
    `option_marks: dict[str, Decimal]`、`source: Literal["ibkr", "yahoo"]`
  - `MarketDataProvider.get_live_quotes(equity: dict[str, int | None], options: dict[str, int]) -> LiveQuotes`
    ——**具体方法**(非 abstract),默认 `get_latest_closes` + 空 marks + `"yahoo"`
  - `ChainedMarketDataProvider(ibkr, yahoo)`——覆写 `get_live_quotes`,历史方法转发 Yahoo

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_provider_chain.py`:

```python
"""ChainedMarketDataProvider tests — fake IBKR leg + fake Yahoo leg."""

from datetime import date
from decimal import Decimal

from app.services.providers.base import LiveQuotes, MarketDataProvider
from app.services.providers.chain import ChainedMarketDataProvider


class _FakeYahoo(MarketDataProvider):
    def __init__(self, closes: dict[str, Decimal]):
        self._closes = closes
        self.latest_calls: list[list[str]] = []
        self.daily_calls: list[str] = []

    def get_daily_closes(self, symbol, start, end):
        self.daily_calls.append(symbol)
        return {date(2026, 7, 3): Decimal("100")}

    def get_latest_close(self, symbol):
        return self._closes.get(symbol)

    def get_latest_closes(self, symbols):
        self.latest_calls.append(list(symbols))
        return {s: self._closes[s] for s in symbols if s in self._closes}


class _FakeIbkr:
    """Stands in for IBKRClientPortalProvider."""

    def __init__(
        self,
        up: bool = True,
        closes: dict[str, Decimal] | None = None,
        marks: dict[str, Decimal] | None = None,
        explode: bool = False,
    ):
        self._up = up
        self._closes = closes or {}
        self._marks = marks or {}
        self._explode = explode

    def available(self) -> bool:
        return self._up

    def resolve_equity_conids(self, equity):
        if self._explode:
            raise RuntimeError("gateway died mid-flight")
        return {s: c or 1 for s, c in equity.items() if s in self._closes}

    def get_equity_closes(self, symbol_conids):
        return {s: self._closes[s] for s in symbol_conids if s in self._closes}

    def get_option_marks(self, symbol_conids):
        return {s: self._marks[s] for s in symbol_conids if s in self._marks}


def test_offline_goes_to_yahoo():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    chain = ChainedMarketDataProvider(_FakeIbkr(up=False), yahoo)
    q = chain.get_live_quotes({"AAPL": 265598}, {"OPT_A": 1001})
    assert q.source == "yahoo"
    assert q.closes == {"AAPL": Decimal("101")}
    assert q.option_marks == {}


def test_online_all_from_ibkr():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    ibkr = _FakeIbkr(
        closes={"AAPL": Decimal("102.5")}, marks={"OPT_A": Decimal("4.35")}
    )
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598}, {"OPT_A": 1001})
    assert q.source == "ibkr"
    assert q.closes == {"AAPL": Decimal("102.5")}
    assert q.option_marks == {"OPT_A": Decimal("4.35")}
    assert yahoo.latest_calls == []  # Yahoo 没被打扰


def test_online_partial_gap_filled_by_yahoo():
    yahoo = _FakeYahoo({"MSFT": Decimal("300")})
    ibkr = _FakeIbkr(closes={"AAPL": Decimal("102.5")})
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598, "MSFT": None}, {})
    assert q.source == "ibkr"  # Gateway 在线,来源仍标 ibkr
    assert q.closes == {"AAPL": Decimal("102.5"), "MSFT": Decimal("300")}
    assert yahoo.latest_calls == [["MSFT"]]


def test_online_gap_fill_still_missing_symbol_absent():
    # 双方都没有 ZZZZ → 缺席于 closes,由 caller(live.py)触发 503。
    yahoo = _FakeYahoo({})
    ibkr = _FakeIbkr(closes={"AAPL": Decimal("102.5")})
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598, "ZZZZ": None}, {})
    assert "ZZZZ" not in q.closes


def test_ibkr_exception_mid_flight_falls_back_to_yahoo():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    ibkr = _FakeIbkr(explode=True)
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598}, {})
    assert q.source == "yahoo"
    assert q.closes == {"AAPL": Decimal("101")}


def test_history_methods_forward_to_yahoo():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    chain = ChainedMarketDataProvider(_FakeIbkr(), yahoo)
    chain.get_daily_closes("AAPL", date(2026, 7, 1), date(2026, 7, 3))
    assert yahoo.daily_calls == ["AAPL"]
    assert chain.get_latest_close("AAPL") == Decimal("101")
    assert chain.get_latest_closes(["AAPL"]) == {"AAPL": Decimal("101")}


def test_base_default_get_live_quotes_is_yahoo_shaped():
    # 基类默认实现:latest closes + 空 marks + "yahoo" —— 现有 fake 不用改。
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    q = yahoo.get_live_quotes({"AAPL": None}, {"OPT_A": 1001})
    assert isinstance(q, LiveQuotes)
    assert q.source == "yahoo"
    assert q.closes == {"AAPL": Decimal("101")}
    assert q.option_marks == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_provider_chain.py -v`
Expected: FAIL —— `ImportError`(`LiveQuotes` / `chain` 不存在)

- [ ] **Step 3: 改 `base.py`**

文件头 imports 改为:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal
```

在 `MarketDataProvider` 类定义**前**加:

```python
@dataclass(frozen=True)
class LiveQuotes:
    """Aggregate answer for one live-snapshot request."""

    closes: dict[str, Decimal]
    option_marks: dict[str, Decimal] = field(default_factory=dict)
    source: Literal["ibkr", "yahoo"] = "yahoo"
```

在 `MarketDataProvider` 类末尾(`get_latest_closes` 之后)加具体方法:

```python
    def get_live_quotes(
        self, equity: dict[str, int | None], options: dict[str, int]
    ) -> LiveQuotes:
        """Live-path aggregate: equity closes + option marks + source label.

        `equity` maps symbol -> known IBKR conid (or None); `options` maps
        option symbol -> conid. Default implementation: latest closes from
        this provider, no option marks — delayed-data behaviour. The chained
        provider overrides this with the IBKR-first logic.
        """
        return LiveQuotes(closes=self.get_latest_closes(list(equity)))
```

- [ ] **Step 4: 创建 `chain.py`**

创建 `backend/app/services/providers/chain.py`:

```python
"""Chained market-data provider: IBKR CP Gateway first, Yahoo fallback.

Live path only — history always goes straight to Yahoo. The IBKR leg is
consulted per request (`available()` probes the Gateway's auth status); any
exception from the IBKR leg mid-flight falls back to the Yahoo path, so the
live-snapshot endpoint never breaks because the Gateway went away.
"""

import logging
from datetime import date
from decimal import Decimal

from app.services.providers.base import LiveQuotes, MarketDataProvider
from app.services.providers.ibkr_cp import IBKRClientPortalProvider
from app.services.providers.yahoo import YahooFinanceProvider

logger = logging.getLogger(__name__)


class ChainedMarketDataProvider(MarketDataProvider):
    def __init__(
        self, ibkr: IBKRClientPortalProvider, yahoo: YahooFinanceProvider
    ) -> None:
        self._ibkr = ibkr
        self._yahoo = yahoo

    # -- live path ---------------------------------------------------------

    def get_live_quotes(
        self, equity: dict[str, int | None], options: dict[str, int]
    ) -> LiveQuotes:
        if self._ibkr.available():
            try:
                return self._live_from_ibkr(equity, options)
            except Exception:
                logger.exception(
                    "IBKR live quotes failed mid-flight; falling back to Yahoo"
                )
        return LiveQuotes(closes=self._yahoo.get_latest_closes(list(equity)))

    def _live_from_ibkr(
        self, equity: dict[str, int | None], options: dict[str, int]
    ) -> LiveQuotes:
        symbol_conids = self._ibkr.resolve_equity_conids(equity)
        closes = self._ibkr.get_equity_closes(symbol_conids)
        missing = [s for s in equity if s not in closes]
        if missing:
            closes = {**closes, **self._yahoo.get_latest_closes(missing)}
        return LiveQuotes(
            closes=closes,
            option_marks=self._ibkr.get_option_marks(options),
            source="ibkr",
        )

    # -- history: always Yahoo ----------------------------------------------

    def get_daily_closes(
        self, symbol: str, start: date, end: date
    ) -> dict[date, Decimal]:
        return self._yahoo.get_daily_closes(symbol, start, end)

    def get_latest_close(self, symbol: str) -> Decimal | None:
        return self._yahoo.get_latest_close(symbol)

    def get_latest_closes(self, symbols: list[str]) -> dict[str, Decimal]:
        return self._yahoo.get_latest_closes(symbols)
```

- [ ] **Step 5: 跑测试确认通过(含全量回归)**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_provider_chain.py -v && $HOME/.local/bin/uv run --no-sync pytest -q`
Expected: 新测试全 PASS;全量套件无回归(基类改动是加法)

- [ ] **Step 6: ruff + commit**

```bash
cd backend && $HOME/.local/bin/uv run --no-sync ruff check .
git add backend/app/services/providers/base.py backend/app/services/providers/chain.py backend/tests/test_provider_chain.py
git commit -m "Phase2B: LiveQuotes + ChainedMarketDataProvider (IBKR-first, Yahoo fallback)"
```

---

### Task 4: `compute_live_snapshot` — get_live_quotes 接入 + 期权实时市值 + 尾点修复

**Files:**
- Modify: `backend/app/services/snapshot/live.py`
- Test: `backend/tests/test_snapshot_live.py`(追加)

**Interfaces:**
- Consumes: Task 3 的 `provider.get_live_quotes(equity, options) -> LiveQuotes`
- Produces:
  - `LiveSnapshot` dataclass 新增字段 `source: Literal["ibkr", "yahoo"]`
  - `compute_live_snapshot(session, account, provider, mode)` 签名不变

**背景(实现者必读):** 现在 `live_holdings_usd` 只累加股票/ETF 市值,而历史
日点(`build_day_points` 的 `_holdings_value`)对期权按成本计入 —— live 尾点
漏了期权的成本价值,是 Milestone A 的 bug。本任务修复:非股票/ETF 持仓无 mark
时按 `cost_basis` 计入尾点(展示仍 `market_* = None`),有 mark 时按实时市值。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_snapshot_live.py` 追加(文件顶部 import 区补
`from app.services.providers.base import LiveQuotes`,并在现有 imports 里确认
`Instrument`、`AssetClass` 已引入;新增 `OptionType` 到 `app.db.enums` import):

```python
class _FakeChain(MarketDataProvider):
    """Provider that answers get_live_quotes like the chained provider would."""

    def __init__(self, quotes: LiveQuotes):
        self._quotes = quotes
        self.seen_equity: dict[str, int | None] | None = None
        self.seen_options: dict[str, int] | None = None

    def get_daily_closes(self, symbol, start, end):
        raise NotImplementedError

    def get_latest_close(self, symbol):
        raise NotImplementedError

    def get_latest_closes(self, symbols):
        raise NotImplementedError

    def get_live_quotes(self, equity, options):
        self.seen_equity = dict(equity)
        self.seen_options = dict(options)
        return self._quotes


def _option_instrument(db_session, conid="9999777"):
    inst = Instrument(
        symbol="AAPL  260116C00150000",
        asset_class=AssetClass.OPTION,
        currency="USD",
        conid=conid,
        underlying_symbol="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("150"),
        expiry=date(2026, 1, 16),
        multiplier=100,
    )
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)
    return inst


def test_live_snapshot_option_priced_with_ibkr_mark(db_session, account, instrument):
    option = _option_instrument(db_session)
    db_session.add(_deposit(account, "10000", datetime(2026, 1, 1, 9)))
    db_session.add(_buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1"))
    # Buy 2 option contracts for 800 total cost.
    db_session.add(_buy(account, option, 2, "800", datetime(2026, 1, 3, 10), "B2"))
    db_session.commit()
    provider = _FakeChain(
        LiveQuotes(
            closes={"AAPL": Decimal("120")},
            option_marks={"AAPL  260116C00150000": Decimal("4.35")},
            source="ibkr",
        )
    )

    snap = compute_live_snapshot(db_session, account, provider, "B")

    assert snap.source == "ibkr"
    by_symbol = {p.symbol: p for p in snap.positions}
    opt = by_symbol["AAPL  260116C00150000"]
    assert opt.market_price == Decimal("4.35")
    assert opt.market_value == Decimal("870")  # 2 × 4.35 × 100
    assert opt.unrealized_pnl == Decimal("70")  # 870 − 800
    # equity/options 组装正确:股票带 DB conid(fixture 无 conid → None),期权带 conid
    assert provider.seen_equity == {"AAPL": None}
    assert provider.seen_options == {"AAPL  260116C00150000": 9999777}
    # 尾点:cash 10000−1000−800=8200;AAPL 1200;期权 870 → 10270
    # cumulative_pnl(mode B)= 10270 − 10000 = 270
    assert snap.curve_tail.cumulative_pnl == Decimal("270")


def test_live_snapshot_option_at_cost_when_no_mark(db_session, account, instrument):
    """离线(或期权缺 mark)→ 期权展示留空,但尾点按成本计入(修 A 的漏计 bug)。"""
    option = _option_instrument(db_session)
    db_session.add(_deposit(account, "10000", datetime(2026, 1, 1, 9)))
    db_session.add(_buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1"))
    db_session.add(_buy(account, option, 2, "800", datetime(2026, 1, 3, 10), "B2"))
    db_session.commit()
    provider = _FakeChain(
        LiveQuotes(closes={"AAPL": Decimal("120")}, option_marks={}, source="yahoo")
    )

    snap = compute_live_snapshot(db_session, account, provider, "B")

    assert snap.source == "yahoo"
    opt = {p.symbol: p for p in snap.positions}["AAPL  260116C00150000"]
    assert opt.market_price is None
    assert opt.market_value is None
    assert opt.unrealized_pnl is None
    # 尾点:8200 + 1200 + 期权成本 800 = 10200 → pnl 200(修复前会漏掉 800)
    assert snap.curve_tail.cumulative_pnl == Decimal("200")


def test_live_snapshot_option_without_conid_not_requested(db_session, account, instrument):
    option = _option_instrument(db_session, conid=None)
    db_session.add(_deposit(account, "10000", datetime(2026, 1, 1, 9)))
    db_session.add(_buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1"))
    db_session.add(_buy(account, option, 2, "800", datetime(2026, 1, 3, 10), "B2"))
    db_session.commit()
    provider = _FakeChain(
        LiveQuotes(closes={"AAPL": Decimal("120")}, option_marks={}, source="ibkr")
    )

    snap = compute_live_snapshot(db_session, account, provider, "B")

    assert provider.seen_options == {}  # conid 缺失 → 不请求,直接成本计
    assert snap.curve_tail.cumulative_pnl == Decimal("200")
```

同时检查现有测试:`_FakeProvider` 继承 `MarketDataProvider`,基类默认
`get_live_quotes` 会转调它的 `get_latest_closes` —— 现有测试**不用改**,
`source` 默认 `"yahoo"`。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_snapshot_live.py -v`
Expected: 新增 3 个 FAIL(`LiveSnapshot` 无 `source`、期权无实时市值);现有的 PASS

- [ ] **Step 3: 改 `live.py`**

改动点(其余保持原样):

1. imports:`AssetClass` 已有;`MarketDataProvider` 保留。
2. `LiveSnapshot` dataclass 加字段:

```python
@dataclass(frozen=True)
class LiveSnapshot:
    fetched_at: datetime
    positions: list[LivePosition]
    curve_tail: CurvePoint
    source: Literal["ibkr", "yahoo"]
```

3. 模块级加 helper:

```python
def _int_conid(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
```

4. `compute_live_snapshot` 主体:把「组价 + overlay」段替换为:

```python
    positions = compute_positions(session, account)
    # Look up asset class once — needed to decide which positions get priced.
    instruments = {
        iid: session.get(Instrument, iid)
        for iid in {p.instrument_id for p in positions}
    }
    equity: dict[str, int | None] = {}
    options: dict[str, int] = {}
    for p in positions:
        inst = instruments[p.instrument_id]
        if inst.asset_class in _PRICED:
            equity[p.symbol] = _int_conid(inst.conid)
        elif inst.asset_class is AssetClass.OPTION:
            conid = _int_conid(inst.conid)
            if conid is not None:
                options[p.symbol] = conid
    quotes = provider.get_live_quotes(equity, options)
    closes = quotes.closes
    missing = [s for s in equity if closes.get(s) is None]
    if missing:
        raise LiveDataUnavailable(missing)

    live_positions: list[LivePosition] = []
    live_holdings_usd = Decimal("0")
    for p in positions:
        inst = instruments[p.instrument_id]
        if inst.asset_class in _PRICED:
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
        elif p.symbol in quotes.option_marks:
            mark = quotes.option_marks[p.symbol]
            market_value = p.quantity * mark * inst.multiplier
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
            # No live mark — the position still counts at cost in the curve
            # tail, matching `_holdings_value`'s cost fallback for history
            # points (fixes Milestone A omitting option value from the tail).
            live_holdings_usd += p.cost_basis
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
```

5. return 补 `source=quotes.source`:

```python
    return LiveSnapshot(
        fetched_at=datetime.now(UTC),
        positions=live_positions,
        curve_tail=curve[-1],
        source=quotes.source,
    )
```

6. 模块 docstring 的 strict 语义描述补一句期权 best-effort(成本兜底)。

- [ ] **Step 4: 跑测试确认通过(含全量回归)**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest -q`
Expected: 全量 PASS。**注意**:若既有测试有「期权/非价资产不进尾点」的断言
被尾点修复改变了预期值,逐个核对新值是否符合"期权按成本计入"口径后更新断言
(这是修 bug 带来的预期变化,不是回归)。

- [ ] **Step 5: ruff + commit**

```bash
cd backend && $HOME/.local/bin/uv run --no-sync ruff check .
git add backend/app/services/snapshot/live.py backend/tests/test_snapshot_live.py
git commit -m "Phase2B: live snapshot — IBKR option marks + fix tail omitting option cost value"
```

---

### Task 5: API 接线 — deps / schemas / accounts + API 测试

**Files:**
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/accounts.py`
- Test: `backend/tests/test_api_accounts.py`(追加)

**Interfaces:**
- Consumes: Task 3 `ChainedMarketDataProvider`、`IBKRClientPortalProvider`;Task 4 `snap.source`
- Produces: `GET /accounts/{id}/live-snapshot` 响应含 `"source": "ibkr" | "yahoo"`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_api_accounts.py` 追加(沿用该文件现有的
`_with_provider` helper 与 fixture 数据约定;`_FakeProvider` 继承基类,默认
`get_live_quotes` 生效):

```python
def test_live_snapshot_reports_source(api_client):
    _upload(api_client)
    key = _with_provider(lambda: _FakeProvider())
    try:
        response = api_client.get("/accounts/U0000000/live-snapshot")
    finally:
        from app.main import app

        del app.dependency_overrides[key]

    assert response.status_code == 200
    assert response.json()["source"] == "yahoo"
```

(说明:`_upload` / `_with_provider` / `_FakeProvider` 都是该文件已有的
helper,照 `test_live_snapshot_returns_overlaid_positions` 的套路。fake 走
基类默认 `get_live_quotes` → `source="yahoo"`;`"ibkr"` 分支已在 Task 3/4
的单测覆盖,API 层只须验证字段透出。)

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest tests/test_api_accounts.py -v -k source`
Expected: FAIL —— 响应 JSON 无 `source` 键

- [ ] **Step 3: 三处接线**

`schemas.py` —— imports 加 `from typing import Literal`;`LiveSnapshotOut` 加字段:

```python
class LiveSnapshotOut(BaseModel):
    fetched_at: datetime
    positions: list[PositionOut]
    curve_tail: CurvePointOut
    source: Literal["ibkr", "yahoo"]
```

`accounts.py` —— return 处加一行:

```python
    return schemas.LiveSnapshotOut(
        fetched_at=snap.fetched_at,
        positions=[schemas.PositionOut(**asdict(p)) for p in snap.positions],
        curve_tail=schemas.CurvePointOut(
            on_date=snap.curve_tail.on_date,
            cumulative_pnl=snap.curve_tail.cumulative_pnl,
            pct=snap.curve_tail.pct,
        ),
        source=snap.source,
    )
```

`deps.py` —— imports 加:

```python
from app.services.providers.chain import ChainedMarketDataProvider
from app.services.providers.ibkr_cp import IBKRClientPortalProvider
```

`get_market_data_provider` 改为:

```python
def get_market_data_provider() -> MarketDataProvider:
    """The market-data provider — overridable in tests with a fake."""
    return ChainedMarketDataProvider(
        ibkr=IBKRClientPortalProvider(), yahoo=YahooFinanceProvider()
    )
```

- [ ] **Step 4: 跑测试确认通过(含全量回归)**

Run: `cd backend && $HOME/.local/bin/uv run --no-sync pytest -q`
Expected: 全量 PASS(现有 live-snapshot API 测试用 fake 覆盖 provider,不碰
真 Gateway;`refresh-prices` 路径经 chain 转发 Yahoo,不受影响)

- [ ] **Step 5: ruff + commit**

```bash
cd backend && $HOME/.local/bin/uv run --no-sync ruff check .
git add backend/app/api/deps.py backend/app/api/schemas.py backend/app/api/accounts.py backend/tests/test_api_accounts.py
git commit -m "Phase2B: wire ChainedMarketDataProvider into API; live-snapshot reports source"
```

---

### Task 6: 前端 — source 透传到徽章

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/(workspace)/_components/LiveStatusBadge.tsx`
- Modify: `frontend/app/(workspace)/positions/_components/LivePositionsTable.tsx`
- Modify: `frontend/app/(workspace)/pnl/_components/LivePnlTail.tsx`

**Interfaces:**
- Consumes: 后端 `LiveSnapshot.source`(Task 5)
- Produces: `LiveStatusBadge` 新增可选 prop `source?: LiveSource | null`

- [ ] **Step 1: `lib/api.ts` 类型**

`LiveSnapshot` 上方加类型、字段:

```typescript
export type LiveSource = "ibkr" | "yahoo";

export type LiveSnapshot = {
  fetched_at: string;
  positions: Position[];
  curve_tail: CurveTail;
  source: LiveSource;
};
```

- [ ] **Step 2: `LiveStatusBadge` 显示来源**

签名与 live 分支改为(其余 variant 不动):

```typescript
const SOURCE_LABEL: Record<LiveSource, string> = {
  ibkr: "IBKR",
  yahoo: "Yahoo (delayed)",
};

export function LiveStatusBadge({
  status,
  lastFetchedAt,
  source = null,
}: {
  status: LivePollStatus;
  lastFetchedAt: Date | null;
  source?: LiveSource | null;
}) {
```

`variantFor` 增加 `source: LiveSource | null` 参数;`case "live"` 的 text 改为:

```typescript
      const label = source ? ` · ${SOURCE_LABEL[source]}` : "";
      return {
        text: `Live${label} · ${ago}s ago`,
        dotClass: "bg-up",
        textClass: "text-muted-strong",
      };
```

调用处 `const v = variantFor(status, lastFetchedAt, nowMs)` 改为
`variantFor(status, source, lastFetchedAt, nowMs)`(参数顺序:status, source,
lastFetchedAt, nowMs)。顶部补 `import type { LiveSource } from "@/lib/api";`。

- [ ] **Step 3: 两个 wrapper 透传**

`LivePositionsTable.tsx`:

```typescript
  const [source, setSource] = useState<LiveSource | null>(null);
```

`onData` 里加 `setSource(snap.source);`;徽章处:

```typescript
        <LiveStatusBadge status={status} lastFetchedAt={lastFetchedAt} source={source} />
```

import 行改 `import { api, type LiveSource, type Position } from "@/lib/api";`。

`LivePnlTail.tsx` 同样三处改动(state + onData `setSource(snap.source);` +
徽章 prop),import 加 `type LiveSource`。

- [ ] **Step 4: lint + build 验证**

Run: `cd frontend && npx eslint . && npm run build`
Expected: 双绿

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts "frontend/app/(workspace)/_components/LiveStatusBadge.tsx" "frontend/app/(workspace)/positions/_components/LivePositionsTable.tsx" "frontend/app/(workspace)/pnl/_components/LivePnlTail.tsx"
git commit -m "Phase2B: badge shows live data source (IBKR / Yahoo delayed)"
```

---

### Task 7: Gateway 工具链 — Makefile / .gitignore / README 配置文档

**Files:**
- Modify: `Makefile`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] **Step 1: `.gitignore` 加 Gateway 目录**

在 `# Local secrets / DB dumps` 段前加:

```
# IBKR Client Portal Gateway (user-downloaded, see README)
gateway/
```

- [ ] **Step 2: Makefile 加 `gateway` target**

`.PHONY` 行加 `gateway`;`help` 里加一行
`@echo "  make gateway         run IBKR Client Portal Gateway (:5000)"`;
`dev-frontend` 后加:

```make
gateway:
	@if [ ! -d gateway/clientportal.gw ]; then \
	  echo "IBKR Client Portal Gateway not found at gateway/clientportal.gw"; \
	  echo ""; \
	  echo "  1. Download: https://download2.interactivebrokers.com/portal/clientportal.gw.zip"; \
	  echo "  2. Unzip so that gateway/clientportal.gw/bin/run.sh exists"; \
	  echo "  3. Re-run: make gateway"; \
	  exit 1; \
	fi
	cd gateway/clientportal.gw && sh bin/run.sh root/conf.yaml
```

- [ ] **Step 3: README 加配置小节(英文段 + 中文段)**

英文 `### Quick start` 之后(`Run parts individually` 代码块后)加:

```markdown
### IBKR Client Portal Gateway (optional, realtime quotes)

Live polling upgrades from delayed Yahoo data to realtime IBKR quotes when
the IBKR Client Portal Gateway is running and logged in (requires Java 8+):

1. Download the [Client Portal Gateway](https://download2.interactivebrokers.com/portal/clientportal.gw.zip)
   and unzip it so that `gateway/clientportal.gw/bin/run.sh` exists.
2. `make gateway` — starts it on `https://localhost:5000`.
3. Open `https://localhost:5000` in a browser (accept the self-signed
   certificate) and log in with your IBKR credentials + 2FA.

The `/positions` and `/pnl` badges show the active source: `Live · IBKR`
(realtime, options priced at IBKR mark) or `Live · Yahoo (delayed)`
(fallback whenever the Gateway is down or logged out — options fall back
to cost). No configuration needed; the fallback is automatic.
```

中文 `### 快速开始` 的"单独启动"代码块后加对应中文段:

```markdown
### IBKR Client Portal Gateway(可选,实时行情)

跑起并登录 IBKR Client Portal Gateway 后,轮询数据自动从 Yahoo 延迟价升级为
IBKR 实时价(需要 Java 8+):

1. 下载 [Client Portal Gateway](https://download2.interactivebrokers.com/portal/clientportal.gw.zip),
   解压到仓库根目录使 `gateway/clientportal.gw/bin/run.sh` 存在。
2. `make gateway` —— 启动在 `https://localhost:5000`。
3. 浏览器访问 `https://localhost:5000`(接受自签名证书),用 IBKR 账号 + 2FA 登录。

`/positions` 与 `/pnl` 的徽章会显示当前数据源:`Live · IBKR`(实时,期权按
IBKR mark 计价)或 `Live · Yahoo (delayed)`(Gateway 掉线/未登录时自动回落,
期权回落成本计价)。无需任何配置,回退全自动。
```

- [ ] **Step 4: 验证 + commit**

Run: `make gateway`
Expected: 打印下载指引后 exit 1(目录不存在时的引导路径)

```bash
git add Makefile .gitignore README.md
git commit -m "Phase2B: make gateway + IBKR Gateway setup docs"
```

---

### Task 8: 收尾 — 全量验证 + README 进度 + 手动冒烟清单

**Files:**
- Modify: `README.md`(进度段)

- [ ] **Step 1: 全量验证**

```bash
cd backend && $HOME/.local/bin/uv run --no-sync pytest -q && $HOME/.local/bin/uv run --no-sync ruff check .
cd frontend && npx eslint . && npm run build
```

Expected: 后端全绿(≈200+ tests,182 基线 + 新增)、ruff 绿、前端双绿

- [ ] **Step 2: README 进度段更新(英文 + 中文)**

英文 `#### 🚧 Phase 2 — Realtime data (Milestone A done)` 改为
`#### 🚧 Phase 2 — Realtime data (Milestones A & B done)`,Milestone B 行改为:

```markdown
- **Milestone B** ✅ — IBKR Client Portal realtime quotes: chained provider
  (`IBKR CP > Yahoo`) behind `live-snapshot`, options priced at IBKR mark
  when the Gateway is up, silent fallback to delayed Yahoo otherwise;
  badge shows the active source. Positions reconciliation & order status
  deferred to later milestones.
```

中文段对应:`#### 🚧 Phase 2 —— 实时数据(Milestone A 已完成)` 改为
`#### 🚧 Phase 2 —— 实时数据(Milestone A、B 已完成)`,Milestone B 行改为:

```markdown
- **Milestone B** ✅ —— IBKR Client Portal 实时报价:live-snapshot 后面挂
  链式 provider(`IBKR CP > Yahoo`),Gateway 在线时期权按 IBKR mark 实时
  计价,掉线静默回落 Yahoo 延迟价;徽章显示当前数据源。持仓对账与订单状态
  留给后续里程碑。
```

```bash
git add README.md
git commit -m "docs: Phase 2 Milestone B — IBKR CP realtime quotes shipped"
```

- [ ] **Step 3: 手动冒烟清单(需要用户参与 —— 真 Gateway + 2FA)**

以下需要用户操作,实现者只准备环境并陪跑:

1. 下载 Gateway 解压到 `gateway/clientportal.gw/`,`make gateway` 启动,
   浏览器 `https://localhost:5000` 登录(IBKR 账号 + 2FA)。
2. `make dev` 起前后端,开 `http://localhost:3000/positions`(**localhost**,
   不要 127.0.0.1)。徽章应显示 `Live · IBKR · Ns ago`;期权行的
   Mkt Price / Mkt Value / Unrealized P&L 应有实时值。
3. 开 `/pnl`,徽章同样 `Live · IBKR`;曲线尾点含期权实时市值。
4. `Ctrl+C` 杀掉 Gateway(保留前后端)。下一 tick 徽章回落
   `Live · Yahoo (delayed)`,期权行 market 列变 `—`,不报错。
5. 重启 Gateway 并重新登录,下一 tick 徽章回 `Live · IBKR`。
6. 杀掉 backend → 徽章 `Quote unavailable`(现状语义,回归确认)。
7. 真实字段核验:若实测发现 snapshot 字段号 / 响应形状与实现不符
   (spec 的"实施注"),按实测修 `ibkr_cp.py` 与 spec,补测试。

- [ ] **Step 4: 完成分支 —— finishing-a-development-branch**

冒烟通过后走 `superpowers:finishing-a-development-branch`:
`git log --oneline main..HEAD` 总览(预期 ≈10 commits:spec×2 + 计划 +
后端×5 + 前端 + 工具链/docs×2),用户选 merge 还是 PR。

---

## 完成标准

- 后端 pytest 全绿 + ruff 全绿;前端 eslint + build 全绿
- Gateway 不存在/不在线时,live-snapshot 行为与 Milestone A 完全一致
  (仅多出 `source: "yahoo"` 字段与期权成本进尾点的修复)
- Gateway 在线时:股票/ETF 用 IBKR 实时价,期权按 mark 计市值,`source: "ibkr"`
- 手动冒烟 7 条通过(需要用户的 Gateway + 2FA)
- README:配置文档 + 进度段更新
