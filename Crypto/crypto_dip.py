"""Dip-kopen: koop als de koers diep onder het hoogste punt van de voorbije periode staat,
verkoop bij een vast winstdoel. Ondersteunt meerdere schijven (bedragen) per munt,
een automatische zoektocht naar de historisch beste koopdrempel/winstdoel per munt,
en een betrouwbaarheidstest met MEERDERE TESTVENSTERS (walk_forward_multi).

SNELHEID_2026-10-16: de optimalisatie gebruikt een snelle variant van de backtest voor één schijf
(_fast_single), identiek resultaat aan ladder_backtest met één schijf maar veel sneller.

TESTVENSTERS_2026-10-17: de werkwijze ('zoek de beste instelling op het verleden, pas ze toe op de toekomst')
wordt in meerdere opeenvolgende jaarvensters blind getest. Per venster wordt de instelling gezocht op ALLE data
vóór dat venster.

DOORLOPEND_2026-10-17: de vensters vormen ÉÉN doorlopende simulatie met hetzelfde geld, zoals in het echt.
Een positie die op het einde van een venster nog open staat, loopt door in het volgende venster en wordt verkocht
volgens HAAR EIGEN winstdoel. De nieuwe instelling van een venster geldt enkel voor nieuwe aankopen.
'Gerealiseerd' = vrij geld + aankoopbedrag van een open positie (= alsof die aan haar aankoopprijs verkocht werd):
enkel echt verkochte winst telt."""
from __future__ import annotations

import numpy as np
import pandas as pd

DIP_GRID = np.round(np.arange(0.30, 0.851, 0.05), 2)            # koopdrempels 30..85%
TARGET_GRID = np.array([0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00])  # winstdoelen

# Wanneer telt iets als een NIEUWE keer in de koopzone (zie episode_starts)
EPISODE_GAP_DAYS = 30
EPISODE_REBOUND = 0.10

# Testvensters
WINDOW_DAYS = 365         # lengte van één testvenster
MIN_TRAIN_DAYS = 365      # minstens zoveel backtest-dagen vóór een venster om op te zoeken (technisch minimum)
MIN_WINDOW_DAYS = 90      # kortere vensters worden niet gebruikt
TRUNC_RATIO = 0.95        # venster korter dan 95% van WINDOW_DAYS = 'ingekort'
# Stabiel = de gevonden instelling verschuift weinig tussen vensters en t.o.v. vandaag
STABLE_DIP_SPREAD = 0.15
STABLE_TARGET_RATIO = 2.5


def drawdown_series(df: pd.DataFrame, lookback: int) -> pd.Series:
    """Daling t.o.v. het hoogste punt van de voorbije `lookback` dagen (negatief, bv. -0.45)."""
    roll_high = df["high"].rolling(lookback, min_periods=lookback).max()
    return df["close"] / roll_high - 1


def episode_starts(dd: np.ndarray, dip: float, gap_days: int = EPISODE_GAP_DAYS,
                   rebound: float = EPISODE_REBOUND) -> np.ndarray:
    """Eerste dag van elke AFZONDERLIJKE keer in de koopzone (= elke afzonderlijke crash)."""
    rebound = min(rebound, dip / 2)
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
    sig = dd <= -dip
    n = len(close)

    def outcome(i: int):
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
    raw_starts = int(np.sum(sig & ~np.concatenate(([False], sig[:-1]))))
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
    """Eén of meer schijven per munt over de hele historiek. Elke schijf = (koopdrempel, bedrag €):
    koop met het volledige schijfbedrag op slotkoers zodra de daling >= drempel, verkoop zodra de koers
    aankoop*(1+target) raakt, daarna opnieuw kopen als de voorwaarde nog geldt. Winst wordt herbelegd.
    'realized_eur' = vrij geld + aankoopbedrag van de open positie (alsof aan aankoopprijs verkocht)."""
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    times = df["time"].to_numpy()
    if dd is None:
        dd = drawdown_series(df, lookback).to_numpy(float)
    n = len(close)
    start = lookback - 1
    capital = float(sum(a for _, a in tranches))
    if n - start < 30 or capital <= 0:
        return {"capital": capital, "valid": False}

    k = len(tranches)
    dips = [d for d, _ in tranches]
    cash = [float(a) for _, a in tranches]
    qty = [0.0] * k
    entry = [0.0] * k
    cost = [0.0] * k
    buy_i = [0] * k
    hold_days = []
    trades, sells, buys, days_in = [], 0, 0, 0
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
                buys += 1
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
    realized = float(sum(cash)) + open_cost
    return {
        "valid": True,
        "capital": capital,
        "final_eur": final,
        "profit_eur": final - capital,
        "realized_eur": realized,
        "realized_pct": (realized / capital - 1) * 100,
        "dip_total_pct": total * 100,
        "dip_annual_pct": ((1 + total) ** (1 / years) - 1) * 100 if years >= 0.5 and total > -1 else np.nan,
        "dip_annual_raw_pct": ((1 + total) ** (1 / years) - 1) * 100 if years > 0 and total > -1 else np.nan,
        "short_period": bool(years < 0.5),
        "dip_round_trips": sells,
        "dip_buys": buys,
        "bt_start": pd.Timestamp(times[start]),
        "bt_end": pd.Timestamp(times[-1]),
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
        "buy_hold_lowest_eur": float(capital * np.min(close[start:]) / close[start]),
        "equity": pd.Series(equity, index=df["time"].iloc[start:].to_numpy()),
        "trades": pd.DataFrame(trades, columns=["time", "price", "side", "schijf"]),
    }


def _fast_single(high: list, close: list, dd: list, start: int, dip: float, target: float, fee: float,
                 capital: float = 1000.0) -> tuple[int, float, float]:
    """Snelle backtest voor ÉÉN schijf (zelfde regels als ladder_backtest): (trades, eindwaarde, laagste)."""
    cash, qty, entry, sells, lowest = capital, 0.0, 0.0, 0, capital
    thr, up, keep = -dip, 1.0 + target, 1.0 - fee
    for i in range(start, len(close)):
        if qty > 0.0:
            tp = entry * up
            if high[i] >= tp:
                cash = qty * tp * keep
                qty = 0.0
                sells += 1
        elif dd[i] <= thr and cash > 0.0:
            qty = cash / close[i] * keep
            entry = close[i]
            cash = 0.0
        eq = cash + qty * close[i]
        if eq < lowest:
            lowest = eq
    return sells, cash + qty * close[-1], lowest


# --------------------------------------------------------------------------- optimalisatie
def optimize_dip(df: pd.DataFrame, lookback: int, fee: float, min_trades: int = 3) -> dict:
    """Test alle combinaties koopdrempel × winstdoel (1 schijf) en kiest de historisch beste ROBUUSTE
    combinatie (mediaan van zichzelf + buren in het rooster)."""
    close_a = df["close"].to_numpy(float)
    n = len(close_a)
    start = lookback - 1
    nd, nt = len(DIP_GRID), len(TARGET_GRID)
    ann = np.full((nd, nt), np.nan)
    trades = np.zeros((nd, nt), dtype=int)
    rows = []
    if n - start >= 30:
        high = df["high"].to_numpy(float).tolist()
        close = close_a.tolist()
        dd = drawdown_series(df, lookback).to_numpy(float).tolist()
        years = (n - start) / 365
        cap = 1000.0
        for a, dip in enumerate(DIP_GRID):
            for b, tgt in enumerate(TARGET_GRID):
                sells, final, lowest = _fast_single(high, close, dd, start, float(dip), float(tgt), fee, cap)
                total = final / cap - 1
                annual = ((1 + total) ** (1 / years) - 1) * 100 if years >= 0.5 and total > -1 else np.nan
                trades[a, b] = sells
                if sells >= min_trades and not np.isnan(annual):
                    ann[a, b] = annual
                rows.append({"dip_pct": dip * 100, "target_pct": tgt * 100, "annual_pct": annual,
                             "trades": sells, "lowest_pct": (lowest / cap - 1) * 100})

    robust = np.full_like(ann, np.nan)
    for a in range(nd):
        for b in range(nt):
            if not np.isnan(ann[a, b]):
                block = ann[max(0, a - 1):a + 2, max(0, b - 1):b + 2]
                robust[a, b] = np.nanmedian(block)

    grid = pd.DataFrame(rows, columns=["dip_pct", "target_pct", "annual_pct", "trades", "lowest_pct"])
    if np.all(np.isnan(robust)):
        return {"found": False, "grid": grid,
                "reason": f"geen enkele combinatie met minstens {min_trades} afgeronde trades"}
    a, b = np.unravel_index(np.nanargmax(robust), robust.shape)
    return {"found": True, "dip": float(DIP_GRID[a]), "target": float(TARGET_GRID[b]),
            "annual_pct": float(ann[a, b]), "robust_pct": float(robust[a, b]),
            "trades": int(trades[a, b]), "grid": grid}


def suggest_ladder(dip: float, amount: float, parts: int = 3, spacing: float = 0.10) -> list[tuple[float, float]]:
    """Bedrag gelijk verdelen over `parts` schijven, telkens `spacing` dieper (max 90%). (Niet standaard.)"""
    amt = round(amount / parts, 2)
    return [(min(0.90, round(dip + i * spacing, 2)), amt) for i in range(parts)]


# --------------------------------------------------------------------------- meerdere testvensters
def is_stable(settings: list[tuple[float, float]]) -> bool | None:
    """Stabiel = koopdrempels binnen STABLE_DIP_SPREAD en hoogste winstdoel ≤ STABLE_TARGET_RATIO × laagste."""
    s = [(d, t) for d, t in settings if d is not None and t is not None]
    if len(s) < 2:
        return None
    dips = [d for d, _ in s]
    tgts = [t for _, t in s]
    return (max(dips) - min(dips) <= STABLE_DIP_SPREAD + 1e-9) and (max(tgts) / min(tgts) <= STABLE_TARGET_RATIO)


def walk_forward_multi(df: pd.DataFrame, lookback: int, fee: float, min_trades: int = 3, n_windows: int = 3,
                       capital: float = 1000.0, fixed: dict | None = None,
                       window_days: int = WINDOW_DAYS) -> dict:
    """
    Meerdere testvensters van `window_days` dagen, achteraan de historiek (het laatste eindigt vandaag), als
    ÉÉN DOORLOPENDE simulatie met hetzelfde geld:
      - per venster wordt de instelling gezocht op alle data vóór het venster (fixed=None), of precies jouw
        instelling gebruikt (fixed={"tranches": [...], "target": ...});
      - die instelling geldt voor NIEUWE aankopen in dat venster;
      - een positie die bij de start van een venster nog open staat, loopt door en wordt verkocht volgens
        haar eigen winstdoel (van het venster waarin ze gekocht werd).
    Per venster: periode, lengte (ingekort?), instelling, aankopen, verkopen, doorgeschoven positie,
    gerealiseerd %, open %, totaal %, kopen&houden %. Samengevat: gerealiseerd en totaal t.o.v. het
    startbedrag, per jaar, positieve vensters, open positie vandaag, stabiliteit, trainingsduur eerste venster.
    """
    n = len(df)
    bt0 = lookback - 1
    times = df["time"]
    windows = []
    for k in range(n_windows):
        end = n - k * window_days
        start = max(end - window_days, bt0 + MIN_TRAIN_DAYS)
        if end - start < MIN_WINDOW_DAYS:
            break
        windows.append((start, end))
    windows.reverse()
    if not windows:
        return {"wf_ok": False, "wf_reason": "te weinig historiek voor een testvenster "
                f"(minstens {MIN_TRAIN_DAYS} + {MIN_WINDOW_DAYS} dagen na de referentieperiode)"}

    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    dd = drawdown_series(df, lookback).to_numpy(float)

    # Instelling per venster
    plans = []
    for s, e in windows:
        if fixed is None:
            opt = optimize_dip(df.iloc[:s].reset_index(drop=True), lookback, fee, min_trades)
            if opt["found"]:
                plans.append({"dips": [opt["dip"]], "shares": [1.0], "target": opt["target"], "reason": ""})
            else:
                plans.append({"dips": None, "shares": None, "target": None,
                              "reason": "geen instelling gevonden in de training: geen nieuwe aankopen"})
        else:
            tot = sum(a for _, a in fixed["tranches"]) or 1.0
            plans.append({"dips": [float(d) for d, _ in fixed["tranches"]],
                          "shares": [float(a) / tot for _, a in fixed["tranches"]],
                          "target": float(fixed["target"]), "reason": ""})
    if all(p["dips"] is None for p in plans):
        return {"wf_ok": False, "wf_reason": plans[0]["reason"].split(":")[0]}

    # Schijven: aantal = maximum over de vensters (bij 'Optimaal' altijd 1). Elke schijf heeft eigen geld.
    k = max(len(p["dips"]) for p in plans if p["dips"])
    first = next(p for p in plans if p["dips"])
    shares = (first["shares"] + [0.0] * k)[:k]
    cash = [capital * sh for sh in shares]
    qty, entry, cost, tgt_open, buy_i = [0.0] * k, [0.0] * k, [0.0] * k, [0.0] * k, [0] * k

    def mtm(i):
        return sum(cash) + sum(qty) * close[i]

    def real():
        return sum(cash) + sum(cost[t] for t in range(k) if qty[t] > 0)

    rows = []
    prev_close_idx = windows[0][0] - 1
    for w, ((s, e), plan) in enumerate(zip(windows, plans), 1):
        carried = any(q > 0 for q in qty)
        m0, r0 = mtm(prev_close_idx), real()
        buys = sells = 0
        dips = plan["dips"]
        for i in range(s, e):
            for t in range(k):
                if qty[t] > 0:
                    tp = entry[t] * (1 + tgt_open[t])
                    if high[i] >= tp:
                        cash[t] = qty[t] * tp * (1 - fee)
                        qty[t] = 0.0
                        sells += 1
                elif dips is not None and t < len(dips) and cash[t] > 0 and dd[i] <= -dips[t]:
                    qty[t] = cash[t] / close[i] * (1 - fee)
                    entry[t] = close[i]
                    cost[t] = cash[t]
                    tgt_open[t] = plan["target"]
                    buy_i[t] = i
                    cash[t] = 0.0
                    buys += 1
        m1, r1 = mtm(e - 1), real()
        open_t = [t for t in range(k) if qty[t] > 0]
        open_cost = sum(cost[t] for t in open_t)
        open_val = sum(qty[t] for t in open_t) * close[e - 1]
        if open_t:
            status = "Positie open" + (" (doorgeschoven)" if carried and buys == 0 and sells == 0 else "")
        elif buys or sells:
            status = "Afgerond"
        else:
            status = "Geen koopkans"
        days = e - s
        rows.append({
            "nr": w, "ok": True, "train_start": times.iloc[bt0], "test_start": times.iloc[s],
            "test_end": times.iloc[e - 1], "years": days / 365, "days": days,
            "truncated": bool(days < window_days * TRUNC_RATIO),
            "dip": (min(dips) if dips else None), "target": plan["target"], "plan_reason": plan["reason"],
            "carried_in": carried, "buys": buys, "trades": sells, "status": status,
            "realized_pct": (r1 / r0 - 1) * 100 if r0 > 0 else np.nan,
            "open_pct": (open_val / open_cost - 1) * 100 if open_t and open_cost > 0 else np.nan,
            "total_pct": (m1 / m0 - 1) * 100 if m0 > 0 else np.nan,
            "bh_pct": (close[e - 1] / close[prev_close_idx] - 1) * 100,
            "open_days": (e - 1 - min(buy_i[t] for t in open_t)) if open_t else np.nan,
        })
        prev_close_idx = e - 1

    years = sum(r["years"] for r in rows)
    m_final, r_final = mtm(n - 1), real()
    bh_mult = close[n - 1] / close[windows[0][0] - 1]

    def ann(mult):
        return ((mult ** (1 / years)) - 1) * 100 if years > 0 and mult > 0 else np.nan

    last = rows[-1]
    open_now = last["open_pct"] if last["status"].startswith("Positie open") else np.nan
    return {
        "wf_ok": True, "wf_fixed": fixed is not None, "windows": rows,
        "n_windows": len(rows), "test_years": years,
        "train_years_first": (windows[0][0] - bt0) / 365,
        "n_truncated": int(sum(1 for r in rows if r["truncated"])),
        "test_start": rows[0]["test_start"], "test_end": last["test_end"],
        "real_trades": int(sum(r["trades"] for r in rows)), "buys": int(sum(r["buys"] for r in rows)),
        "real_total_pct": (r_final / capital - 1) * 100, "real_annual_pct": ann(r_final / capital),
        "total_total_pct": (m_final / capital - 1) * 100, "total_annual_pct": ann(m_final / capital),
        "bh_total_pct": (bh_mult - 1) * 100, "bh_annual_pct": ann(bh_mult),
        "win_pos": int(sum(1 for r in rows if not np.isnan(r["total_pct"]) and r["total_pct"] > 0)),
        "win_active": int(sum(1 for r in rows if r["buys"] or r["trades"] or r["carried_in"])),
        "open_now_pct": open_now,
        "open_now_days": last["open_days"] if not np.isnan(open_now) else np.nan,
        "settings": [(r["dip"], r["target"]) for r in rows if r["dip"] is not None],
        "short_test": bool(years < 0.5),
    }


# --------------------------------------------------------------------------- top & koopniveau
def top_info(df: pd.DataFrame, lookback: int, dips: list[float], target: float) -> dict:
    """De 'top' = hoogste koers (intraday high) van de laatste `lookback` dagen (MEEBEWEGEND venster).
    Koopniveau per schijf = top × (1 − drempel). Verkoopdoel = werkelijke aankoopprijs × (1 + winstdoel)."""
    n = len(df)
    win = df["high"].to_numpy(float)[n - lookback:]
    i_top = n - lookback + int(np.argmax(win))
    top = float(df["high"].iloc[i_top])
    top_date = pd.Timestamp(df["time"].iloc[i_top])
    age = n - 1 - i_top
    days_left = max(lookback - age, 0)
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
