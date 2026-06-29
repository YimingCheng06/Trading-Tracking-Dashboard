from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.db.enums import AssetClass, CashFlowType, TradeSide
from app.db.models import CashFlow, Instrument, PositionSnapshot, Trade
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
    assert snap.fetched_at.tzinfo == UTC
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
    # Modes A (TWR) and B (capital-adjusted) diverge only when cash flows arrive
    # at different portfolio values — a single initial deposit always gives the
    # same result in both modes.
    #
    # Setup:
    #   Jan 1  → deposit 1000, buy 10 AAPL @ 100 = 1000 cost  (cash=0)
    #   Feb 1  → snapshot: AAPL @ 150, market_value=1500        (portfolio=1500)
    #   Mar 1  → deposit 500 more                               (portfolio=2000)
    #   today  → live price 120                                  (portfolio=500+1200=1700)
    #
    # Mode A (TWR): chains  +50 % → 0 % → -15 % ≈ +27.5 % cumulative
    # Mode B (cap-adj): pnl/total_deposits = 200/1500 ≈ 13.3 %
    db_session.add(_deposit(account, "1000", datetime(2026, 1, 1, 9)))
    db_session.add(
        _buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1")
    )
    db_session.add(
        PositionSnapshot(
            account_id=account.id,
            instrument_id=instrument.id,
            snapshot_date=date(2026, 2, 1),
            quantity=Decimal("10"),
            avg_cost=Decimal("100"),
            market_price=Decimal("150"),
            market_value=Decimal("1500"),
            market_value_usd=Decimal("1500"),
            unrealized_pnl=Decimal("500"),
            unrealized_pnl_usd=Decimal("500"),
        )
    )
    db_session.add(_deposit(account, "500", datetime(2026, 3, 1, 9)))
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
