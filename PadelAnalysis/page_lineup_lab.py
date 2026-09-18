"""
page_lineup_lab.py — "🧩 Opstelling-analyse"-pagina (Volgende match,
Opstelling-scenario's, Rotatieplanner, Opgeslagen analyses).

Zie eerdere versies van dit bestand voor de volledige geschiedenis:
PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14 t.e.m.
PADEL_ANALYSIS_WINPROB_OWN_COLUMN_2026-09-18 (poule-schema laden/
persisteren, aggregaatscores, tegenstander-referentiesecties, theoretische
scenario's, reglement-selector, rotatie-veilige enumeratie, samengevoegde
matchup-tabel met padelstat-tiebreak, winkans als aparte sorteerbare kolom).

--------------------------------------------------------------------------
PADEL_ANALYSIS_BEST_WORST_CASE_VARIANTS_2026-09-18 (op verzoek van Kim)
--------------------------------------------------------------------------
Kim's melding, in context: "ik denk eraan om Carl+Stijn in rotatie 1-1 te
laten spelen om die op te offeren om dan met Kim en Nico match 2 van
rotatie 1 te winnen. Maar in de lijst staat die combinatie zelfs niet
[...] ik ga er bvb vanuit dat wij 1ste match toch niet kunnen winnen van
een te sterke speler [...] eigenlijk wil ik voor elk van onze combinaties
[...] willen zien wat het best case en worst case resultaat is." Later
bevestigd: "ook toepassen bij licht verschillende klassementen" (niet
enkel bij een exact gelijk officieel klassement).

ROOT CAUSE: _order_rotations_with_tiebreak() (zie de vorige versie van dit
bestand) bepaalde voor elke rotatie ALTIJD precies ÉÉN volgorde (sterkste
duo eerst, met padelstat als tie-breaker bij een exact gelijk officieel
klassement) en gaf NOOIT de omgekeerde volgorde als alternatief terug. Een
bewuste "sacrifice"-opstelling (het zwakkere duo BEWUST op de zwaarste
match zetten, om het sterkere duo een gunstiger tweede match te geven) kon
daardoor NOOIT in de matchup-tabel verschijnen - niet bij een exact
klassement-gelijkspel, en al helemaal niet bij een licht verschil (waar
die omgekeerde volgorde bovendien een ECHTE overtreding van art. 6.6 is,
niet enkel een vrije keuze).

FIX, kern van de aanpak:
  - _rotation_order_variants(): geeft voor 1 rotatie ALTIJD BEIDE mogelijke
    volgordes terug (normaal + omgekeerd), elk met een expliciete
    "is_regulation_compliant"-vlag:
      * bij een EXACT gelijk officieel klassement: BEIDE varianten zijn
        compliant=True (het reglement staat toe dat de ploeg zelf kiest);
      * bij een VERSCHILLEND officieel klassement: ENKEL de "sterkste
        eerst"-variant is compliant=True; de omgekeerde variant krijgt
        compliant=False met een DUIDELIJK, zichtbaar label dat dit een
        overtreding van art. 6.6 zou zijn - Kim vroeg dit uitdrukkelijk
        ("ook toepassen bij licht verschillende klassementen"), dus deze
        variant wordt WEL gegenereerd en getoond, maar NOOIT verzwegen als
        zijnde "gewoon een andere geldige optie".
  - _enumerate_own_variant_combinations(): bouwt voor een volledige
    (rotatie-veilige) eigen koppelverdeling het cartesisch product van de
    variant-keuzes per rotatie op (bij 2 rotaties dus tot 4 combinaties per
    onderliggende koppelverdeling), en geeft per combinatie mee of ZE IN
    HAAR GEHEEL volledig reglementair is (fully_compliant = alle rotaties
    gebruiken hun compliant-variant).
  - _build_all_valid_matchups() gebruikt deze enumeratie i.p.v. de vorige,
    enkelvoudige _order_rotations_with_tiebreak(). Een NIEUWE checkbox "🎲
    Toon ook bewust omgedraaide, niet-reglementaire varianten" (standaard
    UIT) bepaalt of de niet-compliant-varianten ÜBERHAUPT gegenereerd
    worden - staat ze UIT, dan is het gedrag exact zoals voorheen (enkel de
    reglementair verplichte volgorde, geen toename van het aantal rijen).
  - De puntengrens-VALIDATIE (tournament_rules_dict) blijft ONGEWIJZIGD:
    de som van de 4 officiële klassementen in een rotatie hangt NIET af
    van de gekozen volgorde, dus een rotatie die de puntengrens overschrijdt
    blijft in ALLE varianten uitgesloten - de nieuwe swap-optie opent geen
    achterdeurtje om de puntengrens te omzeilen, enkel om de BORDVOLGORDE
    binnen een reglementair toegelaten rotatie te herzien.
  - Nieuwe kolom "Reglementair" in de matchup-tabel (✅ / ⚠️ per matchup),
    zodat een bewust niet-reglementaire "wat als"-rij NOOIT verward kan
    worden met een gewone, toegelaten optie.

--------------------------------------------------------------------------
PADEL_ANALYSIS_AI_FOLLOWUP_ON_MATCHUPS_2026-09-18 (op verzoek van Kim: "zorg
dat ik kan doorvragen")
--------------------------------------------------------------------------
De "🤖 AI-inzicht over de beste matchups"-knop gaf voorheen slechts 1
eenmalig antwoord, zonder mogelijkheid om door te vragen (zelfde
onderliggende oorzaak als in opponent_analysis.py: geen bijgehouden
chatgeschiedenis). Nu vervangen door dezelfde chat-aanpak: een bijgehouden
geschiedenis in st.session_state, getoond als doorlopend gesprek, met een
doorvraag-invoerveld dat team_ai_advisor.analyze_lineup_options() met de
volledige geschiedenis aanroept.
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
    """Behouden voor eventueel toekomstig gebruik."""
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
# Rotatieplanner - combinatoriek (1 rotatie tegelijk, ONGEWIJZIGD)
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
# Rotatie-bewuste enumeratie: 1 correcte bron van waarheid voor ZOWEL onze
# eigen kant ALS de tegenstander-kant. (ONGEWIJZIGD)
# ─────────────────────────────────────────────
def _all_perfect_matchings_generic(seq: list) -> list:
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
    """Bouwt de ontmoeting ROTATIE PER ROTATIE op — GEGARANDEERD geen speler
    dubbel binnen 1 rotatie."""
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
    n = len(chosen_opp_ids)
    if n == 0:
        return {}
    base = needed_slots // n
    extra = needed_slots % n
    return {pid: base + (1 if i < extra else 0) for i, pid in enumerate(chosen_opp_ids)}


# ─────────────────────────────────────────────
# Bordvolgorde: officiële regel + padelstat-tie-breaker (bij EXACT gelijkspel)
# ─────────────────────────────────────────────
def _pair_official_sum(pair, official_ranks: dict) -> float:
    return sum((official_ranks.get(pid) or 0) for pid in pair)


def _pair_padelstat_sum(pair, padelstat_ratings: dict) -> float:
    return sum((padelstat_ratings.get(pid) or 0) for pid in pair)


def _rank_pairs_with_padelstat_tiebreak(
    pairs: list, official_ranks: dict, padelstat_ratings: dict,
) -> list:
    """Sorteert PRIMAIR op de SOM van de OFFICIËLE klassementen (art. 6.6,
    reglementair verplicht) — maar gebruikt bij een GELIJKSPEL daarin de SOM
    van de PADELSTAT-rating als tie-breaker."""
    def sort_key(pair):
        official_sum = _pair_official_sum(pair, official_ranks)
        padelstat_sum = _pair_padelstat_sum(pair, padelstat_ratings)
        return (official_sum, padelstat_sum)
    return sorted(pairs, key=sort_key, reverse=True)


def _order_rotations_with_tiebreak(
    rotation_structure: list, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
    """De REGLEMENTAIR VERPLICHTE ordening (1 volgorde per rotatie, geen
    varianten) — gebruikt voor de tegenstander-kant (waar we sowieso enkel
    hun eigen keuze becijferen ter info, niet ONZE beslissing) en als
    onderdeel van de nieuwe variant-enumeratie hieronder."""
    ordered_pairs = []
    rotation_results = []
    all_valid = True
    for rotation in rotation_structure:
        if len(rotation) < 2:
            ordered_pairs.extend(rotation)
            rotation_results.append({"total_points": None, "valid": True, "reason": "onvolledige rotatie"})
            continue
        duo_a, duo_b = rotation[0], rotation[1]
        ranked = _rank_pairs_with_padelstat_tiebreak([duo_a, duo_b], official_ranks, padelstat_ratings)
        ordered_pairs.extend(ranked)
        total_points = _pair_official_sum(duo_a, official_ranks) + _pair_official_sum(duo_b, official_ranks)
        valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
        if rules is not None:
            lo, hi = rules["punten_min"], rules["punten_max"]
            if total_points < lo:
                valid, reason = False, f"{total_points:.0f} < min {lo}"
            elif total_points > hi:
                valid, reason = False, f"{total_points:.0f} > max {hi}"
            else:
                valid, reason = True, f"{total_points:.0f} punten (toegelaten: {lo}-{hi})"
        rotation_results.append({"total_points": total_points, "valid": valid, "reason": reason})
        if not valid:
            all_valid = False
    return {"ordered_pairs": ordered_pairs, "rotations": rotation_results, "all_valid": all_valid}


def _build_opponent_boards_and_points(
    rotation_structure: list, name_by_id: dict, rank_by_id: dict, padelstat_by_id: dict,
) -> list:
    """Zet 1 rotatie-veilige tegenstander-structuur om naar boards, MET de
    padelstat-tie-breaker toegepast op de ordening binnen elke rotatie."""
    ordered = _order_rotations_with_tiebreak(rotation_structure, rank_by_id, padelstat_by_id, rules=None)
    boards = []
    for pair in ordered["ordered_pairs"]:
        p1, p2 = tuple(pair)
        boards.append({"opponent_pair": [
            {"name": name_by_id.get(p1, p1), "user_id": p1,
             "ranking": (f"P{int(rank_by_id[p1])}" if rank_by_id.get(p1) is not None else None)},
            {"name": name_by_id.get(p2, p2), "user_id": p2,
             "ranking": (f"P{int(rank_by_id[p2])}" if rank_by_id.get(p2) is not None else None)},
        ]})
    return boards


def _generate_theoretical_opponent_boards_with_repeats(
    chosen_opp_players: list, opponent_max_per_player: dict, opponent_official_ranks: dict,
    opponent_padelstat_ratings: dict, max_variants: int,
) -> tuple:
    ids = [str(p["user_id"]) for p in chosen_opp_players]
    name_by_id = {str(p["user_id"]): p.get("name", str(p["user_id"])) for p in chosen_opp_players}
    structures, truncated = _enumerate_rotation_aware_pairings(ids, opponent_max_per_player)
    total_theoretical = len(structures)
    all_boards = []
    for structure in structures[:max_variants]:
        boards = _build_opponent_boards_and_points(structure, name_by_id, opponent_official_ranks, opponent_padelstat_ratings)
        all_boards.append(boards)
    meta = {
        "total_theoretical": total_theoretical,
        "truncated": truncated or total_theoretical > len(all_boards),
        "players_used": len(ids),
    }
    return all_boards, meta


def _historical_opponent_boards_list(bundle: dict) -> list:
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
    pairs = []
    for b in boards:
        uids = frozenset(str(p.get("user_id")) for p in (b.get("opponent_pair") or []) if p.get("user_id"))
        if len(uids) == 2:
            pairs.append(uids)
    if not pairs:
        return None
    return frozenset(pairs)


def _collect_unique_opponent_lineups(historical_boards_with_labels: list, theoretical_boards: list) -> dict:
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


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_BEST_WORST_CASE_VARIANTS_2026-09-18
# Voor ONZE kant: ALTIJD beide mogelijke volgordes per rotatie genereren,
# elk expliciet gelabeld als reglementair (compliant) of een bewuste,
# NIET-reglementaire "wat als"-omdraaiing.
# ─────────────────────────────────────────────
def _rotation_order_variants(
    duo_a, duo_b, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
    """PADEL_ANALYSIS_BEST_WORST_CASE_VARIANTS_2026-09-18 (op verzoek van
    Kim: "voor elk van onze combinaties willen zien wat het best case en
    worst case resultaat is [...] ook toepassen bij licht verschillende
    klassementen").

    Geeft voor 1 rotatie (2 duo's) ALTIJD een lijst van 1 of 2 varianten
    terug - elke variant is een dict:
        {"ordered_pairs": [eerste, tweede],
         "is_regulation_compliant": bool,
         "swap_label": str}

    - Bij een EXACT gelijk officieel klassement (sum_a == sum_b): BEIDE
      volgordes zijn is_regulation_compliant=True (art. 6.6 staat expliciet
      toe dat de ploeg zelf kiest bij gelijke sterkte). De eerste variant
      gebruikt de padelstat-tie-breaker als AANBEVOLEN keuze (swap_label
      leeg), de tweede krijgt een neutraal label ("alternatieve, even
      geldige keuze bij gelijke officiële sterkte").
    - Bij een VERSCHILLEND officieel klassement: ENKEL de "hoogste som
      eerst"-variant is is_regulation_compliant=True. De omgekeerde
      variant wordt WEL gegenereerd (op Kim's uitdrukkelijk verzoek, ook
      bij een licht verschil) maar krijgt is_regulation_compliant=False
      met een DUIDELIJK ⚠️-label - dit wordt in de UI NOOIT verzwegen of
      als gelijkwaardig gepresenteerd aan de compliant-variant.

    total_points/valid/reason (puntengrens) zijn IDENTIEK voor beide
    varianten binnen dezelfde rotatie - de som van de 4 klassementen hangt
    niet af van welk duo eerst speelt."""
    sum_a = _pair_official_sum(duo_a, official_ranks)
    sum_b = _pair_official_sum(duo_b, official_ranks)
    total_points = sum_a + sum_b

    valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
    if rules is not None:
        lo, hi = rules["punten_min"], rules["punten_max"]
        if total_points < lo:
            valid, reason = False, f"{total_points:.0f} < min {lo}"
        elif total_points > hi:
            valid, reason = False, f"{total_points:.0f} > max {hi}"
        else:
            valid, reason = True, f"{total_points:.0f} punten (toegelaten: {lo}-{hi})"

    is_tie = (sum_a == sum_b)
    ranked = _rank_pairs_with_padelstat_tiebreak([duo_a, duo_b], official_ranks, padelstat_ratings)
    compliant_first, compliant_second = ranked[0], ranked[1]
    # PADEL_ANALYSIS_LINEUP_TRANSPARENCY_2026-09-19 (op verzoek van Kim: "ik
    # vermoed dat het systeem de padelstat score gebruikt ipv de officiele
    # score"): toon ALTIJD de exacte OFFICIËLE puntensom per duo die de
    # volgorde bepaalt, zodat dit nooit een black box is en meteen
    # controleerbaar is welk cijfer de beslissing stuurt (officieel
    # klassement, NIET padelstat - padelstat wordt uitsluitend als
    # tie-breaker gebruikt bij een EXACT gelijke officiële som).
    sum_first = _pair_official_sum(compliant_first, official_ranks)
    sum_second = _pair_official_sum(compliant_second, official_ranks)
    punten_txt = f"officieel {sum_first:.0f} vs {sum_second:.0f} punten"

    variants = [{
        "ordered_pairs": [compliant_first, compliant_second],
        "is_regulation_compliant": True,
        "swap_label": (
            f"gelijke officiële sterkte ({punten_txt}) — aanbevolen o.b.v. padelstat" if is_tie
            else f"{punten_txt} — sterkste eerst (art. 6.6)"
        ),
        "total_points": total_points, "valid": valid, "reason": reason,
    }]
    if is_tie:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": True,
            "swap_label": f"gelijke officiële sterkte ({punten_txt}) — alternatieve, even geldige keuze",
            "total_points": total_points, "valid": valid, "reason": reason,
        })
    else:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": False,
            "swap_label": (
                f"⚠️ NIET reglementair ({punten_txt}, omgedraaid): het sterkere duo moet "
                "normaliter eerst spelen (art. 6.6)"
            ),
            "total_points": total_points, "valid": valid, "reason": reason,
        })
    return {"variants": variants}


def _enumerate_own_variant_combinations(
    rotation_structure: list, official_ranks: dict, padelstat_ratings: dict,
    rules=None, include_non_compliant: bool = False,
) -> list:
    """PADEL_ANALYSIS_BEST_WORST_CASE_VARIANTS_2026-09-18: bouwt voor 1
    rotatie-veilige eigen koppelverdeling het CARTESISCH PRODUCT op van de
    variant-keuzes per rotatie (bij 2 rotaties dus tot 2×2=4 combinaties).

    include_non_compliant=False (standaard, ONGEWIJZIGD gedrag t.o.v. de
    vorige versie): gebruikt per rotatie ENKEL de/haar compliant-variant(en)
    - bij een exact gelijkspel dus 2 keuzes (art. 6.6 staat dat toe), bij
    een verschil precies 1 (de reglementair verplichte).
    include_non_compliant=True: neemt OOK de bewust omgedraaide,
    niet-compliant variant mee in het cartesisch product - dit is de
    nieuwe, expliciet aan te vinken uitbreiding.

    Geeft een lijst terug van
        {"ordered_pairs": [...alle paren, in volgorde over alle rotaties...],
         "rotations": [...per-rotatie info, incl. swap_label...],
         "fully_compliant": bool}
    (all_valid — puntengrens — wordt HIER niet meer apart bijgehouden: die
    hangt niet af van de gekozen volgorde en wordt door de aanroeper via
    "rotations"[i]["valid"] gecontroleerd, exact zoals voorheen)."""
    per_rotation_variant_lists = []
    for rotation in rotation_structure:
        if len(rotation) < 2:
            per_rotation_variant_lists.append([{
                "ordered_pairs": list(rotation), "is_regulation_compliant": True,
                "swap_label": "", "total_points": None, "valid": True, "reason": "onvolledige rotatie",
            }])
            continue
        duo_a, duo_b = rotation[0], rotation[1]
        result = _rotation_order_variants(duo_a, duo_b, official_ranks, padelstat_ratings, rules=rules)
        variants = result["variants"]
        if not include_non_compliant:
            variants = [v for v in variants if v["is_regulation_compliant"]]
        per_rotation_variant_lists.append(variants)

    combinations = []
    for combo in itertools.product(*per_rotation_variant_lists):
        ordered_pairs = []
        rotations_info = []
        fully_compliant = True
        for variant in combo:
            ordered_pairs.extend(variant["ordered_pairs"])
            rotations_info.append({
                "total_points": variant["total_points"], "valid": variant["valid"],
                "reason": variant["reason"], "swap_label": variant["swap_label"],
                "is_regulation_compliant": variant["is_regulation_compliant"],
            })
            if not variant["is_regulation_compliant"]:
                fully_compliant = False
        combinations.append({
            "ordered_pairs": ordered_pairs, "rotations": rotations_info,
            "fully_compliant": fully_compliant,
        })
    return combinations


def _compute_matchup(
    own_ordered_pairs: list, opp_boards: list,
    synergy_fn, player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
) -> dict:
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
    tournament_rules_dict, include_non_compliant_variants: bool = False,
) -> tuple:
    """PADEL_ANALYSIS_BEST_WORST_CASE_VARIANTS_2026-09-18: gebruikt nu
    _enumerate_own_variant_combinations() i.p.v. de enkelvoudige
    _order_rotations_with_tiebreak(), zodat elke eigen koppelverdeling met
    een tie of (indien aangevinkt) een bewuste omdraaiing als MEERDERE
    aparte matchup-rijen kan verschijnen - exact wat nodig is om een
    "sacrifice"-opstelling (zoals Kim's Carl+Stijn/Kim+Nico-voorbeeld) ooit
    te kunnen tonen, met best-case/worst-case zichtbaar naast elkaar."""
    own_structures, own_truncated = _enumerate_rotation_aware_pairings(available_ids, max_per_player)
    valid_own_options = []
    own_excluded_by_rules = 0
    own_variants_generated = 0
    for structure in own_structures:
        combinations = _enumerate_own_variant_combinations(
            structure, official_ranks_strict, player_ratings, rules=tournament_rules_dict,
            include_non_compliant=include_non_compliant_variants,
        )
        for combo in combinations:
            own_variants_generated += 1
            # Puntengrens-validatie is ONGEWIJZIGD: hangt niet af van de
            # gekozen volgorde-variant, enkel van welke 4 spelers samen in
            # de rotatie zitten.
            all_points_valid = all(r["valid"] for r in combo["rotations"])
            if tournament_rules_dict is not None and not all_points_valid:
                own_excluded_by_rules += 1
                continue
            valid_own_options.append((combo["ordered_pairs"], combo["rotations"], combo["fully_compliant"]))
    seen_matchup_keys = set()
    all_matchups = []
    total_seen = 0
    truncated = own_truncated
    for own_ordered_pairs, own_rotations_info, fully_compliant in valid_own_options:
        if truncated and len(all_matchups) >= _MAX_TOTAL_MATCHUPS:
            break
        # PADEL_ANALYSIS_TIE_VARIANT_DEDUP_FIX_2026-09-19 (root cause van
        # "Stijn Mortier komt nooit voor in match 1 van rotatie 1"): dit was
        # voorheen een frozenset-van-frozensets, wat de VOLGORDE van de
        # paren (dus WIE op match 1 vs match 2 van een rotatie staat)
        # volledig negeert. Bij een officieel gelijkspel genereert
        # _rotation_order_variants() BEIDE volgordes (elk met
        # is_regulation_compliant=True) - maar omdat de oude sleutel enkel
        # de ONGEORDENDE verzameling paren gebruikte, botsten die twee
        # varianten op EXACT dezelfde (our_pairs_key, their_key,
        # fully_compliant)-combinatie en werd de 2de (de omgedraaide, dus
        # de variant die bv. Stijn Mortier's duo WEL op match 1 zou zetten)
        # stilzwijgend weggefilterd als "duplicaat". Een TUPLE behoudt de
        # positie (Rotatie1-1 vs Rotatie1-2, ...) terwijl elk paar zelf nog
        # steeds een set is (volgorde BINNEN het koppel maakt niet uit).
        our_pairs_key = tuple(frozenset(p) for p in own_ordered_pairs)
        for their_key, info in unique_opponent_lineups.items():
            boards = info["boards"]
            if len(boards) != len(own_ordered_pairs):
                continue
            total_seen += 1
            # PADEL_ANALYSIS_BEST_WORST_CASE_VARIANTS_2026-09-18: de
            # dedupe-sleutel bevat nu OOK of dit de compliant-variant is,
            # zodat een reglementair correcte en een bewust omgedraaide
            # variant van DEZELFDE koppelverdeling BEIDE als aparte rijen
            # bewaard blijven (voorheen zou de dedupe-key ze ten onrechte
            # als "dezelfde matchup" behandeld hebben).
            mkey = (our_pairs_key, their_key, fully_compliant)
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
                "fully_compliant": fully_compliant,
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
        "own_variants_generated": own_variants_generated,
        "own_excluded_by_rules": own_excluded_by_rules,
        "own_valid": len(valid_own_options),
    }
    return all_matchups, truncated, total_seen, diagnostics


def _format_opponent_lineup_label(boards: list) -> str:
    return " | ".join(" + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards)


def _own_lineup_group_key(assignment: list) -> frozenset:
    """De ONGEORDENDE verzameling eigen koppels van 1 matchup-rij - dus
    dezelfde 'opstelling' ongeacht bordvolgorde of tegen welke
    tegenstander-opstelling ze doorgerekend werd."""
    return frozenset(frozenset(a["our_pair"]) for a in assignment)


def _render_best_worst_case_per_own_lineup(all_matchups: list, name_lookup_global: dict) -> None:
    """PADEL_ANALYSIS_BEST_WORST_CASE_SUMMARY_2026-09-19 (op verzoek van Kim:
    "ik wou dus eigenlijk onze ploegopstellingen visualiseren en voor elk
    van onze mogelijke ploegopstellingen een best case en worst case
    resultaat is. Dat is niet te zien."):

    Groepeert alle matchup-rijen per unieke EIGEN koppelverdeling (dezelfde
    koppels, ongeacht bordvolgorde of tegen welke tegenstander-opstelling)
    en toont per groep het BESTE en SLECHTSTE verwachte resultaat over alle
    doorgerekende tegenstander-scenario's - en, indien de checkbox
    "bewust omgedraaide varianten" hierboven aanstaat, ook over de
    reglementaire vs. bewust niet-reglementaire bordvolgorde. Zo wordt in
    1 oogopslag zichtbaar wat een "sacrifice"-opstelling (zoals Carl+Stijn
    bewust op de zwaarste match) in het beste/slechtste geval oplevert."""
    if not all_matchups:
        return
    groups: dict = {}
    for m in all_matchups:
        key = _own_lineup_group_key(m["assignment"])
        groups.setdefault(key, []).append(m)

    def _sort_val(m):
        ebw = m.get("expected_boards_won")
        return ebw if ebw is not None else m.get("total_score", 0.0)

    def _opp_label(m):
        return " | ".join(
            "+".join(p.get("name", "?") for p in a["opponent_board"]["opponent_pair"])
            for a in m["assignment"]
        )

    st.markdown('<div class="section-header">🏆 Best case / worst case per eigen opstelling</div>', unsafe_allow_html=True)
    st.caption(
        "Voor elke unieke combinatie van ONZE koppels (ongeacht bordvolgorde of tegen wie), het beste en "
        "het slechtste verwachte resultaat over alle doorgerekende tegenstander-opstellingen hierboven — "
        "en, als je de checkbox 'bewust omgedraaide varianten' aanvinkt, ook over de reglementaire vs. "
        "bewust niet-reglementaire bordvolgorde (bv. een zwakker duo bewust op de zwaarste match)."
    )
    summary_rows = []
    for key, rows_for_group in groups.items():
        rows_sorted = sorted(rows_for_group, key=_sort_val)
        worst, best = rows_sorted[0], rows_sorted[-1]
        pair_labels = " | ".join(
            f"{name_lookup_global.get(p1, p1)}/{name_lookup_global.get(p2, p2)}"
            for p1, p2 in (tuple(pair) for pair in key)
        )
        best_ebw, worst_ebw = best.get("expected_boards_won"), worst.get("expected_boards_won")
        summary_rows.append({
            "Eigen opstelling (koppels)": pair_labels,
            "_best_sort": _sort_val(best),
            "Best case": f"{best_ebw:.2f}" if best_ebw is not None else f"score {best.get('total_score', 0):.3f}",
            "Best case tegen": _opp_label(best),
            "Best reglementair": "✅" if best.get("fully_compliant", True) else "⚠️ NIET",
            "Worst case": f"{worst_ebw:.2f}" if worst_ebw is not None else f"score {worst.get('total_score', 0):.3f}",
            "Worst case tegen": _opp_label(worst),
            "Worst reglementair": "✅" if worst.get("fully_compliant", True) else "⚠️ NIET",
            "# scenario's": len(rows_for_group),
        })
    summary_rows.sort(key=lambda r: r.pop("_best_sort"), reverse=True)
    st.dataframe(
        summary_rows, use_container_width=True, hide_index=True,
        column_config={
            "Eigen opstelling (koppels)": st.column_config.TextColumn("Eigen opstelling (koppels)", width=260),
            "Best case tegen": st.column_config.TextColumn("Best case tegen", width=220),
            "Worst case tegen": st.column_config.TextColumn("Worst case tegen", width=220),
            "# scenario's": st.column_config.NumberColumn("# scenario's", width="small"),
        },
        row_height=40,
    )
    st.divider()


# ─────────────────────────────────────────────
# Matchup-tabel: volledige namen over 2 tekstregels, winkans + reglementair
# als APARTE, sorteerbare kolommen.
# ─────────────────────────────────────────────
def _matchups_to_table_rows(matchups: list, name_lookup_global: dict) -> tuple:
    """Bouwt de rijen voor de matchup-tabel. Elke RotatieR-B krijgt TWEE
    kolommen ("RotatieR-B" met de namen, "RotatieR-B %" met de winkans als
    apart, sorteerbaar getal). NIEUW: een "Reglementair"-kolom (✅/⚠️) die
    in 1 oogopslag toont of DEZE volledige matchup-rij de reglementair
    verplichte bordvolgorde gebruikt, of een bewust omgedraaide, niet-
    reglementaire "wat als"-variant is (PADEL_ANALYSIS_BEST_WORST_CASE_
    VARIANTS_2026-09-18)."""
    rows = []
    board_column_names: list = []
    for rank, m in enumerate(matchups, start=1):
        assignment = m["assignment"]
        n_boards = len(assignment)
        n_rotations = -(-n_boards // 2)  # ceiling
        row = {
            "#": rank, "Verwacht": m.get("expected_boards_won"),
            "Reglementair": "✅" if m.get("fully_compliant", True) else "⚠️ NIET",
        }
        for r in range(n_rotations):
            for board_in_rotation in range(2):
                board_idx = r * 2 + board_in_rotation
                if board_idx >= n_boards:
                    continue
                a = assignment[board_idx]
                col_base = f"Rotatie{r+1}-{board_in_rotation+1}"
                if col_base not in board_column_names:
                    board_column_names.append(col_base)
                p1, p2 = a["our_pair"]
                our_full_1 = name_lookup_global.get(p1, p1)
                our_full_2 = name_lookup_global.get(p2, p2)
                opp_pair = a["opponent_board"]["opponent_pair"]
                their_full = [p.get("name", "?") for p in opp_pair]
                wp = a.get("win_probability")
                row[col_base] = f"{our_full_1}+{our_full_2}\nvs {'+'.join(their_full)}"
                row[f"{col_base} %"] = round(wp * 100, 0) if wp is not None else None
        swap_notes = [
            rot.get("swap_label", "") for rot in (m.get("own_rotations") or [])
            if rot.get("swap_label")
        ]
        row["Toelichting"] = " | ".join(swap_notes) if swap_notes else ""
        row["Vorige keer"] = ("🟢 " + ", ".join(m["historical_labels"])) if m["is_historical"] else ""
        rows.append(row)
    return rows, board_column_names


def _render_all_valid_matchups(
    bundle, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, sel_player_id, tournament_rules_dict=None, rules_label=None,
):
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "ALLE reglementair geldige, rotatie-veilige combinaties van onze opstelling tegen hun "
        "opstelling, in ÉÉN tabel — klik op een kolomkop om te sorteren. De opstelling die de "
        "tegenstander vorige keer effectief speelde is gemarkeerd in de kolom 'Vorige keer'."
    )
    # PADEL_ANALYSIS_BEST_WORST_CASE_VARIANTS_2026-09-18: nieuwe, expliciet
    # aan te vinken checkbox — standaard UIT, zodat het aantal rijen niet
    # ongevraagd toeneemt.
    include_non_compliant = st.checkbox(
        "🎲 Toon ook bewust omgedraaide, NIET-reglementaire varianten (bv. een zwakker duo bewust "
        "'opofferen' op de zwaarste match, om het sterkere duo een gunstiger match te geven)",
        value=False, key=f"include_non_compliant_{opp['ploeg_id']}",
        help="Bij een EXACT gelijk officieel klassement zijn beide volgordes sowieso al reglementair "
             "toegelaten (art. 6.6 laat de ploeg dan zelf kiezen) en worden altijd getoond. Deze "
             "checkbox voegt daarnaast varianten toe die het officiële klassement bewust NEGEREN "
             "(dus een overtreding zouden zijn) - duidelijk gelabeld met ⚠️, puur om het best-case/"
             "worst-case-bereik van een koppelkeuze te kunnen inschatten.",
    )
    if include_non_compliant:
        st.caption(
            "⚠️ Rijen gemarkeerd met '⚠️ NIET' in de kolom 'Reglementair' zijn GEEN toegelaten "
            "opstelling volgens het reglement - gebruik ze enkel om een risico-inschatting te maken, "
            "nooit als effectieve wedstrijdopstelling."
        )
    historical_boards_with_labels = _historical_opponent_boards_list(bundle)
    st.markdown("##### 🎯 Tegenstander-roster voor theoretische scenario's")
    st.caption(
        "Kies WIE van de tegenstander waarschijnlijk beschikbaar is. We berekenen dan ALLE mogelijke "
        "opstellingen die zij daaruit kunnen vormen (officiële regel: hun sterkste duo — som van "
        "klassementen, met padelstat als tie-breaker bij gelijkspel — op Match 1, per rotatie) en "
        "voegen die toe aan de tabel hieronder."
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
            opponent_padelstat_ratings = _opponent_padelstat_ratings(bundle)
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
                    opponent_padelstat_ratings, _THEORETICAL_MAX_VARIANTS,
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
            include_non_compliant_variants=include_non_compliant,
        )
    st.divider()
    n_hist = len(historical_boards_with_labels)
    n_theo = len(theoretical_boards)
    with st.expander("🔍 Diagnostiek: hoeveel combinaties werden er precies doorgerekend?", expanded=False):
        st.write(f"- Rotatie-veilige eigen koppelverdelingen (totaal enumereerd): **{build_diag['own_structures_total']}**")
        st.write(f"- Daaruit gegenereerde volgorde-varianten (incl. eventuele swap-varianten): **{build_diag['own_variants_generated']}**")
        st.write(f"- Daarvan uitgesloten door de reglementaire puntengrens: **{build_diag['own_excluded_by_rules']}**")
        st.write(f"- Reglementair geldige eigen combinaties (puntengrens OK): **{build_diag['own_valid']}**")
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
    table_rows, board_column_names = _matchups_to_table_rows(display_matchups, name_lookup_global)
    column_config = {
        "#": st.column_config.NumberColumn("#", width="small"),
        "Verwacht": st.column_config.NumberColumn("Verwacht", format="%.2f", width="small"),
        "Reglementair": st.column_config.TextColumn("Reglementair", width="small"),
    }
    for col_base in board_column_names:
        # PADEL_ANALYSIS_TABLE_READABILITY_FIX_2026-09-19 (op verzoek van Kim:
        # "tabel niet leesbaar want de namen passen er niet in" + "er is een
        # 2de regel in de tabel maar die is niet zichtbaar"): "medium" (~200px)
        # was te smal voor 2 volledige spelersnamen + "vs" + 2 tegenstander-
        # namen op 1 regel, en de standaard rijhoogte van st.dataframe toont
        # enkel de EERSTE tekstregel van een cel. Vaste, ruimere pixelbreedte
        # + expliciete row_height (zie st.dataframe hieronder) lossen dit
        # samen op: de 2de regel ("vs ...") wordt nu gewoon zichtbaar.
        column_config[col_base] = st.column_config.TextColumn(col_base, width=280)
        column_config[f"{col_base} %"] = st.column_config.NumberColumn(f"{col_base} %", format="%.0f%%", width="small")
    column_config["Toelichting"] = st.column_config.TextColumn("Toelichting", width=320)
    column_order = ["#", "Verwacht", "Reglementair"]
    for col_base in board_column_names:
        column_order.append(col_base)
        column_order.append(f"{col_base} %")
    column_order.append("Toelichting")
    column_order.append("Vorige keer")
    st.dataframe(
        table_rows, use_container_width=True, hide_index=True,
        column_config=column_config, column_order=column_order,
        row_height=56,  # genoeg ruimte voor de 2 tekstregels per matchkolom
    )
    st.caption(
        "Elke matchkolom toont de koppels op 2 regels (koppel / vs tegenstander); de winkans staat in de "
        "kolom ernaast als apart, sorteerbaar percentage. 'Reglementair' toont ⚠️ NIET voor een bewust "
        "omgedraaide, niet-toegelaten variant (enkel zichtbaar als je de checkbox hierboven aanvinkt). "
        "De kolom 'Toelichting' toont ALTIJD de exacte OFFICIËLE puntensom per duo die de bordvolgorde "
        "bepaalt (nooit de padelstat-score) — zo kan je die basis meteen zelf controleren."
    )
    if not show_all and len(all_matchups) > len(display_matchups):
        st.caption(f"Beste {len(display_matchups)} van {len(all_matchups)} matchups getoond — vink hierboven aan om alles te zien.")
    st.divider()

    _render_best_worst_case_per_own_lineup(all_matchups, name_lookup_global)

    # PADEL_ANALYSIS_AI_FOLLOWUP_ON_MATCHUPS_2026-09-18 (op verzoek van
    # Kim: "zorg dat ik kan doorvragen"): AI-sectie voor deze matchup-tabel
    # is nu een ECHTE, doorlopende chat i.p.v. 1 eenmalige knop.
    ai_history_key = f"all_matchups_chat_history_v2_{opp['ploeg_id']}"
    if ai_history_key not in st.session_state:
        st.session_state[ai_history_key] = []
    ai_history = st.session_state[ai_history_key]
    if taa is not None and report is not None:
        col_ai_start, col_ai_clear = st.columns([3, 1])
        with col_ai_start:
            ai_start_label = "🤖 AI-inzicht over de beste matchups" if not ai_history else "🤖 AI-inzicht opnieuw genereren (nieuw gesprek)"
            if st.button(ai_start_label, key=f"all_matchups_ai_{opp['ploeg_id']}"):
                with st.spinner("AI analyseert..."):
                    try:
                        antwoord = taa.analyze_lineup_options(report, display_matchups[:5], name_lookup_global)
                    except Exception as exc:
                        antwoord = f"⚠️ Mislukt: {exc}"
                st.session_state[ai_history_key] = [{"role": "assistant", "content": antwoord}]
                st.rerun()
        with col_ai_clear:
            if ai_history and st.button("🗑️ Nieuw gesprek", key=f"all_matchups_ai_clear_{opp['ploeg_id']}"):
                st.session_state[ai_history_key] = []
                st.rerun()
        if ai_history:
            st.caption("Gesprek tot nu toe:")
            for msg in ai_history:
                role_label = "🙋 Jij" if msg["role"] == "user" else "🤖 AI"
                with st.container(border=True):
                    st.markdown(f"**{role_label}**")
                    st.markdown(msg["content"])
            followup_question = st.text_area(
                "Doorvraag", key=f"all_matchups_ai_followup_{opp['ploeg_id']}", height=70,
                label_visibility="collapsed", placeholder="Bv. En wat als Nico niet kan spelen?",
            )
            if st.button("💬 Vraag door", key=f"all_matchups_ai_followup_btn_{opp['ploeg_id']}"):
                if not followup_question.strip():
                    st.warning("Typ eerst een vraag.")
                else:
                    with st.spinner("AI denkt na..."):
                        try:
                            vervolg = taa.analyze_lineup_options(
                                report, display_matchups[:5], name_lookup_global, history=ai_history,
                            )
                        except Exception as exc:
                            vervolg = f"⚠️ Mislukt: {exc}"
                    st.session_state[ai_history_key] = ai_history + [
                        {"role": "user", "content": followup_question.strip()},
                        {"role": "assistant", "content": vervolg},
                    ]
                    st.rerun()

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
                        + ("" if m.get("fully_compliant", True) else " [⚠️ niet-reglementaire variant]")
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
    with st.expander("ℹ️ Wat betekenen winkans, verwachte matchen, synergie, puntengrens en 'Reglementair'?", expanded=False):
        st.markdown(
            "- **Winkans per match**: een RUWE schatting (logistische functie op het ratingverschil), "
            "gebaseerd op padelstats.be playing strength waar bekend, anders het officiële klassement "
            "als terugval — PER SPELER individueel.\n"
            "- **Verwacht aantal gewonnen matchen**: de som van de winkansen over alle matchen van "
            "die opstelling.\n"
            "- **Winkans-kolom**: de winkans per match staat als apart, sorteerbaar percentage naast "
            "de kolom met de koppelnamen.\n"
            "- **Officiële regel (art. 6.6)**: binnen elke ROTATIE speelt het duo met de HOOGSTE SOM "
            "van de 2 OFFICIËLE klassementen op het laagst genummerde match van die rotatie "
            "(RotatieR-1 vóór RotatieR-2). Bij een GELIJKSPEL in officieel klassement mag de ploeg zelf "
            "kiezen (BEIDE volgordes worden dan getoond); bij een verschil is enkel de sterkste-eerst-"
            "volgorde toegelaten.\n"
            "- **Reglementair-kolom**: ✅ = deze matchup-rij gebruikt overal de reglementair verplichte "
            "(of, bij gelijkspel, een even geldige) bordvolgorde. ⚠️ NIET = een BEWUST omgedraaide "
            "variant (enkel zichtbaar als je de bijhorende checkbox aanvinkt) - dit zou een overtreding "
            "van art. 6.6 zijn en dient enkel om het best-case/worst-case-bereik van een koppelkeuze in "
            "te schatten, NOOIT als effectieve wedstrijdopstelling.\n"
            "- **Rotatie-veiligheid**: een speler kan nooit in 2 GELIJKTIJDIGE matchen van dezelfde "
            "rotatie staan.\n"
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
