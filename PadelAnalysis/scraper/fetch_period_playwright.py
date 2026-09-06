# PADEL_ANALYSIS_DEFAULT_PPID_81_FIX
# PADEL_ANALYSIS_PADel_BEFORE_CAPTURE_FIX_V1
"""
fetch_period_playwright.py
Playwright helper voor periode-wisseling op het TVL dashboard.
Geeft per periode de HTML terug; parsing gebeurt via scraper_v2.py.
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
    """Return the padel period <select> element (3rd select with period options)."""
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


def fetch_all_periods_html(
    player_id: str,
    max_periods: Optional[int] = None,
    headless: bool = True,
    delay_between_periods: float = 1.0,
    progress_callback=None,
) -> list[dict]:
    """
    Open player dashboard, iterate over padel periods, capture HTML per period.

    progress_callback(i, total, label, status): optioneel, wordt aangeroepen
    vóór elke periode ("bezig") en erna ("ok"/"empty"/"error"), zodat de UI
    kan tonen waar het scrapen precies staat.

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

            if max_periods is not None:
                all_options = all_options[:max_periods]

            total = len(all_options)
            for i, opt in enumerate(all_options):
                label, value = opt["label"], opt["value"]
                logger.info(f"  [{i+1}/{total}] {label}")
                if progress_callback:
                    progress_callback(i + 1, total, label, "fetching")

                if i > 0:
                    try:
                        padel_select.select_option(value=value, timeout=5000)
                        _wait_after_select(page)
                        _activate_padel_results_tab(page, debug=bool(globals().get('DEBUG', False)))
                        _wait_after_select(page)
                    except Exception as e:
                        logger.error(f"    → selectie FOUT: {e}")
                        results.append({**opt, "html": "", "status": "error", "error": str(e)})
                        if progress_callback:
                            progress_callback(i + 1, total, label, "error")
                        continue

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
