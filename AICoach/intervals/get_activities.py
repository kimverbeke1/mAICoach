from AICoach.intervals.client import IntervalsClient


def main():

    client = IntervalsClient()

    activities = client.get_activities(
        days=30
    )

    print()
    print("ACTIVITIES:", len(activities))
    print()

    if not activities:
        return

    activity = activities[0]

    print("BESCHIKBARE VELDEN")
    print("=" * 60)

    for key in sorted(activity.keys()):
        print(key)

    print()
    print("EERSTE ACTIVITEIT")
    print("=" * 60)

    for key, value in activity.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()