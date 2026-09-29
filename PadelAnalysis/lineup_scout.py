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
"Tegenstander analyseren") - maar dan met lookback=ALLE dit seizoen
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
pagina-render, de tweede aanroep hergebruikt nu de fixtures die de eerste
al ophaalde i.p.v. ze opnieuw te fetchen.

--------------------------------------------------------------------------
PADEL_ANALYSIS_FIRST_LOAD_DEDUPE_2026-09-28 (op verzoek van Kim: "laden van
opstellingsanalyse pagina zonder al ergens op te drukken duurt lang")
--------------------------------------------------------------------------
BEVESTIGD (door de code na te lezen, geen gok): _known_ranking_context()
deed bij ELKE pagina-render opnieuw exact hetzelfde werk dat
_render_volgende_match_and_scout() vlak daarvoor al had gedaan:
  - een 2e _get_saved_schedule(sel_player_id) (Firestore-read van het
    volledige poule-schema),
  - een 2e _get_saved_poule_url(sel_player_id),
  - een 2e ss.identify_own_ploeg_id() over datzelfde, volledige schema
    (de duurste stap: naam-matching over alle fixtures x alle eigen
    interclubmatchen).
Dat was pure duplicatie - geen bug in de uitkomst, wel dubbele kost op
exact de render waar Kim op wacht.

FIX (2 delen, beide hieronder):
  1. _known_ranking_context() wordt gememoiseerd per (player_id, label) in
     st.session_state, zodat ze binnen dezelfde sessie hoogstens EEN keer
     echt rekent i.p.v. bij elke rerun opnieuw. De memo wordt gewist door
     clear_known_ranking_context_cache(), die de bestaande "Ploeg opnieuw
     ophalen"-knop (page_lineup_lab.py) nu mee aanroept.
  2. page_lineup_lab() roept ze bovendien nog uitsluitend aan wanneer de
     scout de waarden NIET al gezet heeft (zie dat bestand) - dus in het
     normale geval waarin de analyse al geladen is, gebeurt dit werk
     helemaal niet meer.

--------------------------------------------------------------------------
PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_CACHE_2026-09-28 (op verzoek van Kim, na
een MEETSESSIE met perf_timing.py - geen gok meer, maar cijfers)
--------------------------------------------------------------------------
GEMETEN (2 opeenvolgende runs, paneel "Laadtijd-analyse"):
  - run 1: totaal 10.36s, waarvan 10.18s in _render_volgende_match_and_scout()
  - run 2: totaal 10.93s, waarvan 10.16s (92.9%) in _resolve_own_ploeg_id().
    ALLE andere stappen samen bleven onder 0.6s; osu.render_scout_header()
    kostte slechts 0.002s en was dus onterecht verdacht.

ROOT CAUSE (bevestigd in schedule_scraper.py): _resolve_own_ploeg_id()
roept ss.identify_own_ploeg_id() aan. Die functie loopt over de kandidaat-
fixtures en roept per kandidaat _fixture_player_sides() aan, die op zijn
beurt doet:
      from scraper_v2 import scrape_uitslagenblad
      data = scrape_uitslagenblad(requests.Session(), url)
Dat is een LIVE HTTP-scrape van het uitslagenblad, PER FIXTURE, telkens met
een VERSE requests.Session(). De loop stopt pas zodra home_score !=
away_score; bij een gelijke of lege uitkomst gaat hij naar de volgende
kandidaat en scrapet opnieuw. Vandaar ~10s.

Het resultaat is echter VOLLEDIG DETERMINISTISCH voor een gegeven speler +
schema: de eigen ploeg-ID verandert niet tussen twee page-loads. Toch werd
die hele scrape-loop bij ELKE render opnieuw uitgevoerd, want er zat
nergens een cache omheen.

FIX (bewust ENKEL in deze app-laag, NIET in schedule_scraper.py):
  - _cached_identify_own_ploeg_id() hieronder wikkelt
    ss.identify_own_ploeg_id() in @st.cache_data met een TTL van 24u. De
    cache-sleutel is (player_id, display_name, fixtures-handtekening),
    waarbij die handtekening enkel de velden bevat die de uitkomst kunnen
    beinvloeden (ploeg-ids/datum/score van de GESPEELDE fixtures, plus de
    datums van de eigen interclubmatchen). Wijzigt er een uitslag, dan
    wijzigt de handtekening en wordt automatisch opnieuw gerekend; blijft
    alles gelijk, dan kost dit 0s.
  - clear_identify_own_team_cache() wist deze cache. De knop "Ploeg opnieuw
    ophalen" (page_lineup_lab.py) bereikt ze via _clear_rank_caches().

BEWUST NIET AANGEPAST: schedule_scraper.py zelf (de verse Session per
fixture, en de loop over alle kandidaten). Die module wordt ook door de
nachtelijke GitHub Actions-prescan gebruikt, waar deze sessie net veel aan
gerepareerd is - een wijziging daar riskeert die werkende prescan-logica te
breken voor een winst die deze cache hier al volledig oplevert.

--------------------------------------------------------------------------
PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_PERSIST_2026-09-29 (op verzoek van Kim, na
een MEETSESSIE: na "Reboot app" kostte _resolve_own_ploeg_id() opnieuw
10.08s van de 11.14s)
--------------------------------------------------------------------------
PROBLEEM: de @st.cache_data-cache hierboven leeft enkel in het GEHEUGEN van
het Streamlit-proces. Na elke herstart (Reboot app, een nieuwe deploy na een
push, of een automatische herstart door Streamlit Cloud) is die leeg en
betaal je de volle ~10s live-scrape opnieuw. Dit was al voorzien in de
eerste analyse ("plus het resultaat persistent wegschrijven"), maar toen
niet gebouwd.
FIX: tweede cache-laag in Firestore, op het player_profiles-document van
de speler, veld OWN_TEAM_CACHE_FIELD:
      {"sig": <sha1 van de fixtures-handtekening>, "name": <display_name>,
       "result": <JSON van (home_ploeg_id, away_ploeg_id, matched_fx)>,
       "saved_at": <ISO-tijdstip>}
Volgorde binnen _cached_identify_own_ploeg_id():
  1. geheugen-cache (Streamlit)        -> ~0s
  2. Firestore, als sig EN naam matchen -> ~0.2s (1 profiel-read)
  3. anders: de echte scrape (~10s), en het resultaat wegschrijven.
Enkel een GELUKTE herkenning wordt weggeschreven (nooit (None, None, None)),
zodat een tijdelijke scrape-fout niet blijvend onthouden wordt. Wijzigt er
een uitslag, dan wijzigt de handtekening en is het opgeslagen resultaat
automatisch ongeldig.
"Ploeg opnieuw ophalen" forceert nog altijd een echte herberekening: de
knop verhoogt een force-token in de sessie; zolang dat token > 0 is, wordt
de Firestore-laag overgeslagen en het verse resultaat overschrijft het
opgeslagen resultaat.
"""

import datetime as _dt
import hashlib
import json

import streamlit as st

from dashboard_common import (
    fb, ll, ss, osu, oa, is_scraping_available, render_cloud_scrape_trigger,
    _parse_match_date, _format_scraped_at, _clean_name,
    _get_saved_poule_url, _save_poule_url, _get_saved_schedule,
    _load_poule_fixtures, _load_poule_schedule_robust, _official_current_rank,
)

# PADEL_ANALYSIS_PERF_TIMING_STAGE2_2026-09-28: de eerste meting wees
# 10.18s van de 10.36s toe aan _render_volgende_match_and_scout(). Deze
# versie meet de 4 substappen BINNEN die functie, zodat duidelijk wordt
# welke van hen de tijd opslorpt.
try:
    import perf_timing as perf
except Exception:  # noqa: BLE001  pragma: no cover
    class _PerfNoop:
        @staticmethod
        def step(_label):
            from contextlib import nullcontext
            return nullcontext()

    perf = _PerfNoop()

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


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_CACHE_2026-09-28
# Zie de module-docstring voor de gemeten root cause (10.16s van 10.93s).
# ─────────────────────────────────────────────
def _fixtures_signature(fixtures: list, own_interclub_matches: list) -> str:
    """Compacte handtekening van ALLES wat de uitkomst van
    identify_own_ploeg_id() kan beinvloeden. Verandert er niets aan de
    gespeelde uitslagen of aan de eigen matchdatums, dan blijft deze string
    identiek en mag het (dure) resultaat hergebruikt worden."""
    fx_part = sorted(
        "|".join([
            str(fx.get("home_ploeg_id") or ""),
            str(fx.get("away_ploeg_id") or ""),
            str(fx.get("date_text") or ""),
            str(fx.get("score") or ""),
            str(fx.get("match_id") or ""),
        ])
        for fx in (fixtures or [])
        if fx.get("played")
    )
    match_part = sorted(
        str(m.get("match_date") or "")
        for m in (own_interclub_matches or [])
        if m.get("match_type") == "interclub"
    )
    return json.dumps({"f": fx_part, "m": match_part}, sort_keys=True)


# PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_PERSIST_2026-09-29 - zie moduledocstring.
OWN_TEAM_CACHE_FIELD = "own_team_identify_cache"
_FORCE_TOKEN_KEY = "own_team_identify_force_token"


def _own_team_force_token() -> int:
    return int(st.session_state.get(_FORCE_TOKEN_KEY, 0) or 0)


def _signature_hash(signature: str) -> str:
    return hashlib.sha1(signature.encode("utf-8")).hexdigest()


def _read_persisted_own_team(player_id: str, display_name: str, sig_hash: str):
    """Geeft het opgeslagen resultaat terug als handtekening EN naam
    overeenkomen, anders None. Faalt stil - dan wordt gewoon herberekend."""
    try:
        prof = fb.get_player_profile(str(player_id)) or {}
        entry = prof.get(OWN_TEAM_CACHE_FIELD) or {}
        if entry.get("sig") != sig_hash or (entry.get("name") or "") != (display_name or ""):
            return None
        result = json.loads(entry.get("result") or "null")
        if not isinstance(result, list) or len(result) != 3:
            return None
        return tuple(result)
    except Exception:  # noqa: BLE001
        return None


def _write_persisted_own_team(player_id: str, display_name: str, sig_hash: str, result) -> None:
    """Schrijft een GELUKT resultaat weg. Faalt stil - de geheugen-cache
    werkt dan nog steeds, enkel de herstart-bescherming ontbreekt."""
    try:
        if not result or not any(result):
            return
        payload = {
            OWN_TEAM_CACHE_FIELD: {
                "sig": sig_hash,
                "name": display_name or "",
                "result": json.dumps(list(result), default=str),
                "saved_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
        }
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
    except Exception:  # noqa: BLE001
        pass


@st.cache_data(ttl=86400, show_spinner="Eigen ploeg bepalen (eenmalig)...")
def _cached_identify_own_ploeg_id(
    player_id: str, display_name: str, signature: str,
    fixtures_json: str, matches_json: str, force_token: int = 0,
):
    """Gecachete wrapper rond ss.identify_own_ploeg_id().

    Laag 1 = deze @st.cache_data (geheugen). Laag 2 = Firestore
    (PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_PERSIST_2026-09-29), overleeft een
    herstart van de app. Pas als beide missen, wordt echt gescrapet.

    `signature` doet het echte cache-werk; `fixtures_json`/`matches_json`
    dragen de data die de onderliggende functie nodig heeft. `force_token`
    > 0 slaat de Firestore-laag over (knop "Ploeg opnieuw ophalen"). Faalt
    de aanroep, dan geven we (None, None, None) terug - identiek aan het
    gedrag van de originele functie bij een mislukte herkenning."""
    sig_hash = _signature_hash(signature)
    if not force_token:
        persisted = _read_persisted_own_team(player_id, display_name, sig_hash)
        if persisted is not None:
            return persisted
    try:
        fixtures = json.loads(fixtures_json)
        own_interclub_matches = json.loads(matches_json)
        result = ss.identify_own_ploeg_id(
            fixtures, own_interclub_matches, own_display_name=display_name,
        )
    except Exception:  # noqa: BLE001
        return None, None, None
    _write_persisted_own_team(player_id, display_name, sig_hash, result)
    return result


def clear_identify_own_team_cache() -> None:
    """Wist de geheugen-cache van _cached_identify_own_ploeg_id() EN
    verhoogt het force-token, zodat de volgende aanroep ook de
    Firestore-laag overslaat en echt herberekent. Aangeroepen via
    _clear_rank_caches(), dus ook door de knop "Ploeg opnieuw ophalen"."""
    try:
        _cached_identify_own_ploeg_id.clear()
    except Exception:  # noqa: BLE001
        pass
    st.session_state[_FORCE_TOKEN_KEY] = _own_team_force_token() + 1


def _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches, own_display_name=None):
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"

    # PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_CACHE_2026-09-28: deze aanroep deed
    # een live uitslagenblad-scrape PER kandidaat-fixture en kostte gemeten
    # 10.16s bij ELKE render. Het resultaat is deterministisch, dus het
    # gaat nu door een cache met een handtekening op de gespeelde uitslagen.
    signature = _fixtures_signature(fixtures, own_interclub_matches)
    try:
        fixtures_json = json.dumps(fixtures, default=str, sort_keys=True)
        matches_json = json.dumps(own_interclub_matches, default=str, sort_keys=True)
    except Exception:  # noqa: BLE001 - nooit de app breken op serialisatie
        fixtures_json = matches_json = None

    if fixtures_json is not None and matches_json is not None:
        home_ploeg_id, away_ploeg_id, matched_fx = _cached_identify_own_ploeg_id(
            str(sel_player_id), own_display_name or "", signature,
            fixtures_json, matches_json, _own_team_force_token(),
        )
    else:
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


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_FIRST_LOAD_DEDUPE_2026-09-28
# ─────────────────────────────────────────────
_KNOWN_RANKING_MEMO_PREFIX = "known_ranking_ctx_v1_"


def clear_known_ranking_context_cache() -> None:
    """Wist de sessie-memo van _known_ranking_context(). Wordt aangeroepen
    door de "Ploeg opnieuw ophalen"-knop (page_lineup_lab.py), samen met de
    andere cache-wissers, zodat een bewuste verversing ook hier doorwerkt."""
    for key in [k for k in list(st.session_state) if str(k).startswith(_KNOWN_RANKING_MEMO_PREFIX)]:
        st.session_state.pop(key, None)


def _compute_known_ranking_context(sel_player_id: str, sel_label: str):
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
        # PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_CACHE_2026-09-28: ook dit pad
        # gaat nu door dezelfde cache - anders zou de Rangschikking-sectie
        # alsnog de volle ~10s scrape-loop betalen.
        try:
            signature = _fixtures_signature(saved_fixtures, own_interclub_matches)
            own_ploeg_id, _own_id2, _resolved = _cached_identify_own_ploeg_id(
                str(sel_player_id), sel_label or "", signature,
                json.dumps(saved_fixtures, default=str, sort_keys=True),
                json.dumps(own_interclub_matches, default=str, sort_keys=True),
                _own_team_force_token(),
            )
        except Exception:
            own_ploeg_id = None

    return reeks_url, (saved_fixtures or []), own_ploeg_id


def _known_ranking_context(sel_player_id: str, sel_label: str):
    """PADEL_ANALYSIS_RANKING_INDEPENDENT_OF_ANALYSIS_2026-09-27: bepaalt
    (reeks_url, fixtures, own_ploeg_id) UITSLUITEND op basis van reeds
    opgeslagen data, ONAFHANKELIJK van de "Volgende match laden"-knop of de
    volledige tegenstander-scout.

    PADEL_ANALYSIS_FIRST_LOAD_DEDUPE_2026-09-28: het resultaat wordt nu
    gememoiseerd per (player_id, label) in st.session_state. Voorheen deed
    deze functie bij ELKE rerun opnieuw een volledige _get_saved_schedule()
    + ss.identify_own_ploeg_id() over dat hele schema - werk dat
    _render_volgende_match_and_scout() vlak ervoor meestal al gedaan had.
    De uitkomst is identiek; enkel de herhaalde kost is weg. Gebruik
    clear_known_ranking_context_cache() om dit bewust te verversen."""
    memo_key = f"{_KNOWN_RANKING_MEMO_PREFIX}{sel_player_id}_{sel_label}"
    if memo_key in st.session_state:
        return st.session_state[memo_key]
    result = _compute_known_ranking_context(sel_player_id, sel_label)
    st.session_state[memo_key] = result
    return result


def _render_volgende_match_and_scout(sel_player_id: str, sel_label: str):
    st.markdown('<div class="section-header">Volgende match</div>', unsafe_allow_html=True)
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"

    with perf.step("  _render_schema_refresh_button"):
        _render_schema_refresh_button(sel_player_id)

    with perf.step("  _cached_own_full_doc (eigen spelersdocument)"):
        sel_doc = _cached_own_full_doc(str(sel_player_id))
    own_interclub_matches = [m for m in (sel_doc or {}).get("matches", []) if m.get("match_type") == "interclub"]

    def _finish(fixtures, reeks_url_val):
        with perf.step("  _resolve_own_ploeg_id (eigen-ploeg-herkenning)"):
            own_ploeg_id = _resolve_own_ploeg_id(
                sel_player_id, fixtures, own_interclub_matches, own_display_name=sel_label,
            )
        if not own_ploeg_id:
            # PADEL_ANALYSIS_PERF_TIMING_STAGE2_2026-09-28: maak zichtbaar
            # DAT hier afgebroken wordt - anders lijkt de pagina enkel
            # traag, terwijl ze in werkelijkheid ook nog eens niets
            # oplevert.
            st.caption("debug: gestopt in _finish() - own_ploeg_id kon niet bepaald worden.")
            return None
        st.session_state[f"vm_fixtures_{sel_player_id}"] = fixtures
        st.session_state[f"vm_own_ploeg_id_{sel_player_id}"] = own_ploeg_id
        with perf.step("  osu.render_scout_header (tegenstander ophalen)"):
            header_result = osu.render_scout_header(sel_player_id=str(sel_player_id), fixtures=fixtures, own_ploeg_id=own_ploeg_id)
        if not header_result:
            st.caption("debug: gestopt na render_scout_header() - geen bundle/opp teruggekregen.")
            return None
        bundle, opp = header_result
        return bundle, opp, reeks_url_val, opp.get("spelgroep_id")

    with perf.step("  _get_saved_schedule (poule-schema uit Firestore)"):
        saved_fixtures, sched_at = _get_saved_schedule(sel_player_id)
    if saved_fixtures:
        with perf.step("  _get_saved_poule_url"):
            reeks_url = _get_saved_poule_url(sel_player_id) or ""
        if sched_at:
            st.caption(f"Schema automatisch opgehaald (via de dagelijkse update) op {_format_scraped_at(sched_at)}.")
        with perf.step("  _render_manual_url_fallback"):
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
    opponent_scout_ui._run_scout_and_scrape() (bij "Tegenstander
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
        # consistentie en om een toekomstige duplicatie meteen te vermijden,
        # gebruikt ook dit de gedeelde cache-conventie.
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
    # PADEL_ANALYSIS_IDENTIFY_OWN_TEAM_CACHE_2026-09-28: de eigen-ploeg-
    # herkenning hoort bij een bewuste verversing ook opnieuw bepaald te
    # worden. Aparte try/except, zodat een fout hierboven dit niet
    # overslaat.
    clear_identify_own_team_cache()


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
