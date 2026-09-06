# PADEL_ANALYSIS_CLICK_PADEL_AFTER_PERIOD_CHANGE_V4
# PADEL_ANALYSIS_CLICK_PADEL_AFTER_PERIOD_CHANGE_V3
"""
scrape_player.py  —  Hoofdorchestrator voor PadelAnalysis
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
    # Enkel ontbrekende periodes, GEEN her-check van de laatste 2 periodes
    result = scrape_player("214435", refresh_recent=0, strict_missing_only=True)
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
          tournament_name, tournament_date_start, tournament_date_end, tournament_week,
          reeks_name, reeks_url, reeks_id, tornooi_id,
          competition_name, match_date, encounter,
          uitslagenblad_url, spelgroep_id, match_id,
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

sys.path.insert(0, str(_ROOT))
import firebase_service as _fb
import re

logger = logging.getLogger(__name__)

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


def _match_identity(m: dict) -> tuple:
    """
    Stabiele 'identiteit' van een match-slot, GEEN score/resultaat inbegrepen
    (die kunnen legitiem achteraf gecorrigeerd worden door TVL).
    """
    return (
        m.get("player_id"),
        m.get("period_label"),
        m.get("match_type"),
        m.get("round_text"),
        m.get("opp1_user_id"),
        m.get("opp2_user_id"),
        m.get("tournament_name") or m.get("competition_name"),
    )


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

    PADEL_ANALYSIS_CURRENT_PERIOD_DETECTION_FIX (deze beurt):
    BUG (opgelost, tweede poging): de vorige fix nam aan dat all_periods[0]
    altijd de huidige/actieve periode is ("eerste periode = huidige"). Die
    aanname is NOOIT rechtstreeks tegen de live website geverifieerd, en is
    de meest waarschijnlijke verklaring waarom nieuw gevonden matchen (bv.
    bij Stijn Mortier, en bij je eigen profiel) bleven "verdwijnen": als TVL
    de dropdown in een andere volgorde toont dan verondersteld, werd
    stelselmatig de VERKEERDE (oude, allang volledig afgeronde) periode
    herchecked, terwijl de werkelijk huidige periode -- eenmaal in
    periods_scraped beland na de allereerste (force_full) scrape -- nooit
    meer opnieuw bekeken werd.
    Nieuwe, betrouwbare aanpak: scraper_v2.get_padel_periods() geeft nu per
    periode een 'selected': bool mee, rechtstreeks afgelezen van het HTML
    'selected'-attribuut op de <option>-tag -- dit is de website's EIGEN
    aanduiding van de actief getoonde periode, geen gok over volgorde meer.
    We herchecken nu altijd de periode(s) die als 'selected' gemarkeerd
    staan; enkel als geen enkele optie 'selected' blijkt (onverwacht/
    afwijkende pagina-structuur) vallen we terug op index 0 als laatste
    redmiddel.
    """
    if force_full or existing_doc is None:
        return all_periods
    already_done = set(existing_doc.get("periods_scraped", []))
    recent = all_periods[:refresh_recent] if refresh_recent > 0 else []
    current = [p for p in all_periods if p.get("selected")]
    if not current and all_periods:
        current = all_periods[:1]  # laatste redmiddel, enkel als 'selected' nergens gevonden werd
    not_yet = [p for p in all_periods[refresh_recent:] if p["label"] not in already_done]
    seen, result = set(), []
    for p in recent + current + not_yet:
        if p["label"] not in seen:
            seen.add(p["label"])
            result.append(p)
    return result


def _merge_matches(existing_doc: Optional[dict], new_matches: list[dict]) -> tuple[list[dict], int, int]:
    """
    UNION-merge: bestaande matches worden nooit zomaar weggegooid. Elke
    match krijgt een stabiele identiteit (zonder score) zodat een verse
    versie van DEZELFDE wedstrijd de oude overschrijft, maar een oudere
    match die toevallig niet meer in de nieuwste parse voorkomt gewoon
    bewaard blijft. Garandeert dat total_matches bij een normale refresh
    nooit kan dalen.
    Returns: (merged_matches, previous_total, new_total)
    """
    existing_matches = []
    if existing_doc:
        existing_matches = existing_doc.get("matches", []) or []
    by_identity: dict = {}
    for m in existing_matches:
        by_identity[_match_identity(m)] = m
    for m in new_matches:
        by_identity[_match_identity(m)] = m
    merged = _dedupe(list(by_identity.values()))
    return merged, len(existing_matches), len(merged)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_player_current(player_id: str) -> dict:
    """Scrape only the currently active (default) period using HTTP only."""
    logger.info(f"[{player_id}] Scraping huidige periode (HTTP only)...")
    return _scrape_current_http(player_id)


def _activate_padel_results_tab(page, debug: bool = False) -> bool:
    """Ensure the TVL results page is on the Padel tab, not Tennis enkel."""
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
    strict_missing_only: bool = False,
) -> dict:
    """
    Full scrape of a player across all (or selected) periods.
    Zie module-docstring voor het volledige datamodel.
    """
    if not force_full_refresh:
        if strict_missing_only:
            refresh_recent = int(refresh_recent or 0)
        else:
            refresh_recent = max(int(refresh_recent or 0), 2)

    def _progress(i, total, label, status):
        if progress_callback:
            try:
                progress_callback(i, total, label, status)
            except Exception:
                pass

    logger.info(f"[{player_id}] === Start scrape ===")
    scrape_start = _utc_now()
    _progress(0, 0, "Voorbereiden...", "starting")
    existing_doc = None
    if save_to_firebase and not force_full_refresh:
        try:
            existing_doc = _fb.get_player(player_id)
            if existing_doc:
                existing_count = len(existing_doc.get("matches", []))
                logger.info(f"[{player_id}] Bestaand document: {existing_count} matches")
        except Exception as e:
            logger.warning(f"[{player_id}] Firebase read fout: {e}")

    import requests
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"})
    _progress(0, 0, "Periodes opzoeken...", "discovering")
    all_periods = get_padel_periods(session, player_id)
    if not all_periods:
        logger.error(f"[{player_id}] Geen periodes gevonden")
        return {"player_id": player_id, "error": "Geen periodes gevonden", "scraped_at": scrape_start}
    logger.info(f"[{player_id}] {len(all_periods)} periodes beschikbaar")
    n_selected = sum(1 for p in all_periods if p.get("selected"))
    if n_selected == 0:
        logger.warning(
            f"[{player_id}] Geen enkele periode gemarkeerd als 'selected' in de HTML — "
            f"val terug op index 0 als aanname voor de huidige periode."
        )
    elif n_selected > 1:
        logger.warning(f"[{player_id}] {n_selected} periodes gemarkeerd als 'selected' (onverwacht) — allemaal meegenomen.")

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
            "matches_added_this_run": 0,
        }

    try:
        period_pages = fetch_all_periods_html(
            player_id,
            max_periods=len(to_scrape),
            headless=headless,
            delay_between_periods=delay_between_periods,
            progress_callback=_progress,
        )
    except Exception as e:
        logger.error(f"[{player_id}] Fout bij ophalen periode-HTML (Playwright): {e}")
        return {
            "player_id": player_id,
            "scraped_at": scrape_start,
            "error": f"Fout bij ophalen periode-HTML: {e}",
            "matches": existing_doc.get("matches", []) if existing_doc else [],
            "stats": _calc_stats(existing_doc.get("matches", []) if existing_doc else []),
        }

    pages_by_label = {p["label"]: p for p in period_pages}
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

    all_matches, prev_total, new_total = _merge_matches(existing_doc, new_matches)
    delta = new_total - prev_total
    if delta > 0:
        logger.info(f"[{player_id}] Merge: {prev_total} -> {new_total} matches (+{delta} nieuw)")
    elif delta == 0:
        logger.info(f"[{player_id}] Merge: {prev_total} -> {new_total} matches (geen netto wijziging)")
    else:
        logger.warning(f"[{player_id}] Merge: {prev_total} -> {new_total} matches ({delta})")

    prev_scraped = set(existing_doc.get("periods_scraped", []) if existing_doc else [])
    prev_empty = set(existing_doc.get("periods_empty", []) if existing_doc else [])
    all_scraped = sorted(prev_scraped | set(scraped_labels),
                         key=lambda l: next((i for i, p in enumerate(all_periods) if p["label"] == l), 999))
    all_empty = sorted(prev_empty | set(empty_labels),
                       key=lambda l: next((i for i, p in enumerate(all_periods) if p["label"] == l), 999))

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
        "matches_added_this_run": max(0, delta),
        "matches_before_this_run": prev_total,
    }

    if save_to_firebase:
        try:
            _fb.save_player_v2(player_id, result)
            logger.info(f"[{player_id}] Opgeslagen in Firebase: {len(all_matches)} matches")
            try:
                verify_doc = _fb.get_player(player_id)
                verify_count = len((verify_doc or {}).get("matches", []))
                if verify_count != len(all_matches):
                    warn_msg = (
                        f"Verificatie na opslaan toont {verify_count} matches, "
                        f"verwacht {len(all_matches)}."
                    )
                    logger.error(f"[{player_id}] {warn_msg}")
                    result["verify_warning"] = warn_msg
                else:
                    logger.info(f"[{player_id}] Verificatie OK: {verify_count} matches bevestigd in Firestore.")
            except Exception as e:
                logger.warning(f"[{player_id}] Verificatie-read mislukt (niet kritiek): {e}")
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
    """Scrape meerdere spelers. Zelfde kwargs als scrape_player()."""
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
    parser.add_argument("--missing-only", action="store_true", help="Enkel echt ontbrekende periodes")
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
            refresh_recent=0 if args.missing_only else DEFAULT_REFRESH_RECENT,
            strict_missing_only=args.missing_only,
        )
        all_results[pid] = result
        s = result.get("stats", {})
        print(f"\n[{pid}] {s.get('total_matches',0)} matches "
              f"({s.get('tournament_matches',0)}T + {s.get('interclub_matches',0)}IC), "
              f"winrate={s.get('winrate',0)}%")
        print(f"  Periodes: {len(result.get('periods_scraped',[]))} gescraped, "
              f"{len(result.get('periods_empty',[]))} leeg, "
              f"{len(result.get('periods_failed',[]))} mislukt")
        print(f"  Nieuw deze run: +{result.get('matches_added_this_run', 0)} matches")
    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nOutput: {out_path}")
    elif len(args.player_ids) == 1:
        pid = args.player_ids[0]
        matches = all_results[pid].get("matches", [])[:2]
        if matches:
            print(f"\nVoorbeeld matches:")
            print(json.dumps(matches, ensure_ascii=False, indent=2))
