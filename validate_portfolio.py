from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json, math
import pandas as pd

from src.config_loader import load_config
from src.config_extras import load_extras
from src.strategy_blocks import StrategyConfig
from src.backtest import _load_ohlcv, backtest_one

ROOT = Path(".")
SEL_PATH = ROOT / "results/portfolios/selection.json"
if not SEL_PATH.exists():
    raise SystemExit("selection.json fehlt – bitte vorher 'python .\\main.py --phase portfolio' ausführen.")

sel = json.loads(SEL_PATH.read_text(encoding="utf-8"))
weights: dict[str, float] = sel.get("weights", {})
if not weights:
    raise SystemExit("Keine Gewichte in selection.json gefunden.")

cfg = load_config("config/config.yaml")
extras = load_extras("config/config.yaml")
corr_cap   = float(extras["portfolio"]["correlation_cap"])
max_w      = float(extras["portfolio"]["max_weight_per_strategy"])
market_cap = float(extras["portfolio"]["max_weight_per_market"])

def _key_of(d: dict) -> str:
    tf = d.get("timeframe", "1m")
    return f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}|{tf}"

# ---- 1) Gewicht-Summen & Caps prüfen
sum_w = float(sum(weights.values()))
by_market = defaultdict(float)
viol_strat = []
for k, w in weights.items():
    if w > max_w + 1e-12:
        viol_strat.append((k, w))
    by_market[k.split("|", 1)[0]] += float(w)
viol_market = [(m, v) for m, v in by_market.items() if v > market_cap + 1e-12]

# ---- 2) Korrelation aus Original-Configs rekonstruieren
conf_sources = [
    ROOT / "results/portfolios/accepted_intersection.json",
    ROOT / "results/backtests/accepted_strategies.json",
    ROOT / "results/forward_tests/accepted_strategies.json",
]
confs = []
for p in conf_sources:
    if p.exists():
        try:
            confs.extend(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

# map: full key -> config
keymap = {_key_of(d): d for d in confs}

# fallback: map ohne timeframe
base_map = {}
for d in confs:
    base = f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}"
    base_map.setdefault(base, d)

selected_cfgs: list[dict] = []
for k in weights.keys():
    d = keymap.get(k)
    if not d:
        base = "|".join(k.split("|")[:4])
        if base in base_map:
            d = dict(base_map[base])
            d["timeframe"] = k.split("|")[-1]
    if d:
        selected_cfgs.append(d)

if not selected_cfgs:
    raise SystemExit("Konnte Strategiekonfigurationen nicht rekonstruieren (prüfe accepted_intersection.json).")

# ---- 3) Equity→Returns je Strategie & Korrelation
ohlcv_dir = Path(cfg.paths.processed) / "ohlcv"
rets = {}
for d in selected_cfgs:
    s = StrategyConfig(**d)
    df = _load_ohlcv(s.symbol, ohlcv_dir)
    m, eq = backtest_one(df, s, cfg.risk.starting_capital, cfg.risk.max_leverage)
    if not eq.empty:
        rets[_key_of(d)] = (eq / float(eq.iloc[0])).pct_change().fillna(0.0)

rets_df = pd.concat(rets, axis=1).dropna(how="all")
viol_corr = []
C = None
if rets_df.shape[1] >= 2:
    C = rets_df.corr()
    cols = list(C.columns)
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            a, b = cols[i], cols[j]
            val = float(C.loc[a, b])
            if val > corr_cap + 1e-12:
                viol_corr.append((a, b, val))

# ---- 4) ENB & Report
w = pd.Series(weights, dtype=float)
enb = float(1.0 / (w.pow(2).sum())) if len(w) else 0.0

report = {
    "sum_weights": sum_w,
    "max_w_per_strategy": max_w,
    "max_w_per_market": market_cap,
    "correlation_cap": corr_cap,
    "enb": enb,
    "violations": {
        "strategy_weights": viol_strat,
        "market_caps": viol_market,
        "correlations": viol_corr,
    }
}
out_path = ROOT / "results/portfolios/validation_report.json"
out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

# Console-Ausgabe
ok_sum = abs(sum_w - 1.0) < 1e-6
ok_strat = len(viol_strat) == 0
ok_market = len(viol_market) == 0
ok_corr = len(viol_corr) == 0
status = "PASS" if (ok_sum and ok_strat and ok_market and ok_corr) else "FAIL"

print(f"[{status}] sum={sum_w:.6f} | ENB={enb:.2f} | strat_caps_ok={ok_strat} | market_caps_ok={ok_market} | corr_ok={ok_corr}")
if not ok_strat:
    print("  > Strategy cap violations:", viol_strat)
if not ok_market:
    print("  > Market cap violations:", viol_market)
if not ok_corr:
    print("  > Corr violations (pair, r):", [(a, b, round(r, 3)) for a, b, r in viol_corr])

print(f"[OK] report -> {out_path}")
