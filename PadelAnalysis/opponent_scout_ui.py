"""
opponent_scout_ui.py - UI-blok voor de tegenstander-analyse bij 'Volgende match'.
Doel van dit bestand:
- 2026-09-09 (v1): de tussenstap verdwijnt. Na een klik op 'Tegenstander
  analyseren' wordt de opstelling van de tegenstander opgezocht EN worden de
  nog onbekende spelers meteen gescrapet, in een doorlopende
  voortgangsweergave (st.status).
- 2026-09-09 (v2): het volledige teamanalysescherm zit in
  opponent_analysis.render_team_analysis() (overzichtstabel, opstelling-editor,
  AI-sectie). Dit bestand geeft er spelgroep_id, home_player_id en een brede
  cache van alle gekende spelersdocumenten aan door.
PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14 (v3, op verzoek van Kim):
Kim wil de Opstelling-scenario's + AI-functies (dashboard.py) BOVENAAN de
pagina tonen, en pas DAARONDER de overzichtstabel/detail-per-speler van de
tegenploeg. Opgesplitst in render_scout_header() + prepare_team_docs().
render_scout_block() blijft bestaan als dunne wrapper voor eventuele andere/
toekomstige aanroepers.
Op Streamlit Community Cloud kan de app zelf niet scrapen (geen Playwright/
browser). Daar wordt een achtergrondtaak getriggerd in plaats van een lokale
scrape.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG/ONTBREKENDE STAP (opgelost): na het toevoegen van een tegenstander-ploeg
(bv. via een handmatig ingegeven poule-URL, zie manual_poule_input.py) bleven
verschillende speelsters onvolledig: geen padelstat playing strength, soms
NUL matchhistoriek, bij sommigen ook geen huidig klassement. "Verversen"
loste dit niet op. Drie samenvallende oorzaken:
  1. _run_scout_and_scrape() riep NERGENS de padelstats.be-scraper aan.
  2. scrape_new_opponent_players() (opponent_scout.py) scrapet UITSLUITEND
     spelers zonder bestaand profiel.
  3. lookback_periods stond hardcoded op 1 (enkel de huidige periode).
Fix: een nieuwe, expliciete "Ververs alles voor deze ploeg"-knop
(render_team_refresh_button) die voor ALLE spelers in de tegenstander-
roster matchdata/padelstat/klassement herhaalt, ongeacht een bestaand
profiel.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17 (op verzoek van Kim,
"we draaien in rondjes")
--------------------------------------------------------------------------
BUG (opgelost, kritiek): _run_full_team_refresh() riep voorheen aan:
    fb.save_player_profile(pid, display_name=naam)
Zoals uitgebreid toegelicht in de moduledocstring van opponent_scout.py:
firebase_service.save_player_profile() zet "club" altijd expliciet in de
payload (als None bij ontbreken), en merge=True beschermt enkel velden die
NIET in de payload staan — dus een reeds bekende club werd bij ELKE klik op
"🔄 Ververs alles voor deze ploeg" stilzwijgend overschreven naar leeg.
Bovendien kreeg een via deze weg aangemaakt/aangeraakt profiel nooit een
"added_by"-marker, waardoor cleanup_ghost_profiles.py deze spelers niet kon
onderscheiden van bewust, handmatig toegevoegde spelers.
Fix: _run_full_team_refresh() gebruikt nu dezelfde
osc._ensure_profile_safe()-helper als opponent_scout.py
(scrape_new_opponent_players()), zodat club behouden blijft en added_by
consistent gezet wordt — één bron van waarheid voor deze logica i.p.v. ze
hier te dupliceren.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLOUD_KLASSEMENT_PADELSTAT_TRIGGER_2026-09-17 (op verzoek van
Kim: "moet wel werken via github actions... bekijk dat eens van dichterbij")
--------------------------------------------------------------------------
BUG (opgelost, kritiek): op Streamlit Cloud (waar Kim uitsluitend test) was
er GEEN ENKELE manier om klassement of padelstat onmiddellijk te forceren
voor een specifieke tegenstander-ploeg. Fix: directe trigger-knoppen voor
klassement/padelstat, elk met de EXACTE tegenstander-roster als 'player'-
input, zodat je niet op de achtergrond-cron hoeft te wachten.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19 (op verzoek van
Kim: "Padelstat cijfers zouden wel scheduled moeten updaten. Ik wil dat wel
1 keer per week op maandag maar ook als je op analyse ploeg drukt om zeker
de laatste waarde te hebben wanneer je dat doet.")
--------------------------------------------------------------------------
FIX: _run_scout_and_scrape() roept nu, ONVOORWAARDELIJK en ALTIJD (niet
enkel voor nog-onbekende spelers), een GEFORCEERDE padelstat-verversing aan
voor de volledige tegenstander-roster, zodra die gekend is — zie
PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19 hieronder voor een
BELANGRIJKE correctie hierop.
--------------------------------------------------------------------------
PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19 (op verzoek van Kim,
zie chat 2026-09-19): splitst de tegenstander-roster op in "al gekende" en
"gloednieuwe" spelers, zodat de padelstat-trigger nooit een lege doelgroep
meer krijgt voor een compleet nieuwe ploeg.
--------------------------------------------------------------------------
PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_2026-09-19 (op verzoek van Kim): alle
zichtbare teksten herzien, geen vermelding meer van "GitHub Actions"/
"deze omgeving kan niet scrapen" enz. Interne code-commentaren blijven wél
technisch correct.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C, op verzoek van Kim):
_render_unified_team_sync_trigger() vervangt de vroegere 3 losse knoppen
door ÉÉN knop die zichzelf herlabelt op basis van _data_completeness().
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19 (op verzoek van Kim):
_ensure_padelstat(), _ensure_fresh_padelstat_for_roster(),
_run_full_team_refresh() en _render_unified_team_sync_trigger() accepteren
nu allemaal een optionele `team_name`-parameter als disambiguatie-hint.
--------------------------------------------------------------------------
PADEL_ANALYSIS_FALSE_MISSING_ON_READ_ERROR_FIX_2026-09-19 (op verzoek van
Kim): _data_completeness() onderscheidt nu een BEVESTIGD ontbrekend gegeven
van een MISLUKTE controle ("*_uncertain"), i.p.v. een leesfout ten onrechte
als "ontbreekt echt" te melden.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21 (op verzoek van Kim):
optionele checkbox "Ook forceren voor spelers die al volledig leken",
standaard uit, om klassement voor de VOLLEDIGE roster te herverversen i.p.v.
enkel de gedetecteerde onvolledige subset.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26 (op verzoek van Kim: "ik heb nu
al 3 fixes gedaan voor snelheid [...] graag alles ineens"):
_is_known() deed 2 ongecachete Firestore-reads PER SPELER, ONVOORWAARDELIJK
bij ELKE Streamlit-rerun via _unknown_players() in prepare_team_docs(). Nu
gecacht via _cached_is_known() (@st.cache_data ttl=300).
--------------------------------------------------------------------------
PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26 (op verzoek van Kim):
_data_completeness() deed 3 Firestore-reads PER SPELER, ONVOORWAARDELIJK bij
ELKE rerun. Nu gecacht (@st.cache_data ttl=300).
--------------------------------------------------------------------------
PADEL_ANALYSIS_OPPONENT_DOCS_CACHE_2026-09-26: all_docs in prepare_team_docs()
gaat nu door _cached_docs_for_players() (@st.cache_data ttl=300) i.p.v.
rechtstreeks ll.get_docs_for_players() bij elke rerun.
--------------------------------------------------------------------------
PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27 (op verzoek van Kim, na
analyse i.s.m. opponent_scout.py: "ik wil snelheid verbeteren [...] pas aan
waar nodig")
--------------------------------------------------------------------------
CONTEXT: opponent_scout._known_matches_total() (aangeroepen binnen
osc.scout_opponent(), vóór dit bestand prepare_team_docs() uitvoert) deed
voorheen een ONGECACHETE fb.get_player()-call per tegenstander-speler - kort
daarna haalt prepare_team_docs() via _cached_docs_for_players() een
vergelijkbare Firestore-read op voor diezelfde spelers (5 min Streamlit-
gecacht, maar bij een EERSTE analyse nog leeg). Dat was een reële, dubbele
Firestore-read per speler bij een nieuwe tegenstander.
FIX (in opponent_scout.py): _known_matches_total() heeft nu een eigen 300s-
TTL-cache (bewust GEEN st.cache_data, want opponent_scout.py moet ook buiten
Streamlit bruikbaar blijven - zie die moduledocstring). Dit bestand roept nu,
naast de bestaande cache-clears (_load_all_player_docs, _cached_is_known,
_data_completeness, _cached_docs_for_players), ook
osc.clear_known_matches_cache() aan op exact dezelfde plekken, zodat een net
gescrapete/ververste speler nergens tot 5 minuten een verouderd
"known_matches_total" laat zien.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Callable, Optional
import streamlit as st
import firebase_service as fb
import lineup_lab as ll
import opponent_analysis as oa
import opponent_scout as osc
import schedule_scraper as ss
try:  # cloud_helpers is optioneel aanwezig; nooit hard falen op import
    from cloud_helpers import (
        is_scraping_available,
        trigger_github_actions_scrape,
        is_github_trigger_configured,
        # PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19: hergebruikt voor de
        # nieuwe, gecombineerde "ontbrekende gegevens ophalen"-knop hieronder.
        _render_tracked_progress,
        DEFAULT_WORKFLOW_FILE,
        KLASSEMENT_WORKFLOW_FILE,
    )
except Exception:  # pragma: no cover
    def is_scraping_available() -> bool:
        return False
    def trigger_github_actions_scrape(**_kwargs):
        return False, "cloud_helpers ontbreekt"
    def is_github_trigger_configured() -> bool:
        return False
    def _render_tracked_progress(*_args, **_kwargs):
        return {"found": False, "status": "unknown"}
    DEFAULT_WORKFLOW_FILE = "scrape-padel.yml"
    KLASSEMENT_WORKFLOW_FILE = "refresh-klassement.yml"
# PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16: optionele import, zodat dit
# bestand blijft werken ook als padelstats_scraper (Playwright-afhankelijk)
# lokaal niet beschikbaar is -- exact hetzelfde patroon als cloud_helpers.
try:
    import padelstats_scraper as pss
except Exception:  # pragma: no cover
    pss = None
# PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19: naam van de
# padelstat-achtergrondtaak, zelfde als in cloud_helpers.py.
PADELSTAT_WORKFLOW_FILE = "refresh-padelstat.yml"


@st.cache_data(ttl=300, show_spinner=False)
def _load_all_player_docs() -> dict:
    """Bredere set van ALLE gekende spelersdocumenten (niet enkel de
    tegenstander-roster), gebruikt als 'global_docs' voor de opportunistische
    ranking-fallback in opponent_dossier. Klein en goedkoop bij het huidige
    aantal spelers; 5 minuten gecached om herhaalde Firestore-reads binnen
    dezelfde sessie te vermijden."""
    try:
        docs = fb.db.collection(fb.PLAYERS_COLLECTION).stream()
        return {d.id: (d.to_dict() or {}) for d in docs}
    except Exception:
        return {}


def load_all_player_docs() -> dict:
    """Publieke naam voor _load_all_player_docs(), zodat dashboard.py dit kan
    hergebruiken zonder een 'privé' (underscore-prefix) functie rechtstreeks
    aan te spreken."""
    return _load_all_player_docs()


def _is_known(player_id: str) -> bool:
    """Een speler geldt als gekend zodra er matchdata OF een profiel bestaat.
    PADEL_ANALYSIS_KNOWN_PLAYER_FIX_2026-09-09: enkel op get_player_profile()
    controleren was te streng."""
    try:
        if fb.get_player_profile(player_id):
            return True
    except Exception:
        pass
    try:
        doc = fb.get_player(player_id) or {}
        return bool(doc.get("matches"))
    except Exception:
        return False


# PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26: zie moduledocstring.
@st.cache_data(ttl=300, show_spinner=False)
def _cached_is_known(player_id: str) -> bool:
    return _is_known(player_id)


def clear_is_known_cache() -> None:
    """Leegt de cache hierboven. Aan te roepen na elke geslaagde sync-actie
    voor de tegenstander-roster, zodat een net gescrapete speler niet tot
    5 minuten als 'nog onbekend' blijft gelden."""
    try:
        _cached_is_known.clear()
    except Exception:
        pass


def _unknown_players(bundle: dict) -> list[dict]:
    return [
        player
        for player in (bundle.get("unique_players", []) or [])
        if not _cached_is_known(player["user_id"])
    ]


# PADEL_ANALYSIS_DATA_COMPLETENESS_CACHE_2026-09-26: zie moduledocstring.
@st.cache_data(ttl=300, show_spinner=False)
def _data_completeness(player_id: str) -> dict:
    """PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19: GESTRUCTUREERDE versie
    van de vroegere _has_incomplete_data() — geeft per CATEGORIE
    (matchdata/klassement/padelstat) een boolean terug.
    PADEL_ANALYSIS_FALSE_MISSING_ON_READ_ERROR_FIX_2026-09-19: onderscheidt
    een BEVESTIGD ontbrekend gegeven van een MISLUKTE controle
    ("*_uncertain")."""
    doc, doc_ok = {}, True
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:
        doc, doc_ok = {}, False
    profile, profile_ok = {}, True
    try:
        profile = fb.get_player_profile(player_id) or {}
    except Exception:
        profile, profile_ok = {}, False
    matchdata_present = bool(doc.get("matches"))
    missing_matchdata = doc_ok and not matchdata_present
    matchdata_uncertain = (not doc_ok) and not matchdata_present
    klassement_present = bool(doc.get("klassement_history") or profile.get("klassement_history"))
    klassement_fully_checked = doc_ok and profile_ok
    missing_klassement = klassement_fully_checked and not klassement_present
    klassement_uncertain = (not klassement_fully_checked) and not klassement_present
    try:
        cached = fb.get_padelstat_rating(player_id)
        padelstat_present = bool(cached and cached.get("rating") is not None)
        missing_padelstat = not padelstat_present
        padelstat_uncertain = False
    except Exception:
        missing_padelstat = False
        padelstat_uncertain = True
    return {
        "missing_matchdata": missing_matchdata,
        "missing_klassement": missing_klassement,
        "missing_padelstat": missing_padelstat,
        "matchdata_uncertain": matchdata_uncertain,
        "klassement_uncertain": klassement_uncertain,
        "padelstat_uncertain": padelstat_uncertain,
    }


def _has_incomplete_data(player_id: str) -> tuple[bool, list[str]]:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16. Dunne wrapper rond
    _data_completeness() (leesbare-tekst-variant)."""
    c = _data_completeness(player_id)
    redenen = []
    if c["missing_matchdata"]:
        redenen.append("geen matchhistoriek")
    elif c.get("matchdata_uncertain"):
        redenen.append("matchhistoriek kon niet gecontroleerd worden (probeer later opnieuw)")
    if c["missing_klassement"]:
        redenen.append("geen klassementshistoriek")
    elif c.get("klassement_uncertain"):
        redenen.append("klassementshistoriek kon niet gecontroleerd worden (probeer later opnieuw)")
    if c["missing_padelstat"]:
        redenen.append("geen padelstat playing strength")
    elif c.get("padelstat_uncertain"):
        redenen.append("playing strength kon niet gecontroleerd worden (probeer later opnieuw)")
    return bool(redenen), redenen


def _ensure_klassement(player_ids: list[str], progress_label: str = "Klassement") -> None:
    """Haalt de klassementshistoriek op voor spelers die deze nog niet hebben.
    Enkel lokaal (Playwright vereist, zie is_scraping_available())."""
    if not is_scraping_available():
        st.caption(
            "📈 Klassementshistoriek wordt automatisch op de achtergrond opgehaald, of forceer "
            "het meteen met de knop '📈 Klassement nu ophalen voor deze ploeg' hierboven."
        )
        return
    to_fetch = []
    for pid in player_ids:
        try:
            prof = fb.get_player_profile(pid) or {}
        except Exception:
            prof = {}
        try:
            doc = fb.get_player(pid) or {}
        except Exception:
            doc = {}
        if not (doc.get("klassement_history") or prof.get("klassement_history")):
            to_fetch.append(pid)
    if not to_fetch:
        return
    try:
        from scrape_klassement import scrape_klassement, klassement_to_history_summary, extract_niveau_winrates
    except Exception as exc:
        st.caption("Klassement automatisch ophalen is momenteel niet beschikbaar.")
        return
    progress = st.progress(0.0, text=f"{progress_label}: starten...")
    for i, pid in enumerate(to_fetch, start=1):
        progress.progress(i / len(to_fetch), text=f"{progress_label}: speler {i}/{len(to_fetch)}...")
        try:
            periods = scrape_klassement(str(pid))
            history = klassement_to_history_summary(periods)
            niveau_winrates = extract_niveau_winrates(periods)
            klass_data = {
                "history": history,
                "niveau_winrates": niveau_winrates,
                "raw_periods": periods,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(payload, merge=True)
            fb.db.collection(fb.PLAYERS_COLLECTION).document(str(pid)).set(payload, merge=True)
        except Exception as exc:
            st.write(f"Klassement ophalen mislukt voor speler {pid}.")
    progress.progress(1.0, text=f"{progress_label}: klaar.")
    _load_all_player_docs.clear()
    # PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27: klassement raakt ook
    # "doc" (players-collectie) aan via de payload hierboven; leeg ook de
    # known-matches-cache zodat een volgende scout_opponent()-aanroep de
    # verse data ziet i.p.v. tot 5 minuten een oude waarde.
    osc.clear_known_matches_cache()


def _ensure_padelstat(
    players: list[dict],
    progress_label: str = "Padelstat",
    force: bool = False,
    team_name: Optional[str] = None,
) -> dict:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16.
    Haalt de padelstats.be playing strength op voor elke speler in `players`.
    Slaat spelers met een gecachete rating over, tenzij force=True.
    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: optionele
    `team_name`-parameter als FALLBACK-disambiguatiehint."""
    result = {"opgehaald": 0, "cache": 0, "niet_gevonden": 0, "fout": 0}
    if not is_scraping_available() or pss is None:
        st.caption(
            "Playing strength wordt automatisch op de achtergrond opgehaald, of forceer het "
            "meteen met de knop '🎯 Playing strength nu ophalen voor deze ploeg' hierboven."
        )
        return result
    te_doen = []
    for p in players:
        pid = str(p["user_id"])
        if not force:
            try:
                cached = fb.get_padelstat_rating(pid)
            except Exception:
                cached = None
            if cached and cached.get("rating") is not None:
                result["cache"] += 1
                continue
        te_doen.append(p)
    if not te_doen:
        return result
    progress = st.progress(0.0, text=f"{progress_label}: starten...")
    for i, p in enumerate(te_doen, start=1):
        pid = str(p["user_id"])
        naam = p.get("name") or pid
        progress.progress(i / len(te_doen), text=f"{progress_label}: {naam} ({i}/{len(te_doen)})...")
        try:
            profiel = fb.get_player_profile(pid) or {}
        except Exception:
            profiel = {}
        existing_club = profiel.get("club") or ""
        club = existing_club or (team_name or "")
        try:
            gevonden = pss.search_and_fetch_padelstat_rating(naam, club=club or None)
        except Exception as exc:
            st.write(f"Playing strength ophalen mislukt voor {naam}.")
            result["fout"] += 1
            continue
        if not gevonden or gevonden.get("rating") is None:
            st.write(f"Geen playing strength gevonden voor {naam}.")
            result["niet_gevonden"] += 1
            continue
        try:
            fb.save_padelstat_rating(
                pid,
                gevonden.get("padelstat_id", ""),
                gevonden.get("rating"),
                gevonden.get("rating_source", "none"),
                gevonden.get("raw_text_snippet", ""),
            )
            result["opgehaald"] += 1
            if gevonden.get("club_disambiguation_note"):
                st.caption(f"⚠️ {naam}: club niet met zekerheid bevestigd.")
        except Exception as exc:
            st.write(f"Playing strength opslaan mislukt voor {naam}.")
            result["fout"] += 1
    progress.progress(1.0, text=f"{progress_label}: klaar.")
    return result


def _ensure_fresh_padelstat_for_roster(
    unique_players: list[dict], auto_scrape: bool, team_name: Optional[str] = None,
) -> None:
    """PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19: garandeert
    dat elke "Tegenstander analyseren"-klik een GEFORCEERDE padelstat-
    verversing aanvraagt voor de volledige tegenstander-roster."""
    if not unique_players:
        return
    if auto_scrape:
        st.write("Playing strength verversen (garandeert de meest recente waarde)...")
        _ensure_padelstat(unique_players, progress_label="Padelstat", force=True, team_name=team_name)
        return
    player_ids_csv = ",".join(str(p["user_id"]) for p in unique_players if p.get("user_id"))
    if not player_ids_csv:
        return
    inputs = {"player": player_ids_csv, "max": str(len(unique_players)), "force_all": "true"}
    if team_name:
        inputs["club"] = team_name
    ok, msg = trigger_github_actions_scrape(
        workflow_file=PADELSTAT_WORKFLOW_FILE,
        inputs=inputs,
    )
    if ok:
        st.write(f"🎯 Playing strength-verversing gestart voor {len(unique_players)} speler(s) (meestal 1-3 min).")
    else:
        st.write("⚠️ Playing strength-verversing kon niet gestart worden.")


def _run_scout_and_scrape(
    fixtures: list[dict],
    opp: dict,
    next_match: dict,
    lookback: int,
    auto_scrape: bool,
    fetch_klassement: bool,
) -> dict:
    """Zoekt de opstelling op, scrapet meteen de onbekende spelers en haalt
    optioneel ook de klassementshistoriek op. Dit blijft het SNELLE
    standaardpad (enkel nieuwe/onbekende spelers, 1 periode terug)."""
    with st.status("Tegenstander analyseren...", expanded=True) as status:
        st.write("Vorige wedstrijd(en) van de tegenstander opzoeken...")
        bundle = osc.scout_opponent(
            fixtures,
            opp["name"],
            opp["ploeg_id"],
            next_match["date_text"],
            lookback=lookback,
        )
        if bundle.get("note"):
            st.write(bundle["note"])
            status.update(label="Analyse afgerond (beperkte data)", state="complete")
            return bundle
        found = len(bundle.get("unique_players", []) or [])
        st.write(f"{found} tegenstander-speler(s) gevonden.")
        unknown = _unknown_players(bundle)
        if unknown:
            if not auto_scrape:
                st.write(
                    f"{len(unknown)} speler(s) nog niet volledig gekend — hun matchdata en playing "
                    "strength worden automatisch samen opgehaald zodra je hieronder 'Nieuwe "
                    "tegenstanders ophalen' gebruikt."
                )
            else:
                st.write(f"{len(unknown)} nieuwe speler(s) scrapen...")
                progress = st.progress(0.0, text="Starten...")
                def _callback(index: int, total: int, name: str) -> None:
                    fraction = index / total if total else 0.0
                    progress.progress(fraction, text=f"({index}/{total}) {name} scrapen...")
                try:
                    result = osc.scrape_new_opponent_players(
                        unknown, lookback_periods=1, delay=1.5, progress_callback=_callback,
                    )
                    progress.progress(1.0, text="Klaar.")
                    scraped = len(result.get("newly_scraped", []) or [])
                    failed = result.get("failed", []) or []
                    st.write(f"{scraped} gescrapet, {len(failed)} mislukt.")
                    for item in failed:
                        st.write(f"Mislukt: {item.get('name')}")
                    # PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27: net
                    # gescrapete spelers hebben nu nieuwe matchdata - hun
                    # eventueel eerder gecachete known_matches_total (0, bij
                    # een gloednieuwe speler) mag hier niet blijven hangen.
                    osc.clear_known_matches_cache()
                except Exception as exc:
                    progress.empty()
                    st.write("Scrapen mislukt.")
        else:
            st.write("Alle spelers zijn al gekend qua matchdata.")
        if fetch_klassement:
            st.write("Klassementshistoriek controleren/ophalen (enkel voor NOG NIET gekende spelers)...")
            all_ids = [p["user_id"] for p in bundle.get("unique_players", []) or []]
            _ensure_klassement(all_ids, progress_label="Klassement")
        all_players = bundle.get("unique_players", []) or []
        unknown_ids = {p["user_id"] for p in unknown}
        known_players = [p for p in all_players if p["user_id"] not in unknown_ids]
        _ensure_fresh_padelstat_for_roster(known_players, auto_scrape=auto_scrape, team_name=opp.get("name"))
        status.update(label="Analyse afgerond", state="complete")
        return bundle


def _run_full_team_refresh(
    unique_players: list[dict],
    lookback_periods: int = 3,
    force: bool = False,
    team_name: Optional[str] = None,
) -> dict:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16. Voor ELKE speler in
    unique_players (ongeacht een reeds bestaand profiel): matchdata
    herscrapen, padelstat ophalen/vernieuwen, klassement ophalen/vernieuwen
    (enkel indien nog niet gekend)."""
    from scrape_player import scrape_player  # lazy: Playwright, zie osc.py
    result = {
        "totaal": len(unique_players),
        "matchdata_ok": 0,
        "matchdata_fout": [],
        "padelstat": {},
        "klassement_gestart": False,
    }
    st.write(f"Matchdata verversen voor {len(unique_players)} speler(s) (tot {lookback_periods} periode(s) terug)...")
    progress = st.progress(0.0, text="Starten...")
    for i, p in enumerate(unique_players, start=1):
        pid = str(p["user_id"])
        naam = p.get("name") or pid
        progress.progress(i / len(unique_players), text=f"({i}/{len(unique_players)}) {naam}...")
        try:
            scrape_player(
                pid,
                max_new_periods=lookback_periods,
                force_full_refresh=force,
                save_to_firebase=True,
            )
            osc._ensure_profile_safe(pid, naam)
            result["matchdata_ok"] += 1
        except Exception as exc:
            result["matchdata_fout"].append({"name": naam, "error": str(exc)})
    progress.progress(1.0, text="Matchdata: klaar.")
    st.write("Playing strength ophalen/vernieuwen...")
    result["padelstat"] = _ensure_padelstat(unique_players, progress_label="Padelstat", force=force, team_name=team_name)
    st.write("Klassementshistoriek ophalen/vernieuwen (enkel voor nog niet gekende spelers)...")
    all_ids = [p["user_id"] for p in unique_players]
    _ensure_klassement(all_ids, progress_label="Klassement")
    result["klassement_gestart"] = True
    # PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27: matchdata is hierboven
    # (mogelijk) herscraped voor de VOLLEDIGE roster - leeg de cache zodat
    # een volgende analyse van deze ploeg de verse known_matches_total ziet.
    osc.clear_known_matches_cache()
    return result


def _render_unified_team_sync_trigger(
    unique_players: list[dict], key_prefix: str, team_name: Optional[str] = None,
) -> dict:
    """PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C): ÉÉN
    GECOMBINEERDE knop i.p.v. 3 losse knoppen, die zichzelf herlabelt op
    basis van _data_completeness() per speler.
    PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21: optionele
    "forceer alles"-checkbox."""
    if not unique_players:
        return {}
    all_ids = [str(p["user_id"]) for p in unique_players if p.get("user_id")]
    if not all_ids:
        return {}
    completeness = {pid: _data_completeness(pid) for pid in all_ids}
    missing_matchdata_ids = [
        pid for pid in all_ids
        if completeness[pid]["missing_matchdata"] or completeness[pid].get("matchdata_uncertain")
    ]
    missing_klassement_ids = [
        pid for pid in all_ids
        if completeness[pid]["missing_klassement"] or completeness[pid].get("klassement_uncertain")
    ]
    n_incomplete = len({
        pid for pid in all_ids
        if completeness[pid]["missing_matchdata"] or completeness[pid]["missing_klassement"]
        or completeness[pid]["missing_padelstat"] or completeness[pid].get("matchdata_uncertain")
        or completeness[pid].get("klassement_uncertain") or completeness[pid].get("padelstat_uncertain")
    })
    if n_incomplete:
        label = f"🔄 Ontbrekende gegevens ophalen ({n_incomplete} van {len(all_ids)} speler(s))"
        help_text = (
            "Haalt in 1 stap de nog ontbrekende wedstrijdgegevens, klassement en playing strength "
            "op voor deze ploeg. Wedstrijdgegevens en playing strength worden hoe dan ook voor de "
            "VOLLEDIGE roster gecontroleerd/ververst; enkel klassement richt zich standaard op de "
            f"{n_incomplete} speler(s) die nog effectief onvolledig zijn."
        )
    else:
        label = "🔄 Controleren op nieuwe wedstrijden"
        help_text = (
            "Deze ploeg is al volledig gekend. Controleert enkel of er intussen nieuwe "
            "wedstrijden bijkwamen (playing strength wordt sowieso al automatisch bij elke "
            "analyse ververst)."
        )
    force_all_players = False
    n_already_complete = len(all_ids) - n_incomplete
    if n_incomplete and n_already_complete:
        force_all_players = st.checkbox(
            "🔁 Ook forceren voor spelers die al volledig leken (bv. na een gewijzigde ploegsituatie)",
            value=False, key=f"{key_prefix}_force_all_sync",
            help=(
                "Standaard wordt klassement enkel opnieuw gecontroleerd voor spelers waarvoor dat "
                "nog ontbreekt of onzeker is. Vink dit aan om klassement voor ALLE "
                f"{len(all_ids)} speler(s) van deze ploeg opnieuw te laten controleren/verversen, "
                "ook wie al volledig leek — handig als de situatie van de ploeg intussen "
                "zichtbaar veranderd is (bv. ze speelden ondertussen matchen)."
            ),
        )
        if force_all_players:
            label = f"🔄 Ontbrekende gegevens ophalen (+ alles forceren voor {len(all_ids)} speler(s))"
    if not is_github_trigger_configured():
        return {"missing_matchdata": len(missing_matchdata_ids), "missing_klassement": len(missing_klassement_ids)}
    if st.button(label, key=f"{key_prefix}_unified_sync", type="primary", help=help_text):
        t0 = time.time()
        ok_match, _ = trigger_github_actions_scrape(player_ids=",".join(all_ids), mode="missing")
        ph_match = st.empty()
        if ok_match:
            _render_tracked_progress(DEFAULT_WORKFLOW_FILE, t0, ph_match, label_prefix="Wedstrijdgegevens: ")
        else:
            ph_match.error("Wedstrijdgegevens: kon niet gestart worden.")
        klassement_target_ids = all_ids if force_all_players else missing_klassement_ids
        if klassement_target_ids:
            t1 = time.time()
            ok_k, _ = trigger_github_actions_scrape(
                workflow_file=KLASSEMENT_WORKFLOW_FILE,
                inputs={
                    "player": ",".join(klassement_target_ids),
                    "max": str(len(klassement_target_ids)),
                    "force_all": "true" if force_all_players else "false",
                },
            )
            ph_k = st.empty()
            if ok_k:
                _render_tracked_progress(KLASSEMENT_WORKFLOW_FILE, t1, ph_k, label_prefix="Klassement: ")
            else:
                ph_k.error("Klassement: kon niet gestart worden.")
        t2 = time.time()
        padelstat_inputs = {"player": ",".join(all_ids), "max": str(len(all_ids)), "force_all": "true"}
        if team_name:
            padelstat_inputs["club"] = team_name
        ok_p, _ = trigger_github_actions_scrape(
            workflow_file=PADELSTAT_WORKFLOW_FILE,
            inputs=padelstat_inputs,
        )
        ph_p = st.empty()
        if ok_p:
            _render_tracked_progress(PADELSTAT_WORKFLOW_FILE, t2, ph_p, label_prefix="Playing strength: ")
        else:
            ph_p.error("Playing strength: kon niet gestart worden.")
        _load_all_player_docs.clear()
        try:
            import freshness_cache as fcache
            fcache.invalidate_all()
        except Exception:
            pass
        try:
            _data_completeness.clear()
        except Exception:
            pass
        clear_opponent_docs_cache()
        clear_is_known_cache()
        # PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27: idem voor de nieuwe
        # _known_matches_total()-cache in opponent_scout.py - anders blijft
        # een net gescrapete/ververste speler tot 5 minuten een verouderd
        # "known_matches_total" tonen ondanks deze expliciete sync-actie.
        osc.clear_known_matches_cache()
        st.rerun()
    return {"missing_matchdata": len(missing_matchdata_ids), "missing_klassement": len(missing_klassement_ids)}


def render_scout_header(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    lookback: int = 1,
) -> Optional[tuple[dict, dict]]:
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: toont enkel de
    'volgende match'-titel, de klassement-checkbox en de 'Tegenstander
    analyseren'-knop; voert desgevallend scout+scrape+klassement-ophaal uit.
    Geeft (bundle, opp) terug zodra een bundle beschikbaar is, anders None."""
    team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id)
    next_match = ss.get_next_match(team_fixtures)
    if not next_match:
        st.success("Geen nog te spelen wedstrijden gevonden voor dit schema.")
        return None
    opp = ss.opponent_of(next_match, own_ploeg_id)
    opp["spelgroep_id"] = next_match.get("spelgroep_id")
    st.markdown(
        f"**{next_match['date_text']}** - tegen **{opp['name']}** "
        f"({next_match.get('poule_label', '')})"
    )
    scout_key = f"scout_{opp['ploeg_id']}_{next_match['date_text']}"
    can_scrape = is_scraping_available()
    fetch_klassement = False
    if not can_scrape:
        st.caption(
            "Nieuwe spelers en klassement worden automatisch op de achtergrond opgehaald, of "
            "forceer dat hieronder direct voor deze ploeg. Playing strength wordt bij elke "
            "analyse altijd automatisch geforceerd ververst voor spelers die al gekend zijn."
        )
    else:
        fetch_klassement = st.checkbox(
            "📈 Ook klassementshistoriek ophalen voor nog onbekende spelers (lokaal, ±30-60s per speler)",
            value=True, key=f"fetch_klassement_{sel_player_id}",
        )
    col_scout, col_refresh = st.columns([2, 2])
    with col_scout:
        if st.button("🔍 Tegenstander analyseren", key=f"btn_scout_{sel_player_id}", type="primary"):
            st.session_state[scout_key] = _run_scout_and_scrape(
                fixtures, opp, next_match, lookback,
                auto_scrape=can_scrape, fetch_klassement=fetch_klassement,
            )
    bundle = st.session_state.get(scout_key)
    with col_refresh:
        if bundle and bundle.get("unique_players") and can_scrape:
            if st.button(
                "🔄 Ververs alles voor deze ploeg",
                key=f"btn_full_refresh_{sel_player_id}",
                help=(
                    "Herhaalt matchdata (meerdere periodes) en playing strength voor ALLE spelers "
                    "van deze ploeg, ook wie al een (onvolledig) profiel heeft. Klassement enkel "
                    "voor wie dat nog nooit had. Trager dan 'Tegenstander analyseren', maar slaat "
                    "niemand over."
                ),
            ):
                with st.status("Volledige ploeg verversen...", expanded=True) as status:
                    refresh_result = _run_full_team_refresh(
                        bundle["unique_players"], lookback_periods=3, force=False, team_name=opp.get("name"),
                    )
                    p = refresh_result["padelstat"]
                    st.write(
                        f"Matchdata: {refresh_result['matchdata_ok']}/{refresh_result['totaal']} OK"
                        + (f", {len(refresh_result['matchdata_fout'])} mislukt" if refresh_result["matchdata_fout"] else "")
                    )
                    st.write(
                        f"Playing strength: {p.get('opgehaald', 0)} opgehaald, {p.get('cache', 0)} al gekend, "
                        f"{p.get('niet_gevonden', 0)} niet gevonden, {p.get('fout', 0)} fout"
                    )
                    for item in refresh_result["matchdata_fout"]:
                        st.write(f"⚠️ {item['name']}: kon niet ververst worden.")
                    status.update(label="Volledige ploeg ververst", state="complete")
                _load_all_player_docs.clear()
    st.divider()
    if bundle:
        if not can_scrape and bundle.get("unique_players"):
            _render_unified_team_sync_trigger(
                bundle["unique_players"], key_prefix=f"scout_{sel_player_id}", team_name=opp.get("name"),
            )
    if not bundle or not bundle.get("unique_players"):
        return (bundle, opp) if bundle else None
    return bundle, opp


@st.cache_data(ttl=300, show_spinner=False)
def _cached_docs_for_players(player_ids: tuple) -> dict:
    """Gecachete variant van ll.get_docs_for_players(). Sleutel is de
    (gesorteerde) tuple van speler-ID's, zodat een gewijzigde tegenstander-
    roster wel meteen een verse ophaling triggert, maar dezelfde roster
    binnen de TTL nooit twee keer wordt opgehaald."""
    try:
        return ll.get_docs_for_players(list(player_ids))
    except Exception:
        return {}


def clear_opponent_docs_cache() -> None:
    """Leegt de cache hierboven. Aan te roepen na elke geslaagde sync-actie
    voor de tegenstander-roster, zodat verse data niet tot 5 minuten
    onzichtbaar blijft."""
    try:
        _cached_docs_for_players.clear()
    except Exception:
        pass


def prepare_team_docs(
    bundle: dict, sel_player_id: str,
) -> tuple[dict, dict]:
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: bouwt all_docs
    (matchdata van de tegenstander-roster) + global_docs terug voor gebruik
    door opponent_analysis.get_team_report()."""
    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        return {}, {}
    unknown_ids = {player["user_id"] for player in _unknown_players(bundle)}
    all_docs = _cached_docs_for_players(tuple(sorted(str(p["user_id"]) for p in unique_players)))
    if unknown_ids:
        st.caption(
            f"⚠️ {len(unknown_ids)} speler(s) nog niet volledig gekend qua matchdata — gebruik de "
            "knop '🔄 Ontbrekende gegevens ophalen' hierboven om dit (samen met klassement en "
            "playing strength) in 1 klik aan te vullen."
        )
    global_docs = _load_all_player_docs()
    return all_docs, global_docs


def render_scout_block(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    reeks_url: Optional[str] = None,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    lookback: int = 1,
):
    """Toont de volgende match en het volledige tegenploeg-analysescherm, in
    de OUDE volgorde. Deze functie blijft behouden voor eventuele andere/
    toekomstige aanroepers die de oorspronkelijke volgorde verwachten."""
    header_result = render_scout_header(sel_player_id, fixtures, own_ploeg_id, lookback=lookback)
    if not header_result:
        return None
    bundle, opp = header_result
    all_docs, global_docs = prepare_team_docs(bundle, sel_player_id)
    if not bundle.get("unique_players"):
        return bundle, opp
    oa.render_team_analysis(
        bundle,
        opp,
        all_docs,
        current_reeks_url=reeks_url,
        current_spelgroep_id=opp.get("spelgroep_id"),
        home_player_id=sel_player_id,
        global_docs=global_docs,
        go_to_player_fn=go_to_player_fn,
        key_prefix=f"scout_team_{sel_player_id}",
    )
    return bundle, opp


# PADEL_ANALYSIS_POULE_TEAMS_TAB_2026-09-19 (Fase D1): publieke naam voor
# _render_unified_team_sync_trigger(), zodat poule_teams_ui.py dit kan
# hergebruiken voor willekeurige ploegen in de poule.
render_unified_team_sync_trigger = _render_unified_team_sync_trigger
