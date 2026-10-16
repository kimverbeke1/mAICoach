"""
zone_optimizer.py - zoekt per munt de beste combinatie koopdrempel / verkoopdoel.
Pure logica, geen Streamlit -> testbaar en later herbruikbaar in de cloud-app.

Regels (1 positie, al het vrije geld in of uit):
  KOPEN    : koers zakt X% onder de hoogste koers sinds je laatste verkoop (of de start)
  VERKOPEN : koers staat Y% boven je aankoopprijs
  Limietorders: uitvoering exact op de drempelprijs zodra de candle die raakt.
  Kosten   : % per order (aankoop EN verkoop).
  Geen blik in de toekomst: drempels worden berekend met data van vóór de candle;
  na een aankoop kan je ten vroegste in de volgende candle verkopen.

Drie aparte simulaties per combinatie, elk start opnieuw met hetzelfde startbedrag:
  volledig  : hele periode
  training  : eerste 70% van de periode
  test      : laatste 30% van de periode
De drie rendementen tel je dus NIET op.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

DEFAULT_BUY_DROPS = [2, 3, 5, 7, 10, 15, 20, 30, 40, 50]
DEFAULT_SELL_RISES = [2, 3, 5, 7, 10, 15, 20, 30, 40, 50]


def simulate(high: np.ndarray, low: np.ndarray, close: np.ndarray,
             buy_drop: float, sell_rise: float, fee_pct: float,
             start_cash: float = 1000.0, return_trades: bool = False) -> dict:
    fee = fee_pct / 100
    cash, coins = start_cash, 0.0
    in_pos, entry, peak, buy_i = False, 0.0, high[0], -1
    trades, open_candles = [], 0
    eq_peak, max_dd = start_cash, 0.0

    for i in range(1, len(close)):
        if not in_pos:
            buy_price = peak * (1 - buy_drop / 100)
            if low[i] <= buy_price:
                coins = cash * (1 - fee) / buy_price
                cash, in_pos, entry, buy_i = 0.0, True, buy_price, i
            else:
                peak = max(peak, high[i])
        else:
            open_candles += 1
            sell_price = entry * (1 + sell_rise / 100)
            if i > buy_i and high[i] >= sell_price:
                cash = coins * sell_price * (1 - fee)
                trades.append((buy_i, i, entry, sell_price))
                coins, in_pos, peak = 0.0, False, sell_price
        equity = cash + coins * close[i]
        eq_peak = max(eq_peak, equity)
        max_dd = min(max_dd, (equity - eq_peak) / eq_peak)

    end_value = cash + coins * close[-1]
    res = {
        "koop_bij_daling_pct": buy_drop,
        "verkoop_bij_stijging_pct": sell_rise,
        "afgeronde_trades": len(trades),
        "eindwaarde": end_value,
        "rendement_pct": (end_value / start_cash - 1) * 100,
        "max_drawdown_pct": max_dd * 100,
        "tijd_in_munt_pct": open_candles / max(len(close) - 1, 1) * 100,
        "open_positie_einde": in_pos,
        "open_positie_resultaat_pct": (close[-1] / entry - 1) * 100 if in_pos else 0.0,
        "open_aankoopprijs": entry if in_pos else None,
        "ooit_gekocht": bool(trades) or in_pos,
    }
    if return_trades:
        res["trades"] = trades
    return res


def _years(df: pd.DataFrame) -> float:
    return max((df["time"].iloc[-1] - df["time"].iloc[0]).total_seconds() / (365.25 * 86400), 1e-9)


def per_jaar(rendement_pct: float, jaren: float) -> float:
    """Rendement omgerekend naar 1 jaar (met samengestelde interest)."""
    return ((1 + rendement_pct / 100) ** (1 / jaren) - 1) * 100


def optimize(df: pd.DataFrame, fee_pct: float, buy_drops=None, sell_rises=None,
             start_cash: float = 1000.0, train_frac: float = 0.7) -> pd.DataFrame:
    buy_drops = buy_drops or DEFAULT_BUY_DROPS
    sell_rises = sell_rises or DEFAULT_SELL_RISES
    h, l, c = (df[k].to_numpy() for k in ("high", "low", "close"))
    cut = int(len(c) * train_frac)
    jaren = _years(df)
    rows = []
    for b in buy_drops:
        for s in sell_rises:
            full = simulate(h, l, c, b, s, fee_pct, start_cash)
            tr = simulate(h[:cut], l[:cut], c[:cut], b, s, fee_pct, start_cash)
            te = simulate(h[cut:], l[cut:], c[cut:], b, s, fee_pct, start_cash)
            full["rendement_per_jaar_pct"] = per_jaar(full["rendement_pct"], jaren)
            full["rendement_training_pct"] = tr["rendement_pct"]
            full["trades_training"] = tr["afgeronde_trades"]
            full["rendement_test_pct"] = te["rendement_pct"]
            full["trades_test"] = te["afgeronde_trades"]
            full["test_ooit_gekocht"] = te["ooit_gekocht"]
            rows.append(full)
    out = pd.DataFrame(rows).sort_values("rendement_pct", ascending=False)
    return out.reset_index(drop=True)


def period_info(df: pd.DataFrame, train_frac: float = 0.7) -> dict:
    cut = int(len(df) * train_frac)
    t = df["time"]
    return {
        "start": t.iloc[0], "einde": t.iloc[-1], "dagen": (t.iloc[-1] - t.iloc[0]).days,
        "training_tot": t.iloc[cut - 1], "test_vanaf": t.iloc[cut],
        "dagen_training": (t.iloc[cut - 1] - t.iloc[0]).days,
        "dagen_test": (t.iloc[-1] - t.iloc[cut]).days,
    }


def buy_and_hold_pct(df: pd.DataFrame, fee_pct: float) -> float:
    f = fee_pct / 100
    return ((df["close"].iloc[-1] / df["close"].iloc[0]) * (1 - f) ** 2 - 1) * 100


def robust_best(results: pd.DataFrame, min_trades_training: int = 3,
                min_trades_test: int = 1) -> pd.Series | None:
    """Beste combinatie die in de training genoeg trades had EN in de testperiode
    zelf ook effectief handelde en winst gaf (0 trades in test telt niet)."""
    ok = results[(results["trades_training"] >= min_trades_training)
                 & (results["trades_test"] >= min_trades_test)
                 & (results["rendement_test_pct"] > 0)]
    return None if ok.empty else ok.iloc[0]


def summarize_symbol(symbol: str, df: pd.DataFrame, fee_pct: float,
                     start_cash: float = 1000.0) -> dict:
    """Eén rij per munt voor het overzicht."""
    res = optimize(df, fee_pct, start_cash=start_cash)
    rb = robust_best(res)
    p = period_info(df)
    bh = buy_and_hold_pct(df, fee_pct)
    row = {
        "munt": symbol,
        "periode": f"{p['start']:%d/%m/%Y} - {p['einde']:%d/%m/%Y}",
        "dagen": p["dagen"],
        "kopen_laten_staan_pct": bh,
    }
    if rb is None:
        row.update({"beste_koop_daling_pct": None, "beste_verkoop_stijging_pct": None,
                    "trades": 0, "eindwaarde": None, "rendement_pct": None,
                    "rendement_per_jaar_pct": None, "rendement_test_pct": None,
                    "trades_test": 0, "max_drawdown_pct": None, "tijd_in_munt_pct": None,
                    "beter_dan_laten_staan": False, "oordeel": "geen betrouwbare combinatie"})
    else:
        row.update({
            "beste_koop_daling_pct": rb.koop_bij_daling_pct,
            "beste_verkoop_stijging_pct": rb.verkoop_bij_stijging_pct,
            "trades": int(rb.afgeronde_trades),
            "eindwaarde": rb.eindwaarde,
            "rendement_pct": rb.rendement_pct,
            "rendement_per_jaar_pct": rb.rendement_per_jaar_pct,
            "rendement_test_pct": rb.rendement_test_pct,
            "trades_test": int(rb.trades_test),
            "max_drawdown_pct": rb.max_drawdown_pct,
            "tijd_in_munt_pct": rb.tijd_in_munt_pct,
            "beter_dan_laten_staan": rb.rendement_pct > bh,
            "oordeel": "OK",
        })
    return row
