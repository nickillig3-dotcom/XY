from __future__ import annotations
from pathlib import Path
from typing import Dict
import json
import pandas as pd

# Project thresholds (see docs):
# - avg monthly return >= 2%
# - max drawdown <= 30% (i.e., value is >= -0.30 because drawdown is negative)
# - worst month >= -10%
# - trades >= 50 (use 50 as the lower bound of the 50–100 guidance)
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "avg_monthly_return_min": 0.02,
    "max_drawdown_abs_max": 0.30,
    "worst_month_min": -0.10,
    "min_trades": 50,
}

def _reason(row: pd.Series, th: Dict[str, float]) -> str:
    reasons = []
    if row.get("avg_monthly_return", 0.0) < th["avg_monthly_return_min"]:
        reasons.append(f"avg_monthly_return<{th['avg_monthly_return_min']:.2%}")
    if row.get("max_drawdown", 0.0) < -th["max_drawdown_abs_max"]:
        reasons.append(f"max_drawdown>{th['max_drawdown_abs_max']:.0%}")
    if row.get("worst_month", 0.0) < th["worst_month_min"]:
        reasons.append(f"worst_month<{th['worst_month_min']:.0%}")
    if row.get("trades", 0) < th["min_trades"]:
        reasons.append(f"trades<{th['min_trades']}")
    return ";".join(reasons)

def evaluate_and_save(metrics_csv: str, strategies_json: str, out_dir: str = "results/backtests", thresholds: Dict[str, float] | None = None) -> pd.DataFrame:
    th = DEFAULT_THRESHOLDS if thresholds is None else thresholds
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(metrics_csv)
    # Flag + Gründe
    df["reason"] = [ _reason(row, th) for _, row in df.iterrows() ]
    df["is_accepted"] = df["reason"].eq("")

    # Speichern der Metriken
    (out / "metrics_with_flags.csv").write_text(df.to_csv(index=False), encoding="utf-8")
    acc = df[df["is_accepted"]].copy()
    (out / "accepted_metrics.csv").write_text(acc.to_csv(index=False), encoding="utf-8")

    # Passende Strategien zur accepted-Liste speichern
    try:
        data = json.loads(Path(strategies_json).read_text(encoding="utf-8"))
        key = lambda d: f"{d['symbol']}|{int(d['fast'])}|{int(d['slow'])}|{float(d['stop_loss_pct'])}"
        strat_map = { key(d): d for d in data }
        acc["__key"] = acc.apply(lambda r: f"{r['symbol']}|{int(r['fast'])}|{int(r['slow'])}|{float(r['stop_loss_pct'])}", axis=1)
        selected = [ strat_map[k] for k in acc["__key"] if k in strat_map ]
        (out / "accepted_strategies.json").write_text(json.dumps(selected, indent=2), encoding="utf-8")
    except Exception:
        (out / "accepted_strategies.json").write_text("[]", encoding="utf-8")
    return df

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Evaluate backtest metrics against acceptance thresholds")
    p.add_argument("--metrics", default="results/backtests/metrics.csv")
    p.add_argument("--strategies", default="results/backtests/strategies.json")
    p.add_argument("--out", default="results/backtests")
    args = p.parse_args()
    df = evaluate_and_save(args.metrics, args.strategies, args.out)
    print(f"[OK] Evaluated. Accepted: {int(df['is_accepted'].sum())} / {len(df)}")
