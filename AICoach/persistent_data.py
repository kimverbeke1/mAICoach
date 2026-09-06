# -*- coding: utf-8 -*-
"""Persistente cache voor mAICoach-data (history en activity streams) op GCS.

Op Streamlit Community Cloud is het bestandssysteem tijdelijk: data/history/*.json
en data/activity_streams/*.csv verdwijnen bij een herstart of slaap. Deze module
spiegelt die data naar Google Cloud Storage, met een automatische lokale fallback
wanneer GCS niet beschikbaar is.

Objectindeling in de bucket:
- history/<YYYY-MM-DD>.json
- activity_streams/<activity_id>.csv
"""

from __future__ import annotations

from pathlib import Path
import json

from AICoach.gcs_store import (
    delete_object,
    gcs_available,
    list_texts,
    object_exists,
    read_text,
    write_text,
)

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "history"
STREAMS_DIR = ROOT / "data" / "activity_streams"

HISTORY_PREFIX = "history/"
STREAMS_PREFIX = "activity_streams/"


def backend() -> str:
    """Geeft 'gcs' of 'lokaal' terug."""
    return "gcs" if gcs_available() else "lokaal"


# --------------------------------------------------------------------------- #
# History (per dag een JSON-object)
# --------------------------------------------------------------------------- #
def save_history_day(date_key: str, summary: dict) -> None:
    date_key = str(date_key)[:10]
    if not date_key:
        return
    if gcs_available():
        if write_text(
            f"{HISTORY_PREFIX}{date_key}.json",
            json.dumps(summary, ensure_ascii=False, indent=2),
            content_type="application/json",
        ):
            return
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_DIR / f"{date_key}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_history_bulk(summaries_by_date: dict) -> int:
    count = 0
    use_gcs = gcs_available()
    if not use_gcs:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    for date_key, summary in summaries_by_date.items():
        key = str(date_key)[:10]
        if not key:
            continue
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        if use_gcs:
            if not write_text(f"{HISTORY_PREFIX}{key}.json", text, content_type="application/json"):
                # Val terug op lokaal voor deze dag.
                HISTORY_DIR.mkdir(parents=True, exist_ok=True)
                (HISTORY_DIR / f"{key}.json").write_text(text, encoding="utf-8")
        else:
            (HISTORY_DIR / f"{key}.json").write_text(text, encoding="utf-8")
        count += 1
    return count


def load_history_records() -> list[dict]:
    """Lees alle history-dagen. GCS heeft voorrang, anders lokaal."""
    if gcs_available():
        items = list_texts(HISTORY_PREFIX)
        if items:
            records = []
            for name, text in items:
                if not name.endswith(".json"):
                    continue
                try:
                    payload = json.loads(text)
                except (ValueError, TypeError):
                    continue
                if isinstance(payload, dict):
                    payload.setdefault("date", Path(name).stem)
                    records.append(payload)
                elif isinstance(payload, list):
                    records.extend(item for item in payload if isinstance(item, dict))
            if records:
                records.sort(key=lambda item: str(item.get("date", "")))
                return records
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
    """Schrijf de GCS-history naar lokale JSON-bestanden.

    Zodat bestaande code die rechtstreeks data/history/*.json leest (zoals
    load_history in data_loaders) na een koude start toch werkt.
    """
    if not gcs_available():
        return 0
    items = list_texts(HISTORY_PREFIX)
    if not items:
        return 0
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, text in items:
        if not name.endswith(".json"):
            continue
        date_key = Path(name).stem[:10]
        if not date_key:
            continue
        (HISTORY_DIR / f"{date_key}.json").write_text(text, encoding="utf-8")
        count += 1
    return count


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
