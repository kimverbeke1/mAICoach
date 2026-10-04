"""
lineup_retrospective.py - Nabeschouwing: per eerder gespeelde ontmoeting de
voorspelde winkans tegenover de echte uitslag, MET de padelstat-/officiële
klassementwaarden van TOEN (niet de huidige), plus een kalibratieblok over
alle gespeelde matchen samen met een instelbare winkansfactor.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03 (op verzoek van Kim: "het zou ook
handig zijn om al gespeelde matchen ook nog te kunnen analyseren maar dan
met de padelstat waardes van toen [...] in principe moet je dan enkel die
opstellen simuleren en eventueel tonen wat het betere alternatief was en
ook de winstpercentages aftoetsen met om te bekijken of de winstkansen wel
goed berekend werden [...] we hebben in het verleden al gekeken om dan ook
de factor voor berekening winst te visualiseren en aanpasbaar te maken")
--------------------------------------------------------------------------
BRONNEN VAN "DE WAARDEN VAN TOEN", in volgorde van betrouwbaarheid:
  1. Een momentopname uit lineup_plan_screen.py (collectie
     "lineup_snapshots"): de EXACTE padelstat-/klassementwaarden die de app
     gebruikte toen je die ontmoeting effectief plande. Enkel beschikbaar
     voor ontmoetingen waar je het planscherm gebruikte.
  2. firebase_service.get_padelstat_rating_at(player_id, datum): de
     padelstat-HISTORIEK (PADEL_ANALYSIS_PADELSTAT_HISTORY_2026-10-03),
     die vanaf de eerste refresh ERNA automatisch verder aangevuld wordt.
     Voor data van VOOR die historiek bestond, is er simpelweg niets - de
     functie geeft dan None terug, geen verzonnen waarde.
  3. Voor TEGENSTANDERS: het officiële klassement staat als tekst
     ("P200" e.d.) al IN het eigen matchrecord (opp1_ranking/opp2_ranking,
     zoals getoond op het uitslagenblad op dat moment) - dat is dus
     ALTIJD een waarde van toen, nooit de huidige.
  4. Voor ONZE EIGEN spelers: er is GEEN historiek van het officiële
     klassement in dit project (enkel klassement_history van TVL, die
     niet per speler teruggekoppeld is aan deze module) - bij ontbrekende
     padelstat-historiek valt dit bestand daarom terug op het HUIDIGE
     officiële klassement, EXPLICIET gelabeld als "benadering" in de UI.
     Dit is een bewuste, duidelijk gecommuniceerde beperking, geen gok die
     verstopt wordt.
--------------------------------------------------------------------------
WAAROM DIT BESTAND EIGEN ENCOUNTER/BOARD-RECONSTRUCTIE HEEFT (NIET
ll.build_encounter_index()/ll.reconstruct_boards() HERGEBRUIKT):
die twee functies in lineup_lab.py geven exact dezelfde GROEPERING
(match_date, encounter) en dedupe-sleutel (match_id + koppel) terug - dat
MOET identiek blijven, dus de logica hieronder is BEWUST een letterlijke
kopie daarvan - maar ze laten de "opp1_ranking"/"opp2_ranking"-tekstvelden
van elk matchrecord vallen, die hier net essentieel zijn (bron 3 hierboven).
Een lokale kopie die deze velden WEL meeneemt is veiliger dan de publieke
functies van lineup_lab.py aan te passen voor een gebruik dat buiten hun
oorspronkelijke scope valt.
--------------------------------------------------------------------------
KALIBRATIE: exact dezelfde methodologie als de eerdere validatie die tot
scale=207 leidde (zie lineup_lab.py, PADEL_ANALYSIS_WINPROB_CALIBRATION_
2026-09-22-commentaar): Brier-score, accuraatheid, en gemiddeld voorspeld
tegenover werkelijk gewonnen per kansklasse (bins van 10 procentpunt). De
schuifregelaar herberekent deze cijfers LIVE voor een gekozen factor, maar
wijzigt NERGENS de globale DEFAULT_WIN_PROBABILITY_SCALE die de rest van de
app gebruikt (lineup_lab.py, lineup_rotation.py) - dat blijft een BEWUSTE,
aparte stap mocht Kim de uitkomst willen overnemen.
"""
import re
from collections import defaultdict
from typing import Dict, List, Optional

import streamlit as st
import lineup_lab as ll
import firebase_service as fb

SNAPSHOT_COLLECTION = "lineup_snapshots"
_DEFAULT_SCALE = ll.DEFAULT_WIN_PROBABILITY_SCALE
_CALIBRATION_BIN_EDGES = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]


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
# PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03: letterlijke kopie van de groepering/
# dedupe-logica in lineup_lab.py (_encounter_key/_board_dedupe_key/
# build_encounter_index/reconstruct_boards) - zie moduledocstring voor waarom
# dit NIET via die functies hergebruikt wordt (ze laten opp*_ranking vallen).
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


def build_retro_encounter_index(docs: Dict[str, dict]) -> Dict[tuple, list]:
    index: Dict[tuple, list] = {}
    for pid, doc in docs.items():
        for m in doc.get("matches", []) or []:
            if m.get("match_type") != "interclub":
                continue
            index.setdefault(_encounter_key(m), []).append((pid, m))
    return index


def list_retro_encounters(index: Dict[tuple, list]) -> List[tuple]:
    """Zelfde label-afleiding als ll.list_encounters(), meest recent eerst.
    Geeft (key, label, date) terug."""
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
    items.sort(key=lambda x: x[2] or "", reverse=True)
    return [(k, lbl) for k, lbl, _ in items]


def reconstruct_boards_with_rankings(entries: list) -> List[dict]:
    """Zoals ll.reconstruct_boards(), maar behoudt ook opp1_ranking/
    opp2_ranking (tekst, bv. "P200") en match_date - nodig voor de
    retrospectieve voorspelling (zie moduledocstring, bron 3)."""
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


# --------------------------------------------------------------- momentopnames
def _find_snapshot_for(date_text, opp_user_ids: set) -> Optional[dict]:
    """PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03: zoekt een momentopname
    (lineup_plan_screen.py) die bij deze datum en minstens 1 van deze
    tegenstander-id's hoort. Faalt altijd stil (None)."""
    iso = to_iso_date(date_text)
    if not iso:
        return None
    try:
        docs = fb.db.collection(SNAPSHOT_COLLECTION).limit(500).stream()
    except Exception:  # noqa: BLE001
        return None
    for doc in docs:
        data = doc.to_dict() or {}
        if to_iso_date(data.get("match_date")) != iso:
            continue
        opp_players = data.get("opponent_players") or {}
        if opp_user_ids and not (set(opp_players.keys()) & {str(u) for u in opp_user_ids if u}):
            continue
        return data
    return None


# --------------------------------------------------------------- voorspelling
def _own_value_at(player_id, date_text, current_official_ranks: dict, snapshot_own: dict):
    """Effectieve rating van EEN eigen speler op `date_text` - zie
    moduledocstring voor de volgorde van bronnen. Geeft (waarde, bron) terug;
    waarde is None als er niets gekend is."""
    pid = str(player_id)
    if snapshot_own and pid in snapshot_own:
        v = snapshot_own[pid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    iso = to_iso_date(date_text)
    if iso:
        try:
            hist = fb.get_padelstat_rating_at(pid, iso)
        except Exception:  # noqa: BLE001
            hist = None
        if hist is not None:
            return float(hist), "padelstat-historiek (op datum)"
    fallback = (current_official_ranks or {}).get(pid)
    if fallback is not None:
        return float(fallback), "huidig officieel klassement (benadering)"
    return None, "onbekend"


def _opponent_value_at(user_id, ranking_text, date_text, snapshot_opp: dict):
    """Effectieve rating van EEN tegenstander-speler op `date_text`."""
    uid = str(user_id) if user_id else None
    if snapshot_opp and uid and uid in snapshot_opp:
        v = snapshot_opp[uid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    if uid:
        iso = to_iso_date(date_text)
        if iso:
            try:
                hist = fb.get_padelstat_rating_at(uid, iso)
            except Exception:  # noqa: BLE001
                hist = None
            if hist is not None:
                return float(hist), "padelstat-historiek (op datum)"
    official = ll.parse_ranking(ranking_text)
    if official is not None:
        return float(official), "officieel klassement (van toen, uit het uitslagenblad)"
    return None, "onbekend"


def predict_board(
    board: dict, current_official_ranks: dict, scale: float = _DEFAULT_SCALE,
    snapshot: Optional[dict] = None,
) -> dict:
    """Herberekent de winkans voor EEN bord, met de waarden van toen."""
    date_text = board.get("match_date")
    p1, p2 = tuple(board["pair"])
    snap_own = (snapshot or {}).get("own_players") or {}
    snap_opp = (snapshot or {}).get("opponent_players") or {}
    our_vals = [_own_value_at(p, date_text, current_official_ranks, snap_own) for p in (p1, p2)]
    their_vals = [
        _opponent_value_at(board.get("opp1_user_id"), board.get("opp1_ranking"), date_text, snap_opp),
        _opponent_value_at(board.get("opp2_user_id"), board.get("opp2_ranking"), date_text, snap_opp),
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
    boards: list, current_official_ranks: dict, opp_ploeg_hint: Optional[str] = None,
    scale: float = _DEFAULT_SCALE, use_snapshot: bool = True,
) -> dict:
    """Voorspelt alle borden van 1 ontmoeting. Zoekt (indien gevraagd) 1x een
    momentopname voor de hele ontmoeting (alle borden delen dezelfde datum/
    tegenstander)."""
    snapshot = None
    if use_snapshot and boards:
        opp_ids = {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards}
        snapshot = _find_snapshot_for(boards[0].get("match_date"), opp_ids)
    predictions = [predict_board(b, current_official_ranks, scale=scale, snapshot=snapshot) for b in boards]
    return {"boards": predictions, "snapshot_used": snapshot is not None}


# --------------------------------------------------------------- kalibratie
def calibration_stats(predictions: list, bin_edges=None) -> Optional[dict]:
    """Brier-score, log loss, accuraatheid en per-kansklasse voorspeld vs.
    werkelijk - exact dezelfde methodologie als de eerdere, handmatige
    validatie die tot scale=207 leidde (zie lineup_lab.py)."""
    bin_edges = bin_edges or _CALIBRATION_BIN_EDGES
    usable = [p for p in predictions if p.get("win_probability") is not None and p.get("actual_won") is not None]
    n = len(usable)
    if n == 0:
        return None
    import math
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


def logistic_curve(scale: float, diffs=None) -> list:
    """(diff, kans)-punten voor de visualisatie van de winkans-curve bij een
    gekozen `scale`."""
    diffs = diffs if diffs is not None else list(range(-400, 401, 10))
    return [(d, ll.estimate_win_probability(0.0, -float(d), scale=scale)) for d in diffs]


# --------------------------------------------------------------- beste alternatief
def best_alternative_for_encounter(
    boards: list, docs: Dict[str, dict], current_official_ranks: dict,
    scale: float = _DEFAULT_SCALE, top_n: int = 3,
) -> Optional[dict]:
    """Zoekt, MET de waarden van toen en ZONDER deze ontmoeting zelf in de
    synergie te laten meetellen (exclude_match_keys - geen lekkage van de
    uitkomst in de eigen voorspelling), de beste alternatieve koppelverdeling
    voor deze ontmoeting. Geeft None terug als er te weinig data is."""
    if not boards:
        return None
    players = sorted({str(p) for b in boards for p in b["pair"]})
    if len(players) < 4:
        return None
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
        val, _ = _own_value_at(pid, date_text, current_official_ranks, snap_own)
        if val is not None:
            player_ratings[pid] = val
    opponent_boards = []
    opponent_ratings = {}
    for b in boards:
        pair_info = []
        for idx, uid_key, ranking_key in ((0, "opp1_user_id", "opp1_ranking"), (1, "opp2_user_id", "opp2_ranking")):
            uid = b.get(uid_key)
            val, _ = _opponent_value_at(uid, b.get(ranking_key), date_text, snap_opp)
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
        return None
    actual_key = tuple(sorted(tuple(sorted(b["pair"])) for b in boards))
    actual_result = next(
        (r for r in results if tuple(sorted(tuple(sorted(a["our_pair"])) for a in r["assignment"])) == actual_key),
        None,
    )
    return {"top": results, "actual": actual_result}


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
            f"Onze spelers: {bp['our_sources'][0]}, {bp['our_sources'][1]} "
            f"(gemiddeld {bp['our_avg']:.0f})" if bp.get("our_avg") is not None else "Onze spelers: onbekend"
        )
        st.caption(
            f"Tegenstander: {bp['their_sources'][0]}, {bp['their_sources'][1]} "
            f"(gemiddeld {bp['their_avg']:.0f})" if bp.get("their_avg") is not None else "Tegenstander: onbekend"
        )


def render_retrospective_tab(profiles: list, max_players: int = 40) -> None:
    """PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03 - zie moduledocstring. Enkel
    deze functie heeft Streamlit nodig; de rest van dit bestand is daar
    volledig los van (ook los testbaar)."""
    st.markdown('<div class="section-header">Nabeschouwing</div>', unsafe_allow_html=True)
    st.caption(
        "Vergelijkt de voorspelde winkans met de echte uitslag van eerder gespeelde ontmoetingen, "
        "MET de padelstat-/klassementwaarden van TOEN (niet de huidige) waar bekend. Gebruik dit om "
        "te controleren of de winkans-formule klopt, en wat het betere alternatief geweest zou zijn."
    )
    player_ids = [str(p.get("player_id")) for p in profiles if p.get("player_id")][:max_players]
    name_lookup = {str(p.get("player_id")): (p.get("display_name") or str(p.get("player_id"))) for p in profiles}
    # PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03: beste-poging terugval - het HUIDIGE
    # officiele klassement, enkel gebruikt als er geen padelstat-historiek is (zie
    # moduledocstring, bron 4). Hergebruikt dezelfde functie als de rest van de app;
    # faalt die (bv. module niet beschikbaar), dan blijft de terugval leeg i.p.v. te crashen.
    current_official_ranks = {}
    try:
        from lineup_scout import _build_own_official_ranks_strict
        current_official_ranks = _build_own_official_ranks_strict(player_ids) or {}
    except Exception:  # noqa: BLE001
        pass
    st.caption(
        "Let op: voor ONZE eigen spelers is er geen historiek van het OFFICIELE klassement in deze app "
        "(enkel van de padelstat-waarde, sinds kort). Ontbreekt er padelstat-historiek voor een speler op "
        "die datum, dan valt de berekening terug op zijn HUIDIGE klassement - duidelijk gelabeld hieronder "
        "als 'benadering'. Voor de tegenstander komt het officiele klassement WEL altijd van toen, want dat "
        "staat al op het uitslagenblad van die dag."
    )
    with st.spinner("Eigen matchen ophalen..."):
        docs = ll.get_docs_for_players(player_ids)
    index = build_retro_encounter_index(docs)
    encounters = list_retro_encounters(index)
    if not encounters:
        st.info("Nog geen gespeelde interclub-ontmoetingen gevonden in de database.")
        return
    labels = [lbl for _k, lbl in encounters]
    key_by_label = {lbl: k for k, lbl in encounters}
    gekozen_label = st.selectbox("Kies een eerder gespeelde ontmoeting", labels, key="retro_pick_encounter")
    gekozen_key = key_by_label[gekozen_label]
    boards = reconstruct_boards_with_rankings(index[gekozen_key])

    scale = st.session_state.get("retro_scale", _DEFAULT_SCALE)
    pred = predict_encounter(boards, current_official_ranks, scale=scale)
    if pred["snapshot_used"]:
        st.success("Een eerdere momentopname van deze ontmoeting werd gevonden - de waarden van toen zijn exact.")
    st.markdown("#### Per match: voorspeld tegenover echt")
    for bp in pred["boards"]:
        _render_board_row(bp, name_lookup)

    st.divider()
    st.markdown("#### Beste alternatief (achteraf, met dezelfde waarden van toen)")
    with st.spinner("Alternatieven doorrekenen..."):
        alt = best_alternative_for_encounter(boards, docs, current_official_ranks, scale=scale)
    if not alt:
        st.caption("Onvoldoende data om alternatieven te berekenen voor deze ontmoeting.")
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

    st.divider()
    st.markdown("#### Kalibratie over alle gespeelde matchen")
    st.caption(
        "Hoe vaak klopte een voorspelling van bv. '60% winkans' ook echt? De Brier-score (lager is beter, "
        "0 = perfect, 0.25 = niet beter dan een muntstuk) en de kans-klassen hieronder gebruiken ALLE "
        "gespeelde matchen van de geselecteerde spelers, niet enkel de bovenstaande ontmoeting."
    )
    c_slider, c_curve = st.columns([2, 1])
    with c_slider:
        scale = st.slider(
            "Winkansfactor (hoe gevoelig de winkans reageert op het ratingverschil)",
            min_value=50, max_value=400, value=int(_DEFAULT_SCALE), step=5, key="retro_scale",
            help=f"Huidige app-standaard: {_DEFAULT_SCALE:.0f}. Een KLEINERE factor maakt elk ratingverschil "
                 "impactvoller (steilere curve); een GROTERE factor maakt de winkans voorzichtiger "
                 "(vlakkere curve). Dit wijzigt ENKEL de berekening hieronder, niet de rest van de app.",
        )
    with c_curve:
        st.caption(f"Bij 100 punten verschil: {_pct(ll.estimate_win_probability(0, -100, scale=scale))} winkans.")

    all_preds = []
    for _k, _lbl in encounters:
        bds = reconstruct_boards_with_rankings(index[_k])
        p = predict_encounter(bds, current_official_ranks, scale=scale, use_snapshot=True)
        all_preds.extend(p["boards"])
    stats = calibration_stats(all_preds)
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
            "systematisch verschil (bv. bij lage kansklassen te hoog, bij hoge te laag) wijst op een "
            "factor die scherper of voorzichtiger zou moeten staan."
        )
