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
toont die diagnostiek op alle drie de plekken waar voorheen enkel "0
combinaties" te zien was.
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
Kim's punten, in eigen woorden, en wat er telkens mee gebeurd is:
  1. "Reeks 1,2,3 enz is niet duidelijk, beter de min/max P-rating." ->
     _render_tournament_rules_selector() toont de afdeling-keuzelijst nu
     als "Afdeling 5 (P100–P300)" i.p.v. enkel "Afdeling 5" (gebruikt het
     TOEGELATEN INDIVIDUEEL KLASSEMENT-bereik van tournament_rules.py, niet
     de punten-per-rotatie-grens — dat is de "P-rating" waar Kim naar
     verwijst).
  2. "Best ook onthouden wat geselecteerd was per speler." -> de gekozen
     combinatie (tornooi, categorie, afdeling) wordt nu bewaard in het
     player_profiles-document van de BEKEKEN speler (sel_player_id) en bij
     een volgend bezoek automatisch teruggezet, i.p.v. telkens terug te
     vallen op de standaardwaarde. Nieuwe helpers: _load_saved_rules_
     selection() / _save_rules_selection(). LET OP (aanname, graag
     bevestigen): als Kim ook bedoelde dat de spelersselecties zelf
     ("Beschikbare eigen spelers" / "Beschikbare tegenstander-spelers")
     onthouden moeten worden tussen sessies, is dat NIET in deze fix
     meegenomen (dat zou een aparte Firestore-structuur vergen) - graag
     laten weten of dat ook gewenst is.
  3. "vervang overal de tekst borden door matchen." -> alle GEBRUIKER-
     ZICHTBARE teksten met "bord"/"borden" zijn vervangen door "match"/
     "matchen" (bv. "verwacht aantal gewonnen borden" -> "... matchen",
     de kolom "Bord" in de tegenstander-referentietabel -> "Match"). Interne
     Python-namen (board_position, opponent_board, boards_count, ...)
     blijven ONGEWIJZIGD - dat zijn geen zichtbare teksten en wijzigen zou
     bestaande, opgeslagen analyses kunnen breken.
  4. "agregaatscore lijkt me ook nutteloos, mag weg" -> BEIDE
     aggregaatscore-secties ("over alle historische scenario's" EN "over
     alle theoretische scenario's") zijn uit de UI verwijderd. De
     onderliggende _aggregate_scenario_scores()-functie blijft gedefinieerd
     (ongebruikt) voor het geval de aangekondigde, GROTERE herwerking
     hieronder (punt 6) er alsnog gebruik van wil maken.
  5. "Selecteer minstens 8 tegenstander-spelers... ik heb geen 8 nodig, dit
     stuk werkt niet." -> root cause: _render_theoretical_opponent_
     scenarios() erfde stilzwijgend hetzelfde `total_boards` over van de
     HISTORISCHE Opstelling-scenario's hierboven (die op zijn beurt
     standaard het HOOGSTE aantal wedstrijden uit een vorige ontmoeting
     voorstelt, bv. 4 als er ooit een dubbele rotatie gespeeld werd) -
     ongeacht of Kim voor DEZE theoretische verkenning maar 1 rotatie (2
     wedstrijden, dus 4 tegenstanders) nodig had. Fix: deze sectie heeft nu
     een EIGEN "Aantal wedstrijden"-veld, standaard gelijk aan de
     historische instelling maar vrij aanpasbaar; wijzigt Kim dit, dan
     worden de eigen speler-plaatsen (max_per_player) voor DEZE sectie
     automatisch herverdeeld (gelijk over de beschikbare spelers).
--------------------------------------------------------------------------
PADEL_ANALYSIS_IDENTICAL_EXPECTED_VALUE_EXPLAINED_2026-09-18 (op verzoek
van Kim: "Allemaal met dezelfde 1.87 verwachting? lijkt me vreemd. [...]
bekijk zeker ook nog eens hoe je die winkans berekent.")
--------------------------------------------------------------------------
GEEN bug gevonden in de winkans-berekening zelf (zie lineup_lab.py:
estimate_win_probability() gebruikt per SPELER een individuele effectieve
rating, gemiddeld per koppel, en is dus NIET afhankelijk van synergie of
van welke twee spelers precies samen een koppel vormen — enkel van de
GEMIDDELDE rating van het koppel). Bij een groep van 8 spelers waarvan de
padelstat-ratings goed correleren met hun officiële klassement (het
klassement bepaalt WELK koppel op welk bord terechtkomt, via de
punten-per-rotatie-regel), kan het dus voorkomen dat VERSCHILLENDE
koppelverdelingen toch dezelfde VERZAMELING van "gemiddelde rating per
bord" opleveren — en dus EXACT dezelfde verwachte-matchen-gewonnen-som,
terwijl enkel de SYNERGIE (partnerhistoriek) tussen de opties verschilt.
Dat is dan geen bug, maar een wiskundig gevolg van hoe de twee lagen
(reglement-bordvolgorde op officieel klassement vs. simulatie-winkans op
individuele rating) los van elkaar werken. Om dit niet langer als
verwarrend/verdacht te laten overkomen: _render_opstelling_scenario() toont
nu een expliciete, informatieve caption zodra 2+ getoonde opties exact
dezelfde verwachte-matchen-gewonnen-waarde hebben, die dit uitlegt.
Kim's aanvullende opmerking ("we kunnen ook om persoonlijke redenen een
ploeg met een lagere winkans kiezen") vergt geen codewijziging: de UI
toonde en toont nog steeds meerdere opties (niet enkel de "beste"), zodat
een bewuste keuze voor een lagere-winkans-optie altijd al mogelijk was.
--------------------------------------------------------------------------
NOG NIET GEBOUWD — voorgesteld als APARTE, volgende stap (op verzoek van
Kim: historische + theoretische scenario's SAMENVOEGEN tot 1 lijst, enkel
reglementair geldige opstellingen tonen, gesorteerd op winkans/verwachte
matchen aflopend, met de op-1-na-beste opties ingeklapt/onderaan)
--------------------------------------------------------------------------
Dit is een substantiële herwerking van de sectie-structuur (2 aparte
subsecties -> 1 gecombineerde, altijd-actieve weergave zonder aparte
"Bereken"-knoppen) en is BEWUST NIET in deze fix meegenomen, conform Kim's
eigen voorkeur voor kleinere, aparte stappen per onderwerp. Zie het gesprek
voor het voorgestelde ontwerp; te bouwen zodra Kim akkoord geeft.
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
# PADEL_ANALYSIS_LABEL_PERSIST_TEXT_MERGE_CLEANUP_2026-09-18: P-rating-label
# + persistente keuze per bekeken speler.
# ─────────────────────────────────────────────
def _load_saved_rules_selection(sel_player_id: str) -> dict:
    """Leest de laatst gekozen tornooi/categorie/afdeling terug uit het
    player_profiles-document van de bekeken speler, zodat de keuze niet
    telkens terugvalt naar de standaardwaarde bij een nieuwe sessie/
    paginaherlading. Faalt stil (lege dict) bij een Firestore-probleem —
    dan gedraagt de selector zich gewoon als voorheen (standaardwaarden)."""
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
    """PADEL_ANALYSIS_LABEL_PERSIST_TEXT_MERGE_CLEANUP_2026-09-18 (op verzoek
    van Kim):
      1. "Reeks 1,2,3 is niet duidelijk, beter de min/max P-rating" -> de
         afdeling-keuzelijst toont nu het toegelaten klassementsbereik
         (bv. "Afdeling 5 (P100–P300)") i.p.v. enkel het cijfer.
      2. "Best ook onthouden wat geselecteerd was" -> de keuze wordt bewaard
         per bekeken speler (sel_player_id) en bij een volgend bezoek
         automatisch teruggezet."""
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
            help="Vandaag enkel Padel Senior Cup volledig ingevuld. Andere tornooien (Mixed, Open, "
                 "Vrouwen) kunnen later toegevoegd worden zodra het bijhorende reglement bezorgd is.",
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
    """Geeft nu een DERDE returnwaarde terug (`diagnostics`, kan None zijn
    bij n<2), zodat _render_rotation_planner() bij 0 kandidaten kan tonen
    wat er berekend werd."""
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
# Opstelling-scenario's
# ─────────────────────────────────────────────
_SCENARIO_CANDIDATE_POOL = 400
_SCENARIO_SAVE_TOP_N = 400
_SCENARIO_DISPLAY_DEFAULT_N = 10
_AGGREGATE_DISPLAY_DEFAULT_N = 20
_THEORETICAL_MAX_VARIANTS = 300
_THEORETICAL_DISPLAY_DEFAULT_N = 10


def _aggregate_scenario_scores(scenarios: list) -> list:
    """PADEL_ANALYSIS_LABEL_PERSIST_TEXT_MERGE_CLEANUP_2026-09-18: sinds deze
    datum NIET meer aangeroepen vanuit de UI (Kim: "aggregaatscore lijkt me
    nutteloos, mag weg") — de functie zelf blijft gedefinieerd, mogelijk
    herbruikbaar in de aangekondigde, grotere samenvoeging van historische +
    theoretische scenario's (zie moduledocstring)."""
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


def _merge_and_sort_scenario_entries(historical_entries: list, theoretical_entries: list) -> tuple:
    """PADEL_ANALYSIS_MERGED_SCENARIO_LIST_2026-09-18 (op verzoek van Kim,
    2x herhaald): zuivere, Streamlit-vrije samenvoeglogica — apart getest
    (zie het gesprek) zodat de sorteer-/filterregels geverifieerd zijn
    zonder een draaiende app nodig te hebben.

    Elke entry (zowel historisch als theoretisch) is een dict met minstens:
        {"kind": "historisch"/"theoretisch", "label": str, "boards": list,
         "results": list (kan leeg zijn), "diagnostics": dict|None,
         "error": str|None}

    Regels:
      1. Een entry zonder GELDIG resultaat (results leeg/None, of een error)
         wordt NIET in de zichtbare lijst opgenomen — enkel geteld.
      2. De zichtbare lijst wordt gesorteerd op de verwachte-matchen-
         gewonnen-waarde (expected_boards_won) van de BESTE optie van elke
         entry, AFLOPEND (hoogste eerst). Ontbreekt expected_boards_won
         (geen padelstat/klassement gekend), dan wordt total_score als
         terugval gebruikt voor de sortering — nooit een crash op een
         ontbrekende sleutel.

    Returns (zichtbare_entries_gesorteerd, aantal_uitgesloten)."""
    combined = list(historical_entries) + list(theoretical_entries)
    zichtbaar = [e for e in combined if not e.get("error") and e.get("results")]
    uitgesloten = len(combined) - len(zichtbaar)

    def _sort_key(entry):
        best = entry["results"][0]
        ebw = best.get("expected_boards_won")
        return ebw if ebw is not None else best.get("total_score", 0.0)

    zichtbaar.sort(key=_sort_key, reverse=True)
    return zichtbaar, uitgesloten


def _render_combined_opponent_scenarios(
    bundle, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, sel_player_id, tournament_rules_dict=None, rules_label=None,
):
    """PADEL_ANALYSIS_MERGED_SCENARIO_LIST_2026-09-18 (op verzoek van Kim,
    2x expliciet herhaald in hetzelfde bewoording):

        "ik zou dit stuk liever combineren met het stuk over die 3
        scenario's. Gewoon meteen alle scenarios tonen maar dan op een
        slimme manier. Geen dingen tonen die niet mogelijk zijn qua
        opstelling. Bij 1 specifieke opstelling van de tegenstander meteen
        onze beste opstelling tonen, geen slechtere alternatieven of
        eventueel wel maar dan via sortering in lijst helemaal onderaan
        waarbij je dan mss elke optie kan openklikken. Je zou moeten
        sorteren van hoogste winstkans naar minste."

    Vervangt de twee vroeger APARTE secties ("Opstelling-scenario's" op
    historische fixtures + "Alle theoretische tegenstander-opstellingen",
    elk met een eigen "Bereken"-knop en eigen paginering) door ÉÉN
    doorlopende lijst:
      - historische scenario's (ECHT gespeeld door de tegenstander dit
        seizoen — bundle["previous_fixtures"]) EN theoretische scenario's
        (mogelijke opstellingen op basis van een zelf gekozen tegenstander-
        roster) staan door elkaar, als gelijkwaardige entries.
      - scenario's ZONDER enkele reglementair geldige eigen opstelling
        worden NIET getoond (Kim: "geen dingen tonen die niet mogelijk
        zijn qua opstelling") — enkel geteld in een informatieve caption.
      - per scenario wordt STANDAARD enkel ONZE BESTE tegenzet getoond
        (Kim: "meteen onze beste opstelling tonen, geen slechtere
        alternatieven") — overige, zwakkere opties zitten in een ingeklapte
        "Toon N andere opties"-subexpander, NIET automatisch zichtbaar.
      - de volledige lijst is gesorteerd op de verwachte-matchen-gewonnen-
        waarde van onze beste tegenzet, AFLOPEND (Kim: "sorteren van
        hoogste winstkans naar minste").
    De onderliggende samenvoeg-/sorteerlogica zit in de losse, apart
    geteste _merge_and_sort_scenario_entries() hierboven (geen Streamlit
    nodig om die te verifiëren).

    Kim's aanvullende vraag "bekijk zeker ook nog eens hoe je die winkans
    berekent" leverde GEEN bug op (zie lineup_lab.py:
    estimate_win_probability() — een individuele, per-speler rating,
    onafhankelijk van synergie/wie-met-wie) - GEEN wijziging aan de
    berekening zelf in deze fix. Zijn opmerking dat een lagere-winkans-
    optie soms bewust gekozen wordt (bv. om persoonlijke redenen tussen 2
    spelers) blijft ondersteund: de "Toon N andere opties"-subexpander
    houdt élke berekende, geldige optie bereikbaar, niet enkel de beste.
    """
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "Alle scenario's (zowel de reeds gespeelde opstellingen van de tegenstander als de "
        "theoretisch mogelijke) in ÉÉN lijst, gesorteerd van hoogste naar laagste verwachte "
        "winstkans. Enkel scenario's met een reglementair geldige eigen tegenzet worden getoond."
    )

    # ── Historische scenario's berekenen (uit bundle["previous_fixtures"]) ──
    historical_entries = []
    for s_idx, fx_bundle in enumerate(bundle.get("previous_fixtures", []) or [], start=1):
        boards = fx_bundle.get("boards", [])
        fx = fx_bundle.get("fixture", {})
        entry = {
            "key": f"hist_{s_idx}", "kind": "historisch",
            "label": (
                f"Historisch — tegen {fx.get('home_name') if fx.get('away_ploeg_id')==opp['ploeg_id'] else fx.get('away_name')} "
                f"({fx.get('date_text','?')})"
            ),
            "boards": boards, "boards_count": len(boards),
            "results": None, "diagnostics": None,
            "error": fx_bundle.get("error"),
        }
        if not entry["error"] and boards:
            results, _truncated, diagnostics = ll.optimize_lineup_vs_scenario(
                available_ids, max_per_player, synergy_fn, boards, player_ratings,
                player_official_ranks=official_ranks_strict, opponent_ratings=opponent_ratings,
                top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
                tournament_rules_dict=tournament_rules_dict,
            )
            entry["results"] = results
            entry["diagnostics"] = diagnostics
        historical_entries.append(entry)

    # ── Theoretische scenario's: opponent-roster-keuze + berekening ──
    st.markdown("##### 🎯 Tegenstander-roster voor theoretische scenario's")
    st.caption(
        "Kies WIE van de tegenstander waarschijnlijk beschikbaar is. We berekenen ALLE mogelijke "
        "opstellingen die zij daaruit kunnen vormen (officiële regel: hun sterkste duo — som van "
        "klassementen — op Match 1) en voegen die toe aan de lijst hieronder."
    )
    unique_players = bundle.get("unique_players", []) or []
    theoretical_entries = []
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
            st.info(
                f"Selecteer minstens {needed} tegenstander-speler(s) ({total_boards} wedstrijden — zie "
                "'Aantal wedstrijden deze ontmoeting' hierboven) om theoretische scenario's toe te voegen. "
                "De historische scenario's hierboven werken al onafhankelijk hiervan."
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
                compute_key = f"theoretical_results_{opp['ploeg_id']}"
                sig_key = f"theoretical_signature_{opp['ploeg_id']}"
                signature = (
                    tuple(sorted(available_ids)), tuple(sorted(max_per_player.items())), int(total_boards),
                    tuple(sorted(chosen_opp_ids)), str(tournament_rules_dict),
                )
                needs_compute = st.session_state.get(sig_key) != signature
                recompute_clicked = st.button(
                    "🔄 Theoretische scenario's (her)berekenen", key=f"theoretical_recompute_{opp['ploeg_id']}", type="primary",
                )
                if needs_compute and compute_key in st.session_state:
                    st.info("De selectie is gewijzigd — klik hierboven om opnieuw te berekenen.")
                if recompute_clicked:
                    computed = []
                    with st.spinner(f"{len(lineups)} theoretische scenario's doorrekenen..."):
                        for idx, boards in enumerate(lineups, start=1):
                            results, _truncated, diagnostics = ll.optimize_lineup_vs_scenario(
                                available_ids, max_per_player, synergy_fn, boards, player_ratings,
                                player_official_ranks=official_ranks_strict, opponent_ratings=opponent_ratings,
                                top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
                                tournament_rules_dict=tournament_rules_dict,
                            )
                            computed.append({
                                "key": f"theo_{idx}", "kind": "theoretisch",
                                "label": "Theoretisch — " + " | ".join(
                                    " + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards
                                ),
                                "boards": boards, "boards_count": len(boards),
                                "results": results, "diagnostics": diagnostics, "error": None,
                            })
                    st.session_state[compute_key] = computed
                    st.session_state[sig_key] = signature
                theoretical_entries = st.session_state.get(compute_key) or []

    # ── Samenvoegen, filteren, sorteren ──
    visible_entries, n_excluded = _merge_and_sort_scenario_entries(historical_entries, theoretical_entries)
    st.divider()
    totaal = len(historical_entries) + len(theoretical_entries)
    if n_excluded:
        st.caption(
            f"ℹ️ {len(visible_entries)} van de {totaal} scenario's getoond (reglementair geldig). "
            f"{n_excluded} scenario('s) zijn niet mogelijk qua opstelling en worden niet getoond."
        )
    else:
        st.caption(f"{len(visible_entries)} scenario('s) getoond, gesorteerd op hoogste verwachte winstkans eerst.")
    if not visible_entries:
        st.info("Nog geen scenario's om te tonen — voeg historische fixtures toe of bereken theoretische scenario's hierboven.")
        return

    show_all_key = f"combined_scenarios_showall_{opp['ploeg_id']}"
    show_all = st.checkbox(
        f"Toon alle {len(visible_entries)} scenario's (i.p.v. de beste {_THEORETICAL_DISPLAY_DEFAULT_N})",
        key=show_all_key,
    ) if len(visible_entries) > _THEORETICAL_DISPLAY_DEFAULT_N else False
    display_entries = visible_entries if show_all else visible_entries[:_THEORETICAL_DISPLAY_DEFAULT_N]

    for rank, entry in enumerate(display_entries, start=1):
        best = entry["results"][0]
        ebw = best.get("expected_boards_won")
        kind_icon = "📋" if entry["kind"] == "historisch" else "🧮"
        ebw_txt = f" — verwacht {ebw:.2f} van {len(best['assignment'])} matchen gewonnen" if ebw is not None else f" — score {best.get('total_score')}"
        st.markdown(f"**#{rank} {kind_icon} {entry['label']}{ebw_txt}**")
        _render_rotation_points_caption(best.get("rotations"))
        _render_assignment_with_outcome(best["assignment"], name_lookup_global)
        overige = entry["results"][1:]
        if overige:
            with st.expander(f"Toon {len(overige)} andere optie(s) voor dit scenario", expanded=False):
                for opt_idx, option in enumerate(overige, start=2):
                    opt_ebw = option.get("expected_boards_won")
                    opt_label = f"**Optie {opt_idx}" + (f" — verwacht {opt_ebw:.2f} matchen gewonnen**" if opt_ebw is not None else f" — score {option.get('total_score')}**")
                    st.markdown(opt_label)
                    _render_rotation_points_caption(option.get("rotations"))
                    _render_assignment_with_outcome(option["assignment"], name_lookup_global)
                    if opt_idx < len(overige) + 1:
                        st.markdown("---")
        if taa is not None and report is not None:
            ai_key = f"combined_scenario_ai_{opp['ploeg_id']}_{entry['key']}"
            if st.button("🤖 AI-analyse van dit scenario", key=f"combined_scenario_ai_btn_{opp['ploeg_id']}_{entry['key']}"):
                with st.spinner("AI analyseert..."):
                    try:
                        st.session_state[ai_key] = taa.analyze_lineup_options(report, entry["results"], name_lookup_global)
                    except Exception as exc:
                        st.session_state[ai_key] = f"⚠️ Mislukt: {exc}"
            if st.session_state.get(ai_key):
                st.markdown(st.session_state[ai_key])
        st.markdown("---")

    if not show_all and len(visible_entries) > len(display_entries):
        st.caption(f"Beste {len(display_entries)} van {len(visible_entries)} getoonde scenario's — vink hierboven aan om alles te zien.")

    st.divider()
    if st.button("💾 Deze analyse opslaan (alle getoonde scenario's)", key=f"save_combined_analysis_{opp['ploeg_id']}"):
        payload = {
            "opponent_name": opp.get("name"), "opponent_ploeg_id": opp.get("ploeg_id"),
            "own_player_ids": available_ids,
            "own_player_labels": [name_lookup_global.get(pid, pid) for pid in available_ids],
            "total_boards": int(total_boards), "max_per_player": max_per_player,
            "scenarios": [
                {
                    "s_idx": rank, "fixture_label": e["label"], "boards_count": e["boards_count"],
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
                } for rank, e in enumerate(visible_entries, start=1)
            ],
        }
        doc_id = fb.save_lineup_analysis(sel_player_id, payload)
        n_total_options = sum(len(s["options"]) for s in payload["scenarios"])
        st.success(f"Analyse opgeslagen ({n_total_options} opties over {len(payload['scenarios'])} scenario's).")

    return visible_entries


def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption("Per scenario berekenen we automatisch onze beste tegenzet — over ALLE mogelijke koppelverdelingen heen.")
    tournament_rules_dict, rules_label = _render_tournament_rules_selector(opp["ploeg_id"], sel_player_id)
    with st.expander("ℹ️ Wat betekenen winkans, verwachte matchen, synergie en de puntengrens?", expanded=False):
        st.markdown(
            "- **Winkans per match**: een RUWE schatting (logistische functie op het ratingverschil), "
            "gebaseerd op padelstats.be playing strength waar bekend, anders het officiële klassement "
            "als terugval — PER SPELER individueel, niet meer 'alles of niets' per match.\n"
            "- **Verwacht aantal gewonnen matchen**: de som van de winkansen over alle matchen van "
            "die opstelling — een interpreteerbaar getal i.p.v. een abstracte score.\n"
            "- **Synergie**: hoe goed dit koppel historisch samen presteert (confidence-shrinkage).\n"
            "- **Officiële regel (art. 6.6)**: binnen elke ROTATIE speelt het duo met de HOOGSTE SOM "
            "van de 2 OFFICIËLE klassementen (nooit padelstat!) op het laagst genummerde match.\n"
            "- **Puntengrens per rotatie**: de SOM van de officiële klassementen van alle 4 spelers "
            "in 1 rotatie moet binnen de grenzen van de gekozen afdeling liggen — anders uitgesloten. "
            "Bij 0 geldige combinaties tonen we voortaan ook de daadwerkelijk berekende punten, zodat "
            "je kan zien of dit aan de afdeling-keuze ligt.\n"
            "- **Waarom tonen meerdere opties soms EXACT dezelfde verwachte matchen?** De winkans per "
            "match hangt enkel af van de individuele rating van elke speler (gemiddeld per koppel), "
            "NIET van de synergie/partnerhistoriek. Als verschillende koppelverdelingen toch dezelfde "
            "gemiddelde rating per match opleveren, is de verwachte-matchen-som identiek — enkel de "
            "synergie (en dus de volgorde/keuze) verschilt dan nog tussen die opties.\n\n"
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
    player_ratings = {pid: oa.get_own_player_rating(pid)[0] for pid in available_ids}  # SIMULATIE (padelstat)
    official_ranks_strict = _build_own_official_ranks_strict(available_ids)  # REGLEMENT (uitsluitend officieel)
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)
    opponent_ratings = _opponent_padelstat_ratings(bundle)

    # PADEL_ANALYSIS_MERGED_SCENARIO_LIST_2026-09-18: historische EN
    # theoretische scenario's samengevoegd tot ÉÉN gesorteerde, gefilterde
    # lijst (zie de uitgebreide toelichting in _render_combined_opponent_
    # scenarios() hierboven).
    visible_entries = _render_combined_opponent_scenarios(
        bundle, opp, available_ids, max_per_player, int(total_boards), synergy_fn,
        player_ratings, official_ranks_strict, opponent_ratings, report,
        name_lookup_global, sel_player_id,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    ) or []

    st.divider()
    chosen_scenario_boards = None
    if visible_entries:
        scenario_pick_labels = ["Geen (enkel eigen synergie)"] + [e["label"] for e in visible_entries]
        scenario_pick = st.selectbox("Matchup-inschatting voor de Rotatieplanner op basis van:", scenario_pick_labels, key=f"rot_scenario_pick_{opp['ploeg_id']}")
        if scenario_pick != scenario_pick_labels[0]:
            matching_entry = next((e for e in visible_entries if e["label"] == scenario_pick), None)
            if matching_entry:
                chosen_scenario_boards = matching_entry.get("boards")
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
