# -*- coding: utf-8 -*-
"""Dagelijkse update voor mAICoach.

Bekijkt de recentste wellness- en trainingsdata en signaleert wat er de voorbije
periode opvalt: rusthartslag, HRV, slaap, readiness en de trend in Form, Fitness
en Fatigue. Voorzichtig geformuleerd en gericht op wat je er praktisch mee kunt.

Belangrijk: Form/Fitness/Fatigue komen uit load_history() (dagelijkse waarden op
basis van wellness, inclusief vandaag), niet uit de laatste activiteit. Zo komt
de getoonde Form overeen met het dashboard en met Intervals.icu.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from AICoach.chat.ai_message_handler import handle_message
from AICoach.dashboard.charts import form_zone_for
from AICoach.dashboard.data_loaders import load_history, load_wellness_frame


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

    if st.button("Laat de AI meedenken over de recente periode", key="daily_ai_deepdive"):
        with st.spinner("mAICoach analyseert je recente periode..."):
            st.session_state.daily_ai_answer = handle_message(_ai_period_prompt())

    answer = st.session_state.get("daily_ai_answer")
    if answer:
        from AICoach.dashboard.ui_helpers import render_assistant_answer

        render_assistant_answer(answer)
        if st.button("Deze analyse bewaren bij mijn kennis", key="daily_ai_save"):
            from AICoach.saved_insights import save_insight

            save_insight(answer, source="Dagelijkse update")
            st.success("Analyse bewaard bij je kennis.")
