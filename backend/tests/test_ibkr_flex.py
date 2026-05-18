import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.db.enums import AssetClass, OptionType, TradeSide
from app.services.parsers.ibkr_flex import (
    _content_hash,
    _dec,
    _parse_dt,
    _parse_trades,
    _split_sections,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ibkr_flex_sample.csv"


def test_split_sections_finds_three_sections():
    with FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    sections = _split_sections(rows)
    assert len(sections) == 3
    trades_header, trades_data = sections[0]
    assert "Buy/Sell" in trades_header
    assert len(trades_data) == 7
    ca_header, ca_data = sections[1]
    assert "Buy/Sell" not in ca_header and "Type" not in ca_header
    assert len(ca_data) == 2
    cash_header, cash_data = sections[2]
    assert "Type" in cash_header
    assert len(cash_data) == 6


def test_parse_dt_handles_timestamp_with_timezone():
    assert _parse_dt("2026-03-26;15:30:58 EDT") == datetime(2026, 3, 26, 15, 30, 58)


def test_parse_dt_handles_date_only():
    assert _parse_dt("2025-11-21") == datetime(2025, 11, 21, 0, 0, 0)


def test_dec_parses_blank_as_none():
    assert _dec("") is None
    assert _dec("12.5") == Decimal("12.5")


def test_content_hash_is_stable_and_short():
    h = _content_hash("a", None, Decimal("1"))
    assert h == _content_hash("a", None, Decimal("1"))
    assert len(h) == 16


# ---------------------------------------------------------------------------
# Task 3: _parse_trades
# ---------------------------------------------------------------------------


def _trades_section():
    with FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    header, data = _split_sections(rows)[0]
    return [dict(zip(header, r, strict=False)) for r in data]


def test_parse_trades_maps_stock_buy():
    instruments, trades, fx = _parse_trades(_trades_section())
    aapl_buy = next(t for t in trades if t.instrument == "AAPL" and t.side == TradeSide.BUY)
    assert aapl_buy.quantity == Decimal("10")
    assert aapl_buy.price == Decimal("100")
    assert aapl_buy.proceeds_usd == Decimal("1000")
    assert aapl_buy.commission_usd == Decimal("1")  # abs(IBCommission)
    assert aapl_buy.fx_rate_to_usd == Decimal("1")
    assert aapl_buy.executed_at == datetime(2026, 1, 5, 10, 0, 0)


def test_parse_trades_quantity_always_positive():
    _, trades, _ = _parse_trades(_trades_section())
    sell = next(t for t in trades if t.instrument == "AAPL" and t.side == TradeSide.SELL)
    assert sell.quantity == Decimal("4")
    assert sell.realized_pnl_ibkr == Decimal("39")


def test_parse_trades_maps_option_instrument():
    instruments, trades, _ = _parse_trades(_trades_section())
    opt = next(i for i in instruments if i.asset_class is AssetClass.OPTION)
    assert opt.symbol == "AAPL  260116C00150000"
    assert opt.underlying_symbol == "AAPL"
    assert opt.option_type is OptionType.CALL
    assert opt.strike == Decimal("150")
    assert opt.expiry == date(2026, 1, 16)
    assert opt.multiplier == 100


def test_parse_trades_harvests_forex_rates():
    _, trades, fx = _parse_trades(_trades_section())
    # CASH rows produce no trades, only FX rates (CAD->USD = 1/price)
    assert all(t.instrument not in ("USD.CAD",) for t in trades)
    assert fx[("CAD", date(2026, 1, 1))] == Decimal("1") / Decimal("1.4")
    assert fx[("CAD", date(2026, 3, 1))] == Decimal("1") / Decimal("1.25")


def test_parse_trades_uses_ibexecid_as_trade_id():
    _, trades, _ = _parse_trades(_trades_section())
    buy = next(t for t in trades if t.instrument == "AAPL" and t.side == TradeSide.BUY)
    assert buy.trade_id == "EXEC0001"  # IBExecID, not a content hash


def test_parse_trades_falls_back_to_content_hash_without_ibexecid():
    rows = [{k: v for k, v in r.items() if k != "IBExecID"} for r in _trades_section()]
    _, trades, _ = _parse_trades(rows)
    buy = next(t for t in trades if t.instrument == "AAPL" and t.side == TradeSide.BUY)
    assert len(buy.trade_id) == 16  # synthetic content hash


def test_parse_trades_rejects_unknown_asset_class():
    rows = _trades_section()
    rows[0] = {**rows[0], "AssetClass": "FUT"}
    try:
        _parse_trades(rows)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "FUT" in str(e)
