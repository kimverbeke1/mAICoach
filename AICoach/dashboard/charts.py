# -*- coding: utf-8 -*-
# charts.py
"""Tijdsgrafieken voor mAICoach.

--------------------------------------------------------------------------
MATCHFITAI_CHARTS_ECHARTS_2026-10-16 (op verzoek van Kim: "pinch is beter")
--------------------------------------------------------------------------
Plotly.js ondersteunt geen pinch-to-zoom op touchscreens (enkel slepen). De
tijdsgrafieken en de streamgrafieken van activiteiten worden daarom nu met
Apache ECharts getekend, dat pinch wel native ondersteunt:
  - 2 vingers knijpen  = in- en uitzoomen (enkel de x-as).
  - 1 vinger slepen    = verschuiven.
  - muiswiel (PC)      = zoomen.
ECharts wordt via een CDN geladen in een st.components.v1.html-blok; er is
GEEN extra Python-pakket nodig.

Wat hetzelfde blijft: Dag/Week/Maand-keuze, training load als bars die in
het midden van hun periode staan (weken ma-zo), fitness-trendlijn met
helling per week, Form-zones (> 5 Fris, -10..5 Grijze zone, -30..-10
Optimaal, < -30 Hoog risico), rode lijn op de geselecteerde dag.

Wat wegvalt: een dag selecteren door op de grafiek te tikken. Een HTML-
component kan geen klik terugsturen naar Streamlit; render_time_chart()
geeft daarom altijd None terug (training_dashboard.py vangt dat al op).

De hartslagzone-grafiek en eventuele andere Plotly-grafieken blijven via
show_plotly() werken (statisch).
"""
import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from AICoach.dashboard.ui_helpers import FIELD_LABELS, has_data

# Standaard: statisch -> de pagina scrollt normaal op mobiel.
PLOT_CONFIG = {
    "displaylogo": False,
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,
    "responsive": True,
}

# Met de schakelaar "Zoom" aan: pannen + betrouwbare zoomknoppen.
PLOT_CONFIG_INTERACTIVE = {
    "displaylogo": False,
    "displayModeBar": False,
    "scrollZoom": True,
    "doubleClick": "reset",
    "responsive": True,
    "modeBarButtonsToRemove": [
        "select2d",
        "lasso2d",
        "toImage",
        "autoScale2d",
        "hoverClosestCartesian",
        "hoverCompareCartesian",
        "toggleSpikelines",
    ],
}

# Weergavekeuze per grafiek. None = ruwe dagdata, "W" = week (ma-zo), "M" = maand.
GRANULARITY_RULES = {
    "Dag": None,
    "Week": "W",
    "Maand": "M",
}

# Velden die bij aggregatie opgeteld worden (belasting), niet gemiddeld.
AGG_SUM_FIELDS = {"training_load"}

LOAD_COLOR = "#1f77b4"
TREND_COLOR = "#444444"

# Form-zones (Form = Fitness - Fatigue), grenzen volgens Kim.
FORM_ZONES = [
    {"name": "Hoog risico", "y0": -1000.0, "y1": -30.0, "band": "rgba(214,39,40,0.13)", "solid": "#d62728"},
    {"name": "Optimaal", "y0": -30.0, "y1": -10.0, "band": "rgba(44,160,44,0.16)", "solid": "#2ca02c"},
    {"name": "Grijze zone", "y0": -10.0, "y1": 5.0, "band": "rgba(128,128,128,0.14)", "solid": "#7f7f7f"},
    {"name": "Fris", "y0": 5.0, "y1": 1000.0, "band": "rgba(31,119,180,0.14)", "solid": "#1f77b4"},
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


def _period_code(rule):
    """Vertaalt zowel de nieuwe ("W"/"M") als de oude ("W-MON"/"MS") regels."""
    if rule in ("W", "W-MON", "W-SUN"):
        return "W"
    if rule in ("M", "MS"):
        return "M"
    return None


def _period_start(dates, code):
    # "W-SUN" = periodes van maandag t.e.m. zondag.
    return dates.dt.to_period("W-SUN" if code == "W" else "M").dt.start_time


def aggregate_frame(df, fields, rule):
    """Aggregeer per week (ma-zo) of maand.

    - training_load wordt opgeteld (periodetotaal), andere velden gemiddeld.
    - "date" is de LAATSTE datum met data binnen de periode (voor lijnen, zodat
      de lopende periode tot en met vandaag meeloopt).
    - "period_start"/"period_end" geven de echte periodegrenzen (voor bars).
    """
    present = [field for field in fields if field in df.columns]
    code = _period_code(rule)
    if code is None or df.empty or not present:
        return df
    frame = df[["date"] + present].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    for field in present:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    frame = frame.dropna(subset=present, how="all")
    if frame.empty:
        return frame
    frame["period_start"] = _period_start(frame["date"], code)
    aggregation = {
        field: ("sum" if field in AGG_SUM_FIELDS else "mean")
        for field in present
    }
    aggregation["date"] = "max"
    result = frame.groupby("period_start", as_index=False).agg(aggregation)
    step = pd.DateOffset(weeks=1) if code == "W" else pd.DateOffset(months=1)
    result["period_end"] = result["period_start"] + step
    return result.sort_values("period_start").reset_index(drop=True)


def _load_bar_trace(plot_df, code):
    """Training load als bars, gecentreerd in hun periode met vaste breedte."""
    frame = plot_df.copy()
    frame["training_load"] = pd.to_numeric(frame["training_load"], errors="coerce")
    frame = frame.dropna(subset=["training_load"])
    if frame.empty:
        return None, None, None
    if code is None:
        starts = pd.to_datetime(frame["date"]).dt.normalize()
        ends = starts + pd.Timedelta(days=1)
        labels = starts.dt.strftime("%d/%m/%Y")
        name = "Training load (per dag)"
    else:
        starts = pd.to_datetime(frame["period_start"])
        ends = pd.to_datetime(frame["period_end"])
        if code == "W":
            labels = "Week van " + starts.dt.strftime("%d/%m/%Y")
            name = "Training load (weektotaal)"
        else:
            labels = starts.dt.strftime("%m/%Y")
            name = "Training load (maandtotaal)"
    spans = ends - starts
    middles = starts + spans / 2
    widths = (spans.dt.total_seconds() * 1000 * 0.8).tolist()
    trace = go.Bar(
        x=middles,
        y=frame["training_load"],
        width=widths,
        name=name,
        marker_color=LOAD_COLOR,
        customdata=labels,
        hovertemplate="%{customdata}<br>Load: %{y:.0f}<extra></extra>",
    )
    return trace, starts.min(), ends.max()


def _trend_trace(plot_df, field):
    """Lineaire trendlijn over de getoonde periode, helling per week in de naam."""
    if field not in plot_df.columns:
        return None
    series = plot_df[["date", field]].copy()
    series["date"] = pd.to_datetime(series["date"], errors="coerce")
    series[field] = pd.to_numeric(series[field], errors="coerce")
    series = series.dropna()
    if len(series) < 3:
        return None
    days = (series["date"] - series["date"].min()).dt.total_seconds() / 86400.0
    if days.max() <= 0:
        return None
    slope, intercept = np.polyfit(days.to_numpy(), series[field].to_numpy(), 1)
    per_week = f"{slope * 7:+.1f}".replace(".", ",")
    label = FIELD_LABELS.get(field, field)
    return go.Scatter(
        x=[series["date"].min(), series["date"].max()],
        y=[intercept, intercept + slope * days.max()],
        mode="lines",
        name=f"Trend {label} ({per_week} per week)",
        line=dict(width=2, dash="dash", color=TREND_COLOR),
        hoverinfo="skip",
    )


def _add_form_zones(fig, y_min, y_max):
    low = min(y_min - 3.0, -35.0)
    high = max(y_max + 3.0, 15.0)
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
            annotation_position="top left",
            annotation=dict(font_size=10, font_color="#555"),
        )
    fig.update_yaxes(range=[low, high], autorange=False)


def configure_time_chart(
    fig,
    selected_date=None,
    x_start=None,
    x_end=None,
    interactive=False,
    pad_days=1,
    uirevision="keep-time-window",
):
    fig.update_layout(
        hovermode="x unified",
        dragmode="pan" if interactive else False,
        legend=dict(orientation="h", yanchor="top", y=-0.32, xanchor="left", x=0, title_text=""),
        margin=dict(l=8, r=8, t=42, b=8),
        uirevision=uirevision,
    )
    fig.update_yaxes(fixedrange=True)
    fig.update_xaxes(fixedrange=not interactive)
    if x_start is not None and x_end is not None:
        pad = pd.Timedelta(days=pad_days)
        fig.update_xaxes(range=[x_start - pad, x_end + pad])
    if selected_date is not None:
        fig.add_vline(
            x=selected_date,
            line_width=1,
            line_dash="solid",
            line_color="#d62728",
        )
    return fig


def _add_rangeslider(fig):
    """MATCHFITAI_CHARTS_RANGESLIDER_2026-10-16: zoomen op mobiel via de
    randen van het venster in de slider (Plotly kent geen pinch-zoom)."""
    fig.update_xaxes(
        rangeslider=dict(
            visible=True,
            thickness=0.12,
            bgcolor="rgba(128,128,128,0.08)",
            bordercolor="rgba(128,128,128,0.35)",
            borderwidth=1,
        )
    )


def zoom_switch(key, label="Zoom"):
    """De "Zoom"-schakelaar. Uit (standaard): statisch, de pagina scrollt
    normaal op mobiel. Aan: pannen met 1 vinger plus zoomknoppen."""
    switch = getattr(st, "toggle", None) or st.checkbox
    return switch(
        label,
        value=False,
        key=f"{key}_interactive",
        help="Aan: pannen en zoomknoppen. Uit: de pagina scrollt normaal op mobiel.",
    )


# Oude interne naam, blijft werken.
_zoom_switch = zoom_switch


def show_plotly(fig, key=None, interactive=False):
    """MATCHFITAI_CHARTS_MOBILE_SHARED_2026-10-16: tekent een willekeurige
    Plotly-figuur met mobielvriendelijk gedrag.

    interactive=False: geen pan/zoom (dragmode=False, vaste assen) -> de
    pagina scrollt gewoon, tikken toont nog steeds de waarden.
    interactive=True: x-as pannen met 1 vinger + zoomknoppen; de y-as blijft
    vast zodat een verticale veeg niet per ongeluk de schaal verandert.
    """
    fig.update_layout(dragmode="pan" if interactive else False)
    fig.update_yaxes(fixedrange=True)
    fig.update_xaxes(fixedrange=not interactive)
    config = PLOT_CONFIG_INTERACTIVE if interactive else PLOT_CONFIG
    st.plotly_chart(fig, use_container_width=True, config=config, key=key)



# --------------------------------------------------------------------------- #
# ECharts (MATCHFITAI_CHARTS_ECHARTS_2026-10-16)
# --------------------------------------------------------------------------- #
ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"


def _clean(value):
    """NaN/inf -> None, numpy -> python, zodat json.dumps lukt."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return round(number, 2) if math.isfinite(number) else None


def _iso(value):
    stamp = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(stamp) else stamp.strftime("%Y-%m-%dT%H:%M:%S")


def render_echart(option, height=380):
    """Tekent een ECharts-optie met pinch-zoom/slepen langs de x-as."""
    from streamlit.components.v1 import html as components_html

    option = dict(option)
    option.setdefault("animation", False)
    option.setdefault("backgroundColor", "transparent")
    option.setdefault("tooltip", {"trigger": "axis", "confine": True})
    option.setdefault("grid", {"left": 44, "right": 14, "top": 40, "bottom": 58})
    option["dataZoom"] = [{
        "type": "inside",
        "xAxisIndex": 0,
        "filterMode": "none",
        "zoomOnMouseWheel": True,
        "moveOnMouseMove": True,
        "moveOnMouseWheel": False,
        "preventDefaultMouseMove": True,
    }]
    payload = json.dumps(option, ensure_ascii=False, allow_nan=False)
    components_html(
        f"""
<div id="chart" style="width:100%;height:{height}px;touch-action:none;"></div>
<script src="{ECHARTS_CDN}"></script>
<script>
  var chart = echarts.init(document.getElementById("chart"), null, {{renderer: "canvas"}});
  chart.setOption({payload});
  window.addEventListener("resize", function () {{ chart.resize(); }});
</script>
""",
        height=height + 8,
    )


def _echart_title(title):
    return {"text": title or "", "left": 4, "top": 2, "textStyle": {"fontSize": 14}}


def _echart_legend():
    return {"bottom": 0, "left": 0, "type": "scroll"}


def _mark_line(selected_date):
    iso = _iso(selected_date)
    if not iso:
        return None
    return {
        "symbol": "none",
        "silent": True,
        "label": {"show": False},
        "lineStyle": {"color": "#d62728", "width": 1, "type": "solid"},
        "data": [{"xAxis": iso}],
    }


def _form_mark_area():
    data = []
    for zone in FORM_ZONES:
        data.append([
            {"yAxis": zone["y0"], "name": zone["name"], "itemStyle": {"color": zone["band"]}},
            {"yAxis": zone["y1"]},
        ])
    return {
        "silent": True,
        "label": {"position": "insideTopLeft", "fontSize": 10, "color": "#555"},
        "data": data,
    }


def render_time_chart(
    df,
    fields,
    key,
    selected_date=None,
    title=None,
    allow_granularity=True,
    default_granularity="Dag",
    show_form_zones=False,
    trend_field=None,
):
    """Tijdsgrafiek met pinch-zoom (ECharts). Geeft altijd None terug."""
    available = [field for field in fields if has_data(df, field)]
    if not available:
        return None

    choice = default_granularity
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

    code = GRANULARITY_RULES.get(choice) if allow_granularity else None
    plot_df = df
    if code is not None:
        plot_df = aggregate_frame(df, available, code)
        selected_date = None  # dagselectie is zinloos op geaggregeerde data
    if plot_df is None or plot_df.empty:
        return None

    series = []
    y_axis = {"type": "value", "scale": True, "splitLine": {"lineStyle": {"opacity": 0.3}}}
    load_bars = available == ["training_load"]

    if load_bars:
        frame = plot_df.copy()
        frame["training_load"] = pd.to_numeric(frame["training_load"], errors="coerce")
        frame = frame.dropna(subset=["training_load"])
        if frame.empty:
            return None
        if code is None:
            starts = pd.to_datetime(frame["date"]).dt.normalize()
            ends = starts + pd.Timedelta(days=1)
            name = "Training load (per dag)"
        else:
            starts = pd.to_datetime(frame["period_start"])
            ends = pd.to_datetime(frame["period_end"])
            name = "Training load (weektotaal)" if code == "W" else "Training load (maandtotaal)"
        middles = starts + (ends - starts) / 2
        series.append({
            "name": name,
            "type": "bar",
            "barWidth": "80%" if code is not None else "60%",
            "itemStyle": {"color": LOAD_COLOR},
            "data": [[_iso(x), _clean(y)] for x, y in zip(middles, frame["training_load"])],
        })
        y_axis = {"type": "value", "min": 0, "splitLine": {"lineStyle": {"opacity": 0.3}}}
    else:
        for field in available:
            if field not in plot_df.columns:
                continue
            values = pd.to_numeric(plot_df[field], errors="coerce")
            series.append({
                "name": FIELD_LABELS.get(field, field),
                "type": "line",
                "showSymbol": False,
                "connectNulls": True,
                "lineStyle": {"width": 2},
                "data": [[_iso(x), _clean(y)] for x, y in zip(plot_df["date"], values)],
            })
        if trend_field and trend_field in available:
            trend = _trend_trace(plot_df, trend_field)
            if trend is not None:
                series.append({
                    "name": trend.name,
                    "type": "line",
                    "showSymbol": False,
                    "silent": True,
                    "lineStyle": {"width": 2, "type": "dashed", "color": TREND_COLOR},
                    "itemStyle": {"color": TREND_COLOR},
                    "tooltip": {"show": False},
                    "data": [[_iso(x), _clean(y)] for x, y in zip(trend.x, trend.y)],
                })

    if not series:
        return None

    mark_line = _mark_line(selected_date)
    if mark_line:
        series[0]["markLine"] = mark_line

    if show_form_zones and "form" in plot_df.columns:
        values = pd.to_numeric(plot_df["form"], errors="coerce").dropna()
        if not values.empty:
            low = min(float(values.min()) - 3.0, -35.0)
            high = max(float(values.max()) + 3.0, 15.0)
            y_axis.update({"scale": False, "min": math.floor(low), "max": math.ceil(high)})
            series[0]["markArea"] = _form_mark_area()

    option = {
        "title": _echart_title(title),
        "legend": _echart_legend(),
        "xAxis": {"type": "time", "splitLine": {"show": False}},
        "yAxis": y_axis,
        "series": series,
    }
    render_echart(option, height=380)
    return None


def render_stream_echart(x_values, y_values, label, color, x_title, height=260):
    """Streamgrafiek van een activiteit (hartslag, tempo, ...) met pinch-zoom."""
    data = [[_clean(x), _clean(y)] for x, y in zip(x_values, y_values)]
    data = [point for point in data if point[0] is not None]
    option = {
        "title": _echart_title(label),
        "grid": {"left": 44, "right": 14, "top": 36, "bottom": 36},
        "xAxis": {"type": "value", "name": x_title, "nameLocation": "middle", "nameGap": 24,
                  "min": "dataMin", "max": "dataMax"},
        "yAxis": {"type": "value", "scale": True, "splitLine": {"lineStyle": {"opacity": 0.3}}},
        "series": [{
            "name": label,
            "type": "line",
            "showSymbol": False,
            "connectNulls": True,
            "sampling": "lttb",
            "lineStyle": {"width": 2, "color": color},
            "itemStyle": {"color": color},
            "data": data,
        }],
    }
    render_echart(option, height=height)
