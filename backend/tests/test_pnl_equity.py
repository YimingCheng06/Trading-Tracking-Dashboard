from datetime import date, datetime
from decimal import Decimal

from app.db.enums import AssetClass, CashFlowType, TradeSide
from app.db.models import CashFlow, Instrument, PositionSnapshot, Trade
from app.services.pnl.equity import build_day_points, compute_account_curve


def _snapshot(account, instrument, day, qty, avg_cost, market_value_usd):
    return PositionSnapshot(
        account_id=account.id,
        instrument_id=instrument.id,
        snapshot_date=day,
        quantity=Decimal(str(qty)),
        avg_cost=Decimal(str(avg_cost)),
        market_price=None if market_value_usd is None else Decimal("1"),
        market_value=None if market_value_usd is None else Decimal(str(market_value_usd)),
        market_value_usd=None if market_value_usd is None else Decimal(str(market_value_usd)),
        unrealized_pnl=None,
        unrealized_pnl_usd=None,
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


def _buy(account, instrument, qty, proceeds_usd, executed_at, trade_id):
    return Trade(
        account_id=account.id, instrument_id=instrument.id, trade_id=trade_id,
        side=TradeSide.BUY, quantity=Decimal(str(qty)), price=Decimal("100"),
        currency="USD", fx_rate_to_usd=Decimal("1"),
        proceeds=Decimal(str(proceeds_usd)), proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal("0"), executed_at=executed_at,
    )


def test_build_day_points_portfolio_value_is_cash_plus_holdings(
    db_session, account, instrument
):
    # Deposit 5000 on Jan 1; buy 10 shares for 1000 on Jan 2.
    db_session.add(
        _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9))
    )
    db_session.add(_buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1"))
    # Snapshot: Jan 2 holdings worth 1000, Jan 5 worth 1100.
    db_session.add_all(
        [
            _snapshot(account, instrument, date(2026, 1, 2), 10, 100, "1000"),
            _snapshot(account, instrument, date(2026, 1, 5), 10, 100, "1100"),
        ]
    )
    db_session.commit()

    points = build_day_points(db_session, account)

    assert [p.on_date for p in points] == [date(2026, 1, 2), date(2026, 1, 5)]
    # Jan 2: cash = 5000 - 1000 = 4000 ; holdings = 1000 ; total = 5000.
    assert points[0].portfolio_value == Decimal("5000")
    # Jan 5: cash = 4000 ; holdings = 1100 ; total = 5100.
    assert points[1].portfolio_value == Decimal("5100")


def test_build_day_points_net_flow_is_deposits_minus_withdrawals(
    db_session, account, instrument
):
    db_session.add_all(
        [
            _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 2, 9)),
            _cash_flow(account, CashFlowType.WITHDRAWAL, "-200", datetime(2026, 1, 5, 9)),
            _cash_flow(account, CashFlowType.FEE, "-10", datetime(2026, 1, 5, 9)),
        ]
    )
    db_session.add(_buy(account, instrument, 1, "100", datetime(2026, 1, 2, 10), "B1"))
    db_session.add_all(
        [
            _snapshot(account, instrument, date(2026, 1, 2), 1, 100, "100"),
            _snapshot(account, instrument, date(2026, 1, 5), 1, 100, "100"),
        ]
    )
    db_session.commit()

    points = build_day_points(db_session, account)
    by_date = {p.on_date: p for p in points}

    assert by_date[date(2026, 1, 2)].net_flow == Decimal("5000")
    # Withdrawal counts; the fee does not.
    assert by_date[date(2026, 1, 5)].net_flow == Decimal("-200")


def test_build_day_points_values_options_at_cost(db_session, account):
    option = Instrument(
        symbol="AAPL  260116C00150000", asset_class=AssetClass.OPTION, currency="USD"
    )
    db_session.add(option)
    db_session.flush()
    db_session.add(_buy(account, option, 2, "600", datetime(2026, 1, 2, 10), "O1"))
    # Option snapshot with no market value → valued at quantity * avg_cost.
    db_session.add(_snapshot(account, option, date(2026, 1, 2), 2, 300, None))
    db_session.commit()

    points = build_day_points(db_session, account)

    # cash = -600 (the buy) ; holdings = 2 * 300 = 600 ; total = 0.
    assert points[0].portfolio_value == Decimal("0")


def test_compute_account_curve_returns_curve_points(db_session, account, instrument):
    db_session.add(
        _cash_flow(account, CashFlowType.DEPOSIT, "1000", datetime(2026, 1, 2, 9))
    )
    db_session.add(_buy(account, instrument, 10, "1000", datetime(2026, 1, 2, 10), "B1"))
    db_session.add_all(
        [
            _snapshot(account, instrument, date(2026, 1, 2), 10, 100, "1000"),
            _snapshot(account, instrument, date(2026, 1, 5), 10, 100, "1100"),
        ]
    )
    db_session.commit()

    curve = compute_account_curve(db_session, account, "B")

    assert [c.on_date for c in curve] == [date(2026, 1, 2), date(2026, 1, 5)]
    # Mode B: cumulative P&L over final net deposits (1000).
    # Jan 2: value 1000, deposits 1000 → pnl 0 → 0%.
    # Jan 5: value 1100, deposits 1000 → pnl 100 → 10%.
    assert curve[0].cumulative_pnl == Decimal("0")
    assert curve[1].cumulative_pnl == Decimal("100")
    assert curve[1].pct == Decimal("100") / Decimal("1000")
