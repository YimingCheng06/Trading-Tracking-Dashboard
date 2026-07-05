from decimal import Decimal
from pathlib import Path

from app.services.providers.base import MarketDataProvider


def test_list_accounts_empty(api_client):
    response = api_client.get("/accounts")
    assert response.status_code == 200
    assert response.json() == []


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

    def get_latest_closes(self, symbols):
        return {s: Decimal("100") for s in symbols}


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
