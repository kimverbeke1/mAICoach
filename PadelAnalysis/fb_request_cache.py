"""
fb_request_cache.py - kleine helpers voor PARALLELLE Firestore-reads.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SINGLE_READ_CACHE_2026-09-29 (op verzoek van Kim, na controle
van de live versies)
--------------------------------------------------------------------------
Dit bestand bevatte eerst een eigen "lees-geheugen per render" (install(),
invalidate(), een memo in st.session_state). Die werd echter NOOIT
geactiveerd: de live dashboard_common.py heeft sindsdien een eigen, sterkere
GEDEELDE leescache (PADEL_ANALYSIS_FIRESTORE_READ_CACHE_2026-09-29,
st.cache_data met TTL 5 min en invalidatie bij schrijven). Twee caches naast
elkaar zou enkel verwarring en dubbele invalidatie-logica opleveren, dus:
  - de per-render-cache is VERWIJDERD uit dit bestand;
  - er is EEN leescache: die in dashboard_common.py;
  - dit bestand bevat enkel nog wat de bestaande aanroepers nodig hebben:
      parallel_read(raw_functie, player_ids)  - lineup_lab.get_docs_for_players
      timed_step(label)                       - lineup_lab.get_docs_for_players
      prefetch(namen, player_ids)             - opponent_analysis.get_team_report
    prefetch() delegeert naar fb._fs_prefetch (dashboard_common.py,
    PADEL_ANALYSIS_FS_CACHE_PREFETCH_2026-09-29), dat parallel voorleest IN
    de gedeelde leescache. Bestaat fb._fs_prefetch niet (bv. buiten de
    Streamlit-app), dan doet prefetch() gewoon niets.

Dit bestand heeft geen harde Streamlit-afhankelijkheid en faalt altijd stil
terug op het oude gedrag: een fout hier mag nooit een pagina breken.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

MAX_WORKERS = 16


def _in_streamlit_main_thread() -> bool:
    """True enkel binnen een Streamlit-run, in de hoofdthread. Daarbuiten
    (scrapers, worker-threads) is er geen script-context."""
    get_ctx = None
    for modulenaam in ("streamlit.runtime.scriptrunner",
                       "streamlit.runtime.scriptrunner_utils.script_run_context"):
        try:
            module = __import__(modulenaam, fromlist=["get_script_run_ctx"])
            get_ctx = getattr(module, "get_script_run_ctx", None)
            if get_ctx is not None:
                break
        except Exception:  # noqa: BLE001
            continue
    try:
        return get_ctx is not None and get_ctx() is not None
    except Exception:  # noqa: BLE001
        return False


def timed_step(label):
    """Timing-stap in het laadtijd-paneel, maar ENKEL binnen een
    Streamlit-run (hoofdthread). Daarbuiten een no-op."""
    from contextlib import nullcontext
    if not _in_streamlit_main_thread():
        return nullcontext()
    try:
        import perf_timing as perf
        return perf.step(label)
    except Exception:  # noqa: BLE001
        return nullcontext()


def parallel_read(raw_functie, player_ids) -> dict:
    """Leest raw_functie(pid) voor alle pids in parallel. Geeft
    {pid: resultaat} terug; een mislukte read geeft None voor die speler.
    Gebruik hier een ONGEWIKKELDE functie (bv. fb._raw_get_player): de
    timing- en cachelaag horen niet in worker-threads."""
    pids = list(dict.fromkeys(str(p) for p in player_ids if p))
    if not pids:
        return {}

    def _lees(pid):
        try:
            return pid, raw_functie(pid)
        except Exception:  # noqa: BLE001
            return pid, None

    if len(pids) == 1:
        return dict([_lees(pids[0])])
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(pids))) as pool:
        return dict(pool.map(_lees, pids))


def prefetch(function_names, player_ids) -> None:
    """Leest de gevraagde (functie, speler)-paren parallel voor in de
    GEDEELDE leescache van dashboard_common.py. Doet niets als die niet
    geinstalleerd is."""
    try:
        import firebase_service as fb
    except Exception:  # noqa: BLE001
        return
    functie = getattr(fb, "_fs_prefetch", None)
    if not callable(functie):
        return
    try:
        functie(tuple(function_names), list(player_ids or []))
    except Exception:  # noqa: BLE001
        pass
