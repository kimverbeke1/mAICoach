"""Opslag voor het Crypto-project: Firestore als die beschikbaar is, anders lokaal (CSV/JSON).

Firestore-collecties:
  crypto_candles/{SYMBOL}_1d   dagcandles als kolom-arrays (t, o, h, l, c, v, q) + checked_from
  crypto_results/{key}         laatst berekende dip-tabel per combinatie van instellingen (JSON)
  crypto_settings/coins        per munt opgeslagen schijven/winstdoel

Credentials (eerste die werkt):
  1. firebase_admin is al geïnitialiseerd door een andere pagina (mAICoach/PadelAnalysis) -> hergebruiken
  2. st.secrets: eerste sectie met 'private_key' en 'client_email' (service account), of een sectie/waarde
     FIREBASE_SERVICE_ACCOUNT_JSON met de JSON-tekst
  3. env FIREBASE_SERVICE_ACCOUNT_JSON / FIREBASE_SERVICE_ACCOUNT / FIREBASE_CREDENTIALS (JSON-tekst),
     zoals in de GitHub Actions
  4. env GOOGLE_APPLICATION_CREDENTIALS (pad naar JSON-bestand)
Zonder credentials werkt alles lokaal, zoals voorheen.  CRYPTO_NO_CLOUD=1 schakelt Firestore uit.
"""
from __future__ import annotations

import json
import os
import time

import pandas as pd

COLL_CANDLES = "crypto_candles"
COLL_RESULTS = "crypto_results"
COLL_SETTINGS = "crypto_settings"
CLOUD_INTERVALS = {"1d"}          # enkel dagdata in Firestore (uur/kwartier is te groot voor één document)
ENV_JSON_KEYS = ("FIREBASE_SERVICE_ACCOUNT_JSON", "FIREBASE_SERVICE_ACCOUNT", "FIREBASE_CREDENTIALS")

_db = None
_err: str | None = None
_LOCAL_RESULTS = os.path.join(os.environ.get("CRYPTO_CACHE_DIR") or
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache"), "results")


def _service_account() -> dict | None:
    """Zoek een service-account-dict in st.secrets of in omgevingsvariabelen."""
    try:
        import streamlit as st
        sec = st.secrets
        for k in ENV_JSON_KEYS:
            if k in sec:
                v = sec[k]
                return json.loads(v) if isinstance(v, str) else dict(v)
        for k in sec:
            v = sec[k]
            if hasattr(v, "keys") and "private_key" in v and "client_email" in v:
                return dict(v)
    except Exception:  # noqa: BLE001 - geen streamlit, geen secrets.toml
        pass
    for k in ENV_JSON_KEYS:
        v = os.environ.get(k)
        if v:
            return json.loads(v)
    return None


def get_db():
    """Firestore-client of None (dan lokaal werken). Wordt één keer per proces bepaald."""
    global _db, _err
    if _db is not None or _err is not None:
        return _db
    if os.environ.get("CRYPTO_NO_CLOUD") == "1":
        _err = "uitgeschakeld (CRYPTO_NO_CLOUD=1)"
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            info = _service_account()
            if info:
                firebase_admin.initialize_app(credentials.Certificate(info))
            elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                firebase_admin.initialize_app()
            else:
                _err = "geen Firebase-credentials gevonden"
                return None
        _db = firestore.client()
    except Exception as e:  # noqa: BLE001
        _err = f"{type(e).__name__}: {e}"
        _db = None
    return _db


def status() -> str:
    get_db()
    return "☁️ Firestore" if _db is not None else f"💻 lokaal ({_err})"


def is_cloud() -> bool:
    return get_db() is not None


# --------------------------------------------------------------------------- candles
def load_candles(symbol: str, interval: str) -> tuple[pd.DataFrame | None, dict]:
    """(df, meta) uit Firestore, of (None, {}) als niet beschikbaar."""
    db = get_db() if interval in CLOUD_INTERVALS else None
    if db is None:
        return None, {}
    try:
        snap = db.collection(COLL_CANDLES).document(f"{symbol}_{interval}").get()
    except Exception:  # noqa: BLE001 - netwerk/rechten: val terug op lokaal
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
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- resultaten (dip-tabel)
def load_result(key: str) -> dict | None:
    """{'json': <tabel als JSON>, 'ts': epoch, 'source': 'app'|'github'} of None."""
    db = get_db()
    if db is not None:
        snap = db.collection(COLL_RESULTS).document(key).get()
        return snap.to_dict() if snap.exists else None
    p = os.path.join(_LOCAL_RESULTS, f"{key}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def save_result(key: str, table_json: str, source: str = "app") -> None:
    doc = {"json": table_json, "ts": int(time.time()), "source": source}
    db = get_db()
    if db is not None:
        db.collection(COLL_RESULTS).document(key).set(doc)
        return
    os.makedirs(_LOCAL_RESULTS, exist_ok=True)
    with open(os.path.join(_LOCAL_RESULTS, f"{key}.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


# --------------------------------------------------------------------------- instellingen per munt
def load_settings() -> dict | None:
    """Dict uit Firestore, of None als er geen Firestore is (dan lokaal bestand gebruiken)."""
    db = get_db()
    if db is None:
        return None
    snap = db.collection(COLL_SETTINGS).document("coins").get()
    return (snap.to_dict() or {}) if snap.exists else {}


def save_settings(data: dict) -> bool:
    db = get_db()
    if db is None:
        return False
    db.collection(COLL_SETTINGS).document("coins").set(data)
    return True
