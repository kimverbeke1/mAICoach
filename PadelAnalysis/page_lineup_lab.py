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
begrijpen waarom (bv. staat de afdeling wel juist ingesteld? hoe ver zaten
de berekende punten van de toegelaten grens verwijderd?).

Fix: lineup_lab.optimize_lineup_vs_scenario() geeft nu een DERDE
returnwaarde terug (`diagnostics`, zie dat bestand) met de daadwerkelijk
BEREKENDE punten-per-rotatie-sommen over alle doorgerekende kandidaten
(ook de uitgesloten). Dit bestand toont die diagnostiek nu op ALLE DRIE de
plekken waar voorheen enkel "0 combinaties" te zien was:
  1. Rotatieplanner (_render_rotation_planner, via _generate_rotation_
     candidates(), die nu ook in de "else"-tak — géén tegenstander-scenario
     gekozen — zelf diagnostiek opbouwt via ll.filter_and_order_lineup_by_
     rotations()).
  2. Historische Opstelling-scenario's (_render_opstelling_scenario).
  3. Alle theoretische tegenstander-opstellingen (_render_theoretical_
     opponent_scenarios).
Nieuwe helper: _format_points_bounds_diagnostic(). GEEN wijziging aan de
reglementslogica zelf, geen nieuwe afdelingen, geen vereenvoudiging — enkel
een concrete, cijfermatige toelichting toegevoegd bij een bestaande
foutmelding.

--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCH_FREQUENCY_REGROUP_2026-09-18 (op verzoek van Kim)
--------------------------------------------------------------------------
"tabel met bordpositiefrequentie mag je hernemen. Beter woord dan bord is
match. en ik ben enkel geinteresseerd in verdeling match 1 en 2 van elke
rotatie. Dus speler in match 1 en match 3 samentellen en frequentie match 2
en match 4. Is om te zien wie meestal de 1ste match speelt van de rotatie."

_render_match1_frequency_opponent() toonde voorheen 1 kolom PER LOS BORD
(Bord 1, Bord 2, Bord 3, Bord 4, ...). Nu hergegroepeerd volgens de
rotatie-indeling (reglement art. 8.7.1: 2 rotaties van telkens 2
gelijktijdige wedstrijden): ONEVEN board_position (1, 3, 5, ...) = de
EERSTE match van een rotatie ("Match 1"), EVEN board_position (2, 4, 6,
...) = de TWEEDE match van een rotatie ("Match 2") — dus nog maar 2
kolommen, ongeacht hoeveel borden er in totaal gespeeld werden.
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
    spelers. Geen padelstat-fallback — ontbrekende waarden komen simpelweg
    niet in de returned dict voor (zie ll.has_missing_official_rank() om dat
    expliciet te signaleren waar nodig)."""
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
    """PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17:
    bouwt het REGLEMENT-dict voor ONZE spelers, UITSLUITEND op basis van het
    echte officiële klassement — GEEN fallback naar padelstat meer (dat was
    de root cause van 'altijd dezelfde opstelling', zie lineup_lab.py se
    moduledocstring). Spelers zonder gekend officieel klassement komen
    simpelweg niet in de dict voor; de aanroeper toont een expliciete
    waarschuwing via ll.has_missing_official_rank()."""
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
    """PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17: toont
    EXPLICIET welke spelers geen gekend officieel klassement hebben, i.p.v.
    in stilte een andere waarde te gebruiken voor de reglementaire
    bordordening/puntengrens."""
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
    """PADEL_ANALYSIS_POINTS_BOUNDS_DIAGNOSTIC_2026-09-18 (op verzoek van
    Kim): geeft, indien beschikbaar, de daadwerkelijk BEREKENDE punten-per-
    rotatie terug (min en max over alle doorgerekende kandidaten), naast de
    toegelaten grens van de gekozen afdeling — zodat je zelf kan beoordelen
    of dit een verkeerd ingestelde afdeling is, of een echte reglementaire
    onmogelijkheid. Retourneert een lege string als er niets zinvols te
    tonen valt (bv. geen reglement actief, of geen enkele rotatie kon
    berekend worden)."""
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
def _render_tournament_rules_selector(ploeg_id: str):
    if tr is None:
        st.caption("⚠️ tournament_rules.py niet gevonden — reglement-gebaseerde puntenfilter niet beschikbaar.")
        return None, None
    with st.expander("📖 Reglement / afdeling (bepaalt de toegelaten puntengrenzen per rotatie)", expanded=False):
        tournaments = tr.list_tournaments()
        default_tournament_idx = tournaments.index(tr.DEFAULT_TOURNAMENT) if tr.DEFAULT_TOURNAMENT in tournaments else 0
        tournament = st.selectbox(
            "Tornooi", tournaments, index=default_tournament_idx, key=f"rules_tournament_{ploeg_id}",
            help="Vandaag enkel Padel Senior Cup volledig ingevuld. Andere tornooien (Mixed, Open, "
                 "Vrouwen) kunnen later toegevoegd worden zodra het bijhorende reglement bezorgd is.",
        )
        categories = tr.list_categories(tournament)
        if not categories:
            st.warning(f"Nog geen categorieën ingevuld voor '{tournament}'.")
            return None, None
        default_cat_idx = categories.index(tr.DEFAULT_CATEGORY) if tr.DEFAULT_CATEGORY in categories else 0
        category = st.selectbox("Categorie", categories, index=default_cat_idx, key=f"rules_category_{ploeg_id}")
        afdelingen = tr.list_afdelingen(tournament, category)
        if not afdelingen:
            st.warning(f"Nog geen afdelingen ingevuld voor '{tournament}' / {category}.")
            return None, None
        afdeling = st.selectbox("Afdeling", afdelingen, key=f"rules_afdeling_{ploeg_id}", format_func=lambda a: f"Afdeling {a}")
        rules = tr.get_afdeling_rules(tournament, category, afdeling)
        st.caption(tr.format_rules_caption(tournament, category, afdeling, rules))
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
            "seizoen. 'Bord' is de vermoedelijke volgorde zoals de dubbels op het uitslagenblad staan."
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
                    "Bord": f"Bord {b.get('board_position', '?')}", "Koppel": namen,
                    "Klassement": " / ".join(rankings) if rankings else "onbekend",
                    "Score": b.get("score") or "onbekend",
                })
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
        if not toonde_iets:
            st.info("Geen bord-detail beschikbaar voor de gekende eerdere ontmoeting(en).")


def _render_match1_frequency_opponent(bundle: dict) -> None:
    """PADEL_ANALYSIS_MATCH_FREQUENCY_REGROUP_2026-09-18 (op verzoek van
    Kim): "tabel met bordpositiefrequentie mag je hernemen. Beter woord dan
    bord is match. en ik ben enkel geinteresseerd in verdeling match 1 en 2
    van elke rotatie. Dus speler in match 1 en match 3 samentellen en
    frequentie match 2 en match 4. Is om te zien wie meestal de 1ste match
    speelt van de rotatie."

    Was voorheen een tabel met 1 kolom PER LOS BORD (Bord 1, Bord 2, Bord 3,
    Bord 4, ...). Nu hergegroepeerd volgens de rotatie-indeling uit het
    reglement (art. 8.7.1: 2 rotaties van telkens 2 gelijktijdige
    wedstrijden -> Match 1+2 = rotatie 1, Match 3+4 = rotatie 2, ...):
    ONEVEN board_position (1, 3, 5, ...) = de EERSTE match van een rotatie,
    EVEN board_position (2, 4, 6, ...) = de TWEEDE match van een rotatie.
    Nog maar 2 kolommen i.p.v. 1 kolom per los bord.

    LET OP (bestaande, ongewijzigde beperking): board_position komt uit
    opponent_scout.extract_opponent_lineup() en is de VOLGORDE waarin de
    dubbels op het uitslagenblad staan — geen letterlijk bevestigd 'Match
    N'-label uit de brondata. De indeling oneven=eerste/even=tweede is dus
    een aanname, maar wel dezelfde aanname die de rest van de app (reglement,
    rotatie-logica) al hanteert voor board_position."""
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
        is_eerste_match_van_rotatie = (pos % 2 == 1)  # oneven = Match 1/3/5/... van een rotatie
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
            "eerdere, gekende wedstrijden dit seizoen. Puur beschrijvend — geen voorspelling. Bedoeld "
            "om te zien wie doorgaans de 1ste match van de rotatie speelt."
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
    """PADEL_ANALYSIS_POINTS_BOUNDS_DIAGNOSTIC_2026-09-18: geeft nu een DERDE
    returnwaarde terug (`diagnostics`, kan None zijn bij n<2), zodat
    _render_rotation_planner() bij 0 kandidaten kan tonen WAT er berekend
    werd (zowel in de tak MET een tegenstander-scenario als in de tak
    ZONDER, die nu zelf ook diagnostiek opbouwt via ll.filter_and_order_
    lineup_by_rotations())."""
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
        "AANTAL GEWONNEN BORDEN (niet op een abstract scoregetal). Klik aan wie/welke combinatie "
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
        ebw_txt = f" (verwacht {ebw:.2f} gewonnen borden)" if ebw is not None else f" (score {cand['score']:.3f})"
        option_labels.append(f"{prefix}{' | '.join(parts)}{ebw_txt}")
    chosen_idx = st.radio(
        "Combinaties", list(range(len(candidates))), format_func=lambda i: option_labels[i],
        key=f"rot_choice_v3_{ploeg_id}_{next_rotation_num}", label_visibility="collapsed",
    )
    chosen = candidates[chosen_idx]
    _render_rotation_points_caption(chosen.get("rotations"))
    if chosen["assignment"]:
        with st.expander("Detail van de gekozen combinatie (winkans per bord)", expanded=True):
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
# Opstelling-scenario's
# ─────────────────────────────────────────────
_SCENARIO_CANDIDATE_POOL = 400
_SCENARIO_SAVE_TOP_N = 400
_SCENARIO_DISPLAY_DEFAULT_N = 10
_AGGREGATE_DISPLAY_DEFAULT_N = 20
_THEORETICAL_MAX_VARIANTS = 300
_THEORETICAL_DISPLAY_DEFAULT_N = 10


def _aggregate_scenario_scores(scenarios: list) -> list:
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


def _render_theoretical_opponent_scenarios(
    bundle, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, tournament_rules_dict=None, rules_label=None,
):
    st.divider()
    st.markdown('<div class="section-header">🧮 Alle theoretische tegenstander-opstellingen</div>', unsafe_allow_html=True)
    st.caption(
        "Kies WIE van de tegenstander waarschijnlijk beschikbaar is. We berekenen ALLE mogelijke "
        "opstellingen die zij daaruit kunnen vormen (officiële regel: hun sterkste duo — som van "
        "klassementen — op Match 1), en voor ELK daarvan ONZE beste tegenzet, apart herberekend."
    )
    st.caption(_WIN_PROB_DISCLAIMER)
    if tournament_rules_dict is not None:
        st.caption(f"📖 Puntengrens per rotatie actief: {rules_label}. Ongeldige combinaties worden uitgesloten.")
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)

    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        st.info("Nog geen tegenstander-spelers gekend om theoretische opstellingen voor te berekenen.")
        return
    opp_labels = [p.get("name", "?") for p in unique_players]
    opp_label_to_id = {p.get("name", "?"): str(p.get("user_id")) for p in unique_players}
    default_ids = _most_recent_opponent_player_ids(bundle)
    if default_ids:
        default_opp_labels = [lbl for lbl, pid in opp_label_to_id.items() if pid in default_ids]
        st.caption(
            f"Standaard geselecteerd: de {len(default_opp_labels)} speler(s) uit hun meest recente "
            "gekende ontmoeting. Verklein deze lijst na rotatie 1 om verder te verfijnen."
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
        st.info(f"Selecteer minstens {needed} tegenstander-speler(s) ({total_boards} wedstrijden).")
        return

    chosen_opp_players = [p for p in unique_players if str(p.get("user_id")) in chosen_opp_ids]
    opponent_official_ranks = _opponent_official_ranks(chosen_opp_ids)
    missing_opp_official = [pid for pid in chosen_opp_ids if pid not in opponent_official_ranks]
    if missing_opp_official:
        opp_names = [p.get("name", pid) for p in chosen_opp_players if str(p.get("user_id")) in missing_opp_official]
        st.caption(
            f"ℹ️ Geen officieel klassement gekend voor: {', '.join(opp_names)} — deze speler(s) worden "
            "bij het genereren van theoretische opstellingen behandeld als 'onbekende sterkte' "
            "(reglementair gelijk aan elkaar, zie tabel resterende volgorde-vrijheid)."
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
    if not lineups:
        st.info("Geen theoretische opstellingen om te tonen.")
        return

    compute_key = f"theoretical_results_{opp['ploeg_id']}"
    sig_key = f"theoretical_signature_{opp['ploeg_id']}"
    signature = (
        tuple(sorted(available_ids)), tuple(sorted(max_per_player.items())), int(total_boards),
        tuple(sorted(chosen_opp_ids)), str(tournament_rules_dict),
    )
    needs_compute = st.session_state.get(sig_key) != signature
    recompute_clicked = st.button("🔄 Alle theoretische scenario's berekenen", key=f"theoretical_recompute_{opp['ploeg_id']}", type="primary")
    if needs_compute and compute_key in st.session_state:
        st.info("De selectie is gewijzigd — klik hierboven om opnieuw te berekenen.")
    if compute_key not in st.session_state and not recompute_clicked:
        st.info("Klik hierboven om alle theoretische scenario's te berekenen.")
        return

    if recompute_clicked:
        computed = []
        uitgesloten = 0
        with st.spinner(f"{len(lineups)} theoretische scenario's doorrekenen..."):
            for idx, boards in enumerate(lineups, start=1):
                results, _truncated, diagnostics = ll.optimize_lineup_vs_scenario(
                    available_ids, max_per_player, synergy_fn, boards, player_ratings,
                    player_official_ranks=official_ranks_strict, opponent_ratings=opponent_ratings,
                    top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
                    tournament_rules_dict=tournament_rules_dict,
                )
                if not results:
                    uitgesloten += 1
                computed.append({"idx": idx, "boards": boards, "results": results, "diagnostics": diagnostics})
        st.session_state[compute_key] = computed
        st.session_state[sig_key] = signature
        if tournament_rules_dict is not None and uitgesloten:
            st.caption(f"ℹ️ {uitgesloten} van de {len(lineups)} scenario's hadden geen enkele reglementair geldige eigen opstelling.")

    stored = st.session_state.get(compute_key) or []
    if not stored:
        return
    show_all_theoretical_key = f"theoretical_showall_{opp['ploeg_id']}"
    show_all_theoretical = st.checkbox(
        f"Toon alle {len(stored)} theoretische scenario's (i.p.v. de eerste {_THEORETICAL_DISPLAY_DEFAULT_N})",
        key=show_all_theoretical_key,
    ) if len(stored) > _THEORETICAL_DISPLAY_DEFAULT_N else False
    display_entries = stored if show_all_theoretical else stored[:_THEORETICAL_DISPLAY_DEFAULT_N]

    for entry in display_entries:
        boards = entry["boards"]
        board_summary = " | ".join(" + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards)
        with st.expander(f"Theoretisch scenario {entry['idx']}: {board_summary}", expanded=False):
            if not entry["results"]:
                st.warning(
                    "Geen enkele eigen koppelverdeling voldoet aan de reglementaire puntengrens per rotatie."
                    if tournament_rules_dict is not None else
                    "Geen geldige opstelling gevonden voor dit scenario."
                )
                if tournament_rules_dict is not None:
                    diag_msg = _format_points_bounds_diagnostic(tournament_rules_dict, entry.get("diagnostics"))
                    if diag_msg:
                        st.caption(diag_msg)
                continue
            best = entry["results"][0]
            ebw = best.get("expected_boards_won")
            st.markdown(f"**Onze beste tegenzet — verwacht {ebw:.2f} van {len(best['assignment'])} borden gewonnen**" if ebw is not None else "**Onze beste tegenzet**")
            _render_rotation_points_caption(best.get("rotations"))
            _render_assignment_with_outcome(best["assignment"], name_lookup_global)

    if not show_all_theoretical and len(stored) > len(display_entries):
        st.caption(f"Eerste {len(display_entries)} van {len(stored)} berekende theoretische scenario's getoond.")

    st.divider()
    st.markdown("#### 📊 Aggregaatscore over alle theoretische scenario's")
    st.caption(
        "Voor elke eigen koppelverdeling: het gemiddeld VERWACHT AANTAL GEWONNEN BORDEN over ALLE "
        "theoretische scenario's waarin ze een geldig resultaat had — de meest robuuste aanwijzing "
        "welke opstelling wij het best klaarhouden, ongeacht wat de tegenstander effectief kiest."
    )
    aggregate = _aggregate_scenario_scores(stored)
    if not aggregate:
        st.info("Nog geen combinaties met een geldig resultaat.")
        return
    show_all_agg = st.checkbox(
        f"Toon alle {len(aggregate)} combinaties (i.p.v. de beste {_AGGREGATE_DISPLAY_DEFAULT_N})",
        key=f"theoretical_agg_showall_{opp['ploeg_id']}",
    ) if len(aggregate) > _AGGREGATE_DISPLAY_DEFAULT_N else False
    weer_te_geven = aggregate if show_all_agg else aggregate[:_AGGREGATE_DISPLAY_DEFAULT_N]
    agg_rows = []
    for combo_key, info in weer_te_geven:
        pair_labels = " | ".join(f"{name_lookup_global.get(p1, p1)}/{name_lookup_global.get(p2, p2)}" for p1, p2 in combo_key)
        agg_rows.append({
            "Koppelverdeling": pair_labels, "Gem. verwachte borden gewonnen": round(info["avg"], 2),
            "Min": round(info["min"], 2), "Max": round(info["max"], 2),
            "In # scenario's": info["count"], "% van scenario's": f"{round(100 * info['count'] / len(stored))}%" if stored else "-",
        })
    st.dataframe(agg_rows, use_container_width=True, hide_index=True)
    if not show_all_agg and len(aggregate) > len(weer_te_geven):
        st.caption(f"Beste {len(weer_te_geven)} van {len(aggregate)} unieke koppelverdelingen getoond.")


def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption("Per scenario berekenen we automatisch onze beste tegenzet — over ALLE mogelijke koppelverdelingen heen.")

    tournament_rules_dict, rules_label = _render_tournament_rules_selector(opp["ploeg_id"])

    with st.expander("ℹ️ Wat betekenen winkans, verwachte borden, synergie en de puntengrens?", expanded=False):
        st.markdown(
            "- **Winkans per bord**: een RUWE schatting (logistische functie op het ratingverschil), "
            "gebaseerd op padelstats.be playing strength waar bekend, anders het officiële klassement "
            "als terugval — PER SPELER individueel, niet meer 'alles of niets' per bord.\n"
            "- **Verwacht aantal gewonnen borden**: de som van de winkansen over alle borden van die "
            "opstelling — een interpreteerbaar getal i.p.v. een abstracte score.\n"
            "- **Synergie**: hoe goed dit koppel historisch samen presteert (confidence-shrinkage).\n"
            "- **Officiële regel (art. 6.6)**: binnen elke ROTATIE speelt het duo met de HOOGSTE SOM "
            "van de 2 OFFICIËLE klassementen (nooit padelstat!) op het laagst genummerde bord.\n"
            "- **Puntengrens per rotatie**: de SOM van de officiële klassementen van alle 4 spelers "
            "in 1 rotatie moet binnen de grenzen van de gekozen afdeling liggen — anders uitgesloten. "
            "Bij 0 geldige combinaties tonen we voortaan ook de daadwerkelijk berekende punten, zodat "
            "je kan zien of dit aan de afdeling-keuze ligt.\n\n"
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
            st.caption(f"🔢 **{total_possible_combos}** mogelijke koppelverdelingen — ALLEMAAL doorgerekend per scenario.")
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

    # PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17:
    # STRIKT gescheiden dicts — GEEN vermenging meer.
    player_ratings = {pid: oa.get_own_player_rating(pid)[0] for pid in available_ids}  # SIMULATIE (padelstat)
    official_ranks_strict = _build_own_official_ranks_strict(available_ids)  # REGLEMENT (uitsluitend officieel)
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)

    opponent_ratings = _opponent_padelstat_ratings(bundle)

    if not bundle.get("previous_fixtures"):
        st.info("Geen historische scenario's beschikbaar. Gebruik 'Alle theoretische tegenstander-opstellingen' hieronder.")
    else:
        signature = (
            tuple(sorted(available_ids)), tuple(sorted(max_per_player.items())), int(total_boards),
            opp.get("ploeg_id"), str(tournament_rules_dict),
        )
        compute_key = f"scenario_results_{opp['ploeg_id']}"
        sig_key = f"scenario_signature_{opp['ploeg_id']}"
        needs_compute = st.session_state.get(sig_key) != signature
        recompute_clicked = st.button("🔄 Herberekenen", key=f"scenario_recompute_{opp['ploeg_id']}")

        if needs_compute or recompute_clicked:
            computed = []
            with st.spinner(f"Alle koppelverdelingen doorrekenen (tot {_SCENARIO_CANDIDATE_POOL} kandidaten)..."):
                for s_idx, fx_bundle in enumerate(bundle["previous_fixtures"], start=1):
                    boards = fx_bundle.get("boards", [])
                    fx = fx_bundle.get("fixture", {})
                    entry = {"s_idx": s_idx, "fixture": fx, "boards_count": len(boards), "error": fx_bundle.get("error"), "results": None, "truncated": False, "diagnostics": None}
                    if not entry["error"] and boards:
                        results, truncated, diagnostics = ll.optimize_lineup_vs_scenario(
                            available_ids, max_per_player, synergy_fn, boards, player_ratings,
                            player_official_ranks=official_ranks_strict, opponent_ratings=opponent_ratings,
                            top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
                            tournament_rules_dict=tournament_rules_dict,
                        )
                        entry["results"] = results
                        entry["truncated"] = truncated
                        entry["diagnostics"] = diagnostics
                    computed.append(entry)
            st.session_state[compute_key] = {
                "opponent_name": opp.get("name"), "opponent_ploeg_id": opp.get("ploeg_id"),
                "available_ids": available_ids, "available_labels": available_labels,
                "total_boards": int(total_boards), "max_per_player": max_per_player, "scenarios": computed,
            }
            st.session_state[sig_key] = signature

        stored = st.session_state.get(compute_key)
        if stored:
            for entry in stored["scenarios"]:
                s_idx, fx, boards_count = entry["s_idx"], entry["fixture"], entry["boards_count"]
                with st.expander(
                    f"Scenario {s_idx}: hun opstelling tegen {fx.get('home_name') if fx.get('away_ploeg_id')==opp['ploeg_id'] else fx.get('away_name')} ({fx.get('date_text','?')}) — {boards_count} wedstrijden",
                    expanded=(s_idx == 1),
                ):
                    if entry["error"]:
                        st.warning(entry["error"])
                        continue
                    if not entry["results"]:
                        st.warning(
                            "Geen enkele eigen koppelverdeling voldoet aan de reglementaire puntengrens."
                            if tournament_rules_dict is not None and boards_count else
                            ("Geen bord-detail beschikbaar." if boards_count == 0 else "Geen geldige opstelling gevonden.")
                        )
                        if tournament_rules_dict is not None and boards_count:
                            diag_msg = _format_points_bounds_diagnostic(tournament_rules_dict, entry.get("diagnostics"))
                            if diag_msg:
                                st.caption(diag_msg)
                        continue
                    if entry["truncated"]:
                        st.caption(f"⚠️ Meer dan {_SCENARIO_CANDIDATE_POOL} combinaties — top kandidaten getoond.")
                    total_computed = len(entry["results"])
                    show_all = st.checkbox(
                        f"Toon alle {total_computed} berekende opties (i.p.v. de beste {_SCENARIO_DISPLAY_DEFAULT_N})",
                        key=f"scenario_showall_{opp['ploeg_id']}_{s_idx}",
                    ) if total_computed > _SCENARIO_DISPLAY_DEFAULT_N else False
                    display_results = entry["results"] if show_all else entry["results"][:_SCENARIO_DISPLAY_DEFAULT_N]
                    for opt_idx, option in enumerate(display_results, start=1):
                        ebw = option.get("expected_boards_won")
                        label = f"**Optie {opt_idx}" + (" (beste)" if opt_idx == 1 else "")
                        label += f" — verwacht {ebw:.2f} van {len(option['assignment'])} borden gewonnen**" if ebw is not None else "**"
                        st.markdown(label)
                        _render_rotation_points_caption(option.get("rotations"))
                        _render_assignment_with_outcome(option["assignment"], name_lookup_global)
                        if opt_idx < len(display_results):
                            st.markdown("---")
                    if taa is not None and report is not None:
                        ai_key = f"scenario_ai_{opp['ploeg_id']}_{s_idx}"
                        if st.button("🤖 AI-analyse van deze opties", key=f"scenario_ai_btn_{opp['ploeg_id']}_{s_idx}"):
                            with st.spinner("AI analyseert..."):
                                try:
                                    st.session_state[ai_key] = taa.analyze_lineup_options(report, display_results, name_lookup_global)
                                except Exception as exc:
                                    st.session_state[ai_key] = f"⚠️ Mislukt: {exc}"
                        if st.session_state.get(ai_key):
                            st.markdown(st.session_state[ai_key])

            st.divider()
            if st.button("💾 Deze analyse opslaan", key=f"save_analysis_{opp['ploeg_id']}"):
                payload = {
                    "opponent_name": stored["opponent_name"], "opponent_ploeg_id": stored["opponent_ploeg_id"],
                    "own_player_ids": stored["available_ids"], "own_player_labels": stored["available_labels"],
                    "total_boards": stored["total_boards"], "max_per_player": stored["max_per_player"],
                    "scenarios": [
                        {
                            "s_idx": e["s_idx"], "fixture_label": e["fixture"].get("date_text", "?"), "boards_count": e["boards_count"],
                            "options": [
                                {
                                    "total_score": opt["total_score"], "expected_boards_won": opt.get("expected_boards_won"),
                                    "assignment": [
                                        {
                                            "our_pair_labels": [name_lookup_global.get(a["our_pair"][0], a["our_pair"][0]), name_lookup_global.get(a["our_pair"][1], a["our_pair"][1])],
                                            "synergy": a["synergy"], "edge": a["edge"], "win_probability": a.get("win_probability"),
                                            "opponent_names": [p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]],
                                        } for a in opt["assignment"]
                                    ],
                                } for opt in (e["results"] or [])
                            ],
                        } for e in stored["scenarios"]
                    ],
                }
                doc_id = fb.save_lineup_analysis(sel_player_id, payload)
                n_total_options = sum(len(s["options"]) for s in payload["scenarios"])
                st.success(f"Analyse opgeslagen ({n_total_options} opties over {len(payload['scenarios'])} scenario's).")

            st.divider()
            st.markdown("#### 📊 Aggregaatscore over alle historische scenario's")
            st.caption("Gemiddeld verwacht aantal gewonnen borden per koppelverdeling, over alle scenario's waarin ze voorkwam.")
            aggregate = _aggregate_scenario_scores(stored["scenarios"])
            if not aggregate:
                st.info("Nog geen combinaties met een geldig resultaat.")
            else:
                n_multi = sum(1 for _, info in aggregate if info["count"] > 1)
                if n_multi:
                    st.caption(f"✅ {n_multi} van de {len(aggregate)} combinaties kwamen in meerdere scenario's voor.")
                show_all_agg = st.checkbox(
                    f"Toon alle {len(aggregate)} combinaties", key=f"scenario_agg_showall_{opp['ploeg_id']}",
                ) if len(aggregate) > _AGGREGATE_DISPLAY_DEFAULT_N else False
                weer_te_geven = aggregate if show_all_agg else aggregate[:_AGGREGATE_DISPLAY_DEFAULT_N]
                agg_rows = []
                for combo_key, info in weer_te_geven:
                    pair_labels = " | ".join(f"{name_lookup_global.get(p1, p1)}/{name_lookup_global.get(p2, p2)}" for p1, p2 in combo_key)
                    agg_rows.append({
                        "Koppelverdeling": pair_labels, "Gem. verwachte borden gewonnen": round(info["avg"], 2),
                        "Min": round(info["min"], 2), "Max": round(info["max"], 2), "In # scenario's": info["count"],
                    })
                st.dataframe(agg_rows, use_container_width=True, hide_index=True)

    _render_theoretical_opponent_scenarios(
        bundle, opp, available_ids, max_per_player, int(total_boards), synergy_fn,
        player_ratings, official_ranks_strict, opponent_ratings, report, name_lookup_global,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    )

    st.divider()
    chosen_scenario_boards = None
    stored = st.session_state.get(f"scenario_results_{opp['ploeg_id']}")
    if stored and stored.get("scenarios"):
        scenario_pick_labels = ["Geen (enkel eigen synergie)"] + [f"Scenario {e['s_idx']}: {e['fixture'].get('date_text','?')}" for e in stored["scenarios"] if e.get("results")]
        scenario_pick = st.selectbox("Matchup-inschatting voor de Rotatieplanner op basis van:", scenario_pick_labels, key=f"rot_scenario_pick_{opp['ploeg_id']}")
        if scenario_pick != scenario_pick_labels[0]:
            s_idx_pick = int(scenario_pick.split(":")[0].replace("Scenario ", ""))
            matching_entry = next((e for e in stored["scenarios"] if e["s_idx"] == s_idx_pick), None)
            if matching_entry:
                for fx_bundle in bundle["previous_fixtures"]:
                    if fx_bundle.get("fixture") is matching_entry["fixture"]:
                        chosen_scenario_boards = fx_bundle.get("boards")
                        break

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
        with st.expander(f"Scenario {scenario.get('s_idx')}: {scenario.get('fixture_label', '?')} — {scenario.get('boards_count', 0)} wedstrijden ({len(options)} opties)"):
            if not options:
                st.info("Geen resultaat opgeslagen.")
                continue
            for opt_idx, option in enumerate(options, start=1):
                ebw = option.get("expected_boards_won")
                st.write(f"**Optie {opt_idx}**" + (f" — verwacht {ebw:.2f} borden gewonnen" if ebw is not None else f" — score {option.get('total_score')}"))
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
