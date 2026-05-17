from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount


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
