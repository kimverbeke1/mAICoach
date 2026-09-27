# -*- coding: utf-8 -*-
"""Dagelijkse update voor mAICoach.
Bekijkt de recentste wellness- en trainingsdata en signaleert wat er de voorbije
periode opvalt: rusthartslag, HRV, slaap, readiness en de trend in Form, Fitness
en Fatigue. Voorzichtig geformuleerd en gericht op wat je er praktisch mee kunt.
Belangrijk: Form/Fitness/Fatigue komen uit load_history() (dagelijkse waarden op
basis van wellness, inclusief vandaag), niet uit de laatste activiteit. Zo komt
de getoonde Form overeen met het dashboard en met Intervals.icu.
--------------------------------------------------------------------------
MATCHFITAI_DAILY_BUTTON_KEY_FIX_2026-09-27 (op verzoek van Kim: "op mai coach
hoofdpagina werkt de 'laat AI meedenken over de recente periode' niet" -
bevestigd via een OpenAI-dashboardcheck: geen enkele nieuwe 'Responses'-log-
entry sinds 16/09 voor deze specifieke aanroep, terwijl andere AI-features
(bv. de Chat-tab) wel recent gebruikt werden)
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd met een gerichte reproductietest van de exacte widget-
key-logica): _unique_key() gaf voorheen een teller terug die in
st.session_state bleef oplopen OVER ALLE RERUNS HEEN, niet enkel binnen 1
script-run. Streamlit herkent een knop-klik enkel als de knop in de RERUN DIE
DE KLIK VERWERKT exact dezelfde `key` heeft als de knop die de gebruiker in de
VORIGE rerun zag en aanklikte. Omdat de teller bij ELKE rerun (dus ook de klik-
verwerkende rerun zelf) opnieuw ophoogde, kreeg de knop daar altijd een ANDERE
key dan net aangeklikt - waardoor st.button() voor deze knop NOOIT True kon
teruggeven, ongeacht hoe vaak erop geklikt werd. Dat verklaart exact het
gerapporteerde "de knop werkt niet": de AI-aanroep werd letterlijk nooit
uitgevoerd, vandaar ook geen nieuwe entries in de OpenAI-logs hiervoor.
FIX: reset_widget_key_counters() wist nu alle _unique_key()-tellers aan het
BEGIN van elke script-run (aangeroepen vanuit training_dashboard.
render_health_app() - de enige echte top-level entry point, zowel bij
standalone uitvoering als via de gecombineerde app). Binnen een NORMALE run
(deze functie wordt exact 1x aangeroepen) produceert _unique_key() daardoor
weer een STABIELE, identieke key bij elke rerun ("daily_ai_deepdive__1"),
waardoor Streamlit een klik weer correct herkent. Wordt deze functie
(zeldzaam, bij dubbele imports/geneste navigatie) toch 2x in dezelfde run
aangeroepen, dan beschermt de teller nog steeds tegen een StreamlitDuplicate-
ElementKey-fout binnen DIE ene run - de oorspronkelijke bedoeling van de
teller blijft dus behouden, enkel de "blijft oplopen over reruns heen"-fout
is verwijderd.
Geverifieerd met een reproductietest die Streamlit's echte klik-matching-
gedrag nabootst: de oude code herkende een klik nooit (button() gaf bij de
klik-verwerkende rerun altijd False terug); met de fix wordt de klik wel
correct herkend (True).
--------------------------------------------------------------------------
MATCHFITAI_DAILY_BUTTON_TEXT_2026-09-27 (op verzoek van Kim: "vervang...
'laat de AI meedenken over...' door... en verwijder dus het woord 'de'")
--------------------------------------------------------------------------
Tekst aangepast van "Laat de AI meedenken over de recente periode" naar
"Laat AI meedenken over mijn recente periode" - het lidwoord "de" voor "AI"
is weggelaten, en "de recente periode" is "mijn recente periode" geworden.
Robuuste widget-keys: render_daily_update() kan in sommige app-structuren (bv.
door dubbele imports of geneste paginanavigatie) meer dan één keer binnen
dezelfde Streamlit-run worden aangeroepen. Vaste keys zoals "daily_ai_deepdive"
botsen dan met StreamlitDuplicateElementKey. _unique_key() lost dit op door
elke aanroep een oplopend volgnummer te geven - MITS de teller aan het begin
van elke NIEUWE run gereset wordt (zie reset_widget_key_counters() hierboven),
anders blijft de knop-key veranderen over reruns heen en breekt klik-detectie
(zie MATCHFITAI_DAILY_BUTTON_KEY_FIX_2026-09-27 hierboven).
"""
from __future__ import annotations
import pandas as pd
import streamlit as st
from AICoach.chat.ai_message_handler import handle_message
from AICoach.dashboard.charts import form_zone_for
from AICoach.dashboard.data_loaders import load_history, load_wellness_frame


def reset_widget_key_counters() -> None:
    """MATCHFITAI_DAILY_BUTTON_KEY_FIX_2026-09-27: wist alle _unique_key()-
    tellers - MOET exact 1x aan het BEGIN van elke script-run aangeroepen
    worden (vanuit render_health_app() in training_dashboard.py), zodat de
    knop-keys hieronder weer stabiel zijn over reruns heen. Zie de uitgebreide
    root-cause-analyse in de moduledocstring."""
    for key in [k for k in list(st.session_state) if str(k).startswith("__key_counter__")]:
        st.session_state.pop(key, None)


def _unique_key(base: str) -> str:
    """Geef een key terug die uniek is BINNEN 1 script-run (dankzij de
    externe reset via reset_widget_key_counters() bij elke nieuwe run), maar
    STABIEL blijft OVER reruns heen bij een normaal, 1x-per-run gebruik -
    zie MATCHFITAI_DAILY_BUTTON_KEY_FIX_2026-09-27 in de moduledocstring voor
    waarom dat onderscheid cruciaal is voor correcte klik-detectie."""
    counter_name = f"__key_counter__{base}"
    count = st.session_state.get(counter_name, 0) + 1
    st.session_state[counter_name] = count
    return f"{base}__{count}"


def _latest_and_previous(df: pd.DataFrame, column: str):
    if df.empty or column not in df.columns or "date" not in df.columns:
        return None, None, None
    series = df[["date", column]].copy()
    series[column] = pd.to_numeric(series[column], errors="coerce")
    series = series.dropna(subset=[column]).sort_values("date")
    if series.empty:
        return None, None, None
    latest = series.iloc[-1]
    previous = series.iloc[-2] if len(series) >= 2 else None
    recent_mean = series[column].tail(8).iloc[:-1].mean() if len(series) >= 3 else None
    return latest, previous, recent_mean


def compute_daily_signals() -> list[str]:
    wellness = load_wellness_frame()
    history = load_history()
    signals: list[str] = []
    latest, previous, _ = _latest_and_previous(wellness, "resting_hr")
    if latest is not None:
        current = float(latest["resting_hr"])
        line = f"Rusthartslag: {current:.0f} bpm"
        if previous is not None:
            change = current - float(previous["resting_hr"])
            if change >= 3:
                line += (
                    f" — {change:.0f} bpm hoger dan gisteren. Als dit een paar dagen "
                    "aanhoudt, plan dan bewust een rustigere dag of extra herstel."
                )
            elif change <= -3:
                line += f" — {abs(change):.0f} bpm lager dan gisteren, doorgaans een teken van goed herstel."
        signals.append(line)
    latest, _, recent_mean = _latest_and_previous(wellness, "hrv")
    if latest is not None:
        current = float(latest["hrv"])
        line = f"HRV: {current:.0f} ms"
        if recent_mean is not None and pd.notna(recent_mean):
            if current <= recent_mean * 0.85:
                line += " — duidelijk onder je recente gemiddelde, wat op minder herstel kan wijzen."
            elif current >= recent_mean * 1.15:
                line += " — boven je recente gemiddelde, meestal een goed herstelteken."
        signals.append(line)
    latest, _, _ = _latest_and_previous(wellness, "sleep_hours")
    if latest is not None:
        current = float(latest["sleep_hours"])
        line = f"Slaap: {current:.1f} uur"
        if current < 6:
            line += " — kort. Houd hier rekening mee bij een zware sessie vandaag."
        signals.append(line)
    latest, _, _ = _latest_and_previous(wellness, "readiness")
    if latest is not None:
        signals.append(f"Readiness: {float(latest['readiness']):.0f}")
    # Form/Fitness/Fatigue uit de dagelijkse historiek (inclusief vandaag).
    for column, label in (("form", "Form"), ("fitness", "Fitness"), ("fatigue", "Fatigue")):
        latest, _, recent_mean = _latest_and_previous(history, column)
        if latest is None:
            continue
        current = float(latest[column])
        line = f"{label}: {current:.1f}"
        if column == "form":
            zone_name, _ = form_zone_for(current)
            if zone_name:
                line += f" (zone: {zone_name})"
        elif recent_mean is not None and pd.notna(recent_mean):
            trend = current - float(recent_mean)
            if abs(trend) >= 1:
                line += f" ({'stijgend' if trend > 0 else 'dalend'} t.o.v. recent gemiddelde)"
        signals.append(line)
    return signals


def _ai_period_prompt() -> str:
    return (
        "Bekijk uitsluitend mijn recentste periode (laatste 7 tot 14 dagen). "
        "Wat valt op in rusthartslag, HRV, slaap, readiness, Form, Fitness en Fatigue? "
        "Noem alleen inzichten die mij praktisch helpen: wanneer ben ik goed hersteld, "
        "wanneer moet ik voorzichtig zijn, en welke signalen verdienen aandacht als ze aanhouden. "
        "Vermijd open deuren en algemene sportadviezen. Maximaal 5 korte, concrete inzichten."
    )


def render_daily_update() -> None:
    st.markdown("### Dagelijkse update")
    signals = compute_daily_signals()
    if not signals:
        st.caption("Nog onvoldoende recente data voor een dagelijkse update.")
        return
    for line in signals:
        st.markdown(f"- {line}")
    if st.button(
        # MATCHFITAI_DAILY_BUTTON_TEXT_2026-09-27: "de" voor "AI" weggelaten,
        # "de recente periode" -> "mijn recente periode".
        "Laat AI meedenken over mijn recente periode",
        key=_unique_key("daily_ai_deepdive"),
    ):
        with st.spinner("mAICoach analyseert je recente periode..."):
            st.session_state.daily_ai_answer = handle_message(_ai_period_prompt())
    answer = st.session_state.get("daily_ai_answer")
    if answer:
        from AICoach.dashboard.ui_helpers import render_assistant_answer
        render_assistant_answer(answer)
        if st.button(
            "Deze analyse bewaren bij mijn kennis",
            key=_unique_key("daily_ai_save"),
        ):
            from AICoach.saved_insights import save_insight
            save_insight(answer, source="Dagelijkse update")
            st.success("Analyse bewaard bij je kennis.")
