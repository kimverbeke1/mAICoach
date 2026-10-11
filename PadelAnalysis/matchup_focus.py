"""
matchup_focus.py - "Winkans per match" van een gekozen speler of koppel: de laagste en hoogste winkans per match
(R1 M1, R1 M2, R2 M1, R2 M2) over ALLE mogelijke tegenstander-koppels.
Zuivere logica: geen Streamlit, geen Firestore. De rekenkern wordt als functie meegegeven (zie
test_matchup_focus.py).
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_FOCUS_2026-10-11 (op verzoek van Kim: "bij filter Anneleen en Evy zie ik toch nog matchen van
Anneleen en Klaudia. Zou ook handig zijn om met je gefilterde resultaat meteen in 1 lijn het min/max winspercentage te
zien per match voor dat koppel")
--------------------------------------------------------------------------
ACHTERGROND: een matchup in de platte tabel is een volledige opstelling (4 matchen). Kies je het koppel Anneleen + Evy,
dan staan ze in precies 1 match van elke rij; de andere 3 matchen (bv. Anneleen + Klaudia) horen bij de rest van die
opstelling. Dat is correct, maar niet wat je wilt zien. Hier wordt daarom per match gewerkt:
  - per match (rotatie + plaats) de laagste en hoogste winkans van het gekozen koppel (of de gekozen speler, met elke
    partner) tegen elk mogelijk tegenstander-koppel op die plaats;
  - een lijst van die matchen (ons duo, tegenstander, winkans).
De winkans van een match hangt enkel af van het eigen koppel en het tegenstander-koppel (niet van de rest van de
opstelling). Daarom wordt ze per combinatie (plaats, ons koppel, tegenstander-koppel) 1x berekend, met een volledige
geldige eigen opstelling en tegenstander-opstelling als drager: precies dezelfde rekenkern als in de matchup-tabel, zodat
de getallen overeenkomen.
"""
import time
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import matchup_universe as mu


def slot_label(slot: int, mpr: int = 2) -> str:
    """Plaats 0 -> "R1 M1", plaats 1 -> "R1 M2", plaats 2 -> "R2 M1", ..."""
    return f"R{slot // mpr + 1} M{slot % mpr + 1}"


def own_items_from_keys(own_players: Iterable, own_pair_keys: Iterable) -> List[frozenset]:
    """Gekozen eigen spelers (id's) en koppels (sleutels "a|b") -> lijst van sets van 1 of 2 id's."""
    items = [frozenset({str(p)}) for p in (own_players or ())]
    items += [frozenset(str(x) for x in str(pk).split("|")) for pk in (own_pair_keys or ())]
    return items


def opp_items_from_keys(opp_players: Iterable, opp_pairs: Iterable) -> List[frozenset]:
    """Gekozen tegenstander-spelers ("id:UID") en -koppels ("id:A|id:B") -> lijst van sets van 1 of 2 id's."""
    items: List[frozenset] = []
    for k in opp_players or ():
        k = str(k)
        if k.startswith("id:"):
            items.append(frozenset({k[3:]}))
    for pk in opp_pairs or ():
        delen = [x[3:] for x in str(pk).split("|") if x.startswith("id:")]
        if len(delen) == 2:
            items.append(frozenset(delen))
    return items


def build_slot_map(keys: Iterable, opp_items: Optional[List[frozenset]] = None, require_vs: bool = False) -> Dict[int, dict]:
    """{plaats: {tegenstander-koppel (frozenset): een opstelling-sleutel waarin dat koppel op die plaats staat}}.
    Met `require_vs` blijven enkel koppels over die (minstens) 1 van de gekozen tegenstander-items bevatten."""
    out: Dict[int, dict] = {}
    for key in keys:
        for s, o in enumerate(key):
            fo = frozenset(str(x) for x in o)
            if require_vs and opp_items and not any(it <= fo for it in opp_items):
                continue
            out.setdefault(s, {}).setdefault(fo, key)
    return out


def own_slot_options(item: frozenset, own_options: Iterable) -> Dict[int, dict]:
    """{plaats: {eigen koppel (frozenset): een eigen opstelling (optie) met dat koppel op die plaats}} voor alle koppels
    die `item` (1 speler of 1 koppel) bevatten. Een optie = (ordered_pairs, ...), zoals _collect_valid_own_options()."""
    item = frozenset(str(x) for x in item)
    out: Dict[int, dict] = {}
    for opt in own_options:
        for s, p in enumerate(opt[0]):
            fp = frozenset(str(x) for x in p)
            if item <= fp:
                out.setdefault(s, {}).setdefault(fp, opt)
    return out


def focus_rows(
    item: frozenset, own_options: Iterable, opp_slot: Dict[int, dict],
    compute_fn: Callable, boards_fn: Callable, time_budget: float = 25.0,
) -> Tuple[List[dict], dict]:
    """Eén rij per (plaats, eigen koppel, tegenstander-koppel): {"slot", "own", "opp", "wp"}.
    `compute_fn(eigen_geordende_koppels, boards)` en `boards_fn(sleutel)` zijn de rekenkern en de bordenbouwer.
    Geeft (rijen, info) terug; info = {"n_skipped", "timed_out"}."""
    own_slot = own_slot_options(item, own_options)
    boards_cache: dict = {}
    rows: List[dict] = []
    n_skipped = 0
    timed_out = False
    t0 = time.perf_counter()
    for s in sorted(own_slot):
        for P, opt in own_slot[s].items():
            for O, key in opp_slot.get(s, {}).items():
                if rows and time.perf_counter() - t0 > time_budget:
                    timed_out = True
                    break
                if key not in boards_cache:
                    boards_cache[key] = boards_fn(key)
                boards = boards_cache[key]
                if len(boards) != len(opt[0]):
                    n_skipped += 1
                    continue
                comp = compute_fn(opt[0], boards)
                a = (comp.get("assignment") or [])[s] if len(comp.get("assignment") or []) > s else None
                if a is None:
                    n_skipped += 1
                    continue
                ons = frozenset(str(x) for x in a.get("our_pair") or ())
                hun = frozenset(
                    str(p.get("user_id")) for p in ((a.get("opponent_board") or {}).get("opponent_pair") or [])
                )
                if ons != P or hun != O:
                    n_skipped += 1  # de rekenkern plaatste de koppels anders dan verwacht: liever overslaan dan een gok
                    continue
                rows.append({"slot": s, "own": P, "opp": O, "wp": a.get("win_probability")})
            if timed_out:
                break
        if timed_out:
            break
    return rows, {"n_skipped": n_skipped, "timed_out": timed_out}


def summarize(rows: List[dict]) -> dict:
    """{"per_slot": {plaats: {"min","max","n","min_row","max_row"}}, "overall": {...} | None, "n_unknown": int}.
    Rijen zonder bekende winkans tellen niet mee voor min/max maar wel voor n_unknown."""
    per_slot: Dict[int, dict] = {}
    alle: List[dict] = []
    n_unknown = 0
    for r in rows:
        if r.get("wp") is None:
            n_unknown += 1
            continue
        alle.append(r)
        per_slot.setdefault(r["slot"], []).append(r)

    def _stat(lijst: List[dict]) -> dict:
        lo = min(lijst, key=lambda r: r["wp"])
        hi = max(lijst, key=lambda r: r["wp"])
        return {"min": lo["wp"], "max": hi["wp"], "n": len(lijst), "min_row": lo, "max_row": hi}

    return {
        "per_slot": {s: _stat(v) for s, v in sorted(per_slot.items())},
        "overall": _stat(alle) if alle else None,
        "n_unknown": n_unknown,
    }


def format_range(lo: float, hi: float) -> str:
    """0.352, 0.618 -> "35% – 62%"; gelijke waarden -> "35%"."""
    a, b = round(lo * 100), round(hi * 100)
    return f"{a}%" if a == b else f"{a}% \u2013 {b}%"


def summary_line(label: str, stats: dict, mpr: int = 2) -> str:
    """Eén regel: "**Anneleen + Evy** · R1 M1: 35% – 62% · R1 M2: ... · **alle matchen: 28% – 71%**"."""
    delen = [f"**{label}**"]
    for s, st_ in (stats.get("per_slot") or {}).items():
        delen.append(f"{slot_label(s, mpr)}: {format_range(st_['min'], st_['max'])}")
    if stats.get("overall"):
        o = stats["overall"]
        delen.append(f"**alle matchen: {format_range(o['min'], o['max'])}**")
    else:
        delen.append("winkans onbekend (ontbrekend klassement/padelstat)")
    return " \u00b7 ".join(delen)
