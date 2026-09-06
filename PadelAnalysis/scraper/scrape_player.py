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
    # (sneller — bedoeld voor geautomatiseerde/CI-runs, zie ci_scrape_all.py)
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

# Firebase service — lives in project root
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

def _match_identity(m: dict) -> tuple:
    """
    Stabiele 'identiteit' van een match-slot, GEEN score/resultaat inbegrepen
    (die kunnen legitiem achteraf gecorrigeerd worden door TVL). Twee entries
    met dezelfde identiteit worden beschouwd als "dezelfde wedstrijd" -- de
    meest recent gescrapete versie wint dan, zie _merge_matches().
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
    Rules:
      - force_full=True  → alles
      - geen existing    → alles
      - anders           → laatste `refresh_recent` periodes altijd,
                           PLUS altijd de huidige/meest-recente periode
                           (all_periods[0]) ongeacht refresh_recent,
                           plus alle periodes die nog niet eerder verwerkt zijn.
    PADEL_ANALYSIS_ALWAYS_RECHECK_CURRENT_PERIOD_FIX_2026-09-06:
    BUG (opgelost): met refresh_recent=0 werd voorheen ELKE periode die ooit
    al gescraped is, voorgoed als "klaar" beschouwd -- ook de HUIDIGE, nog
    lopende periode. We forceren daarom nu ALTIJD een her-check van
    all_periods[0] (de huidige/actieve periode), ongeacht refresh_recent of
    already_done.
    """
    if force_full or existing_doc is None:
        return all_periods
    already_done = set(existing_doc.get("periods_scraped", []))
    recent = all_periods[:refresh_recent] if refresh_recent > 0 else []
    current = all_periods[:1]  # de eerste periode = de huidige/actieve (altijd hercheckt)
    not_yet = [p for p in all_periods[refresh_recent:] if p["label"] not in already_done]
    seen, result = set(), []
    for p in recent + current + not_yet:
        if p["label"] not in seen:
            seen.add(p["label"])
            result.append(p)
    return result

def _merge_matches(existing_doc: Optional[dict], new_matches: list[dict]) -> tuple[list[dict], int, int]:
    """
    PADEL_ANALYSIS_UNION_MERGE_FIX_2026-09-06:
    BUG (opgelost): de vorige aanpak verving bij het herscrapen van een
    periode ALLE oude matches van die periode volledig door wat de verse
    parse teruggaf ("kept_old = matches NIET in de herscrapete periodes" +
    "new_matches"). Dit ging FOUT ervan uit dat een verse parse van een
    periode altijd de VOLLEDIGE set matches van die periode teruggeeft.
    Als TVL om welke reden dan ook een KLEINERE/andere subset toont bij een
    volgende scrape (bv. een paginering- of standaardweergavelimiet op de
    resultatenpagina van een periode), gingen eerder gekende matches van
    die periode STILZWIJGEND VERLOREN, ook al meldde de log correct dat er
    "X nieuwe matches gevonden" waren binnen diezelfde periode -- het
    NETTO-resultaat kon daardoor gelijk blijven of zelfs dalen.
    Nieuwe aanpak: UNION in plaats van vervanging. Bestaande matches worden
    NOOIT zomaar weggegooid. Elke match krijgt een stabiele identiteit
    (_match_identity, ZONDER score/resultaat) zodat écht dezelfde wedstrijd
    (bv. bij een latere scorecorrectie door TVL) wel degelijk geüpdatet
    wordt met de nieuwste versie, maar een oudere match die toevallig niet
    meer voorkomt in de nieuwste parse van diezelfde periode blijft gewoon
    bewaard. Dit garandeert dat total_matches bij een normale (niet-force
    volledige) refresh NOOIT kan dalen -- in het slechtste geval blijft het
    gelijk, normaal gezien stijgt het met precies het aantal echt nieuwe
    matches.
    Returns: (merged_matches, previous_total, new_total) -- de twee tellingen
    worden meegegeven zodat de aanroeper duidelijk kan loggen/tonen wat er
    veranderd is.
    """
    existing_matches = []
    if existing_doc:
        existing_matches = existing_doc.get("matches", []) or []
    by_identity: dict = {}
    for m in existing_matches:
        by_identity[_match_identity(m)] = m
    for m in new_matches:
        by_identity[_match_identity(m)] = m  # verse data wint voor exact dezelfde wedstrijd-slot
    merged = _dedupe(list(by_identity.values()))
    return merged, len(existing_matches), len(merged)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def scrape_player_current(player_id: str) -> dict:
    """
    Scrape only the currently active (default) period using HTTP only.
    Fastest option — no Playwright, no Firebase read/write.
    Useful for quick checks and testing.
    """
    logger.info(f"[{player_id}] Scraping huidige periode (HTTP only)...")
    return _scrape_current_http(player_id)

# PADEL_ANALYSIS_CLICK_PADEL_TAB_FIX
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
            "matches_added_this_run": 0,
        }
    # --- Step 4: Fetch HTML per period via Playwright ---
    try:
        period_pages = fetch_all_periods_html(
            player_id,
            max_periods=len(to_scrape),
            headless=headless,
            delay_between_periods=delay_between_periods,
            progress_callback=_progress,
        )
    except Exception as e:
        # PADEL_ANALYSIS_FETCH_EXCEPTION_SAFETY_2026-09-06: deze stap had
        # voorheen GEEN try/except -- een browsercrash/timeout hier liet de
        # volledige scrape_player()-aanroep ongevangen crashen, wat via de
        # achtergrond-thread wel als "mislukt" getoond wordt, maar hier
        # expliciet afvangen geeft een duidelijkere foutmelding en voorkomt
        # verrassingen bij toekomstig hergebruik van deze functie.
        logger.error(f"[{player_id}] Fout bij ophalen periode-HTML (Playwright): {e}")
        return {
            "player_id": player_id,
            "scraped_at": scrape_start,
            "error": f"Fout bij ophalen periode-HTML: {e}",
            "matches": existing_doc.get("matches", []) if existing_doc else [],
            "stats": _calc_stats(existing_doc.get("matches", []) if existing_doc else []),
        }
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
    # --- Step 6: Merge with existing data (UNION, zie _merge_matches) ---
    all_matches, prev_total, new_total = _merge_matches(existing_doc, new_matches)
    delta = new_total - prev_total
    if delta > 0:
        logger.info(f"[{player_id}] Merge: {prev_total} -> {new_total} matches (+{delta} nieuw)")
    elif delta == 0:
        logger.info(f"[{player_id}] Merge: {prev_total} -> {new_total} matches (geen netto wijziging)")
    else:
        # Zou met de union-merge normaal niet meer mogen voorkomen; loggen
        # als het toch gebeurt (bv. echte dubbels die nu pas herkend worden).
        logger.warning(f"[{player_id}] Merge: {prev_total} -> {new_total} matches ({delta})")
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
        "matches_added_this_run": max(0, delta),
        "matches_before_this_run": prev_total,
    }
    # --- Step 8: Save to Firebase ---
    if save_to_firebase:
        try:
            _fb.save_player_v2(player_id, result)
            logger.info(f"[{player_id}] Opgeslagen in Firebase: {len(all_matches)} matches")
            # PADEL_ANALYSIS_VERIFY_WRITE_2026-09-06: onmiddellijke read-back
            # ter controle dat de schrijfactie ECHT is doorgekomen met het
            # verwachte aantal matches -- vangt stille schrijf-/leesfouten
            # op die anders pas veel later (of nooit) zouden opvallen.
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
    parser.add_argument("--missing-only", action="store_true", help="Enkel echt ontbrekende periodes (geen her-check van laatste 2)")
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
