"""
opponent_scout.py — haalt de individuele opstelling van een tegenstander uit
hun vorige wedstrijd(en) dit seizoen (via het bestaande uitslagenblad), en
scrapet die spelers desgewenst (sequentieel, met wachttijd, op aanvraag).

Ontwerpkeuzes (zie gesprek):
- Teamnamen zijn geen stabiele basis over periodes heen — individuele
  spelers wel. Daarom kijken we naar de tegenstander hun voorgaande
  wedstrijd(en) DIT seizoen, niet naar oudere ontmoetingen.
- Sequentieel scrapen met dezelfde wachttijd-conventie als de rest van de
  scraper (geen parallelle requests — minder opvallend, ook al is het trager).
- Standaard 1 periode (huidige) per nieuwe tegenstander, maar parametriseerbaar
  (`lookback_periods`) zodat dit later makkelijk naar bv. 2 uit te breiden is
  zonder de rest van de code aan te passen.

BELANGRIJKE FIX (cloud-deploy):
`scrape_player` wordt hier bewust LAZY geïmporteerd (pas binnen
scrape_new_opponent_players), niet meer bovenaan het bestand.
scrape_player.py importeert op zijn beurt fetch_period_playwright.py, dat
Playwright vereist. Playwright/browser-binaries zijn niet beschikbaar op
Streamlit Community Cloud. Een top-level import hiervan liet de volledige
dashboard.py crashen bij het laden (ModuleNotFoundError: No module named
'playwright'), ook als er nooit een scrape-knop werd ingedrukt — want
dashboard.py importeert opponent_scout.py op zijn beurt onvoorwaardelijk
bovenaan.

scraper_v2.scrape_uitslagenblad blijft wél bovenaan geïmporteerd: die module
gebruikt enkel requests + BeautifulSoup, geen Playwright, en is dus altijd
veilig om te importeren, ook op cloud.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17 (op verzoek van Kim,
"we draaien in rondjes")
--------------------------------------------------------------------------
BUG (opgelost, kritiek): scrape_new_opponent_players() riep voorheen aan:
    fb.save_player_profile(p["user_id"], display_name=p["name"])
firebase_service.save_player_profile() schrijft met merge=True, MAAR zet
"club" en "club_normalized" altijd EXPLICIET in de payload (als None wanneer
niet meegegeven). Firestore's merge=True beschermt enkel velden die NIET in
de payload staan — een veld dat WEL aanwezig is (ook al is de waarde None)
wordt gewoon overschreven. Elke keer een tegenstander via "🔍 Tegenstander
analyseren" gescout werd, werd hun eventueel bekende club dus STILZWIJGEND
gewist, ongeacht of die club ooit correct was ingevuld (bv. via een eerdere
backfill of handmatige toevoeging).

Daarnaast ontbrak een consistente "added_by"-marker: page_add_player.py
(handmatige toevoeging) en opponent_scout.py (automatische ontdekking via
scouting) zetten BEIDE geen marker, in tegenstelling tot
enrich_opponents.ensure_profiles() (zet "auto_opponent_discovery"). Daardoor
kon cleanup_ghost_profiles.py deze via-scouting-ontdekte spelers niet
onderscheiden van bewust, handmatig toegevoegde spelers.

Fix, in _ensure_profile_safe() hieronder:
  1. Vóór het schrijven wordt het BESTAANDE profiel opgehaald. Is er al een
     club gekend, dan wordt die club expliciet doorgegeven aan
     save_player_profile() (i.p.v. impliciet None), zodat een bestaande club
     nooit meer verloren gaat bij een volgende scout/ververs-actie.
  2. added_by wordt gezet op "opponent_scout", maar ENKEL als het profiel nog
     GEEN added_by-veld heeft — een reeds bestaande marker wordt nooit
     overschreven.

--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20 (op verzoek van Kim: "Ik
ziet dat bij een ploeganalyse soms nog spelers van de eigenlijke ploeg bvb
te weinig zijn. bvb maar 3 spelers.")
--------------------------------------------------------------------------
ROOT CAUSE: scout_opponent() gebruikte tot nu toe een VAST `lookback`
(standaard 1). Als die ene wedstrijd door een onvolledig geparsed
uitslagenblad slechts een deel van de opstelling opleverde, of gewoon
effectief met een kleinere ploeg speelde, bevatte "unique_players" te
weinig spelers voor een zinvolle ploeganalyse.

FIX, twee onderdelen:
  1. scout_opponent() breidt nu AUTOMATISCH de lookback uit (tot
     max_lookback, standaard 4) zodra de roster na de eerste `lookback`
     wedstrijd(en) nog onder `min_players` (standaard 4) spelers telt.
  2. Elke entry in "unique_players" bevat nu ook "appearances" en
     "known_matches_total" als vertrouwensindicator.

--------------------------------------------------------------------------
PADEL_ANALYSIS_OPPONENT_WON_FIELD_2026-09-25 (op verzoek van Kim: "Winst-
matchen mag je eventueel gewoon in groen tonen in de tabel")
--------------------------------------------------------------------------
board.get("won") is dubbelzinnig - het geldt voor de partij die op het
uitslagenblad ALS EERSTE vermeld staat, wat naargelang is_opponent_home
ofwel de tegenstander ofwel de ANDERE partij kan zijn. Door dat hier, op de
ENE plek die is_opponent_home al kent, eenmalig ondubbelzinnig te berekenen
("opponent_won": won de GESCOUTE ploeg dit bord?), kan elke consument dit
veld voortaan zonder verdere aannames gebruiken.

Dit veld bleef in de praktijk ALTIJD None staan, want scrape_uitslagenblad()
in scraper_v2.py zocht tot nu toe naar een niet-bestaande "W"/"V"-letter
i.p.v. het echte, numerieke "Uitslag"-veld (0-1/1-0) - zie
PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25 in scraper_v2.py voor de
volledige analyse en fix. Met die fix krijgt "won" hier eindelijk een
bruikbare waarde, en werkt de berekening hieronder zoals altijd bedoeld was.

--------------------------------------------------------------------------
PADEL_ANALYSIS_OTHER_PAIR_AND_TEAM_SCORE_2026-09-25 (op verzoek van Kim:
"kolom resultaat moet kolom 'winnaar' worden waar de naam van de ploeg komt
die die match gewonnen heeft [...] totaal resultaat met games en sets en
totale score wordt ook niet getoond")
--------------------------------------------------------------------------
ROOT CAUSE (2 aparte gaten):
  1. Elk bord bevatte tot nu toe UITSLUITEND "opponent_pair" - de andere 2
     spelers (onze kant, of bij 2 andere ploegen: de niet-gescoute kant)
     werden simpelweg NIET opgeslagen. Daardoor kon de UI nooit tonen WIE
     een bord won als dat niet de gescoute ploeg was - enkel "Verloren" was
     mogelijk, nooit de naam van de winnende zijde.
  2. scrape_uitslagenblad() berekende voorheen ENKEL bord-informatie - de
     "Samenvatting"-sectie van de pagina (met de ECHTE eindscore in
     matchen/sets/spellen, en een expliciete "(winnaar)"-vermelding) werd
     nooit gelezen. page_lineup_lab.py moest de eindscore dus zelf afleiden
     door borden te tellen - foutgevoelig en onvolledig (geen sets/spellen).

FIX: extract_opponent_lineup() bewaart nu ook "other_pair" per bord (de
2 spelers die niet in opponent_pair zitten), zodat de UI de NAAM van de
winnende zijde altijd kan tonen, ongeacht wie won. Daarnaast geeft deze
functie nu ook de team-niveau samenvatting door (home_team/away_team/
winner_team/team_score_matches/team_score_sets/team_score_games), die
scrape_uitslagenblad() nu rechtstreeks van de pagina leest.
"""
import re
import sys
import time
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scraper_v2 import scrape_uitslagenblad  # noqa: E402  (veilig: geen Playwright)
import firebase_service as fb  # noqa: E402
import schedule_scraper as ss  # noqa: E402

# PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20: standaardwaarden voor
# de automatische lookback-uitbreiding.
MIN_PLAYERS_DEFAULT = 4
MAX_LOOKBACK_DEFAULT = 4


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _ensure_profile_safe(player_id: str, display_name: str, marker: str = "opponent_scout") -> None:
    """PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17.

    Veilige vervanging voor een kale `fb.save_player_profile(id, display_name=...)`-
    aanroep: behoudt een reeds bekende club (i.p.v. die impliciet naar None te
    overschrijven) en zet `added_by` enkel als dat veld nog niet bestaat, zodat
    een bestaande, specifiekere marker (bv. "manual") nooit verloren gaat.
    """
    try:
        existing = fb.get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        existing = {}
    existing_club = existing.get("club") or None
    fb.save_player_profile(
        player_id,
        display_name=display_name,
        club=existing_club,
    )
    if not existing.get("added_by"):
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
                {"added_by": marker}, merge=True
            )
        except Exception:  # noqa: BLE001
            pass


def _known_matches_total(player_id: str) -> int:
    """PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20: telt hoeveel
    matchen WIJ al kennen van deze speler (players-collectie), ongeacht club
    of team. Faalt de lookup (bv. nog geen document), dan is 0 een correct,
    verwacht antwoord - geen foutafhandeling nodig die de rest blokkeert."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        return 0
    matches = doc.get("matches") or []
    return len(matches) if isinstance(matches, list) else 0


def get_opponent_previous_fixtures(
    all_fixtures: list[dict],
    opponent_ploeg_id: str,
    before_date_text: str,
    lookback: int = 1,
) -> list[dict]:
    """
    Geeft de `lookback` meest recente, al GESPEELDE fixtures van de
    tegenstander terug, vóór de datum van de komende wedstrijd.
    """
    team_fixtures = ss.get_team_fixtures(all_fixtures, opponent_ploeg_id)
    before = ss._parse_date_text(before_date_text)
    played_before = [
        f for f in team_fixtures
        if f["played"] and ss._parse_date_text(f["date_text"]) and (
            before is None or ss._parse_date_text(f["date_text"]) < before
        )
    ]
    played_before.sort(key=lambda f: ss._parse_date_text(f["date_text"]))
    return played_before[-lookback:] if lookback else []


def extract_opponent_lineup(fixture: dict, opponent_name: str, opponent_ploeg_id: str, session=None) -> dict:
    """
    Haalt het uitslagenblad van deze (vorige) fixture op en bepaalt welke
    spelers aan de kant van de tegenstander (opponent_ploeg_id) stonden.

    Aanname (niet live geverifieerd): de volgorde van gevonden spelerslinks
    per rij volgt de tabelkolomvolgorde (eerst thuis-koppel, dan
    bezoekend-koppel) — consistent met de rest van de site, en bevestigd
    tegen 2 echte, onafhankelijke bordrijen (zie
    PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25 in scraper_v2.py).

    LET OP voor consumenten van "boards": scrape_uitslagenblad() zet een
    "round_text"-veld per bord, maar dat regex-patroon herkent enkel
    tornooi-achtige ronde-labels ("poule"/"finale"/"1/4" e.d.) — GEEN
    "Dubbel 1"/"Wedstrijd 1"-stijl bordnummering voor interclub-uitslagen-
    bladen. Voor interclub is round_text hier dus zo goed als altijd None;
    de POSITIE van een bord in de "boards"-lijst (index) is de enige
    beschikbare, benaderende indicator van bordvolgorde.
    """
    import requests
    session = session or requests.Session()
    out = {
        "fixture": fixture, "players": [], "boards": [], "error": None,
        # PADEL_ANALYSIS_OTHER_PAIR_AND_TEAM_SCORE_2026-09-25: team-niveau
        # samenvatting, rechtstreeks doorgegeven vanuit scrape_uitslagenblad().
        "home_team": None, "away_team": None,
        "home_ploeg_id": None, "away_ploeg_id": None,
        "winner_team": None, "winner_ploeg_id": None,
        "team_score_matches": None, "team_score_sets": None, "team_score_games": None,
    }
    url = fixture.get("uitslagenblad_url")
    if not url:
        out["error"] = "Geen uitslagenblad-link beschikbaar voor deze fixture."
        return out
    try:
        data = scrape_uitslagenblad(session, url)
    except Exception as e:
        out["error"] = f"Kon uitslagenblad niet ophalen: {e}"
        return out

    for veld in (
        "home_team", "away_team", "home_ploeg_id", "away_ploeg_id",
        "winner_team", "winner_ploeg_id",
        "team_score_matches", "team_score_sets", "team_score_games",
    ):
        out[veld] = data.get(veld)

    is_opponent_home = fixture.get("home_ploeg_id") == opponent_ploeg_id
    # Fallback: vergelijk namen als ploegId-koppeling niet zeker is
    if not is_opponent_home and not (fixture.get("away_ploeg_id") == opponent_ploeg_id):
        home_n = _normalize(data.get("home_team") or "")
        opp_n = _normalize(opponent_name)
        is_opponent_home = bool(opp_n) and opp_n in home_n

    seen_ids = set()
    for board_index, board in enumerate(data.get("matches", [])):
        players = board.get("players", [])
        rankings = board.get("rankings", [])
        if len(players) < 4:
            continue  # onverwachte rij-structuur, overslaan
        # rankings is een parallelle lijst (aanname: zelfde DOM-volgorde als players)
        players_with_rank = [
            {**p, "ranking": rankings[i] if i < len(rankings) else None}
            for i, p in enumerate(players)
        ]
        opp_pair = players_with_rank[0:2] if is_opponent_home else players_with_rank[2:4]
        # PADEL_ANALYSIS_OTHER_PAIR_AND_TEAM_SCORE_2026-09-25: de NIET-
        # gescoute kant van dit bord, tot nu toe altijd weggegooid. Nodig
        # om de naam van de winnende zijde te kunnen tonen ongeacht wie won.
        other_pair = players_with_rank[2:4] if is_opponent_home else players_with_rank[0:2]

        raw_won = board.get("won")
        # PADEL_ANALYSIS_OPPONENT_WON_FIELD_2026-09-25: board.get("won") is
        # dubbelzinnig - het geldt voor de partij die op het uitslagenblad
        # ALS EERSTE vermeld staat (players[0:2], de thuis-kolom), wat
        # naargelang is_opponent_home ofwel de tegenstander ofwel de ANDERE
        # partij kan zijn. Hier, op de ENE plek die is_opponent_home al
        # kent, eenmalig ondubbelzinnig berekend.
        opponent_won = None
        if raw_won is not None:
            opponent_won = bool(raw_won) if is_opponent_home else (not bool(raw_won))

        out["boards"].append({
            "opponent_pair": opp_pair,
            "other_pair": other_pair,
            "score": board.get("score"),
            "sets": board.get("sets"),
            "games": board.get("games"),
            "won": raw_won,  # vanuit perspectief van de partij die als eerste vermeld staat — niet noodzakelijk de tegenstander
            "opponent_won": opponent_won,  # ONDUBBELZINNIG: won de GESCOUTE ploeg (opponent_pair) dit bord?
            "board_position": board_index + 1,  # 1-based, vermoedelijke bordvolgorde (zie docstring hierboven)
        })
        for p in opp_pair:
            if p.get("user_id") and p["user_id"] not in seen_ids:
                seen_ids.add(p["user_id"])
                out["players"].append(p)
    return out


def scout_opponent(
    all_fixtures: list[dict],
    opponent_name: str,
    opponent_ploeg_id: str,
    before_date_text: str,
    lookback: int = 1,
    min_players: int = MIN_PLAYERS_DEFAULT,
    max_lookback: int = MAX_LOOKBACK_DEFAULT,
) -> dict:
    """
    Volledige scouting-bundel voor een aankomende tegenstander:
    hun laatste `lookback` wedstrijd(en) dit seizoen + de daarin gevonden
    individuele spelers (uniek over alle meegenomen wedstrijden).

    PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20: is de roster na de
    initiële `lookback` wedstrijd(en) nog KLEINER dan `min_players`
    (standaard 4), dan wordt de lookback STAP VOOR STAP uitgebreid (tot
    max_lookback, standaard 4) door telkens 1 extra, oudere fixture erbij te
    nemen. Wordt het minimum na max_lookback wedstrijden nog steeds niet
    gehaald, dan wordt gewoon de grootste roster teruggegeven die haalbaar
    was - GEEN blokkerende fout, enkel een kleinere roster dan ideaal.

    Elke entry in "unique_players" bevat "appearances" (in hoeveel van de
    doorzochte wedstrijden deze speler voorkwam) en "known_matches_total"
    (hun totaal gekende matchen in onze database, ongeacht team/club).
    """
    import requests
    session = requests.Session()

    def _scout_with_lookback(current_lookback: int):
        prev_fixtures = get_opponent_previous_fixtures(
            all_fixtures, opponent_ploeg_id, before_date_text, current_lookback,
        )
        if not prev_fixtures:
            return prev_fixtures, [], {}
        results = []
        appearances: dict[str, int] = {}
        names: dict[str, str] = {}
        for fx in prev_fixtures:
            extracted = extract_opponent_lineup(fx, opponent_name, opponent_ploeg_id, session=session)
            results.append(extracted)
            for p in extracted["players"]:
                uid = p["user_id"]
                names[uid] = p["name"]
                appearances[uid] = appearances.get(uid, 0) + 1
            time.sleep(1.0)  # zelfde beleefdheids-pauze als de rest van de scraper
        return prev_fixtures, results, {"appearances": appearances, "names": names}

    prev_fixtures, results, agg = _scout_with_lookback(lookback)
    if not prev_fixtures:
        return {
            "opponent_name": opponent_name,
            "opponent_ploeg_id": opponent_ploeg_id,
            "previous_fixtures": [],
            "unique_players": [],
            "note": "Geen eerdere, al gespeelde wedstrijden van deze tegenstander gevonden dit seizoen "
                    "(bv. hun eerste match, of nog niet gespeeld).",
        }

    effective_lookback = lookback
    while (
        len(agg.get("appearances", {})) < min_players
        and effective_lookback < max_lookback
    ):
        next_lookback = effective_lookback + 1
        next_prev_fixtures, next_results, next_agg = _scout_with_lookback(next_lookback)
        if len(next_prev_fixtures) <= len(prev_fixtures):
            # Geen extra, oudere fixture beschikbaar om bij te nemen -
            # verder proberen heeft geen zin.
            break
        prev_fixtures, results, agg = next_prev_fixtures, next_results, next_agg
        effective_lookback = next_lookback

    appearances = agg.get("appearances", {})
    names = agg.get("names", {})
    unique_players = []
    for uid, naam in names.items():
        unique_players.append({
            "user_id": uid,
            "name": naam,
            "appearances": appearances.get(uid, 0),
            "known_matches_total": _known_matches_total(uid),
        })

    note = None
    if len(unique_players) < min_players:
        note = (
            f"Slechts {len(unique_players)} speler(s) gekend na het doorzoeken van "
            f"{len(prev_fixtures)} vorige wedstrijd(en) (tot {effective_lookback} wedstrijden "
            f"teruggekeken, gewenst minimum was {min_players}). Dit kan wijzen op een kleinere "
            "effectieve ploeg, onvolledig geparste uitslagenbladen, of nog niet genoeg gespeelde "
            "wedstrijden dit seizoen."
        )

    return {
        "opponent_name": opponent_name,
        "opponent_ploeg_id": opponent_ploeg_id,
        "previous_fixtures": results,
        "unique_players": unique_players,
        "lookback_used": effective_lookback,
        "note": note,
    }


def scrape_new_opponent_players(
    players: list[dict],
    lookback_periods: int = 1,
    delay: float = 1.5,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """
    Scrapet sequentieel (met wachttijd) enkel de spelers uit `players` die nog
    NIET in onze database staan. players: [{"user_id":..., "name":...}, ...]

    lookback_periods: hoeveel periodes terug te scrapen (1 = enkel huidige —
    huidig gekozen default; later makkelijk te verhogen zonder verder iets
    aan te passen).

    Geen parallellisatie — bewust, om niet als één plotse vlaag van requests
    op te vallen (zie gesprek over discretie vs. snelheid).

    PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17: gebruikt nu
    _ensure_profile_safe() i.p.v. een kale fb.save_player_profile()-aanroep,
    zodat een bestaande club nooit meer stilzwijgend gewist wordt en elk
    nieuw profiel een added_by-marker krijgt (zie moduledocstring).
    """
    # LAZY IMPORT (fix): scrape_player.py importeert bovenaan
    # fetch_period_playwright.py, wat Playwright vereist. Op Streamlit Cloud
    # is dat niet beschikbaar. Door pas hier te importeren, blijft de rest
    # van dashboard.py/opponent_scout.py gewoon werken op cloud.
    from scrape_player import scrape_player

    to_scrape = []
    for p in players:
        existing = fb.get_player_profile(p["user_id"])
        if not existing:
            to_scrape.append(p)

    total = len(to_scrape)
    done, failed = [], []
    for i, p in enumerate(to_scrape, start=1):
        if progress_callback:
            progress_callback(i, total, p["name"])
        try:
            scrape_player(
                p["user_id"],
                max_new_periods=lookback_periods,
                force_full_refresh=False,
                save_to_firebase=True,
            )
            _ensure_profile_safe(p["user_id"], p["name"])
            done.append(p)
        except Exception as e:
            failed.append({**p, "error": str(e)})
        if i < total:
            time.sleep(delay)

    return {"already_known": len(players) - total, "newly_scraped": done, "failed": failed}
