# -*- coding: utf-8 -*-
#gcs_store.py
"""Google Cloud Storage-laag voor mAICoach.

Levert een GCS-bucket op basis van service-account credentials en een bucketnaam.
Werkt in deze volgorde:
1. Streamlit Secrets: [gcp_service_account] (JSON-velden) + GCS_BUCKET.
2. Omgevingsvariabele GOOGLE_APPLICATION_CREDENTIALS (pad naar JSON) + GCS_BUCKET.
3. Application Default Credentials + GCS_BUCKET.

Als GCS niet beschikbaar is (pakket ontbreekt, geen credentials of geen bucket),
geeft get_bucket() None terug, zodat de aanroeper terugvalt op lokale opslag.

Objecten worden als tekst opgeslagen (JSON of CSV) onder eenvoudige prefixes.

--------------------------------------------------------------------------
MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24 (op verzoek van Kim, na een
concreet incident: "ik zie dit: You can use Cloud Storage after you enable
billing" - de GitHub Actions-sync liep intussen al weken succesvol door en
rapporteerde "persisted: 152" / "persisted: 731", terwijl er in werkelijkheid
NOOIT iets in GCS terechtkwam)
--------------------------------------------------------------------------
ROOT CAUSE: get_bucket() vangt ELKE fout af (verkeerde credentials, ontbrekend
project, GEEN ACTIEVE FACTURERING, netwerkfout, ...) en geeft in alle gevallen
gewoon None terug. gcs_available() rapporteert dan simpelweg False, en de
aanroepers in persistent_data.py (save_wellness/save_activities/
save_history_bulk) sloegen het GCS-gedeelte dan stil over - ze bleven wel het
aantal LOKAAL geschreven records teruggeven, wat sync_latest.py in de
GitHub Actions-log liet zien als "persisted: 152". Dat cijfer klopte dus wel
voor de lokale schijf van de (nadien vernietigde) runner, maar zei niets over
GCS. Vandaar dat de workflow keer op keer "succesvol" leek terwijl er intussen
al weken geen data meer overleefde tot de volgende cold start.

FIX, twee nieuwe, PUUR ADDITIEVE functies (bestaand gedrag verandert niet):
  1. diagnose() - reconstrueert dezelfde stappen als get_bucket(), maar VANGT
     de effectieve foutmelding op i.p.v. ze weg te gooien. Dat is wat nu voor
     het eerst zichtbaar maakt "billing not enabled" i.p.v. enkel een stille
     lege terugval.
  2. clear_bucket_cache() - get_bucket() is een @lru_cache(maxsize=1): eenmaal
     None (bv. tijdens de billing-storing), blijft dat gecached voor de
     resterende levensduur van het PROCES - ook nadat facturering hersteld is.
     Op Streamlit Community Cloud, waar het proces dagenlang kan doorlopen,
     betekende dat: facturering herstellen loste niets op tot de volgende
     herstart. clear_bucket_cache() geeft training_dashboard.py's "Nu
     verversen"-knop een manier om dat zonder herstart te forceren.

persistent_data.py roept diagnose() aan om een eerlijk "gcs_synced"-veld terug
te geven i.p.v. het misleidende, louter-lokale recordaantal als succes te
presenteren. Zie de toelichting daar voor de volledige keten.
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
    """Geef een GCS-bucket of None als GCS niet beschikbaar is.

    LET OP (zie MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24 hierboven): dit
    resultaat wordt PROCESBREED gecached. Is de terugval ooit None geweest
    (bv. tijdens een tijdelijke storing), dan blijft dat zo tot het proces
    herstart of clear_bucket_cache() expliciet aangeroepen wordt - ook als
    de onderliggende oorzaak (credentials, facturering, netwerk) intussen
    opgelost is.
    """
    bucket_name = _bucket_name()
    if not bucket_name:
        return None
    try:
        from google.cloud import storage
    except Exception:  # noqa: BLE001 - pakket niet geinstalleerd
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


def clear_bucket_cache() -> None:
    """MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: wist de lru_cache van
    get_bucket(), zodat een herstelde storing (bv. facturering opnieuw
    ingeschakeld) zonder herstart van het Streamlit-proces effect heeft.
    Veilig om te allen tijde aan te roepen - een lege cache wordt gewoon
    opnieuw opgebouwd bij de eerstvolgende get_bucket()-aanroep."""
    get_bucket.cache_clear()


def diagnose() -> dict:
    """MATCHFITAI_GCS_SILENT_FAILURE_FIX_2026-09-24: geeft de WERKELIJKE
    status van de GCS-verbinding terug, inclusief de foutmelding die
    get_bucket() intern wegvangt. Puur diagnostisch - roept nergens
    get_bucket() zelf aan en raakt dus de bestaande cache niet aan.

    Bedoeld voor gebruik in sync_latest.py (zichtbare waarschuwing in de
    GitHub Actions-log i.p.v. een misleidend "succesvolle" run) en in
    training_dashboard.py (een uitlegbare foutmelding i.p.v. stilzwijgend
    niets doen).

    Returns een dict met:
        bucket_name        : de geconfigureerde bucketnaam, of None.
        package_installed   : is google-cloud-storage importeerbaar?
        credentials_source  : "streamlit_secrets" / "env_file" /
                              "application_default" / None.
        available           : True als een bucket-object opgebouwd kon
                              worden (zegt niets over lees-/schrijfrechten
                              op objectniveau, enkel over de verbinding).
        error               : de laatst opgevangen foutmelding, of None.
    """
    result = {
        "bucket_name": _bucket_name(),
        "package_installed": False,
        "credentials_source": None,
        "available": False,
        "error": None,
    }

    if not result["bucket_name"]:
        result["error"] = "Geen GCS_BUCKET (of GCS_BUCKET_NAME) geconfigureerd."
        return result

    try:
        from google.cloud import storage
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"google-cloud-storage niet geinstalleerd/importeerbaar: {exc}"
        return result
    result["package_installed"] = True

    credentials = _credentials_from_streamlit()
    if credentials is not None:
        result["credentials_source"] = "streamlit_secrets"
    else:
        credentials = _credentials_from_env_file()
        if credentials is not None:
            result["credentials_source"] = "env_file"
        else:
            result["credentials_source"] = "application_default"

    project = get_secret("GCP_PROJECT_ID") or get_secret("GCS_PROJECT_ID")
    try:
        if credentials is not None:
            client = storage.Client(project=project, credentials=credentials) if project else storage.Client(credentials=credentials)
        else:
            client = storage.Client(project=project) if project else storage.Client()
        bucket = client.bucket(result["bucket_name"])
        # Een lichte, echte aanroep i.p.v. enkel het object construeren -
        # dat laatste slaagt namelijk ALTIJD, ongeacht facturering/rechten.
        bucket.exists()
        result["available"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


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
