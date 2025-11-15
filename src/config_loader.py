from __future__ import annotations
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field, model_validator
import yaml

ALLOWED_MARKETS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}

class Paths(BaseModel):
    raw: str
    processed: str

class Risk(BaseModel):
    starting_capital: float = Field(gt=0)
    risk_per_trade_target: float = Field(gt=0, lt=0.05)
    risk_per_trade_max: float = Field(gt=0, lt=0.05)
    max_leverage: float = Field(gt=0, le=5)

    @model_validator(mode="after")
    def _check_ranges(self):
        if not 0.0025 <= self.risk_per_trade_target <= 0.015:
            raise ValueError("risk_per_trade_target should be between 0.25% and 1.5%")
        if not self.risk_per_trade_max <= 0.02:
            raise ValueError("risk_per_trade_max must be <= 2%")
        if self.risk_per_trade_target > self.risk_per_trade_max:
            raise ValueError("risk_per_trade_target cannot exceed risk_per_trade_max")
        return self

class GlobalConfig(BaseModel):
    markets: List[str]
    paths: Paths
    risk: Risk

    @model_validator(mode="after")
    def _validate_markets(self):
        unknown = set(self.markets) - ALLOWED_MARKETS
        if unknown:
            raise ValueError(f"Unsupported markets: {sorted(unknown)}. Allowed: {sorted(ALLOWED_MARKETS)}")
        return self

def load_config(path: str | Path) -> GlobalConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = GlobalConfig(**raw)
    return cfg

