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
BUG (opgelost, destijds): elke klik mislukte omdat een Google Funding Choices
cookie-consent-banner (CSS-klasse "fc-consent-root"/"fc-dialog-overlay") over
de hele pagina lag en alle pointer-events onderschepte. Fix: _dismiss_consent_
banner() sluit de banner (via gangbare knopteksten NL/EN, of desnoods een
JS-verwijdering als fallback) VOOR er iets anders geprobeerd wordt.

PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16 (v6, kritieke
bugfix, gemeld door Kim via diagnose_padelstat_search.py):
BUG (opgelost): de v3-fix uit 2026-09-13 loste het probleem destijds op,
maar bleek NIET robuust tegen twee dingen die zich sindsdien voordeden:
  1. De v3-fix probeerde ELKE knoptekst uit _CONSENT_BUTTON_TEXTS precies
     EENMAAL te klikken, zonder nadien te VERIFIEREN of de banner ook echt
     verdwenen was. Bleek de banner na de klik nog steeds aanwezig (bv. een
     tussentijdse animatie, een tweede laag in de dialoog, of gewoon een net
     ietsje andere render), dan ging de code toch al verder naar
     search_box.click() - wat vervolgens vastliep op exact het probleem uit
     de meldng van Kim: de banner (of specifiek een "Meer informatie"-FAQ-
     knop erin) onderschept alsnog alle pointer-events, tien seconden lang,
     tot Playwright's eigen timeout toeslaat.
  2. Er was geen enkele RETRY-lus: als de eerste dismiss-poging faalde, werd
     er nooit een tweede geprobeerd.
Concreet bewijs uit Kims foutmelding: de click op de ZOEKBALK zelf (niet op
een consent-knop) werd 10+ seconden lang geblokkeerd door
"<button ... aria-label="Meer informatie" class="fc-faq-header
fc-dialog-restricted-content">" en "<div class="fc-dialog-overlay">" - beide
onderdeel van dezelfde fc-consent-root-boom die v3 had moeten sluiten.

Fix, drie onderdelen:
  1. _consent_banner_present(page): controleert EXPLICIET (via page.evaluate)
     of .fc-consent-root nog in de DOM zit - i.p.v. blind aan te nemen dat een
     geklikte knop de banner ook effectief sloot.
  2. _dismiss_consent_banner(page) is herschreven tot een VERIFIERENDE
     retry-lus (tot 4 pogingen, met een korte wachttijd ertussen): na elke
     klikpoging (nu met force=True, om precies het "subtree intercepts
     pointer events"-probleem te omzeilen dat een normale klik blokkeerde)
     wordt gecontroleerd of de banner ECHT weg is via
     _consent_banner_present(). Blijft de banner na alle klikpogingen toch
     hangen, dan volgt een AGRESSIEVERE JS-fallback die niet enkel
     '.fc-consent-root' verwijdert, maar ALLE elementen waarvan de class
     met 'fc-' begint (dekt ook '.fc-dialog-overlay', '.fc-dialog-container',
     enz. - de volledige Funding-Choices-boom - i.p.v. enkel de buitenste
     container).
  3. search_padelstat_player(), _click_and_get_padelstat_id() en
     fetch_padelstat_rating() roepen nu ALLEMAAL _dismiss_consent_banner()
     aan EN wachten nadien expliciet tot de banner weg is (of loggen een
     duidelijke waarschuwing als dat na alle pogingen nog niet lukt) VOOR ze
     een klik op de zoekbalk/pagina proberen. De zoekbalk-klik zelf gebeurt
     nu ook met force=True als allerlaatste vangnet, zodat een eventueel
     onzichtbaar geworden restant van de banner (0px hoog, maar nog in de
     DOM) een geldige klik niet meer kan blokkeren.

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

# PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16: uitgebreide
# lijst met knopteksten (extra NL-varianten toegevoegd t.o.v. v3), want de
# exacte tekst kan per A/B-render van Google Funding Choices verschillen.
_CONSENT_BUTTON_TEXTS = [
    "Alles accepteren", "Accepteren", "Akkoord", "Ik ga akkoord",
    "Alles toestaan", "Toestaan", "Doorgaan", "Aanvaarden", "Alles aanvaarden",
    "Accept all", "I agree", "Agree", "Accept", "OK", "Got it", "Continue",
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

# PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16: hoeveel keer
# we proberen de banner te sluiten voor we het opgeven (met JS-fallback erna).
_CONSENT_DISMISS_ATTEMPTS = 4
_CONSENT_POLL_TIMEOUT_MS = 4000
_CONSENT_POLL_INTERVAL_MS = 250


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


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16
# ---------------------------------------------------------------------------
def _consent_banner_present(page) -> bool:
    """Controleert EXPLICIET of de Funding-Choices-consentbanner nog in de
    DOM aanwezig is (en zichtbaar/met afmetingen, niet enkel technisch
    aanwezig maar al onzichtbaar gemaakt). Dit is de verificatiestap die in
    v3 volledig ontbrak: v3 nam na een klik gewoon aan dat de banner weg was."""
    try:
        return bool(
            page.evaluate(
                """() => {
                    const el = document.querySelector('.fc-consent-root');
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }"""
            )
        )
    except Exception:
        # Kan niet betrouwbaar vaststellen -> conservatief 'nog aanwezig'
        # aannemen, zodat de aanroeper blijft proberen i.p.v. voortijdig
        # verder te gaan.
        return True


def _force_remove_consent_banner(page) -> bool:
    """Agressieve JS-fallback: verwijdert ALLE elementen waarvan de class
    met 'fc-' begint (dekt de volledige Funding-Choices-boom: consent-root,
    dialog-overlay, dialog-container, enz.), niet enkel de buitenste
    container zoals de oorspronkelijke (v3) fallback deed."""
    try:
        removed = page.evaluate(
            """() => {
                const nodes = document.querySelectorAll('[class*="fc-"]');
                let count = 0;
                nodes.forEach(el => { el.remove(); count++; });
                return count;
            }"""
        )
        return bool(removed)
    except Exception:
        return False


def _dismiss_consent_banner(page) -> str:
    """Sluit de cookie-consent-banner, met VERIFICATIE en RETRY.

    PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16: dit is een
    volledige herschrijving t.o.v. v3. In plaats van blind één klik per
    knoptekst te proberen en te hopen dat dat volstond, wordt nu na ELKE
    poging expliciet gecontroleerd (_consent_banner_present) of de banner
    ECHT verdwenen is, met tot _CONSENT_DISMISS_ATTEMPTS pogingen. Klikken
    gebeuren met force=True, omdat het gemelde probleem exact was dat een
    NORMALE klik (die wacht tot een element "stabiel en niet-overlapt" is)
    bleef hangen precies omdat de banner zelf de overlap veroorzaakte -
    force=True negeert die actionability-check bewust.

    Geeft een statusstring terug voor debug-doeleinden."""
    if not _consent_banner_present(page):
        return "geen banner aanwezig (niets te doen)"

    for attempt in range(1, _CONSENT_DISMISS_ATTEMPTS + 1):
        clicked_via = None

        # Spoor 1: knop op de hoofdpagina.
        for text in _CONSENT_BUTTON_TEXTS:
            try:
                btn = page.get_by_role("button", name=re.compile(re.escape(text), re.IGNORECASE))
                if btn.count() > 0:
                    btn.first.click(timeout=3000, force=True)
                    clicked_via = f"knop '{text}' (poging {attempt})"
                    break
            except Exception:
                continue

        # Spoor 2: knop binnen een iframe (sommige CMP's renderen in een
        # apart frame).
        if not clicked_via:
            try:
                for frame in page.frames:
                    for text in _CONSENT_BUTTON_TEXTS:
                        try:
                            btn = frame.get_by_role(
                                "button", name=re.compile(re.escape(text), re.IGNORECASE)
                            )
                            if btn.count() > 0:
                                btn.first.click(timeout=3000, force=True)
                                clicked_via = f"knop '{text}' in iframe (poging {attempt})"
                                break
                        except Exception:
                            continue
                    if clicked_via:
                        break
            except Exception:
                pass

        # Geef de pagina even tijd om de banner effectief te sluiten/animeren.
        try:
            page.wait_for_timeout(_CONSENT_POLL_INTERVAL_MS)
        except Exception:
            pass

        # VERIFICATIE (dit ontbrak in v3): is de banner nu echt weg?
        if not _consent_banner_present(page):
            return clicked_via or f"banner verdween na poging {attempt} (geen klik meer nodig)"

    # Alle klikpogingen uitgeput en de banner zit er nog steeds: agressieve
    # JS-verwijdering van de volledige fc-*-boom, met een korte poll erna.
    _force_remove_consent_banner(page)
    try:
        page.wait_for_timeout(_CONSENT_POLL_INTERVAL_MS)
    except Exception:
        pass

    if not _consent_banner_present(page):
        return f"banner verwijderd via JS-fallback na {_CONSENT_DISMISS_ATTEMPTS} mislukte klikpogingen"

    return (
        f"WAARSCHUWING: banner nog steeds aanwezig na {_CONSENT_DISMISS_ATTEMPTS} "
        "klikpogingen EN een JS-fallback - volgende stap probeert desondanks door te gaan "
        "met force=True op de zoekbalk."
    )


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
            # PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16:
            # verifiërende dismiss (zie functiedocstring hierboven).
            _dismiss_consent_banner(page)
            search_box = page.get_by_placeholder(_CONFIRMED_SEARCH_PLACEHOLDER).first
            # force=True als laatste vangnet: mocht er ondanks alle
            # dismiss-pogingen toch nog een (bijna onzichtbaar) restant van
            # de banner in de DOM hangen, dan negeert force=True de
            # actionability-check die anders opnieuw 10s zou vastlopen.
            search_box.click(timeout=10000, force=True)
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
            search_box.click(timeout=10000, force=True)
            search_box.fill(name)
            page.wait_for_timeout(2000)
            container = page.locator("xpath=//div[@id='search']/following-sibling::div[1]")
            if container.count() == 0:
                return None
            cards = container.first.get_by_role("button")
            if index >= cards.count():
                return None
            cards.nth(index).click(timeout=10000, force=True)
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
