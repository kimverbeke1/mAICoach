"""
matchup_universe.py - de VOLLEDIGE verzameling tegenstander-opstellingen, de keuze van een
representatieve deelverzameling en een EXACTE zoekopdracht op specifieke koppels/spelers.
Zuivere logica: geen Streamlit, geen Firestore. De rekenkern (winkansen per match) wordt als functie
meegegeven, zodat alles offline te testen is (zie test_matchup_completeness.py).
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_COMPLETENESS_2026-10-11 (op verzoek van Kim: "bij de matchup niet alle
combinaties gemaakt [...] Bvb Klaudia en Evy hebben in de 2de rotatie tegen Isis gespeeld tegen
Gallach en Serruys")
--------------------------------------------------------------------------
Oorzaken in de oude opbouw (lineup_matchup_table.py + lineup_rotation.py), alle drie bevestigd in de code:
  A. AFKAPPING OP VOLGORDE: _generate_theoretical_opponent_boards_with_repeats() nam enkel de EERSTE 300
     opstellingen (structures[:300]). De opsommng loopt op gesorteerde speler-id's, dus de spelers met de
     hoogste id's verdwijnen als eerste uit rotatie 2. (Gemeten op 8 spelers, elk 1 match: 630 opstellingen,
     de eerste 300 missen 7 van de 56 (rotatie, koppel)-combinaties - allemaal in rotatie 2.)
  B. SPELERS MET 0 VERWACHTE MATCHEN: de opstellingen werden opgebouwd met een vast aantal matchen per
     tegenstander-speler (_expected_matches_per_player, afgerond naar het totaal). Wie afrondde naar 0 kwam in
     GEEN ENKELE opstelling voor; wie 1 kreeg kon nooit 2 matchen spelen (zoals Galach, die in R1 en R2 speelde).
  C. ENKEL BEWAARDE RIJEN: per eigen opstelling bleven enkel de beste 25 + de slechtste + de historische
     rijen over. Filters (en de tabel) toonden dus enkel die - een specifieke combinatie viel erbuiten.
Aanpak hier:
  1. enumerate_lineups(): ALLE rotatie-veilige opstellingen (elke rotatie 2 disjuncte koppels, een koppel
     speelt maar 1x per ontmoeting), zonder vast aantal per speler. Een speler mag dus 0, 1 of 2 matchen spelen.
  2. select_subset(): voor de samenvattende groepen rekent men niet elke opstelling door (kan tienduizenden
     zijn): de meest waarschijnlijke (model) + zoveel extra dat ELK mogelijk koppel in ELKE rotatie minstens
     1x voorkomt. De dekking (aandeel van het gewicht) wordt getoond.
  3. search_exact(): zodra je filtert op spelers/koppels wordt er EXACT gerekend over alle opstellingen die aan
     je filter voldoen (eigen opstellingen x tegenstander-opstellingen), niet over de bewaarde rijen.
"""
import itertools
import random
import time

_UNIVERSE_SHUFFLE_SEED = 20261011


def pair_key(ids) -> str:
    """Stabiele sleutel van een koppel: de id's gesorteerd, met '|' ertussen."""
    return "|".join(sorted(str(i) for i in ids))


def all_perfect_matchings(seq: list) -> list:
    """Alle manieren om een even aantal elementen in koppels te verdelen (als lijst van frozensets)."""
    if len(seq) == 0:
        return [[]]
    if len(seq) % 2 != 0:
        return []
    first, rest = seq[0], seq[1:]
    out: list = []
    for i, partner in enumerate(rest):
        remaining = rest[:i] + rest[i + 1:]
        for sub in all_perfect_matchings(remaining):
            out.append([frozenset({first, partner})] + sub)
    return out


def _canon_rotation(matching) -> tuple:
    return tuple(sorted(matching, key=lambda p: tuple(sorted(p))))


def enumerate_lineups(
    player_ids, n_rotations: int, matches_per_rotation: int = 2,
    must_pairs=None, must_players=None, max_lineups: int = 60_000,
    node_budget: int = 1_500_000, shuffle_seed=None, must_at=None,
) -> tuple:
    """Alle opstellingen als tuple van rotaties; een rotatie = tuple van `matches_per_rotation` koppels
    (frozensets van speler-id-strings, gesorteerd). Regels: binnen een rotatie spelen alle spelers verschillend,
    en een koppel speelt hoogstens 1x per ontmoeting. GEEN vast aantal matchen per speler.
    `must_pairs` ({frozenset}) / `must_players` ({id}): enkel opstellingen waarin die voorkomen (met snoeien).
    `must_at` ({rotatie-index: frozenset-koppel}): dat koppel moet in PRECIES die rotatie spelen.
    Geeft (lijst, afgekapt) terug. `afgekapt` = max_lineups of node_budget bereikt."""
    ids = sorted({str(p) for p in player_ids})
    need = matches_per_rotation * 2
    must_pairs = {frozenset(str(x) for x in p) for p in (must_pairs or ())}
    must_players = {str(p) for p in (must_players or ())}
    must_at = {int(r): frozenset(str(x) for x in p) for r, p in (must_at or {}).items()}
    if len(ids) < need or n_rotations < 1:
        return [], False
    combos = list(itertools.combinations(ids, need))
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(combos)
    matchings_by_combo = {c: all_perfect_matchings(list(c)) for c in combos}
    out: list = []
    nodes = [0]
    trunc = [False]

    def rec(r, used_pairs, used_players, so_far):
        if trunc[0]:
            return
        nodes[0] += 1
        if nodes[0] > node_budget:
            trunc[0] = True
            return
        if r == n_rotations:
            if must_pairs <= used_pairs and must_players <= used_players:
                out.append(tuple(so_far))
                if len(out) >= max_lineups:
                    trunc[0] = True
            return
        rem_after = n_rotations - r - 1
        for combo in combos:
            pl_after = used_players | set(combo)
            if len(must_players - pl_after) > rem_after * need:
                continue
            for matching in matchings_by_combo[combo]:
                if must_at and r in must_at and must_at[r] not in matching:
                    continue
                if any(p in used_pairs for p in matching):
                    continue
                used_after = used_pairs | set(matching)
                if len(must_pairs - used_after) > rem_after * matches_per_rotation:
                    continue
                so_far.append(_canon_rotation(matching))
                rec(r + 1, used_after, pl_after, so_far)
                so_far.pop()
                if trunc[0]:
                    return

    rec(0, frozenset(), frozenset(), [])
    return out, trunc[0]


def enumerate_universe(player_ids, n_rotations, matches_per_rotation=2, max_lineups=60_000) -> tuple:
    """Alle opstellingen. Zijn het er meer dan `max_lineups`, dan een gelijkmatig gespreide (geschudde,
    vaste seed) steekproef i.p.v. de eerste N op volgorde. Geeft (lijst, totaal_bekend, is_steekproef)."""
    lineups, trunc = enumerate_lineups(player_ids, n_rotations, matches_per_rotation, max_lineups=max_lineups)
    if not trunc:
        return lineups, True, False
    sample, _ = enumerate_lineups(
        player_ids, n_rotations, matches_per_rotation, max_lineups=max_lineups,
        shuffle_seed=_UNIVERSE_SHUFFLE_SEED,
    )
    # Dekking garanderen: elk (rotatie, koppel) dat de steekproef mist, krijgt 1 opstelling waarin het voorkomt.
    ids = sorted({str(p) for p in player_ids})
    covered = {(r, p) for lineup in sample for r, rot in enumerate(lineup) for p in rot}
    for r in range(n_rotations):
        for a, b in itertools.combinations(ids, 2):
            pair = frozenset({a, b})
            if (r, pair) in covered:
                continue
            extra, _ = enumerate_lineups(
                ids, n_rotations, matches_per_rotation, max_lineups=1, must_at={r: pair},
            )
            if extra:
                sample.append(extra[0])
                covered |= {(rr, pp) for rr, rot in enumerate(extra[0]) for pp in rot}
    return sample, False, True


def ordered_key(lineup, rank_pairs_fn) -> tuple:
    """Platte sleutel in matchvolgorde (per rotatie het sterkste duo eerst, art. 6.6) - zoals
    lineup_rotation._opponent_lineup_key() ze maakt. `rank_pairs_fn(lijst_koppels) -> geordende lijst`."""
    return tuple(p for rot in lineup for p in rank_pairs_fn(list(rot)))


def canon_key(key, matches_per_rotation: int = 2) -> tuple:
    """Sleutel zonder volgorde BINNEN een rotatie (twee volgordes van dezelfde koppels zijn dezelfde opstelling)."""
    return tuple(frozenset(key[i:i + matches_per_rotation]) for i in range(0, len(key), matches_per_rotation))


def coverage(key, matches_per_rotation: int = 2) -> set:
    """{(rotatie-index, koppel)} die in deze opstelling voorkomen."""
    return {(i // matches_per_rotation, p) for i, p in enumerate(key)}


def select_subset(keys: list, weights, k: int, matches_per_rotation: int = 2) -> tuple:
    """Kies hoogstens ~k opstellingen: de meest waarschijnlijke (gewicht), zonder gewichten gelijkmatig gespreid,
    aangevuld zodat ELK mogelijk (rotatie, koppel) minstens 1x voorkomt. Geeft (gekozen, dekking_aandeel|None, n_extra)."""
    if len(keys) <= k:
        mass = 1.0 if weights else None
        return list(keys), mass, 0
    if weights:
        order = sorted(keys, key=lambda x: -weights.get(x, 0.0))
        chosen = order[:k]
    else:
        step = max(1, len(keys) // k)
        order = list(keys)
        chosen = order[::step][:k]
    chosen_set = set(chosen)
    covered: set = set()
    for key in chosen:
        covered |= coverage(key, matches_per_rotation)
    universe_cov: set = set()
    for key in keys:
        universe_cov |= coverage(key, matches_per_rotation)
    missing = universe_cov - covered
    n_extra = 0
    if missing:
        for key in order:
            if key in chosen_set:
                continue
            c = coverage(key, matches_per_rotation)
            if c & missing:
                chosen.append(key)
                chosen_set.add(key)
                n_extra += 1
                missing -= c
                if not missing:
                    break
    mass = None
    if weights:
        tot = sum(weights.get(x, 0.0) for x in keys) or 1.0
        mass = sum(weights.get(x, 0.0) for x in chosen) / tot
    return chosen, mass, n_extra


def score_keys(keys: list, score_fn, time_budget: float = 8.0):
    """{sleutel: log-score}. None als de tijdsgrens overschreden wordt (dan geen gewichten voor iedereen)."""
    t0 = time.perf_counter()
    out = {}
    for i, key in enumerate(keys):
        out[key] = score_fn(key)
        if (i & 255) == 255 and time.perf_counter() - t0 > time_budget:
            return None
    return out


def own_option_matches(opt_pairs, own_players=None, own_pair_keys=None, fixed_key=None) -> bool:
    """Voldoet deze eigen opstelling aan de filters? (alle gekozen spelers EN koppels moeten erin zitten)"""
    players = {str(x) for p in opt_pairs for x in p}
    if own_players and not {str(x) for x in own_players} <= players:
        return False
    if own_pair_keys and not set(own_pair_keys) <= {pair_key(p) for p in opt_pairs}:
        return False
    if fixed_key is not None:
        if frozenset(frozenset(str(x) for x in p) for p in opt_pairs) != fixed_key:
            return False
    return True


def key_matches(key, must_pairs, must_players) -> bool:
    """Bevat deze (platte) opstelling alle gevraagde koppels en spelers?"""
    pairs = {frozenset(str(x) for x in p) for p in key}
    players = {str(x) for p in key for x in p}
    return {frozenset(str(x) for x in p) for p in (must_pairs or ())} <= pairs and \
        {str(x) for x in (must_players or ())} <= players


def faces_each_other(own_ordered_pairs, key, own_pair_sets, opp_pair_sets) -> bool:
    """Spelen de gekozen eigen koppels TEGEN de gekozen tegenstander-koppels (zelfde match)? Match i van onze
    opstelling wordt gespeeld tegen match i van hun opstelling (zoals _compute_matchup() ze koppelt). Elk gekozen eigen
    koppel moet tegen een gekozen tegenstander-koppel spelen, en omgekeerd."""
    own_hit, opp_hit = set(), set()
    for op, tp in zip(own_ordered_pairs, key):
        fo = frozenset(str(x) for x in op)
        ft = frozenset(str(x) for x in tp)
        if fo in own_pair_sets and ft in opp_pair_sets:
            own_hit.add(fo)
            opp_hit.add(ft)
    return own_hit == own_pair_sets and opp_hit == opp_pair_sets


def search_exact(
    *, own_options, opp_ids, n_rotations, matches_per_rotation, own_players, own_pair_keys, fixed_key,
    must_opp_pairs, must_opp_players, rank_pairs_fn, weights, hist_info, build_boards_fn, compute_fn,
    make_matchup_fn, cap: int = 40_000, require_vs: bool = False, time_budget: float = 30.0,
) -> tuple:
    """EXACTE zoekopdracht: elke eigen opstelling die aan de eigen filters voldoet x elke tegenstander-opstelling
    die aan de tegenstander-filters voldoet. `hist_info` = {sleutel: info} van EFFECTIEF gespeelde opstellingen
    (zij worden meegenomen als ze aan de filter voldoen, ook als hun volgorde afwijkt).
    `weights` = {sleutel: kans} (mag None zijn). `require_vs`: de gekozen eigen en tegenstander-koppels moeten TEGEN
    ELKAAR spelen (dezelfde match); dat maakt de zoekopdracht veel specifieker.
    Worden het er meer dan `cap` (of duurt het langer dan `time_budget` seconden), dan worden de meest waarschijnlijke tegenstander-opstellingen gehouden en wordt dat in
    de info gemeld (nooit stil afgekapt). Geeft (matchups gesorteerd op verwachte gewonnen matchen, info) terug."""
    own_sel = [o for o in own_options if own_option_matches(o[0], own_players, own_pair_keys, fixed_key)]
    lineups, enum_trunc = enumerate_lineups(
        opp_ids, n_rotations, matches_per_rotation,
        must_pairs=must_opp_pairs, must_players=must_opp_players, max_lineups=120_000,
    )
    hist_info = hist_info or {}
    hist_canon = {}
    for hk, hinfo in hist_info.items():
        if key_matches(hk, must_opp_pairs, must_opp_players):
            hist_canon[canon_key(hk, matches_per_rotation)] = (hk, hinfo)
    entries = []  # (sleutel, boards|None, lineup|None, info|None)
    for hk, hinfo in hist_canon.values():
        entries.append((hk, hinfo.get("boards"), None, hinfo))
    for lineup in lineups:
        key = ordered_key(lineup, rank_pairs_fn)
        if canon_key(key, matches_per_rotation) in hist_canon:
            continue
        entries.append((key, None, lineup, None))
    w = weights or {}
    n_hist = len(hist_canon)
    own_pair_sets = {frozenset(x for x in pk.split("|")) for pk in (own_pair_keys or ())}
    opp_pair_sets = {frozenset(str(x) for x in p) for p in (must_opp_pairs or ())}
    vs_actief = bool(require_vs and own_pair_sets and opp_pair_sets)
    relevant = []
    for e in entries:
        opts = own_sel if not vs_actief else [
            o for o in own_sel if faces_each_other(o[0], e[0], own_pair_sets, opp_pair_sets)
        ]
        if opts:
            relevant.append((e, opts))
    n_opp_matching = len(relevant)
    relevant.sort(key=lambda r: (0 if r[0][3] is not None else 1, -w.get(r[0][0], 0.0)))
    results = []
    used = 0
    truncated = False
    timed_out = False
    t0 = time.perf_counter()
    for (key, boards, lineup, hinfo), opts in relevant:
        if results and len(results) + len(opts) > cap:
            truncated = True
            break
        if results and time.perf_counter() - t0 > time_budget:
            truncated = timed_out = True
            break
        if boards is None:
            boards = build_boards_fn(lineup)
        for opt in opts:
            computed = compute_fn(opt[0], boards)
            results.append(make_matchup_fn(opt, computed, hinfo, w.get(key)))
        used += 1
    results.sort(key=lambda m: (m.get("expected_boards_won") if m.get("expected_boards_won") is not None
                                else m.get("total_score", 0.0)), reverse=True)
    info = {
        "n_own": len(own_sel), "n_opp_matching": n_opp_matching, "n_opp_used": used,
        "n_computed": len(results), "truncated": truncated, "enum_truncated": enum_trunc, "n_hist": n_hist,
        "vs": vs_actief, "timed_out": timed_out, "seconds": time.perf_counter() - t0,
    }
    return results, info
