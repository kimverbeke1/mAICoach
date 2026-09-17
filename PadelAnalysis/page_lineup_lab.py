"""
page_lineup_lab.py — "🧩 Opstelling-analyse"-pagina (Volgende match,
Opstelling-scenario's, Rotatieplanner, Opgeslagen analyses).

PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py,
ongewijzigde logica. Dit is bewust het GROOTSTE van de opgesplitste
bestanden (bevat de rotatieplanner-combinatoriek), maar nog altijd een
fractie van de oorspronkelijke ~1800-regel dashboard.py.

PADEL_ANALYSIS_MANUAL_POULE_URL_PERSIST_2026-09-15 (op verzoek van Kim):
Het invoerveld voor een handmatige poule-URL bewaarde vroeger naar het
AUTOMATISCHE Firestore-veld poule_reeks_url. Vervangen door
manual_poule_input.render(), dat schrijft naar poule_reeks_url_manual
(heeft ALTIJD voorrang, ook bij force=True).

PADEL_ANALYSIS_RENDER_ORDER_2026-09-15 (op verzoek van Kim):
Volgorde is nu Volgende match -> OVERZICHTSTABEL + detail per speler ->
Opstelling-scenario's + Rotatieplanner -> AI-inzichten.

PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15 (op verzoek van Kim):
Fix zit in lineup_lab.py: een opponent_ratings-dict wordt EENMALIG
opgebouwd en meegegeven aan zowel de scenario-berekening als de
Rotatieplanner, zodat matchup-edges consistent op 1 schaal berekend worden.

PADEL_ANALYSIS_LINEUP_LOAD_PERSIST_FIX_2026-09-16 (op verzoek van Kim):
De "📅 Volgende match laden"-knop gebruikt dashboard_common.
_load_poule_schedule_robust(), Playwright-gebaseerd, Firestore-persisterend.

PADEL_ANALYSIS_ALL_COMBINATIONS_AGGREGATE_2026-09-16 (op verzoek van Kim):
_SCENARIO_CANDIDATE_POOL (=400) wordt expliciet meegegeven aan
optimize_lineup_vs_scenario(), zodat ECHT alle haalbare koppelverdelingen
meedingen. Een aggregaatscore-sectie toont per unieke koppelverdeling het
gemiddelde/min/max over alle scenario's waarin ze voorkwam.

PADEL_ANALYSIS_OPPONENT_REFERENCE_FIX_2026-09-17 (op verzoek van Kim):
_render_previous_opponent_lineup()/_render_match1_frequency_opponent():
VOLLEDIG herbouwd op bundle["previous_fixtures"] (de TEGENSTANDER), niet
langer op ons eigen team.

PADEL_ANALYSIS_OFFICIAL_BOARD_ORDER_FIX_2026-09-17 (op verzoek van Kim):
De officiële regel wordt nu ECHT afgedwongen in lineup_lab.py
(optimize_lineup_vs_scenario) i.p.v. een vrije score-maximaliserende
toewijzing. Deze pagina hoefde zelf niet aangepast te worden — verder
uitgebreid/gecorrigeerd hieronder.

PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17 (op verzoek
van Kim): nieuwe sectie "Alle theoretische tegenstander-opstellingen" -
berekent ALLE wiskundig mogelijke opstellingen van een gekozen groep
tegenstander-spelers (niet enkel de historisch al gespeelde), met voor elk
onze beste tegenzet.

--------------------------------------------------------------------------
PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17 (op verzoek van Kim, na het
aanleveren van Reglement_Padel_Senior_Cup.pdf — 3 concrete vragen)
--------------------------------------------------------------------------
Kim's vragen:
  1. "paarverdelingen die niet aan de grenzen voldoen mag je uitsluiten en
     niet tonen" — combinaties buiten de toegelaten punten-per-rotatie-
     grenzen (art. 2.1/9.3.3/9.3.4 van het reglement) worden nu ECHT
     uitgesloten (zie lineup_lab.optimize_lineup_vs_scenario(), dat de
     nieuwe `tournament_rules_dict`-parameter gebruikt om ongeldige
     kandidaten te verwijderen VOORDAT ze getoond worden).
  2. "match 1 van de rotatie = sterkste opstelling" — bevestigd EN
     gecorrigeerd: de vergelijking gebeurt op de SOM van de klassementen
     van de 2 spelers per duo (niet het hoogste individuele klassement,
     wat de vorige implementatie foutief deed — zie lineup_lab.py:
     PADEL_ANALYSIS_SUM_BASED_PAIR_STRENGTH_2026-09-17), en dit geldt PER
     ROTATIE (2 gelijktijdige wedstrijden), niet over de hele ontmoeting.
  3. "Ik heb specifiek het reglement van de senior cup [...] Belangrijkste
     is dat die parameters getoond worden en eventueel instelbaar zijn per
     tornooi versie" — nieuwe functie _render_tournament_rules_selector()
     hieronder: een dropdown Tornooi -> Categorie -> Afdeling (standaard:
     Padel Senior Cup 2026 / Open), met de actieve punten-/klassement-
     grenzen ALTIJD zichtbaar als caption (tournament_rules.
     format_rules_caption()). Andere tornooien (Mixed, Open, Vrouwen) zijn
     nog niet ingevuld in tournament_rules.py — de keuzelijst toont ze pas
     zodra Kim het bijhorende reglement bezorgt en ze daar toegevoegd
     worden; tot dan werkt de app voor een niet-ingevulde combinatie
     gewoon verder ZONDER puntenfilter (rules=None, expliciet gemeld via
     de caption, geen crash).

De gekozen tornooi/categorie/afdeling wordt PER TEGENSTANDER-PLOEG
(opp['ploeg_id']) onthouden in st.session_state, en doorgegeven aan:
  - de Rotatieplanner (_render_rotation_planner/_generate_rotation_candidates)
  - de historische Opstelling-scenario's (_render_opstelling_scenario)
  - de nieuwe theoretische scenario's (_render_theoretical_opponent_scenarios)
zodat alle drie met exact dezelfde, zichtbare regelset rekenen.
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

# PADEL_ANALYSIS_MANUAL_POULE_URL_PERSIST_2026-09-15: optionele import, zodat
# deze pagina blijft werken ook als het component (nog) niet mee gedeployed is.
try:
    import manual_poule_input
except Exception:  # noqa: BLE001  pragma: no cover
    manual_poule_input = None

# PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17: optionele import, zodat deze
# pagina blijft werken (zonder puntenfilter) ook als tournament_rules.py
# nog niet mee gedeployed is.
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


def _render_manual_url_fallback(
    sel_player_id: str,
    sel_label: str,
    key_prefix: str,
    expanded: bool = True,
) -> None:
    """PADEL_ANALYSIS_MANUAL_POULE_URL_PERSIST_2026-09-15."""
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
            "achtergrond (GitHub Actions). Duurt meestal enkele minuten; daarna "
            "verschijnt de nieuwe volgende match hier automatisch."
        )
        render_cloud_scrape_trigger(
            key_prefix=f"vm_schema_{sel_player_id}",
            player_ids=str(sel_player_id),
            mode="missing",
            label="🔄 Schema nu verversen",
        )


def _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches):
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14."""
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
        st.warning(
            "Kon niet automatisch bepalen welke ploeg dit is op de poule-pagina. "
            "Kies hieronder eenmalig je eigen team."
        )
        team_names = sorted({f["home_name"] for f in fixtures} | {f["away_name"] for f in fixtures})
        chosen_team = st.selectbox(
            "Jouw team in dit schema:", [""] + team_names, key=f"manual_team_pick_{sel_player_id}"
        )
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
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14."""
    st.markdown('<div class="section-header">📅 Volgende match</div>', unsafe_allow_html=True)
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"
    _render_schema_refresh_button(sel_player_id)
    sel_doc = fb.get_player(sel_player_id)
    own_interclub_matches = [
        m for m in (sel_doc or {}).get("matches", [])
        if m.get("match_type") == "interclub"
    ]

    def _finish(fixtures, reeks_url_val):
        own_ploeg_id = _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches)
        if not own_ploeg_id:
            return None
        header_result = osu.render_scout_header(
            sel_player_id=str(sel_player_id), fixtures=fixtures, own_ploeg_id=own_ploeg_id,
        )
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
        most_recent = sorted(
            ic_with_url,
            key=lambda m: _parse_match_date(m.get("match_date")) or (0, 0, 0),
            reverse=True,
        )[0]
        auto_reeks_url = most_recent["reeks_url"]

    saved_url = _get_saved_poule_url(sel_player_id)
    reeks_url = st.session_state.get(override_url_key) or saved_url or auto_reeks_url

    if not reeks_url:
        st.info(
            f"Nog geen poule/tabel-schema gekend voor {sel_label}. Dit wordt normaal "
            "automatisch opgehaald door de dagelijkse update (of via de knop hierboven "
            "op de cloud). Je kan hieronder ook zelf de poule/tabel-link plakken — "
            "die wordt blijvend onthouden."
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
    """PADEL_ANALYSIS_SCENARIO_DEFAULT_RECENT_LINEUP_2026-09-10."""
    try:
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs, index = _load_encounter_index(profile_ids)
        all_encounters = ll.list_encounters(index)
        own_keys = [
            key for key, _ in all_encounters
            if any(pid == sel_player_id for pid, _ in index[key])
        ]
        if not own_keys:
            return set()

        def _encounter_date(key):
            dates = []
            for _, entry in index[key]:
                d = _parse_match_date(entry.get("match_date"))
                if d:
                    dates.append(d)
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
    """PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15."""
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
    """PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17."""
    out = {}
    for pid in player_ids:
        try:
            rank = _official_current_rank(pid)
        except Exception:
            rank = None
        if rank is not None:
            out[str(pid)] = rank
    return out


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17: reglement-selector
# ─────────────────────────────────────────────
def _render_tournament_rules_selector(ploeg_id: str):
    """PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17 (op verzoek van Kim,
    vraag 3): dropdown Tornooi -> Categorie -> Afdeling, PER TEGENSTANDER-
    PLOEG onthouden (session_state), met de actieve punten-/klassement-
    grenzen ALTIJD zichtbaar als caption — zodat op elk moment duidelijk is
    met welke reglementsversie gerekend wordt.

    Geeft (rules: Optional[dict], label: str) terug. rules is None zodra
    tournament_rules.py niet beschikbaar is, of de gekozen combinatie
    (tornooi/categorie/afdeling) nog niet is ingevuld — in dat geval wordt
    er verderop NERGENS gefilterd op puntengrenzen (expliciet gemeld via de
    caption, geen crash)."""
    if tr is None:
        st.caption(
            "⚠️ tournament_rules.py niet gevonden — reglement-gebaseerde puntenfilter niet beschikbaar. "
            "Alle combinaties worden getoond zonder puntencontrole."
        )
        return None, None

    with st.expander("📖 Reglement / afdeling (bepaalt de toegelaten puntengrenzen per rotatie)", expanded=False):
        tournaments = tr.list_tournaments()
        default_tournament_idx = tournaments.index(tr.DEFAULT_TOURNAMENT) if tr.DEFAULT_TOURNAMENT in tournaments else 0
        tournament = st.selectbox(
            "Tornooi", tournaments, index=default_tournament_idx,
            key=f"rules_tournament_{ploeg_id}",
            help="Vandaag enkel Padel Senior Cup volledig ingevuld. Andere tornooien (Mixed, Open, Vrouwen) "
                 "kunnen later toegevoegd worden zodra het bijhorende reglement bezorgd is.",
        )
        categories = tr.list_categories(tournament)
        if not categories:
            st.warning(f"Nog geen categorieën ingevuld voor '{tournament}'.")
            return None, None
        default_cat_idx = categories.index(tr.DEFAULT_CATEGORY) if tr.DEFAULT_CATEGORY in categories else 0
        category = st.selectbox(
            "Categorie", categories, index=default_cat_idx, key=f"rules_category_{ploeg_id}",
        )
        afdelingen = tr.list_afdelingen(tournament, category)
        if not afdelingen:
            st.warning(f"Nog geen afdelingen ingevuld voor '{tournament}' / {category}.")
            return None, None
        afdeling = st.selectbox(
            "Afdeling", afdelingen, key=f"rules_afdeling_{ploeg_id}",
            format_func=lambda a: f"Afdeling {a}",
        )
        rules = tr.get_afdeling_rules(tournament, category, afdeling)
        st.caption(tr.format_rules_caption(tournament, category, afdeling, rules))
        label = f"{tournament} — {category}, afdeling {afdeling}"
        return rules, label


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_OPPONENT_REFERENCE_FIX_2026-09-17: tegenstander-referentie
# ─────────────────────────────────────────────
def _render_previous_opponent_lineup(bundle: dict) -> None:
    """PADEL_ANALYSIS_OPPONENT_REFERENCE_FIX_2026-09-17 (op verzoek van Kim)."""
    previous_fixtures = bundle.get("previous_fixtures") or []
    if not previous_fixtures:
        return

    with st.expander(
        f"📋 Tegenstander — eerdere ontmoeting(en) ter referentie ({len(previous_fixtures)})",
        expanded=False,
    ):
        st.caption(
            "De opstelling die de TEGENSTANDER gebruikte in hun vorige, al gespeelde wedstrijd(en) dit "
            "seizoen. 'Bord' is de vermoedelijke volgorde zoals de dubbels op het uitslagenblad staan — "
            "geen letterlijk bevestigd 'Wedstrijd 1/2/3'-label uit de brondata."
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
                    "Bord": f"Bord {b.get('board_position', '?')}",
                    "Koppel": namen,
                    "Klassement": " / ".join(rankings) if rankings else "onbekend",
                    "Score": b.get("score") or "onbekend",
                })
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
        if not toonde_iets:
            st.info("Geen bord-detail beschikbaar voor de gekende eerdere ontmoeting(en).")


def _render_match1_frequency_opponent(bundle: dict) -> None:
    """PADEL_ANALYSIS_OPPONENT_REFERENCE_FIX_2026-09-17 (op verzoek van Kim)."""
    previous_fixtures = bundle.get("previous_fixtures") or []
    boards_met_positie = [
        b for fx in previous_fixtures for b in (fx.get("boards") or [])
        if b.get("board_position") is not None and len(b.get("opponent_pair") or []) == 2
    ]
    if not boards_met_positie:
        return

    tellingen: dict = {}
    namen: dict = {}
    for b in boards_met_positie:
        pos = b["board_position"]
        for p in b["opponent_pair"]:
            uid = p.get("user_id")
            if not uid:
                continue
            namen[uid] = p.get("name", uid)
            tellingen.setdefault(uid, {})
            tellingen[uid][pos] = tellingen[uid].get(pos, 0) + 1

    with st.expander(
        f"📊 Tegenstander — bordpositie-frequentie (over {len(previous_fixtures)} eerdere ontmoeting(en))",
        expanded=False,
    ):
        st.caption(
            "Hoe vaak elke tegenstander-speler op elk bord (vermoedelijke volgorde, zie de sectie "
            "hierboven) stond in hun eerdere, gekende wedstrijden dit seizoen. Puur beschrijvend: de "
            "tegenstander kan bij de volgende ontmoeting evengoed exact hetzelfde herhalen als "
            "volledig doorschuiven zodat iedereen met iedereen speelt — dit is geen voorspelling."
        )
        if len(previous_fixtures) <= 1:
            st.caption(
                "⚠️ Slechts 1 eerdere ontmoeting gekend voor deze tegenstander — de verdeling hieronder "
                "is dus gebaseerd op één enkel datapunt per speler, geen patroon over meerdere "
                "wedstrijden heen."
            )
        alle_posities = sorted({pos for counts in tellingen.values() for pos in counts})
        rows = []
        for uid, counts in sorted(tellingen.items(), key=lambda kv: -(kv[1].get(1, 0))):
            totaal = sum(counts.values())
            row = {"Speler": namen.get(uid, uid)}
            for pos in alle_posities:
                aantal = counts.get(pos, 0)
                pct = round(100 * aantal / totaal, 0) if totaal else 0
                row[f"Bord {pos}"] = f"{aantal}x ({int(pct)}%)"
            rows.append(row)
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _most_recent_opponent_player_ids(bundle: dict) -> set:
    """PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17."""
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
# PADEL_ANALYSIS_ROTATION_PLANNER_REDESIGN_2026-09-14
# ─────────────────────────────────────────────
def _count_perfect_matchings(n: int) -> int:
    """(n-1)!! - aantal mogelijke volledige koppelverdelingen van n spelers."""
    if n < 2 or n % 2 != 0:
        return 0
    result = 1
    k = n - 1
    while k > 0:
        result *= k
        k -= 2
    return result


_ROTATION_EXHAUSTIVE_LIMIT = 400


def _rank_pairs_by_official_rank(pairs: list, official_ranks: dict) -> list:
    """PADEL_ANALYSIS_MATCH1_STRONGEST_RULE_2026-09-14 / PADEL_ANALYSIS_
    SUM_BASED_PAIR_STRENGTH_2026-09-17: dunne wrapper rond de canonieke,
    SOM-gebaseerde ll.rank_pairs_by_official_rank()."""
    return ll.rank_pairs_by_official_rank(pairs, official_ranks)


def _generate_rotation_candidates(
    available_ids: list,
    synergy_fn,
    official_ranks: dict,
    excluded_pairs: set,
    opponent_boards=None,
    player_ratings=None,
    opponent_ratings=None,
    max_results: int = 10,
    tournament_rules_dict=None,
):
    """Genereert kandidaat-koppelverdelingen voor ÉÉN rotatie, EXHAUSTIEF
    voor kleine/gemiddelde groepen.

    PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17: `tournament_rules_dict`
    (optioneel) wordt doorgegeven aan optimize_lineup_vs_scenario(), zodat
    kandidaten die de reglementaire puntengrens per rotatie overschrijden
    NOOIT als optie verschijnen (Kim's vraag 1)."""
    n = len(available_ids)
    if n < 2 or n % 2 != 0:
        return [], 0
    total_possible = _count_perfect_matchings(n)
    top_n = min(max(total_possible, 1), _ROTATION_EXHAUSTIVE_LIMIT)
    required = {pid: 1 for pid in available_ids}
    results = []
    if opponent_boards and player_ratings is not None:
        raw, truncated = ll.optimize_lineup_vs_scenario(
            available_ids, required, synergy_fn, opponent_boards, player_ratings,
            player_official_ranks=official_ranks, opponent_ratings=opponent_ratings,
            top_n=top_n, candidate_pool=_ROTATION_EXHAUSTIVE_LIMIT,
            tournament_rules_dict=tournament_rules_dict,
        )
        for option in raw:
            pairs = [frozenset(a["our_pair"]) for a in option["assignment"]]
            if any(p in excluded_pairs for p in pairs):
                continue
            pair_to_assignment = {frozenset(a["our_pair"]): a for a in option["assignment"]}
            ordered = _rank_pairs_by_official_rank(pairs, official_ranks)
            assignment_ordered = [pair_to_assignment[p] for p in ordered]
            results.append({
                "score": option["total_score"],
                "ordered_pairs": ordered,
                "assignment": assignment_ordered,
                "rotations": option.get("rotations"),
            })
    else:
        raw, truncated = ll.optimize_lineup(available_ids, required, synergy_fn, top_n=top_n)
        for score, pairs in raw:
            pairs_fs = [frozenset(p) for p in pairs]
            if any(p in excluded_pairs for p in pairs_fs):
                continue
            # PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17: ook zonder
            # tegenstander-scenario (enkel eigen synergie) de puntengrens
            # per rotatie toepassen, indien een regelset actief is.
            rotation_eval = ll.filter_and_order_lineup_by_rotations(
                pairs_fs, official_ranks, rules=tournament_rules_dict,
            )
            if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
                continue
            ordered = rotation_eval["ordered_pairs"]
            results.append({
                "score": score, "ordered_pairs": ordered, "assignment": None,
                "rotations": rotation_eval["rotations"],
            })
    results.sort(key=lambda r: -r["score"])
    return results[:max_results], total_possible


def _lineup_options_for_ai(candidates: list, name_lookup: dict) -> list:
    """Zet _generate_rotation_candidates()-resultaten om naar het formaat dat
    team_ai_advisor.analyze_lineup_options() verwacht."""
    out = []
    for cand in candidates:
        assignment = []
        if cand["assignment"]:
            for a in cand["assignment"]:
                assignment.append({
                    "our_pair": tuple(a["our_pair"]),
                    "synergy": a.get("synergy", 0.0),
                    "edge": a.get("edge", 0.0),
                    "opponent_board": a.get("opponent_board", {}),
                })
        else:
            for pair in cand["ordered_pairs"]:
                p1, p2 = tuple(pair)
                assignment.append({
                    "our_pair": (p1, p2),
                    "synergy": 0.0,
                    "edge": 0.0,
                    "opponent_board": {"opponent_pair": []},
                })
        out.append({"total_score": cand["score"], "assignment": assignment})
    return out


def _render_rotation_points_caption(rotations: list, name_lookup_global: dict) -> None:
    """PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17: toont, indien beschikbaar,
    de berekende punten-per-rotatie + of dat binnen de reglementsgrenzen
    valt — zodat Kim ALTIJD ziet waarom een combinatie wel/niet getoond
    wordt, i.p.v. enkel een stille uitsluiting."""
    if not rotations:
        return
    for i, rot in enumerate(rotations, start=1):
        if rot.get("total_points") is None:
            continue
        icon = "✅" if rot.get("valid", True) else "❌"
        st.caption(f"{icon} Rotatie {i}: {rot.get('reason', '')}")


def _render_rotation_planner(
    available_ids: list,
    synergy_fn,
    official_ranks: dict,
    name_lookup_global: dict,
    opp: dict,
    opponent_boards=None,
    player_ratings=None,
    opponent_ratings=None,
    report_for_ai=None,
    tournament_rules_dict=None,
    rules_label=None,
):
    """PADEL_ANALYSIS_ROTATION_PLANNER_REDESIGN_2026-09-14, uitgebreid met
    PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17."""
    st.markdown('<div class="section-header">🔁 Rotatieplanner</div>', unsafe_allow_html=True)
    regel_tekst = (
        f" (volgens {rules_label})" if rules_label else ""
    )
    st.caption(
        "Alle mogelijke koppelverdelingen voor de eerstvolgende rotatie, gerangschikt van beste naar "
        "slechtste. Klik aan wie/welke combinatie effectief speelde (of zal spelen) om door te gaan naar "
        "de volgende rotatie - elke speler krijgt zo nooit twee keer dezelfde partner. Het duo met de "
        f"hoogste SOM van de 2 klassementen staat steeds op Match 1{regel_tekst}, en speelt (sinds de "
        "officiële-regel-fix) ook altijd verplicht tegen HUN sterkste bord - geen vrije toewijzing meer. "
        "Combinaties die de toegelaten puntengrens per rotatie overschrijden worden niet getoond."
    )
    if len(available_ids) < 2 or len(available_ids) % 2 != 0:
        st.info("Selecteer een even aantal spelers (bij 'Beschikbare eigen spelers' hierboven) om de rotatieplanner te gebruiken.")
        return
    ploeg_id = opp["ploeg_id"]
    locked_key = f"rot_locked_v2_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if locked_key not in st.session_state:
        st.session_state[locked_key] = []
    locked_rotations = st.session_state[locked_key]
    for rot_idx, pairs in enumerate(locked_rotations, start=1):
        st.markdown(f"**Rotatie {rot_idx} (bevestigd):**")
        for match_idx, pair in enumerate(pairs, start=1):
            p1, p2 = tuple(pair)
            st.write(f"Match {match_idx}: {name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}")
        if st.button(f"✏️ Rotatie {rot_idx} wijzigen", key=f"rot_edit_v2_{ploeg_id}_{rot_idx}"):
            st.session_state[locked_key] = locked_rotations[: rot_idx - 1]
            st.rerun()
        st.markdown("---")
    excluded_pairs = {p for rot in locked_rotations for p in rot}
    next_rotation_num = len(locked_rotations) + 1
    candidates, total_possible = _generate_rotation_candidates(
        available_ids, synergy_fn, official_ranks, excluded_pairs,
        opponent_boards=opponent_boards, player_ratings=player_ratings,
        opponent_ratings=opponent_ratings,
        max_results=15, tournament_rules_dict=tournament_rules_dict,
    )
    if not candidates:
        if total_possible == 0:
            st.info("Geen geldige koppelverdeling meer mogelijk (oneven aantal spelers of geen spelers beschikbaar).")
        elif tournament_rules_dict is not None:
            st.warning(
                f"Geen enkele van de {total_possible} mogelijke koppelverdelingen valt binnen de "
                "toegelaten puntengrens per rotatie voor de gekozen afdeling — of alle zijn al gebruikt "
                "in eerdere rotaties. Overweeg een andere afdeling te kiezen, of pas de spelersselectie aan."
            )
        else:
            st.warning(
                f"Alle {total_possible} mogelijke koppelverdelingen voor deze groep zijn al gebruikt in "
                "eerdere rotaties (elke speler heeft dan al met elke andere speler samengespeeld). Geen "
                "nieuwe rotatie meer mogelijk zonder een partner te herhalen."
            )
        return
    st.markdown(f"**Rotatie {next_rotation_num} - kies de effectieve/geplande combinatie:**")
    if tournament_rules_dict is not None and total_possible > 0:
        st.caption(
            f"{len(candidates)} van de {total_possible} wiskundig mogelijke koppelverdelingen voldoen aan "
            "de reglementaire puntengrens per rotatie (ongeldige combinaties zijn uitgesloten, niet getoond)."
        )
    elif total_possible > len(candidates):
        st.caption(f"Top {len(candidates)} van {total_possible} mogelijke combinaties getoond (op score gerangschikt).")
    else:
        st.caption(f"Alle {total_possible} mogelijke combinaties voor deze rotatie, op score gerangschikt.")
    option_labels = []
    for i, cand in enumerate(candidates):
        parts = []
        for match_idx, pair in enumerate(cand["ordered_pairs"], start=1):
            p1, p2 = tuple(pair)
            parts.append(f"M{match_idx}: {name_lookup_global.get(p1,p1)}/{name_lookup_global.get(p2,p2)}")
        prefix = "★ " if i == 0 else ""
        option_labels.append(f"{prefix}{' | '.join(parts)}  (score {cand['score']:.3f})")
    chosen_idx = st.radio(
        "Combinaties", list(range(len(candidates))), format_func=lambda i: option_labels[i],
        key=f"rot_choice_v2_{ploeg_id}_{next_rotation_num}", label_visibility="collapsed",
    )
    chosen = candidates[chosen_idx]
    _render_rotation_points_caption(chosen.get("rotations"), name_lookup_global)
    if chosen["assignment"]:
        with st.expander("Detail van de gekozen combinatie (synergie + matchup-edge per paar)", expanded=False):
            for match_idx, a in enumerate(chosen["assignment"], start=1):
                p1, p2 = a["our_pair"]
                opp_names = " / ".join(p.get("name", "?") for p in a.get("opponent_board", {}).get("opponent_pair", []))
                schaal = a.get("edge_scale")
                schaal_txt = {"padelstat": "playing strength", "official": "officieel klassement"}.get(schaal, schaal or "?")
                st.write(
                    f"Match {match_idx}: **{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
                    f"(synergie {a['synergy']}) — vs **{opp_names or 'onbekend'}** "
                    f"(matchup-edge {a['edge']:+.2f}, o.b.v. {schaal_txt})"
                )
    ai_key = f"rot_ai_v2_{ploeg_id}_{next_rotation_num}"
    if taa is not None and report_for_ai is not None:
        if st.button("🤖 AI-inzicht over deze combinaties", key=f"rot_ai_btn_v2_{ploeg_id}_{next_rotation_num}"):
            with st.spinner("AI analyseert de combinaties..."):
                try:
                    ai_options = _lineup_options_for_ai(candidates[:5], name_lookup_global)
                    st.session_state[ai_key] = taa.analyze_lineup_options(report_for_ai, ai_options, name_lookup_global)
                except Exception as exc:
                    st.session_state[ai_key] = f"⚠️ Mislukt: {exc}"
        if st.session_state.get(ai_key):
            st.markdown(st.session_state[ai_key])
    if st.button(f"✅ Bevestig rotatie {next_rotation_num}", key=f"rot_confirm_v2_{ploeg_id}_{next_rotation_num}", type="primary"):
        st.session_state[locked_key] = locked_rotations + [chosen["ordered_pairs"]]
        st.rerun()


# ─────────────────────────────────────────────
# Opstelling-scenario's (HISTORISCH: op basis van al gespeelde tegenstander-wedstrijden)
# ─────────────────────────────────────────────
_SCENARIO_CANDIDATE_POOL = 400
_SCENARIO_SAVE_TOP_N = 400
_SCENARIO_DISPLAY_DEFAULT_N = 10
_AGGREGATE_DISPLAY_DEFAULT_N = 20

_THEORETICAL_MAX_VARIANTS = 300
_THEORETICAL_DISPLAY_DEFAULT_N = 10


def _aggregate_scenario_scores(scenarios: list) -> list:
    """PADEL_ANALYSIS_ALL_COMBINATIONS_AGGREGATE_2026-09-16."""
    scores_by_combo: dict = {}
    for entry in scenarios:
        for option in (entry.get("results") or []):
            pairs = sorted(
                tuple(sorted(a["our_pair"])) for a in option.get("assignment", []) or []
            )
            if not pairs:
                continue
            combo_key = tuple(pairs)
            scores_by_combo.setdefault(combo_key, []).append(option["total_score"])

    aggregated = []
    for combo_key, scores in scores_by_combo.items():
        aggregated.append((combo_key, {
            "avg": sum(scores) / len(scores),
            "min": min(scores),
            "max": max(scores),
            "count": len(scores),
        }))
    aggregated.sort(key=lambda item: (-item[1]["count"], -item[1]["avg"]))
    return aggregated


def _render_theoretical_opponent_scenarios(
    bundle: dict,
    opp: dict,
    available_ids: list,
    max_per_player: dict,
    total_boards: int,
    synergy_fn,
    player_ratings: dict,
    official_ranks: dict,
    opponent_ratings: dict,
    report,
    name_lookup_global: dict,
    tournament_rules_dict=None,
    rules_label=None,
) -> None:
    """PADEL_ANALYSIS_ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17, met
    reglementsfilter sinds PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17."""
    st.divider()
    st.markdown('<div class="section-header">🧮 Alle theoretische tegenstander-opstellingen</div>', unsafe_allow_html=True)
    st.caption(
        "Kies hieronder WIE van de tegenstander waarschijnlijk beschikbaar is. We berekenen dan ALLE "
        "mogelijke opstellingen die zij daaruit kunnen vormen (met de officiële regel toegepast: hun "
        "sterkste duo — som van de 2 klassementen — op Match 1, verplicht tegen ons sterkste duo op "
        "Match 1), en voor ELK daarvan onze beste tegenzet."
    )
    if tournament_rules_dict is not None:
        st.caption(f"📖 Puntengrens per rotatie actief: {rules_label}. Ongeldige combinaties worden uitgesloten.")

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
            f"Standaard vooraf geselecteerd: de {len(default_opp_labels)} speler(s) uit hun meest "
            "recente gekende ontmoeting. Pas gerust aan - bv. verklein deze lijst na rotatie 1, "
            "zodra bekend is wie er bij hen echt speelde, om het aantal scenario's verder te beperken."
        )
    else:
        default_opp_labels = opp_labels[: min(2 * total_boards, len(opp_labels))]

    chosen_opp_labels = st.multiselect(
        "Beschikbare tegenstander-spelers",
        opp_labels,
        default=default_opp_labels,
        key=f"theoretical_opp_players_{opp['ploeg_id']}",
    )
    chosen_opp_ids = [opp_label_to_id[lbl] for lbl in chosen_opp_labels]

    needed = 2 * total_boards
    if len(chosen_opp_ids) < needed:
        st.info(
            f"Selecteer minstens {needed} tegenstander-speler(s) (2 per wedstrijd, {total_boards} "
            "wedstrijden) om theoretische opstellingen te kunnen berekenen."
        )
        return

    chosen_opp_players = [p for p in unique_players if str(p.get("user_id")) in chosen_opp_ids]
    opponent_official_ranks = _opponent_official_ranks(chosen_opp_ids)
    for pid in chosen_opp_ids:
        if pid not in opponent_official_ranks and opponent_ratings.get(pid) is not None:
            opponent_official_ranks[pid] = opponent_ratings[pid]

    lineups, meta = ll.generate_all_opponent_lineups(
        chosen_opp_players, total_boards,
        opponent_official_ranks=opponent_official_ranks,
        max_variants=_THEORETICAL_MAX_VARIANTS,
    )

    if meta["resting_combinations"] > 1:
        st.caption(
            f"🔢 {len(chosen_opp_ids)} beschikbare speler(s), {needed} nodig per wedstrijdmoment -> "
            f"{meta['resting_combinations']} mogelijke keuzes wie er rust, "
            f"× hun mogelijke koppelverdelingen = **{meta['total_theoretical']}** theoretische opstellingen."
        )
    else:
        st.caption(f"🔢 **{meta['total_theoretical']}** theoretische opstellingen mogelijk voor deze {len(chosen_opp_ids)} spelers.")

    if meta["truncated"]:
        st.warning(
            f"⚠️ Er zijn {meta['total_theoretical']} theoretische opstellingen mogelijk, maar enkel de "
            f"eerste {_THEORETICAL_MAX_VARIANTS} worden berekend (performance-limiet). Verklein de "
            "selectie hierboven (bv. na rotatie 1) voor een volledige dekking."
        )

    if not lineups:
        st.info("Geen theoretische opstellingen om te tonen.")
        return

    compute_key = f"theoretical_results_{opp['ploeg_id']}"
    sig_key = f"theoretical_signature_{opp['ploeg_id']}"
    signature = (
        tuple(sorted(available_ids)), tuple(sorted(max_per_player.items())),
        int(total_boards), tuple(sorted(chosen_opp_ids)),
        str(tournament_rules_dict),
    )
    needs_compute = st.session_state.get(sig_key) != signature
    recompute_clicked = st.button(
        "🔄 Alle theoretische scenario's berekenen",
        key=f"theoretical_recompute_{opp['ploeg_id']}", type="primary",
    )

    if needs_compute and compute_key in st.session_state:
        st.info(
            "De selectie is gewijzigd sinds de laatste berekening — klik hierboven om opnieuw te "
            "berekenen met de nieuwe selectie."
        )

    if compute_key not in st.session_state and not recompute_clicked:
        st.info("Klik hierboven om alle theoretische scenario's te berekenen (kan enkele seconden duren).")
        return

    if recompute_clicked:
        computed = []
        uitgesloten_wegens_reglement = 0
        with st.spinner(f"{len(lineups)} theoretische scenario's doorrekenen..."):
            for idx, boards in enumerate(lineups, start=1):
                results, _truncated = ll.optimize_lineup_vs_scenario(
                    available_ids, max_per_player, synergy_fn, boards, player_ratings,
                    player_official_ranks=official_ranks, opponent_ratings=opponent_ratings,
                    top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
                    tournament_rules_dict=tournament_rules_dict,
                )
                if not results:
                    uitgesloten_wegens_reglement += 1
                computed.append({"idx": idx, "boards": boards, "results": results})
        st.session_state[compute_key] = computed
        st.session_state[sig_key] = signature
        if tournament_rules_dict is not None and uitgesloten_wegens_reglement:
            st.caption(
                f"ℹ️ Voor {uitgesloten_wegens_reglement} van de {len(lineups)} theoretische tegenstander-"
                "opstellingen bleek GEEN enkele eigen koppelverdeling binnen de reglementaire puntengrens "
                "te vallen — die scenario's tonen dus geen resultaat."
            )

    stored = st.session_state.get(compute_key) or []
    if not stored:
        return

    show_all_theoretical_key = f"theoretical_showall_{opp['ploeg_id']}"
    show_all_theoretical = False
    if len(stored) > _THEORETICAL_DISPLAY_DEFAULT_N:
        show_all_theoretical = st.checkbox(
            f"Toon alle {len(stored)} theoretische scenario's (i.p.v. de eerste {_THEORETICAL_DISPLAY_DEFAULT_N})",
            key=show_all_theoretical_key,
        )
    display_entries = stored if show_all_theoretical else stored[:_THEORETICAL_DISPLAY_DEFAULT_N]

    for entry in display_entries:
        boards = entry["boards"]
        board_summary = " | ".join(
            " + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards
        )
        with st.expander(f"Theoretisch scenario {entry['idx']}: {board_summary}", expanded=False):
            if not entry["results"]:
                if tournament_rules_dict is not None:
                    st.warning(
                        "Geen enkele eigen koppelverdeling voldoet aan de reglementaire puntengrens per "
                        "rotatie voor dit scenario."
                    )
                else:
                    st.warning("Geen geldige opstelling gevonden voor dit scenario binnen de huidige beperkingen.")
                continue
            best = entry["results"][0]
            st.markdown(f"**Onze beste tegenzet — score {best['total_score']}**")
            _render_rotation_points_caption(best.get("rotations"), name_lookup_global)
            for a in best["assignment"]:
                p1, p2 = a["our_pair"]
                opp_names = " / ".join(p.get("name", "?") for p in a["opponent_board"]["opponent_pair"])
                st.write(
                    f"**{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
                    f"(synergie {a['synergy']}) — vs **{opp_names}** (matchup-edge: {a['edge']:+.2f})"
                )

    if not show_all_theoretical and len(stored) > len(display_entries):
        st.caption(f"Eerste {len(display_entries)} van {len(stored)} berekende theoretische scenario's getoond.")

    st.divider()
    st.markdown("#### 📊 Aggregaatscore over alle theoretische scenario's")
    st.caption(
        "Voor elke eigen koppelverdeling: het gemiddelde van zijn score over ALLE theoretische "
        "scenario's waarin ze een geldig resultaat had. Dit is de meest ROBUUSTE aanwijzing welke "
        "opstelling wij het best klaarhouden, ongeacht wat de tegenstander effectief kiest."
    )
    aggregate = _aggregate_scenario_scores(stored)
    if not aggregate:
        st.info("Nog geen combinaties met een geldig resultaat.")
        return
    show_all_agg_key = f"theoretical_agg_showall_{opp['ploeg_id']}"
    show_all_agg = False
    if len(aggregate) > _AGGREGATE_DISPLAY_DEFAULT_N:
        show_all_agg = st.checkbox(
            f"Toon alle {len(aggregate)} combinaties (i.p.v. de beste {_AGGREGATE_DISPLAY_DEFAULT_N})",
            key=show_all_agg_key,
        )
    weer_te_geven = aggregate if show_all_agg else aggregate[:_AGGREGATE_DISPLAY_DEFAULT_N]
    agg_rows = []
    for combo_key, info in weer_te_geven:
        pair_labels = " | ".join(
            f"{name_lookup_global.get(p1, p1)}/{name_lookup_global.get(p2, p2)}"
            for p1, p2 in combo_key
        )
        agg_rows.append({
            "Koppelverdeling": pair_labels,
            "Gem. score": round(info["avg"], 3),
            "Min": round(info["min"], 3),
            "Max": round(info["max"], 3),
            "In # scenario's": info["count"],
            "% van alle scenario's": f"{round(100 * info['count'] / len(stored))}%" if stored else "-",
        })
    st.dataframe(agg_rows, use_container_width=True, hide_index=True)
    if not show_all_agg and len(aggregate) > len(weer_te_geven):
        st.caption(f"Beste {len(weer_te_geven)} van {len(aggregate)} unieke koppelverdelingen getoond.")


def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    """PADEL_ANALYSIS_LINEUP_SCENARIO_REDESIGN_2026-09-13 / _2026-09-14 /
    _ALL_COMBINATIONS_AGGREGATE_2026-09-16 / _OPPONENT_REFERENCE_FIX_2026-09-17 /
    _ALL_THEORETICAL_OPPONENT_SCENARIOS_2026-09-17 / _TOURNAMENT_RULES_2026-09-17."""
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "Per scenario (een eerdere opstelling van de tegenstander dit seizoen) berekenen we automatisch "
        "de beste opties voor onze eigen opstelling — over ALLE mogelijke koppelverdelingen heen."
    )

    # PADEL_ANALYSIS_TOURNAMENT_RULES_2026-09-17: reglement-selector, ALTIJD
    # bovenaan zichtbaar, geldt voor alle 3 secties hieronder (Rotatieplanner,
    # historische scenario's, theoretische scenario's).
    tournament_rules_dict, rules_label = _render_tournament_rules_selector(opp["ploeg_id"])

    with st.expander("ℹ️ Wat betekenen synergie, matchup-edge, score, aggregaatscore en de puntengrens?", expanded=False):
        st.markdown(
            "- **Synergie**: hoe goed dit koppel historisch samen presteert (confidence-shrinkage: "
            "hoe minder gezamenlijke wedstrijden, hoe meer teruggetrokken richting het individuele "
            "gemiddelde). Waarde tussen 0 en 1.\n"
            "- **Matchup-edge**: een ruwe inschatting van het krachtsverschil met het tegenstander-"
            "koppel op dat bord. Gebruikt padelstats.be playing strength voor BEIDE koppels zodra "
            "die voor de tegenstander gekend is; anders het officiële klassement voor BEIDE zijden.\n"
            "- **Score**: synergie + matchup-edge, opgeteld over alle borden van dat ENE scenario.\n"
            "- **Officiële regel (art. 6.6)**: binnen elke ROTATIE (2 gelijktijdige wedstrijden) speelt "
            "het duo met de HOOGSTE SOM van de 2 klassementen op het laagst genummerde bord (Match 1/3), "
            "aan BEIDE kanten. Er wordt niet langer 'slim' naar de score-maximaliserende toewijzing "
            "gezocht — dat kan de score t.o.v. eerdere berekeningen iets doen dalen, maar is nu wel "
            "reglementair correct.\n"
            "- **Puntengrens per rotatie**: de SOM van de klassementen van ALLE 4 spelers in 1 rotatie "
            "moet, voor de gekozen afdeling (zie '📖 Reglement / afdeling' hierboven), binnen een "
            "minimum en maximum liggen. Combinaties die deze grens overschrijden worden NIET getoond.\n"
            "- **Aggregaatscore**: het gemiddelde van de score van een VOLLEDIGE koppelverdeling over "
            "ALLE scenario's waarin ze voorkwam. Combinaties die in meerdere scenario's voorkwamen "
            "staan bovenaan — daar is de spreiding (min/max) betekenisvol."
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
        st.caption(f"Standaard vooraf geselecteerd: de spelers van jullie vorige interclubontmoeting ({len(default_labels)} speler(s)). Pas gerust aan.")
        if len(default_labels) < 4:
            st.warning(
                f"Slechts {len(default_labels)} speler(s) automatisch teruggevonden voor de vorige "
                "ontmoeting. Dit gebeurt als niet alle teamgenoten van die dag zelf al zijn toegevoegd "
                "via '➕ Speler toevoegen' - hun matchdata is dan nog onbekend. Vul de selectie hieronder "
                "gerust manueel aan met de ontbrekende teamgenoten."
            )
    else:
        default_labels = own_labels[: min(8, len(own_labels))]

    available_labels = st.multiselect(
        "Beschikbare eigen spelers", own_labels,
        default=default_labels,
        key="scenario_available_players",
    )
    if len(available_labels) < 2:
        st.info("Selecteer minstens 2 spelers om een opstelling te kunnen berekenen.")
        return
    available_ids = [own_label_to_id[lbl] for lbl in available_labels]

    total_possible_combos = _count_perfect_matchings(len(available_ids))
    if total_possible_combos:
        if total_possible_combos <= _SCENARIO_CANDIDATE_POOL:
            st.caption(
                f"🔢 Er zijn **{total_possible_combos}** mogelijke koppelverdelingen voor deze "
                f"{len(available_ids)} spelers — ALLEMAAL worden per scenario doorgerekend "
                "(dus ook alternatieven zoals een ander koppel voor eenzelfde speler)."
            )
        else:
            st.caption(
                f"🔢 Er zijn **{total_possible_combos}** mogelijke koppelverdelingen voor deze "
                f"{len(available_ids)} spelers — de {_SCENARIO_CANDIDATE_POOL} beste (op eigen "
                "synergie) worden per scenario doorgerekend, niet letterlijk elke combinatie."
            )

    suggested_boards = max((len(fx.get("boards", [])) for fx in bundle.get("previous_fixtures", [])), default=6) or 6
    c1, c2 = st.columns(2)
    with c1:
        total_boards = st.number_input("Aantal wedstrijden deze ontmoeting", min_value=1, value=int(suggested_boards), step=1)
    with c2:
        st.caption(f"Voorstel gebaseerd op vorige ontmoeting van de tegenstander: {suggested_boards} wedstrijden.")

    default_max = max(1, -(-2 * total_boards // len(available_ids)))
    st.caption("Max. aantal wedstrijden per speler (wat als...): standaard gelijk verdeeld, zelf aanpasbaar (bv. 0 voor een afwezige speler).")
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
        st.error(
            f"Het totaal aantal speler-plaatsen ({total_slots}) moet gelijk zijn aan 2× het aantal "
            f"wedstrijden ({2*total_boards}). Pas de aantallen per speler aan."
        )
        return

    docs_for_synergy = ll.get_docs_for_players(available_ids)
    own_synergy = ll.compute_pairwise_synergy(docs_for_synergy, available_ids)
    synergy_fn = ll.make_pair_score_fn(own_synergy, docs_for_synergy)
    player_ratings = {pid: oa.get_own_player_rating(pid)[0] for pid in available_ids}
    official_ranks = {pid: (_official_current_rank(pid) or player_ratings.get(pid, 0)) for pid in available_ids}
    opponent_ratings = _opponent_padelstat_ratings(bundle)

    if not bundle.get("previous_fixtures"):
        st.info(
            "Geen historische scenario's beschikbaar (geen eerdere, al gespeelde wedstrijd van deze "
            "tegenstander gevonden). Gebruik de sectie 'Alle theoretische tegenstander-opstellingen' "
            "hieronder om toch te plannen, op basis van de gekende tegenstander-spelers."
        )
    else:
        signature = (
            tuple(sorted(available_ids)),
            tuple(sorted(max_per_player.items())),
            int(total_boards),
            opp.get("ploeg_id"),
            str(tournament_rules_dict),
        )
        compute_key = f"scenario_results_{opp['ploeg_id']}"
        sig_key = f"scenario_signature_{opp['ploeg_id']}"
        needs_compute = st.session_state.get(sig_key) != signature
        recompute_clicked = st.button("🔄 Herberekenen", key=f"scenario_recompute_{opp['ploeg_id']}")

        if needs_compute or recompute_clicked:
            computed = []
            with st.spinner(f"Alle mogelijke koppelverdelingen doorrekenen (tot {_SCENARIO_CANDIDATE_POOL} kandidaten per scenario)..."):
                for s_idx, fx_bundle in enumerate(bundle["previous_fixtures"], start=1):
                    boards = fx_bundle.get("boards", [])
                    fx = fx_bundle.get("fixture", {})
                    entry = {
                        "s_idx": s_idx, "fixture": fx, "boards_count": len(boards),
                        "error": fx_bundle.get("error"), "results": None, "truncated": False,
                    }
                    if not entry["error"] and boards:
                        results, truncated = ll.optimize_lineup_vs_scenario(
                            available_ids, max_per_player, synergy_fn, boards, player_ratings,
                            player_official_ranks=official_ranks, opponent_ratings=opponent_ratings,
                            top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
                            tournament_rules_dict=tournament_rules_dict,
                        )
                        entry["results"] = results
                        entry["truncated"] = truncated
                    computed.append(entry)
            st.session_state[compute_key] = {
                "opponent_name": opp.get("name"),
                "opponent_ploeg_id": opp.get("ploeg_id"),
                "available_ids": available_ids,
                "available_labels": available_labels,
                "total_boards": int(total_boards),
                "max_per_player": max_per_player,
                "scenarios": computed,
            }
            st.session_state[sig_key] = signature

        stored = st.session_state.get(compute_key)
        if stored:
            for entry in stored["scenarios"]:
                s_idx, fx, boards_count = entry["s_idx"], entry["fixture"], entry["boards_count"]
                with st.expander(
                    f"Scenario {s_idx}: hun opstelling tegen {fx.get('home_name') if fx.get('away_ploeg_id')==opp['ploeg_id'] else fx.get('away_name')} "
                    f"({fx.get('date_text','?')}) — {boards_count} wedstrijden",
                    expanded=(s_idx == 1),
                ):
                    if entry["error"]:
                        st.warning(entry["error"])
                        continue
                    if not entry["results"]:
                        if boards_count == 0:
                            st.info("Geen bord-detail kunnen ophalen voor dit scenario.")
                        elif tournament_rules_dict is not None:
                            st.warning(
                                "Geen enkele eigen koppelverdeling voldoet aan de reglementaire "
                                "puntengrens per rotatie voor dit scenario."
                            )
                        else:
                            st.warning("Geen geldige opstelling gevonden binnen deze beperkingen.")
                        continue
                    if entry["truncated"]:
                        st.caption(
                            f"⚠️ Meer dan {_SCENARIO_CANDIDATE_POOL} mogelijke koppelverdelingen — resultaat "
                            "gebaseerd op de beste kandidaten binnen die zoekdiepte."
                        )
                    total_computed = len(entry["results"])
                    show_all_key = f"scenario_showall_{opp['ploeg_id']}_{s_idx}"
                    show_all = False
                    if total_computed > _SCENARIO_DISPLAY_DEFAULT_N:
                        show_all = st.checkbox(
                            f"Toon alle {total_computed} berekende opties (i.p.v. de beste {_SCENARIO_DISPLAY_DEFAULT_N})",
                            key=show_all_key,
                        )
                    display_results = entry["results"] if show_all else entry["results"][:_SCENARIO_DISPLAY_DEFAULT_N]
                    if show_all:
                        st.caption(f"Alle {total_computed} berekende opties getoond.")
                    elif total_computed > len(display_results):
                        st.caption(f"Beste {len(display_results)} van {total_computed} berekende opties getoond. Bij opslaan worden ALLE {total_computed} bewaard.")
                    for opt_idx, option in enumerate(display_results, start=1):
                        label = f"**Optie {opt_idx}" + (" (beste)" if opt_idx == 1 else "") + f" — score {option['total_score']}**"
                        st.markdown(label)
                        _render_rotation_points_caption(option.get("rotations"), name_lookup_global)
                        for a in option["assignment"]:
                            p1, p2 = a["our_pair"]
                            opp_pair = a["opponent_board"]["opponent_pair"]
                            opp_names = " / ".join(p.get("name", "?") for p in opp_pair)
                            schaal = a.get("edge_scale")
                            schaal_txt = {"padelstat": "playing strength", "official": "officieel klassement"}.get(schaal, "")
                            schaal_suffix = f", o.b.v. {schaal_txt}" if schaal_txt else ""
                            st.write(
                                f"**{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
                                f"(synergie {a['synergy']}) — vs **{opp_names}** (matchup-edge: {a['edge']:+.2f}{schaal_suffix})"
                            )
                        if opt_idx < len(display_results):
                            st.markdown("---")
                    if taa is not None and report is not None:
                        ai_key = f"scenario_ai_{opp['ploeg_id']}_{s_idx}"
                        if st.button("🤖 AI-analyse van deze opties", key=f"scenario_ai_btn_{opp['ploeg_id']}_{s_idx}"):
                            with st.spinner("AI analyseert de opties..."):
                                try:
                                    st.session_state[ai_key] = taa.analyze_lineup_options(
                                        report, display_results, name_lookup_global
                                    )
                                except Exception as exc:
                                    st.session_state[ai_key] = f"⚠️ Mislukt: {exc}"
                        if st.session_state.get(ai_key):
                            st.markdown(st.session_state[ai_key])

            st.divider()
            if st.button("💾 Deze analyse opslaan (alle berekende opties)", key=f"save_analysis_{opp['ploeg_id']}"):
                payload = {
                    "opponent_name": stored["opponent_name"],
                    "opponent_ploeg_id": stored["opponent_ploeg_id"],
                    "own_player_ids": stored["available_ids"],
                    "own_player_labels": stored["available_labels"],
                    "total_boards": stored["total_boards"],
                    "max_per_player": stored["max_per_player"],
                    "scenarios": [
                        {
                            "s_idx": e["s_idx"],
                            "fixture_label": e["fixture"].get("date_text", "?"),
                            "boards_count": e["boards_count"],
                            "options": [
                                {
                                    "total_score": opt["total_score"],
                                    "assignment": [
                                        {
                                            "our_pair_labels": [
                                                name_lookup_global.get(a["our_pair"][0], a["our_pair"][0]),
                                                name_lookup_global.get(a["our_pair"][1], a["our_pair"][1]),
                                            ],
                                            "synergy": a["synergy"],
                                            "edge": a["edge"],
                                            "opponent_names": [p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]],
                                        }
                                        for a in opt["assignment"]
                                    ],
                                }
                                for opt in (e["results"] or [])
                            ],
                        }
                        for e in stored["scenarios"]
                    ],
                }
                doc_id = fb.save_lineup_analysis(sel_player_id, payload)
                n_total_options = sum(len(s["options"]) for s in payload["scenarios"])
                st.success(f"Analyse opgeslagen ({n_total_options} opties over {len(payload['scenarios'])} scenario's). Te bekijken via het tabblad 'Opgeslagen analyses'.")

            st.divider()
            st.markdown("#### 📊 Aggregaatscore over alle historische scenario's")
            st.caption(
                "Voor elke eigen koppelverdeling die in minstens één scenario een geldig resultaat had: het "
                "gemiddelde van zijn score over alle scenario's waarin die combinatie voorkwam. Combinaties "
                "die in MEERDERE scenario's voorkwamen staan bovenaan."
            )
            aggregate = _aggregate_scenario_scores(stored["scenarios"])
            if not aggregate:
                st.info("Nog geen combinaties met een geldig resultaat in minstens 1 scenario.")
            else:
                n_multi = sum(1 for _, info in aggregate if info["count"] > 1)
                if n_multi:
                    st.caption(f"✅ {n_multi} van de {len(aggregate)} unieke koppelverdelingen kwamen in meerdere scenario's voor.")
                else:
                    st.caption(
                        f"ℹ️ Geen enkele koppelverdeling kwam in meerdere scenario's als beste optie voor — "
                        f"met {sum(1 for e in stored['scenarios'] if e.get('results'))} scenario('s) is dat "
                        "niet ongewoon. Onderstaande rijen tonen dus stuk voor stuk de beste optie per "
                        "scenario, niet een cross-scenario-gemiddelde."
                    )
                show_all_agg_key = f"scenario_agg_showall_{opp['ploeg_id']}"
                show_all_agg = False
                if len(aggregate) > _AGGREGATE_DISPLAY_DEFAULT_N:
                    show_all_agg = st.checkbox(
                        f"Toon alle {len(aggregate)} combinaties (i.p.v. de beste {_AGGREGATE_DISPLAY_DEFAULT_N})",
                        key=show_all_agg_key,
                    )
                weer_te_geven = aggregate if show_all_agg else aggregate[:_AGGREGATE_DISPLAY_DEFAULT_N]
                agg_rows = []
                for combo_key, info in weer_te_geven:
                    pair_labels = " | ".join(
                        f"{name_lookup_global.get(p1, p1)}/{name_lookup_global.get(p2, p2)}"
                        for p1, p2 in combo_key
                    )
                    agg_rows.append({
                        "Koppelverdeling": pair_labels,
                        "Gem. score": round(info["avg"], 3),
                        "Min": round(info["min"], 3),
                        "Max": round(info["max"], 3),
                        "In # scenario's": info["count"],
                    })
                st.dataframe(agg_rows, use_container_width=True, hide_index=True)
                if not show_all_agg and len(aggregate) > len(weer_te_geven):
                    st.caption(f"Beste {len(weer_te_geven)} van {len(aggregate)} unieke koppelverdelingen getoond.")

    _render_theoretical_opponent_scenarios(
        bundle, opp, available_ids, max_per_player, int(total_boards),
        synergy_fn, player_ratings, official_ranks, opponent_ratings,
        report, name_lookup_global,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    )

    st.divider()
    chosen_scenario_boards = None
    stored = st.session_state.get(f"scenario_results_{opp['ploeg_id']}")
    if stored and stored.get("scenarios"):
        scenario_pick_labels = ["Geen (enkel eigen synergie)"] + [
            f"Scenario {e['s_idx']}: {e['fixture'].get('date_text','?')}" for e in stored["scenarios"] if e.get("results")
        ]
        scenario_pick = st.selectbox(
            "Matchup-inschatting voor de Rotatieplanner op basis van:",
            scenario_pick_labels, key=f"rot_scenario_pick_{opp['ploeg_id']}",
        )
        if scenario_pick != scenario_pick_labels[0]:
            s_idx_pick = int(scenario_pick.split(":")[0].replace("Scenario ", ""))
            matching_entry = next((e for e in stored["scenarios"] if e["s_idx"] == s_idx_pick), None)
            if matching_entry:
                chosen_scenario_boards = None
                for fx_bundle in bundle["previous_fixtures"]:
                    if fx_bundle.get("fixture") is matching_entry["fixture"]:
                        chosen_scenario_boards = fx_bundle.get("boards")
                        break

    _render_rotation_planner(
        available_ids, synergy_fn, official_ranks, name_lookup_global, opp,
        opponent_boards=chosen_scenario_boards, player_ratings=player_ratings,
        opponent_ratings=opponent_ratings,
        report_for_ai=report,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    )


def _render_saved_lineup_analyses(name_lookup_global: dict):
    """Toont alle eerder opgeslagen opstelling-scenario-analyses."""
    st.markdown('<div class="section-header">💾 Opgeslagen opstelling-analyses</div>', unsafe_allow_html=True)
    st.caption("Analyses die je eerder opsloeg via '💾 Deze analyse opslaan' bij Opstelling-scenario's.")
    analyses = fb.list_lineup_analyses()
    if not analyses:
        st.info("Nog geen analyses opgeslagen. Bereken en sla een opstelling-scenario op via het tabblad 'Analyseren'.")
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
    st.caption(
        f"Opgeslagen op {_format_scraped_at(analysis.get('saved_at'))} · "
        f"eigen spelers: {', '.join(analysis.get('own_player_labels', []) or [])}"
    )
    for scenario in analysis.get("scenarios", []) or []:
        options = scenario.get("options") or []
        with st.expander(f"Scenario {scenario.get('s_idx')}: {scenario.get('fixture_label', '?')} — {scenario.get('boards_count', 0)} wedstrijden ({len(options)} opties opgeslagen)"):
            if not options:
                st.info("Geen resultaat opgeslagen voor dit scenario.")
                continue
            for opt_idx, option in enumerate(options, start=1):
                st.write(f"**Optie {opt_idx} — score {option.get('total_score')}**")
                for a in option.get("assignment", []) or []:
                    pair_labels = a.get("our_pair_labels") or ["?", "?"]
                    opp_names = " / ".join(a.get("opponent_names", []) or [])
                    st.write(
                        f"{pair_labels[0]} / {pair_labels[1]} (synergie {a.get('synergy')}) — "
                        f"vs {opp_names} (matchup-edge {a.get('edge', 0):+.2f})"
                    )
    if st.button("🗑️ Deze analyse verwijderen", key=f"delete_analysis_{analysis.get('_doc_id')}"):
        fb.delete_lineup_analysis(analysis["_doc_id"])
        st.success("Analyse verwijderd.")
        st.rerun()


def page_lineup_lab():
    """PADEL_ANALYSIS_RENDER_ORDER_2026-09-15 (op verzoek van Kim):
    Volgende match -> OVERZICHTSTABEL + detail per speler -> Opstelling-
    scenario's + Rotatieplanner -> AI-inzichten tegenploeg."""
    st.header("🧩 Opstelling-analyse")
    profiles = _get_all_profiles()
    if not profiles:
        st.info("Nog geen spelers in de database. Voeg eerst spelers toe via '➕ Speler toevoegen'.")
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
                report_for_ai = oa.get_team_report(
                    bundle, opp, all_docs,
                    current_reeks_url=reeks_url, current_spelgroep_id=spelgroep_id,
                    global_docs=global_docs, key_prefix=f"scout_team_{sel_player_id}",
                )
                report_for_ai = oa.render_team_header(
                    report_for_ai, bundle, opp, all_docs,
                    current_reeks_url=reeks_url, current_spelgroep_id=spelgroep_id,
                    global_docs=global_docs, key_prefix=f"scout_team_{sel_player_id}",
                )
            if report_for_ai is not None:
                oa.render_overview_and_detail(
                    report_for_ai, go_to_player_fn=_go_to_player,
                    key_prefix=f"scout_team_{sel_player_id}",
                )
                st.divider()
            _render_opstelling_scenario(
                bundle, opp, profiles, name_lookup_global, str(sel_player_id), report_for_ai
            )
            if report_for_ai is not None:
                st.divider()
                oa.render_ai_section(report_for_ai, opp.get("ploeg_id"), key_prefix=f"scout_team_{sel_player_id}")
    with tab_saved:
        _render_saved_lineup_analyses(name_lookup_global)
