"""
diagnose_padelstat_search.py — toont EXACT waarom
padelstats_scraper.search_and_fetch_padelstat_rating() voor een bepaalde
speler niets teruggeeft.

Locatie: PadelAnalysis/scraper/diagnose_padelstat_search.py

--------------------------------------------------------------------------
WAAROM DIT BESTAAT
--------------------------------------------------------------------------
Vier spelers (De Pourcq Hilde, Breda Hilde, Mondy Severine, Vanlerberghe
Vivianne) krijgen structureel GEEN padelstat-rating, ondanks dat ze wel
matchdata hebben. Uit lezing van padelstats_scraper.py bleek dat
search_and_fetch_padelstat_rating() zonder club NIET faalt op de
club-disambiguatie zelf (het pakt gewoon de eerste kandidaat, met een
waarschuwing) -- dus de kernvraag is: waar in de keten valt het precies
stil?
    1. search_padelstat_player(naam) geeft 0 kandidaten terug
       (de speler staat simpelweg niet op padelstats.be onder die naam), OF
    2. er kandidaten ZIJN, maar _click_and_get_padelstat_id() faalt (bv. de
       klik navigeert niet naar een /speler/<id>-URL binnen de timeout), OF
    3. er gebeurt een exception ERGENS in de Playwright-keten, die door
       enrich_opponents.run_padelstat_for_players() stil wordt opgevangen
       (behalve de logregel "-> FOUT: ...") en dus in de app zelf nooit
       zichtbaar wordt.

Dit script roept dezelfde functies rechtstreeks aan, met VOLLEDIGE, niet-
onderdrukte foutmeldingen en de ruwe kandidatenlijst, zodat je in één run
ziet welk van de drie scenario's van toepassing is.

--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    python diagnose_padelstat_search.py "Mondy Severine" "Vanlerberghe Vivianne"

Standaard headless=False (toont de browser), zodat je ook VISUEEL kan zien
wat er gebeurt als er iets vastloopt (bv. een cookie-banner die toch niet
weggeklikt raakt). Gebruik --headless om zonder zichtbare browser te
draaien.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# --- path setup: zelfde patroon als scrape_player.py ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import padelstats_scraper as ps  # noqa: E402


def diagnose(naam: str, headless: bool) -> None:
    print("=" * 78)
    print(f"DIAGNOSE VOOR: {naam!r}  (headless={headless})")
    print("=" * 78)

    # --- Stap 1: enkel de zoekfunctie, om te zien of er kandidaten zijn ---
    print("\n[Stap 1] search_padelstat_player() -- ruwe zoekresultaten:")
    try:
        candidates = ps.search_padelstat_player(naam, headless=headless)
    except Exception as e:  # noqa: BLE001
        print(f"  EXCEPTION tijdens search_padelstat_player(): {e}")
        traceback.print_exc()
        return

    if not candidates:
        print("  -> 0 kandidaten gevonden.")
        print("  Conclusie: deze speler staat (onder deze exacte naam) niet op padelstats.be,")
        print("  of de zoekfunctie/pagina-structuur werkt anders dan verwacht voor deze naam.")
        print("  Probeer eventueel een kortere/andere schrijfwijze (bv. enkel achternaam).")
        return

    print(f"  -> {len(candidates)} kandidaat/kandidaten gevonden:")
    for c in candidates:
        print(f"     [{c['_index']}] naam={c['name']!r}  klassement={c['klassement']}  club={c['club']!r}")
        print(f"          ruwe kaarttekst: {c['card_text']!r}")

    # --- Stap 2: de klik + padelstat-ID ophalen, voor de EERSTE kandidaat ---
    print("\n[Stap 2] _click_and_get_padelstat_id() voor de eerste kandidaat:")
    try:
        padelstat_id = ps._click_and_get_padelstat_id(naam, candidates[0]["_index"], headless=headless)
    except Exception as e:  # noqa: BLE001
        print(f"  EXCEPTION tijdens _click_and_get_padelstat_id(): {e}")
        traceback.print_exc()
        return

    if not padelstat_id:
        print("  -> Geen padelstat_id teruggekregen (de klik navigeerde niet naar /speler/<id>).")
        print("  Conclusie: de zoekresultaat-kaart werd gevonden, maar het KLIKKEN erop faalt --")
        print("  mogelijk een gewijzigde paginastructuur, een overlay die de klik blokkeert, of een")
        print("  navigatie-timeout. Draai dit script zonder --headless om het visueel te zien.")
        return

    print(f"  -> padelstat_id = {padelstat_id}")

    # --- Stap 3: de rating zelf ophalen ---
    print("\n[Stap 3] fetch_padelstat_rating() voor dit padelstat_id:")
    try:
        result = ps.fetch_padelstat_rating(padelstat_id, headless=headless)
    except Exception as e:  # noqa: BLE001
        print(f"  EXCEPTION tijdens fetch_padelstat_rating(): {e}")
        traceback.print_exc()
        return

    print(f"  -> rating={result['rating']}  rating_source={result['rating_source']}")
    print(f"     raw_text_snippet: {result['raw_text_snippet']!r}")

    # --- Stap 4: de VOLLEDIGE, gecombineerde functie (zoals enrich_opponents die aanroept) ---
    print("\n[Stap 4] search_and_fetch_padelstat_rating() -- de volledige, gecombineerde aanroep:")
    try:
        full_result = ps.search_and_fetch_padelstat_rating(naam, club=None, headless=headless)
    except Exception as e:  # noqa: BLE001
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return
    print(f"  -> {full_result}")

    print("\nCONCLUSIE: als je dit ziet, werkt de volledige keten voor deze naam.")
    print("Komt de app toch nog steeds zonder padelstat, dan zit het verschil in HOE")
    print("enrich_opponents.py deze functie aanroept (bv. een andere naam-schrijfwijze")
    print("dan wat in Firestore staat) -- vergelijk de 'naam' die hierboven gebruikt is")
    print("met profile.get('display_name') in Firestore voor deze speler.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Diagnosticeert waarom padelstats_scraper voor een speler niets teruggeeft."
    )
    parser.add_argument("namen", nargs="+", help="Een of meer spelernamen om te testen.")
    parser.add_argument("--headless", action="store_true", help="Verberg de browser (standaard: zichtbaar).")
    args = parser.parse_args()

    for naam in args.namen:
        diagnose(naam, headless=args.headless)
        print("\n")
