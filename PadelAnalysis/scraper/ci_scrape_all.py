"""
ci_scrape_all.py — GitHub Actions entrypoint voor het (op aanvraag) verversen
van PadelAnalysis-spelers via Firestore, zonder Streamlit en zonder lokaal
firebase-key.json bestand.

Locatie: PadelAnalysis/scraper/ci_scrape_all.py (naast scrape_player.py,
zelfde path-setup patroon).

Firebase-credentials komen uit de environment variable
FIREBASE_SERVICE_ACCOUNT_JSON (GitHub Actions secret), ingelezen via
firebase_service._load_env_credentials(). Lokaal blijft firebase-key.json
gewoon werken (fallback), en op Streamlit Cloud blijft st.secrets werken.

Welke spelers scrapen (env var PLAYER_IDS):
    - Leeg (standaard)       -> alle spelers uit player_profiles.
    - Komma-gescheiden lijst -> enkel die player_id's, bv. "214435,198221".

Welke periodes/spelers effectief gescraped worden (env var MODE):
    - "missing" (standaard) -> ENKEL periodes die nog nooit gescraped zijn,
      per speler. Spelers die al volledig up-to-date zijn worden supersnel
      overgeslagen (geen Playwright-launch nodig) — dit is veruit de
      snelste en meest gebruikelijke modus voor een "ververs alles"-run.
    - "new_users"           -> scrape ENKEL spelers die nog nooit eerder
      gescraped zijn (geen bestaand document in de 'players'-collectie),
      dus volledig nieuw toegevoegde spelers. Bestaande spelers worden
      volledig overgeslagen, ook al zouden ze een nieuwe periode hebben.
    - "full"                -> forceer een volledige herscrape van alle
      periodes voor de opgegeven spelers (traag, normaal niet nodig).

Gebruik (lokaal testen, PowerShell):
    $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content -Raw firebase-key.json
    $env:PLAYER_IDS = "214435"          # optioneel, leeg = alle spelers
    $env:MODE = "missing"               # missing | new_users | full
    python ci_scrape_all.py
"""
import logging
import os
import sys
import time
from pathlib import Path

# --- path setup: zelfde patroon als scrape_player.py ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb
from scrape_player import scrape_player

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ci_scrape_all")

# Beleefde pauze tussen spelers (niet te agressief scrapen richting TVL-website)
DELAY_BETWEEN_PLAYERS = 3.0

VALID_MODES = ("missing", "new_users", "full")
DEFAULT_MODE = "missing"


def get_all_player_ids() -> list:
    """Alle player_id's uit player_profiles — dit zijn de spelers die je via
    de app onder '➕ Speler toevoegen' hebt aangemaakt."""
    docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
    ids = []
    for d in docs:
        data = d.to_dict() or {}
        pid = data.get("player_id") or d.id
        if pid:
            ids.append(str(pid))
    return ids


def get_requested_player_ids() -> list:
    """
    Bepaalt WELKE spelers deze run in aanmerking neemt (voor filtering op
    mode, zie filter_by_mode()).

    - PLAYER_IDS environment variable gezet en niet leeg  -> enkel die spelers
      (komma-gescheiden, spaties worden getrimd, lege stukken genegeerd).
    - Anders                                              -> alle gekende spelers.
    """
    raw = os.environ.get("PLAYER_IDS", "").strip()
    if not raw:
        return get_all_player_ids()

    requested = [p.strip() for p in raw.split(",") if p.strip()]
    if not requested:
        return get_all_player_ids()

    logger.info(f"Specifieke spelers aangevraagd via PLAYER_IDS: {requested}")
    return requested


def get_mode() -> str:
    mode = os.environ.get("MODE", DEFAULT_MODE).strip().lower() or DEFAULT_MODE
    if mode not in VALID_MODES:
        logger.warning(f"Onbekende MODE '{mode}', val terug op '{DEFAULT_MODE}'.")
        return DEFAULT_MODE
    return mode


def filter_by_mode(player_ids: list, mode: str) -> list:
    """Past de mode-specifieke voorselectie toe VOOR het scrapen begint,
    zodat spelers die niet in aanmerking komen niet eens geteld worden in
    de voortgangsbalk/logs."""
    if mode != "new_users":
        return player_ids

    new_only = []
    for pid in player_ids:
        try:
            existing = fb.get_player(pid)
        except Exception as e:
            logger.warning(f"[{pid}] Kon bestaand document niet checken ({e}) — wordt overgeslagen voor mode=new_users.")
            continue
        if existing is None:
            new_only.append(pid)
    skipped = len(player_ids) - len(new_only)
    if skipped:
        logger.info(f"mode=new_users: {skipped} reeds-gekende speler(s) overgeslagen, {len(new_only)} nieuwe speler(s) te scrapen.")
    return new_only


def scrape_kwargs_for_mode(mode: str) -> dict:
    if mode == "full":
        return {"force_full_refresh": True, "refresh_recent": 0, "strict_missing_only": False}
    # "missing" en "new_users" scrapen beide enkel ontbrekende periodes —
    # het verschil zit in filter_by_mode() (welke spelers uberhaupt aan bod komen).
    return {"force_full_refresh": False, "refresh_recent": 0, "strict_missing_only": True}


def main() -> int:
    mode = get_mode()
    player_ids = get_requested_player_ids()
    player_ids = filter_by_mode(player_ids, mode)

    if not player_ids:
        logger.warning(f"Geen spelers gevonden/aangevraagd voor mode='{mode}' — niets te verversen.")
        return 0

    logger.info(f"Mode: '{mode}' — {len(player_ids)} speler(s) worden verwerkt: {player_ids}")
    kwargs = scrape_kwargs_for_mode(mode)
    logger.info(f"scrape_player kwargs: {kwargs}")

    ok, failed, skipped_up_to_date = [], [], []
    for i, pid in enumerate(player_ids, start=1):
        logger.info(f"--- ({i}/{len(player_ids)}) Speler {pid} ---")
        try:
            result = scrape_player(
                pid,
                save_to_firebase=True,
                headless=True,
                **kwargs,
            )
            if result.get("error") or result.get("firebase_error"):
                failed.append((pid, result.get("error") or result.get("firebase_error")))
                logger.error(f"[{pid}] Mislukt: {result.get('error') or result.get('firebase_error')}")
            elif result.get("status") == "up_to_date":
                skipped_up_to_date.append(pid)
                logger.info(f"[{pid}] Al up-to-date, overgeslagen (geen Playwright nodig).")
            else:
                s = result.get("stats", {})
                ok.append(pid)
                logger.info(
                    f"[{pid}] OK — {s.get('total_matches', 0)} matches, "
                    f"winrate {s.get('winrate', 0)}%"
                )
        except Exception as e:
            logger.exception(f"[{pid}] Onverwachte fout: {e}")
            failed.append((pid, str(e)))

        if i < len(player_ids):
            time.sleep(DELAY_BETWEEN_PLAYERS)

    logger.info("=== Samenvatting ===")
    logger.info(f"Ververst: {len(ok)} — Al up-to-date: {len(skipped_up_to_date)} — Mislukt: {len(failed)}")
    for pid, err in failed:
        logger.error(f"  \u274c {pid}: {err}")

    # De workflow faalt (rode X in GitHub Actions) enkel zichtbaar als ALLE
    # verwerkte spelers mislukten. "Up-to-date" spelers tellen niet als
    # mislukking — dat is net het verwachte, gewenste resultaat.
    if ok or skipped_up_to_date or not player_ids:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
