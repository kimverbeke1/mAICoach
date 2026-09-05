# -*- coding: utf-8 -*-

import pandas as pd
import streamlit as st


MIN_VISIBLE_RECORDS = 3
RUN_TOKENS = ("run", "running", "trail")

FIELD_LABELS = {
    "resting_hr": "Rusthartslag",
    "hrv": "HRV",
    "sleep_hours": "Slaap",
    "sleep_score": "Slaapscore",
    "sleep_quality": "Slaapkwaliteit",
    "readiness": "Readiness",
    "steps": "Stappen",
    "vo2max": "VO2max",
    "motivation": "Motivatie",
    "fitness": "Fitness",
    "fatigue": "Fatigue",
    "form": "Form",
    "training_load": "Training load",
}

FIELD_SUFFIXES = {
    "resting_hr": " bpm",
    "hrv": " ms",
    "sleep_hours": " uur",
    "steps": "",
    "vo2max": "",
    "fitness": "",
    "fatigue": "",
    "form": "",
    "training_load": "",
}

FIELD_DIGITS = {
    "steps": 0,
    "sleep_hours": 1,
}


def has_data(df, column, minimum=MIN_VISIBLE_RECORDS):
    return column in df.columns and int(df[column].notna().sum()) >= minimum


def display_value(value, suffix="", digits=1, decimals=None):
    if decimals is not None:
        digits = decimals

    if value is None or pd.isna(value):
        return "Niet beschikbaar"

    return f"{float(value):.{digits}f}{suffix}"



def is_running_sport(sport):
    value = str(sport or "").lower()
    return any(token in value for token in RUN_TOKENS)


def format_duration(minutes):
    if minutes is None or pd.isna(minutes):
        return "Niet beschikbaar"
    total_seconds = int(round(float(minutes) * 60))
    hours, remainder = divmod(total_seconds, 3600)
    mins, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{mins:02d}:{seconds:02d}"
    return f"{mins}:{seconds:02d}"


def format_pace(distance_km, duration_min):
    if (
        distance_km is None
        or duration_min is None
        or pd.isna(distance_km)
        or pd.isna(duration_min)
        or distance_km <= 0
    ):
        return "Niet beschikbaar"

    seconds_per_km = float(duration_min) * 60 / float(distance_km)
    minutes = int(seconds_per_km // 60)
    seconds = int(round(seconds_per_km % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def nearest_row(df, selected_date):
    if df.empty:
        return None
    if selected_date is None:
        return df.iloc[-1]

    exact = df[df["date"].dt.normalize() == selected_date]
    if not exact.empty:
        return exact.iloc[-1]

    distances = (df["date"].dt.normalize() - selected_date).abs()
    return df.loc[distances.idxmin()]


def render_selected_values(row, fields, heading="Geselecteerde dag"):
    if row is None:
        return

    selected_date = row.get("date")
    if pd.notna(selected_date):
        st.markdown(f"### {heading}: {selected_date.strftime('%d/%m/%Y')}")

    visible = [field for field in fields if field in row.index and pd.notna(row.get(field))]
    if not visible:
        st.caption("Voor deze dag zijn geen waarden beschikbaar.")
        return

    for start in range(0, len(visible), 5):
        subset = visible[start : start + 5]
        columns = st.columns(len(subset))
        for column, field in zip(columns, subset):
            column.metric(
                FIELD_LABELS.get(field, field),
                display_value(
                    row.get(field),
                    FIELD_SUFFIXES.get(field, ""),
                    FIELD_DIGITS.get(field, 1),
                ),
            )


def render_assistant_answer(answer):
    marker = "### Technische details"
    if marker not in answer:
        st.markdown(answer)
        return

    main_text, details = answer.split(marker, 1)
    st.markdown(main_text.strip())

    if details.strip():
        with st.expander("Technische details en gebruikte data"):
            st.markdown(details.strip())
