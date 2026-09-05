# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from AICoach.activity_comparison import find_similar_activities
from AICoach.dashboard.charts import PLOT_CONFIG
from AICoach.dashboard.ui_helpers import (
    display_value,
    format_duration,
    format_pace,
    is_running_sport,
)

# Streams komen uit Firestore/lokaal via persistent_data (ensure_local_stream).
try:
    from AICoach.download_activity_streams import ensure_local_stream
    from AICoach.persistent_data import load_stream_csv
except Exception:  # noqa: BLE001 - persistente laag is optioneel
    ensure_local_stream = None
    load_stream_csv = None

# Mogelijke kolomnamen per meetwaarde in de Intervals streams-CSV.
STREAM_TIME_COLUMNS = ("time", "seconds", "elapsed", "secs")
STREAM_DISTANCE_COLUMNS = ("distance", "distance_km", "distance_m")
STREAM_SERIES = [
    ("heartrate", ("heartrate", "hr", "heart_rate"), "Hartslag (bpm)", "#d62728"),
    ("pace", ("pace", "velocity_smooth", "speed", "enhanced_speed"), "Snelheid/Tempo", "#1f77b4"),
    ("altitude", ("altitude", "elevation", "enhanced_altitude"), "Hoogte (m)", "#8c564b"),
    ("cadence", ("cadence", "cadence_running", "cad"), "Cadans", "#2ca02c"),
    ("power", ("power", "watts"), "Vermogen (W)", "#9467bd"),
    ("temp", ("temp", "temperature"), "Temperatuur (°C)", "#e6a700"),
]
STREAM_LAT_COLUMNS = ("lat", "latitude", "position_lat")
STREAM_LON_COLUMNS = ("lng", "lon", "long", "longitude", "position_long")


def _peer_label(row: pd.Series) -> str:
    date_value = pd.to_datetime(row.get("date"), errors="coerce")
    date_label = date_value.strftime("%d/%m/%Y") if not pd.isna(date_value) else "Datum onbekend"
    distance = pd.to_numeric(row.get("distance_km"), errors="coerce")
    duration = pd.to_numeric(row.get("duration_min"), errors="coerce")
    parts = [date_label, str(row.get("name") or "Activiteit")]
    if not pd.isna(distance):
        parts.append(f"{distance:.2f} km")
    if not pd.isna(duration):
        parts.append(format_duration(duration))
    if pd.notna(row.get("avg_hr")):
        parts.append(f"{float(row['avg_hr']):.0f} bpm")
    if pd.notna(row.get("training_load")):
        parts.append(f"load {float(row['training_load']):.1f}")
    return " | ".join(parts)


def _render_peer_selection(selected: pd.Series, peers: pd.DataFrame) -> None:
    st.markdown("#### Selecteer één activiteit om mee te vergelijken")
    st.caption("De geopende activiteit wordt automatisch meegenomen. De vergelijking opent in een aparte tab.")
    for _, peer in peers.iterrows():
        peer_id = str(peer.get("id"))
        if st.button(
            _peer_label(peer),
            key=f"compare_peer_{selected.get('id')}_{peer_id}",
            use_container_width=True,
        ):
            st.session_state.activity_comparison_ids = [str(selected.get("id")), peer_id]
            st.session_state.comparison_active = True
            st.session_state.comparison_answer = ""
            st.session_state.comparison_messages = []
            st.session_state.activity_view = "browser"
            st.rerun()


def similar_activities(df: pd.DataFrame, selected: pd.Series) -> pd.DataFrame:
    return find_similar_activities(df, selected, max_results=20)


def _first_column(frame: pd.DataFrame, names) -> str | None:
    lower = {str(col).lower(): col for col in frame.columns}
    for name in names:
        if name in lower:
            return lower[name]
    return None


def _load_stream_frame(activity_id: str) -> pd.DataFrame:
    """Haal de stream-CSV op als DataFrame (lokaal of hersteld uit Firestore)."""
    if not activity_id:
        return pd.DataFrame()
    # Zorg dat er lokaal een bestand is (herstel eventueel uit Firestore).
    if ensure_local_stream is not None:
        try:
            path = ensure_local_stream(activity_id)
            if path is not None:
                return pd.read_csv(path)
        except Exception:  # noqa: BLE001
            pass
    # Anders rechtstreeks uit de persistente laag lezen.
    if load_stream_csv is not None:
        try:
            import io

            csv_text = load_stream_csv(activity_id)
            if csv_text:
                return pd.read_csv(io.StringIO(csv_text))
        except Exception:  # noqa: BLE001
            pass
    return pd.DataFrame()


def _x_axis(frame: pd.DataFrame):
    time_col = _first_column(frame, STREAM_TIME_COLUMNS)
    if time_col is not None:
        minutes = pd.to_numeric(frame[time_col], errors="coerce") / 60.0
        return minutes, "Tijd (min)"
    dist_col = _first_column(frame, STREAM_DISTANCE_COLUMNS)
    if dist_col is not None:
        values = pd.to_numeric(frame[dist_col], errors="coerce")
        if dist_col.lower() == "distance_m" or values.max() and values.max() > 1000:
            values = values / 1000.0
        return values, "Afstand (km)"
    return pd.Series(range(len(frame))), "Meetpunt"


def _render_stream_charts(frame: pd.DataFrame) -> None:
    x_values, x_title = _x_axis(frame)
    plotted = 0
    for _, columns, label, color in STREAM_SERIES:
        col = _first_column(frame, columns)
        if col is None:
            continue
        y_values = pd.to_numeric(frame[col], errors="coerce")
        if y_values.notna().sum() < 3:
            continue
        fig = go.Figure(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                line=dict(width=2, color=color),
                name=label,
                connectgaps=True,
            )
        )
        fig.update_layout(
            title=dict(text=label, x=0.01, xanchor="left"),
            xaxis_title=x_title,
            margin=dict(l=8, r=8, t=36, b=8),
            height=260,
        )
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
        plotted += 1
    if plotted == 0:
        st.info("Geen bruikbare stream-metingen gevonden voor deze activiteit.")


def _render_map(frame: pd.DataFrame) -> bool:
    lat_col = _first_column(frame, STREAM_LAT_COLUMNS)
    lon_col = _first_column(frame, STREAM_LON_COLUMNS)
    if lat_col is None or lon_col is None:
        return False
    coords = pd.DataFrame({
        "lat": pd.to_numeric(frame[lat_col], errors="coerce"),
        "lon": pd.to_numeric(frame[lon_col], errors="coerce"),
    }).dropna()
    coords = coords[(coords["lat"].between(-90, 90)) & (coords["lon"].between(-180, 180))]
    if coords.empty:
        return False
    st.map(coords, latitude="lat", longitude="lon")
    return True


def render_activity_detail(selected: pd.Series, all_activities: pd.DataFrame) -> None:
    st.markdown(f"## {selected['name']} | {selected['date'].strftime('%d/%m/%Y')}")
    st.caption(f"{selected['sport']} | {selected.get('device') or 'Onbekend apparaat'}")

    primary = [
        ("distance_km", "Afstand", " km", 2),
        ("duration_min", "Duur", "", 0),
        ("training_load", "Load", "", 1),
        ("avg_hr", "Gem. hartslag", " bpm", 0),
        ("max_hr", "Max. hartslag", " bpm", 0),
        ("elevation_gain", "Hoogtemeters", " m", 0),
        ("fitness", "Fitness", "", 1),
        ("fatigue", "Fatigue", "", 1),
        ("form", "Form", "", 1),
        ("intensity", "Intensiteit", "", 1),
        ("calories", "Calorieën", " kcal", 0),
        ("trimp", "TRIMP", "", 1),
    ]
    visible = [item for item in primary if pd.notna(selected.get(item[0]))]
    for start in range(0, len(visible), 4):
        group = visible[start : start + 4]
        columns = st.columns(len(group))
        for column, (field, label, suffix, digits) in zip(columns, group):
            value = selected.get(field)
            formatted = format_duration(value) if field == "duration_min" else display_value(value, suffix, digits)
            column.metric(label, formatted)

    if is_running_sport(selected["sport"]):
        st.metric("Gemiddeld tempo", format_pace(selected.get("distance_km"), selected.get("duration_min")))

    stream_frame = _load_stream_frame(str(selected.get("id") or ""))

    detail_tabs = st.tabs([
        "Overzicht",
        "Grafieken",
        "Kaart",
        "Hartslagzones",
        "Vergelijkbare activiteiten",
    ])

    with detail_tabs[0]:
        details = []
        for field, label, suffix in [
            ("cadence", "Gemiddelde cadans", " spm"),
            ("decoupling", "Decoupling", "%"),
            ("temperature", "Temperatuur", " °C"),
            ("elevation_loss", "Daling", " m"),
            ("resting_hr", "Rusthartslag", " bpm"),
            ("source", "Bron", ""),
        ]:
            value = selected.get(field)
            if value is not None and not (isinstance(value, float) and pd.isna(value)):
                if isinstance(value, (int, float)):
                    value = display_value(value, suffix)
                details.append({"Onderdeel": label, "Waarde": value})
        if selected.get("description"):
            st.write(selected["description"])
        if selected.get("interval_summary"):
            st.markdown("**Intervals**")
            for summary in selected["interval_summary"]:
                st.write(f"- {summary}")
        if details:
            st.dataframe(pd.DataFrame(details), use_container_width=True, hide_index=True)

    with detail_tabs[1]:
        if stream_frame.empty:
            st.info("Geen streamdata beschikbaar voor deze activiteit.")
        else:
            _render_stream_charts(stream_frame)

    with detail_tabs[2]:
        if stream_frame.empty or not _render_map(stream_frame):
            st.info("Geen GPS-gegevens beschikbaar om een kaart te tonen.")

    with detail_tabs[3]:
        zone_times = selected.get("hr_zone_times")
        zones = selected.get("hr_zones")
        if not isinstance(zone_times, list) or not zone_times:
            st.info("Geen hartslagzonegegevens beschikbaar voor deze activiteit.")
        else:
            total = sum(value for value in zone_times if isinstance(value, (int, float)))
            rows = []
            for index, seconds in enumerate(zone_times, start=1):
                lower = zones[index - 1] if isinstance(zones, list) and index - 1 < len(zones) else None
                rows.append({
                    "Zone": f"Z{index}",
                    "Ondergrens": lower,
                    "Tijd": format_duration(seconds / 60),
                    "Aandeel (%)": round(seconds / total * 100, 1) if total else None,
                })
            zone_df = pd.DataFrame(rows)
            st.dataframe(zone_df, use_container_width=True, hide_index=True)
            fig = go.Figure(go.Bar(
                x=zone_df["Zone"], y=zone_df["Aandeel (%)"],
                text=zone_df["Aandeel (%)"], texttemplate="%{text:.1f}%",
            ))
            fig.update_layout(title="Tijd per hartslagzone", yaxis_title="Aandeel (%)", margin=dict(l=8, r=8, t=42, b=8))
            st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)

    with detail_tabs[4]:
        peers = similar_activities(all_activities, selected)
        if peers.empty:
            st.info("Geen voldoende gelijkaardige activiteiten gevonden.")
        else:
            _render_peer_selection(selected, peers)
