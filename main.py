from __future__ import annotations
import argparse, json
from pathlib import Path
from json import dumps, loads
from src.config_loader import load_config
from src.data_loader import load_all_markets, save_processed_ohlcv
from src.features import build_features_for_markets
from src.strategy_generator import generate_ma_crossover_candidates
from src.backtest import backtest_all
from src.evaluation import evaluate_and_save
from src.forward_test import forward_test_all, save_metrics_and_eval
from src.forward_multi import run_forward_multi
from src.portfolio_engine import build_portfolio
from src.execution import run_paper

def _key_no_tf(d: dict) -> str:
    return f"{d['symbol']}|{int(d['fast'])}|{int(d['slow'])}|{float(d['stop_loss_pct'])}"

def _cfgget(root, path: str, default=None):
    cur = root
    for key in path.split('.'):
        if isinstance(cur, dict):
            cur = cur.get(key, None)
        else:
            cur = getattr(cur, key, None)
        if cur is None:
            return default
    return cur

def run(phase: str):
    cfg = load_config("config/config.yaml")

    processed_base = Path(cfg.paths.processed)
    ohlcv_dir = processed_base / "ohlcv"
    feats_dir = processed_base / "features"
    backtest_dir = Path("./results/backtests")
    forward_dir = Path("./results/forward_tests")
    port_dir = Path("./results/portfolios")
    for p in (backtest_dir, forward_dir, port_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Config-Parameter
    corr_cap   = _cfgget(cfg, "portfolio.corr_cap", 0.60)
    max_w      = _cfgget(cfg, "portfolio.max_w_per_strategy", 0.40)
    market_cap = _cfgget(cfg, "portfolio.max_w_per_market", 0.60)
    oos_frac   = _cfgget(cfg, "forward.oos_fraction", 0.60)
    n_splits   = int(_cfgget(cfg, "forward.n_splits", 1))
    min_passes = int(_cfgget(cfg, "forward.min_passes", n_splits))
    pb_days    = int(_cfgget(cfg, "paper.lookback_days", 14))

    strategies = None

    if phase in ("data", "all"):
        dfs = load_all_markets(cfg.markets, cfg.paths.raw)
        save_processed_ohlcv(dfs, ohlcv_dir)
        print(f"[OK] Saved cleaned 1m OHLCV to: {ohlcv_dir}")

    if phase in ("features", "all"):
        build_features_for_markets(cfg.markets, ohlcv_dir, feats_dir)
        print(f"[OK] Saved basic features to: {feats_dir}")

    if phase in ("search", "all"):
        strategies = generate_ma_crossover_candidates(cfg.markets, cfg.risk.risk_per_trade_target, n_per_symbol=20)
        (backtest_dir / "strategies.json").write_text(dumps([s.model_dump() for s in strategies], indent=2), encoding="utf-8")
        print(f"[OK] Generated {len(strategies)} strategy candidates -> {backtest_dir / 'strategies.json'}")

    if phase in ("backtest", "all"):
        if strategies is None:
            path = backtest_dir / "strategies.json"
            if not path.exists():
                strategies = generate_ma_crossover_candidates(cfg.markets, cfg.risk.risk_per_trade_target, n_per_symbol=20)
            else:
                data = loads(path.read_text(encoding="utf-8"))
                from src.strategy_blocks import StrategyConfig
                strategies = [StrategyConfig(**d) for d in data]
        df = backtest_all(strategies, cfg, ohlcv_dir)
        out_csv = backtest_dir / "metrics.csv"
        df.to_csv(out_csv, index=False)
        print(f"[OK] Backtests done -> {out_csv}")
        try:
            top = df.sort_values("net_return", ascending=False).head(5)
            print("\nTop 5 (net_return):")
            print(top[["symbol","timeframe","fast","slow","stop_loss_pct","trades","net_return","max_drawdown","avg_monthly_return","worst_month"]].to_string(index=False))
        except Exception as e:
            print(f"Could not print top results: {e}")

    if phase in ("evaluate", "all"):
        df2 = evaluate_and_save(str(backtest_dir / "metrics.csv"), str(backtest_dir / "strategies.json"), str(backtest_dir))
        acc = int(df2["is_accepted"].sum())
        print(f"[OK] Evaluation done. Accepted: {acc} / {len(df2)}")

    if phase in ("forward", "all"):
        acc_path = backtest_dir / "accepted_strategies.json"
        base_strats_path = backtest_dir / "strategies.json"
        from src.strategy_blocks import StrategyConfig
        if acc_path.exists() and acc_path.read_text(encoding="utf-8").strip() not in ("", "[]"):
            acc_data = loads(acc_path.read_text(encoding="utf-8"))
        else:
            acc_data = loads(base_strats_path.read_text(encoding="utf-8"))
        strategies = [StrategyConfig(**d) for d in acc_data]

        if n_splits <= 1:
            df_fwd = forward_test_all(strategies, cfg, ohlcv_dir, oos_fraction=oos_frac)
            (forward_dir / "strategies.json").write_text(dumps([s.model_dump() for s in strategies], indent=2), encoding="utf-8")
            save_metrics_and_eval(df_fwd, forward_dir / "strategies.json", forward_dir)
            print(f"[OK] Forward-test done -> {forward_dir / 'metrics.csv'}")
        else:
            res = run_forward_multi(strategies, cfg, ohlcv_dir, forward_dir, total_oos_frac=oos_frac, n_splits=n_splits, min_passes=min_passes)
            print(f"[OK] Multi-forward done ({res['splits']} splits, min_passes={res['min_passes']}) -> {res['out_dir']}")
            print(f"    per-split accepted: {res['per_split_counts']} | aggregated accepted: {res['accepted_aggregated']}")

    if phase in ("portfolio", "all"):
        bt_acc_f = backtest_dir / "accepted_strategies.json"
        fwd_acc_f = forward_dir / "accepted_strategies.json"
        use_forward = fwd_acc_f.exists() and fwd_acc_f.read_text(encoding="utf-8").strip() not in ("", "[]")

        src_for_portfolio = bt_acc_f
        if use_forward:
            bt = loads(bt_acc_f.read_text(encoding="utf-8")) if bt_acc_f.exists() else []
            fw = loads(fwd_acc_f.read_text(encoding="utf-8"))
            fw_keys = {_key_no_tf(d) for d in fw}
            inter = [d for d in bt if _key_no_tf(d) in fw_keys]
            tmp = port_dir / "accepted_intersection.json"
            tmp.write_text(dumps(inter, indent=2), encoding="utf-8")
            src_for_portfolio = tmp
            print(f"[OK] Using intersection Backtest&Forward -> {tmp}")

        res, port_eq = build_portfolio(cfg, src_for_portfolio, ohlcv_dir,
                                       corr_cap=corr_cap, max_w=max_w, market_cap=market_cap)
        if not res["selected"]:
            print("[WARN] No portfolio built (no accepted or all too correlated).")
        else:
            (port_dir / "selection.json").write_text(dumps(res, indent=2), encoding="utf-8")
            if port_eq is not None:
                port_eq.to_frame("equity").to_parquet(port_dir / "portfolio_equity.parquet")
                print(f"[OK] Portfolio built: {res['metrics']}")
                print(f"[OK] Saved weights -> {port_dir / 'selection.json'}")
                print(f"[OK] Saved equity  -> {port_dir / 'portfolio_equity.parquet'}")

    if phase in ("paper", "all"):
        out = run_paper(lookback_days=pb_days)
        print(f"[OK] Paper run: {out}")

def main():
    p = argparse.ArgumentParser(description="Local Perp Futures Engine - pipeline")
    p.add_argument("--phase", choices=["data","features","search","backtest","evaluate","forward","portfolio","paper","all"], default="all")
    args = p.parse_args()
    run(args.phase)

if __name__ == "__main__":
    main()
