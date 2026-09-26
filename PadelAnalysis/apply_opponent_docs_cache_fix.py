"""
apply_opponent_docs_cache_fix.py - cachet ll.get_docs_for_players() voor de
TEGENSTANDER-roster in opponent_scout_ui.py.

Locatie: PadelAnalysis/apply_opponent_docs_cache_fix.py
(eenmalig te draaien)

PADEL_ANALYSIS_OPPONENT_DOCS_CACHE_2026-09-26
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd, geen vermoeden - rechtstreeks nagelezen in
opponent_scout_ui.py): prepare_team_docs() doet dit ONVOORWAARDELIJK,
ZONDER cache:

    all_docs = ll.get_docs_for_players([p["user_id"] for p in unique_players])

Dit is EXACT hetzelfde patroon als PADEL_ANALYSIS_UI_SPEED_CACHE_PHASE2_
2026-09-25 al oploste in page_lineup_lab.py (_cached_docs_for_players) -
maar die fix raakte enkel de aanroep voor ONZE EIGEN spelers
(_render_opstelling_scenario). Deze aanroep, voor de TEGENSTANDER-roster,
bleef ongemoeid.

prepare_team_docs() wordt aangeroepen vanuit page_lineup_lab() zodra er een
bundle is:

    if bundle.get("unique_players"):
        all_docs, global_docs = osu.prepare_team_docs(bundle, str(sel_player_id))

Dat gebeurt op ELKE Streamlit-rerun na de eerste "Tegenstander analyseren"-
klik - dus bij elke widget-interactie waar dan ook op de pagina (een andere
ontmoeting kiezen, een rotatie bevestigen, een koppel selecteren, ...).
ll.get_docs_for_players() haalt PER SPELER het volledige matchdocument op
(elk met tot honderden matchrecords) - bij 6-8 tegenstander-spelers is dat
6-8 volledige Firestore-documentreads op ELKE klik, ongeacht wat je
eigenlijk deed.

FIX: prepare_team_docs() gebruikt nu een st.cache_data(ttl=300)-laag,
dezelfde 5-minuten-conventie als alle overige caches in dit project
(_cached_docs_for_players, _cached_own_player_rating, _data_completeness,
_get_all_profiles). De cache-sleutel is de (gesorteerde) tuple van
speler-ID's, zodat een gewijzigde tegenstander-roster wel meteen een verse
ophaling triggert.

Bijkomend: de "🔄 Ontbrekende gegevens ophalen"-knop
(_render_unified_team_sync_trigger, al gepatcht in
apply_data_completeness_cache_fix.py) en de "🔄 Ververs alles voor deze
ploeg"-knop (render_scout_header) legen deze nieuwe cache mee na een
geslaagde sync, zodat verse matchdata niet tot 5 minuten onzichtbaar blijft
na een expliciete ververs-actie.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_opponent_docs_cache_fix.py           # dry-run
    python apply_opponent_docs_cache_fix.py --apply   # uitvoeren

Idempotent. Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_OPPONENT_DOCS_CACHE_2026-09-26"

OLD_PREPARE = '''def prepare_team_docs(
    bundle: dict, sel_player_id: str,
) -> tuple[dict, dict]:
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: toont de 'nog niet
    gekende spelers'-caption/achtergrond-trigger (indien van toepassing) en
    bouwt all_docs (matchdata van de tegenstander-roster) + global_docs
    (brede cache, voor de ranking-fallback in opponent_dossier). Geeft
    (all_docs, global_docs) terug voor gebruik door
    opponent_analysis.get_team_report().
    PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C): de vroegere,
    aparte "🚀 Nieuwe tegenstanders ophalen"-knop is HIER WEGGEHAALD — die
    actie zit nu VOLLEDIG vervat in de gecombineerde knop hoger op de
    pagina (_render_unified_team_sync_trigger(), aangeroepen vanuit
    render_scout_header()), die matchdata + klassement + playing strength
    in 1 klik regelt zodra dat nog nodig is. Deze functie toont hier enkel
    nog een informatieve caption, geen actieknop meer (voorkomt 2 knoppen
    met overlappende functie op dezelfde pagina)."""
    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        return {}, {}
    unknown_ids = {player["user_id"] for player in _unknown_players(bundle)}
    all_docs = ll.get_docs_for_players([p["user_id"] for p in unique_players])
    if unknown_ids:
        st.caption(
            f"⚠️ {len(unknown_ids)} speler(s) nog niet volledig gekend qua matchdata — gebruik de "
            "knop '🔄 Ontbrekende gegevens ophalen' hierboven om dit (samen met klassement en "
            "playing strength) in 1 klik aan te vullen."
        )
    global_docs = _load_all_player_docs()
    return all_docs, global_docs'''

NEW_PREPARE = '''# PADEL_ANALYSIS_OPPONENT_DOCS_CACHE_2026-09-26 (zelfde bottleneck als
# PADEL_ANALYSIS_UI_SPEED_CACHE_PHASE2_2026-09-25 in page_lineup_lab.py,
# maar dan voor de TEGENSTANDER-roster i.p.v. onze eigen spelers - zie de
# uitgebreide toelichting in apply_opponent_docs_cache_fix.py).
@st.cache_data(ttl=300, show_spinner=False)
def _cached_docs_for_players(player_ids: tuple) -> dict:
    """Gecachete variant van ll.get_docs_for_players(). Sleutel is de
    (gesorteerde) tuple van speler-ID's, zodat een gewijzigde tegenstander-
    roster wel meteen een verse ophaling triggert, maar dezelfde roster
    binnen de TTL nooit twee keer wordt opgehaald."""
    try:
        return ll.get_docs_for_players(list(player_ids))
    except Exception:
        return {}


def clear_opponent_docs_cache() -> None:
    """Leegt de cache hierboven. Aan te roepen na elke geslaagde sync-actie
    voor de tegenstander-roster (matchdata/klassement/padelstat), zodat
    verse data niet tot 5 minuten onzichtbaar blijft."""
    try:
        _cached_docs_for_players.clear()
    except Exception:
        pass


def prepare_team_docs(
    bundle: dict, sel_player_id: str,
) -> tuple[dict, dict]:
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: toont de 'nog niet
    gekende spelers'-caption/achtergrond-trigger (indien van toepassing) en
    bouwt all_docs (matchdata van de tegenstander-roster) + global_docs
    (brede cache, voor de ranking-fallback in opponent_dossier). Geeft
    (all_docs, global_docs) terug voor gebruik door
    opponent_analysis.get_team_report().
    PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C): de vroegere,
    aparte "🚀 Nieuwe tegenstanders ophalen"-knop is HIER WEGGEHAALD — die
    actie zit nu VOLLEDIG vervat in de gecombineerde knop hoger op de
    pagina (_render_unified_team_sync_trigger(), aangeroepen vanuit
    render_scout_header()), die matchdata + klassement + playing strength
    in 1 klik regelt zodra dat nog nodig is. Deze functie toont hier enkel
    nog een informatieve caption, geen actieknop meer (voorkomt 2 knoppen
    met overlappende functie op dezelfde pagina).
    PADEL_ANALYSIS_OPPONENT_DOCS_CACHE_2026-09-26: all_docs gaat nu door
    _cached_docs_for_players() i.p.v. rechtstreeks ll.get_docs_for_players()
    - dit werd voorheen op ELKE Streamlit-rerun opnieuw opgehaald voor de
    VOLLEDIGE tegenstander-roster, ongeacht welke widget je aanklikte."""
    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        return {}, {}
    unknown_ids = {player["user_id"] for player in _unknown_players(bundle)}
    all_docs = _cached_docs_for_players(tuple(sorted(str(p["user_id"]) for p in unique_players)))
    if unknown_ids:
        st.caption(
            f"⚠️ {len(unknown_ids)} speler(s) nog niet volledig gekend qua matchdata — gebruik de "
            "knop '🔄 Ontbrekende gegevens ophalen' hierboven om dit (samen met klassement en "
            "playing strength) in 1 klik aan te vullen."
        )
    global_docs = _load_all_player_docs()
    return all_docs, global_docs'''

# Cache-clear toevoegen aan de 2 bestaande "na succesvolle sync"-plekken.
CLEAR_UNIFIED_OLD = '''        _load_all_player_docs.clear()
        # PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_REPORT_REFRESH_2026-09-19 (gevonden
        # bij het naast elkaar leggen van dit bestand en opponent_analysis.py,
        # op verzoek van Kim): opponent_analysis._underlying_data_is_fresher()
        # gebruikt freshness_cache.py — een SESSIE-LOKALE TTL-cache. Zonder
        # deze invalidatie zou het team-rapport hieronder de zonet
        # binnengekomen verse data NIET zien totdat die sessie-cache vanzelf
        # verloopt.
        try:
            import freshness_cache as fcache
            fcache.invalidate_all()
        except Exception:
            pass
        # PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26: idem voor de
        # nieuwe _data_completeness()-cache hierboven - anders blijft de
        # "N van M spelers"-telling tot 5 minuten de OUDE status tonen,
        # ondanks deze expliciete sync-actie.
        try:
            _data_completeness.clear()
        except Exception:
            pass
        st.rerun()'''

CLEAR_UNIFIED_NEW = '''        _load_all_player_docs.clear()
        # PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_REPORT_REFRESH_2026-09-19 (gevonden
        # bij het naast elkaar leggen van dit bestand en opponent_analysis.py,
        # op verzoek van Kim): opponent_analysis._underlying_data_is_fresher()
        # gebruikt freshness_cache.py — een SESSIE-LOKALE TTL-cache. Zonder
        # deze invalidatie zou het team-rapport hieronder de zonet
        # binnengekomen verse data NIET zien totdat die sessie-cache vanzelf
        # verloopt.
        try:
            import freshness_cache as fcache
            fcache.invalidate_all()
        except Exception:
            pass
        # PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26: idem voor de
        # nieuwe _data_completeness()-cache hierboven - anders blijft de
        # "N van M spelers"-telling tot 5 minuten de OUDE status tonen,
        # ondanks deze expliciete sync-actie.
        try:
            _data_completeness.clear()
        except Exception:
            pass
        # PADEL_ANALYSIS_OPPONENT_DOCS_CACHE_2026-09-26: idem voor de
        # matchdocumenten-cache in prepare_team_docs() - anders toont het
        # team-rapport tot 5 minuten nog de OUDE matchdata na deze sync.
        clear_opponent_docs_cache()
        st.rerun()'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if OLD_PREPARE not in tekst:
        print("  KON prepare_team_docs() NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        print("  (mogelijk staat de PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26-fix nog")
        print("   niet in dit bestand - draai eerst apply_data_completeness_cache_fix.py)")
        return False

    nieuw = tekst.replace(OLD_PREPARE, NEW_PREPARE, 1)
    print("  prepare_team_docs(): klaar om all_docs te cachen.")

    if CLEAR_UNIFIED_OLD in nieuw:
        nieuw = nieuw.replace(CLEAR_UNIFIED_OLD, CLEAR_UNIFIED_NEW, 1)
        print("  sync-knop: klaar om de nieuwe cache mee te legen na een sync.")
    else:
        print("  LET OP: kon de 'na succesvolle sync'-sectie niet vinden om de cache-clear toe")
        print("  te voegen - de cache zelf is wel toegevoegd, maar wordt na een expliciete")
        print("  ververs-klik niet automatisch geleegd (verloopt dan gewoon na 5 minuten).")

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
        description="Cachet de tegenstander-matchdocumenten in prepare_team_docs()."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Voer de wijziging effectief uit (anders enkel tonen).")
    parser.add_argument("--file", default="opponent_scout_ui.py",
                        help="Pad naar opponent_scout_ui.py (standaard: huidige map).")
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
