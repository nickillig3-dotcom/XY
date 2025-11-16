from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, List
import pandas as pd
import numpy as np

from src.strategy_blocks import StrategyConfig
from src.backtest import _load_ohlcv, _resample_ohlcv  # vorhandene Helper nutzen

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(int(n), min_periods=int(n)).mean()

def make_key(d: Dict) -> str:
    tf = d.get("timeframe","1m")
    return f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}|{tf}"

def recent_entry_signals(df_raw: pd.DataFrame, strat: StrategyConfig, lookback_bars: int = 1) -> List[Dict]:
    """Liefert Entry-Signale (entry_long/entry_short) innerhalb der letzten lookback_bars Kerzen."""
    df = _resample_ohlcv(df_raw, strat.timeframe)
    need = max(strat.fast, strat.slow) + 2
    if len(df) < need:
        return []

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)

    ma_f = close.rolling(strat.fast, min_periods=strat.fast).mean()
    ma_s = close.rolling(strat.slow, min_periods=strat.slow).mean()

    cross_up   = (ma_f.shift(1) <= ma_s.shift(1)) & (ma_f > ma_s)
    cross_down = (ma_f.shift(1) >= ma_s.shift(1)) & (ma_f < ma_s)

    if strat.trend_tol > 0:
        delta = (ma_f - ma_s) / ma_s.replace(0, np.nan)
        trend_ok_long  = (delta >= strat.trend_tol)
        trend_ok_short = ((-delta) >= strat.trend_tol)
    else:
        trend_ok_long = trend_ok_short = pd.Series(True, index=close.index)

    if strat.atr_thresh > 0:
        atr = _atr(high, low, close, strat.atr_period)
        vol_ok = (atr / close >= strat.atr_thresh).fillna(False)
    else:
        vol_ok = pd.Series(True, index=close.index)

    long_entry  = cross_up   & trend_ok_long  & vol_ok
    short_entry = cross_down & trend_ok_short & vol_ok

    out: List[Dict] = []
    idx = df.index[-int(max(1, lookback_bars)):]  # letzte N Kerzen
    for t in idx:
        is_long  = bool(long_entry.get(t, False))
        is_short = bool(short_entry.get(t, False))
        if strat.direction not in ("both","long") and is_long:
            is_long = False
        if strat.direction not in ("both","short") and is_short:
            is_short = False
        if not (is_long or is_short):
            continue

        px = float(close.loc[t])
        if is_long:
            entry = px
            stop  = entry * (1 - strat.stop_loss_pct)
            action = "entry_long"
        else:
            entry = px
            stop  = entry * (1 + strat.stop_loss_pct)
            action = "entry_short"

        out.append({
            "time": t.isoformat(),
            "symbol": strat.symbol,
            "timeframe": strat.timeframe,
            "action": action,
            "price": entry,
            "stop_px": stop
        })
    # nach Zeit sortieren (älteste zuerst)
    out.sort(key=lambda r: r["time"])
    return out

def last_entry_signal(df_raw: pd.DataFrame, strat: StrategyConfig) -> Optional[Dict]:
    """Kompatibilität: nur die letzte Kerze prüfen."""
    sigs = recent_entry_signals(df_raw, strat, lookback_bars=1)
    return sigs[-1] if sigs else None
