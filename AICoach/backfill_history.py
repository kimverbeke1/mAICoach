# -*- coding: utf-8 -*-
"""Bouwt data/history/*.json op als een doorlopende dagreeks.

Belangrijk (opgeloste sync-bug):
- Vroeger werd er enkel een history-bestand geschreven voor dagen met een
  activiteit. Rustdagen en 'vandaag' (nog geen activiteit) kregen geen bestand,
  waardoor het dashboard verouderde Fitness/Fatigue/Form toonde.
- Nu is wellness.json de primaire bron voor de dagelijkse Fitness (ctl),
  Fatigue (atl) en afgeleide Form (ctl - atl). Wellness bevat elke dag,
  inclusief vandaag. De activiteitdata verrijkt die dagen met training_load,
  hr_load, activity_name en activity_type.
"""

from datetime import date, timedelta
from pathlib import Path
import json

from AICoach.intervals.client import IntervalsClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "history"
WELLNESS_FILE = PROJECT_ROOT / "data" / "wellness" / "wellness.json"


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _first(record, names):
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def _record_date(record):
    return str(
        record.get("id")
        or record.get("date")
        or record.get("start_date")
        or ""
    )[:10]


def _wellness_by_date():
    """Fitness/Fatigue/Form per kalenderdag uit wellness.json (incl. vandaag)."""
    payload = _load_json(WELLNESS_FILE, [])
    if isinstance(payload, dict):
        payload = payload.get("wellness", payload.get("data", []))
    result = {}
    if not isinstance(payload, list):
        return result
    for record in payload:
        if not isinstance(record, dict):
            continue
        date_key = _record_date(record)
        if not date_key:
            continue
        fitness = _first(record, ("ctl", "fitness", "icu_ctl"))
        fatigue = _first(record, ("atl", "fatigue", "icu_atl"))
        form = None
        if fitness is not None and fatigue is not None:
            try:
                form = round(float(fitness) - float(fatigue), 2)
            except (TypeError, ValueError):
                form = None
        result[date_key] = {
            "date": date_key,
            "fitness": fitness,
            "fatigue": fatigue,
            "form": form,
            "resting_hr": _first(record, ("restingHR", "resting_hr", "icu_resting_hr")),
            "weight": _first(record, ("weight", "icu_weight")),
        }
    return result


def _activities_by_date():
    """Activiteitdata per dag (verrijking) via IntervalsClient (behouden gedrag)."""
    client = IntervalsClient()
    activities = client.get_activities(days=365)
    print(f"Activities found: {len(activities)}")
    by_date = {}
    for activity in activities:
        date_key = str(activity.get("start_date_local", ""))[:10]
        if not date_key:
            continue
        by_date[date_key] = {
            "fitness": activity.get("icu_ctl"),
            "fatigue": activity.get("icu_atl"),
            "training_load": activity.get("icu_training_load"),
            "resting_hr": activity.get("icu_resting_hr"),
            "weight": activity.get("icu_weight"),
            "rpe": activity.get("icu_rpe"),
            "feel": activity.get("feel"),
            "hr_load": activity.get("hr_load"),
            "strain_score": activity.get("strain_score"),
            "activity_name": activity.get("name"),
            "activity_type": activity.get("type"),
        }
    return by_date


def build_history():
    """Schrijf één history-bestand per dag voor de volledige periode."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    wellness = _wellness_by_date()
    activities = _activities_by_date()

    all_dates = set(wellness) | set(activities)
    if not all_dates:
        print("Geen wellness- of activiteitdata gevonden; history niet aangepast.")
        return 0

    # Zorg dat vandaag altijd bestaat, ook zonder wellness/activiteit.
    all_dates.add(date.today().isoformat())

    count = 0
    for date_key in sorted(all_dates):
        base = wellness.get(date_key, {"date": date_key})
        summary = {
            "date": date_key,
            "fitness": base.get("fitness"),
            "fatigue": base.get("fatigue"),
            "form": base.get("form"),
            "training_load": None,
            "resting_hr": base.get("resting_hr"),
            "weight": base.get("weight"),
            "rpe": None,
            "feel": None,
            "hr_load": None,
            "strain_score": None,
            "activity_name": None,
            "activity_type": None,
        }

        activity = activities.get(date_key)
        if activity:
            # Activiteit verrijkt de dag; wellness blijft leidend voor ctl/atl.
            if summary["fitness"] is None:
                summary["fitness"] = activity.get("fitness")
            if summary["fatigue"] is None:
                summary["fatigue"] = activity.get("fatigue")
            if summary["form"] is None and summary["fitness"] is not None and summary["fatigue"] is not None:
                try:
                    summary["form"] = round(float(summary["fitness"]) - float(summary["fatigue"]), 2)
                except (TypeError, ValueError):
                    summary["form"] = None
            summary["training_load"] = activity.get("training_load")
            if summary["resting_hr"] is None:
                summary["resting_hr"] = activity.get("resting_hr")
            if summary["weight"] is None:
                summary["weight"] = activity.get("weight")
            summary["rpe"] = activity.get("rpe")
            summary["feel"] = activity.get("feel")
            summary["hr_load"] = activity.get("hr_load")
            summary["strain_score"] = activity.get("strain_score")
            summary["activity_name"] = activity.get("activity_name")
            summary["activity_type"] = activity.get("activity_type")

        outfile = OUTPUT_DIR / f"{date_key}.json"
        with outfile.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False)
        count += 1

    return count


def main():
    count = build_history()
    print()
    print(f"OK {count} dagelijkse samenvattingen opgeslagen (incl. vandaag)")


if __name__ == "__main__":
    main()
