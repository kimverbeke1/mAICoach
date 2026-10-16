"""
data_fetcher.py - historische candles ophalen (Binance public API, geen sleutel nodig)
en lokaal cachen in Crypto/data/. Later vervangbaar door Firestore/cloud-opslag.
"""
from __future__ import annotations
import time
from pathlib import Path
import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data"
BINANCE_URL = "https://api.binance.com/api/v3/klines"
INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def fetch_candles(symbol: str, interval: str = "4h", days: int = 365,
                  use_cache: bool = True) -> pd.DataFrame:
    """Kolommen: time, open, high, low, close, volume, quote_volume (UTC)."""
    DATA_DIR.mkdir(exist_ok=True)
    cache = DATA_DIR / f"{symbol}_{interval}_{days}d.csv"
    if use_cache and cache.exists() and time.time() - cache.stat().st_mtime < 6 * 3600:
        return pd.read_csv(cache, parse_dates=["time"])

    end = int(time.time() * 1000)
    start = end - days * 86_400_000
    rows = []
    while start < end:
        r = requests.get(BINANCE_URL, params={"symbol": symbol, "interval": interval,
                                              "startTime": start, "limit": 1000}, timeout=20)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        start = batch[-1][0] + INTERVAL_MS[interval]
        time.sleep(0.2)

    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume", "ct",
                                     "quote_volume", "n", "tb", "tq", "x"])
    df["time"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[c] = df[c].astype(float)
    df = df[["time", "open", "high", "low", "close", "volume", "quote_volume"]]
    df = df.iloc[:-1]  # laatste candle is nog niet afgesloten
    df.to_csv(cache, index=False)
    return df
