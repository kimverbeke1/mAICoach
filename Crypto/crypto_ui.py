"""Streamlit-pagina Crypto.
- In de hoofdapp (streamlit_app.py) via Crypto/crypto_page.py.
- Lokaal los te draaien via:  streamlit run crypto_app.py
Koersdata: Coinbase. Opslag: Firestore (cloud) of lokaal (crypto_store.py).

Dip-resultaten: COMPACTE, SORTEERBARE tabel; klik een rij voor alle cijfers en de grafiek. Filters: enkel in
koopzone, per oordeel. De brede tabel blijft beschikbaar.

Betrouwbaarheid: MEERDERE TESTVENSTERS als ÉÉN DOORLOPENDE simulatie (walk_forward_multi). Oordeel op
GEREALISEERDE winst met instelbare drempels (min. %/jaar, min. trades, max. diepte open positie, min. testduur,
min. training); drempels wijzigen = meteen nieuw oordeel.

Standaardinstellingen (ingebouwd of bewaard met '💾 Bewaar als standaard') -> de app toont de nachtelijke tabel.
Gewijzigde reken-instellingen -> de app rekent zelf, voor 'Aantal munten bij herberekening' (standaard 150)."""
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
from crypto_dip import (dip_stats, drawdown_series, is_stable, ladder_backtest, optimize_dip, top_info,
                        walk_forward_multi)
from crypto_metrics import add_score, compute_metrics, zigzag_pivots
from crypto_scan import (LIVE_TOP_N, SAVABLE_CALC, TEST_COLS, apply_verdicts, cfg_key, coin_params,
                         effective_defaults, is_default, scan_coin, setup_text, table_from_json, table_to_json,
                         wf_for)
from crypto_texts import C_HELP, DIP_EXAMPLES, DIP_EXPLAIN, GENERAL, H, VERDICT_RULES

K = "crypto_"  # prefix voor session_state-keys (geen botsing met mAICoach/PadelAnalysis)

FEE_PRESETS = {"Coinbase (intro)": (0.25, 0.50), "Eigen waarden": None}
VERDICT_LABELS = ["🟢 Interessant", "🟡 Twijfel", "⚪ Niets bewezen", "⚪ Niet getest",
                  "🟠 Onder water", "🔴 Niet interessant", "⚪ Te weinig data"]
VERDICT_COLORS = {"🟢": "#d4f4dd", "🟡": "#fff1b8", "⚪": "#e9ecef", "🟠": "#ffe0b8", "🔴": "#f8d7da"}
DEFAULT_COINS = ["BTC-USD", "ETH-USD", "SOL-USD"]
VIEW_OPTIONS = ["Compacte tabel (sorteerbaar)", "Brede tabel (alle kolommen)"]

# --------------------------------------------------------------------------- detail-tabellen per munt
SHORT = {
    "coinbase": "Markten waarin je de munt op Coinbase kan kopen.",
    "source": "Optimaal = historisch beste; Vast = jouw algemene waarden; Opgeslagen = door jou bewaard.",
    "dip_pct": "Koop als de slotkoers zoveel onder de top staat (instelling van vandaag).",
    "target_pct": "Verkoop zodra de koers zoveel boven je aankoopprijs staat.",
    "price_now": "Laatste slotkoers.",
    "buy_level": "De regel koopt vandaag als de slotkoers hieronder komt.",
    "sell_level": "Verkoopdoel bij aankoop op het koopniveau (altijd: aankoopprijs + winstdoel).",
    "current_dd_pct": "Hoeveel de koers nu onder de top staat.",
    "to_zone_pct": "Hoeveel de koers nog moet zakken tot de koopzone (0 = nu in de koopzone).",
    "wf_settings": "Instelling per testvenster voor nieuwe aankopen (telkens gezocht op de data ervóór).",
    "stable_txt": "Blijft de gevonden instelling dicht bij elkaar? Instabiel = getallen minder betrouwbaar.",
    "test_period": "Totale periode van de testvensters (eindigt vandaag).",
    "train_years_first": "Data waarop de instelling voor het eerste venster gezocht werd.",
    "win_text": "Actieve vensters met winst (incl. open positie).",
    "real_trades": "Afgeronde trades in de doorlopende test: het bewijs.",
    "real_total_pct": "Enkel echt verkochte winst (open positie aan aankoopprijs).",
    "real_annual_pct": "Gerealiseerd per jaar: dit gebruikt het oordeel.",
    "open_now_pct": "Positie die nu open staat t.o.v. aankoop (papier).",
    "total_annual_pct": "Per jaar inclusief open positie.",
    "bh_annual_pct": "Kopen en houden over dezelfde periode, per jaar.",
    "history_days": "Aantal dagen koersgeschiedenis.",
    "episodes": "Afzonderlijke keren in de koopzone (5+ zegt iets).",
    "ep_text": "Hoe vaak het winstdoel daarna gehaald werd binnen de max. wachttijd.",
    "episode_hit_pct": "Hetzelfde in %: de eerlijkste kans.",
    "median_days": "Typische wachttijd tot het winstdoel.",
    "median_further_pct": "Hoeveel de koers na aankoop meestal nog verder zakte.",
    "worst_further_pct": "De slechtste keer: je stresstest.",
    "bt_start": "Start van de backtest over de hele historiek.",
    "bt_years": "Duur van die backtest.",
    "dip_round_trips": "Afgeronde trades over de hele historiek.",
    "avg_hold_days": "Gemiddelde looptijd van een afgeronde trade.",
    "capital": "Ingezet bedrag (standaard één schijf).",
    "final_eur": "Hele historiek met de instelling van vandaag: achteraf afgesteld, te mooi.",
    "dip_annual_pct": "Hetzelfde per jaar.",
    "buy_hold_eur": "Alles kopen op de startdag en niets doen.",
    "invested_pct": "Hoe vaak er geld in de munt zat.",
    "lowest_eur": "Je slechtste moment tijdens de backtest.",
    "open_result_pct": "Open positie (hele historiek) t.o.v. aankoop.",
}

SECTIONS = [
    ("🎯 Jouw limieten vandaag", [
        ("Bron", "source", "txt"), ("Koopdrempel", "dip_pct", "neg"), ("Winstdoel", "target_pct", "pos"),
        ("Koers nu", "price_now", "px"), ("Koop onder", "buy_level", "px"), ("Verkoop bij", "sell_level", "px"),
        ("Nu onder top", "current_dd_pct", "pct"), ("Nog te zakken", "to_zone_pct", "pct"),
        ("Coinbase", "coinbase", "txt"),
    ]),
    ("🧪 Testvensters (doorlopend, blind getest)", [
        ("Instelling per venster", "wf_settings", "txt"), ("Stabiel?", "stable_txt", "txt"),
        ("Periode", "test_period", "txt"), ("Training eerste venster", "train_years_first", "years"),
        ("Positieve vensters", "win_text", "txt"),
        ("Gerealiseerde trades", "real_trades", "int"), ("Gerealiseerd totaal", "real_total_pct", "sign"),
        ("Gerealiseerd %/jaar", "real_annual_pct", "sign1"), ("Open nu", "open_now_pct", "sign"),
        ("Totaal %/jaar (incl. open)", "total_annual_pct", "sign1"),
        ("Kopen&houden %/jaar", "bh_annual_pct", "sign1"),
    ]),
    ("📊 Bewijs en herstel", [
        ("Dagen data", "history_days", "int"), ("Keren in zone", "episodes", "int"),
        ("Hersteld (keren)", "ep_text", "txt"), ("Kans per keer", "episode_hit_pct", "pct"),
        ("Mediaan dagen", "median_days", "int"), ("Typ. verdere daling", "median_further_pct", "pct"),
        ("Ergste verdere daling", "worst_further_pct", "pct"),
    ]),
    ("💶 Hele historiek (achteraf afgesteld)", [
        ("Start backtest", "bt_start", "date"), ("Periode", "bt_years", "years"),
        ("Trades", "dip_round_trips", "int"), ("Gem. dagen/trade", "avg_hold_days", "int"),
        ("Inzet", "capital", "eur"), ("Eindwaarde", "final_eur", "eur"), ("%/jaar", "dip_annual_pct", "pct1"),
        ("Kopen&houden", "buy_hold_eur", "eur"), ("Tijd belegd", "invested_pct", "pct"),
        ("Laagste waarde", "lowest_eur", "eur"), ("Open positie", "open_result_pct", "sign"),
    ]),
]


def _isna(v) -> bool:
    try:
        return v is None or bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _px(v) -> str:
    if _isna(v):
        return "–"
    v = float(v)
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:.6f}".rstrip("0")


def _years_txt(v) -> str:
    return f"{float(v):.1f} j".replace(".", ",")


def _fmt(v, kind: str) -> str:
    if _isna(v) or (isinstance(v, str) and not v.strip()):
        return "–"
    try:
        if kind == "txt":
            return str(v)
        if kind == "int":
            return f"{float(v):,.0f}".replace(",", ".")
        if kind == "pct":
            return f"{float(v):.0f}%"
        if kind == "pct1":
            return f"{float(v):.1f}%"
        if kind == "sign":
            return f"{float(v):+.0f}%"
        if kind == "sign1":
            return f"{float(v):+.1f}%"
        if kind == "neg":
            return f"−{float(v):.0f}%"
        if kind == "pos":
            return f"+{float(v):.0f}%"
        if kind == "px":
            return _px(v)
        if kind == "eur":
            return "€ " + f"{float(v):,.0f}".replace(",", ".")
        if kind == "years":
            return f"{float(v):.1f} jaar".replace(".", ",")
        if kind == "date":
            return pd.Timestamp(v).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(v)
    return str(v)


def _md_table(r: pd.Series, items, show_help: bool) -> str:
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    head = "| Kenmerk | Waarde |" + (" Uitleg |" if show_help else "")
    sep = "|---|---|" + ("---|" if show_help else "")
    lines = [head, sep]
    for label, col, kind in items:
        if col not in r.index:
            continue
        row = f"| {esc(label)} | **{esc(_fmt(r[col], kind))}** |"
        if show_help:
            row += f" {esc(SHORT.get(col, ''))} |"
        lines.append(row)
    return "\n".join(lines)


def _render_coin_sections(r: pd.Series, cfg: dict, show_help: bool) -> None:
    if isinstance(r.get("why"), str) and r["why"]:
        st.markdown(f"**{r.get('verdict', '')} – waarom:** {r['why']}")
    sections = [s for s in SECTIONS if not (s[0].startswith("🧪") and cfg.get("n_windows", 0) <= 0)]
    left, right = st.columns(2)
    for i, (title, items) in enumerate(sections):
        with (left if i % 2 == 0 else right):
            st.markdown(f"**{title}**")
            st.markdown(_md_table(r, items, show_help))


def _compact_view(t: pd.DataFrame) -> pd.DataFrame:
    def num(c):
        return pd.to_numeric(t[c], errors="coerce").values if c in t.columns else [float("nan")] * len(t)

    def txt(c):
        return [("" if _isna(x) else str(x)) for x in t[c]] if c in t.columns else [""] * len(t)

    return pd.DataFrame({
        "nr": range(1, len(t) + 1),
        "symbol": t["symbol"].values,
        "verdict": t["verdict"].values,
        "now": t["now"].values,
        "rule": [f"−{d:.0f}% / +{g:.0f}%" if not (_isna(d) or _isna(g)) else "–"
                 for d, g in zip(t["dip_pct"], t["target_pct"])],
        "buy_level": [_px(x) for x in t["buy_level"]] if "buy_level" in t else ["–"] * len(t),
        "to_zone_pct": num("to_zone_pct"),
        "real_annual_pct": num("real_annual_pct"),
        "real_trades": num("real_trades"),
        "test_years": num("test_years"),
        "win_text": txt("win_text"),
        "stable_txt": txt("stable_txt"),
        "open_now_pct": num("open_now_pct"),
        "total_annual_pct": num("total_annual_pct"),
        "bh_annual_pct": num("bh_annual_pct"),
        "history_days": num("history_days"),
    })


def _render_compact(t: pd.DataFrame, cfg: dict, vcfg: dict) -> None:
    view = _compact_view(t)
    st.caption("↕️ Klik op een kolomkop om te sorteren (kolom **#** = standaardvolgorde, beste oordeel bovenaan). "
               "👆 Klik een rij aan voor alle cijfers en de grafiek van die munt.")
    event = st.dataframe(
        _style_verdict(view), hide_index=True, width="stretch",
        on_select="rerun", selection_mode="single-row",
        key=K + f"cmp_df_{st.session_state.get(K + 'dip_ver', 0)}_{len(view)}",
        column_config={
            "nr": st.column_config.NumberColumn("#", format="%d", width="small",
                                                help="Standaardvolgorde: op oordeel, dan op gerealiseerd %/jaar."),
            "symbol": st.column_config.TextColumn("Munt"),
            "verdict": st.column_config.TextColumn("Oordeel", help=C_HELP["verdict"]),
            "now": st.column_config.TextColumn("Koopzone nu?", help=C_HELP["now"]),
            "rule": st.column_config.TextColumn("Koop / verkoop (vandaag)",
                                                help="Koopdrempel onder de top / winstdoel boven je aankoopprijs: "
                                                     "de instelling van vandaag, voor je echte orders."),
            "buy_level": st.column_config.TextColumn("Koop onder", help=C_HELP["buy_level"]),
            "to_zone_pct": _num("Nog te zakken %", "%.0f", "to_zone_pct"),
            "real_annual_pct": _num("🧪 Gerealiseerd %/jaar", "%.1f", "real_annual_pct"),
            "real_trades": _num("🧪 Trades", "%d", "real_trades"),
            "test_years": st.column_config.NumberColumn("🧪 Testduur (j)", format="%.1f",
                                                        help="Totale duur van de testvensters samen."),
            "win_text": st.column_config.TextColumn("🧪 Positief", help=C_HELP["win_text"]),
            "stable_txt": st.column_config.TextColumn("🧪 Stabiel?", help=C_HELP["stable_txt"]),
            "open_now_pct": _num("🧪 Open nu %", "%.0f", "open_now_pct"),
            "total_annual_pct": _num("🧪 Totaal %/jaar", "%.1f", "total_annual_pct"),
            "bh_annual_pct": _num("🧪 Kopen&houden %/jaar", "%.1f", "bh_annual_pct"),
            "history_days": _num("Dagen data", "%d", "history_days"),
        })
    rows_sel = []
    try:
        rows_sel = list(event.selection.rows)
    except Exception:
        pass
    if not rows_sel or rows_sel[0] >= len(t):
        return
    r = t.iloc[rows_sel[0]]
    sym = r["symbol"]
    with st.container(border=True):
        st.subheader(f"🔎 {sym}")
        show_help = st.toggle("Toon uitleg per kenmerk", value=True, key=K + "card_help")
        _render_coin_sections(r, cfg, show_help)
        graph_open = st.session_state.get(K + "card_sel") == sym
        if st.button("✖️ Details sluiten" if graph_open else "📈 Testvensters, grafiek en details",
                     key=K + f"cmp_btn_{sym}"):
            st.session_state[K + "card_sel"] = None if graph_open else sym
            st.rerun()
        if graph_open:
            st.divider()
            _detail_dip(sym, cfg, vcfg, kp="card_")


def _filter_table(t: pd.DataFrame) -> pd.DataFrame:
    present = [lbl for lbl in VERDICT_LABELS if lbl in set(t["verdict"])]
    c1, c2 = st.columns([1, 3])
    only_zone = c1.toggle("🛒 Enkel in koopzone", value=False, key=K + "f_zone",
                          help="Toon enkel munten die vandaag onder hun koopdrempel staan.")
    chosen = c2.multiselect("Oordeel", present, default=present, key=K + f"f_verdict_{'|'.join(present)}",
                            help="Toon enkel munten met deze oordelen (bv. enkel 🟢 en 🟡).")
    out = t[t["verdict"].isin(chosen)] if chosen else t.iloc[0:0]
    if only_zone:
        out = out[pd.to_numeric(out["to_zone_pct"], errors="coerce") <= 0]
    if len(out) < len(t):
        st.caption(f"{len(out)} van {len(t)} munten getoond.")
    return out.reset_index(drop=True)


def _num(label, fmt, key):
    return st.column_config.NumberColumn(label, format=fmt, help=C_HELP.get(key))


# --------------------------------------------------------------------------- data (gecached)
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _coinbase_cached() -> dict:
    return get_coinbase_products()


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
def _walk_multi(symbol: str, days: int, lookback: int, fee: float, min_trades: int, n_windows: int,
                amount: float, fixed_tr: tuple | None = None, fixed_target: float | None = None,
                _v: int = 3) -> dict:
    """fixed_tr = None: per venster de beste instelling zoeken. Anders: precies die instelling testen.
    _v = versie van de berekening (doorlopende simulatie), zodat oude cache niet hergebruikt wordt."""
    fixed = None if fixed_tr is None else {"tranches": list(fixed_tr), "target": fixed_target}
    return walk_forward_multi(_klines(symbol, "1d", days), lookback, fee, min_trades, n_windows, amount, fixed)


def _opt_fn(cfg: dict):
    return lambda s: _optimize(s, cfg["days"], cfg["lookback"], cfg["fee"], cfg["min_trades"])


def _wf_fn(cfg: dict):
    return lambda s, tr, tg: _walk_multi(s, cfg["days"], cfg["lookback"], cfg["fee"], cfg["min_trades"],
                                         int(cfg["n_windows"]), float(cfg["amount"]), tr, tg)


def _defaults() -> tuple[dict, dict, dict]:
    """(reken-standaard, oordeel-standaard, wat er bewaard is). Eén keer per sessie gelezen."""
    if K + "app_defaults" not in st.session_state:
        try:
            st.session_state[K + "app_defaults"] = store.load_app_defaults() or {}
        except Exception:  # noqa: BLE001
            st.session_state[K + "app_defaults"] = {}
    stored = st.session_state[K + "app_defaults"]
    calc, verd = effective_defaults(stored)
    return calc, verd, stored


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
def _opt_index(opts: list, value, fallback: int) -> int:
    try:
        return opts.index(value)
    except ValueError:
        return fallback


def _dip_settings(fee: float) -> tuple[dict, dict]:
    """(reken-cfg, oordeel-cfg). Startwaarden = jouw bewaarde standaard (of de ingebouwde)."""
    d, vd, stored = _defaults()
    with st.expander("⚙️ Instellingen dip-kopen", expanded=False):
        st.markdown("**Berekening**")
        c1, c2, c3 = st.columns(3)
        years_opts = [2, 3, 5, 8]
        years = c1.selectbox("Historiek (jaar)", years_opts,
                             index=_opt_index(years_opts, round(d["days"] / 365), 3),
                             key=K + "dip_years", help=H["dip_hist"])
        lb_opts = [90, 180, 365, 730]
        lookback = c2.selectbox("Referentie 'hoogste punt' (dagen)", lb_opts,
                                index=_opt_index(lb_opts, int(d["lookback"]), 2),
                                key=K + "dip_lookback", help=H["lookback"])
        amount = c3.number_input("Bedrag per munt (€)", 50.0, 1_000_000.0, float(d["amount"]), 500.0,
                                 key=K + "dip_amount", help=H["amount"])
        mode = st.radio("Koopdrempel en winstdoel", ["Optimaal per munt (automatisch)", "Vaste waarden"],
                        index=0 if d["optimal"] else 1, horizontal=True, key=K + "dip_mode", help=H["mode"])
        fixed = mode.startswith("Vaste")
        c4, c5, c6, c7 = st.columns(4)
        dip = c4.number_input("Koopdrempel: daling %", 10.0, 95.0, float(d["dip"] * 100), 5.0, key=K + "dip_dip",
                              help=H["dip"], disabled=not fixed) / 100
        target = c5.number_input("Winstdoel %", 2.0, 300.0, float(d["target"] * 100), 5.0, key=K + "dip_target",
                                 help=H["target"], disabled=not fixed) / 100
        mw_opts = [30, 90, 180, 365, 730]
        maxwait = c6.selectbox("Max. wachttijd voor 'kans' (dagen)", mw_opts,
                               index=_opt_index(mw_opts, int(d["maxwait"]), 3),
                               key=K + "dip_maxwait", help=H["maxwait"])
        min_trades = c7.number_input("Min. trades (optimalisatie)", 1, 20, int(d["min_trades"]), 1,
                                     key=K + "dip_mintrades", help=H["min_trades"])
        c8, c9 = st.columns(2)
        n_windows = c8.select_slider("🧪 Aantal testvensters (jaren)", options=[0, 1, 2, 3, 4, 5],
                                     value=int(d["n_windows"]), key=K + "dip_nwin", help=H["n_windows"])
        live_n = c9.slider("Aantal munten bij herberekening (gewijzigde instellingen)", 10, 150,
                           min(150, int(LIVE_TOP_N)), 5, key=K + "dip_live_n", help=H["live_n"])

        st.markdown("**Oordeel** *(wijzigen herberekent niets)*")
        c10, c11, c12 = st.columns(3)
        min_annual = c10.number_input("Min. gerealiseerd rendement %/jaar voor 🟢", 0.0, 200.0,
                                      float(vd["min_annual"]), 1.0, key=K + "v_min_annual", help=H["min_annual"])
        min_real = c11.number_input("Min. afgeronde trades voor 🟢", 1, 30, int(vd["min_real_trades"]), 1,
                                    key=K + "v_min_real", help=H["min_real_trades"])
        max_open = c12.number_input("Max. diepte open positie voor 🟢 (%)", 0.0, 100.0, float(vd["max_open_dd"]),
                                    5.0, key=K + "v_max_open", help=H["max_open_dd"])
        c13, c14 = st.columns(2)
        min_test = c13.number_input("Min. testduur voor 🟢 (jaar)", 0.0, 5.0, float(vd["min_test_years"]), 0.5,
                                    key=K + "v_min_test", help=H["min_test_years"])
        min_train = c14.number_input("Min. training eerste venster voor 🟢 (jaar)", 0.0, 7.0,
                                     float(vd["min_train_years"]), 0.5, key=K + "v_min_train",
                                     help=H["min_train_years"])

        cfg = dict(days=years * 365 + 5, lookback=lookback, amount=amount, optimal=not fixed, dip=dip,
                   target=target, maxwait=maxwait, min_trades=int(min_trades), fee=fee, top_n=int(d["top_n"]),
                   n_windows=int(n_windows), only_cb=True)
        vcfg = dict(min_annual=float(min_annual), min_real_trades=int(min_real), max_open_dd=float(max_open),
                    min_test_years=float(min_test), min_train_years=float(min_train))

        b1, b2 = st.columns([1, 3])
        if b1.button("💾 Bewaar als standaard", key=K + "save_defaults", help=H["save_defaults"]):
            data = {k: cfg[k] for k in SAVABLE_CALC if k != "top_n"}
            data["top_n"] = int(d["top_n"])
            data.update(vcfg)
            where = store.save_app_defaults(data)
            st.session_state[K + "app_defaults"] = data
            d, vd = effective_defaults(data)
            st.success(f"Bewaard ({'in de database' if where == 'cloud' else 'lokaal'}). De nachtelijke update "
                       "rekent voortaan hiermee; tot die gelopen heeft, druk je één keer op *Dip-analyse uitvoeren*.")
        src = "jouw bewaarde standaard" if stored else "de ingebouwde standaard"
        b2.caption(f"Startwaarden = {src}. Kosten worden niet mee bewaard (standaard Coinbase intro, limit).")

    std = is_default(cfg, {**d, "fee": 0.25 / 100})
    if not std:
        cfg["top_n"] = int(live_n)
    st.session_state[K + "dip_is_default"] = std
    return cfg, vcfg


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
        return df.style.map(_c, subset=[c for c in ("verdict", "why") if c in df.columns])
    except Exception:
        return df


def _set_table(t: pd.DataFrame, key: str, ts: float, source: str) -> None:
    st.session_state[K + "dip_table"] = t
    st.session_state[K + "dip_key"] = key
    st.session_state[K + "dip_meta"] = {"ts": ts, "source": source}
    st.session_state[K + "dip_ver"] = st.session_state.get(K + "dip_ver", 0) + 1


def _compute_table(cfg: dict, vcfg: dict) -> pd.DataFrame | None:
    try:
        tops = _top_symbols(cfg["top_n"])
    except Exception as e:
        st.error(f"Kon de Coinbase-munten niet ophalen: {e}")
        return None
    settings = cs.load_all()
    rows = []
    t0 = time.time()
    bar = st.progress(0.0, text="Dagdata bijwerken en rekenen…")
    for i, (sym, cbt) in enumerate(zip(tops["symbol"], tops["coinbase"])):
        bar.progress((i + 1) / len(tops), text=f"{sym} ({i + 1}/{len(tops)}) · {time.time() - t0:.0f} s")
        try:
            df = _klines(sym, "1d", cfg["days"])
            r = scan_coin(sym, cbt, cfg, settings, df, _opt_fn(cfg), _wf_fn(cfg))
            if r:
                rows.append(r)
        except Exception as e:
            st.warning(f"{sym}: {e}")
    bar.empty()
    st.session_state[K + "dip_calc_s"] = time.time() - t0
    return apply_verdicts(pd.DataFrame(rows), vcfg) if rows else None


# --------------------------------------------------------------------------- dip: tabel
def _dip_tab(cfg: dict, vcfg: dict) -> None:
    st.caption("Lange termijn: koop enkel na een diepe val, verkoop bij een winstdoel en wacht zo lang als nodig.")
    if st.session_state.get(K + "dip_is_default", True):
        st.caption(f"⚙️ Standaardinstellingen: de tabel met de top **{cfg['top_n']} munten** wordt elke nacht "
                   "berekend en staat meteen klaar.")
    else:
        st.caption(f"⚙️ Aangepaste instellingen: de app rekent zelf, voor de top **{cfg['top_n']} munten**. Bewaar "
                   "ze met *💾 Bewaar als standaard* om ze ook 's nachts te laten berekenen.")
    key = cfg_key(cfg, cs.load_all())

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
        t_new = _compute_table(cfg, vcfg)
        if t_new is not None:
            _set_table(t_new, key, time.time(), "app")
            try:
                store.save_result(key, table_to_json(t_new), "app")
            except Exception as e:  # noqa: BLE001
                st.warning(f"Resultaat niet bewaard: {e}")

    t = st.session_state.get(K + "dip_table")
    if t is None:
        st.info("Nog geen resultaat voor deze instellingen. Druk op **Dip-analyse uitvoeren**; het resultaat "
                "wordt daarna bewaard.")
        return
    if "train_years_first" not in t.columns:
        st.warning("Deze tabel komt van een oudere versie (zonder doorlopende testvensters). Druk op "
                   "**Opnieuw berekenen**.")
        return
    t = apply_verdicts(t, vcfg)
    meta = st.session_state.get(K + "dip_meta") or {}
    if meta.get("ts"):
        when = pd.Timestamp(meta["ts"], unit="s", tz="UTC").tz_convert("Europe/Brussels")
        age_h = (time.time() - meta["ts"]) / 3600
        src = {"github": "nachtelijke update", "app": "in de app"}.get(meta.get("source"), meta.get("source"))
        txt = f"📦 Berekend op **{when:%d/%m/%Y %H:%M}** ({src}), {len(t)} munten."
        calc_s = st.session_state.get(K + "dip_calc_s")
        if calc_s and meta.get("source") == "app":
            txt += f" Rekentijd {calc_s:.0f} s."
        if age_h > 36:
            txt += " ⚠️ Ouder dan anderhalve dag: druk op *Opnieuw berekenen* voor de recentste koersen."
        st.caption(txt)
    if not have_current:
        st.warning("Instellingen gewijzigd: deze tabel hoort bij andere instellingen. Druk op **Dip-analyse uitvoeren**.")

    counts = t["verdict"].value_counts()
    st.markdown("**Oordeel:** " + "  ·  ".join(f"{lbl} **{counts[lbl]}**" for lbl in VERDICT_LABELS
                                                  if lbl in counts.index)
                + f"  — 🟢 = testduur ≥ {vcfg['min_test_years']:g} j, training ≥ {vcfg['min_train_years']:g} j, "
                  f"≥ {vcfg['min_real_trades']} afgeronde trades, gerealiseerd ≥ {vcfg['min_annual']:.0f}%/jaar, "
                  f"open positie niet dieper dan −{vcfg['max_open_dd']:.0f}%.")
    in_zone = t[pd.to_numeric(t["to_zone_pct"], errors="coerce") <= 0]
    if in_zone.empty:
        st.caption("Geen enkele munt staat nu in haar koopzone.")
    else:
        good = in_zone[in_zone["verdict"].str.startswith("🟢")]
        rest = in_zone.drop(good.index)
        if not good.empty:
            st.success("🛒 Nu in de koopzone én 🟢: " + ", ".join(
                f"{s} (koop onder {_px(b)})" for s, b in zip(good["symbol"], good["buy_level"])))
        if not rest.empty:
            st.info("In de koopzone, maar (nog) niet 🟢: "
                    + ", ".join(f"{s} ({v.split()[0]})" for s, v in zip(rest["symbol"], rest["verdict"])))
    with st.expander("🧭 Hoe wordt het oordeel bepaald?", expanded=False):
        st.markdown(VERDICT_RULES)
    with st.expander("ℹ️ Uitleg kolommen", expanded=False):
        st.markdown(DIP_EXPLAIN)
    with st.expander("📖 Concrete voorbeelden (welke limieten, testvensters, gerealiseerd vs open…)", expanded=False):
        st.markdown(DIP_EXAMPLES)

    view_mode = st.radio("Weergave", VIEW_OPTIONS, horizontal=True, key=K + "dip_view",
                         help="Compact: kerncijfers, sorteerbaar; klik een rij voor alle cijfers en de grafiek. "
                              "Breed: alle kolommen naast elkaar.")
    t = _filter_table(t)
    if t.empty:
        st.info("Geen munten voor deze filters.")
        return
    if view_mode == VIEW_OPTIONS[0]:
        _render_compact(t, cfg, vcfg)
    else:
        _render_wide(t, cfg, vcfg)
    st.caption("⚠️ Verleden ≠ toekomst; survivorship bias maakt kansen te optimistisch.")


def _render_wide(t: pd.DataFrame, cfg: dict, vcfg: dict) -> None:
    t = t.copy()
    t["buy_level_txt"] = [_px(x) for x in t["buy_level"]]
    t["sell_level_txt"] = [_px(x) for x in t["sell_level"]]
    cols = ["symbol", "coinbase", "verdict", "now", "why", "source", "dip_pct", "target_pct", "buy_level_txt",
            "sell_level_txt", "current_dd_pct", "to_zone_pct"]
    if cfg.get("n_windows", 0) > 0:
        cols += TEST_COLS + ["train_years_first"]
    cols += ["history_days", "episodes", "ep_text", "episode_hit_pct", "median_days", "median_further_pct",
             "worst_further_pct", "bt_start", "bt_years", "dip_round_trips", "avg_hold_days", "capital",
             "final_eur", "dip_annual_pct", "buy_hold_eur", "invested_pct", "lowest_eur", "open_result_pct"]
    cols = [c for c in cols if c in t.columns]
    view = t[cols].reset_index(drop=True)
    eur = lambda lbl, key_: st.column_config.NumberColumn(lbl, format="€ %.0f", help=C_HELP[key_])
    st.caption("👆 **Klik een rij aan** om de testvensters, grafiek en details van die munt te zien.")
    event = st.dataframe(
        _style_verdict(view), hide_index=True, width="stretch",
        on_select="rerun", selection_mode="single-row",
        key=K + f"dip_df_{st.session_state.get(K + 'dip_ver', 0)}_{len(t)}",
        column_config={
            "symbol": "Munt",
            "coinbase": st.column_config.TextColumn("Coinbase", help=C_HELP["coinbase"]),
            "verdict": st.column_config.TextColumn("Oordeel", help=C_HELP["verdict"]),
            "now": st.column_config.TextColumn("Koopzone nu?", help=C_HELP["now"]),
            "why": st.column_config.TextColumn("Waarom", width="large", help=C_HELP["why"]),
            "source": st.column_config.TextColumn("Bron", help=C_HELP["source"]),
            "dip_pct": _num("Koopdrempel %", "%.0f", "dip_pct"),
            "target_pct": _num("Winstdoel %", "%.0f", "target_pct"),
            "buy_level_txt": st.column_config.TextColumn("Koop onder", help=C_HELP["buy_level"]),
            "sell_level_txt": st.column_config.TextColumn("Verkoop bij", help=C_HELP["sell_level"]),
            "current_dd_pct": _num("Nu onder top %", "%.0f", "current_dd_pct"),
            "to_zone_pct": _num("Nog te zakken %", "%.0f", "to_zone_pct"),
            "wf_settings": st.column_config.TextColumn("🧪 Instelling per venster", help=C_HELP["wf_settings"]),
            "stable_txt": st.column_config.TextColumn("🧪 Stabiel?", help=C_HELP["stable_txt"]),
            "test_period": st.column_config.TextColumn("🧪 Periode", help=C_HELP["test_period"]),
            "train_years_first": st.column_config.NumberColumn("🧪 Training eerste venster (j)", format="%.1f",
                                                               help=H["min_train_years"]),
            "win_text": st.column_config.TextColumn("🧪 Positief", help=C_HELP["win_text"]),
            "real_trades": _num("🧪 Trades", "%d", "real_trades"),
            "real_total_pct": _num("🧪 Gerealiseerd %", "%.0f", "real_total_pct"),
            "real_annual_pct": _num("🧪 Gerealiseerd %/jaar", "%.1f", "real_annual_pct"),
            "open_now_pct": _num("🧪 Open nu %", "%.0f", "open_now_pct"),
            "total_annual_pct": _num("🧪 Totaal %/jaar", "%.1f", "total_annual_pct"),
            "bh_annual_pct": _num("🧪 Kopen&houden %/jaar", "%.1f", "bh_annual_pct"),
            "history_days": _num("Dagen data", "%d", "history_days"),
            "episodes": _num("Keren in zone", "%d", "episodes"),
            "ep_text": st.column_config.TextColumn("Hersteld (keren)", help=C_HELP["ep_text"]),
            "episode_hit_pct": st.column_config.ProgressColumn("Kans per keer %", min_value=0, max_value=100,
                                                               format="%.0f", help=C_HELP["episode_hit_pct"]),
            "median_days": _num("Mediaan dagen", "%.0f", "median_days"),
            "median_further_pct": _num("Typ. verdere daling %", "%.0f", "median_further_pct"),
            "worst_further_pct": _num("Ergste verdere daling %", "%.0f", "worst_further_pct"),
            "bt_start": st.column_config.DateColumn("Hist.: start", format="DD/MM/YYYY", help=C_HELP["bt_start"]),
            "bt_years": _num("Hist.: jaar", "%.1f", "bt_years"),
            "dip_round_trips": _num("Hist.: trades", "%d", "dip_round_trips"),
            "avg_hold_days": _num("Hist.: dagen/trade", "%.0f", "avg_hold_days"),
            "capital": eur("Inzet €", "capital"),
            "final_eur": eur("Hist.: eindwaarde €", "final_eur"),
            "dip_annual_pct": _num("Hist.: %/jaar", "%.1f", "dip_annual_pct"),
            "buy_hold_eur": eur("Hist.: kopen&houden €", "buy_hold_eur"),
            "invested_pct": _num("Hist.: tijd belegd %", "%.0f", "invested_pct"),
            "lowest_eur": eur("Hist.: laagste €", "lowest_eur"),
            "open_result_pct": _num("Hist.: open positie %", "%.0f", "open_result_pct"),
        })
    rows_sel = []
    try:
        rows_sel = list(event.selection.rows)
    except Exception:
        pass
    if rows_sel and rows_sel[0] < len(view):
        sym = view.iloc[rows_sel[0]]["symbol"]
        st.divider()
        st.subheader(f"📈 {sym}: testvensters, historiek en nu")
        _detail_dip(sym, cfg, vcfg, kp="sel_")


# --------------------------------------------------------------------------- detail
def _detail_tab(gcfg: dict, dcfg: dict, vcfg: dict) -> None:
    syms = set(cs.load_all())
    for key in ("table", "dip_table"):
        t = st.session_state.get(K + key)
        if t is not None:
            syms |= set(t["symbol"])
    syms = {s for s in syms if "-" in s}
    options = sorted(syms) or DEFAULT_COINS
    default = st.query_params.get("coin", options[0])
    c1, c2 = st.columns([2, 3])
    sym = c1.selectbox("Munt", options, index=options.index(default) if default in options else 0,
                       key=K + "detail_sym")
    c1.caption(f"Coinbase: {_cb_text(sym)}")
    mode = c2.radio("Weergave", ["Dip-kopen (lang)", "Grid (kort)"], horizontal=True, key=K + "detail_mode")
    st.query_params["coin"] = sym
    if mode.startswith("Dip"):
        _detail_dip(sym, dcfg, vcfg, kp="det_")
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


def _detail_windows(sym: str, cfg: dict, vcfg: dict, p: dict) -> dict | None:
    st.subheader("2. 🧪 Testvensters (doorlopend, blind getest)")
    wf = wf_for(sym, p, _wf_fn(cfg))
    if not wf["wf_ok"]:
        st.info(f"Niet getest: {wf['wf_reason']}.")
        return None
    st.caption(f"Eén doorlopende simulatie met € {cfg['amount']:,.0f}: een positie die op het einde van een venster "
               "nog open staat, loopt door in het volgende en wordt verkocht volgens haar eigen winstdoel. "
               "De instelling van een venster geldt enkel voor nieuwe aankopen.")
    rows = []
    for w in wf["windows"]:
        dur = _years_txt(w["years"]) + (" ⚠️ ingekort" if w.get("truncated") else "")
        rows.append({
            "Venster": str(w["nr"]),
            "Gezocht op": ("jouw vaste instelling" if wf["wf_fixed"] else
                           f"{pd.Timestamp(w['train_start']):%m/%Y} → {pd.Timestamp(w['test_start']):%m/%Y}"),
            "Getest op": f"{pd.Timestamp(w['test_start']):%d/%m/%Y} → {pd.Timestamp(w['test_end']):%d/%m/%Y}",
            "Duur": dur,
            "Instelling nieuwe aankopen": ("– (geen gevonden)" if w["dip"] is None
                                           else f"−{w['dip'] * 100:.0f}% / +{w['target'] * 100:.0f}%"),
            "Doorgeschoven": "↪️ ja" if w["carried_in"] else "",
            "Aankopen": w["buys"], "Verkopen": w["trades"], "Status einde": w["status"],
            "Gerealiseerd %": None if _isna(w["realized_pct"]) else round(w["realized_pct"], 1),
            "Open %": None if _isna(w["open_pct"]) else round(w["open_pct"], 1),
            "Totaal %": None if _isna(w["total_pct"]) else round(w["total_pct"], 1),
            "Kopen&houden %": round(w["bh_pct"], 1),
        })
    today = f"−{min(d for d, _ in p['tranches']) * 100:.0f}% / +{p['target'] * 100:.0f}%"
    rows.append({"Venster": "Vandaag", "Gezocht op": "alle data tot nu", "Getest op": "–", "Duur": "",
                 "Instelling nieuwe aankopen": today, "Status einde": "→ jouw limieten"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    c = st.columns(6)
    yrs = wf["test_years"]
    c[0].metric("Gerealiseerd %/jaar", "–" if _isna(wf["real_annual_pct"]) else f"{wf['real_annual_pct']:+.1f}%",
                f"{wf['real_total_pct']:+.0f}% over {yrs:.1f} j", delta_color="off", help=C_HELP["real_annual_pct"])
    c[1].metric("Afgeronde trades", wf["real_trades"], help=C_HELP["real_trades"])
    c[2].metric("Positieve vensters", f"{wf['win_pos']} van {wf['win_active']}", help=C_HELP["win_text"])
    c[3].metric("Open nu", "–" if _isna(wf["open_now_pct"]) else f"{wf['open_now_pct']:+.0f}%",
                None if _isna(wf["open_now_days"]) else f"sinds {wf['open_now_days']:.0f} dagen",
                delta_color="off", help=C_HELP["open_now_pct"])
    c[4].metric("Testduur / training", f"{_years_txt(yrs)} / {_years_txt(wf['train_years_first'])}",
                help="Totale testduur en aantal jaar data waarop het eerste venster gezocht werd.")
    c[5].metric("Kopen&houden %/jaar", "–" if _isna(wf["bh_annual_pct"]) else f"{wf['bh_annual_pct']:+.1f}%",
                help=C_HELP["bh_annual_pct"])
    if yrs < vcfg["min_test_years"] or wf["train_years_first"] < vcfg["min_train_years"]:
        st.warning(f"⚠️ **Korte historiek**: test {_years_txt(yrs)} (minimum {vcfg['min_test_years']:g} j), training "
                   f"eerste venster {_years_txt(wf['train_years_first'])} (minimum {vcfg['min_train_years']:g} j). "
                   "Te weinig bewijs voor 🟢.")
    if wf["wf_fixed"]:
        st.caption("Vaste/opgeslagen instelling: in elk venster precies die instelling getest.")
    else:
        stable = is_stable(wf["settings"] + [(min(d for d, _ in p["tranches"]), p["target"])]
                           if p["source"] == "Optimaal" else wf["settings"])
        if stable is False:
            st.warning("⚠️ **Instabiel**: de gevonden instelling verschuift sterk tussen de vensters en vandaag. "
                       "De exacte limieten zijn minder betrouwbaar; overweeg minder in te zetten.")
        elif stable:
            st.caption("✅ Stabiel: de gevonden instelling blijft dicht bij elkaar.")
    return wf


def _detail_dip(sym: str, cfg: dict, vcfg: dict, kp: str = "") -> None:
    q = quote_of(sym)
    try:
        df = _klines(sym, "1d", cfg["days"])
    except Exception as e:
        st.error(f"Kon data niet ophalen: {e}")
        return
    if len(df) < cfg["lookback"] + 60:
        st.warning(f"Te weinig historiek voor deze referentieperiode: {len(df)} dagen data, minstens "
                   f"{cfg['lookback'] + 60} nodig. Kies bij ⚙️ Instellingen een kortere referentie.")
        return

    opt = _optimize(sym, cfg["days"], cfg["lookback"], cfg["fee"], cfg["min_trades"])
    saved = cs.get(sym)
    if saved and saved.get("lookback") != cfg["lookback"]:
        st.caption(f"ℹ️ Opgeslagen instellingen horen bij referentie {saved['lookback']} dagen en worden "
                   "nu niet gebruikt.")
        saved = None
    p = _coin_params(sym, cfg)

    st.subheader("1. Historisch beste koopdrempel × winstdoel (vandaag)")
    if opt["found"]:
        st.markdown(f"Beste stabiele combinatie over de hele historiek: koop bij **−{opt['dip']*100:.0f}%** "
                    f"onder de top, verkoop bij **+{opt['target']*100:.0f}%**. Dit zijn je limieten voor vandaag "
                    f"(tenzij je een eigen instelling opsloeg). Het %/jaar over die historiek "
                    f"({opt['annual_pct']:.1f}%) is achteraf afgesteld: kijk voor de betrouwbaarheid naar de "
                    "testvensters hieronder.")
    else:
        st.warning(f"Geen betrouwbaar optimum: {opt['reason']}. Verlaag 'Min. trades' of kies vaste waarden.")
    with st.expander("Toon alle geteste combinaties (heatmap)", expanded=False):
        st.caption("Elk vakje = één backtest met één schijf: %/jaar en aantal afgeronde trades (tr). "
                   "Leeg = te weinig trades. Groen blok = stabiel goede zone; één los groen vakje = toeval.")
        _heatmap(opt, (opt["dip"], opt["target"]) if opt["found"] else None, key=K + kp + "heat")
    wf = _detail_windows(sym, cfg, vcfg, p) if cfg.get("n_windows", 0) > 0 else None

    st.subheader("3. Jouw bedrag en schijven")
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
    if saved and b3.button("🗑️", key=K + f"{kp}del_{sym}", help="Wis opgeslagen instellingen."):
        cs.delete(sym)
        st.rerun()
    if not tranches:
        st.info("Voeg minstens één schijf met een bedrag toe.")
        return

    ti = top_info(df, cfg["lookback"], [dd_ for dd_, _ in tranches], target)
    st.subheader("4. Jouw limieten in koers (nu)")
    c = st.columns(4)
    c[0].metric("Top (hoogste koers laatste %d dagen)" % cfg["lookback"], f"{_px(ti['top'])} {q}",
                f"{ti['top_date']:%d/%m/%Y} · {ti['top_age']} dagen geleden", delta_color="off",
                help="MEEBEWEGEND venster: het hoogste punt van de laatste X dagen. Een oude piek valt na X dagen weg.")
    c[1].metric("Koers nu", f"{_px(ti['price'])} {q}", f"{ti['dd_pct']:.0f}% t.o.v. top", delta_color="off")
    c[2].metric("Top valt weg over", f"{ti['days_left']} dagen" if ti["days_left"] > 0 else "nu")
    c[3].metric("Top daarna (indien niets hoger)", f"{_px(ti['next_top'])} {q}",
                f"{(ti['next_top'] / ti['top'] - 1) * 100:.0f}% t.o.v. huidige top", delta_color="off")
    lvl = pd.DataFrame([{
        "Schijf": i, "Koopdrempel": f"−{r['dip'] * 100:.0f}%", f"Koop onder ({q})": _px(r["buy_level"]),
        "Nu": "🛒 In koopzone" if r["in_zone"] else f"👀 Nog {r['to_zone_pct']:.0f}% zakken",
        f"Verkoop bij ({q}) bij aankoop op dat niveau": f"{_px(r['sell_target'])} (+{target * 100:.0f}%)",
        "Koopniveau als de top wegvalt": _px(r["level_after"]),
    } for i, r in enumerate(ti["levels"], 1)])
    st.dataframe(lvl, hide_index=True, width="stretch")
    st.caption("Plaats je kooporder (limit) op of onder *Koop onder*. Na een aankoop: verkooporder op "
               "werkelijke aankoopprijs × (1 + winstdoel).")

    bt = ladder_backtest(df, cfg["lookback"], tranches, target, cfg["fee"])
    first = min(d for d, _ in tranches)
    s = dip_stats(df, cfg["lookback"], first, target, cfg["maxwait"])
    st.subheader("5. Resultaat over de hele historiek (achteraf afgesteld)")
    ref = ladder_backtest(df, cfg["lookback"], list(p["tranches"]), p["target"], cfg["fee"])
    if ref.get("valid") and bt.get("valid"):
        if abs(ref["final_eur"] - bt["final_eur"]) < 0.5:
            st.caption("✅ Deze cijfers zijn identiek aan de rij in de dip-tabel (zelfde instelling).")
        else:
            st.warning(
                f"⚠️ Je ziet hier **andere instellingen dan in de dip-tabel**, daarom een andere Eindwaarde.\n\n"
                f"- **Tabel:** {setup_text(p['tranches'], p['target'])} → Eindwaarde **€ {ref['final_eur']:,.0f}**\n"
                f"- **Hier:** {setup_text(tranches, target)} → Eindwaarde **€ {bt['final_eur']:,.0f}**\n\n"
                "Druk op ↩️ om dezelfde cijfers te zien.")
    if not bt.get("valid"):
        st.warning("Te weinig data voor een backtest.")
        return
    st.caption(f"Backtest van **{bt['bt_start']:%d/%m/%Y}** tot vandaag (**{bt['bt_years']:.1f} jaar**), "
               f"{bt['dip_round_trips']} afgeronde trades. De instelling is op dit verleden afgesteld: geen "
               "verwachting voor de toekomst.")
    c = st.columns(6)
    c[0].metric("Inzet", f"€ {bt['capital']:,.0f}")
    c[1].metric("Eindwaarde", f"€ {bt['final_eur']:,.0f}", f"€ {bt['profit_eur']:,.0f}", help=C_HELP["final_eur"])
    c[2].metric("Gerealiseerd", f"€ {bt['realized_eur']:,.0f}", f"{bt['realized_pct']:+.0f}%",
                help="Alsof een open positie aan haar aankoopprijs verkocht werd: enkel afgeronde trades.")
    c[3].metric("%/jaar", "–" if pd.isna(bt["dip_annual_pct"]) else f"{bt['dip_annual_pct']:.1f}%",
                help=C_HELP["dip_annual_pct"])
    c[4].metric("Kopen & houden", f"€ {bt['buy_hold_eur']:,.0f}", help=C_HELP["buy_hold_eur"])
    c[5].metric("Laagste waarde", f"€ {bt['lowest_eur']:,.0f}", f"{bt['lowest_pct']:.0f}%",
                help=C_HELP["lowest_eur"])
    c = st.columns(6)
    c[0].metric("Nu onder top", f"{s['current_dd_pct']:.0f}%", help=C_HELP["current_dd_pct"])
    c[1].metric("Hersteld (keren)", f"{s['episodes_hit']} van {s['episodes_eval']}", help=C_HELP["ep_text"])
    c[2].metric("Mediaan dagen", "–" if pd.isna(s["median_days"]) else f"{s['median_days']:.0f}",
                help=C_HELP["median_days"])
    c[3].metric("Ergste verdere daling", "–" if pd.isna(s["worst_further_pct"]) else f"{s['worst_further_pct']:.0f}%",
                help=C_HELP["worst_further_pct"])
    c[4].metric("Tijd belegd", f"{bt['invested_pct']:.0f}%", help=C_HELP["invested_pct"])
    c[5].metric("Open positie", "–" if pd.isna(bt["open_result_pct"]) else f"{bt['open_result_pct']:+.0f}%",
                help=C_HELP["open_result_pct"])

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
    if wf:
        for w in wf["windows"]:
            x0 = pd.Timestamp(w["test_start"]).isoformat()
            for r in (1, 2, 3):
                fig.add_vline(x=x0, line=dict(color="purple", dash="dot", width=1), row=r, col=1)
            fig.add_annotation(x=x0, y=1, yref="paper", text=f"🧪 venster {w['nr']}", showarrow=False,
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
        dcfg, vcfg = _dip_settings(fee)
        _dip_tab(dcfg, vcfg)
    with t3:
        _detail_tab(gcfg, dcfg, vcfg)
    with t4:
        _uitleg()
