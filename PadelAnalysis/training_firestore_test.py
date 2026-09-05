from datetime import datetime
import firebase_service as fb

COLLECTION = "training_snapshots"

today = datetime.now().strftime("%Y-%m-%d")

snapshot = {
    "date": today,
    "fitness": 25,
    "fatigue": 42,
    "form": -17,
    "source": "test",
    "created_at": datetime.utcnow().isoformat()
}

print("Connecting to Firestore...")

try:
    # write
    fb.db.collection(COLLECTION).document(today).set(snapshot)

    print("✅ Snapshot saved")

    # read back
    doc = (
        fb.db.collection(COLLECTION)
        .document(today)
        .get()
    )

    if doc.exists:
        print("✅ Snapshot read back")

        data = doc.to_dict()

        print("")
        print("Stored document:")
        print(data)

    else:
        print("❌ Document not found")

except Exception as e:
    print("")
    print("❌ ERROR")
    print(type(e).__name__)
    print(e)