"""
page_lineup_lab.py — "🧩 Opstelling-analyse"-pagina (Volgende match,
Opstelling-scenario's, Rotatieplanner, Opgeslagen analyses).
PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14 t.e.m. PADEL_ANALYSIS_TOURNAMENT_
RULES_2026-09-17: zie eerdere versies van dit bestand voor de volledige
geschiedenis (poule-schema laden/persisteren, aggregaatscores, tegenstander-
referentiesecties, theoretische scenario's, reglement-selector).
--------------------------------------------------------------------------
PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17 t.e.m.
PADEL_ANALYSIS_ALL_VALID_MATCHUPS_FLAT_LIST_2026-09-18: zie eerdere versies
voor de volledige geschiedenis (winkans-berekening, puntengrens-diagnostiek,
match1/2-hergroepering, P-rating-labels, samengevoegde scenario-lijst).
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_SAFE_ENUMERATION_2026-09-18 (op verzoek van Kim,
KRITIEKE CORRECTHEIDSFOUT, na de vorige "alle matchups"-fix)
--------------------------------------------------------------------------
Kim's melding, letterlijk: "dit is niet mogelijk. Tim kan niet gelijk in
match 1 en 2 spelen. Match 1 en 2 zijn op hetzelfde moment en match 3 en 4
ook."

ROOT CAUSE (nu volledig begrepen, bevestigd met Kim's eigen voorbeeld):
zowel de vorige _enumerate_all_opponent_pairings() (tegenstander-kant) ALS
lineup_lab.optimize_lineup()/optimize_lineup_vs_scenario() (ONZE kant, via
_build_all_valid_matchups()) kenden elke speler enkel een TOTAAL aantal
matchen toe over de HELE ontmoeting, zonder te controleren of die matchen
wel op VERSCHILLENDE MOMENTEN vallen. Een ontmoeting bestaat uit rotaties
van telkens 2 GELIJKTIJDIGE matchen (art. 8.7.1: match 1+2 = rotatie 1,
match 3+4 = rotatie 2, ...) - een speler kan dus wel meerdere matchen over
VERSCHILLENDE rotaties heen spelen (dat is normaal), maar NOOIT twee keer
BINNEN dezelfde rotatie (die zijn immers gelijktijdig).

Belangrijke, bijkomende vaststelling: dit trof NIET enkel de tegenstander-
kant (Tim, zoals Kim expliciet meldde) maar ook ONZE EIGEN kant op exact
dezelfde manier (in hetzelfde voorbeeld stond "Nico Recour" ook in zowel
Match 1 als Match 2 - hetzelfde probleem, enkel niet expliciet vermeld).

FIX: een nieuwe, rotatie-bewuste enumeratiefunctie
_enumerate_rotation_aware_pairings() vervangt ZOWEL de oude, aparte
tegenstander-enumeratie ALS het gebruik van lineup_lab.optimize_lineup_vs_
scenario() voor onze eigen kant. Deze functie bouwt de ontmoeting ROTATIE
PER ROTATIE op: voor elke rotatie worden exact 4 (of 2, bij een oneven
laatste rotatie) spelers gekozen uit wie nog een match "tegoed" heeft,
verdeeld in paren - GEGARANDEERD geen speler dubbel binnen 1 rotatie. De
bestaande regel "nooit twee keer dezelfde partner" blijft gelden over de
VOLLEDIGE ontmoeting (alle rotaties samen).

Gebruikt nu voor BEIDE kanten (één, correcte bron van waarheid i.p.v. twee
aparte, allebei onvolledige implementaties). De per-match simulatie
(synergie/edge/winkans) gebeurt voortaan lokaal in _compute_matchup(), met
dezelfde publieke lineup_lab-rekenfuncties (effective_simulation_rating,
estimate_win_probability, risk_note_for_probability, matchup_edge) die
lineup_lab.optimize_lineup_vs_scenario() ook al gebruikte - exact dezelfde
formules, nu toegepast op een GEGARANDEERD geldige koppelverdeling in
plaats van op een blind gezochte "beste" combinatie.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_TABLE_2026-09-18 (op verzoek van Kim, na expliciete
bevestiging van een mockup)
--------------------------------------------------------------------------
Kim's feedback op de vorige, per-matchup-tekstblok-weergave: "wat de user
experience betreft: een tabel lijkt handiger. de lijst is nu ook te lang
om handig te vergelijken (...) je kan totaal aantal punten evengoed per
lijn in tabel zetten en dan wel per ploeg. dat is 2 lijnen per case
gespaard. verwachte gewonnen matchen kan ook in tabel, moet niet boven
elke case." + na het tonen van een mockup: "compactere kolombreedte. toon
punten bvb Carl en Nico en toon punten Gregory en tim. Klikken kolomkop
voor sortering filtering." + "Ipv match 1,2,3,4 in titel zou ik Rotatie1-1
en rotatie 1-2 tonen en rotatie 2-1 en rotatie 2-2."

Fix: de per-matchup markdown-tekstblokken zijn vervangen door ÉÉN
st.dataframe-tabel (_matchups_to_table_rows() bouwt de rijen). Kolommen:
  - "#" (rangnummer, ongewijzigd na klik-sortering - net als een
    klassement-rangnummer)
  - "Verwacht" (numeriek, voor correcte numerieke sortering bij een klik
    op de kolomkop - st.dataframe ondersteunt dit ingebouwd, geen extra
    code nodig)
  - "RotX punten (wij/zij)": vervangt de vroegere 2 aparte tekstregels
    ("Rotatie 1: 700 punten", "Rotatie 2: 700 punten") door 1 COMPACTE
    kolom per rotatie, nu met BEIDE teams' punten samen (bv. "✅ 700/700"),
    zoals expliciet gevraagd.
  - "RotatieR-B" (bv. "Rotatie1-1", "Rotatie1-2", "Rotatie2-1",
    "Rotatie2-2" - Kim's exacte gevraagde titelstijl i.p.v. "Match 1/2/3/4"):
    1 compacte cel per match, met BEIDE koppels + hun rating + winkans
    samen (bv. "Carl+Nico (245) vs Gregory+Tim (290): 42%").
  - "Vorige keer": 🟢-markering + datum, of leeg.
Klikbare kolomkop-sortering/filtering komt gratis mee met st.dataframe
(ingebouwd Streamlit-gedrag), geen extra implementatie nodig.
"""
import itertools

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
    toegelaten grens van de gekozen afdeling. (Historisch behouden, sinds
    de tabel-weergave niet meer rechtstreeks aangeroepen vanuit de
    matchup-lijst zelf — blijft bruikbaar voor eventuele toekomstige
    foutmeldingen.)"""
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
# LET OP: dit deel behandelt STEEDS 1 ENKELE rotatie tegelijk (required=1
# per speler), en is daardoor NIET getroffen door de PADEL_ANALYSIS_
# ROTATION_SAFE_ENUMERATION_2026-09-18-bug hierboven (die trad enkel op
# wanneer een speler méérdere matchen over MEERDERE rotaties toegewezen
# kreeg in 1 enkele berekening — hier gebeurt dat nooit: de gebruiker
# bevestigt elke rotatie apart voor de volgende begint). Geen wijzigingen
# nodig aan dit deel.
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
# PADEL_ANALYSIS_ROTATION_SAFE_ENUMERATION_2026-09-18
# Rotatie-bewuste enumeratie: 1 correcte bron van waarheid voor ZOWEL onze
# eigen kant ALS de tegenstander-kant.
# ─────────────────────────────────────────────
def _all_perfect_matchings_generic(seq: list) -> list:
    """Recursieve enumeratie van ALLE manieren om een even-lange lijst te
    verdelen in paren. Zelfstandige, lokale kopie (geen afhankelijkheid van
    de private lineup_lab._all_perfect_matchings) — hier enkel gebruikt
    voor lijsten van 2 of 4 elementen (1 of 2 gelijktijdige matchen per
    rotatie), maar algemeen genoeg voor eender welke even lengte."""
    if len(seq) == 0:
        return [[]]
    if len(seq) % 2 != 0:
        return []
    first, rest = seq[0], seq[1:]
    out: list = []
    for i, partner in enumerate(rest):
        remaining = rest[:i] + rest[i + 1:]
        for sub in _all_perfect_matchings_generic(remaining):
            out.append([frozenset({first, partner})] + sub)
    return out
def _enumerate_rotation_aware_pairings(
    player_ids: list, required_counts: dict, call_budget: int = 300_000,
) -> tuple:
    """PADEL_ANALYSIS_ROTATION_SAFE_ENUMERATION_2026-09-18 (op verzoek van
    Kim, KRITIEKE CORRECTHEIDSFOUT): "Tim kan niet gelijk in match 1 en 2
    spelen. Match 1 en 2 zijn op hetzelfde moment en match 3 en 4 ook."

    Bouwt de ontmoeting ROTATIE PER ROTATIE op (1 rotatie = 2 GELIJKTIJDIGE
    matchen, art. 8.7.1 - of 1 match bij een oneven laatste rotatie): voor
    elke rotatie worden exact 4 (of 2) spelers gekozen uit wie nog een
    match "tegoed" heeft (remaining>0), verdeeld in 1 of 2 paren.
    GEGARANDEERD geen speler dubbel binnen 1 rotatie, want de spelers voor
    1 rotatie worden altijd als DISTINCTE combinatie gekozen. Een speler
    MAG wel over VERSCHILLENDE rotaties heen herhalen (normaal - hij speelt
    dan op een later tijdstip opnieuw); de bestaande regel "nooit twee keer
    dezelfde partner" blijft gelden over de VOLLEDIGE ontmoeting.

    Vervangt zowel de vorige (tegenstander-only) _enumerate_all_opponent_
    pairings() als het gebruik van lineup_lab.optimize_lineup() voor onze
    eigen kant (die laatste was NIET rotatie-bewust) — nu 1 gedeelde,
    correcte functie voor BEIDE kanten.

    required_counts: {player_id: totaal aantal matchen deze speler moet
    spelen over de VOLLEDIGE ontmoeting}.

    Returns (lijst_van_rotatiestructuren, truncated). Elke rotatiestructuur
    is een lijst van rotaties; elke rotatie is een lijst van 1 of 2
    frozensets (2 gelijktijdige paren, of 1 bij een oneven laatste
    rotatie)."""
    total_slots = sum(required_counts.values())
    if total_slots == 0 or total_slots % 2 != 0:
        return [], False
    n_boards = total_slots // 2
    rotation_sizes = []
    remaining_boards = n_boards
    while remaining_boards > 0:
        take = min(2, remaining_boards)
        rotation_sizes.append(take)
        remaining_boards -= take
    results: list = []
    seen_keys = set()
    calls = [0]
    truncated = [False]
    def backtrack(rotation_idx, remaining, used_partner_pairs, rotations_so_far):
        calls[0] += 1
        if calls[0] > call_budget:
            truncated[0] = True
            return
        if rotation_idx == len(rotation_sizes):
            key = tuple(
                tuple(sorted(tuple(sorted(pair)) for pair in rot))
                for rot in rotations_so_far
            )
            if key not in seen_keys:
                seen_keys.add(key)
                results.append([list(rot) for rot in rotations_so_far])
            return
        boards_needed = rotation_sizes[rotation_idx]
        players_needed = boards_needed * 2
        eligible = sorted(p for p in player_ids if remaining[p] > 0)
        if len(eligible) < players_needed:
            return
        for combo in itertools.combinations(eligible, players_needed):
            matchings = _all_perfect_matchings_generic(list(combo))
            for matching in matchings:
                if any(pair in used_partner_pairs for pair in matching):
                    continue
                for pair in matching:
                    for p in pair:
                        remaining[p] -= 1
                rotations_so_far.append(matching)
                new_used = used_partner_pairs | set(matching)
                backtrack(rotation_idx + 1, remaining, new_used, rotations_so_far)
                rotations_so_far.pop()
                for pair in matching:
                    for p in pair:
                        remaining[p] += 1
                if calls[0] > call_budget:
                    return
    backtrack(0, dict(required_counts), set(), [])
    return results, truncated[0]
def _default_opponent_max_per_player(chosen_opp_ids: list, needed_slots: int) -> dict:
    """Verdeelt de benodigde speler-plaatsen (needed_slots = 2 x aantal
    wedstrijden) zo gelijk mogelijk over de gekozen tegenstander-spelers —
    exact dezelfde verdeelstrategie als voor onze eigen kant (afronden naar
    boven voor de eerste spelers, zodat de som altijd exact klopt)."""
    n = len(chosen_opp_ids)
    if n == 0:
        return {}
    base = needed_slots // n
    extra = needed_slots % n
    return {pid: base + (1 if i < extra else 0) for i, pid in enumerate(chosen_opp_ids)}
def _build_opponent_boards_and_points(rotation_structure: list, name_by_id: dict, rank_by_id: dict) -> tuple:
    """Zet 1 rotatie-veilige tegenstander-structuur om naar (boards,
    rotation_points): boards in het standaard formaat, met de officiële
    bordvolgorde-regel correct toegepast PER ROTATIE (art. 6.6, ook voor de
    tegenstander — enkel voor de JUISTE volgorde binnen elke rotatie, GEEN
    validatie tegen ONZE puntengrens-regel: we kunnen/willen de tegenstander
    niet dwingen tot ONZE afdeling se regels, we tonen enkel hun punten ter
    info)."""
    flat = [pair for rotation in rotation_structure for pair in rotation]
    rotation_eval = ll.filter_and_order_lineup_by_rotations(flat, rank_by_id, rules=None)
    boards = []
    for pair in rotation_eval["ordered_pairs"]:
        p1, p2 = tuple(pair)
        boards.append({"opponent_pair": [
            {"name": name_by_id.get(p1, p1), "user_id": p1,
             "ranking": (f"P{int(rank_by_id[p1])}" if rank_by_id.get(p1) is not None else None)},
            {"name": name_by_id.get(p2, p2), "user_id": p2,
             "ranking": (f"P{int(rank_by_id[p2])}" if rank_by_id.get(p2) is not None else None)},
        ]})
    rotation_points = [rot.get("total_points") for rot in rotation_eval["rotations"]]
    return boards, rotation_points
def _opponent_rotation_points_from_boards(boards: list) -> list:
    """Berekent, voor een FLAT, per-rotatie-geordende boards-lijst (2 op een
    rij = 1 rotatie), de som van de klassementen (uit het 'ranking'-veld)
    van de 4 spelers in die rotatie. Werkt voor zowel HISTORISCHE als
    THEORETISCH gegenereerde boards (beide gebruiken hetzelfde 'ranking'-
    veld-formaat) — gebruikt bij het opbouwen van de tabelkolommen, zodat
    geen aparte opslag van punten per unieke tegenstander-opstelling nodig
    is."""
    points = []
    for i in range(0, len(boards), 2):
        chunk = boards[i:i + 2]
        if len(chunk) < 2:
            points.append(None)
            continue
        vals = []
        for b in chunk:
            for p in (b.get("opponent_pair") or []):
                r = ll.parse_ranking(p.get("ranking"))
                if r is not None:
                    vals.append(r)
        points.append(sum(vals) if vals else None)
    return points
def _generate_theoretical_opponent_boards_with_repeats(
    chosen_opp_players: list, opponent_max_per_player: dict, opponent_official_ranks: dict,
    max_variants: int,
) -> tuple:
    """Genereert ALLE rotatie-veilige theoretische tegenstander-opstellingen
    (via _enumerate_rotation_aware_pairings — GEEN losse, tegenstander-
    specifieke enumeratiefunctie meer nodig)."""
    ids = [str(p["user_id"]) for p in chosen_opp_players]
    name_by_id = {str(p["user_id"]): p.get("name", str(p["user_id"])) for p in chosen_opp_players}
    structures, truncated = _enumerate_rotation_aware_pairings(ids, opponent_max_per_player)
    total_theoretical = len(structures)
    all_boards = []
    for structure in structures[:max_variants]:
        boards, _points = _build_opponent_boards_and_points(structure, name_by_id, opponent_official_ranks)
        all_boards.append(boards)
    meta = {
        "total_theoretical": total_theoretical,
        "truncated": truncated or total_theoretical > len(all_boards),
        "players_used": len(ids),
    }
    return all_boards, meta
def _historical_opponent_boards_list(bundle: dict) -> list:
    """Geeft een lijst van (label, boards) terug voor elke historische
    (al gespeelde) opstelling van de tegenstander (bundle["previous_fixtures"]).
    ALTIJD meegenomen, ONGEACHT welke tegenstander-roster momenteel gekozen
    is voor de theoretische verkenning.
    PADEL_ANALYSIS_ROTATION_SAFE_ENUMERATION_2026-09-18: boards worden nu
    EXPLICIET op board_position gesorteerd voordat ze teruggegeven worden —
    voorheen kon de ruwe volgorde afwijken van de werkelijke rotatie-
    indeling, wat de "RotatieR-B"-kolomtoewijzing en de punten-per-rotatie-
    berekening in de war kon sturen (de _opponent_lineup_key()-deduplicatie
    zelf was al ordervrij en dus niet getroffen, maar de latere
    tabelweergave wel)."""
    out = []
    for fx_bundle in bundle.get("previous_fixtures", []) or []:
        boards = fx_bundle.get("boards") or []
        fx = fx_bundle.get("fixture", {}) or {}
        if fx_bundle.get("error") or not boards:
            continue
        sorted_boards = sorted(boards, key=lambda b: b.get("board_position") or 0)
        label = fx.get("date_text") or "onbekende datum"
        out.append((label, sorted_boards))
    return out
def _opponent_lineup_key(boards: list):
    """Structurele sleutel voor een tegenstander-opstelling: een frozenset
    van frozensets van user_id's per bord, ONAFHANKELIJK van bordvolgorde."""
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
    voorkomt, wordt EENMALIG behandeld en als historisch gemarkeerd.
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
    return unique
def _compute_matchup(
    own_ordered_pairs: list, opp_boards: list,
    synergy_fn, player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
) -> dict:
    """PADEL_ANALYSIS_ROTATION_SAFE_ENUMERATION_2026-09-18: berekent, voor 1
    GEGARANDEERD geldige (rotatie-veilige, reeds officieel-geordende) eigen
    koppelverdeling tegen 1 tegenstander-opstelling, de per-match simulatie
    (synergie, edge, winkans) — LOKAAL, dezelfde formules als lineup_lab.
    optimize_lineup_vs_scenario() gebruikte (effective_simulation_rating,
    estimate_win_probability, risk_note_for_probability, matchup_edge),
    maar toegepast op een vooraf bepaalde combinatie i.p.v. een gezochte
    'beste' — nodig omdat optimize_lineup_vs_scenario() zelf niet rotatie-
    veilig is voor onze eigen kant (zie moduledocstring)."""
    assignment = []
    expected_boards_won = 0.0
    total_score = 0.0
    n = min(len(own_ordered_pairs), len(opp_boards))
    for i in range(n):
        p1, p2 = tuple(own_ordered_pairs[i])
        syn = synergy_fn(p1, p2)
        board = opp_boards[i]
        opp_pair = board.get("opponent_pair", []) or []
        our_eff = [
            ll.effective_simulation_rating(p1, player_ratings, official_ranks_strict),
            ll.effective_simulation_rating(p2, player_ratings, official_ranks_strict),
        ]
        their_eff = [
            ll.effective_simulation_rating(
                p.get("user_id"), opponent_ratings,
                {p.get("user_id"): ll.parse_ranking(p.get("ranking"))},
            )
            for p in opp_pair
        ]
        our_eff_known = [v for v in our_eff if v is not None]
        their_eff_known = [v for v in their_eff if v is not None]
        our_avg = (sum(our_eff_known) / len(our_eff_known)) if our_eff_known else None
        their_avg = (sum(their_eff_known) / len(their_eff_known)) if their_eff_known else None
        edge = ll.matchup_edge(our_eff, their_eff)
        win_prob = ll.estimate_win_probability(our_avg, their_avg)
        if win_prob is not None:
            expected_boards_won += win_prob
        total_score += syn + edge
        assignment.append({
            "our_pair": (p1, p2),
            "synergy": round(syn, 3),
            "edge": round(edge, 3),
            "win_probability": round(win_prob, 3) if win_prob is not None else None,
            "risk_note": ll.risk_note_for_probability(win_prob),
            "our_effective_rating": round(our_avg, 1) if our_avg is not None else None,
            "their_effective_rating": round(their_avg, 1) if their_avg is not None else None,
            "opponent_board": board,
        })
    return {
        "assignment": assignment,
        "expected_boards_won": round(expected_boards_won, 2),
        "total_score": round(total_score, 3),
    }
_MATCHUP_DISPLAY_DEFAULT_N = 15
_MAX_TOTAL_MATCHUPS = 800
_THEORETICAL_MAX_VARIANTS = 300
def _build_all_valid_matchups(
    unique_opponent_lineups: dict,
    available_ids: list, max_per_player: dict,
    synergy_fn, player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
    tournament_rules_dict,
) -> tuple:
    """PADEL_ANALYSIS_ROTATION_SAFE_ENUMERATION_2026-09-18: bouwt ALLE
    geldige "wij vs zij"-matchups, met NU OOK onze EIGEN kant volledig
    rotatie-veilig (via _enumerate_rotation_aware_pairings). Bypasst
    hiervoor ll.optimize_lineup_vs_scenario()/ll.optimize_lineup() volledig
    voor deze specifieke berekening — die 2 functies zijn niet rotatie-
    bewust (kunnen een speler in 2 GELIJKTIJDIGE matchen van dezelfde
    rotatie plaatsen). De Rotatieplanner-sectie verderop in dit bestand
    gebruikt die functies nog wel, maar is daar (zie toelichting bovenaan
    dat blok) NIET door deze bug getroffen, want ze verwerkt altijd maar 1
    rotatie tegelijk.
    Returns (matchups_gesorteerd, truncated, total_seen, diagnostics)."""
    own_structures, own_truncated = _enumerate_rotation_aware_pairings(available_ids, max_per_player)
    valid_own_options = []
    own_excluded_by_rules = 0
    for structure in own_structures:
        flat = [pair for rotation in structure for pair in rotation]
        own_eval = ll.filter_and_order_lineup_by_rotations(flat, official_ranks_strict, rules=tournament_rules_dict)
        if tournament_rules_dict is not None and not own_eval["all_valid"]:
            own_excluded_by_rules += 1
            continue
        valid_own_options.append((own_eval["ordered_pairs"], own_eval["rotations"]))
    seen_matchup_keys = set()
    all_matchups = []
    total_seen = 0
    truncated = own_truncated
    for own_ordered_pairs, own_rotations_info in valid_own_options:
        if truncated and len(all_matchups) >= _MAX_TOTAL_MATCHUPS:
            break
        our_pairs_key = frozenset(frozenset(p) for p in own_ordered_pairs)
        for their_key, info in unique_opponent_lineups.items():
            boards = info["boards"]
            if len(boards) != len(own_ordered_pairs):
                continue
            total_seen += 1
            mkey = (our_pairs_key, their_key)
            if mkey in seen_matchup_keys:
                continue
            seen_matchup_keys.add(mkey)
            computed = _compute_matchup(
                own_ordered_pairs, boards, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings,
            )
            all_matchups.append({
                "assignment": computed["assignment"],
                "expected_boards_won": computed["expected_boards_won"],
                "total_score": computed["total_score"],
                "own_rotations": own_rotations_info,
                "is_historical": info["is_historical"],
                "historical_labels": list(info["historical_labels"]),
            })
            if len(all_matchups) >= _MAX_TOTAL_MATCHUPS:
                truncated = True
                break
        if truncated and len(all_matchups) >= _MAX_TOTAL_MATCHUPS:
            break
    def _sort_key(m):
        ebw = m.get("expected_boards_won")
        return ebw if ebw is not None else m.get("total_score", 0.0)
    all_matchups.sort(key=_sort_key, reverse=True)
    diagnostics = {
        "own_structures_total": len(own_structures),
        "own_excluded_by_rules": own_excluded_by_rules,
        "own_valid": len(valid_own_options),
    }
    return all_matchups, truncated, total_seen, diagnostics
def _format_opponent_lineup_label(boards: list) -> str:
    return " | ".join(" + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards)
def _format_match_cell(a: dict, name_lookup_global: dict) -> str:
    """PADEL_ANALYSIS_MATCHUP_TABLE_2026-09-18: compacte, 1-regelige
    weergave van 1 match, voor gebruik als tabelcel (Kim: "compactere
    kolombreedte. toon punten bvb Carl en Nico en toon punten Gregory en
    tim")."""
    p1, p2 = a["our_pair"]
    our_names = f"{name_lookup_global.get(p1, p1)}+{name_lookup_global.get(p2, p2)}"
    opp_pair = a["opponent_board"]["opponent_pair"]
    their_names = "+".join(p.get("name", "?") for p in opp_pair)
    our_r = a.get("our_effective_rating")
    their_r = a.get("their_effective_rating")
    our_txt = f"{our_names} ({our_r:.0f})" if our_r is not None else our_names
    their_txt = f"{their_names} ({their_r:.0f})" if their_r is not None else their_names
    wp = a.get("win_probability")
    wp_txt = f"{int(round(wp * 100))}%" if wp is not None else "?"
    return f"{our_txt} vs {their_txt}: {wp_txt}"
def _matchups_to_table_rows(matchups: list, name_lookup_global: dict) -> list:
    """PADEL_ANALYSIS_MATCHUP_TABLE_2026-09-18: bouwt de tabelrijen voor
    st.dataframe. Kolomtitels "RotatieR-B" (Kim's exacte gevraagde
    benaming) i.p.v. "Match N"; punten-per-rotatie als 1 compacte kolom per
    rotatie (wij/zij samen) i.p.v. 2 aparte tekstregels per matchup."""
    rows = []
    for rank, m in enumerate(matchups, start=1):
        assignment = m["assignment"]
        n_boards = len(assignment)
        n_rotations = -(-n_boards // 2)  # ceiling
        opp_boards = [a["opponent_board"] for a in assignment]
        opp_points = _opponent_rotation_points_from_boards(opp_boards)
        own_rotations_info = m.get("own_rotations") or []
        own_points = [rot.get("total_points") for rot in own_rotations_info]
        own_valid = [rot.get("valid", True) for rot in own_rotations_info]
        row = {"#": rank, "Verwacht": m.get("expected_boards_won")}
        for r in range(n_rotations):
            wij = own_points[r] if r < len(own_points) and own_points[r] is not None else "?"
            zij = opp_points[r] if r < len(opp_points) and opp_points[r] is not None else "?"
            icon = "✅" if (r >= len(own_valid) or own_valid[r]) else "❌"
            row[f"Rot{r+1} punten (wij/zij)"] = f"{icon} {wij}/{zij}"
            for board_in_rotation in range(2):
                board_idx = r * 2 + board_in_rotation
                if board_idx >= n_boards:
                    continue
                col_name = f"Rotatie{r+1}-{board_in_rotation+1}"
                row[col_name] = _format_match_cell(assignment[board_idx], name_lookup_global)
        row["Vorige keer"] = ("🟢 " + ", ".join(m["historical_labels"])) if m["is_historical"] else ""
        rows.append(row)
    return rows
def _render_all_valid_matchups(
    bundle, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, sel_player_id, tournament_rules_dict=None, rules_label=None,
):
    """PADEL_ANALYSIS_ROTATION_SAFE_ENUMERATION_2026-09-18 /
    PADEL_ANALYSIS_MATCHUP_TABLE_2026-09-18: toont ALLE reglementair
    geldige, rotatie-veilige "wij vs zij"-matchups als ÉÉN gesorteerde
    tabel (klikbare kolomkoppen voor sortering, ingebouwd via
    st.dataframe)."""
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "ALLE reglementair geldige, rotatie-veilige combinaties van onze opstelling tegen hun "
        "opstelling, in ÉÉN tabel — klik op een kolomkop om te sorteren. De opstelling die de "
        "tegenstander vorige keer effectief speelde is gemarkeerd in de kolom 'Vorige keer'."
    )
    historical_boards_with_labels = _historical_opponent_boards_list(bundle)
    st.markdown("##### 🎯 Tegenstander-roster voor theoretische scenario's")
    st.caption(
        "Kies WIE van de tegenstander waarschijnlijk beschikbaar is. We berekenen dan ALLE mogelijke "
        "opstellingen die zij daaruit kunnen vormen (officiële regel: hun sterkste duo — som van "
        "klassementen — op Match 1, per rotatie) en voegen die toe aan de tabel hieronder."
    )
    unique_players = bundle.get("unique_players", []) or []
    theoretical_boards: list = []
    if not unique_players:
        st.info("Nog geen tegenstander-spelers gekend om theoretische opstellingen voor te berekenen.")
    else:
        opp_labels = [p.get("name", "?") for p in unique_players]
        opp_label_to_id = {p.get("name", "?"): str(p.get("user_id")) for p in unique_players}
        default_opp_labels = opp_labels
        st.caption(
            f"Standaard staan alle {len(opp_labels)} bekende tegenstander-spelers geselecteerd, zodat ALLE "
            "mogelijke opstellingen automatisch worden meegenomen. Verklein de lijst enkel als je zeker weet "
            "dat bepaalde spelers niet zullen meespelen."
        )
        chosen_opp_labels = st.multiselect(
            "Beschikbare tegenstander-spelers", opp_labels, default=default_opp_labels,
            key=f"theoretical_opp_players_{opp['ploeg_id']}",
        )
        chosen_opp_ids = [opp_label_to_id[lbl] for lbl in chosen_opp_labels]
        needed = 2 * total_boards
        if len(chosen_opp_ids) < 2:
            st.info(
                "Selecteer minstens 2 tegenstander-spelers om theoretische scenario's toe te voegen. "
                "De historische opstelling(en) blijven sowieso al in de tabel staan."
            )
        else:
            chosen_opp_players = [p for p in unique_players if str(p.get("user_id")) in chosen_opp_ids]
            opponent_official_ranks = _opponent_official_ranks(chosen_opp_ids)
            missing_opp_official = [pid for pid in chosen_opp_ids if pid not in opponent_official_ranks]
            if missing_opp_official:
                opp_names = [p.get("name", str(p.get("user_id"))) for p in chosen_opp_players if str(p.get("user_id")) in missing_opp_official]
                st.caption(
                    f"ℹ️ Geen officieel klassement gekend voor: {', '.join(opp_names)} — behandeld als "
                    "'onbekende sterkte' bij het genereren van theoretische opstellingen."
                )
            default_opp_max = _default_opponent_max_per_player(chosen_opp_ids, needed)
            st.caption(
                f"Max. aantal wedstrijden per tegenstander-speler (standaard gelijk verdeeld over {needed} "
                "benodigde plaatsen — een speler mag, net als bij ons, meerdere matchen spelen met "
                "verschillende partners, maar nooit 2 GELIJKTIJDIGE matchen binnen dezelfde rotatie):"
            )
            opp_cols = st.columns(min(len(chosen_opp_ids), 6) or 1)
            opponent_max_per_player = {}
            for i, pid in enumerate(chosen_opp_ids):
                with opp_cols[i % len(opp_cols)]:
                    opponent_max_per_player[pid] = st.number_input(
                        next((p.get("name", pid) for p in chosen_opp_players if str(p.get("user_id")) == pid), pid),
                        min_value=0, max_value=int(total_boards),
                        value=default_opp_max.get(pid, 0), step=1,
                        key=f"opp_max_{opp['ploeg_id']}_{pid}",
                    )
            opp_total_slots = sum(opponent_max_per_player.values())
            if opp_total_slots != needed:
                st.error(
                    f"Som van tegenstander-plaatsen ({opp_total_slots}) moet gelijk zijn aan 2× wedstrijden "
                    f"({needed}). Pas de aantallen hierboven aan."
                )
            else:
                lineups, meta = _generate_theoretical_opponent_boards_with_repeats(
                    chosen_opp_players, opponent_max_per_player, opponent_official_ranks,
                    _THEORETICAL_MAX_VARIANTS,
                )
                st.caption(f"🔢 **{meta['total_theoretical']}** theoretische tegenstander-opstellingen mogelijk met deze verdeling.")
                if meta["truncated"]:
                    st.warning(f"⚠️ Enkel de eerste {_THEORETICAL_MAX_VARIANTS} van {meta['total_theoretical']} worden berekend.")
                compute_key = f"theoretical_boards_{opp['ploeg_id']}"
                sig_key = f"theoretical_boards_sig_{opp['ploeg_id']}"
                signature = (tuple(sorted(chosen_opp_ids)), tuple(sorted(opponent_max_per_player.items())), int(total_boards))
                if st.session_state.get(sig_key) != signature:
                    st.session_state[compute_key] = lineups
                    st.session_state[sig_key] = signature
                theoretical_boards = st.session_state.get(compute_key) or []
    unique_opponent_lineups = _collect_unique_opponent_lineups(historical_boards_with_labels, theoretical_boards)
    if not unique_opponent_lineups:
        st.info("Nog geen tegenstander-opstelling gekend of berekend om tegen te analyseren.")
        return []
    with st.spinner(f"Alle geldige matchups doorrekenen ({len(unique_opponent_lineups)} tegenstander-opstelling(en))..."):
        all_matchups, truncated, total_seen, build_diag = _build_all_valid_matchups(
            unique_opponent_lineups, available_ids, max_per_player, synergy_fn,
            player_ratings, official_ranks_strict, opponent_ratings, tournament_rules_dict,
        )
    st.divider()
    n_hist = len(historical_boards_with_labels)
    n_theo = len(theoretical_boards)
    with st.expander("🔍 Diagnostiek: hoeveel combinaties werden er precies doorgerekend?", expanded=False):
        st.write(f"- Rotatie-veilige eigen koppelverdelingen (totaal enumereerd): **{build_diag['own_structures_total']}**")
        st.write(f"- Daarvan uitgesloten door de reglementaire puntengrens: **{build_diag['own_excluded_by_rules']}**")
        st.write(f"- Reglementair geldige eigen koppelverdelingen: **{build_diag['own_valid']}**")
        st.write(f"- Historische tegenstander-opstellingen (al gespeeld dit seizoen): **{n_hist}**")
        st.write(f"- Theoretische tegenstander-opstellingen (uit de gekozen roster hierboven): **{n_theo}**")
        st.write(f"- Unieke tegenstander-opstellingen na samenvoegen (dubbels verwijderd): **{len(unique_opponent_lineups)}**")
        st.write(f"- Totaal doorgerekende matchup-kandidaten (vóór ontdubbeling): **{total_seen}**")
        st.write(f"- Uiteindelijk getoonde, geldige matchups: **{len(all_matchups)}**")
        if n_theo == 0 and unique_players:
            st.warning(
                "⚠️ Er werden 0 theoretische tegenstander-opstellingen meegenomen — controleer of hierboven "
                "voldoende tegenstander-spelers geselecteerd staan."
            )
    if truncated:
        st.warning(
            f"⚠️ Er zijn meer dan {_MAX_TOTAL_MATCHUPS} geldige matchups gevonden — enkel de eerste "
            f"{_MAX_TOTAL_MATCHUPS} zijn meegenomen. Verklein de spelersselectie voor een volledige dekking."
        )
    st.caption(f"**{len(all_matchups)}** geldige matchup(s) gevonden, gesorteerd van hoogste naar laagste verwachte winstkans.")
    if not all_matchups:
        st.info(
            "Geen enkele matchup voldoet aan de reglementaire puntengrens per rotatie, of er is geen "
            "combinatie mogelijk zonder een speler dubbel in dezelfde rotatie te plaatsen. Controleer de "
            "gekozen afdeling en het aantal beschikbare spelers."
        )
        return []
    show_all_key = f"all_matchups_showall_{opp['ploeg_id']}"
    show_all = st.checkbox(
        f"Toon alle {len(all_matchups)} matchups (i.p.v. de beste {_MATCHUP_DISPLAY_DEFAULT_N})",
        key=show_all_key,
    ) if len(all_matchups) > _MATCHUP_DISPLAY_DEFAULT_N else False
    display_matchups = all_matchups if show_all else all_matchups[:_MATCHUP_DISPLAY_DEFAULT_N]
    table_rows = _matchups_to_table_rows(display_matchups, name_lookup_global)
    st.dataframe(
        table_rows, use_container_width=True, hide_index=True,
        column_config={"Verwacht": st.column_config.NumberColumn("Verwacht", format="%.2f")},
    )
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
            "- **Synergie**: hoe goed dit koppel historisch samen presteert (confidence-shrinkage) — "
            "verwerkt in de matchcel-rating, niet apart getoond in de tabel.\n"
            "- **Officiële regel (art. 6.6)**: binnen elke ROTATIE speelt het duo met de HOOGSTE SOM "
            "van de 2 OFFICIËLE klassementen (nooit padelstat!) op het laagst genummerde match van "
            "die rotatie (RotatieR-1 vóór RotatieR-2).\n"
            "- **Puntengrens per rotatie**: de SOM van de officiële klassementen van alle 4 spelers "
            "in 1 rotatie moet binnen de grenzen van de gekozen afdeling liggen — anders uitgesloten "
            "(✅/❌ in de kolom 'RotX punten').\n"
            "- **Rotatie-veiligheid**: een speler kan nooit in 2 GELIJKTIJDIGE matchen van dezelfde "
            "rotatie staan (bv. nooit tegelijk in Rotatie1-1 én Rotatie1-2) — dit wordt nu voor ZOWEL "
            "onze kant als de tegenstander-kant streng afgedwongen.\n"
            "- **🟢 Vorige keer**: deze matchup komt overeen met een opstelling die de tegenstander "
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
        seen_labels = set()
        scenario_options = []
        for m in all_matchups:
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
