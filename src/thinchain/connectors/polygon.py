import os
import httpx
from .base import BaseConnector, ConnectorError
from ..core.sanitizer import num


class PolygonConnector(BaseConnector):
    name = "polygon"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("POLYGON_API_KEY", "")
        self.base_url = (base_url or os.getenv("POLYGON_BASE_URL") or "https://api.polygon.io").rstrip("/")
        self._last_underlying_price: dict[str, float] = {}

    async def get_chain(self, symbol: str, expiration: str) -> list[dict]:
        url = f"{self.base_url}/v3/snapshot/options/{symbol}"
        params = {"apiKey": self.api_key, "limit": 250}
        results: list[dict] = []
        pages = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            while url and pages < 3:
                resp = await client.get(url, params=params if pages == 0 else None)
                if resp.status_code >= 400:
                    raise ConnectorError(
                        f"Polygon HTTP {resp.status_code} for {symbol}",
                        status_code=resp.status_code,
                    )
                data = resp.json()
                page_results = data.get("results") or []
                results.extend(page_results)
                if page_results:
                    ua = page_results[0].get("underlying_asset") or {}
                    price = num(ua.get("price"))
                    if price is not None:
                        self._last_underlying_price[symbol] = price
                next_url = data.get("next_url")
                if not next_url:
                    break
                # Polygon next_url needs apiKey appended
                sep = "&" if "?" in next_url else "?"
                url = f"{next_url}{sep}apiKey={self.api_key}"
                pages += 1

        rows: list[dict] = []
        for r in results:
            details = r.get("details") or {}
            day = r.get("day") or {}
            last_quote = day.get("last_quote") or {}
            last_trade = day.get("last_trade") or {}
            greeks_in = r.get("greeks") or {}

            exp = details.get("expiration_date")
            if expiration and exp and exp != expiration:
                continue

            rows.append({
                "strike": details.get("strike_price"),
                "expiration": exp,
                "option_type": details.get("contract_type"),
                "bid": last_quote.get("bid"),
                "ask": last_quote.get("ask"),
                "last": last_trade.get("price"),
                "volume": day.get("volume"),
                "open_interest": r.get("open_interest"),
                "implied_volatility": r.get("implied_volatility"),
                "greeks": {
                    "delta": greeks_in.get("delta"),
                    "gamma": greeks_in.get("gamma"),
                    "theta": greeks_in.get("theta"),
                    "vega": greeks_in.get("vega"),
                },
            })
        return rows

    async def get_underlying_price(self, symbol: str) -> float:
        cached = self._last_underlying_price.get(symbol)
        if cached and cached > 0:
            return cached
        # Fallback: snapshot ticker
        url = f"{self.base_url}/v3/snapshot/options/{symbol}"
        params = {"apiKey": self.api_key, "limit": 1}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
        if resp.status_code >= 400:
            raise ConnectorError(f"No underlying price for {symbol}")
        data = resp.json()
        results = data.get("results") or []
        if not results:
            raise ConnectorError(f"No underlying price for {symbol}")
        ua = results[0].get("underlying_asset") or {}
        price = num(ua.get("price"))
        if price is None or price <= 0:
            raise ConnectorError(f"No underlying price for {symbol}")
        return price
