from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(ROOT / "PadelAnalysis")
)

import firebase_service as fb

from AICoach.intervals.client import (
    IntervalsClient,
)

COLLECTION = "training_daily"


def main():

    client = IntervalsClient()

    summary = client.get_daily_summary()

    date_key = summary["date"]

    fb.db.collection(COLLECTION) \
        .document(date_key) \
        .set(summary)

    print()
    print("✅ Firestore update succesvol")
    print()
    print(f"Collection : {COLLECTION}")
    print(f"Document   : {date_key}")


if __name__ == "__main__":
    main()