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
DEFAULT_PADEL_PARAMS = {
    "tab": "padel",
    "tspid": "80",
    "tdpid": "80",
    "ppid": "79",
    "tscid": "80",
    "pcid": "79",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text) -> str:
    return " ".join((text or "").split()).strip()


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
# Period discovery
# ---------------------------------------------------------------------------

def get_padel_periods(session: requests.Session, player_id: str) -> list[dict]:
    """
    Fetch the dashboard and return all available padel periods.
    Returns list of {'label': str, 'value': str, 'select_name': str}.

    The page has 4 <select> dropdowns (tennis enkel, tennis dubbel, padel, pickleball).
    The padel one is the 3rd (index 2) among those containing period options.
    """
    params = {"userId": player_id, **DEFAULT_PADEL_PARAMS}
    html = _get_html(session, DASHBOARD_URL, params=params)
    soup = BeautifulSoup(html, "html.parser")

    selects_with_periods = []
    for sel in soup.find_all("select"):
        opts = sel.find_all("option")
        period_opts = [
            {"label": _clean(o.get_text()), "value": o.get("value", "")}
            for o in opts
            if "resultaten van week" in _clean(o.get_text()).lower()
        ]
        if period_opts:
            selects_with_periods.append({
                "select_name": sel.get("name", ""),
                "periods": period_opts,
            })

    # Index 2 = padel (0=tennis enkel, 1=tennis dubbel, 2=padel, 3=pickleball)
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
    """
    Fetch the dashboard HTML for a specific period.
    'period' is a dict with 'label', 'value', 'select_name'.

    Strategy: find the portlet form for the padel period select and POST to it,
    or fall back to GET with the select_name as a query param.
    """
    params = {"userId": player_id, **DEFAULT_PADEL_PARAMS}
    html = _get_html(session, DASHBOARD_URL, params=params, delay=0.5)
    soup = BeautifulSoup(html, "html.parser")

    select_name = period.get("select_name", "")
    period_value = period.get("value", "")

    # Find the select by name and its parent form
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
        # Fallback: GET with select name as param
        if select_name:
            params[select_name] = period_value
        return _get_html(session, DASHBOARD_URL, params=params, delay=1.5)


# ---------------------------------------------------------------------------
# Identify the padel section in the HTML
# ---------------------------------------------------------------------------

def _get_padel_section_container(soup: BeautifulSoup) -> Optional[Tag]:
    """
    The padel section is wrapped in a container identified by the 3rd occurrence
    of 'Uitslagen Tornooien' h3. We return the common ancestor div that contains
    both the tournament and interclub results.
    """
    # The page structure: for each sport there's a section with two h3 headers.
    # We find the 3rd "Uitslagen Tornooien" and use its parent container.
    h3s_tornooi = [h for h in soup.find_all("h3") if "uitslagen tornooien" in _clean(h.get_text()).lower()]
    if len(h3s_tornooi) < 3:
        # Fewer sections than expected â€” use last one
        target = h3s_tornooi[-1] if h3s_tornooi else None
    else:
        target = h3s_tornooi[2]

    return target


# ---------------------------------------------------------------------------
# Tournament parser
# ---------------------------------------------------------------------------

def parse_tournament_section(soup: BeautifulSoup, player_id: str, period_label: str) -> list[dict]:
    """
    Parse all tournament results from the padel section.

    HTML structure:
      <h3>Uitslagen Tornooien</h3>
      <div class="tournament-organization">
        <div class="details with-border">
          <div class="details-header small">
            <h4 class="details-box-title">CLUB - DATE_START - DATE_END</h4>
          </div>
          <div class="details-body ...">
            <div class="details-content">
              <span class="list-label">Reeks:</span>
              <span class="list-value"><a href="...tornooi-poule-tabel?reeksId=X&tornooiId=Y">REEKS</a></span>
              <span class="list-label">Partner:</span>
              <span class="list-value"><a href="/dashboard?userId=Z">PARTNER</a></span>
              <span class="list-label">Week:</span>
              <span class="list-value">2026-25</span>
              <table>
                <tr>
                  <td data-title="Tegenstander"><a>opp1</a><br/><a>opp2</a></td>
                  <td data-title="Klassement">P200<br/>P100</td>
                  <td data-title="Ronde">...</td>
                  <td data-title="W/V">W</td>
                  <td data-title="Uitslag">9/4</td>
                </tr>
              </table>
            </div>
          </div>
        </div>
      </div>
      <div class="tournament-organization">...</div>
    """
    matches = []

    target_h3 = _get_padel_section_container(soup)
    if target_h3 is None:
        return matches

    # Tournament blocks are div.tournament-organization siblings after the h3
    sibling = target_h3.find_next_sibling()
    while sibling:
        # Stop at Uitslagen Interclub h3
        if sibling.name == "h3" and "uitslagen interclub" in _clean(sibling.get_text()).lower():
            break
        if sibling.name == "h3":
            break

        if sibling.name == "div" and "tournament-organization" in (sibling.get("class") or []):
            matches.extend(_parse_tournament_org_div(sibling, player_id, period_label))

        sibling = sibling.find_next_sibling()

    # Also try: div.details.with-border siblings (interclub-style without tournament-organization wrapper)
    if not matches:
        # Fallback: scrape all div.details.with-border between the two h3s
        h3s_tornooi = [h for h in soup.find_all("h3") if "uitslagen tornooien" in _clean(h.get_text()).lower()]
        h3s_interclub = [h for h in soup.find_all("h3") if "uitslagen interclub" in _clean(h.get_text()).lower()]
        if len(h3s_tornooi) >= 3 and len(h3s_interclub) >= 3:
            start = h3s_tornooi[2]
            end = h3s_interclub[2]
            for div in soup.find_all("div", class_="tournament-organization"):
                # Check if this div is between start and end
                if _is_between(div, start, end):
                    matches.extend(_parse_tournament_org_div(div, player_id, period_label))

    return matches


def _parse_tournament_org_div(org_div: Tag, player_id: str, period_label: str) -> list[dict]:
    """Parse one div.tournament-organization into a list of match dicts."""
    matches = []

    for details_div in org_div.find_all("div", class_="details"):
        header = details_div.find("h4", class_="details-box-title")
        if not header:
            continue

        header_text = _clean(header.get_text())
        # Parse "CLUB NAME - DD/MM/YYYY - DD/MM/YYYY"
        hm = re.match(r"^(.+?)\s+-\s+(\d{2}/\d{2}/\d{4})\s+-\s+(\d{2}/\d{2}/\d{4})$", header_text)
        if hm:
            tournament_name = _clean(hm.group(1))
            date_start = hm.group(2)
            date_end = hm.group(3)
        else:
            tournament_name = header_text
            date_start = date_end = None

        # Extract metadata from list-label / list-value spans
        content = details_div.find("div", class_="details-content")
        if not content:
            continue

        reeks_name = reeks_url = reeks_id = tornooi_id = None
        partner_name = partner_uid = None
        tournament_week = None

        for row in content.find_all("div", class_="row-fluid"):
            # A row-fluid can contain multiple label/value pairs (e.g. Club + Week share one row)
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

        # Parse match rows from table
        table = content.find("table")
        if not table:
            continue

        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue

            # Col 0: Tegenstander â€” two <a> tags
            opp_links = cols[0].find_all("a")
            opp1_name, opp1_uid = _parse_player_link(opp_links[0]) if len(opp_links) > 0 else (None, None)
            opp2_name, opp2_uid = _parse_player_link(opp_links[1]) if len(opp_links) > 1 else (None, None)

            # Col 1: Klassement â€” "P200\nP100"
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
    Parse all interclub results from the padel section.

    HTML structure (div.details.with-border siblings after Uitslagen Interclub h3):
      <div class="details with-border">
        <h4 class="details-box-title">COMPETITION - DD/MM/YYYY</h4>
        <div class="details-content">
          Reeks: PADEL DAMES 100
          Ontmoeting: TEAM A / TEAM B
          <a href="/interclub-uitslagenblad?spelgroepId=X&matchId=Y">Bekijk uitslagenblad</a>
          <table>
            <tr>
              <td data-title="Partner"><a>partner</a></td>
              <td data-title="Tegenstander"><a>opp1</a><br/><a>opp2</a></td>
              <td data-title="Klassement">P200<br/>P100</td>
              <td data-title="Ronde">poule - 5</td>
              <td data-title="W/V">W</td>
              <td data-title="Uitslag">9/1</td>
            </tr>
          </table>
        </div>
      </div>
    """
    matches = []

    h3s_interclub = [h for h in soup.find_all("h3") if "uitslagen interclub" in _clean(h.get_text()).lower()]
    if len(h3s_interclub) < 3:
        target_h3 = h3s_interclub[-1] if h3s_interclub else None
    else:
        target_h3 = h3s_interclub[2]

    if target_h3 is None:
        return matches

    sibling = target_h3.find_next_sibling()
    while sibling:
        # Stop at pickleball or next major section
        if sibling.name == "h3":
            break
        if sibling.name == "h2":
            break

        if sibling.name == "div" and "details" in (sibling.get("class") or []):
            matches.extend(_parse_interclub_details_div(sibling, player_id, period_label))

        sibling = sibling.find_next_sibling()

    return matches


def _parse_interclub_details_div(details_div: Tag, player_id: str, period_label: str) -> list[dict]:
    """Parse one div.details interclub block."""
    matches = []

    header = details_div.find("h4", class_="details-box-title")
    if not header:
        return matches

    header_text = _clean(header.get_text())
    # Format: "COMPETITION NAME - DD/MM/YYYY"
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

    # Extract reeks, ontmoeting, uitslagenblad link from row-fluid divs
    for row in content.find_all("div", class_="row-fluid"):
        # Check list-label spans
        for label_span in row.find_all("span", class_="list-label"):
            value_span = label_span.find_next_sibling("span", class_="list-value")
            if not value_span:
                continue
            label = _clean(label_span.get_text()).rstrip(":")
            if label.lower() == "reeks":
                reeks_name = _clean(value_span.get_text())
            elif label.lower() == "ontmoeting":
                encounter = _clean(value_span.get_text())

        # Check uitslagenblad link
        uitslagen_a = row.find("a", href=re.compile(r"interclub-uitslagenblad"))
        if uitslagen_a:
            uitslagenblad_url = uitslagen_a.get("href", "")
            spelgroep_id = _param_from_url(uitslagenblad_url, "spelgroepId")
            match_id = _param_from_url(uitslagenblad_url, "matchId")

    # Parse match rows
    table = content.find("table")
    if not table:
        return matches

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 5:
            continue

        # Col 0: Partner
        partner_links = cols[0].find_all("a")
        partner_name, partner_uid = _parse_player_link(partner_links[0]) if partner_links else (None, None)

        # Col 1: Tegenstander (two links)
        opp_links = cols[1].find_all("a")
        opp1_name, opp1_uid = _parse_player_link(opp_links[0]) if len(opp_links) > 0 else (None, None)
        opp2_name, opp2_uid = _parse_player_link(opp_links[1]) if len(opp_links) > 1 else (None, None)

        # Col 2: Klassement
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


def _is_between(tag: Tag, start: Tag, end: Tag) -> bool:
    """Check if 'tag' appears in the document after 'start' and before 'end'."""
    all_tags = list(tag.find_all_previous())
    return start in all_tags and end not in all_tags


# ---------------------------------------------------------------------------
# Uitslagenblad scraper
# ---------------------------------------------------------------------------

def scrape_uitslagenblad(session: requests.Session, url: str, delay: float = 1.5) -> dict:
    """
    Scrape a full interclub match sheet (uitslagenblad).
    Returns all match rows with player links for both teams.
    """
    full_url = BASE_URL + url if url.startswith("/") else url
    html = _get_html(session, full_url, delay=delay)
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "url": full_url,
        "scraped_at": _utc_now(),
        "home_team": None,
        "away_team": None,
        "matches": [],
    }

    # Try to extract team names from page header
    for tag in ["h1", "h2", "h3"]:
        h = soup.find(tag)
        if h:
            text = _clean(h.get_text())
            if "/" in text:
                parts = text.split("/", 1)
                result["home_team"] = _clean(parts[0])
                result["away_team"] = _clean(parts[1])
                break

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue

            all_links = [a for a in row.find_all("a") if _user_id_from_url(a.get("href"))]
            if len(all_links) < 2:
                continue

            players = [{"name": _clean(a.get_text()), "user_id": _user_id_from_url(a.get("href"))} for a in all_links]
            rankings = re.findall(r"P\d+", _clean(row.get_text()))
            col_texts = [_clean(c.get_text()) for c in cols]
            result_letter = next((t for t in reversed(col_texts) if t in ("W", "V")), None)
            score_cands = [t for t in col_texts if re.match(r"\d+/\d+", t)]
            score = score_cands[-1] if score_cands else None
            round_cands = [t for t in col_texts if re.match(r"(poule|finale|1/[24])", t, re.I)]
            round_text = round_cands[0] if round_cands else None

            result["matches"].append({
                "players": players,
                "rankings": rankings,
                "round_text": round_text,
                "result": result_letter,
                "won": (result_letter == "W") if result_letter in ("W", "V") else None,
                "score": score,
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
    """
    Scrape all padel results for a player across all (or selected) periods.

    Args:
        player_id: userId from the website.
        periods_to_scrape: List of period labels to include. None = all.
        scrape_uitslagenbladeren: Also fetch interclub detail pages.
        delay_between_periods: Seconds between period fetches (be polite).
    """
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
                # First period is the default page we already fetched during period discovery
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
                logger.info(f"    â†’ {len(t_matches)} tornooi + {len(i_matches)} interclub")
            else:
                empty_labels.append(label)
                logger.info(f"    â†’ leeg")

            scraped_labels.append(label)

        except Exception as e:
            logger.error(f"    â†’ FOUT: {e}")
            failed_periods.append({"label": label, "error": str(e)})

        if i < len(target_periods) - 1:
            time.sleep(delay_between_periods)

    # Optionally fetch uitslagenbladeren
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

    # Detect current period label
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

