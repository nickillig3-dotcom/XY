from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from .strategy_blocks import StrategyConfig
from .config_loader import GlobalConfig

def _load_ohlcv(symbol: str, ohlcv_dir: Path) -> pd.DataFrame:
    df = pd.read_parquet(ohlcv_dir / f"{symbol}_1m.parquet")
    cols = {"open","high","low","close","volume"}
    missing = cols - set(df.columns)
    if missing:
        raise ValueError(f"{symbol}: missing columns in processed OHLCV: {missing}")
    df = df.sort_index()
    fpath = ohlcv_dir / f"{symbol}_funding_1m.parquet"
    if fpath.exists():
        fdf = pd.read_parquet(fpath).sort_index()
        if "funding" not in fdf.columns:
            raise ValueError(f"{symbol}: funding file must contain 'funding'")
        df = df.join(fdf[["funding"]], how="left"); df["funding"] = df["funding"].fillna(0.0)
    else:
        df["funding"] = 0.0
    return df

def _resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "1m": return df
    rule = {"5m":"5min","15m":"15min"}[timeframe]
    agg  = {"open":"first","high":"max","low":"min","close":"last","volume":"sum","funding":"sum"}
    return df.resample(rule).agg(agg).dropna()

def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax(); dd = equity/peak - 1.0
    return float(dd.min()) if len(dd) else 0.0

def _monthly_stats(equity: pd.Series) -> Dict[str, float]:
    if equity.empty: return {"avg_monthly_return":0.0,"worst_month":0.0}
    m = equity.resample("ME").last().pct_change().dropna()
    return {"avg_monthly_return": float(m.mean()) if len(m) else 0.0,
            "worst_month": float(m.min()) if len(m) else 0.0}

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(int(n), min_periods=int(n)).mean()

def backtest_one(df: pd.DataFrame, strat: StrategyConfig, starting_capital: float, max_leverage: float) -> Tuple[Dict, pd.Series]:
    df_tf = _resample_ohlcv(df, strat.timeframe)
    close = df_tf["close"].astype(float)
    high = df_tf["high"].astype(float)
    low  = df_tf["low"].astype(float)

    ma_f = close.rolling(strat.fast, min_periods=strat.fast).mean()
    ma_s = close.rolling(strat.slow, min_periods=strat.slow).mean()

    # Roh-Signale (Kreuzungen)
    cross_up   = (ma_f.shift(1) <= ma_s.shift(1)) & (ma_f > ma_s)
    cross_down = (ma_f.shift(1) >= ma_s.shift(1)) & (ma_f < ma_s)

    # Filter: Trend
    trend_delta = (ma_f - ma_s) / ma_s.replace(0, np.nan)
    trend_ok_long  = (trend_delta >= strat.trend_tol) if strat.trend_tol > 0 else pd.Series(True, index=close.index)
    trend_ok_short = ((-trend_delta) >= strat.trend_tol) if strat.trend_tol > 0 else pd.Series(True, index=close.index)

    # Filter: ATR
    if strat.atr_thresh > 0:
        atr = _atr(high, low, close, strat.atr_period)
        vol_ok = (atr / close >= strat.atr_thresh).fillna(False)
    else:
        vol_ok = pd.Series(True, index=close.index)

    long_entry  = cross_up   & trend_ok_long  & vol_ok
    short_entry = cross_down & trend_ok_short & vol_ok

    equity = float(starting_capital); equity_track = []
    pos = 0; qty = 0.0; entry_price = 0.0; stop_price = 0.0
    fee_rate = strat.fee_rate; slip = strat.slippage; trades = 0

    for t, row in df_tf.iterrows():
        price=float(row["close"]); hi=float(row["high"]); lo=float(row["low"]); fund=float(row.get("funding",0.0))

        # Exits
        if pos==1:
            if lo <= stop_price or short_entry.get(t, False):
                exit_px = (stop_price if lo <= stop_price else price) * (1 - slip)
                pnl=(exit_px-entry_price)*qty; fee=abs(exit_px*qty)*fee_rate
                equity += pnl - fee; pos=0; qty=0.0
        elif pos==-1:
            if hi >= stop_price or long_entry.get(t, False):
                exit_px = (stop_price if hi >= stop_price else price) * (1 + slip)
                pnl=(entry_price-exit_px)*qty; fee=abs(exit_px*qty)*fee_rate
                equity += pnl - fee; pos=0; qty=0.0

        # Entries
        if pos==0:
            risk_amt = equity*strat.risk_fraction
            if risk_amt>0:
                if strat.direction in ("both","long") and long_entry.get(t, False):
                    entry=price*(1+slip); stop=entry*(1-strat.stop_loss_pct); dist=entry-stop
                    if dist>0:
                        q = min(risk_amt*entry/dist, equity*max_leverage)/entry
                        if q>0:
                            fee=abs(entry*q)*fee_rate; equity-=fee
                            pos=1; qty=q; entry_price=entry; stop_price=stop; trades+=1
                elif strat.direction in ("both","short") and short_entry.get(t, False):
                    entry=price*(1-slip); stop=entry*(1+strat.stop_loss_pct); dist=stop-entry
                    if dist>0:
                        q = min(risk_amt*entry/dist, equity*max_leverage)/entry
                        if q>0:
                            fee=abs(entry*q)*fee_rate; equity-=fee
                            pos=-1; qty=q; entry_price=entry; stop_price=stop; trades+=1

        # Funding
        if fund!=0.0 and pos!=0 and qty>0:
            notional=price*qty
            equity += (-notional*fund) if pos==1 else (+notional*fund)

        equity_track.append((t, equity))

    eq = pd.Series({t:v for t,v in equity_track}).sort_index()
    metrics = {"symbol":strat.symbol,"timeframe":strat.timeframe,"fast":strat.fast,"slow":strat.slow,
               "stop_loss_pct":strat.stop_loss_pct,"trades":trades,
               "net_return": float(eq.iloc[-1]/eq.iloc[0]-1.0) if len(eq)>1 else 0.0,
               "max_drawdown": _max_drawdown(eq)}
    metrics.update(_monthly_stats(eq))
    return metrics, eq

def backtest_all(strategies: List[StrategyConfig], cfg: GlobalConfig, ohlcv_dir: Path) -> pd.DataFrame:
    results=[]; cache: Dict[str,pd.DataFrame] = {}
    for s in strategies:
        if s.symbol not in cache: cache[s.symbol] = _load_ohlcv(s.symbol, ohlcv_dir)
        m, _ = backtest_one(cache[s.symbol], s, cfg.risk.starting_capital, cfg.risk.max_leverage)
        results.append(m)
    return pd.DataFrame(results)
