from pydantic import BaseModel
from typing import Optional


class ToolError(BaseModel):
    error: str
    message: str
    symbol: Optional[str] = None


class ChainStats(BaseModel):
    raw_rows: int
    compressed_rows: int
    anomalous_rows_removed: int
    token_estimate_raw: int
    token_estimate_compressed: int


class CompressedChainResponse(BaseModel):
    symbol: str
    expiration: str
    strategy_applied: str
    underlying_price: float
    data_quality: str
    token_savings: str
    rows: list[dict]
    stats: ChainStats


class QuoteResponse(BaseModel):
    symbol: str
    price: float
    is_trustworthy: bool
    anomalies: list[str]
    broker: str


class CircuitStatusResponse(BaseModel):
    symbol: str
    expiration: str
    status: str
    anomaly_rate: float
    serving_from_cache: bool
    recommendation: str
    broker: str
