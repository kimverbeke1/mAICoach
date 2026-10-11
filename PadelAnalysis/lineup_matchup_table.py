"""
lineup_matchup_table.py - Opbouw en weergave van de volledige
"Opstelling-scenario's"-tabel: alle geldige matchups (eigen koppelverdeling
x tegenstander-opstelling), gegroepeerd, gesorteerd en met AI-doorvraag.
Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
--------------------------------------------------------------------------
HISTORIEK (korte samenvatting - de volledige toelichting per marker staat in de git-historiek van dit
bestand): SAVE_BUTTON_VISIBILITY_FIX_2026-09-27 (opslaan-knop vroeg in de resultaten), NO_NONCOMPLIANT_2026-09-29
(enkel reglementaire matchvolgordes), MATCHUPS_ALL_OWN_LINEUPS_2026-09-29 (elke eigen opstelling doorgerekend, per
groep een samenvatting + de beste _KEEP_PER_GROUP rijen), POINT_PROBABILITY_2026-09-30 (kans op 2/1/0 punten, gewogen
over de tegenstander-scenario's), DILUTED_GROUP_PROBS_2026-10-01 (diagnose bij identieke percentages),
OPPONENT_LINEUP_MODEL_2026-10-02 (gewichten uit opponent_lineup_model.py), SCENARIO_MATRIX_2026-10-03,
ROSTER_AND_GROUPS_2026-10-03 (roster-keuze, grote koppen), PAGE_RESTRUCTURE_2026-10-04 (opgesplitst in
render_opponent_scenario_setup() en render_matchup_overview()).
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_FILTERS_2026-10-10 (op verzoek van Kim: "bij alle matchups zou het wel handig zijn om te
kunnen filteren op spelers [...] op koppel. De toelichting in die tabel is niets waard [...] beter gewoon padelstat
van beide spelers tussen haakjes tonen")
--------------------------------------------------------------------------
1. Filters op onze spelers, ons koppel, tegenstander-spelers en tegenstander-koppel (op id's). Alle gekozen
   filters moeten kloppen: kies je 2 spelers, dan spelen ze allebei mee.
2. "Ons duo"/"Tegenstander" tonen per speler "Naam (ps 180)"; de kolom "Toelichting" is weg.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11 (op verzoek van Kim: "Ik zie nu net dat je bij de matchup niet alle
combinaties gemaakt hebt [...] Bvb Klaudia en Evy hebben in de 2de rotatie tegen Isis gespeeld tegen Gallach en
Serruys. bekijk dat grondig want dat moet opgelost worden")
--------------------------------------------------------------------------
Drie bevestigde oorzaken (zie matchup_universe.py voor de meting):
  A. de theoretische tegenstander-opstellingen werden afgekapt op de EERSTE 300 (op volgorde van speler-id's);
  B. ze werden opgebouwd met een vast aantal matchen per tegenstander-speler (afgeleid uit hun historiek, afgerond):
     wie op 0 uitkwam speelde in geen enkele opstelling mee, wie op 1 kwam kon nooit 2 matchen spelen;
  C. per eigen opstelling bleven enkel de beste 25 + de slechtste + de historische rijen over; filters en de tabel
     toonden dus enkel die.
Oplossing:
  1. render_opponent_scenario_setup() bepaalt ALLE rotatie-veilige tegenstander-opstellingen (matchup_universe.py),
     zonder vast aantal per speler. Het model (opponent_lineup_model.py) geeft elke opstelling een gewicht: onwaar-
     schijnlijke tellen nauwelijks mee. Voor de samenvattende groepen worden de meest waarschijnlijke doorgerekend
     (aantal afhankelijk van hoeveel eigen opstellingen er zijn), aangevuld zodat ELK mogelijk koppel in ELKE
     rotatie minstens 1x voorkomt. Een melding toont hoeveel er zijn, hoeveel er doorgerekend werden en welk
     aandeel van het gewicht dat dekt. Een effectief gespeelde opstelling wordt nooit weggelaten.
  2. Filters rekenen EXACT: zodra je een speler/koppel kiest, wordt elke eigen opstelling die aan je filter voldoet
     gekruist met elke tegenstander-opstelling die aan je filter voldoet (matchup_universe.search_exact), niet enkel
     over de bewaarde rijen. Is het product te groot, dan worden de meest waarschijnlijke tegenstander-opstellingen
     gehouden en staat dat er duidelijk bij. De keuzelijsten bevatten ALLE spelers en koppels (niet enkel wie in de
     bewaarde rijen zit).
  3. In "Details" van een groep filtert de tegenstander eveneens exact, voor precies die eigen opstelling.
  4. Elke matchup toont "Kans opstelling %": hoe waarschijnlijk het model de tegenstander-opstelling vindt.
  5. Zware tussenresultaten (universum, gewichten, voorstel, zoekopdrachten) zijn gecachet in st.session_state.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_FILTER_BOTH_ROTATIONS_2026-10-11 (op verzoek van Kim: "het filtersysteem leek niet direct te werken.
ook rekening houden dat dat dan voor beide rotaties moet zijn")
--------------------------------------------------------------------------
1. "Speelt TEGEN" geldt nu ook voor SPELERS (niet enkel koppels): onze gekozen speler(s)/koppel(s) moeten in een match
   tegen de gekozen tegenstander-speler(s)/koppel(s) spelen, in rotatie 1 OF in rotatie 2 (matchup_universe.faces_each_other).
   Het vinkje verschijnt zodra je aan onze kant EN aan hun kant iets kiest.
2. Traagheid: de schatting van het aantal eigen opstellingen (een opsomming die seconden kan duren) draaide bij elke
   herlading, dus ook bij elke filterkeuze; ze is nu gecachet. De exacte zoekopdracht toont een spinner.
"""
import heapq
import itertools
import streamlit as st
from dashboard_common import fb, taa
from lineup_scout import _opponent_official_ranks, _opponent_padelstat_ratings
try:
    import lineup_scenario_matrix as lsm  # PADEL_ANALYSIS_SCENARIO_MATRIX_2026-10-03
except Exception:  # noqa: BLE001  pragma: no cover
    lsm = None
try:
    import opponent_lineup_model as olm  # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02
except Exception:  # noqa: BLE001  pragma: no cover
    olm = None
from lineup_rotation import (
    _enumerate_rotation_aware_pairings, _enumerate_own_variant_combinations,
    _compute_matchup, _default_opponent_max_per_player,
    _historical_opponent_boards_list, _collect_unique_opponent_lineups,
    _opponent_lineup_weight, _aggregate_group_point_probabilities,  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
    _build_opponent_boards_and_points, _rank_pairs_with_padelstat_tiebreak, MATCHES_PER_ROTATION,
)
import matchup_universe as mu  # PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11
_MATCHUP_DISPLAY_DEFAULT_N = 15
# PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29
_MAX_COMPUTED_MATCHUPS = 100_000   # veiligheidsgrens op de rekenlus
_KEEP_PER_GROUP = 25               # bewaarde beste rijen per eigen opstelling
_GROUPS_DISPLAY_DEFAULT = 20       # standaard getoonde eigen opstellingen
_SAVE_MAX_MATCHUPS = 150           # Firestore-document < 1 MB
_MAX_TOTAL_MATCHUPS = _MAX_COMPUTED_MATCHUPS  # oude naam, voor compatibiliteit
# PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01: drempels voor de 2 diagnose-captions hieronder.
_DILUTION_MISSING_RATIO_THRESHOLD = 0.5   # >= 50% onbekende winkansen -> waarschuwing
_DILUTION_THEORETICAL_MIN_COUNT = 20       # 0 historisch + >= 20 theoretisch -> notitie
# PADEL_ANALYSIS_MATCHUP_FILTERS_2026-10-10: groepsdetails pas filterbaar vanaf dit aantal rijen.
_GROUP_DETAIL_FILTER_MIN_ROWS = 6
# PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11
_TARGET_MATCHUPS = 40_000          # streefgetal voor eigen opstellingen x doorgerekende tegenstander-opstellingen
_OPP_SUBSET_MIN = 300
_OPP_SUBSET_MAX = 2_500
_UNIVERSE_MAX_LINEUPS = 60_000     # meer opstellingen dan dit: gespreide steekproef (9+ tegenstander-spelers)
_SEARCH_MAX_COMPUTED = 25_000      # maximum aantal combinaties per exacte zoekopdracht
_SEARCH_TIME_BUDGET = 30.0         # seconden per exacte zoekopdracht
_SCORE_TIME_BUDGET = 8.0           # seconden voor het model-gewicht van het hele universum
_SEARCH_SHOW_DEFAULT_N = 25
_SEARCH_SHOW_MAX = 2_000
def _sort_val(m) -> float:
    ebw = m.get("expected_boards_won")
    return ebw if ebw is not None else m.get("total_score", 0.0)
def _new_group_summary(assignment: list) -> dict:
    return {
        "n": 0, "ebw_sum": 0.0, "ebw_n": 0,
        "best": None, "worst": None,
        "top": [], "historical": [],
        "players": {}, "positions": {},
        "first_assignment": assignment,
        "weights": {},  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: id(m) -> gewicht van zijn tegenstander-scenario
        # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: exacte gewogen som over ALLE matchups.
        "w_sum": 0.0, "w_p2": 0.0, "w_p1": 0.0, "w_p0": 0.0, "n_missing": 0,
        # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02: matchup tegen de MEEST
        # waarschijnlijke tegenstander-opstelling + bereik van P(2).
        "top_w": -1.0, "top_w_m": None, "p2_min": None, "p2_max": None,
    }
def _add_to_group(g: dict, m: dict, counter: int, opponent_weight: float = 1.0) -> None:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: `opponent_weight` is het
    gewicht van het tegenstander-scenario waartegen deze matchup berekend
    is - bewaard per matchup-id in g["weights"], zodat de gewogen
    puntenkans-aggregatie later over de VOLLEDIGE set kan rekenen."""
    val = _sort_val(m)
    g["n"] += 1
    g["weights"][id(m)] = opponent_weight
    # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: incrementeel, over ALLE matchups.
    pp_m = m.get("point_probs") or {}
    g["w_sum"] += opponent_weight
    g["w_p2"] += opponent_weight * pp_m.get("p2", 0.0)
    g["w_p1"] += opponent_weight * pp_m.get("p1", 0.0)
    g["w_p0"] += opponent_weight * pp_m.get("p0", 0.0)
    g["n_missing"] += int(m.get("n_missing_win_probs", 0) or 0)
    # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02
    if opponent_weight > g["top_w"] or (
        opponent_weight == g["top_w"] and g["top_w_m"] is not None
        and pp_m.get("p2", 0.0) > (g["top_w_m"].get("point_probs") or {}).get("p2", 0.0)
    ):
        g["top_w"], g["top_w_m"] = opponent_weight, m
    p2v = pp_m.get("p2")
    if p2v is not None:
        g["p2_min"] = p2v if g["p2_min"] is None else min(g["p2_min"], p2v)
        g["p2_max"] = p2v if g["p2_max"] is None else max(g["p2_max"], p2v)
    ebw = m.get("expected_boards_won")
    if ebw is not None:
        g["ebw_sum"] += ebw
        g["ebw_n"] += 1
    if g["best"] is None or val > _sort_val(g["best"]):
        g["best"] = m
    if g["worst"] is None or val < _sort_val(g["worst"]):
        g["worst"] = m
    if m.get("is_historical"):
        g["historical"].append(m)
    if len(g["top"]) < _KEEP_PER_GROUP:
        heapq.heappush(g["top"], (val, counter, m))
    elif val > g["top"][0][0]:
        heapq.heapreplace(g["top"], (val, counter, m))
    # Persoonlijke winkans per speler in deze matchup (gemiddelde over de
    # matchen waarin die speler staat) - voor "Beste opstelling voor...".
    per_player: dict = {}
    for idx, a in enumerate(m["assignment"]):
        wp = a.get("win_probability")
        p1, p2 = (str(x) for x in a["our_pair"])
        for pid, partner in ((p1, p2), (p2, p1)):
            if pid not in g["positions"]:
                g["positions"][pid] = []
            if g["n"] == 1:
                g["positions"][pid].append((idx // 2 + 1, idx % 2 + 1, partner))
            if wp is not None:
                per_player.setdefault(pid, []).append(wp)
    for pid, kansen in per_player.items():
        gem = sum(kansen) / len(kansen)
        st_ = g["players"].get(pid)
        if st_ is None:
            g["players"][pid] = [gem, gem, gem, 1, ebw or 0.0, 1 if ebw is not None else 0]
        else:
            st_[0] += gem
            st_[1] = min(st_[1], gem)
            st_[2] = max(st_[2], gem)
            st_[3] += 1
            if ebw is not None:
                st_[4] += ebw
                st_[5] += 1
def _finalize_group(key, g: dict) -> dict:
    rows_by_id = {}
    for _, _, m in g["top"]:
        rows_by_id[id(m)] = m
    for m in [g["worst"]] + g["historical"]:
        if m is not None:
            rows_by_id[id(m)] = m
    rows = sorted(rows_by_id.values(), key=_sort_val, reverse=True)
    all_group_matches = [m for _, _, m in g["top"]]
    for m in [g["worst"]] + g["historical"]:
        if m is not None and m not in all_group_matches:
            all_group_matches.append(m)
    point_probs = _aggregate_group_point_probabilities(all_group_matches, g["weights"])
    # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: exacte waarde over ALLE
    # matchups (incrementeel bijgehouden) vervangt de benadering hierboven.
    if g.get("w_sum", 0.0) > 0:
        point_probs = {
            "p2": g["w_p2"] / g["w_sum"], "p1": g["w_p1"] / g["w_sum"],
            "p0": g["w_p0"] / g["w_sum"], "n_missing_ratings": g.get("n_missing", 0),
        }
    return {
        "key": key, "n": g["n"], "rows": rows,
        "best": g["best"], "worst": g["worst"],
        "mean_ebw": (g["ebw_sum"] / g["ebw_n"]) if g["ebw_n"] else None,
        "point_probs": point_probs,  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
        "n_historical_scenarios": len(g["historical"]),
        # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02
        "vs_likely": g.get("top_w_m"), "vs_likely_weight": g.get("top_w", 0.0),
        "p2_min": g.get("p2_min"), "p2_max": g.get("p2_max"),
        "players": g["players"], "positions": g["positions"],
        "first_assignment": g["first_assignment"],
    }
def _own_lineup_group_key(assignment: list) -> frozenset:
    return frozenset(frozenset(a["our_pair"]) for a in assignment)
def _collect_valid_own_options(
    available_ids: list, max_per_player: dict, official_ranks_strict: dict, player_ratings: dict,
    tournament_rules_dict,
) -> tuple:
    """PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: ALLE reglementair geldige eigen opstellingen (uit
    _build_all_valid_matchups() gehaald, zodat ook de filters en de exacte zoekopdracht ze kunnen gebruiken).
    Geeft (opties, diag, afgekapt) terug; een optie = (ordered_pairs, rotations_info, fully_compliant,
    rank_data_incomplete)."""
    own_structures, own_truncated = _enumerate_rotation_aware_pairings(available_ids, max_per_player)
    valid_own_options = []
    own_excluded_by_rules = 0
    own_variants_generated = 0
    for structure in own_structures:
        combinations = _enumerate_own_variant_combinations(
            structure, official_ranks_strict, player_ratings, rules=tournament_rules_dict,
            include_non_compliant=False,
        )
        for combo in combinations:
            own_variants_generated += 1
            if not combo["fully_compliant"]:
                continue
            all_points_valid = all(r["valid"] for r in combo["rotations"])
            if tournament_rules_dict is not None and not all_points_valid:
                own_excluded_by_rules += 1
                continue
            valid_own_options.append((
                combo["ordered_pairs"], combo["rotations"], combo["fully_compliant"],
                combo.get("rank_data_incomplete", False),
            ))
    diag = {
        "own_structures_total": len(own_structures), "own_variants_generated": own_variants_generated,
        "own_excluded_by_rules": own_excluded_by_rules, "own_valid": len(valid_own_options),
    }
    return valid_own_options, diag, own_truncated
def _make_matchup(opt, computed: dict, hinfo, prob=None) -> dict:
    """Eenzelfde matchup-dict voor de hoofdberekening en de exacte zoekopdracht."""
    own_ordered_pairs, own_rotations_info, fully_compliant, rank_data_incomplete = opt
    hinfo = hinfo or {}
    return {
        "assignment": computed["assignment"],
        "expected_boards_won": computed["expected_boards_won"],
        "total_score": computed["total_score"],
        "point_probs": computed.get("point_probs"),  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
        "n_missing_win_probs": computed.get("n_missing_win_probs", 0),
        "rank_data_incomplete": rank_data_incomplete,
        "own_rotations": own_rotations_info,
        "fully_compliant": True,
        "is_historical": bool(hinfo.get("is_historical")),
        "historical_labels": list(hinfo.get("historical_labels") or []),
        "historical_count": hinfo.get("historical_count", 0),
        "opp_probability": prob,  # PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11
    }
def _build_all_valid_matchups(
    unique_opponent_lineups: dict,
    available_ids: list, max_per_player: dict,
    synergy_fn, player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
    tournament_rules_dict, include_non_compliant_variants: bool = False,
    opponent_weight_override: dict = None,  # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02
    opponent_probability: dict = None,      # PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11
) -> tuple:
    """Rekent ELKE reglementaire eigen opstelling door tegen ELKE meegegeven tegenstander-opstelling.
    Geeft (all_matchups, truncated, total_seen, diagnostics, groups) terug.
    include_non_compliant_variants wordt genegeerd (PADEL_ANALYSIS_NO_NONCOMPLIANT_2026-09-29)."""
    valid_own_options, own_diag, own_truncated = _collect_valid_own_options(
        available_ids, max_per_player, official_ranks_strict, player_ratings, tournament_rules_dict,
    )
    seen_matchup_keys = set()
    groups: dict = {}
    total_seen = 0
    computed_n = 0
    truncated = own_truncated
    counter = 0
    opponent_weight_by_key = {
        their_key: _opponent_lineup_weight(info)
        for their_key, info in unique_opponent_lineups.items()
    }
    if opponent_weight_override:
        opponent_weight_by_key = {
            k: opponent_weight_override.get(k, 0.0) for k in unique_opponent_lineups
        }
    probs = opponent_probability or {}
    for opt in valid_own_options:
        own_ordered_pairs = opt[0]
        if computed_n >= _MAX_COMPUTED_MATCHUPS:
            truncated = True
            break
        our_pairs_key = tuple(frozenset(p) for p in own_ordered_pairs)
        for their_key, info in unique_opponent_lineups.items():
            boards = info["boards"]
            if len(boards) != len(own_ordered_pairs):
                continue
            total_seen += 1
            mkey = (our_pairs_key, their_key)
            if mkey in seen_matchup_keys:
                continue
            seen_matchup_keys.add(mkey)
            computed = _compute_matchup(
                own_ordered_pairs, boards, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings,
            )
            m = _make_matchup(opt, computed, info, probs.get(their_key))
            gkey = _own_lineup_group_key(m["assignment"])
            if gkey not in groups:
                groups[gkey] = _new_group_summary(m["assignment"])
            counter += 1
            _add_to_group(groups[gkey], m, counter, opponent_weight=opponent_weight_by_key.get(their_key, 1.0))
            computed_n += 1
            if computed_n >= _MAX_COMPUTED_MATCHUPS:
                truncated = True
                break
    group_list = [_finalize_group(k, g) for k, g in groups.items()]
    group_list.sort(key=lambda g: (
        round(g["point_probs"]["p2"], 3),
        ((g.get("vs_likely") or {}).get("point_probs") or {}).get("p2", 0.0),
    ), reverse=True)
    all_matchups = [m for g in group_list for m in g["rows"]]
    all_matchups.sort(key=_sort_val, reverse=True)
    diagnostics = dict(own_diag)
    diagnostics.update({"matchups_computed": computed_n, "own_groups": len(group_list)})
    return all_matchups, truncated, total_seen, diagnostics, group_list
def _format_opponent_lineup_label(boards: list) -> str:
    return " | ".join(" + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards)
_TABLE_CHAR_WIDTH_PX = 6.6
_TABLE_COL_MIN_WIDTH = 90
_TABLE_COL_MAX_WIDTH = 240
def _estimate_column_width(values: list, min_width: int = _TABLE_COL_MIN_WIDTH, max_width: int = _TABLE_COL_MAX_WIDTH) -> int:
    max_len = 0
    for v in values:
        if v is None:
            continue
        max_len = max(max_len, len(str(v)))
    width = int(max_len * _TABLE_CHAR_WIDTH_PX) + 24
    return max(min_width, min(max_width, width))
def _compliance_badge(fully_compliant: bool, rank_data_incomplete: bool = False) -> str:
    # PADEL_ANALYSIS_NO_NONCOMPLIANT_2026-09-29: er worden enkel nog reglementaire varianten berekend.
    if rank_data_incomplete:
        return "onzeker"
    return "OK"
def _format_point_probs(pp: dict) -> str:
    """Leesbare, korte weergave van een puntenkans-dict, bv. '68% · 2p 24% · 1p 8% · 0p'.
    Niet meer gebruikt in de groepstitel; blijft bestaan als herbruikbare tekst-opmaak."""
    if not pp:
        return "onbekend"
    return (
        f"{pp.get('p2', 0.0) * 100:.0f}% · 2p  "
        f"{pp.get('p1', 0.0) * 100:.0f}% · 1p  "
        f"{pp.get('p0', 0.0) * 100:.0f}% · 0p"
    )
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_MATCHUP_FILTERS_2026-10-10 - zie moduledocstring.
# ─────────────────────────────────────────────
def _norm_name(n) -> str:
    return " ".join(str(n or "").lower().split())
def _opp_key(p: dict) -> str:
    """Sleutel van 1 tegenstander-speler: het user_id, anders de genormaliseerde naam."""
    uid = p.get("user_id")
    return f"id:{uid}" if uid else f"n:{_norm_name(p.get('name'))}"
def _pair_key(keys) -> str:
    return "|".join(sorted(str(k) for k in keys))
def _matchup_keys(m: dict) -> tuple:
    """(onze spelers, onze koppels, tegenstander-spelers, tegenstander-koppels) van 1 matchup, als sets van sleutels."""
    own_players, own_pairs, opp_players, opp_pairs = set(), set(), set(), set()
    for a in (m or {}).get("assignment") or []:
        ons = [str(x) for x in (a.get("our_pair") or ())]
        own_players.update(ons)
        if len(ons) == 2:
            own_pairs.add(_pair_key(ons))
        pair = (a.get("opponent_board") or {}).get("opponent_pair") or []
        hun = [_opp_key(p) for p in pair]
        opp_players.update(hun)
        if len(hun) == 2:
            opp_pairs.add(_pair_key(hun))
    return own_players, own_pairs, opp_players, opp_pairs
def _filter_option_lists(own_options: list, name_lookup_global: dict, opp_ctx) -> dict:
    """PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: keuzes voor de filters uit de VOLLEDIGE set eigen opstellingen
    en het VOLLEDIGE tegenstander-roster (niet meer uit de bewaarde rijen): {"own_players", "own_pairs",
    "opp_players", "opp_pairs"} = {sleutel: label}, gesorteerd op label."""
    own_players: dict = {}
    own_pairs: dict = {}
    for opt in own_options or []:
        for pair in opt[0]:
            raw = list(pair)
            keys = [str(x) for x in raw]
            labels = [str(name_lookup_global.get(x, x)) for x in raw]
            for k, lbl in zip(keys, labels):
                own_players[k] = lbl
            if len(keys) == 2:
                own_pairs[_pair_key(keys)] = " + ".join(sorted(labels))
    opp_players: dict = {}
    opp_pairs: dict = {}
    if opp_ctx:
        names = opp_ctx.get("names") or {}
        ids = list(opp_ctx.get("ids") or [])
        for uid in ids:
            opp_players[f"id:{uid}"] = str(names.get(uid, uid))
        for a, b in itertools.combinations(ids, 2):
            opp_pairs[_pair_key([f"id:{a}", f"id:{b}"])] = " + ".join(
                sorted([str(names.get(a, a)), str(names.get(b, b))])
            )
    def _sorted(d: dict) -> dict:
        return dict(sorted(d.items(), key=lambda kv: kv[1].lower()))
    return {
        "own_players": _sorted(own_players), "own_pairs": _sorted(own_pairs),
        "opp_players": _sorted(opp_players), "opp_pairs": _sorted(opp_pairs),
    }
def _multiselect_safe(label: str, options: dict, key: str, placeholder: str):
    """st.multiselect op een dict {sleutel: label}. Een bewaarde keuze die niet meer in de
    opties zit (bv. na een nieuwe berekening) wordt eerst stil gewist."""
    huidig = st.session_state.get(key)
    if huidig is not None:
        schoon = [k for k in huidig if k in options]
        if schoon != list(huidig):
            st.session_state[key] = schoon
    return st.multiselect(
        label, list(options.keys()), format_func=lambda k: options.get(k, k),
        key=key, placeholder=placeholder,
    )
def _render_filter_widgets(opts: dict, key_prefix: str, own: bool = True, opp: bool = True) -> dict:
    """Toont de filterlijsten en geeft de keuze terug: {"own_players": [...], "own_pairs": [...],
    "opp_players": [...], "opp_pairs": [...]} (sleutels, leeg = geen filter)."""
    sel = {"own_players": [], "own_pairs": [], "opp_players": [], "opp_pairs": [], "vs": False}
    if own and opp:
        c1, c2 = st.columns(2)
        with c1:
            sel["own_players"] = _multiselect_safe("Onze speler(s)", opts["own_players"], f"{key_prefix}_f_op", "Alle")
            sel["own_pairs"] = _multiselect_safe("Ons koppel", opts["own_pairs"], f"{key_prefix}_f_opr", "Alle")
        with c2:
            sel["opp_players"] = _multiselect_safe("Tegenstander-speler(s)", opts["opp_players"], f"{key_prefix}_f_tp", "Alle")
            sel["opp_pairs"] = _multiselect_safe("Tegenstander-koppel", opts["opp_pairs"], f"{key_prefix}_f_tpr", "Alle")
        if (sel["own_players"] or sel["own_pairs"]) and (sel["opp_players"] or sel["opp_pairs"]):
            sel["vs"] = st.checkbox(
                "Onze keuze speelt TEGEN de tegenstander-keuze (in dezelfde match, rotatie 1 of 2)", value=True,
                key=f"{key_prefix}_f_vs",
                help="Aan: je ziet enkel opstellingen waarin onze gekozen speler(s)/koppel(s) in een match tegen de "
                     "gekozen tegenstander(s) spelen, in rotatie 1 of in rotatie 2. Uit: alles moet ergens in de "
                     "opstelling voorkomen, ook als ze niet tegen elkaar spelen.",
            )
    elif own:
        c1, c2 = st.columns(2)
        with c1:
            sel["own_players"] = _multiselect_safe("Onze speler(s)", opts["own_players"], f"{key_prefix}_f_op", "Alle")
        with c2:
            sel["own_pairs"] = _multiselect_safe("Ons koppel", opts["own_pairs"], f"{key_prefix}_f_opr", "Alle")
    elif opp:
        c1, c2 = st.columns(2)
        with c1:
            sel["opp_players"] = _multiselect_safe("Tegenstander-speler(s)", opts["opp_players"], f"{key_prefix}_f_tp", "Alle")
        with c2:
            sel["opp_pairs"] = _multiselect_safe("Tegenstander-koppel", opts["opp_pairs"], f"{key_prefix}_f_tpr", "Alle")
    return sel
def _has_filter(sel: dict) -> bool:
    return any(sel.get(k) for k in ("own_players", "own_pairs", "opp_players", "opp_pairs"))
def _apply_filters(items: list, sel: dict, get_matchup=lambda x: x) -> list:
    """Houdt de items over waarvan de matchup ALLE gekozen spelers/koppels bevat."""
    if not _has_filter(sel):
        return list(items)
    want = (
        set(sel.get("own_players") or []), set(sel.get("own_pairs") or []),
        set(sel.get("opp_players") or []), set(sel.get("opp_pairs") or []),
    )
    out = []
    for it in items:
        have = _matchup_keys(get_matchup(it))
        if all(w <= h for w, h in zip(want, have)):
            out.append(it)
    return out
def _filter_caption(n_na: int, n_voor: int, wat: str) -> None:
    st.caption(
        f"{n_na} van {n_voor} {wat} voldoen aan je filters. Alle gekozen filters moeten kloppen: kies je "
        "2 spelers, dan zie je enkel resultaten waarin ze allebei meespelen."
    )
def _ps_text(pid, ps_map) -> str:
    """" (ps 180)" met de padelstat van deze speler; " (ps ?)" als die niet gekend is;
    "" als er helemaal geen padelstat-lijst is meegegeven (oude aanroepers)."""
    if not ps_map:
        return ""
    v = ps_map.get(pid) if pid in ps_map else ps_map.get(str(pid))
    return f" (ps {int(round(v))})" if v is not None else " (ps ?)"
def _matchups_to_table_rows(
    matchups: list, name_lookup_global: dict, own_ps: dict = None, opp_ps: dict = None,
) -> tuple:
    """`own_ps`/`opp_ps` ({speler-id: padelstat}) zetten de padelstat van elke speler tussen haakjes in
    'Ons duo'/'Tegenstander'; de kolom 'Toelichting' is weg. Een matchup met `opp_probability` krijgt de kolom
    'Kans opstelling %' (PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11)."""
    rows = []
    board_column_names: list = []
    for rank, m in enumerate(matchups, start=1):
        assignment = m["assignment"]
        n_boards = len(assignment)
        n_rotations = -(-n_boards // 2)
        pp = m.get("point_probs") or {}
        row = {
            "#": rank,
            "Verwacht": m.get("expected_boards_won"),
            # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: kansen per uitkomst, apart sorteerbaar.
            "Kans 2p %": round(pp.get("p2", 0.0) * 100, 0) if pp else None,
            "Kans 1p %": round(pp.get("p1", 0.0) * 100, 0) if pp else None,
            "Kans 0p %": round(pp.get("p0", 0.0) * 100, 0) if pp else None,
        }
        if m.get("opp_probability") is not None:
            row["Kans opstelling %"] = round(m["opp_probability"] * 100, 2)
        for r in range(n_rotations):
            for board_in_rotation in range(2):
                board_idx = r * 2 + board_in_rotation
                if board_idx >= n_boards:
                    continue
                a = assignment[board_idx]
                col_base = f"Rotatie{r+1} M{board_in_rotation+1}"
                if col_base not in board_column_names:
                    board_column_names.append(col_base)
                p1, p2 = a["our_pair"]
                our_full_1 = name_lookup_global.get(p1, p1)
                our_full_2 = name_lookup_global.get(p2, p2)
                opp_pair = a["opponent_board"]["opponent_pair"]
                their_full = []
                for p in opp_pair:
                    uid = p.get("user_id")
                    their_full.append(f"{p.get('name', '?')}{_ps_text(str(uid) if uid else '', opp_ps)}")
                wp = a.get("win_probability")
                row[f"{col_base} - Ons duo"] = (
                    f"{our_full_1}{_ps_text(p1, own_ps)} + {our_full_2}{_ps_text(p2, own_ps)}"
                )
                row[f"{col_base} - Tegenstander"] = " + ".join(their_full)
                row[f"{col_base} %"] = round(wp * 100, 0) if wp is not None else None
        n_keer = m.get("historical_count", 0)
        if m["is_historical"]:
            freq = f"{n_keer}x" if n_keer > 1 else "1x"
            row["Vorige keer"] = f"{freq} ({', '.join(m['historical_labels'])})"
        else:
            row["Vorige keer"] = ""
        rows.append(row)
    return rows, board_column_names
def _matchup_table_column_config(table_rows: list, board_column_names: list) -> tuple:
    column_config = {
        "#": st.column_config.NumberColumn("#", width="small"),
        "Verwacht": st.column_config.NumberColumn("Verwacht", format="%.2f", width="small"),
        # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
        "Kans 2p %": st.column_config.NumberColumn("Kans 2p", format="%.0f%%", width="small"),
        "Kans 1p %": st.column_config.NumberColumn("Kans 1p", format="%.0f%%", width="small"),
        "Kans 0p %": st.column_config.NumberColumn("Kans 0p", format="%.0f%%", width="small"),
        "Kans opstelling %": st.column_config.NumberColumn(
            "Kans opstelling", format="%.2f%%", width="small",
            help="Hoe waarschijnlijk het model deze tegenstander-opstelling vindt (over alle mogelijke opstellingen).",
        ),
    }
    for col_base in board_column_names:
        ons_col = f"{col_base} - Ons duo"
        tegen_col = f"{col_base} - Tegenstander"
        pct_col = f"{col_base} %"
        column_config[ons_col] = st.column_config.TextColumn(
            ons_col, width=_estimate_column_width([row.get(ons_col) for row in table_rows], max_width=340),
        )
        column_config[tegen_col] = st.column_config.TextColumn(
            tegen_col, width=_estimate_column_width([row.get(tegen_col) for row in table_rows], max_width=340),
        )
        column_config[pct_col] = st.column_config.NumberColumn(pct_col, format="%.0f%%", width="small")
    heeft_prob = any("Kans opstelling %" in r for r in table_rows)
    column_order = ["#", "Kans 2p %", "Kans 1p %", "Kans 0p %", "Verwacht"]
    if heeft_prob:
        column_order.append("Kans opstelling %")
    for col_base in board_column_names:
        column_order += [f"{col_base} - Ons duo", f"{col_base} - Tegenstander", f"{col_base} %"]
    column_order += ["Vorige keer"]
    return column_config, column_order
def _render_group_dilution_diagnosis(g: dict, best: dict, n_missing: int) -> None:
    """PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01. Toont, ALTIJD zichtbaar, hoeveel van de doorgerekende
    scenario's van deze groep effectief HISTORISCH vs THEORETISCH waren, en - indien van toepassing - EEN van 2
    elkaar uitsluitende waarschuwingen over waarom de percentages mogelijk niet onderscheidend zijn."""
    n_total = g.get("n", 0)
    n_hist = g.get("n_historical_scenarios", 0)
    n_theo = max(0, n_total - n_hist)
    vs = g.get("vs_likely")
    regels = []
    if vs is not None:
        pv = vs.get("point_probs") or {}
        hist_txt = " (effectief gespeeld)" if vs.get("is_historical") else ""
        regels.append(
            f"**Tegen hun waarschijnlijkste opstelling{hist_txt}** "
            f"({g.get('vs_likely_weight', 0) * 100:.0f}% kans): "
            f"**{pv.get('p2', 0) * 100:.0f}% winst** · {pv.get('p1', 0) * 100:.0f}% gelijk · "
            f"{pv.get('p0', 0) * 100:.0f}% verlies"
        )
    if g.get("p2_min") is not None:
        regels.append(
            f"Kans op winst varieert van **{g['p2_min'] * 100:.0f}%** (slechtste tegenstander-opstelling) "
            f"tot **{g['p2_max'] * 100:.0f}%** (gunstigste)."
        )
    regels.append(
        f"Gewogen over {n_total} tegenstander-scenario's ({n_hist} effectief gespeeld, {n_theo} theoretisch)."
    )
    st.markdown("  \n".join(regels))
    n_boards_per_row = len(best.get("assignment") or [])
    denom = n_total * n_boards_per_row
    missing_fraction = (n_missing / denom) if denom else 0.0
    if missing_fraction >= _DILUTION_MISSING_RATIO_THRESHOLD:
        st.warning(
            f"Bij {missing_fraction * 100:.0f}% van de doorgerekende matchen in deze groep is de "
            "winkans onbekend (ontbrekend klassement/rating) - de percentages hierboven steunen "
            "dus voor een groot deel op een neutrale 50%-aanname en zijn minder betrouwbaar. "
            "Vul het ontbrekende klassement/rating aan voor een scherper cijfer."
        )
    elif n_hist == 0 and n_theo >= _DILUTION_THEORETICAL_MIN_COUNT and olm is None:
        st.caption(
            "Let op: dit cijfer is (nog) uitsluitend gebaseerd op THEORETISCHE tegenstander-"
            "opstellingen (nog geen enkele hiervan effectief gespeeld dit seizoen). Bij veel "
            "mogelijke tegenstander-opstellingen kan het verschil tussen eigen opstellingen "
            "hierdoor klein lijken - verklein het tegenstander-roster hierboven tot de spelers "
            "die je effectief verwacht, voor een scherper onderscheid."
        )
def _render_search_results(results: list, info: dict, name_lookup_global: dict, own_ps, opp_ps, key: str) -> None:
    """PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: toont het resultaat van een exacte zoekopdracht."""
    if not results:
        st.info(
            "Geen enkele combinatie voldoet aan deze filters. Controleer of de gekozen spelers/koppels samen in een "
            "reglementair geldige opstelling kunnen staan (puntengrens, speelbudget per speler)."
            + (" Tip: het vinkje 'tegen elkaar' is aan - elke gekozen speler/koppel moet dan tegen een gekozen "
               "tegenstander spelen. Zet het uit als alles gewoon ergens in de opstelling mag voorkomen."
               if info.get("vs") else "")
        )
        return
    st.caption(
        f"**Exacte zoekopdracht over de volledige set:** {info['n_own']} eigen opstelling(en) x "
        f"{info['n_opp_used']:,} tegenstander-opstelling(en) = **{info['n_computed']:,}** combinaties "
        f"({info['n_hist']} daarvan effectief gespeeld)."
        + (" Enkel opstellingen waarin je gekozen spelers/koppels tegen elkaar spelen (rotatie 1 of 2)." if info.get("vs") else "")
        + f" (berekend in {info.get('seconds', 0.0):.1f}s)"
    )
    if info.get("truncated"):
        reden = (
            f"de rekentijd van {_SEARCH_TIME_BUDGET:.0f} seconden is bereikt" if info.get("timed_out")
            else "dat te veel combinaties geeft"
        )
        st.warning(
            f"Er zijn {info['n_opp_matching']:,} tegenstander-opstellingen die aan je filter voldoen; omdat {reden}, "
            f"zijn de {info['n_opp_used']:,} meest waarschijnlijke doorgerekend. "
            "Kies een tegenstander-speler of -koppel erbij voor een volledige dekking."
        )
    if info.get("enum_truncated"):
        st.warning("Het aantal mogelijke tegenstander-opstellingen is zo groot dat de opsomming is afgebroken - "
                   "kies een tegenstander-koppel erbij.")
    n = len(results)
    toon_alle = False
    if n > _SEARCH_SHOW_DEFAULT_N:
        toon_alle = st.checkbox(
            f"Toon alle {min(n, _SEARCH_SHOW_MAX):,} gevonden combinaties (i.p.v. de beste {_SEARCH_SHOW_DEFAULT_N})",
            key=f"{key}_showall",
        )
    shown = results[:_SEARCH_SHOW_MAX] if toon_alle else results[:_SEARCH_SHOW_DEFAULT_N]
    table_rows, board_column_names = _matchups_to_table_rows(shown, name_lookup_global, own_ps=own_ps, opp_ps=opp_ps)
    column_config, column_order = _matchup_table_column_config(table_rows, board_column_names)
    st.dataframe(
        table_rows, use_container_width=True, hide_index=True,
        column_config=column_config, column_order=column_order,
    )
    if n > len(shown):
        st.caption(f"Beste {len(shown)} van {n:,} gevonden combinaties getoond, gesorteerd op verwacht aantal gewonnen matchen.")
def _render_own_lineup_groups_with_opponents(
    groups: list, name_lookup_global: dict, ploeg_key: str = "",
    own_ps: dict = None, opp_ps: dict = None, filter_ctx: dict = None,
) -> None:
    """Werkt op de groepssamenvattingen uit _build_all_valid_matchups(). Het HOOFDGETAL is de gewogen puntenkans
    (2/1/0); de lijst is gesorteerd op kans-op-2-punten.
    PADEL_ANALYSIS_MATCHUP_FILTERS_2026-10-10: filter op onze spelers/koppels boven de lijst.
    PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: `filter_ctx` = {"opts", "search"}: de keuzelijsten komen uit de
    volledige set, en de tegenstander-filter in 'Details' rekent exact (search(sel, own_fixed_key))."""
    if not groups:
        return
    filter_ctx = filter_ctx or {}
    st.markdown('<div class="section-header">Onze opstellingen - klap open voor de tegenstander-opstellingen</div>', unsafe_allow_html=True)
    st.caption(
        "Elke groep hieronder is 1 unieke combinatie van ONZE koppels (ongeacht matchvolgorde of tegen wie), "
        "gerangschikt op de GEWOGEN kans op 2 competitiepunten (ploegwinst) over de doorgerekende "
        "tegenstander-opstellingen. Een tegenstander-opstelling die het model waarschijnlijker vindt, "
        "telt zwaarder mee dan een onwaarschijnlijke. Klap een groep open "
        "voor de beste tegenstander-opstellingen, de slechtste, en elke opstelling die de tegenstander "
        "effectief al speelde."
    )
    st.caption(
        "Puntensysteem: 2 punten bij meer gewonnen matchen dan de tegenstander, 1 punt bij een gelijke "
        "stand, 0 punten bij minder gewonnen matchen. 'Verwacht' (EBW) blijft ernaast staan als secundair "
        "getal, vooral nuttig bij een gelijke puntenkans."
    )
    st.caption(
        "Reglementair: OK = geverifieerd conform art. 6.6. onzeker = minstens 1 speler heeft nog geen bekend "
        "officieel klassement - de volgorde kon NIET betrouwbaar geverifieerd worden."
    )
    p2s = [g["point_probs"]["p2"] for g in groups]
    if len(p2s) > 1:
        spread = (max(p2s) - min(p2s)) * 100
        if spread < 3:
            st.info(
                f"De {len(groups)} eigen opstellingen liggen dicht bij elkaar (kans op winst "
                f"{min(p2s) * 100:.0f}% - {max(p2s) * 100:.0f}%): onze spelers zijn ongeveer even sterk "
                "tegenover deze tegenstander, dus de keuze maakt gemiddeld weinig uit. Het echte verschil "
                "zit in WIE de tegenstander opstelt - zie 'Tegen hun waarschijnlijkste opstelling' per groep "
                "en de Rotatieplanner hierboven."
            )
        else:
            st.markdown(
                f"**Verschil tussen onze beste en slechtste opstelling: {spread:.0f} procentpunt** "
                f"kans op winst ({max(p2s) * 100:.0f}% vs {min(p2s) * 100:.0f}%)."
            )
    st.markdown("**Filter onze opstellingen**")
    opts_groups = filter_ctx.get("opts")
    if opts_groups is None:
        # Terugval (oude aanroepers zonder filter_ctx): keuzelijsten uit de beste matchup van elke groep.
        opts_groups = _filter_option_lists(
            [([a["our_pair"] for a in g["best"]["assignment"]], None, True, False) for g in groups if g.get("best")],
            name_lookup_global, None,
        )
    groep_sel = _render_filter_widgets(opts_groups, f"groups_{ploeg_key}", own=True, opp=False)
    geindexeerd = list(enumerate(groups))
    geindexeerd = _apply_filters(geindexeerd, groep_sel, get_matchup=lambda t: t[1].get("best"))
    if _has_filter(groep_sel):
        _filter_caption(len(geindexeerd), len(groups), "eigen opstellingen")
    if not geindexeerd:
        st.info("Geen enkele eigen opstelling voldoet aan deze filters.")
        st.divider()
        return
    toon_alle = False
    if len(geindexeerd) > _GROUPS_DISPLAY_DEFAULT:
        toon_alle = st.checkbox(
            f"Toon alle {len(geindexeerd)} eigen opstellingen (i.p.v. de beste {_GROUPS_DISPLAY_DEFAULT})",
            key=f"groups_show_all_{ploeg_key}",
        )
    zichtbaar = geindexeerd if toon_alle else geindexeerd[:_GROUPS_DISPLAY_DEFAULT]
    for gi, g in zichtbaar:
        best, worst = g["best"], g["worst"]
        korte_delen, lange_regels = [], []
        for idx, a in enumerate(best["assignment"]):
            p1, p2 = a["our_pair"]
            rot, m_in_rot = idx // 2 + 1, idx % 2 + 1
            naam1, naam2 = name_lookup_global.get(p1, p1), name_lookup_global.get(p2, p2)
            korte_delen.append(f"R{rot}M{m_in_rot} {naam1}/{naam2}")
            lange_regels.append(f"- **Rotatie {rot} - Match {m_in_rot}**: {naam1} / {naam2}")
        best_ebw, worst_ebw = best.get("expected_boards_won"), worst.get("expected_boards_won")
        best_txt = f"{best_ebw:.2f}" if best_ebw is not None else f"score {best.get('total_score', 0):.3f}"
        worst_txt = f"{worst_ebw:.2f}" if worst_ebw is not None else f"score {worst.get('total_score', 0):.3f}"
        badge = _compliance_badge(True, best.get("rank_data_incomplete", False))
        pp_metrics = g.get("point_probs") or {}
        per_rot = {}
        for idx, a in enumerate(best["assignment"]):
            p1_, p2_ = a["our_pair"]
            per_rot.setdefault(idx // 2 + 1, []).append(
                f"{name_lookup_global.get(p1_, p1_)} / {name_lookup_global.get(p2_, p2_)}"
            )
        _sep = " \u00b7 "
        st.markdown("#### " + "  \u00a0|\u00a0  ".join(
            f"R{r}: {_sep.join(v)}" for r, v in sorted(per_rot.items())
        ) + f"  \u00a0 `{badge}`")
        col_p2, col_p1, col_p0, col_ge1 = st.columns(4)
        with col_p2:
            st.metric("Winst (2p)", f"{pp_metrics.get('p2', 0.0) * 100:.0f}%")
        with col_p1:
            st.metric("Gelijk (1p)", f"{pp_metrics.get('p1', 0.0) * 100:.0f}%")
        with col_p0:
            st.metric("Verlies (0p)", f"{pp_metrics.get('p0', 0.0) * 100:.0f}%")
        with col_ge1:
            st.metric("Minstens 1 punt", f"{(pp_metrics.get('p2', 0.0) + pp_metrics.get('p1', 0.0)) * 100:.0f}%")
        n_missing = pp_metrics.get("n_missing_ratings", 0)
        _render_group_dilution_diagnosis(g, best, n_missing)
        with st.expander("Details", expanded=False):
            st.markdown("**Onze opstelling in deze groep:**")
            st.markdown("\n".join(lange_regels))
            gem = g.get("mean_ebw")
            gem_txt = f", gemiddeld EBW {gem:.2f}" if gem is not None else ""
            missing_txt = (
                f" ({n_missing} match(en) zonder bekende winkans, geteld als 50/50 in de puntenkans)"
                if n_missing else ""
            )
            st.caption(
                f"Bovenstaande kansen zijn het gewogen gemiddelde over {g['n']} doorgerekende "
                f"tegenstander-opstelling(en){missing_txt}. Best case {best_txt} en worst case {worst_txt} "
                f"verwachte gewonnen matchen (EBW){gem_txt}."
            )
            if len(g["rows"]) < g["n"]:
                st.caption(
                    f"Getoond: de beste {_KEEP_PER_GROUP}, de slechtste en elke al gespeelde "
                    f"tegenstander-opstelling ({len(g['rows'])} van {g['n']}). Wil je een specifieke "
                    "tegenstander-combinatie zien, filter dan hieronder: dat rekent exact."
                )
            search = filter_ctx.get("search")
            opts_opp = filter_ctx.get("opts")
            gefilterd_exact = False
            if search is not None and opts_opp is not None and opts_opp.get("opp_pairs"):
                st.markdown("**Filter op de tegenstander**")
                det_sel = _render_filter_widgets(opts_opp, f"grpdet_{ploeg_key}_{gi}", own=False, opp=True)
                if _has_filter(det_sel):
                    gefilterd_exact = True
                    results, sinfo = search(det_sel, g["key"])
                    _render_search_results(
                        results, sinfo, name_lookup_global, own_ps, opp_ps, f"grpdet_{ploeg_key}_{gi}_res",
                    )
            if not gefilterd_exact:
                table_rows, board_column_names = _matchups_to_table_rows(
                    g["rows"], name_lookup_global, own_ps=own_ps, opp_ps=opp_ps,
                )
                column_config, column_order = _matchup_table_column_config(table_rows, board_column_names)
                st.dataframe(
                    table_rows, use_container_width=True, hide_index=True,
                    column_config=column_config, column_order=column_order,
                )
                st.caption("Tussen haakjes staat de padelstat (ps) van elke speler.")
    if not toon_alle and len(geindexeerd) > _GROUPS_DISPLAY_DEFAULT:
        st.caption(f"De beste {_GROUPS_DISPLAY_DEFAULT} van {len(geindexeerd)} eigen opstellingen getoond (gesorteerd op kans op 2 punten).")
    st.divider()
def _render_best_for_selected_player(
    groups: list, sel_player_id: str, name_lookup_global: dict,
) -> None:
    """Welke ploegopstelling is het beste VOOR EEN SPECIFIEKE speler? (Wordt niet meer aangeroepen vanuit
    render_matchup_overview() - PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04 - maar blijft bestaan.)
    Sortering op de persoonlijke gemiddelde winkans; ernaast de PLOEG-puntenkans (2/1/0) van dezelfde opstelling."""
    if not groups or not sel_player_id:
        return
    sel_id = str(sel_player_id)
    sel_naam = name_lookup_global.get(sel_id, sel_id)
    rijen = []
    for g in groups:
        stats = g["players"].get(sel_id)
        if not stats:
            continue
        som, laagste, hoogste, n, team_som, team_n = stats
        gemiddeld = som / n
        posities = g["positions"].get(sel_id) or []
        pos_txt = " + ".join(
            f"R{rot}M{m_in_rot} met {name_lookup_global.get(partner, partner)}"
            for rot, m_in_rot, partner in posities
        )
        opstelling_txt = " \u00b7 ".join(
            f"R{idx // 2 + 1}M{idx % 2 + 1} "
            f"{name_lookup_global.get(str(a['our_pair'][0]), a['our_pair'][0])}/"
            f"{name_lookup_global.get(str(a['our_pair'][1]), a['our_pair'][1])}"
            for idx, a in enumerate(g["first_assignment"])
        )
        team_gemiddeld = (team_som / team_n) if team_n else None
        pp = g.get("point_probs") or {}
        rijen.append({
            "Gemiddelde winkans": round(gemiddeld * 100, 1),
            "Slechtste geval": round(laagste * 100, 1),
            "Beste geval": round(hoogste * 100, 1),
            "Team gemiddeld": round(team_gemiddeld, 2) if team_gemiddeld is not None else None,
            "Team Kans 2p %": round(pp.get("p2", 0.0) * 100, 0) if pp else None,
            "Team Kans 1p %": round(pp.get("p1", 0.0) * 100, 0) if pp else None,
            "Team Kans 0p %": round(pp.get("p0", 0.0) * 100, 0) if pp else None,
            f"Positie van {sel_naam}": pos_txt,
            "Volledige ploegopstelling": opstelling_txt,
            "Tegenstander-scenario's": n,
        })
    if not rijen:
        st.info(
            f"{sel_naam} komt in geen enkele doorgerekende opstelling voor - selecteer "
            "deze speler hierboven bij 'Beschikbare eigen spelers' om deze tabel te vullen."
        )
        return
    rijen.sort(key=lambda r: r["Gemiddelde winkans"], reverse=True)
    st.markdown(
        f'<div class="section-header">Beste opstelling voor {sel_naam}</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(rijen, use_container_width=True, hide_index=True)
    beste = rijen[0]
    st.success(
        f"Beste voor {sel_naam}: **{beste['Volledige ploegopstelling']}** "
        f"- gemiddeld **{beste['Gemiddelde winkans']:.1f}%** winkans (slechtste geval {beste['Slechtste geval']:.1f}%)."
    )
    st.divider()
def _render_save_analysis_button(
    all_matchups: list, opp: dict, available_ids: list, name_lookup_global: dict,
    total_boards, max_per_player: dict, sel_player_id,
) -> None:
    """PADEL_ANALYSIS_SAVE_BUTTON_VISIBILITY_FIX_2026-09-27: eigen functie zodat de knop VROEG in de
    resultatensectie kan verschijnen. Payload/opslag-logica: ONGEWIJZIGD."""
    # Enkel de beste _SAVE_MAX_MATCHUPS (Firestore < 1 MB).
    all_matchups = list(all_matchups)[:_SAVE_MAX_MATCHUPS]
    if st.button(f"Deze analyse opslaan (beste {len(all_matchups)} matchups)", key=f"save_all_matchups_{opp['ploeg_id']}"):
        payload = {
            "opponent_name": opp.get("name"), "opponent_ploeg_id": opp.get("ploeg_id"),
            "own_player_ids": available_ids,
            "own_player_labels": [name_lookup_global.get(pid, pid) for pid in available_ids],
            "total_boards": int(total_boards), "max_per_player": max_per_player,
            "scenarios": [
                {
                    "s_idx": rank, "fixture_label": (
                        f"Matchup #{rank}" + (f" (zoals gespeeld op {', '.join(m['historical_labels'])})" if m["is_historical"] else "")
                        + ("" if m.get("fully_compliant", True) else " [niet-reglementaire variant]")
                    ),
                    "boards_count": len(m["assignment"]),
                    "options": [{
                        "total_score": m["total_score"], "expected_boards_won": m.get("expected_boards_won"),
                        "point_probs": m.get("point_probs"),
                        "assignment": [
                            {
                                "our_pair_labels": [name_lookup_global.get(a["our_pair"][0], a["our_pair"][0]), name_lookup_global.get(a["our_pair"][1], a["our_pair"][1])],
                                "synergy": a["synergy"], "edge": a["edge"], "win_probability": a.get("win_probability"),
                                "opponent_names": [p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]],
                            } for a in m["assignment"]
                        ],
                    }],
                } for rank, m in enumerate(all_matchups, start=1)
            ],
        }
        doc_id = fb.save_lineup_analysis(sel_player_id, payload)
        st.success(f"Analyse opgeslagen ({len(all_matchups)} matchups).")
def _model_weights_for_lineups(bundle: dict, unique_opponent_lineups: dict) -> tuple:
    """PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: voorspelde kans per tegenstander-scenario.
    Geeft (weights {key: kans}, stats) of (None, None)."""
    if olm is None or not unique_opponent_lineups:
        return None, None
    try:
        stats = olm.build_opponent_stats(bundle)
        roster = {str(p.get("user_id")) for p in (bundle.get("unique_players") or []) if p.get("user_id")}
        for key in unique_opponent_lineups:
            for pair in key:
                roster |= set(pair)
        roster_uids = sorted(roster)
        logs = {
            key: olm.full_lineup_log_score(stats, list(key), roster_uids)
            for key in unique_opponent_lineups
        }
        return olm.softmax_weights(logs), stats
    except Exception:  # noqa: BLE001
        return None, None
def _render_predicted_opponent_lineups(unique_opponent_lineups: dict, weights: dict, stats: dict) -> None:
    """PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: top 5 voorspelde tegenstander-opstellingen met kans + redenen."""
    if not weights:
        return
    top = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top5_share = sum(w for _, w in top)
    with st.expander(
        f"Voorspelde tegenstander-opstellingen (statistisch model, op basis van "
        f"{stats.get('n_fixtures', 0)} eerdere ontmoeting(en))", expanded=False,
    ):
        st.caption(
            "Het model combineert 3 eenvoudige signalen uit hun eerdere ontmoetingen: wie speelt vaak "
            "mee, wie speelt vaak SAMEN, en wie speelt meestal Match 1 of Match 2. Die kans is het "
            "gewicht van elk scenario in de puntenkansen hieronder. "
            f"De top 5 hieronder samen: {top5_share * 100:.0f}% van het totale gewicht."
        )
        for key, w in top:
            info = unique_opponent_lineups[key]
            hist = f" - effectief gespeeld ({', '.join(info['historical_labels'])})" if info.get("is_historical") else ""
            st.write(f"**{w * 100:.1f}%** - {_format_opponent_lineup_label(info['boards'])}{hist}")
            redenen = []
            for r in range(0, len(key) - 1, 2):
                redenen += olm.explain_rotation(stats, key[r], key[r + 1], max_reasons=2)
            uniek = list(dict.fromkeys(redenen))[:3]
            if uniek:
                st.caption(" · ".join(uniek))
def _expected_matches_per_player(bundle: dict, chosen_ids: list, needed: int, max_per: int) -> dict:
    """PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: verwacht aantal matchen per tegenstander-speler.
    PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: enkel nog INFORMATIEF (de opstellingen worden niet meer
    met dit aantal beperkt). Zonder historiek: None."""
    if olm is None or not chosen_ids:
        return None
    try:
        stats = olm.build_opponent_stats(bundle)
    except Exception:  # noqa: BLE001
        return None
    n_fix = stats.get("n_fixtures", 0)
    if n_fix <= 0:
        return None
    raw = {}
    for u in chosen_ids:
        gem = stats["slot_total"].get(u, 0) / n_fix
        raw[u] = gem if gem > 0 else 0.25  # nooit gezien: kleine kans
    totaal = sum(raw.values()) or 1.0
    doel = {u: min(max_per, v * needed / totaal) for u, v in raw.items()}
    out = {u: int(v) for u, v in doel.items()}
    rest = needed - sum(out.values())
    volgorde = sorted(doel, key=lambda u: doel[u] - int(doel[u]), reverse=True)
    i = 0
    while rest > 0 and i < 10 * len(volgorde):
        u = volgorde[i % len(volgorde)]
        if out[u] < max_per:
            out[u] += 1
            rest -= 1
        i += 1
    return out
def _filter_lineups_to_roster(unique_opponent_lineups: dict, chosen_ids: set, chosen_names: set) -> dict:
    """PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: enkel opstellingen waarvan ELKE speler (op
    id of naam) in de gekozen tegenstander-selectie zit."""
    def _ok(p):
        return str(p.get("user_id")) in chosen_ids or " ".join(str(p.get("name") or "").lower().split()) in chosen_names
    return {
        k: v for k, v in unique_opponent_lineups.items()
        if all(_ok(p) for b in v.get("boards") or [] for p in (b.get("opponent_pair") or []))
    }
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11 - zie moduledocstring.
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner=False, max_entries=3)
def _cached_universe(ids: tuple, n_rot: int, mpr: int, max_lineups: int):
    """Alle opstellingen voor dit roster (alleen-lezen, gedeeld). Geeft (lijst, totaal_bekend, is_steekproef)."""
    return mu.enumerate_universe(list(ids), n_rot, mpr, max_lineups=max_lineups)
def _bundle_signature(bundle: dict) -> tuple:
    out = []
    for fx in (bundle or {}).get("previous_fixtures") or []:
        f = fx.get("fixture") or {}
        out.append((str(f.get("date_text") or ""), len(fx.get("boards") or [])))
    return tuple(out)
def _universe_weights(bundle: dict, keys: list, ids: tuple):
    """Model-gewicht (genormaliseerd over het hele universum) per opstelling, of None zonder model / bij een te lange
    rekentijd / bij een fout."""
    if olm is None or not keys:
        return None
    try:
        stats = olm.build_opponent_stats(bundle)
        roster = {str(p.get("user_id")) for p in (bundle.get("unique_players") or []) if p.get("user_id")}
        roster |= set(ids)
        roster_uids = sorted(roster)
        logs = mu.score_keys(keys, lambda k: olm.full_lineup_log_score(stats, list(k), roster_uids), _SCORE_TIME_BUDGET)
        if logs is None:
            return None
        return olm.softmax_weights(logs)
    except Exception:  # noqa: BLE001
        return None
def _select_theoretical_lineups(bundle: dict, opp: dict, ctx: dict, n_own_est: int, hist_keys: list) -> dict:
    """Alle mogelijke tegenstander-opstellingen -> de doorgerekende deelverzameling. Gecachet in session_state.
    Geeft {"boards": [boards per gekozen opstelling], "universe_weights": dict|None, "info": {...}}."""
    ids = tuple(ctx["ids"])
    n_rot = ctx["n_rot"]
    ranks, ps, names = ctx["ranks"], ctx["ps"], ctx["names"]
    k_target = max(_OPP_SUBSET_MIN, min(_OPP_SUBSET_MAX, _TARGET_MATCHUPS // max(1, int(n_own_est))))
    sig = (
        ids, n_rot, tuple(sorted(ranks.items())), tuple(sorted(ps.items())), _bundle_signature(bundle),
        k_target, len(hist_keys), olm is not None,
    )
    cache_key = f"universe_sel_v1_{opp['ploeg_id']}"
    cached = st.session_state.get(cache_key)
    if cached and cached.get("sig") == sig:
        return cached["result"]
    def rank_fn(pairs):
        return _rank_pairs_with_padelstat_tiebreak(pairs, ranks, ps)
    universe, total_known, is_sample = _cached_universe(ids, n_rot, MATCHES_PER_ROTATION, _UNIVERSE_MAX_LINEUPS)
    keys = [mu.ordered_key(l, rank_fn) for l in universe]
    lineup_by_key = dict(zip(keys, universe))
    weights = _universe_weights(bundle, keys, ids)
    weight_reason = "" if weights is not None else ("geen model beschikbaar" if olm is None else "het model was te traag voor alle opstellingen")
    hist_canon = {mu.canon_key(h, MATCHES_PER_ROTATION) for h in hist_keys}
    pool = [k for k in keys if mu.canon_key(k, MATCHES_PER_ROTATION) not in hist_canon]
    chosen, mass, n_extra = mu.select_subset(pool, weights, k_target, MATCHES_PER_ROTATION)
    boards = [
        _build_opponent_boards_and_points([list(rot) for rot in lineup_by_key[k]], names, ranks, ps)
        for k in chosen
    ]
    info = {
        "n_universe": len(keys), "universe_complete": total_known and not is_sample, "n_used": len(chosen),
        "mass": mass, "n_extra": n_extra, "weighted": weights is not None, "k_target": k_target,
        "weight_reason": weight_reason,
        "n_hist_excluded_dups": len(keys) - len(pool),  # al door een effectief gespeelde opstelling vertegenwoordigd
    }
    result = {"boards": boards, "universe_weights": weights, "info": info, "ctx": ctx}
    st.session_state[cache_key] = {"sig": sig, "result": result}
    return result
def _selection_caption(info: dict) -> str:
    delen = []
    if info["universe_complete"]:
        delen.append(f"Met dit roster zijn **{info['n_universe']:,}** verschillende tegenstander-opstellingen mogelijk")
    else:
        delen.append(
            f"Met dit roster zijn er zo veel tegenstander-opstellingen mogelijk dat een gespreide steekproef van "
            f"**{info['n_universe']:,}** is gebruikt"
        )
    if info["n_used"] >= info["n_universe"] - info.get("n_hist_excluded_dups", 0):
        delen.append("alle zijn doorgerekend")
    elif info["weighted"] and info["mass"] is not None:
        delen.append(
            f"de **{info['n_used']:,}** meest waarschijnlijke (samen {info['mass'] * 100:.0f}% van het gewicht) zijn "
            "doorgerekend, aangevuld zodat elk mogelijk koppel in elke rotatie minstens 1x voorkomt"
        )
    else:
        delen.append(
            f"**{info['n_used']:,}** gelijkmatig gespreide zijn doorgerekend ({info.get('weight_reason') or 'zonder gewichten'}), "
            "aangevuld zodat elk mogelijk koppel in elke rotatie minstens 1x voorkomt"
        )
    return (
        "; ".join(delen) + ". Een specifieke combinatie nodig? Filter in 'Alle matchups' op spelers of koppels: "
        "dat rekent exact over alle opstellingen."
    )
def render_opponent_scenario_setup(
    bundle, opp, total_boards, synergy_fn, player_ratings, official_ranks_strict,
    opponent_ratings, available_ids, max_per_player, name_lookup_global=None,
    tournament_rules_dict=None,
) -> dict:
    """PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04: eerste helft van de vroegere _render_all_valid_matchups():
    tegenstander-roster-keuze, de tegenstander-opstellingen, het statistisch model en de scenario-matrix.
    Geeft {"unique_opponent_lineups", "model_weights", "model_stats", "opp_ctx", "universe_weights"} terug.
    PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: ALLE mogelijke opstellingen (zie moduledocstring)."""
    st.divider()
    st.markdown('<div class="section-header">Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "Kies WIE van de tegenstander waarschijnlijk beschikbaar is. We bepalen daaruit de meest "
        "relevante tegenstander-opstellingen (scenario's) - gebruik die hierna in de Rotatieplanner."
    )
    historical_boards_with_labels = _historical_opponent_boards_list(bundle)
    unique_players = bundle.get("unique_players", []) or []
    theoretical_boards: list = []
    opp_ctx = None
    universe_weights = None
    if not unique_players:
        st.info("Nog geen tegenstander-spelers gekend om theoretische opstellingen voor te berekenen.")
    else:
        opp_labels = [p.get("name", "?") for p in unique_players]
        opp_label_to_id = {p.get("name", "?"): str(p.get("user_id")) for p in unique_players}
        default_opp_labels = opp_labels
        st.caption(
            f"Standaard staan alle {len(opp_labels)} bekende tegenstander-spelers geselecteerd, zodat ALLE "
            "mogelijke opstellingen automatisch worden meegenomen. Verklein de lijst enkel als je zeker weet "
            "dat bepaalde spelers niet zullen meespelen."
        )
        chosen_opp_labels = st.multiselect(
            "Beschikbare tegenstander-spelers", opp_labels, default=default_opp_labels,
            key=f"theoretical_opp_players_{opp['ploeg_id']}",
        )
        chosen_opp_ids = [opp_label_to_id[lbl] for lbl in chosen_opp_labels]
        needed = 2 * total_boards
        if len(chosen_opp_ids) < 2 * MATCHES_PER_ROTATION:
            st.info(
                f"Selecteer minstens {2 * MATCHES_PER_ROTATION} tegenstander-spelers om theoretische scenario's toe te "
                "voegen. De historische opstelling(en) blijven sowieso al in de tabel staan."
            )
        else:
            chosen_opp_players = [p for p in unique_players if str(p.get("user_id")) in chosen_opp_ids]
            opponent_official_ranks = _opponent_official_ranks(chosen_opp_ids)
            missing_opp_official = [pid for pid in chosen_opp_ids if pid not in opponent_official_ranks]
            if missing_opp_official:
                opp_names = [p.get("name", str(p.get("user_id"))) for p in chosen_opp_players if str(p.get("user_id")) in missing_opp_official]
                st.caption(
                    f"Geen officieel klassement gekend voor: {', '.join(opp_names)} - behandeld als "
                    "'onbekende sterkte' bij het genereren van theoretische opstellingen."
                )
            opponent_padelstat_ratings = _opponent_padelstat_ratings(bundle)
            # Informatief: het verwachte aantal matchen per speler (beperkt de opstellingen NIET meer).
            max_per_opp = max(1, int(total_boards) // 2)
            default_opp_max = (
                _expected_matches_per_player(bundle, chosen_opp_ids, needed, max_per_opp)
                or _default_opponent_max_per_player(chosen_opp_ids, needed)
            )
            delen = []
            for pid in sorted(chosen_opp_ids, key=lambda u: -int(default_opp_max.get(u, 0))):
                naam = next((p.get("name", pid) for p in chosen_opp_players if str(p.get("user_id")) == pid), pid)
                rk, ps_ = opponent_official_ranks.get(pid), opponent_padelstat_ratings.get(pid)
                info_txt = " · ".join(x for x in [f"P{int(rk)}" if rk is not None else "P?",
                                                  f"ps {int(ps_)}" if ps_ is not None else ""] if x)
                delen.append(f"{naam} ({info_txt}): **{int(default_opp_max.get(pid, 0))}**")
            st.markdown("Verwacht aantal matchen per tegenstander-speler (enkel ter info): " + " · ".join(delen))
            names = {str(p.get("user_id")): p.get("name", str(p.get("user_id"))) for p in chosen_opp_players}
            opp_ctx = {
                "ids": sorted(str(i) for i in chosen_opp_ids), "names": names,
                "ranks": opponent_official_ranks, "ps": opponent_padelstat_ratings,
                "n_rot": max(1, int(total_boards) // MATCHES_PER_ROTATION),
            }
            hist_keys = []
            for _label, hboards in historical_boards_with_labels:
                hk = _opponent_lineup_key_of(hboards)
                if hk is not None:
                    hist_keys.append(hk)
            # Gecachet: deze opsomming kan seconden duren en draaide anders bij ELKE herlading (ook bij elke
            # filterkeuze) opnieuw. PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11.
            est_key = f"n_own_est_v1_{opp['ploeg_id']}"
            est_sig = (tuple(sorted(str(a) for a in available_ids)), tuple(sorted(max_per_player.items())))
            est_cached = st.session_state.get(est_key)
            if est_cached and est_cached.get("sig") == est_sig:
                n_own_est = est_cached["n"]
            else:
                try:
                    n_structs, _tr = _enumerate_rotation_aware_pairings([str(a) for a in available_ids], max_per_player)
                    n_own_est = max(1, int(len(n_structs) * 1.5))
                except Exception:  # noqa: BLE001
                    n_own_est = 100
                st.session_state[est_key] = {"sig": est_sig, "n": n_own_est}
            sel_result = _select_theoretical_lineups(bundle, opp, opp_ctx, n_own_est, hist_keys)
            theoretical_boards = sel_result["boards"]
            universe_weights = sel_result["universe_weights"]
            st.caption(_selection_caption(sel_result["info"]))
    unique_opponent_lineups = _collect_unique_opponent_lineups(historical_boards_with_labels, theoretical_boards)
    # PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: niet-geselecteerde spelers -> opstelling weg.
    gekozen_namen = st.session_state.get(f"theoretical_opp_players_{opp['ploeg_id']}")
    if unique_players and gekozen_namen is not None:
        gekozen_ids = {str(p.get("user_id")) for p in unique_players if p.get("name", "?") in set(gekozen_namen)}
        gekozen_norm = {" ".join(str(n).lower().split()) for n in gekozen_namen}
        n_voor = len(unique_opponent_lineups)
        unique_opponent_lineups = _filter_lineups_to_roster(unique_opponent_lineups, gekozen_ids, gekozen_norm)
        if len(unique_opponent_lineups) < n_voor:
            st.caption(
                f"{n_voor - len(unique_opponent_lineups)} opstelling(en) weggelaten omdat er een niet-geselecteerde "
                "tegenstander-speler in staat (ook eerder effectief gespeelde opstellingen)."
            )
    if not unique_opponent_lineups:
        st.info("Nog geen tegenstander-opstelling gekend of berekend om tegen te analyseren.")
        return {"unique_opponent_lineups": {}, "model_weights": None, "model_stats": None,
                "opp_ctx": opp_ctx, "universe_weights": universe_weights}
    # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: voorspelde kans per scenario (gecachet per verzameling).
    mw_key = f"model_weights_v1_{opp['ploeg_id']}"
    mw_sig = (frozenset(unique_opponent_lineups.keys()), _bundle_signature(bundle))
    mw_cached = st.session_state.get(mw_key)
    if mw_cached and mw_cached.get("sig") == mw_sig:
        model_weights, model_stats = mw_cached["weights"], mw_cached["stats"]
    else:
        model_weights, model_stats = _model_weights_for_lineups(bundle, unique_opponent_lineups)
        st.session_state[mw_key] = {"sig": mw_sig, "weights": model_weights, "stats": model_stats}
    if model_weights:
        _render_predicted_opponent_lineups(unique_opponent_lineups, model_weights, model_stats)
    # PADEL_ANALYSIS_SCENARIO_MATRIX_2026-10-03: de matrix neemt enkel de meest waarschijnlijke scenario's;
    # een beperkte verzameling (zoals voorheen) volstaat en houdt ze snel.
    matrix_lineups = unique_opponent_lineups
    if model_weights and len(unique_opponent_lineups) > 300:
        top = sorted(unique_opponent_lineups, key=lambda k: -(model_weights.get(k, 0.0)))[:300]
        top_set = set(top) | {k for k, v in unique_opponent_lineups.items() if v.get("is_historical")}
        matrix_lineups = {k: v for k, v in unique_opponent_lineups.items() if k in top_set}
    if lsm is not None:
        try:
            lsm.render_scenario_matrix(
                matrix_lineups, model_weights, available_ids, max_per_player,
                int(total_boards), synergy_fn, player_ratings, official_ranks_strict,
                opponent_ratings, tournament_rules_dict, name_lookup_global or {}, str(opp["ploeg_id"]),
                model_stats=model_stats,
            )
        except Exception as exc:  # noqa: BLE001 - nooit de rest van de pagina breken
            st.warning(f"Scenario-analyse mislukt: {type(exc).__name__}: {exc}")
    return {
        "unique_opponent_lineups": unique_opponent_lineups, "model_weights": model_weights,
        "model_stats": model_stats, "opp_ctx": opp_ctx, "universe_weights": universe_weights,
    }
def _opponent_lineup_key_of(boards: list):
    """Zelfde sleutel als lineup_rotation._opponent_lineup_key(): tuple van frozensets van user_id's per match."""
    pairs = []
    for b in boards or []:
        uids = frozenset(str(p.get("user_id")) for p in (b.get("opponent_pair") or []) if p.get("user_id"))
        if len(uids) == 2:
            pairs.append(uids)
    return tuple(pairs) if pairs else None
def _run_exact_search(
    setup: dict, sel: dict, own_fixed_key, own_options: list, synergy_fn, player_ratings: dict,
    official_ranks_strict: dict, opponent_ratings: dict, search_sig, cache_key: str,
):
    """Exacte zoekopdracht (gecachet): geeft (matchups, info) terug."""
    ctx = setup.get("opp_ctx")
    store = st.session_state.setdefault(cache_key, {})
    ck = (
        search_sig, tuple(sorted(sel.get("own_players") or [])), tuple(sorted(sel.get("own_pairs") or [])),
        tuple(sorted(sel.get("opp_players") or [])), tuple(sorted(sel.get("opp_pairs") or [])),
        own_fixed_key, bool(sel.get("vs")),
    )
    if ck in store:
        return store[ck]
    if ctx is None:
        res = ([], {"n_own": 0, "n_opp_matching": 0, "n_opp_used": 0, "n_computed": 0, "truncated": False,
                    "enum_truncated": False, "n_hist": 0})
        return res
    names, ranks, ps = ctx["names"], ctx["ranks"], ctx["ps"]
    if own_fixed_key is not None:
        own_fixed_key = frozenset(frozenset(str(x) for x in p) for p in own_fixed_key)
    must_players = [k[3:] for k in sel.get("opp_players") or [] if k.startswith("id:")]
    must_pairs = []
    for pk in sel.get("opp_pairs") or []:
        parts = [x[3:] for x in pk.split("|") if x.startswith("id:")]
        if len(parts) == 2:
            must_pairs.append(frozenset(parts))
    unique = setup.get("unique_opponent_lineups") or {}
    hist_info = {k: v for k, v in unique.items() if v.get("is_historical")}
    def rank_fn(pairs):
        return _rank_pairs_with_padelstat_tiebreak(pairs, ranks, ps)
    def build_boards(lineup):
        return _build_opponent_boards_and_points([list(rot) for rot in lineup], names, ranks, ps)
    def compute(own_pairs, boards):
        return _compute_matchup(own_pairs, boards, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings)
    with st.spinner("Zoeken over alle opstellingen (eigen x tegenstander, beide rotaties)..."):
        results, info = mu.search_exact(
            own_options=own_options, opp_ids=ctx["ids"], n_rotations=ctx["n_rot"],
            matches_per_rotation=MATCHES_PER_ROTATION,
            own_players=sel.get("own_players") or [], own_pair_keys=sel.get("own_pairs") or [],
            fixed_key=own_fixed_key, must_opp_pairs=must_pairs, must_opp_players=must_players,
            rank_pairs_fn=rank_fn, weights=setup.get("universe_weights"), hist_info=hist_info,
            build_boards_fn=build_boards, compute_fn=compute, make_matchup_fn=_make_matchup,
            cap=_SEARCH_MAX_COMPUTED, require_vs=bool(sel.get("vs")), time_budget=_SEARCH_TIME_BUDGET,
        )
    if len(store) > 12:
        store.clear()
    store[ck] = (results, info)
    return results, info
def render_matchup_overview(
    setup: dict, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, sel_player_id, tournament_rules_dict=None, rules_label=None,
):
    """PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04: tweede helft van de vroegere _render_all_valid_matchups(): de
    knop "Bereken alle geldige matchups" + de groepenweergave, nu onder de kop "Alle matchups".
    PADEL_ANALYSIS_MATCHUP_FILTERS_2026-10-10: filters + padelstat in de koppel-tabellen.
    PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: filters rekenen exact over de volledige set."""
    unique_opponent_lineups = (setup or {}).get("unique_opponent_lineups") or {}
    model_weights = (setup or {}).get("model_weights")
    universe_weights = (setup or {}).get("universe_weights")
    if not unique_opponent_lineups:
        return []
    st.divider()
    st.markdown('<div class="section-header">Alle matchups</div>', unsafe_allow_html=True)
    st.caption(
        "Alle reglementair geldige, rotatie-veilige combinaties van onze opstelling tegen de "
        "doorgerekende tegenstander-opstellingen, gemiddeld over de tegenstander-scenario's. Zoek je een "
        "specifieke combinatie (bv. ons koppel tegen een bepaald tegenstander-koppel)? Gebruik de filters: die "
        "rekenen exact over alle opstellingen. De opstelling die de tegenstander vorige keer "
        "effectief speelde is gemarkeerd in de kolom 'Vorige keer'."
    )
    include_non_compliant = False
    settings_signature = (
        tuple(sorted(available_ids)),
        tuple(sorted(max_per_player.items())),
        int(total_boards),
        tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
        frozenset(unique_opponent_lineups.keys()),
    )
    ratings_signature = (
        tuple(sorted(player_ratings.items())),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(opponent_ratings.items())),
    )
    signature = (settings_signature, ratings_signature)
    # Nieuwe sleutels (v4): het resultaat heeft 5 delen en elke matchup heeft "point_probs" en "opp_probability".
    result_key = f"scenario_result_v4_{opp['ploeg_id']}"
    sig_key = f"scenario_result_sig_v4_{opp['ploeg_id']}"
    clicked = st.button(
        "Bereken alle geldige matchups", type="primary", key=f"compute_scenarios_{opp['ploeg_id']}",
        help="Berekent pas NA deze klik - wijzig gerust eerst alle instellingen hierboven zonder dat de "
             "pagina telkens opnieuw moet rekenen.",
    )
    if clicked:
        with st.spinner(f"Alle geldige matchups doorrekenen ({len(unique_opponent_lineups)} tegenstander-opstelling(en))..."):
            st.session_state[result_key] = _build_all_valid_matchups(
                unique_opponent_lineups, available_ids, max_per_player, synergy_fn,
                player_ratings, official_ranks_strict, opponent_ratings, tournament_rules_dict,
                include_non_compliant_variants=include_non_compliant,
                opponent_weight_override=model_weights, opponent_probability=universe_weights,
            )
            st.session_state[sig_key] = signature
    stored = st.session_state.get(result_key)
    if stored is None:
        st.info("Stel hierboven alles in en klik op **'Bereken alle geldige matchups'** om de tabel te vullen.")
        return []
    stored_signature = st.session_state.get(sig_key)
    if stored_signature != signature:
        stored_settings = stored_signature[0] if stored_signature else None
        if stored_settings != settings_signature:
            st.warning(
                "De instellingen zijn gewijzigd sinds de laatste berekening - de tabel hieronder toont nog "
                "het VORIGE resultaat. Klik opnieuw op 'Bereken alle geldige matchups' om bij te werken."
            )
        else:
            st.warning(
                "De padelstat- en/of klassementwaarden zijn intussen ververst op de achtergrond sinds je "
                "laatste berekening - de tabel hieronder klopt dus mogelijk niet meer met de actuele data. "
                "Klik opnieuw op 'Bereken alle geldige matchups' om de analyse bij te werken."
            )
    all_matchups, truncated, total_seen, build_diag, groups = stored
    st.divider()
    with st.expander("Diagnostiek: hoeveel combinaties werden er precies doorgerekend?", expanded=False):
        st.write(f"- Rotatie-veilige eigen koppelverdelingen (totaal enumereerd): **{build_diag['own_structures_total']}**")
        st.write(f"- Daaruit gegenereerde volgorde-varianten (incl. eventuele swap-varianten): **{build_diag['own_variants_generated']}**")
        st.write(f"- Daarvan uitgesloten door de reglementaire puntengrens: **{build_diag['own_excluded_by_rules']}**")
        st.write(f"- Reglementair geldige eigen combinaties (puntengrens OK): **{build_diag['own_valid']}**")
        st.write(f"- Doorgerekende tegenstander-opstellingen (na samenvoegen/filteren): **{len(unique_opponent_lineups)}**")
        st.write(f"- Totaal doorgerekende matchup-kandidaten (voor ontdubbeling): **{total_seen}**")
        st.write(f"- Effectief doorgerekende matchups: **{build_diag.get('matchups_computed', 0)}**")
        st.write(f"- Unieke eigen opstellingen (groepen): **{build_diag.get('own_groups', 0)}**")
        st.write(f"- Bewaarde rijen (beste {_KEEP_PER_GROUP} + slechtste + historische per groep): **{len(all_matchups)}**")
        st.caption(
            "Puntenkans en de weging op tegenstander-opstellingen: zie de uitleg boven "
            "'Onze opstellingen' hieronder."
        )
    if truncated:
        st.warning(
            f"Meer dan {_MAX_COMPUTED_MATCHUPS:,} combinaties - de berekening werd daar gestopt. "
            "Verklein de spelersselectie of het tegenstander-roster voor een volledige dekking."
        )
    st.caption(
        f"**{build_diag.get('matchups_computed', 0):,}** matchups doorgerekend over "
        f"**{build_diag.get('own_groups', 0)}** eigen opstellingen, gesorteerd van hoogste naar laagste "
        "gewogen kans op 2 punten."
    )
    if not all_matchups:
        st.info(
            "Geen enkele matchup voldoet aan de reglementaire puntengrens per rotatie, of er is geen "
            "combinatie mogelijk zonder een speler dubbel in dezelfde rotatie te plaatsen. Controleer de "
            "gekozen afdeling en het aantal beschikbare spelers."
        )
        return []
    _render_save_analysis_button(
        all_matchups, opp, available_ids, name_lookup_global, total_boards, max_per_player, sel_player_id,
    )
    st.divider()
    # PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11: ALLE eigen opstellingen (voor de filterlijsten en de exacte
    # zoekopdracht), gecachet per instellingen.
    own_key = f"own_options_v1_{opp['ploeg_id']}"
    own_cached = st.session_state.get(own_key)
    if own_cached and own_cached.get("sig") == signature:
        own_options = own_cached["options"]
    else:
        own_options, _own_diag, _own_tr = _collect_valid_own_options(
            available_ids, max_per_player, official_ranks_strict, player_ratings, tournament_rules_dict,
        )
        st.session_state[own_key] = {"sig": signature, "options": own_options}
    opts = _filter_option_lists(own_options, name_lookup_global, (setup or {}).get("opp_ctx"))
    search_cache_key = f"search_cache_v1_{opp['ploeg_id']}"
    def run_search(sel, own_fixed_key=None):
        return _run_exact_search(
            setup, sel, own_fixed_key, own_options, synergy_fn, player_ratings, official_ranks_strict,
            opponent_ratings, signature, search_cache_key,
        )
    _render_own_lineup_groups_with_opponents(
        groups, name_lookup_global, ploeg_key=str(opp['ploeg_id']),
        own_ps=player_ratings, opp_ps=opponent_ratings,
        filter_ctx={"opts": opts, "search": run_search if (setup or {}).get("opp_ctx") else None},
    )
    with st.expander("Platte tabel (alle matchups los naast elkaar, sorteerbaar per kolom)", expanded=False):
        plat_prefix = f"flat_{opp['ploeg_id']}"
        has_opp_ctx = bool((setup or {}).get("opp_ctx"))
        plat_sel = _render_filter_widgets(opts, plat_prefix, own=True, opp=has_opp_ctx)
        if _has_filter(plat_sel):
            results, sinfo = run_search(plat_sel, None)
            _render_search_results(
                results, sinfo, name_lookup_global, player_ratings, opponent_ratings, f"{plat_prefix}_res",
            )
        else:
            show_all_key = f"all_matchups_showall_{opp['ploeg_id']}"
            show_all = st.checkbox(
                f"Toon alle {len(all_matchups)} matchups (i.p.v. de beste {_MATCHUP_DISPLAY_DEFAULT_N})",
                key=show_all_key,
            ) if len(all_matchups) > _MATCHUP_DISPLAY_DEFAULT_N else False
            display_matchups = all_matchups if show_all else all_matchups[:_MATCHUP_DISPLAY_DEFAULT_N]
            table_rows, board_column_names = _matchups_to_table_rows(
                display_matchups, name_lookup_global, own_ps=player_ratings, opp_ps=opponent_ratings,
            )
            column_config, column_order = _matchup_table_column_config(table_rows, board_column_names)
            st.dataframe(
                table_rows, use_container_width=True, hide_index=True,
                column_config=column_config, column_order=column_order,
            )
            if not show_all and len(all_matchups) > len(display_matchups):
                st.caption(f"Beste {len(display_matchups)} van {len(all_matchups)} bewaarde matchups getoond - vink hierboven aan om alles te zien.")
        st.caption(
            "Elk speler-duo staat in zijn eigen kolom ('Ons duo' / 'Tegenstander'), met tussen haakjes de "
            "padelstat (ps) van elke speler, naast een aparte winkans-kolom per match. 'Kans 2p/1p/0p' toont "
            "de exacte kans op dat aantal competitiepunten voor DEZE ene tegenstander-opstelling (dus "
            "ongewogen - de weging over alle scenario's zit enkel in de groepstitel). 'Kans opstelling' is hoe "
            "waarschijnlijk het model die tegenstander-opstelling vindt. 'Rotatie1 M1' = Match 1 van rotatie 1 "
            "(sterkste duo volgens officieel klassement, art. 6.6), 'Rotatie1 M2' = Match 2, enz."
        )
    st.divider()
    # De AI-sectie werkt, zoals voorheen, op de beste 5 matchups van de volledige (ongefilterde) lijst.
    ai_matchups = list(all_matchups)[:5]
    ai_history_key = f"all_matchups_chat_history_v2_{opp['ploeg_id']}"
    if ai_history_key not in st.session_state:
        st.session_state[ai_history_key] = []
    ai_history = st.session_state[ai_history_key]
    if taa is not None and report is not None:
        col_ai_start, col_ai_clear = st.columns([3, 1])
        with col_ai_start:
            ai_start_label = "AI-inzicht over de beste matchups" if not ai_history else "AI-inzicht opnieuw genereren (nieuw gesprek)"
            if st.button(ai_start_label, key=f"all_matchups_ai_{opp['ploeg_id']}"):
                with st.spinner("AI analyseert..."):
                    try:
                        antwoord = taa.analyze_lineup_options(report, ai_matchups, name_lookup_global)
                    except Exception as exc:
                        antwoord = f"Mislukt: {exc}"
                st.session_state[ai_history_key] = [{"role": "assistant", "content": antwoord}]
                st.rerun()
        with col_ai_clear:
            if ai_history and st.button("Nieuw gesprek", key=f"all_matchups_ai_clear_{opp['ploeg_id']}"):
                st.session_state[ai_history_key] = []
                st.rerun()
        if ai_history:
            st.caption("Gesprek tot nu toe:")
            for msg in ai_history:
                role_label = "Jij" if msg["role"] == "user" else "AI"
                with st.container(border=True):
                    st.markdown(f"**{role_label}**")
                    st.markdown(msg["content"])
            followup_question = st.text_area(
                "Doorvraag", key=f"all_matchups_ai_followup_{opp['ploeg_id']}", height=70,
                label_visibility="collapsed", placeholder="Bv. En wat als Nico niet kan spelen?",
            )
            if st.button("Vraag door", key=f"all_matchups_ai_followup_btn_{opp['ploeg_id']}"):
                if not followup_question.strip():
                    st.warning("Typ eerst een vraag.")
                else:
                    with st.spinner("AI denkt na..."):
                        try:
                            vervolg = taa.analyze_lineup_options(
                                report, ai_matchups, name_lookup_global, history=ai_history,
                            )
                        except Exception as exc:
                            vervolg = f"Mislukt: {exc}"
                    st.session_state[ai_history_key] = ai_history + [
                        {"role": "user", "content": followup_question.strip()},
                        {"role": "assistant", "content": vervolg},
                    ]
                    st.rerun()
    return all_matchups
def _render_all_valid_matchups(
    bundle, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, sel_player_id, tournament_rules_dict=None, rules_label=None,
):
    """PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04: dunne, backward-compatible combinator - roept
    render_opponent_scenario_setup() en render_matchup_overview() ACHTER elkaar aan."""
    setup = render_opponent_scenario_setup(
        bundle, opp, total_boards, synergy_fn, player_ratings, official_ranks_strict,
        opponent_ratings, available_ids, max_per_player, name_lookup_global=name_lookup_global,
        tournament_rules_dict=tournament_rules_dict,
    )
    return render_matchup_overview(
        setup, opp, available_ids, max_per_player, total_boards, synergy_fn,
        player_ratings, official_ranks_strict, opponent_ratings, report,
        name_lookup_global, sel_player_id,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    )
