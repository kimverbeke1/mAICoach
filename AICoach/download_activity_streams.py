# -*- coding: utf-8 -*-
"""Download en persisteer activity streams voor mAICoach.

Haalt per activiteit de streams-CSV op via Intervals.icu en bewaart die zowel
lokaal (data/activity_streams/*.csv) als in Firestore (via persistent_data),
zodat ze een cloud-herstart overleven. Bestaande streams worden niet opnieuw
gedownload, tenzij force=True.
"""

from __future__ import annotations

from pathlib import Path
import json

from AICoach.intervals.client import IntervalsClient
from AICoach.persistent_data import has_stream, load_stream_csv, save_stream_csv

ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = ROOT / "data" / "activities" / "activities.json"
STREAMS_DIR = ROOT / "data" / "activity_streams"


def _load_activities():
    if not ACTIVITIES_FILE.exists():
        return []
    try:
        payload = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("activities", payload.get("data", []))
    return payload if isinstance(payload, list) else []


def _activity_ids():
    ids = []
    for record in _load_activities():
        if isinstance(record, dict) and record.get("id") is not None:
            ids.append(str(record["id"]))
    return ids


def ensure_local_stream(activity_id: str):
    """Zorg dat de stream-CSV lokaal beschikbaar is; herstel uit Firestore indien nodig."""
    activity_id = str(activity_id).strip()
    if not activity_id:
        return None
    local_path = STREAMS_DIR / f"{activity_id}.csv"
    if local_path.exists():
        return local_path
    csv_text = load_stream_csv(activity_id)
    if csv_text:
        STREAMS_DIR.mkdir(parents=True, exist_ok=True)
        local_path.write_text(csv_text, encoding="utf-8")
        return local_path
    return None


def download_activity_streams(force: bool = False, max_activities: int | None = None):
    client = IntervalsClient()
    ids = _activity_ids()
    if max_activities is not None:
        ids = ids[:max_activities]

    STREAMS_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    restored = 0
    skipped = 0
    failed = 0

    for activity_id in ids:
        local_path = STREAMS_DIR / f"{activity_id}.csv"

        if not force and local_path.exists():
            skipped += 1
            continue

        # Al in Firestore? Herstel lokaal zonder opnieuw te downloaden.
        if not force and has_stream(activity_id):
            if ensure_local_stream(activity_id) is not None:
                restored += 1
                continue

        try:
            csv_text = client.get_activity_streams_csv(activity_id)
        except Exception:  # noqa: BLE001 - één activiteit mag de rest niet blokkeren
            failed += 1
            continue

        if not csv_text or not csv_text.strip():
            failed += 1
            continue

        local_path.write_text(csv_text, encoding="utf-8")
        save_stream_csv(activity_id, csv_text)
        downloaded += 1

    return {
        "total": len(ids),
        "downloaded": downloaded,
        "restored_from_firestore": restored,
        "skipped_existing": skipped,
        "failed": failed,
    }


def main():
    result = download_activity_streams()
    print()
    print("ACTIVITY STREAMS")
    print("=" * 60)
    for name, value in result.items():
        print(f"{name}: {value}")
    print()


if __name__ == "__main__":
    main()
