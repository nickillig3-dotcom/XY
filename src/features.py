from __future__ import annotations
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd

def make_basic_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """
    Erwartet OHLCV mit Index=UTC-Timestamps (1m), Spalten: open, high, low, close, volume.
    Gibt Baseline-Features zurück.
    """
    df = pd.DataFrame(index=ohlcv.index)
    close = ohlcv["close"].astype(float)
    df["close"] = close
    df["logret_1"] = np.log(close).diff()
    df["vol_60"] = df["logret_1"].rolling(60, min_periods=10).std()
    df["ma_fast_20"] = close.rolling(20, min_periods=5).mean()
    df["ma_slow_50"] = close.rolling(50, min_periods=10).mean()
    return df.dropna()

def build_features_for_markets(markets: Iterable[str], ohlcv_dir: str | Path, out_dir: str | Path) -> None:
    ohlcv_dir = Path(ohlcv_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol in markets:
        src = ohlcv_dir / f"{symbol}_1m.parquet"
        if not src.exists():
            raise FileNotFoundError(f"Missing processed OHLCV: {src}")
        raw = pd.read_parquet(src)
        feats = make_basic_features(raw)
        feats.to_parquet(out_dir / f"{symbol}_features.parquet")
