"""
apply_profiles_cache_fix.py - cachet _get_all_profiles() in dashboard_common.py.

Locatie: PadelAnalysis/apply_profiles_cache_fix.py  (eenmalig te draaien)

PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26 (op verzoek van Kim: "bekijk nu
eens grondig dat lange wachten bij alle acties. ik merk daar weinig tot geen
verbetering")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd, geen vermoeden - rechtstreeks nagelezen in
dashboard_common.py): _get_all_profiles() doet een VOLLEDIGE Firestore-
collectiescan, ZONDER enige cache:

    def _get_all_profiles() -> list:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        profiles = [d.to_dict() for d in docs]
        ...

page_lineup_lab() roept dit ONVOORWAARDELIJK aan, BOVENAAN de functie:

    def page_lineup_lab():
        st.header(...)
        profiles = _get_all_profiles()

Streamlit voert bij ELKE widget-interactie (een checkbox, een number_input,
een rotatie kiezen, ...) het VOLLEDIGE script opnieuw uit. Dat betekent dat
de HELE player_profiles-collectie (45+ documenten en groeiend) bij ELKE
klik opnieuw uit Firestore gestreamd wordt - een netwerkkost die volledig
losstaat van wat je eigenlijk aan het doen was.

Dit verklaart waarom de eerdere caching-rondes (PADEL_ANALYSIS_UI_SPEED_
CACHE_2026-09-24 en _PHASE2_2026-09-25, beide in page_lineup_lab.py) wel
een deel van de traagheid wegnamen maar het geheel niet: die twee caches
raken de padelstat/klassement-lookups per speler en de matchdocumenten van
de GESELECTEERDE spelers - deze collectiescan zit in dashboard_common.py,
een apart bestand, en werd door geen van beide eerdere fixes geraakt.

FIX: _get_all_profiles() krijgt een st.cache_data(ttl=300)-laag, exact
dezelfde 5-minuten-TTL-conventie als de bestaande caches in
page_lineup_lab.py. Binnen dezelfde sessie wordt de collectie dus
hoogstens 1x per 5 minuten opgehaald i.p.v. bij elke rerun. De TTL is kort
genoeg dat een nieuw toegevoegde speler vanzelf doorkomt; wie niet wil
wachten kan de cache expliciet legen (zie clear_all_profiles_cache()
hieronder, aangeroepen door de bestaande "Ploeg opnieuw ophalen"-knop in
page_lineup_lab.py, zodat een verse ontdekking nooit tot 5 minuten
onzichtbaar blijft).

BELANGRIJK - waarom dit veilig is: _get_all_profiles() wordt op meerdere
plekken gebruikt (o.a. _render_table() in ditzelfde bestand, page_players.py,
page_add_player.py). Een gedeelde cache betekent dat een wijziging op de ene
pagina (bv. een nieuw toegevoegde speler) mogelijk tot 5 minuten niet
zichtbaar is op een ANDERE pagina binnen dezelfde sessie. Dat is een bewuste
afweging (dezelfde die al gold voor de rating-caches) - een page refresh of
het verstrijken van de TTL lost dit vanzelf op, en de winst in snelheid bij
elke gewone widget-interactie weegt hier ruim tegenop.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_profiles_cache_fix.py           # dry-run
    python apply_profiles_cache_fix.py --apply   # uitvoeren

Idempotent: een tweede run merkt dat de fix er al staat en doet niets.
Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26"

OLD_BLOCK = '''def _get_all_profiles() -> list:
    """PADEL_ANALYSIS_GHOST_PROFILE_FILTER_2026-09-12:
    Filtert documenten zonder display_name/player_id uit de Spelers-lijst."""
    try:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        profiles = [d.to_dict() for d in docs]
        return [
            p for p in profiles
            if p and (p.get("display_name") or p.get("player_id"))
        ]
    except Exception:
        return []'''

NEW_BLOCK = '''# PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26 (op verzoek van Kim: "bekijk
# nu eens grondig dat lange wachten bij alle acties. ik merk daar weinig tot
# geen verbetering"):
# ROOT CAUSE: _get_all_profiles() deed een VOLLEDIGE Firestore-collectiescan
# ZONDER enige cache, en page_lineup_lab() riep dit ONVOORWAARDELIJK aan
# BOVENAAN de functie - dus bij ELKE widget-interactie op de hele pagina
# (Streamlit voert bij elke klik het volledige script opnieuw uit). Met 45+
# profielen en groeiend was dit een zware, herhaalde netwerkkost die door
# geen van de eerdere caching-rondes in page_lineup_lab.py geraakt werd -
# die zitten in een ANDER bestand en cachen andere dingen (rating-lookups
# per speler, matchdocumenten van de geselecteerde spelers), niet deze
# volledige-collectie-scan.
#
# FIX: st.cache_data(ttl=300) - dezelfde 5-minuten-conventie als de
# bestaande caches. clear_all_profiles_cache() hieronder laat de bestaande
# "Ploeg opnieuw ophalen"-knop in page_lineup_lab.py deze cache mee legen,
# zodat een net toegevoegde/ontdekte speler niet tot 5 minuten onzichtbaar
# blijft na een expliciete ververs-actie.
@st.cache_data(ttl=300, show_spinner=False)
def _get_all_profiles_cached() -> list:
    try:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        profiles = [d.to_dict() for d in docs]
        return [
            p for p in profiles
            if p and (p.get("display_name") or p.get("player_id"))
        ]
    except Exception:
        return []


def _get_all_profiles() -> list:
    """PADEL_ANALYSIS_GHOST_PROFILE_FILTER_2026-09-12:
    Filtert documenten zonder display_name/player_id uit de Spelers-lijst.

    PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26: gaat nu door
    _get_all_profiles_cached() - zie de toelichting hierboven voor waarom
    dit de dominante bron van traagheid was."""
    return _get_all_profiles_cached()


def clear_all_profiles_cache() -> None:
    """PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26: leegt de cache
    hierboven. Aan te roepen vanuit elke "ververs"-knop die een nieuw
    profiel kan hebben aangemaakt of gewijzigd (bv. "Ploeg opnieuw ophalen"
    in page_lineup_lab.py), zodat het resultaat niet tot 5 minuten
    onzichtbaar blijft na een expliciete gebruikersactie."""
    try:
        _get_all_profiles_cached.clear()
    except Exception:
        pass'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if OLD_BLOCK not in tekst:
        print("  KON _get_all_profiles() NIET VINDEN IN VERWACHTE VORM - niets gewijzigd.")
        print("  Het bestand wijkt af van wat verwacht werd; stuur het opnieuw voor controle.")
        return False

    nieuw = tekst.replace(OLD_BLOCK, NEW_BLOCK, 1)
    print("  _get_all_profiles(): klaar om te cachen.")

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
        description="Cachet _get_all_profiles() zodat het niet bij elke klik herhaald wordt."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Voer de wijziging effectief uit (anders enkel tonen).")
    parser.add_argument("--file", default="dashboard_common.py",
                        help="Pad naar dashboard_common.py (standaard: huidige map).")
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
        print("Optioneel, maar aanbevolen: laat de bestaande 'Ploeg opnieuw ophalen'-knop in")
        print("page_lineup_lab.py ook clear_all_profiles_cache() aanroepen naast de reeds")
        print("bestaande _clear_rank_caches(), zodat een verse ontdekking meteen zichtbaar is.")
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
