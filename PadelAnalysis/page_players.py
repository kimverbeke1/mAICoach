"""
page_players.py — "🔍 Spelers"-pagina.
PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py.
"""
import streamlit as st

import dashboard_common as dc
from dashboard_common import fb, _display_name, _get_all_profiles
from player_dashboard_shared import _render_refresh_controls, render_player_dashboard


def page_players():
    st.header("🔍 Spelers")
    profiles = _get_all_profiles()
    if not profiles:
        st.info("Nog geen spelers in de database. Voeg eerst spelers toe via '➕ Speler toevoegen'.")
        return
    profile_map = {
        f"{_display_name(p)} ({p.get('player_id','?')})": p
        for p in sorted(profiles, key=lambda x: x.get("display_name") or "")
    }
    search_q = st.text_input("🔍 Filter speler", placeholder="Typ naam of club...", label_visibility="collapsed")
    filtered_labels = [lbl for lbl in profile_map if not search_q or search_q.lower() in lbl.lower()]
    if not filtered_labels:
        st.warning("Geen spelers gevonden.")
        return
    default_idx = 0
    jump_id = st.session_state.pop("jump_to_player_id", None)
    if jump_id:
        match_label = next((lbl for lbl, p in profile_map.items() if str(p.get("player_id")) == str(jump_id)), None)
        if match_label in filtered_labels:
            default_idx = filtered_labels.index(match_label)
    chosen_label = st.selectbox("Speler", filtered_labels, index=default_idx, label_visibility="collapsed")
    profile = profile_map[chosen_label]
    player_id = profile.get("player_id")
    _settings_now = fb.get_app_settings()
    _home_id_now = str(_settings_now.get("home_player_id") or "")
    _is_me = _home_id_now == str(player_id)
    hcol1, hcol2 = st.columns([5, 1])
    with hcol1:
        st.subheader(_display_name(profile))
        club = profile.get("club")
        if club:
            st.caption(f"🏟️ {club} · ID: {player_id}")
        if _is_me:
            st.caption("👤 Dit ben jij")
    with st.expander("⚠️ Speler verwijderen", expanded=False):
        st.warning(
            f"Speler '{_display_name(profile)}' definitief verwijderen?"
        )
        if st.button(
            "🗑️ Verwijder speler",
            key=f"delete_player_{player_id}",
            type="secondary",
        ):
            fb.delete_player(str(player_id))
            st.success("Speler verwijderd.")
            st.rerun()
    _render_refresh_controls(player_id, profile, key_prefix="players")
    st.divider()
    render_player_dashboard(player_id, profile)
