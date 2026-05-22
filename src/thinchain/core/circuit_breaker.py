from typing import Optional
from ..models.chain import OptionChain


class CircuitBreaker:
    def __init__(self):
        self._cache: dict[str, OptionChain] = {}

    def _key(self, chain: OptionChain) -> str:
        return f"{chain.symbol}:{chain.expiration}:{chain.broker}"

    def cache_key(self, symbol: str, expiration: str, broker: str) -> str:
        return f"{symbol}:{expiration}:{broker}"

    def get_cached(self, symbol: str, expiration: str, broker: str) -> Optional[OptionChain]:
        return self._cache.get(self.cache_key(symbol, expiration, broker))

    def anomaly_rate(self, chain: OptionChain) -> float:
        if not chain.rows:
            return 0.0
        anomalous = sum(1 for r in chain.rows if r.is_anomalous)
        return anomalous / len(chain.rows)

    def evaluate(self, chain: OptionChain) -> OptionChain:
        if chain.underlying_price is None or chain.underlying_price <= 0:
            chain.data_quality = "circuit_breaker_active"
            cached = self.get_cached(chain.symbol, chain.expiration, chain.broker)
            if cached is not None:
                return cached
            chain.rows = []
            chain.compressed_row_count = 0
            chain.token_estimate_compressed = 0
            return chain

        rate = self.anomaly_rate(chain)

        if rate > 0.65:
            chain.data_quality = "circuit_breaker_active"
            cached = self.get_cached(chain.symbol, chain.expiration, chain.broker)
            if cached is not None:
                return cached
            chain.rows = []
            chain.compressed_row_count = 0
            chain.token_estimate_compressed = 0
            return chain
        elif rate > 0.50:
            chain.data_quality = "degraded"
        elif rate > 0.30:
            chain.data_quality = "noisy"
        else:
            chain.data_quality = "clean"

        return chain

    def update_cache(self, chain: OptionChain) -> None:
        if chain.data_quality == "clean":
            self._cache[self._key(chain)] = chain
