from datetime import datetime
from decimal import Decimal

from app.db.enums import TradeSide
from app.services.ledger.rows import LedgerTrade
from app.services.ledger.table import LedgerTable


def _trade(trade_id: str, **kw) -> LedgerTrade:
    fields = dict(
        trade_id=trade_id,
        instrument="AAPL",
        side=TradeSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("150.25"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds_orig=Decimal("-1502.50"),
        proceeds_usd=Decimal("-1502.50"),
        executed_at=datetime(2026, 1, 5, 14, 30),
    )
    fields.update(kw)
    return LedgerTrade(**fields)


def test_read_missing_file_returns_empty(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    assert table.read() == []


def test_append_then_read_round_trips(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    report = table.append([_trade("EXEC-1"), _trade("EXEC-2")])

    assert (report.added, report.skipped) == (2, 0)
    rows = table.read()
    assert [r.trade_id for r in rows] == ["EXEC-1", "EXEC-2"]
    assert rows[0].quantity == Decimal("10")
    assert rows[0].executed_at == datetime(2026, 1, 5, 14, 30)
    assert rows[0].open_close is None
    assert rows[0].realized_pnl_ibkr is None


def test_append_skips_keys_already_in_file(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    table.append([_trade("EXEC-1")])
    report = table.append([_trade("EXEC-1"), _trade("EXEC-3")])

    assert (report.added, report.skipped) == (1, 1)
    assert [r.trade_id for r in table.read()] == ["EXEC-1", "EXEC-3"]


def test_append_dedups_within_one_batch(tmp_path):
    table = LedgerTable(tmp_path / "trades.csv", LedgerTrade)
    report = table.append([_trade("EXEC-9"), _trade("EXEC-9")])

    assert (report.added, report.skipped) == (1, 1)
    assert len(table.read()) == 1


def test_csv_has_provenance_columns_first(tmp_path):
    path = tmp_path / "trades.csv"
    LedgerTable(path, LedgerTrade).append([_trade("EXEC-1")])
    header = path.read_text().splitlines()[0]
    assert header.startswith("source,import_batch,trade_id,")
