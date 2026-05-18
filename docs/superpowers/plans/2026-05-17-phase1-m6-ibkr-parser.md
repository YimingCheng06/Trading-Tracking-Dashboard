# Phase 1 M6 — IBKR Flex Query CSV Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse an IBKR Flex Query CSV (3 stacked sections — Trades, Corporate Actions, Cash Transactions) into the M2 `Ledger*` row models and append them, deduplicated, to an `AccountLedger`.

**Architecture:** One module `app/services/parsers/ibkr_flex.py`. Pure parsing functions map each CSV section to row models; `parse_flex_csv` assembles a `ParsedStatement`; `import_statement` appends to the four `LedgerTable`s. FX conversion for non-USD cash flows goes through the existing M4 `FxRateProvider`. No DB access — the M3 projection builder rebuilds the DB from the ledger separately.

**Tech Stack:** Python 3.12, stdlib `csv`/`hashlib`/`datetime`, Pydantic v2 row models, pytest (`asyncio_mode=auto`). Run tests with `cd backend && uv run --no-sync pytest`.

**Spec:** `docs/superpowers/specs/2026-05-17-phase1-m6-ibkr-parser-design.md`

---

## File Structure

- Create: `backend/app/services/parsers/ibkr_flex.py` — the whole parser (helpers, section parsers, `parse_flex_csv`, `import_statement`).
- Create: `backend/tests/fixtures/ibkr_flex_sample.csv` — synthetic redacted statement covering every case.
- Create: `backend/tests/test_ibkr_flex.py` — the test module.

`app/services/parsers/__init__.py` already exists (empty). The real `~/Downloads/Tracking.csv` is **never** committed — privacy.

---

## Task 1: Synthetic fixture + section splitter

**Files:**
- Create: `backend/tests/fixtures/ibkr_flex_sample.csv`
- Create: `backend/app/services/parsers/ibkr_flex.py`
- Test: `backend/tests/test_ibkr_flex.py`

- [ ] **Step 1: Create the synthetic fixture**

Create `backend/tests/fixtures/ibkr_flex_sample.csv` with exactly this content (3 stacked sections; account redacted to `U0000000`):

```
"ClientAccountID","CurrencyPrimary","AssetClass","Symbol","Strike","Expiry","DateTime","Put/Call","TradeDate","Quantity","TradePrice","TradeMoney","Taxes","NetCash","ClosePrice","CostBasis","FifoPnlRealized","OrigTradePrice","OrigTradeDate","Buy/Sell","OrderTime","OpenDateTime","ChangeInPrice","ChangeInQuantity","OrderType","IBCommission","IBCommissionCurrency","Conid","IBExecID"
"U0000000","USD","STK","AAPL","","","2026-01-05;10:00:00 EST","","2026-01-05","10","100","1000","0","-1001","100","1000","0","0","","BUY","2026-01-05;10:00:00 EST","","0","0","LMT","-1","USD","9999001","EXEC0001"
"U0000000","USD","STK","AAPL","","","2026-01-09;14:00:00 EST","","2026-01-09","-4","110","-440","0","439","110","-400","39","0","","SELL","2026-01-09;14:00:00 EST","","0","0","LMT","-1","USD","9999001","EXEC0002"
"U0000000","USD","OPT","AAPL  260116C00150000","150","2026-01-16","2026-01-06;11:00:00 EST","C","2026-01-06","2","3","600","0","-601","2.5","600","0","0","","BUY","2026-01-06;11:00:00 EST","","0","0","LMT","-1","USD","9999777","EXEC0003"
"U0000000","USD","OPT","AAPL  260116C00150000","150","2026-01-16","2026-01-08;12:00:00 EST","C","2026-01-08","-1","4","-400","0","399","3.8","-300","99","0","","SELL","2026-01-08;12:00:00 EST","","0","0","LMT","-1","USD","9999777","EXEC0004"
"U0000000","CAD","CASH","USD.CAD","","","2026-01-01;09:00:00 EST","","2026-01-01","100","1.4","140","0","0","0","0","0","0","","BUY","2026-01-01;09:00:00 EST","","0","0","MKT","0","","15016062","EXEC0005"
"U0000000","CAD","CASH","USD.CAD","","","2026-01-02;09:00:00 EST","","2026-01-02","100","1.5","150","0","0","0","0","0","0","","BUY","2026-01-02;09:00:00 EST","","0","0","MKT","0","","15016062","EXEC0006"
"U0000000","CAD","CASH","USD.CAD","","","2026-03-01;09:00:00 EST","","2026-03-01","100","1.25","125","0","0","0","0","0","0","","BUY","2026-03-01;09:00:00 EST","","0","0","MKT","0","","15016062","EXEC0007"
"ClientAccountID","CurrencyPrimary","Symbol","Strike","Expiry","Put/Call","Date/Time","Amount","Quantity","CostBasis","FifoPnlRealized","Conid"
"U0000000","USD","NEWX","","","","2026-02-01;20:25:00 EST","0","100","","0","8888001"
"U0000000","USD","OLDX.OLD","","","","2026-02-01;20:25:00 EST","0","-100","","0","8888002"
"ClientAccountID","AssetClass","Symbol","Conid","Strike","Expiry","Put/Call","Date/Time","SettleDate","AvailableForTradingDate","Amount","CurrencyPrimary","Type","DividendType"
"U0000000","","","","","","","2026-01-01","2026-01-01","2026-01-01","5000","CAD","Deposits/Withdrawals",""
"U0000000","","","","","","","2026-03-01","2026-03-01","","-200","CAD","Deposits/Withdrawals",""
"U0000000","","","","","","","2026-01-15;17:00:00 EST","2026-01-15","","-10","USD","Other Fees",""
"U0000000","","","","","","","2026-02-04","2026-02-04","","1.5","USD","Broker Interest Received",""
"U0000000","STK","AAPL","9999001","","","","2026-02-10;20:20:00 EST","2026-02-10","","5","USD","Dividends","Ordinary Dividend"
"U0000000","STK","AAPL","9999001","","","","2026-02-10;20:20:00 EST","2026-02-10","","-0.75","USD","Withholding Tax",""
```

Note: every CAD cash-flow date (2026-01-01, 2026-03-01) has a matching `USD.CAD` forex row, so the parser's statement FX rates cover them — tests run offline without hitting ECB.

- [ ] **Step 2: Write the failing test for `_split_sections`**

Create `backend/tests/test_ibkr_flex.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -v`
Expected: FAIL — `ImportError` / `cannot import name '_split_sections'`.

- [ ] **Step 4: Write the module header and `_split_sections`**

Create `backend/app/services/parsers/ibkr_flex.py`:

```python
"""Parse an IBKR Flex Query CSV into ledger row models.

A Flex export stacks three sections in one file — Trades, Corporate
Actions, Cash Transactions — each opening with its own header row whose
first cell is "ClientAccountID". `parse_flex_csv` splits the sections and
maps each to the M2 `Ledger*` row models; `import_statement` appends them
to an `AccountLedger`, deduplicated so re-importing a statement is a no-op.
No DB access — the M3 projection builder rebuilds the DB from the ledger.
"""


def _split_sections(
    rows: list[list[str]],
) -> list[tuple[list[str], list[list[str]]]]:
    """Split stacked CSV rows into (header, data_rows) groups.

    A header row is any row whose first cell is "ClientAccountID". Blank
    rows are dropped.
    """
    sections: list[tuple[list[str], list[list[str]]]] = []
    header: list[str] | None = None
    data: list[list[str]] = []
    for row in rows:
        if row and row[0] == "ClientAccountID":
            if header is not None:
                sections.append((header, data))
            header, data = row, []
        elif row:
            data.append(row)
    if header is not None:
        sections.append((header, data))
    return sections
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/fixtures/ibkr_flex_sample.csv backend/app/services/parsers/ibkr_flex.py backend/tests/test_ibkr_flex.py
git commit -m "M6: synthetic Flex fixture + CSV section splitter"
```

---

## Task 2: Parsing helpers

**Files:**
- Modify: `backend/app/services/parsers/ibkr_flex.py`
- Test: `backend/tests/test_ibkr_flex.py`

- [ ] **Step 1: Write failing tests for the helpers**

Add to `backend/tests/test_ibkr_flex.py`:

```python
from datetime import datetime
from decimal import Decimal

from app.services.parsers.ibkr_flex import _content_hash, _dec, _parse_dt


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -k "parse_dt or dec or content_hash" -v`
Expected: FAIL — `cannot import name`.

- [ ] **Step 3: Implement the helpers**

Add to `ibkr_flex.py` (imports at the top, helpers after `_split_sections`):

```python
import hashlib
from datetime import datetime
from decimal import Decimal


def _parse_dt(value: str) -> datetime:
    """Parse an IBKR datetime: '2026-03-26;15:30:58 EDT' or '2025-11-21'.

    The timezone abbreviation is dropped — every timestamp in a statement
    is US/Eastern wall-clock, so naive datetimes order correctly.
    """
    value = value.strip()
    if ";" in value:
        date_part, rest = value.split(";", 1)
        time_part = rest.strip().split(" ")[0]
        return datetime.fromisoformat(f"{date_part}T{time_part}")
    return datetime.fromisoformat(value)


def _dec(value: str | None) -> Decimal | None:
    """Parse a CSV cell to Decimal; blank/None becomes None."""
    if value is None or value.strip() == "":
        return None
    return Decimal(value.strip())


def _content_hash(*parts: object) -> str:
    """Stable 16-hex-char id from the given parts (synthetic row id)."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/parsers/ibkr_flex.py backend/tests/test_ibkr_flex.py
git commit -m "M6: datetime, decimal and content-hash parsing helpers"
```

---

## Task 3: Parse the Trades section

`_parse_trades` consumes the Trades section's row dicts and returns instruments, trades, and the statement FX rates harvested from forex (`CASH`) rows.

**Files:**
- Modify: `backend/app/services/parsers/ibkr_flex.py`
- Test: `backend/tests/test_ibkr_flex.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ibkr_flex.py`:

```python
import csv
from datetime import date

from app.db.enums import AssetClass, OptionType, TradeSide
from app.services.parsers.ibkr_flex import _parse_trades


def _trades_section():
    with FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    header, data = _split_sections(rows)[0]
    return [dict(zip(header, r)) for r in data]


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
        assert False, "expected ValueError"
    except ValueError as e:
        assert "FUT" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -k parse_trades -v`
Expected: FAIL — `cannot import name '_parse_trades'`.

- [ ] **Step 3: Implement `_parse_trades`**

Add to `ibkr_flex.py` (add `from datetime import date` to the datetime import; add the enum/model imports):

```python
from datetime import date, datetime

from app.db.enums import AssetClass, OptionType, TradeSide
from app.services.ledger.rows import LedgerInstrument, LedgerTrade

_ASSET_CLASS = {"STK": AssetClass.STOCK, "OPT": AssetClass.OPTION}
_OPTION_TYPE = {"P": OptionType.PUT, "C": OptionType.CALL}


def _parse_trades(
    rows: list[dict[str, str]],
) -> tuple[list[LedgerInstrument], list[LedgerTrade], dict[tuple[str, date], Decimal]]:
    """Map Trades-section rows to instruments + trades + statement FX rates.

    `CASH` rows are forex conversions: they yield no trade, only a
    {(currency, date): rate} entry (CAD->USD rate = 1 / USD.CAD price).
    Raises ValueError on an unknown AssetClass.
    """
    instruments: dict[str, LedgerInstrument] = {}
    trades: list[LedgerTrade] = []
    fx_rates: dict[tuple[str, date], Decimal] = {}

    for row in rows:
        asset = row["AssetClass"]
        if asset == "CASH":
            left, right = row["Symbol"].split(".")
            price = Decimal(row["TradePrice"])
            on = date.fromisoformat(row["TradeDate"])
            if left == "USD":
                fx_rates[(right, on)] = Decimal("1") / price
            elif right == "USD":
                fx_rates[(left, on)] = price
            continue
        if asset not in _ASSET_CLASS:
            raise ValueError(f"unknown trade AssetClass {asset!r}: {row}")
        asset_class = _ASSET_CLASS[asset]
        symbol = row["Symbol"]
        is_option = asset_class is AssetClass.OPTION
        instruments.setdefault(
            symbol,
            LedgerInstrument(
                symbol=symbol,
                asset_class=asset_class,
                currency=row["CurrencyPrimary"],
                conid=row["Conid"] or None,
                underlying_symbol=symbol.split()[0] if is_option else None,
                option_type=_OPTION_TYPE[row["Put/Call"]] if is_option else None,
                strike=_dec(row["Strike"]) if is_option else None,
                expiry=date.fromisoformat(row["Expiry"]) if is_option else None,
                multiplier=100 if is_option else 1,
            ),
        )
        proceeds = abs(Decimal(row["TradeMoney"]))
        commission = abs(_dec(row["IBCommission"]) or Decimal("0"))
        trades.append(
            LedgerTrade(
                trade_id=row.get("IBExecID")
                or _content_hash(
                    row["Conid"], row["DateTime"], row["Quantity"],
                    row["TradePrice"], row["TradeMoney"], row["IBCommission"],
                ),
                instrument=symbol,
                side=TradeSide.BUY if row["Buy/Sell"] == "BUY" else TradeSide.SELL,
                quantity=abs(Decimal(row["Quantity"])),
                price=Decimal(row["TradePrice"]),
                currency=row["CurrencyPrimary"],
                fx_rate_to_usd=Decimal("1"),
                proceeds_orig=proceeds,
                proceeds_usd=proceeds,
                commission_orig=commission,
                commission_usd=commission,
                realized_pnl_ibkr=_dec(row["FifoPnlRealized"]),
                executed_at=_parse_dt(row["DateTime"]),
            )
        )
    return list(instruments.values()), trades, fx_rates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/parsers/ibkr_flex.py backend/tests/test_ibkr_flex.py
git commit -m "M6: parse Trades section to instruments, trades and FX rates"
```

---

## Task 4: Parse the Cash Transactions section

**Files:**
- Modify: `backend/app/services/parsers/ibkr_flex.py`
- Test: `backend/tests/test_ibkr_flex.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ibkr_flex.py`:

```python
from app.db.enums import CashFlowType
from app.services.fx.provider import StatementFxProvider
from app.services.parsers.ibkr_flex import _parse_cash


def _cash_section():
    with FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    header, data = _split_sections(rows)[2]
    return [dict(zip(header, r)) for r in data]


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
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Mystery" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -k parse_cash -v`
Expected: FAIL — `cannot import name '_parse_cash'`.

- [ ] **Step 3: Implement `_parse_cash`**

Add to `ibkr_flex.py` (add imports for `CashFlowType`, `LedgerCashFlow`, `FxRateProvider`, `convert_to_usd`):

```python
from app.db.enums import AssetClass, CashFlowType, OptionType, TradeSide
from app.services.fx.provider import FxRateProvider, convert_to_usd
from app.services.ledger.rows import LedgerCashFlow, LedgerInstrument, LedgerTrade

# Cash Transaction `Type` -> CashFlowType. "Deposits/Withdrawals" is
# sign-dependent and handled separately. "Withholding Tax" maps to OTHER:
# CashFlowType.TAX was removed from scope; OTHER keeps the cash balance
# correct and the description preserves the original label.
_CASH_TYPE = {
    "Other Fees": CashFlowType.FEE,
    "Broker Interest Received": CashFlowType.INTEREST,
    "Dividends": CashFlowType.DIVIDEND,
    "Withholding Tax": CashFlowType.OTHER,
}


def _parse_cash(
    rows: list[dict[str, str]], fx_provider: FxRateProvider
) -> list[LedgerCashFlow]:
    """Map Cash Transactions rows to LedgerCashFlow.

    Non-USD amounts are converted to USD via `fx_provider`. Raises
    ValueError on an unknown `Type`.
    """
    flows: list[LedgerCashFlow] = []
    for row in rows:
        type_label = row["Type"]
        amount = Decimal(row["Amount"])
        if type_label == "Deposits/Withdrawals":
            flow_type = (
                CashFlowType.DEPOSIT if amount > 0 else CashFlowType.WITHDRAWAL
            )
        elif type_label in _CASH_TYPE:
            flow_type = _CASH_TYPE[type_label]
        else:
            raise ValueError(f"unknown cash Type {type_label!r}: {row}")

        currency = row["CurrencyPrimary"]
        occurred_at = _parse_dt(row["Date/Time"])
        if currency == "USD":
            rate = Decimal("1")
        else:
            rate = fx_provider.get_rate(currency, occurred_at.date())
            if rate is None:
                raise ValueError(
                    f"no FX rate for {currency} on {occurred_at.date()}"
                )
        flows.append(
            LedgerCashFlow(
                flow_type=flow_type,
                instrument=row["Symbol"] or None,
                currency=currency,
                fx_rate_to_usd=rate,
                amount_orig=amount,
                amount_usd=amount * rate,
                description=type_label,
                external_id=_content_hash(
                    type_label, row["Date/Time"], row["Amount"], row["Symbol"]
                ),
                occurred_at=occurred_at,
            )
        )
    return flows
```

(`convert_to_usd` is imported for parity with the M4 API but `_parse_cash` computes `amount * rate` inline since it already holds the rate; the import may be dropped if the spec reviewer prefers — keep the code minimal.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/parsers/ibkr_flex.py backend/tests/test_ibkr_flex.py
git commit -m "M6: parse Cash Transactions section to cash flows"
```

---

## Task 5: Parse the Corporate Actions section

**Files:**
- Modify: `backend/app/services/parsers/ibkr_flex.py`
- Test: `backend/tests/test_ibkr_flex.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ibkr_flex.py`:

```python
from app.db.enums import CorporateActionType
from app.services.parsers.ibkr_flex import _parse_corp


def _corp_section():
    with FIXTURE.open(newline="") as f:
        rows = list(csv.reader(f))
    header, data = _split_sections(rows)[1]
    return [dict(zip(header, r)) for r in data]


def test_parse_corp_pairs_symbol_change():
    actions = _parse_corp(_corp_section())
    assert len(actions) == 1
    action = actions[0]
    assert action.action_type is CorporateActionType.SYMBOL_CHANGE
    assert action.instrument == "NEWX"
    assert action.ex_date == date(2026, 2, 1)
    assert action.ratio == Decimal("1")
    assert "OLDX.OLD" in action.description and "NEWX" in action.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -k parse_corp -v`
Expected: FAIL — `cannot import name '_parse_corp'`.

- [ ] **Step 3: Implement `_parse_corp`**

Add to `ibkr_flex.py` (add `CorporateActionType` to the enum import, `LedgerCorporateAction` to the rows import):

```python
def _parse_corp(rows: list[dict[str, str]]) -> list[LedgerCorporateAction]:
    """Map Corporate Actions rows to LedgerCorporateAction.

    Rows sharing a Date/Time form one event. The supported pattern is a
    symbol change: a `<ticker>.OLD` row (negative quantity) paired with
    the new ticker (positive quantity). Raises ValueError on any other
    shape — unrecognised corporate actions are surfaced, not guessed.
    """
    by_time: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_time.setdefault(row["Date/Time"], []).append(row)

    actions: list[LedgerCorporateAction] = []
    for when, group in by_time.items():
        old = [r for r in group if r["Symbol"].endswith(".OLD")]
        new = [r for r in group if not r["Symbol"].endswith(".OLD")]
        if len(old) != 1 or len(new) != 1:
            raise ValueError(f"unrecognised corporate action group: {group}")
        old_row, new_row = old[0], new[0]
        old_qty = abs(Decimal(old_row["Quantity"]))
        new_qty = abs(Decimal(new_row["Quantity"]))
        actions.append(
            LedgerCorporateAction(
                instrument=new_row["Symbol"],
                action_type=CorporateActionType.SYMBOL_CHANGE,
                ex_date=_parse_dt(when).date(),
                ratio=new_qty / old_qty,
                description=(
                    f"{old_row['Symbol']} → {new_row['Symbol']} "
                    f"({old_qty}:{new_qty})"
                ),
                external_id=_content_hash(
                    old_row["Symbol"], new_row["Symbol"], when
                ),
            )
        )
    return actions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/parsers/ibkr_flex.py backend/tests/test_ibkr_flex.py
git commit -m "M6: parse Corporate Actions section to symbol-change events"
```

---

## Task 6: `parse_flex_csv` — assemble the ParsedStatement

**Files:**
- Modify: `backend/app/services/parsers/ibkr_flex.py`
- Test: `backend/tests/test_ibkr_flex.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ibkr_flex.py`:

```python
from app.services.fx.provider import ChainedFxProvider
from app.services.parsers.ibkr_flex import ParsedStatement, parse_flex_csv


def test_parse_flex_csv_assembles_everything():
    parsed = parse_flex_csv(FIXTURE)
    assert isinstance(parsed, ParsedStatement)
    assert parsed.account_id == "U0000000"
    assert len(parsed.instruments) == 2          # AAPL stock + AAPL option
    assert len(parsed.trades) == 4               # 2 stock + 2 option (no CASH)
    assert len(parsed.cash_flows) == 6
    assert len(parsed.corporate_actions) == 1


def test_parse_flex_csv_uses_harvested_forex_rates_offline():
    # No fx_provider passed: forex rows in the fixture cover every CAD
    # cash-flow date, so this resolves with no network call.
    parsed = parse_flex_csv(FIXTURE)
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
    parsed = parse_flex_csv(FIXTURE, fx_provider=provider)
    deposit = next(
        f for f in parsed.cash_flows if f.amount_orig == Decimal("5000")
    )
    assert deposit.fx_rate_to_usd == Decimal("0.5")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -k parse_flex_csv -v`
Expected: FAIL — `cannot import name 'parse_flex_csv'`.

- [ ] **Step 3: Implement `ParsedStatement` and `parse_flex_csv`**

Add to `ibkr_flex.py` (add `import csv`, `from dataclasses import dataclass`, `from pathlib import Path`, and `from app.services.fx.factory import build_fx_provider`):

```python
import csv
from dataclasses import dataclass
from pathlib import Path

from app.services.fx.factory import build_fx_provider


@dataclass(frozen=True)
class ParsedStatement:
    account_id: str
    instruments: list[LedgerInstrument]
    trades: list[LedgerTrade]
    cash_flows: list[LedgerCashFlow]
    corporate_actions: list[LedgerCorporateAction]


def parse_flex_csv(
    path: Path, *, fx_provider: FxRateProvider | None = None
) -> ParsedStatement:
    """Parse an IBKR Flex Query CSV into a ParsedStatement.

    `fx_provider` overrides FX resolution (used by tests to stay offline).
    When omitted, the provider chains the statement's own forex rates
    first, then ECB rates — see `build_fx_provider`.
    """
    with path.open(newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"{path} is empty")
    account_id = rows[1][0] if len(rows) > 1 else ""

    trades_rows: list[dict[str, str]] = []
    cash_rows: list[dict[str, str]] = []
    corp_rows: list[dict[str, str]] = []
    for header, data in _split_sections(rows):
        dicts = [dict(zip(header, r)) for r in data]
        if "Buy/Sell" in header:
            trades_rows = dicts
        elif "Type" in header:
            cash_rows = dicts
        else:
            corp_rows = dicts

    instruments, trades, statement_rates = _parse_trades(trades_rows)
    provider = fx_provider or build_fx_provider(statement_rates)
    cash_flows = _parse_cash(cash_rows, provider)
    corporate_actions = _parse_corp(corp_rows)
    return ParsedStatement(
        account_id=account_id,
        instruments=instruments,
        trades=trades,
        cash_flows=cash_flows,
        corporate_actions=corporate_actions,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/parsers/ibkr_flex.py backend/tests/test_ibkr_flex.py
git commit -m "M6: parse_flex_csv assembles the full ParsedStatement"
```

---

## Task 7: `import_statement` — append to the ledger, idempotently

**Files:**
- Modify: `backend/app/services/parsers/ibkr_flex.py`
- Test: `backend/tests/test_ibkr_flex.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ibkr_flex.py`:

```python
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount
from app.services.parsers.ibkr_flex import ImportReport, import_statement


def test_import_statement_appends_all_tables(tmp_path):
    ledger = AccountLedger.create(
        tmp_path,
        LedgerAccount(
            broker_account_id="U0000000", name="Test", base_currency="USD"
        ),
    )
    report = import_statement(FIXTURE, ledger, fx_provider=_FX)
    assert isinstance(report, ImportReport)
    assert report.trades.added == 4
    assert report.instruments.added == 2
    assert report.cash_flows.added == 6
    assert report.corporate_actions.added == 1
    assert len(ledger.trades.read()) == 4


def test_import_statement_is_idempotent(tmp_path):
    ledger = AccountLedger.create(
        tmp_path,
        LedgerAccount(
            broker_account_id="U0000000", name="Test", base_currency="USD"
        ),
    )
    import_statement(FIXTURE, ledger, fx_provider=_FX)
    report = import_statement(FIXTURE, ledger, fx_provider=_FX)
    assert report.trades.added == 0
    assert report.cash_flows.added == 0
    assert report.corporate_actions.added == 0
    assert len(ledger.trades.read()) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run --no-sync pytest tests/test_ibkr_flex.py -k import_statement -v`
Expected: FAIL — `cannot import name 'import_statement'`.

- [ ] **Step 3: Implement `ImportReport` and `import_statement`**

Add to `ibkr_flex.py` (add `from app.services.ledger.account_ledger import AccountLedger` and `from app.services.ledger.table import AppendReport`):

```python
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.table import AppendReport


@dataclass(frozen=True)
class ImportReport:
    instruments: AppendReport
    trades: AppendReport
    cash_flows: AppendReport
    corporate_actions: AppendReport


def import_statement(
    path: Path,
    ledger: AccountLedger,
    *,
    fx_provider: FxRateProvider | None = None,
) -> ImportReport:
    """Parse a Flex CSV and append every row to `ledger`.

    Each `LedgerTable.append` deduplicates on the row's `dedup_key`, so
    re-importing the same statement adds nothing and never overwrites a
    row the user edited by hand.
    """
    parsed = parse_flex_csv(path, fx_provider=fx_provider)
    return ImportReport(
        instruments=ledger.instruments.append(parsed.instruments),
        trades=ledger.trades.append(parsed.trades),
        cash_flows=ledger.cash_flows.append(parsed.cash_flows),
        corporate_actions=ledger.corporate_actions.append(
            parsed.corporate_actions
        ),
    )
```

- [ ] **Step 4: Run the full suite**

Run: `cd backend && uv run --no-sync pytest -q`
Expected: PASS — all M6 tests plus the existing 99 tests (110 total).

- [ ] **Step 5: Lint**

Run: `cd backend && uv run --no-sync ruff check app/services/parsers/ tests/test_ibkr_flex.py`
Expected: no errors. Fix any (line length 100; rules E,F,I,N,UP,B,SIM).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/parsers/ibkr_flex.py backend/tests/test_ibkr_flex.py
git commit -m "M6: import_statement appends a parsed Flex CSV to the ledger"
```

---

## Self-Review Notes

- **Spec coverage:** Task 3 covers Trades + forex; Task 4 Cash Transactions + the Type table incl. Withholding Tax→OTHER; Task 5 Corporate Actions; Tasks 6-7 assembly + idempotent import. Every spec section maps to a task.
- **trade_id:** `IBExecID` (IBKR's globally-unique execution id) when the column is present — the reliable key for de-duplicating a trade that appears in two overlapping daily statements. Falls back to a content hash only when `IBExecID` is absent.
- **FX:** non-USD cash flows convert via the M4 provider; the fixture's forex rows make the happy path offline; tests also inject a provider.
- **Privacy:** the real `Tracking.csv` is never added to git; only the synthetic fixture is.
- **Out of scope (do NOT add):** non-USD stock/option trades (sample has none — trades are USD, `fx_rate_to_usd=1`); FIFO cost-basis carry-over across a symbol change (engine work); corporate-action shapes other than symbol change (raise ValueError).
