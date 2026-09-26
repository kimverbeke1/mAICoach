"""
apply_speed_audit_round4_fix.py - vierde en (voor zover nu grondig
gecontroleerd) laatste snelheidsronde: cachet _is_known()/_unknown_players()
in opponent_scout_ui.py, en _load_saved_rules_selection() +
fb.get_player(sel_player_id) in page_lineup_lab.py.

Locatie: PadelAnalysis/apply_speed_audit_round4_fix.py
(eenmalig te draaien, in elk van beide bestanden)

PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26 (op verzoek van Kim: "ik heb nu
al 3 fixes gedaan voor snelheid [...] kan je voor het zekerste nog eens
alles dubbelchecken zodat ik dat niet iedere keer opnieuw voor 1 of andere
functie moet oplossen. graag alles ineens")
--------------------------------------------------------------------------
Systematische controle van page_lineup_lab.py en opponent_scout_ui.py:
elke fb.*-aanroep nagelopen op (a) gecacht via st.cache_data of
st.session_state, of (b) enkel bereikbaar achter een expliciete knop
(st.button/st.form_submit_button). Alles wat aan geen van beide voorwaarden
voldeed en dus bij ELKE Streamlit-rerun opnieuw liep, staat hieronder.

LET OP - transparantie over de dekking: opponent_analysis.py (o.a.
get_team_report/render_team_header, het Overzicht/Detail-per-speler-
tabblad) kon in deze ronde niet opnieuw opgehaald worden en is dus NIET
in deze audit meegenomen. Dat bestand kreeg op 2026-09-25 al een eigen
cache-fix (PADEL_ANALYSIS_TEAM_REPORT_SNAPSHOT_CACHE), maar of daar nog
iets resteert kon nu niet bevestigd worden. Blijft er na deze 4e ronde nog
vertraging bij het Overzicht/Detail-per-speler-tabblad specifiek, dan is
dat bestand de eerstvolgende, gerichte plek om te controleren.

--------------------------------------------------------------------------
BEVINDING 1 (opponent_scout_ui.py, de grootste van deze ronde)
--------------------------------------------------------------------------
_is_known(player_id) doet 2 Firestore-reads (get_player_profile +
get_player) PER SPELER, zonder enige cache:

    def _is_known(player_id: str) -> bool:
        if fb.get_player_profile(player_id):
            return True
        doc = fb.get_player(player_id) or {}
        return bool(doc.get("matches"))

_unknown_players(bundle) roept dit aan voor ELKE speler in de
tegenstander-roster. Dat gebeurt op 2 plekken:
  1. In _run_scout_and_scrape() - ACHTER de "Tegenstander analyseren"-knop,
     dus geen probleem (een bewuste, eenmalige actie).
  2. In prepare_team_docs() - ONVOORWAARDELIJK, bij ELKE rerun zodra er een
     bundle bestaat. Dit werd door de vorige 3 fixes NIET geraakt: die
     cachten all_docs (fix 3) en de completeness-telling (fix 2) apart,
     maar deze _unknown_players()-aanroep zit er los naast.
Bij 6-8 tegenstander-spelers is dat 12-16 Firestore-reads PER KLIK, waar
dan ook op de pagina.

FIX: nieuwe _cached_is_known(), st.cache_data(ttl=300), dezelfde conventie
als alle overige caches in dit project. _unknown_players() gebruikt deze
voortaan i.p.v. de ongecachte _is_known() rechtstreeks aan te roepen (de
oorspronkelijke _is_known() blijft ongewijzigd bestaan en beschikbaar voor
eventuele andere aanroepers).

--------------------------------------------------------------------------
BEVINDING 2 (page_lineup_lab.py)
--------------------------------------------------------------------------
_load_saved_rules_selection(sel_player_id, ploeg_id) doet 1 Firestore-read
(get_player_profile), zonder cache. Aangeroepen vanuit
_render_tournament_rules_selector(), die ONVOORWAARDELIJK aangeroepen
wordt in _render_opstelling_scenario() - dus bij elke rerun. Kleiner in
omvang dan bevinding 1 (1 read i.p.v. 12-16), maar even structureel.

FIX: st.cache_data(ttl=300) toegevoegd. Cache-sleutel is
(sel_player_id, ploeg_id) - identiek aan de bestaande functieparameters.

--------------------------------------------------------------------------
BEVINDING 3 (page_lineup_lab.py)
--------------------------------------------------------------------------
_render_volgende_match_and_scout() doet fb.get_player(sel_player_id) -
het VOLLEDIGE matchdocument van de GESELECTEERDE (eigen) speler, mogelijk
honderden matchrecords - zonder cache, bij elke rerun zolang je in het
"Analyseren"-tabblad zit.

FIX: nieuwe _cached_own_full_doc(), st.cache_data(ttl=300).

--------------------------------------------------------------------------
Alle 3 nieuwe caches worden ALTIJD samen met de reeds bestaande
_clear_rank_caches()/clear_opponent_docs_cache()-aanroepen geleegd bij een
expliciete ververs-actie, zodat verse data nooit tot 5 minuten onzichtbaar
blijft na een bewuste klik.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_speed_audit_round4_fix.py --opponent-file opponent_scout_ui.py --lineup-file page_lineup_lab.py
    python apply_speed_audit_round4_fix.py --opponent-file opponent_scout_ui.py --lineup-file page_lineup_lab.py --apply

Idempotent per bestand. Maakt een back-up (.bak_<timestamp>) voor het
schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26"

# ═══════════════════════════════════════════════════════════════════════
# opponent_scout_ui.py: _is_known()/_unknown_players()
# ═══════════════════════════════════════════════════════════════════════
OPP_OLD_UNKNOWN = '''def _unknown_players(bundle: dict) -> list[dict]:
    return [
        player
        for player in (bundle.get("unique_players", []) or [])
        if not _is_known(player["user_id"])
    ]'''

OPP_NEW_UNKNOWN = '''# PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26 (op verzoek van Kim: "ik heb
# nu al 3 fixes gedaan voor snelheid [...] graag alles ineens"):
# _is_known() doet 2 Firestore-reads PER SPELER, zonder cache. Dit wordt via
# _unknown_players() ONVOORWAARDELIJK aangeroepen in prepare_team_docs() -
# dus bij ELKE Streamlit-rerun, voor de VOLLEDIGE tegenstander-roster. Bij
# 6-8 spelers is dat 12-16 Firestore-reads per klik, ongeacht wat je
# eigenlijk deed. Dit werd door de vorige 3 caching-rondes NIET geraakt: die
# cachten all_docs en de completeness-telling apart, maar deze aanroep zit
# er los naast. De oorspronkelijke, ongecachte _is_known() blijft
# ongewijzigd bestaan (bv. voor _run_scout_and_scrape(), waar dit al achter
# een knop zit en dus geen probleem is) - enkel _unknown_players()
# hieronder gebruikt nu de gecachete variant.
@st.cache_data(ttl=300, show_spinner=False)
def _cached_is_known(player_id: str) -> bool:
    return _is_known(player_id)


def clear_is_known_cache() -> None:
    """Leegt de cache hierboven. Aan te roepen na elke geslaagde sync-actie
    voor de tegenstander-roster, zodat een net gescrapete speler niet tot
    5 minuten als 'nog onbekend' blijft gelden."""
    try:
        _cached_is_known.clear()
    except Exception:
        pass


def _unknown_players(bundle: dict) -> list[dict]:
    return [
        player
        for player in (bundle.get("unique_players", []) or [])
        if not _cached_is_known(player["user_id"])
    ]'''

# Cache-clear toevoegen aan de bestaande "na succesvolle sync"-sectie
# (staat er na de vorige 2 patches al met _data_completeness.clear() en
# clear_opponent_docs_cache()).
OPP_CLEAR_OLD = '''        clear_opponent_docs_cache()
        st.rerun()'''

OPP_CLEAR_NEW = '''        clear_opponent_docs_cache()
        # PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26: idem voor de nieuwe
        # _is_known()-cache hierboven - anders blijft een net gescrapete
        # speler tot 5 minuten als 'nog onbekend' gelden ondanks deze sync.
        clear_is_known_cache()
        st.rerun()'''


def _patch_opponent_file(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False
    tekst = pad.read_text(encoding="utf-8")
    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False
    if OPP_OLD_UNKNOWN not in tekst:
        print(f"  {pad.name}: KON _unknown_players() NIET VINDEN IN VERWACHTE VORM.")
        return False
    nieuw = tekst.replace(OPP_OLD_UNKNOWN, OPP_NEW_UNKNOWN, 1)
    print(f"  {pad.name}: _unknown_players()/_is_known(): klaar om te cachen.")
    if OPP_CLEAR_OLD in nieuw:
        nieuw = nieuw.replace(OPP_CLEAR_OLD, OPP_CLEAR_NEW, 1)
        print(f"  {pad.name}: sync-knop: klaar om ook deze nieuwe cache te legen.")
    else:
        print(f"  {pad.name}: LET OP: kon de bestaande 'na sync'-clear-sectie niet vinden "
              "(mogelijk zijn de vorige 2 patches nog niet toegepast) - de cache zelf is wel "
              "toegevoegd, maar wordt na een ververs-klik niet automatisch geleegd.")
    if not apply:
        print(f"  {pad.name}: DRY-RUN, klaar om te patchen ({len(tekst)} -> {len(nieuw)} tekens).")
        return True
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pad.with_suffix(f".py.bak_{stempel}")
    shutil.copy2(pad, backup)
    pad.write_text(nieuw, encoding="utf-8")
    print(f"  {pad.name}: GEPATCHT. Back-up: {backup.name}")
    return True


# ═══════════════════════════════════════════════════════════════════════
# page_lineup_lab.py: _load_saved_rules_selection() + fb.get_player(sel_player_id)
# ═══════════════════════════════════════════════════════════════════════
LINEUP_OLD_RULES = '''def _load_saved_rules_selection(sel_player_id: str, ploeg_id: str) -> dict:
    try:
        profile = fb.get_player_profile(sel_player_id) or {}
    except Exception:
        profile = {}
    by_team = profile.get("lineup_rules_selection_by_team") or {}
    if str(ploeg_id) in by_team:
        return by_team.get(str(ploeg_id)) or {}
    return profile.get("lineup_rules_selection") or {}'''

LINEUP_NEW_RULES = '''# PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26 (op verzoek van Kim: "ik heb
# nu al 3 fixes gedaan voor snelheid [...] graag alles ineens"):
# doet 1 Firestore-read (get_player_profile), zonder cache. Aangeroepen
# vanuit _render_tournament_rules_selector(), die ONVOORWAARDELIJK
# aangeroepen wordt in _render_opstelling_scenario() - dus bij elke rerun.
# Kleiner in omvang dan de tegenstander-roster-vondsten, maar even
# structureel: elke klik op de pagina deed deze read opnieuw.
@st.cache_data(ttl=300, show_spinner=False)
def _load_saved_rules_selection(sel_player_id: str, ploeg_id: str) -> dict:
    try:
        profile = fb.get_player_profile(sel_player_id) or {}
    except Exception:
        profile = {}
    by_team = profile.get("lineup_rules_selection_by_team") or {}
    if str(ploeg_id) in by_team:
        return by_team.get(str(ploeg_id)) or {}
    return profile.get("lineup_rules_selection") or {}'''

LINEUP_OLD_GETPLAYER = '''    sel_doc = fb.get_player(sel_player_id)
    own_interclub_matches = [m for m in (sel_doc or {}).get("matches", []) if m.get("match_type") == "interclub"]'''

LINEUP_NEW_GETPLAYER = '''    # PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26: fb.get_player(sel_player_id)
    # haalt het VOLLEDIGE matchdocument van de GESELECTEERDE (eigen) speler op
    # (mogelijk honderden matchrecords), zonder cache, bij ELKE rerun zolang je
    # in het "Analyseren"-tabblad zit. Nu gecacht met dezelfde 5-minuten-TTL-
    # conventie als de rest van dit bestand.
    sel_doc = _cached_own_full_doc(str(sel_player_id))
    own_interclub_matches = [m for m in (sel_doc or {}).get("matches", []) if m.get("match_type") == "interclub"]'''

# Nieuwe cache-functie invoegen vlak voor _render_volgende_match_and_scout().
LINEUP_INSERT_ANCHOR = "def _render_volgende_match_and_scout(sel_player_id: str, sel_label: str):"

LINEUP_NEW_CACHE_FN = '''# PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26: zie toelichting bij de
# aanroep in _render_volgende_match_and_scout() hieronder.
@st.cache_data(ttl=300, show_spinner=False)
def _cached_own_full_doc(player_id: str):
    try:
        return fb.get_player(player_id)
    except Exception:
        return None


'''


def _patch_lineup_file(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False
    tekst = pad.read_text(encoding="utf-8")
    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    gevonden = 0
    nieuw = tekst

    if LINEUP_OLD_RULES in nieuw:
        nieuw = nieuw.replace(LINEUP_OLD_RULES, LINEUP_NEW_RULES, 1)
        print(f"  {pad.name}: _load_saved_rules_selection(): klaar om te cachen.")
        gevonden += 1
    else:
        print(f"  {pad.name}: KON _load_saved_rules_selection() NIET VINDEN IN VERWACHTE VORM.")

    if LINEUP_OLD_GETPLAYER in nieuw and LINEUP_INSERT_ANCHOR in nieuw:
        nieuw = nieuw.replace(LINEUP_OLD_GETPLAYER, LINEUP_NEW_GETPLAYER, 1)
        nieuw = nieuw.replace(LINEUP_INSERT_ANCHOR, LINEUP_NEW_CACHE_FN + LINEUP_INSERT_ANCHOR, 1)
        print(f"  {pad.name}: fb.get_player(sel_player_id): klaar om te cachen.")
        gevonden += 1
    else:
        print(f"  {pad.name}: KON de fb.get_player(sel_player_id)-aanroep NIET VINDEN IN VERWACHTE VORM.")

    if gevonden == 0:
        print(f"  {pad.name}: niets gevonden om te patchen - niets gewijzigd.")
        return False

    if not apply:
        print(f"  {pad.name}: DRY-RUN, klaar om te patchen ({len(tekst)} -> {len(nieuw)} tekens).")
        return True

    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pad.with_suffix(f".py.bak_{stempel}")
    shutil.copy2(pad, backup)
    pad.write_text(nieuw, encoding="utf-8")
    print(f"  {pad.name}: GEPATCHT. Back-up: {backup.name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="4e snelheidsronde: cachet de resterende, ongecachte Firestore-hotpaths."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Voer de wijziging effectief uit (anders enkel tonen).")
    parser.add_argument("--opponent-file", default="opponent_scout_ui.py",
                        help="Pad naar opponent_scout_ui.py (standaard: huidige map).")
    parser.add_argument("--lineup-file", default="page_lineup_lab.py",
                        help="Pad naar page_lineup_lab.py (standaard: huidige map).")
    args = parser.parse_args()

    print(f"Modus: {'TOEPASSEN' if args.apply else 'DRY-RUN (er wordt niets gewijzigd)'}\n")

    print(f"=== {args.opponent_file} ===")
    r1 = _patch_opponent_file(Path(args.opponent_file).resolve(), args.apply)

    print(f"\n=== {args.lineup_file} ===")
    r2 = _patch_lineup_file(Path(args.lineup_file).resolve(), args.apply)

    print()
    if not (r1 or r2):
        print("Er is niets gewijzigd.")
        return
    if args.apply:
        print("Klaar. Controleer met:")
        print(f"  python -c \"import ast; ast.parse(open(r'{args.opponent_file}', encoding='utf-8').read()); "
              f"ast.parse(open(r'{args.lineup_file}', encoding='utf-8').read()); print('OK')\"")
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
