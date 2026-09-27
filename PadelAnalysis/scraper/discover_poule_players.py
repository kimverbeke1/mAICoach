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
"elk profiel met eender welk opgeslagen schema" (zie get_tracked_player_
ids() voor hoe die allowlist wordt samengesteld).
Dit is een BEWUSTE gedragswijziging t.o.v. de vorige, te brede aanpak
("alle profielen met een schema") - de vorige aanpak leek in de praktijk
vooral RUIS toe te voegen (tegenstander-profielen met een toevallig
opgeslagen, irrelevant schema), niet legitieme extra eigen teams.
--------------------------------------------------------------------------
PADEL_ANALYSIS_AUTO_TRACK_VIA_SAVED_ANALYSES_2026-09-27 (op verzoek van
Kim: "ik zou willen dat de code dat automatisch detecteert omdat ik al
analyses gedaan heb voor de ploeg van anneleen [...] een gestarte analyse
van een ploeg mag dat triggeren")
--------------------------------------------------------------------------
Tot nu toe moest een 2e (of verdere) eigen team handmatig via de
PRESCAN_TRACKED_PLAYER_IDS-env-var ingesteld worden - en enkel lokaal in
een PowerShell-sessie, NOOIT in de nachtelijke workflow zelf (die env var
werd daar nergens doorgegeven). Kim wil dit automatisch: als hij al een
opstelling-analyse voor een speler heeft OPGESLAGEN (via de "Analyse
opslaan"-knop in Opstelling-scenario's - zie fb.save_lineup_analysis() /
SAVED_LINEUP_ANALYSES_COLLECTION in firebase_service.py), dan bewijst dat
al dat deze speler een "eigen team" is die Kim bewust volgt - dat mag dan
volstaan om hem/haar automatisch aan de tracked-lijst toe te voegen, zonder
een env var te moeten instellen of dit bestand opnieuw aan te passen.
FIX: get_tracked_player_ids() combineert nu 3 bronnen (unie, geen
uitsluiting):
  1. de app-brede "home_player_id" (fb.get_app_settings()) - Kim zelf,
     altijd inbegrepen zoals voorheen.
  2. AUTOMATISCH: elke unieke owner_player_id uit fb.list_lineup_
     analyses() - elke speler voor wie ooit een opstelling-analyse werd
     opgeslagen, wordt voortaan vanzelf mee gevolgd. Dit is precies het
     "gestarte analyse triggert tracking"-criterium dat Kim vroeg.
  3. PRESCAN_TRACKED_PLAYER_IDS (env, komma-gescheiden) blijft bestaan als
     AANVULLENDE, handmatige uitzondering (bv. een speler volgen waarvoor
     nog nooit een analyse werd opgeslagen) - niet langer de ENIGE manier.
EERLIJKE BEPERKING: dit criterium detecteert enkel OPGESLAGEN analyses
(expliciet via de "Analyse opslaan"-knop), niet elke keer dat een speler
enkel bij "Toon analyse voor" geselecteerd werd zonder op te slaan - er is
geen ander persistent spoor van dat laatste in de app. Is dat onvoldoende,
dan blijft PRESCAN_TRACKED_PLAYER_IDS de aangewezen aanvulling.
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
("Verbeke Kim"). Zie schedule_scraper.py voor de volledige analyse.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PRESCAN_CANDIDATE_DIAGNOSTICS_2026-09-27 (op verzoek van
Kim: na een prescan-run waarbij zowel Kim Verbeke zelf als Anneleen Gallant
opnieuw "Eigen ploeg niet herkenbaar" gaven, ondanks dat identify_own_
ploeg_id() los getest - met exact dezelfde, op dat moment opgehaalde data -
wél een eenduidig resultaat gaf voor beide. Vermoeden: de onderliggende
matchdata was op het moment van de prescan-run zelf nog tijdelijk
onvolledig (bv. een nog lopende dagelijkse sync), niet een fout in de
matching-logica zelf.)
--------------------------------------------------------------------------
Om een volgende zo'n mislukking niet opnieuw via een los diagnosescript te
moeten uitzoeken, logt discover_all_poule_teams() nu, ENKEL wanneer
identify_own_ploeg_id() geen eenduidig resultaat oplevert, alsnog het
volledige kandidaat-voor-kandidaat verloop (own_names/opponent_names,
home/away_players uit het uitslagenblad, en de score per kandidaat) op
INFO-niveau — rechtstreeks in de normale nachtelijke log, dus zonder Kim's
werkstroom te wijzigen of een extra script te moeten draaien. Bij een
GESLAAGDE herkenning wordt dit NIET gelogd (geen ruis op het happy path).
Deze diagnostiek hergebruikt uitsluitend de bestaande, al bevestigd
correcte hulpfuncties uit schedule_scraper.py (_parse_date_text,
_known_names_for_date, _fixture_player_sides, _overlap_score) - de
matching-logica zelf (identify_own_ploeg_id) wordt NIET gedupliceerd of
gewijzigd, enkel extra instrumentatie er rond.
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
BEVRIEZING VAN SPELERS ZONDER RESTERENDE WEDSTRIJDEN
--------------------------------------------------------------------------
PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26 (ongewijzigd qua opzet).
--------------------------------------------------------------------------
PADEL_ANALYSIS_FREEZE_HEAD_TO_HEAD_FIX_2026-09-27 (op verzoek van Kim: "je
telt terug spelers van ploegen waar wij zelf niet meer tegen spelen")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door de log te analyseren: "0 bevroren, 26 actief",
terwijl meerdere van de 5 gevonden tegenstanders al lang door Kim's EIGEN
ploeg gespeeld waren): still_upcoming werd tot nu toe bepaald door TE
CONTROLEREN OF DE TEGENSTANDER-PLOEG nog EENDER WELKE onbesliste fixture
had in de VOLLEDIGE poule - dus ook een wedstrijd tegen een ANDERE ploeg,
niet specifiek tegen Kim's eigen ploeg. Bij een poule met meerdere speel-
rondes bleef een tegenstander daardoor "actief" (dus hun spelers bleven
ververst worden) zolang zij nog IEMAND in de poule moesten ontmoeten - ook
als de ENIGE relevante wedstrijd voor Kim (die tussen zijn eigen ploeg en
hen) al lang gespeeld was.
FIX: still_upcoming wordt nu bepaald aan de hand van de ONDERLINGE
fixture(s) tussen Kim's EIGEN, herkende ploeg (own_ploeg_id, nu ook
bewaard per gevonden tegenstander-team) en die specifieke tegenstander -
niet de tegenstander hun volledige wedstrijdkalender. Is er nog minstens 1
onbesliste onderlinge wedstrijd, dan blijft still_upcoming=True (actief).
Zijn ALLE onderlinge wedstrijden al gespeeld, dan wordt bevroren. Wordt er
(zeldzaam) HELEMAAL geen onderlinge fixture teruggevonden, dan blijft de
VEILIGE default still_upcoming=True (nooit onterecht bevriezen bij twijfel).
--------------------------------------------------------------------------
PADEL_ANALYSIS_FREEZE_NOT_APPLIED_TO_OUTPUT_FIX_2026-09-27 (op verzoek van
Kim: "36 spelers i.p.v. 15 [...] de bevriezing wordt wel OPGESLAGEN, maar
nooit TOEGEPAST op wat er naar ci_scrape_all.py doorgaat")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd - Kim's eigen analyse was raak): _mark_team_players_
frozen_state() schreef auto_update_frozen correct weg naar player_profiles,
maar GEEN enkele plek in dit bestand las dat veld terug om de uiteindelijke
final_ids (die naar ci_scrape_all.py via PLAYER_IDS gaan) te filteren. Bij
21 bevroren + 15 actief werden dus alsnog alle 36 doorgegeven.
BEWUSTE KEUZE (op basis van Kim's eigen vraag "moet dat in ci_scrape_all.py
of hier?"): bevestigd via een controle van het huidige ci_scrape_all.py -
dat bestand checkt NERGENS op auto_update_frozen. De uitsluiting gebeurt
daarom HIER, niet in ci_scrape_all.py, want dat laatste bestand is GEDEELDE
infrastructuur die ook voor HANDMATIGE verversingen gebruikt wordt (bv.
"Scrape deze speler nu" in de app, mode="full"). Een bewuste, expliciete
handmatige actie moet auto_update_frozen kunnen NEGEREN - dat onderscheid
zou verloren gaan als de check in ci_scrape_all.py zelf zou zitten.
discover_poule_players.py berekent still_upcoming toch al PER TEAM in
dezelfde run (main(), hieronder) - geen extra Firestore-lezing nodig, enkel
het resultaat bijhouden en er NA het bepalen van new_ids/known_ids op
filteren, vlak vóór final_ids wordt opgebouwd.
FIX: main() houdt nu 2 sets bij tijdens de team-lus: active_player_ids
(voorkwam in minstens 1 nog-actieve/still_upcoming team) en frozen_only_
candidate_ids (voorkwam in minstens 1 bevroren team). Een speler die in
BEIDE voorkomt (bv. lid van 2 verschillende tegenstander-teams, waarvan 1
nog moet spelen) blijft ACTIEF behandeld - active_player_ids heeft
voorrang, om nooit onterecht een speler uit te sluiten die nog wel ergens
relevant is. Pas na het bepalen van new_ids/known_ids wordt final_ids
gefilterd: elke speler die UITSLUITEND in bevroren teams voorkwam, wordt
verwijderd, met een duidelijke logregel over hoeveel spelers hierdoor
uitgesloten werden.
Environment variables (optioneel, met veilige defaults):
    - PRESCAN_TRACKED_PLAYER_IDS (komma-gescheiden player_id's, NIEUW)
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
from typing import Optional
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
    """PADEL_ANALYSIS_TRACKED_PROFILES_SCOPE_FIX_2026-09-27 +
    PADEL_ANALYSIS_AUTO_TRACK_VIA_SAVED_ANALYSES_2026-09-27: bepaalt WELKE
    player_id's als 'eigen team'-detectiebron gebruikt worden - zie de
    uitgebreide toelichting bovenaan dit bestand. Combineert 3 bronnen
    (unie, geen enkele sluit de andere uit):
      1. home_player_id (fb.get_app_settings()) - Kim zelf, altijd.
      2. AUTOMATISCH: elke unieke owner_player_id uit fb.list_lineup_
         analyses() - wie ooit een analyse liet opslaan, wordt vanzelf
         mee gevolgd (het "gestarte analyse triggert tracking"-criterium).
      3. PRESCAN_TRACKED_PLAYER_IDS (env, komma-gescheiden) - optionele,
         AANVULLENDE handmatige uitzondering bovenop de eerste 2 bronnen."""
    ids: set[str] = set()
    try:
        settings = fb.get_app_settings() or {}
        home_id = settings.get("home_player_id")
        if home_id:
            ids.add(str(home_id))
    except Exception as e:  # noqa: BLE001
        logger.error(f"Kon app-instellingen niet lezen: {e}")
    try:
        analyses = fb.list_lineup_analyses()
        auto_ids = {str(a.get("owner_player_id")) for a in analyses if a.get("owner_player_id")}
        if auto_ids - ids:
            logger.info(
                f"Automatisch mee gevolgd via opgeslagen opstelling-analyses: "
                f"{sorted(auto_ids - ids)}"
            )
        ids |= auto_ids
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Kon opgeslagen analyses niet lezen voor auto-tracking: {e}")
    raw = os.environ.get("PRESCAN_TRACKED_PLAYER_IDS", "").strip()
    if raw:
        extra_ids = {p.strip() for p in raw.split(",") if p.strip()}
        if extra_ids - ids:
            logger.info(f"PRESCAN_TRACKED_PLAYER_IDS voegt extra toe: {sorted(extra_ids - ids)}")
        ids |= extra_ids
    if not ids:
        logger.warning(
            "Geen home_player_id, geen opgeslagen analyses, en geen PRESCAN_TRACKED_PLAYER_IDS "
            "- niets om te volgen."
        )
        return []
    return sorted(ids)
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
def _log_own_ploeg_candidate_diagnostics(
    label: str, fixtures: list[dict], own_known_matches: list[dict], own_display_name: str,
) -> None:
    """PADEL_ANALYSIS_PRESCAN_CANDIDATE_DIAGNOSTICS_2026-09-27: logt, ENKEL
    wanneer identify_own_ploeg_id() al gefaald is voor dit profiel, het
    volledige kandidaat-voor-kandidaat verloop op INFO-niveau - dezelfde
    informatie die voorheen enkel via een los diagnosescript (diagnose_
    identify_own_ploeg_v2.py / diagnose_discover_verbose.py) zichtbaar was.
    Hergebruikt uitsluitend bestaande, al bevestigd correcte hulpfuncties
    uit schedule_scraper.py - dupliceert de matching-logica zelf niet."""
    own_dates = {
        parsed
        for m in own_known_matches
        if m.get("match_type") == "interclub"
        for parsed in [ss._parse_date_text(m.get("match_date") or "")]
        if parsed
    }
    candidates = []
    for fx in fixtures:
        parsed = ss._parse_date_text(fx.get("date_text") or "")
        if fx.get("played") and parsed and parsed in own_dates:
            candidates.append((parsed, fx))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        logger.info(
            f"  [{label}] diagnose: 0 kandidaat-fixtures (gespeeld + datum komt overeen met "
            "een eigen bekende interclub-datum) - de datum-koppeling zelf faalt al, vóór de "
            "naam-vergelijking aan bod komt."
        )
        return
    logger.info(f"  [{label}] diagnose: {len(candidates)} kandidaat-fixture(s), per kandidaat:")
    for i, (date_key, fx) in enumerate(candidates, start=1):
        own_names, opp_names = ss._known_names_for_date(
            own_known_matches, date_key, own_display_name=own_display_name,
        )
        home_players, away_players = ss._fixture_player_sides(fx)
        if not home_players and not away_players:
            logger.info(
                f"    ({i}/{len(candidates)}) {fx.get('date_text')} "
                f"({fx.get('home_name')} vs {fx.get('away_name')}): GEEN spelers uit het "
                "uitslagenblad gelezen (fetch-/parsefout - zie een eventuele WARNING van "
                "schedule_scraper hierboven)."
            )
            continue
        home_score = 3 * ss._overlap_score(home_players, own_names) + ss._overlap_score(away_players, opp_names)
        away_score = 3 * ss._overlap_score(away_players, own_names) + ss._overlap_score(home_players, opp_names)
        uitkomst = "TIE (overgeslagen)" if home_score == away_score else (
            f"HOME wint ({fx.get('home_name')})" if home_score > away_score
            else f"AWAY wint ({fx.get('away_name')})"
        )
        logger.info(
            f"    ({i}/{len(candidates)}) {fx.get('date_text')} "
            f"({fx.get('home_name')} vs {fx.get('away_name')}): "
            f"own_names={sorted(own_names)}, opponent_names={sorted(opp_names)}, "
            f"home_players={sorted(home_players)}, away_players={sorted(away_players)}, "
            f"home_score={home_score}, away_score={away_score} -> {uitkomst}"
        )
def _mark_team_players_frozen_state(
    ploeg_id: str, player_ids: list[str], still_upcoming: bool,
) -> None:
    """PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26: zet (of verwijdert)
    auto_update_frozen op elk speler-profiel van deze ploeg, gebaseerd op of
    de ploeg nog een NIET-gespeelde fixture heeft in een gevolgde poule.
    Levende, elke run herberekende status - geen eenmalige markering."""
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
    """Doorloopt elk TOEGESTAAN profiel (zie get_tracked_profiles()),
    herkent de eigen ploeg, en verzamelt ALLE ANDERE ploegen (over alle
    gevolgde poules heen).
    Returns {ploeg_id: {"name":..., "poule_label":..., "fixtures": [...]}}."""
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
            # PADEL_ANALYSIS_PRESCAN_CANDIDATE_DIAGNOSTICS_2026-09-27: enkel
            # bij een mislukking het volledige kandidaat-verloop loggen,
            # zodat de oorzaak meteen in DEZE log zichtbaar is, zonder een
            # apart diagnosescript te moeten draaien.
            try:
                _log_own_ploeg_candidate_diagnostics(label, fixtures, own_matches, label)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"  [{label}] Kon diagnostiek niet loggen ({e}).")
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
                        # PADEL_ANALYSIS_FREEZE_HEAD_TO_HEAD_FIX_2026-09-27:
                        # bewaard zodat de bevriezingscheck in main() de
                        # ONDERLINGE fixture(s) tussen Kim's eigen ploeg en
                        # deze tegenstander kan opzoeken, i.p.v. de volledige
                        # wedstrijdkalender van de tegenstander.
                        "own_ploeg_id": str(own_id),
                    }
    return teams


def _still_playing_each_other(fixtures: list[dict], own_ploeg_id: Optional[str], ploeg_id: str) -> bool:
    """PADEL_ANALYSIS_FREEZE_HEAD_TO_HEAD_FIX_2026-09-27: True zolang er nog
    minstens 1 NIET-gespeelde fixture is tussen own_ploeg_id en ploeg_id
    specifiek - ongeacht of de tegenstander verder nog tegen ANDERE ploegen
    moet spelen. Geeft (veilig, niet-bevriezend) True terug als own_ploeg_id
    ontbreekt of als er helemaal geen onderlinge fixture gevonden wordt -
    bevriezen gebeurt enkel bij een POSITIEVE bevestiging dat alle
    onderlinge wedstrijden al gespeeld zijn."""
    if not own_ploeg_id:
        return True
    head_to_head = [
        fx for fx in fixtures
        if {str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id"))} == {str(own_ploeg_id), str(ploeg_id)}
    ]
    if not head_to_head:
        return True
    return any(not fx.get("played") for fx in head_to_head)
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
    # PADEL_ANALYSIS_FREEZE_NOT_APPLIED_TO_OUTPUT_FIX_2026-09-27: bijgehouden
    # tijdens dezelfde lus die still_upcoming toch al berekent - geen extra
    # Firestore-lezing nodig. Een speler die in minstens 1 nog-actieve team
    # voorkomt, blijft ALTIJD actief behandeld (active_player_ids heeft
    # voorrang op frozen_only_candidate_ids), ook als hij/zij daarnaast ook
    # in een bevroren team zit.
    active_player_ids: set[str] = set()
    frozen_only_candidate_ids: set[str] = set()
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
            # PADEL_ANALYSIS_FREEZE_HEAD_TO_HEAD_FIX_2026-09-27: enkel de
            # ONDERLINGE fixture(s) tussen Kim's eigen ploeg en DEZE
            # tegenstander bepalen still_upcoming - niet de volledige
            # wedstrijdkalender van de tegenstander (zie moduledocstring).
            still_upcoming = _still_playing_each_other(
                info["fixtures"], info.get("own_ploeg_id"), ploeg_id,
            )
            _mark_team_players_frozen_state(ploeg_id, list(found.keys()), still_upcoming)
            if still_upcoming:
                unfrozen_count += len(found)
                active_player_ids.update(found.keys())
            else:
                frozen_count += len(found)
                frozen_only_candidate_ids.update(found.keys())
        if i < len(teams):
            time.sleep(delay)
    # PADEL_ANALYSIS_FREEZE_NOT_APPLIED_TO_OUTPUT_FIX_2026-09-27: enkel
    # spelers die UITSLUITEND in bevroren team(s) voorkwamen, worden
    # effectief uitgesloten - active_player_ids heeft voorrang.
    frozen_only_ids = frozen_only_candidate_ids - active_player_ids
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
    final_ids = [pid for pid in (capped_new + known_ids) if pid not in frozen_only_ids]
    excluded_frozen = len(capped_new) + len(known_ids) - len(final_ids)
    if excluded_frozen:
        logger.info(
            f"{excluded_frozen} speler(s) uitgesloten van deze scrape-run omdat ze uitsluitend "
            "in bevroren team(s) voorkomen (auto_update_frozen) - PADEL_ANALYSIS_FREEZE_NOT_"
            "APPLIED_TO_OUTPUT_FIX_2026-09-27."
        )
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
