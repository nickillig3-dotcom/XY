from __future__ import annotations
from pathlib import Path
from typing import Dict, List
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
    return df

def _resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "1m":
        return df
    rule = {"5m": "5min", "15m": "15min"}[timeframe]
    agg = {"open":"first", "high":"max", "low":"min", "close":"last", "volume":"sum"}
    out = df.resample(rule).agg(agg).dropna()
    return out

def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min()) if len(dd) else 0.0

def _monthly_stats(equity: pd.Series) -> Dict[str, float]:
    if equity.empty:
        return {"avg_monthly_return": 0.0, "worst_month": 0.0}
    m = equity.resample("ME").last().pct_change().dropna()
    if m.empty:
        return {"avg_monthly_return": 0.0, "worst_month": 0.0}
    return {"avg_monthly_return": float(m.mean()), "worst_month": float(m.min())}

def backtest_one(df: pd.DataFrame, strat: StrategyConfig, starting_capital: float, max_leverage: float) -> Dict:
    df_tf = _resample_ohlcv(df, strat.timeframe)
    close = df_tf["close"].astype(float)
    ma_f = close.rolling(strat.fast, min_periods=strat.fast).mean()
    ma_s = close.rolling(strat.slow, min_periods=strat.slow).mean()
    long_entry  = (ma_f.shift(1) <= ma_s.shift(1)) & (ma_f > ma_s)
    short_entry = (ma_f.shift(1) >= ma_s.shift(1)) & (ma_f < ma_s)

    equity = float(starting_capital)
    equity_track = []
    pos = 0
    qty = 0.0
    entry_price = 0.0
    stop_price = 0.0
    trades = 0
    fee_rate = strat.fee_rate
    slip = strat.slippage

    for t, row in df_tf.iterrows():
        price = float(row["close"])
        high  = float(row["high"])
        low   = float(row["low"])

        # Exit-Logik
        if pos == 1:
            if low <= stop_price:
                exit_px = stop_price * (1 - slip)
                pnl = (exit_px - entry_price) * qty
                fee = abs(exit_px * qty) * fee_rate
                equity += pnl - fee
                pos = 0; qty = 0.0
            elif short_entry.get(t, False):
                exit_px = price * (1 - slip)
                pnl = (exit_px - entry_price) * qty
                fee = abs(exit_px * qty) * fee_rate
                equity += pnl - fee
                pos = 0; qty = 0.0

        elif pos == -1:
            if high >= stop_price:
                exit_px = stop_price * (1 + slip)
                pnl = (entry_price - exit_px) * qty
                fee = abs(exit_px * qty) * fee_rate
                equity += pnl - fee
                pos = 0; qty = 0.0
            elif long_entry.get(t, False):
                exit_px = price * (1 + slip)
                pnl = (entry_price - exit_px) * qty
                fee = abs(exit_px * qty) * fee_rate
                equity += pnl - fee
                pos = 0; qty = 0.0

        # Entry (nur wenn flat)
        if pos == 0:
            risk_amt = equity * strat.risk_fraction
            if risk_amt > 0:
                if strat.direction in ("both","long") and long_entry.get(t, False):
                    entry = price * (1 + slip)
                    stop  = entry * (1 - strat.stop_loss_pct)
                    stop_dist = entry - stop
                    if stop_dist > 0:
                        qty_notional = risk_amt * entry / stop_dist  # ~ risk / %SL
                        notional_cap = equity * max_leverage
                        qty_notional = min(qty_notional, notional_cap)
                        q = qty_notional / entry
                        if q > 0:
                            fee = abs(entry * q) * fee_rate
                            equity -= fee
                            pos = 1; qty = q; entry_price = entry; stop_price = stop
                            trades += 1

                elif strat.direction in ("both","short") and short_entry.get(t, False):
                    entry = price * (1 - slip)
                    stop  = entry * (1 + strat.stop_loss_pct)
                    stop_dist = stop - entry
                    if stop_dist > 0:
                        qty_notional = risk_amt * entry / stop_dist
                        notional_cap = equity * max_leverage
                        qty_notional = min(qty_notional, notional_cap)
                        q = qty_notional / entry
                        if q > 0:
                            fee = abs(entry * q) * fee_rate
                            equity -= fee
                            pos = -1; qty = q; entry_price = entry; stop_price = stop
                            trades += 1

        equity_track.append((t, equity))

    eq = pd.Series({t: v for t, v in equity_track}).sort_index()
    metrics = {
        "symbol": strat.symbol,
        "timeframe": strat.timeframe,
        "fast": strat.fast,
        "slow": strat.slow,
        "stop_loss_pct": strat.stop_loss_pct,
        "trades": trades,
        "net_return": float(eq.iloc[-1] / eq.iloc[0] - 1.0) if len(eq) > 1 else 0.0,
        "max_drawdown": _max_drawdown(eq),
    }
    metrics.update(_monthly_stats(eq))
    return metrics, eq

def backtest_all(strategies: List[StrategyConfig], cfg: GlobalConfig, ohlcv_dir: Path) -> pd.DataFrame:
    results = []
    ohlcv_cache: Dict[str, pd.DataFrame] = {}
    for s in strategies:
        if s.symbol not in ohlcv_cache:
            ohlcv_cache[s.symbol] = _load_ohlcv(s.symbol, ohlcv_dir)
        m, _eq = backtest_one(ohlcv_cache[s.symbol], s, cfg.risk.starting_capital, cfg.risk.max_leverage)
        results.append(m)
    df = pd.DataFrame(results)
    return df
