"""Generate demo/raw_output.json and demo/compressed_output.json for README."""
import asyncio
import json
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
import httpx

load_dotenv()

from thinchain.server import get_compressed_chain
from thinchain.connectors.tradier import TradierConnector

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
DEMO_DIR.mkdir(exist_ok=True)


async def nearest_friday_exp() -> str:
    base = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip("/")
    key = os.getenv("TRADIER_API_KEY", "")
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{base}/markets/options/expirations",
            params={"symbol": "SPY", "includeAllRoots": "true", "strikes": "false"},
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        )
    resp.raise_for_status()
    exps = (resp.json().get("expirations") or {}).get("date") or []
    if isinstance(exps, str):
        exps = [exps]
    for d in exps:
        y, m, day = d.split("-")
        if date(int(y), int(m), int(day)).weekday() == 4:
            return d
    return exps[0]


async def fetch_raw(symbol: str, expiration: str) -> dict:
    conn = TradierConnector()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{conn.base_url}/markets/options/chains",
            params={"symbol": symbol, "expiration": expiration, "greeks": "true"},
            headers=conn._headers(),
        )
    resp.raise_for_status()
    return resp.json()


async def main():
    expiration = await nearest_friday_exp()
    print(f"Fetching SPY iron condor for {expiration}...")

    raw = await fetch_raw("SPY", expiration)
    compressed = await get_compressed_chain(symbol="SPY", expiration=expiration, strategy="iron_condor")

    (DEMO_DIR / "raw_output.json").write_text(json.dumps(raw, indent=2))
    (DEMO_DIR / "compressed_output.json").write_text(json.dumps(compressed, indent=2))

    stats = compressed.get("stats", {})
    raw_rows = stats.get("raw_rows", 0)
    comp_rows = stats.get("compressed_rows", 0)
    raw_tokens = stats.get("token_estimate_raw", 0)
    comp_tokens = stats.get("token_estimate_compressed", 0)
    removed = stats.get("anomalous_rows_removed", 0)

    print()
    print("RAW TRADIER PAYLOAD          THINCHAIN OUTPUT")
    print("─" * 60)
    print(f"Rows:        {raw_rows:<15} Rows:        {comp_rows}")
    print(f"Est tokens:  {raw_tokens:<15} Est tokens:  {comp_tokens}")
    print(f"Token savings:           {compressed.get('token_savings')}")
    print(f"Anomalous rows removed:  {removed}")
    print(f"Data quality:            {compressed.get('data_quality')}")
    print(f"Expiration:              {expiration}")
    print(f"Underlying price:        ${compressed.get('underlying_price')}")
    print()
    rows = compressed.get("rows") or []
    if rows:
        print("Sample compressed row:")
        print(json.dumps(rows[0], indent=2))

    return {
        "expiration": expiration,
        "raw_rows": raw_rows,
        "compressed_rows": comp_rows,
        "raw_tokens": raw_tokens,
        "compressed_tokens": comp_tokens,
        "token_savings": compressed.get("token_savings"),
        "data_quality": compressed.get("data_quality"),
        "underlying_price": compressed.get("underlying_price"),
        "anomalous_rows_removed": removed,
    }


if __name__ == "__main__":
    result = asyncio.run(main())
    print(f"\nSUMMARY_JSON={json.dumps(result)}")
