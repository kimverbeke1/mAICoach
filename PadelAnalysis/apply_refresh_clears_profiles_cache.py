"""
apply_refresh_clears_profiles_cache.py - laat de bestaande "Ploeg opnieuw
ophalen"-knop in page_lineup_lab.py ook de nieuwe profielen-cache legen (zie
apply_profiles_cache_fix.py, dat in dashboard_common.py moet draaien VOOR dit
script).

Locatie: PadelAnalysis/apply_refresh_clears_profiles_cache.py
(eenmalig te draaien, NA apply_profiles_cache_fix.py)

PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26 (vervolg)
--------------------------------------------------------------------------
De "Ploeg opnieuw ophalen"-knop in page_lineup_lab.py riep al
_clear_rank_caches() aan (de padelstat/klassement-lookup-caches). Sinds
_get_all_profiles() in dashboard_common.py nu ook gecacht is
(PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26), moet diezelfde knop OOK
dc.clear_all_profiles_cache() aanroepen - anders blijft een net ontdekt of
gewijzigd profiel tot 5 minuten onzichtbaar, ook al klikte de gebruiker
expliciet op "ververs".

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_refresh_clears_profiles_cache.py           # dry-run
    python apply_refresh_clears_profiles_cache.py --apply   # uitvoeren

Idempotent. Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26"

OLD_BLOCK = '''        if st.button("\U0001F504 Ploeg opnieuw ophalen", key=f"refresh_own_roster_{sel_player_id}"):
            for key in [k for k in list(st.session_state) if str(k).startswith(("own_roster_v2_", "full_scout_v2_"))]:
                st.session_state.pop(key, None)
            _load_encounter_index.clear()
            # PADEL_ANALYSIS_UI_SPEED_CACHE_2026-09-24: ook de rating-caches
            # legen, anders blijft een net ververst klassement tot 5 minuten
            # onzichtbaar terwijl de gebruiker net om een verversing vroeg.
            _clear_rank_caches()
            st.rerun()'''

NEW_BLOCK = '''        if st.button("\U0001F504 Ploeg opnieuw ophalen", key=f"refresh_own_roster_{sel_player_id}"):
            for key in [k for k in list(st.session_state) if str(k).startswith(("own_roster_v2_", "full_scout_v2_"))]:
                st.session_state.pop(key, None)
            _load_encounter_index.clear()
            # PADEL_ANALYSIS_UI_SPEED_CACHE_2026-09-24: ook de rating-caches
            # legen, anders blijft een net ververst klassement tot 5 minuten
            # onzichtbaar terwijl de gebruiker net om een verversing vroeg.
            _clear_rank_caches()
            # PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26: idem voor de
            # nieuwe profielen-cache in dashboard_common.py - anders blijft
            # een net ontdekt/gewijzigd profiel tot 5 minuten onzichtbaar
            # ondanks deze expliciete ververs-klik.
            dc.clear_all_profiles_cache()
            st.rerun()'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst and "clear_all_profiles_cache" in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if OLD_BLOCK not in tekst:
        print("  KON DE 'Ploeg opnieuw ophalen'-KNOP NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        print("  Het bestand wijkt af van wat verwacht werd; stuur het opnieuw voor controle.")
        return False

    nieuw = tekst.replace(OLD_BLOCK, NEW_BLOCK, 1)
    print("  'Ploeg opnieuw ophalen'-knop: klaar om clear_all_profiles_cache() toe te voegen.")

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
        description="Laat de 'Ploeg opnieuw ophalen'-knop ook de profielen-cache legen."
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
        print()
        print("LET OP: dit vereist dat 'import dashboard_common as dc' al bovenaan")
        print("page_lineup_lab.py staat (dat is het geval sinds de bestaande import-regel")
        print("'import dashboard_common as dc' - geen extra import nodig).")
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
