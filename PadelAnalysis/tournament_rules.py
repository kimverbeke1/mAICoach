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

--------------------------------------------------------------------------
PADEL_ANALYSIS_KLASSEMENT_DISCRETE_STEPS_FIX_2026-09-19 (op verzoek van Kim:
"P150-P250 is niet mogelijk. Officieel klassement padel heren is
P100,P200,P300,P400,P500,P700,P1000 en voor dame:
P50,P100,P200,P300,P400,P500,P700")
--------------------------------------------------------------------------
BELANGRIJK: het officiële TVL-klassement bestaat NIET als continue schaal
(elk geheel getal mogelijk), maar UITSLUITEND als een vaste, discrete
stappenreeks — GEVERIFIEERD tegen twee onafhankelijke, externe bronnen
(PadelTrack.be se spelerslijst-filter en KTCM.be se inschalingstabel):
    HEREN : P100, P200, P300, P400, P500, P700, P1000  (dus GEEN P50)
    DAMES : P50,  P100, P200, P300, P400, P500, P700   (dus GEEN P1000)
Elke klassement_min/klassement_max hieronder MOET dus exact een lid zijn
van de bijhorende stappenreeks — een grens als "P150" of "P250" zou een
niet-bestaande waarde impliceren en is dus per definitie fout.

BUG GEVONDEN EN OPGELOST: SENIOR_CUP_OPEN afdeling 6 had
"klassement_min": 50 staan — maar P50 bestaat NIET voor heren/Open (enkel
voor Dames). Dit is gecorrigeerd naar 100 (de laagste bestaande heren-
waarde). Alle andere afdelingen (Open 1-5, Dames 1-5) bleken bij controle
al correct — elke klassement_min/klassement_max daar is al een geldige
waarde uit de juiste stappenreeks.

Nieuwe validatiefunctie validate_klassement_steps() hieronder controleert
dit voortaan AUTOMATISCH voor elke afdeling in TOURNAMENTS, zodat een
toekomstige tikfout (bv. bij het toevoegen van een nieuw tornooi/reeks)
onmiddellijk opgemerkt wordt i.p.v. stilzwijgend een onmogelijke grens in
te voeren. Deze check draait éénmalig bij het importeren van deze module
(assert), zodat een foute configuratie de app niet stil laat doorwerken.
"""
from __future__ import annotations

from typing import Optional

# PADEL_ANALYSIS_KLASSEMENT_DISCRETE_STEPS_FIX_2026-09-19: de ENIGE
# geldige officiële klassementswaarden, geverifieerd tegen PadelTrack.be
# en KTCM.be. Nooit een klassement_min/klassement_max buiten deze sets
# gebruiken.
HEREN_KLASSEMENT_STAPPEN = (100, 200, 300, 400, 500, 700, 1000)
DAMES_KLASSEMENT_STAPPEN = (50, 100, 200, 300, 400, 500, 700)

SENIOR_CUP_OPEN = {
    1: {"punten_min": 2400, "punten_max": 3500, "klassement_min": 500, "klassement_max": 1000},
    2: {"punten_min": 1700, "punten_max": 2300, "klassement_min": 400, "klassement_max": 700},
    3: {"punten_min": 1300, "punten_max": 1600, "klassement_min": 300, "klassement_max": 500},
    4: {"punten_min": 900, "punten_max": 1200, "klassement_min": 200, "klassement_max": 400},
    5: {"punten_min": 500, "punten_max": 800, "klassement_min": 100, "klassement_max": 300},
    # PADEL_ANALYSIS_KLASSEMENT_DISCRETE_STEPS_FIX_2026-09-19: klassement_min
    # was hier voorheen 50 (P50) — die waarde bestaat NIET voor heren/Open,
    # enkel voor Dames. Gecorrigeerd naar 100 (P100), de laagste bestaande
    # heren-waarde.
    6: {"punten_min": 300, "punten_max": 450, "klassement_min": 100, "klassement_max": 200},
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


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_KLASSEMENT_DISCRETE_STEPS_FIX_2026-09-19
# ---------------------------------------------------------------------------
def _steps_for_category(category: str) -> tuple:
    """Geeft de geldige klassement-stappenreeks terug voor een categorie.
    'Dames' -> DAMES_KLASSEMENT_STAPPEN (bevat P50, geen P1000).
    Alles anders (o.a. 'Open') -> HEREN_KLASSEMENT_STAPPEN (bevat P1000,
    geen P50) — Open-afdelingen bevatten immers zowel heren als dames-
    duo's, maar de klassement_min/max-grenzen in dit bestand zijn tot nu
    toe steeds op de HEREN-stappenreeks gebaseerd (zie SENIOR_CUP_OPEN)."""
    return DAMES_KLASSEMENT_STAPPEN if category.strip().lower() == "dames" else HEREN_KLASSEMENT_STAPPEN


def validate_klassement_steps() -> list:
    """Doorloopt ALLE afdelingen in TOURNAMENTS en controleert dat
    klassement_min/klassement_max exact een geldige, bestaande officiële
    klassementswaarde is (dus nooit een tussenliggende, niet-bestaande
    waarde zoals P150 of P250). Geeft een lijst van foutmeldingen terug
    (leeg = alles correct). Wordt hieronder bij import automatisch
    aangeroepen (assert), zodat een foute configuratie nooit stilzwijgend
    de app in kan."""
    fouten = []
    for tournament, categories in TOURNAMENTS.items():
        for category, afdelingen in categories.items():
            steps = _steps_for_category(category)
            for afdeling, rules in afdelingen.items():
                for veld in ("klassement_min", "klassement_max"):
                    waarde = rules.get(veld)
                    if waarde is not None and waarde not in steps:
                        fouten.append(
                            f"{tournament} / {category} / afdeling {afdeling}: {veld}={waarde} is GEEN "
                            f"geldige officiële klassementswaarde voor deze categorie (toegelaten: "
                            f"{', '.join('P' + str(s) for s in steps)})"
                        )
    return fouten


# Automatische, blokkerende validatie bij het importeren van deze module:
# een foute configuratie (bv. een toekomstige tikfout bij het toevoegen van
# een nieuw tornooi/reeks) moet DIRECT zichtbaar falen, niet stilzwijgend
# een onmogelijke klassementgrens laten doorwerken naar de rest van de app.
_validation_errors = validate_klassement_steps()
assert not _validation_errors, (
    "tournament_rules.py bevat ongeldige klassement-grenzen (geen bestaande officiële "
    "P-waarde): \n" + "\n".join(_validation_errors)
)
