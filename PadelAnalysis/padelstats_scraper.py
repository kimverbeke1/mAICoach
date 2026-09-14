"""
padelstats_scraper.py - haalt de 'playing strength' (P-waarde) op van
padelstats.be, als externe kalibratiebron voor onze eigen Elo-berekening
(elo_rating.py).

PADEL_ANALYSIS_PADELSTAT_CALIBRATION_2026-09-12:
Doel: NIET om padelstats.be's volledige spelersbestand te scrapen of hun
formule te reconstrueren (die is proprietair). Doel is uitsluitend: voor een
klein aantal individuele, door Kim aangeduide spelers de "playing strength"
opzoeken, zodat onze eigen Elo-schatting (elo_rating.py) daartegen
gekalibreerd/vergeleken kan worden.

BELANGRIJK - waarom Playwright nodig is (geen requests.get):
padelstats.be is een client-side gerenderde React-app (Material-UI). De kale
HTML-bron bevat enkel <div id="root"></div> en een defer-script; alle inhoud
wordt pas na JavaScript-uitvoering opgebouwd.

PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_FIX_2026-09-13 (v3):
BUG (opgelost): elke klik mislukte omdat een Google Funding Choices cookie-
consent-banner (CSS-klasse "fc-consent-root"/"fc-dialog-overlay") over de
hele pagina lag en alle pointer-events onderschepte. Fix: _dismiss_consent_
banner() sluit de banner (via gangbare knopteksten NL/EN, of desnoods een
JS-verwijdering als fallback) VOOR er iets anders geprobeerd wordt.

PADEL_ANALYSIS_PADELSTAT_REAL_STRUCTURE_2026-09-13 (v4):
Uit een dump van #search NA het typen van "Kim Verbeke" bleek de EXACTE,
bevestigde structuur van een zoekresultaat:

    <button class="... MuiCardActionArea-root ...">
      <p class="... css-ly3v7n">Verbeke Kim</p>
      <span class="... css-1v2gfp5"><b>P200</b><b> • </b>PADEL FACTORY</span>
    </button>

search_padelstat_player() zoekt <button>-elementen, leest naam/klassement/
club rechtstreeks uit de knoptekst en klikt om te navigeren; het
padelstats-ID wordt nadien uit de resulterende page.url gehaald.

PADEL_ANALYSIS_PADELSTAT_CLUB_MATCH_BUG_2026-09-13 (v5, kritieke bugfix):
BUG (opgelost): search_and_fetch_padelstat_rating() gebruikte voorheen een
NAIEVE, ASYMMETRISCHE substring-check om de opgegeven club te vergelijken
met een kandidaat-club:

    club_norm in _normalize(candidate.get("club", ""))

Dit faalde systematisch zodra de opgegeven club LANGER was dan de kandidaat-
club (wat in de praktijk vaak het geval is: onze eigen Firestore-clubnamen
bevatten soms een geslachtscode-achtervoegsel zoals " | V" of " | M", bv.
"Padel Factory | V"). Een string als "padel factory | v" is namelijk NOOIT
een substring van het kortere "padel factory" - de vergelijkingsrichting zelf
was dus al principieel te fragiel, los van het achtervoegsel-probleem.
Concreet voorbeeld dat hierdoor faalde: Carl Ide (club "Padel Factory | V"
resp. "| M" in onze eigen data) werd bij 3 gevonden padelstats-kandidaten
NOOIT gekoppeld aan het kandidaat "PADEL FACTORY", ook al was dat overduidelijk
de juiste match - met een verkeerde/onbevestigde speler (en dus verkeerde
playing-strength-waarde) tot gevolg.
Fix, twee onderdelen:
  1. _strip_known_suffixes(): verwijdert een eventueel " | <letter>"-
     achtervoegsel (geslachtscode of vergelijkbaar) VOOR verdere verwerking.
  2. _club_matches(): vervangt de fragiele substring-check door een
     WOORD-OVERLAP-vergelijking - beide clubnamen worden opgesplitst in
     betekenisvolle woorden (met generieke/veelvoorkomende woorden zoals
     "padel", "tennis", "club", "bvba" uitgefilterd via _CLUB_STOPWORDS, om
     te vermijden dat bv. "Padel Factory" en "Tennis en Padel Pollare" vals
     zouden matchen puur op het gedeelde woord "padel") en een match is
     positief zodra er minstens één betekenisvol woord overlapt, ongeacht
     volgorde, lengte-verschil of exacte formulering.
Beide fixes zijn getest tegen het exacte, gemelde Carl Ide-scenario (club
"Padel Factory | V" tegenover kandidaten "T.C. WINDEKIND - WINDEKIND SPORT
BVBA", "PADEL FACTORY", "T. AND P. C") en geven nu de correcte match.

BELANGRIJK - scope en respectvol gebruik:
- Enkel voor INCIDENTELE, individuele opzoekingen - nooit massaal crawlen.
- Resultaten worden gecachet in Firestore (firebase_service.py:
  save_padelstat_rating / get_padelstat_rating).
- De P-waarde op een profielpagina wordt gezocht via de ZICHTBARE TEKST
  (regex rond het label 'Playing strength'), niet via een fragiele
  CSS-class.

Gebruik:
    import padelstats_scraper as ps

    result = ps.fetch_padelstat_rating("1293841")
    print(result["rating"])  # 190

    result = ps.search_and_fetch_padelstat_rating("Kim Verbeke", club="Padel Factory")

    candidates = ps.search_padelstat_player("Kim Verbeke")
    for c in candidates:
        print(c["name"], "|", c["klassement"], "|", c["club"], "->", c["padelstat_id"])
"""
from __future__ import annotations

import re
from typing import Optional

BASE_URL = "https://padelstats.be"

_CONFIRMED_SEARCH_PLACEHOLDER = "Search a player by name or club"

_CONSENT_BUTTON_TEXTS = [
    "Alles accepteren", "Accepteren", "Akkoord", "Ik ga akkoord",
    "Accept all", "I agree", "Agree", "Accept", "OK", "Got it",
]

# Labels voor de "playing strength" op een PROFIELPAGINA (niet te verwarren
# met het officiële klassement dat in de zoekresultaten-kaart staat).
_RATING_LABEL_PATTERNS = [
    r"playing\s*strength[^\d]{0,20}P\s*(\d{2,4})",
    r"speelsterkte[^\d]{0,20}P\s*(\d{2,4})",
]

_GENERIC_P_PATTERN = r"\bP(\d{2,4})\b"

# Herkent "P200 •" of "P200 • CLUB" in de tekst van een resultaatkaart.
_CARD_KLASSEMENT_PATTERN = r"P(\d{2,4})\s*•\s*(.+)"

# PADEL_ANALYSIS_PADELSTAT_CLUB_MATCH_BUG_2026-09-13: woorden die te vaak in
# clubnamen voorkomen om betekenisvol te zijn voor een match (zouden anders
# bv. "Padel Factory" met "Tennis en Padel Pollare" laten matchen puur op
# het gedeelde woord "padel").
_CLUB_STOPWORDS = {
    "de", "het", "een", "en", "and", "the", "of", "voor",
    "club", "cc", "tc", "t.c.", "vzw", "bvba", "nv", "sport", "sports",
    "padel", "tennis", "paddle",
}


def _extract_rating(text: str) -> tuple[Optional[int], str]:
    """Zoekt de 'playing strength'-waarde in de zichtbare tekst van een
    PROFIELPAGINA. Returns (rating, source): 'label' = betrouwbaar (gevonden
    naast het exacte label 'Playing strength'); 'generic' = enkel een los
    P-getal gevonden; 'none' = niets gevonden."""
    for pattern in _RATING_LABEL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1)), "label"
    match = re.search(_GENERIC_P_PATTERN, text)
    if match:
        return int(match.group(1)), "generic"
    return None, "none"


def _visible_text_snippet(text: str, max_len: int = 600) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:max_len] + ("..." if len(cleaned) > max_len else "")


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _strip_known_suffixes(club: str) -> str:
    """PADEL_ANALYSIS_PADELSTAT_CLUB_MATCH_BUG_2026-09-13: verwijdert een
    eventueel ' | <letter>'-achtervoegsel (bv. geslachtscode ' | V' / ' | M')
    dat in ONS eigen Firestore-veld 'club' kan voorkomen (bv.
    'Padel Factory | V'), maar dat padelstats.be niet gebruikt. Zonder deze
    strip kan geen enkele vergelijking met een padelstats-clubnaam ooit
    correct matchen."""
    return re.sub(r"\s*\|\s*[A-Za-z]\s*$", "", str(club or "")).strip()


def _club_words(club: str) -> set[str]:
    """Zet een clubnaam om naar een set betekenisvolle woorden (kleine
    letters, geen interpunctie, generieke/veelvoorkomende woorden uit
    _CLUB_STOPWORDS verwijderd)."""
    text = _normalize(_strip_known_suffixes(club))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return {w for w in text.split() if w and w not in _CLUB_STOPWORDS}


def _club_matches(given_club: str, candidate_club: str) -> bool:
    """PADEL_ANALYSIS_PADELSTAT_CLUB_MATCH_BUG_2026-09-13: vervangt de
    eerdere, foutieve asymmetrische substring-check
    (`club_norm in _normalize(candidate_club)`, die faalde zodra
    given_club LANGER was dan candidate_club - bv. door een
    geslachtscode-achtervoegsel) door een WOORD-OVERLAP-vergelijking.
    Match = minstens 1 betekenisvol woord komt in beide voor, ongeacht
    volgorde, lengte-verschil of exacte formulering. Geeft False terug als
    één van beide geen enkel betekenisvol woord overhoudt (bv. lege
    string), zodat dit nooit per ongeluk "matcht met alles"."""
    given_words = _club_words(given_club)
    candidate_words = _club_words(candidate_club)
    if not given_words or not candidate_words:
        return False
    return bool(given_words & candidate_words)


def _dismiss_consent_banner(page) -> str:
    """Sluit de cookie-consent-banner. Geeft een statusstring terug voor
    debug-doeleinden."""
    for text in _CONSENT_BUTTON_TEXTS:
        try:
            btn = page.get_by_role("button", name=re.compile(re.escape(text), re.IGNORECASE))
            if btn.count() > 0:
                btn.first.click(timeout=3000)
                page.wait_for_timeout(500)
                return f"geklikt op knop met tekst '{text}'"
        except Exception:
            continue
    try:
        for frame in page.frames:
            for text in _CONSENT_BUTTON_TEXTS:
                try:
                    btn = frame.get_by_role("button", name=re.compile(re.escape(text), re.IGNORECASE))
                    if btn.count() > 0:
                        btn.first.click(timeout=3000)
                        page.wait_for_timeout(500)
                        return f"geklikt op knop in iframe met tekst '{text}'"
                except Exception:
                    continue
    except Exception:
        pass
    try:
        removed = page.evaluate(
            """() => {
                const el = document.querySelector('.fc-consent-root');
                if (el) { el.remove(); return true; }
                return false;
            }"""
        )
        if removed:
            return "banner-element rechtstreeks verwijderd via JavaScript (fallback)"
    except Exception:
        pass
    return "geen enkele methode werkte - banner mogelijk nog aanwezig"


def fetch_padelstat_rating(padelstat_player_id: str, headless: bool = True, timeout_ms: int = 15000) -> dict:
    """Haalt de playing-strength-waarde op voor een BEKEND padelstats-ID
    (het getal uit de profiel-URL, bv. 'https://padelstats.be/speler/1293841'
    -> '1293841').

    Returns: {
        "padelstat_id": str, "url": str, "rating": int | None,
        "rating_source": "label" | "generic" | "none",
        "raw_text_snippet": str,
    }
    """
    padelstat_player_id = str(padelstat_player_id).strip()
    url = f"{BASE_URL}/speler/{padelstat_player_id}"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(1000)
            _dismiss_consent_banner(page)
            body_text = page.inner_text("body")
        finally:
            browser.close()

    rating, source = _extract_rating(body_text)
    return {
        "padelstat_id": padelstat_player_id,
        "url": url,
        "rating": rating,
        "rating_source": source,
        "raw_text_snippet": _visible_text_snippet(body_text),
    }


def search_padelstat_player(name: str, headless: bool = True, timeout_ms: int = 15000) -> list[dict]:
    """Zoekt een speler op naam via de padelstats.be-zoekfunctie op de
    homepage en geeft alle gevonden resultaat-kaarten terug, MET klassement
    en club, zonder al te klikken.

    Returns: lijst van {
        "name": str, "klassement": int | None, "club": str,
        "card_text": str, "_index": int,
    }
    """
    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(BASE_URL, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(1000)
            _dismiss_consent_banner(page)

            search_box = page.get_by_placeholder(_CONFIRMED_SEARCH_PLACEHOLDER).first
            search_box.click(timeout=10000)
            search_box.fill(name)
            page.wait_for_timeout(2000)

            container = page.locator("xpath=//div[@id='search']/following-sibling::div[1]")
            if container.count() == 0:
                return []

            cards = container.first.get_by_role("button")
            count = cards.count()
            for i in range(count):
                card_text = cards.nth(i).inner_text().strip()
                if not card_text:
                    continue
                match = re.search(_CARD_KLASSEMENT_PATTERN, card_text)
                klassement = int(match.group(1)) if match else None
                club = match.group(2).strip() if match else ""
                name_part = card_text
                if match:
                    name_part = card_text[:match.start()].strip()
                results.append({
                    "name": name_part or name,
                    "klassement": klassement,
                    "club": club,
                    "card_text": card_text,
                    "_index": i,
                })
        finally:
            browser.close()

    return results


def _click_and_get_padelstat_id(name: str, index: int, headless: bool = True, timeout_ms: int = 15000) -> Optional[str]:
    """Herhaalt de zoekopdracht en klikt op de kaart op positie 'index', en
    leest het padelstats-ID uit de resulterende URL na navigatie."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(BASE_URL, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(1000)
            _dismiss_consent_banner(page)

            search_box = page.get_by_placeholder(_CONFIRMED_SEARCH_PLACEHOLDER).first
            search_box.click(timeout=10000)
            search_box.fill(name)
            page.wait_for_timeout(2000)

            container = page.locator("xpath=//div[@id='search']/following-sibling::div[1]")
            if container.count() == 0:
                return None
            cards = container.first.get_by_role("button")
            if index >= cards.count():
                return None

            cards.nth(index).click(timeout=10000)
            page.wait_for_timeout(1500)
            page.wait_for_url(re.compile(r"/speler/\d+"), timeout=timeout_ms)

            match = re.search(r"/speler/(\d+)", page.url)
            return match.group(1) if match else None
        finally:
            browser.close()


def search_and_fetch_padelstat_rating(
    name: str,
    club: Optional[str] = None,
    headless: bool = True,
) -> Optional[dict]:
    """Zoekt op naam (en optioneel club, om gelijknamige spelers bij andere
    clubs uit te sluiten) en haalt de 'playing strength' van de best passende
    match op.

    PADEL_ANALYSIS_PADELSTAT_CLUB_MATCH_BUG_2026-09-13: gebruikt nu
    _club_matches() (woord-overlap, met geslachtscode-achtervoegsel-strip)
    in plaats van de eerdere, kapotte asymmetrische substring-check - zie
    module-docstring voor het volledige, met een echt gemeld geval
    (Carl Ide) bevestigde bewijs van de bug en de fix.

    Gedrag bij meerdere kandidaten:
      - club gegeven EN een kandidaat waarvan de club minstens 1
        betekenisvol woord deelt met de opgegeven club -> die kandidaat
        wordt gebruikt.
      - club gegeven maar geen match, of geen club gegeven bij >1 kandidaat
        -> de eerste kandidaat wordt gebruikt MET een expliciete
        waarschuwing ("club_disambiguation_note").

    Geeft None terug als er niets gevonden werd.
    """
    candidates = search_padelstat_player(name, headless=headless)
    if not candidates:
        return None

    chosen = None
    note = None

    if club:
        for candidate in candidates:
            if _club_matches(club, candidate.get("club", "")):
                chosen = candidate
                break
        if chosen is None:
            note = (
                f"Club '{club}' niet teruggevonden bij {len(candidates)} kandidaat/kandidaten "
                f"(gevonden clubs: {[c['club'] for c in candidates]}). Eerste resultaat gebruikt "
                "zonder bevestigde club-match - controleer handmatig of dit de juiste speler is."
            )
            chosen = candidates[0]
    else:
        chosen = candidates[0]
        if len(candidates) > 1:
            note = (
                f"{len(candidates)} kandidaten gevonden voor '{name}' "
                f"(clubs: {[c['club'] for c in candidates]}), maar geen club opgegeven om te "
                "disambigueren. Eerste resultaat gebruikt - geef het 'club'-argument mee voor "
                "een zekere match."
            )

    padelstat_id = _click_and_get_padelstat_id(name, chosen["_index"], headless=headless)
    if not padelstat_id:
        return {
            "padelstat_id": None,
            "rating": None,
            "rating_source": "click_failed",
            "matched_name": chosen["name"],
            "matched_club": chosen.get("club", ""),
            "raw_text_snippet": (
                "Kon niet navigeren naar het profiel na het klikken op de kaart "
                f"'{chosen.get('card_text', '')}'."
            ),
        }

    result = fetch_padelstat_rating(padelstat_id, headless=headless)
    result["matched_name"] = chosen["name"]
    result["matched_klassement"] = chosen.get("klassement")
    result["matched_club"] = chosen.get("club", "")
    result["other_candidates"] = [c for c in candidates if c is not chosen]
    if note:
        result["club_disambiguation_note"] = note
    return result
