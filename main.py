from __future__ import annotations
import argparse
from pathlib import Path
from src.config_loader import load_config
from src.data_loader import load_all_markets, save_processed_ohlcv
from src.features import build_features_for_markets

def run(phase: str):
    cfg = load_config("config/config.yaml")

    processed_base = Path(cfg.paths.processed)
    ohlcv_dir = processed_base / "ohlcv"
    feats_dir = processed_base / "features"

    if phase in ("data", "all"):
        dfs = load_all_markets(cfg.markets, cfg.paths.raw)
        save_processed_ohlcv(dfs, ohlcv_dir)
        print(f"[OK] Saved cleaned 1m OHLCV to: {ohlcv_dir}")

    if phase in ("features", "all"):
        build_features_for_markets(cfg.markets, ohlcv_dir, feats_dir)
        print(f"[OK] Saved basic features to: {feats_dir}")

def main():
    parser = argparse.ArgumentParser(description="Local Perp Futures Engine — minimal bootstrap")
    parser.add_argument("--phase", choices=["data", "features", "all"], default="all")
    args = parser.parse_args()
    run(args.phase)

if __name__ == "__main__":
    main()
