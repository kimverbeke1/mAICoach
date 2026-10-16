"""Eenvoudige spot-grid backtest: koop bij elke daling van `step`, verkoop zodra +`step` bereikt is."""
from __future__ import annotations

import pandas as pd


def grid_backtest(df: pd.DataFrame, step: float, levels: int, fee: float,
                  capital: float = 1000.0) -> dict:
    """
    Startprijs P0 = eerste close. Kooplevels L_i = P0*(1-step)^i, i=1..levels.
    Elk level krijgt capital/levels. Gekocht op L_i -> verkocht op L_i*(1+step).
    `fee` = kost per transactie (bv. 0.001 = 0.1%), incl. ingeschatte spread.
    Conservatief: per candle per level eerst verkopen, nooit kopen+verkopen in dezelfde candle.
    """
    p0 = float(df["close"].iloc[0])
    slot = capital / levels
    buy_lv = [p0 * (1 - step) ** i for i in range(1, levels + 1)]
    qty = [0.0] * levels
    cash = capital
    trades, round_trips, realized = [], 0, 0.0

    for row in df.itertuples(index=False):
        for i, lv in enumerate(buy_lv):
            sell_lv = lv * (1 + step)
            if qty[i] > 0:
                if row.high >= sell_lv:
                    proceeds = qty[i] * sell_lv * (1 - fee)
                    realized += proceeds - slot
                    cash += proceeds
                    qty[i] = 0.0
                    round_trips += 1
                    trades.append((row.time, sell_lv, "sell"))
            elif row.low <= lv and cash >= slot - 1e-9:
                qty[i] = slot / lv * (1 - fee)
                cash -= slot
                trades.append((row.time, lv, "buy"))

    last = float(df["close"].iloc[-1])
    holdings = sum(qty) * last
    equity = cash + holdings
    return {
        "grid_round_trips": round_trips,
        "grid_realized_pct": realized / capital * 100,
        "grid_net_pct": (equity / capital - 1) * 100,
        "grid_open_slots": sum(1 for q in qty if q > 0),
        "buy_hold_pct": (last / p0 - 1) * 100,
        "net_per_trip_pct": ((1 + step) * (1 - fee) ** 2 - 1) * 100,
        "trades": pd.DataFrame(trades, columns=["time", "price", "side"]),
        "buy_levels": buy_lv,
    }
