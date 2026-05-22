# ThinChain

The catalytic converter between raw broker data and your AI trading agent.

**Battle-tested.** Sanitization logic extracted from a production options trading app. Handles every bad tick Tradier has thrown at us in production.

## ☁️ Moving to production?

The open-source server runs locally with your own API keys.
For hosted infrastructure with multi-broker failover, SLA guarantees,
and webhook alerts — [join the managed cloud waitlist](https://snipmcp.com).

## The Problem

Tradier's MCP dumps 500-row JSON chains. One bad print can corrupt an agent's reasoning. ThinChain sanitizes, compresses, and circuit-breaks that data before it reaches your model.

## Installation

```bash
git clone https://github.com/snipmcp/thinchain.git
cd thinchain
pip install -e ".[dev]"
cp .env.example .env
```

Or with Docker:

```bash
docker-compose up --build
```

## Configuration

```env
TRADIER_API_KEY=your_key_here
TRADIER_BASE_URL=https://api.tradier.com/v1
POLYGON_API_KEY=your_key_here
POLYGON_BASE_URL=https://api.polygon.io
DEFAULT_BROKER=tradier
CACHE_TTL_SECONDS=30
LOG_LEVEL=INFO
```

## Usage

Three example prompts to send to Claude (or any MCP-compatible agent):

1. `Use get_compressed_chain to get an iron condor setup on SPY expiring 2026-06-19`
2. `Check if SPY options data is trustworthy before I place my trade`
3. `Get me the ATM straddle strikes for AAPL expiring 2026-06-19`

### Run it in two terminals

```bash
# Tab 1 — start the MCP server
python -m thinchain.server
```

```bash
# Tab 2 — call a tool from a Python shell or your MCP client
# Tool signatures:
#   get_compressed_chain(symbol, expiration, strategy="raw",
#                        delta_range=None, broker="tradier")
#   get_sanitized_quote(symbol, broker="tradier")
#   get_circuit_status(symbol, expiration, broker="tradier")
```

## How it works

Three layers between raw broker output and your model:

```
Broker API → [Sanitize] → [Compress] → [Circuit Break] → MCP Tool → AI Agent
              hygiene     strategy      anomaly gate
              rules       slicing       + cache
```

- **Sanitize**: Drops ghost quotes (0.0/0.0), inverted spreads, NaN/empty/dash values, clamps deltas to [-1, 1], normalizes positive theta on long options, flags illiquid strikes.
- **Compress**: Slices the chain to only the strikes relevant to your strategy (iron condor, straddle, etc.) — typically 95%+ token reduction.
- **Circuit Break**: Four-tier data quality (`clean` / `noisy` / `degraded` / `circuit_breaker_active`). When >65% of rows are anomalous, refuses to serve stale data and falls back to last known-good cache.

### Real numbers from a live SPY iron condor (2026-06-19 expiration)

```
RAW TRADIER PAYLOAD          THINCHAIN OUTPUT
─────────────────────────────────────────────
Rows:        482             Rows:        25
Est tokens:  38,560          Est tokens:  2,000
Token savings:               95%
Anomalous rows removed:      217
Data quality:                noisy → still safely served
```

ThinChain compresses 482 rows / 38,560 tokens down to 25 rows / 2,000 tokens — and flags 217 anomalous strikes (illiquid, ghost quotes, wide spreads) that would have polluted the agent's context.

## Roadmap

- Managed cloud tier (hosted, multi-tenant, webhook alerts)
- Polygon connector hardening (live SIP feed)
- Webhook alerts for circuit breaker trips

## Contributing

PRs welcome. Run `pytest` before submitting.
