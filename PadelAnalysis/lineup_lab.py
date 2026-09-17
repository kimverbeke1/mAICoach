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

--------------------------------------------------------------------------
PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17 (op verzoek van Kim,
kritieke bugfix: "hou ook rekening met de officiële regels voor opstelling
spelers match1/match2")
--------------------------------------------------------------------------
BUG (opgelost): optimize_lineup_vs_scenario() zocht voor elke kandidaat-
koppelverdeling van ONS naar de SCORE-MAXIMALISERENDE toewijzing van onze
paren aan hun borden (`itertools.permutations(range(n_boards), n)`, alle
mogelijke toewijzingen doorlopen en de beste kiezen). Dat is GEEN geldige
weergave van de werkelijkheid: in het echte interclub-reglement leggen BEIDE
teams onafhankelijk van elkaar hun eigen bordvolgorde vast (sterkste paar op
Match 1, aflopend volgens het OFFICIËLE klassement), en wordt bord-tegen-
bord gespeeld (Match 1 vs Match 1, Match 2 vs Match 2, ...). Er is dus GEEN
vrije keuze om, voor eenzelfde koppelverdeling, ons zwakste paar tegen hun
zwakste bord te laten uitkomen als dat toevallig een hogere score oplevert -
die vrijheid bestond in de code, maar niet in de werkelijkheid. De regel
werd voorheen enkel gebruikt om ACHTERAF een "Match N"-label op te plakken
in de Rotatieplanner-UI (_rank_pairs_by_official_rank in page_lineup_lab.py),
niet om de score zelf te bepalen.

Fix: optimize_lineup_vs_scenario() past de regel nu ZELF, INTERN toe, voor
beide zijden onafhankelijk:
  1. Hun borden (opponent_boards) worden ALTIJD eerst herordend op hun
     OFFICIËLE klassement (_sort_boards_by_opponent_official_rank) - los van
     de volgorde waarin ze zijn meegegeven (historische data heeft immers
     geen gegarandeerde sterkte-volgorde; board_position uit
     opponent_scout.py is enkel de tabelvolgorde op het uitslagenblad, geen
     bevestigde ranking).
  2. Voor ELKE kandidaat-koppelverdeling van ons wordt ONZE bordvolgorde
     ZELF ook bepaald via de officiële regel (rank_pairs_by_official_rank,
     nu een publieke, canonieke functie i.p.v. een privé-kopie in
     page_lineup_lab.py), op basis van player_official_ranks (met
     player_ratings als terugval).
  3. Bord i (ons, na herordening) speelt VERPLICHT tegen bord i (hen, na
     herordening) - geen enkele andere toewijzing wordt nog overwogen.
Gevolg: de itertools.permutations-zoektocht is volledig verdwenen (sneller
EN correcter). De berekende scores kunnen HOGER of LAGER uitvallen dan
voorheen (meestal iets lager, omdat de kunstmatige "beste toewijzing"-vrijheid
wegvalt) - dat is een BEWUSTE, gewenste wijziging, geen regressie: de
getoonde cijfers weerspiegelen nu een opstelling die ook echt, reglementair
zo gespeeld zou worden.

--------------------------------------------------------------------------
PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17 (op verzoek van
Kim: "ik wil alle scenario's bekijken en voor elk van hun opstellingen, onze
beste opstelling daar tegenover zetten")
--------------------------------------------------------------------------
NIEUW (geen bugfix): tot nu toe kon de "Opstelling-scenario's"-sectie in
page_lineup_lab.py uitsluitend rekenen op HISTORISCH AL GESPEELDE
opstellingen van de tegenstander (bundle["previous_fixtures"], typisch maar
1-3 stuks beschikbaar dit seizoen). Kim wil ALLE THEORETISCH MOGELIJKE
opstellingen bekijken die de tegenstander zou kunnen kiezen uit een door Kim
aangeduide groep spelers, niet enkel wat ze al eerder deden.

Nieuwe functies:
  - _all_perfect_matchings(players): exhaustieve enumeratie van alle manieren
    om een (even) groep spelers in paren te verdelen. Zuivere combinatoriek,
    geen enkele aanname over sterkte.
  - generate_all_opponent_lineups(opponent_players, total_boards,
    opponent_official_ranks, max_variants): bouwt hierop verder en past de
    officiële regel toe (zie hierboven) om, per mogelijke koppelverdeling,
    de (of bij gelijke sterkte: ALLE) geldige bordvolgorde(s) te bepalen -
    inclusief het geval waarbij de tegenstander MEER spelers ter beschikking
    heeft dan er wedstrijden zijn (dan wordt ook "wie rust" als aparte
    keuze meegeteld, via itertools.combinations). Geeft resultaten terug in
    het bestaande "boards"-formaat, zodat ze DIRECT aan
    optimize_lineup_vs_scenario() doorgegeven kunnen worden - exact dezelfde
    functie die ook de historische scenario's en de Rotatieplanner al
    gebruiken, nu dus ook hergebruikt voor volledig theoretische scenario's.

Kim's eigen, bevestigde rekensom (zie het gesprek): bij N spelers, allemaal
gelijk geklasseerd (geen afdwingbare volgorde), is het aantal opstellingen
N!/2^(N/2); zodra klassementen wél overal een volgorde afdwingen, valt dit
terug tot enkel (N-1)!! (de bordvolgorde ligt dan vast per koppelverdeling).
Beide grensgevallen worden door generate_all_opponent_lineups() correct
gegenereerd (volledig gelijke/onbekende sterkte -> alle ordeningen; volledig
verschillende sterkte -> exact 1 ordening per koppelverdeling; gemengde
gevallen -> alles ertussenin, per sterkte-groep apart).
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
# Officiële bordvolgorde-regel (gedeeld: eigen kant EN tegenstander-kant)
# ─────────────────────────────────────────────
def rank_pairs_by_official_rank(pairs: List[frozenset], official_ranks: Dict[str, Optional[float]]) -> List[frozenset]:
    """PADEL_ANALYSIS_MATCH1_STRONGEST_RULE_2026-09-14 / PADEL_ANALYSIS_
    OFFICIAL_BOARD_ORDER_FIX_2026-09-17: sorteert een lijst koppels (frozensets
    van 2 speler-id's) aflopend op de sterkte van het paar (het HOOGSTE
    officiële klassement van de twee spelers in dat paar) - het paar met de
    sterkste speler komt eerst (= 'Match 1' / Bord 1).

    Dit is de PUBLIEKE, canonieke versie (voorheen een privé-kopie
    '_rank_pairs_by_official_rank' in page_lineup_lab.py, enkel gebruikt om
    ACHTERAF een label op te plakken). Sinds PADEL_ANALYSIS_OFFICIAL_BOARD_
    ORDER_FIX_2026-09-17 gebruikt optimize_lineup_vs_scenario() dezelfde
    regel INTERN om de bordvolgorde zelf te bepalen (niet enkel voor de
    latere UI-labeling) - vandaar de verhuizing naar hier, zodat er maar één
    plek is die deze regel definieert."""
    def pair_strength(pair):
        return max((official_ranks.get(pid) or 0) for pid in pair)
    return sorted(pairs, key=pair_strength, reverse=True)


def _sort_boards_by_opponent_official_rank(opponent_boards: List[dict]) -> List[dict]:
    """PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17.

    Sorteert tegenstander-borden op HUN officiële klassement (het
    'ranking'-veld per speler op dat bord), aflopend - het bord met de
    sterkste tegenstander-speler komt eerst (= hun Bord 1).

    Dit is bewust gebaseerd op het OFFICIËLE klassement (parse_ranking van
    het 'ranking'-tekstveld), NIET op padelstats.be playing strength - de
    regel zelf is een reglementair gegeven (gebaseerd op het officiële TVL-
    klassement), terwijl padelstat elders enkel gebruikt wordt om de
    verwachte MATCHUP-EDGE in te schatten (een aparte vraag: 'hoe sterk
    verschillen twee gekoppelde borden van elkaar', niet 'wie moet op welk
    bord staan').

    Ontbreekt het 'ranking'-veld voor (een deel van) een bord, dan telt dat
    bord als sterkte 0 voor de sortering - een ontbrekend klassement is geen
    reden om een bord kunstmatig hoger te plaatsen. Python's sort is stabiel,
    dus bij gelijke sterkte blijft de oorspronkelijke (meegegeven) volgorde
    behouden."""
    def strength(board):
        pair = board.get("opponent_pair", []) or []
        vals = [parse_ranking(p.get("ranking")) for p in pair]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else 0
    return sorted(opponent_boards, key=strength, reverse=True)


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
) -> Tuple[List[dict], bool]:
    """
    Zoekt, voor een SPECIFIEK tegenstander-scenario (hun koppels, bv. uit een
    eerdere wedstrijd OF een volledig theoretisch scenario - zie
    generate_all_opponent_lineups()), de beste koppelvorming aan ONZE kant.

    PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17 (kritieke bugfix, zie
    moduledocstring voor het volledige, gemelde probleem): bepaalt NIET
    LANGER de score-maximaliserende toewijzing van onze paren aan hun borden
    via een vrije zoektocht (dat overtrad de echte 'sterkste paar op Match 1'
    -regel). In plaats daarvan wordt de OFFICIËLE regel nu ZELF, intern,
    consequent toegepast aan BEIDE kanten:
      1. hun borden worden herordend op HUN officiële klassement (aflopend);
      2. voor elke kandidaat-koppelverdeling van ons wordt ONZE bordvolgorde
         ZELF ook bepaald via diezelfde regel (op player_official_ranks, met
         player_ratings als terugval);
      3. bord i (ons) speelt VERPLICHT tegen bord i (hen) - geen andere
         toewijzing wordt nog overwogen.
    Dit is sneller (geen permutatie-zoektocht meer nodig) EN correcter.

    opponent_boards: lijst van {"opponent_pair": [{"name","user_id","ranking"(optioneel)}, ...]}
    player_ratings: pid -> padelstats.be playing strength voor ONZE spelers
      (HOGER = STERKER). Wordt gebruikt wanneer voor een bord ook de
      tegenstander-padelstat gekend is (zie opponent_ratings) - enkel voor de
      EDGE-berekening, niet voor de bordvolgorde zelf.
    player_official_ranks: pid -> officieel TVL-klassement voor ONZE spelers.
      Bepaalt ONZE bordvolgorde (stap 2 hierboven), en dient daarnaast als
      terugval-schaal voor de edge-berekening wanneer de tegenstander geen
      padelstat-rating heeft. Ontbreekt dit, dan valt de code terug op
      player_ratings voor BEIDE doeleinden (oud gedrag, met het risico op
      een schaalmismatch bij de edge - zie PADEL_ANALYSIS_MATCHUP_SCALE_
      CONSISTENCY_2026-09-15).
    opponent_ratings: user_id (van TEGENSTANDER-spelers) -> padelstats.be
      playing strength, enkel gebruikt voor de EDGE-berekening (niet voor de
      bordvolgorde, die is altijd op het OFFICIËLE klassement gebaseerd).

    Returns: (resultaten, truncated) — resultaten = lijst van
      {"total_score", "assignment": [{"our_pair":(p1,p2), "synergy":.., "edge":.., "opponent_board":{...}}]}
      gesorteerd van beste naar slechtste, max top_n.
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
        ordered_our_pairs = rank_pairs_by_official_rank(pair_list, fallback_our_ranks)
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
        results.append({"total_score": round(total, 3), "assignment": assignment})

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
    genereren; die groepen tellen in de praktijk typisch 4-8 spelers.
    Complexiteit: (n-1)!! resultaten, elk O(n) om op te bouwen."""
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
    (sterkste paar op Match 1, aflopend per officieel klassement).

    opponent_players: [{"user_id":.., "name":..}, ...] - de spelers die Kim
        aanduidt als 'komt waarschijnlijk in aanmerking' (bv. de volledige
        gekende roster, of een handmatig ingeperkte selectie - net zoals bij
        'Beschikbare eigen spelers' voor onze eigen kant).
    total_boards: hoeveel wedstrijden er gespeeld worden (dus 2*total_boards
        spelers effectief op het veld; is opponent_players groter, dan wordt
        ELKE mogelijke keuze wie er rust OOK meegeteld/gegenereerd, via
        itertools.combinations - exact de "wie speelt" x "hoe verdelen we
        hen"-vermenigvuldiging die Kim zelf berekende).
    opponent_official_ranks: user_id -> officieel klassement (hoger=sterker).
        Ontbreekt dit voor (een deel van) de groep, dan worden paren met een
        onbekende sterkte behandeld als "gelijk aan elkaar" (de regel legt
        dan geen volgorde op TUSSEN HEN ONDERLING, wel nog t.o.v. paren met
        een gekende, hogere sterkte) - ALLE onderling geldige volgordes
        tussen zulke gelijk-sterke paren worden als aparte varianten
        teruggegeven. Dit reproduceert precies Kim's eigen, bevestigde
        wiskunde: bij volledig gelijke/onbekende sterkte is het aantal
        opstellingen N!/2^(N/2); zodra de regel overal een volgorde afdwingt,
        valt dit terug tot (N-1)!! - en bij een gemengde groep (sommige
        spelers wel, andere geen gekend klassement) valt het resultaat
        ergens daartussenin, per sterkte-groep apart geteld.

    Returns (lineups, meta):
        lineups: lijst van "boards"-lijsten, ELK in het bestaande, standaard
            formaat [{"opponent_pair": [{"name","user_id","ranking"}, ...]}, ...],
            reeds in bordvolgorde (index 0 = Bord 1) volgens de officiële
            regel (of, bij gelijke/onbekende sterkte, in een van de geldige
            volgordes) - rechtstreeks bruikbaar als `opponent_boards`-
            argument voor optimize_lineup_vs_scenario().
        meta: {"total_theoretical": int, "truncated": bool,
               "players_used": int, "resting_combinations": int}
            "total_theoretical" is het WERKELIJKE, volledige aantal (ook als
            er door max_variants uiteindelijk minder gematerialiseerd/
            teruggegeven worden), zodat de UI altijd het eerlijke totaal kan
            tonen, ook wanneer niet alles berekend wordt.
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
                vals = [rank_by_id.get(pid) for pid in pair]
                vals = [v for v in vals if v is not None]
                return max(vals) if vals else None

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
