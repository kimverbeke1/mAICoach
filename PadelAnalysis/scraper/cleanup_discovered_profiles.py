"""
cleanup_discovered_profiles.py - verwijdert AUTOMATISCH AANGEMAAKTE
spelersprofielen (ghost-profielen) weer uit Firestore.

Locatie: PadelAnalysis/scraper/cleanup_discovered_profiles.py

PADEL_ANALYSIS_DISCOVERY_CLEANUP_2026-09-23
--------------------------------------------------------------------------
AANLEIDING: een run die enkel het klassement van de BESTAANDE spelers moest
herstellen -

    python enrich_opponents.py --all --no-padelstat --refresh --klassement-max 50

- maakte ~1468 nieuwe profielen aan, omdat enrich() destijds do_discover=True
als default had (zie PADEL_ANALYSIS_DISCOVERY_OPT_IN_2026-09-23 in
enrich_opponents.py, waar dat is omgedraaid naar een expliciete opt-in).
Dit script ruimt de gevolgen van zo'n run weer op.

HOE HET VEILIG BLIJFT
--------------------------------------------------------------------------
enrich_opponents.ensure_profiles() zet op ELK automatisch aangemaakt profiel
twee velden:

    added_by      = "auto_opponent_discovery"
    discovered_at = <ISO-tijdstempel van die run>

Dit script selecteert UITSLUITEND documenten met dat added_by-veld. Een
profiel dat jij zelf via de app hebt toegevoegd heeft dat veld niet en komt
dus nooit in aanmerking - ongeacht welke opties je meegeeft.

Bovendien, standaard beschermd (nooit verwijderd, ook niet met --apply):
  - je eigen speler (app_settings.home_player_id);
  - elk profiel waarvoor al MATCHDATA in de players-collectie staat, want
    dat is geen lege ghost meer maar een speler die effectief gescrapet is;
  - elk profiel met een opgeslagen padelstat-rating of klassement_history,
    om dezelfde reden.
Met --include-enriched kan je die laatste twee beschermingen opheffen, maar
dan moet je dat expliciet vragen.

--------------------------------------------------------------------------
PADEL_ANALYSIS_CLEANUP_INSPECT_PROTECTED_2026-09-23 (op verzoek van Kim: "ik
wil die 202 profielen eerst zien en welke club dat is. ik vermoed dat die ook
mogen verwijderd worden")
--------------------------------------------------------------------------
De categorie "hebben intussen matchdata/klassement/padelstat" was tot nu toe
enkel een TELLING - je zag dus niet WELKE profielen dat waren, en dus ook niet
of die bescherming terecht was. Dat is precies de verkeerde volgorde bij een
onomkeerbare actie.

Nieuwe vlag --show-protected toont die profielen volledig: naam, club, en per
profiel WAAROM het beschermd is (matchdata / klassement / padelstat), inclusief
het aantal matchen. Zo kan je zelf beoordelen of ze mogen verdwijnen.

BELANGRIJK om te weten bij die beoordeling: zo'n profiel is meestal NIET door
jou aangemaakt. Het is een tegenstander die in een eerdere run ontdekt werd EN
nadien door dezelfde enrichment-stap verrijkt is (padelstat/klassement
opgehaald). Het heeft dus wel data, maar daarom nog geen betekenis voor jouw
ploeg. Blijkt uit de clubkolom dat het allemaal vreemde clubs zijn, dan is
--include-enriched verantwoord.

GEBRUIK (PowerShell, vanuit PadelAnalysis/scraper):

    # 0. De beschermde profielen bekijken (verwijdert niets):
    python cleanup_discovered_profiles.py --since 2026-09-23 --show-protected

    # 1. Kijken wat er zou verdwijnen (verwijdert niets):
    python cleanup_discovered_profiles.py --since 2026-09-23

    # 2. Pas als de lijst klopt, effectief verwijderen:
    python cleanup_discovered_profiles.py --since 2026-09-23 --apply

    # Inclusief de verrijkte ghosts, na inspectie met --show-protected:
    python cleanup_discovered_profiles.py --since 2026-09-23 --include-enriched --apply

    # Eerst een back-up van wat je gaat wissen:
    python cleanup_discovered_profiles.py --since 2026-09-23 --csv verwijderd.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# --- path setup: zelfde patroon als enrich_opponents.py ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

logger = logging.getLogger(__name__)

# Exact de waarde die enrich_opponents.ensure_profiles() wegschrijft.
AUTO_DISCOVERY_MARKER = "auto_opponent_discovery"


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


def _parse_since(text: str) -> Optional[datetime]:
    """Aanvaardt '2026-09-23' of '2026-09-23T12:00:00'."""
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise SystemExit(f"Kon '{text}' niet lezen als datum. Gebruik bv. 2026-09-23.")


def _home_player_id() -> Optional[str]:
    try:
        return str((fb.get_app_settings() or {}).get("home_player_id") or "") or None
    except Exception:  # noqa: BLE001
        return None


def _match_count(player_id: str) -> int:
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        return 0
    return len(doc.get("matches") or [])


def _enrichment_reasons(player_id: str, profile: dict) -> list:
    """PADEL_ANALYSIS_CLEANUP_INSPECT_PROTECTED_2026-09-23: geeft de concrete
    redenen terug waarom dit profiel als 'verrijkt' geldt (en dus standaard
    beschermd is). Lege lijst = een lege ghost, veilig te verwijderen.

    Bewust als LIJST i.p.v. een bool, zodat --show-protected kan tonen WAT er
    precies aanwezig is - anders blijft het een black box en moet je op mijn
    woord geloven dat de bescherming terecht is."""
    redenen = []

    aantal = _match_count(player_id)
    if aantal:
        redenen.append(f"matchdata ({aantal})")

    if profile.get("klassement_history"):
        redenen.append("klassement")

    try:
        if profile.get(fb.OFFICIAL_KLASSEMENT_VIA_PADELSTAT_FIELD):
            redenen.append("officieel klassement")
    except AttributeError:
        # Oudere firebase_service.py zonder dat veldconstante - geen reden
        # om hier te crashen, de andere controles volstaan.
        pass

    try:
        cached = fb.get_padelstat_rating(player_id)
        if cached and cached.get("rating") is not None:
            redenen.append(f"padelstat (P{cached['rating']})")
    except Exception:  # noqa: BLE001
        pass

    return redenen


def collect(since: Optional[datetime], include_enriched: bool) -> tuple[list, list, dict]:
    """Verzamelt (te_verwijderen, beschermd_verrijkt, tellingen).

    beschermd_verrijkt bevat de profielen die enkel dankzij de verrijkings-
    bescherming blijven staan - die lijst voedt --show-protected."""
    tellingen = {"eigen_speler": 0, "buiten_periode": 0, "handmatig": 0}
    home_id = _home_player_id()
    kandidaten = []
    verrijkt = []

    try:
        docs = list(fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream())
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Kon player_profiles niet lezen: {exc}")

    print(f"{len(docs)} profiel(en) in de database.\n")

    if not home_id:
        # Niet fataal: je eigen profiel heeft normaal geen added_by-marker en
        # valt dus sowieso onder "handmatig toegevoegd". Wel het vermelden
        # waard, want de bescherming die je verwacht is er niet.
        print(
            "Let op: app_settings.home_player_id is niet ingesteld, dus je eigen speler kan\n"
            "niet expliciet beschermd worden. Dat is hier ongevaarlijk zolang jouw profiel\n"
            "handmatig is toegevoegd (dan heeft het geen auto-discovery-markering), maar\n"
            "controleer de lijst hieronder toch even op je eigen naam.\n"
        )

    for doc in docs:
        data = doc.to_dict() or {}
        pid = str(data.get("player_id") or doc.id)

        if str(data.get("added_by") or "") != AUTO_DISCOVERY_MARKER:
            tellingen["handmatig"] += 1
            continue

        if home_id and pid == home_id:
            tellingen["eigen_speler"] += 1
            continue

        discovered_at = _parse_iso(data.get("discovered_at"))
        if since is not None:
            if discovered_at is None or discovered_at < since:
                tellingen["buiten_periode"] += 1
                continue

        rij = {
            "player_id": pid,
            "display_name": data.get("display_name") or "",
            "club": data.get("club") or "(geen club)",
            "discovered_at": data.get("discovered_at") or "",
        }

        redenen = _enrichment_reasons(pid, data)
        if redenen and not include_enriched:
            rij["beschermd_want"] = ", ".join(redenen)
            verrijkt.append(rij)
            continue

        rij["heeft"] = ", ".join(redenen) if redenen else "-"
        kandidaten.append(rij)

    kandidaten.sort(key=lambda r: r["display_name"] or r["player_id"])
    verrijkt.sort(key=lambda r: (r["club"], r["display_name"]))
    return kandidaten, verrijkt, tellingen


def _print_protected(verrijkt: list) -> None:
    """PADEL_ANALYSIS_CLEANUP_INSPECT_PROTECTED_2026-09-23."""
    print(f"\n{'=' * 78}")
    print(f"BESCHERMDE PROFIELEN ({len(verrijkt)}) - gegroepeerd per club")
    print(f"{'=' * 78}")
    print(
        "Deze zijn ook automatisch ontdekt, maar hebben intussen data. Staan hier enkel\n"
        "vreemde clubs, dan zijn het tegenstanders en mogen ze mee weg (--include-enriched).\n"
    )

    per_club: dict = {}
    for r in verrijkt:
        per_club.setdefault(r["club"], []).append(r)

    for club in sorted(per_club, key=lambda c: (-len(per_club[c]), c)):
        rijen = per_club[club]
        print(f"\n--- {club}  ({len(rijen)} profiel(en)) ---")
        for r in rijen:
            print(f"  {r['player_id']:<12} {r['display_name']:<34} {r['beschermd_want']}")

    print(f"\n{'-' * 78}")
    print("Samenvatting per club:")
    for club in sorted(per_club, key=lambda c: (-len(per_club[c]), c)):
        print(f"  {len(per_club[club]):>5}  {club}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(
        description="Verwijder automatisch aangemaakte (ghost) spelersprofielen."
    )
    parser.add_argument("--since", default=None,
                        help="Enkel profielen ontdekt VANAF deze datum, bv. 2026-09-23.")
    parser.add_argument("--all-discovered", action="store_true",
                        help="Alles wat ooit automatisch ontdekt is (negeert --since).")
    parser.add_argument("--include-enriched", action="store_true",
                        help="Verwijder OOK profielen die intussen matchdata/klassement/padelstat "
                             "hebben (standaard blijven die beschermd).")
    parser.add_argument("--show-protected", action="store_true",
                        help="Toon de beschermde profielen (naam, club, reden) en stop. "
                             "Verwijdert nooit iets.")
    parser.add_argument("--apply", action="store_true",
                        help="Effectief verwijderen. Zonder deze vlag is het een dry-run.")
    parser.add_argument("--csv", default=None,
                        help="Schrijf de betrokken profielen weg naar dit CSV-bestand.")
    args = parser.parse_args()

    if not args.since and not args.all_discovered:
        raise SystemExit(
            "Geef --since <datum> op (bv. --since 2026-09-23), of --all-discovered als je "
            "echt ALLE ooit automatisch ontdekte profielen wil opruimen."
        )

    since = None if args.all_discovered else _parse_since(args.since)
    if since:
        print(f"Filter: automatisch ontdekt VANAF {since:%Y-%m-%d %H:%M} UTC.\n")
    else:
        print("Filter: ALLE ooit automatisch ontdekte profielen.\n")

    kandidaten, verrijkt, tellingen = collect(since, args.include_enriched)

    # --show-protected: inspecteren en stoppen, nooit verwijderen.
    if args.show_protected:
        if not verrijkt:
            if args.include_enriched:
                print("Met --include-enriched is er niets beschermd - laat die vlag weg om de "
                      "beschermde profielen te zien.")
            else:
                print("Geen beschermde profielen in deze selectie.")
            return
        _print_protected(verrijkt)
        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(verrijkt[0].keys()), delimiter=";")
                writer.writeheader()
                writer.writerows(verrijkt)
            print(f"\nVolledige lijst weggeschreven naar: {args.csv}")
        print("\nEr is NIETS verwijderd (--show-protected is enkel inspectie).")
        print("Mogen deze mee weg? Voeg dan --include-enriched toe aan het opruimcommando.")
        return

    print("Beschermd (blijven staan):")
    print(f"  {tellingen['handmatig']:>6}  handmatig/anders toegevoegd (geen auto-discovery)")
    print(f"  {tellingen['buiten_periode']:>6}  buiten de opgegeven periode")
    print(f"  {len(verrijkt):>6}  hebben intussen matchdata/klassement/padelstat")
    print(f"  {tellingen['eigen_speler']:>6}  je eigen speler")
    if verrijkt:
        print("\n  Tip: draai hetzelfde commando met --show-protected om die laatste groep")
        print("       met naam en club te zien voor je beslist.")
    print()

    if not kandidaten:
        print("Geen profielen die aan de criteria voldoen. Er valt niets op te ruimen.")
        return

    print(f"{len(kandidaten)} profiel(en) komen in aanmerking om verwijderd te worden:\n")
    for r in kandidaten[:25]:
        print(f"  {r['player_id']:<12} {r['display_name']:<34} {r['club']}")
    if len(kandidaten) > 25:
        print(f"  ... en {len(kandidaten) - 25} andere (gebruik --csv voor de volledige lijst)")
    print()

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(kandidaten[0].keys()), delimiter=";")
            writer.writeheader()
            writer.writerows(kandidaten)
        print(f"Volledige lijst weggeschreven naar: {args.csv}\n")

    if not args.apply:
        print("DRY-RUN: er is NIETS verwijderd.")
        print("Klopt de lijst hierboven? Draai dan hetzelfde commando opnieuw met --apply.")
        return

    print("Verwijderen...")
    verwijderd = 0
    mislukt = 0
    for r in kandidaten:
        try:
            # Enkel het PROFIEL wissen. Het players-document blijft ongemoeid:
            # lege ghosts hebben er normaal geen, en verrijkte profielen komen
            # hier enkel terecht als je daar met --include-enriched expliciet
            # om vroeg - hun matchdata blijft dan bewaard en kan later opnieuw
            # aan een profiel gekoppeld worden.
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(r["player_id"]).delete()
            verwijderd += 1
            if verwijderd % 100 == 0:
                print(f"  {verwijderd}/{len(kandidaten)}...")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"  {r['player_id']} ({r['display_name']}) -> FOUT: {exc}")
            mislukt += 1

    print("\n=== Samenvatting ===")
    print(f"Verwijderd : {verwijderd}")
    print(f"Mislukt    : {mislukt}")


if __name__ == "__main__":
    main()
