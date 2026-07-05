"""ChainedMarketDataProvider tests — fake IBKR leg + fake Yahoo leg."""

from datetime import date
from decimal import Decimal

from app.services.providers.base import LiveQuotes, MarketDataProvider
from app.services.providers.chain import ChainedMarketDataProvider


class _FakeYahoo(MarketDataProvider):
    def __init__(self, closes: dict[str, Decimal]):
        self._closes = closes
        self.latest_calls: list[list[str]] = []
        self.daily_calls: list[str] = []

    def get_daily_closes(self, symbol, start, end):
        self.daily_calls.append(symbol)
        return {date(2026, 7, 3): Decimal("100")}

    def get_latest_close(self, symbol):
        return self._closes.get(symbol)

    def get_latest_closes(self, symbols):
        self.latest_calls.append(list(symbols))
        return {s: self._closes[s] for s in symbols if s in self._closes}


class _FakeIbkr:
    """Stands in for IBKRClientPortalProvider."""

    def __init__(
        self,
        up: bool = True,
        closes: dict[str, Decimal] | None = None,
        marks: dict[str, Decimal] | None = None,
        explode: bool = False,
    ):
        self._up = up
        self._closes = closes or {}
        self._marks = marks or {}
        self._explode = explode

    def available(self) -> bool:
        return self._up

    def resolve_equity_conids(self, equity):
        if self._explode:
            raise RuntimeError("gateway died mid-flight")
        return {s: c or 1 for s, c in equity.items() if s in self._closes}

    def get_equity_closes(self, symbol_conids):
        return {s: self._closes[s] for s in symbol_conids if s in self._closes}

    def get_option_marks(self, symbol_conids):
        return {s: self._marks[s] for s in symbol_conids if s in self._marks}


def test_offline_goes_to_yahoo():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    chain = ChainedMarketDataProvider(_FakeIbkr(up=False), yahoo)
    q = chain.get_live_quotes({"AAPL": 265598}, {"OPT_A": 1001})
    assert q.source == "yahoo"
    assert q.closes == {"AAPL": Decimal("101")}
    assert q.option_marks == {}


def test_online_all_from_ibkr():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    ibkr = _FakeIbkr(
        closes={"AAPL": Decimal("102.5")}, marks={"OPT_A": Decimal("4.35")}
    )
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598}, {"OPT_A": 1001})
    assert q.source == "ibkr"
    assert q.closes == {"AAPL": Decimal("102.5")}
    assert q.option_marks == {"OPT_A": Decimal("4.35")}
    assert yahoo.latest_calls == []  # Yahoo 没被打扰


def test_online_partial_gap_filled_by_yahoo():
    yahoo = _FakeYahoo({"MSFT": Decimal("300")})
    ibkr = _FakeIbkr(closes={"AAPL": Decimal("102.5")})
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598, "MSFT": None}, {})
    assert q.source == "ibkr"  # Gateway 在线,来源仍标 ibkr
    assert q.closes == {"AAPL": Decimal("102.5"), "MSFT": Decimal("300")}
    assert yahoo.latest_calls == [["MSFT"]]


def test_online_gap_fill_still_missing_symbol_absent():
    # 双方都没有 ZZZZ → 缺席于 closes,由 caller(live.py)触发 503。
    yahoo = _FakeYahoo({})
    ibkr = _FakeIbkr(closes={"AAPL": Decimal("102.5")})
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598, "ZZZZ": None}, {})
    assert "ZZZZ" not in q.closes


def test_ibkr_exception_mid_flight_falls_back_to_yahoo():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    ibkr = _FakeIbkr(explode=True)
    chain = ChainedMarketDataProvider(ibkr, yahoo)
    q = chain.get_live_quotes({"AAPL": 265598}, {})
    assert q.source == "yahoo"
    assert q.closes == {"AAPL": Decimal("101")}


def test_history_methods_forward_to_yahoo():
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    chain = ChainedMarketDataProvider(_FakeIbkr(), yahoo)
    chain.get_daily_closes("AAPL", date(2026, 7, 1), date(2026, 7, 3))
    assert yahoo.daily_calls == ["AAPL"]
    assert chain.get_latest_close("AAPL") == Decimal("101")
    assert chain.get_latest_closes(["AAPL"]) == {"AAPL": Decimal("101")}


def test_base_default_get_live_quotes_is_yahoo_shaped():
    # 基类默认实现:latest closes + 空 marks + "yahoo" —— 现有 fake 不用改。
    yahoo = _FakeYahoo({"AAPL": Decimal("101")})
    q = yahoo.get_live_quotes({"AAPL": None}, {"OPT_A": 1001})
    assert isinstance(q, LiveQuotes)
    assert q.source == "yahoo"
    assert q.closes == {"AAPL": Decimal("101")}
    assert q.option_marks == {}
