from AICoach.intervals.client import IntervalsClient


def main():

    client = IntervalsClient()

    activities = client.get_activities(
        days=30
    )

    print()
    print("=" * 60)
    print("LAATSTE ACTIVITEITEN")
    print("=" * 60)
    print()

    print(
        f"Aantal activiteiten: {len(activities)}"
    )

    print()

    for idx, activity in enumerate(
        activities[:20],
        start=1,
    ):

        print(
            f"{idx:2d}. "
            f"{activity.get('start_date_local')} | "
            f"{activity.get('type')} | "
            f"{activity.get('name')}"
        )

    print()
    print("=" * 60)
    print()

    newest = activities[0]

    print("MEEST RECENTE ACTIVITEIT")
    print()

    print(
        "Datum:",
        newest.get("start_date_local")
    )

    print(
        "Naam:",
        newest.get("name")
    )

    print(
        "Type:",
        newest.get("type")
    )

    print(
        "Training Load:",
        newest.get("icu_training_load")
    )

    print(
        "Fitness:",
        newest.get("icu_ctl")
    )

    print(
        "Fatigue:",
        newest.get("icu_atl")
    )

    print()


if __name__ == "__main__":
    main()