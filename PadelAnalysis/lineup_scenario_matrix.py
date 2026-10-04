"""
lineup_scenario_matrix.py - "Wat als de tegenstander ...?": een kleine
scenario-matrix i.p.v. honderden matchups of 1 uitgevlakt gemiddelde.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_2026-10-03 (op verzoek van Kim: "gewoon
overal hetzelfde gemiddelde zien is ook niet zinvol. Dus specifieke cases
zijn wel interessant. Wat als ze spelen zoals in vorige matchen (meerdere),
wat als ze hun beste spelers in match 1 van rotatie 1 zetten etc.")
--------------------------------------------------------------------------
KOLOMMEN = benoemde tegenstander-opstellingen (volledige ontmoeting):
  "Zoals op <datum>", "Meest waarschijnlijk (model)", "Statistisch #n",
  "Sterkste duo op R1M1", "Sterkste duo in rotatie 2", "Zonder <beste speler>".
RIJEN = eigen strategieen: Aanvallend / Veilig / Robuust / Counter op Sx.
CELLEN = exacte kans tegen precies die ene opstelling.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_V2_2026-10-03 (feedback Kim: "kan je wat
duiding geven over hoe je tot die kansen gekomen bent", "waarom is S4 0%",
"als ik een speler wegklik [...] moet je die opstelling niet tonen", "ik zie
maar 1 scenario van niet gespeelde matchen [...] via statistiek een paar
combinaties maken", "minstens 1 punt")
--------------------------------------------------------------------------
1. DUIDING: de legende toont per scenario twee getallen:
     - "Modelkans": de kans volgens het statistisch model op exact DEZE
       volledige opstelling (alle rotaties samen), t.o.v. ALLE mogelijke
       opstellingen. Is die kleiner dan 1%, dan staat er "<1%" (vroeger
       afgerond naar 0%, wat leek alsof het onmogelijk was);
     - "Gewicht": dezelfde modelkans, hernormaliseerd over de getoonde
       scenario's - dat is het gewicht in de kolom "Gewogen".
   Plus de redenen van het model ("X & Y speelden al 3x samen", ...).
2. SELECTIE: scenario's met een speler die NIET in "Beschikbare
   tegenstander-spelers" staat, worden weggelaten - ook effectief gespeelde
   opstellingen (dat filter gebeurt in lineup_matchup_table.py, vóór het
   model en deze matrix).
3. STATISTISCHE SCENARIO'S: tot 3 waarschijnlijke, nog niet gespeelde
   opstellingen ("Statistisch #1..3"), zodat er ook bij weinig gespeelde
   ontmoetingen meer dan 1 niet-gespeeld scenario is.
4. "Kans op minstens 1 punt" is nu de standaardweergave.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_V3_2026-10-03 (feedback Kim: "graag sorteren met
grootste gewicht bovenaan en dat wordt dan S1", "'kolom' vervangen door
'Scenario'", "de waarom kan beter opengeklikt worden", "hun opstelling mag
leesbaarder", en de verwarring 52% (matrix) vs 24% (rotatieplanner))
--------------------------------------------------------------------------
1. Scenario's gesorteerd op gewicht (S1 = grootste gewicht).
2. Legende: kolommen "Scenario", "Wat", "Gewicht", "Modelkans", "Rotatie 1",
   "Rotatie 2" - hun opstelling per rotatie in een eigen kolom. Het "waarom"
   staat in een inklapbaar blok.
3. EEN BRON: de getoonde scenario's (met hun gewicht) worden bewaard in
   st.session_state["scen_matrix_scen_v3_<ploeg>"]. Het planscherm in de
   Rotatieplanner gebruikt EXACT deze lijst - S1 betekent dus overal
   hetzelfde, met hetzelfde gewicht. Het verschil 52% vs 24% kwam doordat
   de planner per ROTATIE een eigen kans berekende (andere noemer) - dat
   valt weg.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_V4_2026-10-03 (feedback Kim: "eerst radio button
met kans op winst tonen en dan gelijk en dan verlies")
--------------------------------------------------------------------------
Radiovolgorde Winst -> Gelijk -> Verlies -> Minstens 1 punt. Beste cel per
kolom in het vet. "Counter op Sx" enkel tonen als die specifieke opstelling
>= 1 procentpunt beter doet dan de algemene strategieen op dat scenario.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_V5_2026-10-04 (op verzoek van Kim: "bij de
analyse zijn een aantal zaken die een beetje overlappen [...] de
rotatieplanner is voor mezelf de core. Dus ik zou die na de scenario
analyse tonen. kans op winst en detail bij scenario analyse zelf voor
aanvallend, veilig en robuust mogen dan eigenlijk wel weg")
--------------------------------------------------------------------------
De volledige strategie-matrix (Aanvallend/Veilig/Robuust/Counter-rijen, de
kans-radiobutton en het "Detail: wie tegen wie"-blok) is VERWIJDERD uit
render_scenario_matrix(). Die vraag ("wat is onze beste opstelling tegen
dit scenario?") wordt nu beantwoord door de Rotatieplanner (lineup_plan_
screen.py), die meteen na deze sectie staat en dezelfde scenario's (via
dezelfde st.session_state-sleutel) hergebruikt als snelkeuze, met een
eindresultaat dat bij elke wijziging herrekent. Deze sectie toont nu enkel
nog de scenario-LEGENDE (welke opstellingen, hoe waarschijnlijk, waarom) -
de bouwstenen pick_strategies()/compute_matrix()/build_own_options() blijven
in dit bestand staan (geen functionaliteit verwijderd, enkel niet langer
vanuit render_scenario_matrix() aangeroepen) mocht een latere, aparte
"geavanceerd"-weergave ze nog nodig hebben.

--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04 (op verzoek van Kim: "eigenlijk
komt het er dan op neer dat we meteen de scenario analyse in die
rotatieplanner integreren wat beter is. Nog niet direct die scenario
analyse weglaten maar ik wil wel al eens zien of we die data niet meteen
proper in de rotatieplanner kunnen steken" + "je mag ook de waarom van deze
kansen tonen" bij de S-knoppen in de Rotatieplanner)
--------------------------------------------------------------------------
De "waarom"-reden per scenario werd voorheen ENKEL berekend in de expander
hieronder ("Waarom deze kansen? (model)"), dus niet beschikbaar voor
lineup_plan_screen.py. FIX: de reden wordt nu EENMALIG berekend (niet 2x)
en VERPLICHT mee opgeslagen in de gedeelde st.session_state-lijst
("scen_matrix_scen_v3_<ploeg>") als veld "reasons", naast "model_prob" -
lineup_plan_screen.py kan deze nu rechtstreeks tonen onder de S-knoppen,
zonder het model zelf opnieuw te moeten aanroepen. Deze sectie zelf (de
scenario-analyse) blijft ONGEWIJZIGD bestaan - Kim wil ze voorlopig nog
niet weglaten.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_V6_2026-10-04 (op verzoek van Kim: "dan mag
dat stukje van de scenario analyse in het begin gewoon weg", in dezelfde
beurt als de Rotatieplanner-integratie hierboven - de Rotatieplanner toont
nu immers al een "Scenario-overzicht" met dezelfde Scenario/Wat/Gewicht/
Rotatie 1/Rotatie 2/Waarom-tabel, meteen onder de S-knoppen)
--------------------------------------------------------------------------
De 2 lange introductie-caption-blokken ZIJN WEG (uitleg over kolommen/rijen/
cellen die hier historisch stond maar sinds V5 niet meer klopt, en de
uitleg over Modelkans/Gewicht/"<1%" die nu dubbel stond met de
Rotatieplanner). In de plaats: EEN korte regel die verwijst naar de
Rotatieplanner. De dataframe-tabel en de "Waarom deze kansen?"-expander
blijven ONGEWIJZIGD staan - dit bestand blijft de ENIGE plek die de
scenario's berekent en in st.session_state["scen_matrix_scen_v3_<ploeg>"]
zet; de Rotatieplanner hergebruikt die lijst enkel, zonder zelf opnieuw te
rekenen. Verwijder je deze sectie ooit volledig, dan moet die berekening
ergens anders komen te staan, anders heeft de Rotatieplanner geen
scenario's meer om te tonen.
"""
import streamlit as st

from dashboard_common import ll, _parse_match_date
from lineup_rotation import (
    _enumerate_rotation_aware_pairings, _enumerate_own_variant_combinations,
    _compute_matchup, _opponent_lineup_weight, MATCHES_PER_ROTATION,
)

try:
    import opponent_lineup_model as olm
except Exception:  # noqa: BLE001  pragma: no cover
    olm = None

_MAX_SCENARIOS = 9
_N_STATISTICAL = 3
_SACRIFICE_WP = 0.30
_METRICS = {
    "Kans op winst (2 punten)": "p2",
    "Kans op gelijk (1 punt)": "p1",
    "Kans op verlies (0 punten)": "p0",
    "Kans op minstens 1 punt": "p_ge1",
}
_COUNTER_MIN_GAIN = 0.01  # counter enkel tonen als die op zijn scenario >= 1 procentpunt beter doet


# ---------------------------------------------------------------- helpers
def _player_strength(p: dict, opponent_ratings: dict):
    uid = p.get("user_id")
    if not uid:
        return None
    return ll.effective_simulation_rating(
        uid, opponent_ratings or {}, {uid: ll.parse_ranking(p.get("ranking"))},
    )


def _pair_strength(board: dict, opponent_ratings: dict):
    vals = [_player_strength(p, opponent_ratings) for p in (board.get("opponent_pair") or [])]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _board_uids(board: dict) -> frozenset:
    return frozenset(str(p.get("user_id")) for p in (board.get("opponent_pair") or []) if p.get("user_id"))


def _lineup_text_opp(boards: list) -> str:
    delen = []
    for idx, b in enumerate(boards):
        namen = "/".join(p.get("name", "?") for p in (b.get("opponent_pair") or []))
        delen.append(f"R{idx // MATCHES_PER_ROTATION + 1}M{idx % MATCHES_PER_ROTATION + 1} {namen}")
    return " \u00b7 ".join(delen)


def _lineup_text_own(pairs: list, name_lookup: dict) -> str:
    delen = []
    for idx, pair in enumerate(pairs):
        namen = "/".join(name_lookup.get(u, u) for u in sorted(pair))
        delen.append(f"R{idx // MATCHES_PER_ROTATION + 1}M{idx % MATCHES_PER_ROTATION + 1} {namen}")
    return " \u00b7 ".join(delen)


def _date_key(label: str):
    try:
        d = _parse_match_date(label)
    except Exception:  # noqa: BLE001
        d = None
    return d or (0, 0, 0)


def _pct_txt(p: float) -> str:
    if p is None:
        return "-"
    if p < 0.005:
        return "<1%"
    return f"{p * 100:.0f}%"


def _reasons(model_stats, key) -> str:
    if olm is None or not model_stats:
        return ""
    redenen = []
    for r in range(0, len(key) - 1, MATCHES_PER_ROTATION):
        try:
            redenen += olm.explain_rotation(model_stats, key[r], key[r + 1], max_reasons=2)
        except Exception:  # noqa: BLE001
            pass
    return " \u00b7 ".join(list(dict.fromkeys(redenen))[:3])


# ----------------------------------------------------- tegenstander-scenario's
def build_opponent_scenarios(
    unique_opponent_lineups: dict, model_weights: dict, opponent_ratings: dict, total_boards: int,
) -> list:
    """Kiest de benoemde tegenstander-scenario's. Geeft een lijst van
    {"key", "boards", "labels", "model_prob", "weight"} terug."""
    items = {
        k: v for k, v in unique_opponent_lineups.items()
        if len(v.get("boards") or []) == int(total_boards)
    }
    if not items:
        return []

    def _w(k):
        if model_weights:
            return model_weights.get(k, 0.0)
        return _opponent_lineup_weight(items[k])

    gekozen: dict = {}

    def _voeg_toe(key, label):
        if key is None:
            return
        if key in gekozen:
            if label not in gekozen[key]["labels"]:
                gekozen[key]["labels"].append(label)
            return
        if len(gekozen) >= _MAX_SCENARIOS:
            return
        gekozen[key] = {"key": key, "boards": items[key]["boards"], "labels": [label]}

    def _beste(pred):
        kandidaten = [k for k in items if pred(k)]
        return max(kandidaten, key=_w) if kandidaten else None

    hist = [k for k, v in items.items() if v.get("is_historical")]
    hist.sort(key=lambda k: max(_date_key(l) for l in items[k]["historical_labels"]), reverse=True)
    for k in hist:
        _voeg_toe(k, "Zoals op " + ", ".join(items[k]["historical_labels"]))

    if model_weights:
        _voeg_toe(max(items, key=_w), "Meest waarschijnlijk (model)")
        niet_gespeeld = sorted(
            (k for k, v in items.items() if not v.get("is_historical") and k not in gekozen),
            key=_w, reverse=True,
        )
        for i, k in enumerate(niet_gespeeld[:_N_STATISTICAL], start=1):
            _voeg_toe(k, f"Statistisch #{i}")

    paren, spelers = {}, {}
    for v in items.values():
        for b in v["boards"]:
            s = _pair_strength(b, opponent_ratings)
            if s is not None:
                paren[_board_uids(b)] = s
            for p in b.get("opponent_pair") or []:
                ps = _player_strength(p, opponent_ratings)
                if ps is not None and p.get("user_id"):
                    spelers[str(p["user_id"])] = (ps, p.get("name", "?"))

    if paren:
        sterkste_duo = max(paren, key=paren.get)
        _voeg_toe(_beste(lambda k: _board_uids(items[k]["boards"][0]) == sterkste_duo),
                  "Sterkste duo op R1M1")
        if int(total_boards) > MATCHES_PER_ROTATION:
            _voeg_toe(
                _beste(lambda k: _board_uids(items[k]["boards"][MATCHES_PER_ROTATION]) == sterkste_duo),
                "Sterkste duo in rotatie 2",
            )
    if spelers:
        top_uid = max(spelers, key=lambda u: spelers[u][0])
        _voeg_toe(
            _beste(lambda k: all(top_uid not in _board_uids(b) for b in items[k]["boards"])),
            f"Zonder {spelers[top_uid][1]}",
        )

    out = list(gekozen.values())
    tot = sum(_w(s["key"]) for s in out) or 1.0
    for s in out:
        s["model_prob"] = model_weights.get(s["key"], 0.0) if model_weights else None
        s["weight"] = _w(s["key"]) / tot
    # PADEL_ANALYSIS_SCENARIO_MATRIX_V3_2026-10-03: grootste gewicht = S1.
    out.sort(key=lambda s: s["weight"], reverse=True)
    return out


def _rotation_text_opp(boards: list, rot_idx: int) -> str:
    """PADEL_ANALYSIS_SCENARIO_MATRIX_V3_2026-10-03: 'M1 A / B · M2 C / D' voor 1 rotatie."""
    stuk = boards[rot_idx * MATCHES_PER_ROTATION:(rot_idx + 1) * MATCHES_PER_ROTATION]
    return "  \u00b7  ".join(
        f"M{m + 1} " + " / ".join(p.get("name", "?") for p in (b.get("opponent_pair") or []))
        for m, b in enumerate(stuk)
    )


# ------------------------------------------------------------ eigen opties
def build_own_options(available_ids, max_per_player, official_ranks_strict, player_ratings, rules) -> list:
    """PADEL_ANALYSIS_SCENARIO_MATRIX_V5_2026-10-04: niet langer aangeroepen
    vanuit render_scenario_matrix() (zie moduledocstring) - blijft bestaan
    voor eventueel hergebruik."""
    structures, _ = _enumerate_rotation_aware_pairings(available_ids, max_per_player)
    out, gezien = [], set()
    for structure in structures:
        for combo in _enumerate_own_variant_combinations(
            structure, official_ranks_strict, player_ratings, rules=rules, include_non_compliant=False,
        ):
            if not combo["fully_compliant"]:
                continue
            if rules is not None and not all(r["valid"] for r in combo["rotations"]):
                continue
            key = tuple(frozenset(p) for p in combo["ordered_pairs"])
            if key in gezien:
                continue
            gezien.add(key)
            out.append(combo["ordered_pairs"])
    return out


# ------------------------------------------------------------ berekening
def compute_matrix(scenarios, own_options, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings):
    """PADEL_ANALYSIS_SCENARIO_MATRIX_V5_2026-10-04: niet langer aangeroepen
    vanuit render_scenario_matrix() - zie moduledocstring."""
    cells = []
    for pairs in own_options:
        rij = []
        for scen in scenarios:
            comp = _compute_matchup(
                pairs, scen["boards"], synergy_fn, player_ratings or {},
                official_ranks_strict, opponent_ratings or {},
            )
            pp = comp["point_probs"]
            rij.append({
                "p2": pp["p2"], "p1": pp["p1"], "p0": pp["p0"], "p_ge1": pp["p2"] + pp["p1"],
                "assignment": comp["assignment"], "ebw": comp["expected_boards_won"],
            })
        cells.append(rij)
    return cells


def pick_strategies(scenarios, cells) -> list:
    """PADEL_ANALYSIS_SCENARIO_MATRIX_V5_2026-10-04: niet langer aangeroepen
    vanuit render_scenario_matrix() - zie moduledocstring."""
    if not cells or not scenarios:
        return []
    w = [s["weight"] for s in scenarios]

    def gew(o, k):
        return sum(wi * c[k] for wi, c in zip(w, cells[o]))

    idx = range(len(cells))
    keuzes = [
        ("Aanvallend (max. kans op winst)", max(idx, key=lambda o: (gew(o, "p2"), gew(o, "p_ge1")))),
        ("Veilig (max. kans op minstens 1 punt)", max(idx, key=lambda o: (gew(o, "p_ge1"), gew(o, "p2")))),
        ("Robuust (beste slechtste geval)",
         max(idx, key=lambda o: (min(c["p_ge1"] for c in cells[o]), gew(o, "p2")))),
    ]
    algemeen = [o for _, o in keuzes]
    for s_idx in range(len(scenarios)):
        beste = max(idx, key=lambda o: (cells[o][s_idx]["p2"], cells[o][s_idx]["p_ge1"]))
        referentie = max(cells[o][s_idx]["p2"] for o in algemeen)
        if cells[beste][s_idx]["p2"] - referentie >= _COUNTER_MIN_GAIN:
            keuzes.append((f"Counter op S{s_idx + 1}", beste))
    rijen: dict = {}
    for label, o in keuzes:
        rijen.setdefault(o, []).append(label)
    return [(" + ".join(labels), o) for o, labels in rijen.items()]


# ------------------------------------------------------------ weergave
def render_scenario_matrix(
    unique_opponent_lineups: dict, model_weights: dict, available_ids: list, max_per_player: dict,
    total_boards: int, synergy_fn, player_ratings: dict, official_ranks_strict: dict,
    opponent_ratings: dict, tournament_rules_dict, name_lookup_global: dict, ploeg_key: str,
    model_stats: dict = None,
) -> None:
    """PADEL_ANALYSIS_SCENARIO_MATRIX_V6_2026-10-04 - zie moduledocstring:
    toont enkel nog een korte intro + de scenario-legende (Scenario/Wat/
    Gewicht/Modelkans/Rotatie 1/Rotatie 2) en de "Waarom"-expander. Deze
    functie blijft wel de ENIGE plek die de scenario's berekent en in
    st.session_state["scen_matrix_scen_v3_<ploeg>"] bewaart - de
    Rotatieplanner (lineup_plan_screen.py) hergebruikt die lijst enkel."""
    st.markdown(
        '<div class="section-header">Scenario-analyse: wat als de tegenstander ...?</div>',
        unsafe_allow_html=True,
    )
    scenarios = build_opponent_scenarios(
        unique_opponent_lineups, model_weights, opponent_ratings, total_boards,
    )
    if not scenarios:
        st.info("Nog geen tegenstander-opstellingen in dit formaat (met de gekozen spelers) om scenario's mee te bouwen.")
        return

    # PADEL_ANALYSIS_SCENARIO_MATRIX_V6_2026-10-04: korte intro i.p.v. de 2
    # lange uitlegblokken van voorheen - de volledige toelichting (wat is
    # Modelkans/Gewicht, wat doe je met deze scenario's) staat nu in de
    # Rotatieplanner, net onder deze sectie.
    st.caption(
        "Deze scenario's zijn de snelkeuzes (S1, S2, ...) in de Rotatieplanner hieronder, waar je meteen "
        "ons beste antwoord en het eindresultaat ziet."
    )

    # PADEL_ANALYSIS_ROTATION_INTEGRATION_2026-10-04: redenen EENMALIG berekend,
    # gedeeld met het planscherm via de sessiestate-lijst (zie moduledocstring).
    redenen_per_scenario = [_reasons(model_stats, s["key"]) for s in scenarios]
    # PADEL_ANALYSIS_SCENARIO_MATRIX_V3_2026-10-03: gedeelde bron voor het planscherm.
    st.session_state[f"scen_matrix_scen_v3_{ploeg_key}"] = [
        {"key": s["key"], "boards": s["boards"], "labels": list(s["labels"]),
         "weight": s["weight"], "model_prob": s.get("model_prob"), "reasons": redenen_per_scenario[i]}
        for i, s in enumerate(scenarios)
    ]

    n_rot = max(1, int(total_boards) // MATCHES_PER_ROTATION)
    legenda = []
    for i, s in enumerate(scenarios):
        rij = {
            "Scenario": f"S{i + 1}", "Wat": " / ".join(s["labels"]),
            "Gewicht": _pct_txt(s["weight"]), "Modelkans": _pct_txt(s.get("model_prob")),
        }
        for r in range(n_rot):
            rij[f"Rotatie {r + 1}"] = _rotation_text_opp(s["boards"], r)
        legenda.append(rij)
    st.dataframe(legenda, use_container_width=True, hide_index=True)

    with st.expander("Waarom deze kansen? (model)", expanded=False):
        for i, s in enumerate(scenarios):
            st.markdown(f"**S{i + 1}** - {' / '.join(s['labels'])}: {redenen_per_scenario[i] or 'geen uitgesproken patroon'}")
    st.divider()
