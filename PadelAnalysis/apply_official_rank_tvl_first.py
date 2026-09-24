"""
apply_official_rank_tvl_first.py

PADEL_ANALYSIS_OFFICIAL_RANK_TVL_FIRST_2026-09-25

Draait de prioriteit om die op 2026-09-24 werd ingevoerd
(PADEL_ANALYSIS_OFFICIAL_RANK_SOURCE_FIX_2026-09-24).

PROBLEEM
--------
Het "officieel klassement" dat de app toont komt uit de padelstats.be
zoekkaart ("P200 - CLUB", veld matched_klassement). Die waarde loopt
achter: voor speler 1790766 geeft padelstat P200 terwijl de TVL-pagina
(scrape_klassement.py, versie 2026-09-23-official-first) correct P300
geeft als selected_period_klassement.

Twee plekken geven die snapshot onterecht voorrang:
  1. dashboard_common._official_current_rank()
  2. opponent_analysis._build_report()

FIX
---
TVL-historiek wordt opnieuw de primaire bron voor het officiele
klassement; de padelstat-snapshot blijft enkel terugval wanneer er nog
geen historiek bestaat. Playing strength blijft ongewijzigd uit
padelstat komen.

Het script past alleen de twee bovenstaande plekken aan, maakt van elk
gewijzigd bestand eerst een .bak-kopie, en verifieert achteraf dat elke
wijziging effectief is doorgevoerd. Het is idempotent: een tweede run
meldt gewoon dat alles al toegepast is.

Gebruik (vanuit de map PadelAnalysis):
    python apply_official_rank_tvl_first.py
    python apply_official_rank_tvl_first.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

VERSION_MARKER = "PADEL_ANALYSIS_OFFICIAL_RANK_TVL_FIRST_2026-09-25"

ROOT = Path(__file__).resolve().parent
DASHBOARD_COMMON = ROOT / "dashboard_common.py"
OPPONENT_ANALYSIS = ROOT / "opponent_analysis.py"


class PatchError(RuntimeError):
    pass


def _read(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"Bestand niet gevonden: {path}")
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str, dry_run: bool) -> None:
    if dry_run:
        return
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. dashboard_common.py -> _official_current_rank(): historiek eerst
# ---------------------------------------------------------------------------

_DC_OLD = re.compile(
    r"""
    ^(?P<indent>[ ]*)snapshot\s*=\s*_official_rank_from_padelstat_snapshot\(player_id\)\s*\n
    (?:^[ ]*\n)*
    ^[ ]*if\s+snapshot\s+is\s+not\s+None\s*:\s*\n
    ^[ ]*return\s+snapshot\s*\n
    (?:^[ ]*\n)*
    ^[ ]*rows\s*=\s*od\._history_rows\(ranking_doc\)\s*\n
    ^[ ]*return\s+float\(rows\[0\]\["rank"\]\)\s+if\s+rows\s+else\s+None\s*\n
    """,
    re.MULTILINE | re.VERBOSE,
)

_DC_NEW = '''{indent}# {marker}: de TVL-historiek is opnieuw de PRIMAIRE bron.
{indent}# De padelstat-snapshot komt uit de zoekkaart ("P200 - CLUB",
{indent}# matched_klassement) en loopt aantoonbaar achter: speler 1790766
{indent}# kreeg daar P200 terwijl scrape_klassement.py (versie
{indent}# 2026-09-23-official-first) correct P300 leest als
{indent}# selected_period_klassement. De snapshot blijft enkel terugval
{indent}# zolang er nog GEEN historiek bestaat voor deze speler.
{indent}rows = od._history_rows(ranking_doc)
{indent}if rows and rows[0].get("rank") is not None:
{indent}    try:
{indent}        return float(rows[0]["rank"])
{indent}    except (TypeError, ValueError):
{indent}        pass

{indent}snapshot = _official_rank_from_padelstat_snapshot(player_id)
{indent}if snapshot is not None:
{indent}    return snapshot

{indent}return None
'''


def patch_dashboard_common(text: str) -> tuple[str, str]:
    if VERSION_MARKER in text:
        return text, "al toegepast (marker aanwezig)"

    match = _DC_OLD.search(text)
    if not match:
        raise PatchError(
            "Kon het snapshot-eerst-blok in _official_current_rank() niet "
            "terugvinden in dashboard_common.py. Het bestand wijkt af van de "
            "versie waarop deze patch gebouwd is - niets gewijzigd."
        )

    indent = match.group("indent")
    replacement = _DC_NEW.format(indent=indent, marker=VERSION_MARKER)
    return text[: match.start()] + replacement + text[match.end() :], "aangepast"


# ---------------------------------------------------------------------------
# 2. opponent_analysis.py -> _build_report(): snapshot enkel als fallback
# ---------------------------------------------------------------------------

_OA_OLD = re.compile(
    r"^(?P<indent>[ ]*)if\s+snapshot_rank\s+is\s+not\s+None\s*:\s*$",
    re.MULTILINE,
)

_OA_NEW = (
    '{indent}# {marker}: enkel nog terugval. Voorheen overschreef deze regel\n'
    '{indent}# het TVL-klassement ALTIJD met de padelstat-zoekkaartwaarde,\n'
    '{indent}# waardoor elke speler het achterlopende cijfer toonde.\n'
    '{indent}if snapshot_rank is not None and summary.get("current_rank") is None:'
)

_OA_SCHEMA = re.compile(r"^REPORT_SCHEMA_VERSION\s*=\s*(\d+).*$", re.MULTILINE)


def patch_opponent_analysis(text: str) -> tuple[str, str]:
    if VERSION_MARKER in text:
        return text, "al toegepast (marker aanwezig)"

    matches = list(_OA_OLD.finditer(text))
    if len(matches) != 1:
        raise PatchError(
            f"Verwachtte precies 1 'if snapshot_rank is not None:'-regel in "
            f"opponent_analysis.py, maar vond er {len(matches)} - niets gewijzigd."
        )

    m = matches[0]
    text = (
        text[: m.start()]
        + _OA_NEW.format(indent=m.group("indent"), marker=VERSION_MARKER)
        + text[m.end() :]
    )

    # Schema-versie ophogen, anders blijven bestaande team-rapporten uit
    # Firestore gewoon de oude, foute current_rank tonen zonder herberekening.
    schema = _OA_SCHEMA.search(text)
    if not schema:
        raise PatchError(
            "REPORT_SCHEMA_VERSION niet gevonden in opponent_analysis.py. "
            "Zonder ophoging blijven gecachete rapporten de oude waarde tonen."
        )
    oud = int(schema.group(1))
    nieuw = oud + 1
    text = (
        text[: schema.start()]
        + f"REPORT_SCHEMA_VERSION = {nieuw}  # TVL officieel klassement is "
        f"weer autoritatief; padelstat-snapshot enkel als terugval"
        + text[schema.end() :]
    )
    return text, f"aangepast (schema {oud} -> {nieuw}, forceert herberekening)"


# ---------------------------------------------------------------------------

def verify(path: Path) -> bool:
    return VERSION_MARKER in path.read_text(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Toon enkel wat er zou wijzigen, schrijf niets weg.",
    )
    args = ap.parse_args()

    taken = [
        (DASHBOARD_COMMON, patch_dashboard_common),
        (OPPONENT_ANALYSIS, patch_opponent_analysis),
    ]

    gewijzigd = []
    for path, patcher in taken:
        try:
            origineel = _read(path)
            nieuw, status = patcher(origineel)
        except PatchError as exc:
            print(f"FOUT  {path.name}: {exc}")
            print("\nEr is NIETS gewijzigd. Los dit eerst op.")
            return 1

        if nieuw == origineel:
            print(f"OK    {path.name}: {status}")
            continue

        _write(path, nieuw, args.dry_run)
        gewijzigd.append(path)
        prefix = "DRY   " if args.dry_run else "PATCH "
        print(f"{prefix}{path.name}: {status}")

    if args.dry_run:
        print("\n--dry-run: er is niets naar schijf geschreven.")
        return 0

    print("\n=== Verificatie ===")
    alles_ok = True
    for path, _ in taken:
        ok = verify(path)
        alles_ok = alles_ok and ok
        print(f"{'OK  ' if ok else 'MIS '} {path.name}: marker {VERSION_MARKER}")

    if not alles_ok:
        print("\nMinstens een bestand mist de marker - controleer handmatig.")
        return 1

    if gewijzigd:
        print("\nBackups bewaard als:")
        for path in gewijzigd:
            print(f"  {path.name}.bak")

    print(
        "\nKlaar. Let op: bestaande player_profiles bevatten nog de oude "
        "waarde tot scrape_klassement.py opnieuw gedraaid heeft voor die "
        "spelers."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
