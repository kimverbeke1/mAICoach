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
    - "missing" (standaard) -> ENKEL periodes die nog nooit gescraped zijn.
    - "new_users"           -> scrape ENKEL spelers die nog nooit eerder
      gescraped zijn (geen bestaand document in de 'players'-collectie).
    - "full"                -> forceer een volledige herscrape van alle
      periodes voor de opgegeven spelers (traag, normaal niet nodig).

PADEL_ANALYSIS_AUTO_POULE_UPDATE_2026-09-14:
NA de matchdata-scrape wordt voor diezelfde lijst spelers ook
poule_playwright.update_player_poule() aangeroepen — dezelfde functie die de
handmatige "Schema nu verversen"-knop al gebruikte, nu automatisch voor
iedereen. Zie ENABLE_POULE_UPDATE / POULE_FORCE.

PADEL_ANALYSIS_EINDRONDE_SUPPORT_2026-09-15:
update_player_poule() slaat naast de voorronde-fixtures ook de
EINDRONDE-bracket op, en scopet de voorronde op de eigen pouleId.
Zie POULE_EINDRONDE.

PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15 (op verzoek van Kim):
BUG/ONTBREKENDE STAP (opgelost): na het ophalen van een poule-schema bleven in
de tegenploeg-overzichtstabel bij verschillende spelers (De Purcq Hilde,
Brede Hilde, Severine, ...) de kolommen playing strength, klassement, winrate
historiek en vaste partner historiek LEEG. Dat leek op een mislukte scrape,
maar het was EEN oorzaak met drie zichtbare gevolgen:
opponent_dossier.build_player_summary() doet
    doc = fb.get_player(player_id) or ...
    matches = doc.get("matches", []) or []
Heeft een tegenstander geen EIGEN document, dan is matches leeg, en dan zijn
winrate/partners/vorm/periodes leeg, is er geen klassementshistoriek, én
ontbreekt de playing strength — want bulk_fetch_padelstat_ratings loopt over
fb.search_player_profiles() en die speler stond daar niet in.
De poule-scrape haalt immers enkel FIXTURES en NAMEN op; ze maakt geen
spelers aan. Tegenstanders bestonden dus enkel als naam in een uitslagenblad.
Fix: een nieuwe verrijkingsstap (enrich_opponents.py) die
  1. tegenstanders/partners zonder profiel ontdekt uit onze eigen matchdata,
  2. voor hen een player_profiles-document aanmaakt,
  3. meteen hun padelstats.be playing strength ophaalt.
Vanaf dan pikken ALLE bestaande bulk-acties (matchdata-scrape, klassement,
padelstats) die spelers vanzelf op.
De padelstats-ophaling gebeurt daarmee automatisch in dezelfde run als de
TVL-scrape, in plaats van via een handmatig `python
bulk_fetch_padelstat_ratings.py`.
Belangrijk over de VOLGORDE: de verrijkingsstap draait NA de matchdata-scrape
(ze heeft matchrecords nodig om tegenstanders in te vinden) maar VOOR de
poule-stap. Nieuw aangemaakte spelers hebben in DEZE run nog geen matchdata;
die wordt opgehaald in de volgende run (of meteen als je
ENRICH_SCRAPE_NEW=true zet).

--------------------------------------------------------------------------
PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG/ONTBREKENDE STAP (opgelost): check_player_data.py --team-of toonde dat
AUTOMATISCH ontdekte tegenstanders (via enrich_opponents, hierboven) wél een
profiel en een padelstat-rating kregen, maar STRUCTUREEL geen
klassementshistoriek — enkel handmatig toegevoegde spelers hadden dat.
Oorzaak: klassement werd enkel opgehaald via een lokaal Streamlit-vinkje of
de "Ververs alles"-knop, geen van beide draait in deze workflow.
Fix: enrich_opponents.enrich() heeft nu een DERDE stap
(run_klassement_for_players, zie enrich_opponents.py), die hier standaard
mee aangeroepen wordt naast de bestaande padelstat-stap. Zie
ENABLE_KLASSEMENT / KLASSEMENT_REFRESH / KLASSEMENT_MAX.
Klassement kost aanzienlijk meer tijd per speler dan padelstat (een volledige
Playwright-sessie met meerdere periode-selecties, ~30-90s per speler, tegen
~5-10s voor padelstat) — vandaar een aparte, lagere limiet
(KLASSEMENT_MAX, standaard 8 i.p.v. PADELSTAT_MAX=25).

Environment variables (optioneel, met veilige defaults):
    - ENABLE_POULE_UPDATE ("true"/"false", standaard "true")
    - POULE_FORCE         ("true"/"false", standaard "false")
    - POULE_EINDRONDE     ("true"/"false", standaard "true")
    - ENABLE_ENRICH       ("true"/"false", standaard "true"): tegenstanders
      ontdekken + profielen aanmaken + padelstats + klassement ophalen.
    - ENABLE_PADELSTAT    ("true"/"false", standaard "true"): enkel de
      padelstats-deelstap van de verrijking.
    - PADELSTAT_REFRESH   ("true"/"false", standaard "false"): negeer de
      padelstats-cache en haal iedereen opnieuw op (traag).
    - PADELSTAT_MAX       (getal, standaard 25): max aantal padelstats-
      ophalingen per run. Elke speler kost ~5-10 seconden.
    - ENABLE_KLASSEMENT   ("true"/"false", standaard "true"): enkel de
      klassement-deelstap van de verrijking.
    - KLASSEMENT_REFRESH  ("true"/"false", standaard "false"): negeer de
      klassement-cache en haal iedereen opnieuw op (traag).
    - KLASSEMENT_MAX      (getal, standaard 8): max aantal klassement-
      ophalingen per run. Elke speler kost ~30-90 seconden.
    - ENRICH_SCRAPE_NEW   ("true"/"false", standaard "false"): scrape de NET
      aangemaakte tegenstanders meteen in dezelfde run (trager, maar je hebt
      hun matchdata dan onmiddellijk).

Gebruik (lokaal testen, PowerShell):
    $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content -Raw firebase-key.json
    $env:PLAYER_IDS = "214435"
    $env:MODE = "missing"
    $env:ENABLE_ENRICH = "true"
    $env:PADELSTAT_MAX = "25"
    $env:KLASSEMENT_MAX = "8"
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
# Zelfde beleefde pauze tussen opeenvolgende poule-schema-aanvragen.
DELAY_BETWEEN_POULE_UPDATES = 3.0

VALID_MODES = ("missing", "new_users", "full")
DEFAULT_MODE = "missing"


def get_all_player_ids() -> list:
    """Alle player_id's uit player_profiles."""
    docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
    ids = []
    for d in docs:
        data = d.to_dict() or {}
        pid = data.get("player_id") or d.id
        if pid:
            ids.append(str(pid))
    return ids


def get_requested_player_ids() -> list:
    """Bepaalt WELKE spelers deze run in aanmerking neemt."""
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


def _get_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(f"{name}='{raw}' is geen getal, val terug op {default}.")
        return default


def get_poule_update_enabled() -> bool:
    return _get_bool_env("ENABLE_POULE_UPDATE", True)


def get_poule_force() -> bool:
    return _get_bool_env("POULE_FORCE", False)


def get_poule_eindronde() -> bool:
    """PADEL_ANALYSIS_EINDRONDE_SUPPORT_2026-09-15."""
    return _get_bool_env("POULE_EINDRONDE", True)


def get_enrich_enabled() -> bool:
    """PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15."""
    return _get_bool_env("ENABLE_ENRICH", True)


def get_padelstat_enabled() -> bool:
    """PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15."""
    return _get_bool_env("ENABLE_PADELSTAT", True)


def get_padelstat_refresh() -> bool:
    return _get_bool_env("PADELSTAT_REFRESH", False)


def get_padelstat_max() -> int:
    return _get_int_env("PADELSTAT_MAX", 25)


def get_klassement_enabled() -> bool:
    """PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16."""
    return _get_bool_env("ENABLE_KLASSEMENT", True)


def get_klassement_refresh() -> bool:
    """PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16."""
    return _get_bool_env("KLASSEMENT_REFRESH", False)


def get_klassement_max() -> int:
    """PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16."""
    return _get_int_env("KLASSEMENT_MAX", 8)


def get_enrich_scrape_new() -> bool:
    return _get_bool_env("ENRICH_SCRAPE_NEW", False)


def filter_by_mode(player_ids: list, mode: str) -> list:
    """Mode-specifieke voorselectie VOOR het scrapen begint."""
    if mode != "new_users":
        return player_ids

    new_only = []
    for pid in player_ids:
        try:
            existing = fb.get_player(pid)
        except Exception as e:
            logger.warning(f"[{pid}] Kon bestaand document niet checken ({e}) — overgeslagen voor mode=new_users.")
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
    return {"force_full_refresh": False, "refresh_recent": 0, "strict_missing_only": True}


def run_match_scrapes(player_ids: list, mode: str) -> tuple[list, list, list]:
    """Matchdata-scrape-stap. Returns (ok, failed, skipped_up_to_date)."""
    kwargs = scrape_kwargs_for_mode(mode)
    logger.info(f"scrape_player kwargs: {kwargs}")

    ok, failed, skipped_up_to_date = [], [], []

    for i, pid in enumerate(player_ids, start=1):
        logger.info(f"--- ({i}/{len(player_ids)}) Speler {pid}: matchdata ---")
        try:
            result = scrape_player(pid, save_to_firebase=True, headless=True, **kwargs)
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


def run_enrichment(player_ids: list) -> dict:
    """PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15 +
    PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16.

    Ontdekt tegenstanders/partners zonder profiel, maakt die profielen aan,
    haalt hun padelstats.be playing strength op, EN (nieuw) hun
    klassementshistoriek. Zie de moduledocstring voor de volledige uitleg
    over waarom dit nodig is.

    Draait NA de matchdata-scrape (heeft matchrecords nodig om tegenstanders
    in te vinden) en VOOR de poule-stap.
    """
    leeg = {"nieuwe_profielen": [], "padelstat": {}, "klassement": {}}
    try:
        import enrich_opponents as eo
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"enrich_opponents niet beschikbaar ({e}) — verrijkingsstap overgeslagen. "
            "Plaats enrich_opponents.py naast dit bestand in de scraper-map."
        )
        return leeg

    do_padelstat = get_padelstat_enabled()
    do_klassement = get_klassement_enabled()
    logger.info(
        f"=== Tegenstanders verrijken (padelstats={do_padelstat}, "
        f"padelstat_max={get_padelstat_max()}, klassement={do_klassement}, "
        f"klassement_max={get_klassement_max()}) ==="
    )

    try:
        resultaat = eo.enrich(
            player_ids,
            do_discover=True,
            do_padelstat=do_padelstat,
            padelstat_refresh=get_padelstat_refresh(),
            padelstat_max=get_padelstat_max(),
            do_klassement=do_klassement,
            klassement_refresh=get_klassement_refresh(),
            klassement_max=get_klassement_max(),
        )
    except TypeError:
        # PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16: val terug op de oudere
        # enrich_opponents.py (zonder klassement-parameters) als die nog niet
        # is bijgewerkt, zodat deze workflow niet crasht op een mismatch.
        logger.warning(
            "enrich_opponents.enrich() kent de klassement-parameters nog niet — "
            "werk scraper/enrich_opponents.py bij om klassement automatisch mee "
            "op te halen. Val terug op enkel discover+padelstat."
        )
        resultaat = eo.enrich(
            player_ids,
            do_discover=True,
            do_padelstat=do_padelstat,
            padelstat_refresh=get_padelstat_refresh(),
            padelstat_max=get_padelstat_max(),
        )
        resultaat.setdefault("klassement", {})
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Verrijkingsstap mislukt: {e}")
        return leeg

    nieuwe = resultaat.get("nieuwe_profielen") or []
    if nieuwe:
        logger.info(f"{len(nieuwe)} nieuw(e) spelersprofiel(en) aangemaakt voor tegenstanders.")

        if get_enrich_scrape_new():
            logger.info(f"ENRICH_SCRAPE_NEW=true — matchdata ophalen voor {len(nieuwe)} nieuwe speler(s).")
            ok_new, failed_new, _ = run_match_scrapes(nieuwe, "missing")
            logger.info(f"Nieuwe spelers gescraped: {len(ok_new)} OK, {len(failed_new)} mislukt.")
        else:
            logger.info(
                "Hun matchdata (klassement, winrate, partners) wordt opgehaald in de "
                "volgende run. Zet ENRICH_SCRAPE_NEW=true om dat meteen te doen."
            )

    p = resultaat.get("padelstat") or {}
    if p:
        logger.info(
            f"Padelstats: {p.get('opgehaald', 0)} opgehaald, {p.get('cache', 0)} uit cache, "
            f"{p.get('niet_gevonden', 0)} niet gevonden, {p.get('fout', 0)} fout."
        )
        if p.get("overgeslagen_limiet"):
            logger.info(
                f"{p['overgeslagen_limiet']} speler(s) wachten op een volgende run "
                f"(limiet PADELSTAT_MAX={get_padelstat_max()})."
            )

    # PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16.
    k = resultaat.get("klassement") or {}
    if k:
        logger.info(
            f"Klassement: {k.get('opgehaald', 0)} opgehaald, {k.get('cache', 0)} uit cache, "
            f"{k.get('fout', 0)} fout."
        )
        if k.get("overgeslagen_limiet"):
            logger.info(
                f"{k['overgeslagen_limiet']} speler(s) wachten op een volgende run "
                f"(limiet KLASSEMENT_MAX={get_klassement_max()})."
            )

    return resultaat


def run_poule_updates(player_ids: list, force: bool, include_eindronde: bool = True) -> tuple[list, list]:
    """PADEL_ANALYSIS_AUTO_POULE_UPDATE_2026-09-14 +
    PADEL_ANALYSIS_EINDRONDE_SUPPORT_2026-09-15.

    Werkt per speler het interclub-poule-schema bij (poule_reeks_url +
    interclub_schedule + interclub_eindronde).

    Een speler zonder gekende interclubmatch geeft een verwachte, onschuldige
    fout terug ("Geen interclub-uitslagenblad-URL gevonden") — die wordt hier
    als 'overgeslagen' gelogd, niet als een echte fout.
    """
    import poule_playwright as pp  # lazy import: enkel nodig als deze stap actief is

    updated, skipped_or_failed = [], []
    total = len(player_ids)

    for i, pid in enumerate(player_ids, start=1):
        logger.info(f"--- ({i}/{total}) Speler {pid}: poule-schema ---")
        try:
            try:
                result = pp.update_player_poule(
                    pid, headless=True, force=force, include_eindronde=include_eindronde
                )
            except TypeError:
                logger.warning(
                    f"[{pid}] poule_playwright kent 'include_eindronde' niet — "
                    f"werk scraper/poule_playwright.py bij om de eindronde mee op te slaan."
                )
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
            n_eind = result.get("eindronde", 0)
            n_pending = result.get("eindronde_pending", 0)
            poule_label = result.get("poule_label") or "poule ?"

            detail = f"{n_fixtures} wedstrijd(en) in {poule_label}"
            if n_eind:
                detail += f", eindronde: {n_eind} wedstrijd(en)"
                if n_pending:
                    detail += f" ({n_pending} nog in te vullen)"
            logger.info(f"[{pid}] Poule-schema bijgewerkt: {detail}.")

            # Een poule van 6 ploegen telt 15 wedstrijden. Veel meer wijst op
            # een scoping-probleem (zie PADEL_ANALYSIS_POULE_SCOPE_FIX).
            if n_fixtures > 60:
                logger.warning(
                    f"[{pid}] Ongewoon veel voorronde-fixtures ({n_fixtures}). "
                    f"Controleer de pouleId-scoping in schedule_scraper.parse_poule_schedule()."
                )

            updated.append((pid, detail))

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

    # PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15: NA de matchdata (nodig
    # om tegenstanders in te vinden) en VOOR de poule-stap.
    enrich_result = {}
    if get_enrich_enabled():
        enrich_result = run_enrichment(player_ids)
        logger.info("=== Samenvatting verrijking ===")
        logger.info(
            f"Nieuwe profielen: {len(enrich_result.get('nieuwe_profielen') or [])} — "
            f"padelstats opgehaald: {(enrich_result.get('padelstat') or {}).get('opgehaald', 0)} — "
            f"klassement opgehaald: {(enrich_result.get('klassement') or {}).get('opgehaald', 0)}"
        )
    else:
        logger.info("Verrijkingsstap uitgeschakeld via ENABLE_ENRICH=false.")

    poule_updated, poule_skipped = [], []
    if get_poule_update_enabled():
        force = get_poule_force()
        include_eindronde = get_poule_eindronde()
        logger.info(
            f"=== Poule-schema bijwerken voor {len(player_ids)} speler(s) "
            f"(force={force}, eindronde={include_eindronde}) ==="
        )
        poule_updated, poule_skipped = run_poule_updates(
            player_ids, force=force, include_eindronde=include_eindronde
        )
        logger.info("=== Samenvatting poule-schema ===")
        logger.info(f"Bijgewerkt: {len(poule_updated)} — Overgeslagen/mislukt: {len(poule_skipped)}")
        for pid, info in poule_skipped:
            logger.info(f"  \u26a0\ufe0f {pid}: {info}")
    else:
        logger.info("Poule-schema-stap uitgeschakeld via ENABLE_POULE_UPDATE=false.")

    # De workflow faalt (rode X in GitHub Actions) enkel zichtbaar als ALLE
    # verwerkte spelers mislukten voor de MATCHDATA-stap. De verrijkings- en
    # poule-stappen zijn aanvullend en beïnvloeden de eind-status bewust niet.
    if ok or skipped_up_to_date or not player_ids:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
