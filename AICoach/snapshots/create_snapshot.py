from dotenv import load_dotenv

load_dotenv()

from AICoach.intervals.client import IntervalsClient
from AICoach.storage.snapshot_manager import SnapshotManager


def main():

    client = IntervalsClient()

    athlete = client.get_athlete()

    manager = SnapshotManager()

    filename = manager.save(athlete)

    print()
    print("Snapshot opgeslagen:")
    print(filename)
    print()


if __name__ == "__main__":
    main()
