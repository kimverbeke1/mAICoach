# -*- coding: utf-8 -*-
"""
refresh_klassement_only.py — geïsoleerd, dagelijks script dat de TVL-
klassementshistoriek van alle spelers (eigen team + tegenstanders)
controleert/herstelt. Doet NIETS met matchdata, padelstat of poule-schema's.

Locatie: PadelAnalysis/scraper/refresh_klassement_only.py
(naast enrich_opponents.py / ci_scrape_all.py / refresh_padelstat_only.py,
zelfde path-setup patroon)

--------------------------------------------------------------------------
WAAROM DIT EEN APART SCRIPT IS
--------------------------------------------------------------------------
Op verzoek van Kim (17 september): klassementshistoriek voor tegenstanders
werd tot nu UITSLUITEND lokaal opgehaald, via de checkbox "📈 Ook
klassementshistoriek ophalen" in opponent_scout_ui.py:

    def _ensure_klassement(player_ids, ...):
        if not is_scraping_available():
            return   # <-- stopt hier volledig op Streamlit Cloud

is_scraping_available() is enkel True in een lokale omgeving met
Playwright/browser-binaries. Op de gedeployde Streamlit Cloud-app (waar Kim
uitsluitend test) is dit ALTIJD False, dus klassement voor tegenstanders
werd op Cloud NOOIT automatisch aangevuld - in tegenstelling tot padelstat,
waarvoor sinds gisteren wel al een dagelijkse GitHub Actions-workflow
bestaat (refresh_padelstat_only.py / refresh-padelstat.yml).

Dit script is het klassement-equivalent daarvan: volledig zelfstandig,
draait op GitHub Actions (waar Playwright wel beschikbaar is, net als bij
scrape-padel.yml en refresh-padelstat.yml), eigen workflow, eigen
tijdslimiet, geen afhankelijkheid van de Streamlit-UI.

--------------------------------------------------------------------------
WAAROM "VERVERSEN" TOT NU NIET HIELP (tweede, apart probleem, hier opgelost)
--------------------------------------------------------------------------
Zelfs los van de is_scraping_available()-blokkade hierboven: meerdere
spelers (Breda Hilde, Mondy Severine, De Pourcq Hilde) hadden een
klassement_history-veld dat WEL bestond, maar vrijwel leeg was - één
enkele rij met periode "Huidige pagina" en klassement=None. Dat komt door
een bug in scrape_klassement.py (PADEL_ANALYSIS_KLASSEMENT_COOKIE_VERIFY_
FIX_2026-09-17, zie dat bestand): de cookie-consent-banner werd niet
betrouwbaar gesloten, waardoor de periode-selector niet gevonden werd en de
scrape terugviel op een vrijwel inhoudsloze noodgreep. fb.get_player_
profile()/get_player() zag dus WEL een klassement_history-veld -> de oude
"_has_klassement()"-check (enkel bestaan, geen inhoud-check) beschouwde de
speler dan ten onrechte als "al klaar" en sloeg hem/haar bij een volgende
ronde stilzwijgend over.

Fix, in _is_klassement_usable() hieronder: een klassement_history telt nu
enkel als "bruikbaar" als minstens 1 periode een ECHT klassement-cijfer
bevat (niet enkel het bestaan van het veld). Spelers met enkel de
"Huidige pagina"-lege noodgreep worden dus AUTOMATISCH als kandidaat
herkend voor een nieuwe poging - zonder dat Kim ze handmatig moet
aanwijzen. Dit is het klassement-equivalent van refresh_padelstat_only.py's
PADELSTAT_LOGIC_VERSION-zelfherstelmechanisme, hier gebaseerd op de
INHOUD van de bestaande data i.p.v. een aparte versie-marker (want het
bestaande "leeg door een mislukte scrape"-patroon is zelf al goed
detecteerbaar, zonder een aparte marker nodig te hebben).

--------------------------------------------------------------------------
DAGELIJKS, MET EEN HARDE LIMIET PER RUN (batching)
--------------------------------------------------------------------------
Elke klassement-opzoeking kost een VOLLEDIGE Playwright-sessie met
meerdere periode-selecties (~30-90s per speler, aanzienlijk trager dan
padelstat's ~10-30s). Om nooit tegen een workflow-timeout aan te lopen,
verwerkt dit script STANDAARD MAX 15 spelers per run (KLASSEMENT_MAX,
overschrijfbaar via env of --max). Spelers die deze run niet aan bod
komen, worden gewoon de VOLGENDE dagelijkse run opgepikt.

--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    python refresh_klassement_only.py --dry-run
    python refresh_klassement_only.py
    python refresh_klassement_only.py --max 20
    python refresh_klassement_only.py --player 1759548          (1 speler, altijd)
    python refresh_klassement_only.py --force-all --max 10      (iedereen herzien)
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

DEFAULT_MAX_PER_RUN = 15
DEFAULT_MAX_PERIODS = 10
DEFAULT_PAUSE_SECONDS = 2.0


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


def _get_klassement_doc(player_id: str) -> Optional[dict]:
    """Geeft het klassement_history-veld terug, van het players-document als
    dat bestaat, anders van player_profiles — zelfde volgorde als de rest
    van de codebase (bv. opponent_dossier.build_player_summary())."""
    try:
        player_doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        player_doc = {}
    if player_doc.get("klassement_history"):
        return player_doc["klassement_history"]
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        profile_doc = {}
    return profile_doc.get("klassement_history")


def _is_klassement_usable(klass_doc: Optional[dict]) -> bool:
    """PADEL_ANALYSIS_KLASSEMENT_COOKIE_VERIFY_FIX_2026-09-17 (zelfherstel-
    kant): een klassement_history telt enkel als 'bruikbaar' zodra minstens
    1 periode een ECHT klassement-cijfer bevat. Vangt zo het 'Huidige
    pagina'-met-klassement=None-patroon op dat de cookie-bannerbug
    achterliet — dat is namelijk een technisch aanwezig, maar inhoudelijk
    leeg veld."""
    if not klass_doc:
        return False
    history = klass_doc.get("history") or []
    if not history:
        return False
    return any(row.get("klassement") for row in history)


def needs_check(profile: dict, force_all: bool = False) -> tuple[bool, str]:
    """Bepaalt of deze speler deze run gecontroleerd moet worden, en waarom."""
    if force_all:
        return True, "force-all"

    player_id = _norm_id(profile.get("player_id"))
    klass_doc = _get_klassement_doc(player_id)
    if not _is_klassement_usable(klass_doc):
        if klass_doc:
            return True, "aanwezig maar leeg (vermoedelijk mislukte oude scrape)"
        return True, "geen klassementshistoriek bekend"

    return False, "al bruikbare klassementshistoriek aanwezig"


def select_players_to_process(
    profiles: list,
    max_per_run: int,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
) -> list:
    """Kiest WELKE spelers deze run verwerkt worden. Prioriteit: spelers
    zonder ENIGE klassementshistoriek eerst (waarschijnlijk nooit geprobeerd),
    dan spelers met een 'leeg door mislukte scrape'-record (zelfherstel)."""
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
        "geen klassementshistoriek bekend": 1,
        "aanwezig maar leeg (vermoedelijk mislukte oude scrape)": 2,
    }
    kandidaten.sort(key=lambda item: prioriteit.get(item[1], 9))
    return [p for p, _ in kandidaten[:max_per_run]]


def refresh_one(player_id: str, naam: str, max_periods: int, dry_run: bool = False) -> dict:
    """Voert de effectieve TVL-klassement-opzoeking uit voor 1 speler en
    schrijft het resultaat weg naar ZOWEL players als player_profiles —
    zelfde opslagvorm als enrich_opponents.run_klassement_for_players()."""
    from scrape_klassement import (  # lazy: enkel nodig als deze stap draait
        scrape_klassement,
        klassement_to_history_summary,
        extract_niveau_winrates,
    )

    result = {"player_id": player_id, "naam": naam, "status": None, "klassement": None, "periodes": 0}

    try:
        periods = scrape_klassement(player_id, max_periods=max_periods, headless=True)
    except Exception as e:  # noqa: BLE001
        result["status"] = "fout"
        result["note"] = str(e)
        return result

    history = klassement_to_history_summary(periods)
    niveau_winrates = extract_niveau_winrates(periods)

    if not history or not any(row.get("klassement") for row in history):
        result["status"] = "leeg_gebleven"
        result["note"] = (
            f"{len(periods)} periode(s) gescraped, maar geen enkele met een geldig klassement-cijfer "
            "(mogelijk een andere, nieuwe oorzaak dan de cookie-banner-bug)."
        )
        # We schrijven dit WEL weg (met scraped_at), zodat het bestaan van
        # een recente, mislukte poging zichtbaar is voor verdere diagnose —
        # maar needs_check() zal deze speler bij de VOLGENDE run opnieuw als
        # kandidaat beschouwen (want _is_klassement_usable blijft False).
        if not dry_run:
            _write_klassement(player_id, history, niveau_winrates, periods)
        return result

    result["status"] = "opgehaald"
    result["klassement"] = history[0].get("klassement")
    result["periodes"] = len(history)

    if not dry_run:
        _write_klassement(player_id, history, niveau_winrates, periods)

    return result


def _write_klassement(player_id: str, history: list, niveau_winrates: dict, raw_periods: list) -> None:
    klass_data = {
        "history": history,
        "niveau_winrates": niveau_winrates,
        "raw_periods": raw_periods,
        "scraped_at": _utc_now_iso(),
    }
    payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
        fb.db.collection(fb.PLAYERS_COLLECTION).document(str(player_id)).set(payload, merge=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[{player_id}] Kon klassement niet wegschrijven: {e}")


def run(
    max_per_run: int = DEFAULT_MAX_PER_RUN,
    max_periods: int = DEFAULT_MAX_PERIODS,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    profiles = _all_profiles()

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

        r = refresh_one(pid, naam, max_periods=max_periods, dry_run=dry_run)
        resultaten.append(r)

        if r["status"] == "opgehaald":
            logger.info(f"  -> {r['klassement'] or '?'} ({r['periodes']} periode(s))")
        elif r["status"] == "leeg_gebleven":
            logger.warning(f"  -> LEEG GEBLEVEN: {r.get('note')}")
        else:
            logger.warning(f"  -> {r['status']}: {r.get('note')}")

        if i < len(te_verwerken):
            time.sleep(pause_seconds)

    samenvatting = {
        "totaal_profielen": len(profiles),
        "kandidaten": len(alle_kandidaten),
        "deze_run": len(te_verwerken),
        "opgehaald": sum(1 for r in resultaten if r["status"] == "opgehaald"),
        "leeg_gebleven": sum(1 for r in resultaten if r["status"] == "leeg_gebleven"),
        "fout": sum(1 for r in resultaten if r["status"] == "fout"),
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
    parser.add_argument("--max-periods", type=int, default=DEFAULT_MAX_PERIODS,
                        help=f"Max periodes per speler om te scrapen (standaard {DEFAULT_MAX_PERIODS}).")
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS,
                        help=f"Pauze in seconden tussen spelers (standaard {DEFAULT_PAUSE_SECONDS}).")
    parser.add_argument("--force-all", action="store_true",
                        help="Negeer bestaande data en controleer IEDEREEN opnieuw (traag; gebruik samen met --max).")
    parser.add_argument("--player", type=str, default=None,
                        help="Enkel deze speler controleren (player_id), altijd.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon enkel wie verwerkt zou worden, scrape niets, schrijf niets weg.")
    args = parser.parse_args()

    resultaat = run(
        max_per_run=args.max,
        max_periods=args.max_periods,
        pause_seconds=args.pause,
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
        print(f"  Leeg gebleven          : {resultaat.get('leeg_gebleven', 0)}")
        print(f"  Fout                   : {resultaat.get('fout', 0)}")
        print(f"Resterend na deze run    : {resultaat.get('resterend_na_deze_run', 0)}")
        if resultaat.get("resterend_na_deze_run", 0) > 0:
            print(
                f"\n{resultaat['resterend_na_deze_run']} speler(s) volgen bij de VOLGENDE "
                "(dagelijkse) run — verhoog --max om dit sneller in te lopen."
            )
