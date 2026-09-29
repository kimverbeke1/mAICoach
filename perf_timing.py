"""
perf_timing.py - lichtgewicht timing/profiling voor de PadelAnalysis-app.

PADEL_ANALYSIS_PERF_TIMING_2026-09-28 (op verzoek van Kim: "is het een idee
om debug info toe te voegen zodat je kan zien waar de laadtijd vooral zit?")
--------------------------------------------------------------------------
Doel: stoppen met gokken op basis van code-lezen, en per pagina-render
METEN welke stap hoeveel tijd kost.

Gebruik (3 vormen, kies wat past):

    import perf_timing as perf

    # 1. context manager rond een blok
    with perf.step("get_team_report"):
        report = oa.get_team_report(...)

    # 2. decorator op een functie
    @perf.timed("render_poule_ranking")
    def _render_poule_ranking_section(...):
        ...

    # 3. handmatig, als begin en einde ver uit elkaar liggen
    t = perf.start("scout-keten")
    ...
    perf.stop(t)

En onderaan de pagina (of in de sidebar):

    perf.render_panel()

BELANGRIJK - hoe je de cijfers leest:
  - De metingen worden PER RENDER bijgehouden en bij het begin van elke
    nieuwe render gewist (zie reset()). Je ziet dus altijd de laatste
    render, niet een opeenstapeling.
  - Geneste stappen worden als boom getoond met inspringing. De duur van
    een ouder bevat die van zijn kinderen - tel niet op, lees de boom.
  - "eigen tijd" (self) = duur van de stap MINUS de som van zijn directe
    kinderen. Dat is de kolom waar je naar moet kijken om de echte
    boosdoener te vinden: een ouder van 8s met 7,9s in één kind is niet
    zelf traag.
  - De EERSTE render na het starten van de app is altijd trager (imports,
    koude caches, koude Firestore-verbinding). Meet dus minstens 2 keer.

Overhead van deze module is verwaarloosbaar (time.perf_counter() + een
dict-append per stap), maar zet PERF_ENABLED op False om alles volledig
uit te schakelen zonder de aanroepen te moeten verwijderen.
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


def _records() -> list:
    if _RECORDS_KEY not in st.session_state:
        st.session_state[_RECORDS_KEY] = []
    return st.session_state[_RECORDS_KEY]


def _stack() -> list:
    if _STACK_KEY not in st.session_state:
        st.session_state[_STACK_KEY] = []
    return st.session_state[_STACK_KEY]


def reset() -> None:
    """Wist de metingen van de vorige render. Roep dit AAN HET BEGIN van
    je pagina-functie aan, vóór de eerste step()."""
    if not PERF_ENABLED:
        return
    st.session_state[_RECORDS_KEY] = []
    st.session_state[_STACK_KEY] = []
    st.session_state[_RENDER_START_KEY] = time.perf_counter()


def start(label: str):
    """Start een meting en geef een handle terug voor stop()."""
    if not PERF_ENABLED:
        return None
    stack = _stack()
    handle = {
        "label": label,
        "depth": len(stack),
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
    functienaam)."""
    def decorator(fn):
        naam = label or fn.__name__

        @wraps(fn)
        def wrapper(*args, **kwargs):
            with step(naam):
                return fn(*args, **kwargs)
        return wrapper
    return decorator


def _self_seconds(records: list) -> list:
    """Berekent per stap de 'eigen tijd': de duur minus de som van de
    DIRECTE kinderen. Records staan in afsluitvolgorde (kind vóór ouder),
    en elk record kent zijn diepte - genoeg om de boom te reconstrueren
    zonder expliciete parent-verwijzingen."""
    out = []
    for idx, rec in enumerate(records):
        kind_totaal = 0.0
        # Directe kinderen van dit record zijn de records ERVOOR met
        # depth == rec.depth + 1, tot we een record met depth <= rec.depth
        # tegenkomen (dat hoort bij een andere ouder).
        for eerder in range(idx - 1, -1, -1):
            ander = records[eerder]
            if ander["depth"] <= rec["depth"]:
                break
            if ander["depth"] == rec["depth"] + 1:
                kind_totaal += ander["seconds"]
        out.append({**rec, "self_seconds": max(0.0, rec["seconds"] - kind_totaal)})
    return out


def render_panel(expanded: bool = False, title: str = "Laadtijd-analyse (debug)") -> None:
    """Toont de metingen van de HUIDIGE render. Roep dit ONDERAAN je
    pagina-functie aan, nadat alles getekend is."""
    if not PERF_ENABLED:
        return

    records = _records()
    if not records:
        return

    totaal_render = 0.0
    if _RENDER_START_KEY in st.session_state:
        totaal_render = time.perf_counter() - st.session_state[_RENDER_START_KEY]

    verrijkt = _self_seconds(records)

    # Records staan in AFSLUITvolgorde; voor de boomweergave willen we
    # startvolgorde. Omkeren volstaat niet bij zussen, dus we sorteren
    # niet - we tonen de boom in afsluitvolgorde omgekeerd, wat voor deze
    # (grotendeels sequentiële) pagina overeenkomt met de leesvolgorde.
    boom = list(reversed(verrijkt))

    zwaarste = max(verrijkt, key=lambda r: r["self_seconds"])

    with st.expander(title, expanded=expanded):
        st.caption(
            f"Totaal deze render: **{totaal_render:.2f}s** · gemeten stappen: {len(records)}. "
            "Kijk naar de kolom 'eigen' - dat is de tijd die de stap ZELF kost, "
            "los van zijn substappen. De eerste render na het starten van de app is "
            "altijd trager (koude caches)."
        )
        st.markdown(
            f"**Zwaarste eigen tijd:** `{zwaarste['label']}` - "
            f"{zwaarste['self_seconds']:.2f}s"
        )

        try:
            import pandas as pd
            df = pd.DataFrame([
                {
                    "Stap": ("· " * r["depth"]) + r["label"],
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
        except Exception:  # noqa: BLE001 - pandas mag nooit de app breken
            for r in boom:
                st.write(
                    ("· " * r["depth"])
                    + f"{r['label']}: {r['seconds']:.3f}s (eigen {r['self_seconds']:.3f}s)"
                )

        st.caption(
            "Top 5 op eigen tijd: "
            + ", ".join(
                f"{r['label']} ({r['self_seconds']:.2f}s)"
                for r in sorted(verrijkt, key=lambda x: -x["self_seconds"])[:5]
            )
        )
