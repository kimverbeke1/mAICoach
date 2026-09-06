# PADEL_ANALYSIS_CLICK_PADEL_AFTER_PERIOD_CHANGE_V4
# PADEL_ANALYSIS_CLICK_PADEL_AFTER_PERIOD_CHANGE_V3
"""
scrape_player.py  â€”  Hoofdorchestrator voor PadelAnalysis

Combineert:
  - fetch_period_playwright.py  : Playwright voor periodeselectie
  - scraper_v2.py               : BeautifulSoup parsing
  - firebase_service.py (root)  : Firestore opslag

Gebruik:
    from scraper.scrape_player import scrape_player, scrape_player_current

    # Huidige periode scrapen (snel, geen Playwright nodig)
    result = scrape_player_current("214435")

    # Alle periodes (of specifieke selectie)
    result = scrape_player("214435")
    result = scrape_player("214435", max_new_periods=3)
    result = scrape_player("214435", force_full_refresh=True)

Data model in Firestore (collection: players, document: player_id):
    {
      player_id, last_updated, scraped_at,
      stats: { total_matches, wins, losses, winrate, tournament_matches, interclub_matches },
      periods_scraped: [...],
      periods_empty: [...],
      periods_failed: [...],
      matches: [
        {
          player_id, period_label, match_type ("tornooi"|"interclub"),
          # tornooi:
          tournament_name, tournament_date_start, tournament_date_end, tournament_week,
          reeks_name, reeks_url, reeks_id, tornooi_id,
          # interclub:
          competition_name, match_date, reeks_name, encounter,
          uitslagenblad_url, spelgroep_id, match_id,
          # gemeenschappelijk:
          partner_name, partner_user_id,
          opp1_name, opp1_user_id, opp1_ranking,
          opp2_name, opp2_user_id, opp2_ranking,
          round_text, result, won, score, scraped_at
        }
      ]
    }
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

# --- path setup so this works when called from project root or scraper/ dir ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scraper_v2 import (
    scrape_current_period as _scrape_current_http,
    parse_tournament_section,
    parse_interclub_section,
    get_padel_periods,
    _utc_now,
)
from fetch_period_playwright import fetch_all_periods_html

# Firebase service â€” lives in project root
sys.path.insert(0, str(_ROOT))
import firebase_service as _fb
import re

logger = logging.getLogger(__name__)

# How many of the most recent periods to always re-scrape (to catch late results)
DEFAULT_REFRESH_RECENT = 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _calc_stats(matches: list[dict]) -> dict:
    won = sum(1 for m in matches if m.get("won") is True)
    lost = sum(1 for m in matches if m.get("won") is False)
    total = len(matches)
    known = won + lost
    return {
        "total_matches": total,
        "wins": won,
        "losses": lost,
        "unknown": total - known,
        "winrate": round(won / known * 100, 1) if known else 0.0,
        "tournament_matches": sum(1 for m in matches if m.get("match_type") == "tornooi"),
        "interclub_matches": sum(1 for m in matches if m.get("match_type") == "interclub"),
    }


def _dedupe(matches: list[dict]) -> list[dict]:
    """Remove duplicate matches by (player_id, period_label, match_type, round_text, score, opp1_user_id)."""
    seen, out = set(), []
    for m in matches:
        key = (
            m.get("player_id"),
            m.get("period_label"),
            m.get("match_type"),
            m.get("round_text"),
            m.get("score"),
            m.get("opp1_user_id"),
            m.get("tournament_name") or m.get("competition_name"),
        )
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def _periods_to_scrape(
    all_periods: list[dict],
    existing_doc: Optional[dict],
    refresh_recent: int,
    force_full: bool,
) -> list[dict]:
    """
    Determine which periods need scraping.

    Rules:
      - force_full=True  â†’ alles
      - geen existing    â†’ alles
      - anders           â†’ laatste `refresh_recent` periodes altijd,
                           plus alle periodes die nog niet eerder verwerkt zijn
    """
    if force_full or existing_doc is None:
        return all_periods

    already_done = set(existing_doc.get("periods_scraped", []))
    recent = all_periods[:refresh_recent]
    not_yet = [p for p in all_periods[refresh_recent:] if p["label"] not in already_done]

    seen, result = set(), []
    for p in recent + not_yet:
        if p["label"] not in seen:
            seen.add(p["label"])
            result.append(p)
    return result


def _merge_matches(existing_doc: Optional[dict], new_matches: list[dict], refreshed_periods: list[str]) -> list[dict]:
    """
    Merge new matches into existing ones.
    Periods that were re-scraped replace their old matches; other periods are kept.
    """
    existing_matches = []
    if existing_doc:
        existing_matches = existing_doc.get("matches", []) or []

    replaced = set(refreshed_periods)
    kept_old = [m for m in existing_matches if m.get("period_label") not in replaced]
    return _dedupe(kept_old + new_matches)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_player_current(player_id: str) -> dict:
    """
    Scrape only the currently active (default) period using HTTP only.
    Fastest option â€” no Playwright, no Firebase read/write.
    Useful for quick checks and testing.
    """
    logger.info(f"[{player_id}] Scraping huidige periode (HTTP only)...")
    return _scrape_current_http(player_id)



# PADEL_ANALYSIS_CLICK_PADEL_TAB_FIX
def _activate_padel_results_tab(page, debug: bool = False) -> bool:
    """Ensure the TVL results page is on the Padel tab, not Tennis enkel.

    TVL opens the results dashboard on tennis results by default for some players.
    If we scrape immediately, recent padel tournament results can be missed.
    This helper clicks the Padel tab/link/button when it is present and waits briefly
    for the JS content to update.
    """
    candidates = [
        lambda: page.get_by_role("tab", name=re.compile(r"^\s*padel\s*$", re.I)).first,
        lambda: page.get_by_role("link", name=re.compile(r"^\s*padel\s*$", re.I)).first,
        lambda: page.get_by_role("button", name=re.compile(r"^\s*padel\s*$", re.I)).first,
        lambda: page.get_by_text("Padel", exact=True).first,
        lambda: page.locator("text=Padel").first,
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
                page.wait_for_timeout(800)
            except Exception:
                pass
            if debug:
                print(f"[padel-tab] Padel tab aangeklikt via methode {idx}")
            return True
        except Exception as e:
            if debug:
                print(f"[padel-tab] methode {idx} mislukt: {e}")
            continue

    if debug:
        print("[padel-tab] Geen Padel tab/link/button gevonden; ga verder met huidige pagina")
    return False


def scrape_player(
    player_id: str,
    max_new_periods: Optional[int] = None,
    force_full_refresh: bool = False,
    refresh_recent: int = DEFAULT_REFRESH_RECENT,
    save_to_firebase: bool = True,
    headless: bool = True,
    delay_between_periods: float = 1.5,
    progress_callback=None,
) -> dict:
    # PADEL_ANALYSIS_REFRESH_LAST_12_MONTHS
    # Incremental refresh should not re-scrape all historical periods.
    # TVL period blocks are roughly half-year ranges, so refreshing the 2 most
    # recent periods covers about the last 12 months while still catching late
    # tournament results added inside an already scraped period.
    if not force_full_refresh:
        refresh_recent = max(int(refresh_recent or 0), 2)

    """
    Full scrape of a player across all (or selected) periods.
    Uses Playwright for period navigation, BeautifulSoup for parsing.
    Optionally saves to Firebase (Firestore).

    Args:
        player_id:            userId from tennisenpadelvlaanderen.be
        max_new_periods:      Max number of NEW periods to scrape this run (None = all)
        force_full_refresh:   If True, re-scrape all periods regardless of history
        refresh_recent:       Always re-scrape this many most-recent periods
        save_to_firebase:     Write result to Firestore
        headless:             Run Playwright headless
        delay_between_periods: Seconds between period fetches
        progress_callback:    optional fn(i, total, label, status) voor live UI-feedback
                               status: "starting" | "discovering" | "fetching" | "parsing" | "ok" | "empty" | "error" | "done"

    Returns:
        Full result dict (same structure as what gets saved to Firebase)
    """
    def _progress(i, total, label, status):
        if progress_callback:
            try:
                progress_callback(i, total, label, status)
            except Exception:
                pass  # feedback mag het scrapen nooit doen crashen

    logger.info(f"[{player_id}] === Start scrape ===")
    scrape_start = _utc_now()
    _progress(0, 0, "Voorbereiden...", "starting")

    # --- Step 1: Load existing data from Firebase ---
    existing_doc = None
    if save_to_firebase and not force_full_refresh:
        try:
            existing_doc = _fb.get_player(player_id)
            if existing_doc:
                existing_count = len(existing_doc.get("matches", []))
                logger.info(f"[{player_id}] Bestaand document: {existing_count} matches")
        except Exception as e:
            logger.warning(f"[{player_id}] Firebase read fout: {e}")

    # --- Step 2: Discover all available periods (HTTP, snel) ---
    import requests
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"})
    _progress(0, 0, "Periodes opzoeken...", "discovering")
    all_periods = get_padel_periods(session, player_id)

    if not all_periods:
        logger.error(f"[{player_id}] Geen periodes gevonden")
        return {"player_id": player_id, "error": "Geen periodes gevonden", "scraped_at": scrape_start}

    logger.info(f"[{player_id}] {len(all_periods)} periodes beschikbaar")

    # --- Step 3: Determine which periods to scrape ---
    to_scrape = _periods_to_scrape(all_periods, existing_doc, refresh_recent, force_full_refresh)
    if max_new_periods is not None:
        to_scrape = to_scrape[:max_new_periods]

    logger.info(f"[{player_id}] {len(to_scrape)} periodes te scrapen: {[p['label'][:30] for p in to_scrape]}")

    if not to_scrape:
        logger.info(f"[{player_id}] Niets te scrapen — alles up-to-date")
        _progress(0, 0, "Al up-to-date", "done")
        existing_matches = existing_doc.get("matches", []) if existing_doc else []
        return {
            "player_id": player_id,
            "scraped_at": scrape_start,
            "status": "up_to_date",
            "periods_available": [p["label"] for p in all_periods],
            "periods_scraped": existing_doc.get("periods_scraped", []) if existing_doc else [],
            "periods_empty": existing_doc.get("periods_empty", []) if existing_doc else [],
            "periods_failed": [],
            "matches": existing_matches,
            "stats": _calc_stats(existing_matches),
        }

    # --- Step 4: Fetch HTML per period via Playwright ---
    period_pages = fetch_all_periods_html(
        player_id,
        max_periods=len(to_scrape),
        headless=headless,
        delay_between_periods=delay_between_periods,
        progress_callback=_progress,
    )

    # Align fetched pages to the periods we wanted
    # fetch_all_periods_html always returns from the first available period,
    # so we re-align by label
    pages_by_label = {p["label"]: p for p in period_pages}

    # --- Step 5: Parse each period ---
    new_matches: list[dict] = []
    scraped_labels: list[str] = []
    empty_labels: list[str] = []
    failed_periods: list[dict] = []

    total_to_parse = len(to_scrape)
    for parse_i, period in enumerate(to_scrape, start=1):
        label = period["label"]
        page_data = pages_by_label.get(label)
        _progress(parse_i, total_to_parse, label, "parsing")

        if page_data is None or not page_data.get("html"):
            logger.warning(f"[{player_id}] Geen HTML voor periode: {label}")
            failed_periods.append({"label": label, "error": "Geen HTML ontvangen"})
            continue

        try:
            soup = BeautifulSoup(page_data["html"], "html.parser")
            t_matches = parse_tournament_section(soup, player_id, label)
            i_matches = parse_interclub_section(soup, player_id, label)
            period_matches = t_matches + i_matches

            if period_matches:
                new_matches.extend(period_matches)
                logger.info(f"[{player_id}]   {label[:45]}: {len(t_matches)}T + {len(i_matches)}IC")
            else:
                empty_labels.append(label)
                logger.info(f"[{player_id}]   {label[:45]}: leeg")

            scraped_labels.append(label)

        except Exception as e:
            logger.error(f"[{player_id}]   Parse fout voor {label}: {e}")
            failed_periods.append({"label": label, "error": str(e)})

    # --- Step 6: Merge with existing data ---
    all_matches = _merge_matches(existing_doc, new_matches, scraped_labels)

    # Merge period metadata with existing
    prev_scraped = set(existing_doc.get("periods_scraped", []) if existing_doc else [])
    prev_empty = set(existing_doc.get("periods_empty", []) if existing_doc else [])

    all_scraped = sorted(prev_scraped | set(scraped_labels),
                         key=lambda l: next((i for i, p in enumerate(all_periods) if p["label"] == l), 999))
    all_empty = sorted(prev_empty | set(empty_labels),
                       key=lambda l: next((i for i, p in enumerate(all_periods) if p["label"] == l), 999))

    # --- Step 7: Build result document ---
    result = {
        "player_id": str(player_id),
        "scraped_at": scrape_start,
        "last_updated": _utc_now(),
        "schema_version": "v2",
        "periods_available": [p["label"] for p in all_periods],
        "periods_scraped": all_scraped,
        "periods_empty": all_empty,
        "periods_failed": [f["label"] for f in failed_periods],
        "periods_failed_detail": failed_periods,
        "scrape_settings": {
            "refresh_recent": refresh_recent,
            "force_full_refresh": force_full_refresh,
            "periods_scraped_this_run": scraped_labels,
        },
        "matches": all_matches,
        "stats": _calc_stats(all_matches),
    }

    # --- Step 8: Save to Firebase ---
    if save_to_firebase:
        try:
            _fb.save_player_v2(player_id, result)
            logger.info(f"[{player_id}] Opgeslagen in Firebase: {len(all_matches)} matches")
        except Exception as e:
            logger.error(f"[{player_id}] Firebase write fout: {e}")
            result["firebase_error"] = str(e)

    logger.info(f"[{player_id}] === Klaar: {result['stats']} ===")
    _progress(total_to_parse, total_to_parse, "Klaar", "done")
    return result


def scrape_players(
    player_ids: list[str],
    **kwargs,
) -> dict[str, dict]:
    """
    Scrape meerdere spelers. Zelfde kwargs als scrape_player().
    Returns dict van player_id -> result.
    """
    results = {}
    for pid in player_ids:
        try:
            results[pid] = scrape_player(pid, **kwargs)
        except Exception as e:
            logger.error(f"[{pid}] Scrape fout: {e}")
            results[pid] = {"player_id": pid, "error": str(e)}
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Scrape padel speler(s)")
    parser.add_argument("player_ids", nargs="+", help="Een of meer userId's")
    parser.add_argument("--full", action="store_true", help="Force volledige refresh")
    parser.add_argument("--max", type=int, default=None, help="Max nieuwe periodes")
    parser.add_argument("--no-firebase", action="store_true", help="Niet opslaan in Firebase")
    parser.add_argument("--show", action="store_true", help="Toon browser (niet headless)")
    parser.add_argument("--out", type=str, default=None, help="JSON output bestand")
    args = parser.parse_args()

    all_results = {}
    for pid in args.player_ids:
        result = scrape_player(
            pid,
            force_full_refresh=args.full,
            max_new_periods=args.max,
            save_to_firebase=not args.no_firebase,
            headless=not args.show,
        )
        all_results[pid] = result
        s = result.get("stats", {})
        print(f"\n[{pid}] {s.get('total_matches',0)} matches "
              f"({s.get('tournament_matches',0)}T + {s.get('interclub_matches',0)}IC), "
              f"winrate={s.get('winrate',0)}%")
        print(f"  Periodes: {len(result.get('periods_scraped',[]))} gescraped, "
              f"{len(result.get('periods_empty',[]))} leeg, "
              f"{len(result.get('periods_failed',[]))} mislukt")

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nOutput: {out_path}")
    elif len(args.player_ids) == 1:
        # Single player: toon eerste 2 matches
        pid = args.player_ids[0]
        matches = all_results[pid].get("matches", [])[:2]
        if matches:
            print(f"\nVoorbeeld matches:")
            print(json.dumps(matches, ensure_ascii=False, indent=2))


