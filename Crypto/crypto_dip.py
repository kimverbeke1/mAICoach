"""Dip-kopen: koop als de koers diep onder het hoogste punt van de voorbije periode staat,
verkoop bij een vast winstdoel. Ondersteunt meerdere schijven (bedragen) per munt,
een automatische zoektocht naar de historisch beste koopdrempel/winstdoel per munt,
en een betrouwbaarheidstest (training/test) van dat optimum."""
from __future__ import annotations

import numpy as np
import pandas as pd

DIP_GRID = np.round(np.arange(0.30, 0.851, 0.05), 2)            # koopdrempels 30..85%
TARGET_GRID = np.array([0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00])  # winstdoelen

# Wanneer telt iets als een NIEUWE keer in de koopzone (zie episode_starts)
EPISODE_GAP_DAYS = 30     # zo lang buiten de zone => de volgende duik is een nieuwe keer
EPISODE_REBOUND = 0.10    # of: koers herstelt zoveel procentpunt boven de koopdrempel


def drawdown_series(df: pd.DataFrame, lookback: int) -> pd.Series:
    """Daling t.o.v. het hoogste punt van de voorbije `lookback` dagen (negatief, bv. -0.45)."""
    roll_high = df["high"].rolling(lookback, min_periods=lookback).max()
    return df["close"] / roll_high - 1


def episode_starts(dd: np.ndarray, dip: float, gap_days: int = EPISODE_GAP_DAYS,
                   rebound: float = EPISODE_REBOUND) -> np.ndarray:
    """
    Eerste dag van elke AFZONDERLIJKE keer in de koopzone (= elke afzonderlijke crash).
    Een keer is pas afgelopen als de koers
      (a) hersteld is tot minstens `rebound` procentpunt boven de koopdrempel
          (drempel -50% en rebound 10 => koers moet terug tot -40% of beter), OF
      (b) minstens `gap_days` dagen buiten de zone gebleven is.
    Schommelt de koers dus rond de drempel (-51%, -48%, -52%, ...), dan blijft het dezelfde keer.
    """
    rebound = min(rebound, dip / 2)            # bij kleine drempels niet te streng
    exit_level = -(dip - rebound)
    starts, in_ep, days_out = [], False, 0
    for i, v in enumerate(dd):
        if np.isnan(v):
            continue
        if v <= -dip:
            if not in_ep:
                starts.append(i)
                in_ep = True
            days_out = 0
        elif in_ep:
            days_out += 1
            if v >= exit_level or days_out >= gap_days:
                in_ep = False
    return np.array(starts, dtype=int)


# --------------------------------------------------------------------------- statistiek
def dip_stats(df: pd.DataFrame, lookback: int, dip: float, target: float, max_days: int) -> dict:
    """Wat gebeurde er na aankoop op een koopzone-dag? Per dag én per afzonderlijke keer in de zone."""
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    dd = drawdown_series(df, lookback).to_numpy(float)
    sig = dd <= -dip  # NaN -> False
    n = len(close)

    def outcome(i: int):
        """(status, dagen, verdere_daling) met status 1=gehaald, 0=niet gehaald, None=te recent."""
        tp = close[i] * (1 + target)
        end = min(n, i + 1 + max_days)
        hit = np.flatnonzero(high[i + 1:end] >= tp)
        if hit.size:
            j = i + 1 + hit[0]
            return 1, j - i, low[i + 1:j + 1].min() / close[i] - 1
        if end - (i + 1) < max_days:
            return None, None, None
        return 0, None, (low[i + 1:end].min() / close[i] - 1) if end > i + 1 else 0.0

    hits, days, further, still_open = [], [], [], 0
    for i in np.flatnonzero(sig):
        st_, d, f = outcome(i)
        if st_ is None:
            still_open += 1
            continue
        hits.append(st_)
        further.append(f)
        if d is not None:
            days.append(d)

    starts = episode_starts(dd, dip)
    raw_starts = int(np.sum(sig & ~np.concatenate(([False], sig[:-1]))))   # oude telling, ter vergelijking
    ep_res = [outcome(i)[0] for i in starts]
    ep_eval = [r for r in ep_res if r is not None]

    return {
        "history_days": n,
        "signal_days": int(sig.sum()),
        "episodes": len(starts),
        "episodes_raw": raw_starts,
        "episodes_eval": len(ep_eval),
        "episodes_hit": int(sum(ep_eval)),
        "episode_hit_pct": float(np.mean(ep_eval) * 100) if ep_eval else np.nan,
        "hit_rate_pct": float(np.mean(hits) * 100) if hits else np.nan,
        "median_days": float(np.median(days)) if days else np.nan,
        "median_further_pct": float(np.median(further) * 100) if further else np.nan,
        "worst_further_pct": float(np.min(further) * 100) if further else np.nan,
        "still_open": still_open,
        "current_dd_pct": float(dd[-1] * 100) if n and not np.isnan(dd[-1]) else np.nan,
    }


# --------------------------------------------------------------------------- backtest
def ladder_backtest(df: pd.DataFrame, lookback: int, tranches: list[tuple[float, float]],
                    target: float, fee: float, dd: np.ndarray | None = None) -> dict:
    """
    Eén of meer schijven per munt. Elke schijf = (koopdrempel, bedrag €) en werkt onafhankelijk:
    koop met het volledige schijfbedrag op slotkoers zodra de daling >= drempel,
    verkoop zodra de koers aankoop*(1+target) raakt, daarna opnieuw kopen als de voorwaarde nog geldt.
    Winst blijft in de schijf (herbelegd). Geen stop-loss. Start pas als er een 'top' gekend is.

    %/jaar: 'dip_annual_pct' is NaN bij een periode < 0,5 jaar (gebruikt door de optimalisatie, die geen
    extreme jaarcijfers uit korte periodes wil vergelijken). 'dip_annual_raw_pct' wordt ALTIJD berekend en
    'short_period' zegt of de periode korter dan 0,5 jaar is (voor weergave met waarschuwing).
    """
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    times = df["time"].to_numpy()
    if dd is None:
        dd = drawdown_series(df, lookback).to_numpy(float)
    n = len(close)
    start = lookback - 1
    capital = float(sum(a for _, a in tranches))
    empty = {"capital": capital, "valid": False}
    if n - start < 30 or capital <= 0:
        return empty

    k = len(tranches)
    dips = [d for d, _ in tranches]
    cash = [float(a) for _, a in tranches]
    qty = [0.0] * k
    entry = [0.0] * k
    cost = [0.0] * k  # bedrag (€) dat in de open aankoop van elke schijf zit
    buy_i = [0] * k   # dag-index van de open aankoop per schijf
    hold_days = []    # looptijd (dagen) van elke afgeronde trade
    trades, sells, days_in = [], 0, 0
    equity = np.empty(n - start)

    for idx, i in enumerate(range(start, n)):
        for t in range(k):
            if qty[t] > 0:
                tp = entry[t] * (1 + target)
                if high[i] >= tp:
                    cash[t] = qty[t] * tp * (1 - fee)
                    qty[t] = 0.0
                    sells += 1
                    hold_days.append(i - buy_i[t])
                    trades.append((times[i], tp, "sell", t + 1))
            elif dd[i] <= -dips[t] and cash[t] > 0:
                qty[t] = cash[t] / close[i] * (1 - fee)
                entry[t] = close[i]
                buy_i[t] = i
                cost[t] = cash[t]
                cash[t] = 0.0
                trades.append((times[i], close[i], "buy", t + 1))
        if any(q > 0 for q in qty):
            days_in += 1
        equity[idx] = sum(cash) + sum(qty) * close[i]

    final = float(equity[-1])
    total = final / capital - 1
    years = (n - start) / 365
    open_t = [t for t in range(k) if qty[t] > 0]
    open_cost = float(sum(cost[t] for t in open_t))
    open_value = float(sum(qty[t] for t in open_t) * close[-1])
    return {
        "valid": True,
        "capital": capital,
        "final_eur": final,
        "profit_eur": final - capital,
        "dip_total_pct": total * 100,
        "dip_annual_pct": ((1 + total) ** (1 / years) - 1) * 100 if years >= 0.5 and total > -1 else np.nan,
        "dip_annual_raw_pct": ((1 + total) ** (1 / years) - 1) * 100 if years > 0 and total > -1 else np.nan,
        "short_period": bool(years < 0.5),
        "dip_round_trips": sells,
        "bt_start": pd.Timestamp(times[start]),
        "bt_years": years,
        "avg_hold_days": float(np.mean(hold_days)) if hold_days else np.nan,
        "open_days": (n - 1 - min(buy_i[t] for t in open_t)) if open_t else np.nan,
        "invested_pct": days_in / (n - start) * 100,
        "lowest_eur": float(equity.min()),
        "lowest_pct": (float(equity.min()) / capital - 1) * 100,
        "open_slots": len(open_t),
        "open_cost_eur": open_cost if open_t else np.nan,
        "open_value_eur": open_value if open_t else np.nan,
        "open_result_eur": (open_value - open_cost) if open_t else np.nan,
        "open_result_pct": ((open_value / open_cost - 1) * 100) if open_t and open_cost > 0 else np.nan,
        "buy_hold_eur": capital * close[-1] / close[start],
        "buy_hold_pct": (close[-1] / close[start] - 1) * 100,
        # laagste waarde die kopen&houden onderweg had (zelfde definitie als 'lowest_eur')
        "buy_hold_lowest_eur": float(capital * np.min(close[start:]) / close[start]),
        "equity": pd.Series(equity, index=df["time"].iloc[start:].to_numpy()),
        "trades": pd.DataFrame(trades, columns=["time", "price", "side", "schijf"]),
    }


# --------------------------------------------------------------------------- optimalisatie
def optimize_dip(df: pd.DataFrame, lookback: int, fee: float, min_trades: int = 3) -> dict:
    """
    Test alle combinaties koopdrempel × winstdoel (1 schijf) en kiest de historisch beste.
    'Beste' = hoogste ROBUUSTE %/jaar: mediaan van de combinatie zelf en haar buren in het rooster.
    Zo wint geen toevalstreffer, maar een zone waar het resultaat stabiel goed is.
    Combinaties met minder dan `min_trades` afgeronde trades tellen niet mee (te weinig bewijs).
    """
    dd = drawdown_series(df, lookback).to_numpy(float)
    nd, nt = len(DIP_GRID), len(TARGET_GRID)
    ann = np.full((nd, nt), np.nan)
    trades = np.zeros((nd, nt), dtype=int)
    rows = []
    for a, dip in enumerate(DIP_GRID):
        for b, tgt in enumerate(TARGET_GRID):
            bt = ladder_backtest(df, lookback, [(float(dip), 1000.0)], float(tgt), fee, dd=dd)
            if not bt.get("valid"):
                continue
            trades[a, b] = bt["dip_round_trips"]
            if bt["dip_round_trips"] >= min_trades and not np.isnan(bt["dip_annual_pct"]):
                ann[a, b] = bt["dip_annual_pct"]
            rows.append({"dip_pct": dip * 100, "target_pct": tgt * 100, "annual_pct": bt["dip_annual_pct"],
                         "trades": bt["dip_round_trips"], "lowest_pct": bt["lowest_pct"]})

    robust = np.full_like(ann, np.nan)
    for a in range(nd):
        for b in range(nt):
            if not np.isnan(ann[a, b]):
                block = ann[max(0, a - 1):a + 2, max(0, b - 1):b + 2]
                robust[a, b] = np.nanmedian(block)

    grid = pd.DataFrame(rows)
    if np.all(np.isnan(robust)):
        return {"found": False, "grid": grid,
                "reason": f"geen enkele combinatie met minstens {min_trades} afgeronde trades"}
    a, b = np.unravel_index(np.nanargmax(robust), robust.shape)
    return {"found": True, "dip": float(DIP_GRID[a]), "target": float(TARGET_GRID[b]),
            "annual_pct": float(ann[a, b]), "robust_pct": float(robust[a, b]),
            "trades": int(trades[a, b]), "grid": grid}


def suggest_ladder(dip: float, amount: float, parts: int = 3, spacing: float = 0.10) -> list[tuple[float, float]]:
    """Bedrag gelijk verdelen over `parts` schijven, telkens `spacing` dieper (max 90%). (Niet meer standaard.)"""
    amt = round(amount / parts, 2)
    return [(min(0.90, round(dip + i * spacing, 2)), amt) for i in range(parts)]


# --------------------------------------------------------------------------- training / test
def walk_forward(df: pd.DataFrame, lookback: int, fee: float, min_trades: int = 3,
                 test_frac: float = 0.30, fixed: dict | None = None) -> dict:
    """
    Eerlijke test. De backtest-periode wordt in twee gesplitst:
      TRAINING = eerste (1 - test_frac) deel
      TEST     = laatste test_frac deel: de instellingen worden blind toegepast op data die de
                 zoektocht NIET gezien heeft, met vers kapitaal.
    De test krijgt de voorafgaande `lookback` dagen mee, zodat de 'top' meteen gekend is.

    fixed=None  -> modus 'Optimaal': het optimum wordt enkel in de training gezocht.
    fixed={"tranches": [(drempel, bedrag), ...], "target": 0.3}
                -> modus 'Vaste waarden' of 'Opgeslagen': precies déze instellingen worden getest.

    train_annual_pct / test_annual_pct worden ALTIJD berekend (ook bij een periode < 0,5 jaar);
    train_short / test_short zeggen of die periode korter dan 0,5 jaar is.
    """
    n = len(df)
    bt_len = n - (lookback - 1)
    split = (lookback - 1) + int(bt_len * (1 - test_frac))
    if test_frac <= 0 or split - (lookback - 1) < 180 or n - split < 60:
        return {"wf_ok": False, "wf_reason": "te weinig historiek om te splitsen"}

    train_df = df.iloc[:split].reset_index(drop=True)
    if fixed is None:
        opt = optimize_dip(train_df, lookback, fee, min_trades)
        if not opt["found"]:
            return {"wf_ok": False, "wf_reason": "geen optimum in de trainingsperiode (" + opt["reason"] + ")"}
        tr, target, wf_dip = [(opt["dip"], 1000.0)], opt["target"], opt["dip"]
    else:
        tr = [(float(d), float(a)) for d, a in fixed["tranches"]]
        target = float(fixed["target"])
        wf_dip = min(d for d, _ in tr)

    bt_tr = ladder_backtest(train_df, lookback, tr, target, fee)
    test_df = df.iloc[split - (lookback - 1):].reset_index(drop=True)
    bt_te = ladder_backtest(test_df, lookback, tr, target, fee)
    if not (bt_tr.get("valid") and bt_te.get("valid")):
        return {"wf_ok": False, "wf_reason": "backtest ongeldig"}

    buys = int((bt_te["trades"]["side"] == "buy").sum()) if not bt_te["trades"].empty else 0
    train_buys = int((bt_tr["trades"]["side"] == "buy").sum()) if not bt_tr["trades"].empty else 0
    status = "Geen koopkans" if buys == 0 else ("Positie open" if bt_te["open_slots"] else "Afgerond")
    return {
        "wf_ok": True,
        "wf_dip": wf_dip, "wf_target": target, "wf_fixed": fixed is not None,
        "wf_capital": float(sum(a for _, a in tr)),
        "train_start": bt_tr["bt_start"], "train_years": bt_tr["bt_years"],
        "train_pct": bt_tr["dip_total_pct"], "train_annual_pct": bt_tr["dip_annual_raw_pct"],
        "train_short": bt_tr["short_period"],
        "train_trades": bt_tr["dip_round_trips"], "train_buys": train_buys,
        "test_start": bt_te["bt_start"], "test_years": bt_te["bt_years"],
        "test_pct": bt_te["dip_total_pct"], "test_annual_pct": bt_te["dip_annual_raw_pct"],
        "test_short": bt_te["short_period"],
        "test_trades": bt_te["dip_round_trips"], "test_buys": buys,
        "test_bh_pct": bt_te["buy_hold_pct"], "test_status": status,
        "test_open_days": bt_te["open_days"], "test_open_pct": bt_te["open_result_pct"],
    }


# --------------------------------------------------------------------------- top & koopniveau
def top_info(df: pd.DataFrame, lookback: int, dips: list[float], target: float) -> dict:
    """
    De 'top' = hoogste koers (intraday high) van de laatste `lookback` dagen. Dat is een MEEBEWEGEND venster,
    geen vaste top: een oude piek valt na `lookback` dagen weg en dan wordt de top lager.
    Koopniveau per schijf = top × (1 − drempel). Verkoopdoel = werkelijke aankoopprijs × (1 + winstdoel).
    """
    n = len(df)
    win = df["high"].to_numpy(float)[n - lookback:]
    i_top = n - lookback + int(np.argmax(win))
    top = float(df["high"].iloc[i_top])
    top_date = pd.Timestamp(df["time"].iloc[i_top])
    age = n - 1 - i_top
    days_left = max(lookback - age, 0)                 # dagen tot deze top uit het venster valt
    nxt = float(df["high"].iloc[i_top + 1:].max()) if i_top + 1 < n else top
    price = float(df["close"].iloc[-1])
    levels = []
    for dip in sorted(dips):
        lvl = top * (1 - dip)
        levels.append({"dip": dip, "buy_level": lvl, "sell_target": lvl * (1 + target),
                       "to_zone_pct": max(0.0, (price / lvl - 1) * 100) if price > lvl else 0.0,
                       "in_zone": price <= lvl, "level_after": nxt * (1 - dip)})
    return {"top": top, "top_date": top_date, "top_age": age, "days_left": days_left,
            "next_top": nxt, "price": price, "dd_pct": (price / top - 1) * 100, "levels": levels}
