from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple
import json
import math
import pandas as pd
from .strategy_blocks import StrategyConfig
from .backtest import _load_ohlcv, backtest_one
from .evaluation import evaluate_and_save

def _key_no_tf(d: dict) -> str:
    return f"{d['symbol']}|{int(d['fast'])}|{int(d['slow'])}|{float(d['stop_loss_pct'])}"

def _split_segments(n: int, total_oos_frac: float, n_splits: int) -> List[Tuple[int,int]]:
    """
    Teilt die letzten total_oos_frac der Daten in n_splits gleich große OOS-Segmente.
    Indexgrenzen sind [start, end) (end-exklusiv).
    """
    total_len = max(1, int(n * total_oos_frac))
    total_len = min(total_len, n)
    seg_len = max(1, total_len // n_splits)
    # Stelle sicher, dass wir genau n_splits Segmente bekommen
    start = n - seg_len * n_splits
    segs = []
    for i in range(n_splits):
        a = start + i * seg_len
        b = a + seg_len if i < n_splits - 1 else n  # Rest in letztes Segment
        segs.append((a, b))
    return segs

def run_forward_multi(strategies: List[StrategyConfig],
                      cfg,
                      ohlcv_dir: Path,
                      out_dir: Path,
                      total_oos_frac: float = 0.60,
                      n_splits: int = 3,
                      min_passes: int | None = None) -> Dict:
    """
    Multi-Split Forward:
      - erzeugt n_splits OOS-Segmente über die letzten total_oos_frac der Daten
      - bewertet je Split und speichert metrics/accepted
      - aggregiert Accepted-Strategien: min_passes von n_splits müssen bestanden sein
      - schreibt forward_tests/accepted_strategies.json (aggregiert)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if min_passes is None:
        min_passes = n_splits

    # Cache für OHLCV
    data_cache: Dict[str, pd.DataFrame] = {}

    # Sammle Metrics je Split
    per_split_counts = []
    accepted_keys_per_split: List[set] = []
    split_dirs: List[Path] = []

    for split_idx in range(1, n_splits + 1):
        rows = []
        for s in strategies:
            if s.symbol not in data_cache:
                data_cache[s.symbol] = _load_ohlcv(s.symbol, ohlcv_dir)
            df_full = data_cache[s.symbol]
            if len(df_full) < 100:
                continue

            segs = _split_segments(len(df_full), total_oos_frac, n_splits)
            a, b = segs[split_idx - 1]
            df_oos = df_full.iloc[a:b]
            if df_oos.empty:
                continue

            m, _ = backtest_one(df_oos, s, cfg.risk.starting_capital, cfg.risk.max_leverage)
            m["timeframe"] = s.timeframe
            rows.append(m)

        # Output je Split
        split_dir = out_dir / f"split_{split_idx:02d}"
        split_dir.mkdir(parents=True, exist_ok=True)
        split_dirs.append(split_dir)

        df_metrics = pd.DataFrame(rows)
        (split_dir / "metrics.csv").write_text(df_metrics.to_csv(index=False), encoding="utf-8")
        (split_dir / "strategies.json").write_text(
            json.dumps([s.model_dump() for s in strategies], indent=2),
            encoding="utf-8"
        )

        # Bewertung je Split
        df_acc = evaluate_and_save(str(split_dir / "metrics.csv"),
                                   str(split_dir / "strategies.json"),
                                   str(split_dir))
        acc = df_acc[df_acc.get("is_accepted", False) == True]
        count_acc = int(acc.shape[0])
        per_split_counts.append(count_acc)

        # Set akzeptierter Keys (ohne TF, identisch zu main.py-Intersection-Logik)
        # Falls evaluate_and_save accepted_strategies.json generiert hat, lese daraus
        acc_path = split_dir / "accepted_strategies.json"
        if acc_path.exists():
            accepted = json.loads(acc_path.read_text(encoding="utf-8"))
            keys = {_key_no_tf(d) for d in accepted}
        else:
            # Fallback: aus df_acc
            keys = {_key_no_tf(row) for _, row in acc.to_dict(orient="index").items()}
        accepted_keys_per_split.append(keys)

    # Aggregation über Splits: min_passes
    passes: Dict[str, int] = {}
    first_seen: Dict[str, dict] = {}
    for split_dir in split_dirs:
        acc_path = split_dir / "accepted_strategies.json"
        if not acc_path.exists():
            continue
        accepted = json.loads(acc_path.read_text(encoding="utf-8"))
        for d in accepted:
            k = _key_no_tf(d)
            passes[k] = passes.get(k, 0) + 1
            if k not in first_seen:
                first_seen[k] = d

    kept = [first_seen[k] for k, c in passes.items() if c >= int(min_passes)]
    # Schreibe aggregierte Accepted
    agg_path = out_dir / "accepted_strategies.json"
    agg_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")

    return {
        "per_split_counts": per_split_counts,
        "accepted_aggregated": len(kept),
        "splits": n_splits,
        "min_passes": int(min_passes),
        "out_dir": str(out_dir),
    }
