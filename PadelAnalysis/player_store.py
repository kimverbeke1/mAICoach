# -*- coding: utf-8 -*-
"""
player_store.py
---------------
PadelAnalysis - Persistente opslag van spelerdossiers in Firestore.

Doel: een speler wordt MAXIMAAL 1 keer gescrapet (binnen de TTL). Daarna
komt alles uit Firestore, zodat de tegenstanderanalyse instant opent.

Publieke API:
    get_db()                          -> Firestore client
    get_player(name)                  -> dict | None   (uit Firestore)
    save_player(data)                 -> str (doc id)
    is_stale(data)                    -> bool
    ensure_player(name, url, force)   -> (dict | None, status)
        status in {"cache", "scraped", "refreshed", "failed", "no_scraper"}
    bulk_ensure(names, ...)           -> dict[name] = (data, status)

Collectie: PLAYER_COLLECTION (default "players").
Document-id: player_id (geslugificeerde naam als er geen id is).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import streamlit as st
except Exception:  # buiten Streamlit bruikbaar
    st = None  # type: ignore

import player_scrape_adapter as adapter

PLAYER_COLLECTION = "players"
SCRAPE_TTL_DAYS = 21


# ---------------------------------------------------------------------------
# Firestore
# ---------------------------------------------------------------------------

_db = None


def get_db():
    """Firestore client; hergebruikt bestaande helper indien aanwezig."""
    global _db
    if _db is not None:
        return _db

    import importlib
    for mod_name, fn_name in [
        ("PadelAnalysis.firestore_client", "get_db"),
        ("PadelAnalysis.storage", "get_db"),
        ("firestore_client", "get_db"),
        ("padel_store", "get_db"),
        ("db", "get_db"),
    ]:
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                _db = fn()
                return _db
        except Exception:
            continue

    from google.cloud import firestore
    from google.oauth2 import service_account

    info = None
    if st is not None:
        for key in ("firestore", "gcp_service_account", "FIREBASE_CREDENTIALS", "firebase"):
            if key in st.secrets:
                val = st.secrets[key]
                info = json.loads(val) if isinstance(val, str) else dict(val)
                break

    if info:
        creds = service_account.Credentials.from_service_account_info(info)
        _db = firestore.Client(credentials=creds, project=info.get("project_id"))
    else:
        _db = firestore.Client()
    return _db


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


# ---------------------------------------------------------------------------
# Lezen
# ---------------------------------------------------------------------------

def get_player(name: str) -> Optional[Dict[str, Any]]:
    """Haal een spelerdossier op via document-id of via naamvergelijking."""
    db = get_db()
    doc_id = slug(name)

    try:
        snap = db.collection(PLAYER_COLLECTION).document(doc_id).get()
        if snap.exists:
            return {**snap.to_dict(), "_doc_id": snap.id}
    except Exception:
        pass

    try:
        for d in db.collection(PLAYER_COLLECTION).where("name", "==", name).limit(1).stream():
            return {**d.to_dict(), "_doc_id": d.id}
    except Exception:
        pass

    # laatste redmiddel: volledige scan met losse naamvergelijking
    try:
        target = slug(name)
        for d in db.collection(PLAYER_COLLECTION).limit(3000).stream():
            data = d.to_dict() or {}
            if slug(data.get("name") or data.get("naam") or "") == target:
                return {**data, "_doc_id": d.id}
    except Exception:
        pass
    return None


def is_stale(data: Optional[Dict[str, Any]]) -> bool:
    """True als de speler nog nooit volledig gescrapet is of te oud is."""
    if not data:
        return True
    if not data.get("ranking_history") and not data.get("matches"):
        return True  # enkel ranking bekend -> onvolledig dossier
    last = data.get("last_scraped") or data.get("scraped_at")
    if not last:
        return True
    try:
        dt = _dt.datetime.fromisoformat(str(last).replace("Z", ""))
    except ValueError:
        return True
    return (_dt.datetime.utcnow() - dt).days > SCRAPE_TTL_DAYS


# ---------------------------------------------------------------------------
# Schrijven
# ---------------------------------------------------------------------------

def save_player(data: Dict[str, Any]) -> str:
    db = get_db()
    doc_id = str(data.get("player_id") or slug(data.get("name", "")))
    payload = {k: v for k, v in data.items() if not k.startswith("_")}
    payload["player_id"] = doc_id
    payload.setdefault("last_scraped", _dt.datetime.utcnow().isoformat(timespec="seconds"))
    db.collection(PLAYER_COLLECTION).document(doc_id).set(payload, merge=True)
    return doc_id


# ---------------------------------------------------------------------------
# Kern: cache-or-scrape
# ---------------------------------------------------------------------------

def ensure_player(name: str, url: Optional[str] = None,
                  force: bool = False) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Geef een volledig spelerdossier terug.
      * bestaat en vers  -> ("cache")
      * ontbreekt/oud    -> scrapen + opslaan ("scraped" / "refreshed")
      * scrape faalt     -> bestaande data of None ("failed" / "no_scraper")
    """
    existing = get_player(name)

    if existing and not force and not is_stale(existing):
        return existing, "cache"

    try:
        fresh = adapter.scrape_player(name, url=url or (existing or {}).get("profile_url"))
    except adapter.ScraperNotFound:
        return existing, "no_scraper"
    except Exception:
        return existing, "failed"

    if not fresh:
        return existing, "failed"

    merged: Dict[str, Any] = {**(existing or {})}
    for key, value in fresh.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    merged.setdefault("name", name)

    # bestaande ranking niet verliezen als de scrape er geen vond
    if not merged.get("current_ranking") and existing:
        merged["current_ranking"] = (existing.get("current_ranking")
                                     or existing.get("ranking")
                                     or existing.get("klassement"))

    try:
        save_player(merged)
    except Exception:
        pass  # tonen mag nooit blokkeren op een schrijffout

    return merged, ("refreshed" if existing else "scraped")


def bulk_ensure(names: List[str], urls: Optional[Dict[str, str]] = None,
                force: bool = False, progress=None) -> Dict[str, Tuple[Optional[Dict[str, Any]], str]]:
    """Zorg dat een hele ploeg gescrapet/gecachet is. `progress(i, n, name)` optioneel."""
    urls = urls or {}
    out: Dict[str, Tuple[Optional[Dict[str, Any]], str]] = {}
    total = len(names)
    for i, name in enumerate(names, start=1):
        if progress:
            progress(i, total, name)
        out[name] = ensure_player(name, url=urls.get(name), force=force)
    return out
