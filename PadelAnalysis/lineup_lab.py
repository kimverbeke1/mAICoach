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
liet dat al toe als "genoeg data"). Fix: CONFIDENCE-SHRINKAGE i.p.v. een
harde aan/uit-drempel:
    weight = known_matches / (known_matches + confidence_k)
    score  = weight * paar_winrate + (1 - weight) * individueel_gemiddelde

--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): matchup_edge() kreeg voor "ons" de padelstats.be playing
strength maar voor "hen" het OFFICIËLE TVL-klassement — twee VERSCHILLENDE
meetsystemen tegenover elkaar. Fix: optimize_lineup_vs_scenario() kiest nu
PER BORD een consistente schaal (beide padelstat, of beide officieel).

--------------------------------------------------------------------------
PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17 (op verzoek van Kim,
kritieke bugfix: "hou ook rekening met de officiële regels voor opstelling
spelers match1/match2")
--------------------------------------------------------------------------
BUG (opgelost): optimize_lineup_vs_scenario() zocht voor elke kandidaat-
koppelverdeling van ONS naar de SCORE-MAXIMALISERENDE toewijzing van onze
paren aan hun borden — een vrijheid die in het echte interclub-reglement
niet bestaat. Fix: de OFFICIËLE regel wordt nu ZELF, intern, consequent
toegepast aan BEIDE kanten (bordvolgorde bepaald door officieel klassement,
Bord i vs Bord i verplicht) — zie ook de verdere verfijning hieronder.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17 (op verzoek van Kim, na
het aanleveren van Reglement_Padel_Senior_Cup.pdf — kritieke correctie)
--------------------------------------------------------------------------
BUG (opgelost): rank_pairs_by_official_rank() vergeleek duo's op basis van
het HOOGSTE individuele klassement van de 2 spelers in dat duo
(`max(official_ranks.get(pid) for pid in pair)`). Het officiële reglement
(art. 6.6): "Tijdens de ontmoeting worden duo's samengesteld op basis van
de SOM van de klassementen van de spelers per rotatie [...] Hierbij moet in
match 1/3 het sterke duo aantreden en in match 2/4 het zwakkere duo." — de
vergelijking gebeurt dus op de SOM van de 2 klassementen, niet op het
hoogste van de twee. Bij twee spelers met klassement P200+P200 (som 400) en
een ander duo met P350+P50 (som 400): deze zouden voorheen VERSCHILLEND
geordend kunnen worden (max 200 vs max 350) terwijl het reglement ze als
GELIJK beschouwt (som 400 = som 400, "mag de ploeg kiezen").
Fix: rank_pairs_by_official_rank() gebruikt nu SUM i.p.v. MAX.

--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_RULES_2026-09-17 (op verzoek van Kim, 3 concrete
vragen na het aanleveren van Reglement_Padel_Senior_Cup.pdf)
--------------------------------------------------------------------------
Kim's vragen:
  1. "paarverdelingen die niet aan de grenzen voldoen mag je uitsluiten en
     niet tonen" — combinaties buiten de toegelaten punten-grenzen PER
     ROTATIE (art. 2.1/9.3.3/9.3.4) moeten uitgesloten worden.
  2. "match 1 van de rotatie = sterkste opstelling" — bevestigd/verfijnd:
     dit geldt PER ROTATIE (2 gelijktijdige wedstrijden), niet over de hele
     ontmoeting heen — zie PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17
     hierboven voor de bijhorende correctie (som i.p.v. max).
  3. Andere tornooien (Mixed, Open, Vrouwen) later — parameters moeten
     zichtbaar/instelbaar zijn per tornooiversie (zie tournament_rules.py +
     page_lineup_lab.py:_render_tournament_rules_selector()).

Nieuwe functies (gebruiken tournament_rules.py, optioneel — bestaande
aanroepers die geen `tournament_rules`/`rules` meegeven blijven ONGEWIJZIGD
werken, geen breaking change):
  - group_boards_into_rotations(): groepeert een geordende lijst borden 2-aan-
    2 (rotatie 1 = index 0-1, rotatie 2 = index 2-3, ...) — reglement 8.7.1:
    "Er worden 4 wedstrijden gespeeld in 2 rotaties (van telkens 2
    wedstrijden gelijktijdig op 2 terreinen)."
  - evaluate_rotation(): voor 2 duo's (1 rotatie) samen: berekent de SOM van
    alle 4 spelers hun klassement, bepaalt de juiste volgorde (sterkste duo
    eerst, som-gebaseerd) en toetst het totaal aan de reglementsgrenzen
    (tournament_rules.rotation_points_bounds_ok). Retourneert ook WAAROM een
    rotatie ongeldig is, zodat de UI dat kan tonen i.p.v. enkel te verbergen.
  - filter_and_order_lineup_by_rotations(): past het bovenstaande toe op een
    VOLLEDIGE koppelverdeling (alle rotaties van 1 ontmoeting ineens):
    ordent élke rotatie intern (som-gebaseerd) en geeft aan of de VOLLEDIGE
    koppelverdeling geldig is (alle rotaties binnen de grenzen) — gebruikt
    door optimize_lineup_vs_scenario() om ongeldige kandidaten uit te
    sluiten (vraag 1) vóór ze uberhaupt gescoord worden.
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
    aan/uit-drempel.
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
# Officiële bordvolgorde-regel (gedeeld: eigen kant EN tegenstander-kant)
# ─────────────────────────────────────────────
def _pair_strength_sum(pair, official_ranks: Dict[str, Optional[float]]) -> float:
    """PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17: SOM van de
    klassementen van de 2 spelers in het duo (reglement art. 6.6), NIET het
    hoogste individuele klassement (dat was de vorige, foutieve conventie)."""
    return sum((official_ranks.get(pid) or 0) for pid in pair)


def rank_pairs_by_official_rank(pairs: List[frozenset], official_ranks: Dict[str, Optional[float]]) -> List[frozenset]:
    """PADEL_ANALYSIS_MATCH1_STRONGEST_RULE_2026-09-14 / PADEL_ANALYSIS_
    OFFICIAL_BOARD_ORDER_FIX_2026-09-17 / PADEL_ANALYSIS_SUM_BASED_PAIR_
    STRENGTH_2026-09-17: sorteert een lijst koppels (frozensets van 2
    speler-id's) aflopend op de SOM van de klassementen van de 2 spelers in
    dat duo (art. 6.6: "op basis van de som van de klassementen van de
    spelers") — het duo met de hoogste som komt eerst (= 'Match 1'/'Match 3'
    / laagst genummerde bord van de rotatie).

    LET OP: deze functie sorteert een VLAKKE lijst (globaal), wat voor een
    ontmoeting van MEER dan 1 rotatie (>2 boards) niet meer overeenkomt met
    het reglement — daar geldt de sterkste-eerst-regel PER ROTATIE apart,
    niet over de hele ontmoeting heen (zie group_boards_into_rotations() /
    evaluate_rotation() hieronder, PADEL_ANALYSIS_ROTATION_RULES_2026-09-17).
    Deze functie blijft bestaan voor het eenvoudige/veelvoorkomende geval van
    exact 1 rotation (2 boards, bv. de Rotatieplanner met 4 spelers) en voor
    achterwaartse compatibiliteit."""
    return sorted(pairs, key=lambda pair: _pair_strength_sum(pair, official_ranks), reverse=True)


def _sort_boards_by_opponent_official_rank(opponent_boards: List[dict]) -> List[dict]:
    """PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17, aangepast in
    PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17.

    Sorteert tegenstander-borden op de SOM van de officiële klassementen van
    de 2 spelers op dat bord (aflopend) — het bord met de hoogste som komt
    eerst (= hun Bord 1). Voorheen (PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_
    2026-09-17, eerste versie) werd het MAXIMUM van de 2 spelers gebruikt;
    dat is gecorrigeerd naar de SOM, consistent met art. 6.6 en met
    rank_pairs_by_official_rank() hierboven.

    Ontbreekt het 'ranking'-veld voor (een deel van) een bord, dan telt die
    speler als sterkte 0 voor de som — een ontbrekend klassement is geen
    reden om een bord kunstmatig hoger te plaatsen. Python's sort is stabiel,
    dus bij gelijke sterkte blijft de oorspronkelijke (meegegeven) volgorde
    behouden."""
    def strength(board):
        pair = board.get("opponent_pair", []) or []
        vals = [parse_ranking(p.get("ranking")) for p in pair]
        return sum(v for v in vals if v is not None)
    return sorted(opponent_boards, key=strength, reverse=True)


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_ROTATION_RULES_2026-09-17: rotatie-gebaseerde regels
# (punten-per-rotatie-grenzen + sterkste-duo-per-rotatie), op verzoek van
# Kim na het aanleveren van Reglement_Padel_Senior_Cup.pdf.
# ─────────────────────────────────────────────
def group_boards_into_rotations(items: list, per_rotation: int = 2) -> List[list]:
    """Groepeert een geordende lijst (borden, of paren) 2-aan-2 (of
    `per_rotation`-aan-`per_rotation`) in opeenvolgende rotaties: rotatie 1 =
    index 0..per_rotation-1, rotatie 2 = de volgende `per_rotation`, enz. —
    reglement art. 8.7.1: "Er worden 4 wedstrijden gespeeld in 2 rotaties
    (van telkens 2 wedstrijden gelijktijdig op 2 terreinen)."

    Een onvolledige laatste groep (te weinig items voor een volle rotatie)
    wordt WEL teruggegeven als aparte, kortere groep — de aanroeper
    beslist zelf hoe daarmee om te gaan (bv. geen punten-check toepassen op
    een onvolledige rotatie)."""
    return [items[i:i + per_rotation] for i in range(0, len(items), per_rotation)]


def evaluate_rotation(
    duo_a: frozenset,
    duo_b: frozenset,
    official_ranks: Dict[str, Optional[float]],
    rules: Optional[dict] = None,
) -> dict:
    """PADEL_ANALYSIS_ROTATION_RULES_2026-09-17.

    Evalueert 1 volledige rotatie (2 duo's = 2 gelijktijdige wedstrijden,
    4 spelers samen) tegen het reglement:
      1. bepaalt welk duo het sterkste is (SOM van de 2 klassementen per
         duo, art. 6.6) -> dat duo hoort op het laagst genummerde bord van
         deze rotatie (Match 1 of Match 3);
      2. berekent de SOM van ALLE 4 spelers samen (de "punten per rotatie")
         en toetst die aan `rules` (tournament_rules.get_afdeling_rules(...),
         of None = geen check/altijd geldig).

    Bij gelijke som (`duo_a` en `duo_b` even sterk): art. 6.6 laatste zin
    ("mag de ploeg kiezen welk duo waar opgesteld wordt") — de MEEGEGEVEN
    volgorde (duo_a eerst) wordt in dat geval behouden, geen dwingende
    herschikking nodig.

    Returns:
        {
          "ordered_pairs": [sterkste_of_gelijk_duo, andere_duo],
          "total_points": float,  # som van alle 4 spelers samen
          "valid": bool,          # False als rules gegeven en buiten bereik
          "reason": str,          # leesbare toelichting (ook bij valid=True)
        }
    """
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
            # tournament_rules niet beschikbaar of onverwachte fout -> nooit
            # blokkeren op een defensieve import-fout, gewoon niet filteren.
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
    """PADEL_ANALYSIS_ROTATION_RULES_2026-09-17.

    Past evaluate_rotation() toe op een VOLLEDIGE koppelverdeling (alle
    rotaties van 1 ontmoeting ineens, in de volgorde waarin `pairs` werd
    meegegeven — groepering via group_boards_into_rotations()).

    Gebruikt door optimize_lineup_vs_scenario() om, VOORDAT er gescoord
    wordt, kandidaten uit te sluiten waarvan minstens 1 rotatie buiten de
    toegelaten puntengrenzen valt (Kim's vraag 1: "paarverdelingen die niet
    aan de grenzen voldoen mag je uitsluiten en niet tonen").

    Returns:
        {
          "ordered_pairs": [...],  # ALLE paren, in de juiste bordvolgorde
                                    # (per rotatie: sterkste eerst)
          "rotations": [ {ordered_pairs, total_points, valid, reason}, ... ],
          "all_valid": bool,       # False zodra 1 rotatie ongeldig is
        }

    Een eventuele onvolledige laatste "rotatie" (oneven totaal aantal paren
    — zou in de praktijk niet mogen voorkomen bij Senior Cup, maar dit blijft
    defensief werken voor andere/toekomstige tornooien met een andere
    structuur) wordt NOOIT als ongeldig beschouwd puur op basis van de
    puntengrens (er is geen "2de duo" om de som mee te vormen)."""
    rotations_raw = group_boards_into_rotations(pairs, per_rotation=2)
    ordered_pairs: List[frozenset] = []
    rotation_results = []
    all_valid = True

    for group in rotations_raw:
        if len(group) < 2:
            # Onvolledige rotatie (oneven totaal aantal paren) -- geen
            # zinvolle som-check mogelijk, gewoon ongewijzigd doorgeven.
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
    PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15.

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

    Bepaalt WELKE schaal gebruikt wordt voor dit ene bord se EDGE-berekening
    (NIET voor de bordVOLGORDE zelf - zie _sort_boards_by_opponent_official_
    rank() daarvoor) en geeft meteen de tegenstander-waarden in die schaal
    terug.

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
    tournament_rules_dict: Optional[dict] = None,
) -> Tuple[List[dict], bool]:
    """
    Zoekt, voor een SPECIFIEK tegenstander-scenario (hun koppels, bv. uit een
    eerdere wedstrijd OF een volledig theoretisch scenario), de beste
    koppelvorming aan ONZE kant.

    PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17 / PADEL_ANALYSIS_SUM_
    BASED_PAIR_STRENGTH_2026-09-17 / PADEL_ANALYSIS_ROTATION_RULES_2026-09-17:
    de bordvolgorde ligt VERPLICHT vast via het officiële klassement (SOM per
    duo, PER ROTATIE van 2 borden — niet globaal over de hele ontmoeting), en
    kandidaten waarvan minstens 1 rotatie buiten de reglementair toegelaten
    puntengrenzen valt, worden UITGESLOTEN (niet enkel gelabeld) zodra
    `tournament_rules_dict` is meegegeven.

    tournament_rules_dict: optioneel, het resultaat van
        tournament_rules.get_afdeling_rules(tornooi, categorie, afdeling)
    Wordt dit NIET meegegeven (None, standaard): GEEN filtering op
    puntengrenzen — volledig achterwaarts compatibel met bestaande
    aanroepers die nog geen tornooi/afdeling geselecteerd hebben.

    opponent_boards: lijst van {"opponent_pair": [{"name","user_id","ranking"(optioneel)}, ...]}
    player_ratings: pid -> padelstats.be playing strength voor ONZE spelers
      (HOGER = STERKER). Enkel gebruikt voor de EDGE-berekening.
    player_official_ranks: pid -> officieel TVL-klassement voor ONZE spelers.
      Bepaalt ONZE bordvolgorde EN de reglement-puntensom, en dient daarnaast
      als terugval-schaal voor de edge-berekening.
    opponent_ratings: user_id (van TEGENSTANDER-spelers) -> padelstats.be
      playing strength, enkel gebruikt voor de EDGE-berekening.

    Returns: (resultaten, truncated) — resultaten = lijst van
      {"total_score", "assignment": [...], "rotations": [...], "all_valid": bool}
      gesorteerd van beste naar slechtste, max top_n. Kandidaten met
      all_valid=False worden NOOIT teruggegeven (uitgesloten, niet enkel
      gemarkeerd) zodra tournament_rules_dict is meegegeven.
    """
    candidates, truncated = optimize_lineup(players, required, own_synergy_fn, top_n=candidate_pool)
    if not candidates:
        return [], truncated

    sorted_boards = _sort_boards_by_opponent_official_rank(opponent_boards)
    n_boards = len(sorted_boards)
    fallback_our_ranks = player_official_ranks if player_official_ranks is not None else player_ratings

    results = []
    for synergy_total, pairs in candidates:
        pair_list = list(pairs)

        # PADEL_ANALYSIS_ROTATION_RULES_2026-09-17: eerst PER ROTATIE (2
        # paren tegelijk) ordenen én toetsen aan de puntengrenzen, i.p.v. de
        # oude, globale rank_pairs_by_official_rank()-sortering over ALLE
        # paren ineens (die geen rekening hield met de rotatie-indeling of
        # de puntengrenzen).
        rotation_eval = filter_and_order_lineup_by_rotations(
            pair_list, fallback_our_ranks, rules=tournament_rules_dict,
        )
        if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
            continue  # Kim's vraag 1: uitsluiten, niet tonen.

        ordered_our_pairs = rotation_eval["ordered_pairs"]
        n = min(len(ordered_our_pairs), n_boards)
        if n == 0:
            continue
        ordered_our_pairs = ordered_our_pairs[:n]

        total = 0.0
        assignment = []
        for board_idx in range(n):
            p1, p2 = tuple(ordered_our_pairs[board_idx])
            syn = own_synergy_fn(p1, p2)
            board = sorted_boards[board_idx]
            scale, their_ranks = _board_rank_scale(board.get("opponent_pair", []) or [], opponent_ratings)
            if scale == "padelstat":
                our_ranks = [player_ratings.get(p1), player_ratings.get(p2)]
            else:
                our_ranks = [fallback_our_ranks.get(p1), fallback_our_ranks.get(p2)]
            edge = matchup_edge(our_ranks, their_ranks)
            total += syn + edge
            assignment.append({
                "our_pair": (p1, p2),
                "synergy": round(syn, 3),
                "edge": round(edge, 3),
                "edge_scale": scale,
                "opponent_board": board,
            })
        results.append({
            "total_score": round(total, 3),
            "assignment": assignment,
            "rotations": rotation_eval["rotations"],
            "all_valid": rotation_eval["all_valid"],
        })

    seen = set()
    deduped = []
    for r in sorted(results, key=lambda x: -x["total_score"]):
        key = tuple(sorted(a["our_pair"] for a in r["assignment"]))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped[:top_n], truncated


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17
# Alle theoretisch mogelijke tegenstander-opstellingen genereren
# ─────────────────────────────────────────────
def _all_perfect_matchings(players: List[str]) -> List[List[frozenset]]:
    """Exhaustieve enumeratie van ALLE manieren om `players` (een even
    aantal) te verdelen in paren. Zuivere combinatoriek, geen enkele aanname
    over sterkte/klassement.

    Enkel bedoeld voor kleine groepen (praktisch tot een 10-tal spelers) -
    gebruikt om ALLE theoretisch mogelijke tegenstander-opstellingen te
    genereren; die groepen tellen in de praktijk typisch 4-8 spelers."""
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
    """
    PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17 (op verzoek
    van Kim): genereert ALLE theoretisch mogelijke opstellingen die de
    tegenstander met `opponent_players` zou kunnen opstellen voor
    `total_boards` wedstrijden, MET toepassing van de officiële regel
    (sterkste paar op Match 1, aflopend per officieel klassement, SOM-
    gebaseerd sinds PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17).

    Returns (lineups, meta) — zie eerdere versie voor volledige details.
    Elke lineup is reeds gesorteerd op sterkte via de SOM-conventie.
    """
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
                # PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17: som i.p.v. max.
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
                    continue  # blijf WEL tellen (voor een eerlijk totaal), stop met materialiseren
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
