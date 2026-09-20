"""
page_players.py — "🔍 Spelers"-pagina.
PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py.
PADEL_ANALYSIS_PLAYER_RANKING_SUMMARY_2026-09-16 (op verzoek van Kim):
Toont nu, net als "👤 Mijn profiel", duidelijk het officiële klassement en de
padelstats.be playing strength van de geselecteerde speler (via de gedeelde
dashboard_common._render_player_ranking_summary()). Voorheen toonde deze
pagina enkel naam/club/ID - klassement en playing strength waren pas
zichtbaar na doorklikken naar het tabblad 'Klassement' in
render_player_dashboard().
--------------------------------------------------------------------------
PADEL_ANALYSIS_OWN_CLUB_FIELD_2026-09-20 (op verzoek van Kim: "Die scrape
moet weten in welke ploeg ik speel. ik kan dat niet instellen. ik zie daar
geen veld voor. dat moet zichtbaar en wijzigbaar zijn.")
--------------------------------------------------------------------------
Toont nu, meteen onder de naam/club-caption, het nieuwe club/ploeg-
bewerkingsblok (dashboard_common._render_club_editor()) - zodat de club van
ELKE speler (niet enkel jezelf, zie page_my_profile.py) hier zichtbaar EN
wijzigbaar is. Dit veld bepaalt of scraper/refresh_padelstat_only.py deze
speler ooit opzoekt op padelstats.be (zie de uitgebreide toelichting in
dashboard_common.py) - zonder deze toevoeging was er NERGENS in de app een
plek om dit te corrigeren.
"""
import streamlit as st
import dashboard_common as dc
from dashboard_common import (
    fb, _display_name, _get_all_profiles, _render_player_ranking_summary,
    _render_club_editor,
)
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
    # PADEL_ANALYSIS_OWN_CLUB_FIELD_2026-09-20: club/ploeg zichtbaar EN
    # wijzigbaar maken voor ELKE speler (niet enkel jezelf) - zie
    # dashboard_common.py voor de volledige toelichting.
    _render_club_editor(player_id, profile, key_prefix="players")
    # PADEL_ANALYSIS_PLAYER_RANKING_SUMMARY_2026-09-16: officieel klassement +
    # padelstats.be playing strength, duidelijk zichtbaar (st.metric), meteen
    # onder de naam - net als bij "👤 Mijn profiel".
    _render_player_ranking_summary(player_id)
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
