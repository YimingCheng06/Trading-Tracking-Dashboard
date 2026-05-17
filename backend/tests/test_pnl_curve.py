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


def test_mode_a_empty_returns_empty():
    assert compute_equity_curve([], "A") == []


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
