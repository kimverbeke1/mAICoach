"""
Intervals.icu API client voor MatchFitAI - TrainingData module.

Haalt wellness data (fitness/fatigue/form/load/HRV/rust-HR) en activiteiten op
via de officiele Intervals.icu REST API.

Auth: Basic Auth met username "API_KEY" en de persoonlijke API-key als password.
Docs: https://intervals.icu/api-docs.html
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

BASE_URL = "https://intervals.icu/api/v1"


@dataclass
class WellnessRecord:
    """Een dagelijkse wellness-entry uit Intervals.icu."""

    date: str
    ctl: float | None = None          # Fitness (Chronic Training Load)
    atl: float | None = None          # Fatigue (Acute Training Load)
    form: float | None = None         # Form / TSB (ctl - atl)
    ramp_rate: float | None = None
    resting_hr: int | None = None
    hrv: float | None = None
    weight: float | None = None
    sleep_secs: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "WellnessRecord":
        ctl = raw.get("ctl")
        atl = raw.get("atl")
        form = raw.get("form")
        if form is None and ctl is not None and atl is not None:
            form = round(ctl - atl, 1)
        return cls(
            date=raw.get("id") or raw.get("date"),
            ctl=ctl,
            atl=atl,
            form=form,
            ramp_rate=raw.get("rampRate"),
            resting_hr=raw.get("restingHR"),
            hrv=raw.get("hrv"),
            weight=raw.get("weight"),
            sleep_secs=raw.get("sleepSecs"),
        )


class IntervalsIcuClient:
    """Kleine wrapper rond de Intervals.icu REST API voor een enkele atleet."""

    def __init__(self, athlete_id: str | None = None, api_key: str | None = None):
        self.athlete_id = athlete_id or os.environ["INTERVALS_ATHLETE_ID"]
        self.api_key = api_key or os.environ["INTERVALS_API_KEY"]
        self._auth = HTTPBasicAuth("API_KEY", self.api_key)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{BASE_URL}{path}"
        resp = requests.get(url, auth=self._auth, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_wellness(self, oldest: date, newest: date) -> list[WellnessRecord]:
        """Haal dagelijkse wellness-data op (fitness/fatigue/form/HRV/rust-HR/...)."""
        raw = self._get(
            f"/athlete/{self.athlete_id}/wellness",
            params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        )
        return [WellnessRecord.from_api(r) for r in raw]

    def get_activities(self, oldest: date, newest: date) -> list[dict[str, Any]]:
        """Haal activiteiten op (trainingen) tussen twee data."""
        return self._get(
            "/athlete/" + self.athlete_id + "/activities",
            params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        )

    def get_recent_wellness(self, days: int = 30) -> list[WellnessRecord]:
        newest = date.today()
        oldest = newest - timedelta(days=days)
        return self.get_wellness(oldest, newest)

    def get_recent_activities(self, days: int = 30) -> list[dict[str, Any]]:
        newest = date.today()
        oldest = newest - timedelta(days=days)
        return self.get_activities(oldest, newest)
