
"""
page_lineup_lab.py - "Opstelling-analyse"-pagina (Volgende match,
Opstelling-scenario's, Rotatieplanner, Opgeslagen analyses).
PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27 (op verzoek van Kim: "dit is een
groot bestand dus mss best om het eerst op te splitsen in meerdere kleinere.
want vorige keer duurde dat echt keilang.")
--------------------------------------------------------------------------
Dit bestand was voorheen 1 monolithisch bestand van ~3585 regels. Om
toekomstige aanpassingen sneller en veiliger te maken (kleinere, exacte
patches i.p.v. het hele bestand telkens opnieuw moeten reconstrueren) is
het opgesplitst in de volgende, functioneel samenhangende modules - ELK
FUNCTIONEEL ONGEWIJZIGD t.o.v. de vorige, monolithische versie:
  - lineup_scout.py            : Volgende match laden, scout-header,
                                  caching-helpers (ratings/klassement/docs),
                                  eigen-ploeg-herkenning.
  - lineup_rules.py             : Reglement/afdeling-selector.
  - lineup_opponent_history.py  : Tegenstander-referentie (klassement-
                                  teksten, uitslagenblad-rijen, eindscore,
                                  eerdere ontmoetingen, match1/match2-
                                  frequentie).
  - lineup_rotation.py          : Rotatieplanner-combinatoriek,
                                  bordvolgorde-regels (art. 6.6 +
                                  padelstat-tiebreak), best/worst-case-
                                  variantenumeratie, matchup-berekening
                                  per bord, de Rotatieplanner zelf.
  - lineup_matchup_table.py      : Opbouw en weergave van de volledige
                                  "Opstelling-scenario's"-tabel.
  - lineup_sandbox.py            : Sandbox (handmatige opstelling bouwen).
  - page_lineup_lab.py (dit bestand): orchestratie - _render_opstelling_
                                  scenario(), opgeslagen analyses,
                                  rangschikking-link, page_lineup_lab().
Bij een toekomstige aanpassing: identificeer eerst in WELKE module de
betrokken functie(s) staan (zie de lijst hierboven), en patch enkel dat
kleinere bestand - niet dit hele bestand.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RANGSCHIKKING_ALTIJD_ZICHTBAAR_2026-09-27 (op verzoek van
Kim: "Rangschikking stond er nu dat er eerst een analyse moet gebeuren.
Lijkt me niet nodig. Je mag die rangschikking altijd zien")
--------------------------------------------------------------------------
ROOT CAUSE: de Rangschikking-tab toonde de rangschikkingslink enkel als
`scout_result` niet None was - d.w.z. enkel als de VOLLEDIGE tegenstander-
scout (opponent-analyse, incl. Playwright-ophaling van de tegenstander se
matchdata) gelukt was. De rangschikking zelf heeft daar functioneel niets
mee te maken: het is een PUBLIEKE TVL-pagina (bevestigd via een door Kim
aangeleverde kopie van de pagina-HTML: `isSignedIn(): false`, geen enkel
login-scherm, de tabel laadt gewoon) die uitsluitend `spelgroepId` +
`pouleId` als input nodig heeft. Als de tegenstander-scout faalt (bv. nog
geen playwright-data voor de tegenstander, een tijdelijke netwerkfout, of
de tegenstander-roster kon nog niet ontdekt worden), blokkeerde dat dus
ONTERECHT ook de rangschikking, zelfs als spelgroepId/pouleId al bekend
waren uit een eerdere, wel geslaagde render deze sessie.
FIX (binnen dit bestand): zodra `reeks_url`/`spelgroep_id` gekend zijn,
worden ze bewaard in st.session_state onder een per-speler sleutel. Bij
een latere render waarbij `scout_result` faalt, valt de Rangschikking-tab
terug op deze laatst gekende waarde in plaats van de hele tab te
blokkeren - de rangschikkingslink en de eigen berekende ranking-tabel
(`oa.render_ranking_tab`, indien een rapport gekend is) blijven dan gewoon
zichtbaar.
--------------------------------------------------------------------------
PADEL_ANALYSIS_POULE_RANKING_INTEGRATION_2026-09-27 (op verzoek van Kim:
"ik zie nu die nieuwe logica niet me de punten per ploeg en de info in
welke scenario's we kunnen doorgaan door bij de beste 2 te eindigen.")
--------------------------------------------------------------------------
ROOT CAUSE: `poule_ranking.py` (de module met de volledige rangschikkings-
tabel + kwalificatiescenario's - "eerste 2 gaan door", tie-break via
onderlinge confrontatie bij een gelijke stand tussen 2 ploegen) was al
volledig gebouwd EN getest, maar nooit daadwerkelijk aangesloten op dit
bestand - enkel de aansluitcode zelf was ooit gegeven, nooit effectief in
dit bestand verwerkt. Vandaar dat Kim de puntentabel en de scenario's nooit
zag verschijnen, ondanks dat de module correct werkte.
FIX (binnen dit bestand, in `page_lineup_lab()`, tab "Rangschikking"): na
`_render_rangschikking_link()` en `oa.render_ranking_tab()` wordt nu ook
`poule_ranking.render_poule_ranking_tab(reeks_url_for_ranking, fixtures,
own_ploeg_id)` aangeroepen, zodra `own_ploeg_id` gekend is. Dit gebruikt
DEZELFDE `reeks_url_for_ranking` (nu OF uit de sticky cache) en dezelfde
`fixtures`/`own_ploeg_id` die al in session_state zitten sinds "Volgende
match" - dus geen extra scrape, geen nieuwe afhankelijkheid van de
tegenstander-scout, en zichtbaar in exact dezelfde gevallen als de
rangschikkingslink zelf. Een ontbrekende/falende `poule_ranking`-import
wordt (zoals bij het "Andere ploegen"-tabblad hieronder) opgevangen met
een `st.warning`, nooit met een crash van de hele pagina.
"""
import streamlit as st
from dashboard_common import (
    fb, ll, ss, osu, oa, _display_name, _format_scraped_at, _go_to_player,
    _get_all_profiles,
)
from lineup_scout import (
    _render_volgende_match_and_scout, _scout_team_all_fixtures,
    _recent_own_lineup_roster, _merge_full_opponent_roster,
    _build_own_official_ranks_strict, _render_official_rank_warning,
    _opponent_padelstat_ratings, _cached_docs_for_players,
    _cached_own_player_rating, _clear_rank_caches, _load_encounter_index,
)
from lineup_rules import _render_tournament_rules_selector
from lineup_opponent_history import (
    _render_previous_opponent_lineup, _render_match1_frequency_opponent,
)
from lineup_rotation import _render_rotation_planner, _WIN_PROB_DISCLAIMER
from lineup_matchup_table import _render_all_valid_matchups
from lineup_sandbox import _render_lineup_sandbox
try:
    import opponent_scout as osc
except Exception:  # noqa: BLE001  pragma: no cover
    osc = None
try:
    import poule_ranking
except Exception:  # noqa: BLE001  pragma: no cover
    poule_ranking = None


def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    st.divider()
    st.markdown('<div class="section-header">Opstelling-analyse</div>', unsafe_allow_html=True)
    with st.expander("Wat betekenen winkans, verwachte matchen, synergie, puntengrens en 'Reglementair'?", expanded=False):
        st.markdown(
            "- **Winkans per match**: een RUWE schatting (logistische functie op het ratingverschil), "
            "gebaseerd op padelstats.be playing strength waar bekend, anders het officiele klassement "
            "als terugval - PER SPELER individueel.\n"
            "- **Verwacht aantal gewonnen matchen**: de som van de winkansen over alle matchen van "
            "die opstelling.\n"
            "- **Winkans-kolom**: de winkans per match staat als apart, sorteerbaar percentage naast "
            "de kolom met de koppelnamen.\n"
            "- **Officiele regel (art. 6.6)**: binnen elke ROTATIE speelt het duo met de HOOGSTE SOM "
            "van de 2 OFFICIELE klassementen op het laagst genummerde match van die rotatie "
            "(Rotatie R-1 voor Rotatie R-2). Bij een GELIJKSPEL in officieel klassement mag de ploeg zelf "
            "kiezen (BEIDE volgordes worden dan getoond); bij een verschil is enkel de sterkste-eerst-"
            "volgorde toegelaten.\n"
            "- **Reglementair-badge**: OK = deze matchup-rij gebruikt overal de reglementair verplichte "
            "(of, bij gelijkspel, een even geldige) bordvolgorde. NIET = een BEWUST omgedraaide "
            "variant (enkel zichtbaar als je de bijhorende checkbox aanvinkt) - dit zou een overtreding "
            "van art. 6.6 zijn en dient enkel om het best-case/worst-case-bereik van een koppelkeuze in "
            "te schatten, NOOIT als effectieve wedstrijdopstelling. onzeker = minstens 1 speler heeft "
            "nog geen bekend officieel klassement, waardoor de volgorde NIET betrouwbaar geverifieerd kon "
            "worden (ververs eerst het klassement van deze speler(s)) - in dit geval worden BEIDE mogelijke "
            "volgordes getoond, geen van beide als bevestigd.\n"
            "- **Rotatie-veiligheid**: een speler kan nooit in 2 GELIJKTIJDIGE matchen van dezelfde "
            "rotatie staan.\n"
            "- **Vorige keer**: deze matchup komt overeen met een opstelling die de tegenstander "
            "EFFECTIEF al eens speelde dit seizoen.\n\n"
            + _WIN_PROB_DISCLAIMER
        )
    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    try:
        opp_team_fixtures = ss.get_team_fixtures(fixtures, opp.get("ploeg_id")) if fixtures else []
        next_match = ss.get_next_match(opp_team_fixtures) if opp_team_fixtures else None
        before_date = (next_match or {}).get("date_text") or ""
    except Exception:
        before_date = ""
    full_opp_bundle = _scout_team_all_fixtures(
        fixtures, opp.get("ploeg_id"), opp.get("name") or "", before_date,
    ) if fixtures else {}
    _render_previous_opponent_lineup(bundle, opp=opp, full_bundle=full_opp_bundle)
    _render_match1_frequency_opponent(bundle, full_bundle=full_opp_bundle)
    own_candidates = sorted(profiles, key=lambda x: x.get("display_name") or "")
    own_labels = [_display_name(p) for p in own_candidates]
    own_label_to_id = {
        _display_name(p): str(p.get("player_id"))
        for p in own_candidates if p.get("player_id") is not None
    }
    roster = _recent_own_lineup_roster(fixtures, own_ploeg_id)
    known_ids = set(own_label_to_id.values())
    for pid, naam in roster.items():
        if pid in known_ids:
            continue
        label = f"{naam} (nog geen profiel)"
        own_labels.append(label)
        own_label_to_id[label] = pid
    col_roster, col_refresh = st.columns([3, 1])
    with col_refresh:
        if st.button("Ploeg opnieuw ophalen", key=f"refresh_own_roster_{sel_player_id}"):
            for key in [k for k in list(st.session_state) if str(k).startswith(("own_roster_v2_", "full_scout_v2_"))]:
                st.session_state.pop(key, None)
            _load_encounter_index.clear()
            _clear_rank_caches()
            st.rerun()
    if roster:
        default_labels = [lbl for lbl, pid in own_label_to_id.items() if pid in roster]
        sel_label_self = next(
            (lbl for lbl, pid in own_label_to_id.items() if pid == str(sel_player_id)), None
        )
        if sel_label_self and sel_label_self not in default_labels:
            default_labels.append(sel_label_self)
        with col_roster:
            st.caption(
                f"Standaard vooraf geselecteerd: de opstelling van onze ploeg in de vorige "
                f"interclubontmoeting ({len(default_labels)} speler(s)), rechtstreeks uit het "
                "uitslagenblad van die ontmoeting."
            )
        if len(default_labels) < 4:
            st.warning(
                f"Slechts {len(default_labels)} speler(s) gevonden in het uitslagenblad van "
                "onze vorige ontmoeting. Dat wijst op een onvolledig geparseerd uitslagenblad of "
                "een effectief kleinere ploeg die dag. Vul de selectie hieronder handmatig aan."
            )
    else:
        default_labels = own_labels[: min(8, len(own_labels))]
        with col_roster:
            st.caption(
                "Onze vorige ontmoeting kon niet opgehaald worden (nog geen poule-schema "
                "geladen, of nog geen gespeelde wedstrijd). Selecteer de spelers hieronder zelf."
            )
    available_labels = st.multiselect(
        "Beschikbare eigen spelers", own_labels, default=default_labels,
        key="scenario_available_players",
    )
    if len(available_labels) < 2:
        st.info("Selecteer minstens 2 spelers.")
        return
    available_ids = [own_label_to_id[lbl] for lbl in available_labels]
    official_ranks_for_suggestion = _build_own_official_ranks_strict(available_ids)
    tournament_rules_dict, rules_label = _render_tournament_rules_selector(
        opp["ploeg_id"], sel_player_id,
        available_official_ranks=[official_ranks_for_suggestion.get(pid) for pid in available_ids],
    )
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
        st.error(f"Speler-plaatsen ({total_slots}) moet gelijk zijn aan 2x wedstrijden ({2*total_boards}).")
        return
    docs_for_synergy = _cached_docs_for_players(tuple(sorted(available_ids)))
    own_synergy = ll.compute_pairwise_synergy(docs_for_synergy, available_ids)
    synergy_fn = ll.make_pair_score_fn(own_synergy, docs_for_synergy)
    player_ratings = {pid: _cached_own_player_rating(pid) for pid in available_ids}
    player_ratings = {k: v for k, v in player_ratings.items() if v is not None}
    official_ranks_strict = official_ranks_for_suggestion
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)
    opponent_ratings = _opponent_padelstat_ratings(bundle)
    for _lbl, _pid in own_label_to_id.items():
        name_lookup_global.setdefault(_pid, _lbl)
    all_matchups = _render_all_valid_matchups(
        bundle, opp, available_ids, max_per_player, int(total_boards), synergy_fn,
        player_ratings, official_ranks_strict, opponent_ratings, report,
        name_lookup_global, sel_player_id,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
    ) or []
    st.divider()
    chosen_scenario_boards = None
    _render_rotation_planner(
        available_ids, synergy_fn, official_ranks_strict, name_lookup_global, opp,
        opponent_boards=chosen_scenario_boards, player_ratings=player_ratings,
        opponent_ratings=opponent_ratings, report_for_ai=report,
        tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
        bundle=bundle, total_boards=total_boards,
    )
    st.divider()
    _render_lineup_sandbox(
        bundle, opp, available_ids, name_lookup_global,
        player_ratings, official_ranks_strict, opponent_ratings, synergy_fn,
        profiles=profiles, sel_player_id=sel_player_id,
    )


def _render_saved_lineup_analyses(name_lookup_global: dict):
    st.markdown('<div class="section-header">Opgeslagen opstelling-analyses</div>', unsafe_allow_html=True)
    st.caption("Analyses die je eerder opsloeg.")
    analyses = fb.list_lineup_analyses()
    if not analyses:
        st.info("Nog geen analyses opgeslagen.")
        return
    labels = []
    for a in analyses:
        owner_label = name_lookup_global.get(a.get("owner_player_id"), a.get("owner_player_id"))
        saved_at = _format_scraped_at(a.get("saved_at"))
        labels.append(f"{a.get('opponent_name', '?')} - {owner_label} - {saved_at}")
    chosen = st.selectbox("Kies een opgeslagen analyse", labels, key="saved_analysis_pick")
    idx = labels.index(chosen)
    analysis = analyses[idx]
    st.markdown(f"**Tegenstander:** {analysis.get('opponent_name', '?')}")
    st.caption(f"Opgeslagen op {_format_scraped_at(analysis.get('saved_at'))} - eigen spelers: {', '.join(analysis.get('own_player_labels', []) or [])}")
    for scenario in analysis.get("scenarios", []) or []:
        options = scenario.get("options") or []
        with st.expander(f"{scenario.get('fixture_label', '?')} - {scenario.get('boards_count', 0)} wedstrijden ({len(options)} opties)"):
            if not options:
                st.info("Geen resultaat opgeslagen.")
                continue
            for opt_idx, option in enumerate(options, start=1):
                ebw = option.get("expected_boards_won")
                st.write(f"**Optie {opt_idx}**" + (f" - verwacht {ebw:.2f} matchen gewonnen" if ebw is not None else f" - score {option.get('total_score')}"))
                for a in option.get("assignment", []) or []:
                    pair_labels = a.get("our_pair_labels") or ["?", "?"]
                    opp_names = " / ".join(a.get("opponent_names", []) or [])
                    wp = a.get("win_probability")
                    wp_txt = f", winkans {int(round(wp*100))}%" if wp is not None else ""
                    st.write(f"{pair_labels[0]} / {pair_labels[1]} (synergie {a.get('synergy')}) - vs {opp_names}{wp_txt}")
    if st.button("Deze analyse verwijderen", key=f"delete_analysis_{analysis.get('_doc_id')}"):
        fb.delete_lineup_analysis(analysis["_doc_id"])
        st.success("Analyse verwijderd.")
        st.rerun()


def _build_rangschikking_url(reeks_url: str):
    if not reeks_url:
        return None
    try:
        from urllib.parse import urlparse, parse_qs, urlencode
        parsed = urlparse(reeks_url)
        qs = parse_qs(parsed.query)
        spelgroep_id = (qs.get("spelgroepId") or [None])[0]
        poule_id = (qs.get("pouleId") or [None])[0]
        if not spelgroep_id or not poule_id:
            return None
        base = "https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/interclub-rangschikking"
        return f"{base}?{urlencode({'spelgroepId': spelgroep_id, 'pouleId': poule_id})}"
    except Exception:
        return None


def _render_rangschikking_link(reeks_url: str) -> None:
    """PADEL_ANALYSIS_RANGSCHIKKING_ALTIJD_ZICHTBAAR_2026-09-27: deze
    functie zelf is ongewijzigd - ze toont gewoon de link zodra ze een
    geldige `reeks_url` krijgt. De fix zit in page_lineup_lab() hieronder,
    die deze functie nu ook aanroept met een uit session_state
    teruggevallen waarde wanneer scout_result recent gefaald is."""
    url = _build_rangschikking_url(reeks_url)
    if url:
        try:
            st.link_button("Bekijk de officiele rangschikking op TVL", url)
        except AttributeError:
            st.markdown(f"[Bekijk de officiele rangschikking op TVL]({url})")
    else:
        st.info(
            "Kon de rangschikkingslink nog niet automatisch afleiden - het poule/tabel-schema "
            "moet eerst geladen zijn (zie 'Volgende match' hierboven)."
        )
    st.divider()


def _render_poule_ranking_section(reeks_url_for_ranking: str, sel_player_id) -> None:
    """PADEL_ANALYSIS_POULE_RANKING_INTEGRATION_2026-09-27: sluit de al
    langer bestaande, apart getest `poule_ranking.py`-module effectief aan.
    Toont de volledige puntentabel van de poule + per resterende eigen
    wedstrijd alle kwalificatiescenario's ("gaan we door bij de beste 2?").
    Gebruikt UITSLUITEND al gekende session_state-data (`fixtures`,
    `own_ploeg_id`) - geen extra afhankelijkheid van de tegenstander-scout,
    dus zichtbaar in dezelfde gevallen als de rangschikkingslink hierboven."""
    if poule_ranking is None:
        st.warning(
            "Kon de module 'poule_ranking' niet laden - controleer of poule_ranking.py "
            "in dezelfde map staat als de andere PadelAnalysis-bestanden."
        )
        return
    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    if not own_ploeg_id:
        st.info(
            "Eigen ploeg nog niet gekend voor deze speler - laad eerst 'Volgende match' "
            "hierboven zodat de eigen ploeg herkend kan worden."
        )
        return
    try:
        poule_ranking.render_poule_ranking_tab(reeks_url_for_ranking, fixtures, own_ploeg_id)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Kon de poule-rangschikking niet laden: {exc}")


def page_lineup_lab():
    st.header("Opstelling-analyse")
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
    sel_label = st.selectbox("Toon analyse voor:", labels, index=default_idx, key="lineup_lab_sel_player")
    sel_profile = profile_map[sel_label]
    sel_player_id = sel_profile.get("player_id")
    scout_result = _render_volgende_match_and_scout(str(sel_player_id), sel_label)
    bundle = opp = reeks_url = spelgroep_id = None
    report_for_ai = None
    if scout_result:
        bundle, opp, reeks_url, spelgroep_id = scout_result
        _fixtures_voor_roster = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
        bundle = _merge_full_opponent_roster(bundle, _fixtures_voor_roster, opp)
        extra_namen = bundle.get("_roster_extended_with") or []
        if extra_namen:
            st.caption(
                f"{len(extra_namen)} extra speler(s) uit eerdere ontmoetingen mee "
                f"opgenomen in deze analyse: {', '.join(extra_namen)}."
            )
            onzeker_namen = bundle.get("_roster_extended_low_confidence") or []
            if onzeker_namen:
                st.caption(
                    f"Let op: {', '.join(onzeker_namen)} "
                    + ("is" if len(onzeker_namen) == 1 else "zijn")
                    + " slechts 1x waargenomen en heeft/hebben verder nog geen "
                    "bekende matchdata bij ons - eerder een eenmalige invaller dan een "
                    "bevestigde vaste speler."
                )
        if bundle.get("unique_players"):
            all_docs, global_docs = osu.prepare_team_docs(bundle, str(sel_player_id))
            report_for_ai = oa.get_team_report(
                bundle, opp, all_docs, current_reeks_url=reeks_url,
                current_spelgroep_id=spelgroep_id, global_docs=global_docs,
                key_prefix=f"scout_team_{sel_player_id}",
            )
            report_for_ai = oa.render_team_header(
                report_for_ai, bundle, opp, all_docs, current_reeks_url=reeks_url,
                current_spelgroep_id=spelgroep_id, global_docs=global_docs,
                key_prefix=f"scout_team_{sel_player_id}",
            )
    # PADEL_ANALYSIS_RANGSCHIKKING_ALTIJD_ZICHTBAAR_2026-09-27: zie de
    # uitgebreide toelichting bovenaan dit bestand. reeks_url/spelgroep_id
    # worden hier per speler gecached in session_state zodra ze gekend
    # zijn, zodat de Rangschikking-tab hieronder daarop kan terugvallen
    # wanneer scout_result op een latere render faalt.
    reeks_url_cache_key = f"vm_reeks_url_cache_{sel_player_id}"
    if reeks_url:
        st.session_state[reeks_url_cache_key] = reeks_url
    reeks_url_for_ranking = reeks_url or st.session_state.get(reeks_url_cache_key)
    tab_analyse, tab_rang, tab_poule, tab_saved = st.tabs(
        ["Analyseren", "Rangschikking", "Andere ploegen", "Opgeslagen analyses"]
    )
    with tab_analyse:
        if scout_result:
            sub_overzicht, sub_detail = st.tabs(["Overzicht", "Detail per speler"])
            with sub_overzicht:
                if report_for_ai is not None:
                    oa.render_overview_tab(report_for_ai)
                    st.divider()
                _render_opstelling_scenario(
                    bundle, opp, profiles, name_lookup_global, str(sel_player_id), report_for_ai,
                )
            with sub_detail:
                if report_for_ai is not None:
                    oa.render_player_detail_tab(report_for_ai, key_prefix=f"scout_team_{sel_player_id}")
                else:
                    st.info("Nog geen rapport beschikbaar voor deze tegenploeg.")
            if report_for_ai is not None:
                st.divider()
                oa.render_ai_section(report_for_ai, opp.get("ploeg_id"), key_prefix=f"scout_team_{sel_player_id}")
    with tab_rang:
        # PADEL_ANALYSIS_RANGSCHIKKING_ALTIJD_ZICHTBAAR_2026-09-27: niet
        # langer `if scout_result:` als poortwachter - enkel de effectief
        # benodigde `reeks_url_for_ranking` (nu OF uit cache) bepaalt of de
        # rangschikking getoond kan worden.
        if reeks_url_for_ranking:
            _render_rangschikking_link(reeks_url_for_ranking)
            if report_for_ai is not None:
                oa.render_ranking_tab(report_for_ai)
            elif scout_result:
                # scout_result lukte deze keer wel, maar leverde (nog) geen
                # rapport op (bv. unique_players leeg) - dit onderscheidt
                # zich van het cache-only-scenario hierboven, waar geen
                # melding nodig is omdat de gebruiker gewoon de link ziet.
                st.info("Nog geen rapport beschikbaar voor deze tegenploeg.")
            # PADEL_ANALYSIS_POULE_RANKING_INTEGRATION_2026-09-27: de
            # effectieve puntentabel + kwalificatiescenario's, tot nu toe
            # gebouwd maar nooit aangesloten - zie de toelichting bovenaan
            # dit bestand.
            st.divider()
            _render_poule_ranking_section(reeks_url_for_ranking, sel_player_id)
        else:
            st.info("Kies eerst een speler bij 'Toon analyse voor' hierboven.")
    with tab_poule:
        try:
            import poule_teams_ui as ptu
            ptu.render_poule_teams_tab(str(sel_player_id), name_lookup_global, go_to_player_fn=_go_to_player)
        except Exception as exc:
            st.warning(f"Kon dit tabblad niet laden: {exc}")
    with tab_saved:
        _render_saved_lineup_analyses(name_lookup_global)
