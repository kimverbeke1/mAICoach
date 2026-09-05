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
