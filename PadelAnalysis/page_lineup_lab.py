"""
page_lineup_lab.py — "🧩 Opstelling-analyse"-pagina (Volgende match,
Opstelling-scenario's, Rotatieplanner, Opgeslagen analyses).
PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14 t.e.m. PADEL_ANALYSIS_TOURNAMENT_
RULES_2026-09-17: zie eerdere versies van dit bestand voor de volledige
geschiedenis (poule-schema laden/persisteren, aggregaatscores, tegenstander-
referentiesecties, theoretische scenario's, reglement-selector).
--------------------------------------------------------------------------
PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17 (op verzoek
van Kim, na het testen van de vorige versie — 4 samenhangende problemen)
--------------------------------------------------------------------------
Zie lineup_lab.py voor de volledige toelichting (root cause: official_ranks
viel stilzwijgend terug op padelstat, nu strikt gescheiden; matchup-edge nu
per-speler-fallback i.p.v. alles-of-niets per bord; nieuwe winkans/verwacht-
aantal-gewonnen-borden-weergave).
--------------------------------------------------------------------------
PADEL_ANALYSIS_POINTS_BOUNDS_DIAGNOSTIC_2026-09-18 (op verzoek van Kim)
--------------------------------------------------------------------------
Kim testte zijn eigen ploeg bij Opstelling-scenario's en kreeg zowel daar
als bij de Rotatieplanner enkel "Geen enkele eigen koppelverdeling voldoet
aan de reglementaire puntengrens" te zien, zonder enig cijfer om te
begrijpen waarom. Fix: lineup_lab.optimize_lineup_vs_scenario() geeft nu
een DERDE returnwaarde terug (`diagnostics`) met de daadwerkelijk BEREKENDE
punten-per-rotatie-sommen over alle doorgerekende kandidaten. Dit bestand
toont die diagnostiek op alle plekken waar voorheen enkel "0 combinaties"
te zien was.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCH_FREQUENCY_REGROUP_2026-09-18 (op verzoek van Kim)
--------------------------------------------------------------------------
_render_match1_frequency_opponent() hergegroepeerd volgens de rotatie-
indeling (art. 8.7.1): ONEVEN board_position = de EERSTE match van een
rotatie, EVEN board_position = de TWEEDE match van een rotatie.
--------------------------------------------------------------------------
PADEL_ANALYSIS_LABEL_PERSIST_TEXT_MERGE_CLEANUP_2026-09-18 (op verzoek van
Kim, 5 samenhangende punten na het testen van de vorige versie)
--------------------------------------------------------------------------
1. "Reeks 1,2,3 enz is niet duidelijk, beter de min/max P-rating." ->
   _render_tournament_rules_selector() toont de afdeling-keuzelijst nu als
   "Afdeling 5 (P100–P300)" i.p.v. enkel "Afdeling 5".
2. "Best ook onthouden wat geselecteerd was per speler." -> de gekozen
   combinatie (tornooi, categorie, afdeling) wordt bewaard in het
   player_profiles-document van de bekeken speler en automatisch
   teruggezet.
3. "vervang overal de tekst borden door matchen." -> alle GEBRUIKER-
   ZICHTBARE teksten met "bord"/"borden" zijn vervangen door "match"/
   "matchen". Interne Python-namen (board_position, opponent_board,
   boards_count, ...) blijven ONGEWIJZIGD.
4. "agregaatscore lijkt me ook nutteloos, mag weg" -> BEIDE
   aggregaatscore-secties zijn uit de UI verwijderd.
5. "Selecteer minstens 8 tegenstander-spelers... werkt niet" -> was root
   cause van een STRUCTUREEL probleem dat in de volgende fix hieronder
   volledig is opgelost door de twee secties te vervangen door één model.
--------------------------------------------------------------------------
PADEL_ANALYSIS_IDENTICAL_EXPECTED_VALUE_EXPLAINED_2026-09-18 (op verzoek
van Kim: "Allemaal met dezelfde 1.87 verwachting? lijkt me vreemd.")
--------------------------------------------------------------------------
GEEN bug in de winkans-berekening zelf (lineup_lab.py:
estimate_win_probability() gebruikt een individuele, per-speler rating,
onafhankelijk van synergie/wie-met-wie) — geen wijziging aan de berekening.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ALL_VALID_MATCHUPS_FLAT_LIST_2026-09-18 (op verzoek van Kim,
3x verduidelijkt na 2 eerdere, ONVOLDOENDE pogingen)
--------------------------------------------------------------------------
KERN VAN HET PROBLEEM (nu pas volledig begrepen): de vorige twee versies
(PADEL_ANALYSIS_LABEL_PERSIST_TEXT_MERGE_CLEANUP_2026-09-18 se aankondiging
+ de eerste "samenvoeg"-poging PADEL_ANALYSIS_MERGED_SCENARIO_LIST_2026-09-18)
groepeerden nog altijd per TEGENSTANDER-SCENARIO en toonden daarbinnen enkel
ONZE BESTE tegenzet. Kim's exacte, herhaalde verduidelijking:

    "Als 2 ploegen tegen elkaar moeten spelen dan zijn er een aantal
    ploegopstellingen mogelijk. Wel rekening houdend met de regels. nu wil
    ik ALLE geldige combinaties tonen in een lijst. En die sorteren van
    hoogste winstkans naar kleinste winstkans. Ik zie nu 3 keer dezelfde
    opstelling. had ik eerst niet gemerkt. dus daarom 3 x 1.87 matchen
    gewonnnen :-)"
    "alle mogelijke opstellingen. Je kan misschien de opstelling van vorige
    keer in een kleurtje zetten of toch aanduiden"

Het juiste model (nu correct geïmplementeerd):
  1. Verzamel ALLE structureel UNIEKE tegenstander-opstellingen: de
     historische (bundle["previous_fixtures"], ALTIJD meegenomen, ongeacht
     de gekozen theoretische roster) + de theoretische (uit een zelf
     gekozen tegenstander-roster, via ll.generate_all_opponent_lineups()).
     _collect_unique_opponent_lineups() dedupliceert deze op de SPELER-
     PAREN zelf (_opponent_lineup_key(), ONAFHANKELIJK van bordvolgorde,
     want die ligt sowieso al vast via de officiële regel) — komt een
     historische opstelling ook in de theoretische enumeratie voor, dan
     wordt ze EENMALIG behandeld, gemarkeerd als historisch.
  2. Voor ELKE unieke tegenstander-opstelling: bereken ALLE (niet enkel de
     beste) reglementair geldige eigen tegenzetten via
     ll.optimize_lineup_vs_scenario() — dat gaf al langer ALLE geldige
     opties terug (tot _SCENARIO_SAVE_TOP_N), enkel de UI nam voorheen
     stelselmatig maar results[0].
  3. _build_all_valid_matchups() VOEGT DIT SAMEN tot ÉÉN PLATTE LIJST van
     volledige "matchups" (ons-koppelverdeling + hun-koppelverdeling samen
     als 1 item), niet gegroepeerd per tegenstander-scenario. Ontdubbelt
     structureel identieke matchups (kan voorkomen als 2 verschillende
     tegenstander-opstellingen toch tot exact dezelfde eigen-tegenzet-actie
     leiden EN toevallig dezelfde tegenstander-paren hebben - zeldzaam maar
     mogelijk bij symmetrische roster-keuzes).
  4. Sortering: op verwachte-matchen-gewonnen, AFLOPEND (hoogste winstkans
     eerst) — exact zoals gevraagd.
  5. Markering: elke matchup waarvan de tegenstander-opstelling
     STRUCTUREEL overeenkomt met een effectief gespeelde (historische)
     opstelling krijgt een zichtbare, gekleurde badge ("🟢 Zoals gespeeld
     op ...") — Kim: "de opstelling van vorige keer in een kleurtje
     zetten of toch aanduiden".
Nieuwe, apart geteste pure functies (geen Streamlit nodig, zie het gesprek
voor de testresultaten): _historical_opponent_boards_list(),
_opponent_lineup_key(), _matchup_key(), _collect_unique_opponent_lineups(),
_build_all_valid_matchups(). De oude _merge_and_sort_scenario_entries() en
_render_combined_opponent_scenarios() (uit de vorige, onvoldoende poging)
zijn VOLLEDIG VERVANGEN door dit nieuwe model.
"""
import streamlit as st
import dashboard_common as dc
from dashboard_common import (
    fb, ll, ss, osu, oa, taa, is_scraping_available, render_cloud_scrape_trigger,
    _parse_match_date, _format_scraped_at, _display_name, _go_to_player,
    _clean_name, _get_all_profiles, _get_saved_poule_url, _save_poule_url,
    _get_saved_schedule, _load_poule_fixtures, _load_poule_schedule_robust,
    _official_current_rank,
)
try:
    import manual_poule_input
except Exception:  # noqa: BLE001  pragma: no cover
    manual_poule_input = None
try:
    import tournament_rules as tr
except Exception:  # noqa: BLE001  pragma: no cover
    tr = None
# ─────────────────────────────────────────────
# Volgende match + scout-header
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Ontmoetingen ophalen...")
def _load_encounter_index(profile_ids: tuple):
    docs = ll.get_docs_for_players(list(profile_ids))
    index = ll.build_encounter_index(docs)
    return docs, index
def _render_manual_url_fallback(sel_player_id, sel_label, key_prefix, expanded=True):
    if manual_poule_input is not None:
        manual_poule_input.render(
            str(sel_player_id), player_name=sel_label,
            key_prefix=key_prefix, expanded=expanded,
        )
        return
    st.caption(
        "⚠️ Component manual_poule_input niet gevonden — de URL wordt bewaard in "
        "het automatische veld en kan door de volgende update overschreven worden."
    )
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"
    manual_url = st.text_input("Poule/tabel-URL (eenmalig)", key=f"manual_url_input_{sel_player_id}")
    if manual_url and st.button("Onthouden & laden", key=f"use_manual_url_{sel_player_id}", type="primary"):
        u = manual_url.strip()
        st.session_state[override_url_key] = u
        _save_poule_url(sel_player_id, u)
        st.session_state[load_key] = True
        st.rerun()
def _render_schema_refresh_button(sel_player_id: str) -> None:
    if is_scraping_available():
        return
    with st.expander("🔄 Schema nu verversen (via GitHub Actions)", expanded=False):
        st.caption(
            "Start meteen een update van je matchen én het poule-schema op de "
            "achtergrond (GitHub Actions). Duurt meestal enkele minuten."
        )
        render_cloud_scrape_trigger(
            key_prefix=f"vm_schema_{sel_player_id}", player_ids=str(sel_player_id),
            mode="missing", label="🔄 Schema nu verversen",
        )
def _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches):
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    home_ploeg_id, away_ploeg_id, matched_fx = ss.identify_own_ploeg_id(fixtures, own_interclub_matches)
    own_ploeg_id = st.session_state.get(override_team_key)
    if not own_ploeg_id and matched_fx:
        own_ploeg_id = matched_fx.get("resolved_own_ploeg_id")
    if not own_ploeg_id and matched_fx:
        opp_names_known = {_clean_name(m.get("opp1_name")) for m in own_interclub_matches if m.get("opp1_name")}
        if any(_clean_name(matched_fx["away_name"]) in n or n in _clean_name(matched_fx["away_name"]) for n in opp_names_known):
            own_ploeg_id = home_ploeg_id
        else:
            own_ploeg_id = away_ploeg_id
    if not own_ploeg_id:
        st.warning("Kon niet automatisch bepalen welke ploeg dit is op de poule-pagina. Kies hieronder eenmalig je eigen team.")
        team_names = sorted({f["home_name"] for f in fixtures} | {f["away_name"] for f in fixtures})
        chosen_team = st.selectbox("Jouw team in dit schema:", [""] + team_names, key=f"manual_team_pick_{sel_player_id}")
        if chosen_team and st.button("Bevestigen", key=f"confirm_team_{sel_player_id}"):
            match = next((f for f in fixtures if f["home_name"] == chosen_team), None)
            pid = match["home_ploeg_id"] if match else None
            if not pid:
                match = next((f for f in fixtures if f["away_name"] == chosen_team), None)
                pid = match["away_ploeg_id"] if match else None
            if pid:
                st.session_state[override_team_key] = pid
                st.rerun()
        return None
    return own_ploeg_id
def _render_volgende_match_and_scout(sel_player_id: str, sel_label: str):
    st.markdown('<div class="section-header">📅 Volgende match</div>', unsafe_allow_html=True)
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"
    _render_schema_refresh_button(sel_player_id)
    sel_doc = fb.get_player(sel_player_id)
    own_interclub_matches = [m for m in (sel_doc or {}).get("matches", []) if m.get("match_type") == "interclub"]
    def _finish(fixtures, reeks_url_val):
        own_ploeg_id = _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches)
        if not own_ploeg_id:
            return None
        header_result = osu.render_scout_header(sel_player_id=str(sel_player_id), fixtures=fixtures, own_ploeg_id=own_ploeg_id)
        if not header_result:
            return None
        bundle, opp = header_result
        return bundle, opp, reeks_url_val, opp.get("spelgroep_id")
    saved_fixtures, sched_at = _get_saved_schedule(sel_player_id)
    if saved_fixtures:
        reeks_url = _get_saved_poule_url(sel_player_id) or ""
        if sched_at:
            st.caption(f"Schema automatisch opgehaald (via de dagelijkse update) op {_format_scraped_at(sched_at)}.")
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_saved", expanded=False)
        return _finish(saved_fixtures, reeks_url)
    ic_with_url = [m for m in own_interclub_matches if m.get("reeks_url")]
    auto_reeks_url = None
    if ic_with_url:
        most_recent = sorted(ic_with_url, key=lambda m: _parse_match_date(m.get("match_date")) or (0, 0, 0), reverse=True)[0]
        auto_reeks_url = most_recent["reeks_url"]
    saved_url = _get_saved_poule_url(sel_player_id)
    reeks_url = st.session_state.get(override_url_key) or saved_url or auto_reeks_url
    if not reeks_url:
        st.info(
            f"Nog geen poule/tabel-schema gekend voor {sel_label}. Dit wordt normaal automatisch "
            "opgehaald door de dagelijkse update. Je kan hieronder ook zelf de poule/tabel-link "
            "plakken — die wordt blijvend onthouden."
        )
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_nourl")
        return None
    if not st.session_state.get(load_key):
        src = "handmatig ingesteld" if (st.session_state.get(override_url_key) or saved_url) else "automatisch gevonden via je laatste interclubmatch"
        st.caption(f"Poule/tabel-link is {src}. Klik om je volgende match te laden.")
        cbtn1, cbtn2 = st.columns([1, 1])
        with cbtn1:
            if st.button("📅 Volgende match laden", key=f"load_vm_{sel_player_id}", type="primary"):
                st.session_state[load_key] = True
                st.rerun()
        with cbtn2:
            if st.button("✏️ Andere poule-link gebruiken", key=f"change_url_{sel_player_id}"):
                st.session_state.pop(override_url_key, None)
                _save_poule_url(sel_player_id, "")
                st.session_state.pop(load_key, None)
                st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_haveurl", expanded=False)
        return None
    with st.spinner("Wedstrijdschema ophalen..."):
        try:
            fixtures, fetch_error, meta = _load_poule_schedule_robust(sel_player_id, reeks_url)
        except Exception as e:
            fixtures, fetch_error, meta = [], str(e), None
    if meta is not None and fixtures and not fetch_error:
        st.session_state.pop(load_key, None)
        st.rerun()
    if fetch_error:
        st.warning(f"Kon het wedstrijdschema niet ophalen: {fetch_error}")
        if st.button("🔁 Opnieuw proberen", key=f"retry_vm_{sel_player_id}"):
            _load_poule_fixtures.clear()
            st.rerun()
        if st.button("✏️ Andere poule-link", key=f"reset_manual_{sel_player_id}"):
            st.session_state.pop(override_url_key, None)
            st.session_state.pop(override_team_key, None)
            _save_poule_url(sel_player_id, "")
            st.session_state.pop(load_key, None)
            st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_fetcherr")
        return None
    if not fixtures:
        st.warning("Geen wedstrijden gevonden op de poule-pagina (onverwachte paginastructuur?).")
        if st.button("🔁 Opnieuw proberen", key=f"retry_nofix_{sel_player_id}"):
            _load_poule_fixtures.clear()
            st.rerun()
        if st.button("✏️ Andere poule-link", key=f"reset_manual_nofix_{sel_player_id}"):
            st.session_state.pop(override_url_key, None)
            _save_poule_url(sel_player_id, "")
            st.session_state.pop(load_key, None)
            st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_nofix")
        return None
    return _finish(fixtures, reeks_url)
def _recent_own_lineup_player_ids(sel_player_id: str, profiles: list) -> set:
    try:
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs, index = _load_encounter_index(profile_ids)
        all_encounters = ll.list_encounters(index)
        own_keys = [key for key, _ in all_encounters if any(pid == sel_player_id for pid, _ in index[key])]
        if not own_keys:
            return set()
        def _encounter_date(key):
            dates = [_parse_match_date(entry.get("match_date")) for _, entry in index[key]]
            dates = [d for d in dates if d]
            return max(dates) if dates else (0, 0, 0)
        most_recent_key = max(own_keys, key=_encounter_date)
        boards = ll.reconstruct_boards(index[most_recent_key]) or []
        player_ids = set()
        for board in boards:
            for pid in (board.get("pair") or []):
                if pid:
                    player_ids.add(pid)
        return player_ids
    except Exception:
        return set()
def _opponent_padelstat_ratings(bundle: dict) -> dict:
    """SIMULATIE-schaal (padelstat) voor tegenstander-spelers."""
    out = {}
    for p in bundle.get("unique_players", []) or []:
        uid = p.get("user_id")
        if not uid:
            continue
        try:
            rating = oa.get_own_player_rating(uid)[0]
        except Exception:
            rating = None
        if rating is not None:
            out[str(uid)] = rating
    return out
def _opponent_official_ranks(player_ids: list) -> dict:
    """REGLEMENT-schaal (uitsluitend officieel klassement) voor tegenstander-
    spelers. Geen padelstat-fallback."""
    out = {}
    for pid in player_ids:
        try:
            rank = _official_current_rank(pid)
        except Exception:
            rank = None
        if rank is not None:
            out[str(pid)] = rank
    return out
def _build_own_official_ranks_strict(available_ids: list) -> dict:
    """PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17: bouwt
    het REGLEMENT-dict voor ONZE spelers, UITSLUITEND op basis van het echte
    officiële klassement — GEEN fallback naar padelstat meer."""
    out = {}
    for pid in available_ids:
        try:
            rank = _official_current_rank(pid)
        except Exception:
            rank = None
        if rank is not None:
            out[pid] = rank
    return out
def _render_official_rank_warning(available_ids: list, official_ranks_strict: dict, name_lookup: dict) -> None:
    """Toont EXPLICIET welke spelers geen gekend officieel klassement hebben."""
    missing = ll.has_missing_official_rank(available_ids, official_ranks_strict)
    if missing:
        namen = ", ".join(name_lookup.get(pid, pid) for pid in missing)
        st.warning(
            f"⚠️ Officieel klassement onbekend voor: **{namen}**. Voor deze speler(s) kan de "
            "reglementaire bordvolgorde (sterkste duo eerst) en de puntengrens per rotatie NIET "
            "betrouwbaar geverifieerd worden — ze worden voor deze berekening als 0 punten "
            "meegeteld, wat de uitkomst kan vertekenen. Ververs het klassement van deze speler(s) "
            "voor een betrouwbaar resultaat."
        )
def _format_points_bounds_diagnostic(rules, diagnostics) -> str:
    """Geeft, indien beschikbaar, de daadwerkelijk BEREKENDE punten-per-
    rotatie terug (min en max over alle doorgerekende kandidaten), naast de
    toegelaten grens van de gekozen afdeling."""
    if rules is None or not diagnostics:
        return ""
    seen = diagnostics.get("rotation_points_seen") or []
    if not seen:
        return ""
    lo, hi = rules["punten_min"], rules["punten_max"]
    pmin, pmax = min(seen), max(seen)
    excluded = diagnostics.get("candidates_excluded_by_rules", 0)
    total = diagnostics.get("candidates_total", 0)
    return (
        f"Van de {total} doorgerekende koppelverdeling(en) vielen er {excluded} buiten de toegelaten "
        f"puntengrens per rotatie (**{lo}–{hi}**). De berekende punten per rotatie voor deze "
        f"spelers/dit scenario lagen tussen **{pmin:.0f}** en **{pmax:.0f}**."
    )
# ─────────────────────────────────────────────
# Reglement-selector
# ─────────────────────────────────────────────
def _load_saved_rules_selection(sel_player_id: str) -> dict:
    """Leest de laatst gekozen tornooi/categorie/afdeling terug uit het
    player_profiles-document van de bekeken speler."""
    try:
        profile = fb.get_player_profile(sel_player_id) or {}
    except Exception:
        profile = {}
    return profile.get("lineup_rules_selection") or {}
def _save_rules_selection(sel_player_id: str, tournament: str, category: str, afdeling) -> None:
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(sel_player_id)).set(
            {"lineup_rules_selection": {"tournament": tournament, "category": category, "afdeling": afdeling}},
            merge=True,
        )
    except Exception:
        pass
def _render_tournament_rules_selector(ploeg_id: str, sel_player_id: str):
    """Toont het toegelaten klassementsbereik in het afdeling-label
    (bv. "Afdeling 5 (P100–P300)") en onthoudt de keuze per bekeken speler."""
    if tr is None:
        st.caption("⚠️ tournament_rules.py niet gevonden — reglement-gebaseerde puntenfilter niet beschikbaar.")
        return None, None
    saved = _load_saved_rules_selection(sel_player_id)
    with st.expander("📖 Reglement / afdeling (bepaalt de toegelaten puntengrenzen per rotatie)", expanded=False):
        tournaments = tr.list_tournaments()
        default_tournament = saved.get("tournament") if saved.get("tournament") in tournaments else tr.DEFAULT_TOURNAMENT
        default_tournament_idx = tournaments.index(default_tournament) if default_tournament in tournaments else 0
        tournament = st.selectbox(
            "Tornooi", tournaments, index=default_tournament_idx, key=f"rules_tournament_{ploeg_id}",
            help="Vandaag enkel Padel Senior Cup volledig ingevuld.",
        )
        categories = tr.list_categories(tournament)
        if not categories:
            st.warning(f"Nog geen categorieën ingevuld voor '{tournament}'.")
            return None, None
        default_category = saved.get("category") if saved.get("category") in categories else tr.DEFAULT_CATEGORY
        default_cat_idx = categories.index(default_category) if default_category in categories else 0
        category = st.selectbox("Categorie", categories, index=default_cat_idx, key=f"rules_category_{ploeg_id}")
        afdelingen = tr.list_afdelingen(tournament, category)
        if not afdelingen:
            st.warning(f"Nog geen afdelingen ingevuld voor '{tournament}' / {category}.")
            return None, None
        def _afdeling_label(a):
            a_rules = tr.get_afdeling_rules(tournament, category, a)
            if a_rules:
                return f"Afdeling {a} (P{a_rules['klassement_min']}–P{a_rules['klassement_max']})"
            return f"Afdeling {a}"
        default_afdeling = saved.get("afdeling") if saved.get("afdeling") in afdelingen else None
        default_afd_idx = afdelingen.index(default_afdeling) if default_afdeling in afdelingen else 0
        afdeling = st.selectbox(
            "Afdeling", afdelingen, index=default_afd_idx, key=f"rules_afdeling_{ploeg_id}",
            format_func=_afdeling_label,
        )
        rules = tr.get_afdeling_rules(tournament, category, afdeling)
        st.caption(tr.format_rules_caption(tournament, category, afdeling, rules))
        if saved.get("tournament") != tournament or saved.get("category") != category or saved.get("afdeling") != afdeling:
            _save_rules_selection(sel_player_id, tournament, category, afdeling)
        return rules, f"{tournament} — {category}, afdeling {afdeling}"
# ─────────────────────────────────────────────
# Tegenstander-referentie
# ─────────────────────────────────────────────
def _render_previous_opponent_lineup(bundle: dict) -> None:
    previous_fixtures = bundle.get("previous_fixtures") or []
    if not previous_fixtures:
        return
    with st.expander(f"📋 Tegenstander — eerdere ontmoeting(en) ter referentie ({len(previous_fixtures)})", expanded=False):
        st.caption(
            "De opstelling die de TEGENSTANDER gebruikte in hun vorige, al gespeelde wedstrijd(en) dit "
            "seizoen. 'Match' is de vermoedelijke volgorde zoals de dubbels op het uitslagenblad staan."
        )
        toonde_iets = False
        for fx_bundle in previous_fixtures:
            fx = fx_bundle.get("fixture", {}) or {}
            boards = fx_bundle.get("boards") or []
            if fx_bundle.get("error"):
                st.warning(f"{fx.get('date_text', '?')}: {fx_bundle['error']}")
                continue
            if not boards:
                continue
            toonde_iets = True
            st.markdown(f"**{fx.get('date_text', '?')}**")
            rows = []
            for b in sorted(boards, key=lambda x: x.get("board_position") or 0):
                pair = b.get("opponent_pair") or []
                if len(pair) != 2:
                    continue
                namen = " / ".join(p.get("name", "?") for p in pair)
                rankings = [p.get("ranking") for p in pair if p.get("ranking")]
                rows.append({
                    "Match": f"Match {b.get('board_position', '?')}", "Koppel": namen,
                    "Klassement": " / ".join(rankings) if rankings else "onbekend",
                    "Score": b.get("score") or "onbekend",
                })
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
        if not toonde_iets:
            st.info("Geen match-detail beschikbaar voor de gekende eerdere ontmoeting(en).")
def _render_match1_frequency_opponent(bundle: dict) -> None:
    """Toont, voor elke TEGENSTANDER-speler, hoe vaak die de EERSTE match van
    een rotatie speelde (Match 1, 3, ...) versus de TWEEDE (Match 2, 4, ...)."""
    previous_fixtures = bundle.get("previous_fixtures") or []
    boards_met_positie = [
        b for fx in previous_fixtures for b in (fx.get("boards") or [])
        if b.get("board_position") is not None and len(b.get("opponent_pair") or []) == 2
    ]
    if not boards_met_positie:
        return
    tellingen, namen = {}, {}
    for b in boards_met_positie:
        pos = b["board_position"]
        is_eerste_match_van_rotatie = (pos % 2 == 1)
        for p in b["opponent_pair"]:
            uid = p.get("user_id")
            if not uid:
                continue
            namen[uid] = p.get("name", uid)
            tellingen.setdefault(uid, {"match1": 0, "match2": 0})
            if is_eerste_match_van_rotatie:
                tellingen[uid]["match1"] += 1
            else:
                tellingen[uid]["match2"] += 1
    with st.expander(
        f"📊 Tegenstander — match 1 / match 2-frequentie per rotatie (over {len(previous_fixtures)} eerdere ontmoeting(en))",
        expanded=False,
    ):
        st.caption(
            "Hoe vaak elke tegenstander-speler de EERSTE match van een rotatie speelde (Match 1, "
            "Match 3, ...) versus de TWEEDE match van een rotatie (Match 2, Match 4, ...), in hun "
            "eerdere, gekende wedstrijden dit seizoen. Puur beschrijvend — geen voorspelling."
        )
        if len(previous_fixtures) <= 1:
            st.caption("⚠️ Slechts 1 eerdere ontmoeting gekend — gebaseerd op één enkel datapunt.")
        rows = []
        for uid, counts in sorted(tellingen.items(), key=lambda kv: -kv[1]["match1"]):
            totaal = counts["match1"] + counts["match2"]
            pct1 = round(100 * counts["match1"] / totaal, 0) if totaal else 0
            pct2 = round(100 * counts["match2"] / totaal, 0) if totaal else 0
            rows.append({
                "Speler": namen.get(uid, uid),
                "Match 1 (of 3, 5, ...)": f"{counts['match1']}x ({int(pct1)}%)",
                "Match 2 (of 4, 6, ...)": f"{counts['match2']}x ({int(pct2)}%)",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
def _most_recent_opponent_player_ids(bundle: dict) -> set:
    previous_fixtures = bundle.get("previous_fixtures") or []
    if not previous_fixtures:
        return set()
    most_recent = previous_fixtures[-1]
    boards = most_recent.get("boards") or []
    ids = set()
    for b in boards:
        for p in (b.get("opponent_pair") or []):
            uid = p.get("user_id")
            if uid:
                ids.add(str(uid))
    return ids
# ─────────────────────────────────────────────
# Rotatieplanner - combinatoriek
# ─────────────────────────────────────────────
def _count_perfect_matchings(n: int) -> int:
    if n < 2 or n % 2 != 0:
        return 0
    result = 1
    k = n - 1
    while k > 0:
        result *= k
        k -= 2
    return result
_ROTATION_EXHAUSTIVE_LIMIT = 400
def _generate_rotation_candidates(
    available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
    opponent_boards=None, player_ratings=None, opponent_ratings=None,
    max_results=10, tournament_rules_dict=None,
):
    """Geeft een DERDE returnwaarde terug (`diagnostics`, kan None zijn bij
    n<2), zodat _render_rotation_planner() bij 0 kandidaten kan tonen wat er
    berekend werd."""
    n = len(available_ids)
    if n < 2 or n % 2 != 0:
        return [], 0, None
    total_possible = _count_perfect_matchings(n)
    top_n = min(max(total_possible, 1), _ROTATION_EXHAUSTIVE_LIMIT)
    required = {pid: 1 for pid in available_ids}
    results = []
    diagnostics = None
    if opponent_boards and player_ratings is not None:
        raw, truncated, diagnostics = ll.optimize_lineup_vs_scenario(
            available_ids, required, synergy_fn, opponent_boards, player_ratings,
            player_official_ranks=official_ranks_strict, opponent_ratings=opponent_ratings,
            top_n=top_n, candidate_pool=_ROTATION_EXHAUSTIVE_LIMIT,
            tournament_rules_dict=tournament_rules_dict,
        )
        for option in raw:
            pairs = [frozenset(a["our_pair"]) for a in option["assignment"]]
            if any(p in excluded_pairs for p in pairs):
                continue
            results.append({
                "expected_boards_won": option["expected_boards_won"],
                "score": option["total_score"],
                "ordered_pairs": pairs,
                "assignment": option["assignment"],
                "rotations": option.get("rotations"),
            })
    else:
        raw, truncated = ll.optimize_lineup(available_ids, required, synergy_fn, top_n=top_n)
        rotation_points_seen = []
        excluded_by_rules = 0
        for score, pairs in raw:
            pairs_fs = [frozenset(p) for p in pairs]
            if any(p in excluded_pairs for p in pairs_fs):
                continue
            rotation_eval = ll.filter_and_order_lineup_by_rotations(pairs_fs, official_ranks_strict, rules=tournament_rules_dict)
            for rot in rotation_eval["rotations"]:
                if rot.get("total_points") is not None:
                    rotation_points_seen.append(rot["total_points"])
            if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
                excluded_by_rules += 1
                continue
            results.append({
                "expected_boards_won": None, "score": score,
                "ordered_pairs": rotation_eval["ordered_pairs"], "assignment": None,
                "rotations": rotation_eval["rotations"],
            })
        diagnostics = {
            "candidates_total": len(raw),
            "candidates_excluded_by_rules": excluded_by_rules,
            "rotation_points_seen": rotation_points_seen,
        }
    results.sort(key=lambda r: (-(r["expected_boards_won"] if r["expected_boards_won"] is not None else -1), -r["score"]))
    return results[:max_results], total_possible, diagnostics
def _lineup_options_for_ai(candidates: list, name_lookup: dict) -> list:
    out = []
    for cand in candidates:
        assignment = []
        if cand["assignment"]:
            for a in cand["assignment"]:
                assignment.append({
                    "our_pair": tuple(a["our_pair"]), "synergy": a.get("synergy", 0.0),
                    "edge": a.get("edge", 0.0), "opponent_board": a.get("opponent_board", {}),
                })
        else:
            for pair in cand["ordered_pairs"]:
                p1, p2 = tuple(pair)
                assignment.append({"our_pair": (p1, p2), "synergy": 0.0, "edge": 0.0, "opponent_board": {"opponent_pair": []}})
        out.append({"total_score": cand["score"], "assignment": assignment})
    return out
def _render_rotation_points_caption(rotations: list) -> None:
    if not rotations:
        return
    for i, rot in enumerate(rotations, start=1):
        if rot.get("total_points") is None:
            continue
        icon = "✅" if rot.get("valid", True) else "❌"
        st.caption(f"{icon} Rotatie {i}: {rot.get('reason', '')}")
_WIN_PROB_DISCLAIMER = (
    "⚠️ De winkans-schatting is een RUWE HEURISTIEK (een logistische functie op het "
    "ratingverschil), GEEN gevalideerd of empirisch getoetst voorspellingsmodel — gebruik dit als "
    "richtinggevend signaal, niet als harde garantie."
)
def _render_assignment_with_outcome(assignment: list, name_lookup_global: dict) -> None:
    for a in assignment:
        p1, p2 = a["our_pair"]
        opp_pair = a["opponent_board"]["opponent_pair"]
        opp_names = " / ".join(p.get("name", "?") for p in opp_pair)
        wp = a.get("win_probability")
        risk = a.get("risk_note", "")
        our_r = a.get("our_effective_rating")
        their_r = a.get("their_effective_rating")
        if wp is not None:
            wp_txt = f"**{int(round(wp * 100))}% winkans** ({risk})"
        else:
            wp_txt = "winkans onbekend (onvoldoende rating-data)"
        rating_txt = ""
        if our_r is not None and their_r is not None:
            rating_txt = f" — inschatting {our_r:.0f} vs {their_r:.0f}"
        st.write(
            f"**{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
            f"(synergie {a['synergy']}) — vs **{opp_names}**: {wp_txt}{rating_txt}"
        )
def _render_rotation_planner(
    available_ids, synergy_fn, official_ranks_strict, name_lookup_global, opp,
    opponent_boards=None, player_ratings=None, opponent_ratings=None,
    report_for_ai=None, tournament_rules_dict=None, rules_label=None,
):
    st.markdown('<div class="section-header">🔁 Rotatieplanner</div>', unsafe_allow_html=True)
    regel_tekst = f" (volgens {rules_label})" if rules_label else ""
    st.caption(
        "Alle mogelijke koppelverdelingen voor de eerstvolgende rotatie, gerangschikt op VERWACHT "
        "AANTAL GEWONNEN MATCHEN (niet op een abstract scoregetal). Klik aan wie/welke combinatie "
        "effectief speelde om door te gaan naar de volgende rotatie. Het duo met de hoogste SOM van "
        f"de 2 OFFICIËLE klassementen staat steeds op Match 1{regel_tekst} — de winkans-simulatie "
        "gebruikt daarnaast de padelstats.be playing strength waar bekend."
    )
    st.caption(_WIN_PROB_DISCLAIMER)
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)
    if len(available_ids) < 2 or len(available_ids) % 2 != 0:
        st.info("Selecteer een even aantal spelers om de rotatieplanner te gebruiken.")
        return
    ploeg_id = opp["ploeg_id"]
    locked_key = f"rot_locked_v3_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if locked_key not in st.session_state:
        st.session_state[locked_key] = []
    locked_rotations = st.session_state[locked_key]
    for rot_idx, pairs in enumerate(locked_rotations, start=1):
        st.markdown(f"**Rotatie {rot_idx} (bevestigd):**")
        for match_idx, pair in enumerate(pairs, start=1):
            p1, p2 = tuple(pair)
            st.write(f"Match {match_idx}: {name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}")
        if st.button(f"✏️ Rotatie {rot_idx} wijzigen", key=f"rot_edit_v3_{ploeg_id}_{rot_idx}"):
            st.session_state[locked_key] = locked_rotations[: rot_idx - 1]
            st.rerun()
        st.markdown("---")
    excluded_pairs = {p for rot in locked_rotations for p in rot}
    next_rotation_num = len(locked_rotations) + 1
    candidates, total_possible, rotation_diagnostics = _generate_rotation_candidates(
        available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
        opponent_boards=opponent_boards, player_ratings=player_ratings,
        opponent_ratings=opponent_ratings, max_results=15,
        tournament_rules_dict=tournament_rules_dict,
    )
    if not candidates:
        if total_possible == 0:
            st.info("Geen geldige koppelverdeling meer mogelijk.")
        elif tournament_rules_dict is not None:
            st.warning(
                f"Geen enkele van de {total_possible} mogelijke koppelverdelingen valt binnen de "
                "toegelaten puntengrens per rotatie voor de gekozen afdeling — of alle zijn al "
                "gebruikt. Overweeg een andere afdeling of spelersselectie."
            )
            diag_msg = _format_points_bounds_diagnostic(tournament_rules_dict, rotation_diagnostics)
            if diag_msg:
                st.caption(diag_msg)
        else:
            st.warning(f"Alle {total_possible} mogelijke koppelverdelingen zijn al gebruikt in eerdere rotaties.")
        return
    st.markdown(f"**Rotatie {next_rotation_num} - kies de effectieve/geplande combinatie:**")
    if tournament_rules_dict is not None:
        st.caption(f"{len(candidates)} van {total_possible} combinaties voldoen aan de puntengrens per rotatie.")
    option_labels = []
    for i, cand in enumerate(candidates):
        parts = []
        for match_idx, pair in enumerate(cand["ordered_pairs"], start=1):
            p1, p2 = tuple(pair)
            parts.append(f"M{match_idx}: {name_lookup_global.get(p1,p1)}/{name_lookup_global.get(p2,p2)}")
        prefix = "★ " if i == 0 else ""
        ebw = cand.get("expected_boards_won")
        ebw_txt = f" (verwacht {ebw:.2f} gewonnen matchen)" if ebw is not None else f" (score {cand['score']:.3f})"
        option_labels.append(f"{prefix}{' | '.join(parts)}{ebw_txt}")
    chosen_idx = st.radio(
        "Combinaties", list(range(len(candidates))), format_func=lambda i: option_labels[i],
        key=f"rot_choice_v3_{ploeg_id}_{next_rotation_num}", label_visibility="collapsed",
    )
    chosen = candidates[chosen_idx]
    _render_rotation_points_caption(chosen.get("rotations"))
    if chosen["assignment"]:
        with st.expander("Detail van de gekozen combinatie (winkans per match)", expanded=True):
            _render_assignment_with_outcome(chosen["assignment"], name_lookup_global)
    ai_key = f"rot_ai_v3_{ploeg_id}_{next_rotation_num}"
    if taa is not None and report_for_ai is not None:
        if st.button("🤖 AI-inzicht over deze combinaties", key=f"rot_ai_btn_v3_{ploeg_id}_{next_rotation_num}"):
            with st.spinner("AI analyseert de combinaties..."):
                try:
                    ai_options = _lineup_options_for_ai(candidates[:5], name_lookup_global)
                    st.session_state[ai_key] = taa.analyze_lineup_options(report_for_ai, ai_options, name_lookup_global)
                except Exception as exc:
                    st.session_state[ai_key] = f"⚠️ Mislukt: {exc}"
        if st.session_state.get(ai_key):
            st.markdown(st.session_state[ai_key])
    if st.button(f"✅ Bevestig rotatie {next_rotation_num}", key=f"rot_confirm_v3_{ploeg_id}_{next_rotation_num}", type="primary"):
        st.session_state[locked_key] = locked_rotations + [chosen["ordered_pairs"]]
        st.rerun()
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_ALL_VALID_MATCHUPS_FLAT_LIST_2026-09-18
# Alle geldige "wij vs zij"-matchups: platte lijst, ontdubbeld, gesorteerd
# ─────────────────────────────────────────────
_SCENARIO_CANDIDATE_POOL = 400
_SCENARIO_SAVE_TOP_N = 400
_THEORETICAL_MAX_VARIANTS = 300
_MATCHUP_DISPLAY_DEFAULT_N = 15
_MAX_TOTAL_MATCHUPS = 800


def _aggregate_scenario_scores(scenarios: list) -> list:
    """Historisch overgebleven, sinds PADEL_ANALYSIS_LABEL_PERSIST_TEXT_
    MERGE_CLEANUP_2026-09-18 niet meer aangeroepen vanuit de UI (Kim:
    "aggregaatscore lijkt me nutteloos, mag weg"). Blijft gedefinieerd,
    ongebruikt, voor het geval een toekomstige feature dit alsnog nodig
    heeft."""
    scores_by_combo: dict = {}
    for entry in scenarios:
        for option in (entry.get("results") or []):
            pairs = sorted(tuple(sorted(a["our_pair"])) for a in option.get("assignment", []) or [])
            if not pairs:
                continue
            combo_key = tuple(pairs)
            metric = option.get("expected_boards_won", option.get("total_score"))
            scores_by_combo.setdefault(combo_key, []).append(metric)
    aggregated = []
    for combo_key, scores in scores_by_combo.items():
        aggregated.append((combo_key, {
            "avg": sum(scores) / len(scores), "min": min(scores), "max": max(scores), "count": len(scores),
        }))
    aggregated.sort(key=lambda item: (-item[1]["count"], -item[1]["avg"]))
    return aggregated


def _historical_opponent_boards_list(bundle: dict) -> list:
    """Geeft een lijst van (label, boards) terug voor elke historische
    (al gespeelde) opstelling van de tegenstander (bundle["previous_fixtures"]).
    ALTIJD meegenomen, ONGEACHT welke tegenstander-roster momenteel gekozen
    is voor de theoretische verkenning — Kim: 'de opstelling van vorige keer
    moet je kunnen aanduiden', dus die moet sowieso in de lijst zitten."""
    out = []
    for fx_bundle in bundle.get("previous_fixtures", []) or []:
        boards = fx_bundle.get("boards") or []
        fx = fx_bundle.get("fixture", {}) or {}
        if fx_bundle.get("error") or not boards:
            continue
        label = fx.get("date_text") or "onbekende datum"
        out.append((label, boards))
    return out


def _opponent_lineup_key(boards: list):
    """Structurele sleutel voor een tegenstander-opstelling: een frozenset
    van frozensets van user_id's per bord, ONAFHANKELIJK van bordvolgorde
    (de bordvolgorde ligt sowieso al vast via de officiële regel zodra de
    paren bekend zijn — twee opstellingen met dezelfde spelersparen zijn dus
    altijd dezelfde opstelling, ongeacht de volgorde waarin de borden hier
    aangeleverd worden). Geeft None terug bij een lege/ongeldige boards-lijst
    (nooit een lege frozenset als 'geldige' sleutel laten doorgaan, want dat
    zou verschillende 'niets'-gevallen ten onrechte laten samenvallen)."""
    pairs = []
    for b in boards:
        uids = frozenset(str(p.get("user_id")) for p in (b.get("opponent_pair") or []) if p.get("user_id"))
        if len(uids) == 2:
            pairs.append(uids)
    if not pairs:
        return None
    return frozenset(pairs)


def _collect_unique_opponent_lineups(historical_boards_with_labels: list, theoretical_boards: list) -> dict:
    """Verzamelt ALLE te overwegen tegenstander-opstellingen (historisch +
    theoretisch), ÉÉN keer per structureel unieke opstelling. Een opstelling
    die zowel historisch gespeeld werd ALS in de theoretische enumeratie
    voorkomt, wordt EENMALIG behandeld en als historisch gemarkeerd (met alle
    historische labels/data verzameld) — dat voorkomt precies het "ik zie 3x
    dezelfde opstelling"-effect dat Kim meldde.
    Returns {key: {"boards": [...], "is_historical": bool, "historical_labels": [...]}}."""
    unique: dict = {}
    for label, boards in historical_boards_with_labels:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        entry = unique.setdefault(key, {"boards": boards, "is_historical": False, "historical_labels": []})
        entry["is_historical"] = True
        entry["historical_labels"].append(label)
    for boards in theoretical_boards:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        if key not in unique:
            unique[key] = {"boards": boards, "is_historical": False, "historical_labels": []}
        # Staat de key al (via historisch), dan NIET overschrijven — de
        # historische boards (met score/resultaat) blijven behouden i.p.v.
        # vervangen te worden door de kalere, theoretisch-gegenereerde versie.
    return unique


def _matchup_key(our_pairs: list, their_key) -> tuple:
    """Structurele sleutel voor een VOLLEDIGE matchup (onze koppelverdeling +
    hun koppelverdeling samen), gebruikt om identieke matchups te ontdubbelen
    die toevallig via 2 verschillende tegenstander-opstellingen tot stand
    kwamen (zeldzaam, maar mogelijk bij symmetrische roster-keuzes)."""
    our_key = frozenset(frozenset(p) for p in our_pairs)
    return (our_key, their_key)


def _build_all_valid_matchups(
    unique_opponent_lineups: dict,
    available_ids: list, max_per_player: dict, synergy_fn,
    player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
    tournament_rules_dict,
) -> tuple:
    """PADEL_ANALYSIS_ALL_VALID_MATCHUPS_FLAT_LIST_2026-09-18: de kern van de
    fix. Berekent, voor ELKE unieke tegenstander-opstelling, ALLE (niet enkel
    de beste) reglementair geldige eigen tegenzetten, en voegt dit samen tot
    ÉÉN PLATTE LIJST van volledige matchups — NIET gegroepeerd per
    tegenstander-scenario zoals de vorige (onvoldoende) versies deden.

    Elke matchup-dict bevat: {"assignment", "expected_boards_won",
    "total_score", "rotations", "is_historical", "historical_labels"}.

    Ontdubbelt matchups op (onze koppelverdeling + hun koppelverdeling)
    samen, en sorteert de volledige lijst op verwachte-matchen-gewonnen,
    AFLOPEND (fallback op total_score als expected_boards_won ontbreekt).

    Stopt bij _MAX_TOTAL_MATCHUPS (performance-limiet bij zeer grote
    rosters) — geeft dan truncated=True terug zodat de UI dat kan melden.

    Returns (matchups_gesorteerd, truncated, total_seen)."""
    seen_matchup_keys = set()
    all_matchups = []
    total_seen = 0
    truncated = False

    for their_key, info in unique_opponent_lineups.items():
        if truncated:
            break
        boards = info["boards"]
        results, _trunc, _diag = ll.optimize_lineup_vs_scenario(
            available_ids, max_per_player, synergy_fn, boards, player_ratings,
            player_official_ranks=official_ranks_strict, opponent_ratings=opponent_ratings,
            top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
            tournament_rules_dict=tournament_rules_dict,
        )
        for option in results:
            total_seen += 1
            our_pairs = [a["our_pair"] for a in option["assignment"]]
            mkey = _matchup_key(our_pairs, their_key)
            if mkey in seen_matchup_keys:
                continue
            seen_matchup_keys.add(mkey)
            all_matchups.append({
                "assignment": option["assignment"],
                "expected_boards_won": option.get("expected_boards_won"),
                "total_score": option.get("total_score"),
                "rotations": option.get("rotations"),
                "is_historical": info["is_historical"],
                "historical_labels": list(info["historical_labels"]),
            })
            if len(all_matchups) >= _MAX_TOTAL_MATCHUPS:
                truncated = True
                break

    def _sort_key(m):
        ebw = m.get("expected_boards_won")
        return ebw if ebw is not None else m.get("total_score", 0.0)

    all_matchups.sort(key=_sort_key, reverse=True)
    return all_matchups, truncated, total_seen


def _format_opponent_lineup_label(boards: list) -> str:
    return " | ".join(" + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards)


def _render_all_valid_matchups(
    bundle, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, sel_player_id, tournament_rules_dict=None, rules_label=None,
):
    """PADEL_ANALYSIS_ALL_VALID_MATCHUPS_FLAT_LIST_2026-09-18 (op verzoek van
    Kim, 3x verduidelijkt): toont ALLE geldige "wij vs zij"-matchups als ÉÉN
    platte, gesorteerde lijst — zie de uitgebreide toelichting in de
    moduledocstring bovenaan dit bestand voor de volledige achtergrond en
    waarom de 2 eerdere pogingen ontoereikend waren."""
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "ALLE reglementair geldige combinaties van onze opstelling tegen hun opstelling, in ÉÉN lijst, "
        "gesorteerd van hoogste naar laagste verwachte winstkans. De opstelling die de tegenstander "
        "vorige keer effectief speelde is gemarkeerd."
    )

    # ── Historische tegenstander-opstellingen: ALTIJD beschikbaar ──
    historical_boards_with_labels = _historical_opponent_boards_list(bundle)

    # ── Theoretische tegenstander-opstellingen: op basis van een zelf
    # gekozen roster, met een expliciete "(her)bereken"-knop (kan zwaar
    # zijn bij een grote roster) ──
    st.markdown("##### 🎯 Tegenstander-roster voor theoretische scenario's")
    st.caption(
        "Kies WIE van de tegenstander waarschijnlijk beschikbaar is. We berekenen dan ALLE mogelijke "
        "opstellingen die zij daaruit kunnen vormen (officiële regel: hun sterkste duo — som van "
        "klassementen — op Match 1) en voegen die toe aan de lijst hieronder."
    )
    unique_players = bundle.get("unique_players", []) or []
    theoretical_boards: list = []
    if not unique_players:
        st.info("Nog geen tegenstander-spelers gekend om theoretische opstellingen voor te berekenen.")
    else:
        opp_labels = [p.get("name", "?") for p in unique_players]
        opp_label_to_id = {p.get("name", "?"): str(p.get("user_id")) for p in unique_players}
        default_ids = _most_recent_opponent_player_ids(bundle)
        if default_ids:
            default_opp_labels = [lbl for lbl, pid in opp_label_to_id.items() if pid in default_ids]
            st.caption(
                f"Standaard geselecteerd: de {len(default_opp_labels)} speler(s) uit hun meest recente "
                "gekende ontmoeting. Verklein/verruim deze lijst om verder te verfijnen."
            )
        else:
            default_opp_labels = opp_labels[: min(2 * total_boards, len(opp_labels))]
        chosen_opp_labels = st.multiselect(
            "Beschikbare tegenstander-spelers", opp_labels, default=default_opp_labels,
            key=f"theoretical_opp_players_{opp['ploeg_id']}",
        )
        chosen_opp_ids = [opp_label_to_id[lbl] for lbl in chosen_opp_labels]
        needed = 2 * total_boards
        if len(chosen_opp_ids) < needed:
            st.info(
                f"Selecteer minstens {needed} tegenstander-speler(s) ({total_boards} wedstrijden — zie "
                "'Aantal wedstrijden deze ontmoeting' hierboven) om theoretische scenario's toe te voegen. "
                "De historische opstelling(en) hierboven blijven sowieso al in de lijst staan."
            )
        else:
            chosen_opp_players = [p for p in unique_players if str(p.get("user_id")) in chosen_opp_ids]
            opponent_official_ranks = _opponent_official_ranks(chosen_opp_ids)
            missing_opp_official = [pid for pid in chosen_opp_ids if pid not in opponent_official_ranks]
            if missing_opp_official:
                opp_names = [p.get("name", pid) for p in chosen_opp_players if str(p.get("user_id")) in missing_opp_official]
                st.caption(
                    f"ℹ️ Geen officieel klassement gekend voor: {', '.join(opp_names)} — behandeld als "
                    "'onbekende sterkte' bij het genereren van theoretische opstellingen."
                )
            lineups, meta = ll.generate_all_opponent_lineups(
                chosen_opp_players, total_boards, opponent_official_ranks=opponent_official_ranks,
                max_variants=_THEORETICAL_MAX_VARIANTS,
            )
            if meta["resting_combinations"] > 1:
                st.caption(
                    f"🔢 {len(chosen_opp_ids)} beschikbare speler(s), {needed} nodig -> {meta['resting_combinations']} "
                    f"keuzes wie rust × koppelverdelingen = **{meta['total_theoretical']}** theoretische opstellingen."
                )
            else:
                st.caption(f"🔢 **{meta['total_theoretical']}** theoretische opstellingen mogelijk.")
            if meta["truncated"]:
                st.warning(f"⚠️ Enkel de eerste {_THEORETICAL_MAX_VARIANTS} van {meta['total_theoretical']} worden berekend.")
            if lineups:
                compute_key = f"theoretical_boards_{opp['ploeg_id']}"
                sig_key = f"theoretical_boards_sig_{opp['ploeg_id']}"
                signature = (tuple(sorted(chosen_opp_ids)), int(total_boards))
                needs_compute = st.session_state.get(sig_key) != signature
                recompute_clicked = st.button(
                    "🔄 Theoretische scenario's (her)berekenen", key=f"theoretical_recompute_{opp['ploeg_id']}", type="primary",
                )
                if needs_compute and compute_key in st.session_state:
                    st.info("De selectie is gewijzigd — klik hierboven om opnieuw te berekenen.")
                if recompute_clicked:
                    st.session_state[compute_key] = lineups
                    st.session_state[sig_key] = signature
                theoretical_boards = st.session_state.get(compute_key) or []

    # ── Samenvoegen tot unieke tegenstander-opstellingen ──
    unique_opponent_lineups = _collect_unique_opponent_lineups(historical_boards_with_labels, theoretical_boards)
    if not unique_opponent_lineups:
        st.info("Nog geen tegenstander-opstelling gekend of berekend om tegen te analyseren.")
        return []

    # ── Voor ELKE unieke tegenstander-opstelling: ALLE geldige eigen
    # tegenzetten berekenen, samengevoegd tot ÉÉN platte, gesorteerde lijst ──
    with st.spinner(f"Alle geldige matchups doorrekenen ({len(unique_opponent_lineups)} tegenstander-opstelling(en))..."):
        all_matchups, truncated, total_seen = _build_all_valid_matchups(
            unique_opponent_lineups, available_ids, max_per_player, synergy_fn,
            player_ratings, official_ranks_strict, opponent_ratings, tournament_rules_dict,
        )

    st.divider()
    n_excluded = total_seen - len(all_matchups) if not truncated else None
    if truncated:
        st.warning(
            f"⚠️ Er zijn meer dan {_MAX_TOTAL_MATCHUPS} geldige matchups gevonden — enkel de eerste "
            f"{_MAX_TOTAL_MATCHUPS} (op volgorde van berekening, niet noodzakelijk de beste) zijn "
            "meegenomen. Verklein de spelersselectie voor een volledige dekking."
        )
    st.caption(
        f"**{len(all_matchups)}** geldige matchup(s) gevonden over **{len(unique_opponent_lineups)}** unieke "
        "tegenstander-opstelling(en), gesorteerd van hoogste naar laagste verwachte winstkans."
    )
    if not all_matchups:
        st.info(
            "Geen enkele matchup voldoet aan de reglementaire puntengrens per rotatie. Controleer de "
            "gekozen afdeling, of gebruik de Rotatieplanner om de diagnostiek per combinatie te zien."
        )
        return []

    show_all_key = f"all_matchups_showall_{opp['ploeg_id']}"
    show_all = st.checkbox(
        f"Toon alle {len(all_matchups)} matchups (i.p.v. de beste {_MATCHUP_DISPLAY_DEFAULT_N})",
        key=show_all_key,
    ) if len(all_matchups) > _MATCHUP_DISPLAY_DEFAULT_N else False
    display_matchups = all_matchups if show_all else all_matchups[:_MATCHUP_DISPLAY_DEFAULT_N]

    for rank, matchup in enumerate(display_matchups, start=1):
        ebw = matchup.get("expected_boards_won")
        ebw_txt = f" — verwacht {ebw:.2f} van {len(matchup['assignment'])} matchen gewonnen" if ebw is not None else f" — score {matchup.get('total_score')}"
        st.markdown(f"**#{rank}{ebw_txt}**")
        if matchup["is_historical"]:
            labels_txt = ", ".join(matchup["historical_labels"])
            st.markdown(
                f'<div style="display:inline-block;background-color:#d4edda;color:#155724;'
                f'padding:2px 10px;border-radius:12px;font-size:0.85em;margin-bottom:6px;">'
                f'🟢 Zoals gespeeld op {labels_txt}</div>',
                unsafe_allow_html=True,
            )
        _render_rotation_points_caption(matchup.get("rotations"))
        _render_assignment_with_outcome(matchup["assignment"], name_lookup_global)
        st.markdown("---")

    if not show_all and len(all_matchups) > len(display_matchups):
        st.caption(f"Beste {len(display_matchups)} van {len(all_matchups)} matchups getoond — vink hierboven aan om alles te zien.")

    st.divider()
    if taa is not None and report is not None and st.button("🤖 AI-inzicht over de beste matchups", key=f"all_matchups_ai_{opp['ploeg_id']}"):
        with st.spinner("AI analyseert..."):
            try:
                ai_key = f"all_matchups_ai_result_{opp['ploeg_id']}"
                st.session_state[ai_key] = taa.analyze_lineup_options(report, display_matchups[:5], name_lookup_global)
            except Exception as exc:
                st.session_state[f"all_matchups_ai_result_{opp['ploeg_id']}"] = f"⚠️ Mislukt: {exc}"
    ai_result_key = f"all_matchups_ai_result_{opp['ploeg_id']}"
    if st.session_state.get(ai_result_key):
        st.markdown(st.session_state[ai_result_key])

    if st.button("💾 Deze analyse opslaan (alle getoonde matchups)", key=f"save_all_matchups_{opp['ploeg_id']}"):
        payload = {
            "opponent_name": opp.get("name"), "opponent_ploeg_id": opp.get("ploeg_id"),
            "own_player_ids": available_ids,
            "own_player_labels": [name_lookup_global.get(pid, pid) for pid in available_ids],
            "total_boards": int(total_boards), "max_per_player": max_per_player,
            "scenarios": [
                {
                    "s_idx": rank, "fixture_label": (
                        f"Matchup #{rank}" + (f" (zoals gespeeld op {', '.join(m['historical_labels'])})" if m["is_historical"] else "")
                    ),
                    "boards_count": len(m["assignment"]),
                    "options": [{
                        "total_score": m["total_score"], "expected_boards_won": m.get("expected_boards_won"),
                        "assignment": [
                            {
                                "our_pair_labels": [name_lookup_global.get(a["our_pair"][0], a["our_pair"][0]), name_lookup_global.get(a["our_pair"][1], a["our_pair"][1])],
                                "synergy": a["synergy"], "edge": a["edge"], "win_probability": a.get("win_probability"),
                                "opponent_names": [p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]],
                            } for a in m["assignment"]
                        ],
                    }],
                } for rank, m in enumerate(all_matchups, start=1)
            ],
        }
        doc_id = fb.save_lineup_analysis(sel_player_id, payload)
        st.success(f"Analyse opgeslagen ({len(all_matchups)} matchups).")

    return all_matchups


def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-analyse</div>', unsafe_allow_html=True)
    tournament_rules_dict, rules_label = _render_tournament_rules_selector(opp["ploeg_id"], sel_player_id)
    with st.expander("ℹ️ Wat betekenen winkans, verwachte matchen, synergie en de puntengrens?", expanded=False):
        st.markdown(
            "- **Winkans per match**: een RUWE schatting (logistische functie op het ratingverschil), "
            "gebaseerd op padelstats.be playing strength waar bekend, anders het officiële klassement "
            "als terugval — PER SPELER individueel.\n"
            "- **Verwacht aantal gewonnen matchen**: de som van de winkansen over alle matchen van "
            "die opstelling.\n"
            "- **Synergie**: hoe goed dit koppel historisch samen presteert (confidence-shrinkage).\n"
            "- **Officiële regel (art. 6.6)**: binnen elke ROTATIE speelt het duo met de HOOGSTE SOM "
            "van de 2 OFFICIËLE klassementen (nooit padelstat!) op het laagst genummerde match.\n"
            "- **Puntengrens per rotatie**: de SOM van de officiële klassementen van alle 4 spelers "
            "in 1 rotatie moet binnen de grenzen van de gekozen afdeling liggen — anders uitgesloten.\n"
            "- **🟢 Groene badge**: deze matchup komt overeen met een opstelling die de tegenstander "
            "EFFECTIEF al eens speelde dit seizoen.\n\n"
            + _WIN_PROB_DISCLAIMER
        )
    _render_previous_opponent_lineup(bundle)
    _render_match1_frequency_opponent(bundle)
    own_candidates = sorted(profiles, key=lambda x: x.get("display_name") or "")
    own_labels = [_display_name(p) for p in own_candidates]
    own_label_to_id = {_display_name(p): p.get("player_id") for p in own_candidates}
    recent_ids = _recent_own_lineup_player_ids(sel_player_id, profiles)
    if recent_ids:
        default_labels = [lbl for lbl, pid in own_label_to_id.items() if pid in recent_ids]
        sel_label_self = next((lbl for lbl, pid in own_label_to_id.items() if pid == sel_player_id), None)
        if sel_label_self and sel_label_self not in default_labels:
            default_labels.append(sel_label_self)
        st.caption(f"Standaard vooraf geselecteerd: jullie vorige interclubontmoeting ({len(default_labels)} speler(s)).")
    else:
        default_labels = own_labels[: min(8, len(own_labels))]
    available_labels = st.multiselect("Beschikbare eigen spelers", own_labels, default=default_labels, key="scenario_available_players")
    if len(available_labels) < 2:
        st.info("Selecteer minstens 2 spelers.")
        return
    available_ids = [own_label_to_id[lbl] for lbl in available_labels]
    total_possible_combos = _count_perfect_matchings(len(available_ids))
    if total_possible_combos:
        if total_possible_combos <= _SCENARIO_CANDIDATE_POOL:
            st.caption(f"🔢 **{total_possible_combos}** mogelijke koppelverdelingen — ALLEMAAL doorgerekend per tegenstander-opstelling.")
        else:
            st.caption(f"🔢 **{total_possible_combos}** mogelijke koppelverdelingen — de {_SCENARIO_CANDIDATE_POOL} beste doorgerekend.")
    suggested_boards = max((len(fx.get("boards", [])) for fx in bundle.get("previous_fixtures", [])), default=6) or 6
    c1, c2 = st.columns(2)
    with c1:
        total_boards = st.number_input("Aantal wedstrijden deze ontmoeting", min_value=1, value=int(suggested_boards), step=1)
    with c2:
        st.caption(f"Voorstel: {suggested_boards} wedstrijden.")
    default_max = max(1, -(-2 * total_boards // len(available_ids)))
    cols = st.columns(min(len(available_ids), 6) or 1)
    max_per_player = {}
    for i, pid in enumerate(available_ids):
        with cols[i % len(cols)]:
            max_per_player[pid] = st.number_input(
                name_lookup_global.get(pid, pid), min_value=0, max_value=int(total_boards),
                value=min(default_max, int(total_boards)), step=1, key=f"scenario_max_{pid}",
            )
    total_slots = sum(max_per_player.values())
    if total_slots != 2 * total_boards:
        st.error(f"Speler-plaatsen ({total_slots}) moet gelijk zijn aan 2× wedstrijden ({2*total_boards}).")
        return
    docs_for_synergy = ll.get_docs_for_players(available_ids)
    own_synergy = ll.compute_pairwise_synergy(docs_for_synergy, available_ids)
    synergy_fn = ll.make_pair_score_fn(own_synergy, docs_for_synergy)
    player_ratings = {pid: oa.get_own_player_rating(pid)[0] for pid in available_ids}  # SIMULATIE (padelstat)
    official_ranks_strict = _build_own_official_ranks_strict(available_ids)  # REGLEMENT (uitsluitend officieel)
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)
    opponent_ratings = _opponent_padelstat_ratings(bundle)

    all_matchups = _render_all_valid_matchups(
        bundle, opp, available_ids, max_per_player, int(total_boards), synergy_fn,
        player_ratings, official_ranks_strict, opponent_ratings, report,
        name_lookup_global, sel_player_id,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    ) or []

    st.divider()
    chosen_scenario_boards = None
    if all_matchups:
        # Unieke tegenstander-opstellingen afleiden uit de berekende matchups
        # (voor de Rotatieplanner-basiskeuze), zonder ze een 2de keer te
        # moeten hergenereren.
        seen_labels = set()
        scenario_options = []
        for m in all_matchups:
            their_names = " / ".join(
                a["opponent_board"]["opponent_pair"][0].get("name", "?") + " + " +
                a["opponent_board"]["opponent_pair"][1].get("name", "?")
                for a in m["assignment"][:1]
            ) if m["assignment"] else "?"
            label_key = tuple(sorted(
                frozenset(p.get("name", "?") for p in a["opponent_board"]["opponent_pair"])
                for a in m["assignment"]
            ))
            if label_key in seen_labels:
                continue
            seen_labels.add(label_key)
            boards_for_pick = [a["opponent_board"] for a in m["assignment"]]
            badge = " 🟢" if m["is_historical"] else ""
            scenario_options.append((f"{_format_opponent_lineup_label(boards_for_pick)}{badge}", boards_for_pick))
        scenario_pick_labels = ["Geen (enkel eigen synergie)"] + [s[0] for s in scenario_options]
        scenario_pick = st.selectbox("Matchup-inschatting voor de Rotatieplanner op basis van:", scenario_pick_labels, key=f"rot_scenario_pick_{opp['ploeg_id']}")
        if scenario_pick != scenario_pick_labels[0]:
            idx = scenario_pick_labels.index(scenario_pick) - 1
            chosen_scenario_boards = scenario_options[idx][1]
    _render_rotation_planner(
        available_ids, synergy_fn, official_ranks_strict, name_lookup_global, opp,
        opponent_boards=chosen_scenario_boards, player_ratings=player_ratings,
        opponent_ratings=opponent_ratings, report_for_ai=report,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    )
def _render_saved_lineup_analyses(name_lookup_global: dict):
    st.markdown('<div class="section-header">💾 Opgeslagen opstelling-analyses</div>', unsafe_allow_html=True)
    st.caption("Analyses die je eerder opsloeg.")
    analyses = fb.list_lineup_analyses()
    if not analyses:
        st.info("Nog geen analyses opgeslagen.")
        return
    labels = []
    for a in analyses:
        owner_label = name_lookup_global.get(a.get("owner_player_id"), a.get("owner_player_id"))
        saved_at = _format_scraped_at(a.get("saved_at"))
        labels.append(f"{a.get('opponent_name', '?')} — {owner_label} — {saved_at}")
    chosen = st.selectbox("Kies een opgeslagen analyse", labels, key="saved_analysis_pick")
    idx = labels.index(chosen)
    analysis = analyses[idx]
    st.markdown(f"**Tegenstander:** {analysis.get('opponent_name', '?')}")
    st.caption(f"Opgeslagen op {_format_scraped_at(analysis.get('saved_at'))} · eigen spelers: {', '.join(analysis.get('own_player_labels', []) or [])}")
    for scenario in analysis.get("scenarios", []) or []:
        options = scenario.get("options") or []
        with st.expander(f"{scenario.get('fixture_label', '?')} — {scenario.get('boards_count', 0)} wedstrijden ({len(options)} opties)"):
            if not options:
                st.info("Geen resultaat opgeslagen.")
                continue
            for opt_idx, option in enumerate(options, start=1):
                ebw = option.get("expected_boards_won")
                st.write(f"**Optie {opt_idx}**" + (f" — verwacht {ebw:.2f} matchen gewonnen" if ebw is not None else f" — score {option.get('total_score')}"))
                for a in option.get("assignment", []) or []:
                    pair_labels = a.get("our_pair_labels") or ["?", "?"]
                    opp_names = " / ".join(a.get("opponent_names", []) or [])
                    wp = a.get("win_probability")
                    wp_txt = f", winkans {int(round(wp*100))}%" if wp is not None else ""
                    st.write(f"{pair_labels[0]} / {pair_labels[1]} (synergie {a.get('synergy')}) — vs {opp_names}{wp_txt}")
    if st.button("🗑️ Deze analyse verwijderen", key=f"delete_analysis_{analysis.get('_doc_id')}"):
        fb.delete_lineup_analysis(analysis["_doc_id"])
        st.success("Analyse verwijderd.")
        st.rerun()
def page_lineup_lab():
    st.header("🧩 Opstelling-analyse")
    profiles = _get_all_profiles()
    if not profiles:
        st.info("Nog geen spelers in de database.")
        return
    name_lookup_global = {p.get("player_id"): _display_name(p) for p in profiles}
    profile_map = {_display_name(p): p for p in sorted(profiles, key=lambda x: x.get("display_name") or "")}
    settings = fb.get_app_settings()
    home_id = settings.get("home_player_id")
    home_label = next((lbl for lbl, p in profile_map.items() if p.get("player_id") == home_id), None)
    labels = list(profile_map.keys())
    default_idx = labels.index(home_label) if home_label in labels else 0
    tab_analyse, tab_saved = st.tabs(["🔍 Analyseren", "💾 Opgeslagen analyses"])
    with tab_analyse:
        sel_label = st.selectbox("Toon analyse voor:", labels, index=default_idx, key="lineup_lab_sel_player")
        sel_profile = profile_map[sel_label]
        sel_player_id = sel_profile.get("player_id")
        scout_result = _render_volgende_match_and_scout(str(sel_player_id), sel_label)
        if scout_result:
            bundle, opp, reeks_url, spelgroep_id = scout_result
            report_for_ai = None
            if bundle.get("unique_players"):
                all_docs, global_docs = osu.prepare_team_docs(bundle, str(sel_player_id))
                report_for_ai = oa.get_team_report(bundle, opp, all_docs, current_reeks_url=reeks_url, current_spelgroep_id=spelgroep_id, global_docs=global_docs, key_prefix=f"scout_team_{sel_player_id}")
                report_for_ai = oa.render_team_header(report_for_ai, bundle, opp, all_docs, current_reeks_url=reeks_url, current_spelgroep_id=spelgroep_id, global_docs=global_docs, key_prefix=f"scout_team_{sel_player_id}")
            if report_for_ai is not None:
                oa.render_overview_and_detail(report_for_ai, go_to_player_fn=_go_to_player, key_prefix=f"scout_team_{sel_player_id}")
                st.divider()
            _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, str(sel_player_id), report_for_ai)
            if report_for_ai is not None:
                st.divider()
                oa.render_ai_section(report_for_ai, opp.get("ploeg_id"), key_prefix=f"scout_team_{sel_player_id}")
    with tab_saved:
        _render_saved_lineup_analyses(name_lookup_global)
