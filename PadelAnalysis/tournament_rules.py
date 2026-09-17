"""
tournament_rules.py — configureerbare reglementsparameters per tornooi/categorie/afdeling.

PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17 (op verzoek van Kim, na het aanleveren
van Reglement_Padel_Senior_Cup.pdf).

Kim's 3 vragen, samengevat:
  1. "paarverdelingen die niet aan de grenzen voldoen mag je uitsluiten en niet
     tonen" — combinaties/rotaties buiten de toegelaten punten-grenzen per rotatie
     moeten UITGESLOTEN worden, niet enkel gemarkeerd.
  2. "match 1 van de rotatie = sterkste opstelling" — binnen ÉÉN rotatie (2
     gelijktijdige wedstrijden) speelt het sterkste duo op het laagst genummerde
     bord van die rotatie, het zwakkere duo op het andere bord. BELANGRIJKE
     CORRECTIE t.o.v. de vorige implementatie: het reglement (6.6) vergelijkt de
     SOM van de klassementen van de 2 spelers in een duo, niet het hoogste
     individuele klassement van de twee — dat laatste deed
     lineup_lab.rank_pairs_by_official_rank() voorheen wel (zie de fix in
     lineup_lab.py, PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17).
  3. "Ik heb specifiek het reglement van de senior cup. Er zijn ook andere
     tornooien [...] Belangrijkste is dat die parameters getoond worden en
     eventueel instelbaar zijn per tornooi versie om te weten dat je met de
     juiste regels werkt." — vandaag enkel Padel Senior Cup volledig ingevuld;
     de structuur is uitbreidbaar (TOURNAMENTS-dict), en de actieve keuze moet
     ALTIJD zichtbaar + aanpasbaar zijn in de UI (zie
     page_lineup_lab.py:_render_tournament_rules_selector()).

--------------------------------------------------------------------------
BRON EN BEGRIPSVERDUIDELIJKING
--------------------------------------------------------------------------
Bron: Reglement_Padel_Senior_Cup.pdf (2026), artikel 2.1 (tabellen "Minimum en
maximum aantal punten per rotatie" + "Minimum en maximum toegelaten klassement",
apart voor OPEN en DAMES) en artikel 6.6 ("Tijdens de ontmoeting worden duo's
samengesteld op basis van de som van de klassementen van de spelers per rotatie
[...] De som van de klassementspunten per rotatie moet hierbij tussen de
minimum en maximum grenzen liggen [...] Hierbij moet in match 1/3 het sterke
duo aantreden en in match 2/4 het zwakkere duo.").

Twee VERSCHILLENDE grootheden, beide op dezelfde P-schaal (rechtstreeks
optelbaar, geen aparte omrekening nodig):
  - "klassement" (per INDIVIDUELE speler, bv. P500): elke opgestelde speler
    moet, voor de gekozen afdeling, tussen klassement_min en klassement_max
    liggen (art. 9.3.5/9.3.6: te hoog/te laag klassement -> sancties).
  - "punten per rotatie" (SOM van de klassementen van ALLE 4 spelers die
    samen 1 rotatie vormen — dus de 2 duo's/2 gelijktijdige wedstrijden van
    die rotatie SAMEN, niet per duo apart): moet tussen punten_min en
    punten_max liggen voor de gekozen afdeling (art. 9.3.3/9.3.4: te veel/te
    weinig punten -> sancties, met WO bij te veel punten).

Elke afdeling-entry is een dict:
    {"punten_min": int, "punten_max": int, "klassement_min": int, "klassement_max": int}
"""
from __future__ import annotations

from typing import Optional

# ─────────────────────────────────────────────
# Padel Senior Cup 2026 — art. 2.1 (volledig ingevuld)
# ─────────────────────────────────────────────
SENIOR_CUP_OPEN = {
    1: {"punten_min": 2400, "punten_max": 3500, "klassement_min": 500, "klassement_max": 1000},
    2: {"punten_min": 1700, "punten_max": 2300, "klassement_min": 400, "klassement_max": 700},
    3: {"punten_min": 1300, "punten_max": 1600, "klassement_min": 300, "klassement_max": 500},
    4: {"punten_min": 900, "punten_max": 1200, "klassement_min": 200, "klassement_max": 400},
    5: {"punten_min": 500, "punten_max": 800, "klassement_min": 100, "klassement_max": 300},
    6: {"punten_min": 300, "punten_max": 450, "klassement_min": 50, "klassement_max": 200},
}

SENIOR_CUP_DAMES = {
    1: {"punten_min": 1600, "punten_max": 2200, "klassement_min": 400, "klassement_max": 700},
    2: {"punten_min": 900, "punten_max": 1500, "klassement_min": 200, "klassement_max": 400},
    3: {"punten_min": 500, "punten_max": 800, "klassement_min": 100, "klassement_max": 300},
    4: {"punten_min": 250, "punten_max": 450, "klassement_min": 50, "klassement_max": 200},
    5: {"punten_min": 200, "punten_max": 200, "klassement_min": 50, "klassement_max": 50},
}

# PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17: uitbreidbare registry. Vandaag
# enkel Padel Senior Cup ingevuld (op verzoek van Kim: "vandaag niet teveel
# zorgen over maken" voor Mixed/Open/Vrouwen-tornooien). Voeg een nieuwe
# tornooi-versie toe als een extra top-level key, met dezelfde structuur
# (categorie -> afdeling -> {punten_min, punten_max, klassement_min,
# klassement_max}), zodra Kim het bijhorende reglement bezorgt.
TOURNAMENTS: dict = {
    "Padel Senior Cup 2026": {
        "Open": SENIOR_CUP_OPEN,
        "Dames": SENIOR_CUP_DAMES,
    },
    # Voorbeeld voor een toekomstige, nog niet ingevulde uitbreiding:
    # "Padel Mixed Cup 2026": {"Mixed": {...}},
    # "Padel Open Cup 2026": {"Open": {...}, "Vrouwen": {...}},
}

DEFAULT_TOURNAMENT = "Padel Senior Cup 2026"
DEFAULT_CATEGORY = "Open"


def list_tournaments() -> list:
    return list(TOURNAMENTS.keys())


def list_categories(tournament: str) -> list:
    return list(TOURNAMENTS.get(tournament, {}).keys())


def list_afdelingen(tournament: str, category: str) -> list:
    return sorted(TOURNAMENTS.get(tournament, {}).get(category, {}).keys())


def get_afdeling_rules(tournament: str, category: str, afdeling) -> Optional[dict]:
    """Geeft de regel-dict terug voor een specifieke afdeling, of None als de
    combinatie (tornooi/categorie/afdeling) niet (volledig) ingevuld is —
    aanroepers moeten None als 'geen check toepassen' behandelen, zodat een
    nog niet ingevuld tornooi de rest van de app niet blokkeert."""
    try:
        afdeling_int = int(afdeling)
    except (TypeError, ValueError):
        return None
    return TOURNAMENTS.get(tournament, {}).get(category, {}).get(afdeling_int)


def format_rules_caption(tournament: str, category: str, afdeling, rules: Optional[dict]) -> str:
    """Leesbare, altijd-tonen-bare samenvatting van de actieve regelset —
    zodat in de UI ALTIJD duidelijk is met welke parameters gerekend wordt
    (Kim's vraag 3: 'belangrijkste is dat die parameters getoond worden')."""
    if rules is None:
        return (
            f"⚠️ Geen reglementsparameters gekend voor '{tournament}' / {category} / afdeling {afdeling} — "
            "er wordt NIET gefilterd op puntengrenzen (alle combinaties worden getoond)."
        )
    return (
        f"📖 Reglement actief: **{tournament} — {category}, afdeling {afdeling}**. "
        f"Toegelaten punten per rotatie: **{rules['punten_min']}–{rules['punten_max']}**. "
        f"Toegelaten individueel klassement: **P{rules['klassement_min']}–P{rules['klassement_max']}**."
    )


def rotation_points_bounds_ok(total_punten: float, rules: Optional[dict]) -> tuple:
    """PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17, vraag 1: controleert of de
    SOM van de klassementen van ALLE 4 spelers in 1 rotatie (2 duo's samen)
    binnen de toegelaten grenzen van de afdeling valt.

    Returns (ok: bool, reason: str). Bij rules=None (geen regelset actief of
    onvolledig ingevuld tornooi): ALTIJD ok=True — filtering gebeurt enkel als
    er een expliciete, volledige regelset gekozen is."""
    if rules is None:
        return True, "geen reglement-check actief"
    lo, hi = rules["punten_min"], rules["punten_max"]
    if total_punten < lo:
        return False, f"{total_punten:.0f} punten < minimum {lo} voor deze afdeling"
    if total_punten > hi:
        return False, f"{total_punten:.0f} punten > maximum {hi} voor deze afdeling"
    return True, f"{total_punten:.0f} punten (toegelaten: {lo}–{hi})"


def player_klassement_ok(klassement: Optional[float], rules: Optional[dict]) -> tuple:
    """Controleert of het individuele klassement van 1 speler binnen de
    toegelaten grenzen van de afdeling valt (art. 9.3.5/9.3.6). Bij
    klassement=None (onbekend) of rules=None: ALTIJD ok=True (geen
    ongefundeerde uitsluiting bij ontbrekende data)."""
    if rules is None or klassement is None:
        return True, "onbekend/geen check"
    lo, hi = rules["klassement_min"], rules["klassement_max"]
    if klassement < lo:
        return False, f"P{klassement:.0f} < minimum P{lo}"
    if klassement > hi:
        return False, f"P{klassement:.0f} > maximum P{hi}"
    return True, f"P{klassement:.0f} (toegelaten: P{lo}–P{hi})"
