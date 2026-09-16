"""
enrich_opponents.py — zorgt dat TEGENSTANDERS volwaardige spelers worden.

Locatie: PadelAnalysis/scraper/enrich_opponents.py
(naast scrape_player.py / ci_scrape_all.py, zelfde path-setup patroon)

--------------------------------------------------------------------------
HET PROBLEEM DAT DIT OPLOST
--------------------------------------------------------------------------
Na het ophalen van een poule-schema toonde de tegenploeg-overzichtstabel voor
verschillende spelers (De Purcq Hilde, Brede Hilde, Severine, ...):
  - geen playing strength   ("voer bulk_fetch_padelstat_ratings.py uit")
  - geen klassement, geen klassementshistoriek
  - geen winrate historiek, geen vaste partner historiek

Dat lijken drie losse problemen, maar het is EEN oorzaak. In
opponent_dossier.build_player_summary() staat:
    doc = fb.get_player(player_id) or all_docs.get(str(player_id)) or {}
    matches = doc.get("matches", []) or []
Heeft een tegenstander GEEN eigen document in de players-collectie, dan is
matches leeg. Gevolg, in cascade: winrate/partners/vorm/periodes leeg,
klassement + historiek leeg, playing strength leeg (want
bulk_fetch_padelstat_ratings loopt over fb.search_player_profiles() en die
speler heeft geen profiel).

De poule-scrape haalt enkel FIXTURES en NAMEN op; ze maakt geen spelers aan.
Tegenstanders bestonden dus enkel als naam in een uitslagenblad.

--------------------------------------------------------------------------
WAT DIT BESTAND DOET
--------------------------------------------------------------------------
1. discover_opponent_players()  - vindt alle tegenstanders/partners die in de
   matchrecords van onze eigen spelers voorkomen maar nog GEEN eigen
   player_profiles-document hebben.
2. ensure_profiles()            - maakt voor die spelers een profiel aan.
3. run_padelstat_for_players()  - haalt de padelstats.be playing strength op.
4. run_klassement_for_players() - haalt de TVL-klassementshistoriek op.

--------------------------------------------------------------------------
PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16
--------------------------------------------------------------------------
run_klassement_for_players(), zelfde opbouw als de bestaande lokale flow in
opponent_scout_ui.py (scrape_klassement() + klassement_to_history_summary()
+ extract_niveau_winrates() uit scrape_klassement.py).

--------------------------------------------------------------------------
PADEL_ANALYSIS_INTERCLUB_ONLY_DISCOVERY_2026-09-16 ("worst case")
--------------------------------------------------------------------------
discover_opponent_players() heeft een interclub_only-parameter (standaard
True): enkel matches met match_type == "interclub" leveren kandidaten op,
zodat jarenlange tornooihistoriek geen honderden irrelevante ghost-profielen
genereert. run_padelstat_for_players() en run_klassement_for_players()
geven bovendien spelers MET bestaande matchdata voorrang boven ghosts (zie
_prioritize()) wanneer een *_MAX-limiet spelers moet laten wachten.

--------------------------------------------------------------------------
PADEL_ANALYSIS_GHOST_CLEANUP_TIMESTAMP_2026-09-16
--------------------------------------------------------------------------
ensure_profiles() zet een "discovered_at"-tijdstempel op elk NIEUW
aangemaakt profiel, gebruikt door cleanup_ghost_profiles.py om te
onderscheiden tussen een écht irrelevant profiel en een net ontdekte
speler die nog geen kans kreeg om verrijkt te worden.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): "het padelstat getal zal voortdurend wijzigen. moet dus
regelmatig geupdate worden. checken als dat werkt". Antwoord: het werkte
NIET. run_padelstat_for_players() sloeg elke speler met EENMAAL een
gecachete rating (fb.get_padelstat_rating(...).get("rating") is not None)
voor ALTIJD over, tenzij refresh=True werd gezet -- en dat gebeurde nergens
automatisch in de reguliere CI-run. Een speler kreeg dus zijn/haar
padelstat-waarde precies EEN keer, nooit meer bijgewerkt, terwijl
padelstats.be die waarde continu herberekent op basis van nieuwe resultaten.

Fix, twee onderdelen:
  1. save_padelstat_rating() wordt nog steeds ONGEWIJZIGD aangeroepen. Het
     bestaande veld dat het als tijdstempel zet, heet -- geverifieerd in de
     ACTUELE firebase_service.py -- "fetched_at" (NIET "scraped_at", zoals
     bij klassement_history; de twee functies gebruiken bewust/toevallig een
     andere naam). Dit gebruiken we als staleness-tijdstempel in plaats van
     een apart nieuw veld te introduceren.
  2. run_padelstat_for_players() beschouwt een speler nu als "te verversen"
     als OFWEL er nog geen rating is, OFWEL de bestaande rating ouder is dan
     PADELSTAT_STALE_AFTER_DAYS (standaard 14 dagen). refresh=True blijft
     bestaan als "forceer ALLES te herdoen, ongeacht leeftijd" (traag, enkel
     voor handmatig gebruik) -- de nieuwe standaardwerking (refresh=False)
     doet nu automatisch OOK de verouderde ratings, niet enkel de volledig
     ontbrekende. _prioritize() geeft binnen de te-verversen-lijst nog steeds
     voorrang aan spelers met matchdata boven ghost-profielen.

--------------------------------------------------------------------------
SNELHEID
--------------------------------------------------------------------------
Elke padelstats-speler kost twee Playwright-paginabezoeken (~5-10 sec).
Elke klassement-speler kost EEN Playwright-sessie met meerdere periode-
selecties (~30-90s). Daarom, voor BEIDE stappen: een harde limiet per run
(*_MAX_PER_RUN), spelers MET matchdata krijgen voorrang.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# --- path setup: zelfde patroon als scrape_player.py ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

logger = logging.getLogger(__name__)

# Maximaal aantal padelstats-ophalingen per run (snelheidsbegrenzing).
PADELSTAT_MAX_PER_RUN = 25
# Beleefde pauze tussen padelstats-bezoeken.
PADELSTAT_PAUSE_SECONDS = 1.5
# PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16: na hoeveel dagen een
# bestaande padelstat-rating als "verouderd" geldt en dus automatisch
# opnieuw wordt opgehaald, ook zonder refresh=True.
PADELSTAT_STALE_AFTER_DAYS = 14

# Klassement kost een volledige Playwright-sessie per speler, dus een
# beduidend lagere limiet dan padelstat.
KLASSEMENT_MAX_PER_RUN = 8
KLASSEMENT_MAX_PERIODS = 10
KLASSEMENT_PAUSE_SECONDS = 2.0


def _norm_id(value) -> str:
    """Maakt id's vergelijkbaar ongeacht int/float/str-opslag ('123', 123.0)."""
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        cleaned = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# 1. Tegenstanders ontdekken
# ---------------------------------------------------------------------------
def _known_profile_ids() -> set:
    try:
        profiles = fb.search_player_profiles("", limit=10_000)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[enrich] Kon bestaande profielen niet lezen: {e}")
        return set()
    return {_norm_id(p.get("player_id")) for p in profiles if p.get("player_id")}


def discover_opponent_players(
    player_ids: list,
    include_partners: bool = True,
    interclub_only: bool = True,
) -> dict:
    """Vind spelers die in de matchen van `player_ids` voorkomen als
    tegenstander (of partner) maar nog geen eigen profiel hebben.

    PADEL_ANALYSIS_INTERCLUB_ONLY_DISCOVERY_2026-09-16: interclub_only=True
    (standaard) beperkt de scan tot match_type == "interclub".

    Returns {player_id: display_name} voor de ONTBREKENDE spelers.
    """
    known = _known_profile_ids()
    found: dict[str, str] = {}
    overgeslagen_tornooi = 0
    for pid in player_ids:
        try:
            doc = fb.get_player(pid) or {}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[enrich] [{pid}] kon document niet lezen: {e}")
            continue
        for match in doc.get("matches", []) or []:
            if interclub_only and match.get("match_type") != "interclub":
                overgeslagen_tornooi += 1
                continue
            paren = [
                (match.get("opp1_user_id"), match.get("opp1_name")),
                (match.get("opp2_user_id"), match.get("opp2_name")),
            ]
            if include_partners:
                paren.append((match.get("partner_user_id"), match.get("partner_name")))
            for raw_id, naam in paren:
                other_id = _norm_id(raw_id)
                if not other_id or not other_id.isdigit():
                    continue
                if other_id in known or other_id in found:
                    continue
                naam = (naam or "").strip()
                if naam:
                    found[other_id] = naam
    if interclub_only and overgeslagen_tornooi:
        logger.info(
            f"[enrich] {overgeslagen_tornooi} tornooi-matchrij(en) overgeslagen bij "
            "het ontdekken van tegenstanders (interclub_only=True)."
        )
    return found


# ---------------------------------------------------------------------------
# 2. Profielen aanmaken
# ---------------------------------------------------------------------------
def ensure_profiles(players: dict, club: Optional[str] = None) -> list:
    """Maak player_profiles-documenten aan voor {player_id: naam}.

    PADEL_ANALYSIS_GHOST_CLEANUP_TIMESTAMP_2026-09-16: discovered_at wordt
    hier gezet, enkel bij eerste aanmaak.

    Returns de lijst van aangemaakte player_id's.
    """
    aangemaakt = []
    discovered_at = _utc_now_iso()
    for player_id, naam in (players or {}).items():
        payload = {
            "player_id": str(player_id),
            "display_name": naam,
            "added_by": "auto_opponent_discovery",
            "discovered_at": discovered_at,
        }
        if club:
            payload["club"] = club
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
                payload, merge=True
            )
            aangemaakt.append(str(player_id))
            logger.info(f"[enrich] Profiel aangemaakt: {naam} ({player_id})")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[enrich] Kon profiel {naam} ({player_id}) niet aanmaken: {e}")
    return aangemaakt


# ---------------------------------------------------------------------------
# Gedeelde prioriteringshelper
# ---------------------------------------------------------------------------
def _has_matchdata(player_id: str) -> bool:
    """True als deze speler minstens 1 match heeft in zijn/haar players-doc."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        return False
    return bool(doc.get("matches"))


def _prioritize(candidates: list) -> list:
    """Sorteert een lijst van (player_id, ...)-tupels zodat spelers MET
    matchdata vooraan komen. Stabiele sort."""
    return sorted(candidates, key=lambda item: 0 if _has_matchdata(item[0]) else 1)


# ---------------------------------------------------------------------------
# 3. Padelstats playing strength ophalen
# ---------------------------------------------------------------------------
def _padelstat_is_stale(cached: Optional[dict], stale_after_days: int) -> bool:
    """PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16.

    True als er GEEN gecachete rating is, OF de rating ouder is dan
    stale_after_days. Kan geen leeftijd bepaald worden (geen scraped_at-veld
    -- bv. een heel oude, van vóór deze fix), dan wordt die conservatief ook
    als 'stale' behandeld: beter een keer te veel verversen dan een blijvend
    verouderd getal tonen."""
    if not cached or cached.get("rating") is None:
        return True
    # BELANGRIJK: firebase_service.save_padelstat_rating() zet dit veld als
    # "fetched_at" (geverifieerd in de actuele firebase_service.py) -- NIET
    # "scraped_at" zoals bij klassement_history. Twee verschillende
    # velden voor eenzelfde soort tijdstempel, per functie.
    fetched_at = _parse_iso(cached.get("fetched_at"))
    if fetched_at is None:
        return True
    age = datetime.now(timezone.utc) - fetched_at
    return age > timedelta(days=stale_after_days)


def run_padelstat_for_players(
    player_ids: list,
    refresh: bool = False,
    max_players: int = PADELSTAT_MAX_PER_RUN,
    pause_seconds: float = PADELSTAT_PAUSE_SECONDS,
    stale_after_days: int = PADELSTAT_STALE_AFTER_DAYS,
) -> dict:
    """Haal de padelstats.be playing strength op voor deze spelers.

    PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16: refresh=False (standaard)
    haalt nu OOK spelers op wier bestaande rating ouder is dan
    stale_after_days (zie _padelstat_is_stale()) -- niet enkel spelers die
    nog nooit een rating kregen. refresh=True negeert de cache volledig
    (forceert iedereen, traag, enkel voor handmatig gebruik).

    Bij overschrijding van max_players krijgen spelers MET bestaande
    matchdata voorrang (zie _prioritize()).

    Returns: {"opgehaald": n, "cache": n, "niet_gevonden": n, "fout": n,
    "overgeslagen_limiet": n}.
    """
    samenvatting = {"opgehaald": 0, "cache": 0, "niet_gevonden": 0,
                    "fout": 0, "overgeslagen_limiet": 0}
    try:
        import padelstats_scraper as ps
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[padelstat] padelstats_scraper niet beschikbaar ({e}) — stap overgeslagen."
        )
        return samenvatting

    try:
        alle_profielen = {
            _norm_id(p.get("player_id")): p
            for p in fb.search_player_profiles("", limit=10_000)
            if p.get("player_id")
        }
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[padelstat] Kon profielen niet lezen: {e}")
        return samenvatting

    te_doen = []
    for pid in player_ids:
        key = _norm_id(pid)
        profiel = alle_profielen.get(key)
        if not profiel or not profiel.get("display_name"):
            continue
        if not refresh:
            try:
                cached = fb.get_padelstat_rating(key)
            except Exception:  # noqa: BLE001
                cached = None
            if not _padelstat_is_stale(cached, stale_after_days):
                samenvatting["cache"] += 1
                continue
        te_doen.append((key, profiel))

    if not te_doen:
        logger.info("[padelstat] Iedereen heeft al een actuele playing strength — niets te doen.")
        return samenvatting

    te_doen = _prioritize(te_doen)

    if max_players and len(te_doen) > max_players:
        samenvatting["overgeslagen_limiet"] = len(te_doen) - max_players
        logger.info(
            f"[padelstat] {len(te_doen)} speler(s) te doen (nieuw of ouder dan "
            f"{stale_after_days} dagen), limiet is {max_players}. De overige "
            f"{samenvatting['overgeslagen_limiet']} volgen in een volgende run "
            "(spelers met matchdata kregen voorrang op ghost-profielen)."
        )
        te_doen = te_doen[:max_players]

    totaal = len(te_doen)
    logger.info(f"[padelstat] Playing strength ophalen/verversen voor {totaal} speler(s)…")
    for i, (player_id, profiel) in enumerate(te_doen, start=1):
        naam = profiel.get("display_name") or ""
        club = profiel.get("club") or ""
        prefix = f"[padelstat] ({i}/{totaal}) {naam}"
        try:
            gevonden = ps.search_and_fetch_padelstat_rating(naam, club=club or None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{prefix} -> FOUT: {e}")
            samenvatting["fout"] += 1
            continue
        if not gevonden or gevonden.get("rating") is None:
            logger.info(f"{prefix} -> niet gevonden op padelstats.be")
            samenvatting["niet_gevonden"] += 1
            time.sleep(pause_seconds)
            continue
        try:
            fb.save_padelstat_rating(
                player_id,
                gevonden.get("padelstat_id", ""),
                gevonden.get("rating"),
                gevonden.get("rating_source", "none"),
                gevonden.get("raw_text_snippet", ""),
            )
            samenvatting["opgehaald"] += 1
            vlag = " ⚠️ club niet bevestigd" if gevonden.get("club_disambiguation_note") else ""
            logger.info(f"{prefix} -> P{gevonden['rating']}{vlag}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{prefix} -> opslaan mislukt: {e}")
            samenvatting["fout"] += 1
        time.sleep(pause_seconds)
    return samenvatting


# ---------------------------------------------------------------------------
# 4. Klassementshistoriek ophalen
# ---------------------------------------------------------------------------
def _has_klassement(player_id: str) -> bool:
    """Zelfde controle als opponent_scout_ui._ensure_klassement(): kijkt op
    ZOWEL het players- als het player_profiles-document."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        doc = {}
    try:
        prof = fb.get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        prof = {}
    return bool(doc.get("klassement_history") or prof.get("klassement_history"))


def run_klassement_for_players(
    player_ids: list,
    refresh: bool = False,
    max_players: int = KLASSEMENT_MAX_PER_RUN,
    max_periods: int = KLASSEMENT_MAX_PERIODS,
    pause_seconds: float = KLASSEMENT_PAUSE_SECONDS,
) -> dict:
    """Haalt de TVL-klassementshistoriek op voor deze spelers, met dezelfde
    scrape_klassement.py-functies en opslagvorm als de bestaande lokale flow.

    Returns: {"opgehaald": n, "cache": n, "fout": n, "overgeslagen_limiet": n}.
    """
    samenvatting = {"opgehaald": 0, "cache": 0, "fout": 0, "overgeslagen_limiet": 0}
    try:
        from scrape_klassement import (
            scrape_klassement,
            klassement_to_history_summary,
            extract_niveau_winrates,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[klassement] scrape_klassement niet beschikbaar ({e}) — stap overgeslagen."
        )
        return samenvatting

    te_doen = []
    for pid in player_ids:
        key = _norm_id(pid)
        if not refresh and _has_klassement(key):
            samenvatting["cache"] += 1
            continue
        te_doen.append((key,))

    if not te_doen:
        logger.info("[klassement] Iedereen heeft al klassementshistoriek — niets te doen.")
        return samenvatting

    te_doen = _prioritize(te_doen)
    te_doen = [key for (key,) in te_doen]

    if max_players and len(te_doen) > max_players:
        samenvatting["overgeslagen_limiet"] = len(te_doen) - max_players
        logger.info(
            f"[klassement] {len(te_doen)} speler(s) te doen, limiet is {max_players}. "
            f"De overige {samenvatting['overgeslagen_limiet']} volgen in een volgende run."
        )
        te_doen = te_doen[:max_players]

    totaal = len(te_doen)
    logger.info(f"[klassement] Klassementshistoriek ophalen voor {totaal} speler(s)…")
    for i, pid in enumerate(te_doen, start=1):
        prefix = f"[klassement] ({i}/{totaal}) speler {pid}"
        try:
            periods = scrape_klassement(pid, max_periods=max_periods, headless=True)
            history = klassement_to_history_summary(periods)
            niveau_winrates = extract_niveau_winrates(periods)
            klass_data = {
                "history": history,
                "niveau_winrates": niveau_winrates,
                "raw_periods": periods,
                "scraped_at": _utc_now_iso(),
            }
            payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(
                payload, merge=True
            )
            fb.db.collection(fb.PLAYERS_COLLECTION).document(str(pid)).set(
                payload, merge=True
            )
            samenvatting["opgehaald"] += 1
            huidig = history[0].get("klassement") if history else None
            logger.info(f"{prefix} -> {huidig or '?'} ({len(history)} periode(s))")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{prefix} -> FOUT: {e}")
            samenvatting["fout"] += 1
        if i < totaal:
            time.sleep(pause_seconds)

    return samenvatting


# ---------------------------------------------------------------------------
# Gecombineerde stap (wordt door ci_scrape_all.py aangeroepen)
# ---------------------------------------------------------------------------
def enrich(
    player_ids: list,
    do_discover: bool = True,
    do_padelstat: bool = True,
    padelstat_refresh: bool = False,
    padelstat_max: int = PADELSTAT_MAX_PER_RUN,
    padelstat_stale_after_days: int = PADELSTAT_STALE_AFTER_DAYS,
    do_klassement: bool = True,
    klassement_refresh: bool = False,
    klassement_max: int = KLASSEMENT_MAX_PER_RUN,
    interclub_only: bool = True,
) -> dict:
    """Volledige verrijkingsstap: tegenstanders ontdekken + profielen aanmaken
    + padelstats ophalen/verversen + klassementshistoriek ophalen.

    Returns {"nieuwe_profielen": [...], "padelstat": {...}, "klassement": {...}}.
    """
    resultaat: dict = {"nieuwe_profielen": [], "padelstat": {}, "klassement": {}}
    if do_discover:
        ontbrekend = discover_opponent_players(player_ids, interclub_only=interclub_only)
        if ontbrekend:
            logger.info(
                f"[enrich] {len(ontbrekend)} tegenstander(s)/partner(s) zonder profiel gevonden "
                f"(interclub_only={interclub_only})."
            )
            resultaat["nieuwe_profielen"] = ensure_profiles(ontbrekend)
        else:
            logger.info("[enrich] Alle gekende tegenstanders hebben al een profiel.")

    doelgroep = list(dict.fromkeys(
        [str(p) for p in player_ids] + resultaat["nieuwe_profielen"]
    ))

    if do_padelstat:
        resultaat["padelstat"] = run_padelstat_for_players(
            doelgroep, refresh=padelstat_refresh, max_players=padelstat_max,
            stale_after_days=padelstat_stale_after_days,
        )

    if do_klassement:
        resultaat["klassement"] = run_klassement_for_players(
            doelgroep, refresh=klassement_refresh, max_players=klassement_max
        )

    return resultaat


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(
        description="Tegenstanders als speler aanmaken + padelstats/klassement ophalen."
    )
    parser.add_argument("player_ids", nargs="*", help="Eigen spelers om vanuit te vertrekken.")
    parser.add_argument("--all", action="store_true", help="Vertrek van ALLE gekende profielen.")
    parser.add_argument("--no-discover", action="store_true", help="Geen nieuwe profielen aanmaken.")
    parser.add_argument("--no-padelstat", action="store_true", help="Geen padelstats ophalen.")
    parser.add_argument("--no-klassement", action="store_true", help="Geen klassementshistoriek ophalen.")
    parser.add_argument("--include-tournament", action="store_true",
                        help="Ontdek OOK tornooi-tegenstanders (standaard: enkel interclub).")
    parser.add_argument("--refresh", action="store_true", help="Negeer zowel de padelstats- als klassement-cache VOLLEDIG (forceer iedereen, traag).")
    parser.add_argument("--max", type=int, default=PADELSTAT_MAX_PER_RUN,
                        help=f"Max padelstats-ophalingen deze run (standaard {PADELSTAT_MAX_PER_RUN}).")
    parser.add_argument("--padelstat-stale-days", type=int, default=PADELSTAT_STALE_AFTER_DAYS,
                        help=f"Ververs padelstat automatisch na dit aantal dagen (standaard {PADELSTAT_STALE_AFTER_DAYS}).")
    parser.add_argument("--klassement-max", type=int, default=KLASSEMENT_MAX_PER_RUN,
                        help=f"Max klassement-ophalingen deze run (standaard {KLASSEMENT_MAX_PER_RUN}).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon enkel welke spelers zouden worden aangemaakt.")
    args = parser.parse_args()

    if args.all or not args.player_ids:
        ids = [
            str(p.get("player_id"))
            for p in fb.search_player_profiles("", limit=10_000)
            if p.get("player_id")
        ]
        print(f"Vertrek van alle {len(ids)} gekende profielen.")
    else:
        ids = args.player_ids

    if args.dry_run:
        ontbrekend = discover_opponent_players(ids, interclub_only=not args.include_tournament)
        print(f"\n{len(ontbrekend)} speler(s) zonder profiel:\n")
        for pid, naam in sorted(ontbrekend.items(), key=lambda kv: kv[1]):
            print(f"  {pid:<12} {naam}")
        sys.exit(0)

    res = enrich(
        ids,
        do_discover=not args.no_discover,
        do_padelstat=not args.no_padelstat,
        padelstat_refresh=args.refresh,
        padelstat_max=args.max,
        padelstat_stale_after_days=args.padelstat_stale_days,
        do_klassement=not args.no_klassement,
        klassement_refresh=args.refresh,
        klassement_max=args.klassement_max,
        interclub_only=not args.include_tournament,
    )

    print("\n=== Samenvatting ===")
    print(f"Nieuwe profielen : {len(res['nieuwe_profielen'])}")
    if res["padelstat"]:
        p = res["padelstat"]
        print(
            f"Padelstats       : {p.get('opgehaald', 0)} opgehaald/ververst, "
            f"{p.get('cache', 0)} nog actueel, {p.get('niet_gevonden', 0)} niet gevonden, "
            f"{p.get('fout', 0)} fout"
        )
        if p.get("overgeslagen_limiet"):
            print(f"                   {p['overgeslagen_limiet']} wachten op een volgende run")
    if res["klassement"]:
        k = res["klassement"]
        print(
            f"Klassement       : {k.get('opgehaald', 0)} opgehaald, "
            f"{k.get('cache', 0)} uit cache, {k.get('fout', 0)} fout"
        )
        if k.get("overgeslagen_limiet"):
            print(f"                   {k['overgeslagen_limiet']} wachten op een volgende run")
    if res["nieuwe_profielen"]:
        print(
            f"\nLet op: de {len(res['nieuwe_profielen'])} nieuwe speler(s) hebben nog geen "
            "matchdata. Draai nu ci_scrape_all.py (MODE=new_users) om die op te halen."
        )
