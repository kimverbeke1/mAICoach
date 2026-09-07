"""
schedule_scraper.py — haalt het poule/tabel-schema op en parseert de fixtures.

Oorspronkelijk gebouwd voor de publieke 'zoek-een-competitie-organisatie'-
pagina, maar de parser (parse_poule_schedule) werkt op de RUWE/gerenderde HTML
en wordt nu ook gevoed door poule_playwright.py, dat de clubdashboard-SPA
(/nl/clubdashboard/interclub-poule-tabel?...) via Playwright rendert.

De pagina toont per rij thuis-/bezoekende ploeg (naam + unieke ploegId), datum,
score en een uitslagenblad-link (matchId).

PADEL_ANALYSIS_PLAYED_BY_SCORE_FIX_2026-09-07 (CRUCIAAL voor "Volgende match"):
BUG (opgelost): 'played' werd bepaald als bool(match_id). Op de publieke pagina
klopte dat (nog te spelen matchen hadden geen matchId), MAAR op de
clubdashboard-poule-tabel heeft ELKE rij — ook nog te spelen matchen — een
matchId/uitslagenblad-link. Daardoor werd elke fixture als 'gespeeld'
gemarkeerd en vond get_next_match() NOOIT een volgende match.
Fix: bepaal 'played' op basis van de SCORE. Een rij met een ingevulde
ontmoetingsscore is gespeeld; een rij met lege score is nog te spelen. Dit
klopt voor beide paginatypes (publiek én clubdashboard).
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
    """Fetch the raw HTML of a poule page (publieke variant, requests-only)."""
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
     away_ploeg_id, score, spelgroep_id, match_id, uitslagenblad_url, played}
    Robuust: we zoeken op linkpatronen (ploegId=, matchId=) en tekstpatronen in
    de rij, in plaats van te steunen op een vaste kolomvolgorde.
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
            date_text = ""
            m_date = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}(\s+\d{1,2}:\d{2})?\b", row_text)
            if m_date:
                date_text = m_date.group(0)
            # PADEL_ANALYSIS_PLAYED_BY_SCORE_FIX_2026-09-07: bepaal de score
            # ALTIJD (niet enkel 'if played'), en leid 'played' vervolgens af
            # uit de aanwezigheid van een score. Zo werkt de detectie zowel op
            # de publieke pagina (nog te spelen = geen matchId én geen score)
            # als op de clubdashboard-poule-tabel (nog te spelen = wél matchId,
            # maar GEEN score).
            remainder = row_text.replace(home_name, "").replace(away_name, "")
            if date_text:
                remainder = remainder.replace(date_text, "")
            score_candidates = re.findall(r"\d+[-/]\d+(?:\s*/\s*\d+[-/]\d+)*", remainder)
            score = score_candidates[0] if score_candidates else None
            played = bool(score)
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
        if 0 < len(text) <= 40 and re.search(r"poule|eindronde|klassement|finale|ronde", text, re.I):
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
def identify_own_ploeg_id(fixtures: list[dict], own_known_matches: list[dict]):
    """
    Bepaalt welke ploegId 'wij' zijn door de poule-fixtures te matchen met de
    interclubmatchen die we al van onszelf kennen, op DATUM (onze ploeg speelt
    op een gegeven interclubdatum precies één ontmoeting).
    Returns: (home_ploeg_id, away_ploeg_id, fixture) of (None, None, None).
    """
    own_dates = set()
    for m in own_known_matches:
        if m.get("match_type") != "interclub":
            continue
        d = _parse_date_text(m.get("match_date") or "")
        if d:
            own_dates.add(d)
    if not own_dates:
        return None, None, None
    candidates = []
    for f in fixtures:
        # Enkel al gespeelde fixtures kunnen matchen met een reeds gekende
        # (gescrapete) eigen match; die hebben immers een score.
        if not f.get("played"):
            continue
        d = _parse_date_text(f["date_text"])
        if d and d in own_dates:
            candidates.append((d, f))
    if not candidates:
        return None, None, None
    # Bij meerdere kandidaten: neem de meest recente gespeelde ontmoeting.
    candidates.sort(key=lambda t: t[0], reverse=True)
    f = candidates[0][1]
    return f["home_ploeg_id"], f["away_ploeg_id"], f
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
