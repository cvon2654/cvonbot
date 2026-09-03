"""
Thin client for Kalshi's REST API (trade-api/v2).

Reading market data (events, markets, order books, trades) needs no
authentication at all -- it's public. Signing is only wired up for the
optional /portfolio endpoints (balance, positions), which this bot uses
purely for display. Nothing in this file places, cancels, or amends an
order; there is no method that does, on purpose.

Auth scheme (Kalshi "API key" signing), confirmed against Kalshi's current
docs: each authenticated request carries three headers --
  KALSHI-ACCESS-KEY:       your key id
  KALSHI-ACCESS-TIMESTAMP: unix time in *milliseconds*, as a string
  KALSHI-ACCESS-SIGNATURE: base64(RSA-PSS-SHA256(timestamp + METHOD + path))
where `path` includes the "/trade-api/v2" prefix and excludes any query
string, and the PSS salt length equals the SHA-256 digest size (32 bytes).
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROD_BASE = "https://external-api.kalshi.com/trade-api/v2"
DEMO_BASE = "https://external-api.demo.kalshi.co/trade-api/v2"


class KalshiError(RuntimeError):
    pass


@dataclass
class KalshiAuth:
    key_id: str
    private_key_path: str

    def __post_init__(self) -> None:
        with open(self.private_key_path, "rb") as f:
            self._private_key = serialization.load_pem_private_key(f.read(), password=None)

    def headers(self, method: str, path_with_prefix: str) -> dict:
        timestamp_ms = str(int(time.time() * 1000))
        message = (timestamp_ms + method.upper() + path_with_prefix).encode("utf-8")
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256().digest_size,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        }


class KalshiClient:
    def __init__(self, env: str = "demo", auth: Optional[KalshiAuth] = None, timeout: float = 10.0):
        self.base_url = PROD_BASE if env == "prod" else DEMO_BASE
        self.auth = auth
        self.timeout = timeout
        self._session = requests.Session()

    # -- internal --------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None, authed: bool = False) -> Any:
        # path is relative, e.g. "/markets" -> signed/prefixed as "/trade-api/v2/markets"
        full_prefix = "/trade-api/v2" + path
        url = self.base_url + path
        headers = {}
        if authed:
            if not self.auth:
                raise KalshiError(f"{path} requires an API key; none configured")
            headers = self.auth.headers("GET", full_prefix)
        resp = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise KalshiError(f"GET {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def _paginate(self, path: str, params: dict, items_key: str, authed: bool = False, max_pages: int = 20):
        items = []
        cursor = None
        for _ in range(max_pages):
            page_params = dict(params)
            if cursor:
                page_params["cursor"] = cursor
            data = self._get(path, page_params, authed=authed)
            items.extend(data.get(items_key, []))
            cursor = data.get("cursor")
            if not cursor:
                break
        return items

    # -- public market data ----------------------------------------------

    def get_events(self, status: str = "open", with_nested_markets: bool = True) -> list[dict]:
        params = {"status": status, "with_nested_markets": str(with_nested_markets).lower()}
        return self._paginate("/events", params, "events")

    def get_markets(self, series_ticker: Optional[str] = None, event_ticker: Optional[str] = None,
                     status: str = "open") -> list[dict]:
        params = {"status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        return self._paginate("/markets", params, "markets")

    def get_market(self, ticker: str) -> dict:
        return self._get(f"/markets/{ticker}")["market"]

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        return self._get(f"/markets/{ticker}/orderbook", {"depth": depth})["orderbook"]

    # -- authenticated (display-only; never used to trade) ---------------

    def get_balance(self) -> dict:
        return self._get("/portfolio/balance", authed=True)

    def get_positions(self) -> list[dict]:
        return self._paginate("/portfolio/positions", {}, "market_positions", authed=True)


def sports_events(client: KalshiClient) -> list[dict]:
    """Every open event Kalshi categorizes as Sports, nested markets included."""
    events = client.get_events(status="open", with_nested_markets=True)
    return [e for e in events if (e.get("category") or "").lower() == "sports"]


def extract_price_cents(market: dict) -> Optional[float]:
    """A market's current 'yes' price, in cents (0-100), from whichever field shape
    this account's API responses actually use.

    Confirmed against a real account: current Kalshi responses price markets in
    dollar-denominated string fields (yes_ask_dollars="0.5500", not yes_ask=55) --
    the reverse of what older public docs/examples show. Both are checked, dollar
    fields first, since a live account is the more trustworthy source here.
    """
    for key in ("yes_ask_dollars", "last_price_dollars"):
        val = market.get(key)
        if val is not None:
            try:
                return float(val) * 100
            except (TypeError, ValueError):
                continue
    for key in ("yes_ask", "last_price"):
        val = market.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None
