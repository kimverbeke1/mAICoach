"""
tournament_rules.py — configureerbare reglementsparameters per tornooi/categorie/afdeling.

PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17 (op verzoek van Kim, na het aanleveren
van Reglement_Padel_Senior_Cup.pdf).

Bron: Reglement_Padel_Senior_Cup.pdf (2026), artikel 2.1 (tabellen "Minimum en
maximum aantal punten per rotatie" + "Minimum en maximum toegelaten klassement",
apart voor OPEN en DAMES) en artikel 6.6 ("Tijdens de ontmoeting worden duo's
samengesteld op basis van de som van de klassementen van de spelers per rotatie
[...] De som van de klassementspunten per rotatie moet hierbij tussen de
minimum en maximum grenzen liggen [...] Hierbij moet in match 1/3 het sterke
duo aantreden en in match 2/4 het zwakkere duo.").

Twee VERSCHILLENDE grootheden, beide op dezelfde P-schaal:
  - "klassement" (per INDIVIDUELE speler): tussen klassement_min en
    klassement_max voor de gekozen afdeling.
  - "punten per rotatie" (SOM van de klassementen van ALLE 4 spelers die
    samen 1 rotatie vormen): moet tussen punten_min en punten_max liggen.
"""
from __future__ import annotations

from typing import Optional

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

TOURNAMENTS: dict = {
    "Padel Senior Cup 2026": {
        "Open": SENIOR_CUP_OPEN,
        "Dames": SENIOR_CUP_DAMES,
    },
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
    try:
        afdeling_int = int(afdeling)
    except (TypeError, ValueError):
        return None
    return TOURNAMENTS.get(tournament, {}).get(category, {}).get(afdeling_int)


def format_rules_caption(tournament: str, category: str, afdeling, rules: Optional[dict]) -> str:
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
    if rules is None:
        return True, "geen reglement-check actief"
    lo, hi = rules["punten_min"], rules["punten_max"]
    if total_punten < lo:
        return False, f"{total_punten:.0f} punten < minimum {lo} voor deze afdeling"
    if total_punten > hi:
        return False, f"{total_punten:.0f} punten > maximum {hi} voor deze afdeling"
    return True, f"{total_punten:.0f} punten (toegelaten: {lo}–{hi})"


def player_klassement_ok(klassement: Optional[float], rules: Optional[dict]) -> tuple:
    if rules is None or klassement is None:
        return True, "onbekend/geen check"
    lo, hi = rules["klassement_min"], rules["klassement_max"]
    if klassement < lo:
        return False, f"P{klassement:.0f} < minimum P{lo}"
    if klassement > hi:
        return False, f"P{klassement:.0f} > maximum P{hi}"
    return True, f"P{klassement:.0f} (toegelaten: P{lo}–P{hi})"
