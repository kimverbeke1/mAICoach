from pathlib import Path

ROOT = Path.cwd()

CLIENT_FILE = ROOT / "AICoach" / "intervals" / "client.py"

client_code = '''
from dotenv import load_dotenv
import requests
import os
from datetime import date, timedelta

load_dotenv(".env", override=True)


class IntervalsClient:

    BASE_URL = "https://intervals.icu/api/v1"

    def __init__(self):

        self.api_key = os.getenv("INTERVALS_API_KEY")
        self.athlete_id = os.getenv("INTERVALS_ATHLETE_ID")

        if not self.api_key:
            raise ValueError("INTERVALS_API_KEY ontbreekt")

        if not self.athlete_id:
            raise ValueError("INTERVALS_ATHLETE_ID ontbreekt")

        self.session = requests.Session()
        self.session.auth = (
            "API_KEY",
            self.api_key
        )

    def get_athlete(self):

        url = (
            f"{self.BASE_URL}"
            f"/athlete/{self.athlete_id}"
        )

        response = self.session.get(url)

        response.raise_for_status()

        return response.json()

    def get_activities(self, days=30):

        oldest = (
            date.today()
            - timedelta(days=days)
        ).isoformat()

        url = (
            f"{self.BASE_URL}"
            f"/athlete/{self.athlete_id}"
            f"/activities"
            f"?oldest={oldest}"
        )

        response = self.session.get(url)

        response.raise_for_status()

        return response.json()

    def get_latest_activity(self):

        activities = self.get_activities(days=30)

        if not activities:
            return None

        return activities[0]

    def get_daily_summary(self):

        activity = self.get_latest_activity()

        if not activity:
            return {}

        return {
            "date": str(activity.get("start_date_local", ""))[:10],
            "activity_name": activity.get("name"),
            "activity_type": activity.get("type"),
            "fitness": activity.get("icu_ctl"),
            "fatigue": activity.get("icu_atl"),
            "training_load": activity.get("icu_training_load"),
            "resting_hr": activity.get("icu_resting_hr"),
            "weight": activity.get("icu_weight"),
            "rpe": activity.get("icu_rpe"),
            "feel": activity.get("feel"),
            "hr_load": activity.get("hr_load"),
            "strain_score": activity.get("strain_score"),
        }


if __name__ == "__main__":

    client = IntervalsClient()

    summary = client.get_daily_summary()

    print()
    print("=== DAILY SUMMARY ===")
    print()

    for key, value in summary.items():
        print(f"{key}: {value}")
'''

CLIENT_FILE.write_text(
    client_code.strip(),
    encoding="utf-8"
)

print()
print("✅ client.py vervangen")
print(CLIENT_FILE)