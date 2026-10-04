"""
lineup_retrospective.py - Nabeschouwing: per eerder gespeelde ontmoeting de
voorspelde winkans tegenover de echte uitslag, MET de padelstat-/officiële
klassementwaarden van TOEN (niet de huidige), plus een kalibratieblok over
alle gespeelde matchen samen met een instelbare winkansfactor.
--------------------------------------------------------------------------
(Zie eerdere PADEL_ANALYSIS_RETRO_*-markers in de git-historiek voor de
volledige toelichting bij: brondata-prioriteit padelstat/klassement,
parallelle Firestore-batches, snapshot-cache, persistente winkansfactor,
eindresultaat-vergelijking, "beste alternatief", individuele-vorm-index,
automatische teamgenoten-resolutie, sterkte-gecorrigeerd vorm-model.)
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_CALIBRATION_SIMPLIFY_2026-10-05 (op verzoek van Kim,
na het testen van de vorige versie: "oei. dat is minder. ik wil wel de
snelheidsfix en geen vergelijkingssectie. enkel padelstat gebruiken")
--------------------------------------------------------------------------
De vorige levering toonde 3 tellingen ("Bruikbare matchen (totaal)" / "...
met padelstat voor alle 4" / "... met min. 1 klassement-terugval") plus een
2-koloms "Vergelijking: alle matchen tegenover enkel-padelstat-matchen"-
sectie en een AAN/UIT-schakelaar om te kiezen welke subset de kalibratie
gebruikt. Kim vond dit te veel ("dat is minder") en wil simpelweg: de
kalibratie gebruikt ALTIJD enkel de matchen met padelstat voor alle 4
spelers - geen keuze, geen vergelijking, geen tellingen-blok.
FIX: de 3-tellingen-metrics, de volledige vergelijkingssectie (c_cmp1/
c_cmp2 + de "klein verschil"/"scoort beter"/"scoort slechter"-captions) en
de "Gebruik hieronder enkel de volledige-padelstat-matchen"-checkbox zijn
VERWIJDERD. De kalibratie (schuifloos: zie PADEL_ANALYSIS_RETRO_NO_SLIDER_
2026-10-05 hieronder) werkt nu ONVOORWAARDELIJK op `full_padelstat_rows`
(gather_all_valid_match_data() berekent deze subset nog steeds intern,
enkel de UI errond is vereenvoudigd). Is die subset leeg (nog geen enkele
match met padelstat voor alle 4 spelers), dan toont de sectie een duidelijke
melding i.p.v. een lege of verwarrende tabel.
De automatische teamgenoten-resolutie (PADEL_ANALYSIS_RETRO_FULL_
ENCOUNTER_2026-10-05, "snelheid is opgelost" - Kim's eigen bevestiging)
blijft ONGEWIJZIGD - dat is de snelheidsfix die Kim expliciet wil behouden.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_FULL_ENCOUNTER_2026-10-05 (op verzoek van Kim: "ik zie
bij de nabeschouwing terug van mijn ontmoeting dat enkel mijn matchen
getoond worden en niet de matchen van mijn ploegmakkers waar ik niet aan
meegedaan heb. Ik wil dus wel alle 4 die matchen zien van de ontmoeting. Je
kan dan ook echt eindresultaat vergelijken met voorspeld eindresultaat")
--------------------------------------------------------------------------
_resolve_encounter_teammates(sel_player_id, date, encounter, profiles) zoekt,
ENKEL voor de GEKOZEN ontmoeting (niet voor alle ontmoetingen - dat zou de
performance-bottleneck van PADEL_ANALYSIS_RETRO_PERF_2026-10-04 terugbrengen),
AUTOMATISCH welke andere profielen een interclub-match hebben op DEZELFDE
(match_date, encounter)-sleutel, en voegt enkel HUN matchdocumenten toe aan
`docs` - geen handmatige keuzelijst meer nodig.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_NO_SLIDER_2026-10-05 (op verzoek van Kim: "die slider
met die winkansfactor mag weg. Bedoeling is dat je gewoon via de knop
werkt")
--------------------------------------------------------------------------
st.slider("Winkansfactor...") is VERWIJDERD. De huidige factor (en bias)
staat nu als vaste tekst; de ENIGE manier om deze te wijzigen is nog de
bestaande "Zoek beste model (schaal + bias + vorm)"-knop + "Toepassen".
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_FORM_MODEL_2026-10-05 (op verzoek van Kim: "Hou je
eigenlijk ook rekening bij die winpercentages van iedereen tegen wie ze
gewonnen hebben? [...] Ik vraag me af of die info het model niet nog beter
kan maken?")
--------------------------------------------------------------------------
compute_individual_form_index() toont, per speler, ZOWEL zijn ruwe winrate
ALS het gemiddelde ratingniveau van wie hij versloeg/van wie hij verloor
(diagnose). compute_form_adjustment() gaat verder: het gemiddelde VERSCHIL
tussen "verwachte kans volgens rating" en "werkelijk gewonnen" over al zijn
matchen - een speler die vooral van zwakkeren wint (zijn rating voorspelde
dat al) scoort hier dicht bij 0; een speler die STRUCTUREEL beter speelt
dan zijn rating scoort hier duidelijk positief. find_best_scale_and_bias()
doorzoekt een 3e, optionele parameter (form_weight) - form_weight=0 zit
altijd in de zoekruimte, dus dit kan nooit slechter zijn dan het 2-
parameter-model.
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
_SCALE_BIAS_SEARCH_SCALES = list(range(50, 801, 20))
_BIAS_SEARCH_RANGE = list(range(-150, 151, 10))
_FORM_WEIGHT_SEARCH_RANGE = [0.0, 0.25, 0.5, 0.75, 1.0]


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
    GEEN filter (alle spelers in `docs` tellen mee)."""
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


# PADEL_ANALYSIS_RETRO_FULL_ENCOUNTER_2026-10-05 - zie moduledocstring.
def _resolve_encounter_teammates(
    sel_player_id: str, encounter_key: tuple, profiles: list, max_candidates: int = 200,
) -> Dict[str, dict]:
    """Zoekt, UITSLUITEND voor de ENE ontmoeting `encounter_key` (match_date,
    encounter), welke andere profielen een interclub-matchrecord hebben op
    DIEZELFDE sleutel, en geeft hun VOLLEDIGE matchdocument terug."""
    other_ids = sorted({
        str(p.get("player_id")) for p in profiles
        if p.get("player_id") and str(p.get("player_id")) != str(sel_player_id)
    })[:max_candidates]
    if not other_ids:
        return {}
    try:
        all_docs = ll.get_docs_for_players(other_ids)
    except Exception:  # noqa: BLE001
        return {}
    gevonden = {}
    for pid, doc in all_docs.items():
        for m in doc.get("matches", []) or []:
            if m.get("match_type") == "interclub" and _encounter_key(m) == encounter_key:
                gevonden[pid] = doc
                break
    return gevonden


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
        "opp1_user_id": board.get("opp1_user_id"), "opp2_user_id": board.get("opp2_user_id"),
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
            our_is_padelstat = all(
                s is not None and "klassement" not in s and s != "onbekend" for _, s in our_vals
            ) if our_vals else False
            their_is_padelstat = all(
                s is not None and "klassement" not in s and s != "onbekend" for _, s in their_vals
            ) if their_vals else False
            raw.append({
                "pair": (p1, p2),
                "our_avg": (sum(our_known) / len(our_known)) if our_known else None,
                "their_avg": (sum(their_known) / len(their_known)) if their_known else None,
                "actual_won": board.get("won"), "score": board.get("score"),
                "opp1_name": board.get("opp1_name"), "opp2_name": board.get("opp2_name"),
                "opp1_user_id": board.get("opp1_user_id"), "opp2_user_id": board.get("opp2_user_id"),
                "match_date": date_text,
                "our_is_padelstat": our_is_padelstat, "their_is_padelstat": their_is_padelstat,
            })
    return raw


def compute_individual_form_index(raw_rows: list) -> Dict[str, dict]:
    """Geeft {player_id: {"wins", "losses", "n", "winrate",
    "avg_opp_rating_won", "avg_opp_rating_lost"}} terug, opgebouwd uit ALLE
    `raw_rows`. Een tegenstander-speler krijgt het SPIEGELBEELD van
    `actual_won`."""
    tally: Dict[str, dict] = defaultdict(lambda: {
        "wins": 0, "losses": 0, "opp_ratings_won": [], "opp_ratings_lost": [],
    })
    for r in raw_rows:
        won = r.get("actual_won")
        if won is None:
            continue
        their_avg = r.get("their_avg")
        our_avg = r.get("our_avg")
        for pid in r.get("pair") or ():
            if pid is None:
                continue
            entry = tally[str(pid)]
            entry["wins" if won else "losses"] += 1
            if their_avg is not None:
                entry["opp_ratings_won" if won else "opp_ratings_lost"].append(their_avg)
        for uid in (r.get("opp1_user_id"), r.get("opp2_user_id")):
            if uid is None:
                continue
            entry = tally[str(uid)]
            entry["wins" if not won else "losses"] += 1
            if our_avg is not None:
                entry["opp_ratings_won" if not won else "opp_ratings_lost"].append(our_avg)
    out: Dict[str, dict] = {}
    for pid, entry in tally.items():
        wins, losses = entry["wins"], entry["losses"]
        n = wins + losses
        won_list, lost_list = entry["opp_ratings_won"], entry["opp_ratings_lost"]
        out[pid] = {
            "wins": wins, "losses": losses, "n": n, "winrate": (wins / n) if n else None,
            "avg_opp_rating_won": (sum(won_list) / len(won_list)) if won_list else None,
            "avg_opp_rating_lost": (sum(lost_list) / len(lost_list)) if lost_list else None,
        }
    return out


def _format_individual_form(form_index: Dict[str, dict], player_id, name: str) -> Optional[str]:
    """Korte tekst voor 1 speler, inclusief het gemiddelde niveau van wie
    hij versloeg/van wie hij verloor."""
    entry = form_index.get(str(player_id)) if player_id else None
    if not entry or not entry.get("n"):
        return None
    basis = f"{name} ({entry['winrate'] * 100:.0f}% win, {entry['wins']}/{entry['n']})"
    context_delen = []
    if entry.get("avg_opp_rating_won") is not None:
        context_delen.append(f"won tegen gem. {entry['avg_opp_rating_won']:.0f}")
    if entry.get("avg_opp_rating_lost") is not None:
        context_delen.append(f"verloor tegen gem. {entry['avg_opp_rating_lost']:.0f}")
    if context_delen:
        basis += f" - {', '.join(context_delen)}"
    return basis


def compute_form_adjustment(raw_rows: list, scale: float, bias: float = 0.0) -> Dict[str, dict]:
    """Geeft per speler {"n", "avg_residual"} terug: het gemiddelde VERSCHIL
    tussen "werkelijk gewonnen (1/0)" en "verwachte kans volgens rating+
    schaal+bias" over al zijn gekende matchen."""
    tally: Dict[str, List[float]] = defaultdict(list)
    for r in raw_rows:
        won = r.get("actual_won")
        our_avg, their_avg = r.get("our_avg"), r.get("their_avg")
        if won is None or our_avg is None or their_avg is None:
            continue
        wp = _estimate_win_probability_with_bias(our_avg, their_avg, scale=scale, bias=bias)
        if wp is None:
            continue
        residual = (1.0 if won else 0.0) - wp
        for pid in r.get("pair") or ():
            if pid is not None:
                tally[str(pid)].append(residual)
        for uid in (r.get("opp1_user_id"), r.get("opp2_user_id")):
            if uid is not None:
                tally[str(uid)].append(-residual)
    return {pid: {"n": len(vals), "avg_residual": sum(vals) / len(vals)} for pid, vals in tally.items() if vals}


# PADEL_ANALYSIS_RETRO_ALL_VALID_DATA_2026-10-04 - zie moduledocstring.
def gather_all_valid_match_data(profiles: list) -> dict:
    """Bouwt de SCHAAL-ONAFHANKELIJKE ruwe matchdata over ALLE profielen in
    de database. `full_padelstat_rows` is de subset waarvoor de kalibratie
    hieronder ONVOORWAARDELIJK gebruikt wordt - zie PADEL_ANALYSIS_RETRO_
    CALIBRATION_SIMPLIFY_2026-10-05."""
    all_ids = sorted({str(p.get("player_id")) for p in profiles if p.get("player_id")})
    if not all_ids:
        return {
            "valid_rows": [], "full_padelstat_rows": [], "n_total_boards": 0, "n_valid": 0,
            "n_full_padelstat": 0, "n_fallback": 0, "form_index": {}, "player_ids": [],
        }
    try:
        docs = ll.get_docs_for_players(all_ids)
    except Exception:  # noqa: BLE001
        docs = {}
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
    n_full_padelstat = sum(1 for r in valid_rows if r.get("our_is_padelstat") and r.get("their_is_padelstat"))
    n_fallback = len(valid_rows) - n_full_padelstat
    full_padelstat_rows = [r for r in valid_rows if r.get("our_is_padelstat") and r.get("their_is_padelstat")]
    form_index = compute_individual_form_index(valid_rows)
    return {
        "valid_rows": valid_rows, "full_padelstat_rows": full_padelstat_rows,
        "n_total_boards": len(raw), "n_valid": len(valid_rows),
        "n_full_padelstat": n_full_padelstat, "n_fallback": n_fallback,
        "form_index": form_index, "player_ids": all_ids,
    }


def score_raw_at_scale(raw_rows: list, scale: float, bias: float = 0.0, form_weight: float = 0.0,
                       form_adjustment: Optional[Dict[str, dict]] = None) -> list:
    """Vult elke rij uit gather_raw_match_data() aan met win_probability."""
    out = []
    for r in raw_rows:
        our_avg, their_avg = r["our_avg"], r["their_avg"]
        effective_bias = bias
        if form_weight and form_adjustment and our_avg is not None and their_avg is not None:
            our_pair = r.get("pair") or ()
            their_pair = (r.get("opp1_user_id"), r.get("opp2_user_id"))
            our_res = [form_adjustment[str(p)]["avg_residual"] for p in our_pair if str(p) in form_adjustment]
            their_res = [form_adjustment[str(p)]["avg_residual"] for p in their_pair if p and str(p) in form_adjustment]
            if our_res or their_res:
                our_m = sum(our_res) / len(our_res) if our_res else 0.0
                their_m = sum(their_res) / len(their_res) if their_res else 0.0
                effective_bias = bias + (our_m - their_m) * scale * form_weight
        if effective_bias or form_weight:
            wp = _estimate_win_probability_with_bias(our_avg, their_avg, scale=scale, bias=effective_bias)
        else:
            wp = ll.estimate_win_probability(our_avg, their_avg, scale=scale)
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


def _estimate_win_probability_with_bias(our_avg, their_avg, scale: float, bias: float = 0.0):
    """PURE, lokale uitbreiding van ll.estimate_win_probability() met een
    extra bias/verschuiving-term op het ratingverschil."""
    if our_avg is None or their_avg is None:
        return None
    diff = (our_avg - their_avg) + bias
    try:
        return 1.0 / (1.0 + math.pow(10.0, -diff / scale))
    except OverflowError:
        return 0.0 if diff < 0 else 1.0


def find_best_scale_and_bias(
    raw_rows: list, scales=None, biases=None, form_weights=None,
) -> dict:
    """Doorzoekt een rooster (scale x bias x form_weight) en geeft de
    combinatie met de laagste Brier-score terug. `form_weights` bevat
    ALTIJD 0.0, dus dit kan NOOIT slechter zijn dan zonder vorm-term."""
    scales = scales or _SCALE_BIAS_SEARCH_SCALES
    biases = biases or _BIAS_SEARCH_RANGE
    form_weights = form_weights if form_weights is not None else _FORM_WEIGHT_SEARCH_RANGE
    if 0.0 not in form_weights:
        form_weights = [0.0] + list(form_weights)
    form_adjustment = compute_form_adjustment(raw_rows, scale=_DEFAULT_SCALE, bias=0.0) if any(form_weights) else {}
    best = None
    curve = []
    for s in scales:
        for b in biases:
            for fw in form_weights:
                scored = score_raw_at_scale(raw_rows, s, bias=b, form_weight=fw, form_adjustment=form_adjustment)
                stats = calibration_stats(scored)
                if stats is None:
                    continue
                curve.append({"scale": s, "bias": b, "form_weight": fw, "brier": stats["brier"], "n": stats["n"]})
                if best is None or stats["brier"] < best["brier"]:
                    best = {"scale": s, "bias": b, "form_weight": fw, "brier": stats["brier"], "n": stats["n"]}
    return {"best": best, "curve": curve, "form_adjustment": form_adjustment}


def logistic_curve(scale: float, diffs=None) -> list:
    diffs = diffs if diffs is not None else list(range(-400, 401, 10))
    return [(d, ll.estimate_win_probability(0.0, -float(d), scale=scale)) for d in diffs]


# --------------------------------------------------------------- winkansfactor opslaan
def _load_saved_scale() -> dict:
    """Leest de laatst opgeslagen winkansfactor, bias EN form_weight uit
    Firestore. Faalt stil. Ontbrekende velden (oudere opslag) vallen veilig
    terug op 0.0."""
    try:
        doc = fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_CALIBRATION_SETTINGS_DOC).get()
        data = doc.to_dict() if doc is not None and getattr(doc, "exists", True) else None
        if data and data.get("win_probability_scale") is not None:
            return {
                "scale": float(data["win_probability_scale"]),
                "bias": float(data.get("win_probability_bias") or 0.0),
                "form_weight": float(data.get("win_probability_form_weight") or 0.0),
            }
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_scale_to_firestore(scale: float, bias: float = 0.0, form_weight: float = 0.0) -> None:
    try:
        fb.db.collection(_CALIBRATION_SETTINGS_COLLECTION).document(_CALIBRATION_SETTINGS_DOC).set(
            {
                "win_probability_scale": float(scale),
                "win_probability_bias": float(bias),
                "win_probability_form_weight": float(form_weight),
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


def _source_is_padelstat(sources) -> bool:
    return all(s is not None and "klassement" not in s and s != "onbekend" for s in (sources or []))


def _render_board_row(bp: dict, name_lookup: dict, form_index: Optional[Dict[str, dict]] = None) -> None:
    p1, p2 = bp["pair"]
    ons = f"{name_lookup.get(p1, p1)} / {name_lookup.get(p2, p2)}"
    hen = f"{bp.get('opp1_name', '?')} / {bp.get('opp2_name', '?')}"
    kleur = _outcome_color(bp["win_probability"], bp["actual_won"])
    uitslag = "gewonnen" if bp["actual_won"] is True else ("verloren" if bp["actual_won"] is False else "onbekend")
    badge = "" if (_source_is_padelstat(bp.get("our_sources")) and _source_is_padelstat(bp.get("their_sources"))) \
        else " \u00b7 :orange[deels klassement]"
    st.markdown(
        f"**{ons}** tegen **{hen}** ({bp.get('score') or '?'}) - "
        f"voorspeld :{kleur}[**{_pct(bp['win_probability'])}**] ({bp['risk_note']}), "
        f"echt **{uitslag}**{badge}"
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
        if form_index:
            vorm_regels = []
            for pid in (p1, p2):
                txt = _format_individual_form(form_index, pid, name_lookup.get(pid, str(pid)))
                if txt:
                    vorm_regels.append(txt)
            for uid, naam in ((bp.get("opp1_user_id"), bp.get("opp1_name")), (bp.get("opp2_user_id"), bp.get("opp2_name"))):
                txt = _format_individual_form(form_index, uid, naam or "?")
                if txt:
                    vorm_regels.append(txt)
            if vorm_regels:
                st.caption("Individuele vorm (alle bekende interclub-matchen): " + " \u00b7 ".join(vorm_regels))


def _apply_scale_callback(new_scale: float, new_bias: float = 0.0, new_form_weight: float = 0.0) -> None:
    st.session_state["retro_scale"] = new_scale
    st.session_state["retro_bias"] = new_bias
    st.session_state["retro_form_weight"] = new_form_weight
    st.session_state.pop("retro_best_scale_bias_result", None)
    _save_scale_to_firestore(new_scale, new_bias, new_form_weight)


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
            st.session_state["retro_form_weight"] = saved.get("form_weight", 0.0)

    all_ids_sig = tuple(sorted({str(p.get("player_id")) for p in profiles if p.get("player_id")}))
    all_data_key = "retro_all_valid_data"
    if st.session_state.get(all_data_key + "_sig") != all_ids_sig:
        with perf.step("retro: alle geldige matchdata verzamelen (gather_all_valid_match_data)"):
            with st.spinner("Alle gekende matchen doorzoeken..."):
                st.session_state[all_data_key] = gather_all_valid_match_data(profiles)
        st.session_state[all_data_key + "_sig"] = all_ids_sig
    all_data = st.session_state[all_data_key]
    form_index = all_data.get("form_index") or {}

    with perf.step("retro: eigen matchen ophalen"):
        with st.spinner(f"Matchen van {sel_naam} ophalen..."):
            docs = ll.get_docs_for_players([sel_player_id])

    st.caption(
        f"Vergelijkt, voor **{sel_naam}**, de voorspelde winkans met de echte uitslag van eerder gespeelde "
        "interclub-matchen, MET de padelstat-/klassementwaarden van TOEN (niet de huidige) waar bekend. "
        "Gebruik dit om te controleren of de winkans-formule klopt, en wat het betere alternatief geweest "
        "zou zijn. De kalibratie verderop gebruikt wel ALLE gekende matchen van iedereen, niet enkel van "
        f"{sel_naam}."
    )

    with perf.step("retro: encounter-index bouwen (eigen matchen)"):
        index = build_retro_encounter_index(docs, allowed_player_ids={sel_player_id})
    encounters = list_retro_encounters(index)
    if not encounters:
        st.info(f"Nog geen gespeelde interclub-ontmoetingen gevonden voor {sel_naam}.")
        return

    labels = [lbl for _k, lbl in encounters]
    key_by_label = {lbl: k for k, lbl in encounters}
    gekozen_label = st.selectbox(
        "Kies een eerder gespeelde ontmoeting", labels, key="retro_pick_encounter",
    )
    gekozen_key = key_by_label[gekozen_label]

    with perf.step("retro: teamgenoten van deze ontmoeting zoeken"):
        teammate_docs = _resolve_encounter_teammates(sel_player_id, gekozen_key, profiles)
    docs_encounter = dict(docs)
    docs_encounter.update(teammate_docs)
    if teammate_docs:
        st.caption(
            f"{len(teammate_docs)} teamgenoot/teamgenoten van deze ontmoeting automatisch mee opgenomen: "
            + ", ".join(name_lookup.get(pid, pid) for pid in teammate_docs)
        )
    index_encounter = build_retro_encounter_index(
        docs_encounter, allowed_player_ids=set(docs_encounter.keys()),
    )
    entries_encounter = index_encounter.get(gekozen_key, [])
    boards = reconstruct_boards_with_rankings(entries_encounter)

    own_side_ids = {sel_player_id} | set(teammate_docs.keys())
    for _pid, m in entries_encounter:
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

    player_ids = tuple(sorted(_collect_relevant_player_ids(index_encounter)))
    with perf.step(f"retro: padelstat-historiek laden ({len(player_ids)} spelers)"):
        ratings_cache = _load_padelstat_histories(player_ids)

    scale = st.session_state.get("retro_scale", _DEFAULT_SCALE)
    bias = st.session_state.get("retro_bias", 0.0)
    form_weight = st.session_state.get("retro_form_weight", 0.0)
    with perf.step("retro: ontmoeting voorspellen (predict_encounter)"):
        pred = predict_encounter(boards, current_official_ranks, ratings_cache, scale=scale)
    if pred["snapshot_used"]:
        st.success("Een eerdere momentopname van deze ontmoeting werd gevonden - de waarden van toen zijn exact.")
    st.markdown("#### Per match: voorspeld tegenover echt")
    for bp in pred["boards"]:
        _render_board_row(bp, name_lookup, form_index=form_index)

    st.divider()
    st.markdown("#### Eindresultaat van de ontmoeting: voorspeld tegenover echt")
    n_known_boards = len(boards)
    if n_known_boards < 2 or n_known_boards % 2 != 0:
        st.caption(
            f"We kennen {n_known_boards} van de borden van deze ontmoeting - te weinig (of een oneven "
            "aantal, wat altijd op een ontbrekend bord wijst) voor een betrouwbaar eindresultaat."
        )
    else:
        encounter_pp = _combine_boards_to_point_probs([bp["win_probability"] for bp in pred["boards"]])
        st.caption(f"Gebaseerd op alle {n_known_boards} gekende borden van deze ontmoeting.")
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
            alt = best_alternative_for_encounter(boards, docs_encounter, current_official_ranks, ratings_cache, scale=scale)
    if alt.get("reason") == "too_few_players":
        st.caption(
            f"Onvoldoende eigen spelers gekend voor deze ontmoeting ({alt.get('n_players', 0)} van de nodige 4)."
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

    # PADEL_ANALYSIS_RETRO_CALIBRATION_SIMPLIFY_2026-10-05 - zie moduledocstring:
    # GEEN tellingen-blok, GEEN vergelijkingssectie, GEEN keuzeschakelaar meer -
    # de kalibratie gebruikt ONVOORWAARDELIJK de volledige-padelstat-subset.
    st.divider()
    st.markdown("#### Kalibratie over alle gekende matchen (enkel padelstat)")
    st.caption(
        "Gebruikt ALLE interclub-matchen in de database waarvoor we ECHTE padelstat-waarden hebben voor "
        "alle 4 spelers EN de echte uitslag kennen - dit is de betrouwbaarste subset (het officiele "
        "klassement verandert traag en in grove stappen, en vertekent anders het beeld)."
    )
    raw_rows = all_data.get("full_padelstat_rows") or []
    if not raw_rows:
        st.info(
            "Nog geen enkele match met echte padelstat-waarden voor alle 4 spelers - de kalibratie kan nog "
            "niet berekend worden."
        )
        return

    form_txt = f", vorm-gewicht {form_weight:+.2f}" if form_weight else ""
    st.markdown(f"Huidige instelling: **factor {scale:.0f}**, **bias {bias:+.0f}**{form_txt}.")
    st.caption(
        "Wijzig dit uitsluitend via 'Zoek beste model' hieronder + 'Toepassen' - geen handmatige "
        "schuifregelaar meer."
    )

    with perf.step("retro: kalibratie herberekenen (score_raw_at_scale)"):
        form_adj_cache = compute_form_adjustment(raw_rows, scale=_DEFAULT_SCALE, bias=0.0) if form_weight else {}
        stats = calibration_stats(score_raw_at_scale(raw_rows, scale, bias=bias, form_weight=form_weight, form_adjustment=form_adj_cache))
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
            "opgooien. Probeer hieronder 'Beste model zoeken'."
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
        st.caption("Idealiter liggen 'Gem. voorspeld' en 'Werkelijk gewonnen' per rij dicht bij elkaar.")
        hoogste_bin = stats["bins"][-1] if stats["bins"] else None
        if hoogste_bin and abs(hoogste_bin["gem_voorspeld"] - hoogste_bin["werkelijk"]) >= 8:
            st.caption(
                f"Let op: de hoogste kansklasse ({hoogste_bin['bereik']}) wijkt het meest af "
                f"({hoogste_bin['gem_voorspeld']:.0f}% voorspeld tegenover {hoogste_bin['werkelijk']:.0f}% werkelijk)."
            )

    st.divider()
    st.markdown("##### Beste model zoeken (schaal + bias + individuele vorm)")
    st.caption(
        "Zoekt een schaalfactor, een vaste bias-verschuiving EN hoeveel gewicht de sterkte-gecorrigeerde "
        "individuele vorm van elke speler krijgt. form_weight=0 zit altijd in de zoekruimte, dus dit kan "
        "nooit slechter zijn dan zonder vorm-term."
    )
    if st.button("Zoek beste model (schaal + bias + vorm)", key="retro_find_best_scale_bias"):
        with perf.step("retro: beste model zoeken (find_best_scale_and_bias)"):
            with st.spinner("Rooster van factor x bias x vorm-gewicht doorrekenen (kan even duren)..."):
                st.session_state["retro_best_scale_bias_result"] = find_best_scale_and_bias(raw_rows)
    result2 = st.session_state.get("retro_best_scale_bias_result")
    if result2 and result2.get("best"):
        best2 = result2["best"]
        verbetering = stats["brier"] - best2["brier"]
        form_part = f", vorm-gewicht **{best2['form_weight']:+.2f}**" if best2.get("form_weight") else ""
        st.info(
            f"Voorstel: factor **{best2['scale']}**, bias **{best2['bias']:+.0f}**{form_part} - Brier "
            f"**{best2['brier']:.3f}** (huidig: {stats['brier']:.3f}, verbetering: {verbetering:+.3f})."
        )
        if best2.get("form_weight"):
            st.caption(
                "De vorm-term gaf hier een meetbare verbetering - individuele vorm (gecorrigeerd voor "
                "tegenstandersterkte) kan het model dus verbeteren."
            )
        elif verbetering < 0.005:
            st.caption("De verbetering is klein - noch bias noch vorm lijken hier veel extra te helpen.")
        st.button(
            f"Toepassen: factor {best2['scale']}, bias {best2['bias']:+.0f}, vorm {best2.get('form_weight', 0.0):+.2f}",
            key="retro_apply_best_scale_bias",
            on_click=_apply_scale_callback, args=(best2["scale"], best2["bias"], best2.get("form_weight", 0.0)),
        )
