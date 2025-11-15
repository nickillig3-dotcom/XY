from __future__ import annotations
from pathlib import Path
import pandas as pd, json

def _row_key(r: dict) -> str:
    tf = r.get("timeframe", "1m")
    return f"{r['symbol']}|f{int(r['fast'])}|s{int(r['slow'])}|sl{float(r['stop_loss_pct']):.4f}|{tf}"

def evaluate_and_save(metrics_csv: str, strategies_json: str, out_dir: str,
                      min_trades: int = 10,            # etwas lockerer für kurze Splits
                      max_mdd_floor: float = -0.60,
                      min_avg_month: float = 0.00,
                      worst_month_floor: float = -0.50):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(metrics_csv)

    def _accept(row):
        trades = int(row.get("trades", 0))
        mdd = float(row.get("max_drawdown", 0.0))
        if trades < min_trades or mdd < max_mdd_floor:
            return False
        am = float(row.get("avg_monthly_return", 0.0))
        wm = float(row.get("worst_month", 0.0))
        monthly_available = (abs(am) + abs(wm)) > 1e-12
        if monthly_available:
            return (am >= min_avg_month) and (wm > worst_month_floor) and (float(row.get("net_return", 0.0)) > 0.0)
        else:
            # kurzer OOS-Split: fallback auf NetReturn > 0
            return float(row.get("net_return", 0.0)) > 0.0

    df["is_accepted"] = df.apply(_accept, axis=1)
    (out / "accepted_metrics.csv").write_text(df.to_csv(index=False), encoding="utf-8")

    # Strategien mappen
    try:
        strats = json.loads(Path(strategies_json).read_text(encoding="utf-8"))
    except Exception:
        strats = []
    acc_keys = {_row_key(r) for _, r in df[df["is_accepted"]].iterrows()}

    def _skey(d):
        tf = d.get("timeframe", "1m")
        return f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}|{tf}"

    accepted = [s for s in strats if _skey(s) in acc_keys]
    (out / "accepted_strategies.json").write_text(json.dumps(accepted, indent=2), encoding="utf-8")
    return df
