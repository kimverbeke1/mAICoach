from collections import Counter

from AICoach.intervals.activities import ActivityService


def main():

    service = ActivityService()

    activities = service.get_last_30_days()

    print()
    print("TOTAL ACTIVITIES:", len(activities))
    print()

    sport_counter = Counter()

    for activity in activities:

        sport = (
            activity.get("type")
            or activity.get("sport")
            or "UNKNOWN"
        )

        sport_counter[sport] += 1

    print("SPORT DISTRIBUTION")
    print("=" * 50)

    for sport, count in sport_counter.most_common():

        print(
            f"{sport}: {count}"
        )

    print()

    if activities:

        print("FIRST ACTIVITY KEYS")
        print("=" * 50)

        for key in sorted(
            activities[0].keys()
        ):
            print(key)

        print()


if __name__ == "__main__":
    main()
