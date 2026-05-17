from datetime import datetime
from decimal import Decimal

from app.db.enums import CashFlowType, TradeSide
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount, LedgerCashFlow, LedgerTrade


def test_create_writes_account_toml_and_dir(tmp_path):
    acct = LedgerAccount(
        broker_account_id="U1234567", name="Main", base_currency="USD"
    )
    ledger = AccountLedger.create(tmp_path, acct)

    assert ledger.root == tmp_path / "U1234567"
    assert (ledger.root / "account.toml").exists()


def test_create_then_read_account_round_trips(tmp_path):
    acct = LedgerAccount(
        broker_account_id="U1234567",
        name="Roth IRA",
        base_currency="USD",
        broker="IBKR",
    )
    AccountLedger.create(tmp_path, acct)

    reloaded = AccountLedger(tmp_path / "U1234567").read_account()
    assert reloaded == acct


def test_exposes_four_named_tables(tmp_path):
    ledger = AccountLedger(tmp_path / "U1")
    assert ledger.instruments.path == tmp_path / "U1" / "instruments.csv"
    assert ledger.trades.path == tmp_path / "U1" / "trades.csv"
    assert ledger.cash_flows.path == tmp_path / "U1" / "cash_flows.csv"
    assert (
        ledger.corporate_actions.path
        == tmp_path / "U1" / "corporate_actions.csv"
    )


def test_account_name_with_special_chars_round_trips(tmp_path):
    acct = LedgerAccount(
        broker_account_id="U9",
        name='My "Pro" \\ Account',
        base_currency="USD",
    )
    AccountLedger.create(tmp_path, acct)

    reloaded = AccountLedger(tmp_path / "U9").read_account()
    assert reloaded.name == 'My "Pro" \\ Account'


def test_full_ledger_workflow(tmp_path):
    acct = LedgerAccount(
        broker_account_id="U777", name="Main", base_currency="USD"
    )
    ledger = AccountLedger.create(tmp_path, acct)

    trade = LedgerTrade(
        trade_id="T1",
        instrument="AAPL",
        side=TradeSide.BUY,
        quantity=Decimal("5"),
        price=Decimal("100"),
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        proceeds_orig=Decimal("-500"),
        proceeds_usd=Decimal("-500"),
        executed_at=datetime(2026, 1, 2, 10, 0),
        import_batch="batch-1",
    )
    deposit = LedgerCashFlow(
        flow_type=CashFlowType.DEPOSIT,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("5000"),
        amount_usd=Decimal("5000"),
        occurred_at=datetime(2026, 1, 1, 0, 0),
        import_batch="batch-1",
    )

    assert ledger.trades.append([trade]).added == 1
    assert ledger.cash_flows.append([deposit]).added == 1

    # Re-importing the same statement adds nothing.
    second = ledger.trades.append([trade])
    assert (second.added, second.skipped) == (0, 1)

    read_trade = ledger.trades.read()[0]
    assert read_trade.trade_id == "T1"
    assert read_trade.import_batch == "batch-1"
    assert read_trade.proceeds_usd == Decimal("-500")
    assert ledger.cash_flows.read()[0].amount_usd == Decimal("5000")
