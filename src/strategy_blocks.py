from __future__ import annotations
from pydantic import BaseModel, Field, model_validator

class StrategyConfig(BaseModel):
    symbol: str
    fast: int = Field(ge=5, le=300)
    slow: int = Field(ge=10, le=600)
    stop_loss_pct: float = Field(gt=0, lt=0.2)   # 0.003 = 0.3%
    risk_fraction: float = Field(gt=0, lt=0.05)  # Anteil Equity pro Trade
    fee_rate: float = Field(default=0.0004, ge=0)  # 4 bp pro Seite (Beispiel)
    slippage: float = Field(default=0.0002, ge=0)  # 2 bp Slippage
    direction: str = Field(default="both")         # "long" | "short" | "both"

    @model_validator(mode="after")
    def _check(self):
        if self.fast >= self.slow:
            raise ValueError("fast must be < slow")
        if self.direction not in ("long", "short", "both"):
            raise ValueError("direction must be 'long', 'short', or 'both'")
        return self

