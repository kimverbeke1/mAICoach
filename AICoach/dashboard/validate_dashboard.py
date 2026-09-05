# -*- coding: utf-8 -*-
"""Valideer de modulaire MatchFitAI-dashboardstructuur en de dagelijkse datadekking.

Uitvoeren vanuit de projectroot:
    python -m AICoach.dashboard.validate_dashboard

Dit script wijzigt geen projectdata. Het controleert imports, verwachte bestanden,
JSON-bronnen en de dekking van Fitness, Fatigue en Form per kalenderdag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import importlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = PROJECT_ROOT / "AICoach" / "dashboard"
HISTORY_DIR = PROJECT_ROOT / "data" / "history"
WELLNESS_FILE = PROJECT_ROOT / "data" / "wellness" / "wellness.json"
ACTIVITIES_FILE = PROJECT_ROOT / "data" / "activities" / "activities.json"

EXPECTED_FILES = (
    PROJECT_ROOT / "AICoach" / "pages" / "training_dashboard.py",
    DASHBOARD_DIR / "data_loaders.py",
    DASHBOARD_DIR / "charts.py",
    DASHBOARD_DIR / "ui_helpers.py",
    DASHBOARD_DIR / "recovery_tab.py",
    DASHBOARD_DIR / "knowledge_tab.py",
    DASHBOARD_DIR / "activities_tab.py",
    DASHBOARD_DIR / "activity_detail.py",
    DASHBOARD_DIR / "__init__.py",
)

MODULES = (
    "AICoach.dashboard.data_loaders",
    "AICoach.dashboard.charts",
    "AICoach.dashboard.ui_helpers",
    "AICoach.dashboard.recovery_tab",
    "AICoach.dashboard.knowledge_tab",
    "AICoach.dashboard.activity_detail",
    "AICoach.dashboard.activities_tab",
)

DATE_FIELDS = ("date", "id", "start_date_local", "start_date", "timestamp")
FITNESS_FIELDS = ("fitness", "ctl")
FATIGUE_FIELDS = ("fatigue", "atl")
FORM_FIELDS = ("form", "tsb")
LOAD_FIELDS = ("training_load", "load", "icu_training_load", "ctlLoad", "atlLoad")


@dataclass
class DailyStatus:
    day: str
    fitness: float | None = None
    fatigue: float | None = None
    form: float | None = None
    source: str = ""


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(record: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return None


def _day_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    candidate = text[:10]
    try:
        date.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def _record_day(record: dict[str, Any]) -> str | None:
    return _day_text(_first(record, DATE_FIELDS))


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _records_from_json(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("records", "data", "items", "wellness", "activities"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        return [value]
    return []


def _history_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not HISTORY_DIR.exists():
        return records
    for path in sorted(HISTORY_DIR.rglob("*.json")):
        try:
            for record in _records_from_json(_read_json(path)):
                enriched = dict(record)
                enriched["__source"] = str(path.relative_to(PROJECT_ROOT))
                records.append(enriched)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WAARSCHUWING] Kan {path} niet lezen: {exc}")
    return records


def _merge_status(target: dict[str, DailyStatus], record: dict[str, Any], source: str) -> None:
    day = _record_day(record)
    if day is None:
        return

    status = target.setdefault(day, DailyStatus(day=day))
    fitness = _finite_number(_first(record, FITNESS_FIELDS))
    fatigue = _finite_number(_first(record, FATIGUE_FIELDS))
    form = _finite_number(_first(record, FORM_FIELDS))

    if fitness is not None:
        status.fitness = fitness
    if fatigue is not None:
        status.fatigue = fatigue
    if form is not None:
        status.form = form
    elif status.fitness is not None and status.fatigue is not None:
        status.form = status.fitness - status.fatigue

    if any(value is not None for value in (fitness, fatigue, form)):
        status.source = f"{status.source}, {source}".strip(", ")


def validate_files() -> bool:
    print("\n1. Bestandsstructuur")
    ok = True
    for path in EXPECTED_FILES:
        exists = path.exists()
        print(f"[{'OK' if exists else 'ONTBREEKT'}] {path.relative_to(PROJECT_ROOT)}")
        ok = ok and exists
    return ok


def validate_imports() -> bool:
    print("\n2. Module-imports")
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    ok = True
    for module_name in MODULES:
        try:
            importlib.import_module(module_name)
            print(f"[OK] {module_name}")
        except Exception as exc:  # exact importfouten moeten zichtbaar blijven
            ok = False
            print(f"[FOUT] {module_name}: {type(exc).__name__}: {exc}")
    return ok


def validate_json_source(path: Path, label: str) -> list[dict[str, Any]]:
    print(f"\n3. {label}")
    if not path.exists():
        print(f"[ONTBREEKT] {path.relative_to(PROJECT_ROOT)}")
        return []
    try:
        records = _records_from_json(_read_json(path))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FOUT] {path.relative_to(PROJECT_ROOT)}: {exc}")
        return []
    print(f"[OK] {len(records)} records leesbaar")
    return records


def analyse_daily_status(wellness_records: list[dict[str, Any]]) -> bool:
    print("\n4. Dagelijkse Fitness/Fatigue/Form-dekking")
    timeline: dict[str, DailyStatus] = {}

    history = _history_records()
    for record in history:
        _merge_status(timeline, record, str(record.get("__source", "history")))
    for record in wellness_records:
        _merge_status(timeline, record, "wellness")

    if not timeline:
        print("[FOUT] Geen gedateerde Fitness/Fatigue-records gevonden.")
        return False

    days = sorted(timeline)
    complete = [d for d in days if timeline[d].fitness is not None and timeline[d].fatigue is not None]
    partial = [d for d in days if d not in complete]

    start = date.fromisoformat(days[0])
    end = date.fromisoformat(days[-1])
    expected_days = (end - start).days + 1
    missing_calendar_days = expected_days - len(days)

    print(f"Periode: {days[0]} tot {days[-1]}")
    print(f"Dagen met statusrecord: {len(days)} van {expected_days}")
    print(f"Volledige CTL/ATL-dagen: {len(complete)}")
    print(f"Gedeeltelijke statusdagen: {len(partial)}")
    print(f"Volledig ontbrekende kalenderdagen: {missing_calendar_days}")

    if partial:
        print("Eerste gedeeltelijke dagen:")
        for day in partial[:20]:
            status = timeline[day]
            print(
                f"  {day}: fitness={status.fitness}, fatigue={status.fatigue}, "
                f"form={status.form}, bron={status.source or 'onbekend'}"
            )

    print("\nBesluit:")
    if missing_calendar_days or partial:
        print(
            "[AANDACHT] De huidige bronnen vormen geen volledige dagelijkse tijdlijn. "
            "Er werd bewust geen nulwaarde of forward-fill toegepast."
        )
        return False

    print("[OK] Fitness en Fatigue zijn voor iedere kalenderdag beschikbaar.")
    return True


def inspect_activity_detail_readiness(activity_records: list[dict[str, Any]]) -> None:
    print("\n5. Voorbereiding activiteitdetails en streams")
    if not activity_records:
        print("[AANDACHT] Geen activiteiten beschikbaar voor veldinspectie.")
        return

    candidate_fields = {
        "route": ("latlng", "route", "map", "polyline", "coordinates"),
        "streams": ("streams", "samples", "activity_streams"),
        "laps": ("laps", "intervals"),
        "hartslag": ("heartrate", "heart_rate", "hr", "hr_stream"),
        "tempo/snelheid": ("pace", "speed", "velocity", "speed_stream"),
        "hoogte": ("altitude", "elevation", "altitude_stream"),
        "cadans": ("cadence", "cadence_stream"),
        "power": ("power", "watts", "power_stream"),
        "temperatuur": ("temperature", "temp", "temperature_stream"),
    }

    available: dict[str, set[str]] = {label: set() for label in candidate_fields}
    for record in activity_records:
        keys = set(record)
        for label, fields in candidate_fields.items():
            available[label].update(keys.intersection(fields))

    for label, fields in available.items():
        if fields:
            print(f"[AANWEZIG] {label}: {', '.join(sorted(fields))}")
        else:
            print(f"[NIET GEVONDEN] {label}")

    print(
        "Dit is alleen een lokale veldinventaris. Er worden geen API-calls uitgevoerd "
        "en geen externe gegevens gewijzigd."
    )


def main() -> int:
    print("MatchFitAI dashboardvalidatie")
    files_ok = validate_files()
    imports_ok = validate_imports()
    wellness = validate_json_source(WELLNESS_FILE, "Wellnessbron")
    activities = validate_json_source(ACTIVITIES_FILE, "Activiteitenbron")
    timeline_ok = analyse_daily_status(wellness)
    inspect_activity_detail_readiness(activities)

    print("\nEindstatus")
    if files_ok and imports_ok and timeline_ok:
        print("[OK] Structuur, imports en dagelijkse statusdekking zijn in orde.")
        return 0

    print("[AANDACHT] Minstens één controle vereist verdere actie. Zie details hierboven.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
