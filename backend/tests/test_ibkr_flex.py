import csv
from pathlib import Path

from app.services.parsers.ibkr_flex import _split_sections

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
