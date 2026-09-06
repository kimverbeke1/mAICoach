# -*- coding: utf-8 -*-
"""Persistente opslag van bewaarde inzichten voor mAICoach.

Bewaart conclusies uit de AI Coach of de dagelijkse update, leest ze terug en
verwijdert ze. Werkt met twee backends:

- Google Cloud Storage (persistent, ook op Streamlit Community Cloud) wanneer er
  credentials en een bucket beschikbaar zijn. Alle inzichten staan in één
  JSON-object: saved_insights/saved_insights.json.
- Lokaal JSON-bestand (data/saved_insights.json) als fallback.

De publieke functies (load_saved_insights, save_insight, delete_insight,
render_saved_insights) blijven identiek, zodat de rest van de app niets merkt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

import streamlit as st

from AICoach.gcs_store import gcs_available, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
STORE_FILE = ROOT / "data" / "saved_insights.json"
GCS_PATH = "saved_insights/saved_insights.json"


# --------------------------------------------------------------------------- #
# Lokale JSON-backend (fallback)
# --------------------------------------------------------------------------- #
def _local_load() -> list[dict]:
    if not STORE_FILE.exists():
        return []
    try:
        payload = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _local_write(records: list[dict]) -> None:
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = STORE_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_file.replace(STORE_FILE)


# --------------------------------------------------------------------------- #
# GCS-backend (persistent)
# --------------------------------------------------------------------------- #
def _gcs_load() -> list[dict] | None:
    if not gcs_available():
        return None
    payload = read_json(GCS_PATH)
    if payload is None:
        # Geen object nog aanwezig: behandel als lege, bestaande lijst.
        return []
    return payload if isinstance(payload, list) else []


def _gcs_write(records: list[dict]) -> bool:
    if not gcs_available():
        return False
    return write_json(GCS_PATH, records)


# --------------------------------------------------------------------------- #
# Publieke API
# --------------------------------------------------------------------------- #
def storage_backend() -> str:
    """Geeft 'gcs' of 'lokaal' terug, handig voor een statusmelding."""
    return "gcs" if gcs_available() else "lokaal"


def load_saved_insights() -> list[dict]:
    records = _gcs_load()
    if records is None:
        records = _local_load()
    records.sort(key=lambda item: str(item.get("saved_at", "")), reverse=True)
    return records


def save_insight(content: str, source: str = "AI Coach", title: str = "") -> dict:
    content = (content or "").strip()
    if not content:
        return {}
    record = {
        "id": uuid.uuid4().hex,
        "title": title.strip() or content.splitlines()[0][:80],
        "content": content,
        "source": source,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if gcs_available():
        records = _gcs_load() or []
        records.append(record)
        if not _gcs_write(records):
            # Val terug op lokaal als schrijven onverwacht faalt.
            local = _local_load()
            local.append(record)
            _local_write(local)
    else:
        records = _local_load()
        records.append(record)
        _local_write(records)
    return record


def delete_insight(insight_id: str) -> None:
    if gcs_available():
        records = _gcs_load() or []
        records = [item for item in records if item.get("id") != insight_id]
        _gcs_write(records)
    else:
        records = [item for item in _local_load() if item.get("id") != insight_id]
        _local_write(records)


def _date_label(value) -> str:
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return "onbekend"


def render_saved_insights() -> None:
    st.markdown("### Bewaarde inzichten")
    backend = storage_backend()
    st.caption(
        "Opslag: Google Cloud Storage (blijft bewaard na herstart)."
        if backend == "gcs"
        else "Opslag: lokaal bestand (kan verdwijnen bij een cloud-herstart)."
    )

    records = load_saved_insights()
    if not records:
        st.caption(
            "Nog geen inzichten bewaard. Bewaar conclusies via de AI Coach "
            "of de dagelijkse update om ze hier te verzamelen."
        )
        return

    for record in records:
        header = (
            f"{record.get('title') or 'Inzicht'}  ·  "
            f"{record.get('source', '')}  ·  {_date_label(record.get('saved_at'))}"
        )
        with st.expander(header):
            st.markdown(record.get("content", ""))
            if st.button("Verwijderen", key=f"delete_insight_{record.get('id')}"):
                delete_insight(record.get("id"))
                st.rerun()
