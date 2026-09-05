# -*- coding: utf-8 -*-

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from AICoach.dashboard.ui_helpers import FIELD_LABELS, has_data


PLOT_CONFIG = {
    "displaylogo": False,
    "displayModeBar": False,
    "scrollZoom": True,
    "doubleClick": "reset",
    "responsive": True,
}

# Weergavekeuze per grafiek. None = ruwe dagdata, anders een pandas-resampleregel.
GRANULARITY_RULES = {
    "Dag": None,
    "Week": "W-MON",
    "Maand": "MS",
}

# Velden die bij aggregatie opgeteld worden (belasting), niet gemiddeld.
AGG_SUM_FIELDS = {"training_load"}

# Form-zones volgens Intervals.icu (TSB = Fitness - Fatigue).
FORM_ZONES = [
    {"name": "Hoog risico", "y0": -1000.0, "y1": -30.0, "band": "rgba(214,39,40,0.13)", "solid": "#d62728"},
    {"name": "Optimaal", "y0": -30.0, "y1": -10.0, "band": "rgba(44,160,44,0.16)", "solid": "#2ca02c"},
    {"name": "Grijze zone", "y0": -10.0, "y1": 5.0, "band": "rgba(128,128,128,0.14)", "solid": "#7f7f7f"},
    {"name": "Fris", "y0": 5.0, "y1": 20.0, "band": "rgba(31,119,180,0.14)", "solid": "#1f77b4"},
    {"name": "Overgang", "y0": 20.0, "y1": 1000.0, "band": "rgba(230,167,0,0.16)", "solid": "#e6a700"},
]


def form_zone_for(value):
    """Geeft (naam, kleur) voor een form-waarde, of (None, None) bij ontbrekende waarde."""
    if value is None or pd.isna(value):
        return None, None
    number = float(value)
    for zone in FORM_ZONES:
        if zone["y0"] <= number < zone["y1"]:
            return zone["name"], zone["solid"]
    return None, None


def selected_date_from_event(event):
    if event is None:
        return None
    try:
        points = event.selection.points
    except AttributeError:
        try:
            points = event.get("selection", {}).get("points", [])
        except AttributeError:
            points = []
    if not points:
        return None
    point = points[0]
    x_value = point.get("x") if isinstance(point, dict) else getattr(point, "x", None)
    parsed = pd.to_datetime(x_value, errors="coerce")
    return None if pd.isna(parsed) else parsed.normalize()


def _data_date_range(df, fields):
    """Eerste en laatste datum met echte data, zodat de x-as daar begint/eindigt."""
    present = [field for field in fields if field in df.columns]
    if not present or "date" not in df.columns:
        return None, None
    mask = df[present].notna().any(axis=1)
    dated = pd.to_datetime(df.loc[mask, "date"], errors="coerce").dropna()
    if dated.empty:
        return None, None
    return dated.min(), dated.max()


def aggregate_frame(df, fields, rule):
    """Aggregeer per week/maand.

    - training_load wordt opgeteld (periodetotaal), andere velden gemiddeld.
    - De x-waarde is de LAATSTE datum met data binnen de periode, zodat de
      huidige (onvolledige) maand tot en met vandaag meeloopt.
    """
    present = [field for field in fields if field in df.columns]
    if rule is None or df.empty or not present:
        return df

    frame = df[["date"] + present].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).set_index("date")
    if frame.empty:
        return frame.reset_index()

    aggregation = {
        field: ("sum" if field in AGG_SUM_FIELDS else "mean")
        for field in present
    }
    resampled = frame.resample(rule).agg(aggregation)
    last_dates = frame.resample(rule).apply(lambda block: block.dropna(how="all").index.max())
    if isinstance(last_dates, pd.DataFrame):
        last_dates = last_dates.iloc[:, 0]
    resampled["date"] = last_dates.values
    resampled = resampled.dropna(subset=["date"]).reset_index(drop=True)
    return resampled


def _add_form_zones(fig, y_min, y_max):
    low = min(y_min, -35.0)
    high = max(y_max, 25.0)
    for zone in FORM_ZONES:
        y0 = max(zone["y0"], low)
        y1 = min(zone["y1"], high)
        if y1 <= y0:
            continue
        fig.add_hrect(
            y0=y0,
            y1=y1,
            line_width=0,
            fillcolor=zone["band"],
            layer="below",
            annotation_text=zone["name"],
            annotation_position="right",
            annotation=dict(font_size=10, font_color="#666"),
        )


def configure_time_chart(fig, selected_date=None, x_start=None, x_end=None):
    fig.update_layout(
        hovermode="x unified",
        dragmode="pan",
        legend_title_text="",
        margin=dict(l=8, r=8, t=42, b=8),
        uirevision="keep-time-window",
    )
    fig.update_yaxes(fixedrange=True, autorange=True)
    if x_start is not None and x_end is not None:
        pad = pd.Timedelta(days=1)
        fig.update_xaxes(fixedrange=False, range=[x_start - pad, x_end + pad])
    else:
        fig.update_xaxes(fixedrange=False)

    if selected_date is not None:
        fig.add_vline(
            x=selected_date,
            line_width=1,
            line_dash="solid",
            line_color="#d62728",
        )
    return fig


def render_time_chart(
    df,
    fields,
    key,
    selected_date=None,
    title=None,
    allow_granularity=True,
    default_granularity="Dag",
    show_form_zones=False,
):
    available = [field for field in fields if has_data(df, field)]
    if not available:
        return None

    plot_df = df
    aggregated = False
    rule = None

    if allow_granularity:
        options = list(GRANULARITY_RULES.keys())
        default_index = options.index(default_granularity) if default_granularity in options else 0
        choice = st.radio(
            "Weergave",
            options,
            index=default_index,
            horizontal=True,
            key=f"{key}_granularity",
            label_visibility="collapsed",
        )
        rule = GRANULARITY_RULES.get(choice)
        if rule is not None:
            plot_df = aggregate_frame(df, available, rule)
            aggregated = True
            selected_date = None  # dagselectie is zinloos op geaggregeerde data

    if plot_df is None or plot_df.empty:
        return None

    # Maandweergave van belasting: bar chart met periodetotaal.
    monthly_load = rule == "MS" and available == ["training_load"]

    fig = go.Figure()
    if monthly_load:
        fig.add_trace(
            go.Bar(
                x=plot_df["date"],
                y=plot_df["training_load"],
                name="Training load (maandtotaal)",
                marker_color="#1f77b4",
                hovertemplate="%{x|%m/%Y}<br>Totaal load: %{y:.0f}<extra></extra>",
            )
        )
    else:
        for field in available:
            if field not in plot_df.columns:
                continue
            fig.add_trace(
                go.Scatter(
                    x=plot_df["date"],
                    y=plot_df[field],
                    mode="lines+markers",
                    connectgaps=True,
                    name=FIELD_LABELS.get(field, field),
                    marker=dict(size=4),
                    line=dict(width=2, shape="linear"),
                    hovertemplate=(
                        "%{x|%d/%m/%Y}<br>"
                        + FIELD_LABELS.get(field, field)
                        + ": %{y:.2f}<extra></extra>"
                    ),
                )
            )

    if show_form_zones and "form" in plot_df.columns:
        values = pd.to_numeric(plot_df["form"], errors="coerce").dropna()
        if not values.empty:
            _add_form_zones(fig, float(values.min()), float(values.max()))

    if title:
        fig.update_layout(title=dict(text=title, x=0.01, xanchor="left"))

    x_start, x_end = _data_date_range(plot_df, available)
    fig = configure_time_chart(fig, selected_date, x_start, x_end)

    # Selectie via klikken alleen zinvol op ruwe dagdata.
    if aggregated:
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG, key=key)
        return None

    try:
        return st.plotly_chart(
            fig,
            use_container_width=True,
            config=PLOT_CONFIG,
            key=key,
            on_select="rerun",
            selection_mode="points",
        )
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG, key=key)
        return None
