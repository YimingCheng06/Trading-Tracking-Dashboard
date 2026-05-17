"""Rebuild the SQLite DB projection from one account's CSV ledger.

The ledger is the source of truth; the DB is a disposable query projection.
`rebuild_account` is a full rebuild of one account: account-scoped tables
(trades, cash_flows) are deleted and re-inserted, while global tables
(instruments, corporate_actions) are upserted by their natural key.
positions_snapshot is NOT projected here — it is derived from market data
in a later milestone.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Account, CashFlow, CorporateAction, Instrument, Trade
from app.services.ledger.account_ledger import AccountLedger
from app.services.ledger.rows import LedgerAccount, LedgerInstrument


def upsert_account(session: Session, ledger_account: LedgerAccount) -> Account:
    """Find the Account by broker_account_id, or create it; update its fields."""
    account = session.scalar(
        select(Account).where(
            Account.broker_account_id == ledger_account.broker_account_id
        )
    )
    if account is None:
        account = Account(broker_account_id=ledger_account.broker_account_id)
        session.add(account)
    account.name = ledger_account.name
    account.base_currency = ledger_account.base_currency
    account.broker = ledger_account.broker
    session.flush()
    return account


def upsert_instrument(session: Session, li: LedgerInstrument) -> Instrument:
    """Find the Instrument by its natural key, or create it; update its fields."""
    inst = session.scalar(
        select(Instrument).where(
            Instrument.symbol == li.symbol,
            Instrument.asset_class == li.asset_class,
            Instrument.strike == li.strike,
            Instrument.expiry == li.expiry,
            Instrument.option_type == li.option_type,
        )
    )
    if inst is None:
        inst = Instrument(symbol=li.symbol, asset_class=li.asset_class)
        session.add(inst)
    inst.currency = li.currency
    inst.exchange = li.exchange
    inst.name = li.name
    inst.conid = li.conid
    inst.underlying_symbol = li.underlying_symbol
    inst.option_type = li.option_type
    inst.strike = li.strike
    inst.expiry = li.expiry
    inst.multiplier = li.multiplier
    inst.source = li.source
    inst.import_batch = li.import_batch
    session.flush()
    return inst


def project_instruments(
    session: Session, ledger: AccountLedger
) -> dict[str, Instrument]:
    """Upsert every instrument in the ledger; return a symbol -> Instrument map.

    Raises ValueError if two ledger rows share a symbol — trades and cash
    flows resolve their instrument by this symbol, so it must be unique.
    """
    mapping: dict[str, Instrument] = {}
    for li in ledger.instruments.read():
        if li.symbol in mapping:
            raise ValueError(
                f"duplicate instrument symbol {li.symbol!r} in ledger — "
                f"instrument symbols must be unique"
            )
        mapping[li.symbol] = upsert_instrument(session, li)
    return mapping


def project_trades(
    session: Session,
    account: Account,
    ledger: AccountLedger,
    instruments: dict[str, Instrument],
) -> None:
    """Delete this account's trades, then re-insert them from the ledger.

    If a trade references an unknown instrument the function raises ``ValueError``
    and the session is left uncommitted — the caller is responsible for rollback.
    """
    # Account-scoped full rebuild: drop this account's trades, then re-insert.
    session.execute(delete(Trade).where(Trade.account_id == account.id))
    for lt in ledger.trades.read():
        inst = instruments.get(lt.instrument)
        if inst is None:
            raise ValueError(
                f"trade {lt.trade_id} references unknown instrument "
                f"{lt.instrument!r} (not in instruments.csv)"
            )
        session.add(
            Trade(
                account_id=account.id,
                instrument_id=inst.id,
                trade_id=lt.trade_id,
                side=lt.side,
                open_close=lt.open_close,
                quantity=lt.quantity,
                price=lt.price,
                currency=lt.currency,
                fx_rate_to_usd=lt.fx_rate_to_usd,
                proceeds=lt.proceeds_orig,
                proceeds_usd=lt.proceeds_usd,
                commission=lt.commission_orig,
                commission_usd=lt.commission_usd,
                realized_pnl_ibkr=lt.realized_pnl_ibkr,
                executed_at=lt.executed_at,
                source=lt.source,
                import_batch=lt.import_batch,
            )
        )
    session.flush()


def project_cash_flows(
    session: Session,
    account: Account,
    ledger: AccountLedger,
    instruments: dict[str, Instrument],
) -> None:
    """Delete this account's cash flows, then re-insert them from the ledger.

    Raises ValueError if a flow references an unknown instrument; on that
    error the session is left uncommitted and the caller must roll back.
    """
    session.execute(delete(CashFlow).where(CashFlow.account_id == account.id))
    for lc in ledger.cash_flows.read():
        instrument_id = None
        if lc.instrument is not None:
            inst = instruments.get(lc.instrument)
            if inst is None:
                raise ValueError(
                    f"cash flow references unknown instrument "
                    f"{lc.instrument!r} (not in instruments.csv)"
                )
            instrument_id = inst.id
        session.add(
            CashFlow(
                account_id=account.id,
                instrument_id=instrument_id,
                flow_type=lc.flow_type,
                amount=lc.amount_orig,
                currency=lc.currency,
                fx_rate_to_usd=lc.fx_rate_to_usd,
                amount_usd=lc.amount_usd,
                description=lc.description,
                external_id=lc.external_id,
                occurred_at=lc.occurred_at,
                source=lc.source,
                import_batch=lc.import_batch,
            )
        )
    session.flush()


def project_corporate_actions(
    session: Session,
    ledger: AccountLedger,
    instruments: dict[str, Instrument],
) -> None:
    """Upsert corporate actions by (instrument, action_type, ex_date).

    corporate_actions is a global, instrument-scoped table — upserted rather
    than deleted-per-account, since the same action may appear in several
    accounts' ledgers. Raises ValueError on an unknown instrument; on that
    error the session is left uncommitted and the caller must roll back.
    """
    for lca in ledger.corporate_actions.read():
        inst = instruments.get(lca.instrument)
        if inst is None:
            raise ValueError(
                f"corporate action references unknown instrument "
                f"{lca.instrument!r} (not in instruments.csv)"
            )
        ca = session.scalar(
            select(CorporateAction).where(
                CorporateAction.instrument_id == inst.id,
                CorporateAction.action_type == lca.action_type,
                CorporateAction.ex_date == lca.ex_date,
            )
        )
        if ca is None:
            ca = CorporateAction(
                instrument_id=inst.id,
                action_type=lca.action_type,
                ex_date=lca.ex_date,
            )
            session.add(ca)
        ca.ratio = lca.ratio
        ca.description = lca.description
        ca.external_id = lca.external_id
        ca.source = lca.source
        ca.import_batch = lca.import_batch
    session.flush()


def rebuild_account(session: Session, ledger: AccountLedger) -> Account:
    """Full rebuild of one account's DB projection from its CSV ledger.

    Account-scoped tables (trades, cash_flows) are deleted and re-inserted;
    global tables (instruments, corporate_actions) are upserted by key.
    Running this repeatedly is idempotent. On success the session is
    committed; on any error it is rolled back before the exception
    propagates, so the session is always left clean for the caller.
    """
    try:
        account = upsert_account(session, ledger.read_account())
        instruments = project_instruments(session, ledger)
        project_trades(session, account, ledger, instruments)
        project_cash_flows(session, account, ledger, instruments)
        project_corporate_actions(session, ledger, instruments)
        session.commit()
        return account
    except Exception:
        session.rollback()
        raise
