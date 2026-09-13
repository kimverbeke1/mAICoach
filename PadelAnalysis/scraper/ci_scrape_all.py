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

PADEL_ANALYSIS_AUTO_POULE_UPDATE_2026-09-14 (nieuw, op verzoek van Kim):
BUG/ONTBREKENDE STAP (opgelost): deze dagelijkse workflow scrapete ENKEL
matchresultaten (via scrape_player.py) - nergens werd het interclub-
poule-schema (interclub_schedule/poule_reeks_url, gebruikt door
dashboard.py's "Volgende match"-scherm) automatisch bijgewerkt. Dat
gebeurde voorheen ENKEL wanneer een gebruiker zelf, handmatig, op de
"Schema nu verversen"-knop in de app klikte voor een specifieke speler.
Vandaar dat "Volgende match" bij Kim's eigen naam wél verscheen (hij had
ooit zelf die knop gebruikt) maar bij andere spelers niet (nooit
handmatig getriggerd).

Fix: NA de matchdata-scrape (hierboven, ongewijzigd) wordt voor diezelfde
lijst van verwerkte spelers ook poule_playwright.update_player_poule()
aangeroepen - dezelfde functie die de handmatige "Schema nu verversen"-knop
al gebruikte, nu gewoon automatisch voor iedereen. Elke speler krijgt zo
dagelijks een vers "volgende match"-schema, zonder dat iemand ooit zelf de
knop moet indrukken.

Te controleren via environment variables (optioneel, met veilige defaults):
    - ENABLE_POULE_UPDATE ("true"/"false", standaard "true"): zet de hele
      poule-schema-stap desgewenst volledig uit (bv. om een run te
      versnellen tijdens debuggen van enkel de matchdata-stap).
    - POULE_FORCE ("true"/"false", standaard "false"): bij "true" wordt de
      poule-URL altijd opnieuw AFGELEID uit het meest recente
      interclub-uitslagenblad (trager), i.p.v. een reeds gekende
      poule_reeks_url te hergebruiken (sneller, normale dagelijkse gang).

Belangrijke, bewuste beperking: de poule-stap wordt uitgevoerd voor DEZELFDE
(reeds mode-gefilterde) lijst van player_ids als de matchdata-stap
hierboven - dus bv. bij mode="new_users" enkel voor de nieuw toegevoegde
spelers. Dat is een bewuste keuze: een speler zonder ENIGE bekende
interclubmatch (net toegevoegd, nog niet gescraped) kan sowieso geen
poule-schema afleiden (update_player_poule() heeft een uitslagenblad-URL
uit doc.matches nodig) - de matchdata-stap moet dus sowieso eerst gebeurd
zijn, wat in deze aanroep-volgorde (poule-stap NA de matchdata-loop)
altijd het geval is.

Gebruik (lokaal testen, PowerShell):
    $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content -Raw firebase-key.json
    $env:PLAYER_IDS = "214435"          # optioneel, leeg = alle spelers
    $env:MODE = "missing"               # missing | new_users | full
    $env:ENABLE_POULE_UPDATE = "true"   # optioneel, standaard true
    $env:POULE_FORCE = "false"          # optioneel, standaard false
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
# Zelfde beleefde pauze tussen opeenvolgende poule-schema-aanvragen (aparte
# Playwright-launch per speler, dus ook hier niet te agressief scrapen).
DELAY_BETWEEN_POULE_UPDATES = 3.0

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


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def get_poule_update_enabled() -> bool:
    """PADEL_ANALYSIS_AUTO_POULE_UPDATE_2026-09-14."""
    return _get_bool_env("ENABLE_POULE_UPDATE", True)


def get_poule_force() -> bool:
    """PADEL_ANALYSIS_AUTO_POULE_UPDATE_2026-09-14."""
    return _get_bool_env("POULE_FORCE", False)


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


def run_match_scrapes(player_ids: list, mode: str) -> tuple[list, list, list]:
    """Bestaande matchdata-scrape-stap, ONGEWIJZIGD t.o.v. de vorige versie
    van dit bestand - enkel losgetrokken in een eigen functie zodat main()
    overzichtelijk kan worden uitgebreid met de nieuwe poule-stap hieronder.
    Returns (ok, failed, skipped_up_to_date) - zelfde vorm als voorheen
    inline in main()."""
    kwargs = scrape_kwargs_for_mode(mode)
    logger.info(f"scrape_player kwargs: {kwargs}")
    ok, failed, skipped_up_to_date = [], [], []
    for i, pid in enumerate(player_ids, start=1):
        logger.info(f"--- ({i}/{len(player_ids)}) Speler {pid}: matchdata ---")
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
    return ok, failed, skipped_up_to_date


def run_poule_updates(player_ids: list, force: bool) -> tuple[list, list]:
    """PADEL_ANALYSIS_AUTO_POULE_UPDATE_2026-09-14:
    Werkt voor elke speler in player_ids het interclub-poule-schema bij
    (poule_reeks_url + interclub_schedule), via de bestaande
    poule_playwright.update_player_poule() - dezelfde functie die voorheen
    ENKEL via de handmatige "Schema nu verversen"-knop in de app bereikbaar
    was. Wordt aangeroepen VOOR ALLE verwerkte spelers uit deze run, zodat
    "Volgende match" voor iedereen automatisch actueel blijft, niet enkel
    voor wie ooit zelf de knop indrukte.

    Een speler zonder gekende interclubmatch (bv. speelt geen interclub, of
    matchdata kon niet gescraped worden) geeft een verwachte, onschuldige
    fout terug ("Geen interclub-uitslagenblad-URL gevonden") - die wordt
    hier als 'overgeslagen' gelogd, niet als een echte fout die de hele run
    zou moeten laten falen.

    Returns (updated, skipped_or_failed) - elk een lijst van
    (player_id, info-string).
    """
    import poule_playwright as pp  # lazy import: enkel nodig als deze stap actief is

    updated, skipped_or_failed = [], []
    total = len(player_ids)
    for i, pid in enumerate(player_ids, start=1):
        logger.info(f"--- ({i}/{total}) Speler {pid}: poule-schema ---")
        try:
            result = pp.update_player_poule(pid, headless=True, force=force)
        except Exception as e:
            logger.exception(f"[{pid}] Onverwachte fout bij poule-update: {e}")
            skipped_or_failed.append((pid, str(e)))
            if i < total:
                time.sleep(DELAY_BETWEEN_POULE_UPDATES)
            continue
        if result.get("error"):
            logger.info(f"[{pid}] Poule-schema overgeslagen: {result['error']}")
            skipped_or_failed.append((pid, result["error"]))
        else:
            n_fixtures = result.get("fixtures", 0)
            logger.info(f"[{pid}] Poule-schema bijgewerkt: {n_fixtures} wedstrijd(en) in het schema.")
            updated.append((pid, f"{n_fixtures} wedstrijden"))
        if i < total:
            time.sleep(DELAY_BETWEEN_POULE_UPDATES)
    return updated, skipped_or_failed


def main() -> int:
    mode = get_mode()
    player_ids = get_requested_player_ids()
    player_ids = filter_by_mode(player_ids, mode)
    if not player_ids:
        logger.warning(f"Geen spelers gevonden/aangevraagd voor mode='{mode}' — niets te verversen.")
        return 0
    logger.info(f"Mode: '{mode}' — {len(player_ids)} speler(s) worden verwerkt: {player_ids}")

    ok, failed, skipped_up_to_date = run_match_scrapes(player_ids, mode)

    logger.info("=== Samenvatting matchdata ===")
    logger.info(f"Ververst: {len(ok)} — Al up-to-date: {len(skipped_up_to_date)} — Mislukt: {len(failed)}")
    for pid, err in failed:
        logger.error(f"  \u274c {pid}: {err}")

    poule_updated, poule_skipped = [], []
    if get_poule_update_enabled():
        force = get_poule_force()
        logger.info(f"=== Poule-schema bijwerken voor {len(player_ids)} speler(s) (force={force}) ===")
        poule_updated, poule_skipped = run_poule_updates(player_ids, force=force)
        logger.info("=== Samenvatting poule-schema ===")
        logger.info(f"Bijgewerkt: {len(poule_updated)} — Overgeslagen/mislukt: {len(poule_skipped)}")
        for pid, info in poule_skipped:
            logger.info(f"  \u26a0\ufe0f {pid}: {info}")
    else:
        logger.info("Poule-schema-stap uitgeschakeld via ENABLE_POULE_UPDATE=false.")

    # De workflow faalt (rode X in GitHub Actions) enkel zichtbaar als ALLE
    # verwerkte spelers mislukten voor de MATCHDATA-stap. De poule-stap is
    # een aanvullend comfort-element (net als voorheen bij de handmatige
    # knop) en beïnvloedt de eind-status van de workflow bewust niet: een
    # tegenstander die geen interclub speelt geeft bv. altijd een
    # "geen uitslagenblad gevonden"-melding, wat geen echte fout is.
    if ok or skipped_up_to_date or not player_ids:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
