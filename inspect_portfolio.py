from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
from collections import defaultdict
from src.strategy_blocks import StrategyConfig
from src.backtest import _load_ohlcv, backtest_one
from src.config_loader import load_config

root = Path(".")
sel_path = root / "results/portfolios/selection.json"
acc_path = root / "results/backtests/accepted_strategies.json"
ohlcv_dir = root / "data/processed/ohlcv"

sel = json.loads(sel_path.read_text(encoding="utf-8"))
acc = json.loads(acc_path.read_text(encoding="utf-8"))
cfg = load_config("config/config.yaml")

def make_key(d: dict) -> str:
    tf = d.get("timeframe","1m")
    return f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}|{tf}"

# Map: key -> strategy dict
acc_map = { make_key(d): d for d in acc }

weights = sel.get("weights",{})
rows=[]
rets={}
for k, w in sorted(weights.items(), key=lambda kv: kv[1], reverse=True):
    strat_d = acc_map.get(k)
    if not strat_d:
        # Fallback: versuche ohne timeframe-Anteil
        parts = k.split("|")
        tf = parts[-1] if len(parts) >= 5 else "1m"
        base = "|".join(parts[:-1])
        cand = [d for d in acc if make_key(d).startswith(base)]
        strat_d = cand[0] if cand else None
    if not strat_d:
        continue

    s = StrategyConfig(**strat_d)
    df = _load_ohlcv(s.symbol, ohlcv_dir)
    m, eq = backtest_one(df, s, cfg.risk.starting_capital, cfg.risk.max_leverage)
    # tägliche Renditen
    daily = (eq.resample("D").last().pct_change().dropna())
    rets[k] = daily

    rows.append({
        "key": k, "symbol": s.symbol, "timeframe": s.timeframe,
        "fast": s.fast, "slow": s.slow, "stop_loss_pct": s.stop_loss_pct,
        "weight": w, "net_return": m["net_return"], "max_drawdown": m["max_drawdown"]
    })

# Tabelle & Speichern
df = pd.DataFrame(rows).sort_values("weight", ascending=False)
out_csv = root / "results/portfolios/selected_detail.csv"
df.to_csv(out_csv, index=False)
print("[OK] saved", out_csv)

# Korrelationen der täglichen Renditen
if rets:
    mat = pd.concat(rets, axis=1).corr()
    print("\nCorrelation matrix (daily returns):")
    print(mat.round(2).to_string())
else:
    print("No return series found.")
