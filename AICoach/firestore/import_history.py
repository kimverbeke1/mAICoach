from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]

# bestaande Firebase connectie van PadelAnalysis gebruiken
PADEL_PATH = ROOT / "PadelAnalysis"

sys.path.insert(0, str(PADEL_PATH))

import firebase_service as fb

COLLECTION = "training_daily"


def main():

    history_dir = ROOT / "data" / "history"

    if not history_dir.exists():
        raise FileNotFoundError(
            f"Map niet gevonden: {history_dir}"
        )

    files = sorted(
        history_dir.glob("*.json")
    )

    print()
    print(f"Files gevonden: {len(files)}")
    print()

    count = 0

    for file in files:

        try:

            with open(
                file,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            date_key = (
                data.get("date")
                or file.stem
            )

            # Firestore document id
            date_key = str(date_key)[:10]

            fb.db.collection(COLLECTION) \
                .document(date_key) \
                .set(data)

            count += 1

            print(
                f"✅ {date_key}"
            )

        except Exception as e:

            print(
                f"❌ {file.name}: {e}"
            )

    print()
    print("=" * 40)
    print(f"Import klaar")
    print(f"Collection : {COLLECTION}")
    print(f"Records    : {count}")
    print("=" * 40)
    print()


if __name__ == "__main__":
    main()