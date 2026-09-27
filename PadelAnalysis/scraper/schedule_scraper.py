"""
schedule_scraper.py - haalt het poule/tabel-schema op en parseert de fixtures.

Belangrijk:
- played wordt bepaald via een ingevulde ontmoetingsscore.
- identify_own_ploeg_id vergelijkt het uitslagenblad van de laatste gekende
  interclubdatum met partner- en tegenstandernamen uit het spelersdocument.
  Daardoor wordt de eigen ploeg automatisch onderscheiden van de tegenstander.

PADEL_ANALYSIS_POULE_SCOPE_FIX_2026-09-15
-----------------------------------------
BUG (opgelost): parse_poule_schedule() gaf 287 fixtures terug voor een poule
die er 15 telt. Oorzaak: de functie liep over ALLE <table>-elementen van de
pagina. De clubdashboard-poule-tabel bevat echter veel meer dan de gevraagde
poule (voorronde + eindronde-brackets van andere poules).
Fix: parse_poule_schedule() scopet op de <div class="poule"> met de gevraagde
poule-header-id en negeert table.game-table.

PADEL_ANALYSIS_EINDRONDE_SUPPORT_2026-09-15
-------------------------------------------
De eindronde-brackets worden apart geparsed door parse_eindronde_bracket().

--------------------------------------------------------------------------
PADEL_ANALYSIS_SILENT_EXCEPTION_CI_DIAGNOSIS_2026-09-27 (op verzoek van Kim:
"bekijk de prescan poule of de logica nu werkt")
--------------------------------------------------------------------------
_fixture_player_sides() ving elke fout van scrape_uitslagenblad() af met een
kale `except Exception: return set(), set()` zonder te loggen WAT er
misging. FIX: logt nu expliciet het foutype en de boodschap.

--------------------------------------------------------------------------
PADEL_ANALYSIS_NAME_WORD_ORDER_FIX_2026-09-27 (op verzoek van Kim: "bij de
poule pre-scan log zie ik [...] bij mijn eigen naam [...] Eigen ploeg niet
herkenbaar [...] overgeslagen")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd met echte data uit een eerdere diagnose-run): de
site (uitslagenblad, via scrape_uitslagenblad()) toont spelersnamen in het
formaat "Achternaam Voornaam" (bevestigd: het uitslagenblad van Kim's eigen
wedstrijd gaf letterlijk "verbekekim" terug als genormaliseerde naam - dus
"Verbeke Kim"). Het player_profiles-document se `display_name`-veld staat
echter meestal in het format "Voornaam Achternaam" (Kim's eigen profiel:
"Kim Verbeke"). De oude `_norm()` doet enkel lowercase + niet-alfanumeriek
verwijderen - GEEN herschikking van woorden - dus "kimverbeke" (uit het
profiel) en "verbekekim" (van de site) zijn NOCH exact gelijk, NOCH een
substring van elkaar. Dat liet own_display_name (PADEL_ANALYSIS_OWN_NAME_
MISSING_FIX_2026-09-26) voor Kim's EIGEN naam specifiek altijd falen, en
vermoedelijk ook voor elk ander tracked profiel waarvan display_name in
een andere woordvolgorde staat dan de site gebruikt - wat de opvallend
lange lijst "Eigen ploeg niet herkenbaar" in de nachtelijke prescan-log
grotendeels verklaart (niet enkel Kim zelf).

FIX: nieuwe functie _norm_person_name() - identiek aan _norm(), maar
splitst EERST op woorden, sorteert die woorden alfabetisch, en voegt ze
dan pas samen. "Kim Verbeke" -> tokens ["kim","verbeke"] (al gesorteerd)
-> "kimverbeke". "Verbeke Kim" -> tokens ["verbeke","kim"] -> gesorteerd
["kim","verbeke"] -> "kimverbeke". IDENTIEK, dus nu een exacte match,
ongeacht de woordvolgorde. Gebruikt UITSLUITEND in de functies die
PERSOONSNAMEN vergelijken (_known_names_for_date(), _fixture_player_
sides()) - de gewone _norm() blijft ongewijzigd voor overige doeleinden
(bv. team-naam-vergelijkingen elders), dus dit heeft geen invloed op
andere delen van de codebase.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisenpadelvlaanderen.be"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"

_BRACKET_TABLE_CLASSES = {"game-table"}
_EINDRONDE_RANGE_RE = re.compile(
    r"eindronde\s+([A-Z]{1,3})\s+tot\s+([A-Z]{1,3})\b", re.IGNORECASE
)
_CHANGEPARAM_RE = re.compile(r"changeParam\(\s*(\d+)", re.IGNORECASE)
_SEED_RE = re.compile(r"\(([A-Z]{1,3}\d{1,2})\)")
_SIDE_RE = re.compile(r"\(([TU])\)\s*$")
_DATE_IN_TEXT_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?\b")


def _param_from_url(href: Optional[str], param: str) -> Optional[str]:
    if not href:
        return None
    values = parse_qs(urlparse(href).query).get(param)
    return values[0] if values else None


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _norm(text: Optional[str]) -> str:
    """Algemene tekst-normalisatie (lowercase + niet-alfanumeriek weg) -
    gebruikt voor team-namen en andere vergelijkingen waar woordvolgorde
    er niet toe doet omdat er sowieso maar 1 volgorde bestaat. NIET
    gebruiken voor persoonsnamen - zie _norm_person_name()."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _norm_person_name(text: Optional[str]) -> str:
    """PADEL_ANALYSIS_NAME_WORD_ORDER_FIX_2026-09-27: woordvolgorde-
    ONAFHANKELIJKE normalisatie voor PERSOONSNAMEN. Splitst op woorden,
    verwijdert niet-alfanumeriek per woord, sorteert de woorden
    alfabetisch en voegt ze dan samen - "Kim Verbeke" en "Verbeke Kim"
    geven zo altijd hetzelfde resultaat, ongeacht welke bron (profiel
    vs. site) welke volgorde gebruikt. Zie de uitgebreide root-cause-
    analyse in de moduledocstring hierboven."""
    if not text:
        return ""
    tokens = re.sub(r"[^a-z0-9\s]", "", text.lower()).split()
    return "".join(sorted(tokens))


def poule_id_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    for key in ("pouleId", "pouleid", "poolTableId", "pooltableid"):
        val = _param_from_url(url, key)
        if val:
            return str(val)
    return None


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


def poule_letter_index(letters: Optional[str]) -> Optional[int]:
    text = re.sub(r"[^A-Z]", "", (letters or "").upper())
    if not text:
        return None
    index = 0
    for char in text:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def poule_letters_from_label(label: Optional[str]) -> Optional[str]:
    match = re.search(r"poule\s+([A-Z]{1,3})\b", label or "", re.IGNORECASE)
    return match.group(1).upper() if match else None


def _is_bracket_table(table) -> bool:
    return bool(set(table.get("class") or []) & _BRACKET_TABLE_CLASSES)


def _poule_containers(soup) -> list:
    containers = soup.find_all("div", class_="poule")
    return [c for c in containers if c.find(class_=lambda k: k and "poule-header" in k)]


def _poule_container_id(container) -> Optional[str]:
    header = container.find(class_=lambda c: c and "poule-header" in c)
    if header is not None:
        header_id = header.get("id")
        if header_id and str(header_id).strip().isdigit():
            return str(header_id).strip()
    return None


def _poule_container_label(container) -> Optional[str]:
    title = container.find(class_=lambda c: c and "poule-title" in c)
    text = _clean(title.get_text()) if title is not None else ""
    return text or None


def _select_tables(soup, poule_id: Optional[str]) -> list[tuple]:
    containers = _poule_containers(soup)
    if containers:
        chosen = containers
        if poule_id:
            matched = [c for c in containers if _poule_container_id(c) == str(poule_id)]
            if matched:
                chosen = matched
        out = []
        for container in chosen:
            label = _poule_container_label(container) or "Poule ?"
            for table in container.find_all("table"):
                if not _is_bracket_table(table):
                    out.append((table, label))
        if out:
            return out
    return [
        (table, _find_preceding_label(table))
        for table in soup.find_all("table")
        if not _is_bracket_table(table)
    ]


def parse_poule_schedule(html: str, poule_id: Optional[str] = None) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    fixtures = []
    for table, poule_label in _select_tables(soup, poule_id):
        for row in table.find_all("tr"):
            if "hidden" in (row.get("class") or []):
                continue
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
            group_id = (
                _param_from_url(home_link.get("href"), "spelgroepId")
                or _param_from_url(away_link.get("href"), "spelgroepId")
            )
            match_link = next(
                (a for a in links if _param_from_url(a.get("href"), "matchId")), None
            )
            match_id = _param_from_url(match_link.get("href"), "matchId") if match_link else None
            result_url = match_link.get("href") if match_link else None
            date_match = _DATE_IN_TEXT_RE.search(row_text)
            date_text = date_match.group(0) if date_match else ""
            remainder = row_text.replace(home_name, "").replace(away_name, "")
            if date_text:
                remainder = remainder.replace(date_text, "")
            scores = re.findall(r"\d+[-/]\d+(?:\s*/\s*\d+[-/]\d+)*", remainder)
            score = scores[0] if scores else None
            fixtures.append({
                "stage": "voorronde",
                "poule_label": poule_label,
                "poule_id": str(poule_id) if poule_id else None,
                "date_text": date_text,
                "home_name": home_name,
                "home_ploeg_id": _param_from_url(home_link.get("href"), "ploegId"),
                "away_name": away_name,
                "away_ploeg_id": _param_from_url(away_link.get("href"), "ploegId"),
                "score": score,
                "spelgroep_id": group_id,
                "match_id": match_id,
                "uitslagenblad_url": result_url,
                "played": bool(score),
                "pending": False,
            })
    return fixtures


def parse_eindronde_tabs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    tabs: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        text = _clean(anchor.get_text())
        if not text or "eindronde" not in text.lower():
            continue
        spelgroep_id = anchor.get("tab-id")
        if not spelgroep_id:
            match = _CHANGEPARAM_RE.search(anchor.get("onclick") or "")
            spelgroep_id = match.group(1) if match else None
        if not spelgroep_id or str(spelgroep_id) in seen:
            continue
        seen.add(str(spelgroep_id))
        range_match = _EINDRONDE_RANGE_RE.search(text)
        from_letters = range_match.group(1).upper() if range_match else None
        to_letters = range_match.group(2).upper() if range_match else None
        tabs.append({
            "spelgroep_id": str(spelgroep_id),
            "name": text,
            "from_letters": from_letters,
            "to_letters": to_letters,
            "from_index": poule_letter_index(from_letters),
            "to_index": poule_letter_index(to_letters),
        })
    return tabs


def find_eindronde_for_poule(tabs: list[dict], poule_label: Optional[str]) -> Optional[dict]:
    letters = poule_letters_from_label(poule_label)
    index = poule_letter_index(letters)
    if index is None:
        return None
    for tab in tabs or []:
        low, high = tab.get("from_index"), tab.get("to_index")
        if low is not None and high is not None and low <= index <= high:
            return tab
    return None


def _round_labels(pane) -> dict:
    labels = {}
    for anchor in pane.find_all("a", class_="label"):
        href = (anchor.get("href") or "").lstrip("#")
        text = _clean(anchor.get_text())
        if href and text:
            labels[href] = text
    return labels


def _team_from_cell(cell) -> dict:
    if cell is None:
        return {"name": None, "ploeg_id": None, "seed": None, "side": None}
    link = next(
        (a for a in cell.find_all("a") if _param_from_url(a.get("href"), "ploegId")), None
    )
    raw = _clean(link.get_text()) if link is not None else _clean(cell.get_text())
    seed_match = _SEED_RE.search(raw)
    side_match = _SIDE_RE.search(raw)
    name = _SEED_RE.sub("", raw)
    name = re.sub(r"\([TU]\)", "", name)
    name = _clean(name)
    return {
        "name": name or None,
        "ploeg_id": _param_from_url(link.get("href"), "ploegId") if link is not None else None,
        "seed": seed_match.group(1) if seed_match else None,
        "side": side_match.group(1) if side_match else None,
    }


def _scores_from_row(row) -> list[str]:
    return [
        _clean(td.get_text())
        for td in row.find_all("td")
        if "score" in (td.get("class") or [])
    ]


def parse_eindronde_bracket(html: str, spelgroep_id: Optional[str] = None) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    matches: list[dict] = []
    panes = soup.find_all("div", class_="tab-pane")
    for pane in panes:
        pane_id = (pane.get("id") or "")
        if not pane_id.startswith("tab"):
            continue
        pane_group = pane_id[3:]
        if spelgroep_id and pane_group != str(spelgroep_id):
            continue
        if not pane.find("table", class_="game-table"):
            continue
        labels = _round_labels(pane)
        for content in pane.find_all("div", class_="wizard-content"):
            ronde = labels.get(content.get("id") or "", "")
            for table in content.find_all("table", class_="game-table"):
                for winner_cell in table.find_all("td", class_="match-winner"):
                    row1 = winner_cell.find_parent("tr")
                    if row1 is None or "hidden" in (row1.get("class") or []):
                        continue
                    row2 = row1.find_next_sibling("tr")
                    if row2 is not None and "hidden" in (row2.get("class") or []):
                        row2 = None
                    cells1 = row1.find_all("td")
                    team1 = _team_from_cell(cells1[0] if cells1 else None)
                    cells2 = row2.find_all("td") if row2 is not None else []
                    team2 = _team_from_cell(cells2[0] if cells2 else None)
                    winner_link = next(
                        (a for a in winner_cell.find_all("a")
                         if _param_from_url(a.get("href"), "ploegId")),
                        None,
                    )
                    status_link = next(
                        (a for a in winner_cell.find_all("a")
                         if _param_from_url(a.get("href"), "matchId")),
                        None,
                    )
                    date_span = winner_cell.find("span", class_="date")
                    date_text = ""
                    if date_span is not None:
                        found = _DATE_IN_TEXT_RE.search(_clean(date_span.get_text()))
                        date_text = found.group(0) if found else ""
                    scores1 = _scores_from_row(row1)
                    scores2 = _scores_from_row(row2) if row2 is not None else []
                    has_score = any(s for s in scores1) and any(s for s in scores2)
                    status_text = _clean(status_link.get_text()) if status_link is not None else ""
                    pending = not (team1["ploeg_id"] and team2["ploeg_id"])
                    if not (team1["name"] or team2["name"] or status_link is not None):
                        continue
                    matches.append({
                        "stage": "eindronde",
                        "spelgroep_id": pane_group,
                        "ronde": ronde,
                        "date_text": date_text,
                        "home_name": team1["name"],
                        "home_ploeg_id": team1["ploeg_id"],
                        "home_seed": team1["seed"],
                        "home_side": team1["side"],
                        "away_name": team2["name"],
                        "away_ploeg_id": team2["ploeg_id"],
                        "away_seed": team2["seed"],
                        "away_side": team2["side"],
                        "score": " / ".join(
                            f"{a}-{b}" for a, b in zip(scores1, scores2) if a and b
                        ) or None,
                        "winner_name": _clean(_SEED_RE.sub("", _clean(winner_link.get_text())))
                        if winner_link is not None else None,
                        "winner_ploeg_id": _param_from_url(winner_link.get("href"), "ploegId")
                        if winner_link is not None else None,
                        "match_id": _param_from_url(status_link.get("href"), "matchId")
                        if status_link is not None else None,
                        "uitslagenblad_url": status_link.get("href")
                        if status_link is not None else None,
                        "status_text": status_text or None,
                        "played": bool(has_score and status_text),
                        "pending": pending,
                    })
    return matches


def eindronde_for_team(matches: list[dict], ploeg_id: str) -> list[dict]:
    own = [
        m for m in matches or []
        if m.get("home_ploeg_id") == ploeg_id or m.get("away_ploeg_id") == ploeg_id
    ]
    own.sort(key=lambda m: _parse_date_text(m.get("date_text") or "") or (9999, 99, 99))
    return own


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


def _known_names_for_date(
    own_known_matches: list[dict],
    date_key: tuple,
    own_display_name: Optional[str] = None,
) -> tuple[set[str], set[str]]:
    """PADEL_ANALYSIS_OWN_NAME_MISSING_FIX_2026-09-26 + PADEL_ANALYSIS_
    NAME_WORD_ORDER_FIX_2026-09-27: own_display_name wordt hier expliciet
    aan own_side toegevoegd - GENORMALISEERD via _norm_person_name() zodat
    een woordvolgorde-verschil met de site (bv. profiel "Kim Verbeke" vs.
    site "Verbeke Kim") niet langer een gemiste match veroorzaakt. Zie de
    moduledocstring voor de volledige, met echte data bevestigde analyse."""
    own_side = set()
    opponent_side = set()
    eigen_naam = _norm_person_name(own_display_name)
    if eigen_naam:
        own_side.add(eigen_naam)
    for match in own_known_matches:
        if match.get("match_type") != "interclub":
            continue
        if _parse_date_text(match.get("match_date") or "") != date_key:
            continue
        for key in ("player_name", "display_name", "partner_name"):
            value = _norm_person_name(match.get(key))
            if value:
                own_side.add(value)
        for key in ("opp1_name", "opp2_name"):
            value = _norm_person_name(match.get(key))
            if value:
                opponent_side.add(value)
    return own_side, opponent_side


def _fixture_player_sides(fixture: dict) -> tuple[set[str], set[str]]:
    """Lees het uitslagenblad en geef de spelersnamen per kant terug.

    PADEL_ANALYSIS_SILENT_EXCEPTION_CI_DIAGNOSIS_2026-09-27: logt nu
    expliciet het foutype en de boodschap bij een fout, i.p.v. dit stil
    te verzwijgen.

    PADEL_ANALYSIS_NAME_WORD_ORDER_FIX_2026-09-27: gebruikt
    _norm_person_name() (woordvolgorde-onafhankelijk) i.p.v. _norm() voor
    de spelersnamen - zie moduledocstring."""
    url = fixture.get("uitslagenblad_url")
    if not url:
        return set(), set()
    try:
        from scraper_v2 import scrape_uitslagenblad
        data = scrape_uitslagenblad(requests.Session(), url)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"_fixture_player_sides: kon uitslagenblad niet ophalen/verwerken "
            f"voor {url}: {type(e).__name__}: {e}"
        )
        return set(), set()
    home_players: set[str] = set()
    away_players: set[str] = set()
    for board in data.get("matches", []) or []:
        players = board.get("players", []) or []
        if len(players) < 4:
            continue
        for player in players[:2]:
            name = _norm_person_name(player.get("name"))
            if name:
                home_players.add(name)
        for player in players[2:4]:
            name = _norm_person_name(player.get("name"))
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


def identify_own_ploeg_id(
    fixtures: list[dict],
    own_known_matches: list[dict],
    own_display_name: Optional[str] = None,
):
    """Bepaal automatisch de eigen ploeg via de meest recente gespeelde
    fixture waarvan de datum voorkomt in de matchhistoriek van de
    geselecteerde speler. Zie module-docstring (PADEL_ANALYSIS_NAME_WORD_
    ORDER_FIX_2026-09-27) voor de belangrijkste onderliggende fix."""
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
        own_names, opponent_names = _known_names_for_date(
            own_known_matches, date_key, own_display_name=own_display_name,
        )
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


def get_next_match(
    team_fixtures: list[dict],
    eindronde_matches: Optional[list[dict]] = None,
    ploeg_id: Optional[str] = None,
) -> Optional[dict]:
    for fixture in team_fixtures or []:
        if not fixture.get("played"):
            return fixture
    if not eindronde_matches:
        return None
    own_id = ploeg_id
    if own_id is None and team_fixtures:
        ids = {f.get("home_ploeg_id") for f in team_fixtures} & {
            f.get("away_ploeg_id") for f in team_fixtures
        }
        own_id = next(iter(ids), None)
    relevant = eindronde_for_team(eindronde_matches, own_id) if own_id else []
    for match in relevant:
        if not match.get("played"):
            return match
    if relevant:
        last = relevant[-1]
        if own_id and last.get("winner_ploeg_id") and last["winner_ploeg_id"] != own_id:
            return None
    upcoming = [
        m for m in eindronde_matches
        if not m.get("played") and (m.get("pending") or m.get("home_ploeg_id") == own_id
                                    or m.get("away_ploeg_id") == own_id)
    ]
    upcoming.sort(key=lambda m: _parse_date_text(m.get("date_text") or "") or (9999, 99, 99))
    return upcoming[0] if upcoming else None


def opponent_of(fixture: dict, own_ploeg_id: str) -> dict:
    if fixture.get("home_ploeg_id") == own_ploeg_id:
        return {"name": fixture.get("away_name"), "ploeg_id": fixture.get("away_ploeg_id")}
    return {"name": fixture.get("home_name"), "ploeg_id": fixture.get("home_ploeg_id")}
