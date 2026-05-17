from decimal import Decimal

import pytest

from app.db.enums import TradeSide
from app.db.models import Trade
from app.services.pnl.fifo import run_fifo


def _trade(side, quantity, proceeds_usd, commission_usd="0", trade_id="T"):
    """A minimal in-memory Trade — run_fifo reads only these 5 fields."""
    return Trade(
        trade_id=trade_id,
        side=side,
        quantity=Decimal(str(quantity)),
        proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal(str(commission_usd)),
    )


def test_fifo_realized_pnl_simple():
    result = run_fifo(
        [_trade(TradeSide.BUY, 10, "-1000"), _trade(TradeSide.SELL, 10, "1200")]
    )
    assert result.realized_pnl == Decimal("200")
    assert result.open_quantity == Decimal("0")
    assert result.open_cost_basis == Decimal("0")


def test_fifo_realized_pnl_includes_commission():
    # cost/unit = (1000+5)/10 = 100.5 ; proceeds/unit = (1200-5)/10 = 119.5
    # realized = 10 * (119.5 - 100.5) = 190
    result = run_fifo(
        [
            _trade(TradeSide.BUY, 10, "-1000", "5"),
            _trade(TradeSide.SELL, 10, "1200", "5"),
        ]
    )
    assert result.realized_pnl == Decimal("190")


def test_fifo_partial_lot_match_across_two_buys():
    # Buy 10 @100, buy 10 @110, sell 15 @120.
    # 10*(120-100) + 5*(120-110) = 200 + 50 = 250 ; 5 units of lot2 remain.
    result = run_fifo(
        [
            _trade(TradeSide.BUY, 10, "-1000", trade_id="B1"),
            _trade(TradeSide.BUY, 10, "-1100", trade_id="B2"),
            _trade(TradeSide.SELL, 15, "1800", trade_id="S1"),
        ]
    )
    assert result.realized_pnl == Decimal("250")
    assert result.open_quantity == Decimal("5")
    assert result.open_cost_basis == Decimal("550")  # 5 units @110


def test_fifo_open_position_after_partial_sell():
    result = run_fifo(
        [_trade(TradeSide.BUY, 10, "-1000"), _trade(TradeSide.SELL, 4, "480")]
    )
    assert result.realized_pnl == Decimal("80")  # 4 * (120 - 100)
    assert result.open_quantity == Decimal("6")
    assert result.open_cost_basis == Decimal("600")  # 6 units @100


def test_fifo_sell_exceeding_position_raises():
    with pytest.raises(ValueError, match="exceeds open position"):
        run_fifo([_trade(TradeSide.SELL, 5, "600", trade_id="S9")])


def test_fifo_zero_quantity_raises():
    with pytest.raises(ValueError, match="zero quantity"):
        run_fifo([_trade(TradeSide.BUY, 0, "0", trade_id="Z1")])


def test_fifo_sell_exactly_empties_first_lot():
    # Buy 10 @100, buy 10 @110, sell exactly 10 — first lot fully consumed,
    # second lot left intact.
    result = run_fifo(
        [
            _trade(TradeSide.BUY, 10, "-1000", trade_id="B1"),
            _trade(TradeSide.BUY, 10, "-1100", trade_id="B2"),
            _trade(TradeSide.SELL, 10, "1200", trade_id="S1"),
        ]
    )
    assert result.realized_pnl == Decimal("200")  # 10 * (120 - 100)
    assert result.open_quantity == Decimal("10")
    assert result.open_cost_basis == Decimal("1100")  # 10 units @110
