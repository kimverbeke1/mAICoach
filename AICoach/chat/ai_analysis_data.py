from datetime import date, datetime
from pathlib import Path
import json
import math


ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "history"
ACTIVITY_FILE = ROOT / "data" / "activities" / "activities.json"
WELLNESS_FILE = ROOT / "data" / "wellness" / "wellness.json"
KNOWLEDGE_FILE = ROOT / "data" / "athlete_knowledge.json"

MAX_ACTIVITIES = 250
MAX_WELLNESS_DAYS = 366
MAX_HISTORY_DAYS = 366


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def number(value, digits=2):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return round(result, digits)


def text_date(value):
    if value is None:
        return None

    text = str(value).strip()

    if len(text) < 10:
        return None

    return text[:10]


def date_year(value):
    text = text_date(value)

    if text is None:
        return None

    try:
        return datetime.strptime(text, "%Y-%m-%d").year
    except ValueError:
        return None


def first_value(record, names):
    for name in names:
        value = record.get(name)

        if value is not None:
            return value

    return None


def calculate_form(record):
    fitness = number(
        record.get(
            "icu_ctl",
            record.get("fitness"),
        )
    )
    fatigue = number(
        record.get(
            "icu_atl",
            record.get("fatigue"),
        )
    )

    if fitness is None or fatigue is None:
        return None

    return round(fitness - fatigue, 2)


def load_history():
    records = []

    if not HISTORY_DIR.exists():
        return records

    for history_file in sorted(HISTORY_DIR.glob("*.json")):
        payload = load_json(history_file, None)

        if isinstance(payload, dict):
            records.append(payload)
        elif isinstance(payload, list):
            records.extend(
                item
                for item in payload
                if isinstance(item, dict)
            )

    return records


def load_activities():
    payload = load_json(ACTIVITY_FILE, [])

    if not isinstance(payload, list):
        return []

    return [
        item
        for item in payload
        if isinstance(item, dict)
    ]


def load_wellness():
    payload = load_json(WELLNESS_FILE, [])

    if not isinstance(payload, list):
        return []

    return [
        item
        for item in payload
        if isinstance(item, dict)
    ]


def compact_activity(activity):
    distance = number(
        first_value(
            activity,
            ("distance", "icu_distance"),
        ),
        1,
    )
    moving_time = number(
        first_value(
            activity,
            ("moving_time", "icu_recording_time", "elapsed_time"),
        ),
        0,
    )

    pace_seconds_per_km = None

    if (
        distance is not None
        and distance >= 1000
        and moving_time is not None
        and moving_time > 0
    ):
        pace_seconds_per_km = round(
            moving_time / (distance / 1000),
            1,
        )

    return {
        "date": text_date(
            activity.get("start_date_local")
            or activity.get("start_date")
        ),
        "id": activity.get("id"),
        "name": activity.get("name"),
        "sport": activity.get("type"),
        "race": activity.get("race"),
        "distance_m": distance,
        "moving_time_s": moving_time,
        "pace_s_per_km": pace_seconds_per_km,
        "elevation_gain_m": number(
            activity.get("total_elevation_gain"),
            1,
        ),
        "avg_hr": number(
            activity.get("average_heartrate"),
            1,
        ),
        "max_hr": number(
            activity.get("max_heartrate"),
            1,
        ),
        "resting_hr": number(
            activity.get("icu_resting_hr"),
            1,
        ),
        "training_load": number(
            activity.get("icu_training_load"),
            1,
        ),
        "fitness": number(
            activity.get("icu_ctl"),
            1,
        ),
        "fatigue": number(
            activity.get("icu_atl"),
            1,
        ),
        "form": calculate_form(activity),
        "intensity": number(
            activity.get("icu_intensity"),
            1,
        ),
        "rpe": number(
            first_value(
                activity,
                ("icu_rpe", "session_rpe", "perceived_exertion"),
            ),
            1,
        ),
        "feel": activity.get("feel"),
        "decoupling": number(
            activity.get("decoupling"),
            2,
        ),
        "efficiency_factor": number(
            activity.get("icu_efficiency_factor"),
            4,
        ),
        "temperature_c": number(
            first_value(
                activity,
                ("average_weather_temp", "average_temp"),
            ),
            1,
        ),
        "wind_speed": number(
            activity.get("average_wind_speed"),
            1,
        ),
    }


def compact_wellness(record):
    sleep_seconds = number(
        first_value(
            record,
            ("sleepSecs", "sleep_seconds", "sleep"),
        ),
        0,
    )

    return {
        "date": text_date(
            record.get("id")
            or record.get("date")
            or record.get("start_date")
        ),
        "resting_hr": number(
            first_value(
                record,
                ("restingHR", "resting_hr", "restingHr"),
            ),
            1,
        ),
        "hrv": number(
            first_value(
                record,
                ("hrv", "hrvRMSSD", "hrv_rmssd"),
            ),
            1,
        ),
        "sleep_hours": (
            round(sleep_seconds / 3600, 2)
            if sleep_seconds is not None
            else None
        ),
        "sleep_score": number(
            first_value(
                record,
                ("sleepScore", "sleep_score"),
            ),
            1,
        ),
        "sleep_quality": number(
            first_value(
                record,
                ("sleepQuality", "sleep_quality"),
            ),
            1,
        ),
        "readiness": number(
            first_value(
                record,
                ("readiness", "readinessScore", "readiness_score"),
            ),
            1,
        ),
        "stress": number(
            first_value(
                record,
                ("stress", "stressScore", "stress_score"),
            ),
            1,
        ),
        "fatigue_subjective": number(
            first_value(
                record,
                ("fatigue", "fatigueScore", "fatigue_score"),
            ),
            1,
        ),
        "soreness": number(
            first_value(
                record,
                ("soreness", "sorenessScore", "soreness_score"),
            ),
            1,
        ),
        "mood": number(
            first_value(
                record,
                ("mood", "moodScore", "mood_score"),
            ),
            1,
        ),
        "weight": number(record.get("weight"), 2),
        "spo2": number(
            first_value(record, ("spO2", "spo2")),
            1,
        ),
        "steps": number(record.get("steps"), 0),
    }


def compact_history(record):
    return {
        "date": text_date(record.get("date")),
        "activity_name": record.get("activity_name"),
        "activity_type": record.get("activity_type"),
        "fitness": number(record.get("fitness"), 2),
        "fatigue": number(record.get("fatigue"), 2),
        "form": calculate_form(record),
        "training_load": number(
            record.get("training_load"),
            2,
        ),
        "resting_hr": number(
            record.get("resting_hr"),
            1,
        ),
        "weight": number(record.get("weight"), 2),
    }


def remove_empty_fields(record):
    return {
        key: value
        for key, value in record.items()
        if value is not None
    }


def current_year_records(records, date_key):
    current_year = date.today().year

    filtered = [
        record
        for record in records
        if date_year(record.get(date_key)) == current_year
    ]

    return filtered


def build_ai_analysis_data():
    activities = [
        remove_empty_fields(compact_activity(item))
        for item in load_activities()
    ]
    wellness = [
        remove_empty_fields(compact_wellness(item))
        for item in load_wellness()
    ]
    history = [
        remove_empty_fields(compact_history(item))
        for item in load_history()
    ]

    activities = [
        item
        for item in activities
        if item.get("date")
    ]
    wellness = [
        item
        for item in wellness
        if item.get("date")
    ]
    history = [
        item
        for item in history
        if item.get("date")
    ]

    year = date.today().year

    year_activities = current_year_records(
        activities,
        "date",
    )[-MAX_ACTIVITIES:]
    year_wellness = current_year_records(
        wellness,
        "date",
    )[-MAX_WELLNESS_DAYS:]
    year_history = current_year_records(
        history,
        "date",
    )[-MAX_HISTORY_DAYS:]

    return {
        "dataset_version": 1,
        "year": year,
        "generated_at": datetime.now().isoformat(),
        "instructions_for_analysis": [
            "Zoek zelf naar patronen en onverwachte verbanden.",
            "Vergelijk sterke en zwakke prestaties binnen dezelfde sport.",
            "Onderzoek verbanden met slaap, HRV, rusthartslag, stress, readiness, Form, Fitness, Fatigue en load.",
            "Maak geen causale claims op basis van alleen correlatie.",
            "Vermeld aantallen, effectgrootte en ontbrekende data.",
            "Gebruik alleen velden die echt aanwezig zijn.",
        ],
        "counts": {
            "activities": len(year_activities),
            "wellness_days": len(year_wellness),
            "history_days": len(year_history),
        },
        "activities": year_activities,
        "wellness": year_wellness,
        "daily_training_status": year_history,
        "precomputed_knowledge": load_json(
            KNOWLEDGE_FILE,
            {},
        ),
    }


if __name__ == "__main__":
    payload = build_ai_analysis_data()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
