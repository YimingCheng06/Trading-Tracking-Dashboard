"""IBKRClientPortalClient tests — all offline via httpx.MockTransport."""

from decimal import Decimal

import httpx

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
