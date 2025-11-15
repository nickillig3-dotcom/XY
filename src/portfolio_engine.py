from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple
import json
import numpy as np
import pandas as pd
from .config_loader import GlobalConfig
from .strategy_blocks import StrategyConfig
from .backtest import _load_ohlcv, backtest_one

def _daily_returns(eq: pd.Series) -> pd.Series:
    return eq.resample("D").last().pct_change().dropna()

def _select_with_corr(ret_map: Dict[str, pd.Series], score: pd.Series, corr_cap: float = 0.8, max_n: int | None = 10) -> List[str]:
    chosen: List[str] = []
    for key in score.sort_values(ascending=False).index:
        ok = True
        for c in chosen:
            corr = ret_map[key].corr(ret_map[c])
            if pd.notna(corr) and corr > corr_cap:
                ok = False
                break
        if ok:
            chosen.append(key)
            if max_n and len(chosen) >= max_n:
                break
    return chosen

def _risk_parity_weights(ret_map: Dict[str, pd.Series], keys: List[str], max_w: float) -> pd.Series:
    df = pd.concat({k: ret_map[k] for k in keys}, axis=1).dropna(how="all")
    vol = df.std().replace(0, np.nan)
    inv_vol = 1.0 / vol
    w = inv_vol / inv_vol.sum()
    w = w.fillna(0).clip(upper=max_w)
    # nicht normalisieren – das machen wir nach den Caps
    return w

def _apply_caps_strict(w: pd.Series, symbol_of: Dict[str, str], max_w: float, market_cap: float, max_iters: int = 20) -> pd.Series:
    # 1) pro-Strategie-Kappung
    w = w.clip(upper=max_w)

    for _ in range(max_iters):
        # Markt-Summen
        sums = {}
        for k, v in w.items():
            s = symbol_of[k]
            sums[s] = sums.get(s, 0.0) + float(v)

        # Übergewichtete Märkte hart kappen
        over = {s: val for s, val in sums.items() if val > market_cap + 1e-12}
        if over:
            for s, val in over.items():
                keys = [k for k in w.index if symbol_of[k] == s]
                if val > 0:
                    scale = market_cap / val
                    w.loc[keys] = w.loc[keys] * scale
            # nach dem Kappen erneut clippen (falls Einzeltitel durch Rundung > max_w)
            w = w.clip(upper=max_w)

        # Summe prüfen
        total = float(w.sum())
        if abs(total - 1.0) < 1e-9 and not over:
            break

        # Restgewicht verteilen (nur auf NICHT übergewichtete Märkte)
        sums = {}
        for k, v in w.items():
            s = symbol_of[k]
            sums[s] = sums.get(s, 0.0) + float(v)
        non_over_keys = [k for k in w.index if sums[symbol_of[k]] < market_cap - 1e-12]

        if not non_over_keys:
            # Falls nichts übrig ist, normalisieren wir hart (sollte praktisch nicht vorkommen)
            w = w / max(total, 1e-12)
            break

        residual = 1.0 - total
        if abs(residual) < 1e-9 and not over:
            break

        # Verteile Rest proportional zu aktuellem Gewicht der nicht-übergewichteten
        sub = w.loc[non_over_keys]
        sub_sum = float(sub.sum())
        if sub_sum <= 0:
            # gleichmäßig verteilen
            add = pd.Series(1.0 / len(non_over_keys), index=non_over_keys)
        else:
            add = sub / sub_sum

        w.loc[non_over_keys] = w.loc[non_over_keys] + residual * add
        # Einzeltitel-Grenze erneut beachten
        w = w.clip(upper=max_w)

    # Final: minimale numerische Korrektur auf 1.0
    w = w / float(w.sum())
    return w

def build_portfolio(cfg: GlobalConfig, accepted_json: Path, ohlcv_dir: Path,
                    corr_cap: float = 0.80, max_w: float = 0.40, market_cap: float = 0.70):
    if not accepted_json.exists():
        raise FileNotFoundError(f"{accepted_json} not found")
    data = json.loads(accepted_json.read_text(encoding="utf-8"))
    if not data:
        return {"selected": [], "weights": {}, "metrics": {}}, None

    ret_map: Dict[str, pd.Series] = {}
    eq_map: Dict[str, pd.Series] = {}
    meta: Dict[str, Dict] = {}

    # Backtest der akzeptierten Strategien (kleine Menge → schnell)
    for d in data:
        s = StrategyConfig(**d)
        df = _load_ohlcv(s.symbol, ohlcv_dir)
        m, eq = backtest_one(df, s, cfg.risk.starting_capital, cfg.risk.max_leverage)
        key = f"{s.symbol}|f{s.fast}|s{s.slow}|sl{float(s.stop_loss_pct):.4f}|{getattr(s,'timeframe','1m')}"
        eq_map[key] = eq
        ret_map[key] = _daily_returns(eq)
        meta[key] = {"symbol": s.symbol, **m}

    # grobe Score-Funktion
    score = pd.Series({k: (ret_map[k].mean()*30.0) - max(0.0, -meta[k]["max_drawdown"])*0.5 for k in ret_map})

    # Korridor via Korrelation
    selected = _select_with_corr(ret_map, score, corr_cap=corr_cap, max_n=10)
    if not selected:
        return {"selected": [], "weights": {}, "metrics": {}}, None

    # Risiko-Parität (geclipped), dann strikte Caps
    w_base = _risk_parity_weights(ret_map, selected, max_w=max_w)
    symbol_of = {k: meta[k]["symbol"] for k in selected}
    w = _apply_caps_strict(w_base.copy(), symbol_of, max_w=max_w, market_cap=market_cap)

    # Portfolio-EQ (normiert auf 1.0)
    aligned = pd.concat({k: eq_map[k] / float(eq_map[k].iloc[0]) for k in selected}, axis=1).dropna()
    port_eq = (aligned * w).sum(axis=1)

    # Kennzahlen (Monate)
    mret = port_eq.resample("ME").last().pct_change().dropna()
    metrics = {
        "n_strategies": len(selected),
        "avg_monthly_return": float(mret.mean()) if len(mret) else 0.0,
        "worst_month": float(mret.min()) if len(mret) else 0.0,
        "max_drawdown": float((port_eq/port_eq.cummax() - 1.0).min()) if len(port_eq) else 0.0
    }
    result = {"selected": selected, "weights": w.to_dict(), "metrics": metrics}
    return result, port_eq
