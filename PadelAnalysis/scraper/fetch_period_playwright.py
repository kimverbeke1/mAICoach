# PADEL_ANALYSIS_DEFAULT_PPID_81_FIX
# PADEL_ANALYSIS_PADel_BEFORE_CAPTURE_FIX_V1
"""
fetch_period_playwright.py
Playwright helper voor periode-wisseling op het TVL dashboard.
Geeft per periode de HTML terug; parsing gebeurt via scraper_v2.py.
--------------------------------------------------------------------------
PADEL_ANALYSIS_STALE_SELECT_LOCATOR_FIX_2026-09-21 (op verzoek van Kim, na
een run met speler 1622012: periodes 1-3 lukten, daarna faalden ALLE 13
resterende periodes identiek met "Locator.select_option: Timeout 5000ms
exceeded ... waiting for locator('select').nth(2)")
--------------------------------------------------------------------------
ROOT CAUSE (zeer waarschijnlijk, op basis van het logpatroon): de periode-
select wordt in de oude code precies ÉÉN keer opgezocht, vóór de hele lus
over alle periodes (`padel_select = _get_padel_period_select(page)`).
`_get_padel_period_select()` identificeert de juiste `<select>` weliswaar
op INHOUD (opties met "resultaten van week"), maar het resultaat is nog
steeds een POSITIONELE Locator (Playwright's `.nth(k)`, hier toevallig
overeenkomend met "select".nth(2)) die bij ELKE volgende actie de pagina
OPNIEUW doorzoekt op basis van die vaste index - niet opnieuw op basis van
de oorspronkelijke inhoudsmatch.
In het gemelde geval was periode 3 ("week 27/2025 tot en met week 48/2025")
LEEG (bevestigd verderop in scrape_player.py se log: "... : leeg") - een
lege periode toont vermoedelijk een andere pagina-layout (bv. een "geen
resultaten"-melding die andere filterelementen verbergt/verwijdert),
waardoor het totale aantal `<select>`-elementen op de pagina verschuift.
Zodra dat gebeurt, wijst de vaste `select.nth(2)`-verwijzing niet meer naar
de juiste (of geen enkele) select, en blijft dat voor de REST van de lus zo
- vandaar dat alle 13 overige periodes exact dezelfde timeout gaven: geen
van die pogingen deed ooit een nieuwe poging om de select opnieuw op te
zoeken.
FIX (self-herstellend, twee lagen):
  1. De select wordt voortaan bij ELKE periode OPNIEUW opgezocht
     (`_get_padel_period_select(page)` vlak vóór elke `select_option()`-
     aanroep), i.p.v. één keer helemaal bovenaan de functie. Dit is een
     kleine, goedkope herquery (een handvol `<select>`-elementen) en maakt
     de code robuust tegen ELKE tussentijdse DOM-wijziging, niet enkel het
     specifieke "lege periode"-scenario hierboven.
  2. Als de verse select niet gevonden wordt, of `select_option()` toch
     faalt, wordt ÉÉN volledige "harde herstelpoging" gedaan
     (`_hard_recover()`): de pagina wordt herladen, de Padel-tab opnieuw
     geactiveerd, cookies opnieuw weggeklikt (voor het geval een banner
     terugkeert na herladen), en de select opnieuw gezocht. Lukt dat, dan
     wordt de selectie voor DIE periode opnieuw geprobeerd. Faalt ook dat,
     dan wordt de periode als mislukt gelogd - MAAR de volgende periode in
     de lus krijgt gewoon opnieuw een VERSE poging (stap 1), i.p.v. voort
     te bouwen op een reeds bewezen kapotte toestand. Zo blijft één
     tijdelijk DOM-probleem niet langer alle DAAROPVOLGENDE periodes
     "vergiftigen", zoals in het gemelde geval gebeurde (13 van de 16
     periodes verloren voor een speler die zijn allereerste, volledige
     scrape kreeg).
  Bijkomend voordeel: scrape_player.py se "missing"-boekhouding
  (`periods_scraped`) markeert mislukte periodes sowieso al NIET als
  gedaan, dus een volgende bulk-run zou ze vroeg of laat toch opnieuw
  proberen - maar met deze fix is de kans veel groter dat ze al binnen
  DEZELFDE run alsnog lukken, wat zowel tijd bespaart (geen herhaalde
  bulk-runs nodig) als de speler sneller een volledige, betrouwbare
  historiek geeft.
"""
import time
import logging
from typing import Optional
from playwright.sync_api import sync_playwright
import re

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tennisenpadelvlaanderen.be"
DEFAULT_PADEL_PARAMS = {
    "tab": "padel", "tspid": "80", "tdpid": "80",
    "ppid": "81", "tscid": "80", "pcid": "79",
}


# PADEL_ANALYSIS_FETCH_PERIOD_CLICK_PADEL_FIX
def _activate_padel_results_tab(page, debug: bool = False) -> bool:
    """Force TVL results dashboard to the Padel tab before reading HTML.
    The results dashboard can open on Tennis enkel by default. Period fetching and
    HTML extraction happen in fetch_period_playwright.py, so clicking Padel inside
    scrape_player.py is too late if the HTML is already captured here.
    """
    # JS click first: works even when Padel is a span/li/div styled as a tab.
    try:
        clicked = bool(page.evaluate(r"""
            () => {
                const clean = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const visible = el => {
                    const st = window.getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                };
                const els = Array.from(document.querySelectorAll('a,button,li,span,div,[role="tab"],[role="button"]'))
                    .filter(el => clean(el.innerText || el.textContent) === 'padel' && visible(el));
                if (!els.length) return false;
                const score = el => {
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    const tag = el.tagName.toLowerCase();
                    const cls = (el.className || '').toString().toLowerCase();
                    let s = 0;
                    if (role === 'tab') s += 100;
                    if (tag === 'a' || tag === 'button') s += 80;
                    if (cls.includes('tab') || cls.includes('nav') || cls.includes('active')) s += 50;
                    return s;
                };
                els.sort((a,b) => score(b) - score(a));
                els[0].click();
                return true;
            }
        """))
        if clicked:
            if debug:
                print("[fetch-period/padel] Padel tab clicked via JS")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=2500)
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=2500)
            except Exception:
                pass
            try:
                page.wait_for_timeout(1200)
            except Exception:
                pass
            return True
    except Exception as e:
        if debug:
            print(f"[fetch-period/padel] JS click failed: {e}")
    # Playwright fallbacks.
    candidates = [
        lambda: page.get_by_role("tab", name=re.compile(r"^\s*padel\s*$", re.I)).first,
        lambda: page.get_by_role("link", name=re.compile(r"^\s*padel\s*$", re.I)).first,
        lambda: page.get_by_role("button", name=re.compile(r"^\s*padel\s*$", re.I)).first,
        lambda: page.get_by_text("Padel", exact=True).first,
    ]
    for idx, getter in enumerate(candidates, start=1):
        try:
            loc = getter()
            if loc.count() == 0:
                continue
            loc.click(timeout=2500)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=2500)
            except Exception:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=2500)
            except Exception:
                pass
            try:
                page.wait_for_timeout(1200)
            except Exception:
                pass
            if debug:
                print(f"[fetch-period/padel] Padel tab clicked via fallback {idx}")
            return True
        except Exception as e:
            if debug:
                print(f"[fetch-period/padel] fallback {idx} failed: {e}")
    if debug:
        print("[fetch-period/padel] Padel tab not found")
    return False


def _build_url(player_id: str) -> str:
    qs = "&".join(f"{k}={v}" for k, v in {"userId": player_id, **DEFAULT_PADEL_PARAMS}.items())
    return f"{BASE_URL}/dashboard/resultaten?{qs}"


def _dismiss_cookies(page):
    for txt in ["Alle cookies accepteren", "Cookies accepteren", "Accepteren"]:
        try:
            loc = page.get_by_text(txt, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=2000)
                page.wait_for_timeout(800)
                return
        except Exception:
            pass


def _get_padel_period_select(page):
    """Return the padel period <select> element (3rd select with period options).
    PADEL_ANALYSIS_STALE_SELECT_LOCATOR_FIX_2026-09-21: LET OP - dit geeft
    een POSITIONELE Locator terug die bij een volgende actie de pagina
    OPNIEUW doorzoekt op basis van de HUIDIGE DOM. Roep deze functie daarom
    altijd VLAK VOOR een actie opnieuw aan i.p.v. het resultaat lang vast te
    houden over meerdere periode-wissels heen (zie fetch_all_periods_html)."""
    period_selects = []
    for sel in page.locator("select").all():
        try:
            opts = sel.locator("option").all()
            if any("resultaten van week" in (o.text_content() or "").lower() for o in opts):
                period_selects.append(sel)
        except Exception:
            pass
    return period_selects[2] if len(period_selects) >= 3 else (period_selects[-1] if period_selects else None)


def _get_period_options(page, padel_select) -> list[dict]:
    """Extract all period options from the padel select."""
    options = []
    for o in padel_select.locator("option").all():
        try:
            label = (o.text_content() or "").strip()
            value = page.evaluate("(o) => o.value", o.element_handle())
            if "resultaten van week" in label.lower():
                options.append({"label": label, "value": value})
        except Exception:
            pass
    return options


def _wait_after_select(page, timeout_ms: int = 10000):
    """Wait for network to settle after period selection."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(1500)


def _hard_recover(page, url: str, debug: bool = False):
    """PADEL_ANALYSIS_STALE_SELECT_LOCATOR_FIX_2026-09-21: volledige reset
    van de pagina (herladen + Padel-tab heractiveren + cookies opnieuw
    wegklikken) wanneer een verse select-poging toch mislukt is. Geeft de
    NIEUW gevonden select-Locator terug, of None als dat ook na deze reset
    niet lukt (bv. de site zelf ligt eruit)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        if debug:
            print(f"[fetch-period/recover] herladen mislukt: {e}")
        return None
    _activate_padel_results_tab(page, debug=debug)
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass
    _dismiss_cookies(page)
    _activate_padel_results_tab(page, debug=debug)
    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass
    return _get_padel_period_select(page)


def fetch_all_periods_html(
    player_id: str,
    max_periods: Optional[int] = None,
    target_labels: Optional[list[str]] = None,
    headless: bool = True,
    delay_between_periods: float = 1.0,
    progress_callback=None,
) -> list[dict]:
    """
    Open player dashboard, iterate over padel periods, capture HTML per period.
    progress_callback(i, total, label, status): optioneel, wordt aangeroepen
    vóór elke periode ("bezig") en erna ("ok"/"empty"/"error"), zodat de UI
    kan tonen waar het scrapen precies staat.
    Args:
        max_periods:    (legacy gedrag) als target_labels niet gegeven is,
                         worden enkel de eerste `max_periods` opties uit de
                         dropdown genomen, IN DROPDOWN-VOLGORDE. Dit gaat
                         ervan uit dat de gewenste periodes toevallig de
                         eerste N in de dropdown zijn -- correct voor "de
                         N meest recente periodes", FOUT zodra een specifieke,
                         mogelijk niet-recente periode nodig is (zie bug
                         hieronder).
        target_labels:  PADEL_ANALYSIS_TARGET_LABEL_FIX (2026-09-07) — als
                         gegeven, worden ENKEL dropdown-opties bezocht wiens
                         label exact overeenkomt met een van deze labels,
                         ongeacht hun positie in de dropdown. Dit lost een
                         reële bug op: scrape_player.py bepaalt via HTTP
                         (get_padel_periods) welke periode-LABELS ontbreken,
                         maar die lijst kan in een andere volgorde staan dan
                         (of periodes bevatten die niet aan het begin staan
                         van) de Playwright-dropdown hier. De oude
                         `max_periods`-aanpak nam simpelweg "de eerste N
                         dropdown-opties" en negeerde volledig WELKE labels
                         er effectief gevraagd waren, wat bij scrape_player's
                         strict_missing_only-modus (enkel echt ontbrekende,
                         niet per se recente periodes) tot het ophalen van de
                         VERKEERDE periode leidde.
    Returns list of:
        {"label": str, "value": str, "html": str, "status": "ok"|"empty"|"error"}
    """
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"
        ).new_page()
        try:
            url = _build_url(player_id)
            logger.info(f"Opening: {url}")
            if progress_callback:
                progress_callback(0, 0, "Pagina openen...", "starting")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            _activate_padel_results_tab(page, debug=bool(globals().get('DEBUG', False)))
            page.wait_for_timeout(3000)
            _dismiss_cookies(page)
            _activate_padel_results_tab(page, debug=bool(globals().get('DEBUG', False)))
            padel_select = _get_padel_period_select(page)
            if padel_select is None:
                logger.error("Geen padel period select gevonden")
                return results
            all_options = _get_period_options(page, padel_select)
            logger.info(f"  {len(all_options)} periodes gevonden")
            if target_labels is not None:
                # PADEL_ANALYSIS_TARGET_LABEL_FIX: filter op EXACT label-match,
                # behoud dropdown-volgorde voor de resterende (gefilterde) opties.
                target_set = set(target_labels)
                all_options = [o for o in all_options if o["label"] in target_set]
                found_labels = {o["label"] for o in all_options}
                missing = target_set - found_labels
                if missing:
                    logger.warning(f"  Gevraagde periode(s) niet gevonden in dropdown: {sorted(missing)}")
            elif max_periods is not None:
                all_options = all_options[:max_periods]
            total = len(all_options)
            for i, opt in enumerate(all_options):
                label, value = opt["label"], opt["value"]
                logger.info(f"  [{i+1}/{total}] {label}")
                if progress_callback:
                    progress_callback(i + 1, total, label, "fetching")
                # PADEL_ANALYSIS_TARGET_LABEL_FIX: bij target_labels ALTIJD
                # expliciet selecteren, ook bij i==0. De oude code sloeg de
                # selectie bij i==0 over, in de veronderstelling dat de
                # pagina na het laden toevallig al op de juiste (=eerste
                # gevraagde) periode stond. Dat klopt enkel wanneer we
                # simpelweg "de eerste N dropdown-opties" willen; zodra we
                # een SPECIFIEKE periode nodig hebben (target_labels), is de
                # paginadefault na het laden niet noodzakelijk die periode.
                needs_explicit_select = (i > 0) or (target_labels is not None)
                if needs_explicit_select:
                    # PADEL_ANALYSIS_STALE_SELECT_LOCATOR_FIX_2026-09-21: zie
                    # module-docstring. Elke periode krijgt hier een VERSE
                    # select-resolutie i.p.v. de ene, bovenaan de functie
                    # berekende `padel_select` te blijven hergebruiken - dat
                    # was de kern van het "select nth(2) timeout"-probleem
                    # dat na één lege periode ALLE resterende periodes liet
                    # falen.
                    fresh_select = _get_padel_period_select(page)
                    select_ok = False
                    last_error: Optional[Exception] = None
                    if fresh_select is not None:
                        try:
                            fresh_select.select_option(value=value, timeout=5000)
                            select_ok = True
                        except Exception as e:
                            last_error = e
                    else:
                        last_error = RuntimeError("periode-select niet gevonden op de pagina")
                    if not select_ok:
                        # Eén volledige, harde herstelpoging: herladen +
                        # Padel-tab heractiveren + select opnieuw zoeken.
                        # Lukt DIE poging, dan wordt de selectie voor deze
                        # periode alsnog geprobeerd i.p.v. de periode meteen
                        # als mislukt te boeken.
                        logger.warning(
                            f"    → selectie mislukt ({last_error}); pagina wordt herladen voor "
                            "een herstelpoging..."
                        )
                        recovered_select = _hard_recover(
                            page, url, debug=bool(globals().get('DEBUG', False)),
                        )
                        if recovered_select is not None:
                            try:
                                recovered_select.select_option(value=value, timeout=5000)
                                select_ok = True
                            except Exception as e:
                                last_error = e
                        else:
                            last_error = RuntimeError(
                                "periode-select ook na herladen niet gevonden"
                            )
                    if not select_ok:
                        logger.error(f"    → selectie FOUT (ook na herstelpoging): {last_error}")
                        results.append({**opt, "html": "", "status": "error", "error": str(last_error)})
                        if progress_callback:
                            progress_callback(i + 1, total, label, "error")
                        # BELANGRIJK: geen `continue` op een kapotte, blijvend
                        # herbruikte select-referentie - de VOLGENDE periode
                        # in de lus start opnieuw met een VERSE resolutiepoging
                        # (zie hierboven), dus dit ene mislukte geval "vergiftigt"
                        # de rest van de lus niet langer.
                        continue
                    _wait_after_select(page)
                    _activate_padel_results_tab(page, debug=bool(globals().get('DEBUG', False)))
                    _wait_after_select(page)
                _activate_padel_results_tab(page, debug=bool(globals().get('DEBUG', False)))
                html = page.content()
                results.append({**opt, "html": html, "status": "ok"})
                logger.info(f"    → html captured ({len(html)} bytes)")
                if progress_callback:
                    progress_callback(i + 1, total, label, "ok")
                if i < len(all_options) - 1:
                    time.sleep(delay_between_periods)
        finally:
            page.context.browser.close()
    return results


if __name__ == "__main__":
    import json
    from pathlib import Path
    from bs4 import BeautifulSoup
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from scraper_v2 import parse_tournament_section, parse_interclub_section
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Test: eerste 5 periodes voor speler 214435...")
    pages = fetch_all_periods_html("214435", max_periods=5, headless=True)
    all_matches = []
    for p in pages:
        if not p["html"]:
            print(f"  {p['label'][:55]}: FOUT")
            continue
        soup = BeautifulSoup(p["html"], "html.parser")
        t = parse_tournament_section(soup, "214435", p["label"])
        ic = parse_interclub_section(soup, "214435", p["label"])
        all_matches.extend(t + ic)
        print(f"  {p['label'][:55]}: {len(t)} tornooi + {len(ic)} interclub")
    print(f"\nTotaal: {len(all_matches)} matches")
    out = Path(__file__).parent.parent / "debug_output_v2" / "test_multiperiod_214435.json"
    out.write_text(json.dumps(all_matches, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Output: {out}")
