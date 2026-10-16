# -*- coding: utf-8 -*-
# charts.py
"""Tijdsgrafieken voor mAICoach.

--------------------------------------------------------------------------
MATCHFITAI_CHARTS_MOBILE_2026-10-16 (op verzoek van Kim: "zoom in/out /
pinching werkt niet goed op mobiel", "training load toont rare positionering
van de bars", "trendlijn voor fitness" en "zones voor form")
--------------------------------------------------------------------------
1. MOBIEL ZOOMEN
   ROOT CAUSE: elke grafiek stond standaard op dragmode="pan" + scrollZoom.
   Op een touchscreen vangt Plotly daardoor elke veeg op: de pagina scrollt
   niet meer zodra je vinger op een grafiek staat, en pinch-zoom van Plotly
   zelf is op mobiel onbetrouwbaar.
   FIX: grafieken zijn standaard STATISCH (geen pan/zoom, pagina scrollt
   gewoon, tikken toont nog steeds waarden en selecteert een dag). Per
   grafiek staat een schakelaar "Zoom": aan = pannen met 1 vinger plus
   knoppen voor inzoomen / uitzoomen / reset (die werken wel betrouwbaar op
   mobiel). De periode kies je zoals voorheen via "Periode" op het dashboard.
   Daarnaast hing uirevision vast op 1 constante waarde, waardoor een
   eerder ingezoomd venster bleef "plakken" na het wisselen van Dag/Week/
   Maand of periode. uirevision hangt nu af van grafiek + weergave + bereik.

2. TRAINING LOAD-BARS
   ROOT CAUSE: bij Week/Maand kreeg elke bar als x-positie de LAATSTE datum
   met data in die periode (bv. de 27e, of vandaag in de lopende maand).
   De bars stonden daardoor onregelmatig verschoven en hadden wisselende
   breedtes. Bovendien betekende "W-MON" in pandas weken die op MAANDAG
   EINDIGEN (dinsdag t.e.m. maandag) i.p.v. maandag t.e.m. zondag.
   FIX: training load wordt nu altijd als bars getoond (ook per dag en per
   week), gecentreerd in het midden van hun periode en met een vaste
   breedte van 80% van die periode. Weken lopen maandag t.e.m. zondag.

3. FITNESS-TRENDLIJN en FORM-ZONES
   - trend_field="fitness": voegt een gestippelde lineaire trendlijn toe
     over de getoonde periode, met de helling per week in de legende.
   - show_form_zones=True: kleurbanden volgens Kim:
       > 5          Fris
       -10 tot 5    Grijze zone
       -30 tot -10  Optimaal
       < -30        Hoog risico
     De y-as toont altijd minstens -35 tot +15, zodat de zones zichtbaar zijn.

--------------------------------------------------------------------------
MATCHFITAI_CHARTS_MOBILE_SHARED_2026-10-16 (op verzoek van Kim: dezelfde
mobiele zoomproblemen in de activiteitsdetails)
--------------------------------------------------------------------------
ROOT CAUSE: activity_detail.py bouwt eigen grafieken en gaf enkel
PLOT_CONFIG mee. Een Plotly-figuur zonder expliciete dragmode staat
standaard op "zoom" (box-zoom): op een touchscreen start elke veeg dan een
zoomkader i.p.v. de pagina te laten scrollen.
FIX: twee gedeelde, publieke helpers voor ELKE grafiek die niet via
render_time_chart() loopt:
  - zoom_switch(key): de "Zoom"-schakelaar (zelfde gedrag als hierboven).
  - show_plotly(fig, key, interactive): zet dragmode/fixedrange correct
    (statisch, of pannen + zoomknoppen) en tekent de grafiek.

--------------------------------------------------------------------------
MATCHFITAI_CHARTS_TOUCH_2026-10-16 (op verzoek van Kim: "ik wil geen
zoom-schakelaar, ik wil gewoon de grafiek met mijn vingers verschuiven en
inzoomen")
--------------------------------------------------------------------------
De "Zoom"-schakelaar is verwijderd. Elke grafiek is nu standaard
interactief:
  - 1 vinger slepen  = grafiek horizontaal verschuiven (pan).
  - 2 vingers knijpen / scrollwiel = in- en uitzoomen.
  - dubbeltikken     = terug naar het volledige beeld.
Enkel de x-as (tijd/afstand) zoomt en schuift; de y-as past zich niet aan
een veeg aan, zodat een schuine veeg niet per ongeluk de schaal verandert.
Gevolg: wie met de vinger OP een grafiek veegt, verschuift de grafiek i.p.v.
de pagina - scrol de pagina door naast of tussen de grafieken te vegen.
"""
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
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0, title_text=""),
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


def show_plotly(fig, key=None, interactive=True):
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
    # MATCHFITAI_CHARTS_TOUCH_2026-10-16: altijd verschuiven/zoomen met de
    # vingers, geen schakelaar meer.
    interactive = True

    code = GRANULARITY_RULES.get(choice) if allow_granularity else None
    plot_df = df
    aggregated = False
    if code is not None:
        plot_df = aggregate_frame(df, available, code)
        aggregated = True
        selected_date = None  # dagselectie is zinloos op geaggregeerde data
    if plot_df is None or plot_df.empty:
        return None

    fig = go.Figure()
    load_bars = available == ["training_load"]
    if load_bars:
        trace, x_start, x_end = _load_bar_trace(plot_df, code)
        if trace is None:
            return None
        fig.add_trace(trace)
        pad_days = 0
        vline_date = selected_date + pd.Timedelta(hours=12) if selected_date is not None else None
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
        if trend_field and trend_field in available:
            trend = _trend_trace(plot_df, trend_field)
            if trend is not None:
                fig.add_trace(trend)
        x_start, x_end = _data_date_range(plot_df, available)
        pad_days = 1
        vline_date = selected_date

    if show_form_zones and "form" in plot_df.columns:
        values = pd.to_numeric(plot_df["form"], errors="coerce").dropna()
        if not values.empty:
            _add_form_zones(fig, float(values.min()), float(values.max()))

    if title:
        fig.update_layout(title=dict(text=title, x=0.01, xanchor="left"))

    fig = configure_time_chart(
        fig,
        vline_date,
        x_start,
        x_end,
        interactive=interactive,
        pad_days=pad_days,
        uirevision=f"{key}|{choice}|{x_start}|{x_end}",
    )
    if load_bars:
        fig.update_layout(hovermode="closest", bargap=0)
    fig.update_layout(height=380)

    config = PLOT_CONFIG_INTERACTIVE if interactive else PLOT_CONFIG

    # Selectie via tikken/klikken alleen zinvol op ruwe dagdata.
    if aggregated:
        st.plotly_chart(fig, use_container_width=True, config=config, key=key)
        return None
    try:
        return st.plotly_chart(
            fig,
            use_container_width=True,
            config=config,
            key=key,
            on_select="rerun",
            selection_mode="points",
        )
    except TypeError:
        st.plotly_chart(fig, use_container_width=True, config=config, key=key)
        return None
