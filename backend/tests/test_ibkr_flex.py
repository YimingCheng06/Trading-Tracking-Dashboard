import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.services.parsers.ibkr_flex import _content_hash, _dec, _parse_dt, _split_sections

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
