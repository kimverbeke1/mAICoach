import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

PADEL_PATH = ROOT / "PadelAnalysis"

sys.path.insert(0, str(PADEL_PATH))

import firebase_service as fb

COLLECTION = "training_snapshots"


def main():

    snapshot_dir = ROOT / "data" / "snapshots"

    latest = sorted(snapshot_dir.glob("*.json"))[-1]

    print(f"Snapshot laden: {latest}")

    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Gebruik bestandsnaam als document id
    date_key = latest.stem

    print(f"Firestore document id: {date_key}")

    fb.db.collection(COLLECTION) \
        .document(date_key) \
        .set(data)

    print("")
    print("✅ Firestore update succesvol")
    print(f"Collectie : {COLLECTION}")
    print(f"Document  : {date_key}")


if __name__ == "__main__":
    main()