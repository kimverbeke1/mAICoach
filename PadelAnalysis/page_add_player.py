
"""
page_add_player.py — "➕ Speler toevoegen"-pagina.
PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py,
ongewijzigde logica. Zie dashboard_common.py voor de gedeelde helpers/imports.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost, kritiek): profielen aangemaakt via deze pagina (bewuste,
handmatige toevoeging door Kim) kregen GEEN "added_by"-marker, in
tegenstelling tot enrich_opponents.ensure_profiles() ("auto_opponent_
discovery"). Daardoor kon cleanup_ghost_profiles.py niet betrouwbaar
onderscheiden welke profielen bewust/handmatig zijn toegevoegd (die NOOIT
automatisch opgeruimd mogen worden) versus welke automatisch ontdekt zijn
via scouting/enrichment (die WEL in aanmerking komen voor opruiming als ze
nooit verrijkt raken). Fix: de "➕ Toevoegen"-knop zet nu expliciet
added_by="manual" op het profiel.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18 (op verzoek van Kim: "Nieuwe
spelers zoeken/toevoegen vereist een browser (Playwright) en werkt daarom
structureel enkel lokaal (streamlit run streamlit_app.py), nooit op deze
cloud-omgeving — dat blijft zo, ongeacht configuratie." -> "bouw maar.
Padelstat en klassement moeten dan ook gescrapt worden.")
--------------------------------------------------------------------------
BUG/BEPERKING (opgelost, structureel): op Streamlit Community Cloud toonde
deze pagina voorheen ONVOORWAARDELIJK enkel "Nieuwe spelers zoeken kan
enkel lokaal", zonder ooit de bestaande GitHub Actions-trigger te
overwegen — ongeacht of een GitHub-token geconfigureerd stond. Reden: er
bestond simpelweg geen workflow die op NAAM kon zoeken (scrape-padel.yml
kan enkel bestaande player_id's verversen).
Fix: er is nu een aparte workflow (.github/workflows/search-player.yml +
scraper/search_new_player_ci.py) die player_search.search_players() op een
GitHub Actions-runner (met Playwright) uitvoert en het resultaat cachet in
Firestore. Deze pagina toont op cloud nu cloud_helpers.render_cloud_player
_search(), die deze workflow triggert, op het resultaat polt, en bij
"➕ Toevoegen" meteen de volledige scrape (TVL + padelstat + klassement)
aanbiedt via cloud_helpers.render_full_player_scrape_button() — dezelfde
functie die overal elders in de app al gebruikt wordt voor "deze speler nu
verversen".
"""
import streamlit as st
import dashboard_common as dc
import cloud_helpers as ch
from dashboard_common import (
    fb, is_scraping_available, render_cloud_scrape_trigger,
    _clean, _scrape_progress_widget, _display_name, _get_all_profiles,
)
def page_add_player():
    st.header("➕ Speler toevoegen")
    st.caption("Zoek een speler op de TVL-website en voeg hem/haar toe aan de database.")
    if not is_scraping_available():
        st.info(
            "Nieuwe spelers zoeken op TVL vereist normaal een browser (Playwright), "
            "die hier op de cloud niet beschikbaar is. Dat hoeft geen probleem te "
            "zijn: hieronder kan je dezelfde zoekopdracht via GitHub Actions laten "
            "uitvoeren (duurt meestal 1-3 minuten)."
        )
        ch.render_cloud_player_search(key_prefix="add_player_page_search")
        st.divider()
        st.caption("Alle bestaande spelers verversen (ontbrekende periodes) kan ook rechtstreeks:")
        render_cloud_scrape_trigger(key_prefix="add_player_page", mode="missing", label="🔄 Alle spelers verversen")
        return
    with st.form("search_form"):
        c1, c2, c3 = st.columns([2, 2, 2])
        first = c1.text_input("Voornaam")
        last  = c2.text_input("Achternaam")
        club  = c3.text_input("Club (optioneel)")
        submitted = st.form_submit_button("🔍 Zoek op TVL-website", use_container_width=True, type="primary")
    if submitted:
        if not _clean(first) and not _clean(last):
            st.warning("Geef minstens een voornaam of achternaam in.")
            return
        with st.spinner("Zoeken op tennisenpadelvlaanderen.be..."):
            try:
                from player_search import search_players
                candidates = search_players(
                    first_name=first, last_name=last,
                    club=_clean(club) or None,
                    headless=True, use_cache=False,
                )
                st.session_state["add_candidates"] = candidates
                st.session_state["add_search_done"] = True
            except Exception as e:
                st.error(f"Zoekfout: {e}")
                return
    candidates = st.session_state.get("add_candidates", [])
    if not st.session_state.get("add_search_done"):
        return
    if not candidates:
        st.warning("Geen spelers gevonden op TVL.")
        return
    st.success(f"{len(candidates)} kandidaat(en) gevonden")
    for i, c in enumerate(candidates):
        name = c.get("display_name") or "?"
        club_str = c.get("club") or ""
        pid = c.get("player_id") or "?"
        url = c.get("dashboard_url") or ""
        with st.container(border=True):
            col_info, col_btn = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{name}**")
                if club_str:
                    st.caption(f"🏟️ {club_str} · ID: {pid}")
                else:
                    st.caption(f"ID: {pid}")
                if url:
                    st.markdown(f"[Profiel op TVL ↗]({url})", unsafe_allow_html=False)
            with col_btn:
                scrape_key = f"scrape_{i}"
                do_scrape = st.checkbox("Direct scrapen", key=scrape_key, value=True)
                if st.button("➕ Toevoegen", key=f"add_{i}", use_container_width=True, type="primary"):
                    fb.save_player_profile(
                        player_id=str(pid),
                        display_name=name,
                        club=club_str or None,
                        dashboard_url=url or None,
                        aliases=[name],
                    )
                    # PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17: markeer
                    # als bewust/handmatig toegevoegd, zodat cleanup_ghost_
                    # profiles.py deze speler NOOIT als opruimbaar beschouwt,
                    # ongeacht of er later matchdata/padelstat gevonden wordt.
                    fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(
                        {"added_by": "manual"}, merge=True
                    )
                    if do_scrape:
                        bar, cb = _scrape_progress_widget(label_prefix=f"{name}: ")
                        try:
                            from scrape_player import scrape_player as _scrape
                            result = _scrape(str(pid), save_to_firebase=True, progress_callback=cb)
                            bar.progress(1.0, text="Klaar.")
                            s = result.get("stats", {})
                            st.success(
                                f"✅ {name} toegevoegd — "
                                f"{s.get('total_matches',0)} matches, "
                                f"winrate {s.get('winrate',0)}%"
                            )
                        except Exception as e:
                            st.warning(f"Profiel opgeslagen, scrape mislukt: {e}")
                    else:
                        st.success(f"✅ {name} toegevoegd (nog niet gescraped)")
    st.divider()
    st.subheader("🔄 Meerdere spelers verversen")
    st.caption("Voor onderhoud: vernieuw in bulk (enkel nieuwe periodes per speler, sequentieel met pauze).")
    all_profiles = _get_all_profiles()
    if all_profiles:
        bulk_options = {
            f"{_display_name(p)} ({p.get('player_id','?')})": p.get("player_id")
            for p in sorted(all_profiles, key=lambda x: x.get("display_name") or "")
        }
        bulk_chosen = st.multiselect("Kies spelers", list(bulk_options.keys()), key="bulk_scrape_select")
        if bulk_chosen and st.button("▶️ Verversen", type="primary", use_container_width=True):
            overall = st.progress(0.0, text="Starten...")
            for i, label in enumerate(bulk_chosen):
                mid = bulk_options[label]
                _, cb = _scrape_progress_widget(label_prefix=f"{label}: ")
                try:
                    from scrape_player import scrape_player as _scrape
                    result = _scrape(str(mid), force_full_refresh=False, save_to_firebase=True, progress_callback=cb)
                    s = result.get("stats", {})
                    st.write(f"  ✅ {label}: {s.get('total_matches',0)} matches, winrate {s.get('winrate',0)}%")
                except Exception as e:
                    st.write(f"  ❌ {label}: {e}")
                overall.progress((i + 1) / len(bulk_chosen), text=f"({i+1}/{len(bulk_chosen)}) spelers verwerkt")
            st.success("Bulk-verversing voltooid.")
