"""IBKR Client Portal Gateway client + live-quote provider.

The Gateway is IBKR's locally-run Java program (https://localhost:5000) that
the user starts and logs into manually (2FA). All network calls live in
`IBKRClientPortalClient`; it takes an injectable `httpx.Client` so tests run
offline. The Gateway serves a self-signed certificate, so the default client
disables TLS verification — localhost-only traffic.
"""

import logging
from decimal import Decimal, InvalidOperation

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# IBKR market-data snapshot field ids.
FIELD_LAST = "31"
FIELD_MARK = "7635"


def parse_price(raw: str | None) -> Decimal | None:
    """Parse an IBKR snapshot price, stripping status-letter prefixes.

    IBKR prefixes prices with letters like C (prior close) or H (halted).
    """
    if raw is None:
        return None
    text = raw.strip()
    while text and not (text[0].isdigit() or text[0] in "-."):
        text = text[1:]
    if not text:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _default_http_client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.ibkr_gateway_url,
        verify=False,  # Gateway 自签名证书,仅 localhost 流量
        timeout=settings.ibkr_gateway_timeout_seconds,
    )


class IBKRClientPortalClient:
    """Thin HTTP wrapper over the CP Gateway REST API."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or _default_http_client()
        self._primed = False

    def auth_ok(self) -> bool:
        """True iff the Gateway is up and holds an authenticated session."""
        try:
            res = self._http.post("/iserver/auth/status")
            res.raise_for_status()
            return bool(res.json().get("authenticated"))
        except Exception:
            logger.debug("Gateway auth probe failed; treating as offline", exc_info=True)
            return False

    def ensure_primed(self) -> None:
        """Call /iserver/accounts once per process — required before snapshot."""
        if self._primed:
            return
        self._http.get("/iserver/accounts").raise_for_status()
        self._primed = True

    def search_stock_conid(self, symbol: str) -> int | None:
        res = self._http.get("/iserver/secdef/search", params={"symbol": symbol})
        res.raise_for_status()
        for entry in res.json() or []:
            if entry.get("symbol") != symbol:
                continue
            sections = {s.get("secType") for s in entry.get("sections", [])}
            if entry.get("secType") == "STK" or "STK" in sections:
                try:
                    return int(entry["conid"])
                except (KeyError, TypeError, ValueError):
                    continue
        return None

    def snapshot(
        self, conids: list[int], fields: list[str]
    ) -> dict[int, dict[str, str]]:
        """One quote row per conid; retries once if price fields are absent

        (known Gateway quirk: the first snapshot call after login often
        returns rows without price fields).
        """
        if not conids:
            return {}
        self.ensure_primed()
        rows = self._snapshot_once(conids, fields)
        incomplete = len(rows) < len(conids) or any(
            not any(f in row for f in fields) for row in rows.values()
        )
        if incomplete:
            rows = self._snapshot_once(conids, fields)
        return rows

    def _snapshot_once(
        self, conids: list[int], fields: list[str]
    ) -> dict[int, dict[str, str]]:
        res = self._http.get(
            "/iserver/marketdata/snapshot",
            params={
                "conids": ",".join(str(c) for c in conids),
                "fields": ",".join(fields),
            },
        )
        res.raise_for_status()
        rows: dict[int, dict[str, str]] = {}
        for row in res.json() or []:
            conid = row.get("conid")
            if conid is None:
                continue
            rows[int(conid)] = {k: str(v) for k, v in row.items() if k in fields}
        return rows


class IBKRClientPortalProvider:
    """Live quotes from the CP Gateway.

    Deliberately NOT a MarketDataProvider — it cannot serve history, so it
    only exists as the IBKR leg inside ChainedMarketDataProvider.
    """

    def __init__(self, client: IBKRClientPortalClient | None = None) -> None:
        self._client = client or IBKRClientPortalClient()
        # symbol -> conid search results; conids never change, no expiry.
        self._search_cache: dict[str, int | None] = {}

    def available(self) -> bool:
        return self._client.auth_ok()

    def resolve_equity_conids(
        self, equity: dict[str, int | None]
    ) -> dict[str, int]:
        """DB conids pass through; the rest go through cached secdef search."""
        resolved: dict[str, int] = {}
        for symbol, conid in equity.items():
            if conid is None:
                if symbol not in self._search_cache:
                    self._search_cache[symbol] = (
                        self._client.search_stock_conid(symbol)
                    )
                conid = self._search_cache[symbol]
            if conid is not None:
                resolved[symbol] = conid
        return resolved

    def get_equity_closes(
        self, symbol_conids: dict[str, int]
    ) -> dict[str, Decimal]:
        if not symbol_conids:
            return {}
        rows = self._client.snapshot(list(symbol_conids.values()), [FIELD_LAST])
        closes: dict[str, Decimal] = {}
        for symbol, conid in symbol_conids.items():
            price = parse_price(rows.get(conid, {}).get(FIELD_LAST))
            if price is not None:
                closes[symbol] = price
        return closes

    def get_option_marks(
        self, symbol_conids: dict[str, int]
    ) -> dict[str, Decimal]:
        if not symbol_conids:
            return {}
        rows = self._client.snapshot(
            list(symbol_conids.values()), [FIELD_MARK, FIELD_LAST]
        )
        marks: dict[str, Decimal] = {}
        for symbol, conid in symbol_conids.items():
            row = rows.get(conid, {})
            price = parse_price(row.get(FIELD_MARK))
            if price is None:
                price = parse_price(row.get(FIELD_LAST))
            if price is not None:
                marks[symbol] = price
        return marks
