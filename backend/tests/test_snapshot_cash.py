from datetime import date, datetime
from decimal import Decimal

from app.db.enums import CashFlowType, TradeSide
from app.db.models import CashFlow, Trade
from app.services.pnl.equity import build_day_points
from app.services.snapshot.cash import compute_cash_at


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


def test_compute_cash_at_withdrawal_reduces_cash(db_session, account):
    # IBKR encodes withdrawals as a negative amount_usd; the helper just sums
    # amount_usd over all flow types, so this pins the sign convention.
    db_session.add_all(
        [
            _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9)),
            _cash_flow(account, CashFlowType.WITHDRAWAL, "-2000",
                       datetime(2026, 1, 3, 9)),
        ]
    )
    db_session.commit()
    assert compute_cash_at(db_session, account, date(2026, 1, 5)) == Decimal("3000")


def test_compute_cash_at_includes_dividend_and_interest(db_session, account):
    # Dividends and interest credit cash, fees debit it — the helper sums all
    # flow types so cash sees them all.
    db_session.add_all(
        [
            _cash_flow(account, CashFlowType.DEPOSIT, "5000", datetime(2026, 1, 1, 9)),
            _cash_flow(account, CashFlowType.DIVIDEND, "12",
                       datetime(2026, 1, 2, 9)),
            _cash_flow(account, CashFlowType.INTEREST, "3",
                       datetime(2026, 1, 2, 9)),
            _cash_flow(account, CashFlowType.FEE, "-1",
                       datetime(2026, 1, 2, 9)),
        ]
    )
    db_session.commit()
    # 5000 + 12 + 3 - 1 = 5014
    assert compute_cash_at(db_session, account, date(2026, 1, 5)) == Decimal("5014")


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
