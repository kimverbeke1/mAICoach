"""
schedule_scraper.py — haalt het publieke poule/tabel-schema op
(https://www.tennisenpadelvlaanderen.be/zoek-een-competitie-organisatie?...)

Dit is GEEN Elit 2.0 / login-vereiste pagina — gewone server-side gerenderde
HTML, dus een simpele requests.Session volstaat (geen Playwright nodig).

Belangrijk: deze pagina toont het volledige schema van een afdeling (alle
poules), telkens met thuis-/bezoekende ploeg (naam + unieke ploegId), datum,
score en — bij gespeelde matchen — een link naar het uitslagenblad met een
matchId. Nog te spelen matchen hebben geen score/uitslagenblad-link; dat is
hoe we "gespeeld" vs "nog te spelen" onderscheiden.

Nog te verifiëren in de praktijk (kon ik niet zelf testen):
- Het exacte uiterlijk van de Status-kolom bij een nog niet gespeelde match.
- Of `poolTableId` in de URL effectief filtert, of dat altijd de hele
  afdeling (alle poules) wordt teruggegeven zoals in mijn testvoorbeeld.
"""

import re
import time
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.tennisenpadelvlaanderen.be"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"


def _param_from_url(href: Optional[str], param: str) -> Optional[str]:
    if not href:
        return None
    parsed = parse_qs(urlparse(href).query)
    vals = parsed.get(param)
    return vals[0] if vals else None


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def fetch_poule_schedule_html(url: str, session: Optional[requests.Session] = None, delay: float = 1.0) -> str:
    """Fetch the raw HTML of a 'zoek-een-competitie-organisatie' poule page."""
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    if delay > 0:
        time.sleep(delay)
    full_url = url if url.startswith("http") else BASE_URL + url
    resp = session.get(full_url, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_poule_schedule(html: str) -> list[dict]:
    """
    Parse every poule table on the page into a flat list of fixtures:
    {poule_label, date_text, home_name, home_ploeg_id, away_name,
     away_ploeg_id, score, spelgroep_id, match_id, played}

    Robuust opgezet (zoals de bestaande scrape_uitslagenblad-functie): we
    zoeken op linkpatronen (ploegId=, matchId=) en tekstpatronen in de rij,
    in plaats van te steunen op een vaste kolomvolgorde — die kon ik niet
    rechtstreeks verifiëren in de ruwe HTML (mijn fetch-tool toont enkel een
    al omgezette/leesbare versie van de pagina).
    """
    soup = BeautifulSoup(html, "html.parser")
    fixtures = []

    for table in soup.find_all("table"):
        poule_label = _find_preceding_label(table)

        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            row_text = _clean(row.get_text())
            all_links = row.find_all("a")

            ploeg_links = [a for a in all_links if _param_from_url(a.get("href"), "ploegId")]
            if len(ploeg_links) < 2:
                continue  # geen herkenbare thuis/weg-ploeg-rij (bv. header-rij)

            home_link, away_link = ploeg_links[0], ploeg_links[1]
            home_name = _clean(home_link.get_text())
            away_name = _clean(away_link.get_text())
            home_ploeg_id = _param_from_url(home_link.get("href"), "ploegId")
            away_ploeg_id = _param_from_url(away_link.get("href"), "ploegId")
            spelgroep_id = (
                _param_from_url(home_link.get("href"), "spelgroepId")
                or _param_from_url(away_link.get("href"), "spelgroepId")
            )

            match_link = next((a for a in all_links if _param_from_url(a.get("href"), "matchId")), None)
            match_id = _param_from_url(match_link.get("href"), "matchId") if match_link else None
            uitslagenblad_url = match_link.get("href") if match_link else None
            played = bool(match_id)

            date_text = ""
            m_date = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}(\s+\d{1,2}:\d{2})?\b", row_text)
            if m_date:
                date_text = m_date.group(0)

            score = None
            if played:
                # tekst die overblijft na het weghalen van datum + ploegnamen geeft de beste kans op de score
                remainder = row_text.replace(home_name, "").replace(away_name, "")
                if date_text:
                    remainder = remainder.replace(date_text, "")
                score_candidates = re.findall(r"\d+[-/]\d+(?:\s*/\s*\d+[-/]\d+)*", remainder)
                score = score_candidates[0] if score_candidates else None

            fixtures.append({
                "poule_label": poule_label,
                "date_text": date_text,
                "home_name": home_name,
                "home_ploeg_id": home_ploeg_id,
                "away_name": away_name,
                "away_ploeg_id": away_ploeg_id,
                "score": score,
                "spelgroep_id": spelgroep_id,
                "match_id": match_id,
                "uitslagenblad_url": uitslagenblad_url,
                "played": played,
            })

    return fixtures


def _find_preceding_label(table) -> str:
    """Zoekt het dichtstbijzijnde voorafgaande tekstelement dat op 'Poule X' lijkt."""
    el = table
    for _ in range(8):
        el = el.find_previous(["h1", "h2", "h3", "h4", "h5", "strong", "div", "p"])
        if el is None:
            break
        text = _clean(el.get_text())
        if 0 < len(text) <= 40 and re.search(r"poule|eindronde|klassement", text, re.I):
            return text
    return "Poule ?"


_MONTHS_NL = {
    "jan": 1, "feb": 2, "mrt": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}


def _parse_date_text(date_text: str):
    """'za 21/03/2026 14:00' -> (2026, 3, 21) ; returns None if unparsable."""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_text or "")
    if not m:
        return None
    d, mo, y = m.groups()
    return (int(y), int(mo), int(d))


def identify_own_ploeg_id(fixtures: list[dict], own_known_matches: list[dict]) -> Optional[str]:
    """
    Bepaalt welke ploegId 'wij' zijn door elke gespeelde fixture te vergelijken
    met de matches die we al kennen van onszelf (datum + score-patroon).
    own_known_matches: lijst van match-dicts uit jouw eigen Firestore-doc
    (match_type == 'interclub'), met velden 'match_date' en 'score'.
    """
    own_signatures = set()
    for m in own_known_matches:
        if m.get("match_type") != "interclub":
            continue
        d = _parse_date_text(m.get("match_date") or "")
        if d and m.get("score"):
            own_signatures.add((d, _clean(m["score"])[:6]))  # eerste stukje score als losse match

    for f in fixtures:
        if not f["played"]:
            continue
        d = _parse_date_text(f["date_text"])
        if not d or not f.get("score"):
            continue
        score_prefix = _clean(f["score"])[:6]
        if (d, score_prefix) in own_signatures:
            # gevonden — maar we weten nog niet of WIJ thuis of weg speelden;
            # geef beide ploegIds terug zodat de caller verder kan filteren
            return f["home_ploeg_id"], f["away_ploeg_id"], f
    return None, None, None


def get_team_fixtures(fixtures: list[dict], ploeg_id: str) -> list[dict]:
    """Alle fixtures (gespeeld + nog te spelen) waarin deze ploegId voorkomt, op datum gesorteerd."""
    own = [f for f in fixtures if f["home_ploeg_id"] == ploeg_id or f["away_ploeg_id"] == ploeg_id]
    own.sort(key=lambda f: _parse_date_text(f["date_text"]) or (9999, 99, 99))
    return own


def get_next_match(team_fixtures: list[dict]) -> Optional[dict]:
    """Eerste niet-gespeelde fixture in de (al gesorteerde) lijst."""
    for f in team_fixtures:
        if not f["played"]:
            return f
    return None


def opponent_of(fixture: dict, own_ploeg_id: str) -> dict:
    """Geeft {name, ploeg_id} van de tegenstander in deze fixture."""
    if fixture["home_ploeg_id"] == own_ploeg_id:
        return {"name": fixture["away_name"], "ploeg_id": fixture["away_ploeg_id"]}
    return {"name": fixture["home_name"], "ploeg_id": fixture["home_ploeg_id"]}
