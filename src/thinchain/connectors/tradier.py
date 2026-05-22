import os
import httpx
from .base import BaseConnector, ConnectorError
from ..core.sanitizer import num


class TradierConnector(BaseConnector):
    name = "tradier"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("TRADIER_API_KEY", "")
        self.base_url = (base_url or os.getenv("TRADIER_BASE_URL") or "https://api.tradier.com/v1").rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def get_chain(self, symbol: str, expiration: str) -> list[dict]:
        url = f"{self.base_url}/markets/options/chains"
        params = {"symbol": symbol, "expiration": expiration, "greeks": "true"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=self._headers())
        if resp.status_code >= 400:
            raise ConnectorError(
                f"Tradier returned HTTP {resp.status_code} for {symbol} {expiration}",
                status_code=resp.status_code,
            )
        data = resp.json()
        options = data.get("options")
        if options is None:
            return []
        contracts = options.get("option")
        if contracts is None:
            return []
        if isinstance(contracts, dict):
            contracts = [contracts]

        rows: list[dict] = []
        for c in contracts:
            rows.append({
                "strike": c.get("strike"),
                "expiration": c.get("expiration_date"),
                "option_type": c.get("option_type"),
                "bid": c.get("bid"),
                "ask": c.get("ask"),
                "last": c.get("last"),
                "volume": c.get("volume"),
                "open_interest": c.get("open_interest"),
                "greeks": c.get("greeks") or {},
            })
        return rows

    async def get_underlying_price(self, symbol: str) -> float:
        url = f"{self.base_url}/markets/quotes"
        params = {"symbols": symbol, "greeks": "false"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=self._headers())
        if resp.status_code >= 400:
            raise ConnectorError(
                f"Tradier quote HTTP {resp.status_code} for {symbol}",
                status_code=resp.status_code,
            )
        data = resp.json()
        quotes = data.get("quotes") or {}
        quote = quotes.get("quote")
        if isinstance(quote, list):
            quote = quote[0] if quote else None
        if quote is None:
            raise ConnectorError(f"No underlying price for {symbol}")
        price = num(quote.get("last"))
        if price is None or price <= 0:
            raise ConnectorError(f"No underlying price for {symbol}")
        return price
