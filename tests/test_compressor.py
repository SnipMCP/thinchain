import pytest
from thinchain.core.compressor import Compressor
from thinchain.models.chain import OptionChain, OptionRow, OptionType, Strategy


def _row(strike, option_type, delta, anomalous=False, reason=None):
    return OptionRow(
        strike=strike,
        expiration="2026-06-19",
        option_type=OptionType(option_type),
        bid=1.0,
        ask=1.1,
        delta=delta,
        is_anomalous=anomalous,
        anomaly_reason=reason,
    )


def _chain(rows, underlying=540.0):
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
        broker="tradier",
    )


@pytest.fixture
def compressor():
    return Compressor()


def test_iron_condor_delta_filter(compressor):
    rows = [
        _row(530, "put", -0.30),    # keep (abs 0.30 in [.05, .45])
        _row(560, "call", 0.30),    # keep
        _row(540, "call", 0.55),    # drop (abs > 0.45)
        _row(540, "put", -0.02),    # drop (abs < 0.05)
    ]
    out = compressor.compress(_chain(rows), Strategy.IRON_CONDOR)
    strikes = [r.strike for r in out.rows]
    assert 530 in strikes
    assert 560 in strikes
    assert 540 not in strikes


def test_straddle_atm_filter(compressor):
    rows = [
        _row(535, "call", 0.7),
        _row(540, "call", 0.5),
        _row(540, "put", -0.5),
        _row(545, "call", 0.3),
        _row(550, "call", 0.1),
        _row(555, "call", 0.05),
        _row(600, "call", 0.01),
    ]
    out = compressor.compress(_chain(rows, underlying=540.0), Strategy.STRADDLE)
    # 5 closest strikes: 540, 535, 545, 550, 555
    strikes = set(r.strike for r in out.rows)
    assert 540 in strikes
    assert 600 not in strikes
    assert len(strikes) == 5


def test_raw_returns_all_sanitized(compressor):
    rows = [
        _row(540, "call", 0.5),
        _row(545, "put", -0.3),
        _row(550, "call", 0.05, anomalous=True, reason="ghost_quote"),  # excluded
        _row(555, "put", -0.1, anomalous=True, reason="illiquid"),  # excluded
        _row(560, "call", 0.2, anomalous=True, reason="inverted_spread"),  # kept
    ]
    out = compressor.compress(_chain(rows), Strategy.RAW)
    strikes = [r.strike for r in out.rows]
    assert 540 in strikes
    assert 545 in strikes
    assert 550 not in strikes
    assert 555 not in strikes
    assert 560 in strikes


def test_delta_range_override(compressor):
    rows = [
        _row(540, "call", 0.15),
        _row(545, "call", 0.30),
        _row(550, "call", 0.45),
    ]
    out = compressor.compress(_chain(rows), Strategy.IRON_CONDOR, delta_range=(0.10, 0.20))
    strikes = [r.strike for r in out.rows]
    assert 540 in strikes
    assert 545 not in strikes
    assert 550 not in strikes


def test_anomalous_ghost_excluded(compressor):
    rows = [_row(540, "call", 0.3, anomalous=True, reason="ghost_quote")]
    out = compressor.compress(_chain(rows), Strategy.RAW)
    assert len(out.rows) == 0


def test_anomalous_illiquid_excluded(compressor):
    rows = [_row(540, "call", 0.3, anomalous=True, reason="illiquid")]
    out = compressor.compress(_chain(rows), Strategy.RAW)
    assert len(out.rows) == 0


def test_anomalous_inverted_included(compressor):
    rows = [_row(540, "call", 0.3, anomalous=True, reason="inverted_spread")]
    out = compressor.compress(_chain(rows), Strategy.RAW)
    assert len(out.rows) == 1
    assert out.rows[0].is_anomalous


def test_delta_none_uses_strike_proximity(compressor):
    rows = [
        _row(540, "call", None),   # at-the-money — keep
        _row(540 * 1.20, "call", None),  # far OTM — drop
    ]
    out = compressor.compress(_chain(rows), Strategy.VERTICAL_SPREAD)
    strikes = [r.strike for r in out.rows]
    assert 540 in strikes
    assert 540 * 1.20 not in strikes


def test_token_estimate_calculated(compressor):
    rows = [_row(540, "call", 0.3), _row(545, "put", -0.3)]
    out = compressor.compress(_chain(rows), Strategy.IRON_CONDOR)
    assert out.token_estimate_compressed == len(out.rows) * 80


def test_token_savings_percentage(compressor):
    rows = [_row(540 + i, "call", 0.5) for i in range(100)]
    chain = _chain(rows)
    out = compressor.compress(chain, Strategy.IRON_CONDOR)
    raw_tokens = out.token_estimate_raw
    savings = (1 - out.token_estimate_compressed / raw_tokens) * 100
    assert savings >= 0
    assert f"{int(round(savings))}%"
