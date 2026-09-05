# -*- coding: utf-8 -*-

import streamlit as st

from AICoach.dashboard.charts import render_time_chart, selected_date_from_event
from AICoach.dashboard.data_loaders import load_wellness_frame
from AICoach.dashboard.ui_helpers import nearest_row, render_selected_values


def render_recovery():
    df = load_wellness_frame()

    if df.empty:
        st.warning("Geen wellnessdata gevonden. Vernieuw eerst je gegevens.")
        return

    st.caption(
        f"Laatste wellnessrecord: {df.iloc[-1]['date'].strftime('%d/%m/%Y')}"
    )

    periods = {
        "30 dagen": 30,
        "90 dagen": 90,
        "Dit jaar": 366,
        "Alles": len(df),
    }
    selected_period = st.selectbox(
        "Periode",
        list(periods),
        index=2,
        key="recovery_period",
    )
    view = df.tail(periods[selected_period]).copy()

    selected_date = st.session_state.get("recovery_selected_date")
    selected_row = nearest_row(view, selected_date)
    render_selected_values(
        selected_row,
        [
            "resting_hr",
            "hrv",
            "sleep_hours",
            "sleep_score",
            "readiness",
            "steps",
            "vo2max",
            "motivation",
        ],
    )

    chart_groups = [
        ("Herstel", ["resting_hr", "hrv", "readiness"]),
        ("Slaap", ["sleep_hours", "sleep_score", "sleep_quality"]),
        ("Dagelijkse activiteit", ["steps"]),
        ("VO2max", ["vo2max"]),
    ]

    for index, (title, fields) in enumerate(chart_groups):
        event = render_time_chart(
            view,
            fields,
            key=f"recovery_chart_{index}",
            selected_date=selected_date,
            title=title,
        )
        event_date = selected_date_from_event(event)
        if event_date is not None and event_date != selected_date:
            st.session_state.recovery_selected_date = event_date
            st.rerun()
