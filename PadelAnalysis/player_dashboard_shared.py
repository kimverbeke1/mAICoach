"""
player_dashboard_shared.py — render_player_dashboard(): de volledige
spelersprofiel-weergave (Overzicht/Match Explorer/Partners/Tegenstanders/
Klassement/Debug-tabs), HERGEBRUIKT door zowel "👤 Mijn profiel" als
"🔍 Spelers".

PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py.
Was voorheen _render_player_dashboard() (met underscore-prefix, "privé"
binnen dashboard.py); nu PUBLIEK (render_player_dashboard, geen underscore)
omdat dit bestand door twee ANDERE modules geïmporteerd wordt
(page_my_profile.py en page_players.py) - net zoals opponent_analysis.py's
functies destijds publiek werden gemaakt toen dashboard.py ze rechtstreeks
ging aanroepen.
_render_refresh_controls en _render_padelstat_section blijven wel
"privé" (underscore) - die worden ENKEL binnen dit bestand gebruikt.
"""
import datetime as _datetime_module
import streamlit as st
import pandas as pd

import dashboard_common as dc
from dashboard_common import (
    fb, ll, lq, pia, is_scraping_available, render_cloud_scrape_trigger,
    _parse_match_date, _format_scraped_at, _matches_to_df, _calc_stats_from_matches,
    _persist_stats_if_needed, _winrate_str, _render_metrics, _summarize_opponents,
    _render_table, _period_sort_key, _scrape_progress_widget, _get_all_profiles,
)


def _render_refresh_controls(player_id: str, profile: dict, key_prefix: str):
    if not is_scraping_available():
        render_cloud_scrape_trigger(
            key_prefix=key_prefix,
            player_ids=str(player_id),
            mode="missing",
            label="🔄 Dit profiel verversen",
        )
        return
    rc1, rc2 = st.columns(2)
    with rc1:
        if st.button("🔄 Vernieuwen (enkel nieuwe periodes)", type="primary", key=f"{key_prefix}_refresh"):
            bar, cb = _scrape_progress_widget()
            try:
                from scrape_player import scrape_player as _scrape
                result = _scrape(str(player_id), force_full_refresh=False, save_to_firebase=True, progress_callback=cb)
                bar.progress(1.0, text="Klaar.")
                st.success(f"Klaar — {result.get('stats',{}).get('total_matches',0)} matches totaal.")
                st.rerun()
            except Exception as e:
                st.error(f"Mislukt: {e}")
    with rc2:
        with st.expander("⚙️ Debug: volledig herscrapen"):
            st.caption("Haalt ALLE periodes opnieuw op, niet enkel de nieuwe. Trager, normaal niet nodig.")
            if st.button("⚠️ Volledig herscrapen", key=f"{key_prefix}_full_refresh"):
                bar, cb = _scrape_progress_widget()
                try:
                    from scrape_player import scrape_player as _scrape
                    result = _scrape(str(player_id), force_full_refresh=True, save_to_firebase=True, progress_callback=cb)
                    bar.progress(1.0, text="Klaar.")
                    st.success(f"Klaar — {result.get('stats',{}).get('total_matches',0)} matches totaal.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Mislukt: {e}")


def _render_padelstat_section(player_id: str) -> None:
    """PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13."""
    st.divider()
    st.markdown('<div class="section-header">🎯 Playing strength (padelstats.be)</div>', unsafe_allow_html=True)
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:
        cached = None
    if not cached or cached.get("rating") is None:
        st.info(
            "Nog niet opgehaald van padelstats.be voor deze speler. Voer lokaal "
            "'python bulk_fetch_padelstat_ratings.py' uit (vereist Playwright) "
            "om dit aan te vullen."
        )
        return
    st.metric("Playing strength", f"P{cached['rating']}")
    st.caption(
        f"Bron: padelstats.be · opgehaald op {_format_scraped_at(cached.get('fetched_at'))} · "
        "onafhankelijke, externe schatting - geen officieel TVL-klassement."
    )


def render_player_dashboard(player_id: str, profile: dict):
    """Stats + tabs voor één speler. Herbruikt door 'Mijn profiel' en 'Spelers'."""
    player_doc = fb.get_player(player_id)
    if not player_doc:
        st.warning("Geen data in Firebase voor deze speler. Gebruik de vernieuw-knop hierboven.")
        return
    matches = player_doc.get("matches", [])
    df = _matches_to_df(matches)
    live_stats = _calc_stats_from_matches(matches)
    wins = live_stats["wins"]
    losses = live_stats["losses"]
    total = live_stats["total_matches"]
    t_count = live_stats["tournament_matches"]
    ic_count = live_stats["interclub_matches"]
    stored_total = int((player_doc.get("stats", {}) or {}).get("total_matches", total))
    if stored_total != total:
        st.caption(
            f"ℹ️ Live telling uit de matchlijst: {total} matchen "
            f"(opgeslagen stats gaf {stored_total}). Ik corrigeer de opgeslagen telling nu."
        )
        _persist_stats_if_needed(player_id, player_doc, live_stats)
    _render_metrics(total, wins, losses, t_count, ic_count)
    tab_overview, tab_explorer, tab_partners, tab_opponents, tab_klassement, tab_debug = st.tabs([
        "Overzicht", "Match Explorer", "Partners", "Tegenstanders", "📈 Klassement", "Debug"
    ])
    with tab_overview:
        if df.empty:
            st.info("Geen matches beschikbaar.")
        else:
            st.markdown('<div class="section-header">Per periode</div>', unsafe_allow_html=True)
            periods = df.groupby("period").agg(
                matches=("period", "size"),
                wins=("won", lambda x: x.eq(True).sum()),
                losses=("won", lambda x: x.eq(False).sum()),
            ).reset_index()
            periods["winrate"] = periods.apply(lambda r: _winrate_str(r.wins, r.losses), axis=1)
            periods = periods.sort_values("period", key=lambda s: s.map(_period_sort_key), ascending=False)
            periods = periods.reset_index(drop=True)
            st.caption("👉 Klik op een periode om de matches uit die periode te zien.")
            period_event = st.dataframe(
                periods, use_container_width=True, hide_index=True,
                height=min(400, 40 + len(periods) * 36),
                column_config={
                    "period":  st.column_config.TextColumn("Periode", width="large"),
                    "matches": st.column_config.NumberColumn("M", width="small"),
                    "wins":    st.column_config.NumberColumn("W", width="small"),
                    "losses":  st.column_config.NumberColumn("L", width="small"),
                    "winrate": st.column_config.TextColumn("Winrate", width="small"),
                },
                on_select="rerun", selection_mode="single-row", key=f"periods_table_{player_id}",
            )
            sel_rows = (period_event or {}).get("selection", {}).get("rows", [])
            if sel_rows:
                sel_period = periods.iloc[sel_rows[0]]["period"]
                st.markdown(f"**Matches in periode '{sel_period}':**")
                period_view_cols = [
                    "datum", "type", "reeks", "ronde",
                    "partner", "opp1", "opp1_ranking", "opp2", "opp2_ranking",
                    "score", "result",
                ]
                period_view_cols = [c for c in period_view_cols if c in df.columns]
                pdf = df[df["period"] == sel_period].copy()
                pdf["_sort_date"] = pdf["datum"].apply(lambda d: _parse_match_date(d) or (0, 0, 0))
                pdf = pdf.sort_values("_sort_date", ascending=False)
                pdf["result_display"] = pdf.apply(
                    lambda r: r["result"] or ("W" if r["won"] is True else ("V" if r["won"] is False else "-")),
                    axis=1,
                )
                view_cols = [c for c in period_view_cols if c != "result"] + ["result_display"]
                pdf_display = pdf[view_cols].rename(columns={
                    "datum": "Datum", "type": "Type", "reeks": "Reeks", "ronde": "Ronde",
                    "partner": "Partner", "opp1": "Tegenstander 1", "opp1_ranking": "R1",
                    "opp2": "Tegenstander 2", "opp2_ranking": "R2",
                    "score": "Score", "result_display": "W/V",
                })
                st.dataframe(
                    pdf_display, use_container_width=True, hide_index=True,
                    height=min(500, 40 + len(pdf_display) * 36),
                    column_config={
                        "Datum": st.column_config.TextColumn("Datum", width="small"),
                        "Type": st.column_config.TextColumn("Type", width="small"),
                        "R1": st.column_config.TextColumn("R1", width="small"),
                        "R2": st.column_config.TextColumn("R2", width="small"),
                        "W/V": st.column_config.TextColumn("W/V", width="small"),
                        "Score": st.column_config.TextColumn("Score", width="small"),
                    },
                )
                st.caption(f"{len(pdf_display)} match(en) in deze periode.")
            st.markdown('<div class="section-header">Tornooi vs Interclub</div>', unsafe_allow_html=True)
            tc1, tc2 = st.columns(2)
            for col, label, filter_val in [(tc1, "Tornooi", "tornooi"), (tc2, "Interclub", "interclub")]:
                sub = df[df["type"] == filter_val]
                sub_w = int(sub["won"].eq(True).sum())
                sub_l = int(sub["won"].eq(False).sum())
                col.metric(f"{label} ({len(sub)})", _winrate_str(sub_w, sub_l), f"{sub_w}W – {sub_l}L")
    with tab_explorer:
        if df.empty:
            st.info("Geen matches.")
        else:
            with st.expander("🔽 Filters", expanded=False):
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    type_opts = ["Alle"] + sorted(df["type"].unique().tolist())
                    sel_type = st.selectbox("Type", type_opts, key=f"flt_type_{player_id}")
                    period_opts = ["Alle"] + sorted(df["period"].unique().tolist(), key=_period_sort_key, reverse=True)
                    sel_period = st.selectbox("Periode", period_opts, key=f"flt_period_{player_id}")
                with fc2:
                    result_opts = ["Alle", "W", "V"]
                    sel_result = st.selectbox("Resultaat (W/V)", result_opts, key=f"flt_result_{player_id}")
                    partner_opts = ["Alle"] + sorted(df["partner"].replace("", pd.NA).dropna().unique().tolist())
                    sel_partner = st.selectbox("Partner", partner_opts, key=f"flt_partner_{player_id}")
                with fc3:
                    reeks_opts = ["Alle"] + sorted(df["reeks"].replace("", pd.NA).dropna().unique().tolist())
                    sel_reeks = st.selectbox("Reeks", reeks_opts, key=f"flt_reeks_{player_id}")
                    score_q = st.text_input("Zoek in score", key=f"flt_score_{player_id}")
            fdf = df.copy()
            if sel_type != "Alle":    fdf = fdf[fdf["type"] == sel_type]
            if sel_period != "Alle":  fdf = fdf[fdf["period"] == sel_period]
            if sel_result != "Alle":  fdf = fdf[fdf["result"] == sel_result]
            if sel_partner != "Alle": fdf = fdf[fdf["partner"] == sel_partner]
            if sel_reeks != "Alle":   fdf = fdf[fdf["reeks"] == sel_reeks]
            if score_q:               fdf = fdf[fdf["score"].str.contains(score_q, case=False, na=False)]
            fdf = fdf.copy()
            fdf["result_display"] = fdf.apply(
                lambda r: r["result"] or ("W" if r["won"] is True else ("V" if r["won"] is False else "-")),
                axis=1,
            )
            fdf["_sort_date"] = fdf["datum"].apply(lambda d: _parse_match_date(d) or (0, 0, 0))
            fdf = fdf.sort_values("_sort_date", ascending=False)
            fw = int(fdf["won"].eq(True).sum())
            fl = int(fdf["won"].eq(False).sum())
            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Matches", len(fdf))
            sm2.metric("W", fw)
            sm3.metric("L", fl)
            sm4.metric("Winrate", _winrate_str(fw, fl))
            show_cols = ["type", "datum", "reeks", "ronde", "partner",
                         "opp1", "opp1_ranking", "opp2", "opp2_ranking", "result_display", "score"]
            show_cols = [c for c in show_cols if c in fdf.columns]
            fdf_display = fdf[show_cols].rename(columns={
                "type": "Type", "datum": "Datum",
                "reeks": "Reeks", "ronde": "Ronde", "partner": "Partner",
                "opp1": "Tegenstander 1", "opp1_ranking": "R1",
                "opp2": "Tegenstander 2", "opp2_ranking": "R2",
                "result_display": "W/V", "score": "Score",
            })
            st.caption("👉 Klik op een rij om de details onderaan te tonen.")
            explorer_event = st.dataframe(
                fdf_display, use_container_width=True, hide_index=True,
                height=min(500, 40 + len(fdf) * 36),
                column_config={
                    "W/V": st.column_config.TextColumn("W/V", width="small"),
                    "Score": st.column_config.TextColumn("Score", width="small"),
                    "R1": st.column_config.TextColumn("R1", width="small"),
                    "R2": st.column_config.TextColumn("R2", width="small"),
                },
                on_select="rerun", selection_mode="single-row", key=f"match_explorer_table_{player_id}",
            )
            if not fdf.empty:
                st.markdown("---")
                st.markdown("**Match detail**")
                selected_rows = (explorer_event or {}).get("selection", {}).get("rows", [])
                if not selected_rows:
                    st.info("Klik op een rij in de tabel hierboven om de details te zien.")
                else:
                    idx = selected_rows[0]
                    row = fdf.iloc[idx]
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        st.write(f"**Type:** {row.get('type','–')}")
                        st.write(f"**Datum:** {row.get('datum','–') or '–'}")
                        st.write(f"**Periode:** {row.get('period','–')}")
                        st.write(f"**Toernooi/Competitie:** {row.get('toernooi','–') or '–'}")
                        st.write(f"**Reeks:** {row.get('reeks','–') or '–'}")
                        st.write(f"**Ronde:** {row.get('ronde','–') or '–'}")
                    with dc2:
                        st.write("**Partner:**")
                        pia.render_player_name_action(
                            row.get('partner','–') or '–',
                            pia.resolve_player_id(row.get('partner','–') or '–', pia.build_profile_lookup(_get_all_profiles()), row.get('partner_id','')),
                            key_prefix=f"selected_match_{player_id}_{idx}_partner",
                        )
                        st.write("**Tegenstander 1:**")
                        pia.render_player_name_action(
                            f"{row.get('opp1','–')} ({row.get('opp1_ranking','?')})",
                            pia.resolve_player_id(row.get('opp1','–') or '–', pia.build_profile_lookup(_get_all_profiles()), row.get('opp1_id', row.get('opp1_user_id',''))),
                            key_prefix=f"selected_match_{player_id}_{idx}_opp1",
                        )
                        st.write("**Tegenstander 2:**")
                        pia.render_player_name_action(
                            f"{row.get('opp2','–')} ({row.get('opp2_ranking','?')})",
                            pia.resolve_player_id(row.get('opp2','–') or '–', pia.build_profile_lookup(_get_all_profiles()), row.get('opp2_id', row.get('opp2_user_id',''))),
                            key_prefix=f"selected_match_{player_id}_{idx}_opp2",
                        )
                        st.write(f"**Score:** {row.get('score','–')}")
                        result_val = row.get("result") or ("W" if row.get("won") is True else ("V" if row.get("won") is False else "-"))
                        result_badge = "win" if result_val == "W" else "loss"
                        st.markdown(
                            f"**Resultaat:** <span class='badge-{result_badge}'>"
                            f"{'✅ Winst' if result_badge=='win' else '❌ Verlies'}</span>",
                            unsafe_allow_html=True,
                        )
                        if row.get("reeks_url"):
                            st.markdown(f"[📋 Poule/tabel ↗](https://www.tennisenpadelvlaanderen.be{row['reeks_url']})")
                        if row.get("uitslagenblad"):
                            st.markdown(f"[📄 Uitslagenblad ↗](https://www.tennisenpadelvlaanderen.be{row['uitslagenblad']})")
    with tab_partners:
        st.markdown('<div class="section-header">Partneranalyse</div>', unsafe_allow_html=True)
        with st.expander("Uitleg partneranalyse", expanded=False):
            st.write(
                "Matches/W/V/Winrate met mij komen uitsluitend uit de matchlijst van deze speler. "
                "Partner algemeen komt uit het profiel van de partner, als die partner ook gescraped is. "
                "Delta = winrate met mij minus partner algemene winrate. Positieve delta betekent dat het "
                "duo beter presteert dan de algemene partnerbaseline. Gebruik delta enkel bij voldoende "
                "matchen; de kolom Betrouwbaarheid helpt daarbij."
            )
        match_type_choice = st.radio(
            "Wedstrijdtype", ["Alle", "interclub", "tornooi"],
            horizontal=True, key=f"partner_type_{player_id}",
            format_func=lambda x: "Alle" if x == "Alle" else ("Interclub" if x == "interclub" else "Tornooi"),
        )
        all_profiles_for_partners = _get_all_profiles()
        all_ids_for_partners = [str(p.get("player_id")) for p in all_profiles_for_partners if p.get("player_id")]
        docs_for_partners = ll.get_docs_for_players(all_ids_for_partners)
        profiles_lookup_for_partners = pia.build_profile_lookup(all_profiles_for_partners)
        partner_df = lq.build_partner_analysis_df(
            player_doc, docs_for_partners,
            profiles_lookup=profiles_lookup_for_partners,
            match_type_filter=match_type_choice,
        )
        if not partner_df.empty:
            q = st.text_input("Zoek partner", placeholder="Filter...", label_visibility="collapsed", key=f"pq_{player_id}")
            if q:
                partner_df = partner_df[partner_df["Partner"].str.contains(q, case=False, na=False)]
            _render_table(partner_df, "Partner")
        else:
            st.info("Nog geen partnerhistoriek gevonden voor deze speler binnen dit filter.")
    with tab_opponents:
        st.markdown('<div class="section-header">Tegenstandersanalyse</div>', unsafe_allow_html=True)
        opp_df = _summarize_opponents(df)
        if not opp_df.empty:
            q = st.text_input("Zoek tegenstander", placeholder="Filter...", label_visibility="collapsed", key=f"oq_{player_id}")
            if q:
                opp_df = opp_df[opp_df["tegenstander"].str.contains(q, case=False, na=False)]
        _render_table(opp_df, "tegenstander")
    with tab_klassement:
        st.markdown('<div class="section-header">📈 Klassementshistoriek</div>', unsafe_allow_html=True)
        profile_doc_for_klassement = fb.get_player_profile(player_id) or {}
        klassement_doc = (
            (player_doc or {}).get("klassement_history")
            or (profile_doc_for_klassement or {}).get("klassement_history")
            or (profile or {}).get("klassement_history")
        )
        if klassement_doc:
            history = klassement_doc.get("history", [])
            raw_periods = klassement_doc.get("raw_periods", []) or []
            if not history and raw_periods:
                raw_errors = [
                    p.get("error")
                    for p in raw_periods
                    if isinstance(p, dict) and p.get("error")
                ]
                if raw_errors:
                    st.warning(
                        "Klassementdata werd opgehaald, maar er zijn geen geldige historiekrecords. "
                        "Eerste fout uit raw_periods:"
                    )
                    st.code(str(raw_errors[0]))
                else:
                    st.info(
                        "Klassementdata is aanwezig, maar de compacte historiek is leeg. "
                        "Bekijk raw_periods in de Debug-tab."
                    )
            if history:
                normalized_history = []
                for row in history:
                    r = dict(row or {})
                    klassement_value = (
                        r.get("klassement")
                        or r.get("begin_klassement")
                        or r.get("vorig")
                        or r.get("vorig_klassement")
                    )
                    normalized_history.append({
                        "datum": r.get("datum") or r.get("date") or "",
                        "periode": r.get("periode") or r.get("omschrijving") or r.get("label"),
                        "klassement": klassement_value,
                    })
                hist_df = pd.DataFrame(normalized_history)
                wanted_cols = [c for c in ["datum", "periode", "klassement"] if c in hist_df.columns]
                hist_df = hist_df[wanted_cols]
                if "datum" in hist_df.columns:
                    hist_df["_sort_date"] = hist_df["datum"].apply(lambda d: _parse_match_date(d) or (0, 0, 0))
                    hist_df = hist_df.sort_values("_sort_date", ascending=False).drop(columns=["_sort_date"])
                st.caption("Klassement aan het begin van elke periode.")
                st.dataframe(
                    hist_df.rename(columns={
                        "datum": "Datum",
                        "periode": "Periode",
                        "klassement": "Klassement begin periode",
                    }),
                    use_container_width=True,
                    hide_index=True,
                    height=min(400, 40 + len(hist_df) * 36),
                )
            niveau_data = klassement_doc.get("niveau_winrates", {})
            if niveau_data:
                st.markdown('<div class="section-header">Winrate per tegenstanderniveau</div>', unsafe_allow_html=True)
                niv_rows = [
                    {"Niveau": niv, "Gem. winrate": f"{v['winstratio_avg']}%" if v["winstratio_avg"] is not None else "?",
                     "Totaal matchen": v["total_matchen"]}
                    for niv, v in sorted(niveau_data.items(), key=lambda x: int(x[0][1:]))
                ]
                st.dataframe(pd.DataFrame(niv_rows), use_container_width=True, hide_index=True)
            scraped = _format_scraped_at(klassement_doc.get("scraped_at"))
            st.caption(f"Klassement gescraped op: {scraped}")
        else:
            st.info(
                "Nog geen klassementsdata beschikbaar. Klik hieronder om de klassementshistoriek te laden. "
                "Dit opent een browser en doorloopt alle beschikbare periodes (~30-60 seconden)."
            )
        if is_scraping_available():
            if st.button("📥 Klassementshistoriek laden / verversen", key=f"load_klassement_{player_id}"):
                from scrape_klassement import scrape_klassement, klassement_to_history_summary, extract_niveau_winrates
                bar, cb = _scrape_progress_widget(label_prefix="Klassement: ")
                try:
                    periods = scrape_klassement(str(player_id), progress_callback=cb)
                    bar.progress(1.0, text="Klaar.")
                    history = klassement_to_history_summary(periods)
                    niveau_winrates = extract_niveau_winrates(periods)
                    klass_data = {
                        "history": history,
                        "niveau_winrates": niveau_winrates,
                        "raw_periods": periods,
                        "scraped_at": _datetime_module.datetime.now(_datetime_module.timezone.utc).isoformat(),
                    }
                    payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
                    fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
                    fb.db.collection(fb.PLAYERS_COLLECTION).document(str(player_id)).set(payload, merge=True)
                    if history:
                        st.success(f"Klaar — {len(history)} periodes geladen.")
                    else:
                        st.warning(
                            f"Scrape afgerond, maar compacte historiek is leeg. "
                            f"Raw periodes: {len(periods)}. Bekijk de Klassement-tab of Debug-tab."
                        )
                    st.rerun()
                except Exception as e:
                    st.error(f"Mislukt: {e}")
        _render_padelstat_section(player_id)
    with tab_debug:
        st.json(player_doc, expanded=False)
        st.write(f"**Schema:** {player_doc.get('schema_version','?')}")
        st.write(f"**Periodes gescraped:** {player_doc.get('periods_scraped',[])}")
        st.write(f"**Periodes leeg:** {player_doc.get('periods_empty',[])}")
        st.write(f"**Periodes mislukt:** {player_doc.get('periods_failed',[])}")
