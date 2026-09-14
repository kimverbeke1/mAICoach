"""
page_my_profile.py — "👤 Mijn profiel"-pagina.
PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py.
"""
import streamlit as st

import dashboard_common as dc
from dashboard_common import fb, _display_name, _get_all_profiles, _format_scraped_at, _official_current_rank
from player_dashboard_shared import _render_refresh_controls, render_player_dashboard


def _render_profile_ranking_summary(player_id: str) -> None:
    """PADEL_ANALYSIS_MYPROFILE_RANKING_SUMMARY_2026-09-14."""
    official = _official_current_rank(player_id)
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:
        cached = None
    padelstat = cached.get("rating") if cached else None
    c1, c2 = st.columns(2)
    c1.metric("Officieel klassement", f"P{int(official)}" if official is not None else "Onbekend")
    c2.metric(
        "Playing strength (padelstats.be)",
        f"P{padelstat}" if padelstat is not None else "Onbekend",
    )
    if padelstat is None:
        st.caption(
            "Playing strength nog niet opgehaald van padelstats.be. Voer lokaal "
            "'python bulk_fetch_padelstat_ratings.py' uit om aan te vullen."
        )


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
    # PADEL_ANALYSIS_MYPROFILE_RANKING_SUMMARY_2026-09-14: officieel
    # klassement + padelstats-playing-strength meteen bovenaan.
    _render_profile_ranking_summary(home_id)
    _render_refresh_controls(home_id, home_profile, key_prefix="myprofile")
    st.divider()
    render_player_dashboard(home_id, home_profile)
