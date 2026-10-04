"""
lineup_retrospective.py - Nabeschouwing: per eerder gespeelde ontmoeting de
voorspelde winkans tegenover de echte uitslag, MET de padelstat-/officiële
klassementwaarden van TOEN (niet de huidige), plus een kalibratieblok over
alle gespeelde matchen samen met een instelbare winkansfactor.
--------------------------------------------------------------------------
(Zie eerdere PADEL_ANALYSIS_RETRO_*-markers in de git-historiek voor de
volledige toelichting bij: brondata-prioriteit padelstat/klassement,
parallelle Firestore-batches, snapshot-cache, persistente winkansfactor,
ploegmaten-detectie, eindresultaat-vergelijking, "beste alternatief".)
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_ALL_VALID_DATA_2026-10-04 (op verzoek van Kim: "ik wil
bij de berekening van de kalibratie alle geldige matchdata gebruikt. dus
degene waarbij we de padelstat waarde hebben en resultaat match etc... dat
kiezen van speler mag je weglaten [...] belangrijk is om nu eens te zien in
mijn data: hoeveel matchen komen daar al voor in aanmerking")
--------------------------------------------------------------------------
De kalibratie (Brier-score, kans-klassen, winkansfactor-zoeken) gebruikte
tot nu toe enkel de matchen van de gekozen speler + de handmatig gekozen
ploegmaten (de "Analyseer ook de matchen van"-multiselect). Dat was BEWUST
zo voor de secties "Per match: voorspeld tegenover echt" en "Beste
alternatief" - die hebben de VOLLEDIGE, juiste ploegopstelling van 1
specifieke dag nodig (zie PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04). Maar
voor de KALIBRATIE is die beperking onnodig: elke bord-voorspelling staat
op zich (1 eigen koppel tegen 1 tegenstander-koppel, met een eigen
voorspelde kans en een eigen echte uitslag) - of dat bord toevallig bij een
dames- of herenploeg hoort, speelt voor de Brier-score geen rol.
FIX: gather_all_valid_match_data(profiles, ...) bouwt de encounter-index nu
over ALLE profielen in de database (build_retro_encounter_index() met
allowed_player_ids=None - "geen filter", al een bestaande optie die enkel
nog nooit gebruikt werd), en filtert daarna op rijen waar ZOWEL our_avg als
their_avg als actual_won gekend zijn ("geldige matchdata"). Het aantal
geldige rijen (en het totaal aantal geziene borden) wordt EXPLICIET getoond
in de UI, zodat voortaan meetbaar is hoeveel matchen er effectief
meetellen - dat was voorheen nergens zichtbaar.
De "Analyseer ook de matchen van"-multiselect blijft bestaan, maar ENKEL
nog voor de per-ontmoeting-secties hierboven (voorspeld vs. echt, beste
alternatief) - niet langer voor de kalibratie eronder.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_BIAS_MODEL_2026-10-04 (op verzoek van Kim, met een
concreet voorbeeld: "een match van mezelf en Stijn tegen een ploeg van Kon
Deinze waarbij we 4% kans op winst hadden [op padelstat.be]. Bij mijn
voorbeeld was dat 47%" + "we moeten die brier score fel naar omlaag krijgen
[...] welk model is nodig om dat zo goed mogelijk te doen matchen")
--------------------------------------------------------------------------
Een verschil van 4% (padelstat.be) tegenover 47% (onze formule) is te groot
om enkel met de bestaande 1-parameter-factor (de "steilheid" van de curve)
recht te trekken - dat verandert hoe STERK een ratingverschil doorweegt,
niet of de curve als geheel systematisch te optimistisch/pessimistisch is.
Een bijkomende BIAS-term (een vaste verschuiving van het ratingverschil,
vóór de logistische functie) kan die systematische afwijking wel opvangen:
  p = 1 / (1 + 10^(-(our_avg - their_avg + bias) / scale))
NIEUW, als uitbreiding op de bestaande factor-zoekfunctie:
  - _estimate_win_probability_with_bias(): lokale, PURE herimplementatie
    van dezelfde logistische vorm als ll.estimate_win_probability(), met
    een extra optionele bias-term - GEEN wijziging aan lineup_lab.py of de
    rest van de app, enkel gebruikt binnen deze kalibratieweergave.
  - find_best_scale_and_bias(): doorzoekt een 2D-rooster van (scale, bias)-
    combinaties en geeft de combinatie met de LAAGSTE Brier-score terug,
    naast (ter vergelijking) het resultaat van de bestaande, scale-only
    zoekfunctie - zodat meteen zichtbaar is OF een bias-term echt helpt,
    i.p.v. dat blind aan te nemen.
  - De UI toont beide voorstellen naast elkaar, met een "Toepassen"-knop
    per voorstel (bewaart dan ZOWEL scale als bias; bij het scale-only
    voorstel blijft bias op 0). Bewaring gebeurt in hetzelfde Firestore-
    document als de bestaande winkansfactor (nieuw veld
    "win_probability_bias"), via dezelfde "nooit crashen, enkel minder
    gemak"-aanpak als de bestaande opslag.
  - BEWUST NIET AANGEPAST: de globale DEFAULT_WIN_PROBABILITY_SCALE en de
    rest van de app (matchup-tabel, rotatieplanner, planscherm) gebruiken
    nog steeds de ORIGINELE, bias-vrije formule - dit is en blijft een
    experimentele weergave binnen Nabeschouwing, geen aanpassing van de
    kernformule. Past Kim dit toe en wil hij dit ALGEMEEN doorvoeren, dan
    is dat een aparte, bewuste vervolgstap (buiten deze levering).
"""
import datetime as _dt
import math
import re
from collections import defaultdict
from typing import Dict, List, Optional

import streamlit as st

import lineup_lab as ll
import firebase_service as fb

try:
    import perf_timing as perf
except Exception:  # noqa: BLE001  pragma: no cover
    class _PerfNoop:
        @staticmethod
        def step(_label):
            from contextlib import nullcontext
            return nullcontext()

    perf = _PerfNoop()

SNAPSHOT_COLLECTION = "lineup_snapshots"
_CALIBRATION_SETTINGS_COLLECTION = "app_settings"
_CALIBRATION_SETTINGS_DOC = "retro_calibration"
_DEFAULT_SCALE = ll.DEFAULT_WIN_PROBABILITY_SCALE
_CALIBRATION_BIN_EDGES = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]
_SCALE_SEARCH_RANGE = list(range(50, 801, 5))
# PADEL_ANALYSIS_RETRO_BIAS_MODEL_2026-10-04: grover rooster voor de 2D-zoektocht
# (scale x bias) - fijner zou te traag worden; dit blijft puur rekenwerk, geen I/O.
_SCALE_BIAS_SEARCH_SCALES = list(range(50, 801, 20))
_BIAS_SEARCH_RANGE = list(range(-150, 151, 10))


# --------------------------------------------------------------- datums
def to_iso_date(date_text) -> Optional[str]:
    """TVL-datumtekst ("26/09/2026", "26-09-2026" of al ISO) -> "YYYY-MM-DD".
    Geeft None terug bij een onherkenbaar formaat (nooit een gok)."""
    if not date_text:
        return None
    s = str(date_text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


# ------------------------------------------------- encounter/board-reconstructie
def _encounter_key(m: dict) -> tuple:
    return (m.get("match_date") or "", m.get("encounter") or "")


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


def build_retro_encounter_index(docs: Dict[str, dict], allowed_player_ids=None) -> Dict[tuple, list]:
    """`allowed_player_ids` is een SET van toegelaten spelers, of None voor
    GEEN filter (alle spelers in `docs` tellen mee) - zie
    PADEL_ANALYSIS_RETRO_ALL_VALID_DATA_2026-10-04 voor waar dat laatste nu
    voor gebruikt wordt (kalibratie over alle data)."""
    allowed = {str(p) for p in allowed_player_ids} if allowed_player_ids is not None else None
    index: Dict[tuple, list] = {}
    for pid, doc in docs.items():
        if allowed is not None and str(pid) not in allowed:
            continue
        for m in doc.get("matches", []) or []:
            if m.get("match_type") != "interclub":
                continue
            index.setdefault(_encounter_key(m), []).append((pid, m))
    return index


def list_retro_encounters(index: Dict[tuple, list]) -> List[tuple]:
    """Meest recent eerst, gesorteerd op echte datum (niet de ruwe tekst)."""
    items = []
    for key, entries in index.items():
        date, encounter = key
        reeks = None
        for _pid, m in entries:
            if m.get("reeks_name"):
                reeks = m.get("reeks_name")
                break
        label_parts = [p for p in [date, reeks, encounter] if p]
        label = " \u2014 ".join(label_parts) if label_parts else "Onbekende ontmoeting"
        items.append((key, label, date))
    items.sort(key=lambda x: to_iso_date(x[2]) or "", reverse=True)
    return [(k, lbl) for k, lbl, _ in items]


def reconstruct_boards_with_rankings(entries: list) -> List[dict]:
    """Zoals ll.reconstruct_boards(), maar behoudt ook opp1_ranking/
    opp2_ranking (tekst, bv. "P200") en match_date."""
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
            "match_date": m.get("match_date"),
            "round_text": m.get("round_text"),
            "opp1_name": m.get("opp1_name"), "opp2_name": m.get("opp2_name"),
            "opp1_user_id": m.get("opp1_user_id"), "opp2_user_id": m.get("opp2_user_id"),
            "opp1_ranking": m.get("opp1_ranking"), "opp2_ranking": m.get("opp2_ranking"),
            "score": m.get("score"), "result": m.get("result"), "won": m.get("won"),
            "match_id": m.get("match_id"), "dedupe_key": key,
        }
    return list(seen.values())


# --------------------------------------------------------------- teamgenoten
def _detect_teammates(docs: Dict[str, dict], sel_player_id: str) -> set:
    teammates = set()
    doc = docs.get(str(sel_player_id)) or {}
    for m in doc.get("matches", []) or []:
        if m.get("match_type") != "interclub":
            continue
        if m.get("partner_user_id"):
            teammates.add(str(m["partner_user_id"]))
    return teammates


# --------------------------------------------------------------- momentopnames
@st.cache_data(ttl=300, show_spinner=False)
def _load_all_snapshots() -> list:
    try:
        docs = fb.db.collection(SNAPSHOT_COLLECTION).limit(500).stream()
        return [doc.to_dict() or {} for doc in docs]
    except Exception:  # noqa: BLE001
        return []


def _find_snapshot_for(date_text, opp_user_ids: set) -> Optional[dict]:
    iso = to_iso_date(date_text)
    if not iso:
        return None
    for data in _load_all_snapshots():
        if to_iso_date(data.get("match_date")) != iso:
            continue
        opp_players = data.get("opponent_players") or {}
        if opp_user_ids and not (set(opp_players.keys()) & {str(u) for u in opp_user_ids if u}):
            continue
        return data
    return None


# --------------------------------------------------------------- padelstat-cache
def _collect_relevant_player_ids(index: dict) -> set:
    ids = set()
    for entries in index.values():
        for pid, m in entries:
            ids.add(str(pid))
            for veld in ("partner_user_id", "opp1_user_id", "opp2_user_id"):
                if m.get(veld):
                    ids.add(str(m[veld]))
    return ids


def _parallel_prefetch_padelstat(player_ids: tuple) -> None:
    if not player_ids:
        return
    prefetch = getattr(fb, "_fs_prefetch", None)
    if callable(prefetch):
        try:
            prefetch(("get_padelstat_rating",), list(player_ids))
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        from concurrent.futures import ThreadPoolExecutor

        def _warm(pid):
            try:
                fb.get_padelstat_rating(pid)
            except Exception:  # noqa: BLE001
                pass

        with ThreadPoolExecutor(max_workers=min(16, len(player_ids))) as ex:
            list(ex.map(_warm, player_ids))
    except Exception:  # noqa: BLE001
        pass


@st.cache_data(ttl=300, show_spinner=False)
def _load_padelstat_histories(player_ids: tuple) -> Dict[str, dict]:
    _parallel_prefetch_padelstat(player_ids)
    out: Dict[str, dict] = {}
    for pid in player_ids:
        try:
            data = fb.get_padelstat_rating(pid) or {}
        except Exception:  # noqa: BLE001
            data = {}
        out[pid] = {
            "history": list(data.get("history") or []),
            "flat_rating": data.get("rating"),
            "flat_fetched_at": data.get("fetched_at"),
        }
    return out


def _rating_at_from_history(history: list, moment_iso: str) -> Optional[float]:
    beste = None
    for regel in history:
        t = str(regel.get("fetched_at") or "")
        if t and t[:len(moment_iso)] <= moment_iso and (beste is None or t >= beste[0]):
            beste = (t, regel.get("rating"))
    return beste[1] if beste else None


def _latest_rating_from_history(history: list) -> Optional[float]:
    if not history:
        return None
    beste = max(history, key=lambda r: str(r.get("fetched_at") or ""))
    rating = beste.get("rating")
    return float(rating) if rating is not None else None


def _padelstat_priority_rating(
    pid, date_text, ratings_cache: Dict[str, dict], fallback_value, fallback_label: str,
):
    """GEDEELDE prioriteitsketen voor ZOWEL eigen spelers ALS tegenstanders:
      1. padelstat-historiek OP DATUM (exact);
      2. meest recente padelstat-HISTORIEK-waarde (any datum - "huidig");
      3. het vlakke, niet-gehistoriseerde "rating"-veld;
      4. `fallback_value`/`fallback_label`.
    Geeft (waarde, bron) terug; waarde is None als ECHT niets gekend is."""
    cache_entry = ratings_cache.get(str(pid)) or {}
    history = cache_entry.get("history") or []
    iso = to_iso_date(date_text)
    if iso:
        hist = _rating_at_from_history(history, iso)
        if hist is not None:
            return float(hist), "padelstat-historiek (op datum)"
    latest = _latest_rating_from_history(history)
    if latest is not None:
        return latest, "meest recente padelstat-historiek (geen regel exact op die datum - benadering)"
    flat = cache_entry.get("flat_rating")
    if flat is not None:
        return float(flat), "padelstat (nog geen historiek bijgehouden voor deze speler - huidige waarde)"
    if fallback_value is not None:
        return float(fallback_value), fallback_label
    return None, "onbekend"


# --------------------------------------------------------------- voorspelling
def _own_value_at(player_id, date_text, current_official_ranks: dict, snapshot_own: dict,
                  ratings_cache: Dict[str, dict]):
    pid = str(player_id)
    if snapshot_own and pid in snapshot_own:
        v = snapshot_own[pid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    fallback = (current_official_ranks or {}).get(pid)
    return _padelstat_priority_rating(
        pid, date_text, ratings_cache, fallback,
        "huidig officieel klassement (laatste redmiddel, geen padelstat gekend)",
    )


def _opponent_value_at(user_id, ranking_text, date_text, snapshot_opp: dict,
                       ratings_cache: Dict[str, dict]):
    uid = str(user_id) if user_id else None
    if snapshot_opp and uid and uid in snapshot_opp:
        v = snapshot_opp[uid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    if not uid:
        official = ll.parse_ranking(ranking_text)
        return (float(official), "officieel klassement (van toen, uit het uitslagenblad)") if official is not None else (None, "onbekend")
    official = ll.parse_ranking(ranking_text)
    return _padelstat_priority_rating(
        uid, date_text, ratings_cache, official,
        "officieel klassement (van toen, uit het uitslagenblad - laatste redmiddel, geen padelstat gekend)",
    )


def predict_board(
    board: dict, current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, snapshot: Optional[dict] = None,
) -> dict:
    date_text = board.get("match_date")
    p1, p2 = tuple(board["pair"])
    snap_own = (snapshot or {}).get("own_players") or {}
    snap_opp = (snapshot or {}).get("opponent_players") or {}
    our_vals = [_own_value_at(p, date_text, current_official_ranks, snap_own, ratings_cache) for p in (p1, p2)]
    their_vals = [
        _opponent_value_at(board.get("opp1_user_id"), board.get("opp1_ranking"), date_text, snap_opp, ratings_cache),
        _opponent_value_at(board.get("opp2_user_id"), board.get("opp2_ranking"), date_text, snap_opp, ratings_cache),
    ]
    our_known = [v for v, _ in our_vals if v is not None]
    their_known = [v for v, _ in their_vals if v is not None]
    our_avg = sum(our_known) / len(our_known) if our_known else None
    their_avg = sum(their_known) / len(their_known) if their_known else None
    wp = ll.estimate_win_probability(our_avg, their_avg, scale=scale)
    return {
        "pair": (p1, p2), "our_avg": our_avg, "their_avg": their_avg,
        "win_probability": wp, "risk_note": ll.risk_note_for_probability(wp),
        "our_sources": [s for _, s in our_vals], "their_sources": [s for _, s in their_vals],
        "actual_won": board.get("won"), "score": board.get("score"),
        "opp1_name": board.get("opp1_name"), "opp2_name": board.get("opp2_name"),
        "match_date": date_text,
    }


def predict_encounter(
    boards: list, current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, use_snapshot: bool = True,
) -> dict:
    snapshot = None
    if use_snapshot and boards:
        opp_ids = {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards}
        snapshot = _find_snapshot_for(boards[0].get("match_date"), opp_ids)
    predictions = [predict_board(b, current_official_ranks, ratings_cache, scale=scale, snapshot=snapshot) for b in boards]
    return {"boards": predictions, "snapshot_used": snapshot is not None}


# ------------------------------------------- volledige-ontmoeting-uitkomst
def _combine_boards_to_point_probs(win_probs: list) -> dict:
    probs = [(0.5 if p is None else max(0.0, min(1.0, float(p)))) for p in win_probs]
    n = len(probs)
    if n == 0:
        return {"p2": 0.0, "p1": 0.0, "p0": 0.0}
    tot = {0: 1.0}
    for p in probs:
        nieuw = {}
        for k, pk in tot.items():
            nieuw[k] = nieuw.get(k, 0.0) + pk * (1.0 - p)
            nieuw[k + 1] = nieuw.get(k + 1, 0.0) + pk * p
        tot = nieuw
    half = n / 2.0
    p2 = sum(p for k, p in tot.items() if k > half)
    p1 = sum(p for k, p in tot.items() if k == half)
    p0 = max(0.0, 1.0 - p2 - p1)
    return {"p2": p2, "p1": p1, "p0": p0}


def _actual_encounter_result(boards: list) -> Optional[dict]:
    if not boards:
        return None
    gewonnen = [b.get("won") for b in boards]
    if any(w is None for w in gewonnen):
        return None
    n_win = sum(1 for w in gewonnen if w)
    half = len(boards) / 2.0
    if n_win > half:
        uitkomst = "gewonnen"
    elif n_win == half:
        uitkomst = "gelijk"
    else:
        uitkomst = "verloren"
    return {"n_win": n_win, "n_boards": len(boards), "uitkomst": uitkomst}


# ------------------------------------------------ schaal-onafhankelijke ruwe data
def gather_raw_match_data(index: dict, current_official_ranks: dict, ratings_cache: Dict[str, dict]) -> list:
    """Verzamelt voor ELK bord van ELKE ontmoeting in `index` de SCHAAL-
    ONAFHANKELIJKE ruwe data (our_avg/their_avg/actual_won)."""
    raw = []
    for entries in index.values():
        boards = reconstruct_boards_with_rankings(entries)
        if not boards:
            continue
        opp_ids = {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards}
        snapshot = _find_snapshot_for(boards[0].get("match_date"), opp_ids)
        snap_own = (snapshot or {}).get("own_players") or {}
        snap_opp = (snapshot or {}).get("opponent_players") or {}
        for board in boards:
            p1, p2 = tuple(board["pair"])
            date_text = board.get("match_date")
            our_vals = [_own_value_at(p, date_text, current_official_ranks, snap_own, ratings_cache) for p in (p1, p2)]
            their_vals = [
                _opponent_value_at(board.get("opp1_user_id"), board.get("opp1_ranking"), date_text, snap_opp, ratings_cache),
                _opponent_value_at(board.get("opp2_user_id"), board.get("opp2_ranking"), date_text, snap_opp, ratings_cache),
            ]
            our_known = [v for v, _ in our_vals if v is not None]
            their_known = [v for v, _ in their_vals if v is not None]
            raw.append({
                "pair": (p1, p2),
                "our_avg": (sum(our_known) / len(our_known)) if our_known else None,
                "their_avg": (sum(their_known) / len(their_known)) if their_known else None,
                "actual_won": board.get("won"), "score": board.get("score"),
                "opp1_name": board.get("opp1_name"), "opp2_name": board.get("opp2_name"),
                "match_date": date_text,
            })
    return raw


# PADEL_ANALYSIS_RETRO_ALL_VALID_DATA_2026-10-04 - zie moduledocstring.
def gather_all_valid_match_data(profiles: list) -> dict:
    """Bouwt de SCHAAL-ONAFHANKELIJKE ruwe matchdata over ALLE profielen in
    de database (geen speler-/teamgenoten-keuze nodig). Geeft
    {"valid_rows", "n_total_boards", "n_valid", "player_ids"} terug:
      - "valid_rows": enkel rijen waar our_avg EN their_avg EN actual_won
        gekend zijn ("geldige matchdata", Kim's exacte vraag);
      - "n_total_boards": totaal aantal GEZIENE borden (incl. onvolledige -
        zodat zichtbaar is hoeveel data er potentieel bestaat);
      - "n_valid": len(valid_rows), kortheidshalve apart.
    Faalt een stap (bv. geen Firestore-verbinding), dan geeft deze functie
    lege resultaten terug i.p.v. te crashen - de aanroeper toont dan "0
    matchen gevonden" i.p.v. een foutpagina."""
    all_ids = sorted({str(p.get("player_id")) for p in profiles if p.get("player_id")})
    if not all_ids:
        return {"valid_rows": [], "n_total_boards": 0, "n_valid": 0, "player_ids": []}
    try:
        docs = ll.get_docs_for_players(all_ids)
    except Exception:  # noqa: BLE001
        docs = {}
    # Geen allowed_player_ids-filter: ELK profiel se matchen tellen mee.
    index = build_retro_encounter_index(docs, allowed_player_ids=None)
    current_official_ranks = {}
    try:
        from lineup_scout import _build_own_official_ranks_strict, prefetch_own_player_reads
        prefetch_own_player_reads(all_ids)
        current_official_ranks = _build_own_official_ranks_strict(all_ids) or {}
    except Exception:  # noqa: BLE001
        pass
    relevant_ids = tuple(sorted(_collect_relevant_player_ids(index)))
    ratings_cache = _load_padelstat_histories(relevant_ids)
    raw = gather_raw_match_data(index, current_official_ranks, ratings_cache)
    valid_rows = [r for r in raw if r.get("our_avg") is not None and r.get("their_avg") is not None and r.get("actual_won") is not None]
    return {
        "valid_rows": valid_rows, "n_total_boards": len(raw), "n_valid": len(valid_rows),
        "player_ids": all_ids,
    }


def score_raw_at_scale(raw_rows: list, scale: float, bias: float = 0.0) -> list:
    """Vult elke rij uit gather_raw_match_data() aan met win_probability
    voor EEN specifieke winkansfactor (en optioneel een bias-term, zie
    PADEL_ANALYSIS_RETRO_BIAS_MODEL_2026-10-04) - pure berekening, geen I/O."""
    out = []
    for r in raw_rows:
        if bias:
            wp = _estimate_win_probability_with_bias(r["our_avg"], r["their_avg"], scale=scale, bias=bias)
        else:
            wp = ll.estimate_win_probability(r["our_avg"], r["their_avg"], scale=scale)
        out.append({**r, "win_probability": wp})
    return out


# --------------------------------------------------------------- kalibratie
def calibration_stats(predictions: list, bin_edges=None) -> Optional[dict]:
    bin_edges = bin_edges or _CALIBRATION_BIN_EDGES
    usable = [p for p in predictions if p.get("win_probability") is not None and p.get("actual_won") is not None]
    n = len(usable)
    if n == 0:
        return None
    brier = sum((p["win_probability"] - (1.0 if p["actual_won"] else 0.0)) ** 2 for p in usable) / n
    eps = 1e-9
    log_loss = -sum(
        (1.0 if p["actual_won"] else 0.0) * math.log(max(p["win_probability"], eps))
        + (0.0 if p["actual_won"] else 1.0) * math.log(max(1.0 - p["win_probability"], eps))
        for p in usable
    ) / n
    accuracy = sum(1 for p in usable if (p["win_probability"] >= 0.5) == bool(p["actual_won"])) / n
    mean_pred = sum(p["win_probability"] for p in usable) / n
    mean_actual = sum(1.0 if p["actual_won"] else 0.0 for p in usable) / n
    bins = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        grp = [p for p in usable if lo <= p["win_probability"] < hi or (hi == 1.0 and p["win_probability"] == 1.0)]
        if grp:
            bins.append({
                "bereik": f"{lo * 100:.0f}-{hi * 100:.0f}%", "n": len(grp),
                "gem_voorspeld": sum(x["win_probability"] for x in grp) / len(grp) * 100,
                "werkelijk": sum(1 for x in grp if x["actual_won"]) / len(grp) * 100,
            })
    return {
        "n": n, "brier": brier, "log_loss": log_loss, "accuracy": accuracy,
        "mean_predicted": mean_pred, "mean_actual": mean_actual, "bins": bins,
    }


def find_best_scale(raw_rows: list, scale_range=None) -> dict:
    scale_range = scale_range or _SCALE_SEARCH_RANGE
    curve = []
    best = None
    for s in scale_range:
        stats = calibration_stats(score_raw_at_scale(raw_rows, s))
        if stats is None:
            continue
        curve.append({"scale": s, "brier": stats["brier"], "n": stats["n"]})
        if best is None or stats["brier"] < best["brier"]:
            best = {"scale": s, "brier": stats["brier"]}
    if best is not None:
        best["at_upper_edge"] = (best["scale"] == max(scale_range))
    return {"best": best, "curve": curve}


# PADEL_ANALYSIS_RETRO_BIAS_MODEL_2026-10-04 - zie moduledocstring.
def _estimate_win_probability_with_bias(our_avg, their_avg, scale: float, bias: float = 0.0):
    """PURE, lokale uitbreiding van ll.estimate_win_probability() met een
    extra bias/verschuiving-term op het ratingverschil - zie
    moduledocstring. Raakt NIET aan lineup_lab.py of de rest van de app."""
    if our_avg is None or their_avg is None:
        return None
    diff = (our_avg - their_avg) + bias
    try:
        return 1.0 / (1.0 + math.pow(10.0, -diff / scale))
    except OverflowError:
        return 0.0 if diff < 0 else 1.0


def find_best_scale_and_bias(raw_rows: list, scales=None, biases=None) -> dict:
    """PADEL_ANALYSIS_RETRO_BIAS_MODEL_2026-10-04 - zie moduledocstring.
    Doorzoekt een 2D-rooster (scale x bias) en geeft de combinatie met de
    laagste Brier-score terug, samen met de volledige curve (voor eventuele
    latere visualisatie) - puur rekenwerk, geen I/O."""
    scales = scales or _SCALE_BIAS_SEARCH_SCALES
    biases = biases or _BIAS_SEARCH_RANGE
    best = None
    curve = []
    for s in scales:
        for b in biases:
            scored = score_raw_at_scale(raw_rows, s, bias=b)
            stats = calibration_stats(scored)
            if stats is None:
                continue
            curve.append({"scale": s, "bias": b, "brier": stats["brier"], "n": stats["n"]})
            if best is None or stats["brier"] < best["brier"]:
                best = {"scale": s, "bias": b, "brier": stats["brier"]}
    return {"best": best, "curve": curve}


def logistic_curve(scale: float, diffs=None) -> list:
    diffs = diffs if diffs is not None else list(range(-400, 401, 10))
    return [(d, ll.estimate_win_probability(0.0, -float(d), scale=scale)) for d in diffs]


# --------------------------------------------------------------- winkansfactor opslaan
def _load_saved_scale() -> dict:
    """Leest de laatst opgeslagen winkansfactor EN bias uit Firestore.
    PADEL_ANALYSIS_RETRO_BIAS_MODEL_2026-10-04: geeft nu een dict terug
    i.p.v. enkel een float, met een nieuw "bias"-veld (0.0 als er nog
    nooit een bias werd opgeslagen). Faalt stil."""
    try:
        doc = fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_CALIBRATION_SETTINGS_DOC).get()
        data = doc.to_dict() if doc is not None and getattr(doc, "exists", True) else None
        if data and data.get("win_probability_scale") is not None:
            return {
                "scale": float(data["win_probability_scale"]),
                "bias": float(data.get("win_probability_bias") or 0.0),
            }
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_scale_to_firestore(scale: float, bias: float = 0.0) -> None:
    try:
        fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_CALIBRATION_SETTINGS_DOC).set(
            {
                "win_probability_scale": float(scale),
                "win_probability_bias": float(bias),
                "saved_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            },
            merge=True,
        )
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------- beste alternatief
def best_alternative_for_encounter(
    boards: list, docs: Dict[str, dict], current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, top_n: int = 3,
) -> Optional[dict]:
    if not boards:
        return {"top": [], "actual": None, "reason": "too_few_players", "n_players": 0}
    players = sorted({str(p) for b in boards for p in b["pair"]})
    if len(players) < 4:
        return {"top": [], "actual": None, "reason": "too_few_players", "n_players": len(players)}
    required = ll.required_counts_from_boards(boards)
    exclude_keys = {b["dedupe_key"] for b in boards}
    synergy = ll.compute_pairwise_synergy(docs, players, exclude_match_keys=exclude_keys)
    synergy_fn = ll.make_pair_score_fn(synergy, docs)
    date_text = boards[0].get("match_date")
    snapshot = _find_snapshot_for(date_text, {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards})
    snap_own = (snapshot or {}).get("own_players") or {}
    snap_opp = (snapshot or {}).get("opponent_players") or {}
    player_ratings = {}
    for pid in players:
        val, _ = _own_value_at(pid, date_text, current_official_ranks, snap_own, ratings_cache)
        if val is not None:
            player_ratings[pid] = val
    opponent_boards = []
    opponent_ratings = {}
    for b in boards:
        pair_info = []
        for idx, uid_key, ranking_key in ((0, "opp1_user_id", "opp1_ranking"), (1, "opp2_user_id", "opp2_ranking")):
            uid = b.get(uid_key)
            val, _ = _opponent_value_at(uid, b.get(ranking_key), date_text, snap_opp, ratings_cache)
            if uid and val is not None:
                opponent_ratings[str(uid)] = val
            pair_info.append({
                "user_id": uid, "name": b.get("opp1_name") if idx == 0 else b.get("opp2_name"),
                "ranking": b.get(ranking_key),
            })
        opponent_boards.append({"opponent_pair": pair_info})
    results, _truncated, _diag = ll.optimize_lineup_vs_scenario(
        players, required, synergy_fn, opponent_boards, player_ratings,
        player_official_ranks=current_official_ranks, opponent_ratings=opponent_ratings,
        top_n=top_n, win_probability_scale=scale,
    )
    if not results:
        return {"top": [], "actual": None, "reason": "no_valid_combinations", "n_players": len(players)}
    actual_key = tuple(sorted(tuple(sorted(b["pair"])) for b in boards))
    actual_result = next(
        (r for r in results if tuple(sorted(tuple(sorted(a["our_pair"])) for a in r["assignment"])) == actual_key),
        None,
    )
    return {"top": results, "actual": actual_result, "reason": None, "n_players": len(players)}


# --------------------------------------------------------------------------
# Streamlit-weergave
# --------------------------------------------------------------------------
def _pct(v) -> str:
    return f"{v * 100:.0f}%" if v is not None else "onbekend"


def _outcome_color(predicted_wp, actual_won) -> str:
    if predicted_wp is None or actual_won is None:
        return "gray"
    correct = (predicted_wp >= 0.5) == bool(actual_won)
    return "green" if correct else "red"


def _render_board_row(bp: dict, name_lookup: dict) -> None:
    p1, p2 = bp["pair"]
    ons = f"{name_lookup.get(p1, p1)} / {name_lookup.get(p2, p2)}"
    hen = f"{bp.get('opp1_name', '?')} / {bp.get('opp2_name', '?')}"
    kleur = _outcome_color(bp["win_probability"], bp["actual_won"])
    uitslag = "gewonnen" if bp["actual_won"] is True else ("verloren" if bp["actual_won"] is False else "onbekend")
    st.markdown(
        f"**{ons}** tegen **{hen}** ({bp.get('score') or '?'}) - "
        f"voorspeld :{kleur}[**{_pct(bp['win_probability'])}**] ({bp['risk_note']}), "
        f"echt **{uitslag}**"
    )
    with st.expander("Op basis van welke waarden?", expanded=False):
        st.caption(
            (f"Onze spelers: {bp['our_sources'][0]}, {bp['our_sources'][1]} "
             f"(gemiddeld {bp['our_avg']:.0f})") if bp.get("our_avg") is not None else "Onze spelers: onbekend"
        )
        st.caption(
            (f"Tegenstander: {bp['their_sources'][0]}, {bp['their_sources'][1]} "
             f"(gemiddeld {bp['their_avg']:.0f})") if bp.get("their_avg") is not None else "Tegenstander: onbekend"
        )


def _apply_scale_callback(new_scale: float, new_bias: float = 0.0) -> None:
    st.session_state["retro_scale"] = new_scale
    st.session_state["retro_bias"] = new_bias
    st.session_state.pop("retro_best_scale_result", None)
    st.session_state.pop("retro_best_scale_bias_result", None)
    _save_scale_to_firestore(new_scale, new_bias)


def _persist_scale_callback() -> None:
    _save_scale_to_firestore(
        st.session_state.get("retro_scale", _DEFAULT_SCALE),
        st.session_state.get("retro_bias", 0.0),
    )


def render_retrospective_tab(profiles: list, sel_player_id) -> None:
    st.markdown('<div class="section-header">Nabeschouwing</div>', unsafe_allow_html=True)
    sel_player_id = str(sel_player_id)
    name_lookup = {str(p.get("player_id")): (p.get("display_name") or str(p.get("player_id"))) for p in profiles}
    sel_naam = name_lookup.get(sel_player_id, sel_player_id)

    if "retro_scale" not in st.session_state:
        with perf.step("retro: opgeslagen winkansfactor lezen"):
            saved = _load_saved_scale()
        if saved.get("scale") is not None:
            st.session_state["retro_scale"] = saved["scale"]
            st.session_state["retro_bias"] = saved.get("bias", 0.0)

    with perf.step("retro: eigen matchen ophalen (teamgenoten detecteren)"):
        with st.spinner(f"Matchen van {sel_naam} ophalen..."):
            sel_docs = ll.get_docs_for_players([sel_player_id])
    teammates = _detect_teammates(sel_docs, sel_player_id)
    teammate_options = [p for p in profiles if str(p.get("player_id")) in teammates]
    other_options = [p for p in profiles if str(p.get("player_id")) not in teammates
                     and str(p.get("player_id")) != sel_player_id]
    option_labels = [sel_naam] + [name_lookup.get(str(p.get("player_id")), "?") for p in teammate_options + other_options]
    label_to_id = {sel_naam: sel_player_id}
    label_to_id.update({name_lookup.get(str(p.get("player_id")), "?"): str(p.get("player_id")) for p in teammate_options})
    label_to_id.update({name_lookup.get(str(p.get("player_id")), "?"): str(p.get("player_id")) for p in other_options})
    default_labels = [sel_naam] + [name_lookup.get(str(p.get("player_id")), "?") for p in teammate_options]

    st.caption(
        f"Vergelijkt de voorspelde winkans met de echte uitslag van eerder gespeelde interclub-matchen, MET "
        "de padelstat-/klassementwaarden van TOEN (niet de huidige) waar bekend. Gebruik dit om te "
        "controleren of de winkans-formule klopt, en wat het betere alternatief geweest zou zijn."
    )
    gekozen_labels = st.multiselect(
        "Analyseer ook de matchen van (voor de ontmoeting hieronder en 'Beste alternatief' - "
        "de kalibratie verderop gebruikt ALTIJD alle gekende matchen van iedereen)",
        option_labels, default=default_labels, key=f"retro_teammates_{sel_player_id}",
        help=f"{sel_naam} staat er altijd bij. Standaard vooraf ingevuld met de teamgenoten waarmee "
             f"{sel_naam} al samenspeelde.",
    )
    gekozen_ids = {label_to_id[lbl] for lbl in gekozen_labels if lbl in label_to_id} | {sel_player_id}
    if gekozen_ids == {sel_player_id}:
        docs = sel_docs
    else:
        with perf.step("retro: matchen van gekozen spelers ophalen"):
            with st.spinner("Matchen van de gekozen spelers ophalen..."):
                docs = ll.get_docs_for_players(sorted(gekozen_ids))

    with perf.step("retro: encounter-index bouwen"):
        index = build_retro_encounter_index(docs, allowed_player_ids=gekozen_ids)
    encounters = list_retro_encounters(index)
    if not encounters:
        st.info(f"Nog geen gespeelde interclub-ontmoetingen gevonden voor {sel_naam}.")
        return

    own_side_ids = set(gekozen_ids)
    for entries in index.values():
        for _pid, m in entries:
            if m.get("partner_user_id"):
                own_side_ids.add(str(m["partner_user_id"]))
    current_official_ranks = {}
    with perf.step(f"retro: officieel klassement terugval ophalen ({len(own_side_ids)} spelers)"):
        try:
            from lineup_scout import _build_own_official_ranks_strict, prefetch_own_player_reads
            with perf.step("retro: klassement - parallel voorophalen"):
                prefetch_own_player_reads(sorted(own_side_ids))
            current_official_ranks = _build_own_official_ranks_strict(sorted(own_side_ids)) or {}
        except Exception:  # noqa: BLE001
            pass

    player_ids = tuple(sorted(_collect_relevant_player_ids(index)))
    with perf.step(f"retro: padelstat-historiek laden ({len(player_ids)} spelers)"):
        ratings_cache = _load_padelstat_histories(player_ids)

    labels = [lbl for _k, lbl in encounters]
    key_by_label = {lbl: k for k, lbl in encounters}
    gekozen_label = st.selectbox(
        "Kies een eerder gespeelde ontmoeting", labels, key="retro_pick_encounter",
    )
    gekozen_key = key_by_label[gekozen_label]
    boards = reconstruct_boards_with_rankings(index[gekozen_key])
    scale = st.session_state.get("retro_scale", _DEFAULT_SCALE)
    bias = st.session_state.get("retro_bias", 0.0)
    with perf.step("retro: ontmoeting voorspellen (predict_encounter)"):
        pred = predict_encounter(boards, current_official_ranks, ratings_cache, scale=scale)
    if pred["snapshot_used"]:
        st.success("Een eerdere momentopname van deze ontmoeting werd gevonden - de waarden van toen zijn exact.")
    st.markdown("#### Per match: voorspeld tegenover echt")
    for bp in pred["boards"]:
        _render_board_row(bp, name_lookup)

    st.divider()
    st.markdown("#### Eindresultaat van de ontmoeting: voorspeld tegenover echt")
    n_known_boards = len(boards)
    if n_known_boards < 2 or n_known_boards % 2 != 0:
        st.caption(
            f"We kennen {n_known_boards} van de borden van deze ontmoeting - te weinig (of een oneven "
            "aantal, wat altijd op een ontbrekend bord wijst) voor een betrouwbaar eindresultaat. Voeg "
            "hierboven bij 'Analyseer ook de matchen van' meer teamgenoten van die dag toe."
        )
    else:
        encounter_pp = _combine_boards_to_point_probs([bp["win_probability"] for bp in pred["boards"]])
        st.caption(
            f"Gebaseerd op {n_known_boards} gekende borden van deze ontmoeting - mogelijk een deel als "
            "niet alle teamgenoten van die dag hierboven geselecteerd zijn."
        )
        st.markdown(
            f"Voorspeld (op basis van {n_known_boards} gekende borden): "
            f":green[**{encounter_pp['p2'] * 100:.0f}% winst**] \u00b7 "
            f":orange[**{encounter_pp['p1'] * 100:.0f}% gelijk**] \u00b7 "
            f":red[**{encounter_pp['p0'] * 100:.0f}% verlies**]"
        )
        actual = _actual_encounter_result(boards)
        if actual is None:
            st.caption("De echte uitslag van 1 of meer van deze borden is niet gekend - geen vergelijking mogelijk.")
        else:
            st.markdown(
                f"Echt: **{actual['uitkomst']}** ({actual['n_win']} van {actual['n_boards']} borden gewonnen)."
            )

    st.divider()
    st.markdown("#### Beste alternatief (achteraf, met dezelfde waarden van toen)")
    with perf.step("retro: beste alternatief doorrekenen"):
        with st.spinner("Alternatieven doorrekenen..."):
            alt = best_alternative_for_encounter(boards, docs, current_official_ranks, ratings_cache, scale=scale)
    if alt.get("reason") == "too_few_players":
        st.caption(
            f"Onvoldoende eigen spelers gekend voor deze ontmoeting ({alt.get('n_players', 0)} van de nodige "
            "4) - voeg hierboven bij 'Analyseer ook de matchen van' meer teamgenoten van die dag toe."
        )
    elif alt.get("reason") == "no_valid_combinations":
        st.caption(
            f"{alt.get('n_players', 0)} eigen spelers gekend, maar geen enkele reglementair geldige "
            "alternatieve koppelverdeling gevonden voor deze combinatie (bv. door de puntengrens)."
        )
    elif not alt.get("top"):
        st.caption("Geen alternatieven gevonden voor deze ontmoeting.")
    else:
        actual_ebw = alt["actual"]["expected_boards_won"] if alt["actual"] else None
        for rank, r in enumerate(alt["top"], start=1):
            pairs_txt = " \u00b7 ".join(
                f"{name_lookup.get(a['our_pair'][0], a['our_pair'][0])} / {name_lookup.get(a['our_pair'][1], a['our_pair'][1])}"
                for a in r["assignment"]
            )
            is_actual = alt["actual"] is not None and r is alt["actual"]
            label = " (zoals echt gespeeld)" if is_actual else ""
            st.write(f"**#{rank} - verwacht {r['expected_boards_won']:.2f} gewonnen matchen**{label}: {pairs_txt}")
        if actual_ebw is not None and alt["top"] and alt["top"][0]["expected_boards_won"] - actual_ebw >= 0.1:
            st.caption(
                f"Het beste alternatief lag {alt['top'][0]['expected_boards_won'] - actual_ebw:.2f} hoger "
                "dan de effectief gespeelde opstelling (verwachte gewonnen matchen)."
            )
        elif alt["actual"] is not None:
            st.caption("De effectief gespeelde opstelling was (zo goed als) de beste mogelijke keuze.")

    # PADEL_ANALYSIS_RETRO_ALL_VALID_DATA_2026-10-04: kalibratie over ALLE
    # geldige matchdata in de database - niet langer afhankelijk van de
    # spelerskeuze hierboven. Zie moduledocstring.
    st.divider()
    st.markdown("#### Kalibratie over alle gekende matchen (van iedereen)")
    st.caption(
        "Deze sectie gebruikt ALLE interclub-matchen in de database waarvoor we ZOWEL een rating voor onze "
        "spelers ALS voor de tegenstander ALS de echte uitslag kennen - ongeacht wie je hierboven koos. Dat "
        "geeft het meest betrouwbare beeld van hoe goed de winkans-formule werkelijk voorspelt."
    )
    with perf.step("retro: alle geldige matchdata verzamelen (gather_all_valid_match_data)"):
        with st.spinner("Alle gekende matchen doorzoeken..."):
            all_data = gather_all_valid_match_data(profiles)
    raw_rows = all_data["valid_rows"]
    c_n1, c_n2 = st.columns(2)
    with c_n1:
        st.metric("Bruikbare matchen (rating + uitslag gekend)", all_data["n_valid"])
    with c_n2:
        st.metric("Totaal geziene borden", all_data["n_total_boards"])
    if all_data["n_total_boards"] > 0 and all_data["n_valid"] < all_data["n_total_boards"]:
        ontbrekend = all_data["n_total_boards"] - all_data["n_valid"]
        st.caption(
            f"{ontbrekend} bord(en) vielen af - meestal omdat er voor minstens 1 speler nog geen enkele "
            "padelstat- of officiële-klassementwaarde gekend is, of de uitslag onbekend is."
        )
    if not raw_rows:
        st.info("Nog geen enkele match met zowel een gekende rating voor beide kanten als een gekende uitslag.")
        return

    c_slider, c_curve = st.columns([2, 1])
    with c_slider:
        scale = st.slider(
            "Winkansfactor (hoe gevoelig de winkans reageert op het ratingverschil)",
            min_value=50, max_value=800, value=int(scale), step=5, key="retro_scale",
            on_change=_persist_scale_callback,
            help=f"Huidige app-standaard: {_DEFAULT_SCALE:.0f}. Dit wijzigt ENKEL deze weergave, niet de "
                 "rest van de app. De keuze wordt bewaard voor de volgende keer.",
        )
    with c_curve:
        st.caption(f"Bij 100 punten verschil: {_pct(ll.estimate_win_probability(0, -100, scale=scale))} winkans.")
    if bias:
        st.caption(f"Actieve bias-correctie: **{bias:+.0f}** (zie 'Model met bias' verderop).")
    with perf.step("retro: kalibratie herberekenen (score_raw_at_scale)"):
        scored = score_raw_at_scale(raw_rows, scale, bias=bias)
        stats = calibration_stats(scored)
    if not stats:
        st.info("Nog geen matchen met zowel een gekende winkans als een gekende uitslag.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Brier-score", f"{stats['brier']:.3f}", help="Lager = beter. 0.25 = niet beter dan een muntstuk.")
    with c2:
        st.metric("Accuraatheid", f"{stats['accuracy'] * 100:.0f}%", help="Hoe vaak de favoriet (>=50%) ook echt won.")
    with c3:
        st.metric("Aantal matchen", f"{stats['n']}")
    if stats["brier"] >= 0.245:
        st.warning(
            f"Een Brier-score van {stats['brier']:.3f} ligt zeer dicht bij 0.25 - amper beter dan een muntje "
            "opgooien. Probeer hieronder 'Beste model zoeken (met bias)' - een systematische afwijking "
            "(zoals in jouw padelstat.be-voorbeeld) kan een loutere factor-aanpassing niet oplossen."
        )
    st.caption(
        f"Gemiddeld voorspeld: {stats['mean_predicted'] * 100:.0f}% - gemiddeld werkelijk gewonnen: "
        f"{stats['mean_actual'] * 100:.0f}%."
    )
    if stats["bins"]:
        st.dataframe(
            [{"Kansklasse": b["bereik"], "Aantal": b["n"], "Gem. voorspeld": f"{b['gem_voorspeld']:.0f}%",
              "Werkelijk gewonnen": f"{b['werkelijk']:.0f}%"} for b in stats["bins"]],
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "Idealiter liggen 'Gem. voorspeld' en 'Werkelijk gewonnen' per rij dicht bij elkaar. Een "
            "systematisch verschil (bv. bij lage kansklassen te hoog, bij hoge te laag) wijst op een model "
            "dat scherper, voorzichtiger, of met een bias-term bijgesteld moet worden."
        )

    st.divider()
    st.markdown("##### Beste winkansfactor zoeken (1 parameter)")
    st.caption("Zoekt enkel de beste schaalfactor - de curve blijft gecentreerd rond 0 verschil = 50%.")
    if st.button("Zoek beste winkansfactor", key="retro_find_best_scale"):
        with perf.step("retro: beste winkansfactor zoeken (find_best_scale)"):
            with st.spinner("Factoren doorrekenen..."):
                st.session_state["retro_best_scale_result"] = find_best_scale(raw_rows)
    result = st.session_state.get("retro_best_scale_result")
    if result and result.get("best"):
        best = result["best"]
        if best["scale"] == int(scale) and not bias:
            st.success(f"De huidige factor ({scale:.0f}) is al de beste in het doorzochte bereik - Brier {best['brier']:.3f}.")
        else:
            st.info(f"Voorstel: factor **{best['scale']}**, bias 0 - Brier **{best['brier']:.3f}** (huidig: {stats['brier']:.3f}).")
            st.button(
                f"Toepassen: factor {best['scale']}, geen bias", key="retro_apply_best_scale",
                on_click=_apply_scale_callback, args=(best["scale"], 0.0),
            )
        if best.get("at_upper_edge"):
            st.warning(f"Dit is de bovengrens van het doorzochte bereik (tot {max(_SCALE_SEARCH_RANGE)}) - mogelijk ligt het echte optimum hoger.")

    st.divider()
    st.markdown("##### Beste model zoeken (2 parameters: schaal + bias)")
    st.caption(
        "Zoekt ZOWEL een schaalfactor ALS een vaste verschuiving (bias) van het ratingverschil. Een bias "
        "corrigeert een SYSTEMATISCHE afwijking (bv. als de formule structureel te optimistisch is voor "
        "underdogs) - iets wat een loutere factor niet kan. Experimenteel: wijzigt enkel deze weergave."
    )
    if st.button("Zoek beste model (schaal + bias)", key="retro_find_best_scale_bias"):
        with perf.step("retro: beste model zoeken (find_best_scale_and_bias)"):
            with st.spinner("Rooster van factor x bias doorrekenen (kan even duren)..."):
                st.session_state["retro_best_scale_bias_result"] = find_best_scale_and_bias(raw_rows)
    result2 = st.session_state.get("retro_best_scale_bias_result")
    if result2 and result2.get("best"):
        best2 = result2["best"]
        verbetering = stats["brier"] - best2["brier"]
        st.info(
            f"Voorstel: factor **{best2['scale']}**, bias **{best2['bias']:+.0f}** - Brier **{best2['brier']:.3f}** "
            f"(huidig: {stats['brier']:.3f}, verbetering: {verbetering:+.3f})."
        )
        if verbetering < 0.005:
            st.caption(
                "De verbetering is klein - een bias-term lijkt hier niet veel extra te helpen bovenop een "
                "goed gekozen factor."
            )
        st.button(
            f"Toepassen: factor {best2['scale']}, bias {best2['bias']:+.0f}", key="retro_apply_best_scale_bias",
            on_click=_apply_scale_callback, args=(best2["scale"], best2["bias"]),
        )
