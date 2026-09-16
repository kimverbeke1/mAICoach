"""
page_my_profile.py — "👤 Mijn profiel"-pagina.

PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py.

PADEL_ANALYSIS_PLAYER_RANKING_SUMMARY_2026-09-16 (op verzoek van Kim):
_render_profile_ranking_summary() is verhuisd naar dashboard_common.py als
_render_player_ranking_summary(), zodat page_players.py dezelfde, duidelijke
klassement/playing-strength-weergave kan hergebruiken (Kim wilde dit ook
zien bij andere spelers, niet enkel bij zichzelf). Deze pagina roept nu de
gedeelde versie aan i.p.v. een eigen kopie te onderhouden - het zichtbare
gedrag op deze pagina is ongewijzigd.
"""
import streamlit as st

import dashboard_common as dc
from dashboard_common import (
    fb, _display_name, _get_all_profiles, _format_scraped_at,
    _render_player_ranking_summary,
)
from player_dashboard_shared import _render_refresh_controls, render_player_dashboard


def page_my_profile():
    st.header("👤 Mijn profiel")
    profiles = _get_all_profiles()
    if not profiles:
        st.info("Nog geen spelers in de database. Voeg jezelf eerst toe via '➕ Speler toevoegen'.")
        return
    profile_map = {
        f"{_display_name(p)} ({p.get('player_id','?')})": p
        for p in sorted(profiles, key=lambda x: x.get("display_name") or "")
    }
    settings = fb.get_app_settings()
    home_id = settings.get("home_player_id")
    if not home_id:
        st.caption("Stel hier eenmalig in wie jij bent.")
        pick_label = st.selectbox("Dit ben ik", [""] + list(profile_map.keys()), key="home_player_pick")
        if pick_label and st.button("💾 Instellen als 'mij'", type="primary"):
            fb.save_app_settings({"home_player_id": profile_map[pick_label]["player_id"]})
            st.rerun()
        return
    home_profile = next((p for p in profiles if p.get("player_id") == home_id), None)
    if not home_profile:
        st.warning("De ingestelde 'Dit ben ik'-speler werd niet terugvonden. Stel opnieuw in.")
        if st.button("Opnieuw instellen"):
            fb.save_app_settings({"home_player_id": None})
            st.rerun()
        return
    home_doc = fb.get_player(home_id)
    last_scraped = _format_scraped_at((home_doc or {}).get("scraped_at"))
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.subheader(_display_name(home_profile))
        st.caption(f"laatst gescraped: `{last_scraped}`")
    with hc2:
        if st.button("✏️ Wijzig wie ik ben"):
            fb.save_app_settings({"home_player_id": None})
            st.rerun()
    # PADEL_ANALYSIS_PLAYER_RANKING_SUMMARY_2026-09-16: gedeelde helper
    # (was hier lokaal gedefinieerd als _render_profile_ranking_summary,
    # nu in dashboard_common.py zodat page_players.py 'm ook kan gebruiken).
    _render_player_ranking_summary(home_id)
    _render_refresh_controls(home_id, home_profile, key_prefix="myprofile")
    st.divider()
    render_player_dashboard(home_id, home_profile)
