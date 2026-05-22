"""Live integration test against real Tradier API."""
import asyncio
import json
import os
import sys
import traceback
from datetime import date, timedelta

from dotenv import load_dotenv
import httpx

load_dotenv()

from thinchain.server import get_compressed_chain, get_sanitized_quote, get_circuit_status
from thinchain.connectors.tradier import TradierConnector


def nearest_friday() -> str:
    today = date.today()
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).isoformat()


async def discover_expiration() -> str:
    """Query Tradier's expirations endpoint and pick the soonest standard expiration."""
    base = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip("/")
    key = os.getenv("TRADIER_API_KEY", "")
    url = f"{base}/markets/options/expirations"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            url,
            params={"symbol": "SPY", "includeAllRoots": "true", "strikes": "false"},
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        )
    resp.raise_for_status()
    data = resp.json()
    exps = (data.get("expirations") or {}).get("date") or []
    if isinstance(exps, str):
        exps = [exps]
    # Pick first Friday
    for d in exps:
        try:
            y, m, day = d.split("-")
            if date(int(y), int(m), int(day)).weekday() == 4:
                return d
        except Exception:
            continue
    return exps[0] if exps else nearest_friday()


def _summarize(label: str, resp: dict):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    print(json.dumps(resp, indent=2, default=str)[:4000])
    if "stats" in resp:
        s = resp["stats"]
        print(f"\n→ raw rows: {s['raw_rows']} → compressed rows: {s['compressed_rows']}")
        print(f"→ token savings: {resp.get('token_savings')}")
        print(f"→ data quality: {resp.get('data_quality')}")
        anomalies = [r for r in resp.get("rows", []) if r.get("is_anomalous")]
        if anomalies:
            print(f"→ anomalous rows kept ({len(anomalies)}):")
            for a in anomalies[:5]:
                print(f"   strike={a['strike']} type={a['option_type']} reason={a['anomaly_reason']}")


async def dump_raw_first_row(expiration: str):
    print(f"\n{'='*70}\nRAW TRADIER SAMPLE — first SPY row, expiration={expiration}\n{'='*70}")
    conn = TradierConnector()
    base = conn.base_url
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{base}/markets/options/chains",
            params={"symbol": "SPY", "expiration": expiration, "greeks": "true"},
            headers=conn._headers(),
        )
    resp.raise_for_status()
    data = resp.json()
    options = (data.get("options") or {}).get("option") or []
    if isinstance(options, dict):
        options = [options]
    if not options:
        print("(no rows returned)")
        return
    first = options[0]
    print(json.dumps(first, indent=2))
    g = first.get("greeks")
    print(f"\nField audit:")
    print(f"  option_type: {first.get('option_type')!r}")
    print(f"  greeks present: {g is not None}")
    if isinstance(g, dict):
        print(f"  greeks keys: {sorted(g.keys())}")
        print(f"  has mid_iv: {'mid_iv' in g}")
        print(f"  has implied_volatility: {'implied_volatility' in g}")


async def main():
    if not os.getenv("TRADIER_API_KEY"):
        print("ERROR: TRADIER_API_KEY not set in .env")
        sys.exit(1)

    expiration = await discover_expiration()
    print(f"Using expiration: {expiration}")

    await dump_raw_first_row(expiration)

    failures = []
    try:
        r1 = await get_compressed_chain(symbol="SPY", expiration=expiration, strategy="iron_condor")
        _summarize("1) get_compressed_chain SPY iron_condor", r1)
        if "error" in r1:
            failures.append(("iron_condor", r1))
    except Exception:
        traceback.print_exc()
        failures.append(("iron_condor", "exception"))

    try:
        r2 = await get_compressed_chain(symbol="SPY", expiration=expiration, strategy="straddle")
        _summarize("2) get_compressed_chain SPY straddle", r2)
        if "error" in r2:
            failures.append(("straddle", r2))
    except Exception:
        traceback.print_exc()
        failures.append(("straddle", "exception"))

    try:
        r3 = await get_sanitized_quote(symbol="SPY")
        _summarize("3) get_sanitized_quote SPY", r3)
        if "error" in r3:
            failures.append(("quote", r3))
    except Exception:
        traceback.print_exc()
        failures.append(("quote", "exception"))

    try:
        r4 = await get_circuit_status(symbol="SPY", expiration=expiration)
        _summarize("4) get_circuit_status SPY", r4)
        if "error" in r4:
            failures.append(("circuit", r4))
    except Exception:
        traceback.print_exc()
        failures.append(("circuit", "exception"))

    print(f"\n{'='*70}\nSUMMARY\n{'='*70}")
    print(f"Expiration: {expiration}")
    print(f"Failures: {len(failures)}")
    for name, info in failures:
        print(f"  - {name}: {info}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
