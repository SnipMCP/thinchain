from typing import Optional
from ..models.chain import OptionChain, OptionRow, Strategy, OptionType

TOKENS_PER_ROW = 80

EXCLUDED_ANOMALIES = {"ghost_quote", "illiquid"}


def _pre_filter(rows: list[OptionRow]) -> list[OptionRow]:
    """Exclude unusable anomalies."""
    return [r for r in rows if not (r.is_anomalous and r.anomaly_reason in EXCLUDED_ANOMALIES)]


def _in_delta_range(row: OptionRow, lo: float, hi: float, underlying: float) -> bool:
    if row.delta is not None:
        return lo <= row.delta <= hi
    # Fallback: strike proximity — approximate using midpoint of range
    # If range encompasses ATM-ish deltas, keep strikes near underlying
    return abs(row.strike - underlying) <= underlying * 0.05


class Compressor:
    def compress(
        self,
        chain: OptionChain,
        strategy: Strategy,
        delta_range: Optional[tuple[float, float]] = None,
    ) -> OptionChain:
        rows = _pre_filter(chain.rows)
        underlying = chain.underlying_price

        if delta_range is not None:
            lo, hi = delta_range
            result = [r for r in rows if r.delta is not None and lo <= abs(r.delta) <= hi]
            # Fallback for None-delta rows: use strike proximity
            result += [r for r in rows if r.delta is None and abs(r.strike - underlying) <= underlying * 0.05]
        elif strategy == Strategy.RAW:
            result = rows
        elif strategy == Strategy.IRON_CONDOR:
            result = [
                r for r in rows
                if (r.option_type == OptionType.PUT and r.delta is not None and 0.05 <= abs(r.delta) <= 0.45)
                or (r.option_type == OptionType.CALL and r.delta is not None and 0.05 <= abs(r.delta) <= 0.45)
                or (r.delta is None and abs(r.strike - underlying) <= underlying * 0.10)
            ]
        elif strategy == Strategy.VERTICAL_SPREAD:
            result = [
                r for r in rows
                if (r.delta is not None and 0.20 <= abs(r.delta) <= 0.50)
                or (r.delta is None and abs(r.strike - underlying) <= underlying * 0.05)
            ]
        elif strategy == Strategy.STRADDLE:
            sorted_by_proximity = sorted(rows, key=lambda r: abs(r.strike - underlying))
            seen_strikes: list[float] = []
            for r in sorted_by_proximity:
                if r.strike not in seen_strikes:
                    seen_strikes.append(r.strike)
                if len(seen_strikes) >= 5:
                    break
            allowed = set(seen_strikes[:5])
            result = [r for r in rows if r.strike in allowed]
        elif strategy == Strategy.STRANGLE:
            result = [
                r for r in rows
                if (r.delta is not None and 0.15 <= abs(r.delta) <= 0.35)
                or (r.delta is None and abs(r.strike - underlying) <= underlying * 0.07)
            ]
        elif strategy == Strategy.COVERED_CALL:
            result = [
                r for r in rows
                if r.option_type == OptionType.CALL
                and (
                    (r.delta is not None and 0.20 <= r.delta <= 0.40)
                    or (r.delta is None and abs(r.strike - underlying) <= underlying * 0.05)
                )
            ]
        elif strategy == Strategy.NAKED_PUT:
            result = [
                r for r in rows
                if r.option_type == OptionType.PUT
                and (
                    (r.delta is not None and -0.35 <= r.delta <= -0.15)
                    or (r.delta is None and abs(r.strike - underlying) <= underlying * 0.05)
                )
            ]
        elif strategy == Strategy.BUTTERFLY:
            sorted_by_proximity = sorted(rows, key=lambda r: abs(r.strike - underlying))
            strikes: list[float] = []
            for r in sorted_by_proximity:
                if r.strike not in strikes:
                    strikes.append(r.strike)
                if len(strikes) >= 3:
                    break
            allowed = set(strikes)
            result = [r for r in rows if r.strike in allowed]
        else:
            result = rows

        chain.rows = result
        chain.compressed_row_count = len(result)
        chain.token_estimate_compressed = len(result) * TOKENS_PER_ROW
        return chain
