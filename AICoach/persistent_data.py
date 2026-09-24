# -*- coding: utf-8 -*-
#persistent_data.py
"""Persistente cache voor mAICoach-data (history, wellness, activities en
activity streams) op GCS.

Op Streamlit Community Cloud is het bestandssysteem tijdelijk: data/history/*.json,
data/wellness/wellness.json, data/activities/activities.json en
data/activity_streams/*.csv verdwijnen bij een herstart of slaap. Deze module
spiegelt die data naar Google Cloud Storage, met een automatische lokale fallback
wanneer GCS niet beschikbaar is.

Objectindeling in de bucket:
- history_bulk.json                     (NIEUW, v2 - alle dagen in EEN object)
- history/<YYYY-MM-DD>.json             (LEGACY, v1 - alleen nog gelezen)
- wellness/wellness.json                (NIEUW)
- activities/activities.json            (NIEUW)
- activity_streams/<activity_id>.csv

MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15 (kritieke bugfix):
BUG (opgelost, gemeld door Kim): op de cloud toonde het Dashboard-tabblad wel
data, maar de tabbladen Recovery en Activiteiten bleven LEEG. Oorzaak: deze
module persisteerde uitsluitend history/ (en activity_streams/). wellness.json
en activities.json werden NERGENS naar GCS weggeschreven - ze bleven puur
lokale bestanden.

Zolang de Streamlit-app zelf nog de sync uitvoerde, viel dat niet op: die
schreef die bestanden lokaal weg in dezelfde container die ze daarna ook las.
Sinds MATCHFITAI_DROP_LIVE_SYNC_FROM_APP_2026-09-14 draait de sync echter in
een APARTE GitHub Actions-runner. Die runner schrijft wellness.json en
activities.json lokaal weg en wordt daarna VERNIETIGD - die twee bestanden
bereiken de Streamlit-container dus nooit meer. Enkel history/ overleefde,
omdat dat als enige wel naar GCS werd gespiegeld.

Dat verklaarde precies het waargenomen patroon:
  Dashboard    -> leest data/history/*.json      -> wel in GCS  -> werkte
  Recovery     -> leest data/wellness/wellness.json -> niet in GCS -> leeg
  Activiteiten -> leest data/activities/activities.json -> niet in GCS -> leeg

Fix: save_wellness()/save_activities() + mirror_wellness_to_local()/
mirror_activities_to_local() hieronder, aangeroepen vanuit sync_latest.py
(schrijven) en training_dashboard.py (terugspiegelen bij het laden).

MATCHFITAI_HISTORY_BULK_OBJECT_2026-09-15 (performance-fix):
BUG (opgelost, gemeld door Kim: "altijd traag, niet alleen bij koude start"):
save_history_bulk() schreef EEN GCS-object PER DAG, en mirror_history_to_local()
haalde die via list_texts() weer op. Bij 736 gesynchroniseerde dagen betekende
dat 736 afzonderlijke blob.download_as_text()-netwerkaanroepen bij ELKE
spiegeling - inherent traag over het netwerk, ongeacht caching aan de
app-kant. Lokaal viel dat niet op (gcs_available() is daar False, dus 0
downloads), op de cloud wel.

Fix: history wordt nu als EEN bulk-object (history_bulk.json) geschreven en
gelezen - een upload, een download. De oude per-dag-objecten onder history/
worden nog steeds GELEZEN als fallback (backwards compatible met reeds
bestaande data in de bucket), maar er worden geen nieuwe meer geschreven.
Na de eerstvolgende sync-run staat alles in het bulk-object en is de
spiegeling een enkele netwerkaanroep.

--------------------------------------------------------------------------
MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24 (op verzoek van Kim, na een
concreet incident)
--------------------------------------------------------------------------
WAT ER GEBEURDE: Kim's Cloud Storage-project had geen actieve facturering
meer ("You can use Cloud Storage after you enable billing"). Alle GCS-
aanroepen faalden dus stil (zie gcs_store.get_bucket(), dat elke fout
opvangt en None teruggeeft). Maar de GitHub Actions-sync bleef WEKENLANG
"succesvol" ogen:

    activities: {'oldest': ..., 'newest': '2026-09-24', 'downloaded': 152,
                 'stored': 152, 'persisted': 152}
    wellness:   {..., 'persisted': 731}
    history:    {'days': 731}

ROOT CAUSE: save_wellness()/save_activities()/save_history_bulk() gaven
altijd len(records) terug - het aantal LOKAAL geschreven records op de
(nadien vernietigde) GitHub Actions-runner - ongeacht of de GCS-schrijf-
actie erna uberhaupt lukte. "persisted: 152" zag er in de log uit als
"152 records naar de cloud weggeschreven", maar betekende in werkelijkheid
enkel "152 records lokaal weggeschreven op een wegwerp-runner". Vandaar dat
de app bij elke cold start weer op nul begon: er stond simpelweg nooit iets
in de bucket.

FIX: de drie save_*-functies hieronder geven nu een dict terug met zowel
het lokale aantal als een EXPLICIETE gcs_synced-vlag (en, bij falen, de
concrete foutmelding via gcs_store.diagnose()). sync_latest.py gebruikt dat
om, zodra GCS niet bereikbaar is, een luide, niet te missen waarschuwing in
de GitHub Actions-log te tonen EN de run als mislukt te laten eindigen -
in plaats van groen te blijven terwijl er niets bewaard wordt.

BELANGRIJK: de OUDE aanroepers die nog een kaal getal verwachtten (str(),
optellen, ...) zouden hierdoor breken. Er bestond er maar een: sync_latest.py,
en die is in dezelfde ronde meegepatcht. Is er ergens nog een andere
aanroeper die een int verwacht, dan geeft int(resultaat) een TypeError in
plaats van stil een verkeerd getal te gebruiken - dat is bewust: beter een
zichtbare fout dan een nieuwe stille aanname.
"""
from __future__ import annotations

from pathlib import Path
import json

from AICoach.gcs_store import (
    delete_object,
    diagnose as gcs_diagnose,
    gcs_available,
    list_texts,
    object_exists,
    read_text,
    write_text,
)

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "history"
STREAMS_DIR = ROOT / "data" / "activity_streams"
WELLNESS_FILE = ROOT / "data" / "wellness" / "wellness.json"
ACTIVITIES_FILE = ROOT / "data" / "activities" / "activities.json"

HISTORY_PREFIX = "history/"
STREAMS_PREFIX = "activity_streams/"
# MATCHFITAI_HISTORY_BULK_OBJECT_2026-09-15: alle history-dagen in een object.
HISTORY_BULK_PATH = "history_bulk.json"
# MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15: nieuwe objectpaden.
WELLNESS_PATH = "wellness/wellness.json"
ACTIVITIES_PATH = "activities/activities.json"


def backend() -> str:
    """Geeft 'gcs' of 'lokaal' terug."""
    return "gcs" if gcs_available() else "lokaal"


def gcs_status() -> dict:
    """MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: doorgeefluik naar
    gcs_store.diagnose(), zodat aanroepers hier (sync_latest.py,
    training_dashboard.py) geen aparte import nodig hebben en de
    diagnostische laag op een plek blijft."""
    return gcs_diagnose()


def _write_local_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_local_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
def save_history_day(date_key: str, summary: dict) -> dict:
    """Bewaar een dag. Schrijft altijd lokaal; op GCS wordt de dag in het
    bulk-object bijgewerkt (lees-wijzig-schrijf), zodat er geen losse
    per-dag-objecten meer bijkomen.

    MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: geeft nu
    {"stored_locally": bool, "gcs_synced": bool} terug i.p.v. niets, zodat
    een mislukte GCS-schrijfactie hier niet langer onopgemerkt blijft."""
    date_key = str(date_key)[:10]
    if not date_key:
        return {"stored_locally": False, "gcs_synced": False}
    _write_local_json(HISTORY_DIR / f"{date_key}.json", summary)
    gcs_synced = False
    if gcs_available():
        bulk = _read_history_bulk_remote() or {}
        bulk[date_key] = summary
        gcs_synced = write_text(
            HISTORY_BULK_PATH,
            json.dumps(bulk, ensure_ascii=False),
            content_type="application/json",
        )
    return {"stored_locally": True, "gcs_synced": gcs_synced}


def save_history_bulk(summaries_by_date: dict) -> dict:
    """MATCHFITAI_HISTORY_BULK_OBJECT_2026-09-15: schrijft alle dagen als EEN
    GCS-object in plaats van een object per dag (was: 736 afzonderlijke
    uploads/downloads bij Kim). Lokale per-dag-bestanden blijven behouden,
    want data_loaders.load_history() leest data/history/*.json rechtstreeks.

    MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: gaf voorheen enkel
    len(cleaned) terug - het lokale aantal, ongeacht of write_text() naar
    GCS effectief slaagde. Dat liet een gefaalde GCS-schrijfactie (bv. door
    de billing-storing) in de sync-log verschijnen als "history: {'days':
    731}", wat aanvoelde als succes terwijl er niets in de bucket
    terechtkwam. Geeft nu expliciet beide cijfers terug."""
    cleaned = {}
    for date_key, summary in summaries_by_date.items():
        key = str(date_key)[:10]
        if not key:
            continue
        cleaned[key] = summary
        _write_local_json(HISTORY_DIR / f"{key}.json", summary)

    gcs_synced = False
    if cleaned and gcs_available():
        gcs_synced = write_text(
            HISTORY_BULK_PATH,
            json.dumps(cleaned, ensure_ascii=False),
            content_type="application/json",
        )
    return {"stored_locally": len(cleaned), "gcs_synced": gcs_synced}


def _read_history_bulk_remote():
    """Lees het bulk-object uit GCS. None als het (nog) niet bestaat."""
    if not gcs_available():
        return None
    text = read_text(HISTORY_BULK_PATH)
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_history_legacy_remote():
    """LEGACY (v1): lees de losse per-dag-objecten onder history/.
    Alleen nog gebruikt als fallback wanneer het bulk-object nog niet bestaat,
    zodat reeds bestaande buckets blijven werken tot de eerstvolgende sync."""
    items = list_texts(HISTORY_PREFIX)
    if not items:
        return None
    out = {}
    for name, text in items:
        if not name.endswith(".json"):
            continue
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            continue
        key = Path(name).stem[:10]
        if isinstance(payload, dict) and key:
            payload.setdefault("date", key)
            out[key] = payload
    return out or None


def load_history_records() -> list[dict]:
    """Lees alle history-dagen. GCS heeft voorrang (bulk-object, anders legacy
    per-dag-objecten), daarna lokaal."""
    if gcs_available():
        remote = _read_history_bulk_remote() or _read_history_legacy_remote()
        if remote:
            records = []
            for key, payload in remote.items():
                if isinstance(payload, dict):
                    payload.setdefault("date", key)
                    records.append(payload)
            if records:
                records.sort(key=lambda item: str(item.get("date", "")))
                return records
    records = []
    if HISTORY_DIR.exists():
        for path in sorted(HISTORY_DIR.glob("*.json")):
            payload = _read_local_json(path, None)
            if isinstance(payload, dict):
                records.append(payload)
            elif isinstance(payload, list):
                records.extend(item for item in payload if isinstance(item, dict))
    return records


def mirror_history_to_local() -> int:
    """Schrijf de GCS-history naar lokale JSON-bestanden, zodat bestaande code
    die data/history/*.json rechtstreeks leest (data_loaders.load_history) na
    een koude start werkt.

    MATCHFITAI_HISTORY_BULK_OBJECT_2026-09-15: leest nu bij voorkeur het
    bulk-object (een netwerkaanroep i.p.v. een per dag)."""
    if not gcs_available():
        return 0
    remote = _read_history_bulk_remote()
    if remote is None:
        remote = _read_history_legacy_remote()
    if not remote:
        return 0
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for key, payload in remote.items():
        date_key = str(key)[:10]
        if not date_key or not isinstance(payload, dict):
            continue
        _write_local_json(HISTORY_DIR / f"{date_key}.json", payload)
        count += 1
    return count


# --------------------------------------------------------------------------- #
# Wellness + activities (elk een JSON-bestand)
# MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15
# --------------------------------------------------------------------------- #
def save_wellness(records) -> dict:
    """Bewaar de volledige wellness-lijst (bron voor HRV/slaap in de
    Recovery-tab). Schrijft lokaal en - indien beschikbaar - naar GCS.

    MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: geeft nu
    {"stored_locally": int, "gcs_synced": bool} terug i.p.v. kaal
    len(records) - zie de moduledocstring voor waarom dat onderscheid
    cruciaal is."""
    if not isinstance(records, list):
        return {"stored_locally": 0, "gcs_synced": False}
    _write_local_json(WELLNESS_FILE, records)
    gcs_synced = False
    if gcs_available():
        gcs_synced = write_text(
            WELLNESS_PATH,
            json.dumps(records, ensure_ascii=False),
            content_type="application/json",
        )
    return {"stored_locally": len(records), "gcs_synced": gcs_synced}


def save_activities(records) -> dict:
    """Bewaar de volledige activiteitenlijst (bron voor de Activiteiten-tab).
    Schrijft lokaal en - indien beschikbaar - naar GCS.

    MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: zie save_wellness()
    hierboven - zelfde reden, zelfde vorm."""
    if not isinstance(records, list):
        return {"stored_locally": 0, "gcs_synced": False}
    _write_local_json(ACTIVITIES_FILE, records)
    gcs_synced = False
    if gcs_available():
        gcs_synced = write_text(
            ACTIVITIES_PATH,
            json.dumps(records, ensure_ascii=False),
            content_type="application/json",
        )
    return {"stored_locally": len(records), "gcs_synced": gcs_synced}


def mirror_wellness_to_local() -> int:
    """Haal wellness.json terug uit GCS naar lokaal (koude start op de cloud).
    Geeft het aantal teruggezette records terug, of 0 als GCS niet beschikbaar
    is of het object nog niet bestaat."""
    if not gcs_available():
        return 0
    text = read_text(WELLNESS_PATH)
    if not text:
        return 0
    try:
        records = json.loads(text)
    except (ValueError, TypeError):
        return 0
    if not isinstance(records, list):
        return 0
    _write_local_json(WELLNESS_FILE, records)
    return len(records)


def mirror_activities_to_local() -> int:
    """Haal activities.json terug uit GCS naar lokaal (koude start op de cloud)."""
    if not gcs_available():
        return 0
    text = read_text(ACTIVITIES_PATH)
    if not text:
        return 0
    try:
        records = json.loads(text)
    except (ValueError, TypeError):
        return 0
    if not isinstance(records, list):
        return 0
    _write_local_json(ACTIVITIES_FILE, records)
    return len(records)


def mirror_all_to_local() -> dict:
    """Spiegel history, wellness en activities in een keer terug naar lokaal.
    Dit is wat de Streamlit-app bij het laden moet aanroepen: voor deze fix
    werd enkel history gespiegeld, waardoor Recovery en Activiteiten op de
    cloud leeg bleven (zie moduledocstring)."""
    return {
        "history": mirror_history_to_local(),
        "wellness": mirror_wellness_to_local(),
        "activities": mirror_activities_to_local(),
    }


# --------------------------------------------------------------------------- #
# Activity streams (per activiteit een CSV)
# --------------------------------------------------------------------------- #
def save_stream_csv(activity_id: str, csv_text: str) -> None:
    activity_id = str(activity_id).strip()
    if not activity_id or not csv_text:
        return
    if gcs_available():
        if write_text(f"{STREAMS_PREFIX}{activity_id}.csv", csv_text, content_type="text/csv"):
            return
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)
    (STREAMS_DIR / f"{activity_id}.csv").write_text(csv_text, encoding="utf-8")


def load_stream_csv(activity_id: str) -> str | None:
    activity_id = str(activity_id).strip()
    if not activity_id:
        return None
    if gcs_available():
        text = read_text(f"{STREAMS_PREFIX}{activity_id}.csv")
        if text:
            return text
    path = STREAMS_DIR / f"{activity_id}.csv"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def has_stream(activity_id: str) -> bool:
    activity_id = str(activity_id).strip()
    if not activity_id:
        return False
    if gcs_available() and object_exists(f"{STREAMS_PREFIX}{activity_id}.csv"):
        return True
    return (STREAMS_DIR / f"{activity_id}.csv").exists()


def delete_stream(activity_id: str) -> None:
    activity_id = str(activity_id).strip()
    if not activity_id:
        return
    if gcs_available():
        delete_object(f"{STREAMS_PREFIX}{activity_id}.csv")
    path = STREAMS_DIR / f"{activity_id}.csv"
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
