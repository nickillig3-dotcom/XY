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
            sl_pct = rng.choice([0.003, 0.005, 0.008, 0.01])
            out.append(StrategyConfig(
                symbol=sym, fast=fast, slow=slow,
                stop_loss_pct=sl_pct, risk_fraction=risk_fraction,
                direction="both"
            ))
    return out
