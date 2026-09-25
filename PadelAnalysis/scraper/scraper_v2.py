"""
scraper_v2.py - HTTP-based scraper voor tennisenpadelvlaanderen.be
Geen Playwright. Directe requests + BeautifulSoup op basis van echte HTML structuur.

Data model per match:
  Tornooi:
    player_id, period_label, match_type="tornooi"
    tournament_name, tournament_date_start, tournament_date_end, tournament_week
    reeks_name, reeks_url, reeks_id, tornooi_id
    partner_name, partner_user_id
    opp1_name, opp1_user_id, opp1_ranking
    opp2_name, opp2_user_id, opp2_ranking
    round_text, result ("W"/"V"), won (bool), score
    scraped_at

  Interclub:
    player_id, period_label, match_type="interclub"
    competition_name, match_date
    reeks_name, encounter
    uitslagenblad_url, spelgroep_id, match_id
    partner_name, partner_user_id
    opp1_name, opp1_user_id, opp1_ranking
    opp2_name, opp2_user_id, opp2_ranking
    round_text, result ("W"/"V"), won (bool), score
    scraped_at
"""
import re
import time
import logging
import datetime as _dt
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisenpadelvlaanderen.be"
DASHBOARD_URL = BASE_URL + "/dashboard/resultaten"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-BE,nl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Padel tab parameters (uit de URL van het dashboard)
# LET OP: 'ppid' bleek in de praktijk NIET gegarandeerd hetzelfde als wat een
# echte browsersessie (Playwright) gebruikt -- zie find_current_period_by_date
# hieronder voor de volledige toelichting. Deze params volstaan wel om de
# pagina succesvol op te vragen; enkel het "welke periode is standaard
# geselecteerd"-gedrag kan hierdoor afwijken, vandaar de datum-gebaseerde
# periode-detectie i.p.v. vertrouwen op het HTML 'selected'-attribuut.
DEFAULT_PADEL_PARAMS = {
    "tab": "padel",
    "tspid": "80",
    "tdpid": "80",
    "ppid": "79",
    "tscid": "80",
    "pcid": "79",
}

# ---------------------------------------------------------------------------
# Versiestempel - PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25
# ---------------------------------------------------------------------------
# Kim's eigen verzoek ("Ik heb dat nu al een paar keer gevraagd en zie niets
# veranderen [...] als extra test wil ik zeker de naam van de kolom
# veranderen zodat ik daarmee ook extra kan zien of de code effectief goed
# gecommit wordt"): een expliciete, grep-bare versiestring bovenaan het
# bestand, zodat een deployment altijd te verifieren is met
#     Select-String -Path scraper_v2.py -Pattern "UITSLAG_FIELD_FIX"
# zonder de site zelf te moeten raadplegen.
SCRAPER_V2_VERSION = "2026-09-25-uitslag-field-fix"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text) -> str:
    return " ".join((text or "").split()).strip()


def _clean_lower(text) -> str:
    return _clean(text).lower()


def _user_id_from_url(href: Optional[str]) -> Optional[str]:
    """Extract userId from /dashboard?userId=XXXX"""
    if not href:
        return None
    m = re.search(r"[?&]userId=(\d+)", href)
    return m.group(1) if m else None


def _param_from_url(href: Optional[str], param: str) -> Optional[str]:
    if not href:
        return None
    parsed = parse_qs(urlparse(href).query)
    vals = parsed.get(param)
    return vals[0] if vals else None


def _parse_player_link(a_tag: Tag) -> tuple[Optional[str], Optional[str]]:
    """Returns (name, user_id) from an <a> tag."""
    if a_tag is None:
        return None, None
    return _clean(a_tag.get_text()) or None, _user_id_from_url(a_tag.get("href"))


def _get_html(session: requests.Session, url: str, params: dict = None, delay: float = 1.0) -> str:
    if delay > 0:
        time.sleep(delay)
    resp = session.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Period date-range parsing
# ---------------------------------------------------------------------------
_PERIOD_WEEK_RANGE_RE = re.compile(
    r"week\s+(\d{1,2})[/\s](\d{4})\s+tot\s+en\s+met\s+week\s+(\d{1,2})[/\s](\d{4})",
    re.IGNORECASE,
)


def _iso_week_to_date(year: int, week: int, weekday: int = 1) -> Optional[_dt.date]:
    """weekday: 1 = maandag, 7 = zondag (ISO)."""
    try:
        return _dt.date.fromisocalendar(year, week, weekday)
    except Exception:
        return None


def parse_period_date_range(label: str) -> Optional[tuple[_dt.date, _dt.date]]:
    """
    Parseert 'Resultaten van week W1/Y1 tot en met week W2/Y2' naar
    (start_date, end_date) als datetime.date objecten.
    """
    if not label:
        return None
    m = _PERIOD_WEEK_RANGE_RE.search(label)
    if not m:
        return None
    w1, y1, w2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    start = _iso_week_to_date(y1, w1, 1)
    end = _iso_week_to_date(y2, w2, 7)
    if start and end:
        return start, end
    return None


def find_current_period_by_date(all_periods: list[dict], today: Optional[_dt.date] = None) -> Optional[dict]:
    """
    Bepaalt de werkelijk actieve periode via echte datumvergelijking met
    vandaag. Volledig onafhankelijk van website-sessie/portlet-
    eigenaardigheden (ppid e.d.) of het HTML 'selected'-attribuut, die beide
    bleken af te wijken van wat een echte browsersessie standaard toont.
    """
    today = today or _dt.date.today()
    parsed = []
    for p in all_periods:
        rng = parse_period_date_range(p.get("label", ""))
        if rng:
            parsed.append((p, rng[0], rng[1]))
    if not parsed:
        return None
    containing = [p for p, start, end in parsed if start <= today <= end]
    if containing:
        return containing[0]
    past_or_present = [(p, start) for p, start, end in parsed if start <= today]
    if past_or_present:
        return max(past_or_present, key=lambda x: x[1])[0]
    return min(parsed, key=lambda x: x[1])[0]


# ---------------------------------------------------------------------------
# Period discovery
# ---------------------------------------------------------------------------
def get_padel_periods(session: requests.Session, player_id: str) -> list[dict]:
    """
    Fetch the dashboard and return all available padel periods.
    Returns list of {'label': str, 'value': str, 'select_name': str, 'selected': bool}.
    """
    params = {"userId": player_id, **DEFAULT_PADEL_PARAMS}
    html = _get_html(session, DASHBOARD_URL, params=params)
    soup = BeautifulSoup(html, "html.parser")

    selects_with_periods = []
    for sel in soup.find_all("select"):
        opts = sel.find_all("option")
        period_opts = [
            {
                "label": _clean(o.get_text()),
                "value": o.get("value", ""),
                "selected": o.has_attr("selected"),
            }
            for o in opts
            if "resultaten van week" in _clean(o.get_text()).lower()
        ]
        if period_opts:
            selects_with_periods.append({
                "select_name": sel.get("name", ""),
                "periods": period_opts,
            })

    if len(selects_with_periods) >= 3:
        padel_select = selects_with_periods[2]
    elif selects_with_periods:
        padel_select = selects_with_periods[0]
    else:
        return []

    return [
        {**p, "select_name": padel_select["select_name"]}
        for p in padel_select["periods"]
    ]


# ---------------------------------------------------------------------------
# Period page fetcher
# ---------------------------------------------------------------------------
def fetch_period_html(
    session: requests.Session,
    player_id: str,
    period: dict,
) -> str:
    """Fetch the dashboard HTML for a specific period."""
    params = {"userId": player_id, **DEFAULT_PADEL_PARAMS}
    html = _get_html(session, DASHBOARD_URL, params=params, delay=0.5)
    soup = BeautifulSoup(html, "html.parser")

    select_name = period.get("select_name", "")
    period_value = period.get("value", "")

    padel_select = soup.find("select", {"name": select_name}) if select_name else None
    padel_form = padel_select.find_parent("form") if padel_select else None

    if padel_form:
        form_action = padel_form.get("action", DASHBOARD_URL)
        if not form_action.startswith("http"):
            form_action = BASE_URL + form_action

        form_data = {}
        for inp in padel_form.find_all("input", {"type": "hidden"}):
            name = inp.get("name", "")
            value = inp.get("value", "")
            if name:
                form_data[name] = value
        if select_name:
            form_data[select_name] = period_value
        form_data["userId"] = player_id

        time.sleep(1.5)
        resp = session.post(form_action, data=form_data, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text
    else:
        if select_name:
            params[select_name] = period_value
        return _get_html(session, DASHBOARD_URL, params=params, delay=1.5)


# ---------------------------------------------------------------------------
# Tournament parser
# ---------------------------------------------------------------------------
#
# PADEL_ANALYSIS_CONTENT_BASED_SPORT_FILTER_FIX
# BUG (opgelost): de vorige aanpak identificeerde de padel-sectie via
# POSITIE ("de 3de 'Uitslagen Tornooien'/'Uitslagen Interclub' h3 op de
# pagina", ervan uitgaande dat elke speler exact 4 vaste secties heeft:
# tennis enkel, tennis dubbel, padel, pickleball, in die vaste volgorde).
# Deze aanname bleek NIET betrouwbaar: als een speler niet aan een of
# meerdere van die andere sporten deelneemt, ontbreken hun secties op de
# pagina en verschuift de POSITIE van de padel-sectie -- waardoor de
# verkeerde sectie (of zelfs geen enkele) geselecteerd werd.
#
# Nieuwe aanpak: parseer ALLE secties op de volledige pagina (ongeacht
# positie/telling van hoeveel sport-secties er zijn), en filter het
# resultaat achteraf op INHOUD: enkel matches behouden waarvan reeks_name
# (of tournament_name/competition_name) het woord 'padel' bevat
# (case-insensitive).
def parse_tournament_section(soup: BeautifulSoup, player_id: str, period_label: str) -> list[dict]:
    """
    Parse ALLE tornooiresultaten-secties op de pagina, en filter nadien op
    padel (zie uitleg hierboven). Geen aanname meer over "welke positie is
    de padel-sectie".
    """
    matches = []
    for div in soup.find_all("div", class_="tournament-organization"):
        matches.extend(_parse_tournament_org_div(div, player_id, period_label))
    return [
        m for m in matches
        if "padel" in _clean_lower(m.get("reeks_name")) or "padel" in _clean_lower(m.get("tournament_name"))
    ]


def _parse_tournament_org_div(org_div: Tag, player_id: str, period_label: str) -> list[dict]:
    """Parse one div.tournament-organization into a list of match dicts."""
    matches = []
    for details_div in org_div.find_all("div", class_="details"):
        header = details_div.find("h4", class_="details-box-title")
        if not header:
            continue
        header_text = _clean(header.get_text())
        hm = re.match(r"^(.+?)\s+-\s+(\d{2}/\d{2}/\d{4})\s+-\s+(\d{2}/\d{2}/\d{4})$", header_text)
        if hm:
            tournament_name = _clean(hm.group(1))
            date_start = hm.group(2)
            date_end = hm.group(3)
        else:
            tournament_name = header_text
            date_start = date_end = None

        content = details_div.find("div", class_="details-content")
        if not content:
            continue

        reeks_name = reeks_url = reeks_id = tornooi_id = None
        partner_name = partner_uid = None
        tournament_week = None
        for row in content.find_all("div", class_="row-fluid"):
            label_spans = row.find_all("span", class_='list-label')
            for label_span in label_spans:
                value_span = label_span.find_next_sibling("span", class_='list-value')
                if not value_span:
                    continue
                label = _clean(label_span.get_text()).rstrip(":")
                a = value_span.find("a")
                if label.lower() == "reeks":
                    if a:
                        reeks_name = _clean(a.get_text())
                        reeks_url = a.get("href", "")
                        reeks_id = _param_from_url(reeks_url, "reeksId")
                        tornooi_id = _param_from_url(reeks_url, "tornooiId")
                elif label.lower() == "partner":
                    if a:
                        partner_name = _clean(a.get_text())
                        partner_uid = _user_id_from_url(a.get("href"))
                elif label.lower() == "week":
                    tournament_week = _clean(value_span.get_text())
                tournament_week = _clean(value_span.get_text())

        table = content.find("table")
        if not table:
            continue
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            opp_links = cols[0].find_all("a")
            opp1_name, opp1_uid = _parse_player_link(opp_links[0]) if len(opp_links) > 0 else (None, None)
            opp2_name, opp2_uid = _parse_player_link(opp_links[1]) if len(opp_links) > 1 else (None, None)
            ranking_parts = re.findall(r"P\d+", _clean(cols[1].get_text()))
            opp1_ranking = ranking_parts[0] if len(ranking_parts) > 0 else None
            opp2_ranking = ranking_parts[1] if len(ranking_parts) > 1 else None
            round_text = _clean(cols[2].get_text()) if len(cols) > 2 else None
            result_letter = _clean(cols[3].get_text()) if len(cols) > 3 else None
            score = _clean(cols[4].get_text()) if len(cols) > 4 else None
            matches.append({
                "player_id": player_id,
                "period_label": period_label,
                "match_type": "tornooi",
                "tournament_name": tournament_name,
                "tournament_date_start": date_start,
                "tournament_date_end": date_end,
                "tournament_week": tournament_week,
                "reeks_name": reeks_name,
                "reeks_url": reeks_url,
                "reeks_id": reeks_id,
                "tornooi_id": tornooi_id,
                "partner_name": partner_name,
                "partner_user_id": partner_uid,
                "opp1_name": opp1_name,
                "opp1_user_id": opp1_uid,
                "opp2_name": opp2_name,
                "opp2_user_id": opp2_uid,
                "opp1_ranking": opp1_ranking,
                "opp2_ranking": opp2_ranking,
                "round_text": round_text,
                "result": result_letter,
                "won": (result_letter == "W") if result_letter in ("W", "V") else None,
                "score": score,
                "scraped_at": _utc_now(),
            })
    return matches


# ---------------------------------------------------------------------------
# Interclub parser
# ---------------------------------------------------------------------------
def parse_interclub_section(soup: BeautifulSoup, player_id: str, period_label: str) -> list[dict]:
    """
    Parse ALLE interclub-secties op de pagina (elke 'Uitslagen Interclub' h3
    en zijn bijhorende 'details'-divs), en filter nadien op padel. Zie
    uitgebreide toelichting bij parse_tournament_section() hierboven.
    """
    matches = []
    h3s_interclub = [h for h in soup.find_all("h3") if "uitslagen interclub" in _clean(h.get_text()).lower()]
    for target_h3 in h3s_interclub:
        sibling = target_h3.find_next_sibling()
        while sibling:
            if sibling.name in ("h3", "h2"):
                break
            if sibling.name == "div" and "details" in (sibling.get("class") or []):
                matches.extend(_parse_interclub_details_div(sibling, player_id, period_label))
            sibling = sibling.find_next_sibling()
    return [
        m for m in matches
        if "padel" in _clean_lower(m.get("reeks_name")) or "padel" in _clean_lower(m.get("competition_name"))
    ]


def _parse_interclub_details_div(details_div: Tag, player_id: str, period_label: str) -> list[dict]:
    """Parse one div.details interclub block."""
    matches = []
    header = details_div.find("h4", class_="details-box-title")
    if not header:
        return matches
    header_text = _clean(header.get_text())
    hm = re.match(r"^(.+?)\s+-\s+(\d{2}/\d{2}/\d{4})$", header_text)
    if hm:
        competition_name = _clean(hm.group(1))
        match_date = hm.group(2)
    else:
        competition_name = header_text
        match_date = None

    content = details_div.find("div", class_="details-content")
    if not content:
        return matches

    reeks_name = encounter = None
    uitslagenblad_url = spelgroep_id = match_id = None
    for row in content.find_all("div", class_="row-fluid"):
        for label_span in row.find_all("span", class_="list-label"):
            value_span = label_span.find_next_sibling("span", class_="list-value")
            if not value_span:
                continue
            label = _clean(label_span.get_text()).rstrip(":")
            if label.lower() == "reeks":
                reeks_name = _clean(value_span.get_text())
            elif label.lower() == "ontmoeting":
                encounter = _clean(value_span.get_text())
        uitslagen_a = row.find("a", href=re.compile(r"interclub-uitslagenblad"))
        if uitslagen_a:
            uitslagenblad_url = uitslagen_a.get("href", "")
            spelgroep_id = _param_from_url(uitslagenblad_url, "spelgroepId")
            match_id = _param_from_url(uitslagenblad_url, "matchId")

    table = content.find("table")
    if not table:
        return matches
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        partner_links = cols[0].find_all("a")
        partner_name, partner_uid = _parse_player_link(partner_links[0]) if partner_links else (None, None)
        opp_links = cols[1].find_all("a")
        opp1_name, opp1_uid = _parse_player_link(opp_links[0]) if len(opp_links) > 0 else (None, None)
        opp2_name, opp2_uid = _parse_player_link(opp_links[1]) if len(opp_links) > 1 else (None, None)
        ranking_parts = re.findall(r"P\d+", _clean(cols[2].get_text()))
        opp1_ranking = ranking_parts[0] if len(ranking_parts) > 0 else None
        opp2_ranking = ranking_parts[1] if len(ranking_parts) > 1 else None
        round_text = _clean(cols[3].get_text()) if len(cols) > 3 else None
        result_letter = _clean(cols[4].get_text()) if len(cols) > 4 else None
        score = _clean(cols[5].get_text()) if len(cols) > 5 else None
        matches.append({
            "player_id": player_id,
            "period_label": period_label,
            "match_type": "interclub",
            "competition_name": competition_name,
            "match_date": match_date,
            "reeks_name": reeks_name,
            "encounter": encounter,
            "uitslagenblad_url": uitslagenblad_url,
            "spelgroep_id": spelgroep_id,
            "match_id": match_id,
            "partner_name": partner_name,
            "partner_user_id": partner_uid,
            "opp1_name": opp1_name,
            "opp1_user_id": opp1_uid,
            "opp2_name": opp2_name,
            "opp2_user_id": opp2_uid,
            "opp1_ranking": opp1_ranking,
            "opp2_ranking": opp2_ranking,
            "round_text": round_text,
            "result": result_letter,
            "won": (result_letter == "W") if result_letter in ("W", "V") else None,
            "score": score,
            "scraped_at": _utc_now(),
        })
    return matches


# ---------------------------------------------------------------------------
# Uitslagenblad scraper
# ---------------------------------------------------------------------------
def _col_by_data_title(cols: list, title: str):
    """Zoekt de <td> in `cols` met het opgegeven data-title-attribuut.
    Betrouwbaarder dan positionele kolomindexen: de site markeert elke
    kolom expliciet met data-title (bv. data-title="Uitslag"), en dat
    attribuut verandert niet als de kolomvolgorde ooit zou wijzigen."""
    return next((c for c in cols if c.get("data-title") == title), None)


def _parse_pair_score(text: str) -> Optional[tuple]:
    """Ontleedt een 'X-Y'-tekst (bv. '1-3', '0-1') tot (int, int).
    Geeft None terug als de tekst niet exact dat formaat heeft - GEEN gok."""
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", str(text or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def scrape_uitslagenblad(session: requests.Session, url: str, delay: float = 1.5) -> dict:
    """
    Scrapet 1 interclub-uitslagenblad: de teamsamenvatting (ploegnamen,
    ploeg-ID's, winnaar, eindscore in matchen/sets/spellen) en het detail
    per bord (dubbel).

    PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25 (op verzoek van Kim, na
    grondige analyse van de ECHTE HTML-structuur van een uitslagenblad -
    geen aanname meer, rechtstreeks bevestigd)
    --------------------------------------------------------------------
    ROOT CAUSE (bevestigd, niet langer een vermoeden): de vorige versie
    zocht per bord naar een LOSSE LETTER "W" of "V" in de kolomtekst:

        result_letter = next((t for t in reversed(col_texts) if t in ("W", "V")), None)

    Die letters bestaan NERGENS op een interclub-uitslagenblad. De echte
    kolom heet "Uitslag" (herkenbaar aan data-title="Uitslag") en bevat een
    numeriek paar "0-1" of "1-0" - thuis-uit, PER BORD. Dat paar werd nooit
    gevonden door de oude code, dus "won" bleef ALTIJD None. Dat is de
    volledige verklaring voor de aanhoudende "Resultaat: Onbekend"-melding
    in de UI, ook nadat de rest van de keten (opponent_scout.py,
    page_lineup_lab.py) al correct was opgebouwd rond een "opponent_won"-
    veld: dat veld kreeg simpelweg nooit bruikbare invoer.

    Bevestigde structuur van elke bord-rij (uit een echt uitslagenblad,
    2 onafhankelijke rijen gecontroleerd tegen de vetgedrukte winnaar-
    aanduiding <b class="bold"> die de site zelf ook toont):
        data-title="Uitslag"            "0-1"                thuis-uit: WIE won dit bord
        data-title="Score v/d winnaar"  "6/3 - 6/7 (3) - 10/2"  setcijfers, ALTIJD winnaar-eerst
        data-title="Sets"                "1-2"               sets thuis-uit, dit bord
        data-title="Spellen"             "16-19"              spellen (games) thuis-uit, dit bord

    En de "Samenvatting"-sectie bovenaan de pagina (buiten de bord-tabel):
        Ontvangende ploeg: <a href="...ploegId=334297">... A</a>
        Bezoekende ploeg:  <a href="...ploegId=337680">... D</a> (winnaar)
        Uitslag:  1-3     <- gewonnen MATCHEN/borden, thuis-uit
        Sets:     3-7
        Spellen:  40-56

    FIX: leest nu BEIDE niveaus expliciet via het data-title-attribuut
    i.p.v. positionele tekstvergelijking, en geeft het team-niveau (voor de
    eindscore/winnaar van de VOLLEDIGE ontmoeting) apart en ondubbelzinnig
    terug naast het bestaande bord-niveau.

    Nieuw, additief (bestaande sleutels "players"/"rankings"/"round_text"/
    "result"/"won"/"score" blijven ongewijzigd - geen breaking change voor
    bestaande aanroepers):
      - per bord: "sets", "games" (elk (thuis, uit) of None)
      - op het resultaat zelf: "home_ploeg_id", "away_ploeg_id",
        "winner_team", "winner_ploeg_id", "team_score_matches",
        "team_score_sets", "team_score_games"
    """
    full_url = BASE_URL + url if url.startswith("/") else url
    html = _get_html(session, full_url, delay=delay)
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "url": full_url,
        "scraped_at": _utc_now(),
        "home_team": None,
        "away_team": None,
        "home_ploeg_id": None,
        "away_ploeg_id": None,
        "winner_team": None,
        "winner_ploeg_id": None,
        # Team-niveau eindscore van de VOLLEDIGE ontmoeting (thuis, uit),
        # rechtstreeks uit de "Samenvatting"-sectie - GEEN afleiding uit de
        # bordresultaten.
        "team_score_matches": None,
        "team_score_sets": None,
        "team_score_games": None,
        "matches": [],
    }

    # ---------- Teamnamen: fallback via <h1>/<h2>/<h3> met "thuis / uit" ----------
    for tag in ["h1", "h2", "h3"]:
        h = soup.find(tag)
        if h:
            text = _clean(h.get_text())
            if "/" in text:
                parts = text.split("/", 1)
                result["home_team"] = _clean(parts[0])
                result["away_team"] = _clean(parts[1])
                break

    # ---------- Samenvatting-sectie: ploegnamen, ploeg-ID's, winnaar, eindscore ----------
    for row in soup.find_all("div", class_="row-fluid"):
        for label_span in row.find_all("span", class_="list-label"):
            value_span = label_span.find_next_sibling("span", class_="list-value")
            if not value_span:
                continue
            label = _clean(label_span.get_text()).rstrip(":").lower()
            value_text = _clean(value_span.get_text())
            a = value_span.find("a")

            if label == "ontvangende ploeg":
                if a:
                    result["home_team"] = _clean(a.get_text())
                    result["home_ploeg_id"] = _param_from_url(a.get("href"), "ploegId")
                if "(winnaar)" in value_text.lower():
                    result["winner_team"] = result["home_team"]
                    result["winner_ploeg_id"] = result["home_ploeg_id"]
            elif label == "bezoekende ploeg":
                if a:
                    result["away_team"] = _clean(a.get_text())
                    result["away_ploeg_id"] = _param_from_url(a.get("href"), "ploegId")
                if "(winnaar)" in value_text.lower():
                    result["winner_team"] = result["away_team"]
                    result["winner_ploeg_id"] = result["away_ploeg_id"]
            elif label == "uitslag":
                result["team_score_matches"] = _parse_pair_score(value_text)
            elif label == "sets":
                result["team_score_sets"] = _parse_pair_score(value_text)
            elif label == "spellen":
                result["team_score_games"] = _parse_pair_score(value_text)

    # ---------- Per bord (dubbel) ----------
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cols = tr.find_all("td")
            if len(cols) < 4:
                continue
            all_links = [a for a in tr.find_all("a") if _user_id_from_url(a.get("href"))]
            if len(all_links) < 2:
                continue
            players = [
                {"name": _clean(a.get_text()), "user_id": _user_id_from_url(a.get("href"))}
                for a in all_links
            ]
            rankings = re.findall(r"P\d+", _clean(tr.get_text()))

            uitslag_cel = _col_by_data_title(cols, "Uitslag")
            uitslag_tekst = _clean(uitslag_cel.get_text()) if uitslag_cel is not None else ""
            uitslag_pair = _parse_pair_score(uitslag_tekst)
            # True = de kant die in deze rij als EERSTE (thuis-kolom, dus
            # players[0:2]) vermeld staat, won dit bord. None als het
            # "Uitslag"-veld niet gevonden of niet leesbaar was - bewust
            # GEEN gok, liever expliciet onbekend dan een verzonnen waarde.
            home_won_this_board = (uitslag_pair[0] == 1) if uitslag_pair else None

            score_cel = _col_by_data_title(cols, "Score v/d winnaar")
            score = _clean(score_cel.get_text()) if score_cel is not None else None

            sets_cel = _col_by_data_title(cols, "Sets")
            board_sets = _parse_pair_score(_clean(sets_cel.get_text())) if sets_cel is not None else None

            spellen_cel = _col_by_data_title(cols, "Spellen")
            board_games = _parse_pair_score(_clean(spellen_cel.get_text())) if spellen_cel is not None else None

            result["matches"].append({
                "players": players,
                "rankings": rankings,
                "round_text": None,
                # "won": True betekent "de eerste 2 spelers in deze rij
                # (players[0:2], de THUIS-kolom op het uitslagenblad) wonnen
                # dit bord". Dit is consistent met hoe
                # opponent_scout.extract_opponent_lineup() players[0:2]
                # behandelt als de thuiskolom.
                "won": home_won_this_board,
                "score": score,
                "sets": board_sets,
                "games": board_games,
            })
    return result


# ---------------------------------------------------------------------------
# Main scrape function
# ---------------------------------------------------------------------------
def scrape_player(
    player_id: str,
    periods_to_scrape: Optional[list[str]] = None,
    scrape_uitslagenbladeren: bool = False,
    delay_between_periods: float = 2.0,
) -> dict:
    session = requests.Session()
    logger.info(f"Scraping speler {player_id}...")

    all_periods = get_padel_periods(session, player_id)
    logger.info(f"  {len(all_periods)} periodes gevonden")
    if not all_periods:
        return {"player_id": player_id, "error": "Geen periodes gevonden", "scraped_at": _utc_now()}

    target_periods = (
        [p for p in all_periods if p["label"] in periods_to_scrape]
        if periods_to_scrape is not None
        else all_periods
    )

    all_matches = []
    scraped_labels = []
    empty_labels = []
    failed_periods = []

    for i, period in enumerate(target_periods):
        label = period["label"]
        logger.info(f"  [{i+1}/{len(target_periods)}] {label}")
        try:
            if i == 0:
                params = {"userId": player_id, **DEFAULT_PADEL_PARAMS}
                html = _get_html(session, DASHBOARD_URL, params=params, delay=0)
            else:
                html = fetch_period_html(session, player_id, period)

            soup = BeautifulSoup(html, "html.parser")
            t_matches = parse_tournament_section(soup, player_id, label)
            i_matches = parse_interclub_section(soup, player_id, label)
            period_matches = t_matches + i_matches

            if period_matches:
                all_matches.extend(period_matches)
                logger.info(f"    → {len(t_matches)} tornooi + {len(i_matches)} interclub")
            else:
                empty_labels.append(label)
                logger.info(f"    → leeg")

            scraped_labels.append(label)
        except Exception as e:
            logger.error(f"    → FOUT: {e}")
            failed_periods.append({"label": label, "error": str(e)})

        if i < len(target_periods) - 1:
            time.sleep(delay_between_periods)

    uitslagenblad_results = {}
    if scrape_uitslagenbladeren:
        seen_urls = set()
        for m in all_matches:
            url = m.get("uitslagenblad_url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                key = f"{m.get('spelgroep_id','')}_{m.get('match_id','')}"
                try:
                    logger.info(f"  Uitslagenblad: {url}")
                    uitslagenblad_results[key] = scrape_uitslagenblad(session, url)
                except Exception as e:
                    logger.warning(f"  Uitslagenblad fout ({url}): {e}")

    won = sum(1 for m in all_matches if m.get("won") is True)
    lost = sum(1 for m in all_matches if m.get("won") is False)
    total = len(all_matches)
    known = won + lost

    return {
        "player_id": player_id,
        "scraped_at": _utc_now(),
        "periods_available": [p["label"] for p in all_periods],
        "periods_scraped": scraped_labels,
        "periods_empty": empty_labels,
        "periods_failed": failed_periods,
        "matches": all_matches,
        "uitslagenbladeren": uitslagenblad_results,
        "stats": {
            "total_matches": total,
            "wins": won,
            "losses": lost,
            "unknown": total - known,
            "winrate": round(won / known * 100, 1) if known else 0.0,
            "tournament_matches": sum(1 for m in all_matches if m.get("match_type") == "tornooi"),
            "interclub_matches": sum(1 for m in all_matches if m.get("match_type") == "interclub"),
        },
    }


def scrape_current_period(player_id: str) -> dict:
    """Scrape only the default (current) period. Snel testen."""
    session = requests.Session()
    params = {"userId": player_id, **DEFAULT_PADEL_PARAMS}
    html = _get_html(session, DASHBOARD_URL, params=params)
    soup = BeautifulSoup(html, "html.parser")

    period_label = "HUIDIGE_PERIODE"
    selects_with_periods = []
    for sel in soup.find_all("select"):
        opts = [o for o in sel.find_all("option") if "resultaten van week" in _clean(o.get_text()).lower()]
        if opts:
            selects_with_periods.append(opts)
    if len(selects_with_periods) >= 3:
        period_label = _clean(selects_with_periods[2][0].get_text())
    elif selects_with_periods:
        period_label = _clean(selects_with_periods[0][0].get_text())

    t_matches = parse_tournament_section(soup, player_id, period_label)
    i_matches = parse_interclub_section(soup, player_id, period_label)
    all_matches = t_matches + i_matches

    won = sum(1 for m in all_matches if m.get("won") is True)
    lost = sum(1 for m in all_matches if m.get("won") is False)

    return {
        "player_id": player_id,
        "period_label": period_label,
        "scraped_at": _utc_now(),
        "matches": all_matches,
        "stats": {
            "total": len(all_matches),
            "wins": won,
            "losses": lost,
            "tournament": len(t_matches),
            "interclub": len(i_matches),
        },
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Test: huidige periode voor speler 214435 (Alexandra Chardon)...")
    result = scrape_current_period("214435")
    print(f"\nStats: {result['stats']}")
    print(f"Periode: {result['period_label']}")
    print(f"\nEerste 3 matches:")
    for m in result["matches"][:3]:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    out_path = Path(__file__).parent.parent / "debug_output_v2" / "test_v2_214435.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOutput: {out_path}")
