"""
apply_theoretical_boards_cache_fix.py - repareert een cache in
page_lineup_lab.py die de STORAGE cachete maar niet de COMPUTATIE.

Locatie: PadelAnalysis/apply_theoretical_boards_cache_fix.py
(eenmalig te draaien)

PADEL_ANALYSIS_THEORETICAL_BOARDS_ACTUAL_CACHE_2026-09-26 (op verzoek van
Kim: "toch nog veel trage reacties [...] sommige zaken wil je enkel doen
wanneer je analyse effectief start en niet ervoor (bvb bij wegklikken
speler, bij kiezen rotatie). kiezen andere vorige opstelling duurt ook nog
lang enz...")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door het bestand rechtstreeks te lezen, geen
vermoeden): in _render_all_valid_matchups(), sectie "Tegenstander-roster
voor theoretische scenario's", stond dit patroon:

    lineups, meta = _generate_theoretical_opponent_boards_with_repeats(...)
    ...
    if st.session_state.get(sig_key) != signature:
        st.session_state[compute_key] = lineups
        st.session_state[sig_key] = signature
    theoretical_boards = st.session_state.get(compute_key) or []

De DURE FUNCTIE ZELF (_generate_theoretical_opponent_boards_with_repeats,
die intern _enumerate_rotation_aware_pairings() aanroept - een backtracking-
enumeratie met een call_budget van 300.000) werd ALTIJD aangeroepen. De
signature-check bepaalde enkel of het resultaat WEGGESCHREVEN werd naar
session_state - niet of het BEREKEND werd. Dat is het omgekeerde van wat
een cache hoort te doen: de opslag was gecacht, de computatie niet.

Omdat deze sectie zich bevindt in page_lineup_lab(), VOOR de st.tabs()-
aanroep, wordt dit bij ELKE Streamlit-rerun uitgevoerd - dus bij ELKE
widget-interactie waar dan ook op de pagina (een andere eerdere ontmoeting
kiezen, een rotatie bevestigen, een koppel selecteren, een checkbox
aanvinken in een compleet ander deel van de pagina). Dit is exact het
patroon dat Kim beschreef: "sommige zaken wil je enkel doen wanneer je
analyse effectief start en niet ervoor."

Ter vergelijking: ALLE ANDERE signature-caches in ditzelfde bestand
(_render_rotation_planner's rot_cache_key, _render_all_valid_matchups'
eigen scenario_result_key achteraf, de sandbox's sandbox_result_key) doen
dit WEL correct - de dure aanroep staat daar netjes BINNEN de
if-signature-gewijzigd-check. Deze ene plek was de uitzondering.

FIX: de aanroep van _generate_theoretical_opponent_boards_with_repeats()
verhuist naar BINNEN de if-check. Bij een ongewijzigde signature (het
gebruikelijke geval bij een willekeurige klik elders op de pagina) wordt nu
NIETS meer herberekend - theoretical_boards en meta komen dan rechtstreeks
uit session_state.

--------------------------------------------------------------------------
GECORRIGEERDE EERDERE THEORIE (transparantie)
--------------------------------------------------------------------------
Een eerdere analyse veronderstelde dat de "Welke ontmoeting wil je
bekijken?"-dropdown (key=f"prev_fixture_pick_{id(source)}") een instabiele
widget-key had omdat st.cache_data doorgaans een kopie teruggeeft. Bij
rechtstreekse lezing van het bestand bleek dat ONJUIST: `full_bundle` komt
uit _scout_team_all_fixtures(), dat het resultaat in st.session_state
bewaart (niet st.cache_data) - bij een cache-hit wordt hetzelfde Python-
object teruggegeven, dus id() blijft stabiel binnen een sessie. Die
dropdown was dus GEEN probleem; deze fix betreft uitsluitend de
hierboven beschreven, wel degelijk bevestigde bug.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_theoretical_boards_cache_fix.py           # dry-run
    python apply_theoretical_boards_cache_fix.py --apply   # uitvoeren

Idempotent. Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_THEORETICAL_BOARDS_ACTUAL_CACHE_2026-09-26"

OLD_BLOCK = '''                lineups, meta = _generate_theoretical_opponent_boards_with_repeats(
                    chosen_opp_players, opponent_max_per_player, opponent_official_ranks,
                    opponent_padelstat_ratings, _THEORETICAL_MAX_VARIANTS,
                )
                st.caption(f"🔢 **{meta['total_theoretical']}** theoretische tegenstander-opstellingen mogelijk met deze verdeling.")
                if meta["truncated"]:
                    st.warning(f"⚠️ Enkel de eerste {_THEORETICAL_MAX_VARIANTS} van {meta['total_theoretical']} worden berekend.")
                compute_key = f"theoretical_boards_{opp['ploeg_id']}"
                sig_key = f"theoretical_boards_sig_{opp['ploeg_id']}"
                signature = (tuple(sorted(chosen_opp_ids)), tuple(sorted(opponent_max_per_player.items())), int(total_boards))
                if st.session_state.get(sig_key) != signature:
                    st.session_state[compute_key] = lineups
                    st.session_state[sig_key] = signature
                theoretical_boards = st.session_state.get(compute_key) or []'''

NEW_BLOCK = '''                # PADEL_ANALYSIS_THEORETICAL_BOARDS_ACTUAL_CACHE_2026-09-26 (op
                # verzoek van Kim: "toch nog veel trage reacties [...] sommige
                # zaken wil je enkel doen wanneer je analyse effectief start en
                # niet ervoor"):
                # ROOT CAUSE: _generate_theoretical_opponent_boards_with_repeats()
                # (een backtracking-enumeratie met call_budget=300.000) werd
                # voorheen ALTIJD aangeroepen, ongeacht of de signature
                # gewijzigd was - de if-check hieronder bepaalde enkel of het
                # resultaat WEGGESCHREVEN werd, niet of het BEREKEND werd. Bij
                # elke klik waar dan ook op de pagina (deze sectie staat vóór
                # de tabs) liep deze dure enumeratie dus onnodig opnieuw.
                # FIX: de aanroep zelf staat nu BINNEN de if-check, net als bij
                # alle andere signature-caches in dit bestand.
                compute_key = f"theoretical_boards_{opp['ploeg_id']}"
                meta_key = f"theoretical_boards_meta_{opp['ploeg_id']}"
                sig_key = f"theoretical_boards_sig_{opp['ploeg_id']}"
                signature = (tuple(sorted(chosen_opp_ids)), tuple(sorted(opponent_max_per_player.items())), int(total_boards))
                if st.session_state.get(sig_key) != signature:
                    lineups, meta = _generate_theoretical_opponent_boards_with_repeats(
                        chosen_opp_players, opponent_max_per_player, opponent_official_ranks,
                        opponent_padelstat_ratings, _THEORETICAL_MAX_VARIANTS,
                    )
                    st.session_state[compute_key] = lineups
                    st.session_state[meta_key] = meta
                    st.session_state[sig_key] = signature
                theoretical_boards = st.session_state.get(compute_key) or []
                meta = st.session_state.get(meta_key) or {"total_theoretical": 0, "truncated": False}
                st.caption(f"🔢 **{meta['total_theoretical']}** theoretische tegenstander-opstellingen mogelijk met deze verdeling.")
                if meta["truncated"]:
                    st.warning(f"⚠️ Enkel de eerste {_THEORETICAL_MAX_VARIANTS} van {meta['total_theoretical']} worden berekend.")'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if OLD_BLOCK not in tekst:
        print("  KON HET TE VERVANGEN BLOK NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        print("  (het bestand wijkt af van wat verwacht werd; stuur het opnieuw voor controle)")
        return False

    nieuw = tekst.replace(OLD_BLOCK, NEW_BLOCK, 1)
    print("  theoretische-opstellingen-berekening: klaar om ECHT te cachen "
          "(niet enkel de opslag).")

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
        description="Repareert een cache die de opslag cachete maar niet de berekening."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Voer de wijziging effectief uit (anders enkel tonen).")
    parser.add_argument("--file", default="page_lineup_lab.py",
                        help="Pad naar page_lineup_lab.py (standaard: huidige map).")
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
