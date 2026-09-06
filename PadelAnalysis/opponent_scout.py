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

BELANGRIJKE FIX (cloud-deploy, 2026-09-06):
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


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


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
    for board in data.get("matches", []):
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
        out["boards"].append({
            "opponent_pair": opp_pair,
            "score": board.get("score"),
            "won": board.get("won"),  # vanuit perspectief van de partij die als eerste vermeld staat — niet noodzakelijk de tegenstander
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
) -> dict:
    """
    Volledige scouting-bundel voor een aankomende tegenstander:
    hun laatste `lookback` wedstrijd(en) dit seizoen + de daarin gevonden
    individuele spelers (uniek over alle meegenomen wedstrijden).
    """
    import requests
    session = requests.Session()
    prev_fixtures = get_opponent_previous_fixtures(all_fixtures, opponent_ploeg_id, before_date_text, lookback)
    if not prev_fixtures:
        return {
            "opponent_name": opponent_name,
            "opponent_ploeg_id": opponent_ploeg_id,
            "previous_fixtures": [],
            "unique_players": [],
            "note": "Geen eerdere, al gespeelde wedstrijden van deze tegenstander gevonden dit seizoen "
                    "(bv. hun eerste match, of nog niet gespeeld).",
        }
    results = []
    unique_players = {}
    for fx in prev_fixtures:
        extracted = extract_opponent_lineup(fx, opponent_name, opponent_ploeg_id, session=session)
        results.append(extracted)
        for p in extracted["players"]:
            unique_players[p["user_id"]] = p["name"]
        time.sleep(1.0)  # zelfde beleefdheids-pauze als de rest van de scraper
    return {
        "opponent_name": opponent_name,
        "opponent_ploeg_id": opponent_ploeg_id,
        "previous_fixtures": results,
        "unique_players": [{"user_id": uid, "name": name} for uid, name in unique_players.items()],
        "note": None,
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
    """
    # LAZY IMPORT (fix 2026-09-06): scrape_player.py importeert bovenaan
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
            fb.save_player_profile(p["user_id"], display_name=p["name"])
            done.append(p)
        except Exception as e:
            failed.append({**p, "error": str(e)})
        if i < total:
            time.sleep(delay)
    return {"already_known": len(players) - total, "newly_scraped": done, "failed": failed}
