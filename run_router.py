from __future__ import annotations
from pathlib import Path
import argparse
from src.config_loader import load_config
from src.config_extras import load_extras
from src.router import DryRouter

def main():
    ap = argparse.ArgumentParser(description="Dry-Run Router: update stops & process signals")
    ap.add_argument("--signals", default="results/live/signals.csv", help="Pfad zu signals.csv")
    ap.add_argument("--no-update-stops", action="store_true", help="Stops NICHT aktualisieren (nur Signals verarbeiten)")
    args = ap.parse_args()

    cfg = load_config("config/config.yaml")
    extras = load_extras("config/config.yaml")
    router = DryRouter(cfg, extras, Path("."))

    if not args.no_update_stops:
        router.update_stops()
    router.process_signals(Path(args.signals))

if __name__ == "__main__":
    main()
