"""
lineup_lab.py — Opstelling-analyse (Fase 1: retrospectieve test-tool)

Doel: een eerder gespeelde interclub-ontmoeting reconstrueren uit de al
gescrapete Firestore-data (welke koppels speelden er echt, tegen wie, met
welk resultaat), en daarnaast berekenen wat de beste alternatieve
opstelling(en) geweest zouden zijn op basis van historische partner-synergie
(buiten die ene ontmoeting om, om "leakage" te vermijden).

Geen koppeling met een toekomstige wedstrijdkalender — dit werkt uitsluitend
op data die al in Firestore staat.

Belangrijke spelregel die hier hard gecodeerd is: een speler speelt op één
en dezelfde dag nooit twee keer met dezelfde partner.
"""

import heapq
import itertools
import re
from typing import Callable, Dict, List, Optional, Tuple

import firebase_service as fb


# ─────────────────────────────────────────────
# Data ophalen
# ─────────────────────────────────────────────

def get_all_profiles() -> List[dict]:
    try:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        return [d.to_dict() for d in docs]
    except Exception:
        return []


def get_docs_for_players(player_ids: List[str]) -> Dict[str, dict]:
    """Haalt volledige player-documenten (met matches) op voor een lijst player_ids."""
    out = {}
    for pid in player_ids:
        doc = fb.get_player(pid)
        if doc:
            out[str(pid)] = doc
    return out


# ─────────────────────────────────────────────
# Ontmoetingen (encounters) opsporen
# ─────────────────────────────────────────────

def _encounter_key(m: dict) -> Tuple:
    return (
        m.get("match_date") or "",
        m.get("reeks_name") or "",
        m.get("encounter") or "",
        m.get("competition_name") or "",
    )


def build_encounter_index(docs: Dict[str, dict]) -> Dict[Tuple, List[Tuple[str, dict]]]:
    """
    Doorzoekt alle matches (interclub) van alle gegeven spelers en groepeert
    ze per ontmoeting (zelfde datum + reeks + 'ontmoeting'-tekst + competitie).
    Returns: {encounter_key: [(player_id, match_dict), ...]}
    """
    index: Dict[Tuple, List[Tuple[str, dict]]] = {}
    for pid, doc in docs.items():
        for m in doc.get("matches", []) or []:
            if m.get("match_type") != "interclub":
                continue
            key = _encounter_key(m)
            index.setdefault(key, []).append((pid, m))
    return index


def list_encounters(index: Dict[Tuple, List[Tuple[str, dict]]]) -> List[Tuple[Tuple, str]]:
    """Geeft (key, leesbaar label) terug, recentste datum eerst."""
    items = []
    for key, entries in index.items():
        date, reeks, encounter, competition = key
        label_parts = [p for p in [date, reeks or competition, encounter] if p]
        label = " — ".join(label_parts) if label_parts else "Onbekende ontmoeting"
        items.append((key, label, date))
    items.sort(key=lambda x: x[2] or "", reverse=True)
    return [(key, label) for key, label, _ in items]


# ─────────────────────────────────────────────
# Boards (individuele matchen binnen 1 ontmoeting) reconstrueren
# ─────────────────────────────────────────────

def _board_dedupe_key(m: dict, fallback_pid: str) -> str:
    mid = m.get("match_id")
    if mid:
        return f"mid:{mid}"
    # fallback als match_id ontbreekt: best-effort unieke sleutel
    return "fb:" + "|".join(str(x) for x in [
        m.get("match_date"), m.get("encounter"), m.get("round_text"),
        m.get("score"), frozenset([fallback_pid, m.get("partner_user_id")]),
    ])


def reconstruct_boards(entries: List[Tuple[str, dict]]) -> List[dict]:
    """
    entries: lijst van (player_id, match_dict) voor 1 ontmoeting (kan beide
    perspectieven van hetzelfde board bevatten — wordt hier ontdubbeld).
    Returns: lijst van unieke boards:
      {pair: frozenset({p1,p2}), round_text, opp1_name, opp2_name,
       opp1_user_id, opp2_user_id, score, result, won, match_id}
    """
    seen = {}
    for pid, m in entries:
        key = _board_dedupe_key(m, pid)
        if key in seen:
            continue
        partner = m.get("partner_user_id")
        if not partner:
            continue
        seen[key] = {
            "pair": frozenset({str(pid), str(partner)}),
            "round_text": m.get("round_text"),
            "opp1_name": m.get("opp1_name"),
            "opp2_name": m.get("opp2_name"),
            "opp1_user_id": m.get("opp1_user_id"),
            "opp2_user_id": m.get("opp2_user_id"),
            "score": m.get("score"),
            "result": m.get("result"),
            "won": m.get("won"),
            "match_id": m.get("match_id"),
            "dedupe_key": key,
        }
    return list(seen.values())


def required_counts_from_boards(boards: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for b in boards:
        for p in b["pair"]:
            counts[p] = counts.get(p, 0) + 1
    return counts


# ─────────────────────────────────────────────
# Synergie & individuele vorm
# ─────────────────────────────────────────────

def compute_pairwise_synergy(
    docs: Dict[str, dict],
    player_ids: List[str],
    exclude_match_keys: Optional[set] = None,
) -> Dict[frozenset, dict]:
    """
    Scant ALLE matches (tornooi + interclub) van de gegeven spelers en bouwt
    per koppel (a,b) de historische samenspeel-winrate, met uitsluiting van
    de ontmoeting die net geanalyseerd wordt (om leakage te vermijden).
    """
    exclude_match_keys = exclude_match_keys or set()
    player_set = set(str(p) for p in player_ids)
    seen_global = set()
    acc: Dict[frozenset, dict] = {}

    for pid in player_ids:
        doc = docs.get(str(pid))
        if not doc:
            continue
        for m in doc.get("matches", []) or []:
            partner = m.get("partner_user_id")
            if not partner or str(partner) not in player_set:
                continue
            key = _board_dedupe_key(m, pid)
            if key in exclude_match_keys:
                continue
            if key in seen_global:
                continue
            seen_global.add(key)

            pair = frozenset({str(pid), str(partner)})
            won = m.get("won")
            slot = acc.setdefault(pair, {"matches": 0, "wins": 0, "losses": 0})
            slot["matches"] += 1
            if won is True:
                slot["wins"] += 1
            elif won is False:
                slot["losses"] += 1

    for pair, slot in acc.items():
        known = slot["wins"] + slot["losses"]
        slot["winrate"] = (slot["wins"] / known) if known else None
    return acc


def compute_individual_winrate(doc: Optional[dict]) -> Optional[float]:
    if not doc:
        return None
    stats = doc.get("stats", {}) or {}
    wins = stats.get("wins", 0) or 0
    losses = stats.get("losses", 0) or 0
    known = wins + losses
    return (wins / known) if known else None


def find_player_ranking(player_id: str, docs: Dict[str, dict]) -> Optional[int]:
    """
    Onze eigen spelers hebben geen 'ranking'-veld op zichzelf (enkel
    tegenstanders krijgen een klassement vermeld in een match-record). We
    zoeken daarom opportunistisch: heeft IEMAND deze speler ooit als
    tegenstander gehad? Dan staat hun klassement daar vermeld.
    """
    for doc in docs.values():
        for m in doc.get("matches", []) or []:
            if str(m.get("opp1_user_id")) == str(player_id) and m.get("opp1_ranking"):
                return parse_ranking(m["opp1_ranking"])
            if str(m.get("opp2_user_id")) == str(player_id) and m.get("opp2_ranking"):
                return parse_ranking(m["opp2_ranking"])
    return None


def make_pair_score_fn(
    synergy: Dict[frozenset, dict],
    docs: Dict[str, dict],
    min_matches_for_synergy: int = 1,
) -> Callable[[str, str], float]:
    """
    Score voor een koppel (a,b):
      - als er >= min_matches_for_synergy gezamenlijke matches met gekend
        resultaat zijn: gebruik hun samenspeel-winrate
      - anders: gemiddelde van de individuele winrates van a en b
      - anders (geen data): 0.5 (neutraal)
    """
    indiv_cache: Dict[str, Optional[float]] = {}

    def indiv(p: str) -> Optional[float]:
        if p not in indiv_cache:
            indiv_cache[p] = compute_individual_winrate(docs.get(str(p)))
        return indiv_cache[p]

    def score(a: str, b: str) -> float:
        pair = frozenset({str(a), str(b)})
        slot = synergy.get(pair)
        if slot:
            known = slot["wins"] + slot["losses"]
            if known >= min_matches_for_synergy and slot["winrate"] is not None:
                return slot["winrate"]
        ia, ib = indiv(a), indiv(b)
        vals = [v for v in (ia, ib) if v is not None]
        if vals:
            return sum(vals) / len(vals)
        return 0.5

    return score


# ─────────────────────────────────────────────
# Opstelling-optimalisatie (branch & bound)
# ─────────────────────────────────────────────

def optimize_lineup(
    players: List[str],
    required: Dict[str, int],
    synergy_fn: Callable[[str, str], float],
    top_n: int = 5,
    call_budget: int = 300_000,
) -> Tuple[List[Tuple[float, List[frozenset]]], bool]:
    """
    players: lijst van speler-ids
    required: pid -> exact aantal matchen die dag (som moet even zijn)
    synergy_fn: (a,b) -> score
    Returns: (top_n resultaten [(score, [pair, ...]), ...] desc gesorteerd, truncated)
    Regel: een speler heeft nooit twee keer dezelfde partner op één dag.
    """
    total_slots = sum(required.values())
    if total_slots % 2 != 0:
        raise ValueError("Som van 'required' moet even zijn (elk board = 2 spelers).")
    if total_slots == 0:
        return [], False

    sorted_partners = {
        p: sorted((q for q in players if q != p), key=lambda q: -synergy_fn(p, q))
        for p in players
    }
    best_possible_pair_score = max(
        (synergy_fn(a, b) for a, b in itertools.combinations(players, 2)), default=0.0
    )

    heap: List[Tuple[float, tuple, list]] = []
    seen_keys = set()
    calls = [0]
    truncated = [False]

    def heap_worst():
        return heap[0][0] if heap else float("-inf")

    def backtrack(remaining, used_partners, pairs, score):
        calls[0] += 1
        if calls[0] > call_budget:
            truncated[0] = True
            return
        if not any(v > 0 for v in remaining.values()):
            key = tuple(sorted(tuple(sorted(p)) for p in pairs))
            if key in seen_keys:
                return
            if len(heap) < top_n:
                seen_keys.add(key)
                heapq.heappush(heap, (score, key, list(pairs)))
            elif score > heap_worst():
                seen_keys.add(key)
                heapq.heapreplace(heap, (score, key, list(pairs)))
            return

        remaining_boards = sum(remaining.values()) // 2
        upper_bound = score + remaining_boards * best_possible_pair_score
        if len(heap) >= top_n and upper_bound <= heap_worst():
            return

        anchor = max((p for p in players if remaining[p] > 0), key=lambda p: (remaining[p], p))
        for partner in sorted_partners[anchor]:
            if remaining[partner] <= 0 or partner in used_partners[anchor]:
                continue
            remaining[anchor] -= 1
            remaining[partner] -= 1
            used_partners[anchor].add(partner)
            used_partners[partner].add(anchor)
            pairs.append(frozenset((anchor, partner)))
            backtrack(remaining, used_partners, pairs, score + synergy_fn(anchor, partner))
            pairs.pop()
            used_partners[anchor].discard(partner)
            used_partners[partner].discard(anchor)
            remaining[anchor] += 1
            remaining[partner] += 1
            if calls[0] > call_budget:
                return

    backtrack(dict(required), {p: set() for p in players}, [], 0.0)
    results = sorted(heap, key=lambda x: -x[0])
    return [(round(s, 4), p) for s, _, p in results], truncated[0]


def score_actual_lineup(boards: List[dict], synergy_fn: Callable[[str, str], float]) -> float:
    total = 0.0
    for b in boards:
        a, c = tuple(b["pair"])
        total += synergy_fn(a, c)
    return round(total, 4)


# ─────────────────────────────────────────────
# Scenario-analyse: onze beste tegenzet per mogelijk tegenstander-scenario
# ─────────────────────────────────────────────

def parse_ranking(rank_str) -> Optional[int]:
    """'P100' -> 100, 'P 200' -> 200. Lager = sterker (Tennis Vlaanderen-conventie)."""
    if rank_str is None:
        return None
    m = re.search(r"(\d+)", str(rank_str))
    return int(m.group(1)) if m else None


def matchup_edge(our_ranks: List[Optional[int]], their_ranks: List[Optional[int]]) -> float:
    """
    Ruwe, transparante inschatting van het verschil in slagkracht tussen twee
    koppels op basis van klassement (GEEN echte winkans — enkel een relatieve
    indicatie). Positief = in ons voordeel (hun klassementscijfer hoger/zwakker
    dan het onze). Genormaliseerd zodat het ongeveer in dezelfde grootte-orde
    ligt als een winrate-verschil (0–1-achtig), zodat het samen met de
    synergie-score kan opgeteld worden zonder die te overheersen.
    """
    ours = [r for r in our_ranks if r is not None]
    theirs = [r for r in their_ranks if r is not None]
    if not ours or not theirs:
        return 0.0
    diff = (sum(theirs) / len(theirs)) - (sum(ours) / len(ours))
    return max(-1.0, min(1.0, diff / 150.0))  # ±150 klassementspunten ≈ volle uitslag van de schaal


def optimize_lineup_vs_scenario(
    players: List[str],
    required: Dict[str, int],
    own_synergy_fn: Callable[[str, str], float],
    opponent_boards: List[dict],
    player_rankings: Dict[str, Optional[int]],
    top_n: int = 3,
    candidate_pool: int = 30,
) -> Tuple[List[dict], bool]:
    """
    Zoekt, voor een SPECIFIEK tegenstander-scenario (hun werkelijke koppels uit
    een eerdere wedstrijd), de beste combinatie van (a) onze eigen koppelvorming
    en (b) welke van onze koppels tegen welk tegenstanderskoppel uitkomt.

    opponent_boards: lijst van {"opponent_pair": [{"name","user_id","ranking"(optioneel)}, ...]}
    player_rankings: pid -> klassementscijfer (lager = sterker), voor ONZE spelers

    Returns: (resultaten, truncated) — resultaten = lijst van
      {"total_score", "assignment": [{"our_pair":(p1,p2), "synergy":.., "vs": {...}, "edge":.., "opponent_pair":[...]}]}
      gesorteerd van beste naar slechtste, max top_n.
    """
    candidates, truncated = optimize_lineup(players, required, own_synergy_fn, top_n=candidate_pool)
    if not candidates:
        return [], truncated

    n_boards = len(opponent_boards)
    their_rank_lists = []
    for b in opponent_boards:
        ranks = [parse_ranking(p.get("ranking")) for p in b.get("opponent_pair", [])]
        their_rank_lists.append(ranks)

    results = []
    for synergy_total, pairs in candidates:
        n = min(len(pairs), n_boards)
        if n == 0:
            continue
        pair_list = list(pairs)[:n]
        best_for_this_pairing = None

        # Voor kleine n (boards per ontmoeting blijft beperkt, typisch ≤6) is
        # brute-force permutatie van de toewijzing aan boards probleemloos snel.
        for perm in itertools.permutations(range(n_boards), n):
            total = 0.0
            assignment = []
            for slot_idx, board_idx in enumerate(perm):
                p1, p2 = tuple(pair_list[slot_idx])
                syn = own_synergy_fn(p1, p2)
                our_ranks = [player_rankings.get(p1), player_rankings.get(p2)]
                edge = matchup_edge(our_ranks, their_rank_lists[board_idx])
                total += syn + edge
                assignment.append({
                    "our_pair": (p1, p2),
                    "synergy": round(syn, 3),
                    "edge": round(edge, 3),
                    "opponent_board": opponent_boards[board_idx],
                })
            if best_for_this_pairing is None or total > best_for_this_pairing["total_score"]:
                best_for_this_pairing = {"total_score": round(total, 3), "assignment": assignment}

        if best_for_this_pairing:
            results.append(best_for_this_pairing)

    seen = set()
    deduped = []
    for r in sorted(results, key=lambda x: -x["total_score"]):
        key = tuple(sorted(a["our_pair"] for a in r["assignment"]))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped[:top_n], truncated
