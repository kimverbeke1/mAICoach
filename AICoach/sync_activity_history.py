from datetime import date, timedelta
from pathlib import Path
import json
import os

from dotenv import load_dotenv

from AICoach.intervals.client import IntervalsClient


load_dotenv(".env", override=True)

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY_DIR = ROOT / "data" / "activities"
ACTIVITY_FILE = ACTIVITY_DIR / "activities.json"

DEFAULT_HISTORY_DAYS = 730


def configured_history_days():
    raw_value = os.getenv(
        "INTERVALS_HISTORY_DAYS",
        str(DEFAULT_HISTORY_DAYS),
    )

    try:
        days = int(raw_value)
    except ValueError:
        return DEFAULT_HISTORY_DAYS

    return max(days, 30)


def load_existing_activities():
    if not ACTIVITY_FILE.exists():
        return []

    try:
        with ACTIVITY_FILE.open(
            "r",
            encoding="utf-8",
        ) as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    return [
        activity
        for activity in payload
        if isinstance(activity, dict)
    ]


def merge_activities(existing, downloaded):
    merged = {}

    for activity in existing + downloaded:
        activity_id = activity.get("id")

        if activity_id is None:
            activity_id = (
                f"{activity.get('start_date', '')}:"
                f"{activity.get('type', '')}:"
                f"{activity.get('name', '')}"
            )

        merged[str(activity_id)] = activity

    return sorted(
        merged.values(),
        key=lambda activity: str(
            activity.get("start_date", "")
        ),
    )


def save_activities(activities):
    ACTIVITY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = ACTIVITY_FILE.with_suffix(
        ".tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            activities,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    temporary_file.replace(ACTIVITY_FILE)


def sync_activity_history():
    days = configured_history_days()
    oldest = (
        date.today() - timedelta(days=days)
    ).isoformat()
    newest = date.today().isoformat()

    client = IntervalsClient()
    downloaded = client.get_activities(
        oldest=oldest,
        newest=newest,
    )

    existing = load_existing_activities()
    merged = merge_activities(
        existing,
        downloaded,
    )
    save_activities(merged)

    return {
        "oldest": oldest,
        "newest": newest,
        "downloaded": len(downloaded),
        "stored": len(merged),
        "output_file": str(ACTIVITY_FILE),
    }


def main():
    result = sync_activity_history()

    print()
    print("ACTIVITY HISTORY SYNC")
    print("=" * 60)
    print(f"Periode vanaf: {result['oldest']}")
    print(f"Periode tot: {result['newest']}")
    print(f"Gedownload: {result['downloaded']}")
    print(f"Lokaal opgeslagen: {result['stored']}")
    print(f"Bestand: {result['output_file']}")
    print()


if __name__ == "__main__":
    main()
