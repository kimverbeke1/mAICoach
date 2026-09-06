from pathlib import Path

ROOT = Path.cwd()

files = {

    "AICoach/storage/__init__.py": "",

    "AICoach/storage/snapshot_manager.py": '''
import json
from pathlib import Path
from datetime import datetime


class SnapshotManager:

    def __init__(self):

        self.snapshot_dir = Path("data/snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def save(self, data):

        today = datetime.now().strftime("%Y-%m-%d")

        filename = self.snapshot_dir / f"{today}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

        return filename
''',

    "AICoach/snapshots/create_snapshot.py": '''
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
'''
}

for filename, content in files.items():

    path = ROOT / filename

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        content.strip() + "\n",
        encoding="utf-8"
    )

print()
print("✅ Snapshot module aangemaakt")
print()