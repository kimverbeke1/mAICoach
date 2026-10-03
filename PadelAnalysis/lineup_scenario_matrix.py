"""
lineup_scenario_matrix.py - "Wat als de tegenstander ...?": een kleine
scenario-matrix i.p.v. honderden matchups of 1 uitgevlakt gemiddelde.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_2026-10-03 (op verzoek van Kim: "gewoon
overal hetzelfde gemiddelde zien is ook niet zinvol. Dus specifieke cases
zijn wel interessant. Wat als ze spelen zoals in vorige matchen (meerdere),
wat als ze hun beste spelers in match 1 van rotatie 1 zetten etc." + "We
nemen bvb risico om hem toch te proberen te kloppen en 3-1 of 4-0 te
winnen. of we gaan voor de veilige optie om maximum 2-2 te halen door
slechtere spelers tegen die goeie te laten uitkomen")
--------------------------------------------------------------------------
WAAROM: de groepen in "Onze opstellingen" middelen elke eigen opstelling
over (honderden) tegenstander-opstellingen. Daardoor komen alle eigen
opstellingen op bijna dezelfde kans uit, en verdwijnt net wat interessant
is: hoe goed een opstelling het doet tegen EEN SPECIFIEKE, plausibele
tegenstander-opstelling.

WAT DIT BESTAND DOET (volledige ontmoeting, alle rotaties samen):
  1. KOLOMMEN = een handvol BENOEMDE tegenstander-scenario's:
       - "Zoals op <datum>": elke opstelling die ze effectief speelden;
       - "Meest waarschijnlijk": de top van het statistisch model
         (opponent_lineup_model: deelname, vaste koppels, Match 1/2-voorkeur);
       - "Sterkste duo op R1M1" en "Sterkste duo in rotatie 2": hun sterkste
         koppel (gemiddelde speelsterkte) vooraan, resp. gespaard;
       - "Zonder <sterkste speler>": als hun beste speler niet meespeelt.
     Telkens de waarschijnlijkste volledige opstelling die aan die
     voorwaarde voldoet. Identieke opstellingen worden samengevoegd.
  2. RIJEN = eigen strategieen:
       - Aanvallend: hoogste (gewogen) kans op 2 punten (3-1/4-0);
       - Veilig: hoogste (gewogen) kans op minstens 1 punt (= desnoods
         opofferen voor een 2-2);
       - Robuust: hoogste kans op minstens 1 punt in het SLECHTSTE scenario;
       - Counter op <scenario>: de beste opstelling tegen precies dat ene
         scenario.
     Dezelfde eigen opstelling onder meerdere labels = 1 rij.
  3. CELLEN = exacte kans (geen gemiddelde over andere scenario's) op
     winst / minstens 1 punt / verlies, te kiezen via een schakelaar.
  4. DETAIL per (strategie, scenario): wie tegen wie, winkans per match,
     en welke match een bewuste opoffermatch is.

Gewicht per scenario (voor Aanvallend/Veilig en kolom "Gewogen") = de
modelkans, hernormaliseerd over de getoonde scenario's. Zonder model:
1 + aantal keer effectief gespeeld (lineup_rotation._opponent_lineup_weight).

Rekent op dezelfde functies als de rest van de app (_compute_matchup,
reglementaire eigen opstellingen via _enumerate_own_variant_combinations),
dus de cijfers zijn consistent met de matchup-tabel en de rotatieplanner.
"""
import streamlit as st

from dashboard_common import ll, _parse_match_date
from lineup_rotation import (
    _enumerate_rotation_aware_pairings, _enumerate_own_variant_combinations,
    _compute_matchup, _opponent_lineup_weight, MATCHES_PER_ROTATION,
)

_MAX_SCENARIOS = 8
_SACRIFICE_WP = 0.30  # winkans onder deze grens = "opoffermatch"
_METRICS = {
    "Kans op winst (2 punten)": "p2",
    "Kans op minstens 1 punt": "p_ge1",
    "Kans op verlies (0 punten)": "p0",
}


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
    return " · ".join(delen)


def _lineup_text_own(pairs: list, name_lookup: dict) -> str:
    delen = []
    for idx, pair in enumerate(pairs):
        namen = "/".join(name_lookup.get(u, u) for u in sorted(pair))
        delen.append(f"R{idx // MATCHES_PER_ROTATION + 1}M{idx % MATCHES_PER_ROTATION + 1} {namen}")
    return " · ".join(delen)


def _date_key(label: str):
    try:
        d = _parse_match_date(label)
    except Exception:  # noqa: BLE001
        d = None
    return d or (0, 0, 0)


# ----------------------------------------------------- tegenstander-scenario's
def build_opponent_scenarios(
    unique_opponent_lineups: dict, model_weights: dict, opponent_ratings: dict, total_boards: int,
) -> list:
    """Kiest de benoemde tegenstander-scenario's. Geeft een lijst van
    {"key", "boards", "labels": [..], "weight"} terug (max _MAX_SCENARIOS)."""
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

    # 1. effectief gespeeld, meest recent eerst
    hist = [k for k, v in items.items() if v.get("is_historical")]
    hist.sort(key=lambda k: max(_date_key(l) for l in items[k]["historical_labels"]), reverse=True)
    for k in hist:
        _voeg_toe(k, "Zoals op " + ", ".join(items[k]["historical_labels"]))

    # 2. meest waarschijnlijk volgens het model
    if model_weights:
        _voeg_toe(max(items, key=_w), "Meest waarschijnlijk (model)")

    # sterkste duo / speler over alle opstellingen heen
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
        s["weight"] = _w(s["key"]) / tot
    return out


# ------------------------------------------------------------ eigen opties
def build_own_options(available_ids, max_per_player, official_ranks_strict, player_ratings, rules) -> list:
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
    """cells[o][s] = {"p2","p1","p0","p_ge1","assignment","ebw"}."""
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
    """[(label, own_index)] - ontdubbeld op eigen opstelling (labels samengevoegd)."""
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
    for s_idx, scen in enumerate(scenarios):
        keuzes.append((
            f"Counter op S{s_idx + 1}",
            max(idx, key=lambda o: (cells[o][s_idx]["p2"], cells[o][s_idx]["p_ge1"])),
        ))
    rijen: dict = {}
    for label, o in keuzes:
        rijen.setdefault(o, []).append(label)
    return [(" + ".join(labels), o) for o, labels in rijen.items()]


# ------------------------------------------------------------ weergave
def render_scenario_matrix(
    unique_opponent_lineups: dict, model_weights: dict, available_ids: list, max_per_player: dict,
    total_boards: int, synergy_fn, player_ratings: dict, official_ranks_strict: dict,
    opponent_ratings: dict, tournament_rules_dict, name_lookup_global: dict, ploeg_key: str,
) -> None:
    st.markdown(
        '<div class="section-header">Scenario-analyse: wat als de tegenstander ...?</div>',
        unsafe_allow_html=True,
    )
    scenarios = build_opponent_scenarios(
        unique_opponent_lineups, model_weights, opponent_ratings, total_boards,
    )
    if not scenarios:
        st.info("Nog geen tegenstander-opstellingen in dit formaat om scenario's mee te bouwen.")
        return

    sig = (
        tuple(s["key"] for s in scenarios), tuple(round(s["weight"], 4) for s in scenarios),
        tuple(sorted(available_ids)), tuple(sorted(max_per_player.items())),
        tuple(sorted((player_ratings or {}).items())), tuple(sorted(official_ranks_strict.items())),
        tuple(sorted((opponent_ratings or {}).items())),
        tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
    )
    cache_key, sig_key = f"scen_matrix_v1_{ploeg_key}", f"scen_matrix_sig_v1_{ploeg_key}"
    if st.session_state.get(sig_key) != sig:
        own_options = build_own_options(
            available_ids, max_per_player, official_ranks_strict, player_ratings, tournament_rules_dict,
        )
        cells = compute_matrix(
            scenarios, own_options, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings,
        )
        st.session_state[cache_key] = (own_options, cells)
        st.session_state[sig_key] = sig
    own_options, cells = st.session_state[cache_key]
    if not own_options:
        st.info("Geen reglementair geldige eigen opstelling met de huidige spelers en matchen per speler.")
        return

    st.caption(
        "Elke kolom is EEN concrete opstelling van de tegenstander (geen gemiddelde). Elke rij is een "
        "eigen opstelling, gekozen volgens een strategie. 'Aanvallend' zoekt de hoogste kans op 3-1/4-0; "
        "'Veilig' de hoogste kans op minstens 2-2 (desnoods een zwakker koppel opofferen tegen hun "
        "sterkste); 'Robuust' houdt het best stand in het slechtste scenario; 'Counter op Sx' is de beste "
        "opstelling als je zeker weet dat ze scenario Sx spelen. 'Gewogen' weegt de scenario's met hun "
        "kans hieronder."
    )

    legenda = [{
        "Kolom": f"S{i + 1}", "Scenario": " / ".join(s["labels"]),
        "Kans": round(s["weight"] * 100, 0), "Hun opstelling": _lineup_text_opp(s["boards"]),
    } for i, s in enumerate(scenarios)]
    st.dataframe(
        legenda, use_container_width=True, hide_index=True,
        column_config={"Kans": st.column_config.NumberColumn("Kans", format="%.0f%%", width="small")},
    )

    metric_label = st.radio(
        "Toon in de matrix", list(_METRICS), horizontal=True, key=f"scen_matrix_metric_{ploeg_key}",
    )
    mk = _METRICS[metric_label]
    strategies = pick_strategies(scenarios, cells)
    w = [s["weight"] for s in scenarios]
    rows = []
    for label, o in strategies:
        rij = {"Strategie": label, "Onze opstelling": _lineup_text_own(own_options[o], name_lookup_global)}
        for s_idx in range(len(scenarios)):
            rij[f"S{s_idx + 1}"] = round(cells[o][s_idx][mk] * 100, 0)
        rij["Gewogen"] = round(sum(wi * c[mk] for wi, c in zip(w, cells[o])) * 100, 0)
        rows.append(rij)
    num_cols = [f"S{i + 1}" for i in range(len(scenarios))] + ["Gewogen"]
    try:
        import pandas as _pd
        df = _pd.DataFrame(rows)
        cmap = "RdYlGn_r" if mk == "p0" else "RdYlGn"
        styled = df.style.background_gradient(subset=num_cols, cmap=cmap, vmin=0, vmax=100).format(
            {c: "{:.0f}%" for c in num_cols}
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:  # noqa: BLE001
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("Detail: wie tegen wie in een strategie x scenario", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            r_sel = st.selectbox(
                "Strategie", list(range(len(strategies))), format_func=lambda i: strategies[i][0],
                key=f"scen_matrix_det_row_{ploeg_key}",
            )
        with c2:
            s_sel = st.selectbox(
                "Scenario", list(range(len(scenarios))),
                format_func=lambda i: f"S{i + 1} - {' / '.join(scenarios[i]['labels'])}",
                key=f"scen_matrix_det_col_{ploeg_key}",
            )
        cel = cells[strategies[r_sel][1]][s_sel]
        st.markdown(
            f"**Ontmoeting:** :green[**{cel['p2'] * 100:.0f}% winst**] · "
            f":orange[**{cel['p1'] * 100:.0f}% gelijk**] · :red[**{cel['p0'] * 100:.0f}% verlies**] "
            f"(verwacht {cel['ebw']:.2f} gewonnen matchen)"
        )
        for idx, a in enumerate(cel["assignment"]):
            ons = " / ".join(name_lookup_global.get(u, u) for u in a["our_pair"])
            tegen = " / ".join(p.get("name", "?") for p in a["opponent_board"].get("opponent_pair") or [])
            wp = a.get("win_probability")
            wp_txt = f"{wp * 100:.0f}% winkans" if wp is not None else "winkans onbekend"
            offer = (
                " - :red[opoffermatch]"
                if wp is not None and wp < _SACRIFICE_WP and cel["p_ge1"] >= 0.5 else ""
            )
            st.write(
                f"R{idx // MATCHES_PER_ROTATION + 1}M{idx % MATCHES_PER_ROTATION + 1}: "
                f"**{ons}** tegen **{tegen}** - {wp_txt}{offer}"
            )
    st.divider()
