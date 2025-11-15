from __future__ import annotations
from typing import List, Iterable
import random
from .strategy_blocks import StrategyConfig

def generate_ma_crossover_candidates(markets: Iterable[str], risk_fraction: float, n_per_symbol: int = 20) -> List[StrategyConfig]:
    rng = random.Random(42)
    out: List[StrategyConfig] = []
    for sym in markets:
        for _ in range(n_per_symbol):
            fast = rng.randint(5, 20)
            slow = rng.randint(fast + 5, 60)
            sl_pct = rng.choice([0.003, 0.005, 0.008, 0.010, 0.015, 0.020])
            tf = rng.choice(["5m","15m"])
            # NEU: moderate Filter-Kandidaten
            trend = rng.choice([0.0, 0.001, 0.002, 0.003])     # 0.0–0.3%
            atr   = rng.choice([0.0, 0.002, 0.005, 0.010])     # 0.0–1.0%
            out.append(StrategyConfig(
                symbol=sym, fast=fast, slow=slow,
                stop_loss_pct=sl_pct, risk_fraction=risk_fraction,
                timeframe=tf, direction="both",
                trend_tol=trend, atr_thresh=atr, atr_period=14
            ))
    return out
