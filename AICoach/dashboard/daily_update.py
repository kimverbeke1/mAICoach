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
teruggeven, ongeacht hoe vaak erop geklikt werd.

FIX: reset_widget_key_counters() wist nu alle _unique_key()-tellers aan het
BEGIN van elke script-run (aangeroepen vanuit training_dashboard.
render_health_app()). Binnen een NORMALE run produceert _unique_key() daardoor
weer een STABIELE, identieke key bij elke rerun ("daily_ai_deepdive__1").

--------------------------------------------------------------------------
MATCHFITAI_DAILY_BUTTON_TEXT_2026-09-27 (op verzoek van Kim)
--------------------------------------------------------------------------
Tekst aangepast naar "Laat AI meedenken over mijn recente periode".

--------------------------------------------------------------------------
MATCHFITAI_STALE_SIGNAL_FIX_2026-10-16 (op verzoek van Kim: "readiness toont
altijd 9, dat klopt niet")
--------------------------------------------------------------------------
ROOT CAUSE: _latest_and_previous() laat lege waarden vallen en neemt dan de
LAATSTE NIET-LEGE waarde - ongeacht hoe oud die is. Garmin stuurt al lange tijd
geen readiness meer door naar Intervals.icu (check_readiness.py: readiness is
None op alle recente dagen), dus de dagelijkse update bleef eindeloos de
laatste oude waarde (9) tonen alsof die van vandaag was. Hetzelfde risico gold
voor rusthartslag, HRV en slaap.

FIX: elke wellness-meting wordt nu getoetst aan haar ouderdom t.o.v. vandaag.
  - 0-1 dag oud: getoond zoals voorheen.
  - ouder dan 1 dag maar binnen MAX_SIGNAL_AGE_DAYS: getoond MET de datum van
    de meting erbij, zodat duidelijk is dat het geen meting van vandaag is.
  - ouder dan MAX_SIGNAL_AGE_DAYS: NIET meer als actuele waarde getoond, maar
    als "geen recente data (laatste: X op dd/mm/jjjj)" - en er worden geen
    trend-conclusies meer aan verbonden.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from AICoach.chat.ai_message_handler import handle_message
from AICoach.dashboard.charts import form_zone_for
from AICoach.dashboard.data_loaders import load_history, load_wellness_frame

# MATCHFITAI_STALE_SIGNAL_FIX_2026-10-16: metingen ouder dan dit aantal dagen
# gelden niet meer als actuele waarde.
MAX_SIGNAL_AGE_DAYS = 3


def reset_widget_key_counters() -> None:
    """MATCHFITAI_DAILY_BUTTON_KEY_FIX_2026-09-27: wist alle _unique_key()-
    tellers - MOET exact 1x aan het BEGIN van elke script-run aangeroepen
    worden (vanuit render_health_app() in training_dashboard.py)."""
    for key in [k for k in list(st.session_state) if str(k).startswith("__key_counter__")]:
        st.session_state.pop(key, None)


def _unique_key(base: str) -> str:
    """Key die uniek is BINNEN 1 script-run, maar STABIEL OVER reruns heen."""
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


def _age_days(row) -> int | None:
    """MATCHFITAI_STALE_SIGNAL_FIX_2026-10-16: ouderdom van een meting in dagen."""
    try:
        measured = pd.Timestamp(row["date"]).normalize()
    except (KeyError, TypeError, ValueError):
        return None
    return int((pd.Timestamp.today().normalize() - measured).days)


def _date_text(row) -> str:
    return pd.Timestamp(row["date"]).strftime("%d/%m/%Y")


def _stale_line(label: str, value_text: str, row) -> str:
    return f"{label}: geen recente data (laatste: {value_text} op {_date_text(row)})"


def _date_note(row) -> str:
    """Datum-toevoeging voor een meting die niet van vandaag/gisteren is."""
    age = _age_days(row)
    if age is not None and age > 1:
        return f" (meting van {_date_text(row)})"
    return ""


def _is_stale(row) -> bool:
    age = _age_days(row)
    return age is not None and age > MAX_SIGNAL_AGE_DAYS


def compute_daily_signals() -> list[str]:
    wellness = load_wellness_frame()
    history = load_history()
    signals: list[str] = []

    # Rusthartslag
    latest, previous, _ = _latest_and_previous(wellness, "resting_hr")
    if latest is not None:
        current = float(latest["resting_hr"])
        if _is_stale(latest):
            signals.append(_stale_line("Rusthartslag", f"{current:.0f} bpm", latest))
        else:
            line = f"Rusthartslag: {current:.0f} bpm{_date_note(latest)}"
            if previous is not None:
                change = current - float(previous["resting_hr"])
                if change >= 3:
                    line += (
                        f" — {change:.0f} bpm hoger dan de vorige meting. Als dit een paar dagen "
                        "aanhoudt, plan dan bewust een rustigere dag of extra herstel."
                    )
                elif change <= -3:
                    line += f" — {abs(change):.0f} bpm lager dan de vorige meting, doorgaans een teken van goed herstel."
            signals.append(line)

    # HRV
    latest, _, recent_mean = _latest_and_previous(wellness, "hrv")
    if latest is not None:
        current = float(latest["hrv"])
        if _is_stale(latest):
            signals.append(_stale_line("HRV", f"{current:.0f} ms", latest))
        else:
            line = f"HRV: {current:.0f} ms{_date_note(latest)}"
            if recent_mean is not None and pd.notna(recent_mean):
                if current <= recent_mean * 0.85:
                    line += " — duidelijk onder je recente gemiddelde, wat op minder herstel kan wijzen."
                elif current >= recent_mean * 1.15:
                    line += " — boven je recente gemiddelde, meestal een goed herstelteken."
            signals.append(line)

    # Slaap
    latest, _, _ = _latest_and_previous(wellness, "sleep_hours")
    if latest is not None:
        current = float(latest["sleep_hours"])
        if _is_stale(latest):
            signals.append(_stale_line("Slaap", f"{current:.1f} uur", latest))
        else:
            line = f"Slaap: {current:.1f} uur{_date_note(latest)}"
            if current < 6:
                line += " — kort. Houd hier rekening mee bij een zware sessie vandaag."
            signals.append(line)

    # Readiness (MATCHFITAI_STALE_SIGNAL_FIX_2026-10-16: hier zat de "altijd 9"-bug)
    latest, _, _ = _latest_and_previous(wellness, "readiness")
    if latest is not None:
        current = float(latest["readiness"])
        if _is_stale(latest):
            signals.append(_stale_line("Readiness", f"{current:.0f}", latest))
        else:
            signals.append(f"Readiness: {current:.0f}{_date_note(latest)}")

    # Form/Fitness/Fatigue uit de dagelijkse historiek (inclusief vandaag).
    for column, label in (("form", "Form"), ("fitness", "Fitness"), ("fatigue", "Fatigue")):
        latest, _, recent_mean = _latest_and_previous(history, column)
        if latest is None:
            continue
        current = float(latest[column])
        line = f"{label}: {current:.1f}{_date_note(latest)}"
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
        "Negeer metingen die ouder zijn dan die periode. "
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
