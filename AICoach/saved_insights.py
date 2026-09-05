# -*- coding: utf-8 -*-
"""Download Intervals.icu activity streams naar een lokale CSV-cache.

Secrets/credentials verlopen via IntervalsClient (app_config), dus dit script
werkt zowel lokaal (.env) als op Streamlit Community Cloud (st.secrets).

Let op: op Streamlit Community Cloud is de schijf tijdelijk. De CSV-cache in
data/activity_streams kan bij een herstart verdwijnen en wordt dan opnieuw
opgehaald. Dat is functioneel, maar niet permanent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

import requests

from AICoach.intervals.client import IntervalsClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVITIES_FILE = PROJECT_ROOT / "data" / "activities" / "activities.json"
STREAMS_DIR = PROJECT_ROOT / "data" / "activity_streams"
DEFAULT_PAUSE_SECONDS = 0.15


def load_activities() -> list[dict[str, Any]]:
    if not ACTIVITIES_FILE.exists():
        # Op de cloud kan het bestand nog ontbreken bij een koude start;
        # geef dan een lege lijst terug in plaats van hard te falen.
        return []
    try:
        with ACTIVITIES_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ongeldige JSON in activiteitenbestand: {ACTIVITIES_FILE}") from exc

    if isinstance(payload, list):
        activities = payload
    elif isinstance(payload, dict):
        activities = payload.get("activities", payload.get("data", []))
    else:
        activities = []

    if not isinstance(activities, list):
        raise ValueError("Het activiteitenbestand bevat geen lijst met activiteiten.")

    return [
        activity
        for activity in activities
        if isinstance(activity, dict) and activity.get("id")
    ]


def stream_path(activity_id: str) -> Path:
    safe_id = str(activity_id).replace("/", "_").replace("\\", "_")
    return STREAMS_DIR / f"{safe_id}.csv"


def activity_sort_value(activity: dict[str, Any]) -> str:
    return str(
        activity.get("start_date_local")
        or activity.get("start_date")
        or activity.get("date")
        or ""
    )


def has_streams(activity: dict[str, Any]) -> bool:
    stream_types = activity.get("stream_types")
    if isinstance(stream_types, list):
        return len(stream_types) > 0
    return True


def download_stream(
    client: IntervalsClient,
    activity: dict[str, Any],
    overwrite: bool = False,
) -> dict[str, Any]:
    activity_id = str(activity["id"])
    destination = stream_path(activity_id)

    if destination.exists() and destination.stat().st_size > 0 and not overwrite:
        return {
            "activity_id": activity_id,
            "status": "skipped",
            "path": str(destination.relative_to(PROJECT_ROOT)),
            "bytes": destination.stat().st_size,
        }

    if not has_streams(activity):
        return {"activity_id": activity_id, "status": "no_streams", "path": None, "bytes": 0}

    # Consistent met de IntervalsClient-API (secrets via app_config).
    try:
        csv_text = client.get_activity_streams_csv(activity_id)
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code == 404:
            return {"activity_id": activity_id, "status": "not_found", "path": None, "bytes": 0}
        raise

    if not csv_text.strip():
        return {"activity_id": activity_id, "status": "empty", "path": None, "bytes": 0}

    content = csv_text.encode("utf-8")
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)

    return {
        "activity_id": activity_id,
        "status": "downloaded",
        "path": str(destination.relative_to(PROJECT_ROOT)),
        "bytes": len(content),
    }


def download_activity_streams(
    activity_id: str | None = None,
    overwrite: bool = False,
    limit: int | None = None,
    pause: float = DEFAULT_PAUSE_SECONDS,
) -> dict[str, Any]:
    STREAMS_DIR.mkdir(parents=True, exist_ok=True)
    activities = load_activities()
    activities.sort(key=activity_sort_value, reverse=True)

    if activity_id:
        activities = [
            activity
            for activity in activities
            if str(activity.get("id")) == str(activity_id)
        ]
        if not activities:
            raise ValueError(f"Activiteit {activity_id} staat niet in {ACTIVITIES_FILE}.")

    if limit is not None:
        if limit < 0:
            raise ValueError("limit mag niet negatief zijn.")
        activities = activities[:limit]

    client = IntervalsClient()
    results: list[dict[str, Any]] = []

    for index, activity in enumerate(activities, start=1):
        activity_name = str(activity.get("name") or activity.get("id"))
        activity_key = str(activity.get("id"))
        print(f"[{index}/{len(activities)}] {activity_name} ({activity_key})")
        try:
            result = download_stream(client=client, activity=activity, overwrite=overwrite)
        except requests.RequestException as exc:
            result = {
                "activity_id": activity_key,
                "status": "error",
                "path": None,
                "bytes": 0,
                "error": str(exc),
            }
        results.append(result)
        print(f"  {result['status']}")
        if index < len(activities) and pause > 0:
            time.sleep(pause)

    counts: dict[str, int] = {}
    for result in results:
        status = str(result["status"])
        counts[status] = counts.get(status, 0) + 1

    return {
        "streams_directory": str(STREAMS_DIR.relative_to(PROJECT_ROOT)),
        "activities_considered": len(activities),
        "counts": counts,
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Intervals.icu activity streams naar lokale CSV-cache."
    )
    parser.add_argument("--activity-id", help="Download slechts een activiteit-id.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Download bestaande streambestanden opnieuw.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Beperk het aantal te verwerken activiteiten.",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=DEFAULT_PAUSE_SECONDS,
        help="Pauze tussen API-calls in seconden.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = download_activity_streams(
            activity_id=args.activity_id,
            overwrite=args.overwrite,
            limit=args.limit,
            pause=args.pause,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FOUT: {exc}")
        return 1

    print()
    print("ACTIVITY STREAMS VOLTOOID")
    print("=" * 60)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    error_count = summary.get("counts", {}).get("error", 0)
    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())
