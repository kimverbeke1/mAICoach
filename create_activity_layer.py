from pathlib import Path

ROOT = Path.cwd()

files = {}

files["AICoach/intervals/activities.py"] = r'''
from datetime import datetime, timedelta

from AICoach.intervals.client import IntervalsClient


class ActivityService:

    def __init__(self):
        self.client = IntervalsClient()

    def get_last_30_days(self):

        oldest = (
            datetime.now() - timedelta(days=30)
        ).strftime("%Y-%m-%d")

        return self.client.get_activities(
            oldest=oldest
        )
'''

files["AICoach/training_summary.py"] = r'''
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
'''

for filename, content in files.items():

    path = ROOT / filename

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        content.strip() + "\n",
        encoding="utf-8"
    )

    print("written:", filename)

print()
print("✅ ACTIVITY LAYER GENERATED")
print()