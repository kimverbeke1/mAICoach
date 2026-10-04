"""
page_lineup_lab.py - "Opstelling-analyse"-pagina (Volgende match,
Opstelling-scenario's, Rotatieplanner, Opgeslagen analyses).
PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27: dit bestand is de orchestratie-laag;
de zware onderdelen staan in lineup_scout.py, lineup_rules.py,
lineup_opponent_history.py, lineup_rotation.py en lineup_matchup_table.py.
Patch bij een aanpassing enkel de betrokken module.
--------------------------------------------------------------------------
PADEL_ANALYSIS_FRAGMENT_ISOLATION_STAGE2_2026-09-27
--------------------------------------------------------------------------
_render_opstelling_scenario() heeft @st.fragment, zodat widget-interacties
binnenin (vorige-ontmoeting-dropdown, spelersselectie, aantal-wedstrijden-
velden) enkel dit fragment herladen i.p.v. de hele pagina. De "Ploeg
opnieuw ophalen"-knop binnenin doet bewust WEL een ongescopede st.rerun(),
want die wist caches die ook buiten dit fragment gelden.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PERF_TIMING_2026-09-28: deze versie bevat bovendien
meetpunten (perf_timing.py) rond elke zware stap, plus een paneel
"Laadtijd-analyse (debug)" onderaan de pagina dat per render toont waar de
tijd effectief zit. LET OP bij het lezen: _render_opstelling_scenario()
is een @st.fragment - bij een fragment-only rerun draait perf.reset()
NIET, dus meet de EERSTE pagina-load door de pagina te herladen (F5),
niet door in een widget te klikken.
--------------------------------------------------------------------------
PADEL_ANALYSIS_LAZY_SECTIONS_2026-09-28 (op verzoek van Kim: "laden van
opstellingsanalyse pagina zonder al ergens op te drukken duurt lang")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door de code na te lezen, geen gok): de pagina
gebruikte st.tabs(["Analyseren", "Rangschikking", "Andere ploegen",
"Opgeslagen analyses"]). Streamlit voert de body van ELKE tab uit bij elke
render - ook van de tabs die je niet bekijkt; tabs zijn enkel een
CLIENT-SIDE weergave-switch, geen uitvoeringsgrens. Bij het openen van de
pagina, zonder ook maar iets aan te klikken, betaalde Kim dus meteen:
  - tab "Rangschikking"  -> poule_ranking.render_poule_ranking_tab(): de
    volledige poule-stand + kwalificatie-enumeratie,
  - tab "Andere ploegen" -> poule_teams_ui.render_poule_teams_tab(),
  - tab "Opgeslagen analyses" -> fb.list_lineup_analyses() (Firestore),
bovenop de eigenlijke analyse-tab. Drie van de vier secties waren werk voor
iets dat niet eens zichtbaar was. @st.fragment helpt hier niet: fragments
beperken RERUNS, niet de EERSTE render.
FIX: st.tabs is vervangen door een st.radio-sectiekiezer (horizontaal, dus
visueel nagenoeg identiek aan tabs) met if/elif-blokken. Er draait voortaan
nog exact EEN sectie per render - de sectie die de gebruiker effectief
bekijkt. Alle secties zelf zijn FUNCTIONEEL ONGEWIJZIGD; enkel het moment
waarop ze uitgevoerd worden is veranderd. Wisselen van sectie kost nu wel
een rerun (bij tabs was dat client-side), maar die rerun doet minder werk
dan de vorige situatie waarin alles ALTIJD draaide.
Bijkomend, in dezelfde lijn:
  1. De volledige scout-keten (_render_volgende_match_and_scout() ->
     _merge_full_opponent_roster() -> osu.prepare_team_docs() ->
     oa.get_team_report() -> oa.render_team_header()) draait nu enkel nog
     in de sectie "Analyseren". De sectie "Rangschikking" had die keten
     nooit nodig: die werkt sinds
     PADEL_ANALYSIS_RANKING_INDEPENDENT_OF_ANALYSIS_2026-09-27 al volledig
     op _known_ranking_context().
  2. _known_ranking_context() wordt nog enkel aangeroepen wanneer de scout
     de waarden niet al gezet heeft - zie ook de dedupe/memo aan de kant van
     lineup_scout.py (PADEL_ANALYSIS_FIRST_LOAD_DEDUPE_2026-09-28).
  3. De "Ploeg opnieuw ophalen"-knop wist nu ook die memo, zodat een
     bewuste verversing overal doorwerkt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TTL30_PREFETCH_2026-09-29 (op verzoek van Kim, koude-start-meting)
--------------------------------------------------------------------------
_render_opstelling_scenario() leest nu, zodra de beschikbare eigen spelers
gekend zijn, hun profiel/playing strength/spelersdocument in EEN
parallelle batch voor (lineup_scout.prefetch_own_player_reads), VOOR het
officieel klassement en de player_ratings. Meetpunt: "eigen spelers:
parallel voorophalen". Gemeten winst verwacht: ~1s bij een koude start.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SHARED_PLAYER_DOCS_2026-09-29 (op verzoek van Kim, koude-start-meting export 2026-09-29T18-32)
--------------------------------------------------------------------------
GEMETEN: "oa.render_player_detail_tab" kostte 0.89s bij een koude start
(0.52s eerder), terwijl "Detail per speler" standaard NIET zichtbaar is.
Oorzaak: de sub-tabs "Overzicht" / "Detail per speler" gebruikten nog
st.tabs - en Streamlit voert de inhoud van ELKE tab uit, ook de verborgen.
Hetzelfde patroon als PADEL_ANALYSIS_LAZY_SECTIONS_2026-09-28 hierboven.
FIX: st.radio (horizontaal) i.p.v. st.tabs. Enkel de gekozen weergave
draait nog; standaard "Overzicht". De inhoud van beide weergaven is
ongewijzigd, en de AI-sectie eronder blijft altijd zichtbaar.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29 (op verzoek van Kim: "in de najaarsinterclub zijn het
dus 2 rotaties van 2 matchen")
--------------------------------------------------------------------------
Het invoerveld "Aantal wedstrijden deze ontmoeting" is weg. Het getal werd
geraden uit eerdere uitslagenbladen, met 6 als terugval - fout voor de
najaarsinterclub (4). Het formaat komt nu uit het reglement via de
constanten in lineup_rotation.py (ROTATIONS_PER_ENCOUNTER x
MATCHES_PER_ROTATION) en wordt als vaste tekst getoond. Wijken eerdere
uitslagenbladen van deze tegenstander af, dan meldt een caption dat -
zonder het formaat te wijzigen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29 (op verzoek van Kim: "zorg dat je bij de opstelling
aantal rotaties kan instellen. zal handig zijn voor in voorjaar waar het dan
3 rotaties is")
--------------------------------------------------------------------------
Het aantal rotaties is instelbaar (standaard ROTATIONS_PER_ENCOUNTER = 2,
najaar; voorjaar = 3). De keuze wordt per sessie onthouden en geldt voor de
matchup-tabel en de rotatieplanner. Het aantal matchen per rotatie blijft
vast op 2. 'Max. matchen per speler' is begrensd op het aantal rotaties
(een speler speelt per rotatie hoogstens 1 match) en wordt ook aan de
rotatieplanner doorgegeven.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_PLANNER_PRESETS_2026-09-30 (op verzoek van Kim:
"Snelkeuzes bovenaan, per rotatie: 'Zelfde opstelling als vorige match X'
[...] plus eventueel andere zinvolle presets" + "Custom-modus: klik
spelers één voor één aan [...] Een gekozen speler bij Match 1 verdwijnt
meteen uit de keuzelijst van Match 2" + "Rotatie 2 houdt automatisch
rekening met wie al samen speelde in Rotatie 1")
--------------------------------------------------------------------------
_render_rotation_planner() (lineup_rotation.py) krijgt hier nu OOK
`profiles` en `sel_player_id` mee. Nodig voor de snelkeuzes/presets (eigen
historische opstellingen opzoeken per speler) en de klik-voor-klik-
custom-modus - zie lineup_rotation.py voor de volledige toelichting bij
wat daar precies gebouwd is. Punt 3 uit Kim's plan (geen koppel 2x in
dezelfde ontmoeting) bestond al via `excluded_pairs` en is ONGEWIJZIGD -
de presets/custom-modus respecteren die set net als de bestaande kaarten
en de "geavanceerd"-lijst.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01 (op verzoek van Kim, na het
gezamenlijk uitgetekende ontwerp: "die wat als: mijn winkans bij een
andere partner mag weg" + "ja sandbox verwijderen" + "je zou dus zeker
ook kans op 1,2 of 0 punten bij de rotatieplanner moeten tonen")
--------------------------------------------------------------------------
TWEE VERWIJDERINGEN in dit bestand, beide ZUIVER (geen vervangende aanroep
nodig in page_lineup_lab.py zelf - de nuttige presets uit de sandbox zijn
verhuisd NAAR lineup_rotation.py, zie dat bestand voor de volledige
toelichting):
  1. lineup_whatif._render_whatif_comparison() en zijn import - de
     "Wat als: mijn winkans bij een andere partner"-sectie. Kim: "mag weg".
     Geen andere code was hiervan afhankelijk.
  2. lineup_sandbox._render_lineup_sandbox() en zijn import - de aparte
     "Sandbox: bouw je eigen opstelling"-sectie. Kim bevestigde "sandbox
     verwijderen" nadat de 2 nuttige presets ("Ons sterkste 4 (Elo)",
     "Onze vorige opstelling") verhuisd waren naar de "Zelf samenstellen"-
     expander in de Rotatieplanner (lineup_rotation.py).
--------------------------------------------------------------------------
PADEL_ANALYSIS_PLANNING_ALL_FIXTURES_2026-10-03 (op verzoek van Kim, meermaals
gemeld: "Snelkeuze tegenstander is nog altijd maar 1 optie" + het model
toonde "Op basis van 1 eerdere ontmoeting(en)")
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd in de code: `bundle` komt van de scout-header
(osu.render_scout_header) en bevat enkel de LAATSTE ontmoeting(en) in
"previous_fixtures". De volledige historiek (`full_opp_bundle`, via
_scout_team_all_fixtures met lookback=alle) werd enkel gebruikt voor het
blok "vorige ontmoetingen" en - via _merge_full_opponent_roster - om de
SPELERSLIJST aan te vullen, NIET de ontmoetingen zelf. Matchup-tabel,
Rotatieplanner, snelkeuzes en het statistische model zagen dus maar 1
ontmoeting - wat alle eerdere snelkeuze-fixes zinloos maakte.
FIX: _planning_bundle_with_all_fixtures() maakt een KOPIE van `bundle`
waarin "previous_fixtures" = alle ontmoetingen uit full_opp_bundle +
bundle (ontdubbeld). Die kopie gaat naar de matchup-tabel en de
Rotatieplanner. `bundle` zelf (scout-header, AI-rapport, "vorige
ontmoetingen") blijft ONGEWIJZIGD. Een caption toont hoeveel ontmoetingen
de planning gebruikt, zodat dit voortaan controleerbaar is.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03 (op verzoek van Kim: "het zou ook
handig zijn om al gespeelde matchen ook nog te kunnen analyseren maar dan
met de padelstat waardes van toen")
--------------------------------------------------------------------------
Nieuwe sectie "Nabeschouwing" (SECTION_RETRO), zie lineup_retrospective.py
voor de volledige toelichting. Draait, net als de andere secties sinds
PADEL_ANALYSIS_LAZY_SECTIONS_2026-09-28, UITSLUITEND wanneer de gebruiker
deze sectie effectief kiest - geen enkele impact op de laadtijd van de
andere secties. Faalt de import van lineup_retrospective.py (bv. tijdens
een gefaseerde uitrol), dan toont de sectie een duidelijke melding i.p.v.
de hele pagina te laten crashen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04 (op verzoek van Kim: "er zijn een
aantal zaken die een beetje overlappen bij de analyse [...] Ik vind voor
mezelf de rotatieplanner de core. Dus ik zou die na de scenario analyse
tonen. kans op winst en detail bij scenario analyse zelf voor aanvallend,
veilig en robuust mogen dan eigenlijk wel weg [...] Het stuk van alle
matchups, zou je in een apart stuk mogen doen [...] De beste opstelling
voor mezelf, zal daar wegmogen, aangezien we dat gaan toevoegen bij de
voorstellen van de rotatieplanner")
--------------------------------------------------------------------------
De vroegere ENE aanroep van `_render_all_valid_matchups()` (die intern
ALLES deed: roster-keuze, scenario-matrix, de knop "Bereken alle geldige
matchups" en de groepenweergave) is vervangen door TWEE losse aanroepen,
met de Rotatieplanner ERTUSSEN:
  1. lineup_matchup_table.render_opponent_scenario_setup(...) - toont
     "Opstelling-scenario's" (roster-keuze + verwacht aantal matchen +
     model + scenario-matrix, nu ingekort - zie lineup_scenario_matrix.py)
     en geeft een dict terug met "unique_opponent_lineups"/"model_weights"/
     "model_stats".
  2. _render_rotation_planner(...) - ONGEWIJZIGD aangeroepen (zelfde
     argumenten als voorheen); dit is nu de kern van de pagina, meteen na
     de scenario-analyse.
  3. lineup_matchup_table.render_matchup_overview(setup, ...) - toont "Alle
     matchups" (de knop "Bereken alle geldige matchups" + de groepen-
     weergave, nu ZONDER "Beste opstelling voor mezelf" - die vraag
     beantwoordt de Rotatieplanner nu via de nieuwe "Beste voor <naam>"-rij
     in het planscherm).
Daarnaast wordt st.session_state["viewing_player_id_<ploeg_id>"] gezet
(de speler voor wie de analyse loopt, bovenaan de pagina gekozen) - dat
leest lineup_plan_screen.py om te weten VOOR WIE die "Beste voor <naam>"-
rij berekend moet worden, zonder dat lineup_rotation.py's aanroep van
_render_rotation_planner() hoeft te wijzigen (geen nieuw argument nodig).
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
    _known_ranking_context, clear_known_ranking_context_cache,
    prefetch_own_player_reads,  # PADEL_ANALYSIS_TTL30_PREFETCH_2026-09-29
)
from lineup_rules import _render_tournament_rules_selector
from lineup_opponent_history import (
    _render_previous_opponent_lineup, _render_match1_frequency_opponent,
)
from lineup_rotation import (
    _render_rotation_planner, _WIN_PROB_DISCLAIMER,
    ROTATIONS_PER_ENCOUNTER, MATCHES_PER_ROTATION, MATCHES_PER_ENCOUNTER,  # PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29
    _default_opponent_max_per_player,
    ROTATIONS_MIN, ROTATIONS_MAX,  # PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29
)
# PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04: de 2 losse functies i.p.v. de
# ene gecombineerde _render_all_valid_matchups() - zie moduledocstring.
from lineup_matchup_table import render_opponent_scenario_setup, render_matchup_overview
# PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01: lineup_whatif en lineup_sandbox
# zijn NIET MEER GEIMPORTEERD - zie moduledocstring.
# PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03: lazy/defensief - zie moduledocstring.
_retro_import_error = None
try:
    from lineup_retrospective import render_retrospective_tab
except Exception as e:  # noqa: BLE001  pragma: no cover
    render_retrospective_tab = None
    _retro_import_error = f"{type(e).__name__}: {e}"
# PADEL_ANALYSIS_PERF_TIMING_2026-09-28: meet per render waar de tijd zit.
# Faalt de import, dan draait de pagina gewoon door zonder metingen.
try:
    import perf_timing as perf
except Exception:  # noqa: BLE001  pragma: no cover
    class _PerfNoop:
        @staticmethod
        def reset():
            pass
        @staticmethod
        def render_panel(**_kwargs):
            pass
        @staticmethod
        def step(_label):
            from contextlib import nullcontext
            return nullcontext()
    perf = _PerfNoop()
try:
    import opponent_scout as osc
except Exception:  # noqa: BLE001  pragma: no cover
    osc = None
# PADEL_ANALYSIS_POULE_RANKING_IMPORT_ERROR_VISIBLE_2026-09-27: de echte
# faalreden wordt bewaard i.p.v. stilzwijgend weggegooid.
_poule_ranking_import_error = None
try:
    import poule_ranking
except Exception as e:  # noqa: BLE001  pragma: no cover
    poule_ranking = None
    _poule_ranking_import_error = f"{type(e).__name__}: {e}"
SECTION_ANALYSE = "Analyseren"
SECTION_RANG = "Rangschikking"
SECTION_POULE = "Andere ploegen"
SECTION_SAVED = "Opgeslagen analyses"
SECTION_RETRO = "Nabeschouwing"  # PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03
_SECTIONS = [SECTION_ANALYSE, SECTION_RANG, SECTION_POULE, SECTION_SAVED, SECTION_RETRO]
def _fixture_key(fx_bundle: dict):
    """PADEL_ANALYSIS_PLANNING_ALL_FIXTURES_2026-10-03: sleutel om dezelfde
    ontmoeting uit 2 bundels te herkennen."""
    fx = fx_bundle.get("fixture") or {}
    if fx.get("match_id"):
        return ("id", str(fx.get("match_id")))
    key = (
        str(fx.get("date_text") or ""),
        str(fx.get("home_ploeg_id") or fx.get("home_name") or ""),
        str(fx.get("away_ploeg_id") or fx.get("away_name") or ""),
    )
    if not any(key):
        return ("obj", id(fx_bundle))
    return ("dt",) + key
def _planning_bundle_with_all_fixtures(bundle: dict, full_bundle: dict) -> dict:
    """PADEL_ANALYSIS_PLANNING_ALL_FIXTURES_2026-10-03 - zie moduledocstring."""
    full = (full_bundle or {}).get("previous_fixtures") or []
    eigen = (bundle or {}).get("previous_fixtures") or []
    if not full:
        return bundle
    gezien = set()
    samen = []
    for fxb in list(full) + list(eigen):
        k = _fixture_key(fxb)
        if k in gezien:
            continue
        gezien.add(k)
        samen.append(fxb)
    out = dict(bundle)
    out["previous_fixtures"] = samen
    return out
@st.fragment
def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    """PADEL_ANALYSIS_FRAGMENT_ISOLATION_STAGE2_2026-09-27: @st.fragment
    isoleert deze buitenste functie van een volledige pagina-rerun. Alle
    widgets hieronder (vorige-ontmoeting-dropdown, spelersselectie,
    aantal-wedstrijden-velden) triggeren enkel een herlading van dit
    fragment, niet van de hele pagina."""
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
    # PADEL_ANALYSIS_LINEUP_SNAPSHOT_2026-10-03: datum van de volgende ontmoeting, voor de
    # momentopname die het planscherm bewaart (nabeschouwing met de waarden van toen).
    st.session_state[f"next_match_date_{opp.get('ploeg_id')}"] = before_date
    # PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04: de speler voor wie de analyse
    # loopt - lineup_plan_screen.py leest dit voor de "Beste voor <naam>"-rij.
    st.session_state[f"viewing_player_id_{opp.get('ploeg_id')}"] = str(sel_player_id)
    with perf.step("_scout_team_all_fixtures (in fragment)"):
        full_opp_bundle = _scout_team_all_fixtures(
            fixtures, opp.get("ploeg_id"), opp.get("name") or "", before_date,
        ) if fixtures else {}
    # PADEL_ANALYSIS_PLANNING_ALL_FIXTURES_2026-10-03: planning op ALLE ontmoetingen.
    planning_bundle = _planning_bundle_with_all_fixtures(bundle, full_opp_bundle)
    with perf.step("_render_previous_opponent_lineup (vorige ontmoetingen)"):
        _render_previous_opponent_lineup(bundle, opp=opp, full_bundle=full_opp_bundle)
    with perf.step("_render_match1_frequency_opponent"):
        _render_match1_frequency_opponent(bundle, full_bundle=full_opp_bundle)
    own_candidates = sorted(profiles, key=lambda x: x.get("display_name") or "")
    own_labels = [_display_name(p) for p in own_candidates]
    own_label_to_id = {
        _display_name(p): str(p.get("player_id"))
        for p in own_candidates if p.get("player_id") is not None
    }
    with perf.step("_recent_own_lineup_roster (eigen ploeg scrapen)"):
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
            # PADEL_ANALYSIS_LAZY_SECTIONS_2026-09-28: ook de nieuwe
            # sessie-memo van _known_ranking_context() wissen, zodat een
            # bewuste verversing overal doorwerkt.
            clear_known_ranking_context_cache()
            # Bewust NIET scope="fragment" - deze knop wist caches die ook
            # BUITEN dit fragment relevant zijn.
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
    # PADEL_ANALYSIS_TTL30_PREFETCH_2026-09-29: alle per-speler-reads in 1 parallelle batch.
    with perf.step("eigen spelers: parallel voorophalen"):
        prefetch_own_player_reads(available_ids)
    official_ranks_for_suggestion = _build_own_official_ranks_strict(available_ids)
    tournament_rules_dict, rules_label = _render_tournament_rules_selector(
        opp["ploeg_id"], sel_player_id,
        available_official_ranks=[official_ranks_for_suggestion.get(pid) for pid in available_ids],
    )
    # PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29: formaat uit het reglement, niet geraden.
    # PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29: aantal rotaties instelbaar (najaar 2, voorjaar 3).
    c_rot, c_info = st.columns([1, 3])
    with c_rot:
        n_rotations = int(st.number_input(
            "Aantal rotaties", min_value=ROTATIONS_MIN, max_value=ROTATIONS_MAX,
            value=ROTATIONS_PER_ENCOUNTER, step=1, key="encounter_n_rotations",
            help="Volgens het reglement: najaarsinterclub 2 rotaties, voorjaarsinterclub 3. "
                 "Per rotatie worden altijd 2 matchen tegelijk gespeeld.",
        ))
    total_boards = n_rotations * MATCHES_PER_ROTATION
    with c_info:
        st.caption(
            f"**{n_rotations} rotaties van {MATCHES_PER_ROTATION} matchen** = {total_boards} "
            f"matchen per ontmoeting (standaard najaar: {ROTATIONS_PER_ENCOUNTER} rotaties)."
        )
    n_planning_fx = len([fx for fx in planning_bundle.get("previous_fixtures", []) or [] if fx.get("boards")])
    st.caption(
        f"Planning en voorspellingen gebruiken **{n_planning_fx}** eerdere ontmoeting(en) van deze tegenstander."
    )
    afwijkend = sorted({
        len(fx.get("boards") or []) for fx in planning_bundle.get("previous_fixtures", []) or []
        if fx.get("boards") and len(fx.get("boards")) != total_boards
    })
    if afwijkend:
        st.caption(
            f"Let op: eerdere uitslagenbladen van deze tegenstander tonen "
            f"{', '.join(str(n) for n in afwijkend)} matchen - die ontmoetingen worden niet als "
            "'vorige keer'-opstelling meegenomen, omdat ze niet in dit formaat passen."
        )
    # PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29: max. per speler = aantal rotaties.
    # PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29: de standaardverdeling telt nu EXACT op tot 2x het
    # aantal matchen (vroeger ceil(2*matchen/spelers) per speler, wat bij bv.
    # 6 spelers en 4 matchen 12 plaatsen gaf i.p.v. 8 en meteen de foutmelding
    # hieronder toonde). Een speler staat per rotatie in hoogstens 1 match,
    # dus maximaal ROTATIONS_PER_ENCOUNTER matchen per ontmoeting.
    default_max_per_player = _default_opponent_max_per_player(
        list(available_ids), 2 * int(total_boards),
    )
    cols = st.columns(min(len(available_ids), 6) or 1)
    max_per_player = {}
    for i, pid in enumerate(available_ids):
        with cols[i % len(cols)]:
            max_per_player[pid] = st.number_input(
                name_lookup_global.get(pid, pid), min_value=0, max_value=n_rotations,
                value=min(default_max_per_player.get(pid, 0), n_rotations), step=1,
                key=f"scenario_max_v3_{n_rotations}_{pid}",
            )
    total_slots = sum(max_per_player.values())
    if total_slots != 2 * total_boards:
        st.error(f"Speler-plaatsen ({total_slots}) moet gelijk zijn aan 2x wedstrijden ({2*total_boards}).")
        return
    with perf.step("synergie berekenen (docs + pairwise)"):
        docs_for_synergy = _cached_docs_for_players(tuple(sorted(available_ids)))
        own_synergy = ll.compute_pairwise_synergy(docs_for_synergy, available_ids)
        synergy_fn = ll.make_pair_score_fn(own_synergy, docs_for_synergy)
    with perf.step("eigen player_ratings ophalen"):
        player_ratings = {pid: _cached_own_player_rating(pid) for pid in available_ids}
        player_ratings = {k: v for k, v in player_ratings.items() if v is not None}
    official_ranks_strict = official_ranks_for_suggestion
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)
    with perf.step("_opponent_padelstat_ratings"):
        opponent_ratings = _opponent_padelstat_ratings(bundle)
    for _lbl, _pid in own_label_to_id.items():
        name_lookup_global.setdefault(_pid, _lbl)
    # PADEL_ANALYSIS_PAGE_RESTRUCTURE_2026-10-04: 1) scenario-analyse (ingekort),
    # 2) Rotatieplanner (de kern, meteen hierna), 3) "Alle matchups" apart -
    # zie moduledocstring.
    with perf.step("render_opponent_scenario_setup (scenario-analyse)"):
        setup = render_opponent_scenario_setup(
            planning_bundle, opp, int(total_boards), synergy_fn, player_ratings, official_ranks_strict,
            opponent_ratings, available_ids, max_per_player, name_lookup_global=name_lookup_global,
            tournament_rules_dict=tournament_rules_dict,
        )
    st.divider()
    chosen_scenario_boards = None
    with perf.step("_render_rotation_planner"):
        _render_rotation_planner(
            available_ids, synergy_fn, official_ranks_strict, name_lookup_global, opp,
            opponent_boards=chosen_scenario_boards, player_ratings=player_ratings,
            opponent_ratings=opponent_ratings, report_for_ai=report,
            tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
            bundle=planning_bundle, total_boards=total_boards,
            max_per_player=max_per_player,  # PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29
            profiles=profiles, sel_player_id=sel_player_id,  # PADEL_ANALYSIS_ROTATION_PLANNER_PRESETS_2026-09-30
        )
    with perf.step("render_matchup_overview (alle matchups)"):
        all_matchups = render_matchup_overview(
            setup, opp, available_ids, max_per_player, int(total_boards), synergy_fn,
            player_ratings, official_ranks_strict, opponent_ratings, report,
            name_lookup_global, sel_player_id,
            tournament_rules_dict=tournament_rules_dict, rules_label=rules_label,
        ) or []
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
    """PADEL_ANALYSIS_RANGSCHIKKING_ALTIJD_ZICHTBAAR_2026-09-27: toont de
    link zodra ze een geldige `reeks_url` krijgt."""
    url = _build_rangschikking_url(reeks_url)
    if url:
        try:
            st.link_button("Bekijk de officiele rangschikking op TVL", url)
        except AttributeError:
            st.markdown(f"[Bekijk de officiele rangschikking op TVL]({url})")
    else:
        st.info(
            "Kon de rangschikkingslink nog niet automatisch afleiden - het poule/tabel-schema "
            "moet eerst geladen zijn (zie 'Volgende match' in de sectie Analyseren)."
        )
    st.divider()
def _render_poule_ranking_section(reeks_url_for_ranking: str, sel_player_id) -> None:
    """PADEL_ANALYSIS_POULE_RANKING_INTEGRATION_2026-09-27: sluit
    poule_ranking.py effectief aan.
    PADEL_ANALYSIS_POULE_RANKING_IMPORT_ERROR_VISIBLE_2026-09-27: toont ook
    de ECHTE, onderliggende importfout (indien gekend)."""
    if poule_ranking is None:
        detail = f" Details: `{_poule_ranking_import_error}`." if _poule_ranking_import_error else ""
        st.warning(
            "Kon de module 'poule_ranking' niet laden - controleer of poule_ranking.py "
            f"in dezelfde map staat als de andere PadelAnalysis-bestanden.{detail}"
        )
        return
    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    if not own_ploeg_id:
        st.info(
            "Eigen ploeg nog niet gekend voor deze speler - dit wordt automatisch aangevuld "
            "zodra het poule-schema voor deze speler bekend is (normaal via de dagelijkse "
            "update, of open de sectie 'Analyseren' en laad 'Volgende match')."
        )
        return
    try:
        poule_ranking.render_poule_ranking_tab(reeks_url_for_ranking, fixtures, own_ploeg_id)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Kon de poule-rangschikking niet laden: {type(exc).__name__}: {exc}")
def _ensure_known_ranking_context(sel_player_id, sel_label):
    """PADEL_ANALYSIS_LAZY_SECTIONS_2026-09-28: vult reeks_url/fixtures/
    own_ploeg_id aan uit reeds OPGESLAGEN data, maar doet dat werk enkel
    wanneer het nog nodig is. Overschrijft NOOIT een reeds door de scout
    gezette, autoritatieve waarde."""
    fixtures_key = f"vm_fixtures_{sel_player_id}"
    ploeg_key = f"vm_own_ploeg_id_{sel_player_id}"
    reeks_url_cache_key = f"vm_reeks_url_cache_{sel_player_id}"
    heeft_alles = (
        st.session_state.get(fixtures_key)
        and st.session_state.get(ploeg_key)
        and st.session_state.get(reeks_url_cache_key)
    )
    if heeft_alles:
        return st.session_state.get(reeks_url_cache_key)
    known_reeks_url, known_fixtures, known_own_ploeg_id = _known_ranking_context(
        str(sel_player_id), sel_label,
    )
    if known_fixtures and not st.session_state.get(fixtures_key):
        st.session_state[fixtures_key] = known_fixtures
    if known_own_ploeg_id and not st.session_state.get(ploeg_key):
        st.session_state[ploeg_key] = known_own_ploeg_id
    if known_reeks_url and not st.session_state.get(reeks_url_cache_key):
        st.session_state[reeks_url_cache_key] = known_reeks_url
    return st.session_state.get(reeks_url_cache_key)
def _render_analyse_section(sel_player_id, sel_label, profiles, name_lookup_global):
    """De volledige scout-keten. PADEL_ANALYSIS_LAZY_SECTIONS_2026-09-28:
    draait nu uitsluitend wanneer de gebruiker deze sectie effectief
    bekijkt - voorheen draaide ze bij elke pagina-render, ook wanneer de
    gebruiker in een andere tab keek."""
    with perf.step("_render_volgende_match_and_scout (schema + scout-header)"):
        scout_result = _render_volgende_match_and_scout(str(sel_player_id), sel_label)
    if not scout_result:
        return
    bundle, opp, reeks_url, spelgroep_id = scout_result
    if reeks_url:
        st.session_state[f"vm_reeks_url_cache_{sel_player_id}"] = reeks_url
    _fixtures_voor_roster = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    with perf.step("_merge_full_opponent_roster (volledige tegenstander-historiek)"):
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
    report_for_ai = None
    if bundle.get("unique_players"):
        with perf.step("osu.prepare_team_docs (spelersdocumenten laden)"):
            all_docs, global_docs = osu.prepare_team_docs(bundle, str(sel_player_id))
        with perf.step("oa.get_team_report (rapport bouwen/cache-check)"):
            report_for_ai = oa.get_team_report(
                bundle, opp, all_docs, current_reeks_url=reeks_url,
                current_spelgroep_id=spelgroep_id, global_docs=global_docs,
                key_prefix=f"scout_team_{sel_player_id}",
            )
        with perf.step("oa.render_team_header"):
            report_for_ai = oa.render_team_header(
                report_for_ai, bundle, opp, all_docs, current_reeks_url=reeks_url,
                current_spelgroep_id=spelgroep_id, global_docs=global_docs,
                key_prefix=f"scout_team_{sel_player_id}",
            )
    # PADEL_ANALYSIS_SHARED_PLAYER_DOCS_2026-09-29: st.radio i.p.v. st.tabs - enkel de gekozen weergave draait.
    weergave = st.radio(
        "Weergave", ["Overzicht", "Detail per speler"], horizontal=True,
        label_visibility="collapsed", key=f"lineup_lab_subview_{sel_player_id}",
    )
    if weergave == "Overzicht":
        if report_for_ai is not None:
            with perf.step("oa.render_overview_tab"):
                oa.render_overview_tab(report_for_ai)
            st.divider()
        with perf.step("_render_opstelling_scenario (fragment)"):
            _render_opstelling_scenario(
                bundle, opp, profiles, name_lookup_global, str(sel_player_id), report_for_ai,
            )
    else:
        if report_for_ai is not None:
            with perf.step("oa.render_player_detail_tab"):
                oa.render_player_detail_tab(report_for_ai, key_prefix=f"scout_team_{sel_player_id}")
        else:
            st.info("Nog geen rapport beschikbaar voor deze tegenploeg.")
    if report_for_ai is not None:
        st.divider()
        with perf.step("oa.render_ai_section (enkel UI, geen AI-call)"):
            oa.render_ai_section(report_for_ai, opp.get("ploeg_id"), key_prefix=f"scout_team_{sel_player_id}")
def _render_retrospective_section(profiles) -> None:
    """PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03 - zie moduledocstring en
    lineup_retrospective.py. Draait enkel wanneer de gebruiker deze sectie
    effectief kiest (zelfde lui-ladingspatroon als de andere secties)."""
    if render_retrospective_tab is None:
        st.warning(
            "Kon de module 'lineup_retrospective' niet laden - controleer of "
            "lineup_retrospective.py in dezelfde map staat als de andere "
            f"PadelAnalysis-bestanden. Details: `{_retro_import_error}`."
        )
        return
    try:
        render_retrospective_tab(profiles)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Kon de nabeschouwing niet tonen: {type(exc).__name__}: {exc}")
def page_lineup_lab():
    # PADEL_ANALYSIS_PERF_TIMING_2026-09-28: metingen van de VORIGE render
    # wissen. Moet de allereerste regel zijn, vóór elke perf.step().
    perf.reset()
    st.header("Opstelling-analyse")
    with perf.step("_get_all_profiles"):
        profiles = _get_all_profiles()
    if not profiles:
        st.info("Nog geen spelers in de database.")
        return
    name_lookup_global = {p.get("player_id"): _display_name(p) for p in profiles}
    profile_map = {_display_name(p): p for p in sorted(profiles, key=lambda x: x.get("display_name") or "")}
    with perf.step("fb.get_app_settings"):
        settings = fb.get_app_settings()
    home_id = settings.get("home_player_id")
    home_label = next((lbl for lbl, p in profile_map.items() if p.get("player_id") == home_id), None)
    labels = list(profile_map.keys())
    default_idx = labels.index(home_label) if home_label in labels else 0
    sel_label = st.selectbox("Toon analyse voor:", labels, index=default_idx, key="lineup_lab_sel_player")
    sel_profile = profile_map[sel_label]
    sel_player_id = sel_profile.get("player_id")
    # PADEL_ANALYSIS_LAZY_SECTIONS_2026-09-28: st.radio i.p.v. st.tabs -
    # zie de module-docstring. Tabs voeren ELKE tab-body uit bij elke
    # render; met een radio + if/elif draait er nog exact EEN sectie.
    section = st.radio(
        "Sectie", _SECTIONS, horizontal=True, label_visibility="collapsed",
        key=f"lineup_lab_section_{sel_player_id}",
    )
    if section == SECTION_ANALYSE:
        with perf.step("SECTIE Analyseren"):
            _render_analyse_section(sel_player_id, sel_label, profiles, name_lookup_global)
    elif section == SECTION_RANG:
        # PADEL_ANALYSIS_RANKING_INDEPENDENT_OF_ANALYSIS_2026-09-27: deze
        # sectie hangt NOOIT af van of de gebruiker al "analyseren" deed -
        # ze werkt volledig op reeds opgeslagen data.
        with perf.step("_ensure_known_ranking_context"):
            reeks_url_for_ranking = _ensure_known_ranking_context(sel_player_id, sel_label)
        if reeks_url_for_ranking:
            _render_rangschikking_link(reeks_url_for_ranking)
            st.divider()
            with perf.step("SECTIE Rangschikking (poule_ranking)"):
                _render_poule_ranking_section(reeks_url_for_ranking, sel_player_id)
        else:
            st.info(
                "Kon de rangschikkingslink nog niet bepalen voor deze speler - het poule-schema "
                "is nog niet gekend (dit wordt normaal automatisch aangevuld via de dagelijkse "
                "update, of open de sectie 'Analyseren' en laad 'Volgende match')."
            )
    elif section == SECTION_POULE:
        with perf.step("SECTIE Andere ploegen (poule_teams_ui)"):
            try:
                import poule_teams_ui as ptu
                ptu.render_poule_teams_tab(str(sel_player_id), name_lookup_global, go_to_player_fn=_go_to_player)
            except Exception as exc:
                st.warning(f"Kon deze sectie niet laden: {exc}")
    elif section == SECTION_SAVED:
        with perf.step("SECTIE Opgeslagen analyses"):
            _render_saved_lineup_analyses(name_lookup_global)
    elif section == SECTION_RETRO:
        # PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03: hangt NIET af van de scout-
        # keten - werkt rechtstreeks op de al gescrapete eigen matchdata.
        with perf.step("SECTIE Nabeschouwing"):
            _render_retrospective_section(profiles)
    # PADEL_ANALYSIS_PERF_TIMING_2026-09-28: het meetpaneel staat bewust
    # HELEMAAL onderaan, zodat het de metingen van de volledige render kan
    # tonen. Zet perf_timing.PERF_ENABLED = False om het uit te schakelen.
    st.divider()
    perf.render_panel()
