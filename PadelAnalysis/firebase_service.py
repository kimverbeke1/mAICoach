import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, firestore

SERVICE_ACCOUNT_FILE = "firebase-key.json"
PLAYERS_COLLECTION = "players"
PLAYER_SEARCH_CACHE_COLLECTION = "player_search_cache"
PLAYER_PROFILES_COLLECTION = "player_profiles"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def convert_firestore_values(obj: Any):
    if isinstance(obj, dict):
        return {k: convert_firestore_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_firestore_values(v) for v in obj]
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    return obj


def sanitize_for_firestore(obj: Any):
    if isinstance(obj, dict):
        return {str(k): sanitize_for_firestore(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_firestore(v) for v in obj]
    if isinstance(obj, tuple):
        return [sanitize_for_firestore(v) for v in obj]
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    return obj


def normalize_name(name: str) -> str:
    return " ".join((name or "").lower().split()).strip()


def normalize_search_key(name_query: str, club: Optional[str] = None, sport: str = "Padel") -> str:
    return f"{(sport or '').strip().lower()}|{normalize_name(name_query)}|{normalize_name(club or '')}"


def build_minimal_defaults(player_id: str, player_data: dict) -> dict:
    data = dict(player_data or {})
    data.setdefault("player_id", str(player_id))
    data.setdefault("last_updated", utc_now_iso())
    data.setdefault("stats", {})
    data.setdefault("raw_data", {})
    raw = dict(data.get("raw_data", {}))
    raw.setdefault("player_id", str(player_id))
    raw.setdefault("timestamp", utc_now_iso())
    raw.setdefault("matches", [])
    raw.setdefault("matches_count", len(raw.get("matches", [])) if isinstance(raw.get("matches", []), list) else 0)
    data["raw_data"] = raw
    stats = dict(data.get("stats", {}))
    stats.setdefault("matches", raw.get("matches_count", 0))
    stats.setdefault("wins", 0)
    stats.setdefault("losses", 0)
    stats.setdefault("unknown_results", 0)
    stats.setdefault("winrate", 0.0)
    data["stats"] = stats
    return data


def _load_streamlit_secrets_credentials() -> Optional[credentials.Certificate]:
    try:
        import streamlit as st
        if "firebase" not in st.secrets:
            return None
        firebase_cfg = dict(st.secrets["firebase"])
        if "private_key" in firebase_cfg:
            firebase_cfg["private_key"] = str(firebase_cfg["private_key"]).replace("\\n", "\n")
        return credentials.Certificate(firebase_cfg)
    except Exception:
        return None


def _load_local_file_credentials() -> Optional[credentials.Certificate]:
    candidate_paths = [
        SERVICE_ACCOUNT_FILE,
        os.path.join(os.path.dirname(__file__), SERVICE_ACCOUNT_FILE),
        os.path.join(os.path.dirname(__file__), "scraper", SERVICE_ACCOUNT_FILE),
    ]
    for candidate in candidate_paths:
        if os.path.exists(candidate):
            return credentials.Certificate(candidate)
    return None


def _init_firebase():
    if firebase_admin._apps:
        return firestore.client()
    cred = _load_streamlit_secrets_credentials() or _load_local_file_credentials()
    if cred is None:
        raise FileNotFoundError("Geen Firebase credentials gevonden. Gebruik lokaal firebase-key.json of Streamlit secrets met [firebase].")
    firebase_admin.initialize_app(cred)
    return firestore.client()


db = _init_firebase()


def save_player(player_id: str, player_data: dict):
    prepared = sanitize_for_firestore(build_minimal_defaults(player_id, player_data))
    db.collection(PLAYERS_COLLECTION).document(str(player_id)).set(prepared, merge=False)
    return prepared


def get_player(player_id: str, converted: bool = True):
    doc = db.collection(PLAYERS_COLLECTION).document(str(player_id)).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    return convert_firestore_values(data) if converted else data


def save_player_profile(player_id: str, display_name: Optional[str] = None, club: Optional[str] = None, sport: str = "Padel", dashboard_url: Optional[str] = None, aliases: Optional[List[str]] = None):
    doc = {
        "player_id": str(player_id),
        "display_name": display_name,
        "display_name_normalized": normalize_name(display_name or ""),
        "club": club,
        "club_normalized": normalize_name(club or ""),
        "sport": sport,
        "dashboard_url": dashboard_url,
        "aliases": aliases or [],
        "aliases_normalized": [normalize_name(a) for a in (aliases or []) if a],
        "last_updated": utc_now_iso(),
    }
    db.collection(PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(sanitize_for_firestore(doc), merge=True)
    return doc


def get_player_profile(player_id: str, converted: bool = True):
    doc = db.collection(PLAYER_PROFILES_COLLECTION).document(str(player_id)).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    return convert_firestore_values(data) if converted else data


def get_app_settings() -> dict:
    """Klein settings-document, o.a. wie 'jij' bent (home_player_id)."""
    doc = db.collection("app_settings").document("main").get()
    return doc.to_dict() if doc.exists else {}


def save_app_settings(data: dict):
    db.collection("app_settings").document("main").set(sanitize_for_firestore(data), merge=True)


def search_player_profiles(name_query: str, club: Optional[str] = None, limit: int = 20, converted: bool = True):
    name_q = normalize_name(name_query)
    club_q = normalize_name(club or "")
    docs = db.collection(PLAYER_PROFILES_COLLECTION).stream()
    out = []
    for doc in docs:
        data = doc.to_dict() or {}
        names = [data.get("display_name_normalized", "")] + (data.get("aliases_normalized", []) or [])
        clubs = data.get("club_normalized", "")
        name_match = (not name_q) or any(name_q in n for n in names)
        club_match = (not club_q) or (club_q in clubs)
        if name_match and club_match:
            out.append(convert_firestore_values(data) if converted else data)
    out = sorted(out, key=lambda x: (x.get("display_name") or x.get("player_id") or ""))
    return out[:limit]


def save_player_search_cache(name_query: str, club: Optional[str], sport: str, candidates: List[Dict[str, Any]]):
    key = normalize_search_key(name_query, club, sport)
    doc = {
        "search_key": key,
        "name_query": name_query,
        "club": club,
        "sport": sport,
        "last_updated": utc_now_iso(),
        "candidate_count": len(candidates),
        "candidates": sanitize_for_firestore(candidates),
    }
    db.collection(PLAYER_SEARCH_CACHE_COLLECTION).document(key).set(doc, merge=False)
    return doc


def get_player_search_cache(name_query: str, club: Optional[str] = None, sport: str = "Padel", converted: bool = True):
    key = normalize_search_key(name_query, club, sport)
    doc = db.collection(PLAYER_SEARCH_CACHE_COLLECTION).document(key).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    return convert_firestore_values(data) if converted else data


def save_player_v2(player_id: str, player_data: dict):
    """Save v2 schema player data directly, skipping legacy build_minimal_defaults."""
    prepared = sanitize_for_firestore(dict(player_data))
    prepared["player_id"] = str(player_id)
    if "last_updated" not in prepared:
        prepared["last_updated"] = utc_now_iso()
    db.collection(PLAYERS_COLLECTION).document(str(player_id)).set(prepared, merge=False)
    return prepared

def delete_player(player_id: str) -> dict:
    pid = str(player_id)
    db.collection(PLAYER_PROFILES_COLLECTION).document(pid).delete()
    db.collection(PLAYERS_COLLECTION).document(pid).delete()
    settings = get_app_settings()
    if str(settings.get("home_player_id") or "") == pid:
        save_app_settings({"home_player_id": None})
    return {"player_id": pid, "deleted_from": [PLAYER_PROFILES_COLLECTION, PLAYERS_COLLECTION]}
