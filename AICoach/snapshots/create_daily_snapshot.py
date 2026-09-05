from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from AICoach.intervals.client import IntervalsClient
from AICoach.storage.snapshot_manager import SnapshotManager


def build_snapshot(athlete):

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "athlete_id": athlete.get("id"),
        "name": athlete.get("name"),
        "resting_hr": athlete.get("icu_resting_hr"),
        "weight": athlete.get("icu_weight"),
        "sex": athlete.get("sex"),
        "timezone": athlete.get("timezone"),
        "last_seen": athlete.get("icu_last_seen")
    }


def main():

    client = IntervalsClient()

    athlete = client.get_athlete()

    snapshot = build_snapshot(athlete)

    manager = SnapshotManager()

    filename = manager.save(snapshot)

    print()
    print("✅ Daily snapshot opgeslagen")
    print(filename)
    print(snapshot)
    print()


if __name__ == "__main__":
    main()