"""Kenmerken die bepalen of een munt geschikt is voor frequent swing/grid-trading."""
from __future__ import annotations

import numpy as np
import pandas as pd


def zigzag_pivots(close: np.ndarray, threshold: float) -> list[tuple[int, float, str]]:
    """Keerpunten waarbij de koers minstens `threshold` (bv. 0.03) omkeert."""
    if len(close) < 2:
        return []
    pivots: list[tuple[int, float, str]] = []
    direction = 0
    lo_i = hi_i = ext_i = 0
    lo_p = hi_p = ext_p = float(close[0])
    for i in range(1, len(close)):
        p = float(close[i])
        if direction == 0:
            if p < lo_p:
                lo_i, lo_p = i, p
            if p > hi_p:
                hi_i, hi_p = i, p
            if p >= lo_p * (1 + threshold):
                pivots.append((lo_i, lo_p, "low")); direction = 1; ext_i, ext_p = i, p
            elif p <= hi_p * (1 - threshold):
                pivots.append((hi_i, hi_p, "high")); direction = -1; ext_i, ext_p = i, p
        elif direction == 1:
            if p > ext_p:
                ext_i, ext_p = i, p
            elif p <= ext_p * (1 - threshold):
                pivots.append((ext_i, ext_p, "high")); direction = -1; ext_i, ext_p = i, p
        else:
            if p < ext_p:
                ext_i, ext_p = i, p
            elif p >= ext_p * (1 + threshold):
                pivots.append((ext_i, ext_p, "low")); direction = 1; ext_i, ext_p = i, p
    return pivots


def compute_metrics(df: pd.DataFrame, swing_threshold: float) -> dict:
    close = df["close"].to_numpy(dtype=float)
    days = max((df["time"].iloc[-1] - df["time"].iloc[0]).total_seconds() / 86400, 1e-9)
    ret = np.diff(np.log(close))

    pivots = zigzag_pivots(close, swing_threshold)
    legs = [abs(pivots[k + 1][1] / pivots[k][1] - 1) for k in range(len(pivots) - 1)]

    path = np.abs(np.diff(close)).sum()
    efficiency = abs(close[-1] - close[0]) / path if path > 0 else np.nan

    running_max = np.maximum.accumulate(close)
    max_dd = float((close / running_max - 1).min())

    candles_per_day = len(df) / days
    vol_daily = float(np.std(ret) * np.sqrt(candles_per_day)) if len(ret) > 1 else np.nan
    autocorr = float(pd.Series(ret).autocorr(lag=1)) if len(ret) > 3 else np.nan
    range_pct = float(((df["high"] - df["low"]) / df["close"]).mean())
    quote_vol_day = float(df["quote_volume"].sum() / days)

    return {
        "swings": len(legs),
        "swings_per_week": len(legs) / days * 7,
        "avg_swing_pct": float(np.mean(legs) * 100) if legs else 0.0,
        "efficiency": float(efficiency),
        "autocorr_lag1": autocorr,
        "vol_daily_pct": vol_daily * 100,
        "candle_range_pct": range_pct * 100,
        "drift_pct": float((close[-1] / close[0] - 1) * 100),
        "max_drawdown_pct": max_dd * 100,
        "quote_vol_day_musd": quote_vol_day / 1e6,
    }


def add_score(table: pd.DataFrame) -> pd.DataFrame:
    """Samengestelde score 0-100 op basis van percentielen (relatief binnen de selectie)."""
    t = table.copy()
    pct = lambda s: s.rank(pct=True)
    t["score"] = (
        0.30 * pct(t["swings_per_week"])
        + 0.20 * (1 - pct(t["efficiency"]))
        + 0.30 * pct(t["grid_net_pct"])
        + 0.10 * pct(np.log1p(t["quote_vol_day_musd"]))
        + 0.10 * (1 - pct(t["drift_pct"].abs()))
    ) * 100
    t.loc[t["quote_vol_day_musd"] < 5, "score"] *= 0.7  # weinig liquiditeit = hogere spread
    return t.sort_values("score", ascending=False).reset_index(drop=True)
