from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "history"
ACTIVITY_FILE = ROOT / "data" / "activities" / "activities.json"
WELLNESS_FILE = ROOT / "data" / "wellness" / "wellness.json"
KNOWLEDGE_FILE = ROOT / "data" / "athlete_knowledge.json"


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def record_date(record, wellness=False, activity=False):
    if wellness:
        value = (
            record.get("id")
            or record.get("date")
            or record.get("start_date")
        )
    elif activity:
        value = (
            record.get("start_date_local")
            or record.get("start_date")
        )
    else:
        value = record.get("date")

    return str(value or "")[:10]


def first_value(record, names):
    for name in names:
        value = record.get(name)

        if value is not None:
            return value

    return None


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_history():
    rows = []

    if not HISTORY_DIR.exists():
        return rows

    for history_file in sorted(HISTORY_DIR.glob("*.json")):
        payload = load_json(history_file, None)

        if isinstance(payload, dict):
            rows.append(payload)
        elif isinstance(payload, list):
            rows.extend(
                item
                for item in payload
                if isinstance(item, dict)
            )

    rows = [
        record
        for record in rows
        if record_date(record)
    ]
    rows.sort(key=record_date)

    return rows


def load_activities():
    payload = load_json(ACTIVITY_FILE, [])

    if not isinstance(payload, list):
        return []

    activities = [
        item
        for item in payload
        if isinstance(item, dict)
        and record_date(item, activity=True)
    ]
    activities.sort(
        key=lambda item: record_date(
            item,
            activity=True,
        )
    )

    return activities


def load_wellness():
    payload = load_json(WELLNESS_FILE, [])

    if not isinstance(payload, list):
        return []

    wellness = [
        item
        for item in payload
        if isinstance(item, dict)
        and record_date(item, wellness=True)
    ]
    wellness.sort(
        key=lambda item: record_date(
            item,
            wellness=True,
        )
    )

    return wellness


def average(records, field):
    values = []

    for record in records:
        value = numeric(record.get(field))

        if value is not None:
            values.append(value)

    if not values:
        return None

    return round(sum(values) / len(values), 1)


def calculated_form(record):
    if not record:
        return None

    fitness = numeric(
        record.get(
            "icu_ctl",
            record.get("fitness"),
        )
    )
    fatigue = numeric(
        record.get(
            "icu_atl",
            record.get("fatigue"),
        )
    )

    if fitness is None or fatigue is None:
        return None

    return round(fitness - fatigue, 1)


def compact_wellness(record):
    if not record:
        return {}

    sleep_seconds = numeric(
        first_value(
            record,
            (
                "sleepSecs",
                "sleep_seconds",
                "sleep",
            ),
        )
    )

    return {
        "date": record_date(
            record,
            wellness=True,
        ),
        "resting_hr": first_value(
            record,
            (
                "restingHR",
                "resting_hr",
                "restingHr",
            ),
        ),
        "hrv": first_value(
            record,
            (
                "hrv",
                "hrvRMSSD",
                "hrv_rmssd",
            ),
        ),
        "sleep_hours": (
            round(sleep_seconds / 3600, 2)
            if sleep_seconds is not None
            else None
        ),
        "sleep_score": first_value(
            record,
            (
                "sleepScore",
                "sleep_score",
            ),
        ),
        "readiness": first_value(
            record,
            (
                "readiness",
                "readinessScore",
                "readiness_score",
            ),
        ),
        "stress": first_value(
            record,
            (
                "stress",
                "stressScore",
                "stress_score",
            ),
        ),
        "weight": record.get("weight"),
        "steps": record.get("steps"),
        "spo2": first_value(
            record,
            (
                "spO2",
                "spo2",
            ),
        ),
    }


def build_context():
    history = load_history()
    activities = load_activities()
    wellness = load_wellness()

    latest_history = history[-1] if history else {}
    latest_activity = activities[-1] if activities else {}
    latest_wellness = wellness[-1] if wellness else {}

    last_7 = history[-7:]
    last_30 = history[-30:]

    today_wellness = compact_wellness(
        latest_wellness
    )

    latest_activity_date = record_date(
        latest_activity,
        activity=True,
    )
    latest_history_date = record_date(
        latest_history
    )

    return {
        "current_date": (
            today_wellness.get("date")
            or latest_history_date
            or latest_activity_date
        ),
        "latest_training_status_date": (
            latest_history_date
        ),
        "latest_activity": {
            "date": latest_activity_date,
            "name": latest_activity.get("name"),
            "type": latest_activity.get("type"),
            "training_load": latest_activity.get(
                "icu_training_load"
            ),
            "average_heartrate": latest_activity.get(
                "average_heartrate"
            ),
        },
        "today_wellness": today_wellness,
        "fitness": latest_history.get("fitness"),
        "fatigue": latest_history.get("fatigue"),
        "form": calculated_form(latest_history),
        "training_load": latest_history.get(
            "training_load"
        ),
        "resting_hr": (
            today_wellness.get("resting_hr")
            if today_wellness.get("resting_hr")
            is not None
            else latest_history.get("resting_hr")
        ),
        "weight": (
            today_wellness.get("weight")
            if today_wellness.get("weight")
            is not None
            else latest_history.get("weight")
        ),
        "load_avg_7": average(
            last_7,
            "training_load",
        ),
        "load_avg_30": average(
            last_30,
            "training_load",
        ),
        "fitness_avg_7": average(
            last_7,
            "fitness",
        ),
        "fitness_avg_30": average(
            last_30,
            "fitness",
        ),
        "fatigue_avg_7": average(
            last_7,
            "fatigue",
        ),
        "fatigue_avg_30": average(
            last_30,
            "fatigue",
        ),
        "history_days_loaded": len(history),
        "activities_loaded": len(activities),
        "wellness_days_loaded": len(wellness),
        "athlete_knowledge": load_json(
            KNOWLEDGE_FILE,
            {},
        ),
    }


if __name__ == "__main__":
    print(
        json.dumps(
            build_context(),
            ensure_ascii=False,
            indent=2,
        )
    )
