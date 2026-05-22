import pytest
from thinchain.core.circuit_breaker import CircuitBreaker
from thinchain.models.chain import OptionChain, OptionRow, OptionType


def _row(anomalous=False):
    return OptionRow(
        strike=540,
        expiration="2026-06-19",
        option_type=OptionType.CALL,
        bid=1.0,
        ask=1.1,
        is_anomalous=anomalous,
    )


def _chain(rows, underlying=540.0, broker="tradier"):
    return OptionChain(
        symbol="SPY",
        underlying_price=underlying,
        expiration="2026-06-19",
        rows=rows,
        raw_row_count=len(rows),
        compressed_row_count=len(rows),
        token_estimate_raw=len(rows) * 80,
        token_estimate_compressed=len(rows) * 80,
        data_quality="clean",
        broker=broker,
    )


def test_clean_chain_passes():
    cb = CircuitBreaker()
    rows = [_row(anomalous=(i == 0)) for i in range(20)]  # 5% anomalous
    chain = cb.evaluate(_chain(rows))
    assert chain.data_quality == "clean"


def test_noisy_chain():
    cb = CircuitBreaker()
    rows = [_row(anomalous=(i < 4)) for i in range(10)]  # 40% anomalous
    chain = cb.evaluate(_chain(rows))
    assert chain.data_quality == "noisy"


def test_degraded_chain():
    cb = CircuitBreaker()
    rows = [_row(anomalous=(i < 6)) for i in range(10)]  # 60% anomalous
    chain = cb.evaluate(_chain(rows))
    assert chain.data_quality == "degraded"


def test_circuit_breaker_no_cache():
    cb = CircuitBreaker()
    rows = [_row(anomalous=(i < 7)) for i in range(10)]  # 70% anomalous
    chain = cb.evaluate(_chain(rows))
    assert chain.data_quality == "circuit_breaker_active"
    assert chain.rows == []


def test_circuit_breaker_uses_cache():
    cb = CircuitBreaker()
    # Populate cache with a clean chain
    clean = _chain([_row() for _ in range(10)])
    clean.data_quality = "clean"
    cb.update_cache(clean)

    bad_rows = [_row(anomalous=(i < 7)) for i in range(10)]
    bad_chain = _chain(bad_rows)
    out = cb.evaluate(bad_chain)
    assert out.data_quality == "clean"  # cached one returned
    assert len(out.rows) == 10


def test_cache_only_stores_clean():
    cb = CircuitBreaker()
    chain = _chain([_row() for _ in range(10)])
    chain.data_quality = "degraded"
    cb.update_cache(chain)
    assert cb.get_cached("SPY", "2026-06-19", "tradier") is None


def test_zero_underlying_triggers_breaker():
    cb = CircuitBreaker()
    chain = _chain([_row()], underlying=0.0)
    out = cb.evaluate(chain)
    assert out.data_quality == "circuit_breaker_active"
