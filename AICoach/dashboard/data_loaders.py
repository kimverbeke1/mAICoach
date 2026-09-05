# -*- coding: utf-8 -*-

from pathlib import Path
import json
import math

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DIR = PROJECT_ROOT / "data" / "history"
ACTIVITY_FILE = PROJECT_ROOT / "data" / "activities" / "activities.json"
WELLNESS_FILE = PROJECT_ROOT / "data" / "wellness" / "wellness.json"
KNOWLEDGE_FILE = PROJECT_ROOT / "data" / "athlete_knowledge.json"
RUN_TOKENS = ("run", "running", "trail")


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def first_value(record, names):
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def numeric(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def text_date(value):
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else None


def is_running_sport(sport):
    value = str(sport or "").lower()
    return any(token in value for token in RUN_TOKENS)


@st.cache_data
def load_history():
    rows = []
    if not HISTORY_DIR.exists():
        return pd.DataFrame()

    for history_file in sorted(HISTORY_DIR.glob("*.json")):
        payload = load_json(history_file, None)
        if isinstance(payload, dict):
            rows.append(payload)
        elif isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "date" not in df.columns:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    for column in (
        "fitness",
        "fatigue",
        "training_load",
        "resting_hr",
        "weight",
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "fitness" in df.columns and "fatigue" in df.columns:
        df["form"] = df["fitness"] - df["fatigue"]

    return df.reset_index(drop=True)


@st.cache_data
def load_wellness_frame():
    records = load_json(WELLNESS_FILE, [])
    if not isinstance(records, list) or not records:
        return pd.DataFrame()

    rows = []
    for record in records:
        if not isinstance(record, dict):
            continue

        date_value = text_date(
            record.get("id")
            or record.get("date")
            or record.get("start_date")
        )
        if not date_value:
            continue

        sleep_seconds = numeric(
            first_value(record, ("sleepSecs", "sleep_seconds", "sleep"))
        )

        rows.append(
            {
                "date": date_value,
                "resting_hr": numeric(
                    first_value(record, ("restingHR", "resting_hr", "restingHr"))
                ),
                "hrv": numeric(
                    first_value(record, ("hrv", "hrvRMSSD", "hrv_rmssd"))
                ),
                "sleep_hours": (
                    sleep_seconds / 3600 if sleep_seconds is not None else None
                ),
                "sleep_score": numeric(
                    first_value(record, ("sleepScore", "sleep_score"))
                ),
                "sleep_quality": numeric(
                    first_value(record, ("sleepQuality", "sleep_quality"))
                ),
                "readiness": numeric(
                    first_value(
                        record,
                        ("readiness", "readinessScore", "readiness_score"),
                    )
                ),
                "steps": numeric(record.get("steps")),
                "vo2max": numeric(first_value(record, ("vo2max", "vo2Max"))),
                "motivation": numeric(record.get("motivation")),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


@st.cache_data
def load_activities_frame():
    records = load_json(ACTIVITY_FILE, [])
    if not isinstance(records, list) or not records:
        return pd.DataFrame()

    rows = []
    for record in records:
        if not isinstance(record, dict):
            continue

        date_value = text_date(
            record.get("start_date_local") or record.get("start_date")
        )
        if not date_value:
            continue

        duration_seconds = numeric(record.get("moving_time"))
        if duration_seconds is None:
            duration_seconds = numeric(record.get("elapsed_time"))

        distance_m = numeric(record.get("distance"))
        fitness = numeric(record.get("icu_ctl"))
        fatigue = numeric(record.get("icu_atl"))

        rows.append(
            {
                "id": record.get("id"),
                "date": date_value,
                "name": record.get("name") or record.get("type") or "Activiteit",
                "sport": record.get("type") or "Onbekend",
                "distance_km": distance_m / 1000 if distance_m is not None else None,
                "duration_min": duration_seconds / 60 if duration_seconds is not None else None,
                "avg_hr": numeric(record.get("average_heartrate")),
                "max_hr": numeric(record.get("max_heartrate")),
                "training_load": numeric(record.get("icu_training_load")),
                "fitness": fitness,
                "fatigue": fatigue,
                "form": fitness - fatigue if fitness is not None and fatigue is not None else None,
                "elevation_gain": numeric(record.get("total_elevation_gain")),
                "elevation_loss": numeric(record.get("total_elevation_loss")),
                "calories": numeric(record.get("calories")),
                "intensity": numeric(record.get("icu_intensity")),
                "resting_hr": numeric(record.get("icu_resting_hr")),
                "device": record.get("device_name"),
                "source": record.get("source"),
                "description": record.get("description"),
                "interval_summary": record.get("interval_summary"),
                "hr_zone_times": record.get("icu_hr_zone_times"),
                "hr_zones": record.get("icu_hr_zones"),
                "decoupling": numeric(record.get("decoupling")),
                "trimp": numeric(record.get("trimp")),
                "cadence": numeric(record.get("average_cadence")),
                "temperature": numeric(
                    first_value(record, ("average_weather_temp", "average_temp"))
                ),
                "raw": record,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date", ascending=False).reset_index(drop=True)
