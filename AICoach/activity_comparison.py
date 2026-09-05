# -*- coding: utf-8 -*-
"""Vergelijkingsmotor voor MatchFitAI-activiteiten en herstelcontext."""

from __future__ import annotations

import json
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WELLNESS_FILE = PROJECT_ROOT / "data" / "wellness" / "wellness.json"
RUN_TOKENS = ("run", "running", "trail")
WELLNESS_FIELDS = {
    "resting_hr": ("resting_hr", "restingHR", "icu_resting_hr"),
    "hrv": ("hrv", "hrvRMSSD", "hrv_rmssd"),
    "sleep_hours": ("sleep_hours", "sleepHours"),
    "sleep_secs": ("sleepSecs", "sleep_secs"),
    "sleep_score": ("sleep_score", "sleepScore"),
    "sleep_quality": ("sleep_quality", "sleepQuality"),
    "readiness": ("readiness",),
    "steps": ("steps",),
    "fitness": ("fitness", "ctl", "icu_ctl"),
    "fatigue": ("fatigue", "atl", "icu_atl"),
    "form": ("form", "tsb"),
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if record.get(name) is not None:
            return record[name]
    return None


def is_running_sport(value: Any) -> bool:
    sport = str(value or "").lower()
    return any(token in sport for token in RUN_TOKENS)


def calculate_running_efficiency(row: pd.Series) -> float | None:
    distance = _number(row.get("distance_km"))
    duration = _number(row.get("duration_min"))
    average_hr = _number(row.get("avg_hr"))
    if not distance or not duration or not average_hr:
        return None
    speed_kmh = distance / (duration / 60.0)
    return speed_kmh / average_hr


def find_similar_activities(
    activities_df: pd.DataFrame,
    selected_activity: pd.Series,
    max_results: int = 20,
) -> pd.DataFrame:
    if activities_df.empty:
        return activities_df.copy()

    sport = str(selected_activity.get("sport") or "")
    selected_id = str(selected_activity.get("id") or "")
    peers = activities_df[
        (activities_df["sport"].astype(str) == sport)
        & (activities_df["id"].astype(str) != selected_id)
    ].copy()
    if peers.empty:
        return peers

    if is_running_sport(sport):
        selected_value = _number(selected_activity.get("distance_km"))
        field = "distance_km"
        tolerance = max(1.0, selected_value * 0.15) if selected_value else None
    else:
        selected_value = _number(selected_activity.get("duration_min"))
        field = "duration_min"
        tolerance = max(15.0, selected_value * 0.20) if selected_value else None

    if selected_value is not None and tolerance is not None and field in peers.columns:
        values = pd.to_numeric(peers[field], errors="coerce")
        peers = peers[
            values.between(
                selected_value - tolerance,
                selected_value + tolerance,
                inclusive="both",
            )
        ].copy()
        peers["similarity_score"] = (
            pd.to_numeric(peers[field], errors="coerce") - selected_value
        ).abs()
    else:
        peers["similarity_score"] = 0.0

    if peers.empty:
        return peers
    return peers.sort_values(
        ["similarity_score", "date"], ascending=[True, False]
    ).head(max_results)


def load_wellness_frame() -> pd.DataFrame:
    if not WELLNESS_FILE.exists():
        return pd.DataFrame()
    try:
        payload = json.loads(WELLNESS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pd.DataFrame()

    if isinstance(payload, dict):
        payload = payload.get("wellness", payload.get("records", payload.get("data", [])))
    if not isinstance(payload, list):
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        raw_date = record.get("date") or record.get("id") or record.get("timestamp")
        day = pd.to_datetime(str(raw_date or "")[:10], errors="coerce")
        if pd.isna(day):
            continue
        row: dict[str, Any] = {"date": day.normalize()}
        for output, names in WELLNESS_FIELDS.items():
            row[output] = _number(_first(record, names))
        if row.get("sleep_hours") is None and row.get("sleep_secs") is not None:
            row["sleep_hours"] = row["sleep_secs"] / 3600.0
        if row.get("form") is None and row.get("fitness") is not None and row.get("fatigue") is not None:
            row["form"] = row["fitness"] - row["fatigue"]
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last")


def _metric_summary(window: pd.DataFrame, field: str) -> dict[str, Any] | None:
    if field not in window.columns:
        return None
    values = pd.to_numeric(window[field], errors="coerce").dropna()
    if values.empty:
        return None
    result: dict[str, Any] = {
        "average": round(float(values.mean()), 2),
        "sample_size": int(len(values)),
    }
    if len(values) >= 2:
        result["change_first_to_last"] = round(float(values.iloc[-1] - values.iloc[0]), 2)
    return result


def wellness_context(activity_date: Any, wellness: pd.DataFrame) -> dict[str, Any]:
    day = pd.to_datetime(activity_date, errors="coerce")
    if pd.isna(day) or wellness.empty:
        return {"available": False}
    day = day.normalize()

    context: dict[str, Any] = {"available": True, "activity_date": day.strftime("%Y-%m-%d")}
    for label, offset in (("same_day", 0), ("previous_day", 1)):
        target = day - timedelta(days=offset)
        match = wellness[wellness["date"] == target]
        if match.empty:
            context[label] = None
            continue
        record = match.iloc[-1]
        values = {
            field: round(float(record[field]), 2)
            for field in WELLNESS_FIELDS
            if field != "sleep_secs"
            and field in record.index
            and pd.notna(record[field])
        }
        context[label] = values or None

    for days in (7, 14):
        start = day - timedelta(days=days - 1)
        window = wellness[(wellness["date"] >= start) & (wellness["date"] <= day)]
        summaries = {
            field: summary
            for field in WELLNESS_FIELDS
            if field != "sleep_secs"
            for summary in [_metric_summary(window, field)]
            if summary is not None
        }
        context[f"last_{days}_days"] = summaries
    return context


def comparison_frame(activities: pd.DataFrame) -> pd.DataFrame:
    frame = activities.copy()
    if frame.empty:
        return frame
    frame["efficiency"] = frame.apply(
        lambda row: calculate_running_efficiency(row)
        if is_running_sport(row.get("sport"))
        else None,
        axis=1,
    )
    return frame


def build_ai_comparison_prompt(
    activities: pd.DataFrame,
    user_question: str = "",
    previous_answer: str = "",
    conversation: str = "",
) -> str:
    frame = comparison_frame(activities)
    wellness = load_wellness_frame()
    records: list[dict[str, Any]] = []

    activity_fields = (
        "id", "date", "name", "sport", "distance_km", "duration_min",
        "avg_hr", "max_hr", "training_load", "hr_load", "pace_load",
        "trimp", "intensity", "hr_zone_times", "hr_zones", "pace_zone_times",
        "elevation_gain", "fitness", "fatigue", "form", "resting_hr",
        "hrv", "sleep_hours", "sleep_score", "readiness", "efficiency",
    )
    for _, row in frame.iterrows():
        record: dict[str, Any] = {}
        for field in activity_fields:
            value = row.get(field)
            if value is None:
                continue
            if not isinstance(value, (list, dict)) and pd.isna(value):
                continue
            if isinstance(value, pd.Timestamp):
                value = value.strftime("%Y-%m-%d")
            elif hasattr(value, "item"):
                value = value.item()
            record[field] = value
        record["wellness_context"] = wellness_context(row.get("date"), wellness)
        records.append(record)

    prompt = f"""Je bent de MatchFitAI-vergelijkingscoach.

Vergelijk uitsluitend de geselecteerde activiteiten en hun beschikbare herstelcontext.

VERPLICHTE ANALYSEVOLGORDE
1. Controleer eerst dag zelf, vorige dag, laatste 7 dagen en laatste 14 dagen voor slaap, slaapscore, HRV, rusthartslag, readiness, Fitness, Fatigue en Form.
2. Controleer daarna tempo/snelheid, gemiddelde hartslag, hartslagzones, TRIMP, HR-load, pace-load, totale load en duur.
3. Gebruik hoogteverschil niet als sterke verklaring wanneer de hoogtemeting mogelijk fout is.
4. Noem looptechniek, motivatie, parcours, weer of andere externe factoren niet als verklaring zonder expliciete data.
5. Bij Running en TrailRun mag snelheid gedeeld door gemiddelde hartslag alleen als praktische efficiëntie-indicatie dienen.
6. Bij Padel en Badminton beoordeel je alleen fysiologische belasting en herstelcontext, nooit wedstrijdkwaliteit.
7. Ontbrekende waarden zijn onbekend, nooit nul.
8. Met weinig vergelijkingen spreek je uitsluitend van een voorlopige hypothese.
9. Geef maximaal 5 praktische inzichten in natuurlijk Nederlands.
10. Zet cijfers, sample sizes, datums en beperkingen onder '### Technische details'.

GESELECTEERDE ACTIVITEITEN EN HERSTELCONTEXT
{json.dumps(records, ensure_ascii=False, indent=2)}
"""
    if previous_answer:
        prompt += f"\nEERDERE ANALYSE\n{previous_answer}\n"
    if conversation:
        prompt += f"\nVERVOLGGESPREK\n{conversation}\n"
    if user_question.strip():
        prompt += f"\nVRAAG VAN DE GEBRUIKER\n{user_question.strip()}\n"
    else:
        prompt += "\nVRAAG VAN DE GEBRUIKER\nLeg uit wat de belangrijkste verschillen zijn en welke datagedragen hypothesen deze kunnen verklaren.\n"
    return prompt


def compare_selected_activities(
    activities: pd.DataFrame,
    question: str = "",
    previous_answer: str = "",
    conversation: str = "",
) -> str:
    if activities is None or len(activities) < 2:
        raise ValueError("Selecteer minstens twee activiteiten voor de vergelijking.")
    from AICoach.chat.ai_message_handler import handle_message
    return handle_message(
        build_ai_comparison_prompt(
            activities,
            user_question=question,
            previous_answer=previous_answer,
            conversation=conversation,
        )
    )
