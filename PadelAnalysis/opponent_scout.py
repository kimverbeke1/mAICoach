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
dashboard.py crashen bij het laden, ook als er nooit een scrape-knop werd
ingedrukt — want dashboard.py importeert opponent_scout.py op zijn beurt
onvoorwaardelijk bovenaan.

scraper_v2.scrape_uitslagenblad blijft wél bovenaan geïmporteerd: die module
gebruikt enkel requests + BeautifulSoup, geen Playwright, en is dus altijd
veilig om te importeren, ook op cloud.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17 (op verzoek van Kim,
"we draaien in rondjes")
--------------------------------------------------------------------------
BUG (opgelost, kritiek): scrape_new_opponent_players() riep voorheen aan:
    fb.save_player_profile(p["user_id"], display_name=p["name"])
firebase_service.save_player_profile() zet "club" altijd expliciet in de
payload (als None bij ontbreken), en merge=True beschermt enkel velden die
NIET in de payload staan — een reeds bekende club werd dus STILZWIJGEND
gewist bij elke scout. Fix in _ensure_profile_safe(): bestaand profiel eerst
ophalen, gekende club expliciet doorgeven, en added_by enkel zetten als het
nog ontbreekt.

--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20 (op verzoek van Kim: "Ik
ziet dat bij een ploeganalyse soms nog spelers van de eigenlijke ploeg bvb
te weinig zijn.")
--------------------------------------------------------------------------
scout_opponent() breidt de lookback nu AUTOMATISCH uit (tot max_lookback,
standaard 4) zodra de roster na de eerste `lookback` wedstrijd(en) nog onder
`min_players` (standaard 4) spelers telt. Elke entry in "unique_players"
bevat ook "appearances" en "known_matches_total" als vertrouwensindicator.

--------------------------------------------------------------------------
PADEL_ANALYSIS_OPPONENT_WON_FIELD_2026-09-25 / PADEL_ANALYSIS_OTHER_PAIR_
AND_TEAM_SCORE_2026-09-25
--------------------------------------------------------------------------
extract_opponent_lineup() berekent nu ondubbelzinnig "opponent_won" per
bord, en bewaart ook "other_pair" + team-niveau samenvatting (home_team/
away_team/winner_team/team_score_*), rechtstreeks doorgegeven vanuit
scrape_uitslagenblad().

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCOUT_PARALLEL_FETCH_2026-09-27 (op verzoek van Kim: "de
allereerste analyse is nog steeds traag")
--------------------------------------------------------------------------
BEVESTIGD: scout_opponent() deed voorheen, voor ELKE fixture, een
SEQUENTIËLE live HTTP-fetch MET een expliciete time.sleep(1.0) NA ELKE
fetch, en bij lookback-uitbreiding werden reeds gefetchte fixtures OPNIEUW
herhaald (geen hergebruik). FIX: fetched_cache zorgt dat elke fixture MAX 1
keer gefetcht wordt over de volledige (eventueel uitgebreide) scouting-
poging heen; nieuwe fixtures binnen 1 stap worden bovendien PARALLEL
opgehaald via ThreadPoolExecutor (max_workers standaard 4, I/O-bound
netwerkwerk zonder browser, dus veilig te parallelliseren).

--------------------------------------------------------------------------
PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27 (op verzoek van Kim: "ik wil
snelheid verbeteren [...] pas aan waar nodig")
--------------------------------------------------------------------------
_known_matches_total() had een ongecachete fb.get_player()-call per
tegenstander-speler, vlak naast een vergelijkbare read in opponent_scout_ui.
prepare_team_docs(). FIX: eigen 300s TTL-cache (bewust GEEN st.cache_data,
want dit bestand moet ook buiten Streamlit bruikbaar blijven - zie
scrape_new_opponent_players()'s lazy-import-conventie hierboven).
clear_known_matches_cache() wordt vanuit opponent_scout_ui.py aangeroepen op
dezelfde plekken als de overige cache-clears.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28 (op verzoek van Kim, na
analyse van opponent_scout_ui.py + lineup_scout.py: "eerste laadactie van de
ploegopstelling pagina te versnellen")
--------------------------------------------------------------------------
BEVESTIGD (nieuwe, concrete bug - geen vermoeden): zodra "🔍 Tegenstander
analyseren" geklikt wordt, gebeuren er 2 VOLLEDIG ONAFHANKELIJKE
scout_opponent()-aanroepen voor DEZELFDE tegenstander-ploeg, op dezelfde
pagina-render:
  1. opponent_scout_ui._run_scout_and_scrape(): lookback=1..4 (het snelle
     standaardpad, enkel de meest recente wedstrijd(en)).
  2. lineup_scout._scout_team_all_fixtures() (aangeroepen via
     page_lineup_lab._merge_full_opponent_roster(), voor de "Vorige
     gespeelde matchen"-tab/match1-match2-frequentie): lookback=n = ALLE
     dit seizoen gespeelde wedstrijden van de tegenstander (min_players=0,
     max_lookback=n).
Elke aanroep van scout_opponent() had tot nu toe een EIGEN, lokale
fetched_cache (gedefinieerd ALS lokale variabele binnen de functie zelf) -
dus fixtures die aanroep 1 al ophaalde, werden door aanroep 2 GEWOON OPNIEUW
gefetcht, bovenop de rest. Bij een tegenstander die dit seizoen bv. 8
wedstrijden speelde: aanroep 1 haalt er 1-4 op, aanroep 2 haalt ALLE 8
OPNIEUW op - tot 4 pure, vermijdbare dubbele HTTP-fetches, exact op het
moment dat de analyse voor het eerst verschijnt (de "eerste laadactie"
waar Kim op wijst).
FIX: scout_opponent() accepteert nu een optionele `fetched_cache`-parameter
(een gewoon dict, GEEN Streamlit-afhankelijkheid in dit bestand). Geeft de
aanroeper niks mee, dan is het gedrag exact zoals voorheen (eigen, lokale
cache). Geeft de aanroeper een dict mee, dan wordt DIE hergebruikt/gevuld -
zodat meerdere scout_opponent()-aanroepen voor dezelfde tegenstander-ploeg
binnen dezelfde sessie hun fetch-resultaten kunnen DELEN.
shared_fetch_cache_key(ploeg_id) hieronder is de centrale, consistente
sleutel-naamgeving die BEIDE aanroepers (opponent_scout_ui.py en
lineup_scout.py) gebruiken om in st.session_state naar DEZELFDE gedeelde
cache-dict te verwijzen - hier centraal gedefinieerd (i.p.v. de sleutel-
string op 2 plekken te dupliceren) om een mismatch/tikfout tussen beide
aanroepers onmogelijk te maken.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PROCESS_WIDE_SCOUT_CACHE_2026-09-29 (op verzoek van Kim, na
meting: "osu.render_scout_header" 5.3-5.8s eigen tijd, "_merge_full_
opponent_roster" 3.2s, "_recent_own_lineup_roster" 3.6s - telkens opnieuw
na F5 of een nieuwe sessie)
--------------------------------------------------------------------------
ROOT CAUSE: de gedeelde fetch-cache van hierboven leefde in st.session_state
- dus PER SESSIE. Een F5 of een nieuw tabblad is voor Streamlit een nieuwe
sessie: alle uitslagenbladen werden dan opnieuw live opgehaald (~1-2s per
blad), voor de tegenploeg EN voor de eigen ploeg. Die bladen gaan over al
GESPEELDE wedstrijden en veranderen in de praktijk niet meer.
FIX:
  - get_shared_fetch_cache(ploeg_id): een PROCES-BREDE cache (module-
    niveau, net als _known_matches_cache), die over sessies, F5 en
    paginawissels heen blijft bestaan tot een herstart van de app. TTL 12u
    per ploeg.
  - scout_opponent() bewaart in die cache ENKEL geslaagde resultaten met
    minstens 1 bord. Een fout of een (nog) leeg uitslagenblad wordt dus
    NIET onthouden en bij de volgende poging gewoon opnieuw opgehaald.
  - get_saved_scout_bundle()/save_scout_bundle(): het volledige
    scout-resultaat (de tegenstander-analyse) wordt proces-breed onthouden
    en daarnaast in Firestore (collectie SCOUT_BUNDLES_COLLECTION)
    weggeschreven. Zo blijft de analyse staan na F5, na een paginawissel en
    zelfs na een herstart/deploy van de app - zonder opnieuw op
    "Tegenstander analyseren" te moeten klikken. De sleutel bevat de datum
    van de volgende match: zodra die gespeeld is, hoort er vanzelf een
    nieuwe analyse bij.
Dit bestand blijft vrij van Streamlit-afhankelijkheden.
"""
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scraper_v2 import scrape_uitslagenblad  # noqa: E402  (veilig: geen Playwright)
import firebase_service as fb  # noqa: E402
import schedule_scraper as ss  # noqa: E402

MIN_PLAYERS_DEFAULT = 4
MAX_LOOKBACK_DEFAULT = 4
SCOUT_FETCH_MAX_WORKERS_DEFAULT = 4
_KNOWN_MATCHES_CACHE_TTL = 300
_known_matches_cache: dict[str, tuple[float, int]] = {}
_known_matches_cache_lock = threading.Lock()


# PADEL_ANALYSIS_PROCESS_WIDE_SCOUT_CACHE_2026-09-29 - zie moduledocstring
SHARED_FETCH_TTL_SECONDS = 12 * 3600
_shared_fetch_store: dict[str, tuple[float, dict]] = {}
_shared_fetch_lock = threading.Lock()

SCOUT_BUNDLES_COLLECTION = "scout_bundles"
SCOUT_BUNDLE_TTL_SECONDS = 7 * 24 * 3600
_scout_bundle_store: dict[str, tuple[float, dict]] = {}
_scout_bundle_lock = threading.Lock()


def get_shared_fetch_cache(opponent_ploeg_id: str) -> dict:
    """Proces-brede fetch-cache voor 1 ploeg (zie moduledocstring). Geeft
    altijd hetzelfde dict-object terug zolang de TTL niet verlopen is."""
    key = str(opponent_ploeg_id)
    now = time.time()
    with _shared_fetch_lock:
        entry = _shared_fetch_store.get(key)
        if entry is None or (now - entry[0]) > SHARED_FETCH_TTL_SECONDS:
            entry = (now, {})
            _shared_fetch_store[key] = entry
        return entry[1]


def clear_shared_fetch_cache(opponent_ploeg_id: Optional[str] = None) -> None:
    with _shared_fetch_lock:
        if opponent_ploeg_id is None:
            _shared_fetch_store.clear()
        else:
            _shared_fetch_store.pop(str(opponent_ploeg_id), None)


def _cacheable_fetch_result(result: dict) -> bool:
    """Enkel een geslaagd uitslagenblad MET borden mag onthouden worden."""
    return bool(result) and not result.get("error") and bool(result.get("boards"))


def _bundle_doc_id(bundle_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(bundle_key))[:500]


def get_saved_scout_bundle(bundle_key: str) -> Optional[dict]:
    """Geeft een eerder bewaard scout-resultaat terug: eerst uit het
    proces-geheugen, anders uit Firestore. None als niets (geldigs) gekend
    is. Faalt altijd stil."""
    now = time.time()
    with _scout_bundle_lock:
        entry = _scout_bundle_store.get(bundle_key)
    if entry is not None and (now - entry[0]) <= SCOUT_BUNDLE_TTL_SECONDS:
        return entry[1]
    try:
        doc = fb.db.collection(SCOUT_BUNDLES_COLLECTION).document(_bundle_doc_id(bundle_key)).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        saved_at = float(data.get("saved_at_epoch") or 0)
        bundle = data.get("bundle")
        if not isinstance(bundle, dict) or (now - saved_at) > SCOUT_BUNDLE_TTL_SECONDS:
            return None
    except Exception:  # noqa: BLE001
        return None
    with _scout_bundle_lock:
        _scout_bundle_store[bundle_key] = (saved_at, bundle)
    return bundle


def save_scout_bundle(bundle_key: str, bundle: Optional[dict]) -> None:
    """Bewaart een scout-resultaat proces-breed EN in Firestore. Enkel een
    resultaat met minstens 1 speler wordt bewaard. Faalt altijd stil."""
    if not bundle or not bundle.get("unique_players"):
        return
    now = time.time()
    with _scout_bundle_lock:
        _scout_bundle_store[bundle_key] = (now, bundle)
    try:
        payload = {
            "bundle_key": str(bundle_key),
            "saved_at_epoch": now,
            "bundle": fb.sanitize_for_firestore(bundle),
        }
        fb.db.collection(SCOUT_BUNDLES_COLLECTION).document(_bundle_doc_id(bundle_key)).set(payload)
    except Exception:  # noqa: BLE001
        pass


def clear_saved_scout_bundle(bundle_key: str) -> None:
    with _scout_bundle_lock:
        _scout_bundle_store.pop(bundle_key, None)
    try:
        fb.db.collection(SCOUT_BUNDLES_COLLECTION).document(_bundle_doc_id(bundle_key)).delete()
    except Exception:  # noqa: BLE001
        pass


def shared_fetch_cache_key(opponent_ploeg_id: str) -> str:
    """PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28: centrale sleutel-
    naamgeving voor een gedeelde `fetched_cache` (zie scout_opponent()) over
    MEERDERE aanroepen heen voor dezelfde tegenstander-ploeg, ongeacht welk
    UI-bestand de aanroep doet. Hier centraal gedefinieerd zodat
    opponent_scout_ui.py en lineup_scout.py exact dezelfde sleutel
    gebruiken."""
    return f"osc_shared_fetch_cache_{opponent_ploeg_id}"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _ensure_profile_safe(player_id: str, display_name: str, marker: str = "opponent_scout") -> None:
    """PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17: behoudt een reeds
    bekende club en zet added_by enkel als dat veld nog niet bestaat."""
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
    """PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27: 300s-gecacht (zie
    moduledocstring)."""
    now = time.time()
    with _known_matches_cache_lock:
        cached = _known_matches_cache.get(player_id)
        if cached is not None and (now - cached[0]) < _KNOWN_MATCHES_CACHE_TTL:
            return cached[1]
    try:
        doc = fb.get_player(player_id) or {}
        matches = doc.get("matches") or []
        result = len(matches) if isinstance(matches, list) else 0
    except Exception:  # noqa: BLE001
        result = 0
    with _known_matches_cache_lock:
        _known_matches_cache[player_id] = (now, result)
    return result


def clear_known_matches_cache() -> None:
    """Leegt de cache hierboven. Aan te roepen na elke geslaagde sync-actie
    voor een tegenstander-roster."""
    with _known_matches_cache_lock:
        _known_matches_cache.clear()


def get_opponent_previous_fixtures(
    all_fixtures: list[dict],
    opponent_ploeg_id: str,
    before_date_text: str,
    lookback: int = 1,
) -> list[dict]:
    """Geeft de `lookback` meest recente, al GESPEELDE fixtures van de
    tegenstander terug, vóór de datum van de komende wedstrijd."""
    team_fixtures = ss.get_team_fixtures(all_fixtures, opponent_ploeg_id)
    before = ss._parse_date_text(before_date_text)
    # PADEL_ANALYSIS_LAST_MATCH_BOUNDARY_FIX_2026-09-26: `<=` i.p.v. `<` -
    # strikt VEILIGER (played_before filtert al eerst op f["played"]).
    played_before = [
        f for f in team_fixtures
        if f["played"] and ss._parse_date_text(f["date_text"]) and (
            before is None or ss._parse_date_text(f["date_text"]) <= before
        )
    ]
    played_before.sort(key=lambda f: ss._parse_date_text(f["date_text"]))
    return played_before[-lookback:] if lookback else []


def extract_opponent_lineup(fixture: dict, opponent_name: str, opponent_ploeg_id: str, session=None) -> dict:
    """Haalt het uitslagenblad van deze (vorige) fixture op en bepaalt welke
    spelers aan de kant van de tegenstander stonden.
    PADEL_ANALYSIS_SCOUT_PARALLEL_FETCH_2026-09-27: wordt nu mogelijk vanuit
    meerdere threads tegelijk aangeroepen - elke aanroeper geeft een EIGEN,
    niet-gedeelde requests.Session() mee."""
    import requests
    session = session or requests.Session()
    out = {
        "fixture": fixture, "players": [], "boards": [], "error": None,
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
    if not is_opponent_home and not (fixture.get("away_ploeg_id") == opponent_ploeg_id):
        home_n = _normalize(data.get("home_team") or "")
        opp_n = _normalize(opponent_name)
        is_opponent_home = bool(opp_n) and opp_n in home_n
    seen_ids = set()
    for board_index, board in enumerate(data.get("matches", [])):
        players = board.get("players", [])
        rankings = board.get("rankings", [])
        if len(players) < 4:
            continue
        players_with_rank = [
            {**p, "ranking": rankings[i] if i < len(rankings) else None}
            for i, p in enumerate(players)
        ]
        opp_pair = players_with_rank[0:2] if is_opponent_home else players_with_rank[2:4]
        other_pair = players_with_rank[2:4] if is_opponent_home else players_with_rank[0:2]
        raw_won = board.get("won")
        opponent_won = None
        if raw_won is not None:
            opponent_won = bool(raw_won) if is_opponent_home else (not bool(raw_won))
        out["boards"].append({
            "opponent_pair": opp_pair,
            "other_pair": other_pair,
            "score": board.get("score"),
            "sets": board.get("sets"),
            "games": board.get("games"),
            "won": raw_won,
            "opponent_won": opponent_won,
            "board_position": board_index + 1,
        })
        for p in opp_pair:
            if p.get("user_id") and p["user_id"] not in seen_ids:
                seen_ids.add(p["user_id"])
                out["players"].append(p)
    return out


def _fixture_key(fixture: dict) -> str:
    """Stabiele sleutel om eenzelfde fixture te herkennen, zowel over
    lookback-uitbreidingen binnen 1 scout_opponent()-aanroep heen, als - sinds
    PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28 - over MEERDERE aanroepen
    heen (via een gedeelde fetched_cache)."""
    return fixture.get("uitslagenblad_url") or f"__no_url__{fixture.get('date_text')}"


def _fetch_fixtures_parallel(
    fixtures: list[dict],
    opponent_name: str,
    opponent_ploeg_id: str,
    max_workers: int = SCOUT_FETCH_MAX_WORKERS_DEFAULT,
) -> dict:
    """Haalt de uitslagenbladen van `fixtures` GELIJKTIJDIG op (I/O-bound
    netwerkwerk). Elke thread gebruikt een EIGEN requests.Session()."""
    import requests

    results: dict[str, dict] = {}
    if not fixtures:
        return results
    workers = max(1, min(max_workers, len(fixtures)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_key = {
            executor.submit(
                extract_opponent_lineup,
                fx, opponent_name, opponent_ploeg_id,
                requests.Session(),
            ): _fixture_key(fx)
            for fx in fixtures
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                results[key] = future.result()
            except Exception as e:  # noqa: BLE001
                results[key] = {
                    "fixture": None, "players": [], "boards": [],
                    "error": f"Kon uitslagenblad niet ophalen: {e}",
                }
    return results


def scout_opponent(
    all_fixtures: list[dict],
    opponent_name: str,
    opponent_ploeg_id: str,
    before_date_text: str,
    lookback: int = 1,
    min_players: int = MIN_PLAYERS_DEFAULT,
    max_lookback: int = MAX_LOOKBACK_DEFAULT,
    max_workers: int = SCOUT_FETCH_MAX_WORKERS_DEFAULT,
    fetched_cache: Optional[dict] = None,
) -> dict:
    """
    Volledige scouting-bundel voor een aankomende tegenstander: hun laatste
    `lookback` wedstrijd(en) dit seizoen + de daarin gevonden individuele
    spelers (uniek over alle meegenomen wedstrijden).

    PADEL_ANALYSIS_TEAM_ROSTER_TOO_SMALL_FIX_2026-09-20: lookback breidt
    automatisch uit (tot max_lookback) zodra de roster nog onder
    min_players zit.

    PADEL_ANALYSIS_SCOUT_PARALLEL_FETCH_2026-09-27: elke fixture wordt MAX 1
    keer gefetcht binnen deze aanroep, en nieuwe fixtures worden PARALLEL
    opgehaald.

    PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28 (op verzoek van Kim, zie
    moduledocstring voor de volledige, bevestigde analyse): `fetched_cache`
    is nu een OPTIONELE parameter. Geef je niets mee (standaard, backward-
    compatible), dan gebruikt deze aanroep een eigen, lokale cache zoals
    voorheen. Geef je een dict mee (bv. een gedeelde cache uit
    st.session_state via shared_fetch_cache_key()), dan wordt DIE gebruikt/
    aangevuld - zodat een tweede scout_opponent()-aanroep voor DEZELFDE
    tegenstander-ploeg (bv. de "alle wedstrijden"-scout in lineup_scout.py)
    fixtures die een eerdere aanroep al ophaalde, NIET meer opnieuw fetcht.
    """
    fetched_cache = fetched_cache if fetched_cache is not None else {}
    local_uncached: dict = {}

    def _scout_with_lookback(current_lookback: int):
        prev_fixtures = get_opponent_previous_fixtures(
            all_fixtures, opponent_ploeg_id, before_date_text, current_lookback,
        )
        if not prev_fixtures:
            return prev_fixtures, [], {}
        to_fetch = [
            fx for fx in prev_fixtures
            if _fixture_key(fx) not in fetched_cache and _fixture_key(fx) not in local_uncached
        ]
        if to_fetch:
            nieuw = _fetch_fixtures_parallel(to_fetch, opponent_name, opponent_ploeg_id, max_workers=max_workers)
            # PADEL_ANALYSIS_PROCESS_WIDE_SCOUT_CACHE_2026-09-29: enkel
            # geslaagde bladen met borden in de (gedeelde) cache; fouten en
            # lege bladen enkel lokaal, binnen deze ene aanroep.
            for key, res in nieuw.items():
                if _cacheable_fetch_result(res):
                    fetched_cache[key] = res
                else:
                    local_uncached[key] = res
        results = [
            fetched_cache.get(_fixture_key(fx)) or local_uncached.get(_fixture_key(fx)) or {
                "fixture": fx, "players": [], "boards": [], "error": "Niet opgehaald.",
            }
            for fx in prev_fixtures
        ]
        appearances: dict[str, int] = {}
        names: dict[str, str] = {}
        for extracted in results:
            for p in extracted.get("players", []):
                uid = p["user_id"]
                names[uid] = p["name"]
                appearances[uid] = appearances.get(uid, 0) + 1
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
    """Scrapet sequentieel (met wachttijd) enkel de spelers uit `players` die
    nog NIET in onze database staan. Geen parallellisatie — bewust, om niet
    als één plotse vlaag van requests op te vallen; deze functie wordt
    sowieso enkel lokaal (can_scrape=True) synchroon gebruikt."""
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
