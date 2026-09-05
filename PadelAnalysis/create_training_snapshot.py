from datetime import datetime
import firebase_service as fb

COLLECTION = "training_snapshots"


def create_test_snapshot():
    today = datetime.now().strftime("%Y-%m-%d")

    snapshot = {
        "date": today,
        "fitness": 25,
        "fatigue": 42,
        "form": -17,
        "source": "manual_test",
        "created_at": datetime.utcnow().isoformat()
    }

    print(f"Writing snapshot for {today}...")

    fb.db.collection(COLLECTION) \
        .document(today) \
        .set(snapshot)

    print("✅ Snapshot saved")

    doc = (
        fb.db.collection(COLLECTION)
        .document(today)
        .get()
    )

    if doc.exists:
        print("")
        print("✅ Snapshot loaded back")
        print("")
        print(doc.to_dict())
    else:
        print("❌ Snapshot not found after save")


if __name__ == "__main__":
    create_test_snapshot()