from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import json
import pandas as pd
from .strategy_blocks import StrategyConfig
from .backtest import backtest_one, _load_ohlcv
from .config_loader import GlobalConfig

def forward_test_all(strategies: List[StrategyConfig], cfg: GlobalConfig, ohlcv_dir: Path, oos_fraction: float = 0.30) -> pd.DataFrame:
    """
    Einfaches OOS-Testen: nimmt die letzten oos_fraction der Daten als Out-of-Sample
    und wertet die Strategien dort aus (nutzt denselben backtest_one, aber auf OOS-Slice).
    """
    results = []
    cache: Dict[str, pd.DataFrame] = {}
    for s in strategies:
        if s.symbol not in cache:
            cache[s.symbol] = _load_ohlcv(s.symbol, ohlcv_dir)
        df = cache[s.symbol]
        if len(df) < 500:  # minimaler Puffer
            continue
        split = max(1, int(len(df) * (1 - oos_fraction)))
        df_oos = df.iloc[split:]
        m, _ = backtest_one(df_oos, s, cfg.risk.starting_capital, cfg.risk.max_leverage)
        m["phase"] = "forward_oos"
        results.append(m)
    return pd.DataFrame(results)

def save_metrics_and_eval(df: pd.DataFrame, strategies_json: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.csv").write_text(df.to_csv(index=False), encoding="utf-8")
    # gleiche Akzeptanz-Schwellen wie Backtest verwenden
    from .evaluation import evaluate_and_save
    evaluate_and_save(str(out_dir / "metrics.csv"), str(strategies_json), str(out_dir))
