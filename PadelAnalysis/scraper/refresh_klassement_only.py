# -*- coding: utf-8 -*-
"""
refresh_klassement_only.py — geïsoleerd, dagelijks script dat UITSLUITEND de
TVL-klassementshistoriek van alle spelers (eigen team + tegenstanders)
controleert/herstelt. Doet NIETS met matchdata, padelstat of poule-schema's.

Locatie: PadelAnalysis/scraper/refresh_klassement_only.py
(naast refresh_padelstat_only.py, exact hetzelfde patroon)

--------------------------------------------------------------------------
WAAROM DIT NODIG IS
--------------------------------------------------------------------------
Klim vroeg: "ik zie nog steeds geen juist klassement bij die speelsters, en
een refresh werkt ook niet." Twee samenvallende oorzaken:

  1. scrape_klassement.py had een cookie-consent-banner-bug
     (PADEL_ANALYSIS_KLASSEMENT_COOKIE_VERIFY_FIX_2026-09-17, exact dezelfde
     bugfamilie als PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_
     2026-09-16 in padelstats_scraper.py): een banner-klik zonder verificatie
     liet de pagina overlapt, waardoor scrape_klassement() terugviel op een
     vrijwel lege "Huidige pagina"-noodgreep. Deze fix zit intussen al IN
     scrape_klassement.py (Kim bevestigde dit door het bestand te delen) -
     dit specifieke onderdeel is dus al opgelost.

  2. STRUCTUREEL probleem, dat de "refresh werkt niet"-klacht verklaart:
     klassement wordt UITSLUITEND lokaal gescrapet, via een checkbox in
     opponent_scout_ui.py (_ensure_klassement), die simpelweg NIETS DOET
     zodra is_scraping_available() False teruggeeft:
         def _ensure_klassement(player_ids, ...):
             if not is_scraping_available():
                 return   # <-- stopt hier, geen scrape, geen foutmelding
     Op de gedeployde (cloud) app is dat ALTIJD het geval (geen Playwright-
     browser beschikbaar). Er bestaat, in tegenstelling tot padelstat en
     matchdata, GEEN server-side equivalent dat dit automatisch voor Kim
     doet - de "Verversen"-knop in de Team-analyse (opponent_analysis.py)
     leest bovendien enkel uit Firestore, ze scrapet zelf niets (zie
     PADEL_ANALYSIS_TEAM_REPORT_STALE_CACHE_FIX_2026-09-17). Vandaar: geen
     enkele knop kon ooit klassement laten verschijnen op de cloud-app.

Dit script is de structurele oplossing voor punt 2, met een ingebouwd
zelfherstel-mechanisme voor punt 1 (spelers die VOOR de cookie-fix al eens
gescrapet zijn, en dus een kapotte, quasi-lege historiek hebben staan).

--------------------------------------------------------------------------
ZELFHERSTEL: DE "KAPOTTE FALLBACK"-DETECTIE
--------------------------------------------------------------------------
Een speler die getroffen werd door de cookie-bug heeft in Firestore een
klassement_history met PRECIES 1 periode, met label "Huidige pagina" en
klassement=None - dit is scrape_klassement()'s eigen, letterlijke
noodgreep-waarde bij een mislukte scrape (zie de docstring/code van dat
bestand). _is_broken_fallback_history() herkent dit patroon expliciet en
behandelt zo'n speler als kandidaat voor hercontrole, ONGEACHT of er al een
klassement_logic_version-marker op staat.

Net als bij refresh_padelstat_only.py wordt elke geslaagde (niet-kapotte)
controle gestempeld met KLASSEMENT_LOGIC_VERSION, zodat:
  - spelers die al een correcte historiek hebben, EENMALIG herzien worden na
    deze fix (zelfherstel-marker), en daarna met rust gelaten worden;
  - een volgende scraper-fix (verhoog KLASSEMENT_LOGIC_VERSION) opnieuw een
    algehele hercontrole kan triggeren zonder Firestore handmatig te moeten
    opschonen.

Blijft de "Huidige pagina"-fallback ondanks de cookie-fix toch nog optreden
voor een specifieke speler, dan wijst dat op een ANDER onderliggend
probleem (bv. een gewijzigde paginastructuur). Dat resultaat wordt WEL
gestempeld (met status "fallback"), om te vermijden dat zo'n speler elke
dag opnieuw hetzelfde nutteloze resultaat oplevert - net zoals
refresh_padelstat_only.py "niet gevonden" ook stempelt. Een volgende
KLASSEMENT_LOGIC_VERSION-verhoging (na een nieuwe scraper-fix) triggert dan
opnieuw een poging.

--------------------------------------------------------------------------
DAGELIJKS, MET EEN HARDE LIMIET PER RUN (batching)
--------------------------------------------------------------------------
Klassement scrapen kost PER SPELER een volledige Playwright-sessie die
bovendien meerdere periodes na elkaar doorloopt (elke periode = 1 dropdown-
selectie + wachttijd) - dus duidelijk trager dan de padelstat-opzoeking.
Om nooit tegen een workflow-timeout aan te lopen:
  - standaard MAX 15 spelers per run (KLASSEMENT_MAX, lager dan bij
    padelstat, precies omdat dit trager is per speler);
  - optioneel een cap op het aantal periodes per speler binnen 1 run
    (KLASSEMENT_MAX_PERIODS_PER_PLAYER, standaard geen cap - de volledige
    historiek), om een individuele speler met een zeer lange geschiedenis
    niet de hele run te laten opslokken.
Spelers die deze run niet aan bod komen, worden de VOLGENDE dagelijkse run
opgepikt.

Prioriteitsvolgorde binnen een run:
  1. kapotte fallback-historiek (zelfherstel na de cookie-fix);
  2. geen klassementshistoriek bekend;
  3. verouderde KLASSEMENT_LOGIC_VERSION (eenmalige hercontrole);
  4. (bij --force-all) iedereen, ongeacht status.

--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    python refresh_klassement_only.py --dry-run
    python refresh_klassement_only.py
    python refresh_klassement_only.py --max 20
    python refresh_klassement_only.py --player 1759548          (1 speler, altijd)
    python refresh_klassement_only.py --force-all --max 10      (iedereen herzien)
    python refresh_klassement_only.py --max-periods-per-player 6
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

# Verhogen bij een volgende fix in scrape_klassement.py die een nieuwe,
# algehele hercontrole van ALLE spelers rechtvaardigt (zelfherstel-trigger).
KLASSEMENT_LOGIC_VERSION = "v2-cookie-consent-verify-retry-2026-09-17"

# Lager dan PADELSTAT_MAX (40): klassement scrapen is trager per speler
# (meerdere periodes na elkaar doorlopen), dus minder spelers per run.
DEFAULT_MAX_PER_RUN = 15
DEFAULT_PAUSE_SECONDS = 2.0
DEFAULT_MAX_PERIODS_PER_PLAYER = None  # None = geen cap, volledige historiek


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


def _get_klassement_doc(player_id: str, profile: Optional[dict] = None) -> Optional[dict]:
    """Klassement kan op het players-document staan (waar de rest van de
    matchdata leeft) OF op het player_profiles-document - dezelfde
    dubbele-locatie-aanpak als opponent_dossier._history_summary(). Geeft de
    EERSTE gevonden klassement_history terug, players-document heeft
    voorrang (consistent met hoe de rest van de app dit leest)."""
    try:
        player_doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        player_doc = {}
    if player_doc.get("klassement_history"):
        return player_doc["klassement_history"]
    if profile is not None and profile.get("klassement_history"):
        return profile["klassement_history"]
    return None


def _is_broken_fallback_history(klassement_doc: dict) -> bool:
    """PADEL_ANALYSIS_KLASSEMENT_COOKIE_VERIFY_FIX_2026-09-17 se letterlijke
    noodgreep-signatuur: exact 1 periode, label 'Huidige pagina', klassement
    leeg. Dit is de vingerafdruk van een mislukte scrape van VOOR de
    cookie-fix (of van een scrape die ondanks de fix toch nog faalde)."""
    history = (klassement_doc or {}).get("history") or []
    if len(history) != 1:
        return False
    row = history[0]
    periode = str(row.get("periode") or "").strip().lower()
    return periode == "huidige pagina" and not row.get("klassement")


def needs_check(profile: dict, force_all: bool = False) -> tuple[bool, str]:
    """Bepaalt of deze speler deze run gecontroleerd moet worden, en waarom.

    Returns (moet_gecontroleerd, reden). De reden bepaalt de
    prioriteitsvolgorde (zie module-docstring)."""
    if force_all:
        return True, "force-all"

    pid = _norm_id(profile.get("player_id"))
    klassement = _get_klassement_doc(pid, profile)

    if not klassement or not klassement.get("history"):
        return True, "geen klassementshistoriek bekend"

    if _is_broken_fallback_history(klassement):
        return True, "kapotte fallback-historiek (van vóór de cookie-fix)"

    version = profile.get("klassement_logic_version")
    if version != KLASSEMENT_LOGIC_VERSION:
        return True, "verouderde scraper-versie (eenmalige hercontrole)"

    return False, "al gecontroleerd met huidige scraper-versie"


def select_players_to_process(
    profiles: list,
    max_per_run: int,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
) -> list:
    """Kiest WELKE spelers deze run verwerkt worden, met prioriteit voor
    zelfherstel (kapotte historiek) boven een gewone versie-hercontrole."""
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

    prioriteit = {
        "force-all": 0,
        "kapotte fallback-historiek (van vóór de cookie-fix)": 1,
        "geen klassementshistoriek bekend": 2,
        "verouderde scraper-versie (eenmalige hercontrole)": 3,
    }
    kandidaten.sort(key=lambda item: prioriteit.get(item[1], 9))
    return [p for p, _ in kandidaten[:max_per_run]]


def refresh_one(
    player_id: str,
    naam: str,
    max_periods: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """Voert de effectieve TVL-klassement-scrape uit voor 1 speler en
    stempelt het resultaat met KLASSEMENT_LOGIC_VERSION (zelfherstel-marker),
    zowel bij succes als bij een blijvende 'Huidige pagina'-fallback (zie
    module-docstring voor waarom ook dat laatste gestempeld wordt)."""
    from scrape_klassement import (  # lazy: enkel nodig als deze stap draait
        scrape_klassement,
        klassement_to_history_summary,
        extract_niveau_winrates,
    )

    result = {"player_id": player_id, "naam": naam, "status": None, "periodes": 0, "note": None}

    try:
        periods = scrape_klassement(str(player_id), max_periods=max_periods, headless=True)
    except Exception as e:  # noqa: BLE001
        result["status"] = "fout"
        result["note"] = str(e)
        return result

    if not periods:
        result["status"] = "leeg"
        result["note"] = "scrape_klassement() gaf een lege lijst terug (onverwacht)"
        return result

    if len(periods) == 1 and periods[0].get("label") == "Huidige pagina":
        result["status"] = "fallback"
        result["note"] = (
            "Nog steeds de 'Huidige pagina'-noodgreep, ondanks de cookie-fix. "
            "Wijst op een ander onderliggend probleem (gewijzigde paginastructuur?)."
        )
        if not dry_run:
            _stamp_checked(player_id, status="fallback")
        return result

    history = klassement_to_history_summary(periods)
    niveau_winrates = extract_niveau_winrates(periods)

    result["status"] = "opgehaald"
    result["periodes"] = len(history)

    if not dry_run:
        klass_data = {
            "history": history,
            "niveau_winrates": niveau_winrates,
            "raw_periods": periods,
            "scraped_at": _utc_now_iso(),
        }
        try:
            payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
            fb.db.collection(fb.PLAYERS_COLLECTION).document(str(player_id)).set(payload, merge=True)
        except Exception as e:  # noqa: BLE001
            result["status"] = "opslaan_mislukt"
            result["note"] = str(e)
            return result
        _stamp_checked(player_id, status="opgehaald")

    return result


def _stamp_checked(player_id: str, status: str) -> None:
    """Zet de versie-marker + tijdstempel op het player_profiles-document,
    ONGEACHT of het resultaat 'opgehaald' of 'fallback' was - zie
    module-docstring voor waarom ook 'fallback' bewust gestempeld wordt."""
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
            {
                "klassement_logic_version": KLASSEMENT_LOGIC_VERSION,
                "klassement_last_checked_at": _utc_now_iso(),
                "klassement_last_result": status,
            },
            merge=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[{player_id}] Kon versie-stempel niet wegschrijven: {e}")


def run(
    max_per_run: int = DEFAULT_MAX_PER_RUN,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    max_periods_per_player: Optional[int] = DEFAULT_MAX_PERIODS_PER_PLAYER,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    profiles = _all_profiles()

    # Telling van ALLE kandidaten (voor rapportage), los van de max-cap.
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
        logger.info(f"({i}/{len(te_verwerken)}) {naam} ({pid})...")

        r = refresh_one(pid, naam, max_periods=max_periods_per_player, dry_run=dry_run)
        resultaten.append(r)

        if r["status"] == "opgehaald":
            logger.info(f"  -> {r['periodes']} periode(s) opgehaald")
        elif r["status"] == "fallback":
            logger.warning(f"  -> {r['status']}: {r.get('note')}")
        else:
            logger.warning(f"  -> {r['status']}: {r.get('note')}")

        if i < len(te_verwerken):
            time.sleep(pause_seconds)

    samenvatting = {
        "totaal_profielen": len(profiles),
        "kandidaten": len(alle_kandidaten),
        "deze_run": len(te_verwerken),
        "opgehaald": sum(1 for r in resultaten if r["status"] == "opgehaald"),
        "fallback": sum(1 for r in resultaten if r["status"] == "fallback"),
        "fout": sum(1 for r in resultaten if r["status"] in ("fout", "leeg", "opslaan_mislukt")),
        "resterend_na_deze_run": max(0, len(alle_kandidaten) - len(te_verwerken)),
        "resultaten": resultaten,
    }
    return samenvatting


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(
        description="Controleert/herstelt de TVL-klassementshistoriek van alle spelers, "
                    "los van matchdata-, padelstat- of poule-scraping."
    )
    parser.add_argument("--max", type=int, default=int(os.environ.get("KLASSEMENT_MAX", DEFAULT_MAX_PER_RUN)),
                        help=f"Max aantal spelers deze run (standaard {DEFAULT_MAX_PER_RUN}, of env KLASSEMENT_MAX).")
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS,
                        help=f"Pauze in seconden tussen spelers (standaard {DEFAULT_PAUSE_SECONDS}).")
    parser.add_argument(
        "--max-periods-per-player", type=int,
        default=(
            int(os.environ["KLASSEMENT_MAX_PERIODS"])
            if os.environ.get("KLASSEMENT_MAX_PERIODS") else DEFAULT_MAX_PERIODS_PER_PLAYER
        ),
        help="Beperk het aantal periodes per speler binnen 1 run (standaard: geen cap, volledige historiek).",
    )
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
        max_periods_per_player=args.max_periods_per_player,
        force_all=args.force_all,
        only_player_id=args.player,
        dry_run=args.dry_run,
    )

    print("\n=== Samenvatting klassement-controle ===")
    print(f"Totaal profielen        : {resultaat['totaal_profielen']}")
    print(f"Kandidaten (nog te doen) : {resultaat['kandidaten']}")
    print(f"Verwerkt deze run        : {resultaat['deze_run']}")
    if not args.dry_run:
        print(f"  Opgehaald              : {resultaat.get('opgehaald', 0)}")
        print(f"  Fallback (nog kapot)   : {resultaat.get('fallback', 0)}")
        print(f"  Fout                   : {resultaat.get('fout', 0)}")
        print(f"Resterend na deze run    : {resultaat.get('resterend_na_deze_run', 0)}")
        if resultaat.get("fallback", 0) > 0:
            print(
                f"\n⚠️ {resultaat['fallback']} speler(s) geven na de cookie-fix ALSNOG de "
                "'Huidige pagina'-fallback. Dat wijst op een ander, apart probleem "
                "(gewijzigde paginastructuur?) - controleer klassement_debug.html voor deze spelers."
            )
        if resultaat.get("resterend_na_deze_run", 0) > 0:
            print(
                f"\n{resultaat['resterend_na_deze_run']} speler(s) volgen bij de VOLGENDE "
                "(dagelijkse) run — verhoog --max om dit sneller in te lopen."
            )
