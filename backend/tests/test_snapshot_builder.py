from datetime import date, datetime
from decimal import Decimal

from app.db.enums import AssetClass, TradeSide
from app.db.models import Instrument, PositionSnapshot, Trade
from app.services.providers.base import MarketDataProvider
from app.services.snapshot.builder import rebuild_snapshots


class _FakeProvider(MarketDataProvider):
    """Provider backed by a {symbol: {date: price}} map."""

    def __init__(self, closes_by_symbol):
        self._closes = closes_by_symbol

    def get_daily_closes(self, symbol, start, end):
        return {
            d: p
            for d, p in self._closes.get(symbol, {}).items()
            if start <= d <= end
        }

    def get_latest_close(self, symbol):
        closes = self._closes.get(symbol, {})
        return closes[max(closes)] if closes else None

    def get_latest_closes(self, symbols):
        return {
            s: self._closes[s][max(self._closes[s])]
            for s in symbols
            if s in self._closes and self._closes[s]
        }


def _trade(account, instrument, side, qty, proceeds_usd, *, trade_id, executed_at):
    return Trade(
        account_id=account.id,
        instrument_id=instrument.id,
        trade_id=trade_id,
        side=side,
        quantity=Decimal(str(qty)),
        price=Decimal("100"),
        currency="USD",
        fx_rate_to_usd=Decimal("1"),
        proceeds=Decimal(str(proceeds_usd)),
        proceeds_usd=Decimal(str(proceeds_usd)),
        commission_usd=Decimal("0"),
        executed_at=executed_at,
    )


def _snapshots(session, account):
    return session.query(PositionSnapshot).filter_by(account_id=account.id).all()


def test_rebuild_snapshots_prices_a_stock(db_session, account, instrument):
    # Buy 10 AAPL on Jan 2 at cost 1000 (avg 100).
    db_session.add(
        _trade(account, instrument, TradeSide.BUY, 10, "1000",
               trade_id="B1", executed_at=datetime(2026, 1, 2, 10))
    )
    db_session.commit()
    provider = _FakeProvider(
        {"AAPL": {date(2026, 1, 2): Decimal("100"), date(2026, 1, 5): Decimal("110")}}
    )

    written = rebuild_snapshots(db_session, account, provider)

    assert written == 2
    by_date = {s.snapshot_date: s for s in _snapshots(db_session, account)}
    jan5 = by_date[date(2026, 1, 5)]
    assert jan5.quantity == Decimal("10")
    assert jan5.market_price == Decimal("110")
    assert jan5.market_value_usd == Decimal("1100")
    assert jan5.unrealized_pnl == Decimal("100")  # 1100 - 1000


def test_rebuild_snapshots_options_recorded_at_cost(db_session, account):
    option = Instrument(
        symbol="AAPL  260116C00150000",
        asset_class=AssetClass.OPTION,
        currency="USD",
    )
    stock = Instrument(symbol="AAPL", asset_class=AssetClass.STOCK, currency="USD")
    db_session.add_all([option, stock])
    db_session.flush()
    # A stock trade gives the market-day calendar; an option trade the same day.
    db_session.add_all(
        [
            _trade(account, stock, TradeSide.BUY, 1, "100",
                   trade_id="S1", executed_at=datetime(2026, 1, 2, 10)),
            _trade(account, option, TradeSide.BUY, 2, "600",
                   trade_id="O1", executed_at=datetime(2026, 1, 2, 11)),
        ]
    )
    db_session.commit()
    provider = _FakeProvider(
        {"AAPL": {date(2026, 1, 2): Decimal("100"), date(2026, 1, 5): Decimal("105")}}
    )

    rebuild_snapshots(db_session, account, provider)

    option_rows = [
        s for s in _snapshots(db_session, account)
        if s.instrument_id == option.id
    ]
    # Option held on both market days (Jan 2 and Jan 5), valued at cost (NULL mark).
    assert {s.snapshot_date for s in option_rows} == {date(2026, 1, 2), date(2026, 1, 5)}
    for s in option_rows:
        assert s.market_price is None
        assert s.market_value_usd is None
        assert s.quantity == Decimal("2")
        assert s.avg_cost == Decimal("300")  # 600 / 2


def test_rebuild_snapshots_skips_closed_positions(db_session, account, instrument):
    db_session.add_all(
        [
            _trade(account, instrument, TradeSide.BUY, 10, "1000",
                   trade_id="B1", executed_at=datetime(2026, 1, 2, 10)),
            _trade(account, instrument, TradeSide.SELL, 10, "1100",
                   trade_id="S1", executed_at=datetime(2026, 1, 5, 10)),
        ]
    )
    db_session.commit()
    provider = _FakeProvider(
        {"AAPL": {date(2026, 1, 2): Decimal("100"),
                  date(2026, 1, 5): Decimal("110"),
                  date(2026, 1, 6): Decimal("112")}}
    )

    rebuild_snapshots(db_session, account, provider)

    days = {s.snapshot_date for s in _snapshots(db_session, account)}
    # Held on Jan 2; flat after the Jan 5 sell — no Jan 5 or Jan 6 row.
    assert days == {date(2026, 1, 2)}


def test_rebuild_snapshots_is_idempotent(db_session, account, instrument):
    db_session.add(
        _trade(account, instrument, TradeSide.BUY, 10, "1000",
               trade_id="B1", executed_at=datetime(2026, 1, 2, 10))
    )
    db_session.commit()
    provider = _FakeProvider({"AAPL": {date(2026, 1, 2): Decimal("100")}})

    first = rebuild_snapshots(db_session, account, provider)
    second = rebuild_snapshots(db_session, account, provider)

    assert first == second == 1
    assert len(_snapshots(db_session, account)) == 1  # no duplicates
