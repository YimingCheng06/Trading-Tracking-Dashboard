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
