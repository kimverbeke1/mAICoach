"""
lineup_rotation.py - Rotatieplanner: combinatoriek, bordvolgorde-regels
(art. 6.6 + padelstat-tiebreak), best/worst-case-variantenumeratie, en de
matchup-berekening per bord.

Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
Zie de oorspronkelijke, monolithische versie van page_lineup_lab.py voor de
volledige historische toelichting bij elke fix in deze functies - dit
bestand is functioneel ONGEWIJZIGD t.o.v. die vorige versie.

--------------------------------------------------------------------------
PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29 (op verzoek van Kim: "aantal matchen per ontmoeting in
rotaties is gedefinieerd normaal via het reglement. die parameters zijn niet
direct zichtbaar daar maar in de najaarsinterclub zijn het dus 2 rotaties
van 2 matchen.")
--------------------------------------------------------------------------
Het formaat van een ontmoeting staat in het reglement en is NIET af te
lezen op de TVL-pagina's die we scrapen. Tot nu toe raadde de app het
aantal matchen uit eerdere uitslagenbladen, met 6 als terugval - fout voor
de najaarsinterclub. De constanten hieronder zijn nu de ENIGE bron van
waarheid; page_lineup_lab.py, lineup_sandbox.py en team_ai_advisor.py
lezen ze hier. Bij een ander formaat (bv. een andere periode) volstaat het
deze drie regels aan te passen.

--------------------------------------------------------------------------
PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29 (op verzoek van Kim: "zorg dat je bij de opstelling
aantal rotaties kan instellen. zal handig zijn voor in voorjaar waar het dan
3 rotaties is")
--------------------------------------------------------------------------
ROTATIONS_PER_ENCOUNTER is nu enkel de STANDAARDWAARDE (najaar: 2). Het
effectieve aantal rotaties wordt op de Opstelling-analyse-pagina gekozen
(page_lineup_lab.py) en doorgegeven aan de matchup-tabel, de
rotatieplanner en de sandbox. MATCHES_PER_ROTATION (2 matchen tegelijk per
rotatie) blijft vast.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29 (op verzoek van Kim)
--------------------------------------------------------------------------
De rotatieplanner kiest per rotatie nu EXACT 2 koppels uit de beschikbare
spelers, i.p.v. alle geselecteerde spelers in koppels te verdelen. Zie
_generate_rotation_candidates() voor de details. De oude hulpfuncties
(_count_perfect_matchings, _expand_tied_orderings) blijven staan maar
worden door de planner niet meer gebruikt.

--------------------------------------------------------------------------
PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30 (op verzoek van Kim, na
brainstorm over de matchup-analyse: "puntensysteem. 0 bij verlies, 1 bij
gelijkspel en 2 bij winst" + "opoffer"-scenario's + weging op historische
tegenstander-opstellingen)
--------------------------------------------------------------------------
ROOT CAUSE van "3 bijna-identieke resultaten" (Kim's voorbeeld: Best 2.05 /
2.05 / 2.03): de matchup-tabel middelde elke eigen opstelling over ALLE
mogelijke tegenstander-opstellingen alsof die allemaal even waarschijnlijk
zijn, en gebruikte als maatstaf "verwacht aantal gewonnen matchen" (EBW) -
een getal dat niet zegt of dat een veilige 3-1 is of een muntstuk tussen
2-2 en 3-1.

FIX, twee nieuwe bouwstenen, VOLLEDIG LOS van de bestaande EBW-logica (die
blijft bestaan, ongewijzigd, als secundair/tiebreak-getal):

  1. _match_outcome_point_probabilities(win_probs) - NIEUW. Neemt de 4
     (of n) individuele winkansen van 1 opstelling tegen 1 specifiek
     tegenstander-scenario, en berekent EXACT (geen simulatie - bij 4
     onafhankelijke kansen zijn er maar 16 combinaties) de kans op elke
     mogelijke uitslag, opgeteld tot puntensysteem 0/1/2 (Kim, bevestigd
     2026-09-30: 0 bij verlies, 1 bij gelijkspel/2-2, 2 bij winst - dus
     MEER matchen gewonnen dan de tegenstander = 2, gelijk aantal = 1,
     MINDER = 0). Ontbrekende winkansen (None) worden behandeld als 50%
     voor deze berekening ALLEEN (net als een neutrale muntworp) - de
     aanroeper kan aan de hand van _n_missing_win_probs() zien hoeveel dat
     er waren, om desgewenst te waarschuwen.

  2. Weging van tegenstander-scenario's: elk "unique_opponent_lineups"-item
     (uit lineup_rotation._collect_unique_opponent_lineups(), dit seizoen)
     krijgt een gewicht i.p.v. gelijk te tellen - zie
     _opponent_lineup_weight(). Een lineup die de tegenstander al N keer
     zo speelde (in _dezelfde_ rotatie-positie: rotatie 1 blijft apart van
     rotatie 2, want dat is een ander tactisch signaal) weegt zwaarder dan
     een louter theoretische, nooit geobserveerde combinatie. AL het
     gewicht komt uit dit SEIZOEN (bundle.previous_fixtures) - "alle
     seizoenen" was Kim's uiteindelijke voorkeur, maar de app heeft op dit
     moment GEEN betrouwbare rotatiepositie-informatie over vorige
     seizoenen (enkel round_text zoals "poule - 5", geen rotatienummer).
     Zie de uitgebreide toelichting hierover in het gesprek van
     2026-09-30 (Kim akkoord: "optie 1" = nu bouwen met dit seizoen,
     architectuur zo dat vorige seizoenen er later gewoon bij kunnen).
     _opponent_lineup_weight() is BEWUST de enige plek die dit bepaalt,
     zodat een latere uitbreiding (vorige-seizoenen-data erbij) hier
     lokaal blijft.

  3. _aggregate_group_point_probabilities(rows, weights) - combineert de
     per-scenario resultaten van 1 groep (1 eigen opstelling) tot een
     GEWOGEN gemiddelde kans op 2/1/0 punten over alle doorgerekende
     tegenstander-scenario's van die groep. Dit wordt het NIEUWE
     hoofdgetal in lineup_matchup_table.py; de bestaande best/worst-EBW
     blijft daarnaast zichtbaar als secundair getal.

Niets van het bovenstaande verandert de REGLEMENT-laag (bordvolgorde,
puntengrens per rotatie - art. 6.6/2.1) of de bestaande EBW/win_probability-
berekening: dit is een PARALLELLE, aanvullende maatstaf.
"""
import itertools
import streamlit as st
from dashboard_common import ll, taa
from lineup_scout import (
    _cached_official_rank, _cached_own_player_rating,
    _render_official_rank_warning, _format_points_bounds_diagnostic,
)
# PADEL_ANALYSIS_WINPROB_CALIBRATION_2026-09-22: zie lineup_lab.py voor de
# volledige toelichting bij de kalibratie van de winkans-formule.
# PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29: reglement najaarsinterclub = 2 rotaties x 2 matchen.
# PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29: standaardwaarde; instelbaar op de pagina (voorjaar: 3).
ROTATIONS_PER_ENCOUNTER = 2
ROTATIONS_MIN = 1
ROTATIONS_MAX = 4
MATCHES_PER_ROTATION = 2
MATCHES_PER_ENCOUNTER = ROTATIONS_PER_ENCOUNTER * MATCHES_PER_ROTATION

_WIN_PROB_DISCLAIMER = (
    "De winkans is een logistische schatting op het verschil in speelsterkte, "
    "gekalibreerd op 44 recent gespeelde dubbels (70% van de uitslagen juist voorspeld; "
    "Brier 0.195 tegenover 0.25 voor een muntstuk). Bij uitgesproken favorieten en "
    "underdogs is de schatting nog steeds aan de voorzichtige kant, en de steekproef is "
    "klein - richtinggevend signaal dus, geen garantie."
)

# -----------------------------------------------
# PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30 - zie moduledocstring.
# -----------------------------------------------
def _n_missing_win_probs(win_probs: list) -> int:
    """Aantal onbekende (None) winkansen in de lijst - de aanroeper kan dit
    gebruiken om te waarschuwen dat de puntenkans-berekening deels op een
    neutrale 50%-aanname steunt."""
    return sum(1 for p in win_probs if p is None)


def _match_outcome_point_probabilities(win_probs: list) -> dict:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: exacte kansverdeling op
    het PLOEGRESULTAAT (0/1/2 punten - Kim, bevestigd 2026-09-30) voor 1
    opstelling tegen 1 specifiek tegenstander-scenario, gegeven de
    individuele winkans per match.

    Puntensysteem: MEER matchen gewonnen dan de tegenstander -> 2 punten,
    EVENVEEL -> 1 punt, MINDER -> 0 punten. Bij een even aantal matchen (het
    gebruikelijke geval, bv. 4) is een gelijke stand (bv. 2-2) mogelijk en
    geeft 1 punt; bij een oneven aantal matchen kan dat niet voorkomen en is
    de kans op 1 punt dus 0.

    Berekent dit EXACT (geen Monte Carlo): met n individuele, onafhankelijke
    kansen zijn er 2^n mogelijke uitkomsten - voor de gebruikelijke n=4 is
    dat 16, dus dit is triviaal snel. Werkt voor elk aantal matchen (bv. 6
    bij een ander formaat), niet enkel 4.

    Ontbrekende winkansen (None - onvoldoende rating-data) worden voor DEZE
    berekening als 50% behandeld (neutrale muntworp), zodat de functie
    nooit crasht of None propageert. Gebruik _n_missing_win_probs() om te
    weten hoeveel dat er waren en dat eventueel apart te signaleren.

    Geeft {"p2": float, "p1": float, "p0": float} terug (som = 1.0)."""
    probs = [(0.5 if p is None else max(0.0, min(1.0, float(p)))) for p in win_probs]
    n = len(probs)
    if n == 0:
        return {"p2": 0.0, "p1": 0.0, "p0": 0.0}
    half = n / 2.0
    p2 = p1 = p0 = 0.0
    for outcome in itertools.product((0, 1), repeat=n):
        # outcome[i] == 1 betekent: wij winnen match i.
        prob = 1.0
        for won, p in zip(outcome, probs):
            prob *= p if won else (1.0 - p)
        wins = sum(outcome)
        if wins > half:
            p2 += prob
        elif wins == half:
            p1 += prob
        else:
            p0 += prob
    return {"p2": p2, "p1": p1, "p0": p0}


def _opponent_lineup_weight(info: dict) -> float:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: gewicht van 1
    tegenstander-scenario ("unique_opponent_lineups"-item) voor de gewogen
    puntenkans-aggregatie hieronder.

    Regel (dit seizoen, zie moduledocstring voor waarom): elke keer dat de
    tegenstander deze EXACTE koppelverdeling, IN DEZELFDE ROTATIE-POSITIE,
    dit seizoen effectief speelde (info["historical_count"], gezet door
    _collect_unique_opponent_lineups()) telt voor +1.0 gewicht bovenop een
    vaste BASIS van 1.0 die elk scenario al krijgt (ook een zuiver
    theoretisch, nooit geobserveerd scenario telt dus nog mee, maar wel
    veel lichter dan een herhaald patroon).

    Voorbeeld: nooit gespeeld -> gewicht 1.0. 1x gespeeld -> gewicht 2.0.
    3x gespeeld -> gewicht 4.0 (die combinatie weegt dan 4x zo zwaar als
    een nooit geobserveerde combinatie in het gewogen gemiddelde).

    BEWUST de ENIGE plek die dit bepaalt: een latere uitbreiding met
    vorige-seizoenen-data (zodra die met een betrouwbare rotatiepositie
    beschikbaar is) hoeft enkel deze functie aan te passen."""
    n_seen = int(info.get("historical_count", 0) or 0)
    return 1.0 + float(n_seen)


def _aggregate_group_point_probabilities(rows: list, weights: dict) -> dict:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: combineert de
    per-tegenstander-scenario resultaten van 1 groep (1 eigen opstelling,
    dus een lijst van matchup-dicts met een reeds berekende
    "point_probs"-veld) tot een GEWOGEN gemiddelde puntenkans over alle
    doorgerekende scenario's van die groep.

    `weights` is een dict {matchup_id(m): gewicht}, typisch gevuld via
    _opponent_lineup_weight() per onderliggend tegenstander-scenario - de
    aanroeper (lineup_matchup_table.py) kent de koppeling tussen elke rij en
    zijn tegenstander-scenario-sleutel, dit bestand niet.

    Geeft {"p2": float, "p1": float, "p0": float, "n_missing_ratings": int}
    terug. Bij een lege of ongewogen (totaalgewicht 0) invoer: alle kansen
    0.0 en n_missing_ratings 0, om de aanroeper nooit te laten crashen."""
    totaal_gewicht = 0.0
    p2 = p1 = p0 = 0.0
    n_missing = 0
    for m in rows:
        gewicht = weights.get(id(m), 1.0)
        pp = m.get("point_probs") or {}
        totaal_gewicht += gewicht
        p2 += gewicht * pp.get("p2", 0.0)
        p1 += gewicht * pp.get("p1", 0.0)
        p0 += gewicht * pp.get("p0", 0.0)
        n_missing += int(m.get("n_missing_win_probs", 0) or 0)
    if totaal_gewicht <= 0:
        return {"p2": 0.0, "p1": 0.0, "p0": 0.0, "n_missing_ratings": n_missing}
    return {
        "p2": p2 / totaal_gewicht,
        "p1": p1 / totaal_gewicht,
        "p0": p0 / totaal_gewicht,
        "n_missing_ratings": n_missing,
    }


# -----------------------------------------------
# Rotatieplanner - combinatoriek (1 rotatie tegelijk, ONGEWIJZIGD)
# -----------------------------------------------
def _count_perfect_matchings(n: int) -> int:
    if n < 2 or n % 2 != 0:
        return 0
    result = 1
    k = n - 1
    while k > 0:
        result *= k
        k -= 2
    return result


_ROTATION_EXHAUSTIVE_LIMIT = 400


# -----------------------------------------------
# Rotatie-bewuste enumeratie (rotatie-veilige koppelverdeling over ALLE
# borden van de ontmoeting)
# -----------------------------------------------
def _all_perfect_matchings_generic(seq: list) -> list:
    if len(seq) == 0:
        return [[]]
    if len(seq) % 2 != 0:
        return []
    first, rest = seq[0], seq[1:]
    out: list = []
    for i, partner in enumerate(rest):
        remaining = rest[:i] + rest[i + 1:]
        for sub in _all_perfect_matchings_generic(remaining):
            out.append([frozenset({first, partner})] + sub)
    return out


def _enumerate_rotation_aware_pairings(
    player_ids: list, required_counts: dict, call_budget: int = 300_000,
) -> tuple:
    total_slots = sum(required_counts.values())
    if total_slots == 0 or total_slots % 2 != 0:
        return [], False
    n_boards = total_slots // 2
    rotation_sizes = []
    remaining_boards = n_boards
    while remaining_boards > 0:
        take = min(MATCHES_PER_ROTATION, remaining_boards)  # PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29
        rotation_sizes.append(take)
        remaining_boards -= take
    results: list = []
    seen_keys = set()
    calls = [0]
    truncated = [False]

    def backtrack(rotation_idx, remaining, used_partner_pairs, rotations_so_far):
        calls[0] += 1
        if calls[0] > call_budget:
            truncated[0] = True
            return
        if rotation_idx == len(rotation_sizes):
            key = tuple(
                tuple(sorted(tuple(sorted(pair)) for pair in rot))
                for rot in rotations_so_far
            )
            if key not in seen_keys:
                seen_keys.add(key)
                results.append([list(rot) for rot in rotations_so_far])
            return
        boards_needed = rotation_sizes[rotation_idx]
        players_needed = boards_needed * 2
        eligible = sorted(p for p in player_ids if remaining[p] > 0)
        if len(eligible) < players_needed:
            return
        for combo in itertools.combinations(eligible, players_needed):
            matchings = _all_perfect_matchings_generic(list(combo))
            for matching in matchings:
                if any(pair in used_partner_pairs for pair in matching):
                    continue
                for pair in matching:
                    for p in pair:
                        remaining[p] -= 1
                rotations_so_far.append(matching)
                new_used = used_partner_pairs | set(matching)
                backtrack(rotation_idx + 1, remaining, new_used, rotations_so_far)
                rotations_so_far.pop()
                for pair in matching:
                    for p in pair:
                        remaining[p] += 1
                if calls[0] > call_budget:
                    return

    backtrack(0, dict(required_counts), set(), [])
    return results, truncated[0]


def _default_opponent_max_per_player(chosen_opp_ids: list, needed_slots: int) -> dict:
    n = len(chosen_opp_ids)
    if n == 0:
        return {}
    base = needed_slots // n
    extra = needed_slots % n
    return {pid: base + (1 if i < extra else 0) for i, pid in enumerate(chosen_opp_ids)}


# -----------------------------------------------
# Bordvolgorde: officiele regel + padelstat-tie-breaker
# -----------------------------------------------
def _pair_official_sum(pair, official_ranks: dict) -> float:
    return sum((official_ranks.get(pid) or 0) for pid in pair)


def _pair_official_sum_safe(pair, official_ranks: dict) -> tuple:
    known = [official_ranks.get(pid) for pid in pair]
    is_compleet = all(v is not None for v in known)
    total = sum((v or 0) for v in known)
    return total, is_compleet


def _pair_padelstat_sum(pair, padelstat_ratings: dict) -> float:
    return sum((padelstat_ratings.get(pid) or 0) for pid in pair)


def _rank_pairs_with_padelstat_tiebreak(
    pairs: list, official_ranks: dict, padelstat_ratings: dict,
) -> list:
    def sort_key(pair):
        official_sum = _pair_official_sum(pair, official_ranks)
        padelstat_sum = _pair_padelstat_sum(pair, padelstat_ratings)
        return (official_sum, padelstat_sum)
    return sorted(pairs, key=sort_key, reverse=True)


def _rotation_has_missing_official_rank(duo_a, duo_b, official_ranks: dict) -> bool:
    _, complete_a = _pair_official_sum_safe(duo_a, official_ranks)
    _, complete_b = _pair_official_sum_safe(duo_b, official_ranks)
    return not (complete_a and complete_b)


def _order_rotations_with_tiebreak(
    rotation_structure: list, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
    ordered_pairs = []
    rotation_results = []
    all_valid = True
    for rotation in rotation_structure:
        if len(rotation) < 2:
            ordered_pairs.extend(rotation)
            rotation_results.append({"total_points": None, "valid": True, "reason": "onvolledige rotatie"})
            continue
        duo_a, duo_b = rotation[0], rotation[1]
        ranked = _rank_pairs_with_padelstat_tiebreak([duo_a, duo_b], official_ranks, padelstat_ratings)
        ordered_pairs.extend(ranked)
        total_points = _pair_official_sum(duo_a, official_ranks) + _pair_official_sum(duo_b, official_ranks)
        valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
        if rules is not None:
            lo, hi = rules["punten_min"], rules["punten_max"]
            if total_points < lo:
                valid, reason = False, f"{total_points:.0f} < min {lo}"
            elif total_points > hi:
                valid, reason = False, f"{total_points:.0f} > max {hi}"
            else:
                valid, reason = True, f"{total_points:.0f} punten (toegelaten: {lo}-{hi})"
        rotation_results.append({"total_points": total_points, "valid": valid, "reason": reason})
        if not valid:
            all_valid = False
    return {"ordered_pairs": ordered_pairs, "rotations": rotation_results, "all_valid": all_valid}


def _build_opponent_boards_and_points(
    rotation_structure: list, name_by_id: dict, rank_by_id: dict, padelstat_by_id: dict,
) -> list:
    ordered = _order_rotations_with_tiebreak(rotation_structure, rank_by_id, padelstat_by_id, rules=None)
    boards = []
    for pair in ordered["ordered_pairs"]:
        p1, p2 = tuple(pair)
        boards.append({"opponent_pair": [
            {"name": name_by_id.get(p1, p1), "user_id": p1,
             "ranking": (f"P{int(rank_by_id[p1])}" if rank_by_id.get(p1) is not None else None)},
            {"name": name_by_id.get(p2, p2), "user_id": p2,
             "ranking": (f"P{int(rank_by_id[p2])}" if rank_by_id.get(p2) is not None else None)},
        ]})
    return boards


def _generate_theoretical_opponent_boards_with_repeats(
    chosen_opp_players: list, opponent_max_per_player: dict, opponent_official_ranks: dict,
    opponent_padelstat_ratings: dict, max_variants: int,
) -> tuple:
    ids = [str(p["user_id"]) for p in chosen_opp_players]
    name_by_id = {str(p["user_id"]): p.get("name", str(p["user_id"])) for p in chosen_opp_players}
    structures, truncated = _enumerate_rotation_aware_pairings(ids, opponent_max_per_player)
    total_theoretical = len(structures)
    all_boards = []
    for structure in structures[:max_variants]:
        boards = _build_opponent_boards_and_points(structure, name_by_id, opponent_official_ranks, opponent_padelstat_ratings)
        all_boards.append(boards)
    meta = {
        "total_theoretical": total_theoretical,
        "truncated": truncated or total_theoretical > len(all_boards),
        "players_used": len(ids),
    }
    return all_boards, meta


def _historical_opponent_boards_list(bundle: dict) -> list:
    out = []
    for fx_bundle in bundle.get("previous_fixtures", []) or []:
        boards = fx_bundle.get("boards") or []
        fx = fx_bundle.get("fixture", {}) or {}
        if fx_bundle.get("error") or not boards:
            continue
        sorted_boards = sorted(boards, key=lambda b: b.get("board_position") or 0)
        label = fx.get("date_text") or "onbekende datum"
        out.append((label, sorted_boards))
    return out


def _opponent_lineup_key(boards: list):
    pairs = []
    for b in boards:
        uids = frozenset(str(p.get("user_id")) for p in (b.get("opponent_pair") or []) if p.get("user_id"))
        if len(uids) == 2:
            pairs.append(uids)
    if not pairs:
        return None
    return tuple(pairs)


def _collect_unique_opponent_lineups(historical_boards_with_labels: list, theoretical_boards: list) -> dict:
    unique: dict = {}
    for label, boards in historical_boards_with_labels:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        entry = unique.setdefault(key, {"boards": boards, "is_historical": False, "historical_labels": []})
        entry["is_historical"] = True
        entry["historical_labels"].append(label)
        entry["historical_count"] = entry.get("historical_count", 0) + 1
    for boards in theoretical_boards:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        if key not in unique:
            unique[key] = {
                "boards": boards, "is_historical": False,
                "historical_labels": [], "historical_count": 0,
            }
    return unique


# -----------------------------------------------
# Best/worst-case variant-enumeratie
# -----------------------------------------------
def _rotation_order_variants(
    duo_a, duo_b, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
    """PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21: zie de
    oorspronkelijke docstring in page_lineup_lab.py voor de volledige
    root-cause-analyse - functioneel ONGEWIJZIGD."""
    sum_a, complete_a = _pair_official_sum_safe(duo_a, official_ranks)
    sum_b, complete_b = _pair_official_sum_safe(duo_b, official_ranks)
    total_points = sum_a + sum_b
    rank_data_incomplete = not (complete_a and complete_b)
    valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
    if rules is not None:
        lo, hi = rules["punten_min"], rules["punten_max"]
        if total_points < lo:
            valid, reason = False, f"{total_points:.0f} < min {lo}"
        elif total_points > hi:
            valid, reason = False, f"{total_points:.0f} > max {hi}"
        else:
            valid, reason = True, f"{total_points:.0f} punten (toegelaten: {lo}-{hi})"
    ranked = _rank_pairs_with_padelstat_tiebreak([duo_a, duo_b], official_ranks, padelstat_ratings)
    first_guess, second_guess = ranked[0], ranked[1]
    punten_txt = f"officieel {sum_a:.0f} vs {sum_b:.0f} punten"
    if rank_data_incomplete:
        onvolledig_txt = (
            f"{punten_txt} - ONVOLLEDIG officieel klassement (min. 1 speler ontbreekt): "
            "welk duo echt sterkst is, kan NIET betrouwbaar bepaald worden"
        )
        variants = [
            {
                "ordered_pairs": [first_guess, second_guess],
                "is_regulation_compliant": None,
                "rank_data_incomplete": True,
                "swap_label": onvolledig_txt + " - vermoedelijke volgorde o.b.v. padelstat, NIET bevestigd",
                "total_points": total_points, "valid": valid, "reason": reason,
            },
            {
                "ordered_pairs": [second_guess, first_guess],
                "is_regulation_compliant": None,
                "rank_data_incomplete": True,
                "swap_label": onvolledig_txt + " - omgekeerde volgorde, EVENZEER niet bevestigd",
                "total_points": total_points, "valid": valid, "reason": reason,
            },
        ]
        return {"variants": variants}
    is_tie = (sum_a == sum_b)
    compliant_first, compliant_second = first_guess, second_guess
    first_label = (
        f"gelijke officiele sterkte ({punten_txt}) - aanbevolen o.b.v. padelstat" if is_tie
        else f"{punten_txt} - sterkste eerst (art. 6.6)"
    )
    variants = [{
        "ordered_pairs": [compliant_first, compliant_second],
        "is_regulation_compliant": True,
        "rank_data_incomplete": False,
        "swap_label": first_label,
        "total_points": total_points, "valid": valid, "reason": reason,
    }]
    if is_tie:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": True,
            "rank_data_incomplete": False,
            "swap_label": f"gelijke officiele sterkte ({punten_txt}) - alternatieve, even geldige keuze",
            "total_points": total_points, "valid": valid, "reason": reason,
        })
    else:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": False,
            "rank_data_incomplete": False,
            "swap_label": (
                f"NIET reglementair ({punten_txt}, omgedraaid): het sterkere duo moet "
                "normaliter eerst spelen (art. 6.6)"
            ),
            "total_points": total_points, "valid": valid, "reason": reason,
        })
    return {"variants": variants}


def _enumerate_own_variant_combinations(
    rotation_structure: list, official_ranks: dict, padelstat_ratings: dict,
    rules=None, include_non_compliant: bool = False,
) -> list:
    per_rotation_variant_lists = []
    for rotation in rotation_structure:
        if len(rotation) < 2:
            per_rotation_variant_lists.append([{
                "ordered_pairs": list(rotation), "is_regulation_compliant": True,
                "swap_label": "", "total_points": None, "valid": True, "reason": "onvolledige rotatie",
                "rank_data_incomplete": False,
            }])
            continue
        duo_a, duo_b = rotation[0], rotation[1]
        result = _rotation_order_variants(duo_a, duo_b, official_ranks, padelstat_ratings, rules=rules)
        variants = result["variants"]
        if not include_non_compliant:
            variants = [v for v in variants if v["is_regulation_compliant"] is not False]
        per_rotation_variant_lists.append(variants)
    combinations = []
    for combo in itertools.product(*per_rotation_variant_lists):
        ordered_pairs = []
        rotations_info = []
        fully_compliant = True
        any_rank_data_incomplete = False
        for variant in combo:
            ordered_pairs.extend(variant["ordered_pairs"])
            rotations_info.append({
                "total_points": variant["total_points"], "valid": variant["valid"],
                "reason": variant["reason"], "swap_label": variant["swap_label"],
                "is_regulation_compliant": variant["is_regulation_compliant"],
                "rank_data_incomplete": variant.get("rank_data_incomplete", False),
            })
            if variant["is_regulation_compliant"] is False:
                fully_compliant = False
            if variant.get("rank_data_incomplete"):
                any_rank_data_incomplete = True
        combinations.append({
            "ordered_pairs": ordered_pairs, "rotations": rotations_info,
            "fully_compliant": fully_compliant,
            "rank_data_incomplete": any_rank_data_incomplete,
        })
    return combinations


def _compute_matchup(
    own_ordered_pairs: list, opp_boards: list,
    synergy_fn, player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
) -> dict:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: berekent nu ook
    "point_probs" (exacte 2/1/0-puntenkans, zie
    _match_outcome_point_probabilities()) en "n_missing_win_probs" naast de
    bestaande, ONGEWIJZIGDE velden (assignment/expected_boards_won/
    total_score). De volgorde en inhoud van 'assignment' is exact hetzelfde
    als voorheen - enkel deze 2 nieuwe top-level velden zijn toegevoegd."""
    assignment = []
    expected_boards_won = 0.0
    total_score = 0.0
    win_probs_for_points = []
    n = min(len(own_ordered_pairs), len(opp_boards))
    for i in range(n):
        p1, p2 = tuple(own_ordered_pairs[i])
        syn = synergy_fn(p1, p2)
        board = opp_boards[i]
        opp_pair = board.get("opponent_pair", []) or []
        our_eff = [
            ll.effective_simulation_rating(p1, player_ratings, official_ranks_strict),
            ll.effective_simulation_rating(p2, player_ratings, official_ranks_strict),
        ]
        their_eff = [
            ll.effective_simulation_rating(
                p.get("user_id"), opponent_ratings,
                {p.get("user_id"): ll.parse_ranking(p.get("ranking"))},
            )
            for p in opp_pair
        ]
        our_eff_known = [v for v in our_eff if v is not None]
        their_eff_known = [v for v in their_eff if v is not None]
        our_avg = (sum(our_eff_known) / len(our_eff_known)) if our_eff_known else None
        their_avg = (sum(their_eff_known) / len(their_eff_known)) if their_eff_known else None
        edge = ll.matchup_edge(our_eff, their_eff)
        win_prob = ll.estimate_win_probability(our_avg, their_avg)
        win_probs_for_points.append(win_prob)
        if win_prob is not None:
            expected_boards_won += win_prob
        total_score += syn + edge
        assignment.append({
            "our_pair": (p1, p2),
            "synergy": round(syn, 3),
            "edge": round(edge, 3),
            "win_probability": round(win_prob, 3) if win_prob is not None else None,
            "risk_note": ll.risk_note_for_probability(win_prob),
            "our_effective_rating": round(our_avg, 1) if our_avg is not None else None,
            "their_effective_rating": round(their_avg, 1) if their_avg is not None else None,
            "opponent_board": board,
        })
    point_probs = _match_outcome_point_probabilities(win_probs_for_points)
    return {
        "assignment": assignment,
        "expected_boards_won": round(expected_boards_won, 2),
        "total_score": round(total_score, 3),
        "point_probs": point_probs,
        "n_missing_win_probs": _n_missing_win_probs(win_probs_for_points),
    }


def _expand_tied_orderings(
    results: list, official_ranks_strict: dict, padelstat_ratings: dict,
    tournament_rules_dict, excluded_pairs: set,
    opponent_boards=None, synergy_fn=None, player_ratings: dict = None,
    opponent_ratings: dict = None,
) -> tuple:
    """PADEL_ANALYSIS_ROTATION_TIE_VARIANTS_2026-09-25: zie de
    oorspronkelijke docstring in page_lineup_lab.py voor de volledige
    root-cause-analyse - functioneel ONGEWIJZIGD."""
    expanded = []
    seen_keys = set()
    for cand in results:
        pairs = list(cand["ordered_pairs"])
        n_rot = -(-len(pairs) // 2)
        variant_choices = []
        for r in range(n_rot):
            chunk = pairs[r * 2: r * 2 + 2]
            if len(chunk) < 2:
                variant_choices.append([tuple(chunk)])
                continue
            duo_a, duo_b = chunk[0], chunk[1]
            vr = _rotation_order_variants(duo_a, duo_b, official_ranks_strict, padelstat_ratings, rules=tournament_rules_dict)
            opts = [tuple(v["ordered_pairs"]) for v in vr["variants"] if v["is_regulation_compliant"] is not False]
            variant_choices.append(opts or [(duo_a, duo_b)])
        for combo in itertools.product(*variant_choices):
            new_pairs = [p for chunk in combo for p in chunk]
            if any(p in excluded_pairs for p in new_pairs):
                continue
            key = tuple(frozenset(p) for p in new_pairs)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if new_pairs == pairs:
                expanded.append(cand)
                continue
            if opponent_boards and player_ratings is not None and synergy_fn is not None:
                computed = _compute_matchup(
                    new_pairs, opponent_boards, synergy_fn, player_ratings,
                    official_ranks_strict, opponent_ratings or {},
                )
                expanded.append({
                    "expected_boards_won": computed["expected_boards_won"],
                    "score": computed["total_score"],
                    "ordered_pairs": new_pairs,
                    "assignment": computed["assignment"],
                    "rotations": cand.get("rotations"),
                })
            else:
                rotation_eval = ll.filter_and_order_lineup_by_rotations(
                    [frozenset(p) for p in new_pairs], official_ranks_strict, rules=tournament_rules_dict,
                )
                if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
                    continue
                expanded.append({
                    "expected_boards_won": None,
                    "score": cand["score"],
                    "ordered_pairs": rotation_eval["ordered_pairs"],
                    "assignment": None,
                    "rotations": rotation_eval["rotations"],
                })
    return expanded


def _rotation_boards_for(opponent_boards, rotation_number: int):
    """PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29: geeft de tegenstander-borden voor DEZE rotatie
    terug (precies MATCHES_PER_ROTATION stuks), of None als die niet gekend
    zijn. Accepteert zowel enkel de borden van deze rotatie als de borden van
    de volledige ontmoeting (dan wordt het juiste stuk eruit gesneden)."""
    if not opponent_boards:
        return None
    boards = list(opponent_boards)
    if len(boards) == MATCHES_PER_ROTATION:
        return boards
    offset = (int(rotation_number) - 1) * MATCHES_PER_ROTATION
    stuk = boards[offset: offset + MATCHES_PER_ROTATION]
    return stuk if len(stuk) == MATCHES_PER_ROTATION else None


def _generate_rotation_candidates(
    available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
    opponent_boards=None, player_ratings=None, opponent_ratings=None,
    max_results=10, tournament_rules_dict=None,
    rotation_number: int = 1, player_budget: dict = None,
):
    """PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29 (op verzoek van Kim): kiest per rotatie EXACT
    MATCHES_PER_ROTATION (=2) koppels uit de beschikbare spelers.

    VOORHEEN deelde deze functie ALLE geselecteerde spelers in koppels in
    (perfect matching over de hele selectie): bij 6 spelers dus 3 koppels,
    terwijl een rotatie er maar 2 heeft - en een oneven aantal spelers
    blokkeerde de planner volledig.

    NU: elke combinatie van 4 spelers x elke manier om die in 2 koppels te
    verdelen (3 per combinatie) is een kandidaat, zolang:
      - geen van beide koppels al in een eerdere, bevestigde rotatie speelde
        (excluded_pairs - reglement: een koppel speelt maar 1 keer samen);
      - elke speler nog 'budget' heeft (player_budget: resterend aantal
        matchen per speler, uit 'max. matchen per speler' min wat al
        bevestigd is; None = geen beperking);
      - de puntengrens van de gekozen afdeling gerespecteerd wordt.
    De bordvolgorde (art. 6.6, sterkste duo op match 1, padelstat als
    tiebreak, beide volgordes bij gelijkspel of onvolledig klassement) komt
    uit _rotation_order_variants() - dezelfde regel als in de rest van de
    app. Zijn de tegenstanders van deze rotatie gekend, dan wordt
    gerangschikt op verwacht aantal gewonnen matchen; anders op synergie.

    Geeft (kandidaten[:max_results], totaal_mogelijk, diagnostiek) terug -
    hetzelfde contract als voorheen, zodat de UI ongewijzigd blijft."""
    per_rot = MATCHES_PER_ROTATION
    need = per_rot * 2
    eligible = sorted({
        str(p) for p in available_ids
        if player_budget is None or (player_budget.get(str(p), 0) or 0) > 0
    })
    if len(eligible) < need:
        return [], 0, None
    rot_boards = _rotation_boards_for(opponent_boards, rotation_number)
    padelstat = player_ratings or {}
    excluded = {frozenset(str(x) for x in p) for p in (excluded_pairs or set())}

    results = []
    seen = set()
    total_possible = 0
    excluded_by_rules = 0
    rotation_points_seen = []
    for combo in itertools.combinations(eligible, need):
        for matching in _all_perfect_matchings_generic(list(combo)):
            if any(pair in excluded for pair in matching):
                continue
            total_possible += 1
            duo_a, duo_b = matching[0], matching[1]
            variants = _rotation_order_variants(
                duo_a, duo_b, official_ranks_strict, padelstat, rules=tournament_rules_dict,
            )["variants"]
            variants = [v for v in variants if v["is_regulation_compliant"] is not False]
            if not variants:
                continue
            if variants[0].get("total_points") is not None:
                rotation_points_seen.append(variants[0]["total_points"])
            if tournament_rules_dict is not None and not variants[0]["valid"]:
                excluded_by_rules += 1
                continue
            for v in variants:
                pairs = [frozenset(p) for p in v["ordered_pairs"]]
                key = tuple(pairs)
                if key in seen:
                    continue
                seen.add(key)
                rot_info = [{
                    "total_points": v["total_points"], "valid": v["valid"],
                    "reason": v["reason"], "swap_label": v.get("swap_label", ""),
                    "is_regulation_compliant": v["is_regulation_compliant"],
                    "rank_data_incomplete": v.get("rank_data_incomplete", False),
                }]
                if rot_boards and player_ratings is not None:
                    computed = _compute_matchup(
                        pairs, rot_boards, synergy_fn, player_ratings,
                        official_ranks_strict, opponent_ratings or {},
                    )
                    results.append({
                        "expected_boards_won": computed["expected_boards_won"],
                        "score": computed["total_score"],
                        "ordered_pairs": pairs,
                        "assignment": computed["assignment"],
                        "rotations": rot_info,
                        "point_probs": computed.get("point_probs"),
                    })
                else:
                    score = sum(synergy_fn(*tuple(p)) for p in pairs)
                    results.append({
                        "expected_boards_won": None, "score": round(score, 3),
                        "ordered_pairs": pairs, "assignment": None,
                        "rotations": rot_info, "point_probs": None,
                    })
    results.sort(key=lambda r: (
        -(r["expected_boards_won"] if r["expected_boards_won"] is not None else -1),
        -r["score"],
    ))
    diagnostics = {
        "candidates_total": total_possible,
        "candidates_excluded_by_rules": excluded_by_rules,
        "rotation_points_seen": rotation_points_seen,
    }
    return results[:max_results], total_possible, diagnostics


def _lineup_options_for_ai(candidates: list, name_lookup: dict) -> list:
    out = []
    for cand in candidates:
        assignment = []
        if cand["assignment"]:
            for a in cand["assignment"]:
                assignment.append({
                    "our_pair": tuple(a["our_pair"]), "synergy": a.get("synergy", 0.0),
                    "edge": a.get("edge", 0.0), "opponent_board": a.get("opponent_board", {}),
                })
        else:
            for pair in cand["ordered_pairs"]:
                p1, p2 = tuple(pair)
                assignment.append({"our_pair": (p1, p2), "synergy": 0.0, "edge": 0.0, "opponent_board": {"opponent_pair": []}})
        out.append({"total_score": cand["score"], "assignment": assignment})
    return out


def _render_rotation_points_caption(rotations: list) -> None:
    if not rotations:
        return
    for i, rot in enumerate(rotations, start=1):
        if rot.get("total_points") is None:
            continue
        if rot.get("rank_data_incomplete"):
            st.caption(f"Rotatie {i}: {rot.get('reason', '')} - minstens 1 speler heeft nog geen bekend officieel klassement, deze volgorde is NIET betrouwbaar geverifieerd.")
            continue
        icon = "OK" if rot.get("valid", True) else "FOUT"
        st.caption(f"{icon} Rotatie {i}: {rot.get('reason', '')}")


def _render_assignment_with_outcome(assignment: list, name_lookup_global: dict) -> None:
    for a in assignment:
        p1, p2 = a["our_pair"]
        opp_pair = a["opponent_board"]["opponent_pair"]
        opp_names = " / ".join(p.get("name", "?") for p in opp_pair)
        wp = a.get("win_probability")
        risk = a.get("risk_note", "")
        our_r = a.get("our_effective_rating")
        their_r = a.get("their_effective_rating")
        if wp is not None:
            wp_txt = f"**{int(round(wp * 100))}% winkans** ({risk})"
        else:
            wp_txt = "winkans onbekend (onvoldoende rating-data)"
        rating_txt = ""
        if our_r is not None and their_r is not None:
            rating_txt = f" - inschatting {our_r:.0f} vs {their_r:.0f}"
        st.write(
            f"**{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
            f"(synergie {a['synergy']}) - vs **{opp_names}**: {wp_txt}{rating_txt}"
        )


@st.fragment
def _render_rotation_planner(
    available_ids, synergy_fn, official_ranks_strict, name_lookup_global, opp,
    opponent_boards=None, player_ratings=None, opponent_ratings=None,
    report_for_ai=None, tournament_rules_dict=None, rules_label=None,
    bundle=None, total_boards=None, max_per_player=None,
):
    """PADEL_ANALYSIS_FRAGMENT_ISOLATION_2026-09-26: @st.fragment isoleert
    deze functie van een volledige pagina-rerun. Zie de oorspronkelijke
    docstring in page_lineup_lab.py voor de volledige toelichting bij elke
    eerdere fix - functioneel ONGEWIJZIGD."""
    st.markdown('<div class="section-header">Rotatieplanner</div>', unsafe_allow_html=True)
    regel_tekst = f" (volgens {rules_label})" if rules_label else ""
    st.caption(
        "Alle mogelijke koppelverdelingen voor de eerstvolgende rotatie, gerangschikt op VERWACHT "
        "AANTAL GEWONNEN MATCHEN (niet op een abstract scoregetal). Klik aan wie/welke combinatie "
        "effectief speelde om door te gaan naar de volgende rotatie. Het duo met de hoogste SOM van "
        f"de 2 OFFICIELE klassementen staat steeds op Match 1{regel_tekst} - de winkans-simulatie "
        "gebruikt daarnaast de padelstats.be playing strength waar bekend."
    )
    st.caption(_WIN_PROB_DISCLAIMER)
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)
    # PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29: per rotatie 2 koppels = 4 spelers nodig; een oneven
    # aantal geselecteerde spelers is geen probleem meer.
    if len(available_ids) < 2 * MATCHES_PER_ROTATION:
        st.info(f"Selecteer minstens {2 * MATCHES_PER_ROTATION} spelers om de rotatieplanner te gebruiken.")
        return
    ploeg_id = opp["ploeg_id"]
    locked_key = f"rot_locked_v3_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if locked_key not in st.session_state:
        st.session_state[locked_key] = []
    locked_rotations = st.session_state[locked_key]
    opp_locked_key = f"rot_locked_opp_v1_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if opp_locked_key not in st.session_state:
        st.session_state[opp_locked_key] = []
    locked_opponents = st.session_state[opp_locked_key]
    for rot_idx, pairs in enumerate(locked_rotations, start=1):
        st.markdown(f"**Rotatie {rot_idx} (bevestigd):**")
        opp_voor_rotatie = (
            locked_opponents[rot_idx - 1] if rot_idx - 1 < len(locked_opponents) else None
        )
        for match_idx, pair in enumerate(pairs, start=1):
            p1, p2 = tuple(pair)
            ons = f"{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}"
            tegen = ""
            if opp_voor_rotatie and match_idx - 1 < len(opp_voor_rotatie):
                namen = [x.get("name", "?") for x in opp_voor_rotatie[match_idx - 1]]
                if namen:
                    tegen = f"  -  tegen **{' / '.join(namen)}**"
            st.write(f"Match {match_idx}: {ons}{tegen}")
        if st.button(f"Rotatie {rot_idx} wijzigen", key=f"rot_edit_v3_{ploeg_id}_{rot_idx}"):
            st.session_state[locked_key] = locked_rotations[: rot_idx - 1]
            st.session_state[opp_locked_key] = locked_opponents[: rot_idx - 1]
            st.rerun(scope="fragment")
        st.markdown("---")
    excluded_pairs = {p for rot in locked_rotations for p in rot}
    next_rotation_num = len(locked_rotations) + 1
    # PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29: resterend aantal matchen per speler = 'max. matchen
    # per speler' (instelling hierboven op de pagina) min wat al bevestigd is.
    player_budget = None
    if max_per_player:
        gebruikt = {}
        for rot in locked_rotations:
            for pair in rot:
                for pid in pair:
                    gebruikt[str(pid)] = gebruikt.get(str(pid), 0) + 1
        player_budget = {
            str(pid): int(max_per_player.get(pid, 0) or 0) - gebruikt.get(str(pid), 0)
            for pid in available_ids
        }
        opgebruikt = [
            name_lookup_global.get(pid, pid) for pid in available_ids
            if player_budget.get(str(pid), 0) <= 0
        ]
        if opgebruikt and locked_rotations:
            st.caption(
                "Niet meer beschikbaar in deze rotatie (max. aantal matchen bereikt): "
                + ", ".join(opgebruikt) + "."
            )
    borden_bevestigd = sum(len(rot) for rot in locked_rotations)
    if total_boards is not None and borden_bevestigd >= int(total_boards):
        st.success(
            f"Alle {int(total_boards)} wedstrijden van deze ontmoeting zijn ingedeeld "
            f"over {len(locked_rotations)} rotatie(s)."
        )
        return
    unique_opp_players = (bundle or {}).get("unique_players") or []
    rotation_opponent_boards = None
    if unique_opp_players:
        with st.expander(
            f"Wie stelt de tegenstander op in rotatie {next_rotation_num}?",
            expanded=True,
        ):
            st.caption(
                "Vul hier in wie de tegenstander in DEZE rotatie opstelt (of al opstelde). "
                "De winkansen van de combinaties hieronder worden daar meteen op herrekend. "
                "Laat je dit leeg, dan wordt enkel op eigen synergie gerangschikt (geen "
                "matchup-inschatting tegen een specifieke tegenstander)."
            )
            def _opp_pick_label(speler: dict) -> str:
                naam = speler.get("name", "?")
                uid = str(speler.get("user_id") or "")
                officieel = _cached_official_rank(uid) if uid else None
                padelstat = _cached_own_player_rating(uid) if uid else None
                delen = [f"P{int(officieel)}" if officieel is not None else "P?"]
                if padelstat is not None:
                    delen.append(f"ps {int(padelstat)}")
                return f"{naam} ({' \u00b7 '.join(delen)})"
            paar_frequentie = {}
            for fx_b in (bundle or {}).get("previous_fixtures", []) or []:
                for b in fx_b.get("boards", []) or []:
                    p = b.get("opponent_pair") or []
                    if len(p) == 2:
                        k = frozenset(str(x.get("user_id")) for x in p if x.get("user_id"))
                        if len(k) == 2:
                            paar_frequentie[k] = paar_frequentie.get(k, 0) + 1
            def _pair_label(p1: dict, p2: dict) -> str:
                uid1, uid2 = str(p1.get("user_id")), str(p2.get("user_id"))
                n = paar_frequentie.get(frozenset({uid1, uid2}), 0)
                badge = f"({n}x) " if n else ""
                return f"{badge}{_opp_pick_label(p1)} / {_opp_pick_label(p2)}"
            alle_paren = list(itertools.combinations(unique_opp_players, 2))
            alle_paren.sort(
                key=lambda pr: paar_frequentie.get(
                    frozenset({str(pr[0].get("user_id")), str(pr[1].get("user_id"))}), 0,
                ),
                reverse=True,
            )
            geen_keuze = "- Kies een koppel -"
            paar_labels = [geen_keuze] + [_pair_label(p1, p2) for p1, p2 in alle_paren]
            paar_map = {_pair_label(p1, p2): (p1, p2) for p1, p2 in alle_paren}
            voorstel_idx = [0, 0]
            if opponent_boards:
                offset = (next_rotation_num - 1) * 2
                for i in range(2):
                    idx = offset + i
                    if idx < len(opponent_boards):
                        scenario_pair = (opponent_boards[idx].get("opponent_pair") or [])
                        if len(scenario_pair) == 2:
                            scenario_key = frozenset(str(x.get("user_id")) for x in scenario_pair)
                            for j, (p1, p2) in enumerate(alle_paren, start=1):
                                if frozenset({str(p1.get("user_id")), str(p2.get("user_id"))}) == scenario_key:
                                    voorstel_idx[i] = j
                                    break
            def _opp_pair_uids(paar):
                return {str(p.get("user_id")) for p in paar} if paar else set()
            gekozen_paren = [None, None]
            col_o1, col_o2 = st.columns(2)
            cols = (col_o1, col_o2)
            for i in range(2):
                andere = 1 - i
                uitgesloten_uids = _opp_pair_uids(gekozen_paren[andere])
                if uitgesloten_uids:
                    beschikbare_labels = [geen_keuze] + [
                        _pair_label(p1, p2) for p1, p2 in alle_paren
                        if not ({str(p1.get("user_id")), str(p2.get("user_id"))} & uitgesloten_uids)
                    ]
                else:
                    beschikbare_labels = paar_labels
                key_i = f"rot_opp_pick_pair_{ploeg_id}_{next_rotation_num}_{i}"
                if key_i in st.session_state and st.session_state[key_i] not in beschikbare_labels:
                    st.session_state[key_i] = geen_keuze
                with cols[i]:
                    keuze_lbl = st.selectbox(
                        f"Tegenstander match {i + 1}", beschikbare_labels,
                        index=min(voorstel_idx[i], len(beschikbare_labels) - 1),
                        key=key_i,
                    )
                    if keuze_lbl != geen_keuze:
                        gekozen_paren[i] = paar_map[keuze_lbl]
            if gekozen_paren[0] and gekozen_paren[1]:
                rotation_opponent_boards = [
                    {"opponent_pair": list(gekozen_paren[0])},
                    {"opponent_pair": list(gekozen_paren[1])},
                ]
                st.caption("Winkansen hieronder zijn berekend tegen deze tegenstander-opstelling.")
            elif gekozen_paren[0] or gekozen_paren[1]:
                st.caption("Kies ook een koppel voor de andere match om de winkansen te herberekenen.")
    effective_opponent_boards = rotation_opponent_boards or opponent_boards
    rot_cache_key = f"rot_candidates_v2_{ploeg_id}_{next_rotation_num}"
    rot_sig_key = f"rot_candidates_sig_v2_{ploeg_id}_{next_rotation_num}"
    rot_signature = (
        tuple(sorted(available_ids)),
        tuple(sorted(tuple(sorted(p)) for p in excluded_pairs)) if excluded_pairs else (),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(player_ratings.items())) if player_ratings else (),
        tuple(sorted(opponent_ratings.items())) if opponent_ratings else (),
        tuple(
            tuple(sorted(str(p.get("user_id")) for p in b.get("opponent_pair", [])))
            for b in (effective_opponent_boards or [])
        ),
        tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
        tuple(sorted(player_budget.items())) if player_budget else None,
    )
    if st.session_state.get(rot_sig_key) != rot_signature:
        st.session_state[rot_cache_key] = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
            opponent_boards=effective_opponent_boards, player_ratings=player_ratings,
            opponent_ratings=opponent_ratings, max_results=15,
            tournament_rules_dict=tournament_rules_dict,
            rotation_number=next_rotation_num, player_budget=player_budget,
        )
        st.session_state[rot_sig_key] = rot_signature
    candidates, total_possible, rotation_diagnostics = st.session_state[rot_cache_key]
    if not candidates:
        if total_possible == 0:
            st.info("Geen geldige koppelverdeling meer mogelijk.")
        elif tournament_rules_dict is not None:
            st.warning(
                f"Geen enkele van de {total_possible} mogelijke koppelverdelingen valt binnen de "
                "toegelaten puntengrens per rotatie voor de gekozen afdeling - of alle zijn al "
                "gebruikt. Overweeg een andere afdeling of spelersselectie."
            )
            diag_msg = _format_points_bounds_diagnostic(tournament_rules_dict, rotation_diagnostics)
            if diag_msg:
                st.caption(diag_msg)
        else:
            st.warning(f"Alle {total_possible} mogelijke koppelverdelingen zijn al gebruikt in eerdere rotaties.")
        return
    st.markdown(f"**Rotatie {next_rotation_num} - kies de effectieve/geplande combinatie:**")
    if tournament_rules_dict is not None:
        st.caption(f"{len(candidates)} van {total_possible} combinaties voldoen aan de puntengrens per rotatie.")
    option_labels = []
    for i, cand in enumerate(candidates):
        parts = []
        for match_idx, pair in enumerate(cand["ordered_pairs"], start=1):
            p1, p2 = tuple(pair)
            parts.append(f"M{match_idx}: {name_lookup_global.get(p1,p1)}/{name_lookup_global.get(p2,p2)}")
        prefix = "* " if i == 0 else ""
        ebw = cand.get("expected_boards_won")
        ebw_txt = f" (verwacht {ebw:.2f} gewonnen matchen)" if ebw is not None else f" (score {cand['score']:.3f})"
        option_labels.append(f"{prefix}{' | '.join(parts)}{ebw_txt}")
    chosen_idx = st.radio(
        "Combinaties", list(range(len(candidates))), format_func=lambda i: option_labels[i],
        key=f"rot_choice_v3_{ploeg_id}_{next_rotation_num}", label_visibility="collapsed",
    )
    chosen = candidates[chosen_idx]
    _render_rotation_points_caption(chosen.get("rotations"))
    if chosen["assignment"]:
        with st.expander("Detail van de gekozen combinatie (winkans per match)", expanded=True):
            _render_assignment_with_outcome(chosen["assignment"], name_lookup_global)
    ai_key = f"rot_ai_v3_{ploeg_id}_{next_rotation_num}"
    if taa is not None and report_for_ai is not None:
        if st.button("AI-inzicht over deze combinaties", key=f"rot_ai_btn_v3_{ploeg_id}_{next_rotation_num}"):
            with st.spinner("AI analyseert de combinaties..."):
                try:
                    ai_options = _lineup_options_for_ai(candidates[:5], name_lookup_global)
                    st.session_state[ai_key] = taa.analyze_lineup_options(report_for_ai, ai_options, name_lookup_global)
                except Exception as exc:
                    st.session_state[ai_key] = f"Mislukt: {exc}"
        if st.session_state.get(ai_key):
            st.markdown(st.session_state[ai_key])
    if st.button(f"Bevestig rotatie {next_rotation_num}", key=f"rot_confirm_v3_{ploeg_id}_{next_rotation_num}", type="primary"):
        st.session_state[locked_key] = locked_rotations + [chosen["ordered_pairs"]]
        opp_pairs_voor_log = []
        if rotation_opponent_boards:
            opp_pairs_voor_log = [b.get("opponent_pair") or [] for b in rotation_opponent_boards]
        st.session_state[opp_locked_key] = locked_opponents + [opp_pairs_voor_log]
        st.rerun(scope="fragment")
