"""
apply_history_includes_current_poule_fix.py - laat "Matchen historiek" ook
matchen uit de HUIDIGE poule meetellen, niet enkel andere poules.

Locatie: PadelAnalysis/apply_history_includes_current_poule_fix.py
(eenmalig te draaien)

PADEL_ANALYSIS_HISTORY_INCLUDES_CURRENT_POULE_2026-09-26 (op verzoek van
Kim: "toch nog altijd vreemd dat die ene man 3 matchen heeft maar
matchhistoriek nul. zou dan toch minimum 3 moeten zijn. huidige interclub
mag meetellen bij het verleden")
--------------------------------------------------------------------------
ROOT CAUSE (geen bug, wel een verwarrend ontwerp - bevestigd in de code):
split_matches() verdeelt interclubmatchen in TWEE STRIKT GESCHEIDEN lagen:
  Laag 1 "Deze poule"  : matchen met dezelfde spelgroep_id als NU.
  Laag 2 "Historiek"   : EXPLICIET enkel "alle OVERIGE interclubmatches"
                         (letterlijk uit de docstring van split_matches()).

Speelde een speler al zijn/haar matchen in de HUIDIGE poule, dan gaan die
allemaal naar Laag 1 - en Laag 2 ("Matchen historiek") blijft dan op 0
staan. Dat is geen bug in de zin van "verkeerd geteld", maar wel een
mismatch met wat een gebruiker verwacht van het woord "historiek": matchen
die AL GESPEELD zijn, horen daar intuitief bij, ongeacht welke poule.

FIX: build_player_summary() berekent de "historiek"-velden (matches_
history, wins_history, losses_history, winrate_history, partners_history,
history_results, history_periods, form_history) voortaan over ALLE
interclubmatchen (current_matches + history_matches samen), niet enkel
over history_matches. De "Deze poule"-velden (matches_relevant,
wins_relevant, ...) blijven ONGEWIJZIGD strikt tot de huidige poule beperkt
- die sectie blijft dus exact tonen wat ze al toonde.

Gevolg: "Matchen historiek" toont voortaan minstens evenveel matchen als
"Matchen deze poule" (in de praktijk vaak meer, want Laag 2 bevat dan ook
matchen uit vorige periodes/poules) - nooit meer minder dan wat een
speler in totaal al speelde.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_history_includes_current_poule_fix.py           # dry-run
    python apply_history_includes_current_poule_fix.py --apply   # uitvoeren

Idempotent. Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_HISTORY_INCLUDES_CURRENT_POULE_2026-09-26"

OLD_BLOCK = '''    wins_cur = sum(1 for m in current_matches if m.get("won") is True)
    losses_cur = sum(1 for m in current_matches if m.get("won") is False)
    wins_hist = sum(1 for m in history_matches if m.get("won") is True)
    losses_hist = sum(1 for m in history_matches if m.get("won") is False)'''

NEW_BLOCK = '''    wins_cur = sum(1 for m in current_matches if m.get("won") is True)
    losses_cur = sum(1 for m in current_matches if m.get("won") is False)
    # PADEL_ANALYSIS_HISTORY_INCLUDES_CURRENT_POULE_2026-09-26 (op verzoek
    # van Kim: "toch nog altijd vreemd dat die ene man 3 matchen heeft maar
    # matchhistoriek nul [...] huidige interclub mag meetellen bij het
    # verleden"):
    # ROOT CAUSE: split_matches() scheidt STRIKT "deze poule" (Laag 1) van
    # "alle OVERIGE interclubmatches" (Laag 2) - een speler die AL zijn
    # matchen in de huidige poule speelde, kreeg dus 0 in "Matchen
    # historiek", ook al had die speler wel degelijk al matchen gespeeld.
    # FIX: de historiek-cijfers hieronder gaan voortaan over ALLE
    # interclubmatchen (huidige poule + historiek samen), niet enkel de
    # matchen uit ANDERE poules. "Deze poule" hierboven (wins_cur/
    # losses_cur, matches_relevant, ...) blijft ONGEWIJZIGD strikt beperkt
    # tot de huidige poule.
    all_interclub_matches = current_matches + history_matches
    wins_hist = sum(1 for m in all_interclub_matches if m.get("won") is True)
    losses_hist = sum(1 for m in all_interclub_matches if m.get("won") is False)'''

OLD_RETURN = '''        # Laag 2: historiek uit vorige periodes
        "matches_history": len(history_matches),
        "wins_history": wins_hist,
        "losses_history": losses_hist,
        "winrate_history": _winrate_display(wins_hist, losses_hist),
        "partners_history": _partner_rows(history_matches),
        "history_results": _result_rows(history_matches, limit=15),
        "history_periods": _period_breakdown(history_matches),
        "form_history": _form_string(history_matches),'''

NEW_RETURN = '''        # Laag 2: historiek - ALLE interclubmatchen (huidige poule +
        # vorige periodes samen), zie PADEL_ANALYSIS_HISTORY_INCLUDES_
        # CURRENT_POULE_2026-09-26 hierboven.
        "matches_history": len(all_interclub_matches),
        "wins_history": wins_hist,
        "losses_history": losses_hist,
        "winrate_history": _winrate_display(wins_hist, losses_hist),
        "partners_history": _partner_rows(all_interclub_matches),
        "history_results": _result_rows(all_interclub_matches, limit=15),
        "history_periods": _period_breakdown(all_interclub_matches),
        "form_history": _form_string(all_interclub_matches),'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if OLD_BLOCK not in tekst:
        print("  KON HET wins_hist/losses_hist-BLOK NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        return False
    if OLD_RETURN not in tekst:
        print("  KON DE RETURN-DICT (Laag 2) NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        return False

    nieuw = tekst.replace(OLD_BLOCK, NEW_BLOCK, 1)
    nieuw = nieuw.replace(OLD_RETURN, NEW_RETURN, 1)
    print("  build_player_summary(): 'Matchen historiek' klaar om ALLE interclubmatchen mee te tellen.")

    if not apply:
        print(f"\n  {pad.name}: DRY-RUN, klaar om te patchen ({len(tekst)} -> {len(nieuw)} tekens).")
        return True

    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pad.with_suffix(f".py.bak_{stempel}")
    shutil.copy2(pad, backup)
    pad.write_text(nieuw, encoding="utf-8")
    print(f"\n  {pad.name}: GEPATCHT. Back-up: {backup.name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Laat 'Matchen historiek' ook huidige-poule-matchen meetellen."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Voer de wijziging effectief uit (anders enkel tonen).")
    parser.add_argument("--file", default="opponent_dossier.py",
                        help="Pad naar opponent_dossier.py (standaard: huidige map).")
    args = parser.parse_args()

    pad = Path(args.file).resolve()
    print(f"Bestand: {pad}")
    print(f"Modus: {'TOEPASSEN' if args.apply else 'DRY-RUN (er wordt niets gewijzigd)'}\n")

    gelukt = _patch(pad, args.apply)

    print()
    if not gelukt:
        print("Er is niets gewijzigd.")
        return
    if args.apply:
        check_cmd = (
            "python -c \"import ast; ast.parse(open(r'"
            + pad.name
            + "', encoding='utf-8').read()); print('OK')\""
        )
        print("Klaar. Controleer met:")
        print(f"  {check_cmd}")
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
