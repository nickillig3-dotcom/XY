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
        if "funding" not in fdf.columns: raise ValueError(f"{symbol}: funding file must contain 'funding'")
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

def backtest_one(df: pd.DataFrame, strat: StrategyConfig, starting_capital: float, max_leverage: float) -> Tuple[Dict, pd.Series]:
    df_tf = _resample_ohlcv(df, strat.timeframe)
    close = df_tf["close"].astype(float)
    ma_f = close.rolling(strat.fast, min_periods=strat.fast).mean()
    ma_s = close.rolling(strat.slow, min_periods=strat.slow).mean()
    long_entry  = (ma_f.shift(1) <= ma_s.shift(1)) & (ma_f > ma_s)
    short_entry = (ma_f.shift(1) >= ma_s.shift(1)) & (ma_f < ma_s)

    equity = float(starting_capital); equity_track = []
    pos = 0; qty = 0.0; entry_price = 0.0; stop_price = 0.0
    fee_rate = strat.fee_rate; slip = strat.slippage; trades = 0

    for t, row in df_tf.iterrows():
        price=float(row["close"]); high=float(row["high"]); low=float(row["low"]); fund=float(row.get("funding",0.0))

        # Exits
        if pos==1:
            if low <= stop_price:  # stop long
                exit_px = stop_price*(1-slip); pnl=(exit_px-entry_price)*qty; fee=abs(exit_px*qty)*fee_rate
                equity += pnl - fee; pos=0; qty=0.0
            elif short_entry.get(t, False):  # reverse
                exit_px = price*(1-slip); pnl=(exit_px-entry_price)*qty; fee=abs(exit_px*qty)*fee_rate
                equity += pnl - fee; pos=0; qty=0.0
        elif pos==-1:
            if high >= stop_price:  # stop short
                exit_px = stop_price*(1+slip); pnl=(entry_price-exit_px)*qty; fee=abs(exit_px*qty)*fee_rate
                equity += pnl - fee; pos=0; qty=0.0
            elif long_entry.get(t, False):   # reverse
                exit_px = price*(1+slip); pnl=(entry_price-exit_px)*qty; fee=abs(exit_px*qty)*fee_rate
                equity += pnl - fee; pos=0; qty=0.0

        # Entries
        if pos==0:
            risk_amt = equity*strat.risk_fraction
            if risk_amt>0:
                if strat.direction in ("both","long") and long_entry.get(t, False):
                    entry=price*(1+slip); stop=entry*(1-strat.stop_loss_pct); stop_dist=entry-stop
                    if stop_dist>0:
                        qty_notional=min(risk_amt*entry/stop_dist, equity*max_leverage); q=qty_notional/entry
                        if q>0:
                            fee=abs(entry*q)*fee_rate; equity-=fee; pos=1; qty=q; entry_price=entry; stop_price=stop; trades+=1
                elif strat.direction in ("both","short") and short_entry.get(t, False):
                    entry=price*(1-slip); stop=entry*(1+strat.stop_loss_pct); stop_dist=stop-entry
                    if stop_dist>0:
                        qty_notional=min(risk_amt*entry/stop_dist, equity*max_leverage); q=qty_notional/entry
                        if q>0:
                            fee=abs(entry*q)*fee_rate; equity-=fee; pos=-1; qty=q; entry_price=entry; stop_price=stop; trades+=1

        # Funding (sign: long zahlt bei +funding; short erhält)
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

def backtest_one_with_trades(df: pd.DataFrame, strat: StrategyConfig, starting_capital: float, max_leverage: float) -> Tuple[Dict, pd.Series, pd.DataFrame]:
    df_tf = _resample_ohlcv(df, strat.timeframe)
    close = df_tf["close"].astype(float)
    ma_f = close.rolling(strat.fast, min_periods=strat.fast).mean()
    ma_s = close.rolling(strat.slow, min_periods=strat.slow).mean()
    long_entry  = (ma_f.shift(1) <= ma_s.shift(1)) & (ma_f > ma_s)
    short_entry = (ma_f.shift(1) >= ma_s.shift(1)) & (ma_f < ma_s)

    equity=float(starting_capital); equity_track=[]; log=[]
    pos=0; qty=0.0; entry_price=0.0; stop_price=0.0; entry_time=None
    fee_rate=strat.fee_rate; slip=strat.slippage; trades=0

    for t, row in df_tf.iterrows():
        price=float(row["close"]); high=float(row["high"]); low=float(row["low"]); fund=float(row.get("funding",0.0))

        def _log(action, **kw):
            rec={"time":t.isoformat(),"symbol":strat.symbol,"timeframe":strat.timeframe,"action":action,"pos":pos,"price":price,"qty":qty,"equity":equity}
            rec.update(kw); log.append(rec)

        # Exits
        if pos==1:
            if low<=stop_price:
                exit_px=stop_price*(1-slip); pnl=(exit_px-entry_price)*qty; fee=abs(exit_px*qty)*fee_rate; equity+=pnl-fee
                _log("exit_stop_long", exit_px=exit_px, pnl=pnl, fee=fee, entry_px=entry_price, entry_time=None if entry_time is None else entry_time.isoformat())
                pos=0; qty=0.0
            elif short_entry.get(t, False):
                exit_px=price*(1-slip); pnl=(exit_px-entry_price)*qty; fee=abs(exit_px*qty)*fee_rate; equity+=pnl-fee
                _log("exit_signal_long", exit_px=exit_px, pnl=pnl, fee=fee, entry_px=entry_price, entry_time=None if entry_time is None else entry_time.isoformat())
                pos=0; qty=0.0
        elif pos==-1:
            if high>=stop_price:
                exit_px=stop_price*(1+slip); pnl=(entry_price-exit_px)*qty; fee=abs(exit_px*qty)*fee_rate; equity+=pnl-fee
                _log("exit_stop_short", exit_px=exit_px, pnl=pnl, fee=fee, entry_px=entry_price, entry_time=None if entry_time is None else entry_time.isoformat())
                pos=0; qty=0.0
            elif long_entry.get(t, False):
                exit_px=price*(1+slip); pnl=(entry_price-exit_px)*qty; fee=abs(exit_px*qty)*fee_rate; equity+=pnl-fee
                _log("exit_signal_short", exit_px=exit_px, pnl=pnl, fee=fee, entry_px=entry_price, entry_time=None if entry_time is None else entry_time.isoformat())
                pos=0; qty=0.0

        # Entries
        if pos==0:
            risk_amt = equity*strat.risk_fraction
            if risk_amt>0:
                if strat.direction in ("both","long") and long_entry.get(t, False):
                    entry=price*(1+slip); stop=entry*(1-strat.stop_loss_pct); stop_dist=entry-stop
                    if stop_dist>0:
                        qty_notional=min(risk_amt*entry/stop_dist, equity*max_leverage); q=qty_notional/entry
                        if q>0:
                            fee=abs(entry*q)*fee_rate; equity-=fee
                            pos=1; qty=q; entry_price=entry; stop_price=stop; entry_time=t; trades+=1
                            _log("entry_long", entry_px=entry, fee=fee, stop_px=stop, risk_amt=risk_amt, size=q)
                elif strat.direction in ("both","short") and short_entry.get(t, False):
                    entry=price*(1-slip); stop=entry*(1+strat.stop_loss_pct); stop_dist=stop-entry
                    if stop_dist>0:
                        qty_notional=min(risk_amt*entry/stop_dist, equity*max_leverage); q=qty_notional/entry
                        if q>0:
                            fee=abs(entry*q)*fee_rate; equity-=fee
                            pos=-1; qty=q; entry_price=entry; stop_price=stop; entry_time=t; trades+=1
                            _log("entry_short", entry_px=entry, fee=fee, stop_px=stop, risk_amt=risk_amt, size=q)

        # Funding
        if fund!=0.0 and pos!=0 and qty>0:
            notional=price*qty; cashflow = (-notional*fund) if pos==1 else (+notional*fund)
            equity += cashflow
            _log("funding", cashflow=cashflow, notional=notional, rate=fund)

        equity_track.append((t, equity))

    eq = pd.Series({t:v for t,v in equity_track}).sort_index()
    metrics = {"symbol":strat.symbol,"timeframe":strat.timeframe,"fast":strat.fast,"slow":strat.slow,
               "stop_loss_pct":strat.stop_loss_pct,"trades":trades,
               "net_return": float(eq.iloc[-1]/eq.iloc[0]-1.0) if len(eq)>1 else 0.0,
               "max_drawdown": _max_drawdown(eq)}
    metrics.update(_monthly_stats(eq))
    trades_df = pd.DataFrame(log)
    return metrics, eq, trades_df

def backtest_all(strategies: List[StrategyConfig], cfg: GlobalConfig, ohlcv_dir: Path) -> pd.DataFrame:
    results=[]; cache: Dict[str,pd.DataFrame] = {}
    for s in strategies:
        if s.symbol not in cache: cache[s.symbol] = _load_ohlcv(s.symbol, ohlcv_dir)
        m, _eq = backtest_one(cache[s.symbol], s, cfg.risk.starting_capital, cfg.risk.max_leverage)
        results.append(m)
    return pd.DataFrame(results)
