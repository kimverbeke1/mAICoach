"""
schedule_scraper.py - haalt het poule/tabel-schema op en parseert de fixtures.

Belangrijk:
- played wordt bepaald via een ingevulde ontmoetingsscore.
- identify_own_ploeg_id vergelijkt het uitslagenblad van de laatste gekende
  interclubdatum met partner- en tegenstandernamen uit het spelersdocument.
  Daardoor wordt de eigen ploeg automatisch onderscheiden van de tegenstander.
"""
from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.tennisenpadelvlaanderen.be"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"


def _param_from_url(href: Optional[str], param: str) -> Optional[str]:
    if not href:
        return None
    values = parse_qs(urlparse(href).query).get(param)
    return values[0] if values else None


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _norm(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def fetch_poule_schedule_html(
    url: str,
    session: Optional[requests.Session] = None,
    delay: float = 1.0,
) -> str:
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    if delay > 0:
        time.sleep(delay)
    full_url = url if url.startswith("http") else BASE_URL + url
    response = session.get(full_url, timeout=20)
    response.raise_for_status()
    return response.text


def parse_poule_schedule(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    fixtures = []
    for table in soup.find_all("table"):
        poule_label = _find_preceding_label(table)
        for row in table.find_all("tr"):
            columns = row.find_all("td")
            if len(columns) < 3:
                continue
            row_text = _clean(row.get_text())
            links = row.find_all("a")
            team_links = [a for a in links if _param_from_url(a.get("href"), "ploegId")]
            if len(team_links) < 2:
                continue
            home_link, away_link = team_links[0], team_links[1]
            home_name = _clean(home_link.get_text())
            away_name = _clean(away_link.get_text())
            home_id = _param_from_url(home_link.get("href"), "ploegId")
            away_id = _param_from_url(away_link.get("href"), "ploegId")
            group_id = (
                _param_from_url(home_link.get("href"), "spelgroepId")
                or _param_from_url(away_link.get("href"), "spelgroepId")
            )
            match_link = next(
                (a for a in links if _param_from_url(a.get("href"), "matchId")),
                None,
            )
            match_id = _param_from_url(match_link.get("href"), "matchId") if match_link else None
            result_url = match_link.get("href") if match_link else None
            date_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}(\s+\d{1,2}:\d{2})?\b", row_text)
            date_text = date_match.group(0) if date_match else ""
            remainder = row_text.replace(home_name, "").replace(away_name, "")
            if date_text:
                remainder = remainder.replace(date_text, "")
            scores = re.findall(r"\d+[-/]\d+(?:\s*/\s*\d+[-/]\d+)*", remainder)
            score = scores[0] if scores else None
            fixtures.append({
                "poule_label": poule_label,
                "date_text": date_text,
                "home_name": home_name,
                "home_ploeg_id": home_id,
                "away_name": away_name,
                "away_ploeg_id": away_id,
                "score": score,
                "spelgroep_id": group_id,
                "match_id": match_id,
                "uitslagenblad_url": result_url,
                "played": bool(score),
            })
    return fixtures


def _find_preceding_label(table) -> str:
    element = table
    for _ in range(8):
        element = element.find_previous(["h1", "h2", "h3", "h4", "h5", "strong", "div", "p"])
        if element is None:
            break
        text = _clean(element.get_text())
        if 0 < len(text) <= 40 and re.search(
            r"poule|eindronde|klassement|finale|ronde", text, re.I
        ):
            return text
    return "Poule ?"


def _parse_date_text(date_text: str):
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_text or "")
    if not match:
        match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_text or "")
        if not match:
            return None
        year, month, day = match.groups()
        return int(year), int(month), int(day)
    day, month, year = match.groups()
    return int(year), int(month), int(day)


def _known_names_for_date(own_known_matches: list[dict], date_key: tuple) -> tuple[set[str], set[str]]:
    own_side = set()
    opponent_side = set()
    for match in own_known_matches:
        if match.get("match_type") != "interclub":
            continue
        if _parse_date_text(match.get("match_date") or "") != date_key:
            continue
        for key in ("player_name", "display_name", "partner_name"):
            value = _norm(match.get(key))
            if value:
                own_side.add(value)
        for key in ("opp1_name", "opp2_name"):
            value = _norm(match.get(key))
            if value:
                opponent_side.add(value)
    return own_side, opponent_side


def _fixture_player_sides(fixture: dict) -> tuple[set[str], set[str]]:
    """Lees het uitslagenblad en geef de spelersnamen per kant terug."""
    url = fixture.get("uitslagenblad_url")
    if not url:
        return set(), set()
    try:
        from scraper_v2 import scrape_uitslagenblad

        data = scrape_uitslagenblad(requests.Session(), url)
    except Exception:
        return set(), set()
    home_players: set[str] = set()
    away_players: set[str] = set()
    for board in data.get("matches", []) or []:
        players = board.get("players", []) or []
        if len(players) < 4:
            continue
        for player in players[:2]:
            name = _norm(player.get("name"))
            if name:
                home_players.add(name)
        for player in players[2:4]:
            name = _norm(player.get("name"))
            if name:
                away_players.add(name)
    return home_players, away_players


def _overlap_score(side: set[str], expected: set[str]) -> int:
    score = 0
    for actual in side:
        for wanted in expected:
            if actual == wanted or (len(actual) >= 6 and actual in wanted) or (len(wanted) >= 6 and wanted in actual):
                score += 1
                break
    return score


def identify_own_ploeg_id(fixtures: list[dict], own_known_matches: list[dict]):
    """
    Bepaal automatisch de eigen ploeg via de meest recente gespeelde fixture
    waarvan de datum voorkomt in de matchhistoriek van de geselecteerde speler.

    De functie retourneert bewust de opgeloste eigen ploeg-id in beide eerste
    posities. Dit houdt compatibiliteit met de bestaande dashboard-flow, die
    vroeger zelf nog probeerde te kiezen tussen home en away.
    """
    own_dates = {
        parsed
        for match in own_known_matches
        if match.get("match_type") == "interclub"
        for parsed in [_parse_date_text(match.get("match_date") or "")]
        if parsed
    }
    candidates = []
    for fixture in fixtures:
        parsed = _parse_date_text(fixture.get("date_text") or "")
        if fixture.get("played") and parsed and parsed in own_dates:
            candidates.append((parsed, fixture))
    candidates.sort(key=lambda item: item[0], reverse=True)

    for date_key, fixture in candidates:
        own_names, opponent_names = _known_names_for_date(own_known_matches, date_key)
        home_players, away_players = _fixture_player_sides(fixture)
        if not home_players and not away_players:
            continue
        home_score = 3 * _overlap_score(home_players, own_names) + _overlap_score(away_players, opponent_names)
        away_score = 3 * _overlap_score(away_players, own_names) + _overlap_score(home_players, opponent_names)
        if home_score == away_score:
            continue
        own_id = fixture.get("home_ploeg_id") if home_score > away_score else fixture.get("away_ploeg_id")
        if own_id:
            resolved = dict(fixture)
            resolved["resolved_own_ploeg_id"] = own_id
            return own_id, own_id, resolved

    return None, None, None


def get_team_fixtures(fixtures: list[dict], ploeg_id: str) -> list[dict]:
    team_fixtures = [
        fixture
        for fixture in fixtures
        if fixture.get("home_ploeg_id") == ploeg_id or fixture.get("away_ploeg_id") == ploeg_id
    ]
    team_fixtures.sort(key=lambda fixture: _parse_date_text(fixture.get("date_text") or "") or (9999, 99, 99))
    return team_fixtures


def get_next_match(team_fixtures: list[dict]) -> Optional[dict]:
    for fixture in team_fixtures:
        if not fixture.get("played"):
            return fixture
    return None


def opponent_of(fixture: dict, own_ploeg_id: str) -> dict:
    if fixture.get("home_ploeg_id") == own_ploeg_id:
        return {"name": fixture.get("away_name"), "ploeg_id": fixture.get("away_ploeg_id")}
    return {"name": fixture.get("home_name"), "ploeg_id": fixture.get("home_ploeg_id")}
