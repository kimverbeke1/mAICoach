# -*- coding: utf-8 -*-
"""Persistente cloudopslag voor mAICoach (Google Cloud Storage).

Op Streamlit Community Cloud is het lokale bestandssysteem tijdelijk: bij een
herstart of na de slaapstand verdwijnt alles onder data/. Deze module bewaart
de belangrijke bestanden (history, activity_streams, activities, wellness,
bewaarde inzichten) in een GCS-bucket en haalt ze bij het opstarten terug.

Configuratie (Streamlit Cloud -> App settings -> Secrets):

    GCS_BUCKET = "jouw-bucket-naam"

    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "...@...iam.gserviceaccount.com"
    client_id = "..."
    token_uri = "https://oauth2.googleapis.com/token"

Lokaal kun je in plaats daarvan GOOGLE_APPLICATION_CREDENTIALS naar een
service-account JSON laten wijzen en GCS_BUCKET als omgevingsvariabele zetten.

Als er geen configuratie is, werkt de app gewoon lokaal verder (geen fouten):
alle functies zijn dan een veilige no-op.
"""

from __future__ import annotations

from pathlib import Path
import os

_CLIENT = None
_BUCKET = None
_CHECKED = False


def _load_bucket():
    """Init de GCS-bucket één keer; geeft None als opslag niet is geconfigureerd."""
    global _CLIENT, _BUCKET, _CHECKED
    if _CHECKED:
        return _BUCKET
    _CHECKED = True

    bucket_name = _get_config("GCS_BUCKET")
    if not bucket_name:
        return None

    try:
        from google.cloud import storage
        from google.oauth2 import service_account
    except Exception:  # noqa: BLE001 - package niet aanwezig -> lokaal blijven
        return None

    info = _service_account_info()
    try:
        if info:
            credentials = service_account.Credentials.from_service_account_info(info)
            _CLIENT = storage.Client(credentials=credentials, project=info.get("project_id"))
        else:
            # Valt terug op GOOGLE_APPLICATION_CREDENTIALS / default credentials.
            _CLIENT = storage.Client()
        _BUCKET = _CLIENT.bucket(bucket_name)
    except Exception:  # noqa: BLE001
        _BUCKET = None
    return _BUCKET


def _get_config(name: str):
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # noqa: BLE001
        return None
    return None


def _service_account_info():
    """Haal de service-account als dict uit st.secrets, indien aanwezig."""
    try:
        import streamlit as st

        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:  # noqa: BLE001
        return None
    return None


def is_enabled() -> bool:
    return _load_bucket() is not None


def download_file(remote_name: str, local_path: Path) -> bool:
    """Download één blob naar een lokaal pad. Geeft True bij succes."""
    bucket = _load_bucket()
    if bucket is None:
        return False
    try:
        blob = bucket.blob(remote_name)
        if not blob.exists():
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))
        return True
    except Exception:  # noqa: BLE001
        return False


def upload_file(local_path: Path, remote_name: str) -> bool:
    """Upload één lokaal bestand naar de bucket. Geeft True bij succes."""
    bucket = _load_bucket()
    if bucket is None or not local_path.exists():
        return False
    try:
        bucket.blob(remote_name).upload_from_filename(str(local_path))
        return True
    except Exception:  # noqa: BLE001
        return False


def download_prefix(prefix: str, local_dir: Path) -> int:
    """Download alle blobs onder een prefix naar een lokale map. Geeft aantal terug."""
    bucket = _load_bucket()
    if bucket is None:
        return 0
    count = 0
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        for blob in bucket.list_blobs(prefix=prefix):
            name = blob.name[len(prefix):].lstrip("/")
            if not name:
                continue
            target = local_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(target))
            count += 1
    except Exception:  # noqa: BLE001
        return count
    return count


def upload_dir(local_dir: Path, prefix: str, pattern: str = "*", skip_existing: bool = True) -> int:
    """Upload alle bestanden uit een map naar een prefix. Geeft aantal geüpload terug.

    Met skip_existing worden blobs met dezelfde naam en grootte overgeslagen,
    zodat alleen nieuwe of gewijzigde bestanden verstuurd worden.
    """
    bucket = _load_bucket()
    if bucket is None or not local_dir.exists():
        return 0

    existing = {}
    if skip_existing:
        try:
            for blob in bucket.list_blobs(prefix=prefix):
                existing[blob.name] = blob.size
        except Exception:  # noqa: BLE001
            existing = {}

    count = 0
    try:
        for path in sorted(local_dir.glob(pattern)):
            if not path.is_file():
                continue
            remote_name = f"{prefix.rstrip('/')}/{path.name}"
            if skip_existing and existing.get(remote_name) == path.stat().st_size:
                continue
            bucket.blob(remote_name).upload_from_filename(str(path))
            count += 1
    except Exception:  # noqa: BLE001
        return count
    return count
