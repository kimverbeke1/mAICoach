"""
opponent_lineup_model.py - Eenvoudig, uitlegbaar statistisch model om de
opstelling van de TEGENSTANDER te voorspellen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02 (op verzoek van Kim: "hou
wel ook wat rekening met statistische gegevens zoals: persoon x speelt
bijna altijd met die persoon y. of persoon x speelt bijna altijd 1ste
match. combineer ook die data. We zijn bezig met statistische modellen die
niet te complex mogen zijn maar wel meerwaarde kunnen geven qua
voorspelling")
--------------------------------------------------------------------------
MODEL (bewust simpel - een "naive Bayes"-achtige score met Laplace-
smoothing, volledig gebaseerd op de eerdere ontmoetingen van DEZE
tegenstander dit seizoen, bundle["previous_fixtures"]):

Voor een rotatie-opstelling (koppel A op Match 1, koppel B op Match 2) is
de log-score de som van 3 onafhankelijke factoren:

  1. DEELNAME - per speler van de roster: kans dat hij meespeelt
       p_deelname(x) = (aantal ontmoetingen waarin x speelde + 1) / (N + 2)
     Spelers IN de opstelling dragen log(p) bij, spelers ERBUITEN log(1-p).
     -> een vaste kern-speler maakt opstellingen zonder hem onwaarschijnlijk.

  2. PARTNER-VOORKEUR - per koppel (x, y), symmetrisch:
       P(y | x) = (keer x samen met y + 1) / (keer x gespeeld + (roster-1))
       factor   = sqrt(P(y|x) * P(x|y))
     -> "x speelt bijna altijd met y" maakt dat koppel veel waarschijnlijker.

  3. MATCH-POSITIE - per speler, kans op Match 1 binnen een rotatie:
       p_m1(x) = (keer x op Match 1 + 1) / (keer x gespeeld + 2)
     Spelers op Match 1 dragen log(p_m1) bij, op Match 2 log(1 - p_m1).
     -> "x speelt bijna altijd 1ste match" wordt meegenomen.

De scores van alle mogelijke (reglementair toegelaten) opstellingen worden
via softmax omgezet naar kansen die optellen tot 100%. Zonder historiek
(N = 0) is alles neutraal (gelijke kansen) - het model verzint dus niets.
Per scenario worden de 2-3 sterkste REDENEN in gewone taal teruggegeven
(bv. "Peeters & Janssens speelden 4/5 keer samen"), zodat de voorspelling
controleerbaar blijft i.p.v. een black box.

Dit bestand bevat GEEN Streamlit-code en importeert niets uit de andere
lineup_*-modules (geen cirkelvormige imports): de bordvolgorde-regel
(art. 6.6) wordt als functie (`order_fn`) meegegeven door de aanroeper.
"""
import itertools
import math
from collections import defaultdict

_PAIR_ALPHA = 1.0
_POS_ALPHA = 1.0
_MIN_REASON_COUNT = 2  # pas vanaf 2 waarnemingen noemen we iets een "patroon"


def build_opponent_stats(bundle: dict, matches_per_rotation: int = 2) -> dict:
    """Telt deelname, partner-combinaties en Match-1/Match-2-posities over
    alle eerdere ontmoetingen van deze tegenstander (dit seizoen)."""
    appear = defaultdict(int)
    pair_cnt = defaultdict(int)
    partner_total = defaultdict(int)
    m1_cnt = defaultdict(int)
    slot_total = defaultdict(int)
    names = {}
    n_fix = 0
    for fx_bundle in (bundle or {}).get("previous_fixtures", []) or []:
        boards = fx_bundle.get("boards") or []
        if fx_bundle.get("error") or not boards:
            continue
        boards = sorted(boards, key=lambda b: b.get("board_position") or 0)
        seen = set()
        any_pair = False
        for idx, b in enumerate(boards):
            pair = [p for p in (b.get("opponent_pair") or []) if p.get("user_id")]
            if len(pair) != 2:
                continue
            any_pair = True
            uids = [str(p.get("user_id")) for p in pair]
            if uids[0] == uids[1]:
                continue
            is_m1 = (idx % matches_per_rotation) == 0
            for uid, p in zip(uids, pair):
                names[uid] = p.get("name", uid)
                seen.add(uid)
                slot_total[uid] += 1
                partner_total[uid] += 1
                if is_m1:
                    m1_cnt[uid] += 1
            pair_cnt[frozenset(uids)] += 1
        if any_pair:
            n_fix += 1
            for uid in seen:
                appear[uid] += 1
    return {
        "n_fixtures": n_fix,
        "appear": dict(appear),
        "pair_cnt": dict(pair_cnt),
        "partner_total": dict(partner_total),
        "m1_cnt": dict(m1_cnt),
        "slot_total": dict(slot_total),
        "names": names,
    }


def participation_prob(stats: dict, uid: str) -> float:
    return (stats["appear"].get(uid, 0) + 1.0) / (stats["n_fixtures"] + 2.0)


def partner_prob(stats: dict, uid: str, partner: str, roster_size: int) -> float:
    k = max(roster_size - 1, 1)
    c = stats["pair_cnt"].get(frozenset({uid, partner}), 0)
    return (c + _PAIR_ALPHA) / (stats["partner_total"].get(uid, 0) + _PAIR_ALPHA * k)


def m1_prob(stats: dict, uid: str) -> float:
    return (stats["m1_cnt"].get(uid, 0) + _POS_ALPHA) / (stats["slot_total"].get(uid, 0) + 2.0 * _POS_ALPHA)


def _pair_factor(stats, a, b, roster_size):
    return math.sqrt(partner_prob(stats, a, b, roster_size) * partner_prob(stats, b, a, roster_size))


def _log_participation(stats: dict, in_uids: set, roster_uids: list) -> float:
    total = 0.0
    for uid in roster_uids:
        p = participation_prob(stats, uid)
        total += math.log(p if uid in in_uids else (1.0 - p))
    return total


def rotation_log_score(stats: dict, m1_pair, m2_pair, roster_uids: list) -> float:
    """Log-score van 1 rotatie-opstelling (koppel m1_pair op Match 1,
    m2_pair op Match 2). Hoger = waarschijnlijker."""
    roster_size = len(roster_uids)
    a1, a2 = tuple(m1_pair)
    b1, b2 = tuple(m2_pair)
    score = _log_participation(stats, {a1, a2, b1, b2}, roster_uids)
    score += math.log(_pair_factor(stats, a1, a2, roster_size))
    score += math.log(_pair_factor(stats, b1, b2, roster_size))
    for uid in (a1, a2):
        score += math.log(m1_prob(stats, uid))
    for uid in (b1, b2):
        score += math.log(1.0 - m1_prob(stats, uid))
    return score


def full_lineup_log_score(stats: dict, board_pairs: list, roster_uids: list,
                          matches_per_rotation: int = 2) -> float:
    """Log-score van een VOLLEDIGE ontmoeting (lijst koppels in bordvolgorde).
    Deelname 1x over alle spelers van de ontmoeting; partner- en positie-
    factor per bord."""
    roster_size = len(roster_uids)
    spelers = {u for pair in board_pairs for u in pair}
    score = _log_participation(stats, spelers, roster_uids)
    for idx, pair in enumerate(board_pairs):
        a, b = tuple(pair)
        score += math.log(_pair_factor(stats, a, b, roster_size))
        is_m1 = (idx % matches_per_rotation) == 0
        for uid in (a, b):
            p = m1_prob(stats, uid)
            score += math.log(p if is_m1 else 1.0 - p)
    return score


def softmax_weights(log_scores: dict) -> dict:
    """{key: log_score} -> {key: kans} (som = 1). Numeriek stabiel."""
    if not log_scores:
        return {}
    mx = max(log_scores.values())
    exps = {k: math.exp(v - mx) for k, v in log_scores.items()}
    tot = sum(exps.values()) or 1.0
    return {k: v / tot for k, v in exps.items()}


def explain_rotation(stats: dict, m1_pair, m2_pair, max_reasons: int = 3) -> list:
    """Korte, controleerbare redenen in gewone taal."""
    names = stats["names"]
    n_fix = stats["n_fixtures"]
    redenen = []
    for pair in (m1_pair, m2_pair):
        a, b = tuple(pair)
        c = stats["pair_cnt"].get(frozenset({a, b}), 0)
        if c >= _MIN_REASON_COUNT:
            redenen.append((c * 2, f"{names.get(a, a)} & {names.get(b, b)} speelden al {c}x samen"))
    for uid in tuple(m1_pair):
        n, k = stats["slot_total"].get(uid, 0), stats["m1_cnt"].get(uid, 0)
        if n >= _MIN_REASON_COUNT and k / n >= 0.75:
            redenen.append((k, f"{names.get(uid, uid)} speelt meestal Match 1 ({k}/{n})"))
    for uid in tuple(m2_pair):
        n, k = stats["slot_total"].get(uid, 0), stats["m1_cnt"].get(uid, 0)
        if n >= _MIN_REASON_COUNT and (n - k) / n >= 0.75:
            redenen.append((n - k, f"{names.get(uid, uid)} speelt meestal Match 2 ({n - k}/{n})"))
    if n_fix >= _MIN_REASON_COUNT:
        for uid in set(m1_pair) | set(m2_pair):
            a = stats["appear"].get(uid, 0)
            if a / n_fix >= 0.8:
                redenen.append((a, f"{names.get(uid, uid)} speelde {a}/{n_fix} ontmoetingen"))
    redenen.sort(key=lambda r: r[0], reverse=True)
    return [txt for _, txt in redenen[:max_reasons]]


def predict_rotation_scenarios(
    stats: dict, roster: list, order_fn, official_ranks: dict, rules=None,
    excluded_pairs: set = None, unavailable_uids: set = None, top_n: int = 5,
) -> dict:
    """Alle mogelijke rotatie-opstellingen van de tegenstander (4 spelers,
    2 koppels, bordvolgorde via `order_fn` = art. 6.6-regel), gescoord en
    omgezet naar kansen. Koppels in `excluded_pairs` (al gespeeld in een
    eerdere rotatie van DEZE ontmoeting) en spelers in `unavailable_uids`
    worden overgeslagen. Met `rules` (punten_min/punten_max) worden enkel
    reglementair mogelijke opstellingen meegenomen (indien alle 4 de
    klassementen gekend zijn).
    Geeft {"scenarios": [top_n], "n_total": int} terug; elk scenario heeft
    "pairs" (2 frozensets, geordend), "prob", "reasons"."""
    excluded = {frozenset(p) for p in (excluded_pairs or set())}
    unavailable = set(unavailable_uids or set())
    roster_uids = [str(p.get("user_id")) for p in roster if p.get("user_id")]
    eligible = [u for u in roster_uids if u not in unavailable]
    log_scores = {}
    ordered_by_key = {}
    for combo in itertools.combinations(sorted(eligible), 4):
        a, b, c, d = combo
        for pa, pb in (((a, b), (c, d)), ((a, c), (b, d)), ((a, d), (b, c))):
            duo_a, duo_b = frozenset(pa), frozenset(pb)
            if duo_a in excluded or duo_b in excluded:
                continue
            if rules is not None:
                ranks = [official_ranks.get(u) for u in combo]
                if all(r is not None for r in ranks):
                    tot = sum(ranks)
                    if tot < rules.get("punten_min", -1e9) or tot > rules.get("punten_max", 1e9):
                        continue
            m1, m2 = order_fn([duo_a, duo_b])
            key = (frozenset(m1), frozenset(m2))
            if key in log_scores:
                continue
            log_scores[key] = rotation_log_score(stats, m1, m2, roster_uids)
            ordered_by_key[key] = (frozenset(m1), frozenset(m2))
    probs = softmax_weights(log_scores)
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    scenarios = []
    for key, prob in ranked[:top_n]:
        m1, m2 = ordered_by_key[key]
        scenarios.append({
            "pairs": [m1, m2],
            "prob": prob,
            "reasons": explain_rotation(stats, m1, m2),
        })
    return {"scenarios": scenarios, "n_total": len(probs)}
