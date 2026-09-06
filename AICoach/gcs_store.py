# -*- coding: utf-8 -*-
"""Google Cloud Storage-laag voor mAICoach.

Levert een GCS-bucket op basis van service-account credentials en een bucketnaam.
Werkt in deze volgorde:
1. Streamlit Secrets: [gcp_service_account] (JSON-velden) + GCS_BUCKET.
2. Omgevingsvariabele GOOGLE_APPLICATION_CREDENTIALS (pad naar JSON) + GCS_BUCKET.
3. Application Default Credentials + GCS_BUCKET.

Als GCS niet beschikbaar is (pakket ontbreekt, geen credentials of geen bucket),
geeft get_bucket() None terug, zodat de aanroeper terugvalt op lokale opslag.

Objecten worden als tekst opgeslagen (JSON of CSV) onder eenvoudige prefixes.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

from AICoach.app_config import get_secret


def _credentials_from_streamlit():
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


def _bucket_name():
    return get_secret("GCS_BUCKET") or get_secret("GCS_BUCKET_NAME")


@lru_cache(maxsize=1)
def get_bucket():
    """Geef een GCS-bucket of None als GCS niet beschikbaar is."""
    bucket_name = _bucket_name()
    if not bucket_name:
        return None
    try:
        from google.cloud import storage
    except Exception:  # noqa: BLE001 - pakket niet geïnstalleerd
        return None

    project = get_secret("GCP_PROJECT_ID") or get_secret("GCS_PROJECT_ID")
    credentials = _credentials_from_streamlit() or _credentials_from_env_file()
    try:
        if credentials is not None:
            client = storage.Client(project=project, credentials=credentials) if project else storage.Client(credentials=credentials)
        else:
            client = storage.Client(project=project) if project else storage.Client()
        return client.bucket(bucket_name)
    except Exception:  # noqa: BLE001
        return None


def gcs_available() -> bool:
    return get_bucket() is not None


# --------------------------------------------------------------------------- #
# Object-helpers (tekst)
# --------------------------------------------------------------------------- #
def read_text(path: str):
    """Lees een tekstobject uit de bucket; None als het niet bestaat of faalt."""
    bucket = get_bucket()
    if bucket is None:
        return None
    try:
        blob = bucket.blob(path)
        if not blob.exists():
            return None
        return blob.download_as_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def write_text(path: str, text: str, content_type: str = "text/plain") -> bool:
    """Schrijf een tekstobject naar de bucket. Geeft True bij succes."""
    bucket = get_bucket()
    if bucket is None:
        return False
    try:
        blob = bucket.blob(path)
        blob.upload_from_string(text, content_type=content_type)
        return True
    except Exception:  # noqa: BLE001
        return False


def read_json(path: str):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def write_json(path: str, payload) -> bool:
    return write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json",
    )


def delete_object(path: str) -> bool:
    bucket = get_bucket()
    if bucket is None:
        return False
    try:
        blob = bucket.blob(path)
        if blob.exists():
            blob.delete()
        return True
    except Exception:  # noqa: BLE001
        return False


def list_texts(prefix: str):
    """Geef (naam, tekst) voor alle objecten onder een prefix, of None bij falen."""
    bucket = get_bucket()
    if bucket is None:
        return None
    try:
        results = []
        for blob in bucket.list_blobs(prefix=prefix):
            if blob.name.endswith("/"):
                continue
            results.append((blob.name, blob.download_as_text(encoding="utf-8")))
        return results
    except Exception:  # noqa: BLE001
        return None


def object_exists(path: str) -> bool:
    bucket = get_bucket()
    if bucket is None:
        return False
    try:
        return bucket.blob(path).exists()
    except Exception:  # noqa: BLE001
        return False
