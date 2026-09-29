"""
fb_request_cache.py - lees-geheugen per render voor firebase_service, plus
parallel voorophalen van spelersdocumenten.

PADEL_ANALYSIS_REQUEST_DOC_CACHE_2026-09-29 (op verzoek van Kim, na een
MEETSESSIE met perf_timing.py)
--------------------------------------------------------------------------
GEMETEN (tabel "Opgeteld per stapnaam", tweede F5 na Reboot):
  - Mijn profiel : 4x Firestore get_player (2.45s) + 4x get_player_profile
                   (1.31s) - telkens HETZELFDE document van dezelfde speler,
                   opgevraagd door 4 verschillende helpers (_get_club,
                   _official_current_rank, _virtual_rank,
                   render_player_dashboard).
  - Spelers      : 4x get_player_profile (1.96s) + 3x get_player (1.06s).
  - Opstelling   : 4x get_player_profile voor hetzelfde profiel, plus 7x
                   get_padelstat_rating + 7x get_player NA ELKAAR in
                   oa.get_team_report (~2.5s).
Elke read kost 0.15-0.8s netwerk; de data zelf verandert binnen een render
niet. Dit bestand lost beide patronen op, zonder de aanroepers te wijzigen.

1. LEES-GEHEUGEN PER RENDER (install())
   fb.get_player / fb.get_player_profile / fb.get_padelstat_rating worden
   omwikkeld: binnen DEZELFDE render wordt elk (functie, speler)-paar maar
   EEN keer echt gelezen; volgende aanroepen krijgen een KOPIE (deepcopy) van
   het resultaat, zodat een aanroeper die het resultaat wijzigt nooit een
   andere aanroeper beinvloedt.
   Geldigheid - er wordt NOOIT verouderde data getoond na een wijziging:
     - Het geheugen is gekoppeld aan de render-token van perf_timing
       (st.session_state["_perf_render_start_v1"], gezet door
       perf.begin_run() in streamlit_app.py bij ELKE volledige run, ook na
       st.rerun()). Nieuwe run = leeg geheugen. Fragment-reruns
       (@st.fragment) delen het geheugen van hun laatste volledige run.
     - Extra bovengrens: elk item vervalt na MAX_AGE_SECONDS, ook als de
       render-token ontbreekt (bv. met PERF_ENABLED=False).
     - Elke schrijf-functie van firebase_service (naam begint met save_,
       update_, delete_, set_ of add_) wist het geheugen na afloop.
     - Directe fb.db-schrijfacties in dashboard_common.py roepen
       invalidate() expliciet aan.
   Wordt enkel geinstalleerd vanuit dashboard_common.py, dus enkel in het
   Streamlit-proces. De scrapers in GitHub Actions merken er niets van.

2. PARALLEL VOOROPHALEN (prefetch())
   Leest een lijst spelers in parallel (threads) i.p.v. een voor een, en
   vult daarmee het lees-geheugen. De threads gebruiken de ONGEWIKKELDE
   originele functies (fb._raw_<naam>), want st.session_state en
   perf_timing werken niet buiten de Streamlit-hoofdthread. Het resultaat
   wordt pas in de hoofdthread in het geheugen gezet. De volledige batch
   verschijnt als EEN stap in het laadtijd-paneel.
   De Firestore-client van google-cloud is thread-safe voor gelijktijdige
   leesaanroepen.

Alles faalt stil terug op het oude gedrag (gewoon rechtstreeks lezen): een
fout in deze laag mag nooit een pagina breken.
"""

from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor

# Leesfuncties die per render gememoiseerd worden.
MEMO_FUNCTIONS = ("get_player", "get_player_profile", "get_padelstat_rating")

# Prefixen van schrijf-functies die het geheugen moeten wissen.
_WRITE_PREFIXES = ("save_", "update_", "delete_", "set_", "add_")

MAX_AGE_SECONDS = 30.0
MAX_WORKERS = 16

_MEMO_KEY = "_fb_request_cache_v1"
_PERF_RUN_TOKEN_KEY = "_perf_render_start_v1"  # zie perf_timing.py

_fb = None


# ─────────────────────────────────────────────
# Interne helpers
# ─────────────────────────────────────────────
def _session_state():
    """Geeft st.session_state terug, of None buiten een Streamlit-run."""
    try:
        import streamlit as st
    except Exception:  # noqa: BLE001
        return None
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
        # Buiten de hoofdthread van een Streamlit-run (bv. in een worker-
        # thread) is er geen context: dan GEEN geheugen, gewoon lezen.
        if get_ctx is not None and get_ctx() is None:
            return None
        return st.session_state
    except Exception:  # noqa: BLE001
        return None


def _memo():
    """Het geheugen van de HUIDIGE render, of None als dat niet beschikbaar
    is. Een nieuwe render-token geeft een leeg geheugen."""
    state = _session_state()
    if state is None:
        return None
    try:
        token = state.get(_PERF_RUN_TOKEN_KEY)
        memo = state.get(_MEMO_KEY)
        if not isinstance(memo, dict) or memo.get("token") != token:
            memo = {"token": token, "items": {}}
            state[_MEMO_KEY] = memo
        return memo["items"]
    except Exception:  # noqa: BLE001
        return None


def _fresh(entry) -> bool:
    return (time.monotonic() - entry[0]) <= MAX_AGE_SECONDS


def _copy(value):
    try:
        return copy.deepcopy(value)
    except Exception:  # noqa: BLE001
        return value


def _perf_step(label):
    """Timing-stap in het laadtijd-paneel, maar ENKEL binnen een Streamlit-
    run (hoofdthread). Daarbuiten (scrapers, worker-threads) een no-op."""
    from contextlib import nullcontext
    if _session_state() is None:
        return nullcontext()
    try:
        import perf_timing as perf
        return perf.step(label)
    except Exception:  # noqa: BLE001
        return nullcontext()


def timed_step(label):
    """Publieke variant van _perf_step() voor andere modules
    (bv. lineup_lab.get_docs_for_players)."""
    return _perf_step(label)


# ─────────────────────────────────────────────
# Publieke API
# ─────────────────────────────────────────────
def invalidate(player_id=None) -> None:
    """Wist het lees-geheugen - volledig, of enkel voor 1 speler."""
    items = _memo()
    if items is None:
        return
    if player_id is None:
        items.clear()
        return
    pid = str(player_id)
    for key in [k for k in items if k[1] == pid]:
        items.pop(key, None)


def _memo_wrapper(naam: str, functie):
    def wrapper(player_id, *args, **kwargs):
        # Enkel de gewone vorm (1 positioneel argument) wordt gememoiseerd;
        # elke andere aanroepvorm gaat ongewijzigd door.
        if args or kwargs:
            return functie(player_id, *args, **kwargs)
        items = _memo()
        if items is None:
            return functie(player_id)
        key = (naam, str(player_id))
        entry = items.get(key)
        if entry is not None and _fresh(entry):
            return _copy(entry[1])
        waarde = functie(player_id)
        items[key] = (time.monotonic(), waarde)
        return _copy(waarde)

    wrapper.__name__ = getattr(functie, "__name__", naam)
    wrapper.__doc__ = getattr(functie, "__doc__", None)
    wrapper._fb_request_cache_wrapped = True
    return wrapper


def _write_wrapper(functie):
    def wrapper(*args, **kwargs):
        try:
            return functie(*args, **kwargs)
        finally:
            invalidate()

    wrapper.__name__ = getattr(functie, "__name__", "write")
    wrapper.__doc__ = getattr(functie, "__doc__", None)
    wrapper._fb_request_cache_wrapped = True
    return wrapper


def save_raw_originals(fb) -> None:
    """Bewaart de ONGEWIKKELDE leesfuncties als fb._raw_<naam>, VOOR er
    timing- of geheugenlagen omheen komen. Idempotent."""
    for naam in MEMO_FUNCTIONS:
        raw_naam = f"_raw_{naam}"
        if getattr(fb, raw_naam, None) is None and callable(getattr(fb, naam, None)):
            try:
                setattr(fb, raw_naam, getattr(fb, naam))
            except Exception:  # noqa: BLE001
                pass


def install(fb) -> None:
    """Installeert het lees-geheugen en de schrijf-invalidatie op
    firebase_service. Idempotent. Roep save_raw_originals(fb) eerst aan."""
    global _fb
    _fb = fb
    if getattr(fb, "_fb_request_cache_installed", False):
        return
    save_raw_originals(fb)
    for naam in MEMO_FUNCTIONS:
        functie = getattr(fb, naam, None)
        if callable(functie) and not getattr(functie, "_fb_request_cache_wrapped", False):
            try:
                setattr(fb, naam, _memo_wrapper(naam, functie))
            except Exception:  # noqa: BLE001
                pass
    for naam in dir(fb):
        if not naam.startswith(_WRITE_PREFIXES):
            continue
        functie = getattr(fb, naam, None)
        if not callable(functie) or isinstance(functie, type):
            continue
        if getattr(functie, "_fb_request_cache_wrapped", False):
            continue
        try:
            setattr(fb, naam, _write_wrapper(functie))
        except Exception:  # noqa: BLE001
            pass
    try:
        fb._fb_request_cache_installed = True
    except Exception:  # noqa: BLE001
        pass


def parallel_read(raw_functie, player_ids) -> dict:
    """Leest raw_functie(pid) voor alle pids in parallel. Geeft
    {pid: resultaat} terug; een mislukte read geeft None voor die speler.
    Raakt GEEN Streamlit-state aan - veilig in threads en buiten Streamlit."""
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
    """Vult het lees-geheugen van de huidige render voor alle (functie,
    speler)-paren die er nog niet in zitten - in parallel. Daarna kosten de
    gewone fb.<functie>(pid)-aanroepen van de aanroeper 0 netwerk.
    Doet niets als het geheugen niet beschikbaar is (bv. buiten Streamlit)."""
    fb = _fb
    items = _memo()
    if fb is None or items is None:
        return
    pids = list(dict.fromkeys(str(p) for p in player_ids if p))
    taken = []
    for naam in function_names:
        raw = getattr(fb, f"_raw_{naam}", None)
        if not callable(raw):
            continue
        ontbrekend = [
            pid for pid in pids
            if not ((naam, pid) in items and _fresh(items[(naam, pid)]))
        ]
        if ontbrekend:
            taken.append((naam, raw, ontbrekend))
    if not taken:
        return
    totaal = sum(len(t[2]) for t in taken)
    with _perf_step(f"Firestore: parallel voorophalen ({totaal} reads)"):
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, totaal)) as pool:
            futures = [
                (naam, pid, pool.submit(raw, pid))
                for naam, raw, ontbrekend in taken
                for pid in ontbrekend
            ]
            nu = time.monotonic()
            for naam, pid, future in futures:
                try:
                    items[(naam, pid)] = (nu, future.result())
                except Exception:  # noqa: BLE001
                    # Geen geheugen-item: de gewone aanroep probeert het
                    # later gewoon zelf opnieuw.
                    pass
