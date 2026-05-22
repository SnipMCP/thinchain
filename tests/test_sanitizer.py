import math
import pytest
from thinchain.core.sanitizer import Sanitizer, num, num_int, clamp_delta, normalize_theta, enforce_delta_sign


@pytest.fixture
def sanitizer():
    return Sanitizer()


def _row(option_type="call", bid=1.0, ask=1.1, **kwargs):
    base = {
        "strike": 100,
        "expiration": "2026-06-19",
        "option_type": option_type,
        "bid": bid,
        "ask": ask,
        "last": 1.05,
        "volume": 100,
        "open_interest": 200,
        "greeks": {"delta": 0.3, "gamma": 0.01, "theta": -0.05, "vega": 0.1, "mid_iv": 0.2},
    }
    has_greeks_override = "greeks" in kwargs
    greeks_override = kwargs.pop("greeks", None)
    base.update(kwargs)
    if has_greeks_override:
        base["greeks"] = greeks_override
    return base


def test_ghost_quote_both_zero(sanitizer):
    r = sanitizer.sanitize_row(_row(bid=0.0, ask=0.0))
    assert r.bid is None
    assert r.ask is None
    assert r.is_anomalous
    assert r.anomaly_reason == "ghost_quote"


def test_ghost_quote_partial_zero_ask(sanitizer):
    r = sanitizer.sanitize_row(_row(bid=1.5, ask=0.0))
    assert r.bid is None and r.ask is None
    assert r.is_anomalous
    assert r.anomaly_reason == "bad_spread"


def test_inverted_spread(sanitizer):
    r = sanitizer.sanitize_row(_row(bid=2.5, ask=1.0))
    assert r.bid is None and r.ask is None
    assert r.is_anomalous
    assert r.anomaly_reason == "inverted_spread"


def test_string_dash_bid(sanitizer):
    r = sanitizer.sanitize_row(_row(bid="—", ask=1.5))
    assert r.bid is None and r.ask is None
    assert r.anomaly_reason == "bad_spread"


def test_string_empty_ask(sanitizer):
    r = sanitizer.sanitize_row(_row(bid=1.0, ask=""))
    assert r.bid is None and r.ask is None
    assert r.anomaly_reason == "bad_spread"


def test_string_na_greek(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": "N/A", "theta": -0.05, "mid_iv": 0.2}))
    assert r.delta is None
    # Should not crash


def test_delta_upper_bound(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": 1.8, "theta": -0.05, "mid_iv": 0.2}))
    assert r.delta is None
    assert r.is_anomalous
    assert r.anomaly_reason == "delta_out_of_bounds"


def test_delta_lower_bound(sanitizer):
    r = sanitizer.sanitize_row(_row(option_type="put", greeks={"delta": -1.5, "theta": -0.05, "mid_iv": 0.2}))
    assert r.delta is None
    assert r.is_anomalous
    assert r.anomaly_reason == "delta_out_of_bounds"


def test_delta_exactly_one(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": 1.0, "theta": -0.05, "mid_iv": 0.2}))
    assert r.delta == 1.0


def test_positive_theta_normalized(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": 0.3, "theta": 0.05, "mid_iv": 0.2}))
    assert r.theta == -0.05


def test_negative_theta_kept(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": 0.3, "theta": -0.03, "mid_iv": 0.2}))
    assert r.theta == -0.03


def test_put_delta_sign_enforced(sanitizer):
    r = sanitizer.sanitize_row(_row(option_type="put", greeks={"delta": 0.3, "theta": -0.05, "mid_iv": 0.2}))
    assert r.delta == -0.3


def test_call_delta_sign_enforced(sanitizer):
    r = sanitizer.sanitize_row(_row(option_type="call", greeks={"delta": -0.3, "theta": -0.05, "mid_iv": 0.2}))
    assert r.delta == 0.3


def test_iv_extreme_high(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": 0.3, "theta": -0.05, "mid_iv": 55.0}))
    assert r.implied_volatility is None
    assert r.is_anomalous
    assert r.anomaly_reason == "iv_extreme"


def test_iv_extreme_low(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": 0.3, "theta": -0.05, "mid_iv": -0.1}))
    assert r.implied_volatility is None
    assert r.is_anomalous
    assert r.anomaly_reason == "iv_extreme"


def test_iv_valid_boundary(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": 0.3, "theta": -0.05, "mid_iv": 49.9}))
    assert r.implied_volatility == 49.9


def test_wide_spread_flagged(sanitizer):
    r = sanitizer.sanitize_row(_row(bid=0.50, ask=5.00))
    assert r.bid == 0.50
    assert r.ask == 5.00
    assert r.is_anomalous
    assert r.anomaly_reason == "wide_spread"


def test_illiquid_row(sanitizer):
    r = sanitizer.sanitize_row(_row(volume=0, open_interest=0))
    assert r.is_anomalous
    assert r.anomaly_reason == "illiquid"


def test_greeks_object_missing(sanitizer):
    raw = _row()
    del raw["greeks"]
    r = sanitizer.sanitize_row(raw)
    assert r.delta is None
    assert r.theta is None
    assert r.implied_volatility is None


def test_greeks_object_null(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks=None))
    assert r.delta is None
    assert r.theta is None
    assert r.implied_volatility is None


def test_nan_delta_coerced(sanitizer):
    r = sanitizer.sanitize_row(_row(greeks={"delta": float("nan"), "theta": -0.05, "mid_iv": 0.2}))
    assert r.delta is None


def test_clean_row_passes_through(sanitizer):
    r = sanitizer.sanitize_row(_row())
    assert r.bid == 1.0
    assert r.ask == 1.1
    assert r.delta == 0.3
    assert not r.is_anomalous


def test_underlying_price_zero_returns_empty_chain(sanitizer):
    chain = sanitizer.sanitize_chain([_row()], "SPY", 0.0, "2026-06-19", "tradier")
    assert chain.rows == []
    assert chain.data_quality == "circuit_breaker_active"


# Helper unit tests
def test_num_handles_strings():
    assert num("—") is None
    assert num("") is None
    assert num("N/A") is None
    assert num("1.5") == 1.5


def test_num_handles_nan_inf():
    assert num(float("nan")) is None
    assert num(float("inf")) is None
    assert num(float("-inf")) is None


def test_num_int():
    assert num_int("5") == 5
    assert num_int(None) is None
    assert num_int("") is None


def test_clamp_delta():
    assert clamp_delta(0.5) == 0.5
    assert clamp_delta(1.0) == 1.0
    assert clamp_delta(1.1) is None
    assert clamp_delta(-1.1) is None


def test_normalize_theta():
    assert normalize_theta(0.05) == -0.05
    assert normalize_theta(-0.05) == -0.05
    assert normalize_theta(None) is None


def test_enforce_delta_sign():
    assert enforce_delta_sign(0.3, "put") == -0.3
    assert enforce_delta_sign(-0.3, "call") == 0.3
    assert enforce_delta_sign(None, "put") is None
