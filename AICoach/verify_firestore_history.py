from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

PADEL_PATH = ROOT / "PadelAnalysis"

sys.path.insert(0, str(PADEL_PATH))

import firebase_service as fb

COLLECTION = "training_daily"


def main():

    docs = list(
        fb.db.collection(COLLECTION).stream()
    )

    print()
    print("=== FIRESTORE VERIFY ===")
    print()

    print(f"Collectie : {COLLECTION}")
    print(f"Records    : {len(docs)}")
    print()

    if not docs:
        print("❌ Geen records gevonden")
        return

    sorted_docs = sorted(
        docs,
        key=lambda d: d.id,
        reverse=True,
    )

    print("=== LAATSTE 5 RECORDS ===")
    print()

    for doc in sorted_docs[:5]:

        data = doc.to_dict()

        print(f"Document : {doc.id}")
        print(f"Fitness  : {data.get('fitness')}")
        print(f"Fatigue  : {data.get('fatigue')}")
        print(f"Load     : {data.get('training_load')}")
        print(f"HR Rest  : {data.get('resting_hr')}")
        print(f"Weight   : {data.get('weight')}")
        print("-" * 40)

    print()
    print("✅ Verificatie voltooid")
    print()


if __name__ == "__main__":
    main()