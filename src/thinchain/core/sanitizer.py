import math
from typing import Optional
from ..models.chain import OptionRow, OptionChain, OptionType

TOKENS_PER_ROW = 80


def num(v: object) -> Optional[float]:
    """Coerce any broker value to float | None. NaN/Inf/empty/dash → None."""
    if v is None:
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def num_int(v: object) -> Optional[int]:
    result = num(v)
    return int(result) if result is not None else None


def clamp_delta(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return None if abs(v) > 1.0 else v


def normalize_theta(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return -abs(v)


def enforce_delta_sign(delta: Optional[float], option_type: str) -> Optional[float]:
    if delta is None:
        return None
    if option_type == "put":
        return -abs(delta)
    return abs(delta)


class Sanitizer:
    def sanitize_row(self, raw: dict) -> OptionRow:
        option_type_str = raw.get("option_type", "call")
        try:
            option_type = OptionType(option_type_str)
        except ValueError:
            option_type = OptionType.CALL

        is_anomalous = False
        anomaly_reason: Optional[str] = None

        # Bid/Ask: spread gate
        bid_raw = num(raw.get("bid"))
        ask_raw = num(raw.get("ask"))
        bid_val = bid_raw if bid_raw is not None else 0.0
        ask_val = ask_raw if ask_raw is not None else 0.0

        bid_out: Optional[float] = bid_raw
        ask_out: Optional[float] = ask_raw

        spread_bad = False
        if bid_raw is None or ask_raw is None or bid_val <= 0 or ask_val <= 0 or bid_val >= ask_val:
            spread_bad = True

        if spread_bad:
            if bid_val == 0.0 and ask_val == 0.0 and bid_raw is not None and ask_raw is not None:
                anomaly_reason = "ghost_quote"
            elif bid_raw is not None and ask_raw is not None and bid_val > 0 and ask_val > 0 and bid_val >= ask_val:
                anomaly_reason = "inverted_spread"
            else:
                anomaly_reason = "bad_spread"
            bid_out = None
            ask_out = None
            is_anomalous = True

        # Greeks
        greeks = raw.get("greeks")
        if greeks is None:
            greeks = {}

        delta = clamp_delta(num(greeks.get("delta")))
        # Track raw delta presence to detect out-of-bounds
        raw_delta = num(greeks.get("delta"))
        if raw_delta is not None and delta is None:
            is_anomalous = True
            if anomaly_reason is None:
                anomaly_reason = "delta_out_of_bounds"

        delta = enforce_delta_sign(delta, option_type.value)

        gamma = num(greeks.get("gamma"))
        theta = normalize_theta(num(greeks.get("theta")))
        vega = num(greeks.get("vega"))

        # IV: Tradier uses mid_iv; Polygon flattens it
        iv_raw = greeks.get("mid_iv")
        if iv_raw is None:
            iv_raw = greeks.get("implied_volatility")
        if iv_raw is None:
            iv_raw = raw.get("implied_volatility")
        iv = num(iv_raw)
        if iv is not None and (iv < 0 or iv > 50.0):
            iv = None
            is_anomalous = True
            if anomaly_reason is None:
                anomaly_reason = "iv_extreme"

        # Wide spread check (only if spread is valid)
        if not spread_bad and bid_out is not None and ask_out is not None:
            mid = (bid_out + ask_out) / 2
            if mid > 0 and (ask_out - bid_out) / mid > 1.0:
                is_anomalous = True
                if anomaly_reason is None:
                    anomaly_reason = "wide_spread"

        # Illiquid check
        volume = num_int(raw.get("volume"))
        oi = num_int(raw.get("open_interest"))
        if (volume == 0 or volume is None) and (oi == 0 or oi is None):
            is_anomalous = True
            if anomaly_reason is None:
                anomaly_reason = "illiquid"

        return OptionRow(
            strike=num(raw.get("strike")) or 0.0,
            expiration=str(raw.get("expiration", "")),
            option_type=option_type,
            bid=bid_out,
            ask=ask_out,
            last=num(raw.get("last")),
            volume=volume,
            open_interest=oi,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            implied_volatility=iv,
            is_anomalous=is_anomalous,
            anomaly_reason=anomaly_reason,
        )

    def sanitize_chain(
        self,
        raw_rows: list[dict],
        symbol: str,
        underlying_price: float,
        expiration: str,
        broker: str,
    ) -> OptionChain:
        raw_count = len(raw_rows)

        if underlying_price is None or underlying_price <= 0:
            return OptionChain(
                symbol=symbol,
                underlying_price=0.0,
                expiration=expiration,
                rows=[],
                raw_row_count=raw_count,
                compressed_row_count=0,
                token_estimate_raw=raw_count * TOKENS_PER_ROW,
                token_estimate_compressed=0,
                data_quality="circuit_breaker_active",
                broker=broker,
            )

        sanitized = [self.sanitize_row(r) for r in raw_rows]

        return OptionChain(
            symbol=symbol,
            underlying_price=underlying_price,
            expiration=expiration,
            rows=sanitized,
            raw_row_count=raw_count,
            compressed_row_count=len(sanitized),
            token_estimate_raw=raw_count * TOKENS_PER_ROW,
            token_estimate_compressed=len(sanitized) * TOKENS_PER_ROW,
            data_quality="clean",
            broker=broker,
        )
