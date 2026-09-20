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
poule_playwright.update_player_poule() aangeroepen. Zie ENABLE_POULE_UPDATE
/ POULE_FORCE.
PADEL_ANALYSIS_EINDRONDE_SUPPORT_2026-09-15:
update_player_poule() slaat naast de voorronde-fixtures ook de
EINDRONDE-bracket op, en scopet de voorronde op de eigen pouleId.
Zie POULE_EINDRONDE.
PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15:
Na de matchdata-scrape worden tegenstanders/partners zonder profiel
ontdekt (discover_opponent_players), krijgen ze een profiel, en wordt hun
padelstats.be playing strength opgehaald — automatisch, in dezelfde run.
PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16:
Idem, maar dan voor de TVL-klassementshistoriek (aparte, lagere limiet
KLASSEMENT_MAX omdat elke speler een volledige Playwright-sessie kost).
PADEL_ANALYSIS_INTERCLUB_ONLY_DISCOVERY_2026-09-16 ("worst case"):
discover_opponent_players() beperkt zich standaard tot interclub-matches
(ENABLE_ENRICH/interclub_only), en spelers MET bestaande matchdata krijgen
voorrang op ghost-profielen wanneer een *_MAX-limiet spelers moet laten
wachten.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): "het padelstat getal zal voortdurend wijzigen. moet dus
regelmatig geupdate worden. checken als dat werkt". Dat werkte NIET: een
speler met eenmaal een gecachete padelstat-rating werd voor ALTIJD
overgeslagen in elke volgende run, ongeacht hoe oud die waarde was.
Fix (kern zit in enrich_opponents.py): run_padelstat_for_players() ververst
nu automatisch ook ratings die ouder zijn dan PADELSTAT_STALE_DAYS, niet
enkel volledig ontbrekende. Nieuwe env var:
    - PADELSTAT_STALE_DAYS (getal, standaard 14): na hoeveel dagen een
      bestaande padelstat-rating automatisch opnieuw wordt opgehaald.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): "ik heb dit profiel verversen gekozen bij Stijn Mortier. Ik
zie dat de scraper heel wat spelers aan het verversen is (en niet Stijn
Mortier wegens beperking in aantal). [...] ik zie nu weer een heleboel
nieuwe spelers in mijn spelerslijst. [...] bedoeling is dat enkel die
speler ververst wordt (id speler meegeven)."
ROOT CAUSE: de knop "Scrape deze speler nu" (cloud_helpers.py) triggert
deze workflow met PLAYER_IDS=<1 speler>. main() riep tot nu toe ALTIJD
run_enrichment(player_ids) aan (zodra ENABLE_ENRICH=true, standaard),
ONGEACHT hoeveel spelers er gevraagd werden. Dat deed twee ongewenste
dingen voor een 1-speler-aanvraag:
  1. discover_opponent_players() vond AL die ene speler's tegenstanders/
     partners zonder eigen profiel (uit ZIJN/HAAR eigen interclub-
     matchgeschiedenis) en maakte daar nieuwe ghost-profielen voor aan.
  2. run_klassement_for_players() heeft GEEN staleness-check (enkel
     bestaat/bestaat-niet) -- had de aangevraagde speler dus al ÉÉNMAAL
     een (mogelijk foutieve/verouderde) klassement_history staan, dan werd
     die speler NOOIT opnieuw geprobeerd, terwijl de nieuw ontdekte ghost-
     profielen wél het gedeelde KLASSEMENT_MAX-budget opsouperen.
FIX: wanneer PLAYER_IDS na filtering exact 1 speler bevat, wordt nu
run_single_player_enrichment() aangeroepen i.p.v. run_enrichment(): dat
ververst ENKEL en ALTIJD (cache genegeerd) padelstat + klassement voor
die ene speler, zonder discovery/nieuwe profielen. Bij 2+ spelers (bv. de
dagelijkse cron, of een bewuste bulk-refresh) gold voorheen het volledige
discovery-gedrag (met nieuwe ghost-profielen) - zie de NIEUWSTE fix
hieronder (PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20), die dit
voor de REGULIERE/geplande bulk-run verder aanscherpt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19 (Fase E, op verzoek van Kim,
chat 2026-09-19: "check ci_scrape_all.py en de refresh_*_only.py-scripts
zoals je zelf aangeeft")
--------------------------------------------------------------------------
BEVINDING bij het nagaan van "ik wil de scraping tijd verkorten" (zie ook
Fase E, deel 1 — de venv-/Playwright-cache in de workflow-yml's): dit
bestand had, IN TEGENSTELLING TOT bijna elke andere instelling hier
(PADELSTAT_MAX, KLASSEMENT_MAX, PADELSTAT_STALE_DAYS, ...), twee HARDCODED
wachttijd-constanten (DELAY_BETWEEN_PLAYERS, DELAY_BETWEEN_POULE_UPDATES,
elk 3.0s) die NIET via een environment variable aan te passen waren.
FIX: DELAY_BETWEEN_PLAYERS en DELAY_BETWEEN_POULE_UPDATES zijn nu
overrideable via de nieuwe env vars DELAY_BETWEEN_PLAYERS_SECONDS /
DELAY_BETWEEN_POULE_UPDATES_SECONDS (default ONGEWIJZIGD: 3.0s voor beide).
⚠️ Deze pauzes zijn een BEWUSTE beleefdheids-/rate-limiting-maatregel
tegenover tennisenpadelvlaanderen.be — verlaag dit dus enkel bewust, bij
voorkeur eerst getest met een kleine batch.
--------------------------------------------------------------------------
PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19 (op verzoek van Kim, chat
2026-09-19: "weer veel profielen die aangemaakt worden :-( bekijk dat
grondig dat dat niet meer gebeurt")
--------------------------------------------------------------------------
ROOT CAUSE (in enrich_opponents.py, zie de uitgebreide toelichting daar):
discover_opponent_players() scande tot nu toe de VOLLEDIGE matchhistoriek
van elke gescrapete speler (tot 2017 terug, 16 periodes) om tegenstanders
te ontdekken — vandaar 141 nieuwe ghost-profielen na het verversen van
slechts 4 spelers in Kim's log. Verwijderde ghost-profielen kwamen daardoor
telkens terug zodra ook maar 1 speler die ooit tegen hen speelde opnieuw
gescraped werd.
FIX (destijds): enrich_opponents.discover_opponent_players() beperkt zich
sindsdien tot de N meest recente periodes per speler (DISCOVERY_RECENT_
PERIODS, standaard 2). Zie PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_
2026-09-20 hieronder voor de vervolg-fix: dit bleek niet voldoende, omdat
één period_label in de praktijk een heel interclubseizoen omvat.
--------------------------------------------------------------------------
PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20 (op verzoek van Kim,
chat 2026-09-20: "bij de run padel scraper nog steeds probleem dat teveel
profielen toegevoegd worden" — 279 nieuwe profielen na een run van 5
spelers met amper +1/+2/+2/+1/+0 nieuwe matches)
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd, zie enrich_opponents.py voor de volledige analyse):
een period_label zoals "Resultaten van week 27/2026 tot en met week
48/2026" omvat een VOLLEDIG interclubseizoen (22 weken) - de recency-limiet
van 2026-09-19 beperkte discovery dus in de praktijk tot "vrijwel het
volledige huidige+vorige seizoen", niet tot een paar recente wedstrijden.
FIX (destijds, blijft bestaan als infrastructuur): run_match_scrapes()
verzamelt, per speler, de matchrecords die scrape_player() teruggeeft als
"new_matches_this_run" en geeft die als new_matches_by_player mee aan
run_enrichment()/eo.enrich(). Discovery scant daarmee UITSLUITEND
effectief nieuwe matches i.p.v. alles binnen een brede periode-naam.
Zie PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20 hieronder: deze
fix alleen bleek in de praktijk NOG STEEDS te veel nieuwe profielen op te
leveren bij een normale bulk-run (elke speler met ook maar 1 nieuwe match
tegen een nog-onbekende tegenstander/partner levert alsnog een nieuw
profiel op — en bij tientallen eigen spelers samen kan dat nog steeds een
lange lijst worden). De infrastructuur (new_matches_by_player) blijft
bestaan en nuttig (bv. voor ENABLE_DISCOVERY=true-uitzonderingen), maar is
niet langer de primaire ghost-profiel-mitigatie.
--------------------------------------------------------------------------
PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20 (op verzoek van Kim,
chat 2026-09-20: "AUB: creeer enkel profielen van spelers die rechstreekste
tegenspeler zijn van de persoon die ik selecteer bij ploeganalyse of mensen
die ik zelf expliciet toevoeg bij toevoegen speler")
--------------------------------------------------------------------------
DEFINITIEVE FIX voor de herhaalde "lange lijst van nieuwe profielen"-
meldingen (17-20 september, meerdere pogingen: interclub_only, recency-
cap, new-matches-only - elk hielp, geen enkele loste het probleem
FUNDAMENTEEL op). ROOT CAUSE, nu pas volledig scherp: elke poging tot nu
toe probeerde de discovery-SCAN binnen de bulk-run te VERFIJNEN (minder
periodes, enkel nieuwe matches, ...) - maar Kim's eigenlijke, expliciete
wens is dat de GEPLANDE/BULK-run HELEMAAL GEEN nieuwe profielen mag
aanmaken. Nieuwe profielen mogen ENKEL ontstaan via twee, al bestaande en
correct gescoopte plekken in de APP zelf (niet in deze achtergrondtaak):
  1. Team-analyse ("🔍 Tegenstander analyseren", opponent_scout_ui.py /
     opponent_scout.py: scrape_new_opponent_players()) - deze scant
     UITSLUITEND de roster van de ENE tegenstander-ploeg die je op dat
     moment analyseert (bundle["unique_players"], via osc.scout_opponent())
     - dus effectief "directe tegenspelers van de persoon die je
     selecteert bij ploeganalyse". Dit pad blijft VOLLEDIG ONGEWIJZIGD.
  2. Expliciet "speler toevoegen" (een bewuste, door Kim zelf getriggerde
     actie) - blijft eveneens volledig ongewijzigd, dit bestand komt daar
     niet aan.
FIX (dit bestand): run_enrichment() roept eo.enrich() voortaan aan met
do_discover=get_discovery_enabled() i.p.v. onvoorwaardelijk do_discover=
True. get_discovery_enabled() leest de nieuwe env var ENABLE_DISCOVERY,
met een NIEUWE DEFAULT VAN False — de geplande/bulk-scrape (scrape-
padel.yml, alle spelers, geen specifieke tegenstander-context) maakt dus
voortaan GEEN ENKEL nieuw spelersprofiel meer aan. Padelstat/klassement-
verversing voor AL BESTAANDE profielen (eigen team + reeds gekende
tegenstanders) blijft volledig ongewijzigd werken - enkel het aanmaken van
NIEUWE profielen (ensure_profiles(), enkel bereikbaar via do_discover=True)
is uitgeschakeld in dit pad.
Zet ENABLE_DISCOVERY=true expliciet op een bewust, incidenteel getriggerde
workflow-run (bv. een eenmalige "herbouw de volledige tegenstander-
database"-actie) als je toch, bewust, de brede discovery wil laten lopen -
dat is een uitzondering, geen regulier gedrag.
--------------------------------------------------------------------------
PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20 (op verzoek van
Kim: "aangezien we toch al het padelstat klassement scrapen van padelstat.be
zou ik willen voorstellen om het officieel klassement ook al meteen van
daar te scrapen. Dan moet die scraping van 2 keer per jaar niet meer
gebeuren aangezien padelstat toch regelmatig refresht.")
--------------------------------------------------------------------------
run_padelstat_for_players() (enrich_opponents.py) haalt sindsdien, als
bijproduct van elke reguliere padelstat-ophaling, ook het officiële TVL-
klassement op (zie daar). Daarom verandert hier de DEFAULT van
ENABLE_KLASSEMENT van True naar False: de aparte, tragere TVL-klassement-
scrape (scrape_klassement.py, een volledige Playwright-sessie per speler,
en momenteel bovendien geblokkeerd door bot-detectie op
tennisenpadelvlaanderen.be) is niet langer nodig in de REGULIERE/dagelijkse
run. Deze blijft wél volledig beschikbaar en nuttig voor de MEERDERE-
periodes-historiek-grafiek (die padelstat niet kan leveren) - zet
ENABLE_KLASSEMENT=true expliciet in een incidentele/handmatige of 2x-per-
jaar geplande workflow-run wanneer je die volledige historiek wil
verversen.
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
# PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19: dit zijn nog steeds de
# DEFAULT-waarden (ongewijzigd, 3.0s) — zie get_delay_between_players()/
# get_delay_between_poule_updates() hieronder voor de env-overrideable
# versie die main() daadwerkelijk gebruikt.
DELAY_BETWEEN_PLAYERS = 3.0
DELAY_BETWEEN_POULE_UPDATES = 3.0
VALID_MODES = ("missing", "new_users", "full")
DEFAULT_MODE = "missing"
# PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: default hier BEWUST
# gelijk gehouden aan enrich_opponents.DISCOVERY_RECENT_PERIODS_DEFAULT
# (los gedefinieerd i.p.v. geïmporteerd, want deze module mag niet hard
# falen als enrich_opponents.py toevallig ontbreekt/ouder is - zie de
# bestaande lazy-import + TypeError-fallback-structuur in run_enrichment()).
# Blijft relevant als AANVULLENDE cap, ook wanneer discovery bewust via
# ENABLE_DISCOVERY=true opnieuw aangezet wordt (zie hieronder).
DEFAULT_DISCOVERY_RECENT_PERIODS = 2
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
def _get_float_env(name: str, default: float) -> float:
    """PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19: analoog aan
    _get_int_env(), maar voor de nieuwe, floating-point wachttijd-env-vars."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        logger.warning(f"{name}='{raw}' is geen getal, val terug op {default}.")
        return default
def get_poule_update_enabled() -> bool:
    return _get_bool_env("ENABLE_POULE_UPDATE", True)
def get_poule_force() -> bool:
    return _get_bool_env("POULE_FORCE", False)
def get_poule_eindronde() -> bool:
    return _get_bool_env("POULE_EINDRONDE", True)
def get_enrich_enabled() -> bool:
    return _get_bool_env("ENABLE_ENRICH", True)
def get_discovery_enabled() -> bool:
    """PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20 (op verzoek van
    Kim: "creeer enkel profielen van spelers die rechtstreekse tegenspeler
    zijn van de persoon die ik selecteer bij ploeganalyse of mensen die ik
    zelf expliciet toevoeg bij toevoegen speler"):
    Nieuwe default: False. De geplande/bulk-scrape (deze workflow, voor
    ALLE spelers) mag GEEN nieuwe spelersprofielen meer aanmaken - dat
    gebeurt voortaan UITSLUITEND via de al bestaande, correct gescoopte
    UI-paden (team-analyse voor 1 specifieke tegenstander-ploeg, en
    expliciet "speler toevoegen"), niet via deze achtergrondtaak.
    Zet ENABLE_DISCOVERY=true expliciet voor een bewuste, incidentele
    uitzondering (bv. eenmalig de volledige tegenstander-database
    herbouwen) - géén regulier gedrag."""
    return _get_bool_env("ENABLE_DISCOVERY", False)
def get_padelstat_enabled() -> bool:
    return _get_bool_env("ENABLE_PADELSTAT", True)
def get_padelstat_refresh() -> bool:
    return _get_bool_env("PADELSTAT_REFRESH", False)
def get_padelstat_max() -> int:
    return _get_int_env("PADELSTAT_MAX", 25)
def get_padelstat_stale_days() -> int:
    """PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16."""
    return _get_int_env("PADELSTAT_STALE_DAYS", 14)
def get_klassement_enabled() -> bool:
    """PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20: default
    gewijzigd van True naar False. run_padelstat_for_players() haalt het
    officiële klassement (snapshot) sindsdien al op als bijproduct van de
    padelstat-verversing die hieronder (ENABLE_PADELSTAT) sowieso al
    standaard aanstaat - de aparte, tragere TVL-scrape (volledige
    meerdere-periodes-historiek, een hele Playwright-sessie per speler) is
    daarom niet langer nodig in de REGULIERE run. Zet ENABLE_KLASSEMENT=true
    expliciet voor een incidentele/2x-per-jaar-run die de volledige
    historiek-grafiek wil verversen."""
    return _get_bool_env("ENABLE_KLASSEMENT", False)
def get_klassement_refresh() -> bool:
    return _get_bool_env("KLASSEMENT_REFRESH", False)
def get_klassement_max() -> int:
    return _get_int_env("KLASSEMENT_MAX", 8)
def get_enrich_scrape_new() -> bool:
    return _get_bool_env("ENRICH_SCRAPE_NEW", False)
def get_delay_between_players() -> float:
    """PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19: env-overrideable
    versie van DELAY_BETWEEN_PLAYERS (default ONGEWIJZIGD, 3.0s). Zie de
    module-docstring voor de waarschuwing tegen te agressief verlagen."""
    return _get_float_env("DELAY_BETWEEN_PLAYERS_SECONDS", DELAY_BETWEEN_PLAYERS)
def get_delay_between_poule_updates() -> float:
    """PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19: env-overrideable
    versie van DELAY_BETWEEN_POULE_UPDATES (default ONGEWIJZIGD, 3.0s)."""
    return _get_float_env("DELAY_BETWEEN_POULE_UPDATES_SECONDS", DELAY_BETWEEN_POULE_UPDATES)
def get_discovery_recent_periods() -> int:
    """PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: beperkt het
    ontdekken van nieuwe tegenstander-profielen tot de N meest recente
    periodes per speler (standaard 2), als AANVULLENDE cap - enkel nog
    relevant wanneer ENABLE_DISCOVERY bewust op true gezet is (zie
    get_discovery_enabled())."""
    return _get_int_env("DISCOVERY_RECENT_PERIODS", DEFAULT_DISCOVERY_RECENT_PERIODS)
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
def run_match_scrapes(
    player_ids: list, mode: str, delay_seconds: float = DELAY_BETWEEN_PLAYERS,
) -> tuple[list, list, list, dict]:
    """Matchdata-scrape-stap. Returns (ok, failed, skipped_up_to_date,
    new_matches_by_player).
    PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19: delay_seconds is nu een
    parameter (default ONGEWIJZIGD) i.p.v. de module-constante rechtstreeks
    te gebruiken — main() geeft de env-overrideable waarde door (zie
    get_delay_between_players()).
    PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20: verzamelt nog
    steeds, per speler, de matchrecords die scrape_player() teruggeeft als
    "new_matches_this_run" - deze infrastructuur blijft bestaan (nuttig
    voor een bewuste ENABLE_DISCOVERY=true-uitzondering), ook al is
    discovery sinds PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20
    standaard uitgeschakeld in de reguliere run."""
    kwargs = scrape_kwargs_for_mode(mode)
    logger.info(f"scrape_player kwargs: {kwargs}")
    ok, failed, skipped_up_to_date = [], [], []
    new_matches_by_player: dict = {}
    for i, pid in enumerate(player_ids, start=1):
        logger.info(f"--- ({i}/{len(player_ids)}) Speler {pid}: matchdata ---")
        try:
            result = scrape_player(pid, save_to_firebase=True, headless=True, **kwargs)
            new_matches_by_player[str(pid)] = result.get("new_matches_this_run") or []
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
            new_matches_by_player[str(pid)] = []
        if i < len(player_ids):
            time.sleep(delay_seconds)
    return ok, failed, skipped_up_to_date, new_matches_by_player
def run_enrichment(player_ids: list, new_matches_by_player: dict = None) -> dict:
    """PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15 +
    PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16 +
    PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16 +
    PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20.
    Ververst padelstat (incl. officieel klassement) + optioneel de
    volledige TVL-klassementshistoriek voor de opgegeven spelers.
    PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20: do_discover
    (nieuwe profielen aanmaken voor tegenstanders/partners zonder profiel)
    staat nu STANDAARD UIT in deze functie (get_discovery_enabled(),
    default False) - zie module-docstring voor de volledige toelichting.
    Padelstat/klassement-verversing voor AL BESTAANDE profielen (eigen team
    + reeds gekende tegenstanders) is hierdoor NIET beïnvloed - enkel het
    aanmaken van NIEUWE profielen is uitgeschakeld in dit pad.
    LET OP: dit is de BULK-variant (2+ spelers, bv. de dagelijkse cron of
    een bewuste multi-speler-refresh). Voor een 1-speler-aanvraag wordt in
    main() in plaats hiervan run_single_player_enrichment() gebruikt (zie
    PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19 hierboven) — GEEN
    discovery, gegarandeerde refresh van enkel die ene speler (dit was al
    zo, ongewijzigd).
    Draait NA de matchdata-scrape en VOOR de poule-stap.
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
    do_discover = get_discovery_enabled()
    do_padelstat = get_padelstat_enabled()
    do_klassement = get_klassement_enabled()
    stale_days = get_padelstat_stale_days()
    discovery_recent_periods = get_discovery_recent_periods()
    logger.info(
        f"=== Tegenstanders verrijken (discovery={do_discover} "
        f"[standaard UIT sinds 2026-09-20 - zie ENABLE_DISCOVERY], "
        f"padelstats={do_padelstat}, padelstat_max={get_padelstat_max()}, "
        f"padelstat_stale_days={stale_days}, klassement(TVL)={do_klassement}, "
        f"klassement_max={get_klassement_max()}) ==="
    )
    try:
        resultaat = eo.enrich(
            player_ids,
            do_discover=do_discover,
            do_padelstat=do_padelstat,
            padelstat_refresh=get_padelstat_refresh(),
            padelstat_max=get_padelstat_max(),
            padelstat_stale_after_days=stale_days,
            do_klassement=do_klassement,
            klassement_refresh=get_klassement_refresh(),
            klassement_max=get_klassement_max(),
            discovery_recent_periods=discovery_recent_periods,
            new_matches_by_player=new_matches_by_player,
        )
    except TypeError:
        # PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20: eerste
        # terugval-laag - probeer zonder new_matches_by_player, voor het
        # geval enrich_opponents.py deze parameter nog niet kent.
        logger.warning(
            "enrich_opponents.enrich() kent 'new_matches_by_player' nog niet — "
            "werk scraper/enrich_opponents.py bij. Val terug op de discovery_recent_periods-only-cap."
        )
        try:
            resultaat = eo.enrich(
                player_ids,
                do_discover=do_discover,
                do_padelstat=do_padelstat,
                padelstat_refresh=get_padelstat_refresh(),
                padelstat_max=get_padelstat_max(),
                padelstat_stale_after_days=stale_days,
                do_klassement=do_klassement,
                klassement_refresh=get_klassement_refresh(),
                klassement_max=get_klassement_max(),
                discovery_recent_periods=discovery_recent_periods,
            )
        except TypeError:
            # PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: tweede
            # terugval-laag - probeer zonder discovery_recent_periods, voor
            # het geval enrich_opponents.py nog ouder is.
            logger.warning(
                "enrich_opponents.enrich() kent 'discovery_recent_periods' nog niet — "
                "werk scraper/enrich_opponents.py bij. Val terug op het oude, "
                "ONBEPERKTE discovery-gedrag (indien do_discover=True)."
            )
            try:
                resultaat = eo.enrich(
                    player_ids,
                    do_discover=do_discover,
                    do_padelstat=do_padelstat,
                    padelstat_refresh=get_padelstat_refresh(),
                    padelstat_max=get_padelstat_max(),
                    padelstat_stale_after_days=stale_days,
                    do_klassement=do_klassement,
                    klassement_refresh=get_klassement_refresh(),
                    klassement_max=get_klassement_max(),
                )
            except TypeError:
                # Val terug op een NOG oudere enrich_opponents.py die ook de
                # overige nieuwste parameters nog niet kent, zodat deze
                # workflow niet crasht op een signatuur-mismatch.
                logger.warning(
                    "enrich_opponents.enrich() kent niet alle verwachte parameters — "
                    "werk scraper/enrich_opponents.py bij. Val terug op een basisaanroep."
                )
                try:
                    resultaat = eo.enrich(
                        player_ids,
                        do_discover=do_discover,
                        do_padelstat=do_padelstat,
                        padelstat_refresh=get_padelstat_refresh(),
                        padelstat_max=get_padelstat_max(),
                        do_klassement=do_klassement,
                        klassement_refresh=get_klassement_refresh(),
                        klassement_max=get_klassement_max(),
                    )
                except TypeError:
                    resultaat = eo.enrich(
                        player_ids,
                        do_discover=do_discover,
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
        # PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_ONLY_2026-09-20: dit pad kan
        # in de REGULIERE run enkel nog bereikt worden als iemand bewust
        # ENABLE_DISCOVERY=true zette - anders is do_discover=False en geeft
        # eo.enrich() hier altijd een lege lijst terug.
        logger.info(f"{len(nieuwe)} nieuw(e) spelersprofiel(en) aangemaakt voor tegenstanders (ENABLE_DISCOVERY=true actief).")
        if get_enrich_scrape_new():
            logger.info(f"ENRICH_SCRAPE_NEW=true — matchdata ophalen voor {len(nieuwe)} nieuwe speler(s).")
            ok_new, failed_new, _, _ = run_match_scrapes(nieuwe, "missing", delay_seconds=get_delay_between_players())
            logger.info(f"Nieuwe spelers gescraped: {len(ok_new)} OK, {len(failed_new)} mislukt.")
        else:
            logger.info(
                "Hun matchdata (klassement, winrate, partners) wordt opgehaald in de "
                "volgende run. Zet ENRICH_SCRAPE_NEW=true om dat meteen te doen."
            )
    p = resultaat.get("padelstat") or {}
    if p:
        logger.info(
            f"Padelstats: {p.get('opgehaald', 0)} opgehaald/ververst, {p.get('cache', 0)} nog actueel, "
            f"{p.get('niet_gevonden', 0)} niet gevonden, {p.get('fout', 0)} fout "
            f"(waarvan {p.get('klassement_opgehaald', 0)} met officieel klassement meegenomen)."
        )
        if p.get("overgeslagen_limiet"):
            logger.info(
                f"{p['overgeslagen_limiet']} speler(s) wachten op een volgende run "
                f"(limiet PADELSTAT_MAX={get_padelstat_max()})."
            )
    k = resultaat.get("klassement") or {}
    if k:
        logger.info(
            f"Klassement (TVL, volledige historiek): {k.get('opgehaald', 0)} opgehaald, "
            f"{k.get('cache', 0)} uit cache, {k.get('fout', 0)} fout."
        )
        if k.get("overgeslagen_limiet"):
            logger.info(
                f"{k['overgeslagen_limiet']} speler(s) wachten op een volgende run "
                f"(limiet KLASSEMENT_MAX={get_klassement_max()})."
            )
    return resultaat
def run_single_player_enrichment(player_id: str) -> dict:
    """PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19 (op verzoek van
    Kim: "bedoeling is dat enkel die speler ververst wordt (id speler
    meegeven)").
    Roept enrich_opponents.run_single_player_refresh() aan: GEEN discovery,
    GEEN nieuwe ghost-profielen, en een GEFORCEERDE refresh (cache/
    staleness genegeerd) van padelstat (incl. officieel klassement) +
    optioneel de volledige TVL-klassementshistoriek voor exact deze ene
    speler. Gebruikt door main() zodra er na filtering exact 1 speler
    overblijft (zie daar)."""
    leeg = {"nieuwe_profielen": [], "padelstat": {}, "klassement": {}}
    try:
        import enrich_opponents as eo
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"enrich_opponents niet beschikbaar ({e}) — losse-speler-verversing overgeslagen."
        )
        return leeg
    try:
        result = eo.run_single_player_refresh(player_id)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Losse-speler-verversing mislukt voor {player_id}: {e}")
        return leeg
    return {
        "nieuwe_profielen": [],
        "padelstat": result.get("padelstat", {}),
        "klassement": result.get("klassement", {}),
    }
def run_poule_updates(
    player_ids: list, force: bool, include_eindronde: bool = True,
    delay_seconds: float = DELAY_BETWEEN_POULE_UPDATES,
) -> tuple[list, list]:
    """PADEL_ANALYSIS_AUTO_POULE_UPDATE_2026-09-14 +
    PADEL_ANALYSIS_EINDRONDE_SUPPORT_2026-09-15.
    PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19: delay_seconds is nu een
    parameter (default ONGEWIJZIGD) i.p.v. de module-constante rechtstreeks
    te gebruiken."""
    import poule_playwright as pp
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
                time.sleep(delay_seconds)
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
            if n_fixtures > 60:
                logger.warning(
                    f"[{pid}] Ongewoon veel voorronde-fixtures ({n_fixtures}). "
                    f"Controleer de pouleId-scoping in schedule_scraper.parse_poule_schedule()."
                )
            updated.append((pid, detail))
        if i < total:
            time.sleep(delay_seconds)
    return updated, skipped_or_failed
def main() -> int:
    mode = get_mode()
    player_ids = get_requested_player_ids()
    player_ids = filter_by_mode(player_ids, mode)
    if not player_ids:
        logger.warning(f"Geen spelers gevonden/aangevraagd voor mode='{mode}' — niets te verversen.")
        return 0
    # PADEL_ANALYSIS_CONFIGURABLE_DELAYS_2026-09-19: eenmalig opgehaald en
    # doorgegeven, i.p.v. de module-constanten rechtstreeks in de
    # onderliggende functies te gebruiken — zie module-docstring.
    delay_players = get_delay_between_players()
    delay_poule = get_delay_between_poule_updates()
    if delay_players != DELAY_BETWEEN_PLAYERS or delay_poule != DELAY_BETWEEN_POULE_UPDATES:
        logger.info(
            f"Aangepaste wachttijden actief: tussen spelers={delay_players}s "
            f"(standaard {DELAY_BETWEEN_PLAYERS}s), tussen poule-updates={delay_poule}s "
            f"(standaard {DELAY_BETWEEN_POULE_UPDATES}s)."
        )
    logger.info(f"Mode: '{mode}' — {len(player_ids)} speler(s) worden verwerkt: {player_ids}")
    if os.environ.get("ENABLE_DISCOVERY", "").strip() == "":
        logger.info(
            "ENABLE_DISCOVERY niet expliciet gezet — PADEL_ANALYSIS_DISCOVERY_SCOPED_TO_UI_"
            "ONLY_2026-09-20: default is nu False. Deze bulk-run maakt dus GEEN nieuwe "
            "spelersprofielen aan - dat gebeurt voortaan enkel via team-analyse (per specifieke "
            "tegenstander-ploeg) of expliciet 'speler toevoegen' in de app zelf."
        )
    if os.environ.get("ENABLE_KLASSEMENT", "").strip() == "":
        logger.info(
            "ENABLE_KLASSEMENT niet expliciet gezet — PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_"
            "VIA_PADELSTAT_2026-09-20: default is nu False (was True). Het officiële "
            "klassement wordt voortaan als snapshot meegenomen via de padelstat-verversing "
            "hieronder. Zet ENABLE_KLASSEMENT=true voor een incidentele/2x-per-jaar-run die "
            "de volledige TVL-historiek (meerdere periodes) wil verversen."
        )
    ok, failed, skipped_up_to_date, new_matches_by_player = run_match_scrapes(
        player_ids, mode, delay_seconds=delay_players
    )
    logger.info("=== Samenvatting matchdata ===")
    logger.info(f"Ververst: {len(ok)} — Al up-to-date: {len(skipped_up_to_date)} — Mislukt: {len(failed)}")
    for pid, err in failed:
        logger.error(f"  \u274c {pid}: {err}")
    totaal_nieuwe_matches = sum(len(v) for v in new_matches_by_player.values())
    logger.info(f"Netto nieuwe matches deze run (over alle spelers): {totaal_nieuwe_matches}")
    enrich_result = {}
    if get_enrich_enabled():
        # PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19: bij EXACT 1
        # aangevraagde speler (bv. de "Scrape deze speler nu"-knop) NOOIT
        # discovery/nieuwe ghost-profielen aanmaken, en die ene speler altijd
        # geforceerd verversen (cache/staleness genegeerd) i.p.v. de
        # bulk-verrijking te draaien die met andere (ghost-)spelers kan
        # concurreren om het gedeelde *_MAX-budget.
        if len(player_ids) == 1:
            logger.info(
                f"=== Losse-speler-verversing gedetecteerd (PLAYER_IDS bevat exact 1 speler: "
                f"{player_ids[0]}) — ENKEL deze speler wordt ververst (padelstat+klassement), "
                "GEEN discovery/nieuwe tegenstander-profielen. ==="
            )
            enrich_result = run_single_player_enrichment(player_ids[0])
        else:
            enrich_result = run_enrichment(player_ids, new_matches_by_player=new_matches_by_player)
        logger.info("=== Samenvatting verrijking ===")
        logger.info(
            f"Nieuwe profielen: {len(enrich_result.get('nieuwe_profielen') or [])} — "
            f"padelstats opgehaald/ververst: {(enrich_result.get('padelstat') or {}).get('opgehaald', 0)} — "
            f"officieel klassement via padelstat: {(enrich_result.get('padelstat') or {}).get('klassement_opgehaald', 0)} — "
            f"klassement (TVL, historiek) opgehaald: {(enrich_result.get('klassement') or {}).get('opgehaald', 0)}"
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
            player_ids, force=force, include_eindronde=include_eindronde, delay_seconds=delay_poule,
        )
        logger.info("=== Samenvatting poule-schema ===")
        logger.info(f"Bijgewerkt: {len(poule_updated)} — Overgeslagen/mislukt: {len(poule_skipped)}")
        for pid, info in poule_skipped:
            logger.info(f"  \u26a0\ufe0f {pid}: {info}")
    else:
        logger.info("Poule-schema-stap uitgeschakeld via ENABLE_POULE_UPDATE=false.")
    if ok or skipped_up_to_date or not player_ids:
        return 0
    return 1
if __name__ == "__main__":
    sys.exit(main())
