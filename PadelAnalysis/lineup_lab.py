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

PADEL_ANALYSIS_MATCHUP_EDGE_DIRECTION_FIX_2026-09-13 (kritieke bugfix):
BUG (opgelost): matchup_edge() gebruikte de conventie "lager klassementsgetal
= sterker" (zie de oude docstring van parse_ranking: "Lager = sterker
(Tennis Vlaanderen-conventie)"). Dat is het TEGENOVERGESTELDE van de
conventie die overal elders in dit project geldt (HOGER = STERKER, zie
opponent_dossier.py en padelstats.be 'playing strength'). Fix: het teken van
'diff' is omgedraaid (ons - hun i.p.v. hun - ons).

PADEL_ANALYSIS_BOARD_DEDUPE_SAME_MATCHID_FIX_2026-09-13 (kritieke bugfix):
BUG (opgelost): _board_dedupe_key() gebruikte UITSLUITEND match_id om
duplicaten te herkennen. Voor bepaalde competitievormen registreert de
scraper ALLE dubbels van één speeldag onder HETZELFDE match_id, waardoor
verschillende boards ten onrechte werden samengevouwen. Fix: de
dedupe-sleutel bevat nu ook de SPELERS VAN DAT SPECIFIEKE BOARD.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SYNERGY_CONFIDENCE_SHRINKAGE_2026-09-15 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): make_pair_score_fn() gaf bij EEN enkele gezamenlijke,
gewonnen wedstrijd een synergie van 1.0 terug (min_matches_for_synergy=1
liet dat al toe als "genoeg data"). Concreet gemeld voorbeeld: Nico Recour /
Mortier Stijn speelden precies 1 keer samen, wonnen die ene wedstrijd, en
kregen daardoor synergie 1.0 — een cijfer dat evenveel gewicht kreeg als een
koppel met 20 gezamenlijke wedstrijden.

Fix: CONFIDENCE-SHRINKAGE i.p.v. een harde aan/uit-drempel. Het
koppelresultaat wordt steeds gemengd met het gemiddelde van de individuele
winrates van beide spelers, met een gewicht dat toeneemt naarmate er meer
gezamenlijke wedstrijden gekend zijn:

    weight = known_matches / (known_matches + confidence_k)
    score  = weight * paar_winrate + (1 - weight) * individueel_gemiddelde

Met de standaardwaarde confidence_k=3.0:
    1 gezamenlijke match  -> weight ≈ 0.25 (overwegend individueel gemiddelde)
    6 gezamenlijke matches -> weight ≈ 0.67
    20 gezamenlijke matches -> weight ≈ 0.87 (overwegend het koppelresultaat)

Dit vervangt het oude, harde min_matches_for_synergy-gedrag; de parameter
blijft bestaan voor eventuele achterwaartse compatibiliteit maar wordt niet
langer gebruikt als aan/uit-schakelaar.

--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): matchup_edge() kreeg voor "ons" de padelstats.be playing
strength (via opponent_analysis.get_own_player_rating(), continu
herberekend) maar voor "hen" het OFFICIËLE TVL-klassement uit het historische
uitslagenblad (opp1_ranking/opp2_ranking, enkel per seizoen bijgewerkt).
Concreet gemeld voorbeeld: Nico Recour / Carl Ide kregen een matchup-edge van
+0.67 (in ons voordeel) tegen L'hoëst Bert / Van Rossom Sam, terwijl Bert en
Sam een HOGERE padelstats-rating hadden dan Nico en Carl — het cijfer klopte
dus niet met de eigen padelstat-vergelijking, omdat twee VERSCHILLENDE
meetsystemen tegenover elkaar gezet werden.

Fix: optimize_lineup_vs_scenario() kiest nu PER BORD een consistente schaal:
    - is de padelstats-rating van BEIDE tegenstanders op dat bord gekend
      (opponent_ratings, sinds PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15
      automatisch opgehaald voor elke tegenstander) -> gebruik padelstat voor
      BEIDE zijden (ons via player_ratings, hen via opponent_ratings);
    - anders -> val voor BEIDE zijden terug op het officiële klassement
      (player_official_ranks voor ons, de "ranking"-tekst op het bord voor
      hen), zodat er nooit twee verschillende schalen tegen elkaar
      afgewogen worden.
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

    LET OP (datacompleetheid, geen codefout): deze index kan enkel dubbels
    tonen van spelers die zelf AL in 'docs' zitten. Speelde iemand in dezelfde
    ontmoeting mee, maar is die persoon nooit zelf toegevoegd, dan ontbreekt
    diens board volledig uit deze index.
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
# Dubbels (individuele matchen binnen 1 ontmoeting) reconstrueren
# ─────────────────────────────────────────────
def _board_dedupe_key(m: dict, fallback_pid: str) -> str:
    """PADEL_ANALYSIS_BOARD_DEDUPE_SAME_MATCHID_FIX_2026-09-13:
    Bevat nu ALTIJD de spelers van dit specifieke board (fallback_pid +
    partner_user_id, alfabetisch gesorteerd), niet enkel match_id."""
    mid = m.get("match_id")
    partner = m.get("partner_user_id")
    pair_key = "|".join(sorted([str(fallback_pid), str(partner)]))
    if mid:
        return f"mid:{mid}|pair:{pair_key}"
    return "fb:" + "|".join(str(x) for x in [
        m.get("match_date"), m.get("encounter"), m.get("round_text"),
        m.get("score"), pair_key,
    ])


def reconstruct_boards(entries: List[Tuple[str, dict]]) -> List[dict]:
    """
    entries: lijst van (player_id, match_dict) voor 1 ontmoeting (kan beide
    perspectieven van hetzelfde board bevatten — wordt hier ontdubbeld).
    Returns: lijst van unieke dubbels:
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
    Gebruikt dezelfde _board_dedupe_key() als reconstruct_boards().
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
    Onze eigen spelers hebben geen 'ranking'-veld op zichzelf. We zoeken
    daarom opportunistisch: heeft IEMAND deze speler ooit als tegenstander
    gehad? Dan staat hun klassement daar vermeld.

    LET OP: dit geeft het OFFICIËLE TVL-klassement terug (hoger = sterker),
    GEEN padelstats.be playing strength."""
    for doc in docs.values():
        for m in doc.get("matches", []) or []:
            if str(m.get("opp1_user_id")) == str(player_id) and m.get("opp1_ranking"):
                return parse_ranking(m["opp1_ranking"])
            if str(m.get("opp2_user_id")) == str(player_id) and m.get("opp2_ranking"):
                return parse_ranking(m["opp2_ranking"])
    return None


# Standaard "prior strength": bij hoeveel gezamenlijke matches het gewicht
# van het koppelresultaat gelijk is aan dat van het individuele gemiddelde
# (weight=0.5 bij known_matches == confidence_k). Hoger = terughoudender
# (meer matches nodig voor vertrouwen); lager = sneller vertrouwen op het
# koppelresultaat.
DEFAULT_SYNERGY_CONFIDENCE_K = 3.0


def make_pair_score_fn(
    synergy: Dict[frozenset, dict],
    docs: Dict[str, dict],
    min_matches_for_synergy: int = 1,
    confidence_k: float = DEFAULT_SYNERGY_CONFIDENCE_K,
) -> Callable[[str, str], float]:
    """
    PADEL_ANALYSIS_SYNERGY_CONFIDENCE_SHRINKAGE_2026-09-15: score voor een
    koppel (a,b) via confidence-shrinkage in plaats van een harde
    aan/uit-drempel:

        weight = known_matches / (known_matches + confidence_k)
        score  = weight * paar_winrate + (1 - weight) * individueel_gemiddelde

    Bij 0 gezamenlijke matches: enkel het individuele gemiddelde (of 0.5 als
    ook dat ontbreekt). Bij veel gezamenlijke matches: nadert het
    koppelresultaat zelf.

    min_matches_for_synergy blijft bestaan voor achterwaartse compatibiliteit
    (oude aanroepers geven dit nog mee) maar heeft geen effect meer op het
    resultaat — de shrinkage regelt dit nu vloeiend i.p.v. met een harde knip.
    """
    indiv_cache: Dict[str, Optional[float]] = {}

    def indiv(p: str) -> Optional[float]:
        if p not in indiv_cache:
            indiv_cache[p] = compute_individual_winrate(docs.get(str(p)))
        return indiv_cache[p]

    def score(a: str, b: str) -> float:
        pair = frozenset({str(a), str(b)})
        slot = synergy.get(pair)

        ia, ib = indiv(a), indiv(b)
        indiv_vals = [v for v in (ia, ib) if v is not None]
        indiv_avg = (sum(indiv_vals) / len(indiv_vals)) if indiv_vals else None

        if slot:
            known = slot["wins"] + slot["losses"]
            if known > 0 and slot["winrate"] is not None:
                weight = known / (known + confidence_k)
                basis = indiv_avg if indiv_avg is not None else slot["winrate"]
                return round(weight * slot["winrate"] + (1 - weight) * basis, 4)

        return round(indiv_avg, 4) if indiv_avg is not None else 0.5

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
    """'P100' -> 100, 'P 200' -> 200.
    PADEL_ANALYSIS_MATCHUP_EDGE_DIRECTION_FIX_2026-09-13: correcte,
    projectbrede conventie: HOGER = STERKER."""
    if rank_str is None:
        return None
    m = re.search(r"(\d+)", str(rank_str))
    return int(m.group(1)) if m else None


def matchup_edge(our_ranks: List[Optional[float]], their_ranks: List[Optional[float]]) -> float:
    """
    Ruwe, transparante inschatting van het verschil in slagkracht tussen twee
    koppels op basis van klassement/rating (GEEN echte winkans — enkel een
    relatieve indicatie). Positief = in ons voordeel.

    KRITIEK: our_ranks en their_ranks MOETEN op dezelfde schaal/metriek
    zitten (beide padelstat, OF beide officieel klassement) — zie
    PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15. Deze functie zelf
    doet geen schaalkeuze; dat gebeurt in optimize_lineup_vs_scenario().

    HOGER GETAL = STERKER. Genormaliseerd zodat het ongeveer in dezelfde
    grootte-orde ligt als een winrate-verschil (0–1-achtig).
    """
    ours = [r for r in our_ranks if r is not None]
    theirs = [r for r in their_ranks if r is not None]
    if not ours or not theirs:
        return 0.0
    diff = (sum(ours) / len(ours)) - (sum(theirs) / len(theirs))
    return max(-1.0, min(1.0, diff / 150.0))  # ±150 klassementspunten ≈ volle uitslag van de schaal


def _board_rank_scale(
    opponent_pair: List[dict],
    opponent_ratings: Optional[Dict[str, Optional[float]]],
) -> tuple:
    """PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15.

    Bepaalt WELKE schaal gebruikt wordt voor dit ene bord en geeft meteen de
    tegenstander-waarden in die schaal terug.

    Returns (scale, their_ranks):
      scale = "padelstat"  als BEIDE tegenstanders een padelstat-rating hebben
      scale = "official"   anders (val terug op het klassement-tekstveld)
    """
    if opponent_ratings:
        padelstat_vals = []
        all_present = True
        for p in opponent_pair:
            uid = str(p.get("user_id") or "")
            val = opponent_ratings.get(uid) if uid else None
            if val is None:
                all_present = False
                break
            padelstat_vals.append(val)
        if all_present and padelstat_vals:
            return "padelstat", padelstat_vals

    official_vals = [parse_ranking(p.get("ranking")) for p in opponent_pair]
    return "official", official_vals


def optimize_lineup_vs_scenario(
    players: List[str],
    required: Dict[str, int],
    own_synergy_fn: Callable[[str, str], float],
    opponent_boards: List[dict],
    player_ratings: Dict[str, Optional[float]],
    player_official_ranks: Optional[Dict[str, Optional[int]]] = None,
    opponent_ratings: Optional[Dict[str, Optional[float]]] = None,
    top_n: int = 3,
    candidate_pool: int = 30,
) -> Tuple[List[dict], bool]:
    """
    Zoekt, voor een SPECIFIEK tegenstander-scenario (hun werkelijke koppels uit
    een eerdere wedstrijd), de beste combinatie van (a) onze eigen koppelvorming
    en (b) welke van onze koppels tegen welk tegenstanderskoppel uitkomt.

    opponent_boards: lijst van {"opponent_pair": [{"name","user_id","ranking"(optioneel)}, ...]}
    player_ratings: pid -> padelstats.be playing strength voor ONZE spelers
      (HOGER = STERKER). Wordt gebruikt wanneer voor een bord ook de
      tegenstander-padelstat gekend is (zie opponent_ratings).
    player_official_ranks: pid -> officieel TVL-klassement voor ONZE spelers,
      als terugval-schaal wanneer de tegenstander geen padelstat-rating heeft.
      Ontbreekt dit, dan valt de code terug op player_ratings (oud gedrag,
      met het risico op een schaalmismatch — zie de moduledocstring).
    opponent_ratings: user_id (van TEGENSTANDER-spelers) -> padelstats.be
      playing strength, sinds PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15
      automatisch opgehaald voor elke tegenstander. Ontbreekt dit of is een
      speler er niet in gekend, dan valt DIT SPECIFIEKE BORD terug op het
      officiële klassement (voor BEIDE zijden, zie PADEL_ANALYSIS_MATCHUP_
      SCALE_CONSISTENCY_2026-09-15) i.p.v. de twee schalen te mengen.

    Returns: (resultaten, truncated) — resultaten = lijst van
      {"total_score", "assignment": [{"our_pair":(p1,p2), "synergy":.., "edge":.., "opponent_board":{...}}]}
      gesorteerd van beste naar slechtste, max top_n.
    """
    candidates, truncated = optimize_lineup(players, required, own_synergy_fn, top_n=candidate_pool)
    if not candidates:
        return [], truncated

    n_boards = len(opponent_boards)

    # PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15: per bord vooraf
    # bepalen welke schaal gebruikt wordt, zodat "onze" en "hun" waarden voor
    # datzelfde bord altijd van dezelfde metriek komen.
    board_scales: List[str] = []
    their_rank_lists: List[List[Optional[float]]] = []
    for b in opponent_boards:
        scale, their_ranks = _board_rank_scale(b.get("opponent_pair", []) or [], opponent_ratings)
        board_scales.append(scale)
        their_rank_lists.append(their_ranks)

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

                scale = board_scales[board_idx]
                if scale == "padelstat":
                    our_ranks = [player_ratings.get(p1), player_ratings.get(p2)]
                else:
                    # Consistent met "official" schaal voor hun kant: gebruik
                    # ONS officiële klassement, niet de padelstat-rating.
                    fallback_ranks = player_official_ranks if player_official_ranks is not None else player_ratings
                    our_ranks = [fallback_ranks.get(p1), fallback_ranks.get(p2)]

                edge = matchup_edge(our_ranks, their_rank_lists[board_idx])
                total += syn + edge
                assignment.append({
                    "our_pair": (p1, p2),
                    "synergy": round(syn, 3),
                    "edge": round(edge, 3),
                    "edge_scale": scale,
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
