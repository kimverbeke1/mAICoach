# -*- coding: utf-8 -*-
"""Firestore-clientfabriek voor mAICoach.

Levert een Firestore-client op basis van service-account credentials. Werkt op
drie manieren, in volgorde van voorrang:

1. Streamlit Secrets: een tabel [gcp_service_account] met de service-account JSON.
2. Omgevingsvariabele GOOGLE_APPLICATION_CREDENTIALS die naar een JSON-bestand wijst.
3. Application Default Credentials (bijv. lokaal via gcloud).

Als Firestore niet beschikbaar is (pakket ontbreekt of geen credentials), geeft
get_firestore_client() None terug, zodat de aanroeper kan terugvallen op lokale opslag.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

from AICoach.app_config import get_secret


def _credentials_from_streamlit():
    """Bouw service-account credentials uit Streamlit Secrets, indien aanwezig."""
    try:
        import streamlit as st
    except Exception:  # noqa: BLE001
        return None
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        info = dict(st.secrets["gcp_service_account"])
    except Exception:  # noqa: BLE001
        return None
    try:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_info(info)
    except Exception:  # noqa: BLE001
        return None


def _credentials_from_env_file():
    path = get_secret("GOOGLE_APPLICATION_CREDENTIALS")
    if not path or not os.path.exists(path):
        return None
    try:
        from google.oauth2 import service_account

        with open(path, "r", encoding="utf-8") as handle:
            info = json.load(handle)
        return service_account.Credentials.from_service_account_info(info)
    except Exception:  # noqa: BLE001
        return None


@lru_cache(maxsize=1)
def get_firestore_client():
    """Geef een Firestore-client of None als Firestore niet beschikbaar is."""
    try:
        from google.cloud import firestore
    except Exception:  # noqa: BLE001 - pakket niet geïnstalleerd
        return None

    project = get_secret("GCP_PROJECT_ID") or get_secret("FIRESTORE_PROJECT_ID")

    credentials = _credentials_from_streamlit() or _credentials_from_env_file()
    try:
        if credentials is not None:
            if project:
                return firestore.Client(project=project, credentials=credentials)
            return firestore.Client(credentials=credentials)
        # Val terug op Application Default Credentials.
        if project:
            return firestore.Client(project=project)
        return firestore.Client()
    except Exception:  # noqa: BLE001 - geen geldige credentials
        return None


def firestore_available() -> bool:
    return get_firestore_client() is not None
