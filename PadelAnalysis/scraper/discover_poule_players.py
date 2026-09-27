# -*- coding: utf-8 -*-
"""
discover_poule_players.py — PADEL_ANALYSIS_POULE_PRESCAN_2026-09-19 (Fase D2,
op verzoek van Kim, chat 2026-09-19).
Kim's melding, samengevat: "Nu ik er aan denk is het misschien wel beter om
in de achtergrond al meteen alle spelers van je poule op te halen op
voorhand. bv. om middernacht. [...] rekening houden dat een ploeg plots
extra spelers kan gebruikt hebben. [...] zo veel mogelijk op voorhand
gescrapt is en dan zeker ook goed op letten dat je wanneer nodig enkel de
missing data of data die kan gewijzigd is refreshen."

--------------------------------------------------------------------------
DOEL EN ONTWERPKEUZE: hergebruik, geen nieuwe scrape-logica
--------------------------------------------------------------------------
Dit script doet ZELF geen matchdata-, padelstat- of klassement-scrape — het
bepaalt ENKEL, requests-only, WELKE spelers er over de VOLLEDIGE poule
besproken moeten worden, en geeft die lijst door aan ci_scrape_all.py.

--------------------------------------------------------------------------
PADEL_ANALYSIS_TRACKED_PROFILES_SCOPE_FIX_2026-09-27 (op verzoek van Kim:
"Bij de poule pre-scan log zie ik ploegen van poule C. Geen idee waarom die
in de lijst komt. Is normaal niet nodig.")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door de nachtelijke log te analyseren): get_tracked_
profiles() behandelde TOT NU TOE elk player_profiles-document met een
opgeslagen `interclub_schedule` als "een van Kim's eigen teams om de eigen-
ploeg-detectie op los te laten" - dus 42 profielen in de laatste run. Een
groot deel daarvan (Caroline Clement, Depuydt Evelyn, Geeraerts Gertie,
Lauwers René, Serruys Tracey, e.a. - namen die NERGENS in Kim's eigen
Poule Q-omgeving voorkomen) zijn in werkelijkheid TEGENSTANDER-profielen
die ooit, via een andere weg (bv. cross-referentie bij het aanmaken van een
profiel-stub, of een eerdere, andere analyse), toevallig ZELF ook een
interclub_schedule opgeslagen kregen - voor een HELEMAAL ANDERE poule
(Poule C, G) die niets met Kim's eigen team te maken heeft.
Voor elk van die profielen probeerde discover_all_poule_teams() alsnog
"de eigen ploeg" te herkennen (wat vrijwel altijd faalt, vandaar de lange
lijst "Eigen ploeg niet herkenbaar" in de log) - en de handvol gevallen
waarbij dat WEL toevallig lukte, voegde dan de VOLLEDIGE, voor Kim
irrelevante poule (bv. Poule C) toe aan de discovery-resultaten.
FIX: get_tracked_profiles() gebruikt nu een EXPLICIETE allowlist van
player_id's om als "eigen team"-detectiebron te gebruiken, in plaats van
"elk profiel met eender welk opgeslagen schema":
  - PRESCAN_TRACKED_PLAYER_IDS (env, komma-gescheiden): expliciete lijst,
    voor het geval Kim bewust meerdere eigen spelers/teams wil volgen.
  - Zonder die env var: valt terug op ENKEL de app-brede "home_player_id"
    (fb.get_app_settings()) - Kim's eigen, hoofdzakelijk gevolgde profiel.
Dit is een BEWUSTE gedragswijziging t.o.v. de vorige, te brede aanpak
("alle profielen met een schema") - de vorige aanpak leek in de praktijk
vooral RUIS toe te voegen (tegenstander-profielen met een toevallig
opgeslagen, irrelevant schema), niet legitieme extra eigen teams. Wil Kim
toch meerdere eigen teams tegelijk volgen, dan kan dat gewoon via
PRESCAN_TRACKED_PLAYER_IDS zonder dit bestand opnieuw te moeten aanpassen.

--------------------------------------------------------------------------
STAP 1: welke poules volgen we? (enkel de expliciet toegestane profielen)
--------------------------------------------------------------------------
Per toegestaan profiel wordt (via schedule_scraper.identify_own_ploeg_id(),
dezelfde functie die de UI gebruikt) de EIGEN ploeg herkend en uitgesloten
— we willen enkel de ANDERE ploegen in de poule pre-scannen.
PADEL_ANALYSIS_DISCOVER_OWN_NAME_MISSING_FIX_2026-09-26 (blijft bestaan):
own_display_name wordt expliciet meegegeven aan identify_own_ploeg_id().
PADEL_ANALYSIS_NAME_WORD_ORDER_FIX_2026-09-27 (in schedule_scraper.py, niet
dit bestand): loste een TWEEDE, onafhankelijke oorzaak op van dezelfde
"Eigen ploeg niet herkenbaar"-melding - een woordvolgorde-verschil tussen
het profiel se display_name ("Kim Verbeke") en hoe de site namen toont
("Verbeke Kim"). Zie schedule_scraper.py voor de volledige analyse. Beide
fixes samen (dit bestand + schedule_scraper.py) waren nodig: de scope-fix
hier voorkomt dat IRRELEVANTE profielen uberhaupt geprobeerd worden, de
naam-fix in schedule_scraper.py zorgt dat Kim's EIGEN, wel-relevante
profiel ook effectief herkend wordt.

--------------------------------------------------------------------------
STAP 2: per andere ploeg, hun spelers ophalen uit reeds gespeelde matchen
--------------------------------------------------------------------------
Zie eerdere versie - ongewijzigd: opponent_scout.scout_opponent() haalt de
spelers op uit AL HUN gespeelde wedstrijden dit seizoen.

--------------------------------------------------------------------------
STAP 3: nieuw vs. gekend, en een batch-limiet voor VOLLEDIG nieuwe spelers
--------------------------------------------------------------------------
Ongewijzigd - zie PRESCAN_NEW_PLAYERS_MAX hieronder.

--------------------------------------------------------------------------
PADEL_ANALYSIS_FREEZE_VS_OWN_TEAM_FIX_2026-09-27 (op verzoek van Kim: "ik
zie de fout. played mag op false als wij er niet moeten tegen spelen. dus
enkel witte kaproenen en lobbeke zouden true moeten zijn omdat je dat moet
bekijken vanuit onze ploeg. natuurlijk moet elke ploeg nog matchen spelen")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd): `still_upcoming` werd berekend via
`ss.get_team_fixtures(info["fixtures"], ploeg_id)` - dat geeft ALLE
fixtures van de TEGENSTANDER-ploeg in de volledige poule terug, ongeacht
tegen wie. Voor LUDOVIEK Padel C leverde dat dus ook hun (voor ONS totaal
irrelevante) wedstrijd tegen K.T.C. DE WITTE KAPROENEN op 10/10 op, en
zolang DIE nog niet gespeeld was, bleef `still_upcoming=True` - ook al was
de wedstrijd LUDOVIEK-tegen-ONS allang gespeeld en afgerond (bevestigd:
26/09 Padel Factory B vs LUDOVIEK, played=True). Elke ploeg in een poule
heeft bijna altijd nog wedstrijden te spelen tegen ANDEREN, dus deze check
kon in de praktijk vrijwel nooit "bevroren" opleveren.
De vraag die hier beantwoord moet worden is niet "heeft deze ploeg nog EEN
wedstrijd te spelen in de poule" maar "heeft deze ploeg nog een wedstrijd
te spelen TEGEN ONS" - want dat, en enkel dat, bepaalt of WIJ hun
spelersdata nog moeten blijven verversen.

FIX: `own_id` (al beschikbaar in discover_all_poule_teams(), waar de eigen
ploeg net herkend en uitgesloten wordt) wordt nu MEE opgeslagen per team-
entry, en still_upcoming filtert expliciet op fixtures waarin zowel
`ploeg_id` (de tegenstander) ALS `own_id` (onszelf) voorkomen - dus
letterlijk de onderlinge confrontatie(s) tussen ons en die ene
tegenstander, niet hun wedstrijden tegen de rest van de poule.
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


def get_tracked_player_ids() -> list[str]:
    """PADEL_ANALYSIS_TRACKED_PROFILES_SCOPE_FIX_2026-09-27: bepaalt WELKE
    player_id's als 'eigen team'-detectiebron gebruikt worden - een
    EXPLICIETE, kleine lijst i.p.v. "elk profiel met eender welk
    opgeslagen schema" (zie moduledocstring voor de volledige root-cause-
    analyse van waarom dat laatste irrelevante poules zoals Poule C
    binnenhaalde).
    Volgorde van voorrang:
      1. PRESCAN_TRACKED_PLAYER_IDS (env, komma-gescheiden) - expliciete
         lijst, voor wie bewust meerdere eigen spelers/teams wil volgen.
      2. Anders: enkel de app-brede "home_player_id"
         (fb.get_app_settings()) - de veilige, minimale default."""
    raw = os.environ.get("PRESCAN_TRACKED_PLAYER_IDS", "").strip()
    if raw:
        ids = [p.strip() for p in raw.split(",") if p.strip()]
        if ids:
            logger.info(f"PRESCAN_TRACKED_PLAYER_IDS expliciet gezet: {ids}")
            return ids
    try:
        settings = fb.get_app_settings() or {}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Kon app-instellingen niet lezen: {e}")
        return []
    home_id = settings.get("home_player_id")
    if not home_id:
        logger.warning(
            "Geen PRESCAN_TRACKED_PLAYER_IDS gezet EN geen home_player_id gevonden in de "
            "app-instellingen - niets om te volgen."
        )
        return []
    return [str(home_id)]


def get_tracked_profiles() -> list[dict]:
    """Haalt de player_profiles-documenten op voor exact de toegestane
    player_id's (zie get_tracked_player_ids()) - enkel diegene met een
    opgeslagen interclub_schedule zijn bruikbaar als discoverybron."""
    ids = get_tracked_player_ids()
    profiles = []
    for pid in ids:
        try:
            profile = fb.get_player_profile(pid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{pid}] Kon profiel niet lezen: {e}")
            continue
        if profile and profile.get("interclub_schedule"):
            profiles.append(profile)
        elif profile:
            logger.info(f"[{profile.get('display_name') or pid}] Nog geen opgeslagen poule-schema - overgeslagen.")
        else:
            logger.warning(f"[{pid}] Geen player_profiles-document gevonden.")
    return profiles


def _own_known_interclub_matches(player_id: str) -> list[dict]:
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        doc = {}
    return [m for m in (doc.get("matches", []) or []) if m.get("match_type") == "interclub"]


def _mark_team_players_frozen_state(
    ploeg_id: str, player_ids: list[str], still_upcoming: bool,
) -> None:
    """PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26 +
    PADEL_ANALYSIS_FREEZE_VS_OWN_TEAM_FIX_2026-09-27: zet (of verwijdert)
    auto_update_frozen op elk speler-profiel van deze ploeg, gebaseerd op of
    de ONDERLINGE CONFRONTATIE met onszelf nog een niet-gespeelde fixture
    heeft (zie moduledocstring voor de volledige root-cause-analyse van
    waarom dit voorheen "elke fixture in de hele poule" was, wat vrijwel
    nooit tot bevriezing leidde). Levende, elke run herberekende status -
    geen eenmalige markering."""
    for pid in player_ids:
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(
                {
                    "auto_update_frozen": not still_upcoming,
                    "auto_update_frozen_reason": (
                        None if still_upcoming
                        else "onderlinge confrontatie met onze ploeg al gespeeld, geen nieuwe gepland"
                    ),
                    "auto_update_frozen_via_ploeg_id": str(ploeg_id),
                    "auto_update_frozen_updated_at": _utc_now_iso(),
                },
                merge=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{pid}] Kon auto_update_frozen-status niet bijwerken: {e}")


def discover_all_poule_teams() -> dict:
    """Doorloopt elk TOEGESTAAN profiel (zie get_tracked_profiles()),
    herkent de eigen ploeg, en verzamelt ALLE ANDERE ploegen (over alle
    gevolgde poules heen).

    PADEL_ANALYSIS_FREEZE_VS_OWN_TEAM_FIX_2026-09-27: elke team-entry
    bewaart nu ook `own_ploeg_id` - de eigen ploeg-id die bij DIT specifieke
    gevolgde schema hoort - zodat de bevries-check in main() achteraf kan
    filteren op "nog een wedstrijd tegen ONS", niet "nog een wedstrijd tegen
    eender wie in de poule". Zonder dit veld zou die informatie na deze
    functie onherroepelijk verloren zijn.

    Returns {ploeg_id: {"name":..., "poule_label":..., "fixtures": [...],
                        "own_ploeg_id": ...}}."""
    teams: dict = {}
    tracked = get_tracked_profiles()
    logger.info(f"{len(tracked)} toegestaan(e) eigen-speler-profiel(en) met opgeslagen poule-schema gevonden.")
    for profile in tracked:
        pid = profile.get("player_id")
        label = profile.get("display_name") or pid
        fixtures = profile.get("interclub_schedule") or []
        if not fixtures:
            continue
        own_matches = _own_known_interclub_matches(pid)
        try:
            # PADEL_ANALYSIS_DISCOVER_OWN_NAME_MISSING_FIX_2026-09-26 +
            # PADEL_ANALYSIS_NAME_WORD_ORDER_FIX_2026-09-27 (schedule_
            # scraper.py): own_display_name wordt hier doorgegeven, en
            # wordt sinds de woordvolgorde-fix ook effectief herkend als
            # de site een andere naamvolgorde toont dan het profiel.
            own_id, _own_id2, _resolved = ss.identify_own_ploeg_id(
                fixtures, own_matches, own_display_name=label,
            )
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
                        "own_ploeg_id": str(own_id),
                    }
    return teams


def discover_players_for_team(ploeg_id: str, team_info: dict) -> dict:
    """Voor 1 ploeg: hun spelers uit AL HUN gespeelde wedstrijden dit
    seizoen, via opponent_scout.scout_opponent() — requests-only."""
    fixtures = team_info["fixtures"]
    team_fixtures = ss.get_team_fixtures(fixtures, ploeg_id)
    n_played = sum(1 for fx in team_fixtures if fx.get("played"))
    if n_played == 0:
        return {}
    bundle = osc.scout_opponent(
        fixtures, team_info["name"], ploeg_id, before_date_text="", lookback=n_played,
    )
    if bundle.get("note"):
        return {}
    return {p["user_id"]: p["name"] for p in (bundle.get("unique_players", []) or [])}


def _still_upcoming_against_own_team(fixtures: list, ploeg_id: str, own_ploeg_id: str) -> bool:
    """PADEL_ANALYSIS_FREEZE_VS_OWN_TEAM_FIX_2026-09-27: True als er nog
    een NIET-gespeelde fixture bestaat waarin zowel `ploeg_id` (de
    tegenstander) als `own_ploeg_id` (onszelf) voorkomen - dus specifiek
    de onderlinge confrontatie(s) tussen ons en die ene tegenstander.

    Bewust NIET ss.get_team_fixtures() hergebruikt: die geeft ALLE
    fixtures van 1 ploeg terug (tegen om het even wie in de poule) - exact
    de te brede vraag die het probleem veroorzaakte. Hier wordt op BEIDE
    kanten tegelijk gefilterd."""
    ploeg_id, own_ploeg_id = str(ploeg_id), str(own_ploeg_id)
    for fx in fixtures or []:
        sides = {str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id"))}
        if sides == {ploeg_id, own_ploeg_id} and not fx.get("played"):
            return True
    return False


def _is_fully_new_player(player_id: str) -> bool:
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        return True
    return not bool(doc.get("matches"))


def _save_prescan_summary(
    teams: dict, all_players: dict, new_ids: list, known_ids: list, capped_new: list,
) -> None:
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
        logger.info("Geen andere ploegen gevonden in de toegestane, gevolgde poule(s) — niets te doen.")
        _write_output("", 0)
        return 0
    logger.info(f"{len(teams)} andere ploeg(en) gevonden over de toegestane, gevolgde poule(s).")
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
        if found:
            # PADEL_ANALYSIS_FREEZE_VS_OWN_TEAM_FIX_2026-09-27: filtert nu
            # op de onderlinge confrontatie met own_ploeg_id, niet op elke
            # fixture van de tegenstander in de hele poule.
            still_upcoming = _still_upcoming_against_own_team(
                info["fixtures"], ploeg_id, info["own_ploeg_id"],
            )
            _mark_team_players_frozen_state(ploeg_id, list(found.keys()), still_upcoming)
            if still_upcoming:
                unfrozen_count += len(found)
            else:
                frozen_count += len(found)
        if i < len(teams):
            time.sleep(delay)
    if frozen_count or unfrozen_count:
        logger.info(
            f"Automatisch bijwerken: {frozen_count} speler(s) bevroren (onderlinge confrontatie "
            f"met ons al gespeeld), {unfrozen_count} speler(s) actief (nog minstens 1 geplande "
            "ontmoeting TEGEN ONS) - status is elke run opnieuw herberekend."
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
