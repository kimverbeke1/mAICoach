# -*- coding: utf-8 -*-
"""Activiteitenpagina van mAICoach.

- Sorteerbare/filterbare tabel (klik kolomkop om te sorteren).
- Selecteer 1 rij om details te openen (geen dropdown).
- Selecteer 2 rijen en start de vergelijking via een knop. De vergelijking opent
  in een aparte tab die je weer kunt sluiten. Het aanvinken zelf doet GEEN AI-call.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from AICoach.dashboard.activity_detail import render_activity_detail
from AICoach.dashboard.data_loaders import load_activities_frame

ALL_SPORTS_LABEL = "Alle sporten"

TABLE_COLUMNS = [
    ("date", "Datum"),
    ("name", "Naam"),
    ("sport", "Sport"),
    ("distance_km", "Afstand (km)"),
    ("duration_min", "Duur (min)"),
    ("avg_hr", "Gem. HR"),
    ("max_hr", "Max HR"),
    ("training_load", "Load"),
    ("elevation_gain", "Hoogtewinst (m)"),
    ("calories", "Calorieen"),
]


def _row_by_id(df: pd.DataFrame, activity_id: str):
    matches = df[df["id"].astype(str) == str(activity_id)]
    return None if matches.empty else matches.iloc[0]


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    sports = sorted(
        str(value)
        for value in df.get("sport", pd.Series(dtype=str)).dropna().unique()
        if str(value).strip()
    )
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return df.copy()

    row1 = st.columns([1.1, 1, 1])
    with row1[0]:
        sport = st.selectbox("Sport", [ALL_SPORTS_LABEL, *sports], key="activities_sport_filter")
    with row1[1]:
        start = st.date_input("Vanaf", value=dates.min().date(), key="activities_start_date")
    with row1[2]:
        end = st.date_input("Tot en met", value=dates.max().date(), key="activities_end_date")

    max_distance = float(pd.to_numeric(df.get("distance_km"), errors="coerce").max() or 0)
    row2 = st.columns([1.4, 1.3])
    with row2[0]:
        search = st.text_input("Zoeken op naam", key="activities_search").strip()
    distance_range = None
    with row2[1]:
        if max_distance > 0:
            distance_range = st.slider(
                "Afstand (km)",
                min_value=0.0,
                max_value=round(max_distance + 0.5, 1),
                value=(0.0, round(max_distance + 0.5, 1)),
                key="activities_distance_range",
            )

    filtered = df.copy()
    if sport != ALL_SPORTS_LABEL:
        filtered = filtered[filtered["sport"].astype(str) == sport]
    filtered_dates = pd.to_datetime(filtered["date"], errors="coerce").dt.date
    filtered = filtered[filtered_dates.between(start, end, inclusive="both")]
    if search:
        filtered = filtered[
            filtered["name"].fillna("").astype(str).str.contains(search, case=False, regex=False)
        ]
    if distance_range is not None:
        distances = pd.to_numeric(filtered["distance_km"], errors="coerce")
        filtered = filtered[distances.between(distance_range[0], distance_range[1], inclusive="both")]
    return filtered.sort_values("date", ascending=False).reset_index(drop=True)


def _display_table(filtered: pd.DataFrame) -> pd.DataFrame:
    table = pd.DataFrame()
    for key, label in TABLE_COLUMNS:
        if key not in filtered.columns:
            continue
        if key == "date":
            table[label] = pd.to_datetime(filtered[key], errors="coerce").dt.strftime("%d/%m/%Y")
        elif key in ("distance_km", "training_load"):
            table[label] = pd.to_numeric(filtered[key], errors="coerce").round(2)
        elif key in ("duration_min", "avg_hr", "max_hr", "elevation_gain", "calories"):
            table[label] = pd.to_numeric(filtered[key], errors="coerce").round(0)
        else:
            table[label] = filtered[key].astype(str)
    return table


def _render_browser(df: pd.DataFrame) -> None:
    st.subheader("Activiteiten")
    filtered = _apply_filters(df)
    if filtered.empty:
        st.info("Geen activiteiten gevonden voor deze filters.")
        return

    st.caption(
        "Klik op een kolomkop om te sorteren. Selecteer 1 rij voor details, "
        "of 2 rijen om te vergelijken."
    )
    table = _display_table(filtered)
    event = st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        height=560,
        on_select="rerun",
        selection_mode="multi-row",
        key="activities_dataframe",
    )

    try:
        selected_rows = event.selection.rows
    except AttributeError:
        selected_rows = event.get("selection", {}).get("rows", []) if event else []

    selected_ids = [str(filtered.iloc[index]["id"]) for index in selected_rows if index < len(filtered)]

    actions = st.columns([3, 3, 6])
    with actions[0]:
        if st.button("Open details", disabled=len(selected_ids) != 1, use_container_width=True):
            st.session_state.selected_activity_id = selected_ids[0]
            st.session_state.activity_view = "detail"
            st.rerun()
    with actions[1]:
        if st.button(
            "Vergelijk in aparte tab",
            disabled=len(selected_ids) != 2,
            type="primary",
            use_container_width=True,
        ):
            st.session_state.activity_comparison_ids = selected_ids
            st.session_state.comparison_active = True
            st.session_state.comparison_answer = ""
            st.session_state.comparison_messages = []
            st.rerun()
    with actions[2]:
        if len(selected_ids) == 0:
            st.caption("Niets geselecteerd.")
        elif len(selected_ids) == 1:
            st.caption("1 rij geselecteerd — open details of selecteer er nog 1 om te vergelijken.")
        elif len(selected_ids) == 2:
            st.caption("2 rijen geselecteerd — klik op 'Vergelijk in aparte tab'.")
        else:
            st.caption(f"{len(selected_ids)} rijen geselecteerd — selecteer er exact 2 om te vergelijken.")


def render_activities() -> None:
    df = load_activities_frame()
    if df.empty:
        st.info("Er zijn nog geen activiteiten beschikbaar.")
        return

    if st.session_state.get("activity_view") == "detail":
        selected = _row_by_id(df, st.session_state.get("selected_activity_id", ""))
        if selected is None:
            st.session_state.activity_view = "browser"
            st.rerun()
        if st.button("Terug naar activiteiten", key="detail_back_to_activities"):
            st.session_state.activity_view = "browser"
            st.rerun()
        render_activity_detail(selected, df)
        return

    _render_browser(df)
