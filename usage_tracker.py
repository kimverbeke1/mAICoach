# -*- coding: utf-8 -*-
"""usage_tracker.py - verborgen gebruiksstatistieken voor mAICoach + PadelAnalysis.

Staat in de repo-root (naast streamlit_app.py en perf_timing.py).

Schrijft naar twee Firestore-collecties die NERGENS in de UI getoond worden:
  _admin_sessions    1 document per browsersessie (start, laatste activiteit, duur, bezochte pagina's)
  _admin_usage_logs  1 document per paginawissel (app, pagina, tijdstip, sessie-id)

Bewaard wordt NIET: IP-adres, user-agent, namen. Enkel een willekeurige sessie-id.

Performantie: Firestore-schrijfacties draaien in een achtergrondthread, en gebeuren
enkel bij (a) nieuwe sessie, (b) paginawissel, (c) hoogstens 1x per HEARTBEAT_SECONDS.
Faalt altijd stil: tracking mag de app nooit breken.

Uitschakelen: USAGE_TRACKING_ENABLED = False.
"""
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

USAGE_TRACKING_ENABLED = True
HEARTBEAT_SECONDS = 60
SESSIONS_COLLECTION = "_admin_sessions"
USAGE_LOGS_COLLECTION = "_admin_usage_logs"

_DB = None  # None = nog niet geprobeerd, False = niet beschikbaar


def _get_db():
    """Hergebruikt de bestaande Firestore-client uit PadelAnalysis/firebase_service.py."""
    global _DB
    if _DB is not None:
        return _DB
    try:
        pa_dir = str(Path(__file__).resolve().parent / "PadelAnalysis")
        if pa_dir not in sys.path:
            sys.path.append(pa_dir)  # append: nooit gelijknamige modules overschaduwen
        import firebase_service  # noqa: WPS433

        _DB = firebase_service.db
    except Exception:  # noqa: BLE001
        _DB = False
    return _DB


def _write(db, sid, app, page, started, now, page_changed):
    try:
        from google.cloud.firestore_v1 import ArrayUnion, Increment

        session = {
            "session_id": sid,
            "started_at": started,
            "last_seen": now,
            "duration_sec": int((now - started).total_seconds()),
            "last_app": app,
            "last_page": page,
            "apps": ArrayUnion([app]),
            "pages": ArrayUnion([f"{app}: {page}"]),
        }
        if page_changed:
            session["page_views"] = Increment(1)
        db.collection(SESSIONS_COLLECTION).document(sid).set(session, merge=True)
        if page_changed:
            db.collection(USAGE_LOGS_COLLECTION).add(
                {"timestamp": now, "session_id": sid, "app": app, "page": page}
            )
    except Exception:  # noqa: BLE001
        pass


def track(app: str, page: str) -> None:
    """Registreer dat deze sessie nu `page` van `app` bekijkt."""
    if not USAGE_TRACKING_ENABLED:
        return
    try:
        ss = st.session_state
        now = datetime.now(timezone.utc)
        sid = ss.get("_usage_sid")
        new_session = sid is None
        if new_session:
            sid = uuid.uuid4().hex[:16]
            ss["_usage_sid"] = sid
            ss["_usage_started"] = now
        key = f"{app}|{page}"
        page_changed = ss.get("_usage_last_key") != key
        last_beat = ss.get("_usage_last_beat")
        beat_due = last_beat is None or (now - last_beat).total_seconds() >= HEARTBEAT_SECONDS
        if not (new_session or page_changed or beat_due):
            return
        db = _get_db()
        if not db:
            return
        ss["_usage_last_key"] = key
        ss["_usage_last_beat"] = now
        threading.Thread(
            target=_write,
            args=(db, sid, app, page, ss["_usage_started"], now, page_changed),
            daemon=True,
        ).start()
    except Exception:  # noqa: BLE001
        pass
