"""
lineup_rotation.py - Rotatieplanner: combinatoriek, bordvolgorde-regels
(art. 6.6 + padelstat-tiebreak), best/worst-case-variantenumeratie, en de
matchup-berekening per bord.

Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
Zie de oorspronkelijke, monolithische versie van page_lineup_lab.py voor de
volledige historische toelichting bij elke fix in deze functies - dit
bestand is functioneel ONGEWIJZIGD t.o.v. die vorige versie.
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
_WIN_PROB_DISCLAIMER = (
    "De winkans is een logistische schatting op het verschil in speelsterkte, "
    "gekalibreerd op 44 recent gespeelde dubbels (70% van de uitslagen juist voorspeld; "
    "Brier 0.195 tegenover 0.25 voor een muntstuk). Bij uitgesproken favorieten en "
    "underdogs is de schatting nog steeds aan de voorzichtige kant, en de steekproef is "
    "klein - richtinggevend signaal dus, geen garantie."
)


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
        take = min(2, remaining_boards)
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
    assignment = []
    expected_boards_won = 0.0
    total_score = 0.0
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
    return {
        "assignment": assignment,
        "expected_boards_won": round(expected_boards_won, 2),
        "total_score": round(total_score, 3),
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


def _generate_rotation_candidates(
    available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
    opponent_boards=None, player_ratings=None, opponent_ratings=None,
    max_results=10, tournament_rules_dict=None,
):
    n = len(available_ids)
    if n < 2 or n % 2 != 0:
        return [], 0, None
    total_possible = _count_perfect_matchings(n)
    top_n = min(max(total_possible, 1), _ROTATION_EXHAUSTIVE_LIMIT)
    required = {pid: 1 for pid in available_ids}
    results = []
    diagnostics = None
    if opponent_boards and player_ratings is not None:
        raw, truncated, diagnostics = ll.optimize_lineup_vs_scenario(
            available_ids, required, synergy_fn, opponent_boards, player_ratings,
            player_official_ranks=official_ranks_strict, opponent_ratings=opponent_ratings,
            top_n=top_n, candidate_pool=_ROTATION_EXHAUSTIVE_LIMIT,
            tournament_rules_dict=tournament_rules_dict,
        )
        for option in raw:
            pairs = [frozenset(a["our_pair"]) for a in option["assignment"]]
            if any(p in excluded_pairs for p in pairs):
                continue
            results.append({
                "expected_boards_won": option["expected_boards_won"],
                "score": option["total_score"],
                "ordered_pairs": pairs,
                "assignment": option["assignment"],
                "rotations": option.get("rotations"),
            })
    else:
        raw, truncated = ll.optimize_lineup(available_ids, required, synergy_fn, top_n=top_n)
        rotation_points_seen = []
        excluded_by_rules = 0
        for score, pairs in raw:
            pairs_fs = [frozenset(p) for p in pairs]
            if any(p in excluded_pairs for p in pairs_fs):
                continue
            rotation_eval = ll.filter_and_order_lineup_by_rotations(pairs_fs, official_ranks_strict, rules=tournament_rules_dict)
            for rot in rotation_eval["rotations"]:
                if rot.get("total_points") is not None:
                    rotation_points_seen.append(rot["total_points"])
            if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
                excluded_by_rules += 1
                continue
            results.append({
                "expected_boards_won": None, "score": score,
                "ordered_pairs": rotation_eval["ordered_pairs"], "assignment": None,
                "rotations": rotation_eval["rotations"],
            })
        diagnostics = {
            "candidates_total": len(raw),
            "candidates_excluded_by_rules": excluded_by_rules,
            "rotation_points_seen": rotation_points_seen,
        }
    padelstat_for_tiebreak = player_ratings or {}
    results = _expand_tied_orderings(
        results, official_ranks_strict, padelstat_for_tiebreak, tournament_rules_dict,
        excluded_pairs, opponent_boards=opponent_boards, synergy_fn=synergy_fn,
        player_ratings=player_ratings, opponent_ratings=opponent_ratings,
    )
    if len(results) > total_possible:
        total_possible = len(results)
    results.sort(key=lambda r: (-(r["expected_boards_won"] if r["expected_boards_won"] is not None else -1), -r["score"]))
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
    bundle=None, total_boards=None,
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
    if len(available_ids) < 2 or len(available_ids) % 2 != 0:
        st.info("Selecteer een even aantal spelers om de rotatieplanner te gebruiken.")
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
    rot_cache_key = f"rot_candidates_v1_{ploeg_id}_{next_rotation_num}"
    rot_sig_key = f"rot_candidates_sig_v1_{ploeg_id}_{next_rotation_num}"
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
    )
    if st.session_state.get(rot_sig_key) != rot_signature:
        st.session_state[rot_cache_key] = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
            opponent_boards=effective_opponent_boards, player_ratings=player_ratings,
            opponent_ratings=opponent_ratings, max_results=15,
            tournament_rules_dict=tournament_rules_dict,
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
