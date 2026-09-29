"""
lineup_sandbox.py - Sandbox: handmatig een opstelling samenstellen,
rotatie per rotatie en match per match.

Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
Zie de oorspronkelijke, monolithische versie van page_lineup_lab.py voor de
volledige historische toelichting bij elke fix - functioneel ONGEWIJZIGD.
PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29: het invoerveld "Aantal rotaties in de sandbox" is weg; het
aantal rotaties komt uit het reglement (lineup_rotation.ROTATIONS_PER_ENCOUNTER).
"""
import streamlit as st
from dashboard_common import ll, _parse_match_date
from lineup_scout import (
    _load_encounter_index, _cached_official_rank, _cached_own_player_rating,
)
from lineup_rotation import (
    _pair_official_sum_safe, _compute_matchup,
    ROTATIONS_PER_ENCOUNTER,  # PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29
)
from lineup_matchup_table import _estimate_column_width


def _recent_own_lineup_boards(sel_player_id: str, profiles: list) -> list:
    try:
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs, index = _load_encounter_index(profile_ids)
        all_encounters = ll.list_encounters(index)
        own_keys = [key for key, _ in all_encounters if any(pid == sel_player_id for pid, _ in index[key])]
        if not own_keys:
            return []

        def _encounter_date(key):
            dates = [_parse_match_date(entry.get("match_date")) for _, entry in index[key]]
            dates = [d for d in dates if d]
            return max(dates) if dates else (0, 0, 0)

        most_recent_key = max(own_keys, key=_encounter_date)
        boards = ll.reconstruct_boards(index[most_recent_key]) or []
        pairs = []
        for board in sorted(boards, key=lambda b: b.get("board_position") or 0):
            pair = board.get("pair") or []
            if len(pair) == 2:
                pairs.append(tuple(pair))
        return pairs
    except Exception:
        return []


def _most_recent_opponent_boards_for_sandbox(bundle: dict) -> list:
    previous_fixtures = bundle.get("previous_fixtures") or []
    if not previous_fixtures:
        return []
    most_recent = previous_fixtures[-1]
    boards = sorted(most_recent.get("boards") or [], key=lambda b: b.get("board_position") or 0)
    pairs = []
    for b in boards:
        pair = b.get("opponent_pair") or []
        if len(pair) == 2:
            pairs.append([p.get("name", "?") for p in pair])
    return pairs


def _apply_sandbox_preset(
    ploeg_key: str, n_rotations: int, own_pair_labels: list = None, opp_pair_labels: list = None,
) -> None:
    slot = 0
    for r in range(int(n_rotations)):
        for m_i in range(2):
            if own_pair_labels is not None:
                key = f"sandbox_own_r{r}_m{m_i}_{ploeg_key}"
                pair = own_pair_labels[slot: slot + 2] if slot + 2 <= len(own_pair_labels) else []
                st.session_state[key] = list(pair)
            if opp_pair_labels is not None:
                key = f"sandbox_opp_r{r}_m{m_i}_{ploeg_key}"
                pair = opp_pair_labels[slot: slot + 2] if slot + 2 <= len(opp_pair_labels) else []
                st.session_state[key] = list(pair)
            slot += 2


def _smart_prefill_sandbox_defaults(
    ploeg_key: str, available_ids: list, official_ranks_strict: dict,
    name_lookup_global: dict, n_rotations: int, label_fn=None,
) -> None:
    any_existing = any(
        f"sandbox_own_r{r}_m{m_i}_{ploeg_key}" in st.session_state
        for r in range(int(n_rotations)) for m_i in range(2)
    )
    if any_existing:
        return
    ids_sorted = sorted(
        available_ids,
        key=lambda pid: official_ranks_strict.get(pid) if official_ranks_strict.get(pid) is not None else -1,
        reverse=True,
    )
    _label = label_fn or (lambda pid: name_lookup_global.get(pid, pid))
    labels_sorted = [_label(pid) for pid in ids_sorted]
    _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=labels_sorted)


@st.fragment
def _render_lineup_sandbox(
    bundle, opp, available_ids, name_lookup_global,
    player_ratings, official_ranks_strict, opponent_ratings, synergy_fn,
    profiles=None, sel_player_id=None,
) -> None:
    """PADEL_ANALYSIS_FRAGMENT_ISOLATION_2026-09-26: @st.fragment isoleert
    deze functie van een volledige pagina-rerun. Zie de oorspronkelijke
    docstring in page_lineup_lab.py voor de volledige toelichting bij elke
    eerdere fix - functioneel ONGEWIJZIGD."""
    st.markdown('<div class="section-header">Sandbox: bouw je eigen opstelling</div>', unsafe_allow_html=True)
    st.caption(
        "Stel zelf, rotatie per rotatie en match per match, een opstelling samen: kies wie van ONS team en "
        "wie van DE TEGENSTANDER er in elke match staat. Handig om een specifieke hypothese te testen zonder "
        "te moeten zoeken in de volledige combinatie-tabel hierboven."
    )
    unique_players = bundle.get("unique_players", []) or []
    if len(available_ids) < 2:
        st.info("Selecteer hierboven minstens 2 eigen spelers om de sandbox te gebruiken.")
        return
    if len(unique_players) < 2:
        st.info("Nog geen tegenstander-spelers gekend om in de sandbox te kiezen.")
        return

    def _speler_label(pid: str) -> str:
        naam = name_lookup_global.get(pid, pid)
        officieel = official_ranks_strict.get(pid)
        padelstat = player_ratings.get(pid)
        delen = []
        delen.append(f"P{int(officieel)}" if officieel is not None else "P?")
        if padelstat is not None:
            delen.append(f"ps {int(padelstat)}")
        return f"{naam} ({' \u00b7 '.join(delen)})"

    own_labels = [_speler_label(pid) for pid in available_ids]
    own_label_to_id = {_speler_label(pid): pid for pid in available_ids}

    def _opp_label(speler: dict) -> str:
        naam = speler.get("name", "?")
        uid = str(speler.get("user_id") or "")
        officieel = _cached_official_rank(uid) if uid else None
        padelstat = _cached_own_player_rating(uid) if uid else None
        delen = [f"P{int(officieel)}" if officieel is not None else "P?"]
        if padelstat is not None:
            delen.append(f"ps {int(padelstat)}")
        return f"{naam} ({' \u00b7 '.join(delen)})"

    opp_labels = [_opp_label(p) for p in unique_players]
    opp_label_to_player = {_opp_label(p): p for p in unique_players}
    ploeg_key = opp["ploeg_id"]
    # PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29: vast volgens het reglement.
    n_rotations = ROTATIONS_PER_ENCOUNTER
    _smart_prefill_sandbox_defaults(
        ploeg_key, available_ids, official_ranks_strict, name_lookup_global,
        n_rotations, label_fn=_speler_label,
    )
    with st.expander("Snel invullen met een standaardoptie", expanded=False):
        preset_cols = st.columns(4)
        with preset_cols[0]:
            if st.button(
                "Tegenstander: vorige match", key=f"preset_opp_prev_{ploeg_key}", use_container_width=True,
                help="Vult het tegenstander-duo per match in met hun meest recente, effectief gespeelde opstelling.",
            ):
                opp_pairs = _most_recent_opponent_boards_for_sandbox(bundle)
                _naam_naar_label = {p.get("name", "?"): lbl for lbl, p in opp_label_to_player.items()}
                flat = [_naam_naar_label.get(name, name) for pair in opp_pairs for name in pair]
                if flat:
                    _apply_sandbox_preset(ploeg_key, n_rotations, opp_pair_labels=flat)
                    st.rerun(scope="fragment")
                else:
                    st.warning("Geen eerdere tegenstander-opstelling gekend.")
        with preset_cols[1]:
            if st.button(
                "Ons sterkste 4 (Elo)", key=f"preset_own_elo_{ploeg_key}", use_container_width=True,
                help="Vult ONS duo per match in met de sterkste beschikbare spelers volgens padelstat/Elo-rating.",
            ):
                ids_by_elo = sorted(
                    available_ids,
                    key=lambda pid: player_ratings.get(pid) if player_ratings.get(pid) is not None else -1,
                    reverse=True,
                )
                labels_by_elo = [_speler_label(pid) for pid in ids_by_elo]
                _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=labels_by_elo)
                st.rerun(scope="fragment")
        with preset_cols[2]:
            if st.button(
                "Onze vorige opstelling", key=f"preset_own_prev_{ploeg_key}", use_container_width=True,
                help="Herhaalt ONZE opstelling (koppels) van de vorige interclubmatch.",
            ):
                own_pairs = _recent_own_lineup_boards(sel_player_id, profiles or []) if sel_player_id else []
                flat = [_speler_label(pid) for pair in own_pairs for pid in pair]
                if flat:
                    _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=flat)
                    st.rerun(scope="fragment")
                else:
                    st.warning("Geen vorige eigen opstelling gekend.")
        with preset_cols[3]:
            if st.button(
                "Willekeurig geldig", key=f"preset_own_random_{ploeg_key}", use_container_width=True,
                help="Vult ONS duo per match willekeurig in (elke speler max. 1x, rotatie-veilig).",
            ):
                import random
                shuffled = list(available_ids)
                random.shuffle(shuffled)
                labels_random = [_speler_label(pid) for pid in shuffled]
                _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=labels_random)
                st.rerun(scope="fragment")
    own_ordered_pairs, opp_boards, rotation_meta = [], [], []
    used_own_pairs_seen: dict = {}
    incomplete = False
    with st.form(key=f"sandbox_form_{ploeg_key}"):
        for r in range(int(n_rotations)):
            st.markdown(f"**Rotatie {r + 1}**")
            col_m1, col_m2 = st.columns(2)
            matches = []
            for m_i, col in enumerate((col_m1, col_m2)):
                with col:
                    st.markdown(f"Match {m_i + 1}" + (" *(sterkste duo, art. 6.6)*" if m_i == 0 else ""))
                    our_sel = st.multiselect(
                        "Ons duo", own_labels, max_selections=2,
                        key=f"sandbox_own_r{r}_m{m_i}_{ploeg_key}",
                    )
                    opp_sel = st.multiselect(
                        "Tegenstander-duo", opp_labels, max_selections=2,
                        key=f"sandbox_opp_r{r}_m{m_i}_{ploeg_key}",
                    )
                    matches.append((our_sel, opp_sel))
            m1_own, m1_opp = matches[0]
            m2_own, m2_opp = matches[1]
            own_overlap = set(m1_own) & set(m2_own)
            opp_overlap = set(m1_opp) & set(m2_opp)
            if own_overlap:
                st.error(f"Rotatie {r + 1}: {', '.join(own_overlap)} kan niet in beide matchen tegelijk spelen.")
            if opp_overlap:
                st.error(f"Rotatie {r + 1}: tegenstander {', '.join(opp_overlap)} kan niet in beide matchen tegelijk spelen.")
            for m_i, (our_sel, opp_sel) in enumerate(matches):
                if len(our_sel) != 2 or len(opp_sel) != 2:
                    incomplete = True
                    continue
                p1, p2 = own_label_to_id[our_sel[0]], own_label_to_id[our_sel[1]]
                pair_key = frozenset({p1, p2})
                if pair_key in used_own_pairs_seen:
                    prev_rot = used_own_pairs_seen[pair_key]
                    st.warning(
                        f"Rotatie {r + 1} Match {m_i + 1}: koppel {our_sel[0]}+{our_sel[1]} speelde al samen in "
                        f"Rotatie {prev_rot} - een zelfde koppel mag normaliter niet 2x samenspelen."
                    )
                used_own_pairs_seen[pair_key] = r + 1
                opp_players = [opp_label_to_player[lbl] for lbl in opp_sel]
                own_ordered_pairs.append((p1, p2))
                opp_boards.append({"opponent_pair": opp_players})
                rotation_meta.append((r + 1, m_i + 1))
        if incomplete:
            st.info("Vul voor elke match exact 2 eigen spelers en 2 tegenstander-spelers in om de resultaten te zien.")
        sandbox_clicked = st.form_submit_button(
            "Bereken sandbox", type="primary",
            help="Vul eerst alle matchen hierboven in (of gebruik een standaardoptie hierboven), klik dan pas "
                 "op deze knop - pas dan wordt er iets herberekend.",
        )
    if not own_ordered_pairs:
        return
    sandbox_settings_signature = (
        tuple(own_ordered_pairs),
        tuple(tuple(sorted(p.get("user_id") for p in b["opponent_pair"])) for b in opp_boards),
    )
    sandbox_ratings_signature = (
        tuple(sorted(player_ratings.items())),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(opponent_ratings.items())),
    )
    sandbox_signature = (sandbox_settings_signature, sandbox_ratings_signature)
    sandbox_result_key = f"sandbox_result_{ploeg_key}"
    sandbox_sig_key = f"sandbox_result_sig_{ploeg_key}"
    if sandbox_clicked:
        st.session_state[sandbox_result_key] = _compute_matchup(
            own_ordered_pairs, opp_boards, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings,
        )
        st.session_state[sandbox_sig_key] = sandbox_signature
    computed = st.session_state.get(sandbox_result_key)
    if computed is None:
        st.info("Stel de sandbox in en klik op **'Bereken sandbox'** om de winkans en puntensom te zien.")
        return
    stored_sandbox_signature = st.session_state.get(sandbox_sig_key)
    if stored_sandbox_signature != sandbox_signature:
        stored_sandbox_settings = stored_sandbox_signature[0] if stored_sandbox_signature else None
        if stored_sandbox_settings != sandbox_settings_signature:
            st.warning(
                "De sandbox-selectie is gewijzigd sinds de laatste berekening - onderstaand resultaat is nog "
                "het VORIGE. Klik opnieuw op 'Bereken sandbox' om bij te werken."
            )
        else:
            st.warning(
                "De padelstat- en/of klassementwaarden zijn intussen ververst op de achtergrond sinds je "
                "laatste berekening - onderstaand resultaat klopt mogelijk niet meer. Klik opnieuw op "
                "'Bereken sandbox' om bij te werken."
            )
    rows = []
    row_completeness: dict = {}
    for (rot_no, match_no), a in zip(rotation_meta, computed["assignment"]):
        p1, p2 = a["our_pair"]
        our_sum, our_complete = _pair_official_sum_safe(frozenset({p1, p2}), official_ranks_strict)
        wp = a.get("win_probability")
        row_completeness[(rot_no, match_no)] = our_complete
        rows.append({
            "Rotatie": rot_no, "Match": match_no,
            "Ons duo": f"{name_lookup_global.get(p1, p1)}+{name_lookup_global.get(p2, p2)}",
            "Officieel (ons)": our_sum,
            "Tegenstander": "+".join(p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]),
            "Winkans %": round(wp * 100) if wp is not None else None,
        })
    st.dataframe(
        rows, use_container_width=True, hide_index=True,
        column_config={
            "Rotatie": st.column_config.NumberColumn("Rotatie", width="small"),
            "Match": st.column_config.NumberColumn("Match", width="small"),
            "Ons duo": st.column_config.TextColumn("Ons duo", width=_estimate_column_width([r.get("Ons duo") for r in rows])),
            "Officieel (ons)": st.column_config.NumberColumn("Officieel (ons)", width="small"),
            "Tegenstander": st.column_config.TextColumn("Tegenstander", width=_estimate_column_width([r.get("Tegenstander") for r in rows])),
            "Winkans %": st.column_config.NumberColumn("Winkans %", format="%.0f%%", width="small"),
        },
    )
    for r in range(1, int(n_rotations) + 1):
        rot_rows = [row for row in rows if row["Rotatie"] == r]
        if len(rot_rows) == 2:
            s1, s2 = rot_rows[0]["Officieel (ons)"], rot_rows[1]["Officieel (ons)"]
            compleet_1 = row_completeness.get((r, rot_rows[0]["Match"]), True)
            compleet_2 = row_completeness.get((r, rot_rows[1]["Match"]), True)
            if not (compleet_1 and compleet_2):
                st.warning(
                    f"Rotatie {r}: officieel klassement onbekend voor minstens 1 speler - de "
                    "reglement-check (art. 6.6) kan hier NIET betrouwbaar uitgevoerd worden."
                )
            else:
                if s1 < s2:
                    st.warning(
                        f"Rotatie {r}: Match 1 ({s1:.0f}p) is officieel ZWAKKER dan Match 2 ({s2:.0f}p) - "
                        "dit is NIET reglementair (art. 6.6), tenzij je dit bewust test als 'wat als'-scenario."
                    )
                elif s1 == s2:
                    st.caption(f"Rotatie {r}: Match 1 en Match 2 zijn officieel exact gelijk sterk ({s1:.0f}p) - beide volgordes zijn toegelaten.")
                else:
                    st.caption(f"Rotatie {r}: Match 1 ({s1:.0f}p) is officieel sterker dan Match 2 ({s2:.0f}p) - reglementair conform (art. 6.6).")
    total_ebw = computed.get("expected_boards_won")
    if total_ebw is not None:
        st.metric("Verwacht totaal aantal gewonnen matchen (deze sandbox-opstelling)", f"{total_ebw:.2f} / {len(own_ordered_pairs)}")
    st.divider()
