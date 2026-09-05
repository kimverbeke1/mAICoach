# -*- coding: utf-8 -*-
"""Feitelijke kennislaag voor mAICoach.

Belangrijke wijziging: dit bestand berekent GEEN interpretatieve prestatie- of
efficiëntieconclusies meer voor. De vorige versie leidde tautologische inzichten
af (bijvoorbeeld "lagere hartslag bij gelijke snelheid"), doordat de "topgroep"
net op basis van snelheid/hartslag werd gedefinieerd. Die logica is verwijderd.

Wat blijft, is louter feitelijke, niet-interpretatieve data:
- datakwaliteit en dekking,
- feitelijke records (beste geschatte 10 km),
- feitelijke belastingsprofielen per sport,
- feitelijke wellness-trends (eerste versus recente periode).

De interpretatie en het ontdekken van bruikbare patronen gebeurt door GPT in
athlete_insight_generator.py, dat rechtstreeks op de ruwe data werkt.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "history"
ACTIVITY_FILE = ROOT / "data" / "activities" / "activities.json"
WELLNESS_FILE = ROOT / "data" / "wellness" / "wellness.json"
KNOWLEDGE_FILE = ROOT / "data" / "athlete_knowledge.json"

RUN_TOKENS = ("run", "running", "trail")
TEN_K_MIN_METERS = 9500.0
TEN_K_MAX_METERS = 10500.0

WELLNESS_ALIASES = {
    "resting_hr": ("restingHR", "resting_hr", "restingHr"),
    "hrv": ("hrv", "hrvRMSSD", "hrv_rmssd"),
    "sleep_seconds": ("sleepSecs", "sleep_seconds", "sleep"),
    "sleep_score": ("sleepScore", "sleep_score"),
    "sleep_quality": ("sleepQuality", "sleep_quality"),
    "readiness": ("readiness", "readinessScore", "readiness_score"),
    "stress": ("stress", "stressScore", "stress_score"),
    "subjective_fatigue": ("fatigue", "fatigueScore", "fatigue_score"),
    "soreness": ("soreness", "sorenessScore", "soreness_score"),
    "mood": ("mood", "moodScore", "mood_score"),
    "motivation": ("motivation", "motivationScore", "motivation_score"),
    "weight": ("weight",),
    "spo2": ("spO2", "spo2"),
    "steps": ("steps",),
    "vo2max": ("vo2max", "vo2Max"),
    "respiration": ("respiration",),
}

METRIC_LABELS = {
    "resting_hr": "Rusthartslag",
    "hrv": "HRV",
    "sleep_hours": "Slaapduur",
    "sleep_score": "Slaapscore",
    "sleep_quality": "Slaapkwaliteit",
    "readiness": "Readiness",
    "stress": "Stress",
    "subjective_fatigue": "Subjectieve vermoeidheid",
    "soreness": "Spierpijn",
    "mood": "Stemming",
    "motivation": "Motivatie",
    "weight": "Gewicht",
    "steps": "Stappen",
    "vo2max": "VO2max",
}


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def rounded(value, digits=2):
    return round(value, digits) if value is not None else None


def mean(values):
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def confidence(sample_size):
    if sample_size >= 40:
        return {"label": "hoog", "score": 0.85}
    if sample_size >= 25:
        return {"label": "redelijk", "score": 0.70}
    if sample_size >= 15:
        return {"label": "middelmatig", "score": 0.55}
    if sample_size >= 8:
        return {"label": "laag", "score": 0.35}
    return {"label": "onvoldoende", "score": 0.15}


def text_date(value):
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else None


def first_value(record, names):
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def load_history():
    records = []
    if not HISTORY_DIR.exists():
        return records
    for path in sorted(HISTORY_DIR.glob("*.json")):
        payload = load_json(path, None)
        if isinstance(payload, dict):
            records.append(payload)
        elif isinstance(payload, list):
            records.extend(item for item in payload if isinstance(item, dict))
    return records


def load_activities():
    payload = load_json(ACTIVITY_FILE, [])
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def load_wellness():
    payload = load_json(WELLNESS_FILE, [])
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def activity_date(activity):
    return text_date(activity.get("start_date_local") or activity.get("start_date"))


def wellness_date(record):
    return text_date(record.get("id") or record.get("date") or record.get("start_date"))


def normalized_sport(activity):
    sport = str(activity.get("type", "Unknown")).strip()
    return sport or "Unknown"


def is_running_sport(sport):
    value = str(sport).lower()
    return any(token in value for token in RUN_TOKENS)


def calculate_form(record):
    fitness = number(record.get("icu_ctl", record.get("fitness")))
    fatigue = number(record.get("icu_atl", record.get("fatigue")))
    if fitness is None or fatigue is None:
        return None
    return fitness - fatigue


def duration_seconds(activity):
    moving = number(activity.get("moving_time"))
    if moving is not None and moving > 0:
        return moving
    elapsed = number(activity.get("elapsed_time"))
    return elapsed if elapsed is not None and elapsed > 0 else None


def format_duration(seconds):
    if seconds is None:
        return None
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds_left = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds_left:02d}" if hours else f"{minutes}:{seconds_left:02d}"


def compact_wellness(record):
    if not record:
        return {}
    result = {}
    for metric, aliases in WELLNESS_ALIASES.items():
        value = number(first_value(record, aliases))
        if value is not None:
            result[metric] = value
    sleep_seconds = result.pop("sleep_seconds", None)
    if sleep_seconds is not None:
        result["sleep_hours"] = sleep_seconds / 3600
    return result


def wellness_index(records):
    return {wellness_date(item): item for item in records if wellness_date(item)}


def previous_date_text(value):
    text = text_date(value)
    if text is None:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None
    from datetime import timedelta

    return (parsed - timedelta(days=1)).isoformat()


def build_non_running_load_profiles(activities, wellness_by_date, history_by_date):
    grouped = {}
    for activity in activities:
        sport = normalized_sport(activity)
        if is_running_sport(sport):
            continue
        grouped.setdefault(sport, []).append(activity)
    profiles = []
    for sport, items in sorted(grouped.items()):
        if len(items) < 3:
            continue
        durations = [duration_seconds(item) for item in items]
        loads = [number(item.get("icu_training_load")) for item in items]
        average_hrs = [number(item.get("average_heartrate")) for item in items]
        forms = [calculate_form(item) for item in items]
        profiles.append(
            {
                "sport": sport,
                "analysis_kind": "load_profile_only",
                "sample_size": len(items),
                "average_duration_minutes": rounded(
                    mean(durations) / 60 if mean(durations) is not None else None, 1
                ),
                "average_training_load": rounded(mean(loads), 1),
                "average_heartrate": rounded(mean(average_hrs), 1),
                "average_form": rounded(mean(forms), 1),
                "statement": (
                    "Dit profiel beschrijft alleen fysiologische belasting en context. "
                    "Het zegt niets over winst, verlies, techniek of kwaliteit van de prestatie."
                ),
                "activity_ids": [item.get("id") for item in items],
            }
        )
    return profiles


def build_wellness_coverage(wellness):
    coverage = {}
    for metric, aliases in WELLNESS_ALIASES.items():
        available = sum(
            1 for record in wellness if number(first_value(record, aliases)) is not None
        )
        coverage[metric] = {
            "available": available,
            "total": len(wellness),
            "coverage_percent": rounded(
                available / len(wellness) * 100 if wellness else 0, 1
            ),
        }
    return coverage


def build_wellness_trends(wellness):
    trends = []
    for metric, aliases in WELLNESS_ALIASES.items():
        values = [number(first_value(record, aliases)) for record in wellness]
        values = [value for value in values if value is not None]
        if len(values) < 14:
            continue
        block_size = max(7, len(values) // 4)
        first_average = mean(values[:block_size])
        recent_average = mean(values[-block_size:])
        difference = recent_average - first_average
        trends.append(
            {
                "metric": metric,
                "label": METRIC_LABELS.get(metric, metric),
                "sample_size": len(values),
                "confidence": confidence(len(values)),
                "first_period_average": rounded(first_average, 2),
                "recent_period_average": rounded(recent_average, 2),
                "difference": rounded(difference, 2),
            }
        )
    return trends


def best_10k(activities, wellness_by_date):
    candidates = []
    for activity in activities:
        sport = normalized_sport(activity)
        if not is_running_sport(sport):
            continue
        distance = number(activity.get("distance"))
        duration = duration_seconds(activity)
        if distance is None or duration is None:
            continue
        if not TEN_K_MIN_METERS <= distance <= TEN_K_MAX_METERS:
            continue
        equivalent_seconds = duration * 10000.0 / distance
        date_value = activity_date(activity)
        candidates.append(
            {
                "activity_id": activity.get("id"),
                "date": date_value,
                "name": activity.get("name"),
                "distance_meters": rounded(distance, 1),
                "recorded_duration": format_duration(duration),
                "estimated_10k_seconds": rounded(equivalent_seconds, 1),
                "estimated_10k_time": format_duration(equivalent_seconds),
                "average_heartrate": rounded(number(activity.get("average_heartrate")), 1),
                "fitness": rounded(number(activity.get("icu_ctl")), 1),
                "fatigue": rounded(number(activity.get("icu_atl")), 1),
                "form": rounded(calculate_form(activity), 1),
                "training_load": rounded(number(activity.get("icu_training_load")), 1),
                "same_day_wellness": compact_wellness(wellness_by_date.get(date_value)),
                "previous_day_wellness": compact_wellness(
                    wellness_by_date.get(previous_date_text(date_value))
                ),
            }
        )
    candidates.sort(key=lambda item: item["estimated_10k_seconds"])
    return {
        "status": "available" if candidates else "not_found",
        "candidate_count": len(candidates),
        "best": candidates[0] if candidates else None,
        "top_results": candidates[:10],
        "definition": (
            "Loopactiviteiten van 9.5 tot 10.5 km, omgerekend naar exact "
            "10.0 km op basis van gemiddelde snelheid."
        ),
        "limitations": [
            "Dit is geen beste 10 km-segmentanalyse binnen langere activiteiten.",
            "GPS-afstand, pauzes en parcours kunnen de schatting beïnvloeden.",
        ],
    }


def build_knowledge():
    history = load_history()
    activities = load_activities()
    wellness = load_wellness()
    wellness_by_date = wellness_index(wellness)
    history_by_date = {text_date(item.get("date")): item for item in history if text_date(item.get("date"))}
    return {
        "schema_version": 7,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Deze kennislaag bevat uitsluitend feitelijke aggregaten. Er worden geen "
            "interpretatieve prestatie- of efficiëntieconclusies voorberekend. GPT "
            "ontdekt bruikbare patronen zelf uit de ruwe data."
        ),
        "data_quality": {
            "snapshot_count": len(history),
            "activity_count": len(activities),
            "wellness_count": len(wellness),
            "wellness_coverage": build_wellness_coverage(wellness),
        },
        "performance_records": {
            "best_10k": best_10k(activities, wellness_by_date),
        },
        "non_running_load_profiles": build_non_running_load_profiles(
            activities, wellness_by_date, history_by_date
        ),
        "wellness_trends": build_wellness_trends(wellness),
        "coach_rules": [
            "Bereken geen conclusies voor; laat GPT patronen ontdekken uit de ruwe data.",
            "Gebruik alleen Running en TrailRun voor prestatie- en efficiëntieanalyse.",
            "Behandel Padel, Badminton en andere sporten zonder resultaatdata uitsluitend als belastingprofiel.",
            "Vermijd tautologische vaststellingen zoals lagere hartslag bij gelijke snelheid.",
            "Focus op stuurbare factoren: slaap, HRV, readiness, Form, Fitness en Fatigue vooraf.",
        ],
    }


def save_knowledge(knowledge):
    KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = KNOWLEDGE_FILE.with_suffix(".tmp")
    with temporary_file.open("w", encoding="utf-8") as handle:
        json.dump(knowledge, handle, ensure_ascii=False, indent=2)
    temporary_file.replace(KNOWLEDGE_FILE)


def generate_athlete_knowledge():
    knowledge = build_knowledge()
    save_knowledge(knowledge)
    return knowledge


def main():
    knowledge = generate_athlete_knowledge()
    quality = knowledge["data_quality"]
    best = knowledge["performance_records"]["best_10k"]
    print()
    print("ATHLETE LEARNING ENGINE")
    print("=" * 60)
    print(f"Activiteiten: {quality['activity_count']}")
    print(f"Wellness records: {quality['wellness_count']}")
    print(f"Niet-loop belastingprofielen: {len(knowledge['non_running_load_profiles'])}")
    print(f"Wellness-trends: {len(knowledge['wellness_trends'])}")
    print(f"10 km kandidaten: {best['candidate_count']}")
    if best["best"]:
        print(f"Beste geschatte 10 km: {best['best']['estimated_10k_time']}")
        print(f"Datum: {best['best']['date']}")
    print(f"Kennisbestand: {KNOWLEDGE_FILE}")
    print()


if __name__ == "__main__":
    main()
