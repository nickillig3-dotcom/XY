from __future__ import annotations
import argparse
from pathlib import Path
from json import dumps, loads
from src.config_loader import load_config
from src.data_loader import load_all_markets, save_processed_ohlcv
from src.features import build_features_for_markets
from src.strategy_generator import generate_ma_crossover_candidates
from src.backtest import backtest_all

def run(phase: str):
    cfg = load_config("config/config.yaml")

    processed_base = Path(cfg.paths.processed)
    ohlcv_dir = processed_base / "ohlcv"
    feats_dir = processed_base / "features"
    results_dir = Path("./results/backtests")
    results_dir.mkdir(parents=True, exist_ok=True)

    strategies = None

    if phase in ("data", "all"):
        dfs = load_all_markets(cfg.markets, cfg.paths.raw)
        save_processed_ohlcv(dfs, ohlcv_dir)
        print(f"[OK] Saved cleaned 1m OHLCV to: {ohlcv_dir}")

    if phase in ("features", "all"):
        build_features_for_markets(cfg.markets, ohlcv_dir, feats_dir)
        print(f"[OK] Saved basic features to: {feats_dir}")

    if phase in ("search", "all"):
        strategies = generate_ma_crossover_candidates(cfg.markets, cfg.risk.risk_per_trade_target, n_per_symbol=4)
        with (results_dir / "strategies.json").open("w", encoding="utf-8") as f:
            f.write(dumps([s.model_dump() for s in strategies], indent=2))
        print(f"[OK] Generated {len(strategies)} strategy candidates -> {results_dir / 'strategies.json'}")

    if phase in ("backtest", "all"):
        if strategies is None:
            path = results_dir / "strategies.json"
            if not path.exists():
                # Fallback: on-the-fly generieren, falls nicht vorhanden
                strategies = generate_ma_crossover_candidates(cfg.markets, cfg.risk.risk_per_trade_target, n_per_symbol=4)
            else:
                data = loads(path.read_text(encoding="utf-8"))
                from src.strategy_blocks import StrategyConfig
                strategies = [StrategyConfig(**d) for d in data]

        df = backtest_all(strategies, cfg, ohlcv_dir)
        out_csv = results_dir / "metrics.csv"
        df.to_csv(out_csv, index=False)
        print(f"[OK] Backtests done -> {out_csv}")
        # Top 5 anzeigen
        try:
            top = df.sort_values("net_return", ascending=False).head(5)
            print("\nTop 5 (net_return):")
            print(top[["symbol","fast","slow","stop_loss_pct","trades","net_return","max_drawdown","avg_monthly_return","worst_month"]].to_string(index=False))
        except Exception as e:
            print(f"Could not print top results: {e}")

def main():
    parser = argparse.ArgumentParser(description="Local Perp Futures Engine — pipeline")
    parser.add_argument("--phase", choices=["data","features","search","backtest","all"], default="all")
    args = parser.parse_args()
    run(args.phase)

if __name__ == "__main__":
    main()
