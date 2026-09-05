from datetime import date, timedelta
from pathlib import Path
import json
import os

from dotenv import load_dotenv

from AICoach.intervals.client import IntervalsClient


load_dotenv(".env", override=True)

ROOT = Path(__file__).resolve().parents[1]
WELLNESS_DIR = ROOT / "data" / "wellness"
WELLNESS_FILE = WELLNESS_DIR / "wellness.json"
DEFAULT_HISTORY_DAYS = 730


def history_days():
    try:
        return max(int(os.getenv("INTERVALS_HISTORY_DAYS", "730")), 30)
    except ValueError:
        return DEFAULT_HISTORY_DAYS


def load_existing():
    if not WELLNESS_FILE.exists():
        return []
    try:
        with WELLNESS_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def record_date(record):
    return str(
        record.get("id")
        or record.get("date")
        or record.get("start_date")
        or ""
    )[:10]


def merge(existing, downloaded):
    records = {}
    for item in existing + downloaded:
        if not isinstance(item, dict):
            continue
        key = record_date(item)
        if key:
            records[key] = item
    return [records[key] for key in sorted(records)]


def save(records):
    WELLNESS_DIR.mkdir(parents=True, exist_ok=True)
    temporary_file = WELLNESS_FILE.with_suffix(".tmp")
    with temporary_file.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    temporary_file.replace(WELLNESS_FILE)


def sync_wellness_history():
    days = history_days()
    oldest = (date.today() - timedelta(days=days)).isoformat()
    newest = date.today().isoformat()

    downloaded = IntervalsClient().get_wellness(
        oldest=oldest,
        newest=newest,
    )
    records = merge(load_existing(), downloaded)
    save(records)

    return {
        "oldest": oldest,
        "newest": newest,
        "downloaded": len(downloaded),
        "stored": len(records),
        "output_file": str(WELLNESS_FILE),
        "fields": sorted({key for item in records for key in item}),
    }


def main():
    result = sync_wellness_history()
    print()
    print("WELLNESS HISTORY SYNC")
    print("=" * 60)
    print(f"Periode: {result['oldest']} tot {result['newest']}")
    print(f"Gedownload: {result['downloaded']}")
    print(f"Opgeslagen: {result['stored']}")
    print(f"Bestand: {result['output_file']}")
    print("Beschikbare velden:")
    for field in result["fields"]:
        print(f"- {field}")
    print()


if __name__ == "__main__":
    main()
