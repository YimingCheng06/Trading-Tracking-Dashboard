"""One account's CSV ledger directory: 4 record tables + account.toml.

account.toml holds four flat string keys, so it is written by hand (the
standard library has a TOML reader but no writer) and read with tomllib.
"""

import tomllib
from pathlib import Path

from app.services.ledger.rows import (
    LedgerAccount,
    LedgerCashFlow,
    LedgerCorporateAction,
    LedgerInstrument,
    LedgerTrade,
)
from app.services.ledger.table import LedgerTable


class AccountLedger:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.instruments: LedgerTable[LedgerInstrument] = LedgerTable(
            root / "instruments.csv", LedgerInstrument
        )
        self.trades: LedgerTable[LedgerTrade] = LedgerTable(
            root / "trades.csv", LedgerTrade
        )
        self.cash_flows: LedgerTable[LedgerCashFlow] = LedgerTable(
            root / "cash_flows.csv", LedgerCashFlow
        )
        self.corporate_actions: LedgerTable[LedgerCorporateAction] = LedgerTable(
            root / "corporate_actions.csv", LedgerCorporateAction
        )

    @classmethod
    def create(cls, accounts_dir: Path, account: LedgerAccount) -> "AccountLedger":
        root = accounts_dir / account.broker_account_id
        root.mkdir(parents=True, exist_ok=True)
        lines = [
            f'broker_account_id = "{account.broker_account_id}"',
            f'name = "{account.name}"',
            f'base_currency = "{account.base_currency}"',
            f'broker = "{account.broker}"',
        ]
        (root / "account.toml").write_text("\n".join(lines) + "\n")
        return cls(root)

    def read_account(self) -> LedgerAccount:
        with (self.root / "account.toml").open("rb") as f:
            return LedgerAccount.model_validate(tomllib.load(f))
