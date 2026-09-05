from datetime import datetime, timedelta

from AICoach.firestore.firestore_service import (
    get_latest_training_date,
    save_training_record,
)

from AICoach.intervals.activities import (
    ActivityService,
)


def main():

    print()
    print("=== MATCHFIT AI SYNC ===")
    print()

    latest_date = get_latest_training_date()

    if latest_date:

        print(
            f"Laatste Firestore datum: {latest_date}"
        )

        start_date = (
            datetime.strptime(
                latest_date,
                "%Y-%m-%d"
            )
            + timedelta(days=1)
        )

    else:

        print(
            "Geen records gevonden"
        )

        start_date = (
            datetime.now()
            - timedelta(days=30)
        )

    oldest = start_date.strftime(
        "%Y-%m-%d"
    )

    print(
        f"Ophalen vanaf: {oldest}"
    )
    print()

    activities = ActivityService() \
        .get_activities_since(
            oldest
        )

    print(
        f"Ontvangen activiteiten: "
        f"{len(activities)}"
    )

    imported = 0

    for activity in activities:

        record = {
            "date": activity.get("date"),
            "activity_name": activity.get(
                "activity_name"
            ),
            "activity_type": activity.get(
                "activity_type"
            ),
            "fitness": activity.get(
                "fitness"
            ),
            "fatigue": activity.get(
                "fatigue"
            ),
            "training_load": activity.get(
                "training_load"
            ),
            "resting_hr": activity.get(
                "resting_hr"
            ),
            "weight": activity.get(
                "weight"
            ),
        }

        save_training_record(
            record
        )

        imported += 1

    print()
    print(
        f"✅ Nieuwe records: {imported}"
    )
    print()


if __name__ == "__main__":
    main()