# -*- coding: utf-8 -*-
"""Lichte incrementele synchronisatie voor mAICoach.

1. Zet bij een koude start eerst de persistente history uit Firestore terug naar
   lokale bestanden (zodat data/history/*.json meteen bestaat).
2. Haalt enkel de recentste ontbrekende activiteiten en wellness op (met een
   kleine overlap zodat retroactief bijgestelde CTL/ATL correct worden bijgewerkt).
3. Herbouwt LOKAAL data/history/*.json uit wellness (primaire bron voor
   Fitness/Fatigue/Form, inclusief vandaag), verrijkt met training_load uit
   activities.json, en spiegelt die history naar Firestore.

Zo tonen dashboard en dagelijkse update altijd dezelfde, actuele Form die
overeenkomt met Intervals.icu, en overleven de gegevens een cloud-herstart.
"""

from datetime import date, timedelta
from pathlib import Path
import json

from AICoach.intervals.client import IntervalsClient
from AICoach.persistent_data import mirror_history_to_local, save_history_bulk
from AICoach.sync_activity_history import (
    configured_history_days,
    load_existing_activities,
    merge_activities,
    save_activities,
)
from AICoach.sync_wellness_history import (
    history_days,
    load_existing as load_existing_wellness,
    merge as merge_wellness,
    record_date as wellness_record_date,
    save as save_wellness,
)

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities" / "activities.json"
WELLNESS_FILE = ROOT / "data" / "wellness" / "wellness.json"
HISTORY_DIR = ROOT / "data" / "history"

OVERLAP_DAYS = 7


def _activity_date(record):
    value = record.get("start_date_local") or record.get("start_date")
    return str(value or "")[:10]


def _last_date(values):
    valid = [value for value in values if value]
    return max(valid) if valid else None


def _oldest_from(last_date, fallback_days):
    if not last_date:
        return (date.today() - timedelta(days=fallback_days)).isoformat()
    try:
        anchor = date.fromisoformat(str(last_date)[:10])
    except ValueError:
        return (date.today() - timedelta(days=fallback_days)).isoformat()
    return (anchor - timedelta(days=OVERLAP_DAYS)).isoformat()


def _load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _first(record, names):
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def sync_latest_activities():
    existing = load_existing_activities()
    last_date = _last_date(_activity_date(item) for item in existing)
    oldest = _oldest_from(last_date, configured_history_days())
    newest = date.today().isoformat()
    downloaded = IntervalsClient().get_activities(oldest=oldest, newest=newest)
    merged = merge_activities(existing, downloaded)
    save_activities(merged)
    return {"oldest": oldest, "newest": newest, "downloaded": len(downloaded), "stored": len(merged)}


def sync_latest_wellness():
    existing = load_existing_wellness()
    last_date = _last_date(
        wellness_record_date(item) for item in existing if isinstance(item, dict)
    )
    oldest = _oldest_from(last_date, history_days())
    newest = date.today().isoformat()
    downloaded = IntervalsClient().get_wellness(oldest=oldest, newest=newest)
    merged = merge_wellness(existing, downloaded)
    save_wellness(merged)
    return {"oldest": oldest, "newest": newest, "downloaded": len(downloaded), "stored": len(merged)}


def rebuild_history_local():
    """Herbouw data/history/*.json uit wellness (primair) + activiteiten, en spiegel naar Firestore."""
    wellness = _load_json(WELLNESS_FILE, [])
    if isinstance(wellness, dict):
        wellness = wellness.get("wellness", wellness.get("data", []))
    activities = _load_json(ACTIVITIES_FILE, [])
    if isinstance(activities, dict):
        activities = activities.get("activities", activities.get("data", []))

    per_day = {}
    for record in wellness if isinstance(wellness, list) else []:
        if not isinstance(record, dict):
            continue
        day = str(record.get("id") or record.get("date") or record.get("start_date") or "")[:10]
        if not day:
            continue
        fitness = _first(record, ("ctl", "icu_ctl", "fitness"))
        fatigue = _first(record, ("atl", "icu_atl", "fatigue"))
        form = _first(record, ("form", "tsb", "icu_tsb"))
        if form is None and fitness is not None and fatigue is not None:
            try:
                form = round(float(fitness) - float(fatigue), 2)
            except (TypeError, ValueError):
                form = None
        per_day[day] = {
            "date": day,
            "fitness": fitness,
            "fatigue": fatigue,
            "form": form,
            "training_load": None,
            "resting_hr": _first(record, ("restingHR", "resting_hr", "icu_resting_hr")),
            "weight": _first(record, ("weight", "icu_weight")),
        }

    for record in activities if isinstance(activities, list) else []:
        if not isinstance(record, dict):
            continue
        day = _activity_date(record)
        if not day:
            continue
        entry = per_day.setdefault(day, {"date": day, "fitness": None, "fatigue": None, "form": None,
                                          "training_load": None, "resting_hr": None, "weight": None})
        load = record.get("icu_training_load")
        if load is not None:
            try:
                entry["training_load"] = (entry["training_load"] or 0) + float(load)
            except (TypeError, ValueError):
                pass
        if entry.get("fitness") is None and record.get("icu_ctl") is not None:
            entry["fitness"] = record.get("icu_ctl")
        if entry.get("fatigue") is None and record.get("icu_atl") is not None:
            entry["fatigue"] = record.get("icu_atl")
        if entry.get("form") is None and entry.get("fitness") is not None and entry.get("fatigue") is not None:
            try:
                entry["form"] = round(float(entry["fitness"]) - float(entry["fatigue"]), 2)
            except (TypeError, ValueError):
                pass

    per_day.setdefault(date.today().isoformat(), {"date": date.today().isoformat()})

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    for day, summary in per_day.items():
        (HISTORY_DIR / f"{day}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Spiegel naar Firestore zodat de history een cloud-herstart overleeft.
    save_history_bulk(per_day)
    return {"days": len(per_day)}


def sync_latest_data():
    # Koude start: zet persistente history uit Firestore terug naar lokaal.
    restored = mirror_history_to_local()
    activities = sync_latest_activities()
    wellness = sync_latest_wellness()
    history = rebuild_history_local()
    return {
        "restored_from_firestore": restored,
        "activities": activities,
        "wellness": wellness,
        "history": history,
    }


def main():
    result = sync_latest_data()
    print()
    print("LICHTE SYNC VOLTOOID")
    print("=" * 60)
    for name, info in result.items():
        print(f"{name}: {info}")
    print()


if __name__ == "__main__":
    main()
