"""
opponent_scout_ui.py - UI-blok voor de tegenstander-analyse bij 'Volgende match'.
Doel van dit bestand:
- 2026-09-09 (v1): de tussenstap verdwijnt. Na een klik op 'Tegenstander
  analyseren' wordt de opstelling van de tegenstander opgezocht EN worden de
  nog onbekende spelers meteen gescrapet, in een doorlopende
  voortgangsweergave (st.status).
- 2026-09-09 (v2): het volledige teamanalysescherm zit in
  opponent_analysis.render_team_analysis(). Dit bestand geeft er spelgroep_id,
  home_player_id en een brede cache van alle gekende spelersdocumenten aan door.
PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14 (v3): Opgesplitst in
render_scout_header() + prepare_team_docs(). render_scout_block() blijft
bestaan als dunne wrapper.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16 / PADEL_ANALYSIS_SCOUT_PROFILE_
INTEGRITY_2026-09-17 / PADEL_ANALYSIS_CLOUD_KLASSEMENT_PADELSTAT_TRIGGER_
2026-09-17 / PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19 /
PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19 / PADEL_ANALYSIS_UI_
NEUTRAL_LANGUAGE_2026-09-19 / PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 /
PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19 / PADEL_ANALYSIS_
FALSE_MISSING_ON_READ_ERROR_FIX_2026-09-19 / PADEL_ANALYSIS_TEAM_SYNC_FULL_
FORCE_OPTION_2026-09-21: zie eerdere versies van dit bestand voor de
volledige, uitgebreide toelichting bij elke fix - functioneel ongewijzigd.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26 / PADEL_ANALYSIS_DATA_
COMPLETENESS_CACHE_2026-09-26 / PADEL_ANALYSIS_OPPONENT_DOCS_CACHE_2026-09-26:
_is_known()/_data_completeness()/all_docs in prepare_team_docs() zijn nu
@st.cache_data(ttl=300)-gecacht i.p.v. ongecachete Firestore-reads bij ELKE
Streamlit-rerun.
--------------------------------------------------------------------------
PADEL_ANALYSIS_KNOWN_MATCHES_CACHE_2026-09-27 (op verzoek van Kim): een
ongecachete fb.get_player()-call per tegenstander-speler in opponent_scout.
_known_matches_total() is nu 300s gecacht (in opponent_scout.py zelf, bewust
géén st.cache_data). Dit bestand roept osc.clear_known_matches_cache() aan
op dezelfde plekken als de overige cache-clears.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28 (op verzoek van Kim, na analyse
i.s.m. lineup_scout.py: "eerste laadactie van de ploegopstelling pagina te
versnellen")
--------------------------------------------------------------------------
BEVESTIGD: naast _run_scout_and_scrape() hieronder (osc.scout_opponent() met
lookback=1..4) doet lineup_scout._scout_team_all_fixtures() - VOOR dezelfde
tegenploeg, op dezelfde pagina-render - een TWEEDE, onafhankelijke
osc.scout_opponent()-aanroep met lookback=ALLE gespeelde wedstrijden (voor
de "Vorige gespeelde matchen"-tab). Elke aanroep had een EIGEN, lokale
fetch-cache, dus de 2e aanroep herhaalde fetches die de 1e al deed.
FIX: _run_scout_and_scrape() geeft nu een GEDEELDE fetch-cache mee aan
osc.scout_opponent(), opgeslagen in st.session_state onder
osc.shared_fetch_cache_key(ploeg_id) - EXACT dezelfde sleutel die
lineup_scout._scout_team_all_fixtures() nu ook gebruikt (zie dat bestand),
zodat beide aanroepen voor dezelfde tegenploeg hun opgehaalde fixtures
DELEN i.p.v. dubbel te fetchen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PROCESS_WIDE_SCOUT_CACHE_2026-09-29 (op verzoek van Kim:
"opstelling analyse zou wel moeten blijven staan als je wisselt van pagina",
en meting: render_scout_header 5.3-5.8s eigen tijd)
--------------------------------------------------------------------------
ROOT CAUSE: het scout-resultaat stond ENKEL in st.session_state[scout_key].
Na F5 of een nieuwe sessie was het weg: de analyse verdween en na een nieuwe
klik werden alle uitslagenbladen opnieuw live opgehaald.
FIX:
  - render_scout_header() haalt een ontbrekend resultaat eerst op via
    osc.get_saved_scout_bundle(scout_key) (proces-geheugen, anders
    Firestore). De analyse staat dus meteen terug, zonder klik en zonder
    live fetch. Er wordt dan ook GEEN padelstat-workflow gestart - dat
    gebeurt enkel bij een bewuste klik op "Tegenstander analyseren".
  - Na een klik wordt het nieuwe resultaat met osc.save_scout_bundle()
    bewaard.
  - _run_scout_and_scrape() gebruikt de proces-brede fetch-cache
    osc.get_shared_fetch_cache() i.p.v. een sessie-dict.
  - Een caption toont wanneer de getoonde analyse uit het geheugen komt;
    "Tegenstander analyseren" blijft beschikbaar om bewust te herberekenen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCOUT_HEADER_PREFETCH_2026-09-29 (op verzoek van Kim: "bij
opstelling analyse duurt de 1ste maal zo lang"; meting: render_scout_header
5.4-5.7s bij een koude start, OOK na de proces-brede scout-cache hierboven)
--------------------------------------------------------------------------
Zodra er een (teruggezette) analyse is, doen twee plekken per
tegenstander-speler Firestore-reads NA ELKAAR:
  - _render_unified_team_sync_trigger() -> _data_completeness(pid):
    get_player + get_player_profile + get_padelstat_rating per speler;
  - prepare_team_docs() -> _unknown_players() -> _cached_is_known(pid):
    get_player_profile (+ get_player) per speler.
Bij een ploeg van ~10 spelers zijn dat ~30 reads van ~0.2s na elkaar.
FIX: net voor die checks worden deze drie reads voor ALLE spelers van de
ploeg in EEN parallelle batch in de gedeelde leescache gezet
(fb._fs_prefetch, zie dashboard_common.py). De checks zelf zijn
ONGEWIJZIGD; ze lezen daarna uit de cache.
ZICHTBAARHEID: render_scout_header() krijgt eigen meetpunten
("scout: ..."), zodat de volgende meting toont welk deel van de "eigen
tijd" van render_scout_header echt overblijft - i.p.v. te raden.
--------------------------------------------------------------------------
PADEL_ANALYSIS_LAZY_GLOBAL_DOCS_2026-09-29 (op verzoek van Kim: "bij
opstelling analyse duurt de 1ste maal zo lang"; meting 2026-09-29T18-50:
render 8.87s, zwaarste eigen tijd osu.prepare_team_docs 2.02s)
--------------------------------------------------------------------------
GEMETEN: prepare_team_docs() kostte 2.37s, waarvan maar 0.35s in de
gemeten Firestore-reads. De overige 2.02s "eigen tijd" is
_load_all_player_docs(): een stream van de VOLLEDIGE spelerscollectie
(alle spelers, met al hun matchen) - niet via fb.get_..., dus onzichtbaar
als aparte Firestore-stap. Gecachet voor 5 min, dus vooral de eerste load.
ROOT CAUSE: die volledige collectie (global_docs) wordt ALTIJD geladen,
maar enkel gebruikt bij een HERBOUW van het team-rapport
(opponent_dossier.build_player_summary -> _current_rank_fallback, en dan
nog enkel voor spelers zonder klassement). In dezelfde meting werd het
rapport NIET herbouwd (geen "team report: HERBOUW"-stap): de 2s werden dus
volledig voor niets betaald.
FIX: prepare_team_docs() geeft global_docs nu terug als _LazyAllPlayerDocs:
een alleen-lezen Mapping die de collectie pas laadt bij het EERSTE echte
gebruik (lezen, itereren, len, bool, ...). Wordt het rapport niet
herbouwd, dan wordt de collectie nooit geladen. Wordt het wel gebruikt,
dan is het gedrag identiek aan voorheen - ook "if global_docs" laadt eerst,
zodat een lege collectie nog altijd terugvalt op all_docs. Het laden zelf
verschijnt nu als aparte stap "Firestore: alle spelersdocumenten
(global_docs)" in het laadtijd-paneel.
Hashing/pickling (bv. als het ooit aan een @st.cache_data-functie wordt
meegegeven) levert een gewone, volledig geladen dict op.
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
try:
    import padelstats_scraper as pss
except Exception:  # pragma: no cover
    pss = None
PADELSTAT_WORKFLOW_FILE = "refresh-padelstat.yml"

# PADEL_ANALYSIS_SCOUT_HEADER_PREFETCH_2026-09-29 - zie moduledocstring.
try:
    import perf_timing as _perf
except Exception:  # noqa: BLE001  pragma: no cover
    _perf = None

_ROSTER_READS = ("get_player", "get_player_profile", "get_padelstat_rating")


def _step(label: str):
    if _perf is None:
        from contextlib import nullcontext
        return nullcontext()
    return _perf.step(label)


def _prefetch_roster_reads(unique_players: list) -> None:
    """Leest de per-speler-Firestore-reads van deze ploeg parallel voor in
    de gedeelde leescache. Doet niets als die niet geinstalleerd is."""
    functie = getattr(fb, "_fs_prefetch", None)
    if not callable(functie):
        return
    pids = [str(p.get("user_id")) for p in (unique_players or []) if p.get("user_id")]
    if not pids:
        return
    try:
        functie(_ROSTER_READS, pids)
    except Exception:  # noqa: BLE001 - voorophalen mag nooit de pagina breken
        pass


@st.cache_data(ttl=300, show_spinner=False)
def _load_all_player_docs() -> dict:
    try:
        docs = fb.db.collection(fb.PLAYERS_COLLECTION).stream()
        return {d.id: (d.to_dict() or {}) for d in docs}
    except Exception:
        return {}


def load_all_player_docs() -> dict:
    return _load_all_player_docs()


# PADEL_ANALYSIS_LAZY_GLOBAL_DOCS_2026-09-29 - zie moduledocstring.
from collections.abc import Mapping as _Mapping


class _LazyAllPlayerDocs(_Mapping):
    """Alleen-lezen Mapping rond _load_all_player_docs(), die pas laadt bij
    het eerste echte gebruik. Elke lees-operatie gaat via _data()."""

    __slots__ = ("_cache",)

    def __init__(self) -> None:
        self._cache = None

    def _data(self) -> dict:
        if self._cache is None:
            with _step("Firestore: alle spelersdocumenten (global_docs)"):
                self._cache = _load_all_player_docs() or {}
        return self._cache

    def __getitem__(self, key):
        return self._data()[key]

    def __iter__(self):
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def __bool__(self) -> bool:
        return bool(self._data())

    def __contains__(self, key) -> bool:
        return key in self._data()

    def get(self, key, default=None):
        return self._data().get(key, default)

    def keys(self):
        return self._data().keys()

    def values(self):
        return self._data().values()

    def items(self):
        return self._data().items()

    def __reduce__(self):
        return (dict, (dict(self._data()),))

    def __repr__(self) -> str:
        status = "niet geladen" if self._cache is None else f"{len(self._cache)} spelers"
        return f"<_LazyAllPlayerDocs {status}>"


def _is_known(player_id: str) -> bool:
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


@st.cache_data(ttl=300, show_spinner=False)
def _cached_is_known(player_id: str) -> bool:
    return _is_known(player_id)


def clear_is_known_cache() -> None:
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


@st.cache_data(ttl=300, show_spinner=False)
def _data_completeness(player_id: str) -> dict:
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
    osc.clear_known_matches_cache()


def _ensure_padelstat(
    players: list[dict],
    progress_label: str = "Padelstat",
    force: bool = False,
    team_name: Optional[str] = None,
) -> dict:
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
    optioneel ook de klassementshistoriek op.
    PADEL_ANALYSIS_SHARED_FETCH_CACHE_2026-09-28: geeft nu een GEDEELDE
    fetch-cache mee aan osc.scout_opponent() (zie moduledocstring), zodat
    lineup_scout._scout_team_all_fixtures() - dat voor DEZELFDE tegenploeg
    een 2e, bredere scout doet - de hier al opgehaalde fixtures kan
    hergebruiken i.p.v. ze opnieuw te fetchen."""
    with st.status("Tegenstander analyseren...", expanded=True) as status:
        st.write("Vorige wedstrijd(en) van de tegenstander opzoeken...")
        # PADEL_ANALYSIS_PROCESS_WIDE_SCOUT_CACHE_2026-09-29: proces-breed.
        shared_cache = osc.get_shared_fetch_cache(str(opp["ploeg_id"]))
        bundle = osc.scout_opponent(
            fixtures,
            opp["name"],
            opp["ploeg_id"],
            next_match["date_text"],
            lookback=lookback,
            fetched_cache=shared_cache,
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
    from scrape_player import scrape_player
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
    osc.clear_known_matches_cache()
    return result


def _render_unified_team_sync_trigger(
    unique_players: list[dict], key_prefix: str, team_name: Optional[str] = None,
) -> dict:
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
                f"{len(all_ids)} speler(s) van deze ploeg opnieuw te laten controleren/verversen."
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
        osc.clear_known_matches_cache()
        st.rerun()
    return {"missing_matchdata": len(missing_matchdata_ids), "missing_klassement": len(missing_klassement_ids)}


def render_scout_header(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    lookback: int = 1,
) -> Optional[tuple[dict, dict]]:
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
            st.session_state.pop(f"{scout_key}_restored", None)
            osc.save_scout_bundle(scout_key, st.session_state[scout_key])
    # PADEL_ANALYSIS_PROCESS_WIDE_SCOUT_CACHE_2026-09-29: na F5/nieuwe
    # sessie het eerder bewaarde resultaat terugzetten i.p.v. te verdwijnen.
    if scout_key not in st.session_state:
        with _step("scout: opgeslagen analyse laden"):
            restored = osc.get_saved_scout_bundle(scout_key)
        if restored:
            st.session_state[scout_key] = restored
            st.session_state[f"{scout_key}_restored"] = True
    bundle = st.session_state.get(scout_key)
    if bundle and st.session_state.get(f"{scout_key}_restored"):
        st.caption(
            "ℹ️ Eerder berekende analyse voor deze match teruggezet. Klik op "
            "'🔍 Tegenstander analyseren' om ze opnieuw te berekenen."
        )
    with col_refresh:
        if bundle and bundle.get("unique_players") and can_scrape:
            if st.button(
                "🔄 Ververs alles voor deze ploeg",
                key=f"btn_full_refresh_{sel_player_id}",
                help=(
                    "Herhaalt matchdata (meerdere periodes) en playing strength voor ALLE spelers "
                    "van deze ploeg, ook wie al een (onvolledig) profiel heeft. Klassement enkel "
                    "voor wie dat nog nooit had."
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
    if bundle and bundle.get("unique_players"):
        # PADEL_ANALYSIS_SCOUT_HEADER_PREFETCH_2026-09-29: alle per-speler-
        # reads in EEN parallelle batch, VOOR de checks hieronder en in
        # prepare_team_docs() - zie moduledocstring.
        _prefetch_roster_reads(bundle["unique_players"])
    if bundle:
        if not can_scrape and bundle.get("unique_players"):
            with _step("scout: volledigheidscheck + sync-knop"):
                _render_unified_team_sync_trigger(
                    bundle["unique_players"], key_prefix=f"scout_{sel_player_id}", team_name=opp.get("name"),
                )
    if not bundle or not bundle.get("unique_players"):
        return (bundle, opp) if bundle else None
    return bundle, opp


@st.cache_data(ttl=300, show_spinner=False)
def _cached_docs_for_players(player_ids: tuple) -> dict:
    try:
        return ll.get_docs_for_players(list(player_ids))
    except Exception:
        return {}


def clear_opponent_docs_cache() -> None:
    try:
        _cached_docs_for_players.clear()
    except Exception:
        pass


def prepare_team_docs(
    bundle: dict, sel_player_id: str,
) -> tuple[dict, dict]:
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
    # PADEL_ANALYSIS_LAZY_GLOBAL_DOCS_2026-09-29: pas laden bij echt gebruik
    # (enkel bij een herbouw van het team-rapport) - zie moduledocstring.
    global_docs = _LazyAllPlayerDocs()
    return all_docs, global_docs


def render_scout_block(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    reeks_url: Optional[str] = None,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    lookback: int = 1,
):
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


render_unified_team_sync_trigger = _render_unified_team_sync_trigger
