"""
elo_rating.py - gebalanceerde koppelverdeling op basis van spelerssterkte.

PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13 (BELANGRIJKE ARCHITECTUURWIJZIGING):
Dit bestand bevatte voorheen een EIGEN, zelf berekende Elo-schatting
(compute_player_elo, met een eigen K-factor-schema en verwachte-score-
formule, gebaseerd op onze eigen Firestore-matchdata). Die eigen berekening
is VOLLEDIG VERWIJDERD, op uitdrukkelijk verzoek van Kim, nadat een
kalibratietest (elo_calibration.py) aantoonde dat het model structureel en
onoplosbaar afweek van de externe referentie padelstats.be: zelfs een brede
grid search over de K-factor en de Elo-deler kon Tim Van Rossom (padelstat
360) en Gregory Claeys (padelstat 230) niet ook maar benaderen (beste fit gaf
respectievelijk ~195 en ~73, in de VERKEERDE richting voor Gregory). De
grondoorzaak: onze berekening ankerde elke match aan het RUWE, officiële
P-klassement van de tegenstander uit dat ene matchrecord, terwijl
padelstats.be vermoedelijk een wederzijds bijgewerkt NETWERK-Elo berekent
over alle ~200.000 actieve Vlaamse spelers samen - twee fundamenteel
verschillende methodes die met onze beperkte, lokale matchdata niet
converteerbaar zijn.

Besluit (Optie B uit de discussie): in plaats van de eigen berekening verder
te verfijnen, wordt de 'playing strength' voortaan RECHTSTREEKS gescraped
van padelstats.be (zie padelstats_scraper.py / bulk_fetch_padelstat_
ratings.py) en gecachet in Firestore (firebase_service.py:
save_padelstat_rating / get_padelstat_rating). Alle schermen die voorheen de
eigen Elo toonden (opponent_dossier.py, opponent_analysis.py, dashboard.py)
zijn overgeschakeld op die gecachete padelstats-waarde.

Wat WEL bewaard is uit dit bestand: suggest_balanced_pairings() is een
generieke koppelverdeling-utility die simpelweg een {player_id: sterkte}-
dict als input neemt - het maakt voor deze functie niet uit of die
'sterkte' een padelstat-waarde, een officieel klassement, of iets anders is.
Deze functie blijft daarom gewoon bruikbaar; enkel de manier waarop de
sterkte-waarden bepaald worden (nu via padelstats.be, met een fallback naar
het officiële TVL-klassement) is elders in de code aangepast - zie
opponent_analysis._own_player_rating().
"""
from __future__ import annotations

# Boven dit aantal spelers wordt niet meer exhaustief elke koppelverdeling
# doorgerekend (11!! = 10.395 verdelingen bij 12 spelers is nog triviaal
# snel; bij grotere groepen wordt een gebalanceerde heuristiek gebruikt).
EXHAUSTIVE_PAIRING_LIMIT = 12


def _all_perfect_matchings(ids: list[str]) -> list[list[tuple[str, str]]]:
    """Genereert ALLE mogelijke volledige koppelverdelingen (perfect
    matchings) van een even aantal spelers. Recursief: neem de eerste
    speler, koppel die aan elke mogelijke partner, en herhaal voor de rest."""
    if not ids:
        return [[]]
    first, rest = ids[0], ids[1:]
    result = []
    for i in range(len(rest)):
        partner = rest[i]
        remaining = rest[:i] + rest[i + 1:]
        for sub in _all_perfect_matchings(remaining):
            result.append([(first, partner)] + sub)
    return result


def _greedy_balanced_matching(ids: list[str], player_ratings: dict[str, float]) -> list[tuple[str, str]]:
    """Fallback voor grote groepen (> EXHAUSTIVE_PAIRING_LIMIT spelers):
    sorteer op sterkte en koppel sterkste met zwakste, tweede-sterkste met
    tweede-zwakste, enzovoort. Een bekende, eenvoudige heuristiek voor
    gebalanceerde koppels; niet gegarandeerd optimaal, maar snel en
    redelijk voor grote groepen."""
    sorted_ids = sorted(ids, key=lambda pid: player_ratings[pid])
    n = len(sorted_ids)
    return [(sorted_ids[i], sorted_ids[n - 1 - i]) for i in range(n // 2)]


def suggest_balanced_pairings(
    player_ratings: dict[str, float],
    top_n: int = 3,
) -> list[dict]:
    """Gegeven {player_id: sterkte} voor een EVEN aantal spelers, berekent
    alle (of bij een grote groep: één gebalanceerde) koppelverdeling(en) en
    scoort elke verdeling op BALANS: hoe kleiner het verschil tussen de
    sterkste en de zwakste koppel-gemiddelde-sterkte, hoe gebalanceerder (en
    dus beter gerangschikt).

    'sterkte' kan eender welke numerieke waarde zijn (padelstats.be playing
    strength, officieel P-klassement, ...) - deze functie is bewust bron-
    onafhankelijk, zie module-docstring.

    Returns: lijst van {"pairs": [(id_a, id_b), ...], "pair_ratings": [float, ...],
    "spread": float}, gesorteerd van meest naar minst gebalanceerd, max top_n
    resultaten. Lege lijst als er minder dan 2 spelers zijn of een oneven
    aantal (een oneven aantal kan niet volledig in koppels verdeeld worden).
    """
    ids = list(player_ratings.keys())
    n = len(ids)
    if n < 2 or n % 2 != 0:
        return []

    if n <= EXHAUSTIVE_PAIRING_LIMIT:
        matchings = _all_perfect_matchings(ids)
    else:
        matchings = [_greedy_balanced_matching(ids, player_ratings)]

    scored = []
    for pairs in matchings:
        pair_ratings = [(player_ratings[a] + player_ratings[b]) / 2.0 for a, b in pairs]
        spread = max(pair_ratings) - min(pair_ratings) if pair_ratings else 0.0
        scored.append({"pairs": pairs, "pair_ratings": pair_ratings, "spread": round(spread, 1)})
    scored.sort(key=lambda x: x["spread"])
    return scored[:top_n]
