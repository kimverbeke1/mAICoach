from datetime import datetime
from pathlib import Path
import json

from dotenv import load_dotenv

load_dotenv()

from AICoach.intervals.client import IntervalsClient


def save_snapshot(data: dict) -> Path:

    snapshot_dir = Path("data/snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d")

    filename = snapshot_dir / f"{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

    return filename


def main():

    client = IntervalsClient()

    athlete = client.get_athlete()

    filename = save_snapshot(athlete)

    print()
    print("✅ Snapshot opgeslagen")
    print(filename)
    print()


if __name__ == "__main__":
    main()