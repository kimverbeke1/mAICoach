# -*- coding: utf-8 -*-
"""Beste resultaten voor mAICoach.

- Beste pace op standaardafstanden (1, 5, 10, 16, 21.1, 42.2 km).
- Records per categorie (HR-efficiëntie, laagste gem. HR, langste afstand,
  hoogste load, meeste hoogtemeters, hoogste TRIMP).
- Selecteer een rij in een tabel om de volledige details van die prestatie te zien.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from AICoach.dashboard.data_loaders import load_activities_frame, is_running_sport
from AICoach.dashboard.ui_helpers import format_duration, format_pace

TARGET_DISTANCES_KM = [1, 5, 10, 16, 21.1, 42.2]
DISTANCE_TOLERANCE = 0.97


def _date_label(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed.strftime("%d/%m/%Y") if not pd.isna(parsed) else "onbekend"


def _running_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "sport" not in df.columns:
        return pd.DataFrame()
    runs = df[df["sport"].apply(is_running_sport)].copy()
    if runs.empty:
        return runs
    runs["distance_km"] = pd.to_numeric(runs.get("distance_km"), errors="coerce")
    runs["duration_min"] = pd.to_numeric(runs.get("duration_min"), errors="coerce")
    runs = runs[(runs["distance_km"] > 0) & (runs["duration_min"] > 0)].copy()
    if runs.empty:
        return runs
    runs["pace_min_per_km"] = runs["duration_min"] / runs["distance_km"]
    return runs


def best_pace_records(df: pd.DataFrame) -> pd.DataFrame:
    runs = _running_frame(df)
    rows: list[dict] = []
    if not runs.empty:
        for target in TARGET_DISTANCES_KM:
            eligible = runs[runs["distance_km"] >= target * DISTANCE_TOLERANCE]
            if eligible.empty:
                continue
            best = eligible.loc[eligible["pace_min_per_km"].idxmin()]
            rows.append(
                {
                    "Afstand": f"{target:g} km",
                    "Beste pace": format_pace(best["distance_km"], best["duration_min"]),
                    "Afstand run": f"{float(best['distance_km']):.2f} km",
                    "Gem. HR": f"{float(best['avg_hr']):.0f} bpm" if pd.notna(best.get("avg_hr")) else "—",
                    "Datum": _date_label(best.get("date")),
                    "_id": str(best.get("id")),
                }
            )
    return pd.DataFrame(rows)


def _best_row(df: pd.DataFrame, column: str, largest: bool):
    if df.empty or column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce")
    subset = df.loc[values.notna()].copy()
    if subset.empty:
        return None
    subset[column] = values.loc[values.notna()]
    idx = subset[column].idxmax() if largest else subset[column].idxmin()
    return subset.loc[idx]


def _fmt(row, column, suffix, digits):
    value = pd.to_numeric(row.get(column), errors="coerce")
    return "—" if pd.isna(value) else f"{float(value):.{digits}f}{suffix}"


def metric_records(df: pd.DataFrame) -> pd.DataFrame:
    runs = _running_frame(df)
    rows: list[dict] = []

    def add(title, row, value_text):
        if row is None:
            return
        rows.append(
            {
                "Categorie": title,
                "Waarde": value_text,
                "Sport": str(row.get("sport") or "—"),
                "Datum": _date_label(row.get("date")),
                "_id": str(row.get("id")),
            }
        )

    if not runs.empty and "avg_hr" in runs.columns:
        eligible = runs[pd.to_numeric(runs["avg_hr"], errors="coerce") > 0].copy()
        if not eligible.empty:
            eligible["speed_kmh"] = eligible["distance_km"] / (eligible["duration_min"] / 60.0)
            eligible["efficiency"] = eligible["speed_kmh"] / eligible["avg_hr"]
            best_eff = eligible.loc[eligible["efficiency"].idxmax()]
            add("Beste HR-efficiëntie (snelheid per hartslag)", best_eff,
                f"{float(best_eff['efficiency']):.4f} km/u per bpm")
        long_runs = runs[runs["distance_km"] >= 5]
        low_hr = _best_row(long_runs, "avg_hr", largest=False)
        add("Laagste gem. HR (run ≥ 5 km)", low_hr, _fmt(low_hr, "avg_hr", " bpm", 0) if low_hr is not None else "—")

    longest = _best_row(df, "distance_km", largest=True)
    add("Langste afstand", longest, _fmt(longest, "distance_km", " km", 2) if longest is not None else "—")
    hardest = _best_row(df, "training_load", largest=True)
    add("Hoogste training load", hardest, _fmt(hardest, "training_load", "", 0) if hardest is not None else "—")
    climb = _best_row(df, "elevation_gain", largest=True)
    add("Meeste hoogtemeters", climb, _fmt(climb, "elevation_gain", " m", 0) if climb is not None else "—")
    trimp = _best_row(df, "trimp", largest=True)
    add("Hoogste TRIMP", trimp, _fmt(trimp, "trimp", "", 0) if trimp is not None else "—")
    return pd.DataFrame(rows)


def _render_detail(df: pd.DataFrame, activity_id: str) -> None:
    match = df[df["id"].astype(str) == str(activity_id)]
    if match.empty:
        return
    row = match.iloc[0]
    st.markdown(f"#### {row.get('name') or 'Activiteit'}")
    st.caption(f"{_date_label(row.get('date'))} · {row.get('sport') or '—'}")
    fields = [
        ("Afstand", _fmt(row, "distance_km", " km", 2)),
        ("Duur", format_duration(row.get("duration_min"))),
        ("Pace", format_pace(row.get("distance_km"), row.get("duration_min"))),
        ("Gem. HR", _fmt(row, "avg_hr", " bpm", 0)),
        ("Max HR", _fmt(row, "max_hr", " bpm", 0)),
        ("Training load", _fmt(row, "training_load", "", 0)),
        ("TRIMP", _fmt(row, "trimp", "", 0)),
        ("Hoogtewinst", _fmt(row, "elevation_gain", " m", 0)),
        ("Calorieen", _fmt(row, "calories", "", 0)),
        ("Fitness", _fmt(row, "fitness", "", 1)),
        ("Fatigue", _fmt(row, "fatigue", "", 1)),
        ("Form", _fmt(row, "form", "", 1)),
    ]
    detail = pd.DataFrame(
        [{"Onderdeel": label, "Waarde": value} for label, value in fields if value != "—"]
    )
    st.dataframe(detail, use_container_width=True, hide_index=True)


def _render_records_with_detail(df: pd.DataFrame, records: pd.DataFrame, key: str) -> None:
    if records.empty:
        st.caption("Nog onvoldoende data.")
        return
    visible = records.drop(columns=["_id"])
    event = st.dataframe(
        visible,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
    )
    try:
        rows = event.selection.rows
    except AttributeError:
        rows = event.get("selection", {}).get("rows", []) if event else []
    if rows:
        activity_id = records.iloc[rows[0]]["_id"]
        _render_detail(df, activity_id)
    else:
        st.caption("Selecteer een rij om de details van die prestatie te zien.")


def render_best_results() -> None:
    st.subheader("Beste resultaten")
    df = load_activities_frame()
    if df.empty:
        st.info("Er zijn nog geen activiteiten beschikbaar.")
        return

    st.markdown("#### Beste pace per afstand")
    _render_records_with_detail(df, best_pace_records(df), key="best_pace_table")

    st.markdown("#### Records per categorie")
    _render_records_with_detail(df, metric_records(df), key="best_metric_table")
