"""
lineup_lab.py — Opstelling-analyse (Fase 1: retrospectieve test-tool)

Doel: een eerder gespeelde interclub-ontmoeting reconstrueren uit de al
gescrapete Firestore-data, en berekenen wat de beste alternatieve
opstelling(en) geweest zouden zijn op basis van historische partner-synergie.

Belangrijke spelregel die hier hard gecodeerd is: een speler speelt op één
en dezelfde dag nooit twee keer met dezelfde partner.

PADEL_ANALYSIS_MATCHUP_EDGE_DIRECTION_FIX_2026-09-13: matchup_edge() gebruikt
de projectbrede conventie HOGER = STERKER.

PADEL_ANALYSIS_BOARD_DEDUPE_SAME_MATCHID_FIX_2026-09-13: dedupe-sleutel bevat
ook de spelers van dat specifieke board, niet enkel match_id.

PADEL_ANALYSIS_SYNERGY_CONFIDENCE_SHRINKAGE_2026-09-15: confidence-shrinkage
i.p.v. een harde aan/uit-drempel voor koppelsynergie.

PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17 /
PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17: de bordvolgorde ligt
VERPLICHT vast via de SOM van de officiële klassementen van de 2 spelers per
duo (reglement art. 6.6), PER ROTATIE (2 gelijktijdige wedstrijden) — niet
globaal over de hele ontmoeting.

PADEL_ANALYSIS_ROTATION_RULES_2026-09-17: puntengrenzen per rotatie (art.
2.1/9.3.3/9.3.4) sluiten ongeldige koppelverdelingen UIT (zie
tournament_rules.py, optionele `tournament_rules_dict`-parameter).

--------------------------------------------------------------------------
PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17 (op verzoek
van Kim, na het testen van de vorige versie — 3 samenhangende problemen)
--------------------------------------------------------------------------
Kim's kernpunten, in eigen woorden:
  1. "je toont de eigenlijke ploeg altijd in dezelfde opstelling" — voor elk
     tegenstander-scenario moet ONZE beste tegenzet apart herberekend worden,
     niet steeds hetzelfde resultaat.
  2. "voor de ploegopstelling moet je het OFFICIEEL klassement gebruiken maar
     voor de simulatie kan je rekening houden met de padelstat score" —
     TWEE VERSCHILLENDE doelen die STRIKT gescheiden moeten blijven:
       a) REGLEMENT (bordvolgorde + puntengrens): uitsluitend het OFFICIËLE
          klassement, NOOIT vermengd met padelstat.
       b) SIMULATIE (wie wint waarschijnlijk): bij voorkeur padelstat (meer
          actueel dan het officiële klassement, dat maar 1x/seizoen
          verandert), per speler individueel, met een terugval naar officieel
          klassement enkel voor de spelers waarvoor geen padelstat gekend is.
  3. "matchup edge lijkt nu gewoon berekend op basis van klassement" en "het
     zou beter zijn om het verwacht eindresultaat te vermelden met de
     risico's" — de simulatie moet een interpreteerbare WINKANS per bord en
     een VERWACHT AANTAL GEWONNEN BORDEN geven, i.p.v. een abstract
     "score"-getal, mét een expliciete waarschuwing dat dit een ruwe
     schatting is (geen gevalideerd statistisch model).

BUG (root cause van punt 1, opgelost): in de vorige versie werd, bij het
OPBOUWEN van 'official_ranks' (in page_lineup_lab.py, niet in dit bestand),
een ONBEKEND officieel klassement stilzwijgend vervangen door de
padelstat-rating: `_official_current_rank(pid) or player_ratings.get(pid, 0)`.
Dat vermengde de REGLEMENT-schaal met de SIMULATIE-schaal voor exact de
functies (rank_pairs_by_official_rank, de puntengrens-check) die daar NOOIT
padelstat mogen gebruiken — met als zichtbaar gevolg dat de zoekruimte van
toegelaten combinaties kunstmatig kon instorten tot telkens dezelfde ene
combinatie, ONGEACHT het tegenstander-scenario (want reglement-ordening en
puntengrens hangen immers NIET af van de tegenstander). Fix: de aanroeper
(page_lineup_lab.py) bouwt voortaan een STRIKT officieel-klassement-dict
(geen fallback naar padelstat) — zie ook de nieuwe validatiehelper
`has_missing_official_rank()` hieronder, die de UI kan gebruiken om expliciet
te waarschuwen i.p.v. in stilte te substitueren.

NIEUWE FUNCTIES (simulatie, volledig los van de reglement-functies
hierboven):
  - effective_simulation_rating(pid, padelstat_ratings, official_ranks):
    per SPELER (niet per bord/paar) padelstat-rating indien gekend, anders
    het officiële klassement als terugval — GEEN alles-of-niets-schakelaar
    meer per bord (dat was PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15
    se aanpak: beide spelers OP HETZELFDE BORD moesten padelstat hebben,
    anders viel het HELE bord terug op officieel — bij vaak ontbrekende
    tegenstander-padelstat (zeer gebruikelijk, zie de rest van dit project)
    viel de edge daardoor STRUCTUREEL vaak terug op klassement, wat Kim
    terecht "niet waardevol" noemt).
  - estimate_win_probability(our_avg, their_avg, scale=300.0): eenvoudige,
    Elo-achtige logistische schatting van de winkans voor ONS op 1 bord,
    gebaseerd op het (ongeknipte) ratingverschil — NIET de eerder gebruikte,
    naar [-1,1] afgeknipte 'edge'-waarde, want die verliest net de
    grootte-informatie die een winkans-schatting nodig heeft bij grote
    verschillen. Uitdrukkelijk gelabeld als RUWE HEURISTIEK, geen
    gevalideerd model — dat wordt ook zo in de UI gecommuniceerd.
  - risk_note_for_probability(p): leesbare risico-omschrijving ("zeer
    onzeker", "kleine voorsprong", "duidelijke favoriet", ...).

optimize_lineup_vs_scenario() berekent nu, per bord in 'assignment': zowel de
bestaande 'edge' (ongewijzigd qua schaal-logica per-bord-conventie vervangen
door per-speler fallback) als NIEUW 'win_probability' en 'risk_note'. Het
resultaat-dict krijgt een nieuw top-level veld 'expected_boards_won' (som van
de win_probability over alle borden) — een veel interpreteerbaarder getal dan
de vorige, abstracte 'total_score'. 'total_score' (synergie+edge-som) blijft
bestaan voor de interne rangschikking/sortering van kandidaten, maar wordt in
de UI niet langer als hoofdgetal getoond (zie page_lineup_lab.py).
"""
import heapq
import itertools
import math
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
    index: Dict[Tuple, List[Tuple[str, dict]]] = {}
    for pid, doc in docs.items():
        for m in doc.get("matches", []) or []:
            if m.get("match_type") != "interclub":
                continue
            key = _encounter_key(m)
            index.setdefault(key, []).append((pid, m))
    return index


def list_encounters(index: Dict[Tuple, List[Tuple[str, dict]]]) -> List[Tuple[Tuple, str]]:
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
    for doc in docs.values():
        for m in doc.get("matches", []) or []:
            if str(m.get("opp1_user_id")) == str(player_id) and m.get("opp1_ranking"):
                return parse_ranking(m["opp1_ranking"])
            if str(m.get("opp2_user_id")) == str(player_id) and m.get("opp2_ranking"):
                return parse_ranking(m["opp2_ranking"])
    return None


DEFAULT_SYNERGY_CONFIDENCE_K = 3.0


def make_pair_score_fn(
    synergy: Dict[frozenset, dict],
    docs: Dict[str, dict],
    min_matches_for_synergy: int = 1,
    confidence_k: float = DEFAULT_SYNERGY_CONFIDENCE_K,
) -> Callable[[str, str], float]:
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
# Officiële bordvolgorde-regel — UITSLUITEND op officieel klassement.
# ─────────────────────────────────────────────
def has_missing_official_rank(player_ids: List[str], official_ranks: Dict[str, Optional[float]]) -> List[str]:
    """PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17:
    geeft de spelers terug wiens OFFICIËLE klassement onbekend is (None of
    afwezig in official_ranks). Bedoeld voor de UI om EXPLICIET te
    waarschuwen dat de reglementaire bordvolgorde/puntengrens voor die
    spelers niet met zekerheid te verifiëren is — in plaats van, zoals
    voorheen, in stilte een andere (padelstat-)waarde te substitueren."""
    return [pid for pid in player_ids if official_ranks.get(pid) is None]


def _pair_strength_sum(pair, official_ranks: Dict[str, Optional[float]]) -> float:
    """SOM van de klassementen van de 2 spelers in het duo (reglement art.
    6.6), NIET het hoogste individuele klassement. Ontbrekende waarden tellen
    hier als 0 (de aanroeper moet has_missing_official_rank() gebruiken om
    dat expliciet te signaleren aan de gebruiker — deze functie zelf blijft
    defensief/nooit crashend)."""
    return sum((official_ranks.get(pid) or 0) for pid in pair)


def rank_pairs_by_official_rank(pairs: List[frozenset], official_ranks: Dict[str, Optional[float]]) -> List[frozenset]:
    """Sorteert een lijst koppels aflopend op de SOM van de OFFICIËLE
    klassementen van de 2 spelers in dat duo (art. 6.6). GEEN padelstat-
    fallback hier — official_ranks MOET een strikt officieel-klassement-dict
    zijn (zie has_missing_official_rank() voor het signaleren van gaten)."""
    return sorted(pairs, key=lambda pair: _pair_strength_sum(pair, official_ranks), reverse=True)


def _sort_boards_by_opponent_official_rank(opponent_boards: List[dict]) -> List[dict]:
    """Sorteert tegenstander-borden op de SOM van hun OFFICIËLE klassementen
    (aflopend) — het bord met de hoogste som komt eerst (= hun Bord 1).
    Gebruikt uitsluitend het 'ranking'-tekstveld (officieel klassement), NOOIT
    padelstat — die vermenging hoort enkel thuis in de SIMULATIE-laag
    (effective_simulation_rating() hieronder)."""
    def strength(board):
        pair = board.get("opponent_pair", []) or []
        vals = [parse_ranking(p.get("ranking")) for p in pair]
        return sum(v for v in vals if v is not None)
    return sorted(opponent_boards, key=strength, reverse=True)


# ─────────────────────────────────────────────
# Rotatie-gebaseerde regels (punten-per-rotatie-grenzen + sterkste-duo-per-rotatie)
# ─────────────────────────────────────────────
def group_boards_into_rotations(items: list, per_rotation: int = 2) -> List[list]:
    """Groepeert een geordende lijst 2-aan-2 in opeenvolgende rotaties
    (reglement art. 8.7.1: 2 rotaties van telkens 2 gelijktijdige
    wedstrijden)."""
    return [items[i:i + per_rotation] for i in range(0, len(items), per_rotation)]


def evaluate_rotation(
    duo_a: frozenset,
    duo_b: frozenset,
    official_ranks: Dict[str, Optional[float]],
    rules: Optional[dict] = None,
) -> dict:
    """Evalueert 1 volledige rotatie (2 duo's, 4 spelers) tegen het
    reglement: bepaalt welk duo sterkst is (SOM-gebaseerd, art. 6.6) en
    toetst de totale punten-som aan `rules` (tournament_rules.
    get_afdeling_rules(...), of None = geen check/altijd geldig)."""
    sum_a = _pair_strength_sum(duo_a, official_ranks)
    sum_b = _pair_strength_sum(duo_b, official_ranks)
    ordered = [duo_a, duo_b] if sum_a >= sum_b else [duo_b, duo_a]
    total_points = sum_a + sum_b

    valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
    if rules is not None:
        try:
            import tournament_rules as _tr
            valid, reason = _tr.rotation_points_bounds_ok(total_points, rules)
        except Exception:
            valid, reason = True, f"{total_points:.0f} punten (reglement-check niet beschikbaar)"

    return {
        "ordered_pairs": ordered,
        "total_points": total_points,
        "valid": valid,
        "reason": reason,
    }


def filter_and_order_lineup_by_rotations(
    pairs: List[frozenset],
    official_ranks: Dict[str, Optional[float]],
    rules: Optional[dict] = None,
) -> dict:
    """Past evaluate_rotation() toe op een VOLLEDIGE koppelverdeling (alle
    rotaties van 1 ontmoeting ineens). Gebruikt door
    optimize_lineup_vs_scenario() om, VOORDAT er gescoord wordt, kandidaten
    uit te sluiten waarvan minstens 1 rotatie buiten de toegelaten
    puntengrenzen valt."""
    rotations_raw = group_boards_into_rotations(pairs, per_rotation=2)
    ordered_pairs: List[frozenset] = []
    rotation_results = []
    all_valid = True

    for group in rotations_raw:
        if len(group) < 2:
            ordered_pairs.extend(group)
            rotation_results.append({
                "ordered_pairs": group, "total_points": None,
                "valid": True, "reason": "onvolledige rotatie, geen check mogelijk",
            })
            continue
        result = evaluate_rotation(group[0], group[1], official_ranks, rules)
        ordered_pairs.extend(result["ordered_pairs"])
        rotation_results.append(result)
        if not result["valid"]:
            all_valid = False

    return {
        "ordered_pairs": ordered_pairs,
        "rotations": rotation_results,
        "all_valid": all_valid,
    }


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17
# Simulatie-laag: volledig los van de reglement-functies hierboven.
# ─────────────────────────────────────────────
def parse_ranking(rank_str) -> Optional[int]:
    """'P100' -> 100. HOGER = STERKER (projectbrede conventie)."""
    if rank_str is None:
        return None
    m = re.search(r"(\d+)", str(rank_str))
    return int(m.group(1)) if m else None


def effective_simulation_rating(
    pid: str,
    padelstat_ratings: Optional[Dict[str, Optional[float]]],
    official_ranks: Optional[Dict[str, Optional[float]]],
) -> Optional[float]:
    """PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17: per
    SPELER (niet per bord!) de padelstat-rating indien gekend, anders het
    officiële klassement als terugval. Dit vervangt de vorige, strengere
    "beide spelers op dit bord moeten padelstat hebben, anders valt het HELE
    bord terug op officieel"-conventie — die liet de edge/simulatie
    STRUCTUREEL vaak terugvallen op klassement zodra ook maar 1 van de 4
    spelers geen padelstat had (heel gebruikelijk voor tegenstanders).

    Returns None als GEEN van beide bronnen een waarde heeft voor deze
    speler (de aanroeper moet dat geval afhandelen — geen educated guess)."""
    if padelstat_ratings:
        val = padelstat_ratings.get(str(pid))
        if val is not None:
            return float(val)
    if official_ranks:
        val = official_ranks.get(str(pid))
        if val is not None:
            return float(val)
    return None


def estimate_win_probability(our_avg: Optional[float], their_avg: Optional[float], scale: float = 300.0) -> Optional[float]:
    """PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17: RUWE,
    Elo-achtige logistische schatting van de winkans voor ONS op dit ene
    bord, gebaseerd op het (ongeknipte) verschil in effectieve rating.

        p = 1 / (1 + 10^(-(our_avg - their_avg) / scale))

    `scale` bepaalt hoe snel de winkans oploopt met het ratingverschil — een
    KLEINERE scale maakt elk verschil impactvoller. scale=300 is een
    vertrekpunt, GEEN gevalideerde, empirisch bepaalde waarde voor padel: dit
    is uitdrukkelijk een HEURISTIEK, geen statistisch onderbouwd model (zie
    ook de verplichte UI-caveat in page_lineup_lab.py).

    Returns None als (een van) beide gemiddelden onbekend zijn — de
    aanroeper toont dan 'onbekend' i.p.v. een verzonnen getal."""
    if our_avg is None or their_avg is None:
        return None
    diff = our_avg - their_avg
    try:
        return 1.0 / (1.0 + math.pow(10.0, -diff / scale))
    except OverflowError:
        return 0.0 if diff < 0 else 1.0


def risk_note_for_probability(p: Optional[float]) -> str:
    """Leesbare risico-omschrijving bij een winkans-schatting."""
    if p is None:
        return "onbekend (onvoldoende data voor een schatting)"
    if p >= 0.75:
        return "duidelijke favoriet"
    if p >= 0.6:
        return "lichte voorsprong"
    if p > 0.4:
        return "onzeker, ongeveer in evenwicht"
    if p > 0.25:
        return "lichte achterstand"
    return "duidelijk onderliggend"


def matchup_edge(our_ranks: List[Optional[float]], their_ranks: List[Optional[float]]) -> float:
    """Ruwe, transparante inschatting van het verschil in slagkracht,
    genormaliseerd naar ongeveer [-1, 1] — behouden voor de interne
    kandidaat-rangschikking (total_score) en achterwaartse compatibiliteit.
    Voor een interpreteerbare winkans, gebruik estimate_win_probability()
    (die het ONGEKNIPTE verschil gebruikt, niet deze afgeknipte waarde)."""
    ours = [r for r in our_ranks if r is not None]
    theirs = [r for r in their_ranks if r is not None]
    if not ours or not theirs:
        return 0.0
    diff = (sum(ours) / len(ours)) - (sum(theirs) / len(theirs))
    return max(-1.0, min(1.0, diff / 150.0))


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17
# ─────────────────────────────────────────────
def _all_perfect_matchings(players: List[str]) -> List[List[frozenset]]:
    if len(players) == 0:
        return [[]]
    if len(players) % 2 != 0:
        return []
    first, rest = players[0], players[1:]
    out: List[List[frozenset]] = []
    for i, partner in enumerate(rest):
        remaining = rest[:i] + rest[i + 1:]
        for sub in _all_perfect_matchings(remaining):
            out.append([frozenset({first, partner})] + sub)
    return out


DEFAULT_MAX_THEORETICAL_LINEUPS = 300


def generate_all_opponent_lineups(
    opponent_players: List[dict],
    total_boards: int,
    opponent_official_ranks: Optional[Dict[str, Optional[float]]] = None,
    max_variants: int = DEFAULT_MAX_THEORETICAL_LINEUPS,
) -> Tuple[List[List[dict]], dict]:
    """Genereert ALLE theoretisch mogelijke opstellingen die de tegenstander
    kan vormen, MET toepassing van de officiële regel (SOM-gebaseerd,
    uitsluitend officieel klassement)."""
    ids = [str(p["user_id"]) for p in opponent_players]
    name_by_id = {str(p["user_id"]): p.get("name", str(p["user_id"])) for p in opponent_players}
    rank_by_id = {pid: (opponent_official_ranks or {}).get(pid) for pid in ids}

    needed = 2 * total_boards
    if needed <= 0 or len(ids) < needed:
        return [], {
            "total_theoretical": 0, "truncated": False,
            "players_used": len(ids), "resting_combinations": 0,
        }

    resting_groups = list(itertools.combinations(ids, needed))
    all_lineups: List[List[dict]] = []
    total_theoretical = 0

    for playing_ids in resting_groups:
        matchings = _all_perfect_matchings(list(playing_ids))
        for matching in matchings:
            def _pair_strength(pair):
                vals = [rank_by_id.get(pid) for pid in pair]
                known = [v for v in vals if v is not None]
                return sum(known) if known else None

            groups: Dict[Optional[float], List[frozenset]] = {}
            for pair in matching:
                groups.setdefault(_pair_strength(pair), []).append(pair)
            known_keys = sorted((k for k in groups if k is not None), reverse=True)
            ordered_groups = [groups[k] for k in known_keys]
            if None in groups:
                ordered_groups.append(groups[None])

            group_perms = [list(itertools.permutations(g)) for g in ordered_groups]
            for combo in itertools.product(*group_perms):
                ordered_pairs = [pair for grp in combo for pair in grp]
                total_theoretical += 1
                if len(all_lineups) >= max_variants:
                    continue
                boards = []
                for pair in ordered_pairs:
                    p1, p2 = tuple(pair)
                    boards.append({"opponent_pair": [
                        {
                            "name": name_by_id.get(p1, p1), "user_id": p1,
                            "ranking": (f"P{int(rank_by_id[p1])}" if rank_by_id.get(p1) is not None else None),
                        },
                        {
                            "name": name_by_id.get(p2, p2), "user_id": p2,
                            "ranking": (f"P{int(rank_by_id[p2])}" if rank_by_id.get(p2) is not None else None),
                        },
                    ]})
                all_lineups.append(boards)

    meta = {
        "total_theoretical": total_theoretical,
        "truncated": total_theoretical > len(all_lineups),
        "players_used": len(ids),
        "resting_combinations": len(resting_groups),
    }
    return all_lineups, meta


# ─────────────────────────────────────────────
# Scenario-analyse: onze beste tegenzet per mogelijk tegenstander-scenario
# ─────────────────────────────────────────────
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
    tournament_rules_dict: Optional[dict] = None,
    win_probability_scale: float = 300.0,
) -> Tuple[List[dict], bool]:
    """
    Zoekt, voor een SPECIFIEK tegenstander-scenario, de beste koppelvorming
    aan ONZE kant.

    STRIKTE SCHEIDING (PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_
    2026-09-17):
      - REGLEMENT (bordvolgorde + puntengrens): uitsluitend
        `player_official_ranks` (ONZE spelers) en het 'ranking'-tekstveld op
        elk tegenstander-bord (HUN officiële klassement). GEEN padelstat.
        `player_official_ranks` moet een STRIKT officieel-klassement-dict
        zijn (geen padelstat-fallback) — gebruik has_missing_official_rank()
        in de aanroeper om ontbrekende waarden te signaleren.
      - SIMULATIE (win_probability/edge): per speler, padelstat
        (`player_ratings` voor ons, `opponent_ratings` voor hen) bij
        voorkeur, met een terugval naar het officiële klassement PER SPELER
        (niet meer per bord/paar) via effective_simulation_rating().

    player_official_ranks: VERPLICHT voor correcte werking indien
      tournament_rules_dict is meegegeven of indien de bordvolgorde
      betrouwbaar moet zijn. Ontbreekt dit (None), dan wordt player_ratings
      NOODGEDWONGEN ook voor de reglement-ordening gebruikt (achterwaartse
      compatibiliteit voor aanroepers die nog geen apart officieel-
      klassement-dict opbouwen) — de aanroeper krijgt dan GEEN garantie dat
      dit reglementair correct is; gebruik has_missing_official_rank() om
      dat expliciet te checken/melden.

    Returns: (resultaten, truncated) — resultaten = lijst van
      {"total_score", "expected_boards_won", "assignment": [...],
       "rotations": [...], "all_valid": bool}
      'assignment'-items bevatten nu ook "win_probability", "risk_note",
      "our_effective_rating", "their_effective_rating" naast de bestaande
      "synergy"/"edge"/"edge_scale"/"opponent_board"/"our_pair".
    """
    candidates, truncated = optimize_lineup(players, required, own_synergy_fn, top_n=candidate_pool)
    if not candidates:
        return [], truncated

    sorted_boards = _sort_boards_by_opponent_official_rank(opponent_boards)
    n_boards = len(sorted_boards)
    # Reglement-ordening: UITSLUITEND officieel klassement. Bij ontbreken
    # (None meegegeven) val terug op player_ratings ENKEL als noodgreep voor
    # achterwaartse compatibiliteit — zie docstring hierboven.
    regulation_ranks = player_official_ranks if player_official_ranks is not None else player_ratings

    results = []
    for synergy_total, pairs in candidates:
        pair_list = list(pairs)

        rotation_eval = filter_and_order_lineup_by_rotations(
            pair_list, regulation_ranks, rules=tournament_rules_dict,
        )
        if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
            continue  # buiten de puntengrens -> uitsluiten, niet tonen.

        ordered_our_pairs = rotation_eval["ordered_pairs"]
        n = min(len(ordered_our_pairs), n_boards)
        if n == 0:
            continue
        ordered_our_pairs = ordered_our_pairs[:n]

        total = 0.0
        expected_boards_won = 0.0
        assignment = []
        for board_idx in range(n):
            p1, p2 = tuple(ordered_our_pairs[board_idx])
            syn = own_synergy_fn(p1, p2)
            board = sorted_boards[board_idx]
            opp_pair = board.get("opponent_pair", []) or []

            # SIMULATIE: per speler effectieve rating (padelstat bij
            # voorkeur, officieel als terugval) — GEEN alles-of-niets meer
            # per bord.
            our_eff = [
                effective_simulation_rating(p1, player_ratings, player_official_ranks),
                effective_simulation_rating(p2, player_ratings, player_official_ranks),
            ]
            their_eff = [
                effective_simulation_rating(
                    p.get("user_id"), opponent_ratings,
                    {p.get("user_id"): parse_ranking(p.get("ranking"))},
                )
                for p in opp_pair
            ]
            our_eff_known = [v for v in our_eff if v is not None]
            their_eff_known = [v for v in their_eff if v is not None]
            our_avg = (sum(our_eff_known) / len(our_eff_known)) if our_eff_known else None
            their_avg = (sum(their_eff_known) / len(their_eff_known)) if their_eff_known else None

            edge = matchup_edge(our_eff, their_eff)
            win_prob = estimate_win_probability(our_avg, their_avg, scale=win_probability_scale)
            if win_prob is not None:
                expected_boards_won += win_prob

            total += syn + edge
            assignment.append({
                "our_pair": (p1, p2),
                "synergy": round(syn, 3),
                "edge": round(edge, 3),
                "win_probability": round(win_prob, 3) if win_prob is not None else None,
                "risk_note": risk_note_for_probability(win_prob),
                "our_effective_rating": round(our_avg, 1) if our_avg is not None else None,
                "their_effective_rating": round(their_avg, 1) if their_avg is not None else None,
                "opponent_board": board,
            })
        results.append({
            "total_score": round(total, 3),
            "expected_boards_won": round(expected_boards_won, 2),
            "assignment": assignment,
            "rotations": rotation_eval["rotations"],
            "all_valid": rotation_eval["all_valid"],
        })

    # PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17: sorteer
    # op expected_boards_won (het interpreteerbare, aan Kim getoonde getal)
    # i.p.v. het abstracte total_score — bij gelijke expected_boards_won
    # blijft total_score de tiebreaker (fijnere synergie-onderscheiding).
    seen = set()
    deduped = []
    for r in sorted(results, key=lambda x: (-x["expected_boards_won"], -x["total_score"])):
        key = tuple(sorted(a["our_pair"] for a in r["assignment"]))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped[:top_n], truncated
