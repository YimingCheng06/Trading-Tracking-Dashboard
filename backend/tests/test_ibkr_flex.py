import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.db.enums import AssetClass, CashFlowType, CorporateActionType, OptionType, TradeSide
from app.services.fx.provider import StatementFxProvider
from app.services.ledger.account_ledger import AccountLedger
from app.services.parsers.ibkr_flex import (
    ImportReport,
    ParsedStatement,
    _content_hash,
    _dec,
    _parse_cash,
    _parse_corp,
    _parse_dt,
    _parse_trades,
    _split_sections,
    import_statement,
    parse_flex_csv,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ibkr_flex_sample.csv"
MULTI = Path(__file__).parent / "fixtures" / "ibkr_flex_multi_account.csv"


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


def test_parse_trades_forex_pair_with_usd_as_quote():
    # A `CAD.USD`-style pair (USD on the right leg) yields the price directly.
    cash = next(r for r in _trades_section() if r["AssetClass"] == "CASH")
    cash = {**cash, "Symbol": "CAD.USD"}
    _, _, fx = _parse_trades([cash])
    on = date.fromisoformat(cash["TradeDate"])
    assert fx[("CAD", on)] == Decimal(cash["TradePrice"])


def test_parse_trades_rejects_forex_pair_without_usd():
    cash = next(r for r in _trades_section() if r["AssetClass"] == "CASH")
    cash = {**cash, "Symbol": "EUR.CAD"}
    try:
        _parse_trades([cash])
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "USD" in str(e)


# ---------------------------------------------------------------------------
# Task 4: _parse_cash
# ---------------------------------------------------------------------------


def _cash_section():
    with FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    header, data = _split_sections(rows)[2]
    return [dict(zip(header, r, strict=False)) for r in data]


# CAD rates the fixture's forex rows would give: 1/1.4 on 2026-01-01, 1/1.25 on 2026-03-01
_FX = StatementFxProvider(
    {
        ("CAD", date(2026, 1, 1)): Decimal("1") / Decimal("1.4"),
        ("CAD", date(2026, 3, 1)): Decimal("1") / Decimal("1.25"),
    }
)


def test_parse_cash_deposit_and_withdrawal_by_sign():
    flows = _parse_cash(_cash_section(), _FX)
    deposit = next(f for f in flows if f.amount_orig == Decimal("5000"))
    assert deposit.flow_type is CashFlowType.DEPOSIT
    withdrawal = next(f for f in flows if f.amount_orig == Decimal("-200"))
    assert withdrawal.flow_type is CashFlowType.WITHDRAWAL


def test_parse_cash_converts_cad_to_usd():
    flows = _parse_cash(_cash_section(), _FX)
    deposit = next(f for f in flows if f.amount_orig == Decimal("5000"))
    assert deposit.currency == "CAD"
    assert deposit.fx_rate_to_usd == Decimal("1") / Decimal("1.4")
    assert deposit.amount_usd == Decimal("5000") * (Decimal("1") / Decimal("1.4"))


def test_parse_cash_type_mapping():
    flows = _parse_cash(_cash_section(), _FX)
    by_type = {f.description: f.flow_type for f in flows}
    assert by_type["Other Fees"] is CashFlowType.FEE
    assert by_type["Broker Interest Received"] is CashFlowType.INTEREST
    assert by_type["Dividends"] is CashFlowType.DIVIDEND
    assert by_type["Withholding Tax"] is CashFlowType.OTHER


def test_parse_cash_usd_rows_have_rate_one():
    flows = _parse_cash(_cash_section(), _FX)
    fee = next(f for f in flows if f.description == "Other Fees")
    assert fee.fx_rate_to_usd == Decimal("1")
    assert fee.amount_usd == Decimal("-10")


def test_parse_cash_rejects_unknown_type():
    rows = _cash_section()
    rows[0] = {**rows[0], "Type": "Mystery"}
    try:
        _parse_cash(rows, _FX)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "Mystery" in str(e)


# ---------------------------------------------------------------------------
# Task 5: _parse_corp
# ---------------------------------------------------------------------------


def _corp_section():
    with FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    header, data = _split_sections(rows)[1]
    return [dict(zip(header, r, strict=False)) for r in data]


def test_parse_corp_pairs_symbol_change():
    actions = _parse_corp(_corp_section())
    assert len(actions) == 1
    action = actions[0]
    assert action.action_type is CorporateActionType.SYMBOL_CHANGE
    assert action.instrument == "NEWX"
    assert action.ex_date == date(2026, 2, 1)
    assert action.ratio == Decimal("1")
    assert "OLDX.OLD" in action.description and "NEWX" in action.description


def test_parse_corp_rejects_unrecognised_group():
    rows = _corp_section()
    # Duplicate the .OLD row → a 2-.OLD / 1-new group, which is not a
    # recognised symbol-change pair.
    rows.append(dict(next(r for r in rows if r["Symbol"].endswith(".OLD"))))
    try:
        _parse_corp(rows)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "corporate action" in str(e)


# ---------------------------------------------------------------------------
# Task 6: parse_flex_csv / ParsedStatement
# ---------------------------------------------------------------------------


def test_parse_flex_csv_assembles_everything():
    statements = parse_flex_csv(FIXTURE)
    assert len(statements) == 1
    parsed = statements[0]
    assert isinstance(parsed, ParsedStatement)
    assert parsed.account_id == "U0000000"
    assert len(parsed.instruments) == 2          # AAPL stock + AAPL option
    assert len(parsed.trades) == 4               # 2 stock + 2 option (no CASH)
    assert len(parsed.cash_flows) == 6
    assert len(parsed.corporate_actions) == 1


def test_parse_flex_csv_uses_harvested_forex_rates_offline():
    # No fx_provider passed: forex rows in the fixture cover every CAD
    # cash-flow date, so this resolves with no network call.
    parsed = parse_flex_csv(FIXTURE)[0]
    deposit = next(
        f for f in parsed.cash_flows if f.amount_orig == Decimal("5000")
    )
    assert deposit.fx_rate_to_usd == Decimal("1") / Decimal("1.4")


def test_parse_flex_csv_accepts_injected_provider():
    provider = StatementFxProvider(
        {
            ("CAD", date(2026, 1, 1)): Decimal("0.5"),
            ("CAD", date(2026, 3, 1)): Decimal("0.5"),
        }
    )
    parsed = parse_flex_csv(FIXTURE, fx_provider=provider)[0]
    deposit = next(
        f for f in parsed.cash_flows if f.amount_orig == Decimal("5000")
    )
    assert deposit.fx_rate_to_usd == Decimal("0.5")


def test_parse_flex_csv_splits_multiple_accounts():
    statements = parse_flex_csv(MULTI)
    assert [s.account_id for s in statements] == ["U0000001", "U0000002"]


def test_parse_flex_csv_accumulates_repeated_sections():
    # U0000001's trades come from two separate Trades sections — both
    # must survive (rows accumulate, the later section does not overwrite).
    s1 = parse_flex_csv(MULTI)[0]
    assert {t.trade_id for t in s1.trades} == {"EXEC-A1", "EXEC-A2"}


def test_parse_flex_csv_per_account_contents():
    s1, s2 = parse_flex_csv(MULTI)
    assert len(s1.trades) == 2
    assert len(s1.cash_flows) == 1
    assert len(s1.corporate_actions) == 1
    assert len(s2.trades) == 1
    assert s2.corporate_actions == []


def test_parse_cash_uses_transaction_id_as_external_id():
    s1 = parse_flex_csv(MULTI)[0]
    assert s1.cash_flows[0].external_id == "TXN-D1"


def test_parse_corp_uses_action_id_as_external_id():
    s1 = parse_flex_csv(MULTI)[0]
    assert s1.corporate_actions[0].external_id == "ACT-1"


# ---------------------------------------------------------------------------
# Task 7: import_statement / ImportReport
# ---------------------------------------------------------------------------


def test_import_statement_appends_all_tables(tmp_path):
    reports = import_statement(FIXTURE, tmp_path, fx_provider=_FX)
    assert set(reports) == {"U0000000"}
    report = reports["U0000000"]
    assert isinstance(report, ImportReport)
    assert report.trades.added == 4
    assert report.instruments.added == 2
    assert report.cash_flows.added == 6
    assert report.corporate_actions.added == 1
    assert len(AccountLedger(tmp_path / "U0000000").trades.read()) == 4


def test_import_statement_is_idempotent(tmp_path):
    import_statement(FIXTURE, tmp_path, fx_provider=_FX)
    reports = import_statement(FIXTURE, tmp_path, fx_provider=_FX)
    assert reports["U0000000"].trades.added == 0
    assert reports["U0000000"].cash_flows.added == 0
    assert reports["U0000000"].corporate_actions.added == 0
    assert len(AccountLedger(tmp_path / "U0000000").trades.read()) == 4


def test_import_statement_routes_each_account_to_its_own_ledger(tmp_path):
    reports = import_statement(MULTI, tmp_path)
    assert set(reports) == {"U0000001", "U0000002"}
    assert reports["U0000001"].trades.added == 2
    assert reports["U0000002"].trades.added == 1
    # Each account got its own ledger directory, auto-created with account.toml.
    assert (tmp_path / "U0000001" / "account.toml").exists()
    assert (tmp_path / "U0000002" / "account.toml").exists()
    assert len(AccountLedger(tmp_path / "U0000001").trades.read()) == 2
    assert len(AccountLedger(tmp_path / "U0000002").trades.read()) == 1
