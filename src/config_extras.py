from __future__ import annotations
from pathlib import Path

DEFAULTS = {
    "portfolio": {
        "correlation_cap": 0.60,
        "max_weight_per_strategy": 0.40,
        "max_weight_per_market": 0.60,
    },
    "forward": {
        "oos_fraction": 0.60,
        "n_splits": 1,
        "min_passes": 1,
    },
    "paper": {
        "lookback_days": 14,
        "poll_seconds": 300,
        "analyze_trades": True,
    },
    "live": {
        "killswitch_path": "results/live/KILL",
        "max_notional": 0.0,            # 0 = nur Leverage-Grenze
        "daily_loss_limit_pct": 0.02,   # 2% vom Tages-Start-Equity
        "use_portfolio_weights": True   # Risk fraction pro Trade * Portfolio-Gewicht
    },
}

def load_extras(cfg_path: str = "config/config.yaml") -> dict:
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    out = {}
    for section, defs in DEFAULTS.items():
        sec = data.get(section, {}) or {}
        merged = dict(defs); merged.update(sec)
        out[section] = merged
    return out
