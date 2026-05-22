from pydantic import BaseModel
from typing import Optional
from enum import Enum


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class Strategy(str, Enum):
    IRON_CONDOR = "iron_condor"
    VERTICAL_SPREAD = "vertical_spread"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    COVERED_CALL = "covered_call"
    NAKED_PUT = "naked_put"
    BUTTERFLY = "butterfly"
    RAW = "raw"


class OptionRow(BaseModel):
    strike: float
    expiration: str
    option_type: OptionType
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    implied_volatility: Optional[float] = None
    is_anomalous: bool = False
    anomaly_reason: Optional[str] = None


class OptionChain(BaseModel):
    symbol: str
    underlying_price: float
    expiration: str
    rows: list[OptionRow]
    raw_row_count: int
    compressed_row_count: int
    token_estimate_raw: int
    token_estimate_compressed: int
    data_quality: str
    broker: str
