# -*- coding: utf-8 -*-
from datetime import date, timedelta
import io

import pandas as pd
import requests

from AICoach.app_config import require_secret


class IntervalsClient:
    BASE_URL = "https://intervals.icu/api/v1"

    def __init__(self):
        # Werkt lokaal (.env) en op Streamlit Cloud (st.secrets) via app_config.
        self.api_key = require_secret("INTERVALS_API_KEY")
        self.athlete_id = require_secret("INTERVALS_ATHLETE_ID")
        self.session = requests.Session()
        self.session.auth = ("API_KEY", self.api_key)
        self.session.headers.update({"Accept": "application/json"})

    def _request(self, method, path, params=None, accept=None):
        headers = {"Accept": accept} if accept else None
        response = self.session.request(
            method,
            f"{self.BASE_URL}{path}",
            params=params,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        return response

    def _get(self, path, params=None):
        return self._request("GET", path, params=params).json()

    @staticmethod
    def normalize_activity_id(activity_id):
        value = str(activity_id or "").strip()
        if not value:
            raise ValueError("Activity-id ontbreekt")
        return value

    def get_athlete(self):
        return self._get(f"/athlete/{self.athlete_id}")

    def get_activities(self, days=30, oldest=None, newest=None):
        if oldest is None:
            oldest = (date.today() - timedelta(days=days)).isoformat()
        if newest is None:
            newest = date.today().isoformat()
        payload = self._get(
            f"/athlete/{self.athlete_id}/activities",
            params={"oldest": oldest, "newest": newest},
        )
        return payload if isinstance(payload, list) else []

    def get_wellness(self, days=30, oldest=None, newest=None):
        if oldest is None:
            oldest = (date.today() - timedelta(days=days)).isoformat()
        if newest is None:
            newest = date.today().isoformat()
        payload = self._get(
            f"/athlete/{self.athlete_id}/wellness",
            params={"oldest": oldest, "newest": newest},
        )
        return payload if isinstance(payload, list) else []

    def get_activity_streams_csv(self, activity_id):
        activity_id = self.normalize_activity_id(activity_id)
        response = self._request(
            "GET",
            f"/activity/{activity_id}/streams.csv",
            accept="text/csv",
        )
        return response.text

    def get_activity_streams_frame(self, activity_id):
        csv_text = self.get_activity_streams_csv(activity_id)
        if not csv_text.strip():
            return pd.DataFrame()
        return pd.read_csv(io.StringIO(csv_text))

    def get_latest_activity(self):
        activities = self.get_activities(days=30)
        if not activities:
            return None
        return max(activities, key=lambda item: str(item.get("start_date", "")))

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
    print(client.get_daily_summary())
