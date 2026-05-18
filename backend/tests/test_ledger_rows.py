from datetime import date, datetime
from decimal import Decimal

from app.db.enums import (
    AssetClass,
    CashFlowType,
    CorporateActionType,
    OptionType,
    RecordSource,
    TradeSide,
)
from app.services.ledger import rows


def test_trade_defaults_and_dedup_key():
    t = rows.LedgerTrade(
        trade_id="EXEC-1",
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
    assert t.source == RecordSource.PARSED
    assert t.import_batch is None
    assert t.commission_orig == Decimal("0")
    assert t.dedup_key == ("EXEC-1",)


def test_instrument_dedup_key_includes_option_fields():
    opt = rows.LedgerInstrument(
        symbol="AAPL 250117C00200000",
        asset_class=AssetClass.OPTION,
        currency="USD",
        option_type=OptionType.CALL,
        strike=Decimal("200"),
        expiry=date(2025, 1, 17),
    )
    assert opt.multiplier == 1
    assert opt.dedup_key == (
        "AAPL 250117C00200000",
        AssetClass.OPTION,
        Decimal("200"),
        date(2025, 1, 17),
        OptionType.CALL,
    )


def test_cash_flow_dedup_key_prefers_external_id():
    with_id = rows.LedgerCashFlow(
        flow_type=CashFlowType.DIVIDEND,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("22"),
        amount_usd=Decimal("22"),
        external_id="DIV-9",
        occurred_at=datetime(2026, 2, 14),
    )
    assert with_id.dedup_key == ("DIV-9",)


def test_cash_flow_dedup_key_falls_back_to_content_hash():
    no_id = rows.LedgerCashFlow(
        flow_type=CashFlowType.DEPOSIT,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("5000"),
        amount_usd=Decimal("5000"),
        occurred_at=datetime(2026, 1, 1),
    )
    assert no_id.dedup_key == (
        CashFlowType.DEPOSIT,
        datetime(2026, 1, 1),
        Decimal("5000"),
    )


def test_corporate_action_dedup_key():
    ca = rows.LedgerCorporateAction(
        instrument="AAPL",
        action_type=CorporateActionType.SPLIT,
        ex_date=date(2024, 6, 10),
        ratio=Decimal("10"),
    )
    assert ca.dedup_key == ("AAPL", CorporateActionType.SPLIT, date(2024, 6, 10))


def test_corporate_action_dedup_key_prefers_external_id():
    ca = rows.LedgerCorporateAction(
        instrument="AAPL",
        action_type=CorporateActionType.SPLIT,
        ex_date=date(2024, 6, 10),
        ratio=Decimal("10"),
        external_id="ACT-42",
    )
    assert ca.dedup_key == ("ACT-42",)


def test_account_model():
    acct = rows.LedgerAccount(
        broker_account_id="U1", name="Main", base_currency="USD"
    )
    assert acct.broker == "IBKR"


def test_cash_flow_dedup_key_uses_nonempty_falsy_id():
    """A non-empty id like "0" must still be used, not treated as absent."""
    cf = rows.LedgerCashFlow(
        flow_type=CashFlowType.DEPOSIT,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("5000"),
        amount_usd=Decimal("5000"),
        external_id="0",
        occurred_at=datetime(2026, 1, 1),
    )
    assert cf.dedup_key == ("0",)


def test_cash_flow_dedup_key_treats_empty_id_as_absent():
    """An empty-string external_id falls back to the content key."""
    cf = rows.LedgerCashFlow(
        flow_type=CashFlowType.DEPOSIT,
        currency="USD",
        fx_rate_to_usd=Decimal("1.0"),
        amount_orig=Decimal("5000"),
        amount_usd=Decimal("5000"),
        external_id="",
        occurred_at=datetime(2026, 1, 1),
    )
    assert cf.dedup_key == (CashFlowType.DEPOSIT, datetime(2026, 1, 1), Decimal("5000"))
