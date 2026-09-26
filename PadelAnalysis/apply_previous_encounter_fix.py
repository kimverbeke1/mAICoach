"""
apply_previous_encounter_fix.py - repareert de datumgrens voor de
tegenstander-historiek, en isoleert het wisselen van eerdere ontmoeting
achter @st.fragment.

Locatie: PadelAnalysis/apply_previous_encounter_fix.py  (eenmalig te draaien)

PADEL_ANALYSIS_OPPONENT_HISTORY_DATE_FIX_2026-09-26 (op verzoek van Kim: "ik
heb net een match achter de rug en iedereen heeft nu 3 matchen gespeeld. bij
de nieuwe tegenstander zie ik echter maar 2 ontmoetingen waarbij de laatste
nu op een verkeerde datum getoond wordt")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd, rechtstreeks in de code gelezen): _render_opstelling_
scenario() gebruikt `own_ploeg_id` (ONZE eigen ploeg) om de datumgrens te
bepalen waarmee de tegenstander-historiek gefilterd wordt:

    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    opp_team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id) if fixtures else []
    next_match = ss.get_next_match(opp_team_fixtures) if opp_team_fixtures else None
    before_date = (next_match or {}).get("date_text") or ""

Dat geeft ONZE eerstvolgende speeldatum terug, niet die van de tegenstander.
get_opponent_previous_fixtures() (opponent_scout.py) gebruikt deze datum
vervolgens als STRIKTE bovengrens (`<`, niet `<=`) om te bepalen welke
tegenstander-ontmoetingen als "al gespeeld, dus tonen" gelden. Twee
concrete gevolgen:
  1. Verschilt onze eerstvolgende speeldatum van die van de tegenstander,
     dan filtert de historiek op de verkeerde grens.
  2. Speelde de tegenstander toevallig op DEZELFDE datum als onze
     eerstvolgende wedstrijd, dan sluit de STRIKTE `<` hun recentste,
     al gespeelde ontmoeting net uit - exact "de laatste wordt op een
     verkeerde datum getoond" / "maar 2 i.p.v. 3 ontmoetingen".

FIX: `opp.get("ploeg_id")` i.p.v. `own_ploeg_id` - de eerstvolgende
wedstrijd van de TEGENSTANDER is de juiste grens voor "toon alle
ontmoetingen die zij al gespeeld hebben vóór hun volgende wedstrijd".

--------------------------------------------------------------------------
PADEL_ANALYSIS_FRAGMENT_ISOLATION_PREV_ENCOUNTER_2026-09-26 (op verzoek van
Kim: "wel nog eens kijken bij wisselen eerder match [...] ik wil dat
instant")
--------------------------------------------------------------------------
@st.fragment staat al op _render_rotation_planner() en _render_lineup_
sandbox() (zie PADEL_ANALYSIS_FRAGMENT_ISOLATION_2026-09-26), maar
_render_previous_opponent_lineup() - de functie met de "welke ontmoeting
wil je bekijken?"-dropdown - kreeg die isolatie nooit. Elke wissel van
ontmoeting bleef daardoor de VOLLEDIGE pagina opnieuw opbouwen (team-
rapport, overzichtstabel, match1/match2-frequentietabel, de volledige
matchup-tabel eronder), ook al raakte je enkel deze ene dropdown aan.

FIX: @st.fragment op _render_previous_opponent_lineup(). Deze functie roept
zelf nergens st.rerun() aan, dus geen scope="fragment" nodig zoals bij de
rotatieplanner/sandbox - de isolatie werkt hier via de dropdown-widget zelf.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_previous_encounter_fix.py           # dry-run
    python apply_previous_encounter_fix.py --apply   # uitvoeren

Idempotent. Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_OPPONENT_HISTORY_DATE_FIX_2026-09-26"

# ── 1. Datumgrens: own_ploeg_id -> opp.get("ploeg_id") ──
DATE_OLD = '''    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    # Aparte bundle over ALLE gespeelde ontmoetingen van de tegenploeg, enkel
    # voor de match1/match2-statistiek (de gewone bundle bevat er maar 1).
    try:
        opp_team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id) if fixtures else []
        next_match = ss.get_next_match(opp_team_fixtures) if opp_team_fixtures else None
        before_date = (next_match or {}).get("date_text") or ""
    except Exception:
        before_date = ""'''

DATE_NEW = '''    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    # PADEL_ANALYSIS_OPPONENT_HISTORY_DATE_FIX_2026-09-26 (op verzoek van
    # Kim: "ik heb net een match achter de rug en iedereen heeft nu 3
    # matchen gespeeld. bij de nieuwe tegenstander zie ik echter maar 2
    # ontmoetingen waarbij de laatste nu op een verkeerde datum getoond
    # wordt"):
    # ROOT CAUSE: hier stond `own_ploeg_id` (ONZE eigen ploeg) - dat gaf ONZE
    # eerstvolgende speeldatum terug i.p.v. die van de TEGENSTANDER, en
    # get_opponent_previous_fixtures() gebruikt die datum als STRIKTE
    # bovengrens (`<`). Speelde de tegenstander toevallig op dezelfde datum
    # als onze eigen volgende wedstrijd, dan sloot die strikte grens hun
    # recentste, al gespeelde ontmoeting net uit.
    # FIX: opp.get("ploeg_id") - de eerstvolgende wedstrijd van de
    # TEGENSTANDER is de juiste grens voor "toon alle ontmoetingen die zij
    # al speelden vóór hun volgende wedstrijd".
    # Aparte bundle over ALLE gespeelde ontmoetingen van de tegenploeg, enkel
    # voor de match1/match2-statistiek (de gewone bundle bevat er maar 1).
    try:
        opp_team_fixtures = ss.get_team_fixtures(fixtures, opp.get("ploeg_id")) if fixtures else []
        next_match = ss.get_next_match(opp_team_fixtures) if opp_team_fixtures else None
        before_date = (next_match or {}).get("date_text") or ""
    except Exception:
        before_date = ""'''

# ── 2. @st.fragment op _render_previous_opponent_lineup() ──
FRAGMENT_OLD = '''def _render_previous_opponent_lineup(bundle: dict, opp: dict = None, full_bundle: dict = None) -> None:
    """Eerdere ontmoetingen van de tegenstander, kiesbaar via dropdown.'''

FRAGMENT_NEW = '''# PADEL_ANALYSIS_FRAGMENT_ISOLATION_PREV_ENCOUNTER_2026-09-26 (op verzoek
# van Kim: "wel nog eens kijken bij wisselen eerder match [...] ik wil dat
# instant"): @st.fragment stond al op _render_rotation_planner() en
# _render_lineup_sandbox() (zie PADEL_ANALYSIS_FRAGMENT_ISOLATION_2026-09-26),
# maar deze functie - met de "welke ontmoeting wil je bekijken?"-dropdown -
# kreeg die isolatie nooit. Elke wissel bleef daardoor de VOLLEDIGE pagina
# opnieuw opbouwen. Deze functie roept zelf geen st.rerun() aan, dus GEEN
# scope="fragment" nodig zoals bij de rotatieplanner/sandbox.
@st.fragment
def _render_previous_opponent_lineup(bundle: dict, opp: dict = None, full_bundle: dict = None) -> None:
    """Eerdere ontmoetingen van de tegenstander, kiesbaar via dropdown.'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if DATE_OLD not in tekst:
        print("  KON DE DATUMGRENS-BLOK NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        print("  (het bestand wijkt af van wat verwacht werd; stuur het opnieuw voor controle)")
        return False

    if FRAGMENT_OLD not in tekst:
        print("  KON _render_previous_opponent_lineup() NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        return False

    nieuw = tekst.replace(DATE_OLD, DATE_NEW, 1)
    print("  Datumgrens (own_ploeg_id -> opp['ploeg_id']): klaar om te repareren.")

    nieuw = nieuw.replace(FRAGMENT_OLD, FRAGMENT_NEW, 1)
    print("  @st.fragment op _render_previous_opponent_lineup(): klaar om toe te voegen.")

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
        description="Fixt de datumgrens voor tegenstander-historiek en isoleert het wisselen ervan."
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
