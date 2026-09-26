# -*- coding: utf-8 -*-
"""
discover_poule_players.py — PADEL_ANALYSIS_POULE_PRESCAN_2026-09-19 (Fase D2,
op verzoek van Kim, chat 2026-09-19).

Kim's melding, samengevat: "Nu ik er aan denk is het misschien wel beter om
in de achtergrond al meteen alle spelers van je poule op te halen op
voorhand. bv. om middernacht. Dat kan gemakkelijk na match 1. [...] rekening
houden dat een ploeg plots extra spelers kan gebruikt hebben. [...] zo veel
mogelijk op voorhand gescrapt is en dan zeker ook goed op letten dat je
wanneer nodig enkel de missing data of data die kan gewijzigd is refreshen."

Locatie: PadelAnalysis/scraper/discover_poule_players.py (naast
ci_scrape_all.py, refresh_padelstat_only.py, enrich_opponents.py — zelfde
path-setup patroon).

--------------------------------------------------------------------------
DOEL EN ONTWERPKEUZE: hergebruik, geen nieuwe scrape-logica
--------------------------------------------------------------------------
Dit script doet ZELF geen matchdata-, padelstat- of klassement-scrape — het
bepaalt ENKEL, requests-only (GEEN Playwright nodig, dus snel en licht),
WELKE spelers er over de VOLLEDIGE poule (niet enkel de eerstvolgende
tegenstander) besproken moeten worden, en geeft die lijst door aan de
BESTAANDE, al goed geteste pijplijn (ci_scrape_all.py — matchdata +
padelstat + klassement, met zijn eigen staleness-/cache-skip-logica).

Waarom dit NIET via enrich_opponents.discover_opponent_players() kan: die
functie scant UITSLUITEND de matches van de meegegeven player_ids zelf
(dus onze EIGEN spelers se interclub-tegenstanders/partners) — ploegen die
we dit seizoen nog nooit gespeeld hebben (bv. de 3de/4de ronde-tegenstander
in de poule) komen daar NOOIT in voor. Voor een ECHTE volledige poule-
pre-scrape is dus een ANDERE discovery-bron nodig: het reeds opgeslagen
poule-schema (interclub_schedule, zie page_lineup_lab.py/schedule_scraper.py)
geeft ALLE ploegen in de poule, en opponent_scout.scout_opponent() kan van
ELKE ploeg (niet enkel de eerstvolgende tegenstander) de spelers uit hun
reeds gespeelde wedstrijden dit seizoen afleiden — via scraper_v2, dus
UITSLUITEND requests + BeautifulSoup, geen browser nodig.

--------------------------------------------------------------------------
STAP 1: welke poules volgen we? (alle eigen, gevolgde spelers)
--------------------------------------------------------------------------
Elk player_profiles-document met een opgeslagen `interclub_schedule` (dat
schema wordt gevuld zodra iemand ooit "Volgende match" laadt, zie
page_lineup_lab.py/schedule_scraper.py) representeert een poule die Kim
actief volgt. Dit script doorloopt ALLE zulke profielen (niet enkel de
huidige "home_player_id"), zodat het ook werkt als Kim meerdere spelers/
teams tegelijk volgt.

Per gevolgd profiel wordt (via schedule_scraper.identify_own_ploeg_id(),
dezelfde functie die de UI gebruikt) de EIGEN ploeg herkend en uitgesloten
— we willen enkel de ANDERE ploegen in de poule pre-scannen.

--------------------------------------------------------------------------
STAP 2: per andere ploeg, hun spelers ophalen uit reeds gespeelde matchen
--------------------------------------------------------------------------
Voor elke andere ploeg in de poule: hoeveel van hun wedstrijden zijn al
gespeeld (played=True in het opgeslagen schema)? Is dat er minstens 1, dan
haalt opponent_scout.scout_opponent() de spelers op UIT AL HUN gespeelde
wedstrijden dit seizoen (lookback = aantal gespeelde wedstrijden, dus NIET
beperkt tot de laatste 1 zoals bij de eerstvolgende tegenstander) — dit is
exact hoe Kim's vraag "een ploeg kan plots extra spelers gebruikt hebben"
gedekt wordt: een speler die pas in wedstrijd 3 opdook, wordt hier ook
gevonden, ook al kenden we hem/haar nog niet van wedstrijd 1.

--------------------------------------------------------------------------
STAP 3: nieuw vs. gekend, en een batch-limiet voor VOLLEDIG nieuwe spelers
--------------------------------------------------------------------------
Een reeds gekende speler (heeft al een 'players'-document met matchdata)
is GOEDKOOP om opnieuw te bekijken: ci_scrape_all.py se mode="missing"
slaat hem/haar bijna altijd snel over ("up_to_date", geen Playwright-
sessie nodig) en enrich_opponents.py se padelstat/klassement-staleness-
check doet hetzelfde. Een VOLLEDIG NIEUWE speler (nog nooit gezien) kost
wél een echte Playwright-sessie voor matchdata, plus padelstat, plus
klassement — dat is de dominante tijdskost, en bij een grote poule (bv.
8 ploegen x 4-5 spelers) kan dat de 30-minuten-limiet van GitHub Actions
overschrijden bij de EERSTE run.

Fix: nieuwe spelers worden gecapt op PRESCAN_NEW_PLAYERS_MAX (env,
standaard 15) per run — wie er deze keer niet bij is, wordt bij de
VOLGENDE (nachtelijke) run GEWOON OPNIEUW gevonden door dezelfde discovery
hierboven (want die speler heeft dan nog steeds geen 'players'-document),
en komt dan opnieuw in aanmerking. Geen aparte queue/bookkeeping nodig —
zelfhelend over meerdere nachten, exact hetzelfde patroon als
refresh_padelstat_only.py se PADELSTAT_MAX-batching. Nieuwe spelers worden
VOOR de reeds gekende spelers in de resulterende PLAYER_IDS-lijst gezet,
zodat ze binnen ci_scrape_all.py se padelstat/klassement-budget (dat de
volgorde van de meegegeven lijst als prioriteit gebruikt zodra iedereen
al matchdata heeft, zie _prioritize() in enrich_opponents.py) voorrang
krijgen op reeds bekende, gewoon-te-verversen spelers.

--------------------------------------------------------------------------
UITVOER
--------------------------------------------------------------------------
Schrijft de resulterende, kant-en-klare PLAYER_IDS-string (komma-lijst)
naar $GITHUB_OUTPUT (voor de volgende workflow-stap/job) EN naar een klein
Firestore-samenvattingsdocument (app_state/poule_prescan_state) — dat
laatste is de basis voor een latere "laatst pre-scand op..."-weergave in
de UI (Fase D3), maar wordt in DIT script al voorzien zodat D3 daar direct
op kan verder bouwen zonder dit script opnieuw te moeten aanpassen.

Environment variables (optioneel, met veilige defaults):
    - PRESCAN_NEW_PLAYERS_MAX (getal, standaard 15)
    - PRESCAN_DELAY_BETWEEN_TEAMS (seconden, standaard 1.5)

Gebruik (lokaal testen, PowerShell):
    $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content -Raw firebase-key.json
    python discover_poule_players.py
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402
import schedule_scraper as ss  # noqa: E402
import opponent_scout as osc  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("discover_poule_players")

DEFAULT_NEW_PLAYERS_MAX = 15
DEFAULT_DELAY_BETWEEN_TEAMS = 1.5
PRESCAN_STATE_COLLECTION = "app_state"
PRESCAN_STATE_DOC = "poule_prescan_state"


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
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_new_players_max() -> int:
    return _get_int_env("PRESCAN_NEW_PLAYERS_MAX", DEFAULT_NEW_PLAYERS_MAX)


def get_delay_between_teams() -> float:
    return _get_float_env("PRESCAN_DELAY_BETWEEN_TEAMS", DEFAULT_DELAY_BETWEEN_TEAMS)


def get_tracked_profiles() -> list[dict]:
    """Alle player_profiles die een opgeslagen poule-schema hebben — dit
    zijn de spelers/teams die Kim actief volgt via 'Volgende match'."""
    try:
        profiles = fb.search_player_profiles("", limit=10_000) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Kon profielen niet lezen: {e}")
        return []
    return [p for p in profiles if p.get("interclub_schedule")]


def _own_known_interclub_matches(player_id: str) -> list[dict]:
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        doc = {}
    return [m for m in (doc.get("matches", []) or []) if m.get("match_type") == "interclub"]


def _mark_team_players_frozen_state(
    ploeg_id: str, player_ids: list[str], still_upcoming: bool,
) -> None:
    """PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26: zet (of verwijdert)
    auto_update_frozen op elk speler-profiel van deze ploeg, gebaseerd op of
    de ploeg nog een NIET-gespeelde fixture heeft in een gevolgde poule.

    Dit is een LEVENDE, elke run herberekende status - geen eenmalige,
    permanente markering. still_upcoming=True zet auto_update_frozen
    expliciet terug op False (zelf-herstellend bij een gewijzigde
    kalender), still_upcoming=False zet het op True (regulier/bulk
    bijwerken van deze speler overslaan - zie enrich_opponents.py).

    Fouten per speler worden gelogd maar blokkeren de rest van de run niet
    - dit is een aanvullende optimalisatie, geen kritiek pad."""
    for pid in player_ids:
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(
                {
                    "auto_update_frozen": not still_upcoming,
                    "auto_update_frozen_reason": (
                        None if still_upcoming
                        else "geen geplande ontmoetingen meer in de gevolgde poules"
                    ),
                    "auto_update_frozen_via_ploeg_id": str(ploeg_id),
                    "auto_update_frozen_updated_at": _utc_now_iso(),
                },
                merge=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{pid}] Kon auto_update_frozen-status niet bijwerken: {e}")


def discover_all_poule_teams() -> dict:
    """Doorloopt elk gevolgd eigen-profiel, herkent de eigen ploeg, en
    verzamelt ALLE ANDERE ploegen (over alle gevolgde poules heen).
    Returns {ploeg_id: {"name":..., "poule_label":..., "fixtures": [...]}}.
    Bij meerdere gevolgde profielen in DEZELFDE poule wordt de eerste
    gevonden fixtures-lijst gebruikt (ze zijn identiek, gewoon uit een
    ander profiel opgeslagen)."""
    teams: dict = {}
    tracked = get_tracked_profiles()
    logger.info(f"{len(tracked)} gevolgd(e) eigen-speler-profiel(en) met opgeslagen poule-schema gevonden.")
    for profile in tracked:
        pid = profile.get("player_id")
        label = profile.get("display_name") or pid
        fixtures = profile.get("interclub_schedule") or []
        if not fixtures:
            continue
        own_matches = _own_known_interclub_matches(pid)
        try:
            own_id, _own_id2, _resolved = ss.identify_own_ploeg_id(fixtures, own_matches)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{label}] Kon eigen ploeg niet herkennen ({e}) — dit poule-schema overgeslagen.")
            continue
        if not own_id:
            logger.warning(f"[{label}] Eigen ploeg niet herkenbaar in opgeslagen schema — overgeslagen.")
            continue
        for fx in fixtures:
            for side in ("home", "away"):
                ploeg_id = fx.get(f"{side}_ploeg_id")
                name = fx.get(f"{side}_name")
                if not ploeg_id or not name:
                    continue
                ploeg_id = str(ploeg_id)
                if ploeg_id == str(own_id):
                    continue
                if ploeg_id not in teams:
                    teams[ploeg_id] = {
                        "name": name,
                        "poule_label": fx.get("poule_label") or "?",
                        "fixtures": fixtures,
                    }
    return teams


def discover_players_for_team(ploeg_id: str, team_info: dict) -> dict:
    """Voor 1 ploeg: hun spelers uit AL HUN gespeelde wedstrijden dit
    seizoen (niet enkel de meest recente), via opponent_scout.scout_
    opponent() — requests-only, geen Playwright nodig. Returns
    {user_id: name}."""
    fixtures = team_info["fixtures"]
    team_fixtures = ss.get_team_fixtures(fixtures, ploeg_id)
    n_played = sum(1 for fx in team_fixtures if fx.get("played"))
    if n_played == 0:
        return {}
    # before_date_text="" -> geen datumgrens (zie opponent_scout.
    # get_opponent_previous_fixtures: before=None betekent "alle gespeelde
    # fixtures komen in aanmerking"). lookback=n_played -> ALLE gespeelde
    # wedstrijden van deze ploeg dit seizoen, zodat een speler die pas in
    # een latere wedstrijd opdook ook gevonden wordt.
    bundle = osc.scout_opponent(
        fixtures, team_info["name"], ploeg_id, before_date_text="", lookback=n_played,
    )
    if bundle.get("note"):
        return {}
    return {p["user_id"]: p["name"] for p in (bundle.get("unique_players", []) or [])}


def _is_fully_new_player(player_id: str) -> bool:
    """True als deze speler nog GEEN matchdata heeft (dus een echte,
    volledige Playwright-scrape nodig zou hebben) — gebruikt om de
    PRESCAN_NEW_PLAYERS_MAX-cap toe te passen."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        return True
    return not bool(doc.get("matches"))


def _save_prescan_summary(
    teams: dict, all_players: dict, new_ids: list, known_ids: list, capped_new: list,
) -> None:
    """Bewaart een klein samenvattingsdocument — basis voor een latere
    'laatst pre-scand op...'-weergave in de UI (Fase D3)."""
    try:
        fb.db.collection(PRESCAN_STATE_COLLECTION).document(PRESCAN_STATE_DOC).set({
            "last_run_at": _utc_now_iso(),
            "teams_found": len(teams),
            "team_names": sorted({t["name"] for t in teams.values()}),
            "players_found_total": len(all_players),
            "players_new_total": len(new_ids),
            "players_new_this_run": len(capped_new),
            "players_known": len(known_ids),
        })
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Kon prescan-samenvatting niet opslaan (niet blokkerend): {e}")


def main() -> int:
    new_players_max = get_new_players_max()
    delay = get_delay_between_teams()
    teams = discover_all_poule_teams()
    if not teams:
        logger.info("Geen andere ploegen gevonden in gevolgde poules — niets te doen.")
        _write_output("", 0)
        return 0
    logger.info(f"{len(teams)} andere ploeg(en) gevonden over alle gevolgde poules.")
    all_players: dict[str, str] = {}
    frozen_count, unfrozen_count = 0, 0
    for i, (ploeg_id, info) in enumerate(teams.items(), start=1):
        logger.info(f"--- ({i}/{len(teams)}) {info['name']} ({info['poule_label']}) ---")
        try:
            found = discover_players_for_team(ploeg_id, info)
            logger.info(f"  -> {len(found)} speler(s) gevonden.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"  -> kon spelers niet ophalen: {e}")
            found = {}
        for pid, name in found.items():
            all_players.setdefault(pid, name)
        # PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26 (op verzoek van
        # Kim: "gewoon automatisch afzetten als match gespeeld is"): heeft
        # deze ploeg nog een NIET-gespeelde fixture in het gevolgde
        # poule-schema? Zo niet, dan mogen hun gekende spelers stoppen met
        # regulier/bulk bijwerken - een bewuste "analyseer opnieuw"-klik
        # blijft ze altijd gewoon verversen (zie enrich_opponents.py).
        # Zelf-herstellend: verandert de kalender alsnog (bv. een
        # uitgestelde wedstrijd), dan wordt dit bij de volgende run
        # automatisch weer ontdooid.
        if found:
            team_fixtures = ss.get_team_fixtures(info["fixtures"], ploeg_id)
            still_upcoming = any(not fx.get("played") for fx in team_fixtures)
            _mark_team_players_frozen_state(ploeg_id, list(found.keys()), still_upcoming)
            if still_upcoming:
                unfrozen_count += len(found)
            else:
                frozen_count += len(found)
        if i < len(teams):
            time.sleep(delay)
    if frozen_count or unfrozen_count:
        logger.info(
            f"Automatisch bijwerken: {frozen_count} speler(s) bevroren (geen geplande "
            f"ontmoeting meer), {unfrozen_count} speler(s) actief (nog minstens 1 geplande "
            "ontmoeting) - status is elke run opnieuw herberekend."
        )
    logger.info(f"{len(all_players)} unieke speler(s) gevonden over {len(teams)} ploeg(en) samen.")
    new_ids, known_ids = [], []
    for pid in all_players:
        (new_ids if _is_fully_new_player(pid) else known_ids).append(pid)
    capped_new = new_ids[:new_players_max]
    overflow = len(new_ids) - len(capped_new)
    logger.info(
        f"{len(known_ids)} al bekend (matchdata bestaat al) — {len(new_ids)} volledig nieuw, "
        f"waarvan {len(capped_new)} deze run meegenomen (limiet {new_players_max})"
        + (f", {overflow} volgen bij een volgende run." if overflow else ".")
    )
    # Nieuwe spelers EERST in de lijst: geeft hen voorrang binnen het
    # padelstat/klassement-run-budget zodra iedereen al matchdata heeft
    # (zie enrich_opponents._prioritize()).
    final_ids = capped_new + known_ids
    _save_prescan_summary(teams, all_players, new_ids, known_ids, capped_new)
    _write_output(",".join(final_ids), len(final_ids))
    return 0


def _write_output(player_ids_csv: str, count: int) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        try:
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(f"player_ids={player_ids_csv}\n")
                f.write(f"player_count={count}\n")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Kon GITHUB_OUTPUT niet wegschrijven: {e}")
    logger.info(f"PLAYER_IDS voor de volgende stap ({count} speler(s)): {player_ids_csv}")


if __name__ == "__main__":
    sys.exit(main())
