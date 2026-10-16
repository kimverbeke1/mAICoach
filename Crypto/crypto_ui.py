"""Streamlit-pagina Crypto.
- In de hoofdapp (streamlit_app.py) via Crypto/crypto_page.py.
- Lokaal los te draaien via:  streamlit run crypto_app.py
Koersdata: Coinbase. Opslag: Firestore (cloud) of lokaal (crypto_store.py)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import crypto_settings as cs
import crypto_store as store
from crypto_backtest import grid_backtest
from crypto_data import base_of, coinbase_label, get_coinbase_products, get_klines, get_top_symbols, quote_of
from crypto_dip import dip_stats, drawdown_series, ladder_backtest, optimize_dip, top_info, walk_forward
from crypto_metrics import add_score, compute_metrics, zigzag_pivots
from crypto_scan import (TEST_COLS, cfg_key, coin_params, finalize, fmt_annual, scan_coin, setup_text,
                         table_from_json, table_to_json, wf_for)
from crypto_texts import C_HELP, DIP_EXAMPLES, DIP_EXPLAIN, GENERAL, H, VERDICT_RULES

K = "crypto_"  # prefix voor session_state-keys (geen botsing met mAICoach/PadelAnalysis)

FEE_PRESETS = {"Coinbase (intro)": (0.25, 0.50), "Eigen waarden": None}
VERDICT_LABELS = ["🟢 Interessant", "🟡 Twijfel", "⚪ Niets bewezen", "⚪ Niet getest",
                  "🟠 Onder water", "🔴 Niet interessant"]
VERDICT_COLORS = {"🟢": "#d4f4dd", "🟡": "#fff1b8", "⚪": "#e9ecef", "🟠": "#ffe0b8", "🔴": "#f8d7da"}
DEFAULT_COINS = ["BTC-USD", "ETH-USD", "SOL-USD"]


def _num(label, fmt, key):
    return st.column_config.NumberColumn(label, format=fmt, help=C_HELP.get(key))


# --------------------------------------------------------------------------- data (gecached)
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _coinbase_cached() -> dict:
    return get_coinbase_products()  # raise bij mislukking => wordt niet gecached


def _cb_products() -> dict | None:
    try:
        return _coinbase_cached()["products"]
    except Exception as e:  # noqa: BLE001
        st.session_state[K + "cb_error"] = str(e)
        return None


def _cb_text(symbol: str) -> str:
    return coinbase_label(_cb_products(), base_of(symbol))


@st.cache_data(ttl=900, show_spinner=False)
def _top_symbols(n: int) -> pd.DataFrame:
    return get_top_symbols(n)


@st.cache_data(ttl=900, show_spinner=False)
def _klines(symbol: str, interval: str, days: int) -> pd.DataFrame:
    return get_klines(symbol, interval, days)


@st.cache_data(ttl=3600, show_spinner=False)
def _optimize(symbol: str, days: int, lookback: int, fee: float, min_trades: int) -> dict:
    return optimize_dip(_klines(symbol, "1d", days), lookback, fee, min_trades)


@st.cache_data(ttl=3600, show_spinner=False)
def _walk_forward(symbol: str, days: int, lookback: int, fee: float, min_trades: int, test_frac: float,
                  fixed_tr: tuple | None = None, fixed_target: float | None = None) -> dict:
    """fixed_tr/fixed_target = None: optimum in de training zoeken. Anders: precies die instelling blind testen."""
    fixed = None if fixed_tr is None else {"tranches": list(fixed_tr), "target": fixed_target}
    return walk_forward(_klines(symbol, "1d", days), lookback, fee, min_trades, test_frac, fixed)


def _opt_fn(cfg: dict):
    return lambda s: _optimize(s, cfg["days"], cfg["lookback"], cfg["fee"], cfg["min_trades"])


def _wf_fn(cfg: dict):
    return lambda s, tr, tg: _walk_forward(s, cfg["days"], cfg["lookback"], cfg["fee"], cfg["min_trades"],
                                           cfg["test_frac"], tr, tg)


# --------------------------------------------------------------------------- kosten + bron
def _fee_settings() -> float:
    with st.expander("💶 Kosten (fees)", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        preset = c1.selectbox("Beurs", list(FEE_PRESETS), key=K + "preset", help=H["preset"])
        vals = FEE_PRESETS[preset]
        locked = vals is not None
        maker = c2.number_input("Maker-fee %", 0.0, 2.0, vals[0] if locked else 0.25, 0.05,
                                key=K + "maker_" + preset, disabled=locked, help=H["maker"])
        taker = c3.number_input("Taker-fee %", 0.0, 2.0, vals[1] if locked else 0.50, 0.05,
                                key=K + "taker_" + preset, disabled=locked, help=H["taker"])
        otype = c4.radio("Ordertype", ["Limit (maker)", "Market (taker)"], key=K + "otype",
                         help=H["ordertype"])
        spread = c5.number_input("Extra spread %", 0.0, 1.0, 0.0, 0.05, key=K + "spread", help=H["spread"])
        fee_pct = (maker if otype.startswith("Limit") else taker) + spread
        rt = (1 - (1 - fee_pct / 100) ** 2) * 100
        st.caption(f"Kost per transactie: **{fee_pct:.2f}%** → per koop+verkoop: **{rt:.2f}%**")
    return fee_pct / 100


def _source_caption() -> None:
    try:
        cb = _coinbase_cached()
        n_ok = sum(1 for p in cb["products"].values() if p["quotes"])
        cb_txt = f"Coinbase-lijst van {cb['fetched']} ({n_ok} verhandelbare munten" + \
                 (", oudere cache" if cb.get("stale") else "") + ")"
    except Exception as e:  # noqa: BLE001
        cb_txt = f"⚠️ Coinbase-lijst niet beschikbaar: {e}"
    st.caption(f"Koersdata: **Coinbase** · Opslag: **{store.status()}** · {cb_txt}")


# --------------------------------------------------------------------------- grid
def _grid_settings(fee: float) -> dict:
    with st.expander("⚙️ Instellingen grid / swing", expanded=False):
        c1, c2, c3 = st.columns(3)
        interval = c1.selectbox("Candle-interval", ["15m", "1h", "6h"], index=1, key=K + "interval",
                                help=H["interval"])
        days = c2.selectbox("Periode (dagen)", [30, 60, 90, 180, 365], index=2, key=K + "days",
                            help=H["days"])
        top_n = c3.slider("Aantal munten (top volume)", 10, 80, 30, 5, key=K + "topn", help=H["topn"])
        c5, c6, c7 = st.columns(3)
        swing = c5.number_input("Swing-drempel %", 0.5, 20.0, 3.0, 0.5, key=K + "swing", help=H["swing"]) / 100
        step = c6.number_input("Grid-stap %", 0.3, 20.0, 2.0, 0.1, key=K + "step", help=H["step"]) / 100
        levels = c7.slider("Grid-levels (koopniveaus)", 2, 40, 10, key=K + "levels", help=H["levels"])
    return dict(interval=interval, days=days, top_n=top_n, fee=fee, swing=swing, step=step, levels=levels)


def _grid_tab(cfg: dict) -> None:
    st.caption("Korte termijn: veel kleine schommelingen benutten. Werkt enkel als de munt zijwaarts beweegt "
               "en de stap ruim boven de kosten ligt. (Uur/kwartier-data wordt lokaal gecached, niet in de cloud.)")
    if st.button("🔄 Grid-analyse uitvoeren", key=K + "run", type="primary"):
        try:
            tops = _top_symbols(cfg["top_n"])
        except Exception as e:
            st.error(f"Kon de Coinbase-munten niet ophalen: {e}")
            return
        rows, bar = [], st.progress(0.0, text="Data ophalen…")
        for i, (sym, cbt) in enumerate(zip(tops["symbol"], tops["coinbase"])):
            bar.progress((i + 1) / len(tops), text=f"{sym} ({i + 1}/{len(tops)})")
            try:
                df = _klines(sym, cfg["interval"], cfg["days"])
                if len(df) < 50:
                    continue
                m = compute_metrics(df, cfg["swing"])
                bt = grid_backtest(df, cfg["step"], cfg["levels"], cfg["fee"])
                m.update({k: v for k, v in bt.items() if k not in ("trades", "buy_levels")})
                rows.append({"symbol": sym, "coinbase": cbt, **m})
            except Exception as e:
                st.warning(f"{sym}: {e}")
        bar.empty()
        if rows:
            st.session_state[K + "table"] = add_score(pd.DataFrame(rows))
            st.session_state[K + "table_cfg"] = cfg

    table = st.session_state.get(K + "table")
    if table is None:
        st.info("Druk op **Grid-analyse uitvoeren**.")
        return
    if st.session_state.get(K + "table_cfg") != cfg:
        st.warning("Instellingen gewijzigd — voer de analyse opnieuw uit.")
    cols = ["symbol", "coinbase", "score", "swings_per_week", "avg_swing_pct", "efficiency", "autocorr_lag1",
            "grid_round_trips", "grid_net_pct", "buy_hold_pct", "drift_pct", "max_drawdown_pct",
            "quote_vol_day_musd"]
    st.dataframe(table[cols], hide_index=True, width="stretch", column_config={
        "symbol": "Munt",
        "coinbase": st.column_config.TextColumn("Coinbase", help=C_HELP["coinbase"]),
        "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f",
                                                 help=C_HELP["score"]),
        "swings_per_week": _num("Swings/week", "%.1f", "swings_per_week"),
        "avg_swing_pct": _num("Gem. swing %", "%.1f", "avg_swing_pct"),
        "efficiency": _num("Trend-efficiëntie", "%.3f", "efficiency"),
        "autocorr_lag1": _num("Autocorr", "%.3f", "autocorr_lag1"),
        "grid_round_trips": _num("Grid trades", "%d", "grid_round_trips"),
        "grid_net_pct": _num("Grid netto %", "%.1f", "grid_net_pct"),
        "buy_hold_pct": st.column_config.NumberColumn("Kopen&houden %", format="%.1f",
                                                      help="Resultaat als je bij de start alles kocht en hield."),
        "drift_pct": _num("Drift %", "%.1f", "drift_pct"),
        "max_drawdown_pct": _num("Max daling %", "%.1f", "max_drawdown_pct"),
        "quote_vol_day_musd": _num("Volume/dag (M$)", "%.0f", "quote_vol_day_musd"),
    })
    net = ((1 + cfg["step"]) * (1 - cfg["fee"]) ** 2 - 1) * 100
    st.caption(f"Netto winst per afgeronde grid-trade: **{net:.2f}%**.")


# --------------------------------------------------------------------------- dip: instellingen
def _dip_settings(fee: float, top_n: int) -> dict:
    with st.expander("⚙️ Instellingen dip-kopen", expanded=False):
        c1, c2, c3 = st.columns(3)
        years = c1.selectbox("Historiek (jaar)", [2, 3, 5, 8], index=2, key=K + "dip_years", help=H["dip_hist"])
        lookback = c2.selectbox("Referentie 'hoogste punt' (dagen)", [90, 180, 365, 730], index=2,
                                key=K + "dip_lookback", help=H["lookback"])
        amount = c3.number_input("Bedrag per munt (€)", 50.0, 1_000_000.0, 1000.0, 100.0,
                                 key=K + "dip_amount", help=H["amount"])
        mode = st.radio("Koopdrempel en winstdoel", ["Optimaal per munt (automatisch)", "Vaste waarden"],
                        horizontal=True, key=K + "dip_mode", help=H["mode"])
        fixed = mode.startswith("Vaste")
        c4, c5, c6, c7 = st.columns(4)
        dip = c4.number_input("Koopdrempel: daling %", 10.0, 95.0, 50.0, 5.0, key=K + "dip_dip",
                              help=H["dip"], disabled=not fixed) / 100
        target = c5.number_input("Winstdoel %", 2.0, 300.0, 30.0, 5.0, key=K + "dip_target",
                                 help=H["target"], disabled=not fixed) / 100
        maxwait = c6.selectbox("Max. wachttijd voor 'kans' (dagen)", [30, 90, 180, 365, 730], index=3,
                               key=K + "dip_maxwait", help=H["maxwait"])
        min_trades = c7.number_input("Min. trades (optimalisatie)", 1, 20, 3, 1, key=K + "dip_mintrades",
                                     help=H["min_trades"])
        test_frac = st.select_slider("🧪 Betrouwbaarheidstest: testperiode = laatste … van de backtest",
                                     options=[0, 20, 25, 30, 40, 50], value=30, format_func=lambda v: f"{v}%",
                                     key=K + "dip_testfrac", help=H["test_frac"]) / 100
    return dict(days=years * 365 + 5, lookback=lookback, amount=amount, optimal=not fixed, dip=dip,
                target=target, maxwait=maxwait, min_trades=int(min_trades), fee=fee, top_n=top_n,
                test_frac=test_frac, only_cb=True)


def _coin_params(sym: str, cfg: dict) -> dict:
    return coin_params(sym, cfg, cs.load_all(), _opt_fn(cfg))


def _style_verdict(df: pd.DataFrame):
    def _c(v):
        if isinstance(v, str):
            for k, c in VERDICT_COLORS.items():
                if v.startswith(k):
                    return f"background-color: {c}; color: #111"
        return ""
    try:
        return df.style.map(_c, subset=["verdict", "why"])
    except Exception:  # oudere pandas/jinja2: gewoon zonder kleur tonen
        return df


def _set_table(t: pd.DataFrame, key: str, ts: float, source: str) -> None:
    st.session_state[K + "dip_table"] = t
    st.session_state[K + "dip_key"] = key
    st.session_state[K + "dip_meta"] = {"ts": ts, "source": source}
    st.session_state[K + "dip_ver"] = st.session_state.get(K + "dip_ver", 0) + 1


def _compute_table(cfg: dict) -> pd.DataFrame | None:
    try:
        tops = _top_symbols(cfg["top_n"])
    except Exception as e:
        st.error(f"Kon de Coinbase-munten niet ophalen: {e}")
        return None
    settings = cs.load_all()
    rows = []
    bar = st.progress(0.0, text="Dagdata bijwerken" + (" en optimaliseren…" if cfg["optimal"] else "…"))
    for i, (sym, cbt) in enumerate(zip(tops["symbol"], tops["coinbase"])):
        bar.progress((i + 1) / len(tops), text=f"{sym} ({i + 1}/{len(tops)})")
        try:
            df = _klines(sym, "1d", cfg["days"])
            r = scan_coin(sym, cbt, cfg, settings, df, _opt_fn(cfg), _wf_fn(cfg))
            if r:
                rows.append(r)
        except Exception as e:
            st.warning(f"{sym}: {e}")
    bar.empty()
    return finalize(rows) if rows else None


# --------------------------------------------------------------------------- dip: tabel
def _dip_tab(cfg: dict) -> None:
    st.caption("Lange termijn: koop enkel na een diepe val, verkoop bij een winstdoel en wacht zo lang als nodig.")
    key = cfg_key(cfg, cs.load_all())

    # Bewaard resultaat voor deze instellingen? Eén keer per sleutel per sessie opzoeken.
    if st.session_state.get(K + "dip_key") != key and st.session_state.get(K + "dip_tried") != key:
        st.session_state[K + "dip_tried"] = key
        try:
            res = store.load_result(key)
        except Exception as e:  # noqa: BLE001
            res = None
            st.caption(f"Bewaard resultaat niet leesbaar: {e}")
        if res:
            try:
                _set_table(table_from_json(res["json"]), key, res.get("ts", 0), res.get("source", "?"))
            except Exception as e:  # noqa: BLE001
                st.caption(f"Bewaard resultaat ongeldig: {e}")

    have_current = st.session_state.get(K + "dip_key") == key
    label = "🔄 Opnieuw berekenen" if have_current else "🔄 Dip-analyse uitvoeren"
    if st.button(label, key=K + "dip_run", type="primary",
                 help="Werkt de koersdata bij (enkel nieuwe dagen) en rekent de tabel opnieuw. "
                      "Het resultaat wordt bewaard, zodat het de volgende keer meteen klaarstaat."):
        t_new = _compute_table(cfg)
        if t_new is not None:
            _set_table(t_new, key, time.time(), "app")
            try:
                store.save_result(key, table_to_json(t_new), "app")
            except Exception as e:  # noqa: BLE001
                st.warning(f"Resultaat niet bewaard: {e}")

    t = st.session_state.get(K + "dip_table")
    if t is None:
        st.info("Nog geen resultaat voor deze instellingen. Druk op **Dip-analyse uitvoeren**: de eerste keer "
                "duurt dit wat langer (koersdata + optimalisatie per munt); daarna wordt alles bewaard.")
        return
    meta = st.session_state.get(K + "dip_meta") or {}
    if meta.get("ts"):
        when = pd.Timestamp(meta["ts"], unit="s", tz="UTC").tz_convert("Europe/Brussels")
        age_h = (time.time() - meta["ts"]) / 3600
        src = {"github": "nachtelijke update", "app": "in de app"}.get(meta.get("source"), meta.get("source"))
        txt = f"📦 Berekend op **{when:%d/%m/%Y %H:%M}** ({src})."
        if age_h > 36:
            txt += " ⚠️ Ouder dan anderhalve dag: druk op *Opnieuw berekenen* voor de recentste koersen."
        st.caption(txt)
    if not have_current:
        st.warning("Instellingen gewijzigd: deze tabel hoort bij andere instellingen. Druk op **Dip-analyse uitvoeren**.")

    counts = t["verdict"].value_counts()
    st.markdown("**Oordeel:** " + "  ·  ".join(f"{lbl} **{counts[lbl]}**" for lbl in VERDICT_LABELS
                                                  if lbl in counts.index)
                + "  — gesorteerd van interessant naar niet interessant.")
    in_zone = t[t["to_zone_pct"] <= 0]
    if in_zone.empty:
        st.caption("Geen enkele munt staat nu in haar koopzone.")
    else:
        good = in_zone[in_zone["verdict"].str.startswith(("🟢", "🟡"))]
        rest = in_zone.drop(good.index)
        if not good.empty:
            st.success("🛒 Nu in de koopzone én met bruikbaar bewijs (🟢/🟡): "
                       + ", ".join(f"{s} ({v.split()[0]})" for s, v in zip(good["symbol"], good["verdict"])))
        if not rest.empty:
            st.info("In de koopzone, maar zwak of geen bewijs: "
                    + ", ".join(f"{s} ({v.split()[0]})" for s, v in zip(rest["symbol"], rest["verdict"])))
    with st.expander("🧭 Hoe wordt het oordeel bepaald?", expanded=False):
        st.markdown(VERDICT_RULES)
    with st.expander("ℹ️ Uitleg kolommen", expanded=False):
        st.markdown(DIP_EXPLAIN)
    with st.expander("📖 Concrete voorbeelden (testperiode, test trades, kopen&houden, eindwaarde, %/jaar…)",
                     expanded=False):
        st.markdown(DIP_EXAMPLES)

    t = t.copy()
    cols = ["symbol", "coinbase", "verdict", "now", "why", "source", "dip_pct", "target_pct", "current_dd_pct",
            "to_zone_pct"]
    if cfg["test_frac"] > 0:
        for c_ in TEST_COLS:
            if c_ not in t:
                t[c_] = None
        cols += TEST_COLS
    cols += ["history_days", "episodes", "ep_text", "episode_hit_pct", "hit_rate_pct", "median_days",
             "median_further_pct", "worst_further_pct", "still_open",
             "bt_start", "bt_years", "dip_round_trips", "avg_hold_days", "capital", "final_eur", "profit_eur",
             "dip_annual_pct", "buy_hold_eur", "invested_pct", "lowest_eur", "open_cost_eur", "open_value_eur",
             "open_result_eur", "open_result_pct"]
    cols = [c for c in cols if c in t.columns]
    view = t[cols].reset_index(drop=True)
    eur = lambda lbl, key_: st.column_config.NumberColumn(lbl, format="€ %.0f", help=C_HELP[key_])
    st.caption("👆 **Klik een rij aan** om de grafiek en details van die munt (historisch én nu) direct onder de tabel te zien.")
    event = st.dataframe(
        _style_verdict(view), hide_index=True, width="stretch",
        on_select="rerun", selection_mode="single-row", key=K + f"dip_df_{st.session_state.get(K + 'dip_ver', 0)}",
        column_config={
            "symbol": "Munt",
            "coinbase": st.column_config.TextColumn("Coinbase", help=C_HELP["coinbase"]),
            "verdict": st.column_config.TextColumn("Oordeel", help=C_HELP["verdict"]),
            "now": st.column_config.TextColumn("Koopzone nu?", help=C_HELP["now"]),
            "why": st.column_config.TextColumn("Waarom", width="large", help=C_HELP["why"]),
            "source": st.column_config.TextColumn("Bron", help=C_HELP["source"]),
            "dip_pct": _num("Koopdrempel %", "%.0f", "dip_pct"),
            "target_pct": _num("Winstdoel %", "%.0f", "target_pct"),
            "current_dd_pct": _num("Nu onder top %", "%.0f", "current_dd_pct"),
            "to_zone_pct": _num("Nog te zakken %", "%.0f", "to_zone_pct"),
            "wf_params": st.column_config.TextColumn("🧪 Training: drempel/doel", help=C_HELP["wf_params"]),
            "train_period": st.column_config.TextColumn("🧪 Training: periode", help=C_HELP["train_period"]),
            "train_annual_txt": st.column_config.TextColumn("🧪 Training %/jaar", help=C_HELP["train_annual_pct"]),
            "test_period": st.column_config.TextColumn("🧪 Test: periode", help=C_HELP["test_period"]),
            "test_status": st.column_config.TextColumn("🧪 Test: status", help=C_HELP["test_status"]),
            "test_trades": _num("🧪 Test trades", "%d", "test_trades"),
            "test_pct": _num("🧪 Test totaal %", "%.0f", "test_pct"),
            "test_annual_txt": st.column_config.TextColumn("🧪 Test %/jaar", help=C_HELP["test_annual_pct"]),
            "test_eur": eur("🧪 Test eindwaarde €", "test_eur"),
            "test_bh_pct": _num("🧪 Test kopen&houden %", "%.0f", "test_bh_pct"),
            "history_days": _num("Dagen data", "%d", "history_days"),
            "episodes": _num("Keren in zone", "%d", "episodes"),
            "ep_text": st.column_config.TextColumn("Hersteld (keren)", help=C_HELP["ep_text"]),
            "episode_hit_pct": st.column_config.ProgressColumn("Kans per keer %", min_value=0, max_value=100,
                                                               format="%.0f", help=C_HELP["episode_hit_pct"]),
            "hit_rate_pct": _num("Kans per dag %", "%.0f", "hit_rate_pct"),
            "median_days": _num("Mediaan dagen", "%.0f", "median_days"),
            "median_further_pct": _num("Typ. verdere daling %", "%.0f", "median_further_pct"),
            "worst_further_pct": _num("Ergste verdere daling %", "%.0f", "worst_further_pct"),
            "still_open": _num("Te recent", "%d", "still_open"),
            "bt_start": st.column_config.DateColumn("Start backtest", format="DD/MM/YYYY", help=C_HELP["bt_start"]),
            "bt_years": _num("Periode (jaar)", "%.1f", "bt_years"),
            "dip_round_trips": _num("Trades", "%d", "dip_round_trips"),
            "avg_hold_days": _num("Gem. dagen/trade", "%.0f", "avg_hold_days"),
            "capital": eur("Inzet €", "capital"),
            "final_eur": eur("Eindwaarde €", "final_eur"),
            "profit_eur": eur("Winst €", "profit_eur"),
            "dip_annual_pct": _num("%/jaar", "%.1f", "dip_annual_pct"),
            "buy_hold_eur": eur("Kopen&houden €", "buy_hold_eur"),
            "invested_pct": _num("Tijd belegd %", "%.0f", "invested_pct"),
            "lowest_eur": eur("Laagste waarde €", "lowest_eur"),
            "open_cost_eur": eur("Open: vast €", "open_cost_eur"),
            "open_value_eur": eur("Open: waarde €", "open_value_eur"),
            "open_result_eur": eur("Open: resultaat €", "open_result_eur"),
            "open_result_pct": _num("Open: resultaat %", "%.0f", "open_result_pct"),
        })
    st.caption("⚠️ Verleden ≠ toekomst; survivorship bias maakt kansen te optimistisch.")

    rows_sel = []
    try:
        rows_sel = list(event.selection.rows)
    except Exception:
        pass
    if rows_sel and rows_sel[0] < len(view):
        sym = view.iloc[rows_sel[0]]["symbol"]
        st.divider()
        st.subheader(f"📈 {sym}: historiek en nu")
        _detail_dip(sym, cfg, kp="sel_")


# --------------------------------------------------------------------------- detail
def _detail_tab(gcfg: dict, dcfg: dict) -> None:
    syms = set(cs.load_all())
    for key in ("table", "dip_table"):
        t = st.session_state.get(K + key)
        if t is not None:
            syms |= set(t["symbol"])
    syms = {s for s in syms if "-" in s}            # oude Binance-namen (BTCUSDT) niet meer tonen
    options = sorted(syms) or DEFAULT_COINS
    default = st.query_params.get("coin", options[0])
    c1, c2 = st.columns([2, 3])
    sym = c1.selectbox("Munt", options, index=options.index(default) if default in options else 0,
                       key=K + "detail_sym")
    c1.caption(f"Coinbase: {_cb_text(sym)}")
    mode = c2.radio("Weergave", ["Dip-kopen (lang)", "Grid (kort)"], horizontal=True, key=K + "detail_mode")
    st.query_params["coin"] = sym  # blijft behouden bij F5
    if mode.startswith("Dip"):
        _detail_dip(sym, dcfg, kp="det_")
    else:
        _detail_grid(sym, gcfg)


def _markers(fig, trades, row=None):
    for side, color, sm in (("buy", "green", "triangle-up"), ("sell", "red", "triangle-down")):
        s = trades[trades["side"] == side]
        if s.empty:
            continue
        txt = [f"schijf {x}" for x in s["schijf"]] if "schijf" in s else None
        tr = go.Scatter(x=s["time"], y=s["price"], mode="markers", text=txt,
                        name="koop" if side == "buy" else "verkoop",
                        marker=dict(color=color, symbol=sm, size=9))
        fig.add_trace(tr, row=row, col=1) if row else fig.add_trace(tr)


def _detail_grid(sym: str, cfg: dict) -> None:
    try:
        df = _klines(sym, cfg["interval"], cfg["days"])
    except Exception as e:
        st.error(f"Kon data niet ophalen: {e}")
        return
    if df.empty:
        st.warning("Geen data.")
        return
    m = compute_metrics(df, cfg["swing"])
    bt = grid_backtest(df, cfg["step"], cfg["levels"], cfg["fee"])
    c = st.columns(5)
    c[0].metric("Swings/week", f"{m['swings_per_week']:.1f}", help=C_HELP["swings_per_week"])
    c[1].metric("Grid trades", bt["grid_round_trips"], help=C_HELP["grid_round_trips"])
    c[2].metric("Grid netto", f"{bt['grid_net_pct']:.1f}%", help=C_HELP["grid_net_pct"])
    c[3].metric("Kopen & houden", f"{bt['buy_hold_pct']:.1f}%")
    c[4].metric("Open posities einde", f"{bt['grid_open_slots']}/{cfg['levels']}",
                help="Veel open = koers onder je grid gezakt, je zit vast.")
    fig = go.Figure(go.Candlestick(x=df["time"], open=df["open"], high=df["high"],
                                   low=df["low"], close=df["close"], name=sym))
    piv = zigzag_pivots(df["close"].to_numpy(), cfg["swing"])
    if piv:
        fig.add_trace(go.Scatter(x=[df["time"].iloc[i] for i, _, _ in piv], y=[p for _, p, _ in piv],
                                 mode="lines+markers", name=f"Swings ≥{cfg['swing']*100:.1f}%",
                                 line=dict(color="orange", width=1)))
    _markers(fig, bt["trades"])
    for lv in bt["buy_levels"]:
        fig.add_hline(y=lv, line=dict(color="gray", width=0.5, dash="dot"))
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width="stretch", key=K + "grid_fig")


def _heatmap(opt: dict, chosen: tuple[float, float] | None, key: str) -> None:
    g = opt["grid"]
    if g.empty:
        return
    piv = g.pivot(index="dip_pct", columns="target_pct", values="annual_pct")
    trd = g.pivot(index="dip_pct", columns="target_pct", values="trades")
    text = [[f"{v:.1f}%<br>{int(n)} tr" if pd.notna(v) else "" for v, n in zip(rv, rn)]
            for rv, rn in zip(piv.values, trd.values)]
    fig = go.Figure(go.Heatmap(z=piv.values, x=[f"+{c:.0f}%" for c in piv.columns],
                               y=[f"−{r:.0f}%" for r in piv.index], text=text, texttemplate="%{text}",
                               colorscale="RdYlGn", zmid=0, colorbar=dict(title="%/jaar")))
    if chosen:
        fig.add_trace(go.Scatter(x=[f"+{chosen[1]*100:.0f}%"], y=[f"−{chosen[0]*100:.0f}%"], mode="markers",
                                 marker=dict(symbol="square-open", size=38, color="black", line=dict(width=3)),
                                 name="gekozen", showlegend=False))
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title="Winstdoel", yaxis_title="Koopdrempel (daling t.o.v. top)")
    st.plotly_chart(fig, width="stretch", key=key)


def _detail_test(sym: str, cfg: dict, p: dict) -> None:
    st.subheader("🧪 Betrouwbaarheidstest (training / test)")
    wf = wf_for(sym, p, _wf_fn(cfg))
    if not wf["wf_ok"]:
        st.info(f"Niet getest: {wf['wf_reason']}.")
        return
    wf_label = "instelling uit de tabel" if wf["wf_fixed"] else "beste instelling in de training"
    capital = wf["wf_capital"] if wf["wf_fixed"] else cfg["amount"]
    st.markdown(
        f"**Training** {wf['train_start']:%d/%m/%Y} → {wf['test_start']:%d/%m/%Y} "
        f"({wf['train_years']:.1f} jaar): {wf_label} = koop bij **−{wf['wf_dip']*100:.0f}%**, "
        f"verkoop bij **+{wf['wf_target']*100:.0f}%** → {wf['train_pct']:.0f}% totaal, "
        f"**{fmt_annual(wf['train_annual_pct'], wf['train_short'] and wf['train_buys'] > 0)}** per jaar "
        f"({wf['train_trades']} trades).  \n"
        f"**Test** {wf['test_start']:%d/%m/%Y} → vandaag ({wf['test_years']:.1f} jaar), blind met diezelfde "
        f"instelling en vers kapitaal: status **{wf['test_status']}**, {wf['test_trades']} afgeronde trades "
        f"({wf['test_buys']}× gekocht).")
    c = st.columns(4)
    c[0].metric("Test totaal", f"{wf['test_pct']:.0f}%", help=C_HELP["test_pct"])
    short_shown = bool(wf["test_short"]) and wf["test_buys"] > 0
    c[1].metric("Test %/jaar", fmt_annual(wf["test_annual_pct"], short_shown), help=C_HELP["test_annual_pct"])
    c[2].metric("Test eindwaarde", f"€ {capital * (1 + wf['test_pct'] / 100):,.0f}",
                f"€ {capital * wf['test_pct'] / 100:,.0f}", help=C_HELP["test_eur"])
    c[3].metric("Test kopen & houden", f"{wf['test_bh_pct']:.0f}%", help=C_HELP["test_bh_pct"])
    if short_shown:
        st.caption(f"⚠️ De testperiode is maar {wf['test_years']:.2f} jaar: het %/jaar-cijfer is omgerekend en niet "
                   "betrouwbaar. Kijk naar **Test totaal**.")
    if wf["test_status"] == "Geen koopkans":
        st.caption("De munt kwam in de testperiode nooit tot de koopdrempel. 0% = geld bleef liggen. "
                   "Over de kwaliteit van de instelling zegt dit niets.")
    elif wf["test_pct"] <= 0 and wf["test_status"] == "Positie open":
        st.caption("🟠 Test negatief met een open positie: gekocht tijdens de val en nog niet hersteld "
                   f"(open sinds {wf['test_open_days']:.0f} dagen). Papieren verlies, geen bewijs dat het faalt.")
    elif wf["test_pct"] <= 0:
        st.caption("⚠️ In de test negatief: de instelling werkte hier niet. Wees voorzichtig.")
    elif wf["test_pct"] < wf["test_bh_pct"]:
        st.caption(f"🟡 Test positief, maar kopen&houden deed beter ({wf['test_bh_pct']:.0f}% vs "
                   f"{wf['test_pct']:.0f}%): de strategie voegde in deze periode niets toe.")
    else:
        st.caption("✅ Test positief én beter dan kopen&houden: de instelling houdt stand op data die ze niet gezien heeft.")


def _px(v: float) -> str:
    """Koers leesbaar: veel decimalen voor kleine munten, weinig voor grote."""
    if v is None or pd.isna(v):
        return "–"
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:.6f}".rstrip("0")


def _detail_dip(sym: str, cfg: dict, kp: str = "") -> None:
    """kp = unieke prefix voor widget-keys, zodat dezelfde munt op twee plaatsen getoond kan worden."""
    q = quote_of(sym)
    try:
        df = _klines(sym, "1d", cfg["days"])
    except Exception as e:
        st.error(f"Kon data niet ophalen: {e}")
        return
    if len(df) < cfg["lookback"] + 60:
        st.warning("Te weinig historiek voor deze referentieperiode.")
        return

    opt = _optimize(sym, cfg["days"], cfg["lookback"], cfg["fee"], cfg["min_trades"])
    saved = cs.get(sym)
    if saved and saved.get("lookback") != cfg["lookback"]:
        st.caption(f"ℹ️ Opgeslagen instellingen horen bij referentie {saved['lookback']} dagen en worden "
                   "nu niet gebruikt.")
        saved = None
    # Instelling zoals de tabelrij ze gebruikt (opgeslagen > optimaal > vast; standaard één schijf).
    p = _coin_params(sym, cfg)

    # ---- optimalisatie
    st.subheader("1. Historisch beste koopdrempel × winstdoel")
    if opt["found"]:
        st.markdown(f"Beste stabiele combinatie over de hele historiek: koop bij **−{opt['dip']*100:.0f}%** "
                    f"onder de top, verkoop bij **+{opt['target']*100:.0f}%** → **{opt['annual_pct']:.1f}%/jaar** "
                    f"({opt['trades']} trades; buurcombinaties gemiddeld {opt['robust_pct']:.1f}%/jaar).")
    else:
        st.warning(f"Geen betrouwbaar optimum: {opt['reason']}. Verlaag 'Min. trades' of kies vaste waarden.")
    with st.expander("Toon alle geteste combinaties (heatmap)", expanded=False):
        st.caption("Elk vakje = één backtest met één schijf: %/jaar en aantal afgeronde trades (tr). "
                   "Leeg = te weinig trades. Groen blok = stabiel goede zone; één los groen vakje = toeval.")
        _heatmap(opt, (opt["dip"], opt["target"]) if opt["found"] else None, key=K + kp + "heat")
    if cfg["test_frac"] > 0:
        _detail_test(sym, cfg, p)

    # ---- bedrag en schijven (standaard: zoals in de tabel = één schijf)
    st.subheader("2. Jouw bedrag en schijven")
    reset_k = K + f"{kp}reset_{sym}"
    rv = st.session_state.get(reset_k, 0)
    if saved:
        init_tr, init_tgt = saved["tranches"], saved["target"]
        src = f"opgeslagen op {saved['updated']}"
    else:
        init_tr, init_tgt = list(p["tranches"]), p["target"]
        src = f"zoals in de tabel ({p['source'].lower()})"
    st.caption(f"Bron: **{src}**: {setup_text(init_tr, init_tgt)}. Standaard zit je hele bedrag in één schijf; "
               "voeg rijen toe om het te verdelen.")

    c1, c2 = st.columns([3, 1])
    with c1:
        edited = st.data_editor(
            pd.DataFrame({"Koopdrempel %": [d * 100 for d, _ in init_tr], "Bedrag €": [a for _, a in init_tr]}),
            num_rows="dynamic", hide_index=True, width="stretch", key=K + f"{kp}ladder_{sym}_{rv}",
            column_config={
                "Koopdrempel %": st.column_config.NumberColumn(min_value=5, max_value=95, step=5, format="%.0f",
                                                               help=H["ladder"]),
                "Bedrag €": st.column_config.NumberColumn(min_value=0, step=50, format="€ %.0f",
                                                          help="Bedrag voor deze schijf."),
            })
    target = c2.number_input("Winstdoel %", 2.0, 300.0, float(init_tgt * 100), 5.0,
                             key=K + f"{kp}det_target_{sym}_{rv}", help=H["target"]) / 100
    tranches = [(float(r["Koopdrempel %"]) / 100, float(r["Bedrag €"])) for _, r in edited.dropna().iterrows()
                if r["Bedrag €"] > 0]
    b1, b2, b3 = c2.columns(3)
    if b1.button("💾", key=K + f"{kp}save_{sym}", help="Opslaan: bewaar deze schijven en dit winstdoel voor deze "
                 "munt. De dip-analyse gebruikt ze dan automatisch (ook in de nachtelijke update)."):
        if tranches:
            cs.save(sym, target, tranches, cfg["lookback"])
            st.rerun()
    if b2.button("↩️", key=K + f"{kp}undo_{sym}", help="Zoals in de tabel: wijzigingen hierboven ongedaan maken."):
        st.session_state[reset_k] = rv + 1
        st.rerun()
    if saved and b3.button("🗑️", key=K + f"{kp}del_{sym}", help="Wis opgeslagen instellingen; "
                           "terug naar optimaal/vast."):
        cs.delete(sym)
        st.rerun()
    if not tranches:
        st.info("Voeg minstens één schijf met een bedrag toe.")
        return

    # ---- de regel in cijfers
    ti = top_info(df, cfg["lookback"], [dd_ for dd_, _ in tranches], target)
    st.subheader("3. De regel in cijfers (nu)")
    c = st.columns(4)
    c[0].metric("Top (hoogste koers laatste %d dagen)" % cfg["lookback"], f"{_px(ti['top'])} {q}",
                f"{ti['top_date']:%d/%m/%Y} · {ti['top_age']} dagen geleden", delta_color="off",
                help="De top is een MEEBEWEGEND venster: het hoogste punt (intraday) van de laatste X dagen "
                     "(referentie, instelbaar). Hij hangt niet aan je laatste verkoop. Een oude piek valt na X dagen "
                     "weg en dan wordt de top lager.")
    c[1].metric("Koers nu", f"{_px(ti['price'])} {q}", f"{ti['dd_pct']:.0f}% t.o.v. top", delta_color="off",
                help="Laatste slotkoers (dagcandle) en hoeveel die onder de top staat.")
    c[2].metric("Top valt weg over", f"{ti['days_left']} dagen" if ti["days_left"] > 0 else "nu",
                help="Na dit aantal dagen valt de huidige top uit het venster. Zonder nieuw hoger punt wordt de top "
                     "dan de volgende hoogste koers (zie rechts) en schuift het koopniveau mee omlaag.")
    c[3].metric("Top daarna (indien niets hoger)", f"{_px(ti['next_top'])} {q}",
                f"{(ti['next_top'] / ti['top'] - 1) * 100:.0f}% t.o.v. huidige top", delta_color="off")
    lvl = pd.DataFrame([{
        "Schijf": i, "Koopdrempel": f"−{r['dip'] * 100:.0f}%", f"Koopniveau ({q})": _px(r["buy_level"]),
        "Nu": "🛒 In koopzone" if r["in_zone"] else f"👀 Nog {r['to_zone_pct']:.0f}% zakken",
        "Verkoopdoel bij aankoop op dat niveau": f"{_px(r['sell_target'])} (+{target * 100:.0f}%)",
        "Koopniveau als de top wegvalt": _px(r["level_after"]),
    } for i, r in enumerate(ti["levels"], 1)])
    st.dataframe(lvl, hide_index=True, width="stretch")
    with st.expander("🔍 Hoe werken top, koopniveau en opnieuw kopen precies?", expanded=False):
        st.markdown(
            f"- **Koopniveau = top × (1 − koopdrempel)**, nu {_px(ti['top'])} × (1 − {tranches[0][0] * 100:.0f}%) = "
            f"**{_px(ti['levels'][0]['buy_level'])} {q}**. De regel koopt op de dag dat de **slotkoers** op of onder "
            "dat niveau staat (aan die slotkoers, dus vaak iets lager).\n"
            f"- **Verkoop = werkelijke aankoopprijs × (1 + {target * 100:.0f}%)**, niet 'koopniveau + winstdoel'.\n"
            "- **De top hangt niet aan je laatste verkoop.** Na een verkoop is de koers meestal nog ver onder de top, "
            "dus er wordt pas opnieuw gekocht als de koers **opnieuw** tot het koopniveau zakt.\n"
            "- **Het koopniveau beweegt mee**: valt de oude top uit het venster, dan wordt hij lager (en het koopniveau "
            "ook); klimt de koers naar een nieuwe top, dan stijgt het koopniveau.\n"
            "- Schommelt de koers lang rond het koopniveau, dan koop en verkoop je dus **regelmatig** (elke ronde "
            "±winstdoel min kosten).\n"
            "- Zie *Uitleg → voorbeeld 10* voor een rekenvoorbeeld (top 100, koop bij 15, verkoop +20%).")

    # ---- resultaat
    bt = ladder_backtest(df, cfg["lookback"], tranches, target, cfg["fee"])
    first = min(d for d, _ in tranches)
    s = dip_stats(df, cfg["lookback"], first, target, cfg["maxwait"])
    st.subheader("4. Resultaat met jouw bedrag (hele historiek)")
    ref = ladder_backtest(df, cfg["lookback"], list(p["tranches"]), p["target"], cfg["fee"])
    if ref.get("valid") and bt.get("valid"):
        if abs(ref["final_eur"] - bt["final_eur"]) < 0.5:
            st.caption("✅ Deze cijfers zijn identiek aan de rij in de dip-tabel (zelfde instelling).")
        else:
            st.warning(
                f"⚠️ Je ziet hier **andere instellingen dan in de dip-tabel**, daarom een andere Eindwaarde.\n\n"
                f"- **Tabel:** {setup_text(p['tranches'], p['target'])} → Eindwaarde **€ {ref['final_eur']:,.0f}** "
                f"({ref['dip_round_trips']} trades)\n"
                f"- **Hier:** {setup_text(tranches, target)} → Eindwaarde **€ {bt['final_eur']:,.0f}** "
                f"({bt['dip_round_trips']} trades)\n\n"
                "Druk op ↩️ (*Zoals in de tabel*) om dezelfde cijfers te zien.")
    if not bt.get("valid"):
        st.warning("Te weinig data voor een backtest.")
        return
    st.caption(f"Backtest van **{bt['bt_start']:%d/%m/%Y}** tot vandaag (**{bt['bt_years']:.1f} jaar**). "
               f"{bt['dip_round_trips']} afgeronde trades"
               + ("" if pd.isna(bt["avg_hold_days"]) else f", gemiddeld **{bt['avg_hold_days']:.0f} dagen** per trade")
               + ("" if pd.isna(bt["open_days"]) else f"; open positie loopt al **{bt['open_days']:.0f} dagen**") + ".")
    c = st.columns(6)
    c[0].metric("Inzet", f"€ {bt['capital']:,.0f}", help=C_HELP["capital"])
    c[1].metric("Eindwaarde", f"€ {bt['final_eur']:,.0f}", f"€ {bt['profit_eur']:,.0f}", help=C_HELP["final_eur"])
    c[2].metric("%/jaar", "–" if pd.isna(bt["dip_annual_pct"]) else f"{bt['dip_annual_pct']:.1f}%",
                help=C_HELP["dip_annual_pct"])
    c[3].metric("Kopen & houden", f"€ {bt['buy_hold_eur']:,.0f}", help=C_HELP["buy_hold_eur"])
    c[4].metric("Laagste waarde", f"€ {bt['lowest_eur']:,.0f}", f"{bt['lowest_pct']:.0f}%",
                help=C_HELP["lowest_eur"])
    c[5].metric("Tijd belegd", f"{bt['invested_pct']:.0f}%", help=C_HELP["invested_pct"])
    open_val = 0.0 if pd.isna(bt["open_value_eur"]) else bt["open_value_eur"]
    st.caption(
        f"**Eindwaarde € {bt['final_eur']:,.0f}** = vrij geld € {bt['final_eur'] - open_val:,.0f} "
        f"(verkocht, of nog nooit gekocht) + open positie nu waard € {open_val:,.0f}. "
        f"Winst = eindwaarde − inzet. *Open: vast* is wat je voor die open positie betaalde en komt dus "
        f"**niet** extra bij de winst.")
    if not pd.isna(bt["dip_annual_pct"]):
        st.caption(f"Controle: € {bt['capital']:,.0f} × (1 + {bt['dip_annual_pct']:.1f}%) ^ {bt['bt_years']:.1f} jaar "
                   f"≈ € {bt['capital'] * (1 + bt['dip_annual_pct'] / 100) ** bt['bt_years']:,.0f}.")
    st.caption(f"Slechtste moment: de strategie zakte tot € {bt['lowest_eur']:,.0f}; "
               f"kopen&houden zakte tot € {bt['buy_hold_lowest_eur']:,.0f} (zelfde inzet, zelfde periode).")
    c = st.columns(6)
    c[0].metric("Nu onder top", f"{s['current_dd_pct']:.0f}%", help=C_HELP["current_dd_pct"])
    c[1].metric("Hersteld (keren)", f"{s['episodes_hit']} van {s['episodes_eval']}", help=C_HELP["ep_text"])
    c[2].metric("Mediaan dagen", "–" if pd.isna(s["median_days"]) else f"{s['median_days']:.0f}",
                help=C_HELP["median_days"])
    c[3].metric("Ergste verdere daling", "–" if pd.isna(s["worst_further_pct"]) else f"{s['worst_further_pct']:.0f}%",
                help=C_HELP["worst_further_pct"])
    c[4].metric("Trades", bt["dip_round_trips"], help=C_HELP["dip_round_trips"])
    c[5].metric("Open schijven", f"{bt['open_slots']}/{len(tranches)}",
                help="Aantal schijven dat nu gekocht en nog niet verkocht is.")
    st.caption(f"Keren in zone: **{s['episodes']}** afzonderlijke crashes (zonder 'zelfde crash'-filter zouden "
               f"het er {s['episodes_raw']} zijn). {C_HELP['episodes']}")
    if bt["open_slots"]:
        c = st.columns(6)
        c[0].metric("Open: vast", f"€ {bt['open_cost_eur']:,.0f}", help=C_HELP["open_cost_eur"])
        c[1].metric("Open: waarde nu", f"€ {bt['open_value_eur']:,.0f}", help=C_HELP["open_value_eur"])
        c[2].metric("Open: resultaat", f"€ {bt['open_result_eur']:,.0f}", f"{bt['open_result_pct']:.0f}%",
                    help=C_HELP["open_result_eur"])

    dd = drawdown_series(df, cfg["lookback"]) * 100
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.04,
                        subplot_titles=("Koers met aan- en verkopen, top en koopniveau", "Daling t.o.v. top",
                                        "Waarde van je inzet"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["close"], name=sym, line=dict(color="#1f77b4")), row=1, col=1)
    _markers(fig, bt["trades"], row=1)
    roll_top = df["high"].rolling(cfg["lookback"], min_periods=cfg["lookback"]).max()
    fig.add_trace(go.Scatter(x=df["time"], y=roll_top, name="top (meebewegend)",
                             line=dict(color="#7f7f7f", width=1, dash="dash")), row=1, col=1)
    for i, (d_, _a) in enumerate(tranches, 1):
        fig.add_trace(go.Scatter(x=df["time"], y=roll_top * (1 - d_), name=f"koopniveau schijf {i} (−{d_ * 100:.0f}%)",
                                 line=dict(width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["time"], y=dd, name="% onder top", fill="tozeroy",
                             line=dict(color="#d62728", width=1)), row=2, col=1)
    for i, (d, a) in enumerate(tranches, 1):
        fig.add_hline(y=-d * 100, line=dict(color="black", dash="dash", width=1), row=2, col=1,
                      annotation_text=f"schijf {i}: €{a:,.0f}", annotation_position="bottom left")
    eq = bt["equity"]
    fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name="strategie €", line=dict(color="green")), row=3, col=1)
    start_px = df["close"].iloc[cfg["lookback"] - 1]
    bh = bt["capital"] * df["close"].iloc[cfg["lookback"] - 1:] / start_px
    fig.add_trace(go.Scatter(x=df["time"].iloc[cfg["lookback"] - 1:], y=bh.values, name="kopen&houden €",
                             line=dict(color="gray", dash="dot")), row=3, col=1)
    fig.add_hline(y=bt["capital"], line=dict(color="black", width=0.5), row=3, col=1)
    if cfg["test_frac"] > 0:
        wf = wf_for(sym, p, _wf_fn(cfg))
        if wf["wf_ok"]:
            x0 = wf["test_start"].isoformat()
            for r in (1, 2, 3):
                fig.add_vline(x=x0, line=dict(color="purple", dash="dot", width=1), row=r, col=1)
            fig.add_annotation(x=x0, y=1, yref="paper", text="🧪 start test", showarrow=False,
                               xanchor="left", font=dict(color="purple"))
    fig.update_yaxes(type="log", row=1, col=1)
    fig.update_layout(height=850, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, width="stretch", key=K + kp + "fig")


def _uitleg() -> None:
    st.markdown(GENERAL)
    st.markdown("## 🧭 Oordeel")
    st.markdown(VERDICT_RULES)
    st.markdown("## 📖 Concrete voorbeelden")
    st.markdown(DIP_EXAMPLES)
    st.markdown("## ℹ️ Alle kolommen")
    st.markdown(DIP_EXPLAIN)


def render_crypto_page() -> None:
    st.header("🪙 Crypto – analyse")
    fee = _fee_settings()
    _source_caption()
    t1, t2, t3, t4 = st.tabs(["Dip-kopen (lang)", "Grid/swing (kort)", "Detail munt", "Uitleg"])
    with t2:
        gcfg = _grid_settings(fee)
        _grid_tab(gcfg)
    with t1:
        dcfg = _dip_settings(fee, gcfg["top_n"])
        _dip_tab(dcfg)
    with t3:
        _detail_tab(gcfg, dcfg)
    with t4:
        _uitleg()
