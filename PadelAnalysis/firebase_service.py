# firebase_service.py
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore
logger = logging.getLogger(__name__)
SERVICE_ACCOUNT_FILE = "firebase-key.json"
PLAYERS_COLLECTION = "players"
PLAYER_SEARCH_CACHE_COLLECTION = "player_search_cache"
PLAYER_PROFILES_COLLECTION = "player_profiles"
SAVED_LINEUP_ANALYSES_COLLECTION = "saved_lineup_analyses"
PADELSTAT_CACHE_COLLECTION = "padelstat_cache"
# PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20: bron-label dat
# in een klassement_history-rij gezet wordt zodra die rij AFKOMSTIG is van
# padelstats.be (i.p.v. van de TVL-scraper scrape_klassement.py). Gebruikt om
# exact 1 zo'n rij te kunnen upserten (i.p.v. bij elke refresh een nieuwe rij
# toe te voegen) zonder de rest van de klassement_history (TVL-periodes,
# niveau_winrates, ...) aan te raken.
PADELSTAT_KLASSEMENT_SOURCE = "padelstats.be"
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
# ---------------------------------------------------------------------------
# Credential loading — 3 mogelijke bronnen, in deze volgorde:
#   1. Streamlit secrets ([firebase] sectie)     -> Streamlit Community Cloud
#   2. Environment variable met volledige JSON   -> GitHub Actions / CI
#   3. Lokaal firebase-key.json bestand          -> lokale ontwikkelmachine
# ---------------------------------------------------------------------------
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
def _load_env_credentials() -> Optional[credentials.Certificate]:
    """
    Laadt Firebase-credentials uit een environment variable — bedoeld voor
    CI/CD-omgevingen zoals GitHub Actions.
    """
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON") or os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if not raw:
        return None
    try:
        info = json.loads(raw)
        if "private_key" in info:
            info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
        return credentials.Certificate(info)
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
    cred = (
        _load_streamlit_secrets_credentials()
        or _load_env_credentials()
        or _load_local_file_credentials()
    )
    if cred is None:
        raise FileNotFoundError(
            "Geen Firebase credentials gevonden. Gebruik lokaal firebase-key.json, "
            "Streamlit secrets met [firebase], of environment variable "
            "FIREBASE_SERVICE_ACCOUNT_JSON (bv. in GitHub Actions)."
        )
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
    """
    Save v2 schema player data directly, skipping legacy build_minimal_defaults.
    PADEL_ANALYSIS_WRITE_GUARD_FIX (deze beurt):
    BUG (opgelost): deze functie schreef altijd met merge=False (volledige
    documentvervanging). Als een scrape-run om welke reden dan ook een
    RESULTAAT MET MINDER (of 0) matches opleverde dan al in Firestore stond
    -- bv. een netwerkhik, een Playwright-timeout die stil een lege
    periodelijst teruggaf, of een gedeeltelijke parse-fout die geen
    exception opgooide -- dan werd de GOEDE, bestaande data van die speler
    VOLLEDIG OVERSCHREVEN en dus verloren, zonder enige waarschuwing. Dit is
    de meest waarschijnlijke verklaring voor "ik had deze speler al
    gescraped, maar nu toont de app hem plots als niet-gescraped".
    Fix: vóór het schrijven wordt de bestaande data opgehaald. Als de NIEUWE
    data significant MINDER matches bevat dan wat al gekend was, weigert
    deze functie de bestaande matches/stats te laten verdwijnen -- de oude
    matches/stats worden behouden, en er wordt een duidelijke markering
    ("_write_guard_triggered") in het document gezet zodat dit zichtbaar is
    in de Debug-tab van de app, in plaats van stil dataverlies te laten
    gebeuren. Een bewuste, expliciete "force_full_refresh" met een kleinere
    (correcte) matchset kan dit niet gebruiken om per ongeluk in de val te
    lopen: force_full_refresh-resultaten van scrape_player.py bevatten altijd
    de HERSCRAPTE volledige set, dus in de normale, gezonde situatie is dit
    nooit kleiner dan de vorige (foutieve/onvolledige) data.
    """
    prepared = sanitize_for_firestore(dict(player_data))
    prepared["player_id"] = str(player_id)
    if "last_updated" not in prepared:
        prepared["last_updated"] = utc_now_iso()
    new_matches = prepared.get("matches") or []
    try:
        existing = get_player(player_id, converted=False)
    except Exception as e:
        logger.warning(f"[{player_id}] Kon bestaand document niet ophalen voor write-guard check: {e}")
        existing = None
    existing_matches = (existing or {}).get("matches") or []
    if existing_matches and len(new_matches) < len(existing_matches):
        warn_msg = (
            f"Nieuwe scrape had {len(new_matches)} matches, minder dan de "
            f"{len(existing_matches)} al gekende matches. Oude matches/stats "
            f"behouden i.p.v. overschreven, om dataverlies te vermijden."
        )
        logger.error(f"[{player_id}] WRITE GUARD: {warn_msg}")
        prepared["matches"] = existing_matches
        prepared["stats"] = existing.get("stats", prepared.get("stats", {}))
        prepared["_write_guard_triggered"] = True
        prepared["_write_guard_note"] = warn_msg
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
def cleanup_ghost_profiles() -> int:
    """PADEL_ANALYSIS_GHOST_PROFILE_CLEANUP_2026-09-12:
    Verwijdert profieldocumenten zonder display_name EN zonder player_id.
    Zulke documenten zijn geen echte spelersprofielen, maar ontstaan als
    bijproduct van merge=True-writes op een player_id die geen (meer)
    bestaand profiel heeft -- met name dashboard._save_poule_url() (schrijft
    enkel {"poule_reeks_url": ...}) en de Playwright/GitHub Actions-flow die
    interclub_schedule wegschrijft."""
    removed = 0
    for doc in db.collection(PLAYER_PROFILES_COLLECTION).stream():
        data = doc.to_dict() or {}
        if not data.get("display_name") and not data.get("player_id"):
            doc.reference.delete()
            removed += 1
    return removed
def save_lineup_analysis(owner_player_id: str, data: dict) -> str:
    """PADEL_ANALYSIS_SAVED_LINEUP_ANALYSES_2026-09-12:
    Slaat een berekende opstelling-scenario-analyse permanent op (nieuwe
    collectie), zodat ze later terug te bekijken is via het tabblad
    'Opgeslagen analyses' in Opstelling-analyse, zonder herberekening.
    Geeft het aangemaakte document-ID terug."""
    doc = dict(data)
    doc["owner_player_id"] = str(owner_player_id)
    doc["saved_at"] = utc_now_iso()
    ref = db.collection(SAVED_LINEUP_ANALYSES_COLLECTION).document()
    ref.set(sanitize_for_firestore(doc))
    return ref.id
def list_lineup_analyses(owner_player_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Geeft alle opgeslagen opstelling-analyses terug (recentste eerst).
    Optioneel gefilterd op wie de analyse opsloeg (owner_player_id)."""
    docs = db.collection(SAVED_LINEUP_ANALYSES_COLLECTION).stream()
    out = []
    for doc in docs:
        data = doc.to_dict() or {}
        if owner_player_id and str(data.get("owner_player_id") or "") != str(owner_player_id):
            continue
        data["_doc_id"] = doc.id
        out.append(convert_firestore_values(data))
    out.sort(key=lambda x: x.get("saved_at") or "", reverse=True)
    return out
def delete_lineup_analysis(doc_id: str) -> None:
    db.collection(SAVED_LINEUP_ANALYSES_COLLECTION).document(str(doc_id)).delete()
def save_padelstat_rating(
    player_id: str,
    padelstat_id: str,
    rating: Optional[int],
    rating_source: str,
    raw_text_snippet: str = "",
    matched_klassement: Optional[int] = None,
    club_confirmed: Optional[bool] = None,
) -> dict:
    """PADEL_ANALYSIS_PADELSTAT_CALIBRATION_2026-09-12:
    Cachet een opgezochte padelstats.be-waarde voor een eigen speler, zodat
    dezelfde speler niet herhaaldelijk opnieuw gescraped hoeft te worden
    (padelstats_scraper.py gebruikt Playwright, wat traag is en de site
    onnodig belast bij herhaling). doc-ID = onze eigen player_id, niet het
    padelstats-ID, zodat opzoeken vanuit de rest van de app eenvoudig blijft.
    PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20 (op verzoek
    van Kim): twee nieuwe, OPTIONELE parameters, puur ter informatie/debug
    opgeslagen in dezelfde padelstat_cache-cache (GEEN impact op bestaande
    lezers van dit document, die deze velden gewoon negeren):
      - matched_klassement: het officiële TVL-klassement (P-waarde) zoals
        padelstats.be dat toont in de zoekresultaatkaart (bv. "P200" in
        "P200 • PADEL FACTORY") - zie padelstats_scraper.py
        search_and_fetch_padelstat_rating()["matched_klassement"]. Dit is
        NIET hetzelfde als 'rating' (de 'playing strength', een apart,
        door padelstats.be zelf berekend cijfer op de profielpagina).
      - club_confirmed: False zodra de club-match onzeker was (zie
        gevonden.get("club_disambiguation_note") in enrich_opponents.py),
        zodat achteraf zichtbaar blijft welke waarden extra voorzichtig
        geïnterpreteerd moeten worden.
    De effectieve upsert van matched_klassement IN klassement_history (het
    veld dat de rest van de app - opponent_dossier.py - echt leest voor
    "Huidig klassement") gebeurt in save_official_klassement_from_padelstat()
    hieronder, NIET hier: deze functie blijft puur de padelstat-cache."""
    doc = {
        "player_id": str(player_id),
        "padelstat_id": str(padelstat_id),
        "rating": rating,
        "rating_source": rating_source,
        "raw_text_snippet": raw_text_snippet,
        "fetched_at": utc_now_iso(),
    }
    if matched_klassement is not None:
        doc["matched_klassement"] = matched_klassement
    if club_confirmed is not None:
        doc["club_confirmed"] = club_confirmed
    db.collection(PADELSTAT_CACHE_COLLECTION).document(str(player_id)).set(sanitize_for_firestore(doc), merge=True)
    return doc
def get_padelstat_rating(player_id: str) -> Optional[dict]:
    doc = db.collection(PADELSTAT_CACHE_COLLECTION).document(str(player_id)).get()
    if not doc.exists:
        return None
    return convert_firestore_values(doc.to_dict())
# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20 (op verzoek van
# Kim: "aangezien we toch al het padelstat klassement scrapen van padelstat.be
# zou ik willen voorstellen om het officieel klassement ook al meteen van
# daar te scrapen. Dan moet die scraping van 2 keer per jaar niet meer
# gebeuren aangezien padelstat toch regelmatig refresht.")
# ---------------------------------------------------------------------------
# ACHTERGROND: padelstats_scraper.search_and_fetch_padelstat_rating() haalt,
# bovenop de 'playing strength' (rating), AL het officiële TVL-klassement op
# uit de zoekresultaatkaart (bv. "P200" in "P200 • PADEL FACTORY" - zie de
# bevestigde kaartstructuur in de docstring van dat bestand). Die waarde werd
# tot nu toe enkel gelogd, nooit opgeslagen. Omdat elke reguliere
# padelstat-verversing (enrich_opponents.run_padelstat_for_players(), draait
# voor ALLE spelers, elke run) dit sowieso al ophaalt, kan het officiële
# klassement voortaan GRATIS meeliften op die bestaande scrape - de aparte,
# traGere TVL-klassement-scrape (scrape_klassement.py, slechts 2x/jaar
# officieel relevant en bovendien momenteel geblokkeerd door bot-detectie
# van tennisenpadelvlaanderen.be) is daarmee niet langer de ENIGE bron.
# LET OP - dit is een SNAPSHOT, geen historiek: padelstats.be toont enkel het
# HUIDIGE klassement, niet de meerdere periodes (Start/Zomer/...) die
# scrape_klassement.py wel oplevert. Deze functie voegt daarom een ENKELE,
# upsertbare rij toe aan klassement_history.history (herkenbaar aan
# "source": PADELSTAT_KLASSEMENT_SOURCE), met een ECHTE (huidige) datum zodat
# opponent_dossier._history_rows() deze rij correct als de MEEST RECENTE
# sorteert (TVL-rijen hebben geen datum, enkel een periode-label) - zonder
# de eventuele reeds aanwezige TVL-periodes te verwijderen of te overschrijven.
def _klassement_history_doc_for_read(player_id: str) -> dict:
    """Leest de BESTAANDE klassement_history op, bij voorkeur uit
    player_profiles (bestaat ALTIJD zodra een profiel is aangemaakt, ook
    voor tegenstanders zonder eigen 'players'-document), aangevuld met wat
    in 'players' staat als dat recenter/voller zou zijn. In de praktijk
    schrijft run_klassement_for_players() exact dezelfde payload naar beide
    collecties, dus dit is vrijwel altijd identiek - dit is puur een
    defensieve keuze voor het (zeldzame) geval dat ze uiteenlopen."""
    try:
        profile = get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        profile = {}
    profile_history = profile.get("klassement_history") or {}
    if profile_history.get("history"):
        return profile_history
    try:
        player_doc = get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        player_doc = {}
    return player_doc.get("klassement_history") or profile_history
def save_official_klassement_from_padelstat(
    player_id: str,
    klassement_rank: int,
    club_confirmed: bool = True,
) -> dict:
    """Upsert van het OFFICIËLE klassement (P-waarde), zoals opgehaald uit de
    padelstats.be-zoekresultaatkaart, in klassement_history.history - zonder
    een eventuele bestaande, door scrape_klassement.py opgebouwde
    meerdere-periodes-historiek te verliezen.
    Idempotent: een herhaalde aanroep (volgende run) VERVANGT de vorige
    padelstat-rij (herkend via "source") i.p.v. er telkens een nieuwe aan toe
    te voegen - klassement_history.history blijft dus altijd maximaal 1 rij
    met source=PADELSTAT_KLASSEMENT_SOURCE bevatten.
    Retourneert de nieuwe klassement_history-payload (voor logging/debug)."""
    existing_history = _klassement_history_doc_for_read(player_id)
    rows = list(existing_history.get("history") or [])
    rows = [r for r in rows if r.get("source") != PADELSTAT_KLASSEMENT_SOURCE]
    new_row = {
        "periode": "Playing strength / klassement via padelstats.be",
        "datum": utc_now_iso()[:10],  # echte, huidige datum (YYYY-MM-DD)
        "klassement": f"P{klassement_rank}",
        "source": PADELSTAT_KLASSEMENT_SOURCE,
        "club_confirmed": club_confirmed,
    }
    rows.append(new_row)
    updated_history = dict(existing_history)
    updated_history["history"] = rows
    updated_history["padelstat_klassement_updated_at"] = utc_now_iso()
    payload = {"klassement_history": sanitize_for_firestore(updated_history)}
    db.collection(PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
    db.collection(PLAYERS_COLLECTION).document(str(player_id)).set(payload, merge=True)
    return updated_history
