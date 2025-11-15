from __future__ import annotations
from pathlib import Path
from typing import Dict, Iterable
import pandas as pd

__all__ = ["load_symbol_csv", "load_all_markets", "save_processed_ohlcv"]

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

def load_symbol_csv(csv_path: str | Path) -> pd.DataFrame:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV: {csv_path} (expected columns: {REQUIRED_COLUMNS})")
    df = pd.read_csv(csv_path)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name} missing columns: {sorted(missing)}")
    # Zeitstempel auf UTC parsieren, Index setzen, doppelte Zeilen entfernen
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    # Numerische Spalten säubern
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def load_all_markets(markets: Iterable[str], raw_dir: str | Path) -> Dict[str, pd.DataFrame]:
    raw_dir = Path(raw_dir)
    out: Dict[str, pd.DataFrame] = {}
    for symbol in markets:
        out[symbol] = load_symbol_csv(raw_dir / f"{symbol}_1m.csv")
    return out

def save_processed_ohlcv(dfs: Dict[str, pd.DataFrame], out_dir: str | Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for symbol, df in dfs.items():
        df.to_parquet(out_dir / f"{symbol}_1m.parquet")

