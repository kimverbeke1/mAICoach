"""
perf_timing.py - lichtgewicht timing/profiling voor de VOLLEDIGE app
(mAICoach + PadelAnalysis).

LOCATIE: repo-root (mAICoach/perf_timing.py), NIET meer in PadelAnalysis/.
Zo kunnen beide delen dezelfde helper importeren: streamlit_app.py en
AICoach zetten de repo-root al op sys.path, PadelAnalysis/dashboard.py en
dashboard_common.py doen dat sinds PADEL_ANALYSIS_PERF_TIMING_ROLLOUT ook.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PERF_TIMING_2026-09-28 (op verzoek van Kim: "is het een idee
om debug info toe te voegen zodat je kan zien waar de laadtijd vooral zit?")
--------------------------------------------------------------------------
Doel: stoppen met gokken op basis van code-lezen, en per render METEN welke
stap hoeveel tijd kost. Eerste resultaat: 10.16s van 10.93s bleek in
identify_own_ploeg_id() te zitten - iets wat 3 rondes code-lezen gemist had.

--------------------------------------------------------------------------
PERF_TIMING_ROLLOUT_2026-09-29 (op verzoek van Kim: timing uitrollen over
de hele app, met EEN centrale ingang)
--------------------------------------------------------------------------
Nieuw:
  1. begin_run() / end_run() - bedoeld voor streamlit_app.py, de ENIGE
     echte ingang (st.navigation). begin_run() wist de metingen en start de
     klok; end_run() tekent het paneel onderaan elke pagina. Zo werkt de
     timing voor ELKE pagina, zonder dat elke pagina zelf reset() en
     render_panel() moet aanroepen.
  2. "Eigenaar"-logica: zodra begin_run() in deze sessie gedraaid heeft, zijn
     reset() en render_panel() op pagina-niveau NO-OPS. Die aanroepen
     (bv. in page_lineup_lab.py en training_dashboard.py) mogen dus blijven
     staan: ze doen enkel nog iets wanneer een pagina STANDALONE draait
     (bv. `streamlit run PadelAnalysis/dashboard.py`). Zonder deze regel zou
     page_lineup_lab.py halverwege de run alle metingen van de navigatie
     wissen, en zou het paneel twee keer verschijnen.
  3. Het paneel toont stappen nu in STARTvolgorde (echte boomvolgorde).
     Voorheen: omgekeerde afsluitvolgorde, waardoor zussen in omgekeerde
     volgorde stonden (zichtbaar in Kim's eerste meting).
  4. Extra tabel "Opgeteld per stapnaam" zodra een stap meerdere keren
     voorkomt in een render - bv. een Firestore-helper die 6x per render
     wordt aangeroepen valt per aanroep niet op, maar opgeteld wel.

Gebruik:

    import perf_timing as perf

    with perf.step("get_team_report"):          # 1. blok
        report = oa.get_team_report(...)

    @perf.timed("render_poule_ranking")         # 2. decorator
    def _render_poule_ranking_section(...):
        ...

    t = perf.start("scout-keten"); ...; perf.stop(t)   # 3. handmatig

LET OP: zet @perf.timed NOOIT rechtstreeks op een @st.cache_data-functie
waarvan elders .clear() wordt aangeroepen - de wrapper verbergt dan die
.clear(). Time in dat geval de (niet-gecachete) aanroeper.

Hoe je de cijfers leest:
  - Metingen gelden PER RENDER en worden bij elke nieuwe volledige run
    gewist. Fragment-reruns (@st.fragment) draaien streamlit_app.py NIET
    opnieuw: die metingen komen er dus niet bij tot de volgende volledige
    run. Meet een eerste pagina-load daarom met F5.
  - "Eigen (s)" = duur van de stap MIN de som van zijn directe substappen.
    Daar zoek je de echte boosdoener.
  - De eerste render na het (her)starten van de app is altijd trager
    (imports, koude caches, koude Firestore/GCS-verbinding). Meet 2x.

Zet PERF_ENABLED op False om alles volledig uit te schakelen zonder de
aanroepen te moeten verwijderen.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from functools import wraps

import streamlit as st

# Zet op False om alle timing-code inert te maken (geen meting, geen paneel).
PERF_ENABLED = True

_RECORDS_KEY = "_perf_records_v1"
_STACK_KEY = "_perf_stack_v1"
_RENDER_START_KEY = "_perf_render_start_v1"
_SEQ_KEY = "_perf_seq_v1"
_OWNER_KEY = "_perf_central_owner_v1"


def _records() -> list:
    if _RECORDS_KEY not in st.session_state:
        st.session_state[_RECORDS_KEY] = []
    return st.session_state[_RECORDS_KEY]


def _stack() -> list:
    if _STACK_KEY not in st.session_state:
        st.session_state[_STACK_KEY] = []
    return st.session_state[_STACK_KEY]


def _next_seq() -> int:
    seq = st.session_state.get(_SEQ_KEY, 0) + 1
    st.session_state[_SEQ_KEY] = seq
    return seq


def _is_centrally_owned() -> bool:
    return bool(st.session_state.get(_OWNER_KEY))


def _do_reset() -> None:
    st.session_state[_RECORDS_KEY] = []
    st.session_state[_STACK_KEY] = []
    st.session_state[_SEQ_KEY] = 0
    st.session_state[_RENDER_START_KEY] = time.perf_counter()


# ─────────────────────────────────────────────
# Centrale ingang (streamlit_app.py)
# ─────────────────────────────────────────────
def begin_run() -> None:
    """Roep dit aan in streamlit_app.py, bij het begin van ELKE run (vóór
    navigation.run()). Wist de metingen van de vorige run, start de klok,
    en markeert deze sessie als 'centraal beheerd' - waardoor reset() en
    render_panel() op pagina-niveau vanaf nu no-ops zijn."""
    if not PERF_ENABLED:
        return
    st.session_state[_OWNER_KEY] = True
    _do_reset()


def end_run(expanded: bool = False, title: str = "Laadtijd-analyse (debug)") -> None:
    """Roep dit aan in streamlit_app.py, NA navigation.run(). Tekent het
    paneel onderaan de pagina, ongeacht welke pagina er draaide."""
    if not PERF_ENABLED:
        return
    _render_panel_impl(expanded=expanded, title=title)


# ─────────────────────────────────────────────
# Pagina-niveau (blijft werken bij standalone gebruik)
# ─────────────────────────────────────────────
def reset() -> None:
    """Wist de metingen van de vorige render. Roep dit AAN HET BEGIN van
    een pagina-functie aan. NO-OP zodra streamlit_app.py via begin_run()
    de timing centraal beheert - anders zou dit de al lopende metingen van
    de navigatie wissen."""
    if not PERF_ENABLED or _is_centrally_owned():
        return
    _do_reset()


def render_panel(expanded: bool = False, title: str = "Laadtijd-analyse (debug)") -> None:
    """Toont de metingen van de HUIDIGE render. Roep dit ONDERAAN een
    pagina-functie aan. NO-OP zodra streamlit_app.py via end_run() het
    paneel centraal tekent - anders zou het twee keer verschijnen."""
    if not PERF_ENABLED or _is_centrally_owned():
        return
    _render_panel_impl(expanded=expanded, title=title)


# ─────────────────────────────────────────────
# Meten
# ─────────────────────────────────────────────
def start(label: str):
    """Start een meting en geef een handle terug voor stop()."""
    if not PERF_ENABLED:
        return None
    stack = _stack()
    handle = {
        "label": label,
        "depth": len(stack),
        "seq": _next_seq(),
        "t0": time.perf_counter(),
    }
    stack.append(handle)
    return handle


def stop(handle) -> float:
    """Sluit een meting af die met start() begon. Geeft de duur in
    seconden terug (0.0 wanneer timing uitstaat)."""
    if not PERF_ENABLED or handle is None:
        return 0.0
    duration = time.perf_counter() - handle["t0"]
    stack = _stack()
    if stack and stack[-1] is handle:
        stack.pop()
    else:
        # Defensief: bij een ontbrekende stop() elders raakt de stack uit
        # sync. We herstellen zonder te crashen - timing mag NOOIT de app
        # breken.
        try:
            stack.remove(handle)
        except ValueError:
            pass
    _records().append({
        "label": handle["label"],
        "depth": handle["depth"],
        "seq": handle.get("seq", 0),
        "seconds": duration,
    })
    return duration


@contextmanager
def step(label: str):
    """Context manager: `with perf.step("naam"): ...`"""
    handle = start(label)
    try:
        yield
    finally:
        stop(handle)


def timed(label: str = None):
    """Decorator: `@perf.timed("naam")` (of zonder naam, dan de
    functienaam). Zie de LET OP in de moduledocstring over
    @st.cache_data-functies."""
    def decorator(fn):
        naam = label or fn.__name__

        @wraps(fn)
        def wrapper(*args, **kwargs):
            with step(naam):
                return fn(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# Weergave
# ─────────────────────────────────────────────
def _self_seconds(records: list) -> list:
    """Berekent per stap de 'eigen tijd': de duur minus de som van de
    DIRECTE kinderen. Werkt op de AFSLUITvolgorde (kind vóór ouder) - de
    volgorde waarin records binnenkomen."""
    out = []
    for idx, rec in enumerate(records):
        kind_totaal = 0.0
        for eerder in range(idx - 1, -1, -1):
            ander = records[eerder]
            if ander["depth"] <= rec["depth"]:
                break
            if ander["depth"] == rec["depth"] + 1:
                kind_totaal += ander["seconds"]
        out.append({**rec, "self_seconds": max(0.0, rec["seconds"] - kind_totaal)})
    return out


def _aggregate_by_label(verrijkt: list) -> list:
    """Telt aanroepen en tijd op per stapnaam. Enkel stapnamen die MEER dan
    1x voorkomen worden teruggegeven - de rest staat al in de hoofdtabel."""
    per_label: dict = {}
    for rec in verrijkt:
        agg = per_label.setdefault(rec["label"], {"n": 0, "tot": 0.0, "eigen": 0.0})
        agg["n"] += 1
        agg["tot"] += rec["seconds"]
        agg["eigen"] += rec["self_seconds"]
    rows = [
        {"Stap": label, "Aantal": a["n"], "Totaal (s)": round(a["tot"], 3),
         "Eigen (s)": round(a["eigen"], 3)}
        for label, a in per_label.items() if a["n"] > 1
    ]
    rows.sort(key=lambda r: -r["Eigen (s)"])
    return rows


def _render_panel_impl(expanded: bool, title: str) -> None:
    records = _records()
    if not records:
        return

    totaal_render = 0.0
    if _RENDER_START_KEY in st.session_state:
        totaal_render = time.perf_counter() - st.session_state[_RENDER_START_KEY]

    verrijkt = _self_seconds(records)
    # PERF_TIMING_ROLLOUT_2026-09-29: echte boomvolgorde = startvolgorde.
    boom = sorted(verrijkt, key=lambda r: r.get("seq", 0))
    zwaarste = max(verrijkt, key=lambda r: r["self_seconds"])
    herhaald = _aggregate_by_label(verrijkt)

    st.divider()
    with st.expander(title, expanded=expanded):
        st.caption(
            f"Totaal deze render: **{totaal_render:.2f}s** · gemeten stappen: {len(records)}. "
            "Kijk naar de kolom 'Eigen' - dat is de tijd die de stap ZELF kost, "
            "los van zijn substappen. De eerste render na het starten van de app is "
            "altijd trager (koude caches). Meet met F5, niet via een klik binnen een fragment."
        )
        st.markdown(
            f"**Zwaarste eigen tijd:** `{zwaarste['label'].strip()}` - "
            f"{zwaarste['self_seconds']:.2f}s"
        )

        try:
            import pandas as pd
            df = pd.DataFrame([
                {
                    "Stap": ("· " * r["depth"]) + r["label"].strip(),
                    "Totaal (s)": round(r["seconds"], 3),
                    "Eigen (s)": round(r["self_seconds"], 3),
                    "% van render": (
                        round(100 * r["self_seconds"] / totaal_render, 1)
                        if totaal_render > 0 else None
                    ),
                }
                for r in boom
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
            if herhaald:
                st.markdown("**Opgeteld per stapnaam** (stappen die meerdere keren voorkomen)")
                st.dataframe(pd.DataFrame(herhaald), use_container_width=True, hide_index=True)
        except Exception:  # noqa: BLE001 - pandas mag nooit de app breken
            for r in boom:
                st.write(
                    ("· " * r["depth"])
                    + f"{r['label'].strip()}: {r['seconds']:.3f}s (eigen {r['self_seconds']:.3f}s)"
                )

        st.caption(
            "Top 5 op eigen tijd: "
            + ", ".join(
                f"{r['label'].strip()} ({r['self_seconds']:.2f}s)"
                for r in sorted(verrijkt, key=lambda x: -x["self_seconds"])[:5]
            )
        )
