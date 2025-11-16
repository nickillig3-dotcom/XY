from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from typing import List, Dict, Set, Tuple

from src.config_loader import load_config
from src.strategy_blocks import StrategyConfig
from src.backtest import _load_ohlcv
from src.signals import recent_entry_signals, make_key

ROOT = Path(".")
PORT = ROOT / "results/portfolios"
BT   = ROOT / "results/backtests"
FW   = ROOT / "results/forward_tests"
OUT  = ROOT / "results/live"; OUT.mkdir(parents=True, exist_ok=True)
SIG_F = OUT / "signals.csv"

def _load_candidates_for_keys(keys: List[str]) -> List[dict]:
    sources = [
        PORT / "accepted_intersection.json",
        BT / "accepted_strategies.json",
        FW / "accepted_strategies.json",
    ]
    confs = []
    for p in sources:
        if p.exists():
            try:
                confs.extend(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
    full = { make_key(d): d for d in confs }
    base = {}
    for d in confs:
        base_key = f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}"
        base.setdefault(base_key, d)

    out = []
    for k in keys:
        d = full.get(k)
        if not d:
            b = "|".join(k.split("|")[:4])
            if b in base:
                d = dict(base[b]); d["timeframe"] = k.split("|")[-1]
        if d:
            out.append(d)
    return out

def _load_existing_keys() -> Set[Tuple[str,str,str]]:
    """(time, strategy_key, action) zur Deduplizierung bereits geloggter Signale."""
    seen: Set[Tuple[str,str,str]] = set()
    if SIG_F.exists():
        try:
            import csv
            with SIG_F.open("r", encoding="utf-8", newline="") as f:
                r = csv.DictReader(f)
                for row in r:
                    seen.add((row.get("time",""), row.get("strategy_key",""), row.get("action","")))
        except Exception:
            pass
    return seen

def main():
    ap = argparse.ArgumentParser(description="Emit entry signals for current portfolio")
    ap.add_argument("--lookback-bars", type=int, default=1, help="check last N bars for fresh entries")
    ap.add_argument("--touch", action="store_true", help="create CSV with header if missing, even if no signals")
    args = ap.parse_args()

    sel_p = PORT / "selection.json"
    if not sel_p.exists():
        raise SystemExit("selection.json fehlt – bitte vorher Portfolio bauen.")
    sel = json.loads(sel_p.read_text(encoding="utf-8"))
    weight_keys = list((sel.get("weights", {}) or {}).keys())
    if not weight_keys:
        raise SystemExit("Keine Gewichte in selection.json – nichts zu tun.")

    cfg = load_config("config/config.yaml")
    ohlcv_dir = Path(cfg.paths.processed) / "ohlcv"
    configs = _load_candidates_for_keys(weight_keys)
    if not configs:
        raise SystemExit("Konnte Strategiekonfigurationen nicht rekonstruieren.")

    if args.touch and not SIG_F.exists():
        with SIG_F.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["time","symbol","timeframe","action","price","stop_px","strategy_key"])
            w.writeheader()

    seen = _load_existing_keys()
    to_append = []
    for d in configs:
        strat = StrategyConfig(**d)
        df = _load_ohlcv(strat.symbol, ohlcv_dir)
        sigs = recent_entry_signals(df, strat, lookback_bars=max(1, args.lookback-bars if hasattr(args,'lookback-bars') else args.lookback_bars))
        for s in sigs:
            s["strategy_key"] = make_key(d)
            key = (s["time"], s["strategy_key"], s["action"])
            if key not in seen:
                to_append.append(s)

    if not to_append:
        print("[OK] Keine neuen Entry-Signale im gewählten Lookback.")
        return

    write_header = not SIG_F.exists()
    with SIG_F.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["time","symbol","timeframe","action","price","stop_px","strategy_key"])
        if write_header: w.writeheader()
        for r in to_append:
            w.writerow(r)

    print(f"[OK] {len(to_append)} Signal(e) angehängt -> {SIG_F}")

if __name__ == "__main__":
    main()
