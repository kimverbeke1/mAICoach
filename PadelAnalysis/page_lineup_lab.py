
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
klassement) en gaf NOOIT de omgekeerde volgorde als alternatief terug.
FIX, kern van de aanpak:
  - _rotation_order_variants(): geeft voor 1 rotatie ALTIJD BEIDE mogelijke
    volgordes terug (normaal + omgekeerd), elk met een expliciete
    "is_regulation_compliant"-vlag.
  - _enumerate_own_variant_combinations(): bouwt voor een volledige
    (rotatie-veilige) eigen koppelverdeling het cartesisch product van de
    variant-keuzes per rotatie op.
  - _build_all_valid_matchups() gebruikt deze enumeratie i.p.v. de vorige,
    enkelvoudige _order_rotations_with_tiebreak(). Een NIEUWE checkbox "🎲
    Toon ook bewust omgedraaide, niet-reglementaire varianten" (standaard
    UIT) bepaalt of de niet-compliant-varianten ÜBERHAUPT gegenereerd
    worden.
  - Nieuwe kolom "Reglementair" in de matchup-tabel (✅ / ⚠️ per matchup).
--------------------------------------------------------------------------
PADEL_ANALYSIS_AI_FOLLOWUP_ON_MATCHUPS_2026-09-18 (op verzoek van Kim: "zorg
dat ik kan doorvragen")
--------------------------------------------------------------------------
De "🤖 AI-inzicht over de beste matchups"-knop gaf voorheen slechts 1
eenmalig antwoord, zonder mogelijkheid om door te vragen. Nu vervangen door
dezelfde chat-aanpak: een bijgehouden geschiedenis in st.session_state,
getoond als doorlopend gesprek.
--------------------------------------------------------------------------
PADEL_ANALYSIS_THREE_TABS_SPLIT_2026-09-21 (op verzoek van Kim: "ik zou tab
overzicht, detail per speler en rangschikking maken: detail per speler moet
naar detail per speler tab. Opstelling analyse mag bij overzicht (staat nu
bij detail).")
--------------------------------------------------------------------------
FIX: page_lineup_lab() gebruikt nu 3 EIGEN tabbladen binnen "🔍 Analyseren",
die de nieuwe, losse bouwstenen uit opponent_analysis.py hergebruiken
(render_overview_tab() / render_player_detail_tab() / render_ranking_tab()).
--------------------------------------------------------------------------
PADEL_ANALYSIS_ENCOUNTER_CACHE_MANUAL_CLEAR_2026-09-21 (op verzoek van Kim,
chat 2026-09-21: "4-teammates-probleem" — eerste diagnose: de
_encounter_key()-fix (lineup_lab.py) is logisch correct, maar
@st.cache_data(ttl=600) op _load_encounter_index() hieronder kan een
eerder berekende, foutieve groepering tot 10 minuten laten "doorleven")
--------------------------------------------------------------------------
Nieuwe, kleine "🔄 Ontmoetingen-cache verversen"-knop, geplaatst vlak boven
de "Beschikbare eigen spelers"-selector, roept `_load_encounter_index.clear()`
aan en forceert een rerun. Deze cache/knop is intussen enkel nog relevant
voor de sandbox-preset "📋 Onze vorige opstelling" (_recent_own_lineup_
boards()) — de HOOFDSELECTIE ("Beschikbare eigen spelers") gebruikt deze
cache sinds de fixes hieronder niet meer.
--------------------------------------------------------------------------
PADEL_ANALYSIS_OWN_TEAM_PARTNER_ID_FALLBACK_FIX_2026-09-21 (op verzoek van
Kim, chat 2026-09-21: "het probleem dat mijn eigen ploeg nog steeds maar
3 spelers toont blijft bestaan")
--------------------------------------------------------------------------
Eerste tussenstap: _recent_own_lineup_player_ids() gebruikte niet langer
ll.reconstruct_boards()/board["pair"] (die een correct opgeloste
partner_user_id vereiste, notoir onbetrouwbaar), maar verzamelde in de
plaats elke `pid` met een eigen entry in de encounter-index-groep — op
basis van exacte matching van (match_date, encounter)-TEKST tussen de
onafhankelijk gescrapete documenten van elke teamgenoot. Bleek in de
praktijk (zie volgende fix) NOG STEEDS te fragiel.
--------------------------------------------------------------------------
PADEL_ANALYSIS_DATE_ONLY_TEAMMATE_MATCH_FIX_2026-09-21 (op verzoek van Kim:
"beschikbare eigen spelers in laatste versie is nu maar 1 [...] kijk gewoon
naar de spelers van mijn ploeg van de vorige match")
--------------------------------------------------------------------------
Tussenstap: matching op EXACTE (match_date, encounter)-TEKST bleek nog
steeds te fragiel tussen 4 onafhankelijk gescrapete documenten, dus
vervangen door matching op UITSLUITEND de kalenderdatum
(_parse_match_date()), gezocht over ALLE profielen in de database. Bleek
(zie volgende fix) OOK niet correct: interclub-speeldagen zijn league-breed
vaak gestandaardiseerd, dus dit pikte ook spelers van HELEMAAL ANDERE
teams op die toevallig dezelfde speeldag hadden (incl. de tegenstander die
op dat moment geanalyseerd werd).
--------------------------------------------------------------------------
PADEL_ANALYSIS_OWN_TEAM_CLUB_SCOPED_MATCH_FIX_2026-09-21 (op verzoek van
Kim, chat 2026-09-21, letterlijk: "fout. je moet de eigen spelers nemen bij
de eigen spelers. niet de tegenstanders!")
--------------------------------------------------------------------------
Tussenstap: kandidaten werden beperkt tot profielen met dezelfde
(genormaliseerde) `club` als sel_player_id, plus een harde uitsluiting van
de huidige tegenstander-roster. Bleek (zie volgende, DEFINITIEVE fix) OOK
niet robuust genoeg: het `club`-veld in player_profiles is NIET voor elke
teamgenoot betrouwbaar ingevuld (enkel bewust toegevoegde/bewerkte
profielen hebben dit consistent). Met een onvolledig ingevuld club-veld
filterde de club-check bijna alle échte teamgenoten weg — vandaar Kim's
melding "nu maar 1 ploeggenoot, geen 4".
--------------------------------------------------------------------------
PADEL_ANALYSIS_SHARED_OPPONENT_TEAMMATE_MATCH_FIX_2026-09-21 (op verzoek
van Kim, chat 2026-09-21: "in de laatste versie vind je nu maar 1
ploeggenoot, geen 4. check dit grondig") — DEFINITIEVE fix
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd): ELKE eerdere poging matchte teamgenoten via een
veld dat NIET betrouwbaar voor alle 4 teamgenoten is ingevuld:
(match_date, encounter)-tekst → verschilt subtiel per apart gescrapete
speler; kalenderdatum alleen → discrimineert niet tussen teams;
`club`-veld → notoir onvolledig ingevuld.
FIX (definitief): _recent_own_lineup_player_ids() matcht teamgenoten nu op
GEDEELDE TEGENSTANDER-IDENTITEIT op dezelfde kalenderdatum — een veld dat
WEL bij elke individuele match aanwezig is (opp1_user_id/opp2_user_id EN,
als extra redundantie, opp1_name/opp2_name):
  1. Bepaal sel_player_id's meest recente interclub-matchdatum, én
     verzamel sel_player_id's EIGEN tegenstander-identiteit voor die datum.
  2. Een kandidaat-profiel hoort bij ONS team op die datum als en slechts
     als het, in zijn/haar EIGEN match op DIEZELFDE datum, minstens 1
     tegenstander-ID (of -naam) DEELT met sel_player_id's tegenstander-set.
Dit vereist GEEN club-veld en GEEN partner_user_id — enkel de
opponent-velden die de scraper per match altijd meeneemt. `exclude_ids`
(huidige tegenstander-roster) blijft bestaan als extra, expliciete
garantie, maar is met deze fix strikt genomen al overbodig.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21 (op verzoek van Kim:
"ik merk nog een probleem in de opstellingen. bij de ploeg van Anneleen
Gallant stel je anneleen op in de 1ste rotatie terwijl zij P100 is en
andere ploeggenoten P200" — en later bevestigd dat de eerdere fix van dit
exacte probleem, PADEL_ANALYSIS_MISSING_RANK_ORDER_FIX_2026-09-19, NOOIT in
dit bestand was aangekomen)
--------------------------------------------------------------------------
ROOT CAUSE (preciezer dan de 2026-09-19-fix begreep): _rotation_order_
variants() berekende `rank_data_incomplete` WEL correct via
_rotation_has_missing_official_rank(), en toonde dus terecht een "❓
onzeker"-label zodra 1 van de 4 spelers een onbekend officieel klassement
had. MAAR: de eigenlijke VOLGORDE (compliant_first/compliant_second) werd
ONGEWIJZIGD nog steeds berekend via _rank_pairs_with_padelstat_tiebreak()
-> _pair_official_sum(), die een ontbrekend klassement nog altijd
stilzwijgend als 0 telt. Als bv. 1 van de 2 P200-speelsters in het ANDERE
duo een tijdelijk ontbrekend officieel klassement had, werd DAT duo's som
ten onrechte (200+0=200) LAGER berekend dan Anneleen's duo (100+200=300) —
en Anneleen's (zwakkere) duo werd NOG STEEDS als "eerste" (rotatie 1)
variant gepresenteerd, enkel met een klein "❓ onzeker"-label erbij dat
makkelijk over het hoofd te zien is.
FIX: wanneer rank_data_incomplete=True, wordt de rotatie nu — net zoals bij
een ECHT gelijkspel — behandeld als "beide volgordes mogelijk, geen van
beide bevestigd": _rotation_order_variants() genereert dan BEIDE
volgordes (huidige en omgekeerde), ELK met is_regulation_compliant=None en
een duidelijk "❓ onzeker, ONVOLLEDIGE data"-label. Zo verschijnt Anneleen's
duo NOOIT meer als de enige, ogenschijnlijk-bevestigde "eerste" optie
zodra data ontbreekt.
Bijkomend, 2 gerelateerde gaten gedicht in dezelfde sessie:
  - _render_rotation_points_caption() (Rotatieplanner) toonde voorheen enkel
    ✅/❌, nooit een ❓ — zelfs als lineup_lab.py's evaluate_rotation() een
    "rank_data_incomplete"-vlag teruggaf. Nu expliciet gecontroleerd en
    getoond.
  - De Sandbox se reglement-check (_render_lineup_sandbox()) gebruikte
    _pair_official_sum() (die NOOIT None teruggeeft, enkel 0 bij een
    ontbrekend klassement) en controleerde vervolgens "if s1 is None or s2
    is None" — een check die dus NOOIT kon afgaan (dode code). Nu gebruikt
    de sandbox _pair_official_sum_safe() om de completeness apart bij te
    houden, zodat de "❓ onbekend"-waarschuwing daadwerkelijk verschijnt.
"""
import itertools
import re
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
    import opponent_scout as osc
except Exception:  # noqa: BLE001  pragma: no cover
    osc = None
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
    with st.expander("🔄 Schema nu verversen", expanded=False):
        st.caption(
            "Start meteen een update van je matchen én het poule-schema op de achtergrond. "
            "Je ziet hieronder live de voortgang; zodra dit klaar is, wordt de 'Volgende "
            "match' hieronder automatisch bijgewerkt — geen page-refresh nodig."
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
# PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26: zie toelichting bij de
# aanroep in _render_volgende_match_and_scout() hieronder.
@st.cache_data(ttl=300, show_spinner=False)
def _cached_own_full_doc(player_id: str):
    try:
        return fb.get_player(player_id)
    except Exception:
        return None


def _render_volgende_match_and_scout(sel_player_id: str, sel_label: str):
    st.markdown('<div class="section-header">📅 Volgende match</div>', unsafe_allow_html=True)
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"
    _render_schema_refresh_button(sel_player_id)
    # PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26: fb.get_player(sel_player_id)
    # haalt het VOLLEDIGE matchdocument van de GESELECTEERDE (eigen) speler op
    # (mogelijk honderden matchrecords), zonder cache, bij ELKE rerun zolang je
    # in het "Analyseren"-tabblad zit. Nu gecacht met dezelfde 5-minuten-TTL-
    # conventie als de rest van dit bestand.
    sel_doc = _cached_own_full_doc(str(sel_player_id))
    own_interclub_matches = [m for m in (sel_doc or {}).get("matches", []) if m.get("match_type") == "interclub"]
    def _finish(fixtures, reeks_url_val):
        own_ploeg_id = _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches)
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
def _own_team_name(fixtures: list, own_ploeg_id: str) -> str:
    """Teamnaam van onze eigen ploeg, afgeleid uit het poule-schema."""
    for fx in fixtures or []:
        if str(fx.get("home_ploeg_id")) == str(own_ploeg_id):
            return fx.get("home_name") or ""
        if str(fx.get("away_ploeg_id")) == str(own_ploeg_id):
            return fx.get("away_name") or ""
    return ""


def _scout_team_all_fixtures(fixtures: list, ploeg_id: str, team_name: str, before_date: str) -> dict:
    """Scout een ploeg over AL hun gespeelde ontmoetingen (niet enkel de
    laatste). Gebruikt dezelfde uitslagenblad-bron als de gewone
    tegenstander-analyse, maar met een onbeperkte lookback.

    Resultaat wordt per (ploeg, datum) in st.session_state gecacht: het
    ophalen doet 1 HTTP-call per ontmoeting met een beleefdheidspauze, dus
    dit mag niet bij elke rerun opnieuw gebeuren.
    """
    if osc is None or not fixtures or not ploeg_id:
        return {}
    # PADEL_ANALYSIS_STALE_SCOUT_CACHE_BUMP_2026-09-25: versie opgehoogd
    # zodat sessies met een oude bundle (van voor opponent_won bestond)
    # niet stil een cache-hit geven zonder dat veld - zie de toelichting
    # in apply_fixture_score_and_perf_fix.py.
    cache_key = f"full_scout_v2_{ploeg_id}_{before_date}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    try:
        played = osc.get_opponent_previous_fixtures(fixtures, str(ploeg_id), before_date, lookback=99)
        n = len(played)
        if not n:
            st.session_state[cache_key] = {}
            return {}
        bundle = osc.scout_opponent(
            fixtures, team_name, str(ploeg_id), before_date,
            lookback=n, min_players=0, max_lookback=n,
        )
    except Exception:
        bundle = {}
    st.session_state[cache_key] = bundle
    return bundle


def _recent_own_lineup_roster(fixtures: list, own_ploeg_id: str) -> dict:
    """Wie speelde er in ONZE vorige interclubontmoeting?

    Leest dit rechtstreeks uit het uitslagenblad van die ontmoeting, via
    dezelfde functie die de tegenstander-opstelling al ophaalt
    (opponent_scout.scout_opponent) - maar met ONS eigen ploeg_id. Dat is
    exact de ploegkolom uit het matchdetail: alle spelers van de ploeg,
    ongeacht of hun eigen profiel al gescrapet is, hun club-veld ingevuld
    is, of hun partner_user_id correct opgelost raakte.

    Alle eerdere methodes (partner_user_id, encounter-tekst, kalenderdatum,
    club-veld, gedeelde tegenstander-identiteit) leidden de ploeg INDIRECT
    af uit losse, per speler apart gescrapete matchrecords - precies de
    reden dat er telkens 1 of 3 spelers uitkwamen in plaats van 4.

    Geeft {player_id: naam} terug; leeg bij een onbekende ploeg/fout.
    """
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
        own_bundle = osc.scout_opponent(
            fixtures, _own_team_name(fixtures, own_ploeg_id),
            str(own_ploeg_id), before_date, lookback=1,
        )
        roster = {
            str(p["user_id"]): (p.get("name") or str(p["user_id"]))
            for p in (own_bundle.get("unique_players") or []) if p.get("user_id")
        }
    except Exception:
        roster = {}
    st.session_state[cache_key] = roster
    return roster


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_UI_SPEED_CACHE_2026-09-24 (op verzoek van Kim: "een apart
# topic is snelheid van gebruik voor de user. Bij elke knop moet je lang
# wachten voor je iets ziet wat vervelend is. Hoe kan dit versneld worden")
# ─────────────────────────────────────────────
# ROOT CAUSE van de traagheid: Streamlit voert bij ELKE interactie (elke
# knop, checkbox, selectbox) het VOLLEDIGE script opnieuw uit. Elke
# oa.get_own_player_rating() en _official_current_rank() doet daarbij 2-3
# APARTE Firestore-reads per speler. Met ~10 eigen spelers + ~8
# tegenstanders zijn dat 50+ netwerkrondjes per klik - dat is exact de
# wachttijd die Kim ervaart, en ze staat volledig los van de eigenlijke
# berekening.
#
# FIX: beide lookups gaan door een st.cache_data-laag met een TTL van 5
# minuten. Binnen dezelfde sessie wordt een speler dus hoogstens 1x per 5
# minuten opgehaald i.p.v. bij elke rerun. De TTL is bewust kort genoeg dat
# een verse scrape vanzelf doorkomt; wie niet wil wachten gebruikt de
# bestaande "Verversen"-knoppen (die roepen al invalidate_all() aan).
@st.cache_data(ttl=300, show_spinner=False)
def _cached_own_player_rating(player_id: str):
    """Gecachete padelstat/playing-strength-lookup (zie toelichting hierboven)."""
    try:
        return oa.get_own_player_rating(str(player_id))[0]
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _cached_official_rank(player_id: str):
    """Gecachet officieel klassement (padelstat-snapshot, dan TVL-historiek)."""
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


# PADEL_ANALYSIS_UI_SPEED_CACHE_PHASE2_2026-09-25 (op verzoek van Kim: "toch
# nog altijd traag om mee te werken"): de vorige caching-ronde (2026-09-24)
# raakte enkel de padelstat/klassement-lookups per speler, maar liet de
# ZWAARSTE aanroep op deze pagina ONGEMOEID: ll.get_docs_for_players(
# available_ids) in _render_opstelling_scenario() haalt het VOLLEDIGE
# matchdocument (elk met tot honderden matchrecords) op voor ELKE eigen
# speler - en dat gebeurt bij ELKE widget-interactie op deze pagina (elke
# number_input voor max_per_player, elke checkbox, elke selectbox-wijziging
# stuurt Streamlit een volledige script-rerun). Bij 4-8 eigen spelers is dat
# 4-8 volledige Firestore-documentreads per klik - de dominante resterende
# bron van traagheid, los van de reeds gecachete rating-lookups.
@st.cache_data(ttl=300, show_spinner=False)
def _cached_docs_for_players(player_ids: tuple) -> dict:
    """Gecachete variant van ll.get_docs_for_players(). Sleutel is de
    (gesorteerde) tuple van speler-ID's, zodat een gewijzigde selectie wel
    meteen een verse ophaling triggert, maar dezelfde selectie binnen de
    TTL nooit twee keer wordt opgehaald."""
    try:
        return ll.get_docs_for_players(list(player_ids))
    except Exception:
        return {}


def _clear_rank_caches() -> None:
    """Leegt de lookup-caches hierboven (gebruikt door de ververs-knoppen)."""
    try:
        _cached_own_player_rating.clear()
        _cached_official_rank.clear()
        _cached_docs_for_players.clear()
    except Exception:
        pass


def _merge_full_opponent_roster(bundle: dict, fixtures: list, opp: dict) -> dict:
    """Vult bundle["unique_players"] aan met spelers uit ALLE eerdere
    ontmoetingen van deze tegenploeg.

    PADEL_ANALYSIS_FULL_ROSTER_IN_OVERVIEW_2026-09-24 (op verzoek van Kim:
    "Bij TP Rumbeke zie ik 4 spelers bij analyse maar ik zie bij
    tegenstander match 1 match 2 een extra speler. Carrein Elke. die zou
    dan toch ook in eerste overzicht moeten getoond worden")
    ----------------------------------------------------------------------
    ROOT CAUSE: render_scout_header() bouwt de bundle op met lookback=1 -
    dus met de roster van UITSLUITEND de laatste ontmoeting. De
    match1/match2-frequentietabel gebruikt sinds
    PADEL_ANALYSIS_FREQUENCY_ALL_FIXTURES_2026-09-22 wel de VOLLEDIGE
    historiek (_scout_team_all_fixtures). Een speelster die enkel in een
    EERDERE ontmoeting speelde - zoals Carrein Elke - verscheen daardoor
    wel in de frequentietabel maar niet in de overzichtstabel, de
    theoretische scenario's of de sandbox.

    FIX: de spelers uit de volledige scout worden hier bij de bundle
    gevoegd, ontdubbeld op user_id. Dit gebeurt VOOR het team-rapport
    opgebouwd wordt, zodat de overzichtstabel, de scenario-roster en de
    sandbox allemaal dezelfde, volledige ploeg zien.
    """
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
        # PADEL_ANALYSIS_ROSTER_CONFIDENCE_LABEL_2026-09-25: opponent_scout.
        # scout_opponent() berekent sinds PADEL_ANALYSIS_TEAM_ROSTER_TOO_
        # SMALL_FIX_2026-09-20 al "appearances" (in hoeveel doorzochte
        # ontmoetingen deze speler voorkwam) en "known_matches_total" per
        # speler, expliciet bedoeld als vertrouwensindicator - maar dat werd
        # tot nu toe nergens in de UI getoond: de indicator bestond wel in
        # de data maar was voor Kim onzichtbaar. Voor spelers die HIER (via
        # de bredere, volledige-seizoen-scout) toegevoegd worden is dat
        # net extra relevant: een speler met appearances=1 en known_
        # matches_total=0 is een eenmalige waarneming zonder verdere
        # bevestiging, iets anders dan een vaste basisspeler. Dat verschil
        # wordt hier als apart veld op de bundle gezet i.p.v. stilzwijgend
        # te laten liggen; page_lineup_lab() toont dit als caption.
        onzeker = [
            p.get("name", "?") for p in toegevoegd
            if (p.get("appearances") or 0) <= 1 and not p.get("known_matches_total")
        ]
        bundle["_roster_extended_with"] = [p.get("name", "?") for p in toegevoegd]
        bundle["_roster_extended_low_confidence"] = onzeker
    return bundle


def _current_official_rank_prefer_padelstat(player_id: str):
    """Actueel officieel klassement: eerst de padelstat-snapshot van de
    recentste refresh, daarna pas de tragere TVL-historiek als fallback.

    PADEL_ANALYSIS_UI_SPEED_CACHE_2026-09-24: gaat nu door _cached_official_
    rank() - zie de toelichting daar voor waarom dit de belangrijkste
    snelheidswinst is."""
    return _cached_official_rank(str(player_id))


def _opponent_padelstat_ratings(bundle: dict) -> dict:
    """SIMULATIE-schaal (padelstat) voor tegenstander-spelers."""
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
    """REGLEMENT-schaal (uitsluitend officieel klassement) voor tegenstander-
    spelers. Geen padelstat-fallback."""
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
    """PADEL_ANALYSIS_SIMULATION_VS_REGULATION_SCALE_SPLIT_2026-09-17: bouwt
    het REGLEMENT-dict voor ONZE spelers, UITSLUITEND op basis van het echte
    officiële klassement — GEEN fallback naar padelstat meer."""
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
# PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26 (op verzoek van Kim: "ik heb
# nu al 3 fixes gedaan voor snelheid [...] graag alles ineens"):
# doet 1 Firestore-read (get_player_profile), zonder cache. Aangeroepen
# vanuit _render_tournament_rules_selector(), die ONVOORWAARDELIJK
# aangeroepen wordt in _render_opstelling_scenario() - dus bij elke rerun.
# Kleiner in omvang dan de tegenstander-roster-vondsten, maar even
# structureel: elke klik op de pagina deed deze read opnieuw.
@st.cache_data(ttl=300, show_spinner=False)
def _load_saved_rules_selection(sel_player_id: str, ploeg_id: str) -> dict:
    try:
        profile = fb.get_player_profile(sel_player_id) or {}
    except Exception:
        profile = {}
    by_team = profile.get("lineup_rules_selection_by_team") or {}
    if str(ploeg_id) in by_team:
        return by_team.get(str(ploeg_id)) or {}
    return profile.get("lineup_rules_selection") or {}
def _save_rules_selection(sel_player_id: str, ploeg_id: str, tournament: str, category: str, afdeling) -> None:
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(sel_player_id)).set(
            {"lineup_rules_selection_by_team": {
                str(ploeg_id): {"tournament": tournament, "category": category, "afdeling": afdeling},
            }},
            merge=True,
        )
    except Exception:
        pass
def _render_tournament_rules_selector(ploeg_id: str, sel_player_id: str, available_official_ranks: list = None):
    if tr is None:
        st.caption("⚠️ tournament_rules.py niet gevonden — reglement-gebaseerde puntenfilter niet beschikbaar.")
        return None, None
    saved = _load_saved_rules_selection(sel_player_id, ploeg_id)
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
        suggested_afdeling, suggestion_exact = (None, False)
        if available_official_ranks:
            suggested_afdeling, suggestion_exact = tr.suggest_afdeling(tournament, category, available_official_ranks)
        def _afdeling_label(a):
            base = tr.format_afdeling_label(tournament, category, a)
            if a == suggested_afdeling:
                tag = "aanbevolen o.b.v. team" if suggestion_exact else "dichtste match o.b.v. team, niet perfect"
                base += f"  ⭐ ({tag})"
            return base
        default_afdeling = saved.get("afdeling") if saved.get("afdeling") in afdelingen else None
        if default_afdeling is None and suggested_afdeling in afdelingen:
            default_afdeling = suggested_afdeling
        default_afd_idx = afdelingen.index(default_afdeling) if default_afdeling in afdelingen else 0
        afdeling = st.selectbox(
            "Afdeling", afdelingen, index=default_afd_idx, key=f"rules_afdeling_{ploeg_id}",
            format_func=_afdeling_label,
            help="⭐ = automatisch voorgesteld op basis van het officiële klassement van de geselecteerde "
                 "eigen spelers — je kan dit hieronder altijd manueel overschrijven.",
        )
        rules = tr.get_afdeling_rules(tournament, category, afdeling)
        st.caption(tr.format_rules_caption(tournament, category, afdeling, rules))
        if suggested_afdeling is not None and afdeling != suggested_afdeling:
            st.caption(
                f"ℹ️ Let op: dit wijkt af van de automatische suggestie (afdeling {suggested_afdeling} "
                f"o.b.v. de geselecteerde spelers). Dat kan bewust zijn (ploeg speelt in een andere "
                "afdeling dan het klassement zou suggereren)."
            )
        elif suggested_afdeling is not None and not suggestion_exact:
            st.warning(
                f"⚠️ Geen enkele afdeling dekt het officiële klassement van ALLE geselecteerde spelers "
                f"perfect — afdeling {suggested_afdeling} is de dichtste benadering. Controleer de "
                "teamsamenstelling of kies manueel een andere afdeling."
            )
        with st.expander("📋 Volledige reglementstabel (alle afdelingen)", expanded=False):
            st.markdown(tr.format_full_rules_table_markdown(tournament, category))
        if saved.get("tournament") != tournament or saved.get("category") != category or saved.get("afdeling") != afdeling:
            _save_rules_selection(sel_player_id, ploeg_id, tournament, category, afdeling)
        return rules, f"{tournament} — {category}, afdeling {afdeling}"
# ─────────────────────────────────────────────
# Tegenstander-referentie
# ─────────────────────────────────────────────
def _rank_text_for_opponent(player: dict) -> str:
    """Officieel klassement + padelstat playing strength van 1 tegenstander-
    speler, als korte tekst.

    PADEL_ANALYSIS_OPPONENT_RANKS_IN_MATCH_TABLE_2026-09-24 (op verzoek van
    Kim: "Bij tegenstander match 1 en match 2 mag je ook nog eens klassement
    vermelden. toch plaats genoeg. Zowel officieel als padelstat
    klassement"). Het 'ranking'-veld op het bord is het officiele klassement
    zoals het op het uitslagenblad stond; is dat leeg, dan wordt het
    gecachete officiele klassement gebruikt. De padelstat-waarde komt uit
    dezelfde gecachete lookup als de rest van de simulatie."""
    uid = str(player.get("user_id") or "")
    officieel = player.get("ranking")
    if not officieel and uid:
        rank = _cached_official_rank(uid)
        if rank is not None:
            officieel = f"P{int(rank)}"
    padelstat = _cached_own_player_rating(uid) if uid else None
    delen = [str(officieel) if officieel else "P?"]
    if padelstat is not None:
        delen.append(f"ps P{int(padelstat)}")
    return " / ".join(delen)


def _fixture_rows(
    boards: list, home_team: str = None, away_team: str = None,
    is_opponent_home: bool = None,
) -> list:
    """Zet de dubbels van 1 ontmoeting om naar tabelrijen, MET klassement.

    PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26 (op verzoek van Kim: "Bij
    winnaar toon je de naam van de spelers bij de eerdere ontmoetingen. De
    ploegnaam is daar beter"):
    ----------------------------------------------------------------------
    Elke rij toont al "Speler 1"/"Speler 2" apart - een DERDE keer namen
    tonen in de kolom "Winnaar" voegt weinig toe. De ploegnaam maakt in 1
    oogopslag duidelijk WELKE ploeg dat bord won, zonder de namen in de 2
    kolommen ernaast te moeten herkennen.

    FIX: is home_team/away_team/is_opponent_home meegegeven (zie
    _fixture_final_score(), die dit nu berekent), dan toont "Winnaar" de
    PLOEGNAAM. Ontbreekt die info (bv. een ouder uitslagenblad zonder
    team-samenvatting), dan valt dit terug op de spelersnamen - het
    bestaande, werkende gedrag blijft dus als vangnet intact."""
    heeft_teaminfo = (
        home_team is not None and away_team is not None and is_opponent_home is not None
    )
    rows = []
    for b in sorted(boards, key=lambda x: x.get("board_position") or 0):
        pair = b.get("opponent_pair") or []
        if len(pair) != 2:
            continue
        pos = b.get("board_position")
        rot = (int(pos) + 1) // 2 if pos else "?"
        m_in_rot = 1 if (pos and int(pos) % 2 == 1) else 2
        opponent_won = b.get("opponent_won")
        other_pair = b.get("other_pair") or []

        winnaar_namen = "Onbekend"
        if opponent_won is True:
            if heeft_teaminfo:
                winnaar_namen = home_team if is_opponent_home else away_team
            else:
                winnaar_namen = " / ".join(p.get("name", "?") for p in pair)
        elif opponent_won is False:
            if heeft_teaminfo:
                winnaar_namen = away_team if is_opponent_home else home_team
            elif len(other_pair) == 2:
                winnaar_namen = " / ".join(p.get("name", "?") for p in other_pair)

        rows.append({
            "Match": f"Rotatie {rot} — Match {m_in_rot}" if pos else "Match ?",
            "Speler 1": pair[0].get("name", "?"),
            "Klassement 1": _rank_text_for_opponent(pair[0]),
            "Speler 2": pair[1].get("name", "?"),
            "Klassement 2": _rank_text_for_opponent(pair[1]),
            "Score": b.get("score") or "onbekend",
            "Winnaar": winnaar_namen,
            "_opponent_won": opponent_won,  # intern: bepaalt de rijkleur, niet getoond
        })
    return rows


def _render_fixture_rows_table(rows: list) -> None:
    """PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25: toont
    _fixture_rows()-resultaat met een groene rij zodra de GESCOUTE ploeg
    (onze eerstvolgende tegenstander) dat bord won, en een lichte rode tint
    wanneer zij het verloren. "Onbekend" (geen leesbare score) blijft
    ongekleurd. Faalt de styling (bv. een oudere pandas/Streamlit-versie),
    dan valt dit terug op de gewone, ongekleurde tabel - nooit een crash
    voor een puur cosmetische toevoeging."""
    if not rows:
        st.info("Geen bruikbare dubbels in deze ontmoeting.")
        return
    zichtbare_kolommen = [k for k in rows[0].keys() if not k.startswith("_")]
    try:
        import pandas as _pd

        def _kleur_resultaat(row):
            if row.get("_opponent_won") is True:
                return ["background-color: #d4edda"] * len(row)
            if row.get("_opponent_won") is False:
                return ["background-color: #f8d7da"] * len(row)
            return [""] * len(row)

        df = _pd.DataFrame(rows)
        styled = df.style.apply(_kleur_resultaat, axis=1)
        st.dataframe(
            styled, use_container_width=True, hide_index=True,
            column_order=zichtbare_kolommen,
        )
        st.caption(
            "\U0001F7E2 Groen = de GESCOUTE ploeg (onze eerstvolgende tegenstander) won dit bord - "
            "een gevaarlijk koppel om rekening mee te houden. \U0001F534 Rood = zij verloren dit bord."
        )
    except Exception:
        st.dataframe(
            [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
            use_container_width=True, hide_index=True,
        )


def _parse_set_score(score_text: str):
    """Ontleedt 1 bordscore (bv. '6-3 6-2' of '6/4 3/6 10/7') tot
    (sets_links, sets_rechts). Geeft None terug als de tekst niet als
    setscore te lezen valt - dan wordt dit bord overgeslagen i.p.v. een
    verzonnen winnaar te tonen.

    PADEL_ANALYSIS_FIXTURE_FINAL_SCORE_2026-09-25: gebruikt om de eindstand
    van een volledige ontmoeting af te leiden (zie _fixture_final_score()).
    Aanname: de 2 cijfers per set staan in dezelfde volgorde als de 2
    spelers in "opponent_pair" (links = die kolom, rechts = de andere
    ploeg) - dit is de gebruikelijke notatie op een uitslagenblad. Klopt
    die aanname een keer niet, dan draait enkel de eindscore van die ene
    ontmoeting om; het cijfer per bord (kolom "Score" hierboven) blijft
    hoe dan ook de originele, onbewerkte tekst tonen ter controle.
    """
    if not score_text:
        return None
    sets_links = sets_rechts = 0
    gevonden = False
    for token in re.split(r"[\s,]+", str(score_text).strip()):
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", token)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a == b:
            continue  # onbeslist/onleesbaar, telt niet mee als setwinst
        gevonden = True
        if a > b:
            sets_links += 1
        else:
            sets_rechts += 1
    if not gevonden:
        return None
    return sets_links, sets_rechts


def _fixture_final_score(
    fx: dict, boards: list, scouted_team_name: str, opponent_ploeg_id: str = None,
    fixture_bundle: dict = None,
):
    """Eindscore van 1 volledige ontmoeting: matchen/sets/spellen + winnaar.

    PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26 (op verzoek van Kim: "Bij
    winnaar toon je de naam van de spelers bij de eerdere ontmoetingen. De
    ploegnaam is daar beter"):
    ----------------------------------------------------------------------
    Geeft nu ook "is_scouted_home" mee terug: was de GESCOUTE tegenstander
    (scouted_team_name/opponent_ploeg_id) in DEZE historische ontmoeting de
    THUIS- of UITploeg? Die berekening bestond al intern in deze functie
    (nodig voor de bordentelling-terugval), maar werd nooit doorgegeven -
    _fixture_rows() kon daardoor de ploegnaam van de winnaar per bord niet
    tonen en viel terug op spelersnamen.

    Geeft een dict terug: {"home_name", "away_name", "matches", "sets",
    "games", "winner", "is_scouted_home"}.
    """
    fixture_bundle = fixture_bundle or {}
    home_name = fixture_bundle.get("home_team") or fx.get("home_name") or ""
    away_name = fixture_bundle.get("away_team") or fx.get("away_name") or ""
    winner = fixture_bundle.get("winner_team")

    matches_pair = fixture_bundle.get("team_score_matches")
    sets_pair = fixture_bundle.get("team_score_sets")
    games_pair = fixture_bundle.get("team_score_games")

    is_scouted_home = None
    if opponent_ploeg_id is not None:
        if str(fx.get("home_ploeg_id")) == str(opponent_ploeg_id):
            is_scouted_home = True
        elif str(fx.get("away_ploeg_id")) == str(opponent_ploeg_id):
            is_scouted_home = False
    if is_scouted_home is None and scouted_team_name and home_name:
        is_scouted_home = bool(
            _clean_name(scouted_team_name) in _clean_name(home_name)
            or _clean_name(home_name) in _clean_name(scouted_team_name)
        )

    if matches_pair is None:
        # Terugval (oud gedrag): tellen via de borden - enkel het aantal
        # gewonnen matchen is dan beschikbaar, geen sets/spellen.
        scouted_wins = sum(1 for b in boards if b.get("opponent_won") is True)
        other_wins = sum(1 for b in boards if b.get("opponent_won") is False)
        known = scouted_wins + other_wins
        if known == 0:
            return None
        matches_pair = (
            (scouted_wins, other_wins) if is_scouted_home else (other_wins, scouted_wins)
        )
        if not winner:
            if matches_pair[0] > matches_pair[1]:
                winner = home_name or None
            elif matches_pair[1] > matches_pair[0]:
                winner = away_name or None

    return {
        "home_name": home_name,
        "away_name": away_name,
        "matches": matches_pair,
        "sets": sets_pair,
        "games": games_pair,
        "winner": winner,
        "is_scouted_home": is_scouted_home,
    }


def _render_previous_opponent_lineup(bundle: dict, opp: dict = None, full_bundle: dict = None) -> None:
    """Eerdere ontmoetingen van de tegenstander, kiesbaar via dropdown.

    PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25 (op verzoek van
    Kim: "totaal resultaat met games en sets en totale score wordt ook niet
    getoond [...] Gewonnen ploeg kan je groen zetten ook"):
    toont nu het volledige lange formaat - Matchen X-Y, Sets X-Y, Spellen
    X-Y - plus de winnaar-naam apart, in het groen. Zie
    _fixture_final_score() voor waar deze cijfers nu vandaan komen
    (rechtstreeks van de pagina, niet langer afgeleid uit bordentelling).
    """
    source = full_bundle if (full_bundle or {}).get("previous_fixtures") else bundle
    previous_fixtures = (source or {}).get("previous_fixtures") or []
    if not previous_fixtures:
        return
    bruikbaar = []
    for fx_bundle in previous_fixtures:
        if fx_bundle.get("error") or not (fx_bundle.get("boards") or []):
            continue
        bruikbaar.append(fx_bundle)
    titel = f"\U0001F4CB Tegenstander \u2014 eerdere ontmoeting(en) ter referentie ({len(bruikbaar)})"
    with st.expander(titel, expanded=False):
        st.caption(
            "De opstelling die de TEGENSTANDER gebruikte in hun al gespeelde wedstrijden dit "
            "seizoen, met per speler het officiele klassement en (waar gekend) de padelstat "
            "playing strength. 'Rotatie X \u2014 Match Y' volgt de volgorde op het uitslagenblad."
        )
        if not bruikbaar:
            st.info("Geen match-detail beschikbaar voor de gekende eerdere ontmoeting(en).")
            return
        scouted_name = (opp or {}).get("name") or ""
        opponent_ploeg_id = (opp or {}).get("ploeg_id")
        labels = []
        scores = []
        for fx_bundle in bruikbaar:
            fx = fx_bundle.get("fixture", {}) or {}
            datum = fx.get("date_text", "?")
            tegen = fx_bundle.get("home_team") or fx.get("home_name") or ""
            uit = fx_bundle.get("away_team") or fx.get("away_name") or ""
            wedstrijd = f" ({tegen} vs {uit})" if tegen and uit else ""
            labels.append(f"{datum}{wedstrijd}")
            score = _fixture_final_score(
                fx, fx_bundle.get("boards") or [], scouted_name,
                opponent_ploeg_id=opponent_ploeg_id, fixture_bundle=fx_bundle,
            )
            scores.append(score)
        if len(bruikbaar) > 1:
            def _label_met_eindscore(i):
                s = scores[i]
                if not s or not s.get("matches"):
                    return labels[i]
                m = s["matches"]
                return f"{labels[i]} \u2014 {m[0]}-{m[1]}"
            keuze = st.selectbox(
                "Welke ontmoeting wil je bekijken?", list(range(len(bruikbaar))),
                format_func=_label_met_eindscore, index=len(bruikbaar) - 1,
                key=f"prev_fixture_pick_{id(source)}",
            )
        else:
            keuze = 0
            m = (scores[0] or {}).get("matches")
            titel_txt = f"**{labels[0]}**"
            if m:
                titel_txt += f" \u2014 **{m[0]}-{m[1]}**"
            st.caption(f"Enige gekende ontmoeting: {titel_txt}")
        score = scores[keuze]
        if score and score.get("matches"):
            home, away = score["home_name"] or "?", score["away_name"] or "?"
            m = score["matches"]
            delen = [f"Matchen: {m[0]}-{m[1]}"]
            if score.get("sets"):
                s = score["sets"]
                delen.append(f"Sets: {s[0]}-{s[1]}")
            if score.get("games"):
                g = score["games"]
                delen.append(f"Spellen: {g[0]}-{g[1]}")
            st.markdown(f"**Eindscore: {home} - {away}**")
            st.markdown(" \u00b7 ".join(delen))
            if score.get("winner"):
                st.success(f"\U0001F7E2 Winnaar: **{score['winner']}**")
            st.caption(
                "Rechtstreeks van de 'Samenvatting'-sectie van het uitslagenblad - niet afgeleid "
                "uit de bordresultaten hieronder."
            )
        # PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26: ploegnaam i.p.v.
        # spelersnamen in de kolom "Winnaar" - zie _fixture_rows().
        rows = _fixture_rows(
            bruikbaar[keuze].get("boards") or [],
            home_team=(score or {}).get("home_name"),
            away_team=(score or {}).get("away_name"),
            is_opponent_home=(score or {}).get("is_scouted_home"),
        )
        _render_fixture_rows_table(rows)


def _render_match1_frequency_opponent(bundle: dict, full_bundle: dict = None) -> None:
    """Match 1 / Match 2-frequentie per tegenstander-speler.

    PADEL_ANALYSIS_FREQUENCY_ALL_FIXTURES_2026-09-22 (op verzoek van Kim:
    "je rekent maar 1 match mee om te bekijken hoeveel keer iemand match 1
    en match 2 gespeeld heeft. je moet alle matchen meenemen"):
    ROOT CAUSE: deze functie las `bundle["previous_fixtures"]`, en die
    bundle wordt door render_scout_header() opgebouwd met lookback=1 (enkel
    de laatste ontmoeting; scout_opponent() breidt dat enkel uit zolang de
    ROSTER te klein is, niet om statistiek op te bouwen). Alle ontmoetingen
    daarvoor werden dus nooit geteld.
    FIX: er wordt nu een APARTE bundle over ALLE gespeelde ontmoetingen
    meegegeven (`full_bundle`, zie _scout_team_all_fixtures()); valt terug
    op de oorspronkelijke bundle als die niet beschikbaar is.
    """
    source = full_bundle if (full_bundle or {}).get("previous_fixtures") else bundle
    previous_fixtures = (source or {}).get("previous_fixtures") or []
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
    n_fixtures = len(previous_fixtures)
    n_boards = len(boards_met_positie)
    with st.expander(
        f"\U0001F4CA Tegenstander \u2014 match 1 / match 2-frequentie per rotatie "
        f"(over {n_fixtures} ontmoeting(en), {n_boards} dubbel(s))",
        expanded=False,
    ):
        st.caption(
            "Hoe vaak elke tegenstander-speler de EERSTE match van een rotatie speelde (Match 1, "
            "Match 3, ...) versus de TWEEDE match van een rotatie (Match 2, Match 4, ...), over "
            "ALLE gekende, al gespeelde ontmoetingen van deze ploeg dit seizoen. Puur "
            "beschrijvend \u2014 geen voorspelling."
        )
        if n_fixtures <= 1:
            st.caption(
                "\u26A0\uFE0F Slechts 1 ontmoeting gekend \u2014 gebaseerd op \u00e9\u00e9n enkel datapunt. Meer "
                "ontmoetingen verschijnen hier automatisch zodra deze ploeg er gespeeld heeft."
            )
        rows = []
        for uid, counts in sorted(tellingen.items(), key=lambda kv: -kv[1]["match1"]):
            totaal = counts["match1"] + counts["match2"]
            pct1 = round(100 * counts["match1"] / totaal, 0) if totaal else 0
            pct2 = round(100 * counts["match2"] / totaal, 0) if totaal else 0
            # PADEL_ANALYSIS_OPPONENT_RANKS_IN_MATCH_TABLE_2026-09-24 (op
            # verzoek van Kim: "Bij tegenstander match 1 en match 2 mag je
            # ook nog eens klassement vermelden [...] Zowel officieel als
            # padelstat klassement"): zonder deze cijfers moest je de
            # sterkte van een tegenstander elders opzoeken om te kunnen
            # inschatten waarom ze op match 1 of match 2 stonden.
            officieel = _cached_official_rank(str(uid))
            padelstat = _cached_own_player_rating(str(uid))
            rows.append({
                "Speler": namen.get(uid, uid),
                "Officieel": f"P{int(officieel)}" if officieel is not None else "?",
                "Padelstat": f"P{int(padelstat)}" if padelstat is not None else "-",
                "Match 1 (of 3, 5, ...)": f"{counts['match1']}x ({int(pct1)}%)",
                "Match 2 (of 4, 6, ...)": f"{counts['match2']}x ({int(pct2)}%)",
                "Totaal dubbels": totaal,
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


def _expand_tied_orderings(
    results: list, official_ranks_strict: dict, padelstat_ratings: dict,
    tournament_rules_dict, excluded_pairs: set,
    opponent_boards=None, synergy_fn=None, player_ratings: dict = None,
    opponent_ratings: dict = None,
) -> tuple:
    """PADEL_ANALYSIS_ROTATION_TIE_VARIANTS_2026-09-25 (op verzoek van Kim:
    "Ik enerzijds bij mijn ploeg [...] maar de combinatie Stijn Kim in M1
    staat er niet bij. Ik kan volgens mij 5 combinaties van ploeg opstelling
    maken in eerste rotatie [...] deze ontbreken: M1: Kim Verbeke/Stijn
    Mortier | M2: Carl Ide/Nico Recour en M1: Kim Verbeke/Carl Ide | M2:
    Stijn Mortier/Nico Recour")
    ----------------------------------------------------------------------
    ROOT CAUSE (bevestigd, geen gok): met 4 spelers bestaan er wiskundig
    exact 3 PARTITIES (_count_perfect_matchings(4) == 3) - en Kim's 2
    "ontbrekende" combinaties zijn GEEN nieuwe partities, maar de reeds
    getoonde partities #1 en #2 met M1 en M2 verwisseld (bv. haar 1e
    combinatie was al {Carl,Nico}/{Stijn,Kim}; de "ontbrekende" is
    dezelfde 2 koppels, enkel {Stijn,Kim} nu op M1 i.p.v. M2). Bij een
    EXACT gelijk officieel klassement (of onbekende rankdata) is dat
    OMDRAAIEN reglementair evenzeer toegelaten (art. 6.6 laat de ploeg dan
    zelf kiezen) - _rotation_order_variants() past die regel al correct
    toe in de volledige matchup-tabel (_render_all_valid_matchups), maar
    deze functie (de Rotatieplanner) vertrouwde tot nu toe rechtstreeks op
    lineup_lab.optimize_lineup()/optimize_lineup_vs_scenario(), die per
    partitie maar EEN vaste M1/M2-volgorde teruggeeft. Met top_n gelijk aan
    het aantal PARTITIES (3) was er dus structureel geen ruimte voor de
    omgewisselde varianten, los van of ze al dan niet intern berekend
    werden.

    FIX: voor elke kandidaat wordt hier, per rotatie (elk paar van 2
    borden), gecontroleerd of BEIDE volgordes reglementair toegelaten zijn
    (via _rotation_order_variants() - exact dezelfde functie/regel als de
    matchup-tabel). Is dat zo, dan wordt de omgewisselde variant ALS APARTE
    KANDIDAAT toegevoegd. Is er een opponent_boards-scenario gekozen, dan
    wordt de winkans van de nieuwe volgorde opnieuw berekend via
    _compute_matchup() (die andere posities => andere tegenstander per
    match => een ANDERE winkans, dus dit mag nooit de oude waarde
    hergebruiken). Zonder scenario blijft de synergie-score ongewijzigd
    (synergie hangt af van WIE met wie speelt, niet van de bordvolgorde).
    """
    expanded = []
    seen_keys = set()
    for cand in results:
        pairs = list(cand["ordered_pairs"])
        n_rot = -(-len(pairs) // 2)
        variant_choices = []
        for r in range(n_rot):
            chunk = pairs[r * 2: r * 2 + 2]
            if len(chunk) < 2:
                variant_choices.append([tuple(chunk)])
                continue
            duo_a, duo_b = chunk[0], chunk[1]
            vr = _rotation_order_variants(duo_a, duo_b, official_ranks_strict, padelstat_ratings, rules=tournament_rules_dict)
            opts = [tuple(v["ordered_pairs"]) for v in vr["variants"] if v["is_regulation_compliant"] is not False]
            variant_choices.append(opts or [(duo_a, duo_b)])
        for combo in itertools.product(*variant_choices):
            new_pairs = [p for chunk in combo for p in chunk]
            if any(p in excluded_pairs for p in new_pairs):
                continue
            key = tuple(frozenset(p) for p in new_pairs)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if new_pairs == pairs:
                expanded.append(cand)
                continue
            if opponent_boards and player_ratings is not None and synergy_fn is not None:
                computed = _compute_matchup(
                    new_pairs, opponent_boards, synergy_fn, player_ratings,
                    official_ranks_strict, opponent_ratings or {},
                )
                expanded.append({
                    "expected_boards_won": computed["expected_boards_won"],
                    "score": computed["total_score"],
                    "ordered_pairs": new_pairs,
                    "assignment": computed["assignment"],
                    "rotations": cand.get("rotations"),
                })
            else:
                rotation_eval = ll.filter_and_order_lineup_by_rotations(
                    [frozenset(p) for p in new_pairs], official_ranks_strict, rules=tournament_rules_dict,
                )
                if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
                    continue
                expanded.append({
                    "expected_boards_won": None,
                    "score": cand["score"],
                    "ordered_pairs": rotation_eval["ordered_pairs"],
                    "assignment": None,
                    "rotations": rotation_eval["rotations"],
                })
    return expanded


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
    # PADEL_ANALYSIS_ROTATION_TIE_VARIANTS_2026-09-25: zie
    # _expand_tied_orderings() hierboven - voegt de reglementair evenzeer
    # toegelaten, omgewisselde M1/M2-varianten toe bij een gelijk (of
    # onbekend) officieel klassement, wat top_n hierboven (op aantal
    # PARTITIES, niet aantal ordeningen) structureel afsneed.
    padelstat_for_tiebreak = player_ratings or {}
    results = _expand_tied_orderings(
        results, official_ranks_strict, padelstat_for_tiebreak, tournament_rules_dict,
        excluded_pairs, opponent_boards=opponent_boards, synergy_fn=synergy_fn,
        player_ratings=player_ratings, opponent_ratings=opponent_ratings,
    )
    if len(results) > total_possible:
        total_possible = len(results)
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
        # PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21: de
        # Rotatieplanner gebruikt lineup_lab.py's evaluate_rotation(), die een
        # "rank_data_incomplete"-vlag kan teruggeven — dit moet HIER expliciet
        # als ❓ getoond worden, niet stilzwijgend als ✅/❌ behandeld worden,
        # exact dezelfde reden als bij de Opstelling-scenario's-tabel
        # (Anneleen-bug).
        if rot.get("rank_data_incomplete"):
            st.caption(f"❓ Rotatie {i}: {rot.get('reason', '')} — ⚠️ minstens 1 speler heeft nog geen bekend officieel klassement, deze volgorde is NIET betrouwbaar geverifieerd.")
            continue
        icon = "✅" if rot.get("valid", True) else "❌"
        st.caption(f"{icon} Rotatie {i}: {rot.get('reason', '')}")
# PADEL_ANALYSIS_WINPROB_CALIBRATION_2026-09-22: de vorige tekst stelde dat
# de winkans "GEEN gevalideerd of empirisch getoetst" model was. Dat klopt
# sinds de kalibratie met validate_winprob.py niet meer letterlijk, maar de
# steekproef (44 matchen) is te klein om van een gevalideerd model te
# spreken. De tekst vermeldt nu wat er effectief gemeten is, inclusief de
# beperking - eerlijker in beide richtingen.
_WIN_PROB_DISCLAIMER = (
    "⚠️ De winkans is een logistische schatting op het verschil in speelsterkte, "
    "gekalibreerd op 44 recent gespeelde dubbels (70% van de uitslagen juist voorspeld; "
    "Brier 0.195 tegenover 0.25 voor een muntstuk). Bij uitgesproken favorieten en "
    "underdogs is de schatting nog steeds aan de voorzichtige kant, en de steekproef is "
    "klein — richtinggevend signaal dus, geen garantie."
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
    bundle=None, total_boards=None,
):
    """PADEL_ANALYSIS_ROTATION_PICK_OPPONENT_2026-09-24 (op verzoek van Kim:
    "Bij de rotatieplanner loopt er ook iets fout. Eigenlijk wil je gewoon
    de match kunnen kiezen die gespeeld is in de eerste rotatie. Dus zowel
    eigen spelers als medespelers. en dan moet je de mogelijkheden krijgen
    van opstellingen voor rotatie 2 waarbij je dan kan zien wat daar de
    beste optie is.")
    ----------------------------------------------------------------------
    PROBLEEM: de planner liet enkel ONZE koppelverdeling per rotatie kiezen.
    Wie de tegenstander in die rotatie opstelde, kwam uit een APARTE
    selectbox hoger op de pagina ("Matchup-inschatting voor de
    Rotatieplanner op basis van"), en gold dan voor ALLE rotaties tegelijk.
    Daardoor kon je niet invoeren wat er in rotatie 1 ECHT gespeeld is, en
    klopte de inschatting voor rotatie 2 niet: die ging nog steeds uit van
    hetzelfde tegenstander-scenario, ook al zijn de spelers die in rotatie 1
    speelden in de praktijk deels uitgeput.

    FIX: per rotatie kan je nu ZELF de 2 tegenstander-duo's aanduiden
    (standaard voorgevuld uit het gekozen scenario). Die keuze bepaalt de
    winkansen van de kandidaten voor DIE rotatie, en wordt mee vastgelegd
    bij "Bevestig rotatie" - zodat rotatie 2 vertrekt van de werkelijk
    gespeelde situatie in plaats van een algemeen scenario.

    PADEL_ANALYSIS_ROTATION_COUNT_FROM_BOARDS_2026-09-25 (op verzoek van
    Kim: "Ik zie ook dat het systeem na bevestig rotatie 1 dan plots
    bevestig rotatie 2 toont maar en dan rotatie 3 maar er zijn nu in deze
    interclub maar 2 rotaties. Andere interclub tornooien [...] kan wel 3
    rotaties zijn maar dat haal je normaal uit de reglement sectie.")
    ----------------------------------------------------------------------
    ROOT CAUSE: er was GEEN stopconditie - de planner bleef "Rotatie N"
    aanbieden zolang er nog een geldige koppelverdeling bestond, ongeacht
    hoeveel wedstrijden deze ontmoeting effectief telt. `total_boards` is
    nieuw: dezelfde waarde die hoger op de pagina al werd ingevuld/berekend
    ("Aantal wedstrijden deze ontmoeting" - in de praktijk vaak al
    voorgesteld op basis van eerder gespeelde ontmoetingen, en waar
    mogelijk aan te vullen vanuit het reglement zodra tournament_rules.py
    dat aantal per afdeling bijhoudt). Zodra `len(locked_rotations) * 2 >=
    total_boards`, toont de planner een afsluitende melding i.p.v. een
    nieuwe rotatie te openen.
    """
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
    # PADEL_ANALYSIS_ROTATION_PICK_OPPONENT_2026-09-24: per bevestigde
    # rotatie bewaren we nu ook WIE de tegenstander opstelde, zodat de
    # weergave hieronder de volledige, werkelijk gespeelde situatie toont.
    opp_locked_key = f"rot_locked_opp_v1_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if opp_locked_key not in st.session_state:
        st.session_state[opp_locked_key] = []
    locked_opponents = st.session_state[opp_locked_key]

    for rot_idx, pairs in enumerate(locked_rotations, start=1):
        st.markdown(f"**Rotatie {rot_idx} (bevestigd):**")
        opp_voor_rotatie = (
            locked_opponents[rot_idx - 1] if rot_idx - 1 < len(locked_opponents) else None
        )
        for match_idx, pair in enumerate(pairs, start=1):
            p1, p2 = tuple(pair)
            ons = f"{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}"
            tegen = ""
            if opp_voor_rotatie and match_idx - 1 < len(opp_voor_rotatie):
                namen = [x.get("name", "?") for x in opp_voor_rotatie[match_idx - 1]]
                if namen:
                    tegen = f"  \u2014  tegen **{' / '.join(namen)}**"
            st.write(f"Match {match_idx}: {ons}{tegen}")
        if st.button(f"✏️ Rotatie {rot_idx} wijzigen", key=f"rot_edit_v3_{ploeg_id}_{rot_idx}"):
            st.session_state[locked_key] = locked_rotations[: rot_idx - 1]
            st.session_state[opp_locked_key] = locked_opponents[: rot_idx - 1]
            st.rerun()
        st.markdown("---")
    excluded_pairs = {p for rot in locked_rotations for p in rot}
    next_rotation_num = len(locked_rotations) + 1

    # PADEL_ANALYSIS_ROTATION_COUNT_FROM_BOARDS_2026-09-25: stop met nieuwe
    # rotaties aanbieden zodra het aantal reeds bevestigde borden het totaal
    # voor DEZE ontmoeting bereikt - zie docstring hierboven.
    borden_bevestigd = sum(len(rot) for rot in locked_rotations)
    if total_boards is not None and borden_bevestigd >= int(total_boards):
        st.success(
            f"\u2705 Alle {int(total_boards)} wedstrijden van deze ontmoeting zijn ingedeeld "
            f"over {len(locked_rotations)} rotatie(s)."
        )
        return

    # ── Tegenstander-duo's voor DEZE rotatie ──
    unique_opp_players = (bundle or {}).get("unique_players") or []
    rotation_opponent_boards = None
    if unique_opp_players:
        with st.expander(
            f"\U0001F465 Wie stelt de tegenstander op in rotatie {next_rotation_num}?",
            expanded=True,
        ):
            # PADEL_ANALYSIS_ROTATION_OPPONENT_PAIR_DROPDOWN_2026-09-25 (op
            # verzoek van Kim: "Tegenstander instellen match 1 en match 2.
            # nu kan je daar maar 1 speler selecteren maar je speelt altijd
            # tegen 2 personen. Mss beter om gewoon een dropdown list van
            # geldige spelerscombinaties van de tegenstander te tonen die
            # je dan kan kiezen.")
            # ------------------------------------------------------------
            # De vorige 2 multiselects per match (elk max_selections=2)
            # lieten je 2 spelers apart aanklikken, wat foutgevoelig is en
            # in de praktijk als "je kan er maar 1 kiezen" aanvoelde. Nu 1
            # SELECTBOX per match, gevuld met ALLE geldige 2-spelerscombi's
            # uit de gekende tegenstander-roster - je kiest dus in 1 klik
            # een volledig koppel i.p.v. losse namen te moeten samenvoegen.
            # Combinaties die dit seizoen al EFFECTIEF samen speelden staan
            # bovenaan (🟢) en tonen hoe vaak, als geheugensteun.
            st.caption(
                "Vul hier in wie de tegenstander in DEZE rotatie opstelt (of al opstelde). "
                "De winkansen van de combinaties hieronder worden daar meteen op herrekend. "
                "Laat je dit leeg, dan wordt het scenario gebruikt dat je hoger op de pagina koos."
            )

            def _opp_pick_label(speler: dict) -> str:
                naam = speler.get("name", "?")
                uid = str(speler.get("user_id") or "")
                officieel = _cached_official_rank(uid) if uid else None
                padelstat = _cached_own_player_rating(uid) if uid else None
                delen = [f"P{int(officieel)}" if officieel is not None else "P?"]
                if padelstat is not None:
                    delen.append(f"ps {int(padelstat)}")
                return f"{naam} ({' \u00b7 '.join(delen)})"

            paar_frequentie = {}
            for fx_b in (bundle or {}).get("previous_fixtures", []) or []:
                for b in fx_b.get("boards", []) or []:
                    p = b.get("opponent_pair") or []
                    if len(p) == 2:
                        k = frozenset(str(x.get("user_id")) for x in p if x.get("user_id"))
                        if len(k) == 2:
                            paar_frequentie[k] = paar_frequentie.get(k, 0) + 1

            def _pair_label(p1: dict, p2: dict) -> str:
                uid1, uid2 = str(p1.get("user_id")), str(p2.get("user_id"))
                n = paar_frequentie.get(frozenset({uid1, uid2}), 0)
                badge = f"\U0001F7E2 {n}x \u00b7 " if n else ""
                return f"{badge}{_opp_pick_label(p1)} / {_opp_pick_label(p2)}"

            alle_paren = list(itertools.combinations(unique_opp_players, 2))
            alle_paren.sort(
                key=lambda pr: paar_frequentie.get(
                    frozenset({str(pr[0].get("user_id")), str(pr[1].get("user_id"))}), 0,
                ),
                reverse=True,
            )
            geen_keuze = "\u2014 Kies een koppel \u2014"
            paar_labels = [geen_keuze] + [_pair_label(p1, p2) for p1, p2 in alle_paren]
            paar_map = {_pair_label(p1, p2): (p1, p2) for p1, p2 in alle_paren}

            # Voorvullen uit het gekozen scenario, zodat de planner meteen
            # bruikbaar is zonder handmatig invullen.
            voorstel_idx = [0, 0]
            if opponent_boards:
                offset = (next_rotation_num - 1) * 2
                for i in range(2):
                    idx = offset + i
                    if idx < len(opponent_boards):
                        scenario_pair = (opponent_boards[idx].get("opponent_pair") or [])
                        if len(scenario_pair) == 2:
                            scenario_key = frozenset(str(x.get("user_id")) for x in scenario_pair)
                            for j, (p1, p2) in enumerate(alle_paren, start=1):
                                if frozenset({str(p1.get("user_id")), str(p2.get("user_id"))}) == scenario_key:
                                    voorstel_idx[i] = j
                                    break

            # PADEL_ANALYSIS_ROTATION_OPPONENT_CROSS_FILTER_2026-09-26 (op
            # verzoek van Kim: "de tegenstanders match 2 worden niet
            # aangepast (of niet correct) want ik kan bvb zelfde spelers van
            # match 1 nog kiezen wat onmogelijk is aangezien een speler nooit
            # in 2 matchen tegelijk kan spelen")
            # ------------------------------------------------------------
            # ROOT CAUSE: beide selectboxen kregen dezelfde, volledige
            # `paar_labels`-lijst - de overlap werd pas ACHTERAF gemeld als
            # foutmelding, nooit VOORAF onmogelijk gemaakt. Dat is exact het
            # patroon dat al eerder in de Sandbox gefixt is (PADEL_ANALYSIS_
            # SANDBOX_MATCH2_LINKED_TO_MATCH1_2026-09-26) - hier ontbrak die
            # fix nog, omdat de Rotatieplanner koppel-dropdowns gebruikt
            # i.p.v. losse multiselects en dus een aparte implementatie had.
            # FIX: Match 2 toont nu enkel nog koppels die GEEN speler delen
            # met het al gekozen koppel van Match 1 (en omgekeerd, voor het
            # geval iemand Match 2 eerst invult). Wijzigt Match 1 nadat Match
            # 2 al gekozen was op een manier die een overlap veroorzaakt, dan
            # wordt Match 2's keuze hier gereset - Streamlit toont anders een
            # bestaande sessiewaarde die niet meer in de gefilterde opties zit.
            def _opp_pair_uids(paar):
                return {str(p.get("user_id")) for p in paar} if paar else set()

            gekozen_paren = [None, None]
            col_o1, col_o2 = st.columns(2)
            cols = (col_o1, col_o2)
            for i in range(2):
                andere = 1 - i
                uitgesloten_uids = _opp_pair_uids(gekozen_paren[andere])
                if uitgesloten_uids:
                    beschikbare_labels = [geen_keuze] + [
                        _pair_label(p1, p2) for p1, p2 in alle_paren
                        if not ({str(p1.get("user_id")), str(p2.get("user_id"))} & uitgesloten_uids)
                    ]
                else:
                    beschikbare_labels = paar_labels
                key_i = f"rot_opp_pick_pair_{ploeg_id}_{next_rotation_num}_{i}"
                if key_i in st.session_state and st.session_state[key_i] not in beschikbare_labels:
                    st.session_state[key_i] = geen_keuze
                with cols[i]:
                    keuze_lbl = st.selectbox(
                        f"Tegenstander match {i + 1}", beschikbare_labels,
                        index=min(voorstel_idx[i], len(beschikbare_labels) - 1),
                        key=key_i,
                    )
                    if keuze_lbl != geen_keuze:
                        gekozen_paren[i] = paar_map[keuze_lbl]
                # Match 2 moet ONMIDDELLIJK weten wat Match 1 net koos (niet
                # pas volgende rerun) - vandaar deze berekening PER ITERATIE,
                # i.p.v. na de hele loop.

            if gekozen_paren[0] and gekozen_paren[1]:
                rotation_opponent_boards = [
                    {"opponent_pair": list(gekozen_paren[0])},
                    {"opponent_pair": list(gekozen_paren[1])},
                ]
                st.caption("\u2705 Winkansen hieronder zijn berekend tegen deze tegenstander-opstelling.")
            elif gekozen_paren[0] or gekozen_paren[1]:
                st.caption("Kies ook een koppel voor de andere match om de winkansen te herberekenen.")

    # De per-rotatie gekozen tegenstander heeft voorrang op het algemene scenario.
    effective_opponent_boards = rotation_opponent_boards or opponent_boards
    # PADEL_ANALYSIS_ROTATION_PLANNER_CACHE_2026-09-25 (op verzoek van Kim:
    # "Het laden bij het aanklikken van een keuze is wel een beetje
    # vervelend. zo ook bvb bij aanklikken rotatie 1"):
    # In tegenstelling tot de matchup-scenariotabel en de sandbox (beide al
    # achter een expliciete knop + signature-cache), riep de Rotatieplanner
    # _generate_rotation_candidates() ONVOORWAARDELIJK aan bij ELKE render -
    # dus bij ELKE widget-interactie op de hele pagina, ook volledig
    # onrelateerde. Dezelfde signature-cache-aanpak als elders in dit
    # bestand: enkel herrekenen als de daadwerkelijk bepalende invoer
    # effectief gewijzigd is.
    rot_cache_key = f"rot_candidates_v1_{ploeg_id}_{next_rotation_num}"
    rot_sig_key = f"rot_candidates_sig_v1_{ploeg_id}_{next_rotation_num}"
    rot_signature = (
        tuple(sorted(available_ids)),
        tuple(sorted(tuple(sorted(p)) for p in excluded_pairs)) if excluded_pairs else (),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(player_ratings.items())) if player_ratings else (),
        tuple(sorted(opponent_ratings.items())) if opponent_ratings else (),
        tuple(
            tuple(sorted(str(p.get("user_id")) for p in b.get("opponent_pair", [])))
            for b in (effective_opponent_boards or [])
        ),
        tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
    )
    if st.session_state.get(rot_sig_key) != rot_signature:
        st.session_state[rot_cache_key] = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
            opponent_boards=effective_opponent_boards, player_ratings=player_ratings,
            opponent_ratings=opponent_ratings, max_results=15,
            tournament_rules_dict=tournament_rules_dict,
        )
        st.session_state[rot_sig_key] = rot_signature
    candidates, total_possible, rotation_diagnostics = st.session_state[rot_cache_key]
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
        # PADEL_ANALYSIS_ROTATION_PICK_OPPONENT_2026-09-24: leg ook vast
        # tegen WIE deze rotatie gespeeld werd, zodat de bevestigde
        # weergave hierboven de volledige situatie toont en een latere
        # rotatie daar niet mee in de war raakt.
        opp_pairs_voor_log = []
        if rotation_opponent_boards:
            opp_pairs_voor_log = [b.get("opponent_pair") or [] for b in rotation_opponent_boards]
        st.session_state[opp_locked_key] = locked_opponents + [opp_pairs_voor_log]
        st.rerun()
# ─────────────────────────────────────────────
# Rotatie-bewuste enumeratie
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
# Bordvolgorde: officiële regel + padelstat-tie-breaker
# ─────────────────────────────────────────────
def _pair_official_sum(pair, official_ranks: dict) -> float:
    return sum((official_ranks.get(pid) or 0) for pid in pair)
def _pair_official_sum_safe(pair, official_ranks: dict) -> tuple:
    known = [official_ranks.get(pid) for pid in pair]
    is_compleet = all(v is not None for v in known)
    total = sum((v or 0) for v in known)
    return total, is_compleet
def _pair_padelstat_sum(pair, padelstat_ratings: dict) -> float:
    return sum((padelstat_ratings.get(pid) or 0) for pid in pair)
def _rank_pairs_with_padelstat_tiebreak(
    pairs: list, official_ranks: dict, padelstat_ratings: dict,
) -> list:
    def sort_key(pair):
        official_sum = _pair_official_sum(pair, official_ranks)
        padelstat_sum = _pair_padelstat_sum(pair, padelstat_ratings)
        return (official_sum, padelstat_sum)
    return sorted(pairs, key=sort_key, reverse=True)
def _rotation_has_missing_official_rank(duo_a, duo_b, official_ranks: dict) -> bool:
    _, complete_a = _pair_official_sum_safe(duo_a, official_ranks)
    _, complete_b = _pair_official_sum_safe(duo_b, official_ranks)
    return not (complete_a and complete_b)
def _order_rotations_with_tiebreak(
    rotation_structure: list, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
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
    return tuple(pairs)
def _collect_unique_opponent_lineups(historical_boards_with_labels: list, theoretical_boards: list) -> dict:
    unique: dict = {}
    for label, boards in historical_boards_with_labels:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        entry = unique.setdefault(key, {"boards": boards, "is_historical": False, "historical_labels": []})
        entry["is_historical"] = True
        entry["historical_labels"].append(label)
        # PADEL_ANALYSIS_OPPONENT_LINEUP_FREQUENCY_2026-09-24 (op verzoek van
        # Kim: "bij de matchup kan je eventueel ook de opstelling die de
        # tegenstander al eens gebruikt heeft in vorige matchen aanduiden
        # met daarbij frequentie eventueel"): hoe vaker een opstelling
        # terugkeert, hoe waarschijnlijker ze opnieuw opgesteld wordt.
        entry["historical_count"] = entry.get("historical_count", 0) + 1
    for boards in theoretical_boards:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        if key not in unique:
            unique[key] = {
                "boards": boards, "is_historical": False,
                "historical_labels": [], "historical_count": 0,
            }
    return unique
# ─────────────────────────────────────────────
# Best/worst-case variant-enumeratie
# ─────────────────────────────────────────────
def _rotation_order_variants(
    duo_a, duo_b, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
    """PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21 (op verzoek van
    Kim: "bij de ploeg van Anneleen Gallant stel je anneleen op in de 1ste
    rotatie terwijl zij P100 is en andere ploeggenoten P200"):
    ROOT CAUSE (vervolg op de 2026-09-19-fix): de vorige versie berekende
    `rank_data_incomplete` wel correct, maar liet de VOLGORDE zelf
    (compliant_first/compliant_second) nog steeds bepalen door
    _rank_pairs_with_padelstat_tiebreak() -> _pair_official_sum(), die een
    ontbrekend klassement nog steeds als 0 telt. Zo kon een duo met een
    TIJDELIJK ontbrekend klassement bij een teamgenoot ten onrechte als
    "zwakker" (0-fallback) berekend worden, waardoor het ANDERE (in
    werkelijkheid zwakkere) duo alsnog als "eerste, sterkste" variant
    gepresenteerd werd - enkel met een klein "❓ onzeker"-label erbij, wat
    licht over het hoofd te zien is.
    FIX: is rank_data_incomplete=True, dan behandelen we deze rotatie nu
    EXACT zoals een echt gelijkspel: BEIDE volgordes worden gegenereerd,
    ELK met is_regulation_compliant=None (geen van beide is bevestigd) en
    een expliciet "❓ onzeker — ONVOLLEDIGE data"-label. Zo verschijnt de
    mogelijk-verkeerde volgorde NOOIT meer als de enige, schijnbaar
    bevestigde default-optie: beide opties staan naast elkaar, duidelijk
    als onbevestigd gelabeld, tot het klassement ververst is."""
    sum_a, complete_a = _pair_official_sum_safe(duo_a, official_ranks)
    sum_b, complete_b = _pair_official_sum_safe(duo_b, official_ranks)
    total_points = sum_a + sum_b
    rank_data_incomplete = not (complete_a and complete_b)
    valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
    if rules is not None:
        lo, hi = rules["punten_min"], rules["punten_max"]
        if total_points < lo:
            valid, reason = False, f"{total_points:.0f} < min {lo}"
        elif total_points > hi:
            valid, reason = False, f"{total_points:.0f} > max {hi}"
        else:
            valid, reason = True, f"{total_points:.0f} punten (toegelaten: {lo}-{hi})"
    ranked = _rank_pairs_with_padelstat_tiebreak([duo_a, duo_b], official_ranks, padelstat_ratings)
    first_guess, second_guess = ranked[0], ranked[1]
    punten_txt = f"officieel {sum_a:.0f} vs {sum_b:.0f} punten"
    if rank_data_incomplete:
        # PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21: BEIDE
        # volgordes zijn hier onbevestigd - geen enkele mag als "eerste,
        # bevestigde" keuze getoond worden.
        onvolledig_txt = (
            f"{punten_txt} — ❓ ONVOLLEDIG officieel klassement (min. 1 speler ontbreekt): "
            "welk duo écht sterkst is, kan NIET betrouwbaar bepaald worden"
        )
        variants = [
            {
                "ordered_pairs": [first_guess, second_guess],
                "is_regulation_compliant": None,
                "rank_data_incomplete": True,
                "swap_label": onvolledig_txt + " — vermoedelijke volgorde o.b.v. padelstat, NIET bevestigd",
                "total_points": total_points, "valid": valid, "reason": reason,
            },
            {
                "ordered_pairs": [second_guess, first_guess],
                "is_regulation_compliant": None,
                "rank_data_incomplete": True,
                "swap_label": onvolledig_txt + " — omgekeerde volgorde, EVENZEER niet bevestigd",
                "total_points": total_points, "valid": valid, "reason": reason,
            },
        ]
        return {"variants": variants}
    is_tie = (sum_a == sum_b)
    compliant_first, compliant_second = first_guess, second_guess
    first_label = (
        f"gelijke officiële sterkte ({punten_txt}) — aanbevolen o.b.v. padelstat" if is_tie
        else f"{punten_txt} — sterkste eerst (art. 6.6)"
    )
    variants = [{
        "ordered_pairs": [compliant_first, compliant_second],
        "is_regulation_compliant": True,
        "rank_data_incomplete": False,
        "swap_label": first_label,
        "total_points": total_points, "valid": valid, "reason": reason,
    }]
    if is_tie:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": True,
            "rank_data_incomplete": False,
            "swap_label": f"gelijke officiële sterkte ({punten_txt}) — alternatieve, even geldige keuze",
            "total_points": total_points, "valid": valid, "reason": reason,
        })
    else:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": False,
            "rank_data_incomplete": False,
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
    per_rotation_variant_lists = []
    for rotation in rotation_structure:
        if len(rotation) < 2:
            per_rotation_variant_lists.append([{
                "ordered_pairs": list(rotation), "is_regulation_compliant": True,
                "swap_label": "", "total_points": None, "valid": True, "reason": "onvolledige rotatie",
                "rank_data_incomplete": False,
            }])
            continue
        duo_a, duo_b = rotation[0], rotation[1]
        result = _rotation_order_variants(duo_a, duo_b, official_ranks, padelstat_ratings, rules=rules)
        variants = result["variants"]
        if not include_non_compliant:
            # PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21: bij
            # ontbrekende rankdata zijn NU beide varianten is_regulation_
            # compliant=None — "None is not False" dus deze blijven ALTIJD
            # zichtbaar in de standaardweergave, precies zoals bij een tie.
            variants = [v for v in variants if v["is_regulation_compliant"] is not False]
        per_rotation_variant_lists.append(variants)
    combinations = []
    for combo in itertools.product(*per_rotation_variant_lists):
        ordered_pairs = []
        rotations_info = []
        fully_compliant = True
        any_rank_data_incomplete = False
        for variant in combo:
            ordered_pairs.extend(variant["ordered_pairs"])
            rotations_info.append({
                "total_points": variant["total_points"], "valid": variant["valid"],
                "reason": variant["reason"], "swap_label": variant["swap_label"],
                "is_regulation_compliant": variant["is_regulation_compliant"],
                "rank_data_incomplete": variant.get("rank_data_incomplete", False),
            })
            if variant["is_regulation_compliant"] is False:
                fully_compliant = False
            if variant.get("rank_data_incomplete"):
                any_rank_data_incomplete = True
        combinations.append({
            "ordered_pairs": ordered_pairs, "rotations": rotations_info,
            "fully_compliant": fully_compliant,
            "rank_data_incomplete": any_rank_data_incomplete,
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
            all_points_valid = all(r["valid"] for r in combo["rotations"])
            if tournament_rules_dict is not None and not all_points_valid:
                own_excluded_by_rules += 1
                continue
            valid_own_options.append((
                combo["ordered_pairs"], combo["rotations"], combo["fully_compliant"],
                combo.get("rank_data_incomplete", False),
            ))
    seen_matchup_keys = set()
    all_matchups = []
    total_seen = 0
    truncated = own_truncated
    for own_ordered_pairs, own_rotations_info, fully_compliant, rank_data_incomplete in valid_own_options:
        if truncated and len(all_matchups) >= _MAX_TOTAL_MATCHUPS:
            break
        our_pairs_key = tuple(frozenset(p) for p in own_ordered_pairs)
        for their_key, info in unique_opponent_lineups.items():
            boards = info["boards"]
            if len(boards) != len(own_ordered_pairs):
                continue
            total_seen += 1
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
                "rank_data_incomplete": rank_data_incomplete,
                "own_rotations": own_rotations_info,
                "fully_compliant": fully_compliant,
                "is_historical": info["is_historical"],
                "historical_labels": list(info["historical_labels"]),
                "historical_count": info.get("historical_count", 0),
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
_TABLE_CHAR_WIDTH_PX = 6.6
_TABLE_COL_MIN_WIDTH = 90
_TABLE_COL_MAX_WIDTH = 240
def _estimate_column_width(values: list, min_width: int = _TABLE_COL_MIN_WIDTH, max_width: int = _TABLE_COL_MAX_WIDTH) -> int:
    max_len = 0
    for v in values:
        if v is None:
            continue
        max_len = max(max_len, len(str(v)))
    width = int(max_len * _TABLE_CHAR_WIDTH_PX) + 24
    return max(min_width, min(max_width, width))
def _compliance_badge(fully_compliant: bool, rank_data_incomplete: bool = False) -> str:
    if rank_data_incomplete:
        return "❓ onzeker"
    return "✅" if fully_compliant else "⚠️ NIET"
def _own_lineup_group_key(assignment: list) -> frozenset:
    return frozenset(frozenset(a["our_pair"]) for a in assignment)
def _matchups_to_table_rows(matchups: list, name_lookup_global: dict) -> tuple:
    rows = []
    board_column_names: list = []
    for rank, m in enumerate(matchups, start=1):
        assignment = m["assignment"]
        n_boards = len(assignment)
        n_rotations = -(-n_boards // 2)
        row = {"#": rank, "Verwacht": m.get("expected_boards_won")}
        for r in range(n_rotations):
            for board_in_rotation in range(2):
                board_idx = r * 2 + board_in_rotation
                if board_idx >= n_boards:
                    continue
                a = assignment[board_idx]
                col_base = f"Rotatie{r+1} M{board_in_rotation+1}"
                if col_base not in board_column_names:
                    board_column_names.append(col_base)
                p1, p2 = a["our_pair"]
                our_full_1 = name_lookup_global.get(p1, p1)
                our_full_2 = name_lookup_global.get(p2, p2)
                opp_pair = a["opponent_board"]["opponent_pair"]
                their_full = [p.get("name", "?") for p in opp_pair]
                wp = a.get("win_probability")
                row[f"{col_base} — Ons duo"] = f"{our_full_1}+{our_full_2}"
                row[f"{col_base} — Tegenstander"] = "+".join(their_full)
                row[f"{col_base} %"] = round(wp * 100, 0) if wp is not None else None
        swap_notes = [
            rot.get("swap_label", "") for rot in (m.get("own_rotations") or [])
            if rot.get("swap_label")
        ]
        row["Toelichting"] = " | ".join(swap_notes) if swap_notes else ""
        # PADEL_ANALYSIS_OPPONENT_LINEUP_FREQUENCY_2026-09-24: toon HOE VAAK
        # de tegenstander deze opstelling al gebruikte, niet enkel DAT ze
        # ze ooit gebruikten - 3x dezelfde opstelling is een veel sterker
        # signaal dan 1x.
        n_keer = m.get("historical_count", 0)
        if m["is_historical"]:
            freq = f"\U0001F7E2 {n_keer}x" if n_keer > 1 else "\U0001F7E2 1x"
            row["Vorige keer"] = f"{freq} ({', '.join(m['historical_labels'])})"
        else:
            row["Vorige keer"] = ""
        rows.append(row)
    return rows, board_column_names
def _matchup_table_column_config(table_rows: list, board_column_names: list) -> tuple:
    column_config = {
        "#": st.column_config.NumberColumn("#", width="small"),
        "Verwacht": st.column_config.NumberColumn("Verwacht", format="%.2f", width="small"),
    }
    for col_base in board_column_names:
        ons_col = f"{col_base} — Ons duo"
        tegen_col = f"{col_base} — Tegenstander"
        pct_col = f"{col_base} %"
        column_config[ons_col] = st.column_config.TextColumn(
            ons_col, width=_estimate_column_width([row.get(ons_col) for row in table_rows]),
        )
        column_config[tegen_col] = st.column_config.TextColumn(
            tegen_col, width=_estimate_column_width([row.get(tegen_col) for row in table_rows]),
        )
        column_config[pct_col] = st.column_config.NumberColumn(pct_col, format="%.0f%%", width="small")
    column_config["Toelichting"] = st.column_config.TextColumn(
        "Toelichting", width=_estimate_column_width([row.get("Toelichting") for row in table_rows], min_width=160, max_width=320),
    )
    column_order = ["#", "Verwacht"]
    for col_base in board_column_names:
        column_order += [f"{col_base} — Ons duo", f"{col_base} — Tegenstander", f"{col_base} %"]
    column_order += ["Toelichting", "Vorige keer"]
    return column_config, column_order
def _render_own_lineup_groups_with_opponents(all_matchups: list, name_lookup_global: dict) -> None:
    if not all_matchups:
        return
    groups: dict = {}
    for m in all_matchups:
        key = _own_lineup_group_key(m["assignment"])
        groups.setdefault(key, []).append(m)
    def _sort_val(m):
        ebw = m.get("expected_boards_won")
        return ebw if ebw is not None else m.get("total_score", 0.0)
    st.markdown('<div class="section-header">🏆 Onze opstellingen — klap open voor de tegenstander-opstellingen</div>', unsafe_allow_html=True)
    st.caption(
        "Elke groep hieronder is 1 unieke combinatie van ONZE koppels (ongeacht bordvolgorde of tegen wie), "
        "met het best-case/worst-case-resultaat al zichtbaar in de titel. Klap een groep open om ALLE "
        "doorgerekende tegenstander-opstellingen tegen DIE opstelling te zien, gesorteerd van beste naar "
        "slechtste verwachte winkans voor ons."
    )
    st.caption(
        "Reglementair: ✅ = geverifieerd conform art. 6.6. ⚠️ NIET = een bewust omgedraaide, niet-toegelaten "
        "variant. ❓ onzeker = minstens 1 speler heeft nog geen bekend officieel klassement — de volgorde kon "
        "NIET betrouwbaar geverifieerd worden."
    )
    group_entries = []
    for key, rows_for_group in groups.items():
        rows_sorted = sorted(rows_for_group, key=_sort_val, reverse=True)
        best, worst = rows_sorted[0], rows_sorted[-1]
        # PADEL_ANALYSIS_READABLE_LINEUP_TITLE_2026-09-24 (op verzoek van
        # Kim: "Die namen worden wel heel dicht en onduidelijk getoond.
        # eventueel multiline met Rotatie1-Match 1, Rotatie1-Match2 enz...")
        # De titel gebruikte een kale pipe-reeks van 4 koppels achter
        # elkaar, zonder te zeggen WELK koppel op welke match stond - bij
        # 4 duo's is dat in de praktijk onleesbaar.
        # Een st.expander-label kan geen echte regeleinden bevatten, dus de
        # titel krijgt hier expliciete R1M1/R1M2-prefixen (kort en
        # ondubbelzinnig), en de volledige opstelling wordt BINNEN de
        # expander nog eens per regel uitgeschreven.
        volgorde = [a["our_pair"] for a in best["assignment"]]
        korte_delen, lange_regels = [], []
        for idx, (p1, p2) in enumerate(volgorde):
            rot = idx // 2 + 1
            m_in_rot = idx % 2 + 1
            naam1 = name_lookup_global.get(p1, p1)
            naam2 = name_lookup_global.get(p2, p2)
            korte_delen.append(f"R{rot}M{m_in_rot} {naam1}/{naam2}")
            lange_regels.append(f"- **Rotatie {rot} — Match {m_in_rot}**: {naam1} / {naam2}")
        group_entries.append((" · ".join(korte_delen), lange_regels, rows_sorted, best, worst))

    group_entries.sort(key=lambda g: _sort_val(g[3]), reverse=True)

    for pair_labels, lange_regels, rows_sorted, best, worst in group_entries:
        best_ebw, worst_ebw = best.get("expected_boards_won"), worst.get("expected_boards_won")
        best_txt = f"{best_ebw:.2f}" if best_ebw is not None else f"score {best.get('total_score', 0):.3f}"
        worst_txt = f"{worst_ebw:.2f}" if worst_ebw is not None else f"score {worst.get('total_score', 0):.3f}"
        best_badge = _compliance_badge(best.get("fully_compliant", True), best.get("rank_data_incomplete", False))
        worst_badge = _compliance_badge(worst.get("fully_compliant", True), worst.get("rank_data_incomplete", False))
        header = (
            f"Best {best_txt} {best_badge} \u00b7 Worst {worst_txt} {worst_badge}  \u2014  {pair_labels}"
        )
        with st.expander(header, expanded=False):
            st.markdown("**Onze opstelling in deze groep:**")
            st.markdown("\n".join(lange_regels))
            st.caption(
                f"Best case {best_txt} en worst case {worst_txt} verwachte gewonnen matchen, over "
                f"{len(rows_sorted)} doorgerekende tegenstander-opstelling(en)."
            )
            table_rows, board_column_names = _matchups_to_table_rows(rows_sorted, name_lookup_global)
            column_config, column_order = _matchup_table_column_config(table_rows, board_column_names)
            st.dataframe(
                table_rows, use_container_width=True, hide_index=True,
                column_config=column_config, column_order=column_order,
            )
    st.divider()
def _render_best_for_selected_player(
    all_matchups: list, sel_player_id: str, name_lookup_global: dict,
) -> None:
    """Welke ploegopstelling is het beste VOOR EEN SPECIFIEKE speler?

    PADEL_ANALYSIS_BEST_FOR_SELECTED_PLAYER_2026-09-24 (op verzoek van Kim,
    zie eerdere toelichting in dit bestand) + PADEL_ANALYSIS_BEST_FOR_
    PLAYER_TEAM_RESULT_2026-09-25 (op verzoek van Kim: "Bij beste opstelling
    voor mezelf zie ik niet het team resultaat.. mag er bij in de tabel. de
    andere kolommen [...] kan je gerust smaller maken zodat ook volledige
    ploegopstelling wel past op scherm"):
    Toont nu ook het TEAMresultaat (gemiddeld verwacht aantal gewonnen
    matchen over de HELE ploeg, over dezelfde tegenstander-scenario's)
    naast de persoonlijke winkans - zodat direct zichtbaar is of een
    opstelling die goed is VOOR DEZE SPELER ook goed is VOOR HET TEAM, of
    net een compromis vereist. De percentage-kolommen kregen een
    expliciete, smalle kolombreedte zodat de (vaak langere) kolom
    'Volledige ploegopstelling' meer ruimte krijgt.
    """
    if not all_matchups or not sel_player_id:
        return
    sel_id = str(sel_player_id)
    sel_naam = name_lookup_global.get(sel_id, sel_id)
    groepen: dict = {}
    for m in all_matchups:
        eigen_kansen = []
        eigen_posities = []
        for idx, a in enumerate(m["assignment"]):
            p1, p2 = (str(x) for x in a["our_pair"])
            if sel_id not in (p1, p2):
                continue
            wp = a.get("win_probability")
            if wp is not None:
                eigen_kansen.append(wp)
            partner = p2 if p1 == sel_id else p1
            rot = idx // 2 + 1
            m_in_rot = idx % 2 + 1
            eigen_posities.append((rot, m_in_rot, partner))
        if not eigen_kansen:
            continue
        key = _own_lineup_group_key(m["assignment"])
        slot = groepen.setdefault(key, {
            "kansen": [], "posities": eigen_posities,
            "assignment": m["assignment"], "n_opstellingen": 0,
            "team_ebw": [],
        })
        slot["kansen"].append(sum(eigen_kansen) / len(eigen_kansen))
        team_ebw = m.get("expected_boards_won")
        if team_ebw is not None:
            slot["team_ebw"].append(team_ebw)
        slot["n_opstellingen"] += 1
    if not groepen:
        st.info(
            f"{sel_naam} komt in geen enkele doorgerekende opstelling voor - selecteer "
            "deze speler hierboven bij 'Beschikbare eigen spelers' om deze tabel te vullen."
        )
        return
    rijen = []
    for slot in groepen.values():
        kansen = slot["kansen"]
        gemiddeld = sum(kansen) / len(kansen)
        posities = slot["posities"]
        pos_txt = " + ".join(
            f"R{rot}M{m_in_rot} met {name_lookup_global.get(partner, partner)}"
            for rot, m_in_rot, partner in posities
        )
        opstelling_txt = " \u00b7 ".join(
            f"R{idx // 2 + 1}M{idx % 2 + 1} "
            f"{name_lookup_global.get(str(a['our_pair'][0]), a['our_pair'][0])}/"
            f"{name_lookup_global.get(str(a['our_pair'][1]), a['our_pair'][1])}"
            for idx, a in enumerate(slot["assignment"])
        )
        team_ebw_list = slot["team_ebw"]
        team_gemiddeld = (sum(team_ebw_list) / len(team_ebw_list)) if team_ebw_list else None
        rijen.append({
            "Gemiddelde winkans": round(gemiddeld * 100, 1),
            "Slechtste geval": round(min(kansen) * 100, 1),
            "Beste geval": round(max(kansen) * 100, 1),
            "Team gemiddeld": round(team_gemiddeld, 2) if team_gemiddeld is not None else None,
            f"Positie van {sel_naam}": pos_txt,
            "Volledige ploegopstelling": opstelling_txt,
            "Tegenstander-scenario's": slot["n_opstellingen"],
        })
    rijen.sort(key=lambda r: r["Gemiddelde winkans"], reverse=True)
    st.markdown(
        f'<div class="section-header">\U0001F3AF Beste opstelling voor {sel_naam}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Alle doorgerekende ploegopstellingen waarin **{sel_naam}** meespeelt, gerangschikt op "
        "de GEMIDDELDE persoonlijke winkans over ALLE tegenstander-opstellingen - dus robuust "
        "tegen een verrassing van de tegenstander. 'Slechtste geval' toont hoe diep die kans kan "
        "zakken als de tegenstander de voor ons ongunstigste opstelling kiest."
    )
    st.caption(
        "'Team gemiddeld' is het verwacht aantal gewonnen matchen voor de HELE ploeg (niet enkel "
        f"{sel_naam}) bij dezelfde opstelling - zo zie je meteen of een opstelling die goed is voor "
        f"{sel_naam} persoonlijk, ook goed is voor het team, of net een compromis vereist."
    )
    try:
        import pandas as _pd
        df = _pd.DataFrame(rijen)
        styled = df.style.background_gradient(
            subset=["Gemiddelde winkans"], cmap="RdYlGn", vmin=0, vmax=100,
        ).format({
            "Gemiddelde winkans": "{:.1f}%",
            "Slechtste geval": "{:.1f}%",
            "Beste geval": "{:.1f}%",
            "Team gemiddeld": lambda v: f"{v:.2f}" if v is not None else "-",
        })
        st.dataframe(
            styled, use_container_width=True, hide_index=True,
            column_config={
                "Gemiddelde winkans": st.column_config.NumberColumn("Gem. winkans", width="small"),
                "Slechtste geval": st.column_config.NumberColumn("Worst", width="small"),
                "Beste geval": st.column_config.NumberColumn("Best", width="small"),
                "Team gemiddeld": st.column_config.NumberColumn("Team gem.", width="small"),
                "Tegenstander-scenario's": st.column_config.NumberColumn("Scen.", width="small"),
                "Volledige ploegopstelling": st.column_config.TextColumn(
                    "Volledige ploegopstelling", width="large",
                ),
            },
        )
    except Exception:
        st.dataframe(rijen, use_container_width=True, hide_index=True)
    beste = rijen[0]
    team_val = beste.get("Team gemiddeld")
    team_txt = f", team gemiddeld **{team_val:.2f}**" if team_val is not None else ""
    st.success(
        f"\U0001F3C6 Beste voor {sel_naam}: **{beste['Volledige ploegopstelling']}** "
        f"\u2014 gemiddeld **{beste['Gemiddelde winkans']:.1f}%** winkans "
        f"(slechtste geval {beste['Slechtste geval']:.1f}%){team_txt}."
    )
    st.divider()


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

            # PADEL_ANALYSIS_OPPONENT_ROSTER_RESET_2026-09-25 (op verzoek
            # van Kim: "Als je bij de tegenstander bv. van 5 naar 4 spelers
            # herrekent dan zou je automatisch alles op totaal 8 matchen
            # moeten zeggen. Nu heb je het probleem bij spelers dat er 2
            # spelers dan op 1 match staan en als je dan naar 4 spelers
            # gaat dan krijg je de melding dat er niet genoeg matchen
            # zijn.")
            # ------------------------------------------------------------
            # ROOT CAUSE: elke st.number_input hieronder heeft een VASTE
            # key per speler (f"opp_max_{ploeg_id}_{pid}"). Streamlit
            # bewaart de waarde van zo'n widget in st.session_state en
            # NEGEERT `value=` zodra die key al bestaat - dus wanneer Kim
            # de selectie van 5 naar 4 spelers wijzigt, houden de OVERBLIJ-
            # VENDE 4 spelers nog hun oude waarde vast (berekend toen er
            # nog 5 spelers - en dus een ANDERE verdeling van `needed`
            # plaatsen - waren), in plaats van opnieuw gelijk verdeeld te
            # worden. De som klopt dan niet meer met `needed`, wat exact de
            # foutmelding "niet genoeg matchen" veroorzaakte.
            #
            # FIX: bij elke wijziging van de tegenstander-selectie OF het
            # aantal wedstrijden wordt hier eerst elke bestaande
            # opp_max_-key voor deze ploeg gewist, VOORDAT de widgets
            # hieronder aangemaakt worden - zodat `value=default_opp_max`
            # weer effectief toegepast wordt en de som altijd opnieuw
            # correct op `needed` uitkomt.
            roster_sig_key = f"opp_roster_sig_{opp['ploeg_id']}"
            roster_signature = (tuple(sorted(chosen_opp_ids)), int(total_boards))
            if st.session_state.get(roster_sig_key) != roster_signature:
                prefix = f"opp_max_{opp['ploeg_id']}_"
                for stale_key in [k for k in list(st.session_state) if str(k).startswith(prefix)]:
                    st.session_state.pop(stale_key, None)
                st.session_state[roster_sig_key] = roster_signature

            st.caption(
                f"Max. aantal wedstrijden per tegenstander-speler (standaard gelijk verdeeld over {needed} "
                "benodigde plaatsen — een speler mag, net als bij ons, meerdere matchen spelen met "
                "verschillende partners, maar nooit 2 GELIJKTIJDIGE matchen binnen dezelfde rotatie). "
                "Dit herberekent automatisch zodra je de selectie hierboven of het aantal wedstrijden wijzigt:"
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
                # PADEL_ANALYSIS_THEORETICAL_BOARDS_ACTUAL_CACHE_2026-09-26 (op
                # verzoek van Kim: "toch nog veel trage reacties [...] sommige
                # zaken wil je enkel doen wanneer je analyse effectief start en
                # niet ervoor"):
                # ROOT CAUSE: _generate_theoretical_opponent_boards_with_repeats()
                # (een backtracking-enumeratie met call_budget=300.000) werd
                # voorheen ALTIJD aangeroepen, ongeacht of de signature
                # gewijzigd was - de if-check hieronder bepaalde enkel of het
                # resultaat WEGGESCHREVEN werd, niet of het BEREKEND werd. Bij
                # elke klik waar dan ook op de pagina (deze sectie staat vóór
                # de tabs) liep deze dure enumeratie dus onnodig opnieuw.
                # FIX: de aanroep zelf staat nu BINNEN de if-check, net als bij
                # alle andere signature-caches in dit bestand.
                compute_key = f"theoretical_boards_{opp['ploeg_id']}"
                meta_key = f"theoretical_boards_meta_{opp['ploeg_id']}"
                sig_key = f"theoretical_boards_sig_{opp['ploeg_id']}"
                signature = (tuple(sorted(chosen_opp_ids)), tuple(sorted(opponent_max_per_player.items())), int(total_boards))
                if st.session_state.get(sig_key) != signature:
                    lineups, meta = _generate_theoretical_opponent_boards_with_repeats(
                        chosen_opp_players, opponent_max_per_player, opponent_official_ranks,
                        opponent_padelstat_ratings, _THEORETICAL_MAX_VARIANTS,
                    )
                    st.session_state[compute_key] = lineups
                    st.session_state[meta_key] = meta
                    st.session_state[sig_key] = signature
                theoretical_boards = st.session_state.get(compute_key) or []
                meta = st.session_state.get(meta_key) or {"total_theoretical": 0, "truncated": False}
                st.caption(f"🔢 **{meta['total_theoretical']}** theoretische tegenstander-opstellingen mogelijk met deze verdeling.")
                if meta["truncated"]:
                    st.warning(f"⚠️ Enkel de eerste {_THEORETICAL_MAX_VARIANTS} van {meta['total_theoretical']} worden berekend.")
    unique_opponent_lineups = _collect_unique_opponent_lineups(historical_boards_with_labels, theoretical_boards)
    if not unique_opponent_lineups:
        st.info("Nog geen tegenstander-opstelling gekend of berekend om tegen te analyseren.")
        return []
    settings_signature = (
        tuple(sorted(available_ids)),
        tuple(sorted(max_per_player.items())),
        int(total_boards),
        tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
        bool(include_non_compliant),
        frozenset(unique_opponent_lineups.keys()),
    )
    ratings_signature = (
        tuple(sorted(player_ratings.items())),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(opponent_ratings.items())),
    )
    signature = (settings_signature, ratings_signature)
    result_key = f"scenario_result_{opp['ploeg_id']}"
    sig_key = f"scenario_result_sig_{opp['ploeg_id']}"
    clicked = st.button(
        "🚀 Bereken alle geldige matchups", type="primary", key=f"compute_scenarios_{opp['ploeg_id']}",
        help="Berekent pas NA deze klik — wijzig gerust eerst alle instellingen hierboven zonder dat de "
             "pagina telkens opnieuw moet rekenen.",
    )
    if clicked:
        with st.spinner(f"Alle geldige matchups doorrekenen ({len(unique_opponent_lineups)} tegenstander-opstelling(en))..."):
            st.session_state[result_key] = _build_all_valid_matchups(
                unique_opponent_lineups, available_ids, max_per_player, synergy_fn,
                player_ratings, official_ranks_strict, opponent_ratings, tournament_rules_dict,
                include_non_compliant_variants=include_non_compliant,
            )
            st.session_state[sig_key] = signature
    stored = st.session_state.get(result_key)
    if stored is None:
        st.info("⬆️ Stel hierboven alles in en klik op **'Bereken alle geldige matchups'** om de tabel te vullen.")
        return []
    stored_signature = st.session_state.get(sig_key)
    if stored_signature != signature:
        stored_settings = stored_signature[0] if stored_signature else None
        if stored_settings != settings_signature:
            st.warning(
                "⚠️ De instellingen zijn gewijzigd sinds de laatste berekening — de tabel hieronder toont nog "
                "het VORIGE resultaat. Klik opnieuw op 'Bereken alle geldige matchups' om bij te werken."
            )
        else:
            st.warning(
                "🔄 De padelstat- en/of klassementwaarden zijn intussen ververst op de achtergrond sinds je "
                "laatste berekening — de tabel hieronder klopt dus mogelijk niet meer met de actuele data. "
                "Klik opnieuw op 'Bereken alle geldige matchups' om de analyse bij te werken."
            )
    all_matchups, truncated, total_seen, build_diag = stored
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
    _render_own_lineup_groups_with_opponents(all_matchups, name_lookup_global)
    # PADEL_ANALYSIS_BEST_FOR_SELECTED_PLAYER_2026-09-24: aparte tabel,
    # enkel voor de speler waarmee deze analyse gestart is.
    _render_best_for_selected_player(all_matchups, sel_player_id, name_lookup_global)
    with st.expander("📋 Platte tabel (alle matchups los naast elkaar, sorteerbaar per kolom)", expanded=False):
        show_all_key = f"all_matchups_showall_{opp['ploeg_id']}"
        show_all = st.checkbox(
            f"Toon alle {len(all_matchups)} matchups (i.p.v. de beste {_MATCHUP_DISPLAY_DEFAULT_N})",
            key=show_all_key,
        ) if len(all_matchups) > _MATCHUP_DISPLAY_DEFAULT_N else False
        display_matchups = all_matchups if show_all else all_matchups[:_MATCHUP_DISPLAY_DEFAULT_N]
        table_rows, board_column_names = _matchups_to_table_rows(display_matchups, name_lookup_global)
        column_config, column_order = _matchup_table_column_config(table_rows, board_column_names)
        st.dataframe(
            table_rows, use_container_width=True, hide_index=True,
            column_config=column_config, column_order=column_order,
        )
        st.caption(
            "Elk speler-duo staat in zijn eigen kolom ('Ons duo' / 'Tegenstander'), naast een aparte "
            "winkans-kolom per match. 'Rotatie1 M1' = Match 1 van rotatie 1 (sterkste duo volgens officieel "
            "klassement, art. 6.6), 'Rotatie1 M2' = Match 2, enz. De kolom 'Toelichting' toont de exacte "
            "officiële puntensom per duo die deze volgorde bepaalt (nooit de padelstat-score)."
        )
        if not show_all and len(all_matchups) > len(display_matchups):
            st.caption(f"Beste {len(display_matchups)} van {len(all_matchups)} matchups getoond — vink hierboven aan om alles te zien.")
    st.divider()
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
def _recent_own_lineup_boards(sel_player_id: str, profiles: list) -> list:
    try:
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs, index = _load_encounter_index(profile_ids)
        all_encounters = ll.list_encounters(index)
        own_keys = [key for key, _ in all_encounters if any(pid == sel_player_id for pid, _ in index[key])]
        if not own_keys:
            return []
        def _encounter_date(key):
            dates = [_parse_match_date(entry.get("match_date")) for _, entry in index[key]]
            dates = [d for d in dates if d]
            return max(dates) if dates else (0, 0, 0)
        most_recent_key = max(own_keys, key=_encounter_date)
        boards = ll.reconstruct_boards(index[most_recent_key]) or []
        pairs = []
        for board in sorted(boards, key=lambda b: b.get("board_position") or 0):
            pair = board.get("pair") or []
            if len(pair) == 2:
                pairs.append(tuple(pair))
        return pairs
    except Exception:
        return []
def _most_recent_opponent_boards_for_sandbox(bundle: dict) -> list:
    previous_fixtures = bundle.get("previous_fixtures") or []
    if not previous_fixtures:
        return []
    most_recent = previous_fixtures[-1]
    boards = sorted(most_recent.get("boards") or [], key=lambda b: b.get("board_position") or 0)
    pairs = []
    for b in boards:
        pair = b.get("opponent_pair") or []
        if len(pair) == 2:
            pairs.append([p.get("name", "?") for p in pair])
    return pairs
def _apply_sandbox_preset(
    ploeg_key: str, n_rotations: int, own_pair_labels: list = None, opp_pair_labels: list = None,
) -> None:
    slot = 0
    for r in range(int(n_rotations)):
        for m_i in range(2):
            if own_pair_labels is not None:
                key = f"sandbox_own_r{r}_m{m_i}_{ploeg_key}"
                pair = own_pair_labels[slot: slot + 2] if slot + 2 <= len(own_pair_labels) else []
                st.session_state[key] = list(pair)
            if opp_pair_labels is not None:
                key = f"sandbox_opp_r{r}_m{m_i}_{ploeg_key}"
                pair = opp_pair_labels[slot: slot + 2] if slot + 2 <= len(opp_pair_labels) else []
                st.session_state[key] = list(pair)
            slot += 2
def _smart_prefill_sandbox_defaults(
    ploeg_key: str, available_ids: list, official_ranks_strict: dict,
    name_lookup_global: dict, n_rotations: int, label_fn=None,
) -> None:
    """PADEL_ANALYSIS_SANDBOX_SHOW_RANKS_2026-09-24: `label_fn` is nieuw en
    VERPLICHT voor correcte werking sinds de sandbox-labels ook het
    klassement bevatten. Zonder deze parameter zou de prefill labels zetten
    die niet meer bestaan in de multiselect-opties, waardoor Streamlit de
    voorinvulling stilzwijgend negeert."""
    any_existing = any(
        f"sandbox_own_r{r}_m{m_i}_{ploeg_key}" in st.session_state
        for r in range(int(n_rotations)) for m_i in range(2)
    )
    if any_existing:
        return
    ids_sorted = sorted(
        available_ids,
        key=lambda pid: official_ranks_strict.get(pid) if official_ranks_strict.get(pid) is not None else -1,
        reverse=True,
    )
    _label = label_fn or (lambda pid: name_lookup_global.get(pid, pid))
    labels_sorted = [_label(pid) for pid in ids_sorted]
    _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=labels_sorted)
def _render_lineup_sandbox(
    bundle, opp, available_ids, name_lookup_global,
    player_ratings, official_ranks_strict, opponent_ratings, synergy_fn,
    profiles=None, sel_player_id=None,
) -> None:
    """PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21: het reglement-
    check-blok onderaan gebruikte _pair_official_sum() (die NOOIT None
    teruggeeft, enkel 0 bij een ontbrekend klassement) en controleerde dan
    "if s1 is None or s2 is None" — een check die dus NOOIT kon afgaan (dode
    code). Nu wordt de completeness apart bijgehouden via
    _pair_official_sum_safe(), zodat de "❓ onbekend"-waarschuwing
    daadwerkelijk verschijnt zodra een speler in de sandbox een ontbrekend
    officieel klassement heeft."""
    st.markdown('<div class="section-header">🧪 Sandbox: bouw je eigen opstelling</div>', unsafe_allow_html=True)
    st.caption(
        "Stel zelf, rotatie per rotatie en match per match, een opstelling samen: kies wie van ONS team en "
        "wie van DE TEGENSTANDER er in elke match staat. Handig om een specifieke hypothese te testen zonder "
        "te moeten zoeken in de volledige combinatie-tabel hierboven."
    )
    unique_players = bundle.get("unique_players", []) or []
    if len(available_ids) < 2:
        st.info("Selecteer hierboven minstens 2 eigen spelers om de sandbox te gebruiken.")
        return
    if len(unique_players) < 2:
        st.info("Nog geen tegenstander-spelers gekend om in de sandbox te kiezen.")
        return
    # PADEL_ANALYSIS_SANDBOX_SHOW_RANKS_2026-09-24 (op verzoek van Kim: "bij
    # de sandbox zou het wel beter zijn dat je ook het P-niveau toont van de
    # spelers zodat je weet wie je in match 1 en 2 kunt zetten"):
    # de sandbox toonde enkel namen. Om art. 6.6 te kunnen toepassen (het
    # duo met de HOOGSTE som officiele klassementen hoort op match 1) moest
    # je die cijfers elders opzoeken - precies de stap die de sandbox zou
    # moeten wegnemen. De labels tonen nu het officiele klassement, en waar
    # gekend ook de padelstat playing strength tussen haakjes.
    def _speler_label(pid: str) -> str:
        naam = name_lookup_global.get(pid, pid)
        officieel = official_ranks_strict.get(pid)
        padelstat = player_ratings.get(pid)
        delen = []
        delen.append(f"P{int(officieel)}" if officieel is not None else "P?")
        if padelstat is not None:
            delen.append(f"ps {int(padelstat)}")
        return f"{naam} ({' \u00b7 '.join(delen)})"

    own_labels = [_speler_label(pid) for pid in available_ids]
    own_label_to_id = {_speler_label(pid): pid for pid in available_ids}

    def _opp_label(speler: dict) -> str:
        naam = speler.get("name", "?")
        uid = str(speler.get("user_id") or "")
        officieel = _cached_official_rank(uid) if uid else None
        padelstat = _cached_own_player_rating(uid) if uid else None
        delen = [f"P{int(officieel)}" if officieel is not None else "P?"]
        if padelstat is not None:
            delen.append(f"ps {int(padelstat)}")
        return f"{naam} ({' \u00b7 '.join(delen)})"

    opp_labels = [_opp_label(p) for p in unique_players]
    opp_label_to_player = {_opp_label(p): p for p in unique_players}
    ploeg_key = opp["ploeg_id"]
    n_rotations = st.number_input(
        "Aantal rotaties in de sandbox", min_value=1, max_value=6, value=2, step=1,
        key=f"sandbox_n_rot_{ploeg_key}",
    )
    _smart_prefill_sandbox_defaults(
        ploeg_key, available_ids, official_ranks_strict, name_lookup_global,
        n_rotations, label_fn=_speler_label,
    )
    with st.expander("⚡ Snel invullen met een standaardoptie", expanded=False):
        preset_cols = st.columns(4)
        with preset_cols[0]:
            if st.button(
                "🔁 Tegenstander: vorige match", key=f"preset_opp_prev_{ploeg_key}", use_container_width=True,
                help="Vult het tegenstander-duo per match in met hun meest recente, effectief gespeelde opstelling.",
            ):
                opp_pairs = _most_recent_opponent_boards_for_sandbox(bundle)
                # PADEL_ANALYSIS_SANDBOX_SHOW_RANKS_2026-09-24: de labels
                # bevatten nu ook het klassement, dus een preset moet op
                # naam terugzoeken welk label daarbij hoort.
                _naam_naar_label = {p.get("name", "?"): lbl for lbl, p in opp_label_to_player.items()}
                flat = [_naam_naar_label.get(name, name) for pair in opp_pairs for name in pair]
                if flat:
                    _apply_sandbox_preset(ploeg_key, n_rotations, opp_pair_labels=flat)
                    st.rerun()
                else:
                    st.warning("Geen eerdere tegenstander-opstelling gekend.")
        with preset_cols[1]:
            if st.button(
                "💪 Ons sterkste 4 (Elo)", key=f"preset_own_elo_{ploeg_key}", use_container_width=True,
                help="Vult ONS duo per match in met de sterkste beschikbare spelers volgens padelstat/Elo-rating.",
            ):
                ids_by_elo = sorted(
                    available_ids,
                    key=lambda pid: player_ratings.get(pid) if player_ratings.get(pid) is not None else -1,
                    reverse=True,
                )
                labels_by_elo = [_speler_label(pid) for pid in ids_by_elo]
                _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=labels_by_elo)
                st.rerun()
        with preset_cols[2]:
            if st.button(
                "📋 Onze vorige opstelling", key=f"preset_own_prev_{ploeg_key}", use_container_width=True,
                help="Herhaalt ONZE opstelling (koppels) van de vorige interclubmatch.",
            ):
                own_pairs = _recent_own_lineup_boards(sel_player_id, profiles or []) if sel_player_id else []
                flat = [_speler_label(pid) for pair in own_pairs for pid in pair]
                if flat:
                    _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=flat)
                    st.rerun()
                else:
                    st.warning("Geen vorige eigen opstelling gekend.")
        with preset_cols[3]:
            if st.button(
                "🎲 Willekeurig geldig", key=f"preset_own_random_{ploeg_key}", use_container_width=True,
                help="Vult ONS duo per match willekeurig in (elke speler max. 1x, rotatie-veilig).",
            ):
                import random
                shuffled = list(available_ids)
                random.shuffle(shuffled)
                labels_random = [_speler_label(pid) for pid in shuffled]
                _apply_sandbox_preset(ploeg_key, n_rotations, own_pair_labels=labels_random)
                st.rerun()
    own_ordered_pairs, opp_boards, rotation_meta = [], [], []
    used_own_pairs_seen: dict = {}
    incomplete = False
    with st.form(key=f"sandbox_form_{ploeg_key}"):
        for r in range(int(n_rotations)):
            st.markdown(f"**Rotatie {r + 1}**")
            col_m1, col_m2 = st.columns(2)
            matches = []
            for m_i, col in enumerate((col_m1, col_m2)):
                with col:
                    st.markdown(f"Match {m_i + 1}" + (" *(sterkste duo, art. 6.6)*" if m_i == 0 else ""))
                    our_sel = st.multiselect(
                        "Ons duo", own_labels, max_selections=2,
                        key=f"sandbox_own_r{r}_m{m_i}_{ploeg_key}",
                    )
                    opp_sel = st.multiselect(
                        "Tegenstander-duo", opp_labels, max_selections=2,
                        key=f"sandbox_opp_r{r}_m{m_i}_{ploeg_key}",
                    )
                    matches.append((our_sel, opp_sel))
            m1_own, m1_opp = matches[0]
            m2_own, m2_opp = matches[1]
            own_overlap = set(m1_own) & set(m2_own)
            opp_overlap = set(m1_opp) & set(m2_opp)
            # PADEL_ANALYSIS_SANDBOX_OVERLAP_BLOCKS_COMPUTE_2026-09-26 (op
            # verzoek van Kim: "ik kan bvb zelfde spelers van match 1 nog
            # kiezen wat onmogelijk is aangezien een speler nooit in 2
            # matchen tegelijk kan spelen"):
            # De detectie hieronder (own_overlap/opp_overlap) bestond al,
            # maar bleef PUUR COSMETISCH - de st.error() verscheen wel, maar
            # de berekening ging gewoon door met de overlappende selectie.
            # rotation_has_overlap zorgt er nu voor dat de paren van DEZE
            # rotatie NIET meer worden toegevoegd aan own_ordered_pairs/
            # opp_boards zodra er overlap is - een fysiek onmogelijke
            # opstelling kan dus nooit meer een winkans-percentage krijgen.
            rotation_has_overlap = bool(own_overlap) or bool(opp_overlap)
            if own_overlap:
                st.error(f"⚠️ Rotatie {r + 1}: {', '.join(own_overlap)} kan niet in beide matchen tegelijk spelen.")
            if opp_overlap:
                st.error(f"⚠️ Rotatie {r + 1}: tegenstander {', '.join(opp_overlap)} kan niet in beide matchen tegelijk spelen.")
            for m_i, (our_sel, opp_sel) in enumerate(matches):
                if len(our_sel) != 2 or len(opp_sel) != 2:
                    incomplete = True
                    continue
                if rotation_has_overlap:
                    # Overlap in deze rotatie gedetecteerd (zie hierboven) -
                    # deze match NIET meenemen in de berekening, zodat een
                    # onmogelijke dubbele inzet van een speler nooit een
                    # winkans krijgt getoond alsof het een geldige
                    # opstelling was.
                    incomplete = True
                    continue
                p1, p2 = own_label_to_id[our_sel[0]], own_label_to_id[our_sel[1]]
                pair_key = frozenset({p1, p2})
                if pair_key in used_own_pairs_seen:
                    prev_rot = used_own_pairs_seen[pair_key]
                    st.warning(
                        f"⚠️ Rotatie {r + 1} Match {m_i + 1}: koppel {our_sel[0]}+{our_sel[1]} speelde al samen in "
                        f"Rotatie {prev_rot} — een zelfde koppel mag normaliter niet 2× samenspelen."
                    )
                used_own_pairs_seen[pair_key] = r + 1
                opp_players = [opp_label_to_player[lbl] for lbl in opp_sel]
                own_ordered_pairs.append((p1, p2))
                opp_boards.append({"opponent_pair": opp_players})
                rotation_meta.append((r + 1, m_i + 1))
        if incomplete:
            st.info("Vul voor elke match exact 2 eigen spelers en 2 tegenstander-spelers in om de resultaten te zien.")
        sandbox_clicked = st.form_submit_button(
            "🚀 Bereken sandbox", type="primary",
            help="Vul eerst alle matchen hierboven in (of gebruik een standaardoptie hierboven), klik dan pas "
                 "op deze knop — pas dan wordt er iets herberekend.",
        )
    if not own_ordered_pairs:
        return
    sandbox_settings_signature = (
        tuple(own_ordered_pairs),
        tuple(tuple(sorted(p.get("user_id") for p in b["opponent_pair"])) for b in opp_boards),
    )
    sandbox_ratings_signature = (
        tuple(sorted(player_ratings.items())),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(opponent_ratings.items())),
    )
    sandbox_signature = (sandbox_settings_signature, sandbox_ratings_signature)
    sandbox_result_key = f"sandbox_result_{ploeg_key}"
    sandbox_sig_key = f"sandbox_result_sig_{ploeg_key}"
    if sandbox_clicked:
        st.session_state[sandbox_result_key] = _compute_matchup(
            own_ordered_pairs, opp_boards, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings,
        )
        st.session_state[sandbox_sig_key] = sandbox_signature
    computed = st.session_state.get(sandbox_result_key)
    if computed is None:
        st.info("⬆️ Stel de sandbox in en klik op **'Bereken sandbox'** om de winkans en puntensom te zien.")
        return
    stored_sandbox_signature = st.session_state.get(sandbox_sig_key)
    if stored_sandbox_signature != sandbox_signature:
        stored_sandbox_settings = stored_sandbox_signature[0] if stored_sandbox_signature else None
        if stored_sandbox_settings != sandbox_settings_signature:
            st.warning(
                "⚠️ De sandbox-selectie is gewijzigd sinds de laatste berekening — onderstaand resultaat is nog "
                "het VORIGE. Klik opnieuw op 'Bereken sandbox' om bij te werken."
            )
        else:
            st.warning(
                "🔄 De padelstat- en/of klassementwaarden zijn intussen ververst op de achtergrond sinds je "
                "laatste berekening — onderstaand resultaat klopt mogelijk niet meer. Klik opnieuw op "
                "'Bereken sandbox' om bij te werken."
            )
    rows = []
    row_completeness: dict = {}
    for (rot_no, match_no), a in zip(rotation_meta, computed["assignment"]):
        p1, p2 = a["our_pair"]
        # PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21: gebruik de
        # SAFE-variant (zie docstring van deze functie hierboven) i.p.v.
        # _pair_official_sum() (altijd 0-fallback, nooit None), waardoor de
        # onderstaande "if s1 is None or s2 is None"-check voorheen dode
        # code was.
        our_sum, our_complete = _pair_official_sum_safe(frozenset({p1, p2}), official_ranks_strict)
        wp = a.get("win_probability")
        row_completeness[(rot_no, match_no)] = our_complete
        rows.append({
            "Rotatie": rot_no, "Match": match_no,
            "Ons duo": f"{name_lookup_global.get(p1, p1)}+{name_lookup_global.get(p2, p2)}",
            "Officieel (ons)": our_sum,
            "Tegenstander": "+".join(p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]),
            "Winkans %": round(wp * 100) if wp is not None else None,
        })
    st.dataframe(
        rows, use_container_width=True, hide_index=True,
        column_config={
            "Rotatie": st.column_config.NumberColumn("Rotatie", width="small"),
            "Match": st.column_config.NumberColumn("Match", width="small"),
            "Ons duo": st.column_config.TextColumn("Ons duo", width=_estimate_column_width([r.get("Ons duo") for r in rows])),
            "Officieel (ons)": st.column_config.NumberColumn("Officieel (ons)", width="small"),
            "Tegenstander": st.column_config.TextColumn("Tegenstander", width=_estimate_column_width([r.get("Tegenstander") for r in rows])),
            "Winkans %": st.column_config.NumberColumn("Winkans %", format="%.0f%%", width="small"),
        },
    )
    for r in range(1, int(n_rotations) + 1):
        rot_rows = [row for row in rows if row["Rotatie"] == r]
        if len(rot_rows) == 2:
            s1, s2 = rot_rows[0]["Officieel (ons)"], rot_rows[1]["Officieel (ons)"]
            compleet_1 = row_completeness.get((r, rot_rows[0]["Match"]), True)
            compleet_2 = row_completeness.get((r, rot_rows[1]["Match"]), True)
            if not (compleet_1 and compleet_2):
                st.warning(
                    f"⚠️ Rotatie {r}: officieel klassement onbekend voor minstens 1 speler — de "
                    "reglement-check (art. 6.6) kan hier NIET betrouwbaar uitgevoerd worden."
                )
            else:
                if s1 < s2:
                    st.warning(
                        f"⚠️ Rotatie {r}: Match 1 ({s1:.0f}p) is officieel ZWAKKER dan Match 2 ({s2:.0f}p) — "
                        "dit is NIET reglementair (art. 6.6), tenzij je dit bewust test als 'wat als'-scenario."
                    )
                elif s1 == s2:
                    st.caption(f"ℹ️ Rotatie {r}: Match 1 en Match 2 zijn officieel exact gelijk sterk ({s1:.0f}p) — beide volgordes zijn toegelaten.")
                else:
                    st.caption(f"✅ Rotatie {r}: Match 1 ({s1:.0f}p) is officieel sterker dan Match 2 ({s2:.0f}p) — reglementair conform (art. 6.6).")
    total_ebw = computed.get("expected_boards_won")
    if total_ebw is not None:
        st.metric("Verwacht totaal aantal gewonnen matchen (deze sandbox-opstelling)", f"{total_ebw:.2f} / {len(own_ordered_pairs)}")
    st.divider()
def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-analyse</div>', unsafe_allow_html=True)
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
            "- **Reglementair-badge**: ✅ = deze matchup-rij gebruikt overal de reglementair verplichte "
            "(of, bij gelijkspel, een even geldige) bordvolgorde. ⚠️ NIET = een BEWUST omgedraaide "
            "variant (enkel zichtbaar als je de bijhorende checkbox aanvinkt) - dit zou een overtreding "
            "van art. 6.6 zijn en dient enkel om het best-case/worst-case-bereik van een koppelkeuze in "
            "te schatten, NOOIT als effectieve wedstrijdopstelling. ❓ onzeker = minstens 1 speler heeft "
            "nog geen bekend officieel klassement, waardoor de volgorde NIET betrouwbaar geverifieerd kon "
            "worden (ververs eerst het klassement van deze speler(s)) — in dit geval worden BEIDE mogelijke "
            "volgordes getoond, geen van beide als bevestigd.\n"
            "- **Rotatie-veiligheid**: een speler kan nooit in 2 GELIJKTIJDIGE matchen van dezelfde "
            "rotatie staan.\n"
            "- **🟢 Vorige keer**: deze matchup komt overeen met een opstelling die de tegenstander "
            "EFFECTIEF al eens speelde dit seizoen.\n\n"
            + _WIN_PROB_DISCLAIMER
        )
    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")

    # Aparte bundle over ALLE gespeelde ontmoetingen van de tegenploeg, enkel
    # voor de match1/match2-statistiek (de gewone bundle bevat er maar 1).
    try:
        opp_team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id) if fixtures else []
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

    # Teamgenoten die in het uitslagenblad staan maar nog geen eigen profiel
    # hebben, worden expliciet toegevoegd i.p.v. stilzwijgend weggefilterd -
    # anders mis je ze precies wanneer je ze nodig hebt.
    known_ids = set(own_label_to_id.values())
    for pid, naam in roster.items():
        if pid in known_ids:
            continue
        label = f"{naam} (nog geen profiel)"
        own_labels.append(label)
        own_label_to_id[label] = pid

    col_roster, col_refresh = st.columns([3, 1])
    with col_refresh:
        if st.button("\U0001F504 Ploeg opnieuw ophalen", key=f"refresh_own_roster_{sel_player_id}"):
            for key in [k for k in list(st.session_state) if str(k).startswith(("own_roster_v2_", "full_scout_v2_"))]:
                st.session_state.pop(key, None)
            _load_encounter_index.clear()
            # PADEL_ANALYSIS_UI_SPEED_CACHE_2026-09-24: ook de rating-caches
            # legen, anders blijft een net ververst klassement tot 5 minuten
            # onzichtbaar terwijl de gebruiker net om een verversing vroeg.
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
                f"\u26A0\uFE0F Slechts {len(default_labels)} speler(s) gevonden in het uitslagenblad van "
                "onze vorige ontmoeting. Dat wijst op een onvolledig geparseerd uitslagenblad of "
                "een effectief kleinere ploeg die dag. Vul de selectie hieronder handmatig aan."
            )
    else:
        default_labels = own_labels[: min(8, len(own_labels))]
        with col_roster:
            st.caption(
                "\u26A0\uFE0F Onze vorige ontmoeting kon niet opgehaald worden (nog geen poule-schema "
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
        st.error(f"Speler-plaatsen ({total_slots}) moet gelijk zijn aan 2× wedstrijden ({2*total_boards}).")
        return
    # PADEL_ANALYSIS_UI_SPEED_CACHE_PHASE2_2026-09-25: zie _cached_docs_for_players().
    docs_for_synergy = _cached_docs_for_players(tuple(sorted(available_ids)))
    own_synergy = ll.compute_pairwise_synergy(docs_for_synergy, available_ids)
    synergy_fn = ll.make_pair_score_fn(own_synergy, docs_for_synergy)
    # PADEL_ANALYSIS_UI_SPEED_CACHE_2026-09-24: gecachet, zie _cached_own_player_rating().
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
        bundle=bundle, total_boards=total_boards,
    )
    st.divider()
    _render_lineup_sandbox(
        bundle, opp, available_ids, name_lookup_global,
        player_ratings, official_ranks_strict, opponent_ratings, synergy_fn,
        profiles=profiles, sel_player_id=sel_player_id,
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
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_RANGSCHIKKING_LINK_2026-09-26
# ─────────────────────────────────────────────
def _build_rangschikking_url(reeks_url: str) -> str | None:
    """Bouwt de link naar de officiele TVL-rangschikkingspagina van deze
    poule, op basis van de al gekende poule/tabel-URL (reeks_url).

    Gebruikt DEZELFDE spelgroepId + pouleId als die poule/tabel-URL - geen
    nieuwe scrape nodig, enkel de query-parameters overnemen. Geeft None
    terug als reeks_url ontbreekt of niet het verwachte formaat heeft (dan
    toont de aanroeper een duidelijke uitleg i.p.v. een kapotte link)."""
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
    """PADEL_ANALYSIS_RANGSCHIKKING_LINK_2026-09-26 (op verzoek van Kim:
    "zou ik daar een extra tab willen met rangschikking en daar gewoon in
    1ste instantie een link naar de rangschikking"):
    de tab "🏆 Rangschikking" bestaat al (roept oa.render_ranking_tab() aan
    - een eigen berekende tabel); dit voegt bovenaan die tab enkel de
    gevraagde rechtstreekse link naar de OFFICIELE TVL-pagina toe.

    PADEL_ANALYSIS_RANGSCHIKKING_NO_RAW_URL_2026-09-26 (op verzoek van Kim:
    "de url [...] moet niet getoond worden want daar kan je ook op
    klikken en gaat naar zelfde pagina"): de st.caption(url) hieronder
    toonde de RUWE link ONDER de al klikbare knop - een dubbele,
    overbodige weergave van exact dezelfde bestemming. Verwijderd; de
    knop zelf blijft de enige, klikbare manier om de pagina te openen.
    """
    url = _build_rangschikking_url(reeks_url)
    if url:
        try:
            st.link_button("\U0001F517 Bekijk de officiele rangschikking op TVL", url)
        except AttributeError:
            st.markdown(f"[\U0001F517 Bekijk de officiele rangschikking op TVL]({url})")
    else:
        st.info(
            "Kon de rangschikkingslink nog niet automatisch afleiden - het poule/tabel-schema "
            "moet eerst geladen zijn (zie 'Volgende match' hierboven)."
        )
    st.divider()


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
    # PADEL_ANALYSIS_RANGSCHIKKING_TOP_LEVEL_TAB_2026-09-26 (op verzoek van
    # Kim: "rangschikking staat nu naast overzicht en detail per speler. ik
    # zou rangschikken naast analyseren/andere ploegen en opgeslagen
    # analyses willen"): de spelerselectie en de volledige scout/rapport-
    # opbouw staan nu VOOR st.tabs(), dus BUITEN elk tabblad - Streamlit
    # voert de code binnen ELK tabblad toch bij iedere rerun uit (enkel de
    # WEERGAVE is verborgen voor niet-actieve tabbladen), dus deze opbouw
    # 1x laten gebeuren en het resultaat hergebruiken in zowel het
    # Analyseren- als het Rangschikking-tabblad voorkomt dat dezelfde,
    # relatief zware scout/rapport-opbouw dubbel zou draaien.
    sel_label = st.selectbox("Toon analyse voor:", labels, index=default_idx, key="lineup_lab_sel_player")
    sel_profile = profile_map[sel_label]
    sel_player_id = sel_profile.get("player_id")
    scout_result = _render_volgende_match_and_scout(str(sel_player_id), sel_label)
    bundle = opp = reeks_url = spelgroep_id = None
    report_for_ai = None
    if scout_result:
        bundle, opp, reeks_url, spelgroep_id = scout_result
        # PADEL_ANALYSIS_FULL_ROSTER_IN_OVERVIEW_2026-09-24: vul de
        # roster aan met spelers uit EERDERE ontmoetingen (zie
        # _merge_full_opponent_roster()) VOORDAT het team-rapport
        # opgebouwd wordt - anders ontbreken ze in de overzichtstabel,
        # de theoretische scenario's en de sandbox.
        _fixtures_voor_roster = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
        bundle = _merge_full_opponent_roster(bundle, _fixtures_voor_roster, opp)
        extra_namen = bundle.get("_roster_extended_with") or []
        if extra_namen:
            st.caption(
                f"\u2795 {len(extra_namen)} extra speler(s) uit eerdere ontmoetingen mee "
                f"opgenomen in deze analyse: {', '.join(extra_namen)}."
            )
            # PADEL_ANALYSIS_ROSTER_CONFIDENCE_LABEL_2026-09-25: zie
            # _merge_full_opponent_roster() - toont expliciet WELKE van
            # deze extra spelers slechts 1x gezien zijn en verder geen
            # bekende matchdata hebben, zodat een onzekere roster niet
            # blind als een bevestigd feit gepresenteerd wordt.
            onzeker_namen = bundle.get("_roster_extended_low_confidence") or []
            if onzeker_namen:
                st.caption(
                    f"\u2753 Let op: {', '.join(onzeker_namen)} "
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
    tab_analyse, tab_rang, tab_poule, tab_saved = st.tabs(
        ["🔍 Analyseren", "🏆 Rangschikking", "🌐 Andere ploegen", "💾 Opgeslagen analyses"]
    )
    with tab_analyse:
        if scout_result:
            sub_overzicht, sub_detail = st.tabs(["📊 Overzicht", "🔎 Detail per speler"])
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
        if scout_result:
            # PADEL_ANALYSIS_RANGSCHIKKING_LINK_2026-09-26: link naar
            # de officiele TVL-rangschikking, bovenaan deze tab.
            _render_rangschikking_link(reeks_url)
            if report_for_ai is not None:
                oa.render_ranking_tab(report_for_ai)
            else:
                st.info("Nog geen rapport beschikbaar voor deze tegenploeg.")
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
