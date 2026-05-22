from fastmcp import FastMCP
from dotenv import load_dotenv
import os
import logging
from typing import Optional

from .core.sanitizer import Sanitizer
from .core.compressor import Compressor
from .core.circuit_breaker import CircuitBreaker
from .connectors.base import ConnectorError
from .connectors.tradier import TradierConnector
from .connectors.polygon import PolygonConnector
from .models.chain import Strategy

mcp = FastMCP("thinchain")

_sanitizer = Sanitizer()
_compressor = Compressor()
_circuit = CircuitBreaker()

VALID_STRATEGIES = [s.value for s in Strategy]


def _get_connector(broker: str):
    broker = (broker or "tradier").lower()
    if broker == "tradier":
        return TradierConnector()
    if broker == "polygon":
        return PolygonConnector()
    raise ConnectorError(f"Unknown broker '{broker}'")


@mcp.tool()
async def get_compressed_chain(
    symbol: str,
    expiration: str,
    strategy: str = "raw",
    delta_range: Optional[list[float]] = None,
    broker: str = "tradier",
) -> dict:
    """Fetch, sanitize, and compress an options chain for AI agent use."""
    if strategy not in VALID_STRATEGIES:
        return {
            "error": "invalid_strategy",
            "message": f"Unknown strategy '{strategy}'. Valid: {', '.join(VALID_STRATEGIES)}",
        }

    try:
        connector = _get_connector(broker)
    except ConnectorError as e:
        return {"error": "connector_error", "message": str(e), "symbol": symbol}

    try:
        raw_rows = await connector.get_chain(symbol, expiration)
        underlying_price = await connector.get_underlying_price(symbol)
    except ConnectorError as e:
        return {"error": "connector_error", "message": str(e), "symbol": symbol}

    if not raw_rows:
        return {
            "error": "connector_error",
            "message": f"{connector.name.capitalize()} returned no data for {symbol} {expiration}",
            "symbol": symbol,
        }

    chain = _sanitizer.sanitize_chain(raw_rows, symbol, underlying_price, expiration, connector.name)
    raw_anomalous = sum(1 for r in chain.rows if r.is_anomalous)
    chain = _circuit.evaluate(chain)
    serving_from_cache = False

    if chain.data_quality == "circuit_breaker_active":
        cached = _circuit.get_cached(symbol, expiration, connector.name)
        if cached is None:
            return {
                "error": "circuit_breaker_active",
                "message": f"{symbol} data quality too degraded to serve. No cache available.",
                "symbol": symbol,
            }
        serving_from_cache = True

    strat_enum = Strategy(strategy)
    dr = tuple(delta_range) if delta_range and len(delta_range) == 2 else None
    chain = _compressor.compress(chain, strat_enum, dr)

    _circuit.update_cache(chain)

    raw_tokens = chain.token_estimate_raw or 1
    savings_pct = max(0, int(round((1 - chain.token_estimate_compressed / raw_tokens) * 100)))

    return {
        "symbol": chain.symbol,
        "expiration": chain.expiration,
        "strategy_applied": strategy,
        "underlying_price": chain.underlying_price,
        "data_quality": chain.data_quality,
        "token_savings": f"{savings_pct}%",
        "serving_from_cache": serving_from_cache,
        "rows": [r.model_dump() for r in chain.rows],
        "stats": {
            "raw_rows": chain.raw_row_count,
            "compressed_rows": chain.compressed_row_count,
            "anomalous_rows_removed": raw_anomalous,
            "token_estimate_raw": chain.token_estimate_raw,
            "token_estimate_compressed": chain.token_estimate_compressed,
        },
    }


@mcp.tool()
async def get_sanitized_quote(symbol: str, broker: str = "tradier") -> dict:
    """Get a single underlying quote with data quality check."""
    try:
        connector = _get_connector(broker)
        price = await connector.get_underlying_price(symbol)
    except ConnectorError as e:
        return {"error": "connector_error", "message": str(e), "symbol": symbol}

    anomalies: list[str] = []
    is_trustworthy = True
    if price is None or price <= 0:
        anomalies.append("invalid_underlying_price")
        is_trustworthy = False

    return {
        "symbol": symbol,
        "price": price,
        "is_trustworthy": is_trustworthy,
        "anomalies": anomalies,
        "broker": connector.name,
    }


@mcp.tool()
async def get_circuit_status(symbol: str, expiration: str, broker: str = "tradier") -> dict:
    """Check whether live options data for a symbol is currently trustworthy."""
    try:
        connector = _get_connector(broker)
    except ConnectorError as e:
        return {"error": "connector_error", "message": str(e), "symbol": symbol}

    try:
        raw_rows = await connector.get_chain(symbol, expiration)
        underlying_price = await connector.get_underlying_price(symbol)
    except ConnectorError as e:
        return {"error": "connector_error", "message": str(e), "symbol": symbol}

    chain = _sanitizer.sanitize_chain(raw_rows, symbol, underlying_price, expiration, connector.name)
    rate = _circuit.anomaly_rate(chain)
    chain = _circuit.evaluate(chain)

    serving_from_cache = False
    if chain.data_quality == "circuit_breaker_active":
        cached = _circuit.get_cached(symbol, expiration, connector.name)
        serving_from_cache = cached is not None

    recommendations = {
        "clean": "Data is clean. Safe to proceed.",
        "noisy": "High illiquid strike count (normal for wide chains). Compressor filters safely.",
        "degraded": "Elevated anomalies detected. Review compressed output before acting.",
        "circuit_breaker_active": "Data too corrupted to serve. Serving from cache or refusing.",
    }
    recommendation = recommendations.get(chain.data_quality, "Unknown status.")

    return {
        "symbol": symbol,
        "expiration": expiration,
        "status": chain.data_quality,
        "anomaly_rate": round(rate, 4),
        "serving_from_cache": serving_from_cache,
        "recommendation": recommendation,
        "broker": connector.name,
    }


def main():
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    tradier_key = os.getenv("TRADIER_API_KEY")
    if not tradier_key:
        logging.warning("TRADIER_API_KEY not set — Tradier tools will fail at runtime")

    polygon_key = os.getenv("POLYGON_API_KEY")
    if not polygon_key:
        logging.warning("POLYGON_API_KEY not set — Polygon tools will fail at runtime")

    mcp.run()


if __name__ == "__main__":
    main()
