from __future__ import annotations
from pydantic import BaseModel, Field, model_validator

class StrategyConfig(BaseModel):
    symbol: str
    timeframe: str = Field(default="1m")  # "1m" | "5m" | "15m"
    fast: int = Field(ge=3, le=300)
    slow: int = Field(ge=5, le=600)
    stop_loss_pct: float = Field(gt=0, lt=0.2)
    risk_fraction: float = Field(gt=0, lt=0.05)
    fee_rate: float = Field(default=0.0004, ge=0)
    slippage: float = Field(default=0.0002, ge=0)
    direction: str = Field(default="both")  # "long" | "short" | "both"

    @model_validator(mode="after")
    def _check(self):
        if self.fast >= self.slow:
            raise ValueError("fast must be < slow")
        if self.direction not in ("long", "short", "both"):
            raise ValueError("direction must be 'long', 'short', or 'both'")
        if self.timeframe not in ("1m", "5m", "15m"):
            raise ValueError("timeframe must be one of: 1m, 5m, 15m")
        return self
