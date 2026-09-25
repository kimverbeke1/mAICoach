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
backfill of handmatige toevoeging). Concreet bevestigd: 4 gemelde spelers
(De Pourcq Hilde, Breda Hilde, Mondy Severine, Vanlerberghe Vivianne) tonen
allemaal club "(geen club)", ondanks dat het diagnosescript bevestigde dat ze
WEL degelijk op padelstats.be met een club geregistreerd staan
(T.C. WAREGEM GAVER voor de laatste twee).
Daarnaast ontbrak een consistente "added_by"-marker: page_add_player.py
(handmatige toevoeging) en opponent_scout.py (automatische ontdekking via
scouting) zetten BEIDE geen marker, in tegenstelling tot
enrich_opponents.ensure_profiles() (zet "auto_opponent_discovery"). Daardoor
kon cleanup_ghost_profiles.py deze via-scouting-ontdekte spelers niet
onderscheiden van bewust, handmatig toegevoegde spelers — de Spelers-lijst
kon dus nooit betrouwbaar opgeruimd worden voor DEZE categorie profielen.
Fix, in _ensure_profile_safe() hieronder:
  1. Vóór het schrijven wordt het BESTAANDE profiel opgehaald. Is er al een
     club gekend, dan wordt die club expliciet doorgegeven aan
     save_player_profile() (i.p.v. impliciet None), zodat een bestaande club
     nooit meer verloren gaat bij een volgende scout/ververs-actie.
  2. added_by wordt gezet op "opponent_scout", maar ENKEL als het profiel nog
     GEEN added_by-veld heeft — een reeds bestaande marker (bv.
     "auto_opponent_discovery" of "manual") wordt nooit overschreven. Dit
     laat cleanup_ghost_profiles.py toe om via-scouting-ontdekte spelers mee
     op te nemen in de opruiming, zonder ooit een bewust, handmatig
     toegevoegde speler te raken.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20 (op verzoek van Kim: "Ik
ziet dat bij een ploeganalyse soms nog spelers van de eigenlijke ploeg bvb
te weinig zijn. bvb maar 3 spelers. Gelieve altijd de spelers van de vorige
match te nemen als startbasis en ook het aantal matchen van die spelers
zodat je niet direct met foutmeldingen begint.")
--------------------------------------------------------------------------
ROOT CAUSE: scout_opponent() gebruikte tot nu toe een VAST `lookback`
(standaard 1 - enkel de allerlaatste, al gespeelde wedstrijd van de
tegenstander). Als die ene wedstrijd door een onvolledig/onverwacht
geparsed uitslagenblad slechts een deel van de opstelling opleverde (bv.
1 van de 2 dubbels kon niet correct geparsed worden - zie
extract_opponent_lineup()'s "if len(players) < 4: continue # onverwachte
rij-structuur, overslaan"), of gewoon effectief met een kleinere ploeg
speelde die specifieke match, bevatte "unique_players" te weinig spelers
voor een zinvolle ploeganalyse (bv. 3 i.p.v. de gebruikelijke 4).
FIX, twee onderdelen:
  1. scout_opponent() breidt nu AUTOMATISCH de lookback uit (tot
     max_lookback, standaard 4) zodra de roster na de eerste `lookback`
     wedstrijd(en) nog onder `min_players` (standaard 4) spelers telt - dit
     is exact "gebruik altijd de spelers van de vorige match(en) als
     startbasis": in plaats van te stoppen bij 1 onvolledige match, wordt
     stilzwijgend verder teruggekeken tot er genoeg spelers gekend zijn (of
     de historiek op is). Dit voorkomt dat een ploeganalyse met een te
     kleine/onvolledige roster start en downstream (bv. de opstelling-
     analyse) meteen op een foutmelding "te weinig spelers" botst.
  2. Elke entry in "unique_players" bevat nu, AANVULLEND (bestaande sleutels
     "user_id"/"name" blijven ongewijzigd - GEEN breaking change voor
     bestaande aanroepers/UI-code), twee nieuwe velden:
       - "appearances": in hoeveel van de doorzochte, recente
         tegenstander-wedstrijden deze speler voorkwam (hogere waarde =
         vermoedelijk vaste basisspeler, geen invaller).
       - "known_matches_total": het totaal aantal matchen dat WIJ al kennen
         van deze speler (via fb.get_player(), ongeacht club/team - dus ook
         nuttig voor een speler die nog geen eigen profiel/matchdata heeft:
         dan is dit gewoon 0, een duidelijk signaal "nog niets bekend" i.p.v.
         een onverklaarde lege tabelrij).
     Dit geeft Kim en de UI meteen een kwaliteits-/vertrouwensindicator per
     speler, zodat een kleine/onzekere roster NIET blind als "foutmelding"
     hoeft te worden gepresenteerd, maar CONTEXT krijgt ("3 spelers gekend,
     waarvan 1 met slechts 2 bekende matchen - mogelijk nog onvolledig").
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
# de automatische lookback-uitbreiding. 4 spelers is de gebruikelijke
# minimale kern voor 1 rotatie (2 dubbels) - vaak zijn er meer (invallers,
# meerdere rotaties), maar minder dan 4 is zelden bruikbaar als startbasis
# voor een ploeganalyse.
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
    bezoekend-koppel) — consistent met de rest van de site.
    LET OP voor consumenten van "boards": scrape_uitslagenblad() zet een
    "round_text"-veld per bord, maar dat regex-patroon herkent enkel
    tornooi-achtige ronde-labels ("poule"/"finale"/"1/4" e.d.) — GEEN
    "Dubbel 1"/"Wedstrijd 1"-stijl bordnummering voor interclub-uitslagen-
    bladen. Voor interclub is round_text hier dus zo goed als altijd None;
    de POSITIE van een bord in de "boards"-lijst (index) is de enige
    beschikbare, benaderende indicator van bordvolgorde (aanname: de tabel
    toont de dubbels in dezelfde volgorde als op de fysieke pagina, top naar
    onder). Zie page_lineup_lab.py voor waar dit als "vermoedelijke
    bordvolgorde" gebruikt en expliciet zo gelabeld wordt.
    """
    import requests
    session = session or requests.Session()
    out = {"fixture": fixture, "players": [], "boards": [], "error": None}
    url = fixture.get("uitslagenblad_url")
    if not url:
        out["error"] = "Geen uitslagenblad-link beschikbaar voor deze fixture."
        return out
    try:
        data = scrape_uitslagenblad(session, url)
    except Exception as e:
        out["error"] = f"Kon uitslagenblad niet ophalen: {e}"
        return out
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
        raw_won = board.get("won")
        # PADEL_ANALYSIS_OPPONENT_WON_FIELD_2026-09-25 (op verzoek van Kim:
        # "Winstmatchen mag je eventueel gewoon in groen tonen in de
        # tabel"): board.get("won") is dubbelzinnig - het geldt voor de
        # partij die op het uitslagenblad ALS EERSTE vermeld staat, wat
        # naargelang is_opponent_home ofwel de tegenstander ofwel de
        # ANDERE partij kan zijn. page_lineup_lab.py's _fixture_rows() zou
        # dit anders moeten HERberekenen (en dus opnieuw met dezelfde
        # dubbelzinnigheid kunnen fout gaan) om te weten of de GESCOUTE
        # ploeg (opponent_pair) dit bord won. Door dat HIER, op de ENE
        # plek die is_opponent_home al kent, eenmalig ondubbelzinnig te
        # berekenen, kan elke consument dit veld voortaan zonder verdere
        # aannames gebruiken.
        opponent_won = None
        if raw_won is not None:
            opponent_won = bool(raw_won) if is_opponent_home else (not bool(raw_won))
        out["boards"].append({
            "opponent_pair": opp_pair,
            "score": board.get("score"),
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

    PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20 (op verzoek van Kim:
    "Gelieve altijd de spelers van de vorige match te nemen als startbasis
    [...] zodat je niet direct met foutmeldingen begint"):
    Is de roster na de initiële `lookback` wedstrijd(en) nog KLEINER dan
    `min_players` (standaard 4 - de gebruikelijke minimale kern voor 1
    rotatie), dan wordt de lookback STAP VOOR STAP uitgebreid (tot
    max_lookback, standaard 4) door telkens 1 extra, oudere fixture erbij te
    nemen - dit voorkomt dat een toevallig onvolledig geparsed of kleiner
    opgestelde vorige match meteen een te kleine/onbruikbare ploeganalyse
    oplevert. Wordt het minimum na max_lookback wedstrijden nog steeds niet
    gehaald (bv. de tegenstander heeft simpelweg nog geen 4 wedstrijden
    gespeeld dit seizoen), dan wordt gewoon de grootste roster teruggegeven
    die haalbaar was - GEEN blokkerende fout, enkel een kleinere roster dan
    ideaal.

    Elke entry in "unique_players" bevat nu ook "appearances" (in hoeveel
    van de doorzochte wedstrijden deze speler voorkwam) en
    "known_matches_total" (hun totaal gekende matchen in onze database,
    ongeacht team/club) - beide ADDITIEF, bestaande "user_id"/"name"-sleutels
    blijven ongewijzigd voor bestaande aanroepers.
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

    # PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20: automatisch verder
    # teruckijken zolang de roster te klein blijft, tot max_lookback bereikt
    # is of er geen extra fixtures meer over zijn (herkenbaar doordat een
    # grotere lookback-waarde exact dezelfde prev_fixtures teruggeeft).
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
            # PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20: additief,
            # geen impact op bestaande aanroepers die enkel user_id/name lezen.
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
    # van dashboard.py/opponent_scout.py gewoon werken op cloud; enkel het
    # effectief scrapen van nieuwe tegenstander-spelers vereist een lokale
    # omgeving (waar is_scraping_available() dit al afschermt in dashboard.py).
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
