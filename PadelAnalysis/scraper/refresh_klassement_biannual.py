# -*- coding: utf-8 -*-
"""
refresh_klassement_biannual.py — geïsoleerd script dat het OFFICIËLE TVL-
klassement van ALLE spelers met bestaande profieldata TWEE KEER PER JAAR
controleert/vernieuwt, exact wanneer Tennis & Padel Vlaanderen het officiële
klassement zelf herberekent.

Locatie: PadelAnalysis/scraper/refresh_klassement_biannual.py
(naast refresh_klassement_only.py / refresh_padelstat_only.py, zelfde
path-setup-patroon)

--------------------------------------------------------------------------
PADEL_ANALYSIS_KLASSEMENT_BIANNUAL_SCHEDULE_2026-09-19 (op verzoek van Kim)
--------------------------------------------------------------------------
Kim's exacte melding: "even een opmerking ook nog over het officiële
padelklassement. Zomerklassement: de berekening start altijd op de maandag
van week 27 [...] tussen 27 juni en 3 juli. Winterklassement: [...] maandag
van week 49 [...] tussen 30 november en 6 december. Ik heb in het verleden
mails gekregen dat mijn klassement aangepast is op 2/12/2025 en 30/06/2025
en op 01/07/2025. Dat is dus de dag na of de dag van de aanpassing. Het
laatste nieuwe padelklassement ophalen kunnen we dus 2 keer per jaar apart
schedulen. [...] Bij een refresh van een speler moet je dus het officiële
klassement niet opnieuw scrapen voor die speler want dat verandert maar 2
keer per jaar en dat gaan we oplossen met scheduled scrape voor alle
spelers in mijn database die al profieldata hebben."

GEVERIFIEERD (zuivere datumwiskunde, los van Firestore/scraping):
    ISO-week-27-maandag 2026 = 29/06/2026 (Kim's eigen voorbeeld, klopt)
    ISO-week-49-maandag 2025 = 01/12/2025 (Kim's mail: 02/12/2025 = dag NA)
    ISO-week-27-maandag 2025 = 30/06/2025 (Kim's mail: exact DIE dag)
Dit bevestigt dat de officiële ISO-8601-weekberekening (iso_week_monday())
hieronder exact overeenkomt met de echte TVL-herberekeningsmomenten.

WAT DIT SCRIPT DOET
--------------------------------------------------------------------------
Dit is GEEN dagelijks script (in tegenstelling tot refresh_klassement_
only.py, dat hiermee NIET vervangen wordt maar een ANDER doel dient - zie
onder "VERHOUDING TOT refresh_klassement_only.py"). Dit script:
  1. Berekent, voor het huidige jaar, de exacte maandag van ISO-week 27
     (zomerklassement) en ISO-week 49 (winterklassement).
  2. Bepaalt of "vandaag" binnen een klein VEILIGHEIDSVENSTER rond een van
     die twee maandagen valt (WINDOW_DAYS_BEFORE/WINDOW_DAYS_AFTER
     hieronder) - is dat NIET het geval (355+ dagen per jaar), dan doet het
     script NIETS: geen enkele Firestore-read, geen enkele scrape. Dit is
     bewust GOEDKOOP op alle "gewone" dagen.
  3. Valt vandaag WEL binnen zo'n venster, dan wordt een PERIODE-ID bepaald
     (bv. "2026-zomer") en worden ALLE gekende spelerprofielen (eigen team
     + tegenstanders - "alle spelers in mijn database die al profieldata
     hebben") die voor DEZE periode nog geen geverifieerd klassement
     hebben, in kleine dagelijkse batches (max_per_run) ververst. Het
     venster is bewust een aantal dagen breed (zie WINDOW_DAYS_AFTER) zodat
     een grote spelerslijst over meerdere dagelijkse cron-runs verspreid
     kan worden zonder de workflow-tijdslimiet te raken - net als het
     bestaande batching-patroon in refresh_klassement_only.py/
     refresh_padelstat_only.py, maar dan slechts 2x per jaar geactiveerd
     i.p.v. dagelijks.
  4. Elke speler die deze periode al verwerkt is (marker
     "official_klassement_period_marker" == period_id), wordt overgeslagen
     - zo kan de workflow gerust élke dag binnen het venster draaien zonder
     ooit dubbel werk te doen, en wordt de volledige lijst gegarandeerd
     precies 1x per periode ververst, ook al duurt dat meerdere dagen.

VERHOUDING TOT refresh_klassement_only.py (blijft ONGEWIJZIGD bestaan!)
--------------------------------------------------------------------------
refresh_klassement_only.py blijft dagelijks draaien en blijft
verantwoordelijk voor:
  - het EERSTE keer ophalen van klassement voor een NIEUWE speler (nog
    nooit een klassement_history gehad) - "de ganse historiek ophalen mag
    blijven zoals het is als je een speler scrapt", exact zoals Kim vroeg;
  - het zelfherstel-mechanisme voor de "kapotte fallback"-historiek (van
    vóór de cookie-consent-fix, zie die module-docstring).
Dit NIEUWE script komt daar dus NIET voor in de plaats, maar VULT aan: het
garandeert dat een speler die AL een (correct) klassement heeft, dat cijfer
toch nog 2x per jaar op de juiste, officiële momenten opnieuw geverifieerd
krijgt - zonder dat dit ooit gebeurt bij een gewone, gerichte 1-speler-
refresh (zie PADEL_ANALYSIS_SINGLE_PLAYER_KLASSEMENT_REMOVED_2026-09-19 in
cloud_helpers.py, waar de klassement-trigger uit de "Scrape deze speler
nu"-knop is weggehaald, precies omdat DIT script die taak nu overneemt).

GEBRUIK (lokaal testen)
--------------------------------------------------------------------------
    python refresh_klassement_biannual.py --dry-run
    python refresh_klassement_biannual.py --simulate-date 2026-06-29 --dry-run
    python refresh_klassement_biannual.py --simulate-date 2026-06-30 --max 5
    python refresh_klassement_biannual.py --force --player 1759548   (test buiten venster, 1 speler)
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_MAX_PER_RUN = 20
DEFAULT_PAUSE_SECONDS = 2.0
# Veiligheidsvenster rond de exacte maandag: 1 dag ervoor (voor het geval de
# workflow een dag te vroeg draait of de berekening ergens net anders valt)
# tot 9 dagen erna (voldoende opeenvolgende dagelijkse cron-runs om een
# volledige spelerslijst in kleine batches te verwerken zonder de
# workflow-tijdslimiet te overschrijden).
WINDOW_DAYS_BEFORE = 1
WINDOW_DAYS_AFTER = 9


def _norm_id(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_week_monday(year: int, week: int) -> date:
    """Geeft de datum van de MAANDAG van een gegeven ISO-8601-week terug.
    ISO 8601: 4 januari valt altijd in week 1 van dat jaar - dit is de
    standaard, correcte manier om een ISO-weeknummer naar een datum om te
    zetten (GEVERIFIEERD tegen Kim's 3 bekende referentiedata, zie
    module-docstring)."""
    jan4 = date(year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
    return week1_monday + timedelta(weeks=week - 1)


def zomerklassement_monday(year: int) -> date:
    """Maandag van ISO-week 27 - valt tussen 27 juni en 3 juli."""
    return iso_week_monday(year, 27)


def winterklassement_monday(year: int) -> date:
    """Maandag van ISO-week 49 - valt tussen 30 november en 6 december."""
    return iso_week_monday(year, 49)


def current_period_id(today: date) -> Optional[str]:
    """Bepaalt of 'today' binnen het activatievenster van het zomer- of
    winterklassement valt. Geeft dan een unieke periode-ID terug (bv.
    '2026-zomer'). Buiten beide vensters: None - het script doet dan
    NIETS (355+ dagen per jaar, geen enkele scrape/Firestore-kost)."""
    for label, monday_fn in (("zomer", zomerklassement_monday), ("winter", winterklassement_monday)):
        monday = monday_fn(today.year)
        window_start = monday - timedelta(days=WINDOW_DAYS_BEFORE)
        window_end = monday + timedelta(days=WINDOW_DAYS_AFTER)
        if window_start <= today <= window_end:
            return f"{today.year}-{label}"
    return None


def _all_profiles_with_data() -> list:
    """'Alle spelers in mijn database die al profieldata hebben' (letterlijk
    op verzoek van Kim) - alle player_profiles-documenten met minstens een
    bruikbare naam (eigen team EN alle gekende tegenstanders)."""
    try:
        profiles = fb.search_player_profiles("", limit=10_000) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Kon profielen niet lezen: {e}")
        return []
    return [p for p in profiles if p.get("player_id") and p.get("display_name")]


def _needs_this_period(profile: dict, period_id: str, force: bool = False) -> bool:
    if force:
        return True
    return profile.get("official_klassement_period_marker") != period_id


def _has_matchdata(player_id: str) -> bool:
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        return False
    return bool(doc.get("matches"))


def _prioritize(profiles: list) -> list:
    """Spelers MET bestaande matchdata krijgen voorrang - zelfde patroon als
    enrich_opponents._prioritize()/refresh_klassement_only.py, zodat bij een
    eventuele afkapping op max_per_run de meest relevante spelers (actief
    in onze ontmoetingen) het eerst aan bod komen."""
    return sorted(
        profiles,
        key=lambda p: 0 if _has_matchdata(_norm_id(p.get("player_id"))) else 1,
    )


def _stamp(player_id: str, period_id: str, status: str) -> None:
    """Zet de periode-marker + tijdstempel, ONGEACHT of het resultaat
    'opgehaald' of een fout was - net als bij de bestaande *_only.py-
    scripts, zodat een mislukte poging niet elke dag binnen hetzelfde
    venster opnieuw geprobeerd wordt (een volgende periode triggert vanzelf
    een nieuwe poging via de nieuwe period_id)."""
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
            {
                "official_klassement_period_marker": period_id,
                "official_klassement_last_synced_at": _utc_now_iso(),
                "official_klassement_last_result": status,
            },
            merge=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[{player_id}] Kon periode-marker niet wegschrijven: {e}")


def refresh_one(player_id: str, naam: str, dry_run: bool = False) -> dict:
    """Haalt de VOLLEDIGE officiële klassementshistoriek op voor 1 speler,
    met dezelfde scrape_klassement.py-functies/opslagvorm als de bestaande
    lokale flow en refresh_klassement_only.py. Op uitdrukkelijk verzoek van
    Kim blijft dit de VOLLEDIGE historiek (net als bij het scrapen van een
    NIEUWE speler) - enkel de FREQUENTIE waarmee dit voor een reeds bekende
    speler gebeurt (2x/jaar i.p.v. bij elke losse 1-speler-refresh) is
    nieuw."""
    from scrape_klassement import (  # lazy: enkel nodig als deze stap draait
        scrape_klassement,
        klassement_to_history_summary,
        extract_niveau_winrates,
    )
    result = {"player_id": player_id, "naam": naam, "status": None, "periodes": 0, "note": None}
    try:
        periods = scrape_klassement(str(player_id), max_periods=None, headless=True)
    except Exception as e:  # noqa: BLE001
        result["status"] = "fout"
        result["note"] = str(e)
        return result
    if not periods:
        result["status"] = "leeg"
        result["note"] = "scrape_klassement() gaf een lege lijst terug (onverwacht)"
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


def run(
    max_per_run: int = DEFAULT_MAX_PER_RUN,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    force: bool = False,
    dry_run: bool = False,
    simulate_date: Optional[str] = None,
    only_player_id: Optional[str] = None,
) -> dict:
    today = date.fromisoformat(simulate_date) if simulate_date else datetime.now(timezone.utc).date()
    period_id = current_period_id(today)
    if not period_id and not force:
        logger.info(
            f"Vandaag ({today.isoformat()}) valt buiten het zomer-/winterklassement-venster - "
            "niets te doen (dit is NORMAAL gedrag, 355+ dagen per jaar draait dit script leeg door)."
        )
        return {"period_id": None, "kandidaten": 0, "deze_run": 0, "resultaten": []}
    period_id = period_id or f"{today.year}-force"
    logger.info(f"Actief venster gedetecteerd: periode='{period_id}' (vandaag: {today.isoformat()}).")
    profiles = _all_profiles_with_data()
    if only_player_id:
        wanted = {_norm_id(p) for p in str(only_player_id).split(",") if p.strip()}
        profiles = [p for p in profiles if _norm_id(p.get("player_id")) in wanted]
    kandidaten = [p for p in profiles if _needs_this_period(p, period_id, force=force)]
    geprioriteerd = _prioritize(kandidaten)
    te_verwerken = geprioriteerd if only_player_id else geprioriteerd[:max_per_run]
    logger.info(
        f"{len(profiles)} speler(s) met profieldata gevonden. {len(kandidaten)} kandidaat/kandidaten "
        f"voor periode '{period_id}', waarvan {len(te_verwerken)} deze run verwerkt worden "
        f"(max={max_per_run})."
    )
    if dry_run:
        logger.info("--dry-run: er wordt NIETS gescrapet of weggeschreven, enkel getoond wie aan bod zou komen.")
        for p in te_verwerken:
            logger.info(f"  zou verwerkt worden: {p.get('display_name')} ({p.get('player_id')})")
        return {
            "period_id": period_id, "kandidaten": len(kandidaten),
            "deze_run": len(te_verwerken), "resultaten": [],
        }
    resultaten = []
    for i, p in enumerate(te_verwerken, start=1):
        pid = _norm_id(p.get("player_id"))
        naam = p.get("display_name") or pid
        logger.info(f"({i}/{len(te_verwerken)}) {naam} ({pid})...")
        r = refresh_one(pid, naam, dry_run=dry_run)
        resultaten.append(r)
        if r["status"] == "opgehaald":
            logger.info(f"  -> {r['periodes']} periode(s) opgehaald")
        else:
            logger.warning(f"  -> {r['status']}: {r.get('note')}")
        _stamp(pid, period_id, r["status"])
        if i < len(te_verwerken):
            time.sleep(pause_seconds)
    samenvatting = {
        "period_id": period_id,
        "kandidaten": len(kandidaten),
        "deze_run": len(te_verwerken),
        "opgehaald": sum(1 for r in resultaten if r["status"] == "opgehaald"),
        "fout": sum(1 for r in resultaten if r["status"] in ("fout", "leeg", "opslaan_mislukt")),
        "resterend_na_deze_run": max(0, len(kandidaten) - len(te_verwerken)),
        "resultaten": resultaten,
    }
    return samenvatting


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(
        description="Ververst het OFFICIËLE TVL-klassement van alle spelers met profieldata, "
                    "maar ENKEL tijdens de 2 jaarlijkse activatievensters (zomer-/winterklassement)."
    )
    parser.add_argument("--max", type=int, default=int(os.environ.get("KLASSEMENT_BIANNUAL_MAX", DEFAULT_MAX_PER_RUN)),
                        help=f"Max aantal spelers deze run (standaard {DEFAULT_MAX_PER_RUN}, of env KLASSEMENT_BIANNUAL_MAX).")
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS,
                        help=f"Pauze in seconden tussen spelers (standaard {DEFAULT_PAUSE_SECONDS}).")
    parser.add_argument("--force", action="store_true",
                        help="Negeer het datumvenster EN de periode-marker (enkel voor handmatig testen/herstel).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon enkel wie verwerkt zou worden, scrape niets, schrijf niets weg.")
    parser.add_argument("--simulate-date", type=str, default=None,
                        help="YYYY-MM-DD: doe alsof 'vandaag' deze datum is (enkel voor testen).")
    parser.add_argument("--player", type=str, default=None,
                        help="Enkel deze speler(s) controleren (player_id, of komma-gescheiden lijst).")
    args = parser.parse_args()

    resultaat = run(
        max_per_run=args.max, pause_seconds=args.pause, force=args.force,
        dry_run=args.dry_run, simulate_date=args.simulate_date, only_player_id=args.player,
    )
    print("\n=== Samenvatting officieel-klassement (2x/jaar) ===")
    print(f"Periode                 : {resultaat['period_id']}")
    print(f"Kandidaten (nog te doen) : {resultaat['kandidaten']}")
    print(f"Verwerkt deze run        : {resultaat['deze_run']}")
    if not args.dry_run and resultaat.get("period_id"):
        print(f"  Opgehaald              : {resultaat.get('opgehaald', 0)}")
        print(f"  Fout                   : {resultaat.get('fout', 0)}")
        print(f"Resterend na deze run    : {resultaat.get('resterend_na_deze_run', 0)}")
        if resultaat.get("resterend_na_deze_run", 0) > 0:
            print(
                f"\n{resultaat['resterend_na_deze_run']} speler(s) volgen bij de VOLGENDE "
                "dagelijkse run binnen dit venster — verhoog --max om dit sneller in te lopen."
            )
