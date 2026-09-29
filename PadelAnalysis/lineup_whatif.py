"""
lineup_whatif.py - "Wat als"-vergelijking: de winkans van JOUZELF op EEN
gekozen bordpositie (bv. "match 2 van elke rotatie"), met 2 partnerkeuzes
naast elkaar vergeleken.

--------------------------------------------------------------------------
PADEL_ANALYSIS_WHATIF_PARTNER_COMPARE_2026-09-29 (op verzoek van Kim: "stel
dat ik met Nico en Joris mijn 2 matchen speel in de 2de match van elke
rotatie. wat zijn dan mijn winstkansen. Hoger dan met Carl?" - de AI kende
op dat moment de eigen spelers niet en kon dit niet berekenen)
--------------------------------------------------------------------------
PROBLEEM: de bestaande matchup-tabel (lineup_matchup_table.py) beantwoordt
een ANDERE vraag - "wat is de beste volledige ploegopstelling" - en werkt
op ALLE 4-6 spelers tegelijk. Een gerichte vraag als "wat als IK met partner
X speel op positie Y" was daar niet apart uit te lezen zonder door
honderden rijen te scrollen. De AI-chat (team_ai_advisor.py) kende dan weer
de eigen spelers helemaal niet, dus kon zelfs geen educated guess geven.

FIX: dit bestand berekent de winkans EXACT (dezelfde formule als de rest
van de app: ll.effective_simulation_rating + ll.estimate_win_probability -
GEEN AI, GEEN educated guess) voor een specifiek (partner, bordpositie)-
paar, tegen ALLE historisch gekende tegenstander-opstellingen op die
positie - en toont 2 keuzes naast elkaar.

BRON VAN DE TEGENSTANDER-STERKTE OP DIE POSITIE (in volgorde van voorkeur):
  1. Alle historische tegenstander-opstellingen van DIT seizoen, exact op
     deze bordpositie (rotatie x match-nummer) - de meest betrouwbare bron.
  2. Ontbreekt dat (bv. eerste keer tegen deze tegenstander, of nog geen
     historiek op precies deze positie), dan ALLE gekende tegenstander-
     opstellingen ongeacht positie - duidelijk gelabeld als bredere schatting.
  3. Is er HELEMAAL geen boards-historiek, dan het gemiddelde van alle
     gekende tegenstander-spelers - duidelijk gelabeld als ruwe schatting.
Bij elke stap wordt expliciet getoond welke bron gebruikt is en hoeveel
waarnemingen erachter zitten, zodat "3% verschil op 1 waarneming" niet als
harde zekerheid overkomt.

BEWUST NIET GEDAAN: deze tool verifieert NIET of de gekozen partnercombinatie
voor de VOLLEDIGE ontmoeting reglementair geldig is (puntengrens per
rotatie, geen dubbele koppels) - dat blijft de taak van de matchup-tabel en
de rotatieplanner hierboven. Dit is bewust een snel, geïsoleerd "wat als"-
instrument voor de vraag "hoe gevoelig is MIJN winkans voor mijn
partnerkeuze op deze ene positie", niet een vervanging van de volledige
ploeg-optimalisatie.
"""

import streamlit as st

from dashboard_common import ll
from lineup_rotation import (
    MATCHES_PER_ROTATION, ROTATIONS_PER_ENCOUNTER, _WIN_PROB_DISCLAIMER,
    _historical_opponent_boards_list,
)

_GEEN_KEUZE = "- Kies partner -"
_DUIDELIJK_VERSCHIL_PP = 3.0  # percentagepunten - onder deze grens: "gelijkwaardig"


def _boards_at_slot(historical_boards_with_labels: list, slot_index: int) -> list:
    """(label, board)-paren op EXACT deze 0-based bordpositie, over alle
    historische tegenstander-opstellingen heen."""
    out = []
    for label, boards in historical_boards_with_labels:
        sorted_boards = sorted(boards, key=lambda b: b.get("board_position") or 0)
        if slot_index < len(sorted_boards):
            out.append((label, sorted_boards[slot_index]))
    return out


def _all_known_opponent_boards(historical_boards_with_labels: list) -> list:
    out = []
    for label, boards in historical_boards_with_labels:
        for b in boards:
            out.append((label, b))
    return out


def _win_prob_for_pair_vs_board(
    pair: tuple, board: dict, player_ratings: dict, official_ranks_strict: dict,
    opponent_ratings: dict,
):
    p1, p2 = pair
    our_eff = [
        ll.effective_simulation_rating(p1, player_ratings, official_ranks_strict),
        ll.effective_simulation_rating(p2, player_ratings, official_ranks_strict),
    ]
    opp_pair = board.get("opponent_pair", []) or []
    their_eff = [
        ll.effective_simulation_rating(
            p.get("user_id"), opponent_ratings,
            {p.get("user_id"): ll.parse_ranking(p.get("ranking"))},
        )
        for p in opp_pair
    ]
    our_known = [v for v in our_eff if v is not None]
    their_known = [v for v in their_eff if v is not None]
    our_avg = (sum(our_known) / len(our_known)) if our_known else None
    their_avg = (sum(their_known) / len(their_known)) if their_known else None
    return ll.estimate_win_probability(our_avg, their_avg)


def _estimate_slot_win_probability(
    pair: tuple, slot_index: int, bundle: dict,
    player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
) -> tuple:
    """Geeft (gemiddelde winkans of None, n_waarnemingen, bron-omschrijving)
    terug voor `pair` op bordpositie `slot_index` (0-based). Zie de
    moduledocstring voor de volgorde van fallback-bronnen."""
    historical = _historical_opponent_boards_list(bundle)

    exact = _boards_at_slot(historical, slot_index)
    if exact:
        probs = [
            _win_prob_for_pair_vs_board(pair, b, player_ratings, official_ranks_strict, opponent_ratings)
            for _, b in exact
        ]
        probs = [p for p in probs if p is not None]
        if probs:
            return sum(probs) / len(probs), len(probs), "exact deze bordpositie, dit seizoen"

    alle = _all_known_opponent_boards(historical)
    if alle:
        probs = [
            _win_prob_for_pair_vs_board(pair, b, player_ratings, official_ranks_strict, opponent_ratings)
            for _, b in alle
        ]
        probs = [p for p in probs if p is not None]
        if probs:
            return sum(probs) / len(probs), len(probs), "alle gekende tegenstander-opstellingen (niet specifiek deze positie)"

    unique_players = bundle.get("unique_players", []) or []
    if unique_players:
        opp_ids = [p.get("user_id") for p in unique_players if p.get("user_id")]
        # Terugval-official-rank per tegenstander uit hun eigen "ranking"-veld
        # (bv. "P250"), zodat een tegenstander zonder padelstat-rating hier
        # niet stilzwijgend als "onbekend" telt - zelfde bron als elders in
        # de app (board.get("opponent_pair")[i].get("ranking")).
        opp_official = {
            str(p.get("user_id")): ll.parse_ranking(p.get("ranking"))
            for p in unique_players if p.get("user_id")
        }
        ratings = [
            r for r in (
                ll.effective_simulation_rating(pid, opponent_ratings, opp_official) for pid in opp_ids
            ) if r is not None
        ]
        if ratings:
            gem_opp = sum(ratings) / len(ratings)
            our_eff = [
                ll.effective_simulation_rating(pair[0], player_ratings, official_ranks_strict),
                ll.effective_simulation_rating(pair[1], player_ratings, official_ranks_strict),
            ]
            our_known = [v for v in our_eff if v is not None]
            our_avg = (sum(our_known) / len(our_known)) if our_known else None
            p = ll.estimate_win_probability(our_avg, gem_opp)
            if p is not None:
                return p, 0, "ruwe schatting o.b.v. gemiddelde sterkte van alle gekende tegenstander-spelers (geen specifieke opstelling)"

    return None, 0, "onbekend - onvoldoende data (nog geen tegenstander-spelers of ratings gekend)"


def _slot_label(rotation: int, match_in_rotation: int) -> str:
    return f"Rotatie {rotation} - Match {match_in_rotation}"


def _render_option_column(
    col, titel: str, key_prefix: str, slots: list, partner_options: list,
    partner_label_to_id: dict, sel_player_id: str, sel_label: str,
    bundle: dict, player_ratings: dict, official_ranks_strict: dict,
    opponent_ratings: dict, synergy_fn,
) -> dict:
    """Tekent de partnerkeuze-selectboxen voor 1 optie (A of B) en geeft de
    berekende resultaten terug: {"per_slot": [...], "gemiddeld": float|None,
    "totaal_verwacht": float|None, "duplicaat": bool}."""
    with col:
        st.markdown(f"**{titel}**")
        gekozen_partners = []
        for i, (rotatie, match_in_rotatie) in enumerate(slots):
            key = f"whatif_{key_prefix}_partner_{i}"
            label = st.selectbox(
                _slot_label(rotatie, match_in_rotatie), [_GEEN_KEUZE] + partner_options,
                key=key,
            )
            gekozen_partners.append(None if label == _GEEN_KEUZE else partner_label_to_id.get(label))

        duplicaat = False
        gekend = set()
        for pid in gekozen_partners:
            if pid is None:
                continue
            if pid in gekend:
                duplicaat = True
            gekend.add(pid)
        if duplicaat:
            st.error(
                "Dezelfde partner staat hier 2x gekozen - een koppel mag reglementair niet 2x "
                "samen spelen. Kies voor minstens 1 rotatie een andere partner."
            )

        per_slot = []
        for (rotatie, match_in_rotatie), partner_id in zip(slots, gekozen_partners):
            if partner_id is None:
                per_slot.append(None)
                continue
            slot_index = (rotatie - 1) * MATCHES_PER_ROTATION + (match_in_rotatie - 1)
            pair = (str(sel_player_id), str(partner_id))
            kans, n_obs, bron = _estimate_slot_win_probability(
                pair, slot_index, bundle, player_ratings, official_ranks_strict, opponent_ratings,
            )
            syn = None
            try:
                syn = synergy_fn(str(sel_player_id), str(partner_id))
            except Exception:  # noqa: BLE001
                pass
            per_slot.append({
                "rotatie": rotatie, "match": match_in_rotatie, "partner_id": partner_id,
                "kans": kans, "n_obs": n_obs, "bron": bron, "synergie": syn,
            })

        geldige = [s for s in per_slot if s and s["kans"] is not None]
        if geldige and not duplicaat:
            gemiddeld = sum(s["kans"] for s in geldige) / len(geldige)
            totaal_verwacht = sum(s["kans"] for s in geldige)
            for s in geldige:
                syn_txt = f", synergie {s['synergie']:.2f}" if s["synergie"] is not None else ""
                st.caption(
                    f"R{s['rotatie']} M{s['match']}: **{int(round(s['kans'] * 100))}%** "
                    f"winkans ({s['bron']}, n={s['n_obs']}{syn_txt})"
                )
            st.metric(f"Gemiddelde winkans ({titel})", f"{gemiddeld * 100:.1f}%")
        else:
            gemiddeld = None
            totaal_verwacht = None
            if not duplicaat:
                st.info("Kies hierboven voor elke rotatie een partner om de winkans te zien.")

        return {
            "per_slot": per_slot, "gemiddeld": gemiddeld,
            "totaal_verwacht": totaal_verwacht, "duplicaat": duplicaat,
        }


def _render_whatif_comparison(
    bundle: dict, opp: dict, available_ids: list, name_lookup_global: dict,
    player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
    synergy_fn, sel_player_id: str, sel_label: str, n_rotations=None,
) -> None:
    """PADEL_ANALYSIS_WHATIF_PARTNER_COMPARE_2026-09-29 - zie moduledocstring.
    Vergelijkt 2 partnerkeuzes voor JEZELF op een gekozen bordpositie."""
    n_rotations = int(n_rotations or ROTATIONS_PER_ENCOUNTER)
    ploeg_key = str(opp.get("ploeg_id"))

    st.markdown(
        '<div class="section-header">Wat als: mijn winkans bij een andere partner</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Vergelijk EXACT (zelfde formule als de rest van de app) wat jouw persoonlijke winkans "
        f"zou zijn met 2 verschillende partnerkeuzes, op een gekozen bordpositie. Jouw eigen "
        f"speler staat vast op **{sel_label}**; kies hieronder enkel de partner(s)."
    )
    st.caption(_WIN_PROB_DISCLAIMER)

    partner_ids = [pid for pid in available_ids if str(pid) != str(sel_player_id)]
    if len(partner_ids) < 2:
        st.info("Selecteer hierboven minstens 2 andere eigen spelers om partnerkeuzes te vergelijken.")
        return

    partner_options = sorted(
        (name_lookup_global.get(pid, pid) for pid in partner_ids),
        key=lambda lbl: lbl.lower(),
    )
    partner_label_to_id = {name_lookup_global.get(pid, pid): pid for pid in partner_ids}

    zelfde_positie = st.checkbox(
        "Zelfde matchpositie in elke rotatie (bv. 'altijd Match 2')", value=True,
        key=f"whatif_same_slot_{ploeg_key}",
    )
    if zelfde_positie:
        match_keuze = st.radio(
            "Matchpositie", [1, 2], index=1, horizontal=True,
            format_func=lambda m: f"Match {m}" + (" (sterkste duo, art. 6.6)" if m == 1 else ""),
            key=f"whatif_match_choice_{ploeg_key}",
        )
        slots = [(r, match_keuze) for r in range(1, n_rotations + 1)]
    else:
        slots = []
        cols = st.columns(n_rotations)
        for r in range(1, n_rotations + 1):
            with cols[r - 1]:
                m = st.selectbox(
                    f"Rotatie {r}", [1, 2], format_func=lambda m: f"Match {m}",
                    key=f"whatif_slot_r{r}_{ploeg_key}",
                )
            slots.append((r, m))

    col_a, col_b = st.columns(2)
    result_a = _render_option_column(
        col_a, "Optie A", f"a_{ploeg_key}_{n_rotations}", slots, partner_options,
        partner_label_to_id, sel_player_id, sel_label, bundle, player_ratings,
        official_ranks_strict, opponent_ratings, synergy_fn,
    )
    result_b = _render_option_column(
        col_b, "Optie B", f"b_{ploeg_key}_{n_rotations}", slots, partner_options,
        partner_label_to_id, sel_player_id, sel_label, bundle, player_ratings,
        official_ranks_strict, opponent_ratings, synergy_fn,
    )

    if (
        result_a["gemiddeld"] is not None and result_b["gemiddeld"] is not None
        and not result_a["duplicaat"] and not result_b["duplicaat"]
    ):
        verschil_pp = (result_a["gemiddeld"] - result_b["gemiddeld"]) * 100
        st.divider()
        if abs(verschil_pp) < _DUIDELIJK_VERSCHIL_PP:
            st.info(
                f"**Gelijkwaardig binnen de onzekerheid van de schatting**: Optie A "
                f"{result_a['gemiddeld']*100:.1f}% tegenover Optie B {result_b['gemiddeld']*100:.1f}% "
                f"(verschil {abs(verschil_pp):.1f} procentpunt). Kies op basis van andere criteria "
                "(bv. bewezen samenspel, eerlijke speeltijd-verdeling)."
            )
        elif verschil_pp > 0:
            st.success(
                f"**Optie A geeft een hogere winkans**: {result_a['gemiddeld']*100:.1f}% tegenover "
                f"{result_b['gemiddeld']*100:.1f}% voor Optie B (verschil {verschil_pp:.1f} procentpunt)."
            )
        else:
            st.success(
                f"**Optie B geeft een hogere winkans**: {result_b['gemiddeld']*100:.1f}% tegenover "
                f"{result_a['gemiddeld']*100:.1f}% voor Optie A (verschil {abs(verschil_pp):.1f} procentpunt)."
            )
        laagste_n = min(
            [s["n_obs"] for s in result_a["per_slot"] if s] + [s["n_obs"] for s in result_b["per_slot"] if s],
            default=0,
        )
        if laagste_n <= 1:
            st.caption(
                "Let op: minstens 1 van de gebruikte schattingen berust op erg weinig (of geen) "
                "historische waarnemingen - behandel dit verschil als een indicatie, geen garantie."
            )
    st.divider()
