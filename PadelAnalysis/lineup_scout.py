"""
lineup_scout.py - Volgende match laden, scout-header, eigen-ploeg-
herkenning, en de gedeelde caching-helpers (padelstat/klassement/officieel-
klassement/eigen-matchdocumenten) die de rest van de Opstelling-analyse-
modules hergebruiken.
Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
Zie page_lineup_lab.py voor het volledige overzicht van alle modules.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RANKING_INDEPENDENT_OF_ANALYSIS_2026-09-27 (op verzoek van
Kim, meermaals gemeld: "Kies eerst een speler bij 'Toon analyse voor'
hierboven. Wordt getoond bij de rangschikking. Dat is niet ok.")
--------------------------------------------------------------------------
_known_ranking_context() leest UITSLUITEND reeds opgeslagen data en bepaalt
daaruit reeks_url/fixtures/own_ploeg_id ONAFHANKELIJK van elke knop-klik of
scout.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28 (op verzoek van Kim, na analyse
i.s.m. opponent_scout.py + opponent_scout_ui.py: "eerste laadactie van de
ploegopstelling pagina te versnellen")
--------------------------------------------------------------------------
BEVESTIGD (concrete, geen vermoeden): _scout_team_all_fixtures() hieronder
(aangeroepen via page_lineup_lab._merge_full_opponent_roster(), voor de
"Vorige gespeelde matchen"/match1-match2-frequentie-features) deed een
TWEEDE, volledig onafhankelijke osc.scout_opponent()-aanroep voor DEZELFDE
tegenstander-ploeg als opponent_scout_ui._run_scout_and_scrape() (bij
"🔍 Tegenstander analyseren") - maar dan met lookback=ALLE dit seizoen
gespeelde wedstrijden i.p.v. enkel de laatste 1-4. Omdat scout_opponent()'s
fetched_cache tot nu toe ENKEL lokaal (binnen 1 aanroep) leefde, herhaalde
deze 2e, bredere aanroep fetches die de 1e aanroep al gedaan had - exact op
de pagina-render waar de analyse voor het eerst verschijnt (de "eerste
laadactie" waar Kim op wijst).
FIX: _scout_team_all_fixtures() geeft nu dezelfde GEDEELDE fetch-cache mee
aan osc.scout_opponent() als opponent_scout_ui._run_scout_and_scrape() -
via osc.shared_fetch_cache_key(ploeg_id) in st.session_state (zie
opponent_scout.py voor de centrale sleutel-definitie en de volledige
toelichting). Welke van de 2 aanroepen ook het eerst gebeurt op een
pagina-render (de volgorde ligt vast in page_lineup_lab.py: eerst de
scout-header/knop, dan pas _merge_full_opponent_roster()), de tweede
aanroep hergebruikt nu de fixtures die de eerste al ophaalde i.p.v. ze
opnieuw te fetchen.
"""
import streamlit as st
from dashboard_common import (
    fb, ll, ss, osu, oa, is_scraping_available, render_cloud_scrape_trigger,
    _parse_match_date, _format_scraped_at, _clean_name,
    _get_saved_poule_url, _save_poule_url, _get_saved_schedule,
    _load_poule_fixtures, _load_poule_schedule_robust, _official_current_rank,
)
try:
    import opponent_scout as osc
except Exception:  # noqa: BLE001  pragma: no cover
    osc = None
try:
    import manual_poule_input
except Exception:  # noqa: BLE001  pragma: no cover
    manual_poule_input = None


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
        "Component manual_poule_input niet gevonden - de URL wordt bewaard in "
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
    with st.expander("Schema nu verversen", expanded=False):
        st.caption(
            "Start meteen een update van je matchen en het poule-schema op de achtergrond. "
            "Je ziet hieronder live de voortgang; zodra dit klaar is, wordt de 'Volgende "
            "match' hieronder automatisch bijgewerkt - geen page-refresh nodig."
        )
        render_cloud_scrape_trigger(
            key_prefix=f"vm_schema_{sel_player_id}", player_ids=str(sel_player_id),
            mode="missing", label="Schema nu verversen",
        )


def _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches, own_display_name=None):
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    home_ploeg_id, away_ploeg_id, matched_fx = ss.identify_own_ploeg_id(
        fixtures, own_interclub_matches, own_display_name=own_display_name,
    )
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


@st.cache_data(ttl=300, show_spinner=False)
def _cached_own_full_doc(player_id: str):
    try:
        return fb.get_player(player_id)
    except Exception:
        return None


def _known_ranking_context(sel_player_id: str, sel_label: str):
    """PADEL_ANALYSIS_RANKING_INDEPENDENT_OF_ANALYSIS_2026-09-27: bepaalt
    (reeks_url, fixtures, own_ploeg_id) UITSLUITEND op basis van reeds
    opgeslagen data, ONAFHANKELIJK van de "Volgende match laden"-knop of de
    volledige tegenstander-scout."""
    saved_fixtures, _sched_at = _get_saved_schedule(sel_player_id)
    sel_doc = _cached_own_full_doc(str(sel_player_id))
    own_interclub_matches = [
        m for m in (sel_doc or {}).get("matches", []) if m.get("match_type") == "interclub"
    ]
    reeks_url = _get_saved_poule_url(sel_player_id)
    if not reeks_url:
        ic_with_url = [m for m in own_interclub_matches if m.get("reeks_url")]
        if ic_with_url:
            most_recent = sorted(
                ic_with_url,
                key=lambda m: _parse_match_date(m.get("match_date")) or (0, 0, 0),
                reverse=True,
            )[0]
            reeks_url = most_recent.get("reeks_url")
    own_ploeg_id = None
    if saved_fixtures:
        try:
            own_ploeg_id, _own_id2, _resolved = ss.identify_own_ploeg_id(
                saved_fixtures, own_interclub_matches, own_display_name=sel_label,
            )
        except Exception:
            own_ploeg_id = None
    return reeks_url, (saved_fixtures or []), own_ploeg_id


def _render_volgende_match_and_scout(sel_player_id: str, sel_label: str):
    st.markdown('<div class="section-header">Volgende match</div>', unsafe_allow_html=True)
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"
    _render_schema_refresh_button(sel_player_id)
    sel_doc = _cached_own_full_doc(str(sel_player_id))
    own_interclub_matches = [m for m in (sel_doc or {}).get("matches", []) if m.get("match_type") == "interclub"]
    def _finish(fixtures, reeks_url_val):
        own_ploeg_id = _resolve_own_ploeg_id(
            sel_player_id, fixtures, own_interclub_matches, own_display_name=sel_label,
        )
        if not own_ploeg_id:
            return None
        st.session_state[f"vm_fixtures_{sel_player_id}"] = fixtures
        st.session_state[f"vm_own_ploeg_id_{sel_player_id}"] = own_ploeg_id
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
            "plakken - die wordt blijvend onthouden."
        )
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_nourl")
        return None
    if not st.session_state.get(load_key):
        src = "handmatig ingesteld" if (st.session_state.get(override_url_key) or saved_url) else "automatisch gevonden via je laatste interclubmatch"
        st.caption(f"Poule/tabel-link is {src}. Klik om je volgende match te laden.")
        cbtn1, cbtn2 = st.columns([1, 1])
        with cbtn1:
            if st.button("Volgende match laden", key=f"load_vm_{sel_player_id}", type="primary"):
                st.session_state[load_key] = True
                st.rerun()
        with cbtn2:
            if st.button("Andere poule-link gebruiken", key=f"change_url_{sel_player_id}"):
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
        if st.button("Opnieuw proberen", key=f"retry_vm_{sel_player_id}"):
            _load_poule_fixtures.clear()
            st.rerun()
        if st.button("Andere poule-link", key=f"reset_manual_{sel_player_id}"):
            st.session_state.pop(override_url_key, None)
            st.session_state.pop(override_team_key, None)
            _save_poule_url(sel_player_id, "")
            st.session_state.pop(load_key, None)
            st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_fetcherr")
        return None
    if not fixtures:
        st.warning("Geen wedstrijden gevonden op de poule-pagina (onverwachte paginastructuur?).")
        if st.button("Opnieuw proberen", key=f"retry_nofix_{sel_player_id}"):
            _load_poule_fixtures.clear()
            st.rerun()
        if st.button("Andere poule-link", key=f"reset_manual_nofix_{sel_player_id}"):
            st.session_state.pop(override_url_key, None)
            _save_poule_url(sel_player_id, "")
            st.session_state.pop(load_key, None)
            st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_nofix")
        return None
    return _finish(fixtures, reeks_url)


def _own_team_name(fixtures: list, own_ploeg_id: str) -> str:
    for fx in fixtures or []:
        if str(fx.get("home_ploeg_id")) == str(own_ploeg_id):
            return fx.get("home_name") or ""
        if str(fx.get("away_ploeg_id")) == str(own_ploeg_id):
            return fx.get("away_name") or ""
    return ""


def _scout_team_all_fixtures(fixtures: list, ploeg_id: str, team_name: str, before_date: str) -> dict:
    """PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28: geeft nu dezelfde
    GEDEELDE fetch-cache mee aan osc.scout_opponent() als
    opponent_scout_ui._run_scout_and_scrape() (bij "🔍 Tegenstander
    analyseren") - via osc.shared_fetch_cache_key(ploeg_id) in
    st.session_state. Zie moduledocstring voor de volledige, bevestigde
    analyse van de dubbele-fetch-bug die dit oplost."""
    if osc is None or not fixtures or not ploeg_id:
        return {}
    cache_key = f"full_scout_v2_{ploeg_id}_{before_date}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    try:
        played = osc.get_opponent_previous_fixtures(fixtures, str(ploeg_id), before_date, lookback=99)
        n = len(played)
        if not n:
            st.session_state[cache_key] = {}
            return {}
        shared_cache = st.session_state.setdefault(
            osc.shared_fetch_cache_key(str(ploeg_id)), {}
        )
        bundle = osc.scout_opponent(
            fixtures, team_name, str(ploeg_id), before_date,
            lookback=n, min_players=0, max_lookback=n,
            fetched_cache=shared_cache,
        )
    except Exception:
        bundle = {}
    st.session_state[cache_key] = bundle
    return bundle


def _recent_own_lineup_roster(fixtures: list, own_ploeg_id: str) -> dict:
    if not fixtures or not own_ploeg_id or osc is None:
        return {}
    try:
        team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id)
        next_match = ss.get_next_match(team_fixtures)
    except Exception:
        return {}
    before_date = (next_match or {}).get("date_text") or ""
    cache_key = f"own_roster_v2_{own_ploeg_id}_{before_date}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    try:
        # PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28: eigen ploeg heeft een
        # ANDER ploeg_id dan de tegenstander, dus geen overlap met
        # _scout_team_all_fixtures()/opponent_scout_ui - maar voor
        # consistentie en om een toekomstige duplicatie (bv. als deze roster
        # ooit ELDERS ook opgevraagd wordt) meteen te vermijden, gebruikt
        # ook dit de gedeelde cache-conventie.
        shared_cache = st.session_state.setdefault(
            osc.shared_fetch_cache_key(str(own_ploeg_id)), {}
        )
        own_bundle = osc.scout_opponent(
            fixtures, _own_team_name(fixtures, own_ploeg_id),
            str(own_ploeg_id), before_date, lookback=1,
            fetched_cache=shared_cache,
        )
        roster = {
            str(p["user_id"]): (p.get("name") or str(p["user_id"]))
            for p in (own_bundle.get("unique_players") or []) if p.get("user_id")
        }
    except Exception:
        roster = {}
    st.session_state[cache_key] = roster
    return roster


@st.cache_data(ttl=300, show_spinner=False)
def _cached_own_player_rating(player_id: str):
    try:
        return oa.get_own_player_rating(str(player_id))[0]
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _cached_official_rank(player_id: str):
    try:
        snapshot = fb.get_official_klassement_via_padelstat(str(player_id)) or {}
        value = snapshot.get("klassement")
        if value is not None:
            return float(value)
    except Exception:
        pass
    try:
        return _official_current_rank(str(player_id))
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _cached_docs_for_players(player_ids: tuple) -> dict:
    try:
        return ll.get_docs_for_players(list(player_ids))
    except Exception:
        return {}


def _clear_rank_caches() -> None:
    try:
        _cached_own_player_rating.clear()
        _cached_official_rank.clear()
        _cached_docs_for_players.clear()
    except Exception:
        pass


def _merge_full_opponent_roster(bundle: dict, fixtures: list, opp: dict) -> dict:
    if not bundle or not fixtures:
        return bundle
    try:
        team_fixtures = ss.get_team_fixtures(fixtures, opp.get("ploeg_id"))
        next_match = ss.get_next_match(team_fixtures) if team_fixtures else None
        before_date = (next_match or {}).get("date_text") or ""
    except Exception:
        before_date = ""
    full_bundle = _scout_team_all_fixtures(
        fixtures, opp.get("ploeg_id"), opp.get("name") or "", before_date,
    )
    extra = full_bundle.get("unique_players") or []
    if not extra:
        return bundle
    bestaand = bundle.get("unique_players") or []
    gekend = {str(p.get("user_id")) for p in bestaand if p.get("user_id")}
    toegevoegd = []
    for speler in extra:
        uid = str(speler.get("user_id") or "")
        if not uid or uid in gekend:
            continue
        gekend.add(uid)
        toegevoegd.append(speler)
    if toegevoegd:
        bundle = dict(bundle)
        bundle["unique_players"] = list(bestaand) + toegevoegd
        onzeker = [
            p.get("name", "?") for p in toegevoegd
            if (p.get("appearances") or 0) <= 1 and not p.get("known_matches_total")
        ]
        bundle["_roster_extended_with"] = [p.get("name", "?") for p in toegevoegd]
        bundle["_roster_extended_low_confidence"] = onzeker
    return bundle


def _current_official_rank_prefer_padelstat(player_id: str):
    return _cached_official_rank(str(player_id))


def _opponent_padelstat_ratings(bundle: dict) -> dict:
    out = {}
    for p in bundle.get("unique_players", []) or []:
        uid = p.get("user_id")
        if not uid:
            continue
        rating = _cached_own_player_rating(str(uid))
        if rating is not None:
            out[str(uid)] = rating
    return out


def _opponent_official_ranks(player_ids: list) -> dict:
    out = {}
    for pid in player_ids:
        try:
            rank = _current_official_rank_prefer_padelstat(pid)
        except Exception:
            rank = None
        if rank is not None:
            out[str(pid)] = rank
    return out


def _build_own_official_ranks_strict(available_ids: list) -> dict:
    out = {}
    for pid in available_ids:
        try:
            rank = _current_official_rank_prefer_padelstat(pid)
        except Exception:
            rank = None
        if rank is not None:
            out[pid] = rank
    return out


def _render_official_rank_warning(available_ids: list, official_ranks_strict: dict, name_lookup: dict) -> None:
    missing = ll.has_missing_official_rank(available_ids, official_ranks_strict)
    if missing:
        namen = ", ".join(name_lookup.get(pid, pid) for pid in missing)
        st.warning(
            f"Officieel klassement onbekend voor: **{namen}**. Voor deze speler(s) kan de "
            "reglementaire bordvolgorde (sterkste duo eerst) en de puntengrens per rotatie NIET "
            "betrouwbaar geverifieerd worden - ze worden voor deze berekening als 0 punten "
            "meegeteld, wat de uitkomst kan vertekenen. Ververs het klassement van deze speler(s) "
            "voor een betrouwbaar resultaat."
        )


def _format_points_bounds_diagnostic(rules, diagnostics) -> str:
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
        f"puntengrens per rotatie (**{lo}-{hi}**). De berekende punten per rotatie voor deze "
        f"spelers/dit scenario lagen tussen **{pmin:.0f}** en **{pmax:.0f}**."
    )
