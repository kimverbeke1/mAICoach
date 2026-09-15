# PADEL_ANALYSIS_BOARD_IDENTITY_FIX_2026-09-15
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

    result = scrape_player_current("214435")
    result = scrape_player("214435")
    result = scrape_player("214435", max_new_periods=3)
    result = scrape_player("214435", force_full_refresh=True)
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
    find_current_period_by_date,
    _utc_now,
)
from fetch_period_playwright import fetch_all_periods_html

sys.path.insert(0, str(_ROOT))
import firebase_service as _fb
import re

logger = logging.getLogger(__name__)

DEFAULT_REFRESH_RECENT = 2

# Bij een volledige herscrape (--full) mag maximaal dit aandeel van de
# gevraagde periodes mislukken; daarboven wordt er NIETS weggeschreven.
# Zie PADEL_ANALYSIS_FULL_REFRESH_ABORT_GUARD_2026-09-15.
MAX_FAILED_PERIOD_RATIO = 0.25


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


def _norm(value) -> str:
    """Normaliseer een naam/tekst tot een vergelijkbare sleutel."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


# PADEL_ANALYSIS_BOARD_IDENTITY_FIX_2026-09-15
# BUG (opgelost): "Merge: 39 -> 21 matches (-18)" terwijl de nieuw gescrapete
# periode LEEG was. Een merge die niets toevoegt kan onmogelijk matches
# verliezen -- tenzij de dedupe bestaande matches samenvouwt.
#
# Root cause: _match_identity() gebruikte match_id als VOLLEDIGE identiteit:
#     if match_id: return ("match_id", str(match_id))
# Maar op TVL deelt EEN INTERCLUB-ONTMOETING hetzelfde match_id over AL haar
# borden (Dubbel 1, Dubbel 2, Dubbel 3, ...). Het uitslagenblad is immers
# per ontmoeting, niet per bord. Alle borden van dezelfde ontmoeting kregen
# dus dezelfde identiteit en _dedupe() hield er exact EEN over.
#
# Dit is exact dezelfde fout die eerder al tweemaal is opgelost:
#   - "winrate met partner 0%"  -> partner toegevoegd aan de dedupe-sleutel
#   - "slechts 2 spelers in vorige lineup" (reconstruct_boards) -> spelers
#     toegevoegd aan de sleutel
# ... maar ze stond hier nog in de merge zelf, waar ze het meeste schade doet:
# de matches verdwijnen uit het document en de stats/winrates worden op de
# uitgedunde set berekend.
#
# Fix: match_id blijft de STABIELE ANKER, maar de identiteit wordt aangevuld
# met de velden die borden binnen dezelfde ontmoeting onderscheiden:
# round_text, partner en de twee tegenstanders. De score blijft bewust BUITEN
# de identiteit, zodat een latere correctie van de score dezelfde wedstrijd
# blijft updaten i.p.v. te dupliceren.
#
# Idem voor de spelgroep-fallback: ("spelgroep", player_id, spelgroep_id) was
# nog grover -- dat vouwde ALLE matches van een hele spelgroep samen tot een.
def _board_discriminator(m: dict) -> tuple:
    """Velden die twee borden BINNEN dezelfde ontmoeting onderscheiden.

    Bewust zonder score: een gecorrigeerde score mag geen duplicaat maken."""
    return (
        _norm(m.get("round_text")),
        _norm(m.get("partner_user_id") or m.get("partner_name")),
        _norm(m.get("opp1_user_id") or m.get("opp1_name")),
        _norm(m.get("opp2_user_id") or m.get("opp2_name")),
    )


def _match_identity(m: dict) -> tuple:
    """Stabiele, per-WEDSTRIJD (per bord) unieke identiteit.

    match_id / spelgroep_id identificeren de ONTMOETING, niet het bord; ze
    worden daarom altijd gecombineerd met _board_discriminator()."""
    match_id = m.get("match_id")
    if match_id:
        return ("match_id", str(match_id), str(m.get("player_id")), *_board_discriminator(m))

    spelgroep_id = m.get("spelgroep_id")
    if spelgroep_id:
        return (
            "spelgroep",
            str(m.get("player_id")),
            str(spelgroep_id),
            _norm(m.get("match_date")),
            _norm(m.get("encounter")),
            *_board_discriminator(m),
        )

    return (
        "compound",
        m.get("player_id"),
        m.get("period_label"),
        m.get("match_type"),
        m.get("competition_name") or m.get("tournament_name"),
        m.get("match_date") or m.get("tournament_date_start"),
        m.get("encounter"),
        m.get("reeks_id"),
        m.get("tornooi_id"),
        m.get("round_text"),
        m.get("opp1_user_id"),
        m.get("opp2_user_id"),
        # Namen + score enkel als laatste onderscheidende factoren voor het
        # geval user_id's ontbreken of identiek zijn tussen twee borden.
        m.get("opp1_name"),
        m.get("opp2_name"),
        m.get("score"),
    )


def _dedupe(matches: list[dict]) -> list[dict]:
    """Dedupe op exact dezelfde sterke identiteit als _match_identity, zodat
    de dedupe-stap nooit strenger (en dus foutief samenvoegend) is dan de
    merge-identiteit zelf."""
    seen, out = set(), []
    for m in matches:
        key = _match_identity(m)
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

    De huidige/actieve periode wordt bepaald via echte datumvergelijking
    (scraper_v2.find_current_period_by_date), onafhankelijk van website-
    sessie/portlet-eigenaardigheden. Die periode wordt altijd herchecked,
    plus (bij niet-strict) de laatste `refresh_recent` periodes, plus alle
    periodes die nog nooit gescraped zijn.
    """
    if force_full or existing_doc is None:
        return all_periods

    already_done = set(existing_doc.get("periods_scraped", []))
    recent = all_periods[:refresh_recent] if refresh_recent > 0 else []

    current_period = find_current_period_by_date(all_periods)
    current = [current_period] if current_period else (all_periods[:1] if all_periods else [])

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
    match krijgt een stabiele identiteit (zie _match_identity) zodat een
    verse versie van DEZELFDE wedstrijd de oude overschrijft, maar twee
    aparte wedstrijden nooit meer als een worden gezien (zie
    PADEL_ANALYSIS_BOARD_IDENTITY_FIX_2026-09-15).

    VANGNET: een union-merge kan per definitie nooit minder resultaten
    opleveren dan er bestaande matches waren. Gebeurt dat toch, dan is de
    identiteitsfunctie te grof en zouden we stilletjes historiek weggooien.
    In dat geval behouden we de bestaande matches ongemoeid en loggen we een
    expliciete fout, zodat het probleem zichtbaar wordt i.p.v. dataverlies.

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

    if len(merged) < len(existing_matches):
        verloren = len(existing_matches) - len(merged)
        logger.error(
            f"MERGE-VANGNET: union-merge zou {verloren} bestaande match(es) laten "
            f"verdwijnen ({len(existing_matches)} -> {len(merged)}). Dat kan niet "
            f"kloppen bij een union; de match-identiteit is te grof. Bestaande "
            f"matches worden behouden."
        )
        behouden: dict = {}
        for m in existing_matches:
            behouden[_match_identity(m)] = m
        for m in merged:
            behouden.setdefault(_match_identity(m), m)
        merged = list(behouden.values())
        if len(merged) < len(existing_matches):
            merged = list(existing_matches)

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

    current_via_date = find_current_period_by_date(all_periods)
    if current_via_date:
        logger.info(f"[{player_id}] Huidige periode (via datumvergelijking): {current_via_date['label']}")
    else:
        logger.warning(f"[{player_id}] Kon geen enkel periode-label parsen naar een datumbereik — val terug op index 0.")

    to_scrape = _periods_to_scrape(all_periods, existing_doc, refresh_recent, force_full_refresh)

    if max_new_periods is not None:
        to_scrape = to_scrape[:max_new_periods]

    target_labels = [p["label"] for p in to_scrape]
    logger.info(f"[{player_id}] {len(to_scrape)} periodes te scrapen: {[l[:30] for l in target_labels]}")

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

    # PADEL_ANALYSIS_TARGET_LABEL_FIX (DEFINITIEVE fix van "verversen vindt
    # nieuwe matchen niet"):
    # BUG (opgelost): deze aanroep gebruikte voorheen max_periods=len(to_scrape),
    # wat fetch_all_periods_html deed vertrouwen op "neem simpelweg de eerste N
    # dropdown-opties, IN DROPDOWN-VOLGORDE". Dat werkte toevallig voor een
    # volledige herscrape (alle periodes = alle dropdown-opties), maar FAALDE
    # in strict_missing_only/"missing"-modus: daar wordt vaak maar 1 specifieke
    # periode gevraagd (de huidige, correct bepaald via datumvergelijking),
    # maar max_periods=1 pakte blind de EERSTE dropdown-optie -- die niet
    # noodzakelijk de gevraagde is -> label-mismatch -> "Geen HTML voor periode"
    # -> 0 nieuwe matchen, ook al staan ze wel degelijk op de site.
    # fetch_period_playwright.py ondersteunt sinds 2026-09-07 een
    # `target_labels`-parameter die ENKEL de dropdown-opties bezoekt wiens
    # label exact overeenkomt met een gevraagd label, ongeacht positie.
    try:
        period_pages = fetch_all_periods_html(
            player_id,
            target_labels=target_labels,
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

    # PADEL_ANALYSIS_FULL_REFRESH_ABORT_GUARD_2026-09-15
    # Bij force_full_refresh wordt existing_doc NIET gelezen, dus het
    # MERGE-VANGNET in _merge_matches() heeft geen baseline en doet niets:
    # de merge begint altijd vanaf 0. De enige bescherming is dan de write
    # guard in firebase_service, en die is te grof -- die vergelijkt enkel
    # totalen. Bij een GEDEELTELIJK mislukte full refresh (bv. 8 van de 16
    # periodes) kan een te kleine maar "groot genoeg" ogende set er gewoon
    # doorglippen en de historiek uitdunnen.
    #
    # Daarom: bij een volledige herscrape breken we af zodra er te veel
    # periodes mislukt zijn. Beter geen update dan een halve.
    if force_full_refresh and to_scrape:
        mislukt = len(failed_periods)
        gevraagd = len(to_scrape)
        ratio = mislukt / gevraagd if gevraagd else 0.0
        if mislukt and ratio > MAX_FAILED_PERIOD_RATIO:
            msg = (
                f"Volledige herscrape AFGEBROKEN: {mislukt} van de {gevraagd} "
                f"periodes mislukt ({ratio:.0%} > {MAX_FAILED_PERIOD_RATIO:.0%}). "
                f"Er wordt NIETS weggeschreven, om te vermijden dat een "
                f"onvolledige scrape de bestaande historiek overschrijft. "
                f"Draai opnieuw wanneer de site/verbinding stabiel is."
            )
            logger.error(f"[{player_id}] {msg}")
            _progress(0, 0, "Afgebroken", "aborted")

            # Lees het bestaande document enkel om het ONGEWIJZIGD terug te
            # geven aan de aanroeper (we schrijven niet).
            try:
                safe_doc = _fb.get_player(player_id) or {}
            except Exception:  # noqa: BLE001
                safe_doc = {}
            safe_matches = safe_doc.get("matches", []) or []

            return {
                "player_id": str(player_id),
                "scraped_at": scrape_start,
                "status": "aborted_incomplete_full_refresh",
                "error": msg,
                "periods_failed": [f["label"] for f in failed_periods],
                "periods_failed_detail": failed_periods,
                "periods_scraped_this_run": scraped_labels,
                "matches": safe_matches,
                "stats": _calc_stats(safe_matches),
                "matches_added_this_run": 0,
            }

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

                    # De write guard in firebase_service kan de MATCHES hebben
                    # behouden terwijl result["stats"] op de (kleinere) nieuwe
                    # set berekend is. Dan lopen matches en stats uiteen en
                    # rekenen winrate/partneranalyse op verkeerde cijfers.
                    # Hersynchroniseer de stats met wat er echt in Firestore staat.
                    verify_matches = (verify_doc or {}).get("matches", []) or []
                    if verify_matches:
                        herberekend = _calc_stats(verify_matches)
                        logger.warning(
                            f"[{player_id}] Stats hersynchroniseerd met het bewaarde "
                            f"document: {result['stats'].get('total_matches')} -> "
                            f"{herberekend.get('total_matches')} matches, "
                            f"winrate {result['stats'].get('winrate')}% -> "
                            f"{herberekend.get('winrate')}%."
                        )
                        result["stats"] = herberekend
                        result["matches"] = verify_matches
                        try:
                            _fb.save_player_v2(player_id, result)
                        except Exception as e:  # noqa: BLE001
                            logger.error(f"[{player_id}] Stats-hersync wegschrijven mislukt: {e}")
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
    parser.add_argument("--max-failed-ratio", type=float, default=None,
                        help=("Max aandeel mislukte periodes bij --full voor er wordt "
                              f"afgebroken (standaard {MAX_FAILED_PERIOD_RATIO})."))
    args = parser.parse_args()

    if args.max_failed_ratio is not None:
        MAX_FAILED_PERIOD_RATIO = args.max_failed_ratio

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
