"""Equity-curve math — two P&L-percentage modes.

Pure functions over a daily series. The daily portfolio values come from
positions_snapshot (the market-data layer); this module only does the math.

- Mode A (IBKR / time-weighted return): deposits do not distort past
  percentages; daily returns are chained.
- Mode B (capital-adjusted): every day's percentage is cumulative P&L
  divided by the **final (latest-day) total net deposits**, so the whole
  curve rescales when money is added.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class DayPoint:
    on_date: date
    portfolio_value: Decimal  # total account value at end of day, USD
    net_flow: Decimal  # external deposits minus withdrawals that day. The
    # Mode A return excludes this flow — it is treated as occurring at the
    # END of the day, so a deposit does not inflate that day's return.


@dataclass(frozen=True)
class CurvePoint:
    on_date: date
    cumulative_pnl: Decimal   # portfolio_value - cumulative net deposits
    pct: Decimal | None       # percentage for the chosen mode; None if undefined


def _cumulative(points: list[DayPoint]) -> list[tuple[Decimal, Decimal]]:
    """Per point: (cumulative net deposits, cumulative P&L)."""
    cum_deposits = Decimal("0")
    out: list[tuple[Decimal, Decimal]] = []
    for p in points:
        cum_deposits += p.net_flow
        out.append((cum_deposits, p.portfolio_value - cum_deposits))
    return out


def _mode_a(points: list[DayPoint]) -> list[CurvePoint]:
    """Time-weighted return: chain daily returns, excluding external flows."""
    curve: list[CurvePoint] = []
    cum_factor = Decimal("1")
    prev_value = Decimal("0")
    for p, (_, cum_pnl) in zip(points, _cumulative(points), strict=True):
        # A zero prior value (e.g. a total loss, or before the first
        # deposit) yields a 0 return — TWR cannot recover from a 100% loss.
        if prev_value > 0:
            daily_return = (p.portfolio_value - p.net_flow) / prev_value - 1
        else:
            daily_return = Decimal("0")
        cum_factor *= 1 + daily_return
        curve.append(CurvePoint(p.on_date, cum_pnl, cum_factor - 1))
        prev_value = p.portfolio_value
    return curve


def _mode_b(points: list[DayPoint]) -> list[CurvePoint]:
    """Capital-adjusted: cumulative P&L over the final total net deposits."""
    cumulative = _cumulative(points)
    final_deposits = cumulative[-1][0] if cumulative else Decimal("0")
    curve: list[CurvePoint] = []
    for p, (_, cum_pnl) in zip(points, cumulative, strict=True):
        pct = cum_pnl / final_deposits if final_deposits > 0 else None
        curve.append(CurvePoint(p.on_date, cum_pnl, pct))
    return curve


def compute_equity_curve(
    points: list[DayPoint], mode: Literal["A", "B"]
) -> list[CurvePoint]:
    """Build the equity curve for `mode` over a chronological daily series."""
    if mode == "A":
        return _mode_a(points)
    if mode == "B":
        return _mode_b(points)
    raise ValueError(f"unknown equity-curve mode {mode!r}")
