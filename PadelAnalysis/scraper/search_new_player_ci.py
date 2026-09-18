"""
search_new_player_ci.py — GitHub Actions entrypoint voor het (op aanvraag)
zoeken van een NIEUWE, nog onbekende speler op TVL via player_search.py,
met het resultaat weggeschreven naar Firestore, zodat de Streamlit
Cloud-app het resultaat kan ophalen zonder zelf Playwright te moeten
draaien.

Locatie: PadelAnalysis/scraper/search_new_player_ci.py (naast
scrape_player.py en ci_scrape_all.py, zelfde path-setup patroon).

PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18 (op verzoek van Kim):
"Nieuwe spelers zoeken/toevoegen vereist een browser (Playwright) en werkt
daarom structureel enkel lokaal" was tot nu toe een harde beperking op
Streamlit Community Cloud, want scrape-padel.yml/ci_scrape_all.py kunnen
ENKEL bestaande player_id's verversen (scrape_player.scrape_player()) —
er was geen enkele workflow die op NAAM kon zoeken
(player_search.search_players()).

Dit script is de cloud-tegenhanger van de lokale "🔍 Zoek op TVL-website"-
knop in page_add_player.py (die player_search.search_players() rechtstreeks
in het Streamlit-proces aanroept, en dus enkel werkt als Playwright lokaal
beschikbaar is). Op een GitHub Actions ubuntu-runner (zelfde
venv/Playwright-cache-aanpak als scrape-padel.yml) is Playwright wél
beschikbaar.

Firestore-opslag:
Het resultaat wordt weggeschreven via
firebase_service.save_player_search_cache(name_query, club, sport,
candidates) — DEZELFDE cache die player_search.py lokaal ook al vult/leest
(sleutel = normalize_search_key(name_query, club, sport)). Hierdoor kan de
Streamlit-app, ongeacht of de zoekopdracht lokaal of via deze workflow is
uitgevoerd, altijd dezelfde fb.get_player_search_cache() aanroepen om het
resultaat op te halen. Er is dus GEEN nieuwe Firestore-collectie nodig.

Gebruik (lokaal testen, PowerShell):
    $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content -Raw firebase-key.json
    python search_new_player_ci.py --first "Jan" --last "Janssens" --club "Padel Club X"

Gebruik (GitHub Actions, zie .github/workflows/search-player.yml):
    workflow_dispatch-inputs first_name/last_name/club worden als
    --first/--last/--club doorgegeven.
"""
import argparse
import logging
import sys
from pathlib import Path

# --- path setup: zelfde patroon als scrape_player.py / ci_scrape_all.py ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402
from player_search import search_players  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("search_new_player_ci")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Zoek een nieuwe, nog onbekende speler op TVL (voor gebruik vanaf GitHub Actions/cloud)."
    )
    parser.add_argument("--first", default="", help="Voornaam")
    parser.add_argument("--last", default="", help="Achternaam")
    parser.add_argument("--club", default="", help="Club (optioneel)")
    args = parser.parse_args()

    first = (args.first or "").strip()
    last = (args.last or "").strip()
    club = (args.club or "").strip() or None
    name_query = f"{first} {last}".strip()

    if not first and not last:
        logger.error("Geef minstens --first of --last op (beide zijn leeg) — niets te zoeken.")
        return 1

    logger.info(f"Zoeken op TVL: voornaam='{first}' achternaam='{last}' club='{club or ''}'")
    try:
        candidates = search_players(
            first_name=first,
            last_name=last,
            club=club,
            headless=True,
            use_cache=False,
        )
    except Exception as e:
        logger.exception(f"Zoekfout tijdens player_search.search_players(): {e}")
        # Sla ook een lege cache op i.p.v. niets: zo blijft de Streamlit-app
        # niet oneindig "nog geen resultaat" tonen, maar krijgt de gebruiker
        # duidelijk "0 kandidaten gevonden" te zien in plaats van een
        # eeuwige wachtstand.
        try:
            fb.save_player_search_cache(name_query, club, "Padel", [])
        except Exception as cache_err:  # pragma: no cover - best effort
            logger.warning(f"Kon lege cache niet opslaan: {cache_err}")
        return 1

    logger.info(f"{len(candidates)} kandidaat/kandidaten gevonden voor '{name_query}'.")
    fb.save_player_search_cache(name_query, club, "Padel", candidates)
    logger.info("Resultaat opgeslagen in Firestore (player_search_cache).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
