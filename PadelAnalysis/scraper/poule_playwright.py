"""
poule_playwright.py — Optie B: de interclub POULE/TABEL-pagina (Elit 2.0
clubdashboard-SPA) via Playwright renderen en de fixtures naar Firestore
schrijven, zodat de gedeployde Streamlit-app (die GEEN browser heeft) de
"volgende match" gewoon uit Firestore kan lezen.

Locatie: PadelAnalysis/scraper/poule_playwright.py

--------------------------------------------------------------------------
WAT IS ER GEWIJZIGD T.O.V. DE OORSPRONKELIJKE VERSIE
--------------------------------------------------------------------------
1) De poule-URL wordt via VIJF sporen afgeleid i.p.v. enkel via <a href>.
   De oude weg faalde voor 10 van de 11 spelers, omdat Elit 2.0 navigatie
   doet via <button>/JS-routing in plaats van echte hrefs — hetzelfde patroon
   dat we al kenden van de padelstats-scraper.

     1. <a href> met interclub-poule-tabel / pouleId / pooltableId  (oude weg)
     2. regex over de VOLLEDIGE gerenderde HTML (vangt hrefs in scripts,
        __NEXT_DATA__, data-attributen, inline JSON, router-state, ...)
     3. regex over alle XHR/fetch-responses die de SPA ophaalt
     4. URL zelf opbouwen uit de losse id's
     5. klikken op een poule/tabel-element en de resulterende page.url uitlezen

2) update_player_poule() probeert tot 4 uitslagenbladen (nieuwste eerst).

3) --diagnose toont per spoor wat er gevonden werd.

4) _match_sort_key()/_parse_match_date() zijn echte functies, zodat
   diagnose_poule_speler.py ze kan importeren.

--------------------------------------------------------------------------
PADEL_ANALYSIS_EINDRONDE_SUPPORT_2026-09-15
--------------------------------------------------------------------------
5) De pouleId wordt nu doorgegeven aan parse_poule_schedule(), zodat enkel
   de eigen poule geparsed wordt. Zonder die scoping leverde een poule van
   15 wedstrijden er 287 op: de pagina bevat ook alle andere poules en acht
   eindronde-tabs.

6) De eindronde-brackets worden NIET meer genegeerd maar APART opgeslagen.
   Zodra de voorronde uitgespeeld is, staat de volgende match daar. Per
   speler wordt weggeschreven:

     interclub_schedule            voorronde-fixtures (eigen poule)
     interclub_eindronde           bracketwedstrijden van de juiste
                                   eindronde-tab (1/16 .. finale), inclusief
                                   nog niet ingevulde plekken (pending)
     interclub_eindronde_spelgroep spelgroepId van die eindronde-tab
     interclub_eindronde_naam      bv. "Eindronde Q TOT AF ..."

   De juiste eindronde-tab wordt gekozen op basis van de poulenaam: de tabs
   dekken alfabetische reeksen ("Eindronde Q TOT AF"), en Poule AA valt
   daarbinnen. Zie schedule_scraper.find_eindronde_for_poule().
"""

from __future__ import annotations

import logging
import re
import sys
import json
from pathlib import Path
from datetime import date as _date, datetime as _datetime
from typing import Optional, Iterable
from urllib.parse import urlparse, parse_qs, urlencode

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
POULE_PATH = "/nl/clubdashboard/interclub-poule-tabel"

# --- Firestore-veldnamen (centraal, zodat diagnosescripts ze kunnen hergebruiken) ---
# De automatisch afgeleide poule-URL.
FIELD_POULE_URL = "poule_reeks_url"
# Een HANDMATIG ingestelde poule-URL. Heeft ALTIJD voorrang op de automatische
# afleiding: handig wanneer de scrape geen link kan afleiden (bv. omdat de
# nieuwste gekende match uit een afgelopen seizoen komt) en je de reeks zelf kent.
FIELD_MANUAL_POULE_URL = "poule_reeks_url_manual"
# De geparste fixtures van de VOORRONDE + tijdstempel.
FIELD_SCHEDULE = "interclub_schedule"
FIELD_SCHEDULE_SCRAPED_AT = "interclub_schedule_scraped_at"
# Bron van de gebruikte URL: "manual" | "cached" | "derived"
FIELD_POULE_URL_SOURCE = "poule_reeks_url_source"
# De EINDRONDE-bracket (1/16 .. finale) + welke tab dat is.
FIELD_EINDRONDE = "interclub_eindronde"
FIELD_EINDRONDE_SPELGROEP = "interclub_eindronde_spelgroep"
FIELD_EINDRONDE_NAAM = "interclub_eindronde_naam"
# De poule waarop gescoped werd (pouleId + label), handig voor debugging.
FIELD_POULE_ID = "poule_id"
FIELD_POULE_LABEL = "poule_label"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Patronen waarmee we een poule/tabel-link herkennen.
_POULE_HREF_PATTERNS = (
    "interclub-poule-tabel",
    "pooltableid",
    "pouleid",
    "poule-tabel",
)

# Elke URL-achtige string in de HTML die naar de poule-tabel wijst.
_URL_IN_TEXT_RE = re.compile(
    r"""(?:href=|url=|"|'|\()\s*((?:https?://[^\s"'<>\\]+|/)?[^\s"'<>\\]*"""
    r"""(?:interclub-poule-tabel|interclub-poule|poule-tabel)[^\s"'<>\\]*)""",
    re.IGNORECASE,
)

# Losse id's, zowel in query-vorm (?pouleId=123) als in JSON ("pouleId": 123).
_ID_RE = re.compile(
    r"""["'&?]?\s*\b(pouleId|poulId|poolId|pooltableId|poolTableId|afdelingId|
        afdelingsId|spelgroepId|spelGroepId|reeksId)\b["']?\s*[:=]\s*["']?(\d{1,12})""",
    re.IGNORECASE | re.VERBOSE,
)

# Tekst waarop we kunnen klikken als laatste redmiddel.
_CLICK_TEXTS = (
    "poule",
    "tabel",
    "stand",
    "klassement",
    "rangschikking",
    "kalender",
)


# ---------------------------------------------------------------------------
# Lage-niveau Playwright helpers
# ---------------------------------------------------------------------------
def _dismiss_cookies(page) -> None:
    for txt in [
        "Alle cookies accepteren",
        "Cookies accepteren",
        "Accepteren",
        "Accept all",
        "Ik ga akkoord",
    ]:
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
    if not url:
        return ""
    url = url.strip().replace("&amp;", "&")
    if url.startswith("http"):
        return url
    return BASE_URL + ("" if url.startswith("/") else "/") + url


def _wait_for_table(page) -> None:
    for sel in ("table tr", "table", "[class*='poule']", "[class*='tabel']"):
        try:
            page.wait_for_selector(sel, timeout=4000)
            break
        except Exception:
            continue
    _settle(page, timeout_ms=6000)


def _reveal_eindronde_tabs(page) -> None:
    """Klik de eindronde-tabs open zodat hun brackets in de DOM staan.

    De tab-panes worden server-side meegestuurd, maar de wizard-content van
    niet-actieve rondes kan pas volledig renderen nadat de tab aangeklikt is.
    Mislukt dit, dan is dat niet fataal: parse_eindronde_bracket() leest wat
    er wél in de HTML staat."""
    try:
        toggles = page.locator("li#endRoundGroups a.dropdown-toggle")
        if toggles.count() > 0:
            toggles.first.click(timeout=2500)
            page.wait_for_timeout(400)
    except Exception:
        pass

    try:
        items = page.locator("li#endRoundGroups .dropdown-menu a[tab-id]")
        count = min(items.count(), 12)
        for i in range(count):
            try:
                items.nth(i).click(timeout=1500)
                page.wait_for_timeout(250)
            except Exception:
                continue
        if count:
            logger.info(f"[poule] {count} eindronde-tab(s) geopend voor rendering")
    except Exception:
        pass

    # Ook alle ronde-stappen (1/16, 1/8, ...) aanklikken.
    try:
        steps = page.locator(".wizard-navigation a.label")
        for i in range(min(steps.count(), 40)):
            try:
                steps.nth(i).click(timeout=800)
                page.wait_for_timeout(120)
            except Exception:
                continue
    except Exception:
        pass

    _settle(page, timeout_ms=5000)


def _open_page(pw, headless: bool):
    browser = pw.chromium.launch(headless=headless)
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="nl-BE",
        viewport={"width": 1600, "height": 1200},
        extra_http_headers={
            "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8",
            "Referer": BASE_URL + "/",
        },
    )
    return browser, context


def _render_html(
    url: str,
    headless: bool = True,
    wait_for_table: bool = True,
    reveal_eindronde: bool = False,
) -> str:
    """Open een clubdashboard-URL met een echte Chromium en geef de gerenderde
    HTML terug (na WAF + JS-rendering)."""
    url = _full_url(url)
    with sync_playwright() as pw:
        browser, context = _open_page(pw, headless)
        page = context.new_page()
        try:
            logger.info(f"[poule] openen: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            _dismiss_cookies(page)
            _settle(page)
            if wait_for_table:
                _wait_for_table(page)
            if reveal_eindronde:
                _reveal_eindronde_tabs(page)
            html = page.content()
            logger.info(f"[poule] gerenderde HTML: {len(html)} bytes")
            return html
        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# Spoor 1 + 2: extractie uit gerenderde HTML
# ---------------------------------------------------------------------------
def _from_anchors(html: str) -> list[str]:
    """Spoor 1 (oude weg): expliciete <a href>-elementen."""
    try:
        from bs4 import BeautifulSoup
    except Exception:  # noqa: BLE001
        return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        low = a["href"].lower()
        if any(pat in low for pat in _POULE_HREF_PATTERNS):
            out.append(a["href"])
    return out


def _from_raw_html(html: str) -> list[str]:
    """Spoor 2: elke URL-achtige string in de volledige HTML."""
    out = []
    for m in _URL_IN_TEXT_RE.finditer(html or ""):
        cand = m.group(1)
        if cand and len(cand) < 500:
            out.append(cand)
    return out


def _collect_ids(texts: Iterable[str]) -> dict:
    """Verzamel losse id's (pouleId, afdelingId, spelgroepId, ...)."""
    found: dict[str, str] = {}
    for text in texts:
        if not text:
            continue
        for m in _ID_RE.finditer(text):
            key = m.group(1).lower()
            val = m.group(2)
            if key in ("pouleid", "poulid", "poolid", "pooltableid"):
                found.setdefault("pouleId", val)
            elif key in ("afdelingid", "afdelingsid"):
                found.setdefault("afdelingId", val)
            elif key in ("spelgroepid", "reeksid"):
                found.setdefault("spelgroepId", val)
    return found


def _ids_from_url(url: str) -> dict:
    """Haal spelgroepId/pouleId/afdelingId uit de uitslagenblad-URL zelf."""
    out = {}
    try:
        qs = parse_qs(urlparse(_full_url(url)).query)
    except Exception:  # noqa: BLE001
        return out
    for key, vals in qs.items():
        low = key.lower()
        if not vals:
            continue
        if low == "spelgroepid":
            out["spelgroepId"] = vals[0]
        elif low in ("pouleid", "pooltableid"):
            out["pouleId"] = vals[0]
        elif low in ("afdelingid", "afdelingsid"):
            out["afdelingId"] = vals[0]
    return out


def _pick_best(candidates: list[str]) -> Optional[str]:
    """Voorkeur voor een expliciete interclub-poule-tabel-link."""
    cleaned = []
    for href in candidates:
        href = (href or "").strip().strip("\"'")
        if not href or href.lower().startswith("javascript"):
            continue
        cleaned.append(href)
    for href in cleaned:
        if "interclub-poule-tabel" in href.lower() and "=" in href:
            return _full_url(href)
    for href in cleaned:
        if "interclub-poule-tabel" in href.lower():
            return _full_url(href)
    return _full_url(cleaned[0]) if cleaned else None


# ---------------------------------------------------------------------------
# Spoor 4: URL opbouwen uit losse id's
# ---------------------------------------------------------------------------
def _build_poule_url(ids: dict) -> Optional[str]:
    """Bouw zelf de poule-tabel-URL als we de id's kennen."""
    if not ids.get("pouleId"):
        return None
    params = {}
    for key in ("afdelingId", "pouleId", "spelgroepId"):
        if ids.get(key):
            params[key] = ids[key]
    return f"{BASE_URL}{POULE_PATH}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Hoofd-afleiding: uitslagenblad -> poule-URL
# ---------------------------------------------------------------------------
def _click_to_poule(page, context) -> Optional[str]:
    """Laatste redmiddel: klik op een poule/tabel-achtig element."""
    for txt in _CLICK_TEXTS:
        for getter in ("get_by_role", "get_by_text"):
            try:
                if getter == "get_by_role":
                    loc = page.get_by_role("button", name=re.compile(txt, re.I))
                else:
                    loc = page.get_by_text(re.compile(txt, re.I))
                if loc.count() == 0:
                    continue
                before = page.url
                try:
                    with context.expect_page(timeout=4000) as popup_info:
                        loc.first.click(timeout=3000)
                    new_page = popup_info.value
                    _settle(new_page, timeout_ms=6000)
                    if "poule" in (new_page.url or "").lower():
                        return new_page.url
                except Exception:
                    _settle(page, timeout_ms=6000)
                    if page.url != before and "poule" in (page.url or "").lower():
                        return page.url
            except Exception:
                continue
    return None


def derive_poule_url_from_uitslagenblad(
    uitslagenblad_url: str,
    headless: bool = True,
    diagnose: bool = False,
    dump: Optional[str] = None,
) -> Optional[str]:
    """Render het uitslagenblad en leid de poule/tabel-URL af via vijf sporen."""
    if not uitslagenblad_url:
        return None

    url = _full_url(uitslagenblad_url)
    api_payloads: list[str] = []
    result: Optional[str] = None
    trace: dict[str, object] = {}

    with sync_playwright() as pw:
        browser, context = _open_page(pw, headless)
        page = context.new_page()

        # --- spoor 3: alle XHR/fetch-antwoorden meelezen ------------------
        def _on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct.lower():
                    return
                if len(api_payloads) > 60:
                    return
                body = resp.text()
                if body and len(body) < 2_000_000:
                    api_payloads.append(body)
            except Exception:
                pass

        page.on("response", _on_response)

        try:
            logger.info(f"[poule] openen uitslagenblad: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            _dismiss_cookies(page)
            _settle(page)
            html = page.content()

            if dump:
                Path(dump).write_text(html, encoding="utf-8")
                logger.info(f"[poule] uitslagenblad-HTML weggeschreven: {dump}")

            anchors = _from_anchors(html)
            trace["1_anchors"] = anchors[:10]
            result = _pick_best(anchors)
            if result:
                trace["gebruikt_spoor"] = 1

            if not result:
                raw = _from_raw_html(html)
                trace["2_raw_html"] = raw[:10]
                result = _pick_best(raw)
                if result:
                    trace["gebruikt_spoor"] = 2

            if not result:
                api_hits: list[str] = []
                for payload in api_payloads:
                    api_hits.extend(_from_raw_html(payload))
                trace["3_api_urls"] = api_hits[:10]
                result = _pick_best(api_hits)
                if result:
                    trace["gebruikt_spoor"] = 3

            if not result:
                ids = _ids_from_url(url)
                ids.update({k: v for k, v in _collect_ids([html]).items() if k not in ids})
                ids.update({k: v for k, v in _collect_ids(api_payloads).items() if k not in ids})
                trace["4_ids"] = ids
                result = _build_poule_url(ids)
                if result:
                    trace["gebruikt_spoor"] = 4

            if not result:
                clicked = _click_to_poule(page, context)
                trace["5_click_url"] = clicked
                if clicked:
                    result = clicked
                    trace["gebruikt_spoor"] = 5

        except Exception as e:  # noqa: BLE001
            logger.warning(f"[poule] kon uitslagenblad niet verwerken: {e}")
            trace["fout"] = str(e)
        finally:
            context.close()
            browser.close()

    if diagnose:
        print("\n=== DIAGNOSE poule-afleiding ===")
        print(f"uitslagenblad : {url}")
        print(f"json-responses: {len(api_payloads)}")
        print(json.dumps(trace, ensure_ascii=False, indent=2, default=str))
        print(f"resultaat     : {result}")
        print("================================\n")
    elif result:
        logger.info(f"[poule] poule-URL gevonden via spoor {trace.get('gebruikt_spoor')}: {result}")
    else:
        logger.warning(f"[poule] geen poule-URL gevonden. Sporen: {trace}")

    return result


# ---------------------------------------------------------------------------
# Poule-tabel renderen + fixtures/bracket parsen
# ---------------------------------------------------------------------------
def fetch_poule_fixtures(
    poule_url: str,
    headless: bool = True,
    include_eindronde: bool = True,
) -> tuple[list[dict], list[dict], dict, str]:
    """Render de poule-tabel en parse voorronde + eindronde.

    Returns (fixtures, eindronde_matches, meta, rendered_html).

    meta bevat: poule_id, poule_label, eindronde_spelgroep, eindronde_naam.

    De pouleId wordt uit de URL gehaald en doorgegeven aan de parser. Zonder
    die scoping levert de pagina ook alle andere poules en alle
    eindronde-brackets op (287 i.p.v. 15 fixtures).
    """
    poule_id = ss.poule_id_from_url(poule_url)
    html = _render_html(
        poule_url,
        headless=headless,
        wait_for_table=True,
        reveal_eindronde=include_eindronde,
    )

    try:
        fixtures = ss.parse_poule_schedule(html, poule_id=poule_id)
    except TypeError:
        # Oudere schedule_scraper zonder poule_id-parameter.
        logger.warning("[poule] schedule_scraper is verouderd (geen poule_id-scoping)")
        fixtures = ss.parse_poule_schedule(html)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[poule] parse_poule_schedule faalde: {e}")
        fixtures = []

    poule_label = next(
        (f.get("poule_label") for f in fixtures if f.get("poule_label")), None
    )
    meta: dict = {
        "poule_id": poule_id,
        "poule_label": poule_label,
        "eindronde_spelgroep": None,
        "eindronde_naam": None,
    }
    logger.info(
        f"[poule] {len(fixtures)} fixture(s) geparsed uit "
        f"{poule_label or 'poule ?'} (pouleId={poule_id})"
    )

    eindronde: list[dict] = []
    if include_eindronde:
        try:
            tabs = ss.parse_eindronde_tabs(html)
            tab = ss.find_eindronde_for_poule(tabs, poule_label)
            if tab:
                meta["eindronde_spelgroep"] = tab.get("spelgroep_id")
                meta["eindronde_naam"] = tab.get("name")
                eindronde = ss.parse_eindronde_bracket(
                    html, spelgroep_id=tab.get("spelgroep_id")
                )
                pending = sum(1 for m in eindronde if m.get("pending"))
                logger.info(
                    f"[poule] eindronde '{tab.get('name')}' "
                    f"(spelgroepId={tab.get('spelgroep_id')}): "
                    f"{len(eindronde)} wedstrijd(en), {pending} nog in te vullen"
                )
            elif tabs:
                logger.info(
                    f"[poule] {len(tabs)} eindronde-tab(s) gevonden, maar geen match "
                    f"voor {poule_label or 'onbekende poule'}"
                )
        except AttributeError:
            logger.warning(
                "[poule] schedule_scraper kent nog geen eindronde-parser; "
                "werk schedule_scraper.py bij om de eindronde mee op te slaan."
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[poule] eindronde parsen faalde: {e}")

    return fixtures, eindronde, meta, html


# ---------------------------------------------------------------------------
# Matchselectie
# ---------------------------------------------------------------------------
def _parse_match_date(raw) -> Optional[_date]:
    """Parse een ruwe datum uit een matchrecord naar een datetime.date.

    Geeft bewust een ECHTE date terug (niet een (jaar, maand, dag)-tuple),
    zodat aanroepers `.year` / `.month` / `.day` kunnen gebruiken en datums
    onderling vergelijkbaar zijn. Geeft None terug als de datum ontbreekt of
    onleesbaar is; gooit nooit een exception.
    """
    if isinstance(raw, dict):
        raw = raw.get("match_date") or raw.get("date")

    if raw is None or raw == "":
        return None

    if isinstance(raw, _datetime):
        return raw.date()
    if isinstance(raw, _date):
        return raw
    if all(hasattr(raw, a) for a in ("year", "month", "day")):
        try:
            return _date(int(raw.year), int(raw.month), int(raw.day))
        except Exception:  # noqa: BLE001
            return None

    if not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    try:
        parsed = ss._parse_date_text(text)
    except Exception:  # noqa: BLE001
        parsed = None
    if parsed:
        try:
            y, m, d = parsed[0], parsed[1], parsed[2]
            if y < 100 and d > 1900:
                y, d = d, y
            return _date(int(y), int(m), int(d))
        except Exception:  # noqa: BLE001
            pass

    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        try:
            return _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except Exception:  # noqa: BLE001
            return None
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        try:
            return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:  # noqa: BLE001
            return None

    return None


def _match_sort_key(match: dict) -> _date:
    """Sorteersleutel voor een matchrecord: nieuwste eerst bij reverse=True."""
    return _parse_match_date(match) or _date.min


def _interclub_matches(player_doc: dict) -> list[dict]:
    """Alle interclubmatches met een uitslagenblad-URL, nieuwste eerst."""
    ics = [
        m for m in (player_doc or {}).get("matches", [])
        if m.get("match_type") == "interclub" and m.get("uitslagenblad_url")
    ]
    ics.sort(key=_match_sort_key, reverse=True)
    return ics


def _most_recent_interclub_uitslagenblad(player_doc: dict) -> Optional[str]:
    ics = _interclub_matches(player_doc)
    return ics[0].get("uitslagenblad_url") if ics else None


def _all_interclub_uitslagenbladen(player_doc: dict, limit: int = 4) -> list[str]:
    """Alle interclub-uitslagenbladen, nieuwste eerst, ontdubbeld."""
    seen, out = set(), []
    for m in _interclub_matches(player_doc):
        u = m.get("uitslagenblad_url")
        if u and u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Per speler: afleiden + renderen + opslaan in Firestore
# ---------------------------------------------------------------------------
def update_player_poule(
    player_id: str,
    headless: bool = True,
    force: bool = False,
    diagnose: bool = False,
    include_eindronde: bool = True,
) -> dict:
    """
    Hoofd-entrypoint per speler (draai in GitHub Actions):
      - vind de interclub-uitslagenbladen (nieuwste eerst),
      - leid poule-URL af (Playwright, vijf sporen),
      - render poule-tabel + parse voorronde EN eindronde (Playwright),
      - schrijf alles naar het player-document.

    force=False: als er al een poule_reeks_url op het profiel staat, gebruiken
    we die meteen (sneller); we renderen dan enkel de poule-tabel opnieuw.
    """
    out = {"player_id": str(player_id), FIELD_POULE_URL: None, "fixtures": 0,
           "eindronde": 0, "eindronde_pending": 0,
           "error": None, "probed_uitslagenbladen": 0, "source": None}

    try:
        player_doc = fb.get_player(player_id) or {}
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Firestore read fout: {e}"
        return out

    try:
        profile = fb.get_player_profile(player_id) or {}
    except Exception:
        profile = {}

    # 1) Handmatige override heeft ALTIJD voorrang, ook bij --force.
    poule_url = (profile.get(FIELD_MANUAL_POULE_URL) or "").strip() or None
    if poule_url:
        poule_url = _full_url(poule_url)
        out["source"] = "manual"

    # 2) Anders: eerder opgeslagen URL hergebruiken, tenzij --force.
    if not poule_url and not force:
        poule_url = (profile.get(FIELD_POULE_URL) or "").strip() or None
        if poule_url:
            out["source"] = "cached"

    # 3) Anders: afleiden uit de uitslagenbladen.
    if not poule_url:
        bladen = _all_interclub_uitslagenbladen(player_doc)
        if not bladen:
            out["error"] = "Geen interclub-uitslagenblad-URL gevonden voor deze speler."
            return out
        for ub in bladen:
            out["probed_uitslagenbladen"] += 1
            poule_url = derive_poule_url_from_uitslagenblad(
                ub, headless=headless, diagnose=diagnose
            )
            if poule_url:
                break
        if not poule_url:
            out["error"] = (
                f"Kon geen poule/tabel-link afleiden uit {len(bladen)} uitslagenblad(en). "
                f"Zet desnoods handmatig '{FIELD_MANUAL_POULE_URL}' op het profiel, "
                "of draai met --diagnose voor het spoor-per-spoor-verslag."
            )
            return out
        out["source"] = "derived"

    out[FIELD_POULE_URL] = poule_url

    fixtures, eindronde, meta, _html = fetch_poule_fixtures(
        poule_url, headless=headless, include_eindronde=include_eindronde
    )
    out["fixtures"] = len(fixtures)
    out["eindronde"] = len(eindronde)
    out["eindronde_pending"] = sum(1 for m in eindronde if m.get("pending"))
    out[FIELD_POULE_ID] = meta.get("poule_id")
    out[FIELD_POULE_LABEL] = meta.get("poule_label")
    out[FIELD_EINDRONDE_NAAM] = meta.get("eindronde_naam")

    def _clean_for_fs(value):
        if hasattr(fb, "sanitize_for_firestore"):
            return fb.sanitize_for_firestore(value)
        return value

    # Schrijf resultaat weg (ook als fixtures leeg is bewaren we de URL, zodat
    # de app die tenminste heeft en niet opnieuw hoeft af te leiden).
    payload = {
        FIELD_POULE_URL: poule_url,
        FIELD_POULE_URL_SOURCE: out["source"],
        FIELD_POULE_ID: meta.get("poule_id"),
        FIELD_POULE_LABEL: meta.get("poule_label"),
        FIELD_SCHEDULE: _clean_for_fs(fixtures),
        FIELD_SCHEDULE_SCRAPED_AT: _utc_now_iso(),
    }
    # Overschrijf een bestaande eindronde NIET met een lege lijst: bij een
    # mislukte render is "niets gevonden" geen bewijs dat er niets is.
    if eindronde:
        payload[FIELD_EINDRONDE] = _clean_for_fs(eindronde)
        payload[FIELD_EINDRONDE_SPELGROEP] = meta.get("eindronde_spelgroep")
        payload[FIELD_EINDRONDE_NAAM] = meta.get("eindronde_naam")

    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
        # Ook op het players-document, zodat dashboard.py het overal terugvindt.
        fb.db.collection(fb.PLAYERS_COLLECTION).document(str(player_id)).set(
            {FIELD_POULE_URL: poule_url}, merge=True
        )
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Firestore write fout: {e}"

    return out


def set_manual_poule_url(player_id: str, poule_url: str) -> dict:
    """Zet handmatig de poule-URL voor een speler."""
    url = _full_url((poule_url or "").strip())
    fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
        {FIELD_MANUAL_POULE_URL: url}, merge=True
    )
    return {"player_id": str(player_id), FIELD_MANUAL_POULE_URL: url}


def _utc_now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI / debug
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(description="Render interclub poule-tabel via Playwright (Optie B).")
    parser.add_argument("--player", help="player_id: leid poule af + sla schedule op in Firestore.")
    parser.add_argument("--poule-url", help="Render deze poule-tabel-URL rechtstreeks en parse fixtures.")
    parser.add_argument("--uitslagenblad", help="Leid de poule-URL af uit dit uitslagenblad (geen opslag).")
    parser.add_argument("--show", action="store_true", help="Toon browser (niet headless).")
    parser.add_argument("--force", action="store_true", help="Negeer een reeds opgeslagen poule_reeks_url.")
    parser.add_argument("--diagnose", action="store_true",
                        help="Toon per spoor wat er gevonden werd (aanrader bij falen).")
    parser.add_argument("--dump", type=str, default=None,
                        help="Schrijf de gerenderde HTML naar dit bestand (voor parser-afstemming).")
    parser.add_argument("--set-manual-url", type=str, default=None,
                        help="Zet handmatig de poule-URL voor --player (heeft altijd voorrang).")
    parser.add_argument("--no-eindronde", action="store_true",
                        help="Sla de eindronde-brackets over (enkel de voorronde).")
    args = parser.parse_args()

    headless = not args.show
    include_eindronde = not args.no_eindronde

    if args.set_manual_url and args.player:
        print(json.dumps(set_manual_poule_url(args.player, args.set_manual_url),
                         ensure_ascii=False, indent=2))
        res = update_player_poule(args.player, headless=headless, diagnose=args.diagnose,
                                  include_eindronde=include_eindronde)
        print(json.dumps(res, ensure_ascii=False, indent=2))

    elif args.uitslagenblad:
        url = derive_poule_url_from_uitslagenblad(
            args.uitslagenblad, headless=headless, diagnose=True, dump=args.dump
        )
        print(f"Afgeleide poule-URL: {url}")

    elif args.poule_url:
        fixtures, eindronde, meta, html = fetch_poule_fixtures(
            args.poule_url, headless=headless, include_eindronde=include_eindronde
        )
        print(f"\nPoule: {meta.get('poule_label')} (pouleId={meta.get('poule_id')})")
        print(f"{len(fixtures)} voorronde-fixture(s) geparsed.")
        print(json.dumps(fixtures[:5], ensure_ascii=False, indent=2))
        if eindronde:
            pending = sum(1 for m in eindronde if m.get("pending"))
            print(f"\nEindronde: {meta.get('eindronde_naam')} "
                  f"(spelgroepId={meta.get('eindronde_spelgroep')})")
            print(f"{len(eindronde)} bracketwedstrijd(en), {pending} nog in te vullen.")
            print(json.dumps(eindronde[:5], ensure_ascii=False, indent=2))
        if args.dump:
            Path(args.dump).write_text(html, encoding="utf-8")
            print(f"\nGerenderde poule-HTML weggeschreven: {args.dump}")

    elif args.player:
        res = update_player_poule(
            args.player, headless=headless, force=args.force, diagnose=args.diagnose,
            include_eindronde=include_eindronde,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if args.dump and res.get(FIELD_POULE_URL):
            html = _render_html(res[FIELD_POULE_URL], headless=headless,
                                wait_for_table=True, reveal_eindronde=include_eindronde)
            Path(args.dump).write_text(html, encoding="utf-8")
            print(f"Gerenderde poule-HTML weggeschreven: {args.dump}")

    else:
        parser.print_help()
