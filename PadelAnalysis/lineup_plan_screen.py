"""
lineup_plan_screen.py - Planscherm voor een VOLLEDIGE ontmoeting (najaar:
2 rotaties x 2 matchen), aanpasbaar speler per speler.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PLAN_SCREEN_2026-10-03 (op verzoek van Kim: "ik vind het nogal
moeilijk om het overzicht te bewaren omdat je al een kaart moet kiezen voor
rotatie 1 en dan daarna voor rotatie 2 [...] Je stelt die beter samen voor
met dan meteen ook een eindresultaat van die keuze getoond. Zo zie je direct
de impact van je keuze." + "het zou handig zijn om daar meteen onze 4
spelers ook onder te kunnen zien [...] dan vervalt het kader met die zelf
samenstellen en wordt dat vervangen door een selectie zoals je ziet bij de
tegenstander" + "Bij de speler-per-speler-keuze voor de tegenstander wordt
de puntengrens niet gecontroleerd" + "Bij opofferen zou ik verwachten dat we
Kim en Carl zien omdat wij de minste" + Kim akkoord: "ok met het plan")
--------------------------------------------------------------------------
1. TEGENSTANDER: 8 speler-vakjes (R1/R2 x M1/M2 x 2). Snelkeuze-knoppen
   S1, S2, ... gebruiken EXACT de scenario's (en gewichten) van de
   scenario-analyse in de matchup-tabel (st.session_state
   "scen_matrix_scen_v3_<ploeg>") - S1 betekent dus overal hetzelfde.
   Welke tegenstander telt mee in het resultaat:
     - alle 8 vakjes ingevuld   -> exact die opstelling;
     - enkel rotatie 1 ingevuld -> hun rotatie 2 voorspeld door het model
                                   (zonder hun koppels uit rotatie 1);
     - anders                   -> gewogen over de scenario's S1..Sn.
2. ONZE PLOEG: 8 speler-vakjes. Knoppen "Beste plan", "Gespreid",
   "Opofferen", "Minstens 1 punt" vullen ze in; daarna kan je speler per
   speler aanpassen. Elke wijziging herrekent METEEN het eindresultaat
   (winst/gelijk/verlies voor de hele ontmoeting + winkans per match).
     - Beste plan     = meeste verwachte competitiepunten (2xP(winst)+P(gelijk));
     - Minstens 1 punt = hoogste kans op winst of gelijk;
     - Opofferen      = onze 2 ZWAKSTE spelers (padelstat, anders officieel
                        klassement) spelen samen 1 match, de rest zo sterk
                        mogelijk - beste plan binnen die voorwaarde;
     - Gespreid       = onze 2 zwakste spelers spelen NOOIT samen.
   Een vergelijkingstabel toont de 4 voorstellen naast elkaar.
3. CONTROLES (eigen ploeg EN tegenstander): elke speler max. 1x per
   rotatie, geen koppel 2x in de ontmoeting, puntengrens per rotatie
   (som van de 4 officiele klassementen) en art. 6.6 (sterkste duo op M1).
   Eigen ploeg ook: max. matchen per speler. Overtredingen staan in rood.
4. TIJDENS DE WEDSTRIJD: vink "Rotatie 1 is gespeeld" aan en kies de
   uitslag (2-0 / 1-1 / 0-2). Het resultaat rekent dan met die echte
   tussenstand, en de voorstel-knoppen optimaliseren enkel nog rotatie 2.
Bewust GEEN Streamlit-fragment: dit draait binnen het fragment van
_render_rotation_planner(); st.rerun(scope="fragment") herlaadt enkel dat.
"""
import streamlit as st
from dashboard_common import ll
from lineup_scout import _cached_official_rank, _cached_own_player_rating
from lineup_rotation import (
    _generate_rotation_candidates, _rank_pairs_with_padelstat_tiebreak, _norm_name,
    MATCHES_PER_ROTATION,
)
try:
    import opponent_lineup_model as olm
except Exception:  # noqa: BLE001  pragma: no cover
    olm = None

_N_ROT = 2
_R2_PRED_TOP = 6
_GEEN = "- Kies speler -"
_PRESETS = [
    ("best", "Beste plan", "meeste verwachte punten"),
    ("spread", "Gespreid", "onze 2 zwakste spelers nooit samen"),
    ("sacrifice", "Opofferen", "onze 2 zwakste spelers samen in 1 match"),
    ("safe", "Minstens 1 punt", "hoogste kans op winst of gelijk"),
]
_SLOTS = [(r, m, i) for r in range(_N_ROT) for m in range(MATCHES_PER_ROTATION) for i in range(2)]


# ---------------------------------------------------------------- rekenkern
def _wins_dist(a, b) -> list:
    a = 0.5 if a is None else a
    b = 0.5 if b is None else b
    return [(1 - a) * (1 - b), a * (1 - b) + b * (1 - a), a * b]


def _points(dists: list, offset: int = 0) -> dict:
    """Combineert winst-verdelingen per rotatie (elk [P0, P1, P2] gewonnen
    matchen) tot de kans op 2/1/0 competitiepunten. `offset` = al gewonnen
    matchen (rotatie 1 gespeeld)."""
    tot = {offset: 1.0}
    n_matches = 0
    for d in dists:
        nieuw = {}
        for k, pk in tot.items():
            for j, pj in enumerate(d):
                nieuw[k + j] = nieuw.get(k + j, 0.0) + pk * pj
        tot = nieuw
        n_matches += len(d) - 1
    half = n_matches / 2.0
    p2 = sum(p for k, p in tot.items() if k > half)
    p1 = sum(p for k, p in tot.items() if k == half)
    return {"p2": p2, "p1": p1, "p0": max(0.0, 1.0 - p2 - p1)}


def _score(kind: str, pp: dict) -> tuple:
    if kind == "safe":
        return (pp["p2"] + pp["p1"], pp["p2"])
    return (2 * pp["p2"] + pp["p1"], pp["p2"])


class _Ctx:
    """Alles wat de berekening nodig heeft, met een winkans-cache per
    (ons koppel, hun koppel)."""
    def __init__(self, player_ratings, official_ranks_strict, opponent_ratings, opp_ranks):
        self.pr = player_ratings or {}
        self.orank = official_ranks_strict or {}
        self.opr = opponent_ratings or {}
        self.opp_ranks = opp_ranks or {}
        self.cache = {}

    def strength(self, uid):
        return ll.effective_simulation_rating(uid, self.pr, self.orank)

    def wp(self, own_pair, opp_pair):
        key = (frozenset(own_pair), frozenset(opp_pair))
        if key not in self.cache:
            ours = [self.strength(u) for u in own_pair]
            theirs = []
            for u in opp_pair:
                r = self.opp_ranks.get(u)
                theirs.append(ll.effective_simulation_rating(
                    u, self.opr, {u: float(r) if r is not None else None}))
            ours = [v for v in ours if v is not None]
            theirs = [v for v in theirs if v is not None]
            self.cache[key] = ll.estimate_win_probability(
                sum(ours) / len(ours) if ours else None,
                sum(theirs) / len(theirs) if theirs else None,
            )
        return self.cache[key]

    def outcome(self, plan, opp_dist, played_k=None):
        """plan = [r1_pairs, r2_pairs]; opp_dist = [(r1_pairs, r2_pairs, w)].
        Met played_k telt rotatie 1 als gespeeld met k gewonnen matchen."""
        acc = {"p2": 0.0, "p1": 0.0, "p0": 0.0}
        tw = sum(w for *_, w in opp_dist) or 1.0
        for o1, o2, w in opp_dist:
            d2 = _wins_dist(self.wp(plan[1][0], o2[0]), self.wp(plan[1][1], o2[1]))
            if played_k is None:
                d1 = _wins_dist(self.wp(plan[0][0], o1[0]), self.wp(plan[0][1], o1[1]))
                pp = _points([d1, d2])
            else:
                pp = _points_with_offset(d2, played_k)
            for k in acc:
                acc[k] += (w / tw) * pp[k]
        return acc

    def match_wps(self, plan, opp_dist):
        tw = sum(w for *_, w in opp_dist) or 1.0
        out = []
        for r in range(_N_ROT):
            for m in range(MATCHES_PER_ROTATION):
                out.append(sum(
                    (w / tw) * (0.5 if (v := self.wp(plan[r][m], (o1 if r == 0 else o2)[m])) is None else v)
                    for o1, o2, w in opp_dist
                ))
        return out


def _points_with_offset(d2: list, k: int) -> dict:
    half = (MATCHES_PER_ROTATION * _N_ROT) / 2.0
    p2 = p1 = 0.0
    for j, pj in enumerate(d2):
        t = k + j
        if t > half:
            p2 += pj
        elif t == half:
            p1 += pj
    return {"p2": p2, "p1": p1, "p0": max(0.0, 1.0 - p2 - p1)}


def _own_plans(available_ids, synergy_fn, official_ranks_strict, player_ratings, opponent_ratings,
               rules, max_per_player, fixed_r1=None) -> list:
    """Alle reglementaire eigen plannen [r1, r2] (koppels in bordvolgorde)."""
    budget = {str(p): int((max_per_player or {}).get(p, _N_ROT) or 0) for p in available_ids}
    if fixed_r1 is not None:
        r1_opts = [fixed_r1]
    else:
        r1_raw, _, _ = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, set(), opponent_boards=None,
            player_ratings=player_ratings, opponent_ratings=opponent_ratings, max_results=100_000,
            tournament_rules_dict=rules, rotation_number=1, player_budget=budget,
        )
        r1_opts = [c["ordered_pairs"] for c in r1_raw]
    plans = []
    for r1 in r1_opts:
        b2 = dict(budget)
        for p in r1:
            for u in p:
                b2[str(u)] = b2.get(str(u), 0) - 1
        r2_raw, _, _ = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, {frozenset(p) for p in r1},
            opponent_boards=None, player_ratings=player_ratings, opponent_ratings=opponent_ratings,
            max_results=100_000, tournament_rules_dict=rules, rotation_number=2, player_budget=b2,
        )
        for c in r2_raw:
            plans.append([[frozenset(p) for p in r1], [frozenset(p) for p in c["ordered_pairs"]]])
    return plans


def _weakest_two(available_ids, ctx: _Ctx):
    sterk = [(ctx.strength(u), u) for u in available_ids]
    sterk = [x for x in sterk if x[0] is not None]
    if len(sterk) < 4:
        return None
    sterk.sort()
    return frozenset({sterk[0][1], sterk[1][1]})


def _pick_presets(plans, opp_dist, ctx, weakest, played_k=None) -> dict:
    out = {}
    scored = [(p, ctx.outcome(p, opp_dist, played_k)) for p in plans]
    for kind, _, _ in _PRESETS:
        if kind == "spread":
            pool = [x for x in scored if weakest and all(weakest != pr for rot in x[0] for pr in rot)]
        elif kind == "sacrifice":
            pool = [x for x in scored if weakest and any(weakest == pr for rot in x[0] for pr in rot)]
        else:
            pool = scored
        if not pool:
            continue
        sk = "safe" if kind == "safe" else "best"
        out[kind] = max(pool, key=lambda x: _score(sk, x[1]))
    return out


# ------------------------------------------------------------ tegenstander
def _opp_pairs_from_boards(boards):
    pairs = [frozenset(str(p.get("user_id")) for p in (b.get("opponent_pair") or []) if p.get("user_id"))
             for b in boards]
    if len(pairs) < _N_ROT * MATCHES_PER_ROTATION or any(len(p) != 2 for p in pairs):
        return None
    return [pairs[0:2], pairs[2:4]]


def _predict_r2(bundle, roster, r1, opp_ranks, opp_ps, rules):
    if olm is None:
        return []
    stats = olm.build_opponent_stats(bundle, MATCHES_PER_ROTATION)
    def _order(pairs):
        return _rank_pairs_with_padelstat_tiebreak(pairs, opp_ranks, opp_ps)
    pred = olm.predict_rotation_scenarios(
        stats, roster, _order, opp_ranks, rules=rules,
        excluded_pairs={frozenset(p) for p in r1}, top_n=_R2_PRED_TOP,
    )["scenarios"]
    return [([frozenset(p) for p in s["pairs"]], s["prob"]) for s in pred]


# ------------------------------------------------------------ controles
def _check_rotation(r_pairs, ranks, rules, wie: str, r_idx: int) -> list:
    fouten = []
    spelers = [u for p in r_pairs for u in p]
    if len(set(spelers)) != len(spelers):
        fouten.append(f"{wie} rotatie {r_idx + 1}: een speler staat 2x in dezelfde rotatie.")
    if rules is not None:
        waarden = [ranks.get(u) for u in set(spelers)]
        if all(v is not None for v in waarden):
            tot = sum(waarden)
            lo, hi = rules.get("punten_min"), rules.get("punten_max")
            if lo is not None and tot < lo or hi is not None and tot > hi:
                fouten.append(f"{wie} rotatie {r_idx + 1}: {tot:.0f} punten - buiten de puntengrens ({lo}-{hi}).")
        else:
            fouten.append(f"{wie} rotatie {r_idx + 1}: puntengrens niet controleerbaar (klassement onbekend).")
    if len(r_pairs) == 2:
        s1 = sum(ranks.get(u) or 0 for u in r_pairs[0])
        s2 = sum(ranks.get(u) or 0 for u in r_pairs[1])
        if s2 > s1:
            fouten.append(f"{wie} rotatie {r_idx + 1}: sterkste duo staat niet op M1 (art. 6.6: {s1:.0f} < {s2:.0f}).")
    return fouten


def _check_encounter(plan, ranks, rules, wie: str, max_per_player=None) -> list:
    fouten = []
    for r, rot in enumerate(plan):
        fouten += _check_rotation(rot, ranks, rules, wie, r)
    alle = [p for rot in plan for p in rot]
    if len(set(alle)) != len(alle):
        fouten.append(f"{wie}: een koppel speelt 2x samen in de ontmoeting.")
    if max_per_player:
        tel = {}
        for p in alle:
            for u in p:
                tel[u] = tel.get(u, 0) + 1
        for u, n in tel.items():
            if n > int(max_per_player.get(u, _N_ROT) or 0):
                fouten.append(f"{wie}: een speler speelt {n} matchen (max. {max_per_player.get(u)}).")
    return fouten


# ------------------------------------------------------------ weergave
def _impact_md(pp: dict, prefix="Ontmoeting") -> str:
    return (f"### {prefix}: :green[{pp['p2'] * 100:.0f}% winst] · :orange[{pp['p1'] * 100:.0f}% gelijk] · "
            f":red[{pp['p0'] * 100:.0f}% verlies]")


def _plan_txt(plan, names) -> str:
    return "  |  ".join(
        f"R{r + 1}: " + " · ".join(" / ".join(names.get(u, u) for u in sorted(p)) for p in rot)
        for r, rot in enumerate(plan)
    )


def _slot_widgets(prefix: str, uids: list, label_of: dict, titel: str, opp_excl_r2=True):
    """8 selectboxes. Geeft {(r,m,i): uid} terug."""
    uid_of = {v: k for k, v in label_of.items()}
    gekozen = {}
    for slot in _SLOTS:
        v = st.session_state.get(f"{prefix}_{slot[0]}{slot[1]}{slot[2]}")
        if v in uid_of:
            gekozen[slot] = uid_of[v]
    st.markdown(f"**{titel}**")
    for r in range(_N_ROT):
        cols = st.columns(4)
        r1_pairs = set()
        if r == 1 and opp_excl_r2:
            for m in range(MATCHES_PER_ROTATION):
                a, b = gekozen.get((0, m, 0)), gekozen.get((0, m, 1))
                if a and b:
                    r1_pairs.add(frozenset({a, b}))
        for c_idx, (m, i) in enumerate([(m, i) for m in range(MATCHES_PER_ROTATION) for i in range(2)]):
            slot = (r, m, i)
            key = f"{prefix}_{r}{m}{i}"
            elders = {u for s_, u in gekozen.items() if s_ != slot and s_[0] == r}
            partner = gekozen.get((r, m, 1 - i))
            opties = [_GEEN] + [
                label_of[u] for u in uids
                if u not in elders and not (partner and frozenset({u, partner}) in r1_pairs)
            ]
            if st.session_state.get(key) not in opties:
                st.session_state[key] = _GEEN
            with cols[c_idx]:
                keuze = st.selectbox(f"R{r + 1} M{m + 1} - speler {i + 1}", opties, key=key)
            if keuze != _GEEN:
                gekozen[slot] = uid_of[keuze]
            else:
                gekozen.pop(slot, None)
    return gekozen


def _slots_to_plan(gekozen: dict, rotations=range(_N_ROT)):
    plan = []
    for r in rotations:
        rot = []
        for m in range(MATCHES_PER_ROTATION):
            a, b = gekozen.get((r, m, 0)), gekozen.get((r, m, 1))
            if not (a and b):
                return None
            rot.append(frozenset({a, b}))
        plan.append(rot)
    return plan


def _fill(prefix: str, plan, label_of: dict, rotations=range(_N_ROT)) -> bool:
    waarden = {}
    for r in rotations:
        for m in range(MATCHES_PER_ROTATION):
            pair = sorted(plan[r][m], key=lambda u: label_of.get(u, u))
            for i in range(2):
                if pair[i] not in label_of:
                    return False
                waarden[f"{prefix}_{r}{m}{i}"] = label_of[pair[i]]
    st.session_state.update(waarden)
    return True


def render_plan_screen(
    available_ids, synergy_fn, official_ranks_strict, name_lookup_global, ploeg_id,
    player_ratings, opponent_ratings, tournament_rules_dict, max_per_player,
    bundle, unique_opp_players,
) -> None:
    rules = tournament_rules_dict
    roster_uids = [str(p.get("user_id")) for p in unique_opp_players if p.get("user_id")]
    opp_ranks = {u: _cached_official_rank(u) for u in roster_uids}
    opp_ps = {u: v for u in roster_uids if (v := _cached_own_player_rating(u)) is not None}
    ctx = _Ctx(player_ratings, official_ranks_strict, opponent_ratings, opp_ranks)

    def _lbl(naam, rk, ps):
        info = " · ".join(x for x in [f"P{int(rk)}" if rk is not None else "P?",
                                      f"ps {int(ps)}" if ps is not None else ""] if x)
        return f"{naam} ({info})"
    opp_names = {str(p.get("user_id")): p.get("name", "?") for p in unique_opp_players if p.get("user_id")}
    opp_label = {u: _lbl(opp_names[u], opp_ranks.get(u), opp_ps.get(u)) for u in roster_uids}
    own_label = {u: _lbl(name_lookup_global.get(u, u), official_ranks_strict.get(u), (player_ratings or {}).get(u))
                 for u in available_ids}
    names_all = {**{u: name_lookup_global.get(u, u) for u in available_ids}, **opp_names}

    # ---- scenario's: EXACT die van de scenario-analyse (zelfde S1, zelfde gewicht)
    naam_naar_uid = {_norm_name(n): u for u, n in opp_names.items()}
    def _to_uid(p):
        u = str(p.get("user_id") or "")
        return u if u in opp_names else naam_naar_uid.get(_norm_name(p.get("name")))
    scen = []
    for i, s in enumerate(st.session_state.get(f"scen_matrix_scen_v3_{ploeg_id}") or []):
        boards = [{"opponent_pair": [{"user_id": _to_uid(p)} for p in (b.get("opponent_pair") or [])]}
                  for b in s.get("boards") or []]
        pairs = _opp_pairs_from_boards(boards)
        if pairs:
            scen.append({"name": f"S{i + 1}", "labels": s.get("labels") or [], "pairs": pairs, "w": s["weight"]})

    st.markdown('<div class="section-header">Plan voor de volledige ontmoeting</div>', unsafe_allow_html=True)
    st.caption(
        "Stel hieronder beide rotaties samen - voor de tegenstander en voor ons - speler per speler. "
        "Het eindresultaat onderaan wordt bij elke wijziging meteen herrekend. Gebruik de knoppen als "
        "vertrekpunt en pas daarna zelf aan."
    )

    # ---- tegenstander
    opp_prefix = f"plan_opp_v1_{ploeg_id}"
    if scen:
        st.markdown("**Tegenstander - snelkeuze** (zelfde scenario's en gewichten als de scenario-analyse hierboven)")
        knop_cols = st.columns(min(len(scen), 5))
        for i, s in enumerate(scen):
            with knop_cols[i % len(knop_cols)]:
                if st.button(f"{s['name']} · {s['w'] * 100:.0f}%", key=f"{opp_prefix}_use_{i}",
                             help=" / ".join(s["labels"]) + " - " + _plan_txt(s["pairs"], names_all),
                             use_container_width=True):
                    if _fill(opp_prefix, s["pairs"], opp_label):
                        st.rerun(scope="fragment")
                    st.warning("Een speler van dit scenario zit niet in de tegenstander-selectie.")
    else:
        st.caption("Nog geen scenario's van de scenario-analyse beschikbaar - vul de tegenstander zelf in.")
    volgorde = sorted(roster_uids, key=lambda u: -(opp_ranks.get(u) or 0))
    opp_sel = _slot_widgets(opp_prefix, volgorde, opp_label, "Tegenstander")
    opp_plan = _slots_to_plan(opp_sel)
    opp_r1 = _slots_to_plan(opp_sel, rotations=[0])
    if opp_plan is not None:
        opp_dist = [(opp_plan[0], opp_plan[1], 1.0)]
        opp_bron = "de ingevulde tegenstander-opstelling"
    elif opp_r1 is not None:
        r2_pred = _predict_r2(bundle, unique_opp_players, opp_r1[0], opp_ranks, opp_ps, rules)
        opp_dist = [(opp_r1[0], p, w) for p, w in r2_pred] or []
        opp_bron = "hun ingevulde rotatie 1 + voorspelde rotatie 2"
    else:
        opp_dist = [(s["pairs"][0], s["pairs"][1], s["w"]) for s in scen]
        opp_bron = f"gewogen over de scenario's S1-S{len(scen)}" if scen else ""
    opp_fouten = _check_encounter(opp_plan, opp_ranks, rules, "Tegenstander") if opp_plan else (
        _check_rotation(opp_r1[0], opp_ranks, rules, "Tegenstander", 0) if opp_r1 else [])
    for f in opp_fouten:
        st.markdown(f":red[{f}]")
    if not opp_dist:
        st.info("Kies een scenario of vul de tegenstander in om het resultaat te zien.")
        return

    # ---- rotatie 1 gespeeld?
    played_k = None
    c_g, c_u = st.columns([1, 2])
    with c_g:
        gespeeld = st.checkbox("Rotatie 1 is gespeeld", key=f"plan_r1_played_{ploeg_id}")
    if gespeeld:
        with c_u:
            uitslag = st.radio("Uitslag rotatie 1 (voor ons)", ["2-0", "1-1", "0-2"], horizontal=True,
                               key=f"plan_r1_score_{ploeg_id}")
        played_k = {"2-0": 2, "1-1": 1, "0-2": 0}[uitslag]

    # ---- eigen plannen + voorstellen
    own_prefix = f"plan_own_v1_{ploeg_id}"
    own_sel_now = {}
    for slot in _SLOTS:
        v = st.session_state.get(f"{own_prefix}_{slot[0]}{slot[1]}{slot[2]}")
        u = next((k for k, lab in own_label.items() if lab == v), None)
        if u:
            own_sel_now[slot] = u
    fixed_r1 = None
    if played_k is not None:
        r1 = _slots_to_plan(own_sel_now, rotations=[0])
        if r1 is None:
            st.warning("Vul eerst onze rotatie 1 in (wie speelde), dan wordt enkel rotatie 2 geoptimaliseerd.")
            return
        fixed_r1 = r1[0]
    sig = (tuple(sorted(available_ids)), tuple(sorted((max_per_player or {}).items())),
           tuple(sorted(official_ranks_strict.items())), tuple(sorted((player_ratings or {}).items())),
           tuple(sorted(rules.items())) if rules else None,
           tuple(tuple(p) for p in fixed_r1) if fixed_r1 else None)
    pk = f"plan_own_plans_v1_{ploeg_id}"
    if st.session_state.get(pk + "_sig") != sig:
        st.session_state[pk] = _own_plans(available_ids, synergy_fn, official_ranks_strict, player_ratings,
                                          opponent_ratings, rules, max_per_player, fixed_r1=fixed_r1)
        st.session_state[pk + "_sig"] = sig
    plans = st.session_state[pk]
    if not plans:
        st.warning("Geen reglementair geldig plan mogelijk met de huidige spelers, matchen per speler en puntengrens.")
        return
    weakest = _weakest_two(available_ids, ctx)
    presets = _pick_presets(plans, opp_dist, ctx, weakest, played_k)

    st.markdown("**Onze ploeg - voorstellen**" + (" (enkel rotatie 2, rotatie 1 is gespeeld)" if played_k is not None else ""))
    if weakest:
        st.caption("Onze 2 zwakste spelers (padelstat, anders klassement): "
                   + " en ".join(name_lookup_global.get(u, u) for u in sorted(weakest)) + f". Tegenstander: {opp_bron}.")
    knop_cols = st.columns(len(_PRESETS))
    vergelijk = []
    for col, (kind, titel, uitleg) in zip(knop_cols, _PRESETS):
        with col:
            if kind not in presets:
                st.button(titel, key=f"{own_prefix}_p_{kind}", disabled=True, use_container_width=True,
                          help="Geen geldig plan voor deze voorwaarde.")
                continue
            plan, pp = presets[kind]
            if st.button(f"{titel} · {pp['p2'] * 100:.0f}% winst", key=f"{own_prefix}_p_{kind}",
                         help=uitleg, use_container_width=True):
                rots = [1] if played_k is not None else range(_N_ROT)
                _fill(own_prefix, plan, own_label, rotations=rots)
                st.rerun(scope="fragment")
            vergelijk.append({
                "Voorstel": titel, "Plan": _plan_txt(plan, names_all),
                "Winst": f"{pp['p2'] * 100:.0f}%", "Gelijk": f"{pp['p1'] * 100:.0f}%",
                "Verlies": f"{pp['p0'] * 100:.0f}%", "Min. 1 punt": f"{(pp['p2'] + pp['p1']) * 100:.0f}%",
            })
    with st.expander("Vergelijk de voorstellen", expanded=False):
        st.dataframe(vergelijk, use_container_width=True, hide_index=True)

    own_volgorde = sorted(available_ids, key=lambda u: -(ctx.strength(u) or 0))
    own_sel = _slot_widgets(own_prefix, own_volgorde, own_label, "Onze ploeg")
    own_plan = _slots_to_plan(own_sel)
    if own_plan is None:
        st.info("Vul alle 8 vakjes van onze ploeg in (of klik een voorstel) om het eindresultaat te zien.")
        return
    for f in _check_encounter(own_plan, official_ranks_strict, rules, "Onze ploeg", max_per_player):
        st.markdown(f":red[{f}]")

    # ---- eindresultaat
    pp = ctx.outcome(own_plan, opp_dist, played_k)
    st.markdown(_impact_md(pp))
    wps = ctx.match_wps(own_plan, opp_dist)
    ev = sum(wps[2:]) + (played_k if played_k is not None else sum(wps[:2]))
    st.markdown(f"Verwacht **{ev:.1f}** gewonnen matchen op 4 · tegenstander: {opp_bron}.")
    regels = []
    for r in range(_N_ROT):
        for m in range(MATCHES_PER_ROTATION):
            ons = " / ".join(names_all.get(u, u) for u in sorted(own_plan[r][m]))
            if opp_plan is not None or (r == 0 and opp_r1 is not None):
                bron = opp_plan if opp_plan is not None else opp_r1
                tegen = " tegen " + " / ".join(names_all.get(u, u) for u in sorted(bron[r][m]))
            else:
                tegen = " (gemiddeld over de scenario's)"
            if r == 0 and played_k is not None:
                regels.append(f"R1 M{m + 1}: **{ons}**{tegen} - gespeeld")
            else:
                regels.append(f"R{r + 1} M{m + 1}: **{ons}**{tegen} - **{wps[r * 2 + m] * 100:.0f}%** winkans")
    st.markdown("  \n".join(regels))
