# -*- coding: utf-8 -*-
"""
refresh_padelstat_only.py — geïsoleerd, dagelijks script dat UITSLUITEND de
padelstats.be playing strength van alle spelers (eigen team + tegenstanders)
controleert/herstelt. Doet NIETS met matchdata, klassement of poule-schema's.

Locatie: PadelAnalysis/scraper/refresh_padelstat_only.py
(naast enrich_opponents.py / ci_scrape_all.py, zelfde path-setup patroon)

--------------------------------------------------------------------------
WAAROM DIT EEN APART SCRIPT IS (bewust losgekoppeld van ci_scrape_all.py)
--------------------------------------------------------------------------
Op verzoek van Kim: de matchdata-scrape liep vast op de 30-minuten-limiet
van GitHub Actions naarmate de spelerslijst groeide, en "een speler
verversen" loste de padelstat-problemen niet op. Om dat laatste eerst apart,
gericht op te kunnen lossen (zonder te wachten op de bredere timeout-fix),
is dit een volledig zelfstandig script: eigen workflow, eigen tijdslimiet,
geen afhankelijkheid van scrape_player.py of poule_playwright.py.

--------------------------------------------------------------------------
WAAROM "VERVERSEN" TOT NU TOE NIET HIELP (kernprobleem, hier opgelost)
--------------------------------------------------------------------------
enrich_opponents.run_padelstat_for_players() (en dus ook de "Ververs alles"-
knop in opponent_scout_ui.py) doet, zonder force=True:

    cached = fb.get_padelstat_rating(pid)
    if cached and cached.get("rating") is not None:
        continue  # overslaan: "er staat al iets"

Dat "er staat al iets" is precies het probleem. Deze sessie zijn twee
bugs in padelstats_scraper.py opgelost die er eerder voor zorgden dat de
gevonden waarde VERKEERD kon zijn of de scrape gewoon MISLUKTE:
  - PADEL_ANALYSIS_PADELSTAT_CLUB_MATCH_BUG_2026-09-13: een fragiele,
    asymmetrische substring-vergelijking kon de verkeerde gelijknamige
    speler kiezen (bv. Carl Ide werd niet gekoppeld aan zijn eigen club).
  - PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16: de
    cookie-consent-banner op padelstats.be blokkeerde de zoekbalk, waardoor
    de scrape vastliep zonder ooit een waarde op te halen.
Elke speler wiens rating VOOR deze fixes werd opgehaald, kan dus een foute
of ontbrekende waarde hebben -- en een gewone refresh slaat die speler
STRUCTUREEL over, want er "staat al iets" (of het faalde stil).

Fix: dit script stempelt elke succesvolle opzoeking met een
PADELSTAT_LOGIC_VERSION-marker (padelstat_logic_version-veld op het
player_profiles-document). Bij elke run wordt een speler als "moet
gecontroleerd worden" beschouwd zodra:
  1. er helemaal geen rating bekend is, OF
  2. de opgeslagen padelstat_logic_version niet overeenkomt met de HUIDIGE
     versie hieronder (dus: nooit gecontroleerd MET de gerepareerde
     scraper) -- dit is het EENMALIGE zelfherstel-mechanisme dat oude,
     mogelijk foute waarden alsnog corrigeert, zonder dat Kim iets hoeft
     te doen, ON daarna nooit meer onnodig, want eenmaal bijgewerkte
     spelers krijgen de nieuwe versie-marker en worden dus overgeslagen.
Verhoog PADELSTAT_LOGIC_VERSION wanneer er ooit weer een fix in
padelstats_scraper.py komt die een NIEUWE algehele hercontrole rechtvaardigt.

--------------------------------------------------------------------------
DAGELIJKS, MET EEN HARDE LIMIET PER RUN (batching)
--------------------------------------------------------------------------
Elke padelstat-opzoeking kost een volledige Playwright-sessie (~10-30s).
Om nooit tegen een workflow-timeout aan te lopen, verwerkt dit script
STANDAARD MAX 40 spelers per run (PADELSTAT_MAX, overschrijfbaar via env of
--max). Spelers die deze run niet aan bod komen, worden gewoon de VOLGENDE
dagelijkse run opgepikt -- na een paar dagen is iedereen bijgewerkt, en
daarna blijft het script supersnel (enkel echt nieuwe/niet-geverifieerde
spelers kosten nog tijd).

Prioriteitsvolgorde binnen een run:
  1. spelers met een NIET-actuele padelstat_logic_version (zelfherstel);
  2. spelers zonder enige rating (nieuw toegevoegd);
  3. (bij --force-all) iedereen, ongeacht versie-marker.

--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    python refresh_padelstat_only.py --dry-run
    python refresh_padelstat_only.py
    python refresh_padelstat_only.py --max 60
    python refresh_padelstat_only.py --player 1759548          (1 speler, altijd)
    python refresh_padelstat_only.py --force-all --max 20      (iedereen herzien)
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

logger = logging.getLogger(__name__)

# Verhogen bij een volgende fix in padelstats_scraper.py die een nieuwe,
# algehele hercontrole van ALLE spelers rechtvaardigt (zelfherstel-trigger).
PADELSTAT_LOGIC_VERSION = "v2-clubwordmatch-consentretry-2026-09-16"

DEFAULT_MAX_PER_RUN = 40
DEFAULT_PAUSE_SECONDS = 1.5


def _norm_id(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _all_profiles() -> list:
    try:
        return fb.search_player_profiles("", limit=10_000) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Kon profielen niet lezen: {e}")
        return []


def needs_check(profile: dict, force_all: bool = False) -> tuple[bool, str]:
    """Bepaalt of deze speler deze run gecontroleerd moet worden, en waarom.

    Returns (moet_gecontroleerd, reden). De reden wordt gebruikt om de
    prioriteitsvolgorde te bepalen (zie module-docstring)."""
    if force_all:
        return True, "force-all"

    version = profile.get("padelstat_logic_version")
    if version != PADELSTAT_LOGIC_VERSION:
        return True, "verouderde-versie (mogelijk foute oude waarde)"

    player_id = _norm_id(profile.get("player_id"))
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:  # noqa: BLE001
        cached = None
    if not cached or cached.get("rating") is None:
        return True, "geen rating bekend"

    return False, "al gecontroleerd met huidige scraper-versie"


def select_players_to_process(
    profiles: list,
    max_per_run: int,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
) -> list:
    """Kiest WELKE spelers deze run verwerkt worden, met prioriteit voor
    zelfherstel (verouderde versie) boven nieuw-ontbrekend."""
    if only_player_id:
        pid = _norm_id(only_player_id)
        match = next((p for p in profiles if _norm_id(p.get("player_id")) == pid), None)
        return [match] if match else []

    kandidaten = []
    for p in profiles:
        if not p.get("player_id") or not p.get("display_name"):
            continue
        moet, reden = needs_check(p, force_all=force_all)
        if moet:
            kandidaten.append((p, reden))

    prioriteit = {"force-all": 0, "verouderde-versie (mogelijk foute oude waarde)": 1, "geen rating bekend": 2}
    kandidaten.sort(key=lambda item: prioriteit.get(item[1], 9))
    return [p for p, _ in kandidaten[:max_per_run]]


def refresh_one(player_id: str, naam: str, club: str, dry_run: bool = False) -> dict:
    """Voert de effectieve padelstats.be-opzoeking uit voor 1 speler en
    stempelt het resultaat met PADELSTAT_LOGIC_VERSION (zelfherstel-marker),
    ONGEACHT of er al eerder een (mogelijk foute) waarde stond."""
    import padelstats_scraper as pss  # lazy: enkel nodig als deze stap draait

    result = {"player_id": player_id, "naam": naam, "status": None, "rating": None, "note": None}

    try:
        gevonden = pss.search_and_fetch_padelstat_rating(naam, club=club or None)
    except Exception as e:  # noqa: BLE001
        result["status"] = "fout"
        result["note"] = str(e)
        return result

    if not gevonden or gevonden.get("rating") is None:
        result["status"] = "niet_gevonden"
        if not dry_run:
            _stamp_checked(player_id, found=False)
        return result

    result["status"] = "opgehaald"
    result["rating"] = gevonden.get("rating")
    if gevonden.get("club_disambiguation_note"):
        result["note"] = gevonden["club_disambiguation_note"]

    if not dry_run:
        try:
            fb.save_padelstat_rating(
                player_id,
                gevonden.get("padelstat_id", ""),
                gevonden.get("rating"),
                gevonden.get("rating_source", "none"),
                gevonden.get("raw_text_snippet", ""),
            )
        except Exception as e:  # noqa: BLE001
            result["status"] = "opslaan_mislukt"
            result["note"] = str(e)
            return result
        _stamp_checked(player_id, found=True)

    return result


def _stamp_checked(player_id: str, found: bool) -> None:
    """Zet de versie-marker + tijdstempel, ONGEACHT of er een waarde
    gevonden werd -- ook 'niet gevonden' is een geldig, bewust resultaat dat
    niet elke dag opnieuw geprobeerd hoeft te worden totdat de scraper zelf
    weer verandert (PADELSTAT_LOGIC_VERSION omhoog)."""
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
            {
                "padelstat_logic_version": PADELSTAT_LOGIC_VERSION,
                "padelstat_last_checked_at": _utc_now_iso(),
                "padelstat_last_result": "found" if found else "not_found",
            },
            merge=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[{player_id}] Kon versie-stempel niet wegschrijven: {e}")


def run(
    max_per_run: int = DEFAULT_MAX_PER_RUN,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    profiles = _all_profiles()

    # Telling van ALLE kandidaten (voor rapportage), los van de max-cap.
    # Zelfde filter als select_players_to_process (player_id + display_name
    # vereist) zodat een profiel zonder bruikbare naam niet eeuwig als
    # "resterend" blijft meetellen zonder ooit verwerkt te kunnen worden.
    alle_kandidaten = [
        p for p in profiles
        if p.get("player_id") and p.get("display_name") and needs_check(p, force_all=force_all)[0]
    ] if not only_player_id else []
    te_verwerken = select_players_to_process(profiles, max_per_run, force_all=force_all, only_player_id=only_player_id)

    logger.info(
        f"{len(profiles)} speler(s) totaal in player_profiles. "
        f"{len(alle_kandidaten) or len(te_verwerken)} kandidaat/kandidaten voor controle, "
        f"waarvan {len(te_verwerken)} deze run verwerkt worden (max={max_per_run})."
    )
    if dry_run:
        logger.info("--dry-run: er wordt NIETS gescrapet of weggeschreven, enkel getoond wie aan bod zou komen.")
        for p in te_verwerken:
            moet, reden = needs_check(p, force_all=force_all)
            logger.info(f"  zou verwerkt worden: {p.get('display_name')} ({p.get('player_id')}) — reden: {reden}")
        return {
            "totaal_profielen": len(profiles),
            "kandidaten": len(alle_kandidaten),
            "deze_run": len(te_verwerken),
            "resultaten": [],
        }

    resultaten = []
    for i, p in enumerate(te_verwerken, start=1):
        pid = _norm_id(p.get("player_id"))
        naam = p.get("display_name") or pid
        club = p.get("club") or ""
        logger.info(f"({i}/{len(te_verwerken)}) {naam} ({pid}, club='{club}')...")

        r = refresh_one(pid, naam, club, dry_run=dry_run)
        resultaten.append(r)

        if r["status"] == "opgehaald":
            note = f" — {r['note']}" if r.get("note") else ""
            logger.info(f"  -> P{r['rating']}{note}")
        elif r["status"] == "niet_gevonden":
            logger.info("  -> niet gevonden op padelstats.be")
        else:
            logger.warning(f"  -> {r['status']}: {r.get('note')}")

        if i < len(te_verwerken):
            time.sleep(pause_seconds)

    samenvatting = {
        "totaal_profielen": len(profiles),
        "kandidaten": len(alle_kandidaten),
        "deze_run": len(te_verwerken),
        "opgehaald": sum(1 for r in resultaten if r["status"] == "opgehaald"),
        "niet_gevonden": sum(1 for r in resultaten if r["status"] == "niet_gevonden"),
        "fout": sum(1 for r in resultaten if r["status"] in ("fout", "opslaan_mislukt")),
        "resterend_na_deze_run": max(0, len(alle_kandidaten) - len(te_verwerken)),
        "resultaten": resultaten,
    }
    return samenvatting


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(
        description="Controleert/herstelt de padelstats.be playing strength van alle spelers, "
                    "los van matchdata- of poule-scraping."
    )
    parser.add_argument("--max", type=int, default=int(os.environ.get("PADELSTAT_MAX", DEFAULT_MAX_PER_RUN)),
                        help=f"Max aantal spelers deze run (standaard {DEFAULT_MAX_PER_RUN}, of env PADELSTAT_MAX).")
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS,
                        help=f"Pauze in seconden tussen spelers (standaard {DEFAULT_PAUSE_SECONDS}).")
    parser.add_argument("--force-all", action="store_true",
                        help="Negeer de versie-marker en controleer IEDEREEN opnieuw (traag; gebruik samen met --max).")
    parser.add_argument("--player", type=str, default=None,
                        help="Enkel deze speler controleren (player_id), altijd, ongeacht versie-marker.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon enkel wie verwerkt zou worden, scrape niets, schrijf niets weg.")
    args = parser.parse_args()

    resultaat = run(
        max_per_run=args.max,
        pause_seconds=args.pause,
        force_all=args.force_all,
        only_player_id=args.player,
        dry_run=args.dry_run,
    )

    print("\n=== Samenvatting padelstat-controle ===")
    print(f"Totaal profielen        : {resultaat['totaal_profielen']}")
    print(f"Kandidaten (nog te doen) : {resultaat['kandidaten']}")
    print(f"Verwerkt deze run        : {resultaat['deze_run']}")
    if not args.dry_run:
        print(f"  Opgehaald              : {resultaat.get('opgehaald', 0)}")
        print(f"  Niet gevonden          : {resultaat.get('niet_gevonden', 0)}")
        print(f"  Fout                   : {resultaat.get('fout', 0)}")
        print(f"Resterend na deze run    : {resultaat.get('resterend_na_deze_run', 0)}")
        if resultaat.get("resterend_na_deze_run", 0) > 0:
            print(
                f"\n{resultaat['resterend_na_deze_run']} speler(s) volgen bij de VOLGENDE "
                "(dagelijkse) run — verhoog --max om dit sneller in te lopen."
            )
