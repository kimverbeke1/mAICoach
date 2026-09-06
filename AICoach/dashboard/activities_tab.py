# -*- coding: utf-8 -*-
"""Activiteitenpagina van mAICoach.

UX-principes:
- Doorklikken op een activiteit opent meteen de details (elke rij is een knop).
- Geen detail-/vergelijkknoppen onderaan.
- Vergelijken gebeurt via een schakelaar bovenaan. In vergelijkmodus krijgt elke
  activiteit een selectievakje en staat de vergelijkknop prominent bovenaan
  (goed zichtbaar, ook op mobiel).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from AICoach.dashboard.activity_detail import render_activity_detail
from AICoach.dashboard.data_loaders import load_activities_frame
from AICoach.dashboard.ui_helpers import format_duration

ALL_SPORTS_LABEL = "Alle sporten"
PAGE_SIZE = 20


def _row_by_id(df: pd.DataFrame, activity_id: str):
    matches = df[df["id"].astype(str) == str(activity_id)]
    return None if matches.empty else matches.iloc[0]


def _selected_ids() -> list[str]:
    values = st.session_state.get("activity_comparison_ids", [])
    return list(dict.fromkeys(str(value) for value in values))[:2]


def _toggle_selection(activity_id: str) -> None:
    ids = _selected_ids()
    activity_id = str(activity_id)
    if activity_id in ids:
        ids.remove(activity_id)
    elif len(ids) < 2:
        ids.append(activity_id)
    else:
        st.toast("Je kunt exact 2 activiteiten selecteren. Deselecteer er eerst een.")
    st.session_state.activity_comparison_ids = ids


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    sports = sorted(
        str(value)
        for value in df.get("sport", pd.Series(dtype=str)).dropna().unique()
        if str(value).strip()
    )
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return df.copy()

    row1 = st.columns([1.2, 1, 1])
    with row1[0]:
        sport = st.selectbox("Sport", [ALL_SPORTS_LABEL, *sports], key="activities_sport_filter")
    with row1[1]:
        start = st.date_input("Vanaf", value=dates.min().date(), key="activities_start_date")
    with row1[2]:
        end = st.date_input("Tot en met", value=dates.max().date(), key="activities_end_date")
    search = st.text_input("Zoeken op naam", key="activities_search").strip()

    filtered = df.copy()
    if sport != ALL_SPORTS_LABEL:
        filtered = filtered[filtered["sport"].astype(str) == sport]
    filtered_dates = pd.to_datetime(filtered["date"], errors="coerce").dt.date
    filtered = filtered[filtered_dates.between(start, end, inclusive="both")]
    if search:
        filtered = filtered[
            filtered["name"].fillna("").astype(str).str.contains(search, case=False, regex=False)
        ]
    return filtered.sort_values("date", ascending=False).reset_index(drop=True)


def _activity_summary(row: pd.Series) -> str:
    date_value = pd.to_datetime(row.get("date"), errors="coerce")
    date_label = date_value.strftime("%d/%m/%Y") if not pd.isna(date_value) else ""
    parts = [date_label, str(row.get("sport") or "Onbekend")]
    if pd.notna(row.get("distance_km")):
        parts.append(f"{float(row['distance_km']):.1f} km")
    if pd.notna(row.get("duration_min")):
        parts.append(format_duration(row["duration_min"]))
    if pd.notna(row.get("avg_hr")):
        parts.append(f"{float(row['avg_hr']):.0f} bpm")
    if pd.notna(row.get("training_load")):
        parts.append(f"load {float(row['training_load']):.0f}")
    return "  ·  ".join(part for part in parts if part)


def _open_detail(activity_id: str) -> None:
    st.session_state.selected_activity_id = str(activity_id)
    st.session_state.activity_view = "detail"
    st.rerun()


def _start_comparison() -> None:
    st.session_state.comparison_active = True
    st.session_state.comparison_answer = ""
    st.session_state.comparison_messages = []
    st.session_state.comparison_autostart = True
    st.rerun()


def _render_compare_bar() -> None:
    ids = _selected_ids()
    bar = st.columns([6, 4])
    with bar[0]:
        st.caption(f"{len(ids)}/2 geselecteerd. Vink 2 activiteiten aan en start de vergelijking.")
    with bar[1]:
        if st.button(
            "⚖️ Vergelijk 2 activiteiten",
            disabled=len(ids) != 2,
            use_container_width=True,
            type="primary",
        ):
            _start_comparison()


def _render_list(filtered: pd.DataFrame, compare_mode: bool) -> None:
    total = len(filtered)
    page = int(st.session_state.get("activities_page", 1))
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 1), pages)
    st.session_state.activities_page = page
    start = (page - 1) * PAGE_SIZE
    rows = filtered.iloc[start : start + PAGE_SIZE]

    selected = set(_selected_ids())

    for _, row in rows.iterrows():
        activity_id = str(row.get("id"))
        name = str(row.get("name") or "Activiteit")
        summary = _activity_summary(row)

        if compare_mode:
            columns = st.columns([1, 11])
            with columns[0]:
                checked = st.checkbox(
                    " ",
                    value=activity_id in selected,
                    key=f"cmp_{activity_id}",
                    label_visibility="collapsed",
                )
                if checked and activity_id not in selected and len(selected) < 2:
                    _toggle_selection(activity_id)
                    st.rerun()
                elif not checked and activity_id in selected:
                    _toggle_selection(activity_id)
                    st.rerun()
                elif checked and activity_id not in selected and len(selected) >= 2:
                    st.session_state[f"cmp_{activity_id}"] = False
            with columns[1]:
                st.markdown(f"**{name}**")
                st.caption(summary)
        else:
            # Elke activiteit is één grote, aantikbare knop -> opent details.
            if st.button(
                f"**{name}**\n\n{summary}",
                key=f"open_{activity_id}",
                use_container_width=True,
            ):
                _open_detail(activity_id)

    if pages > 1:
        nav = st.columns([2, 3, 2])
        with nav[0]:
            if st.button("← Vorige", disabled=page <= 1, use_container_width=True):
                st.session_state.activities_page = page - 1
                st.rerun()
        with nav[1]:
            st.caption(f"Pagina {page} van {pages}  ·  {total} activiteiten")
        with nav[2]:
            if st.button("Volgende →", disabled=page >= pages, use_container_width=True):
                st.session_state.activities_page = page + 1
                st.rerun()


def _render_browser(df: pd.DataFrame) -> None:
    st.subheader("Activiteiten")

    top = st.columns([7, 5])
    with top[0]:
        if not st.session_state.get("compare_mode"):
            st.caption("Tik op een activiteit om de details te openen.")
    with top[1]:
        compare_mode = st.toggle(
            "Vergelijkmodus",
            key="compare_mode",
            help="Selecteer 2 activiteiten om ze met AI te vergelijken.",
        )

    filtered = _apply_filters(df)

    if compare_mode:
        _render_compare_bar()

    if filtered.empty:
        st.info("Geen activiteiten gevonden voor deze filters.")
        return

    _render_list(filtered, compare_mode=bool(compare_mode))


def render_activities() -> None:
    df = load_activities_frame()
    if df.empty:
        st.info("Er zijn nog geen activiteiten beschikbaar.")
        return
    if "activity_comparison_ids" not in st.session_state:
        st.session_state.activity_comparison_ids = []

    if st.session_state.get("activity_view") == "detail":
        selected = _row_by_id(df, st.session_state.get("selected_activity_id", ""))
        if selected is None:
            st.session_state.activity_view = "browser"
            st.rerun()
        if st.button("← Terug naar activiteiten", key="detail_back_to_activities"):
            st.session_state.activity_view = "browser"
            st.rerun()
        render_activity_detail(selected, df)
        return

    _render_browser(df)
