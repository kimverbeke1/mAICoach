"""Opslag voor het Crypto-project: Firestore als die beschikbaar is, anders lokaal (CSV/JSON).

Firestore-collecties:
  crypto_candles/{SYMBOL}_1d     dagcandles als kolom-arrays (t, o, h, l, c, v, q) + checked_from
  crypto_results/{key}           laatst berekende dip-tabel per combinatie van instellingen (JSON)
  crypto_settings/coins          per munt opgeslagen schijven/winstdoel
  crypto_settings/app_defaults   jouw standaardinstellingen (knop '💾 Bewaar als standaard'); de app start
                                 hiermee en de nachtelijke update rekent ermee

Welke Firestore-verbinding (eerste die werkt):
  1. PadelAnalysis/firebase_service.py -> `db`: EXACT dezelfde verbinding (project + database) als PadelAnalysis.
  2. Service account uit st.secrets of env (FIREBASE_SERVICE_ACCOUNT_JSON eerst; daarna een secrets-sectie met
     'private_key' + 'client_email'), zoals in de GitHub Actions.
  3. env GOOGLE_APPLICATION_CREDENTIALS.
Bij de EERSTE toegang wordt de verbinding getest met één leesopdracht. Mislukt die, dan schakelt de module over
op LOKAAL en toont status() de reden. De pagina crasht dus nooit door Firestore.
CRYPTO_NO_CLOUD=1 schakelt Firestore volledig uit.
"""
from __future__ import annotations

import json
import os
import sys
import time

import pandas as pd

COLL_CANDLES = "crypto_candles"
COLL_RESULTS = "crypto_results"
COLL_SETTINGS = "crypto_settings"
DOC_DEFAULTS = "app_defaults"
CLOUD_INTERVALS = {"1d"}
ENV_JSON_KEYS = ("FIREBASE_SERVICE_ACCOUNT_JSON", "FIREBASE_SERVICE_ACCOUNT", "FIREBASE_CREDENTIALS")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CACHE = os.environ.get("CRYPTO_CACHE_DIR") or os.path.join(_HERE, "data_cache")
_LOCAL_RESULTS = os.path.join(_CACHE, "results")
_LOCAL_DEFAULTS = os.path.join(_CACHE, "app_defaults.json")

_db = None
_err: str | None = None
_via: str = ""


def _short(e: Exception) -> str:
    msg = str(e).split("\n")[0]
    return f"{type(e).__name__}: {msg[:160]}"


def _from_padel():
    """Hergebruik de Firestore-client van PadelAnalysis (firebase_service.db)."""
    p = os.path.join(_ROOT, "PadelAnalysis")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.append(p)
    import firebase_service as fb  # noqa: PLC0415
    db = getattr(fb, "db", None)
    if db is None and hasattr(fb, "get_db"):
        db = fb.get_db()
    return db


def _service_account() -> dict | None:
    try:
        import streamlit as st
        sec = st.secrets
        for k in ENV_JSON_KEYS:
            if k in sec:
                v = sec[k]
                return json.loads(v) if isinstance(v, str) else dict(v)
        for k in ("firebase", "firebase_service_account", "FIREBASE"):
            if k in sec and hasattr(sec[k], "keys") and "private_key" in sec[k]:
                return dict(sec[k])
        for k in sec:
            v = sec[k]
            if hasattr(v, "keys") and "private_key" in v and "client_email" in v:
                return dict(v)
    except Exception:  # noqa: BLE001
        pass
    for k in ENV_JSON_KEYS:
        v = os.environ.get(k)
        if v:
            return json.loads(v)
    return None


def _from_secrets():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        info = _service_account()
        if info:
            firebase_admin.initialize_app(credentials.Certificate(info))
        elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            firebase_admin.initialize_app()
        else:
            return None
    return firestore.client()


def get_db():
    """Firestore-client of None (dan lokaal werken). Wordt één keer per proces bepaald én getest."""
    global _db, _err, _via
    if _db is not None or _err is not None:
        return _db
    if os.environ.get("CRYPTO_NO_CLOUD") == "1":
        _err = "uitgeschakeld (CRYPTO_NO_CLOUD=1)"
        return None
    errors = []
    for name, fn in (("PadelAnalysis", _from_padel), ("service account", _from_secrets)):
        try:
            db = fn()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {_short(e)}")
            continue
        if db is None:
            continue
        try:
            db.collection(COLL_SETTINGS).document("coins").get()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {_short(e)}")
            continue
        _db, _via = db, name
        return _db
    _err = "; ".join(errors) if errors else "geen Firebase-credentials gevonden"
    return None


def status() -> str:
    get_db()
    return f"☁️ Firestore (via {_via})" if _db is not None else f"💻 lokaal ({_err})"


def is_cloud() -> bool:
    return get_db() is not None


def _disable(e: Exception) -> None:
    global _db, _err
    _db, _err = None, f"uitgevallen tijdens gebruik: {_short(e)}"


# --------------------------------------------------------------------------- candles
def load_candles(symbol: str, interval: str) -> tuple[pd.DataFrame | None, dict]:
    db = get_db() if interval in CLOUD_INTERVALS else None
    if db is None:
        return None, {}
    try:
        snap = db.collection(COLL_CANDLES).document(f"{symbol}_{interval}").get()
    except Exception as e:  # noqa: BLE001
        _disable(e)
        return None, {}
    if not snap.exists:
        return pd.DataFrame(), {}
    d = snap.to_dict() or {}
    df = pd.DataFrame({"open_time": d.get("t", []), "open": d.get("o", []), "high": d.get("h", []),
                       "low": d.get("l", []), "close": d.get("c", []), "volume": d.get("v", []),
                       "quote_volume": d.get("q", [])})
    if not df.empty:
        df["open_time"] = df["open_time"].astype("int64")
    return df, {"checked_from": d.get("checked_from"), "updated": d.get("updated")}


def save_candles(symbol: str, interval: str, df: pd.DataFrame, meta: dict) -> bool:
    db = get_db() if interval in CLOUD_INTERVALS else None
    if db is None:
        return False
    f = lambda c: [float(x) for x in df[c].to_numpy()]
    try:
        db.collection(COLL_CANDLES).document(f"{symbol}_{interval}").set({
            "symbol": symbol, "interval": interval,
            "t": [int(x) for x in df["open_time"].to_numpy()],
            "o": f("open"), "h": f("high"), "l": f("low"), "c": f("close"),
            "v": f("volume"), "q": f("quote_volume"),
            "checked_from": meta.get("checked_from"), "updated": int(time.time()),
        })
        return True
    except Exception as e:  # noqa: BLE001
        _disable(e)
        return False


# --------------------------------------------------------------------------- resultaten (dip-tabel)
def _local_result_path(key: str) -> str:
    return os.path.join(_LOCAL_RESULTS, f"{key}.json")


def load_result(key: str) -> dict | None:
    db = get_db()
    if db is not None:
        try:
            snap = db.collection(COLL_RESULTS).document(key).get()
            return snap.to_dict() if snap.exists else None
        except Exception as e:  # noqa: BLE001
            _disable(e)
    p = _local_result_path(key)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def save_result(key: str, table_json: str, source: str = "app") -> None:
    doc = {"json": table_json, "ts": int(time.time()), "source": source}
    db = get_db()
    if db is not None:
        try:
            db.collection(COLL_RESULTS).document(key).set(doc)
            return
        except Exception as e:  # noqa: BLE001
            _disable(e)
    os.makedirs(_LOCAL_RESULTS, exist_ok=True)
    with open(_local_result_path(key), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


# --------------------------------------------------------------------------- instellingen per munt
def load_settings() -> dict | None:
    db = get_db()
    if db is None:
        return None
    try:
        snap = db.collection(COLL_SETTINGS).document("coins").get()
        return (snap.to_dict() or {}) if snap.exists else {}
    except Exception as e:  # noqa: BLE001
        _disable(e)
        return None


def save_settings(data: dict) -> bool:
    db = get_db()
    if db is None:
        return False
    try:
        db.collection(COLL_SETTINGS).document("coins").set(data)
        return True
    except Exception as e:  # noqa: BLE001
        _disable(e)
        return False


# --------------------------------------------------------------------------- jouw standaardinstellingen
def load_app_defaults() -> dict:
    """Bewaarde standaardinstellingen (leeg dict als er nog geen zijn)."""
    db = get_db()
    if db is not None:
        try:
            snap = db.collection(COLL_SETTINGS).document(DOC_DEFAULTS).get()
            return (snap.to_dict() or {}) if snap.exists else {}
        except Exception as e:  # noqa: BLE001
            _disable(e)
    if os.path.exists(_LOCAL_DEFAULTS):
        try:
            with open(_LOCAL_DEFAULTS, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_app_defaults(data: dict) -> str:
    """Bewaar de standaardinstellingen. Geeft 'cloud' of 'lokaal' terug."""
    db = get_db()
    if db is not None:
        try:
            db.collection(COLL_SETTINGS).document(DOC_DEFAULTS).set(data)
            return "cloud"
        except Exception as e:  # noqa: BLE001
            _disable(e)
    os.makedirs(_CACHE, exist_ok=True)
    with open(_LOCAL_DEFAULTS, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return "lokaal"
