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

Welke spelers scrapen:
    - Standaard: ALLE spelers uit player_profiles.
    - Specifieke spelers: geef hun player_id's mee via de environment
      variable PLAYER_IDS, komma-gescheiden, bv.:
          PLAYER_IDS="214435,198221"
      Dit wordt in de workflow ingevuld vanuit de handmatige
      workflow_dispatch-input (zie .github/workflows/scrape-padel.yml).

Gebruik (lokaal testen, PowerShell):
    $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content -Raw firebase-key.json
    $env:PLAYER_IDS = "214435"          # optioneel, leeg = alle spelers
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
    Bepaalt WELKE spelers deze run moet verversen.

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


def main() -> int:
    player_ids = get_requested_player_ids()
    if not player_ids:
        logger.warning("Geen spelers gevonden/aangevraagd — niets te verversen.")
        return 0

    logger.info(f"{len(player_ids)} speler(s) worden ververst: {player_ids}")

    ok, failed = [], []
    for i, pid in enumerate(player_ids, start=1):
        logger.info(f"--- ({i}/{len(player_ids)}) Speler {pid} ---")
        try:
            result = scrape_player(
                pid,
                force_full_refresh=False,
                save_to_firebase=True,
                headless=True,
            )
            if result.get("error") or result.get("firebase_error"):
                failed.append((pid, result.get("error") or result.get("firebase_error")))
                logger.error(f"[{pid}] Mislukt: {result.get('error') or result.get('firebase_error')}")
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
    logger.info(f"Geslaagd: {len(ok)} — Mislukt: {len(failed)}")
    for pid, err in failed:
        logger.error(f"  \u274c {pid}: {err}")

    # De workflow faalt (rode X in GitHub Actions) enkel zichtbaar als ALLE
    # gevraagde spelers mislukten. Eén occasionele mislukking (bv. TVL-site
    # tijdelijk onbereikbaar voor die speler) mag de hele run niet als
    # gefaald markeren, want de andere spelers zijn dan wel correct ververst.
    if ok:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
