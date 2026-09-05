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
