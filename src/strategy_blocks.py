from __future__ import annotations
from pydantic import BaseModel

class StrategyConfig(BaseModel):
    symbol: str
    fast: int
    slow: int
    stop_loss_pct: float
    risk_fraction: float
    direction: str = "both"   # "both", "long", "short"
    timeframe: str = "15m"    # "1m", "5m", "15m"
    fee_rate: float = 0.0004
    slippage: float = 0.0002
    # NEU: Filter (optional)
    trend_tol: float = 0.0     # z.B. 0.001 = 0.1%
    atr_thresh: float = 0.0    # z.B. 0.005 = 0.5%
    atr_period: int = 14
