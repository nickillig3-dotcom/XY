from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import json
import pandas as pd
from .config_loader import load_config
from .strategy_blocks import StrategyConfig
from .backtest import _load_ohlcv, backtest_one

# try import of the extended logger
try:
    from .backtest import backtest_one_with_trades as _bt_with_trades
except Exception:
    _bt_with_trades = None

def _key_of(d: dict) -> str:
    tf = d.get("timeframe", "1m")
    return f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}|{tf}"

def run_paper(lookback_days: int = 14) -> Dict:
    root = Path(".")
    cfg = load_config("config/config.yaml")
    ohlcv_dir = Path(cfg.paths.processed) / "ohlcv"
    port_dir = Path("./results/portfolios")
    paper_dir = Path("./results/paper_trading")
    paper_dir.mkdir(parents=True, exist_ok=True)

    sel = json.loads((port_dir / "selection.json").read_text(encoding="utf-8"))
    weights: Dict[str, float] = sel.get("weights", {})

    # Strategy configs (intersection preferred)
    cand_files = [
        port_dir / "accepted_intersection.json",
        Path("./results/backtests/accepted_strategies.json"),
        Path("./results/forward_tests/accepted_strategies.json"),
    ]
    conf: List[dict] = []
    for p in cand_files:
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, list):
                    conf.extend(d)
            except Exception:
                pass

    cmap = { _key_of(d): d for d in conf }
    if weights:
        base_map = {}
        for d in conf:
            base = f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}"
            base_map.setdefault(base, d)
        for k in list(weights.keys()):
            if k not in cmap:
                base = "|".join(k.split("|")[:4])
                if base in base_map: cmap[k] = base_map[base]

    # Einzel-Equities -> normiert -> Returns + Trades sammeln
    eq_norm: Dict[str, pd.Series] = {}
    used = []; trades_frames = []
    for k, w in weights.items():
        d = cmap.get(k)
        if not d: continue
        s = StrategyConfig(**d)
        df = _load_ohlcv(s.symbol, ohlcv_dir)
        if df.empty: continue
        if lookback_days:
            cutoff = df.index.max() - pd.Timedelta(days=int(lookback_days))
            df = df[df.index >= cutoff]

        if _bt_with_trades is not None:
            m, eq, tr = _bt_with_trades(df, s, cfg.risk.starting_capital, cfg.risk.max_leverage)
            if isinstance(tr, pd.DataFrame) and not tr.empty:
                tr = tr.copy()
                tr["strategy_key"] = k
                tr["weight"] = float(w)
                trades_frames.append(tr)
        else:
            m, eq = backtest_one(df, s, cfg.risk.starting_capital, cfg.risk.max_leverage)

        if eq.empty: continue
        eq_norm[k] = eq / float(eq.iloc[0])
        used.append({"key": k, "weight": float(w), "symbol": s.symbol, "timeframe": getattr(s,"timeframe","1m"),
                     "fast": s.fast, "slow": s.slow, "stop_loss_pct": s.stop_loss_pct})

    if not eq_norm:
        (paper_dir / "paper_equity.parquet").write_text("", encoding="utf-8")
        (paper_dir / "run_meta.json").write_text(json.dumps({"status": "no_series"}), encoding="utf-8")
        return {"status": "no_series"}

    # Portfolio-Returns (union index), fehlende = 0
    rets = {k: v.pct_change().fillna(0.0) for k, v in eq_norm.items()}
    rets_df = pd.concat(rets, axis=1).sort_index().fillna(0.0)
    w = pd.Series({k: float(weights.get(k, 0.0)) for k in rets_df.columns}).reindex(rets_df.columns).fillna(0.0)
    port_ret = (rets_df * w).sum(axis=1)
    port_eq = (1.0 + port_ret).cumprod() * cfg.risk.starting_capital
    port_eq.to_frame("equity").to_parquet(paper_dir / "paper_equity.parquet")

    # Trades-CSV (falls vorhanden)
    if trades_frames:
        pd.concat(trades_frames, ignore_index=True).to_csv(paper_dir / "trades.csv", index=False)

    (paper_dir / "run_meta.json").write_text(
        json.dumps({"status": "ok", "lookback_days": lookback_days, "used": used}, indent=2),
        encoding="utf-8"
    )
    return {"status": "ok", "n_series": len(eq_norm), "lookback_days": lookback_days}
