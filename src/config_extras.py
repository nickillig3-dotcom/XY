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
    },
}

def load_extras(cfg_path: str = "config/config.yaml") -> dict:
    """Liest optionale Sektionen und merged DEFAULTS + alle Keys aus YAML (Pass-Through)."""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}

    out = {}
    for section, defs in DEFAULTS.items():
        sec = data.get(section, {}) or {}
        merged = dict(defs)           # Defaults
        merged.update(sec)            # ALLE Keys aus YAML durchreichen
        out[section] = merged
    return out
