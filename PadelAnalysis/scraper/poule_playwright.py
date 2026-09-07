"""
poule_playwright.py — Optie B: de interclub POULE/TABEL-pagina (Elit 2.0
clubdashboard-SPA) via Playwright renderen en de fixtures naar Firestore
schrijven, zodat de gedeployde Streamlit-app (die GEEN browser heeft) de
"volgende match" gewoon uit Firestore kan lezen.

Locatie: PadelAnalysis/scraper/poule_playwright.py
(naast scrape_player.py / fetch_period_playwright.py / ci_scrape_all.py)

WAAROM PLAYWRIGHT:
De pagina's onder /nl/clubdashboard/interclub-poule-tabel?... en
/nl/clubdashboard/interclub-uitslagenblad?... zijn:
  1) beschermd door een WAF (een platte requests.get geeft HTTP 403), en
  2) een client-side gerenderde SPA (de fixtures komen pas na JS-uitvoering
     in de DOM).
Een echte Chromium (Playwright) passeert de WAF én voert de JS uit. Playwright
is niet beschikbaar op Streamlit Community Cloud, maar WEL in de GitHub Actions
workflow (scrape-padel.yml, ubuntu-runner met `playwright install`). Daarom
draait deze module in CI en schrijft het resultaat naar Firestore.

DATASTROOM (per speler):
  meest recente interclubmatch.uitslagenblad_url
    -> Playwright rendert uitslagenblad
       -> vind link naar interclub-poule-tabel (afdelingId/pouleId/spelgroepId)  => reeks_url
    -> Playwright rendert die poule-tabel
       -> parse fixtures (schedule_scraper.parse_poule_schedule op de
          gerenderde HTML)  => interclub_schedule
  -> schrijf {poule_reeks_url, interclub_schedule, interclub_schedule_scraped_at}
     naar het player-document in Firestore.

De Streamlit-app (dashboard.py) leest 'poule_reeks_url' en/of
'interclub_schedule' en toont zo de volgende match zonder zelf te scrapen.

BELANGRIJK (parsing): de clubdashboard-poule-tabel is mogelijk anders
gestructureerd dan de publieke 'zoek-een-competitie-organisatie'-pagina waar
schedule_scraper.parse_poule_schedule oorspronkelijk voor gemaakt is. Deze
module rendert de ECHTE DOM en probeert die parser; komt er niets uit, dan
schrijft de debug-modus de gerenderde HTML weg (--dump) zodat de parser
gericht kan worden afgestemd op de echte structuur.
"""
from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright

# --- path setup: zelfde patroon als scrape_player.py / ci_scrape_all.py ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb           # noqa: E402
import schedule_scraper as ss           # noqa: E402  (requests-only parser, cloud-safe)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisenpadelvlaanderen.be"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Patronen waarmee we op het gerenderde uitslagenblad de poule/tabel-link
# herkennen. We zoeken defensief op meerdere varianten.
_POULE_HREF_PATTERNS = (
    "interclub-poule-tabel",
    "pooltableid",
    "pouleid",
)


# ---------------------------------------------------------------------------
# Lage-niveau Playwright helpers
# ---------------------------------------------------------------------------
def _dismiss_cookies(page) -> None:
    for txt in ["Alle cookies accepteren", "Cookies accepteren", "Accepteren", "Accept all", "Ik ga akkoord"]:
        try:
            loc = page.get_by_text(txt, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=2000)
                page.wait_for_timeout(600)
                return
        except Exception:
            pass


def _settle(page, timeout_ms: int = 12000) -> None:
    """Wacht tot de SPA klaar is met laden/renderen."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(1500)


def _full_url(url: str) -> str:
    return url if url.startswith("http") else BASE_URL + ("" if url.startswith("/") else "/") + url


def _render_html(url: str, headless: bool = True, wait_for_table: bool = True) -> str:
    """Open een clubdashboard-URL met een echte Chromium en geef de gerenderde
    HTML terug (na WAF + JS-rendering)."""
    url = _full_url(url)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="nl-BE",
            extra_http_headers={
                "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8",
                "Referer": BASE_URL + "/",
            },
        )
        page = context.new_page()
        try:
            logger.info(f"[poule] openen: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            _dismiss_cookies(page)
            _settle(page)
            if wait_for_table:
                # Beste-inspanning: wacht tot er minstens één tabel/rij zichtbaar is.
                for sel in ("table tr", "table", "[class*='poule']", "[class*='tabel']"):
                    try:
                        page.wait_for_selector(sel, timeout=4000)
                        break
                    except Exception:
                        continue
                _settle(page, timeout_ms=6000)
            html = page.content()
            logger.info(f"[poule] gerenderde HTML: {len(html)} bytes")
            return html
        finally:
            context.browser.close()


# ---------------------------------------------------------------------------
# Poule-URL afleiden uit een uitslagenblad (gerenderd)
# ---------------------------------------------------------------------------
def _extract_poule_href_from_html(html: str) -> Optional[str]:
    """Zoek in gerenderde uitslagenblad-HTML de link naar de poule/tabel."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        low = a["href"].lower()
        if any(pat in low for pat in _POULE_HREF_PATTERNS):
            candidates.append(a["href"])
    if not candidates:
        return None
    # Voorkeur: een expliciete interclub-poule-tabel-link.
    for href in candidates:
        if "interclub-poule-tabel" in href.lower():
            return _full_url(href)
    return _full_url(candidates[0])


def derive_poule_url_from_uitslagenblad(uitslagenblad_url: str, headless: bool = True) -> Optional[str]:
    """Render het uitslagenblad en haal de poule/tabel-URL eruit."""
    if not uitslagenblad_url:
        return None
    try:
        html = _render_html(uitslagenblad_url, headless=headless, wait_for_table=False)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[poule] kon uitslagenblad niet renderen: {e}")
        return None
    return _extract_poule_href_from_html(html)


# ---------------------------------------------------------------------------
# Poule-tabel renderen + fixtures parsen
# ---------------------------------------------------------------------------
def fetch_poule_fixtures(poule_url: str, headless: bool = True) -> tuple[list[dict], str]:
    """Render de poule-tabel en parse de fixtures.
    Returns (fixtures, rendered_html). fixtures kan leeg zijn als de
    paginastructuur afwijkt (gebruik dan de gerenderde HTML om de parser af
    te stemmen)."""
    html = _render_html(poule_url, headless=headless, wait_for_table=True)
    try:
        fixtures = ss.parse_poule_schedule(html)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[poule] parse_poule_schedule faalde: {e}")
        fixtures = []
    logger.info(f"[poule] {len(fixtures)} fixture(s) geparsed uit poule-tabel")
    return fixtures, html


# ---------------------------------------------------------------------------
# Per speler: afleiden + renderen + opslaan in Firestore
# ---------------------------------------------------------------------------
def _most_recent_interclub_uitslagenblad(player_doc: dict) -> Optional[str]:
    ics = [
        m for m in (player_doc or {}).get("matches", [])
        if m.get("match_type") == "interclub" and m.get("uitslagenblad_url")
    ]
    if not ics:
        return None
    ics.sort(key=lambda m: ss._parse_date_text(m.get("match_date") or "") or (0, 0, 0), reverse=True)
    return ics[0].get("uitslagenblad_url")


def update_player_poule(player_id: str, headless: bool = True, force: bool = False) -> dict:
    """
    Hoofd-entrypoint per speler (draai in GitHub Actions):
      - vind meest recente interclub-uitslagenblad,
      - leid poule-URL af (Playwright),
      - render poule-tabel + parse fixtures (Playwright),
      - schrijf poule_reeks_url + interclub_schedule naar het player-document.
    force=False: als er al een poule_reeks_url op het profiel staat, gebruiken
    we die meteen (sneller); we renderen dan enkel de poule-tabel opnieuw.
    """
    out = {"player_id": str(player_id), "poule_reeks_url": None, "fixtures": 0, "error": None}
    try:
        player_doc = fb.get_player(player_id) or {}
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Firestore read fout: {e}"
        return out

    profile = {}
    try:
        profile = fb.get_player_profile(player_id) or {}
    except Exception:
        profile = {}

    poule_url = None if force else (profile.get("poule_reeks_url") or None)

    if not poule_url:
        ub = _most_recent_interclub_uitslagenblad(player_doc)
        if not ub:
            out["error"] = "Geen interclub-uitslagenblad-URL gevonden voor deze speler."
            return out
        poule_url = derive_poule_url_from_uitslagenblad(ub, headless=headless)
        if not poule_url:
            out["error"] = "Kon geen poule/tabel-link afleiden uit het uitslagenblad."
            return out

    out["poule_reeks_url"] = poule_url

    fixtures, _html = fetch_poule_fixtures(poule_url, headless=headless)
    out["fixtures"] = len(fixtures)

    # Schrijf resultaat weg (ook als fixtures leeg is bewaren we de URL, zodat
    # de app die tenminste heeft en niet opnieuw hoeft af te leiden).
    payload = {
        "poule_reeks_url": poule_url,
        "interclub_schedule": fb.sanitize_for_firestore(fixtures) if hasattr(fb, "sanitize_for_firestore") else fixtures,
        "interclub_schedule_scraped_at": _utc_now_iso(),
    }
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
        # Ook op het players-document, zodat dashboard.py het overal terugvindt.
        fb.db.collection(fb.PLAYERS_COLLECTION).document(str(player_id)).set(
            {"poule_reeks_url": poule_url}, merge=True
        )
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Firestore write fout: {e}"
    return out


def _utc_now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI / debug
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Render interclub poule-tabel via Playwright (Optie B).")
    parser.add_argument("--player", help="player_id: leid poule af + sla schedule op in Firestore.")
    parser.add_argument("--poule-url", help="Render deze poule-tabel-URL rechtstreeks en parse fixtures.")
    parser.add_argument("--uitslagenblad", help="Leid de poule-URL af uit dit uitslagenblad (geen opslag).")
    parser.add_argument("--show", action="store_true", help="Toon browser (niet headless).")
    parser.add_argument("--force", action="store_true", help="Negeer een reeds opgeslagen poule_reeks_url.")
    parser.add_argument("--dump", type=str, default=None,
                        help="Schrijf de gerenderde HTML naar dit bestand (voor parser-afstemming).")
    args = parser.parse_args()
    headless = not args.show

    if args.uitslagenblad:
        url = derive_poule_url_from_uitslagenblad(args.uitslagenblad, headless=headless)
        print(f"Afgeleide poule-URL: {url}")
        if args.dump:
            html = _render_html(args.uitslagenblad, headless=headless, wait_for_table=False)
            Path(args.dump).write_text(html, encoding="utf-8")
            print(f"Gerenderde uitslagenblad-HTML weggeschreven: {args.dump}")

    elif args.poule_url:
        fixtures, html = fetch_poule_fixtures(args.poule_url, headless=headless)
        print(f"{len(fixtures)} fixture(s) geparsed.")
        print(json.dumps(fixtures[:10], ensure_ascii=False, indent=2))
        if args.dump:
            Path(args.dump).write_text(html, encoding="utf-8")
            print(f"Gerenderde poule-HTML weggeschreven: {args.dump}")

    elif args.player:
        res = update_player_poule(args.player, headless=headless, force=args.force)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if args.dump and res.get("poule_reeks_url"):
            html = _render_html(res["poule_reeks_url"], headless=headless, wait_for_table=True)
            Path(args.dump).write_text(html, encoding="utf-8")
            print(f"Gerenderde poule-HTML weggeschreven: {args.dump}")

    else:
        parser.print_help()
