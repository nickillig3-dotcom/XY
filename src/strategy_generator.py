from __future__ import annotations
from typing import List, Iterable
import random
from .strategy_blocks import StrategyConfig

def generate_ma_crossover_candidates(markets: Iterable[str], risk_fraction: float, n_per_symbol: int = 20) -> List[StrategyConfig]:
    rng = random.Random(42)
    out: List[StrategyConfig] = []
    for sym in markets:
        for _ in range(n_per_symbol):
            tf = rng.choices(["1m","5m","15m"], weights=[1,3,2], k=1)[0]
            # kleinere Fenster, damit auf aggregierten Bars genug Signale entstehen
            fast = rng.randint(5, 20) if tf == "1m" else rng.randint(3, 12)
            slow = rng.randint(fast + 5, 60) if tf == "1m" else rng.randint(fast + 3, 40)
            sl_pct = rng.choice([0.005, 0.008, 0.01, 0.015, 0.02])  # 0.5–2.0%
            out.append(StrategyConfig(
                symbol=sym,
                timeframe=tf,
                fast=fast, slow=slow,
                stop_loss_pct=sl_pct,
                risk_fraction=risk_fraction,
                direction="both"
            ))
    return out
