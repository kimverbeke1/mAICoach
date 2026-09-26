"""
apply_data_completeness_cache_fix.py - cachet _data_completeness() in
opponent_scout_ui.py.

Locatie: PadelAnalysis/apply_data_completeness_cache_fix.py
(eenmalig te draaien)

PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26 (op verzoek van Kim: "bij
eerdere ontmoetingen een andere ontmoeting duren duurt toch wel lang vind
ik. eerste analyse is ook wel even wachten net als bevestig rotatie 1 of
een koppel kiezen enz")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd, geen vermoeden - rechtstreeks nagelezen in
opponent_scout_ui.py): _render_unified_team_sync_trigger() doet dit
ONVOORWAARDELIJK, ZONDER cache:

    completeness = {pid: _data_completeness(pid) for pid in all_ids}

En _data_completeness() doet PER SPELER drie aparte Firestore-reads:

    doc = fb.get_player(player_id)
    profile = fb.get_player_profile(player_id)
    cached = fb.get_padelstat_rating(player_id)

_render_unified_team_sync_trigger() wordt aangeroepen vanuit
render_scout_header(), en dat gebeurt ENKEL wanneer "not can_scrape" -
d.w.z. op Streamlit Community Cloud, Kim's gebruikelijke omgeving (zie de
docstrings elders in dit bestand: "op Streamlit Cloud (waar Kim uitsluitend
test)"). Zodra een tegenstander eenmaal geanalyseerd is, blijft de bundle in
st.session_state staan - en render_scout_header() draait dan bij ELKE
volgende Streamlit-rerun opnieuw mee, ongeacht WELKE widget je aanklikte.

Dat verklaart precies het gemelde patroon: een andere eerdere ontmoeting
kiezen, een rotatie bevestigen, een koppel selecteren - stuk voor stuk
gewone reruns die stuk voor stuk deze 3-reads-per-speler-check opnieuw
uitvoeren, voor de VOLLEDIGE tegenstander-roster, ongeacht of er ook maar
iets aan hun data veranderd is. Bij 6-8 spelers is dat 18-24 Firestore-reads
op ELKE klik, los van wat je eigenlijk aan het doen was.

FIX: _data_completeness() krijgt een st.cache_data(ttl=300)-laag, dezelfde
5-minuten-conventie als de overige caches in dit project
(_cached_own_player_rating, _get_all_profiles, freshness_cache.py). Binnen
die TTL wordt een speler dus hoogstens 1x per 5 minuten echt bevraagd,
ongeacht hoeveel reruns er binnen die tijd gebeuren.

Bijkomend: de "Ontbrekende gegevens ophalen"-knop in
_render_unified_team_sync_trigger() zelf leegt deze nieuwe cache na een
geslaagde sync (naast de reeds bestaande _load_all_player_docs.clear() en
fcache.invalidate_all()), zodat de eerstvolgende render na een expliciete
ververs-actie meteen de nieuwe status ziet in plaats van tot 5 minuten te
wachten.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_data_completeness_cache_fix.py           # dry-run
    python apply_data_completeness_cache_fix.py --apply   # uitvoeren

Idempotent. Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26"

# _data_completeness(): functiegrens-gebaseerd, tot aan de volgende functie.
DATA_COMPLETENESS_PATTERN = re.compile(
    r"^def _data_completeness\(.*?(?=^def _has_incomplete_data\()",
    re.S | re.M,
)


def _build_replacement(original_block: str) -> str:
    """Voegt de cache-decorator toe VOOR de functiedefinitie, zonder de
    uitgebreide, reeds bestaande docstring/logica van de functie zelf aan
    te raken - enkel de decorator-regel en een korte toelichting worden
    toegevoegd."""
    anchor = "def _data_completeness(player_id: str) -> dict:"
    if anchor not in original_block:
        return None
    prefix = (
        "# PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26 (op verzoek van\n"
        "# Kim: \"bij eerdere ontmoetingen een andere ontmoeting duren duurt\n"
        "# toch wel lang [...] bevestig rotatie 1 of een koppel kiezen enz\"):\n"
        "# deze functie deed 3 Firestore-reads PER SPELER, ONVOORWAARDELIJK bij\n"
        "# ELKE rerun van de pagina (elke widget-klik, niet enkel een expliciete\n"
        "# ververs-actie) - zie de uitgebreide toelichting in\n"
        "# apply_data_completeness_cache_fix.py. Nu gecacht met dezelfde\n"
        "# 5-minuten-TTL-conventie als de overige caches in dit project.\n"
        "@st.cache_data(ttl=300, show_spinner=False)\n"
    )
    return original_block.replace(anchor, prefix + anchor, 1)


# Voegt een cache-clear toe in de bestaande "na succesvolle sync"-sectie,
# naast de reeds bestaande _load_all_player_docs.clear() en
# fcache.invalidate_all().
CLEAR_OLD = '''        _load_all_player_docs.clear()
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
        st.rerun()'''

CLEAR_NEW = '''        _load_all_player_docs.clear()
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


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    m = DATA_COMPLETENESS_PATTERN.search(tekst)
    if not m:
        print("  KON _data_completeness() NIET AFBAKENEN - niets gewijzigd.")
        print("  (verwacht dat _has_incomplete_data() direct erna volgt)")
        return False

    original_block = m.group(0)
    new_block = _build_replacement(original_block)
    if new_block is None:
        print("  KON DE FUNCTIEDEFINITIE-REGEL NIET VINDEN IN HET AFGEBAKENDE BLOK - niets gewijzigd.")
        return False

    if CLEAR_OLD not in tekst:
        print("  KON DE 'na succesvolle sync'-SECTIE NIET VINDEN - niets gewijzigd.")
        print("  (decorator wordt NIET toegepast zonder de cache-clear erbij - anders")
        print("   blijft de UI tot 5 minuten een verouderde status tonen na een ververs-klik)")
        return False

    nieuw = tekst[:m.start()] + new_block + tekst[m.end():]
    nieuw = nieuw.replace(CLEAR_OLD, CLEAR_NEW, 1)
    print("  _data_completeness(): klaar om te cachen.")
    print("  sync-knop: klaar om de nieuwe cache mee te legen na een sync.")

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
        description="Cachet _data_completeness() zodat het niet bij elke klik herhaald wordt."
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
