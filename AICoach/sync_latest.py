# -*- coding: utf-8 -*-
# #sync_latest.py
"""Lichte incrementele synchronisatie voor mAICoach.

1. Zet bij een koude start eerst de persistente data uit GCS terug naar
   lokale bestanden (zodat data/history/*.json, data/wellness/wellness.json en
   data/activities/activities.json meteen bestaan).
2. Haalt enkel de recentste ontbrekende activiteiten en wellness op (met een
   kleine overlap zodat retroactief bijgestelde CTL/ATL correct worden bijgewerkt).
3. Herbouwt LOKAAL data/history/*.json uit wellness (primaire bron voor
   Fitness/Fatigue/Form, inclusief vandaag), verrijkt met training_load uit
   activities.json, en spiegelt die history naar GCS.

Zo tonen dashboard en dagelijkse update altijd dezelfde, actuele Form die
overeenkomt met Intervals.icu, en overleven de gegevens een cloud-herstart.

MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15 (kritieke bugfix):
BUG (opgelost, gemeld door Kim: Recovery- en Activiteiten-tab bleven LEEG op
de cloud, terwijl Dashboard wel werkte): deze module schreef enkel de
herbouwde history naar GCS (save_history_bulk). wellness.json en
activities.json werden uitsluitend LOKAAL bewaard (via save_wellness/
save_activities uit sync_wellness_history/sync_activity_history).

Zolang de Streamlit-app zelf de sync uitvoerde, was dat voldoende: dezelfde
container schreef en las die bestanden. Sinds de sync in een APARTE GitHub
Actions-runner draait (MATCHFITAI_DROP_LIVE_SYNC_FROM_APP_2026-09-14), wordt
die runner na afloop vernietigd - de twee bestanden bereikten de
Streamlit-container dus nooit. Enkel history overleefde, omdat dat als enige
naar GCS werd gespiegeld.

Fix: na elke sync worden wellness en activities nu OOK naar GCS geschreven
(persist_wellness/persist_activities), en bij een koude start worden alle
drie de bronnen teruggezet via mirror_all_to_local().

--------------------------------------------------------------------------
MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24 (op verzoek van Kim, na een
concreet incident: Cloud Storage-facturering stond uit, maar deze log bleef
wekenlang "persisted: 152" / "persisted: 731" tonen alsof alles goed ging)
--------------------------------------------------------------------------
ROOT CAUSE: persist_wellness()/persist_activities()/save_history_bulk() in
persistent_data.py gaven voorheen enkel het LOKALE recordaantal terug,
ongeacht of de daaropvolgende GCS-schrijfactie effectief slaagde. Op een
GitHub Actions-runner die na afloop VERNIETIGD wordt, is "lokaal opgeslagen"
echter betekenisloos voor persistentie - enkel "naar GCS geschreven" telt.
Een storing aan de GCS-kant (verkeerde credentials, netwerk, of in dit geval
uitgeschakelde facturering) bleef daardoor volledig onzichtbaar: de run
eindigde groen, de log oogde overtuigend, en toch verdween alle data bij de
eerstvolgende cold start.

FIX, twee delen:
  1. De drie save_*-aanroepen hieronder gebruiken nu de nieuwe, expliciete
     {"stored_locally": ..., "gcs_synced": bool}-vorm uit persistent_data.py.
  2. main() controleert na de volledige sync of ALLE drie de GCS-schrijf-
     acties gelukt zijn. Is dat niet zo, dan drukt het een luide, niet te
     missen waarschuwing af MET de concrete oorzaak (via
     persistent_data.gcs_status(), dat de eigenlijke foutmelding van Google
     Cloud doorgeeft - bv. "billing not enabled") en sluit af met
     sys.exit(1). Dat laat de GitHub Actions-run als MISLUKT verschijnen
     i.p.v. als misleidend succesvol, en (indien ingesteld) triggert dat een
     e-mailnotificatie van GitHub zelf bij een falende scheduled workflow -
     precies het soort onopgemerkt-blijvend probleem dat hier weken duurde.
"""
from datetime import date, timedelta
from pathlib import Path
import json
import sys

from AICoach.intervals.client import IntervalsClient
from AICoach.persistent_data import (
    gcs_status,
    mirror_all_to_local,
    save_history_bulk,
    save_activities as persist_activities,
    save_wellness as persist_wellness,
)
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
    # MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15: ook naar GCS, anders
    # bereikt dit bestand de Streamlit-container nooit (zie moduledocstring).
    # MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: persist_activities() geeft
    # nu {"stored_locally": ..., "gcs_synced": bool} terug i.p.v. een kaal
    # getal - zie persistent_data.py voor de volledige toelichting.
    persisted = persist_activities(merged)
    return {
        "oldest": oldest,
        "newest": newest,
        "downloaded": len(downloaded),
        "stored": len(merged),
        "persisted_locally": persisted["stored_locally"],
        "gcs_synced": persisted["gcs_synced"],
    }


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
    # MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15: ook naar GCS - dit is
    # de bron voor HRV/slaap in de Recovery-tab.
    # MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: zie sync_latest_activities().
    persisted = persist_wellness(merged)
    return {
        "oldest": oldest,
        "newest": newest,
        "downloaded": len(downloaded),
        "stored": len(merged),
        "persisted_locally": persisted["stored_locally"],
        "gcs_synced": persisted["gcs_synced"],
    }


def rebuild_history_local():
    """Herbouw data/history/*.json uit wellness (primair) + activiteiten, en spiegel naar GCS."""
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
    # Spiegel naar GCS zodat de history een cloud-herstart overleeft.
    # MATCHFITAI_HISTORY_BULK_OBJECT_2026-09-15: save_history_bulk schrijft nu
    # een bulk-object i.p.v. een object per dag (was 736 aparte uploads).
    # MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: geeft nu ook gcs_synced
    # terug i.p.v. enkel het lokale aantal.
    persisted = save_history_bulk(per_day)
    return {
        "days_locally": persisted["stored_locally"],
        "gcs_synced": persisted["gcs_synced"],
    }


def sync_latest_data():
    # Koude start: zet ALLE persistente bronnen uit GCS terug naar lokaal.
    # MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15: was mirror_history_to_local(),
    # wat enkel history terugzette - wellness/activities ontbraken daardoor.
    restored = mirror_all_to_local()
    activities = sync_latest_activities()
    wellness = sync_latest_wellness()
    history = rebuild_history_local()
    return {
        "restored_from_storage": restored,
        "activities": activities,
        "wellness": wellness,
        "history": history,
    }


def _print_gcs_failure_banner() -> None:
    """MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: drukt de WERKELIJKE
    oorzaak af (bv. "billing not enabled") i.p.v. enkel te melden dat er
    iets mis is - dat laatste bleek in de praktijk niet genoeg om het
    probleem tijdig op te merken."""
    status = gcs_status()
    print()
    print("!" * 70)
    print("!! WAARSCHUWING: GOOGLE CLOUD STORAGE IS NIET BEREIKBAAR")
    print("!" * 70)
    print(
        "De data hierboven is enkel LOKAAL op deze (wegwerp-)runner "
        "opgeslagen en gaat straks VERLOREN - er is NIETS naar de cloud "
        "geschreven. De app zal bij de volgende cold start niets nieuws "
        "terugvinden."
    )
    print()
    print(f"  Bucket geconfigureerd : {status['bucket_name'] or '(geen)'}")
    print(f"  Pakket geinstalleerd  : {status['package_installed']}")
    print(f"  Credentials-bron      : {status['credentials_source']}")
    print(f"  Concrete foutmelding  : {status['error']}")
    print()
    print("Vaak voorkomende oorzaken: uitgeschakelde facturering op het GCP-")
    print("project, verlopen/ingetrokken service-account-credentials, of een")
    print("gewijzigde GCS_BUCKET-naam in de secrets.")
    print("!" * 70)


def main():
    result = sync_latest_data()
    print()
    print("LICHTE SYNC VOLTOOID")
    print("=" * 60)
    for name, info in result.items():
        print(f"{name}: {info}")
    print()

    # MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: expliciete eindcontrole.
    # Elk van deze drie MOET gcs_synced=True zijn, anders is deze hele run
    # voor niets geweest zodra de runner verdwijnt.
    gcs_ok = (
        result["activities"]["gcs_synced"]
        and result["wellness"]["gcs_synced"]
        and result["history"]["gcs_synced"]
    )
    if not gcs_ok:
        _print_gcs_failure_banner()
        sys.exit(1)


if __name__ == "__main__":
    main()
