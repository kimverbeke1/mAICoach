from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urljoin, urlparse
import re
import unicodedata

from playwright.sync_api import sync_playwright

from firebase_service import (
    get_player_search_cache,
    save_player_search_cache,
    save_player_profile,
)

BASE_SITE_URL = "https://www.tennisenpadelvlaanderen.be"
BASE_SEARCH_URL = "https://www.tennisenpadelvlaanderen.be/zoek-een-speler"
DEBUG_DIR = Path("debug_output")
DEBUG_DIR.mkdir(exist_ok=True)
SEARCH_LOG_FILE = DEBUG_DIR / "player_search_debug.log"


def log_line(message: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(line)
    with open(SEARCH_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def clean_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _fold(text: str) -> str:
    """Case/diacritic-insensitive normalisation, no substring matching."""
    text = clean_text(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return clean_text(text)


def _title_from_search(full_name: str) -> str:
    # Preserve input if it already has casing; otherwise title-case for display.
    full_name = clean_text(full_name)
    return full_name if any(ch.isupper() for ch in full_name) else full_name.title()


def normalize_name_parts(first_name: str, last_name: str) -> Tuple[str, str, str]:
    first_name = clean_text(first_name)
    last_name = clean_text(last_name)
    full_name = clean_text(f"{first_name} {last_name}")
    return first_name, last_name, full_name


def split_full_name(full_name: str) -> Tuple[str, str, str]:
    parts = [p for p in clean_text(full_name).split() if p]
    if len(parts) >= 2:
        first_name = parts[0]
        last_name = " ".join(parts[1:])
    elif len(parts) == 1:
        first_name = ""
        last_name = parts[0]
    else:
        first_name = last_name = ""
    return normalize_name_parts(first_name, last_name)


def build_search_url(first_name: str, last_name: str, sport_id: int = 2) -> str:
    first_name, last_name, _ = normalize_name_parts(first_name, last_name)
    return (
        f"{BASE_SEARCH_URL}?sportId={sport_id}"
        f"&playerName={quote(last_name)}"
        f"&playerFirstName={quote(first_name)}"
        f"#searchResultStart"
    )


def dismiss_cookie_banner_if_present(page):
    for label in ["Alle cookies accepteren", "Cookies accepteren", "Ik ga akkoord", "Accepteren"]:
        try:
            loc = page.get_by_text(label, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=500)
                log_line(f"Cookie banner gesloten via: {label}")
                return
        except Exception:
            pass


def detect_robot_page(page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=1500).lower()
        return ("ben jij een robot?" in body) or ("verhoogd aantal geautomatiseerde toegangspogingen" in body)
    except Exception:
        return False


def extract_player_id_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        vals = parse_qs(parsed.query).get("userId")
        return vals[0] if vals else None
    except Exception:
        return None


def _candidate_starts_with_exact_search_name(candidate_text: str, full_name: str) -> bool:
    """True if candidate text starts with exactly the searched first+last name.

    Example:
    - search 'Bart Claeys' matches 'Bart Claeys Padel Factory ...'
    - search 'Carl Ide' does NOT match 'Carlotta Ide ...'
    """
    cand_tokens = _fold(candidate_text).split()
    search_tokens = _fold(full_name).split()
    if not cand_tokens or not search_tokens:
        return False
    if len(cand_tokens) < len(search_tokens):
        return False
    return cand_tokens[: len(search_tokens)] == search_tokens


def _exact_name_match(candidate_name: str, full_name: str) -> bool:
    return _fold(candidate_name) == _fold(full_name)


def _club_match(candidate_club: Optional[str], requested_club: Optional[str]) -> bool:
    if not requested_club:
        return True
    return _fold(requested_club) in _fold(candidate_club or "")


def _split_name_club_from_raw(raw_text: str, fallback_first: str, fallback_last: str) -> Tuple[str, Optional[str]]:
    """Extract name + club from TVL search-result text.

    TVL often returns one line like:
      'Bart Claeys Padel Factory | M Tennis enkel 5 ptn ...'

    We want:
      name='Bart Claeys', club='Padel Factory'

    For all exact Bart Claeys variants we return the searched name and the club
    found immediately after that name, before the first '|'.
    """
    fallback_full = clean_text(f"{fallback_first} {fallback_last}")
    display_name = _title_from_search(fallback_full)
    raw = clean_text(raw_text)
    if not raw:
        return display_name, None

    # Focus on the part before the first |, because the rest is ranking/metadata.
    prefix = clean_text(raw.split("|")[0])

    if _candidate_starts_with_exact_search_name(prefix, fallback_full):
        # Remove exactly the number of search tokens from the original prefix.
        parts = prefix.split()
        search_len = len(fallback_full.split())
        club = clean_text(" ".join(parts[search_len:])) or None
        return display_name, club

    # Fallback for structured multiline result: first line = name, following line = club.
    lines = [clean_text(line) for line in raw_text.splitlines()]
    lines = [line for line in lines if line and line.lower() not in {"profiel bekijken", "bekijk profiel"}]
    if lines:
        first = lines[0]
        if _candidate_starts_with_exact_search_name(first, fallback_full):
            parts = first.split()
            search_len = len(fallback_full.split())
            club = clean_text(" ".join(parts[search_len:])) or None
            if not club and len(lines) > 1:
                club = lines[1]
            return display_name, club
        return first, lines[1] if len(lines) > 1 else None

    return display_name, None


def parse_result_block(raw_text: str, fallback_first: str, fallback_last: str) -> Tuple[str, Optional[str]]:
    return _split_name_club_from_raw(raw_text, fallback_first, fallback_last)


def _candidate_from_url_and_meta(url: str, display_name: str, club: Optional[str]) -> Optional[Dict]:
    full_url = urljoin(BASE_SITE_URL, url)
    player_id = extract_player_id_from_url(full_url)
    if not player_id:
        return None
    return {
        "display_name": clean_text(display_name) or None,
        "club": clean_text(club) or None,
        "player_id": str(player_id),
        "dashboard_url": full_url,
        "source": "search_result",
    }


def _dedupe(candidates: List[Dict]) -> List[Dict]:
    unique = []
    seen = set()
    for c in candidates:
        key = c.get("player_id") or c.get("dashboard_url")
        if key and key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _filter_candidates(candidates: List[Dict], full_name: str, club: Optional[str]) -> List[Dict]:
    out = []
    for c in _dedupe(candidates):
        name = c.get("display_name") or ""
        if not _exact_name_match(name, full_name):
            log_line(f"DROP name mismatch: searched='{full_name}' | candidate='{name}'")
            continue
        if not _club_match(c.get("club"), club):
            log_line(f"DROP club mismatch: requested='{club}' | candidate='{c.get('club')}' | name='{name}'")
            continue
        out.append(c)
    return out


def _save_profiles(candidates: List[Dict]) -> List[Dict]:
    """Return unique search candidates without saving them to Firebase.

    Important:
    Searching in the 'Speler toevoegen' page must NOT add players to the database.
    A player should only be saved after the user explicitly clicks 'Toevoegen'
    in dashboard.py.
    """
    return _dedupe(candidates)

def _raw_candidate_elements(page) -> List[Dict]:
    """Single browser roundtrip to extract candidate controls and their containers.

    Avoids the slow Playwright loop over every <a> tag and avoids the broad '.row'
    selector that caused club names to be mixed across players.
    """
    return page.evaluate(
        r"""() => {
            const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
            const candidates = [];
            const seen = new Set();
            const els = Array.from(document.querySelectorAll('a,button,[role="button"],[onclick],[data-href],[data-url]'));

            for (const el of els) {
                const txt = clean(el.innerText || el.textContent || '');
                const ownHref = el.getAttribute('href') || el.getAttribute('data-href') || el.getAttribute('data-url') || '';
                const a = el.closest('a');
                const href = ownHref || (a ? (a.getAttribute('href') || '') : '');
                const onclick = el.getAttribute('onclick') || '';
                const urlish = href || onclick;

                if (!urlish.includes('userId=') && !txt.toLowerCase().includes('profiel bekijken')) {
                    continue;
                }

                const container = el.closest('article, li, tr, .views-row, .search-result, .card, [class*="search-result"], [class*="result"]') || el.parentElement || el;
                const rawText = clean(container.innerText || container.textContent || txt);
                const key = `${urlish}|${rawText}`;
                if (seen.has(key)) continue;
                seen.add(key);
                candidates.push({ href: urlish, raw_text: rawText, text: txt });
            }
            return candidates;
        }"""
    )


def extract_candidates_from_page(page, fallback_first: str, fallback_last: str, club: Optional[str] = None) -> List[Dict]:
    candidates: List[Dict] = []
    full_name = clean_text(f"{fallback_first} {fallback_last}")

    try:
        raw_items = _raw_candidate_elements(page)
        log_line(f"Ruwe profielkandidaten gevonden: {len(raw_items)}")
    except Exception as e:
        log_line(f"Kon profielkandidaten niet uitlezen: {e}")
        raw_items = []

    for item in raw_items:
        href = item.get("href") or ""
        raw_text = item.get("raw_text") or item.get("text") or ""
        parsed_name, parsed_club = parse_result_block(raw_text, fallback_first, fallback_last)
        c = _candidate_from_url_and_meta(href, parsed_name, parsed_club)
        if c:
            candidates.append(c)
            log_line(f"Kandidaat parsed: {c.get('player_id')} | {c.get('display_name')} | {c.get('club')}")

    candidates = _filter_candidates(candidates, full_name, club)
    log_line(f"Exact gefilterde kandidaten: {len(candidates)}")
    return _save_profiles(candidates)


def click_search_button_if_needed(page):
    actions = [
        lambda: page.get_by_role("button", name="Zoek").first.click(timeout=1000),
        lambda: page.get_by_role("button", name="Search").first.click(timeout=1000),
        lambda: page.locator("button[type='submit']").first.click(timeout=1000),
        lambda: page.get_by_text("Zoek", exact=True).click(timeout=1000),
    ]
    for idx, action in enumerate(actions, start=1):
        try:
            action()
            try:
                page.wait_for_load_state("domcontentloaded", timeout=1500)
            except Exception:
                pass
            log_line(f"Zoekknop geklikt via methode {idx}")
            return True
        except Exception:
            continue
    try:
        page.keyboard.press("Enter")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=1500)
        except Exception:
            pass
        log_line("Zoektrigger via Enter")
        return True
    except Exception:
        return False


def _install_resource_blocking(page):
    try:
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "font", "media"}
            else route.continue_(),
        )
    except Exception:
        pass


def search_players(
    full_name: Optional[str] = None,
    club: Optional[str] = None,
    sport: str = "Padel",
    headless: bool = True,
    use_cache: bool = True,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> List[Dict]:
    if full_name is not None:
        first_name, last_name, full_name = split_full_name(full_name)
    else:
        first_name, last_name, full_name = normalize_name_parts(first_name or "", last_name or "")

    if use_cache:
        cached = get_player_search_cache(full_name, club=club, sport=sport)
        if cached and isinstance(cached.get("candidates"), list) and cached.get("candidates"):
            cached_candidates = _filter_candidates(cached.get("candidates", []), full_name, club)
            if cached_candidates:
                log_line(f"Cache gebruikt voor zoekterm: {full_name}")
                return cached_candidates
            log_line(f"Cache genegeerd: geen exacte match voor {full_name}")

    if SEARCH_LOG_FILE.exists():
        SEARCH_LOG_FILE.unlink()

    url = build_search_url(first_name=first_name, last_name=last_name, sport_id=2)
    log_line(f"Zoek-URL: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
            ],
        )
        context = browser.new_context()
        page = context.new_page()
        _install_resource_blocking(page)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            dismiss_cookie_banner_if_present(page)

            try:
                page.get_by_text("Profiel bekijken", exact=False).first.wait_for(timeout=2500)
            except Exception:
                pass

            if detect_robot_page(page):
                raise RuntimeError("Robot-check gedetecteerd op zoekpagina")

            candidates = extract_candidates_from_page(page, first_name, last_name, club=club)
            if candidates:
                log_line(f"Kandidaten direct zichtbaar: {len(candidates)}")
                save_player_search_cache(full_name, club=club, sport=sport, candidates=candidates)
                return candidates

            log_line("Nog geen kandidaten zichtbaar na URL-load, probeer expliciet op zoekknop te klikken...")
            if click_search_button_if_needed(page):
                if detect_robot_page(page):
                    raise RuntimeError("Robot-check gedetecteerd na zoektrigger")
                candidates = extract_candidates_from_page(page, first_name, last_name, club=club)
                if candidates:
                    log_line(f"Kandidaten gevonden na expliciete zoektrigger: {len(candidates)}")
                    save_player_search_cache(full_name, club=club, sport=sport, candidates=candidates)
                    return candidates

            log_line("Geen kandidaten gevonden")
            return []
        finally:
            context.close()
            browser.close()
