# -*- coding: utf-8 -*-
"""Persistente cache voor mAICoach-data (history en activity streams).

Op Streamlit Community Cloud is het bestandssysteem tijdelijk: data/history/*.json
en data/activity_streams/*.csv verdwijnen bij een herstart of slaap. Deze module
spiegelt die data naar Firestore, zodat ze een koude start overleven, met een
automatische lokale fallback wanneer Firestore niet beschikbaar is.

Backends:
- Firestore (persistent): collecties 'history' en 'activity_streams'.
- Lokaal bestandssysteem (fallback): data/history/*.json en
  data/activity_streams/*.csv.

De publieke functies zijn bewust generiek zodat sync_latest en de detailweergave
ze kunnen gebruiken zonder de rest van de app te wijzigen.
"""

from __future__ import annotations

from pathlib import Path
import json

from AICoach.firestore_store import get_firestore_client

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "history"
STREAMS_DIR = ROOT / "data" / "activity_streams"

HISTORY_COLLECTION = "history"
STREAMS_COLLECTION = "activity_streams"


# --------------------------------------------------------------------------- #
# Firestore helpers
# --------------------------------------------------------------------------- #
def _collection(name):
    client = get_firestore_client()
    if client is None:
        return None
    try:
        return client.collection(name)
    except Exception:  # noqa: BLE001
        return None


def backend() -> str:
    """Geeft 'firestore' of 'lokaal' terug."""
    return "firestore" if get_firestore_client() is not None else "lokaal"


# --------------------------------------------------------------------------- #
# History (per dag een JSON-record)
# --------------------------------------------------------------------------- #
def save_history_day(date_key: str, summary: dict) -> None:
    """Bewaar één dag-samenvatting, naar Firestore of lokaal."""
    date_key = str(date_key)[:10]
    if not date_key:
        return
    collection = _collection(HISTORY_COLLECTION)
    if collection is not None:
        try:
            collection.document(date_key).set(dict(summary))
            return
        except Exception:  # noqa: BLE001
            pass
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_DIR / f"{date_key}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_history_bulk(summaries_by_date: dict) -> int:
    """Bewaar meerdere dagen in één keer. Geeft het aantal opgeslagen dagen terug."""
    collection = _collection(HISTORY_COLLECTION)
    if collection is not None:
        client = get_firestore_client()
        try:
            batch = client.batch()
            count = 0
            for date_key, summary in summaries_by_date.items():
                key = str(date_key)[:10]
                if not key:
                    continue
                batch.set(collection.document(key), dict(summary))
                count += 1
                # Firestore batch-limiet is 500 bewerkingen.
                if count % 450 == 0:
                    batch.commit()
                    batch = client.batch()
            batch.commit()
            return count
        except Exception:  # noqa: BLE001
            pass
    # Lokale fallback.
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for date_key, summary in summaries_by_date.items():
        key = str(date_key)[:10]
        if not key:
            continue
        (HISTORY_DIR / f"{key}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        count += 1
    return count


def load_history_records() -> list[dict]:
    """Lees alle history-dagen. Firestore heeft voorrang, anders lokaal."""
    collection = _collection(HISTORY_COLLECTION)
    if collection is not None:
        try:
            records = []
            for document in collection.stream():
                data = document.to_dict() or {}
                data.setdefault("date", document.id)
                records.append(data)
            if records:
                records.sort(key=lambda item: str(item.get("date", "")))
                return records
        except Exception:  # noqa: BLE001
            pass
    # Lokale fallback.
    records = []
    if HISTORY_DIR.exists():
        for path in sorted(HISTORY_DIR.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append(payload)
            elif isinstance(payload, list):
                records.extend(item for item in payload if isinstance(item, dict))
    return records


def mirror_history_to_local() -> int:
    """Schrijf de Firestore-history naar lokale JSON-bestanden.

    Handig zodat bestaande code die rechtstreeks data/history/*.json leest
    (zoals load_history in data_loaders) na een koude start toch werkt.
    """
    collection = _collection(HISTORY_COLLECTION)
    if collection is None:
        return 0
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for document in collection.stream():
            data = document.to_dict() or {}
            date_key = str(data.get("date") or document.id)[:10]
            if not date_key:
                continue
            (HISTORY_DIR / f"{date_key}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            count += 1
        return count
    except Exception:  # noqa: BLE001
        return 0


# --------------------------------------------------------------------------- #
# Activity streams (per activiteit een CSV)
# --------------------------------------------------------------------------- #
def save_stream_csv(activity_id: str, csv_text: str) -> None:
    """Bewaar de stream-CSV van één activiteit."""
    activity_id = str(activity_id).strip()
    if not activity_id or not csv_text:
        return
    collection = _collection(STREAMS_COLLECTION)
    if collection is not None:
        try:
            collection.document(activity_id).set({"csv": csv_text})
            return
        except Exception:  # noqa: BLE001
            pass
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)
    (STREAMS_DIR / f"{activity_id}.csv").write_text(csv_text, encoding="utf-8")


def load_stream_csv(activity_id: str) -> str | None:
    """Lees de stream-CSV van één activiteit; None als die niet bestaat."""
    activity_id = str(activity_id).strip()
    if not activity_id:
        return None
    collection = _collection(STREAMS_COLLECTION)
    if collection is not None:
        try:
            document = collection.document(activity_id).get()
            if document.exists:
                data = document.to_dict() or {}
                text = data.get("csv")
                if text:
                    return text
        except Exception:  # noqa: BLE001
            pass
    # Lokale fallback.
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
    collection = _collection(STREAMS_COLLECTION)
    if collection is not None:
        try:
            return collection.document(activity_id).get().exists
        except Exception:  # noqa: BLE001
            pass
    return (STREAMS_DIR / f"{activity_id}.csv").exists()
