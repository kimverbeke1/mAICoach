"""
ranking_refresh.py - verversknop voor de sectie "Rangschikking" + diagnose waarom een stand niet klopt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RANKING_REFRESH_2026-10-11 (op verzoek van Kim: "ik ben toch voorstander om bij de rangschikking een
refresh knop te hebben waarbij je dan minstens refreshed wie tegen wie gespeeld heeft en dan natuurlijk ook bijhoren
hoeveel punten elke ploeg heeft. Ik heb nu bvb een rangschikking waar 2 ploegen hun score niet geupdate is. tenzij je
daar bepaalde oorzaken voor ziet die je op een automatische manier kan oplossen")
--------------------------------------------------------------------------
WAAROM EEN STAND NIET KLOPT - vier mogelijke oorzaken, in volgorde van wat de knop zelf kan oplossen:
  1. ONZE STAND-CACHE: de punten komen live van TVL (poule_ranking.py) maar werden tot 30 minuten onzichtbaar gecachet.
     -> de knop wist die cache en haalt de stand opnieuw op (nu 10 minuten, met het ophaalmoment onder de stand).
  2. ONZE LEES-CACHES: het poule-schema ("wie speelde tegen wie") staat in Firestore (door de achtergronddienst
     weggeschreven) maar de app las het via een gedeelde leescache van 30 minuten, en hield bovendien een kopie vast
     in de sessie (vm_fixtures_<speler>) die NOOIT vernieuwd werd. Een schema-update die al klaar was, bleef dus onzichtbaar.
     -> de knop wist de leescache en leest het schema opnieuw in.
  3. ONS SCHEMA LOOPT ACHTER OP TVL: TVL telt voor een ploeg meer ontmoetingen dan er gespeelde ontmoetingen in ons
     opgeslagen schema staan. -> de knop start zelf een schema-update (lokaal rechtstreeks, op de cloud via de
     achtergronddienst, ongeveer 3 tot 5 minuten) en leest het resultaat daarna opnieuw in.
  4. TVL LOOPT ACHTER OP DE UITSLAG: in ons schema staat al een uitslag die TVL nog niet in zijn stand verwerkt heeft.
     DAT kan de app niet oplossen: de stand lost vanzelf op zodra TVL de uitslag verwerkt. De diagnose zegt dan
     precies welke ontmoeting(en) het zijn en welke punten de ploeg volgens ons schema zou hebben.
  (Daarnaast: zelfde aantal ontmoetingen maar andere punten - bv. strafpunten of een forfait van TVL - wordt apart
  gemeld; niets automatisch.)
De diagnose vergelijkt per ploeg het aantal ontmoetingen en de punten van TVL met wat ons schema zegt (consistency_report()).
De score van een ontmoeting is "matchen / sets / games", telkens thuis - uit (bevestigd, zie speelschema_view.py).
--------------------------------------------------------------------------
PADEL_ANALYSIS_RANKING_REFRESH_V2_2026-10-11 (op verzoek van Kim: "ververs rangschikking heeft het probleem opgelost. Ik moest
wel manueel pagina nog refreshen dus dat zou beter direct geupdate worden [...] ik snap ook niet goed waarom er naast ververs
rangschikking ook een knop staat 'schema ook bij TVL ophalen'. Vanuit gebruiker standpunt maakt het niet uit van waar het komt
als het maar klopt. dus 1 knop zou voldoende moeten zijn.")
--------------------------------------------------------------------------
1. EEN KNOP. "Schema ook bij TVL ophalen" is weg: de app beslist zelf (diagnose) of het schema bij TVL opgehaald moet worden.
2. NIET MEER MANUEEL VERVERSEN. De vorige versie wachtte hoogstens 4 minuten op de achtergronddienst, terwijl die (matchdata,
   padelstat, klassement, teamgenoten en poule-schema van de speler) langer kan duren; daarna werd het resultaat nooit meer
   ingelezen en moest je zelf de pagina verversen. Nu blokkeert de pagina niet meer: een lopende update wordt elke 8 seconden
   gecontroleerd (st.fragment(run_every=8)): staat er in de database een schema dat NA de start is weggeschreven, of meldt de
   achtergronddienst "klaar", dan worden stand en schema opnieuw ingelezen en ververst de hele pagina zichzelf. Na een F5 gaat
   het wachten door: het startmoment staat in de URL (?rank_wait=...). Na 20 minuten wordt het opgegeven, met een melding.
3. SNELLER. De update vraagt aan de achtergronddienst enkel het schema (invoer schedule_only, zie scrape-padel.yml): geen
   padelstat, klassement of teamgenoten. Kent de workflow die invoer nog niet (yml nog niet gecommit), dan weigert GitHub de
   aanvraag (422) en start de app automatisch de gewone, volledige scrape.
Zuivere logica (consistency_report) en weergave (render_refresh_block) zijn gescheiden; alle afhankelijkheden van de
app (poule_ranking, dashboard_common, cloud_helpers, lineup_scout) komen via `adapters`, zodat alles offline te testen
is (test_ranking_refresh.py).
"""
import re
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import streamlit as st

import poule_ranking as pr

STATUS_OK = "ok"
STATUS_SCHEMA_ACHTER = "schema_achter"
STATUS_TVL_ACHTER = "tvl_achter"
STATUS_PUNTEN = "punten_wijken_af"
STATUS_ONZEKER = "onzeker"

_STATUS_TEKST = {
    STATUS_OK: "klopt",
    STATUS_SCHEMA_ACHTER: "ons schema loopt achter",
    STATUS_TVL_ACHTER: "TVL heeft de uitslag nog niet verwerkt",
    STATUS_PUNTEN: "andere punten bij gelijk aantal ontmoetingen",
    STATUS_ONZEKER: "niet te controleren",
}
_DATE_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:\D+(\d{1,2}):(\d{2}))?")


def _date_key(fx: dict) -> tuple:
    m = _DATE_RE.search(str(fx.get("date_text") or ""))
    if not m:
        return (0, 0, 0, 0, 0)
    d, mo, y, hh, mi = m.groups()
    return (int(y), int(mo), int(d), int(hh or 0), int(mi or 0))


def _uitslag_tekst(fx: dict) -> str:
    parsed = pr._parse_score(fx.get("score"))
    return f"{parsed[0]}-{parsed[1]}" if parsed else "uitslag onleesbaar"


def consistency_report(standings: list, fixtures: list) -> Optional[dict]:
    """Vergelijkt de stand van TVL (ontmoetingen + punten per ploeg) met de GESPEELDE ontmoetingen in ons opgeslagen
    schema. Geeft None terug als er geen stand is. Anders:
      {"rows": [per ploeg: ploeg_id, naam, plaats, tvl_ontmoetingen, tvl_punten, schema_ontmoetingen, schema_punten,
                onleesbaar, status, verwacht_punten],
       "schema_achter": [naam], "tvl_achter": [naam], "punten_wijken_af": [naam], "onzeker": [naam],
       "tvl_nog_niet_verwerkt": [{"datum", "thuis", "uit", "uitslag"}],
       "needs_schedule_refresh": bool, "all_ok": bool, "n_teams": int, "n_played": int}
    Status per ploeg:
      ok               - zelfde aantal ontmoetingen en zelfde punten;
      schema_achter    - TVL telt MEER ontmoetingen dan ons schema (ons schema moet vernieuwd worden);
      tvl_achter       - ons schema heeft MEER gespeelde ontmoetingen dan TVL telt (TVL moet nog verwerken);
      punten_wijken_af - zelfde aantal, andere punten;
      onzeker          - een van de getallen ontbreekt of een uitslag is onleesbaar.
    De richting van het scoreveld is thuis-uit (bevestigd); een gelijkspel (2-2) geeft beide ploegen 1 punt."""
    teams: dict = {}
    for s in standings or []:
        if s.get("ploeg_id") is None:
            continue
        teams[str(s["ploeg_id"])] = s
    if not teams:
        return None
    ids = set(teams)
    per = {pid: {"n": 0, "pts": 0, "onleesbaar": 0, "fixtures": []} for pid in ids}
    played = [
        fx for fx in fixtures or []
        if fx.get("played") and str(fx.get("home_ploeg_id")) in ids and str(fx.get("away_ploeg_id")) in ids
    ]
    for fx in played:
        h, a = str(fx["home_ploeg_id"]), str(fx["away_ploeg_id"])
        for pid in (h, a):
            per[pid]["n"] += 1
            per[pid]["fixtures"].append(fx)
        parsed = pr._parse_score(fx.get("score"))
        if parsed is None:
            per[h]["onleesbaar"] += 1
            per[a]["onleesbaar"] += 1
            continue
        bh, ba = parsed
        if bh > ba:
            per[h]["pts"] += pr.WIN_POINTS
        elif bh < ba:
            per[a]["pts"] += pr.WIN_POINTS
        else:
            per[h]["pts"] += pr.DRAW_POINTS
            per[a]["pts"] += pr.DRAW_POINTS
    rows = []
    nog_niet_verwerkt: dict = {}
    for pid, s in teams.items():
        p = per[pid]
        tvl_n, tvl_p = s.get("ontmoetingen"), s.get("punten")
        if tvl_n is None or tvl_p is None or p["onleesbaar"]:
            status = STATUS_ONZEKER
        elif p["n"] == tvl_n and p["pts"] == tvl_p:
            status = STATUS_OK
        elif p["n"] == tvl_n:
            status = STATUS_PUNTEN
        elif p["n"] > tvl_n:
            status = STATUS_TVL_ACHTER
            # De laatst gespeelde ontmoeting(en) van deze ploeg zijn degene die TVL nog niet telt.
            for fx in sorted(p["fixtures"], key=_date_key, reverse=True)[: p["n"] - tvl_n]:
                nog_niet_verwerkt[id(fx)] = fx
        else:
            status = STATUS_SCHEMA_ACHTER
        rows.append({
            "ploeg_id": pid, "naam": s.get("ploeg_naam") or pid, "plaats": s.get("plaats"),
            "tvl_ontmoetingen": tvl_n, "tvl_punten": tvl_p,
            "schema_ontmoetingen": p["n"], "schema_punten": p["pts"], "onleesbaar": p["onleesbaar"],
            "status": status,
            "verwacht_punten": p["pts"] if status == STATUS_TVL_ACHTER else tvl_p,
        })
    rows.sort(key=lambda r: (r["plaats"] if r["plaats"] is not None else 99, r["naam"]))

    def _namen(status):
        return [r["naam"] for r in rows if r["status"] == status]

    return {
        "rows": rows,
        "schema_achter": _namen(STATUS_SCHEMA_ACHTER), "tvl_achter": _namen(STATUS_TVL_ACHTER),
        "punten_wijken_af": _namen(STATUS_PUNTEN), "onzeker": _namen(STATUS_ONZEKER),
        "tvl_nog_niet_verwerkt": [
            {"datum": fx.get("date_text") or "?", "thuis": fx.get("home_name") or "?",
             "uit": fx.get("away_name") or "?", "uitslag": _uitslag_tekst(fx)}
            for fx in sorted(nog_niet_verwerkt.values(), key=_date_key)
        ],
        "needs_schedule_refresh": any(r["status"] == STATUS_SCHEMA_ACHTER for r in rows),
        "all_ok": all(r["status"] == STATUS_OK for r in rows),
        "n_teams": len(rows), "n_played": len(played),
    }


# ---------------------------------------------------------------------------------------------- adapters
_PENDING_MAX_SECONDS = 20 * 60     # zo lang wachten we op een schema-update, daarna geven we het op
_POLL_SECONDS = 8                  # hoe vaak de wachtende pagina zichzelf controleert
_QP_KEY = "rank_wait"              # URL-parameter: het startmoment van een lopende update (overleeft F5)
_SLACK_SECONDS = 5                 # klokverschil tussen deze server en de achtergronddienst


def _to_epoch(value) -> Optional[float]:
    """datetime, ISO-tekst of getal -> seconden sinds 1970 (UTC); onleesbaar -> None."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


def default_adapters() -> dict:
    """De echte app-afhankelijkheden. Elke ontbrekende module laat enkel de bijhorende mogelijkheid vallen."""
    ad: dict = {
        "ranking_url": pr._build_ranking_url_from_reeks_url,
        "load_ranking": pr._load_poule_ranking_cached,
        "clear_ranking_cache": pr.clear_ranking_cache,
        "format_time": pr.format_local_time,
        "get_saved_schedule": lambda pid: ([], None),
        "clear_fs_cache": None,
        "clear_known_ctx": None,
        "clear_fixtures_cache": None,
        "local_available": lambda: False,
        "local_refresh": None,
        "github_configured": lambda: False,
        "trigger_github": None,
        "find_run": None,
        "run_progress": None,
    }
    try:
        import dashboard_common as dc
        # Elke koppeling apart: ontbreekt er 1 functie, dan vallen de andere niet weg.
        ad["get_saved_schedule"] = getattr(dc, "_get_saved_schedule", ad["get_saved_schedule"])
        ad["clear_fs_cache"] = getattr(dc, "clear_firestore_read_cache", None)
        ad["local_available"] = getattr(dc, "is_scraping_available", ad["local_available"])
        ad["local_refresh"] = getattr(dc, "_load_poule_schedule_robust", None)
        ad["clear_fixtures_cache"] = getattr(getattr(dc, "_load_poule_fixtures", None), "clear", None)
    except Exception:  # noqa: BLE001
        pass
    try:
        import lineup_scout as ls
        ad["clear_known_ctx"] = ls.clear_known_ranking_context_cache
    except Exception:  # noqa: BLE001
        pass
    try:
        import cloud_helpers as ch
        ad["github_configured"] = ch.is_github_trigger_configured

        def _trigger(pid):
            """Start de achtergronddienst voor 1 speler. Eerst met 'schedule_only' (enkel het schema, veel sneller); kent de
            workflow die invoer nog niet (scrape-padel.yml niet bijgewerkt), dan geweigerd (422) en dan de gewone start."""
            t0 = time.time()
            wf = ch._get_github_settings()[2] or ch.DEFAULT_WORKFLOW_FILE
            ok, msg = ch.trigger_github_actions_scrape(
                workflow_file=wf, inputs={"player_ids": str(pid), "mode": "missing", "schedule_only": "true"},
            )
            if ok:
                return True, msg, wf, t0, True
            if "geweigerd" in str(msg):
                t0 = time.time()
                ok, msg = ch.trigger_github_actions_scrape(player_ids=str(pid), mode="missing", workflow_file=wf)
                return ok, msg, wf, t0, False
            return False, msg, wf, t0, False
        ad["trigger_github"] = _trigger

        def _find_run(wf, after_epoch):
            """ENKELE aanvraag (geen wachtlus): de run van deze workflow die na `after_epoch` gestart is, of None."""
            import requests
            token, repo, _w, _r = ch._get_github_settings()
            if not token:
                return None
            resp = requests.get(
                f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs", params={"per_page": 5}, timeout=10,
                headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                         "X-GitHub-Api-Version": "2022-11-28"},
            )
            if resp.status_code != 200:
                return None
            for run in resp.json().get("workflow_runs", []) or []:
                created = ch._iso_to_epoch(run.get("created_at"))
                if created is not None and created >= after_epoch - _SLACK_SECONDS:
                    return run
            return None
        ad["find_run"] = _find_run
        ad["run_progress"] = getattr(ch, "_get_run_step_progress", None)
    except Exception:  # noqa: BLE001
        pass
    return ad


# ---------------------------------------------------------------------------------------------- verversen
def _clear_app_caches(ad: dict, pid: str) -> None:
    """Wist wat het schema of de stand tot 30 minuten oud kan houden (oorzaken 1 en 2)."""
    ad["clear_ranking_cache"]()
    for naam in ("clear_fs_cache", "clear_known_ctx", "clear_fixtures_cache"):
        fn = ad.get(naam)
        if callable(fn):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass
    st.session_state.pop(f"vm_fixtures_{pid}", None)


def _reload_schedule(ad: dict, pid: str):
    """Leest het schema opnieuw uit de database en zet het in de sessie. Geeft (fixtures, bijgewerkt_op) terug."""
    try:
        fixtures, sched_at = ad["get_saved_schedule"](pid)
    except Exception:  # noqa: BLE001
        fixtures, sched_at = [], None
    if fixtures:
        st.session_state[f"vm_fixtures_{pid}"] = fixtures
    return fixtures or [], sched_at


def _set_wait_param(t0: float) -> None:
    try:
        st.query_params[_QP_KEY] = str(int(t0))
    except Exception:  # noqa: BLE001
        pass


def _clear_wait_param() -> None:
    try:
        if _QP_KEY in st.query_params:
            del st.query_params[_QP_KEY]
    except Exception:  # noqa: BLE001
        pass


def _read_wait_param() -> Optional[float]:
    try:
        v = st.query_params.get(_QP_KEY)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(v, list):
        v = v[0] if v else None
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def _start_schedule_update(ad: dict, pid: str, reeks_url: str, note: Callable[[str], None]) -> Optional[dict]:
    """Start een schema-update (oorzaak 3). Lokaal rechtstreeks (geeft dan None terug: klaar), op de cloud via de
    achtergronddienst zonder te blokkeren (geeft dan de wachtende toestand terug)."""
    if ad["local_available"]() and callable(ad.get("local_refresh")):
        with st.spinner("Schema ophalen bij TVL..."):
            try:
                _fx, err, _meta = ad["local_refresh"](pid, reeks_url)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
        note(f"Schema ophalen bij TVL mislukt: {err}" if err else "Schema opnieuw opgehaald bij TVL.")
        return None
    if not ad["github_configured"]() or not callable(ad.get("trigger_github")):
        note(
            "Het schema kan niet bij TVL opgehaald worden: er is geen verbinding met de achtergronddienst ingesteld "
            "(Streamlit-secret [github])."
        )
        return None
    ok, msg, wf, t0, schedule_only = ad["trigger_github"](pid)
    if not ok:
        extra = " Controleer of het GitHub-token in de Streamlit-secrets nog geldig is." if "verlopen" in str(msg) else ""
        note(f"Schema-update kon niet gestart worden: {msg}{extra}")
        return None
    note(
        "Schema-update gestart op de achtergrond"
        + (" (enkel het schema, ongeveer 2 minuten)." if schedule_only else " (de volledige scrape draait mee, dat duurt enkele minuten langer).")
        + " Deze pagina ververst vanzelf zodra het klaar is."
    )
    return {"wf": wf, "t0": t0, "started": t0, "run_id": None, "schedule_only": schedule_only}


def run_refresh(ad: dict, pid: str, reeks_url: str, url: str):
    """De verversactie (1 knop). Geeft (logboek [(tijd, tekst)], wachtende toestand | None) terug.
    Altijd: caches wissen, stand opnieuw ophalen, schema opnieuw uit de database lezen. Loopt ons schema dan nog achter op
    TVL, dan start dit ook een schema-update; op de cloud wacht de pagina daar niet op maar controleert ze zichzelf."""
    log: list = []

    def note(tekst: str) -> None:
        # Belgische tijd, zoals de ophaaltijd van de stand (de server draait in UTC).
        log.append((ad["format_time"](datetime.now(timezone.utc)), tekst))

    pending = None
    with st.spinner("Rangschikking en schema verversen..."):
        _clear_app_caches(ad, pid)
        data = None
        try:
            data = ad["load_ranking"](url)
            note("Stand opgehaald bij TVL.")
        except Exception as exc:  # noqa: BLE001
            note(f"De stand kon niet bij TVL opgehaald worden: {type(exc).__name__}: {exc}")
        fixtures, sched_at = _reload_schedule(ad, pid)
        note(
            f"Schema opnieuw ingelezen uit de database ({len([f for f in fixtures if f.get('played')])} gespeelde "
            f"ontmoetingen, bijgewerkt op {ad['format_time'](sched_at, True)})." if fixtures
            else "Er staat (nog) geen schema in de database."
        )
    report = consistency_report((data or {}).get("standings"), fixtures) if data else None
    if report and report["needs_schedule_refresh"]:
        note(f"TVL telt meer ontmoetingen dan ons schema kent (bij {', '.join(report['schema_achter'])}) - het schema wordt opnieuw opgehaald.")
        pending = _start_schedule_update(ad, pid, reeks_url, note)
        if pending is None:  # lokaal klaar (of niet gelukt): nu opnieuw inlezen
            _clear_app_caches(ad, pid)
            _reload_schedule(ad, pid)
    return log, pending


def finish_pending(ad: dict, pid: str, url: str, note_text: str) -> None:
    """Een schema-update is klaar (of afgebroken): caches wissen, stand en schema opnieuw inlezen, wachttoestand opruimen."""
    _clear_app_caches(ad, pid)
    try:
        ad["load_ranking"](url)
    except Exception:  # noqa: BLE001
        pass
    fixtures, sched_at = _reload_schedule(ad, pid)
    log = list(st.session_state.get(f"rank_refresh_log_{pid}") or [])
    log.append((ad["format_time"](datetime.now(timezone.utc)), f"{note_text} (schema bijgewerkt op {ad['format_time'](sched_at, True)})."))
    st.session_state[f"rank_refresh_log_{pid}"] = log
    st.session_state.pop(f"rank_refresh_pending_{pid}", None)
    _clear_wait_param()


def _fail_pending(ad: dict, pid: str, url: str, tekst: str) -> None:
    """De wachttijd is voorbij of de run mislukte: opruimen met een melding (de diagnose toont of het schema nog achterloopt)."""
    log = list(st.session_state.get(f"rank_refresh_log_{pid}") or [])
    log.append((ad["format_time"](datetime.now(timezone.utc)), tekst))
    st.session_state[f"rank_refresh_log_{pid}"] = log
    st.session_state.pop(f"rank_refresh_pending_{pid}", None)
    _clear_wait_param()


def _pending_body(ad: dict, pid: str, url: str, reeks_url: str) -> None:
    """Eén controle van een lopende schema-update (draait elke _POLL_SECONDS vanzelf, zonder dat je iets doet):
    1. staat er in de database al een schema dat NA de start is weggeschreven? Dan is het klaar;
    2. anders: hoe ver staat de achtergronddienst (voortgangsbalk), en is die al klaar of mislukt?
    Bij 'klaar' wordt alles opnieuw ingelezen en de hele pagina vernieuwd."""
    pending = st.session_state.get(f"rank_refresh_pending_{pid}")
    if not pending:
        return
    now = time.time()
    # 1. is het schema al vernieuwd?
    fn = ad.get("clear_fs_cache")
    if callable(fn):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass
    try:
        _fx, sched_at = ad["get_saved_schedule"](pid)
    except Exception:  # noqa: BLE001
        sched_at = None
    stamp = _to_epoch(sched_at)
    if stamp is not None and stamp >= pending["t0"] - _SLACK_SECONDS:
        finish_pending(ad, pid, url, "Schema-update klaar")
        st.rerun()
        return
    # 2. voortgang van de achtergronddienst
    progress = None
    try:
        if pending.get("run_id") is None and callable(ad.get("find_run")):
            run = ad["find_run"](pending["wf"], pending["t0"])
            if run:
                pending["run_id"] = run.get("id")
                st.session_state[f"rank_refresh_pending_{pid}"] = pending
        if pending.get("run_id") is not None and callable(ad.get("run_progress")):
            progress = ad["run_progress"](pending["run_id"])
    except Exception:  # noqa: BLE001
        progress = None
    if progress and progress.get("status") == "completed":
        if progress.get("conclusion") == "success":
            finish_pending(ad, pid, url, "Schema-update klaar")
        else:
            _fail_pending(ad, pid, url, "De schema-update is afgerond maar niet gelukt - kijk of het schema nu nog achterloopt en probeer opnieuw.")
        st.rerun()
        return
    if now - pending["started"] > _PENDING_MAX_SECONDS:
        _fail_pending(
            ad, pid, url,
            f"De schema-update duurt langer dan {_PENDING_MAX_SECONDS // 60} minuten - er wordt niet langer gewacht. Klik opnieuw op "
            "'Ververs rangschikking' als het schema nog achterloopt.",
        )
        st.rerun()
        return
    wacht = int(now - pending["started"])
    if progress and progress.get("steps_total"):
        done, total = int(progress.get("steps_done") or 0), int(progress["steps_total"])
        stap = progress.get("current_step") or ""
        st.progress(min(1.0, done / total), text=f"Schema-update bezig: stap {min(done + 1, total)} van {total}"
                    + (f" \u2014 {stap}" if stap else "") + f" ({wacht}s)")
    else:
        st.info(f"Schema-update bezig ({wacht}s)... de voortgang is nog niet zichtbaar.")
    st.caption("Deze pagina ververst vanzelf zodra het klaar is - je hoeft niets te doen.")


# Een fragment met een eigen timer: alleen deze controle draait elke _POLL_SECONDS opnieuw, de rest van de pagina niet.
_pending_polling = st.fragment(run_every=_POLL_SECONDS)(_pending_body)


# ---------------------------------------------------------------------------------------------- weergave
def _render_report(report: Optional[dict], reeks_ok: bool = True) -> None:
    if report is None:
        return
    if report["all_ok"]:
        st.caption(
            f"\u2705 De stand van TVL en ons schema komen overeen: alle {report['n_teams']} ploegen hebben evenveel "
            f"ontmoetingen en punten ({report['n_played']} gespeelde ontmoetingen)."
        )
        return
    regels = []
    if report["schema_achter"]:
        regels.append(
            f"**Ons schema loopt achter** voor {', '.join(report['schema_achter'])}: TVL telt meer ontmoetingen dan er in "
            "ons schema gespeeld zijn. Klik op **Ververs rangschikking**: dan wordt het schema bij TVL opgehaald."
        )
    if report["tvl_achter"]:
        regels.append(
            f"**TVL heeft nog niet alle uitslagen verwerkt**: voor {', '.join(report['tvl_achter'])} staat in ons schema al een "
            "uitslag die TVL nog niet meetelt. Dat kan deze app niet oplossen - het loopt vanzelf gelijk zodra TVL de uitslag "
            "verwerkt. Verversen verandert dit niet."
        )
        for fx in report["tvl_nog_niet_verwerkt"]:
            regels.append(f"- {fx['datum']}: {fx['thuis']} - {fx['uit']}, uitslag {fx['uitslag']} (thuis - uit)")
        verschillen = [
            f"{r['naam']}: {r['verwacht_punten']} punten volgens ons schema (TVL toont {r['tvl_punten']})"
            for r in report["rows"] if r["status"] == STATUS_TVL_ACHTER
        ]
        if verschillen:
            regels.append("Verwachte punten zodra TVL bijgewerkt is: " + "; ".join(verschillen) + ".")
    if report["punten_wijken_af"]:
        regels.append(
            f"**Zelfde aantal ontmoetingen, andere punten** bij {', '.join(report['punten_wijken_af'])}: TVL kent mogelijk "
            "strafpunten of een forfait toe, of een uitslag staat in ons schema anders dan bij TVL. Hier valt niets te verversen."
        )
    if report["onzeker"]:
        regels.append(f"Niet te controleren (ontbrekend getal of onleesbare uitslag): {', '.join(report['onzeker'])}.")
    st.warning("\n\n".join(regels))
    with st.expander("Details per ploeg (TVL tegenover ons schema)", expanded=False):
        st.dataframe(
            [
                {
                    "Plaats": r["plaats"], "Ploeg": r["naam"],
                    "TVL ontmoetingen": r["tvl_ontmoetingen"], "TVL punten": r["tvl_punten"],
                    "Schema ontmoetingen": r["schema_ontmoetingen"], "Schema punten": r["schema_punten"],
                    "Status": _STATUS_TEKST.get(r["status"], r["status"]),
                }
                for r in report["rows"]
            ],
            use_container_width=True, hide_index=True,
        )


def render_refresh_block(player_id, reeks_url: str, adapters: Optional[dict] = None) -> None:
    """Verversknop + diagnose, bedoeld boven de stand in de sectie "Rangschikking" van page_lineup_lab.py.
    EEN knop: stand en schema opnieuw inlezen en, als het schema achterloopt, het schema bij TVL ophalen. Dat laatste
    wordt niet afgewacht met een blokkerende pagina: een lopende update wordt elke paar seconden gecontroleerd en de
    pagina ververst zichzelf zodra ze klaar is. Na een F5 gaat het wachten gewoon door (de URL onthoudt het startmoment)."""
    ad = adapters or default_adapters()
    pid = str(player_id)
    url = ad["ranking_url"](reeks_url)
    if not url:
        return
    state_key = f"rank_refresh_log_{pid}"
    pend_key = f"rank_refresh_pending_{pid}"
    # Na een F5 is de sessie leeg maar de URL onthoudt het startmoment van een lopende update.
    if st.session_state.get(pend_key) is None:
        t0 = _read_wait_param()
        if t0 is not None:
            if time.time() - t0 > _PENDING_MAX_SECONDS:
                _clear_wait_param()
            else:
                wf = None
                try:
                    import cloud_helpers as _ch
                    wf = _ch._get_github_settings()[2] or _ch.DEFAULT_WORKFLOW_FILE
                except Exception:  # noqa: BLE001
                    wf = "scrape-padel.yml"
                st.session_state[pend_key] = {"wf": wf, "t0": t0, "started": t0, "run_id": None, "schedule_only": None}
    pending = st.session_state.get(pend_key)
    c1, _c2 = st.columns([2, 5])
    with c1:
        klik = st.button(
            "\U0001F504 Ververs rangschikking", key=f"rank_refresh_btn_{pid}", type="primary", disabled=bool(pending),
            help="Haalt de stand (punten) opnieuw op bij TVL en leest het speelschema opnieuw in. Loopt ons schema achter op "
                 "TVL, dan wordt het schema meteen bij TVL vernieuwd en ververst de pagina zichzelf zodra dat klaar is.",
        )
    if klik:
        log, new_pending = run_refresh(ad, pid, reeks_url, url)
        st.session_state[state_key] = log
        if new_pending:
            st.session_state[pend_key] = new_pending
            _set_wait_param(new_pending["t0"])
        st.rerun()
    try:
        data = ad["load_ranking"](url)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"De stand kon niet bij TVL opgehaald worden: {type(exc).__name__}: {exc}")
        data = None
    fixtures = st.session_state.get(f"vm_fixtures_{pid}") or []
    sched_at = None
    try:
        _fx_saved, sched_at = ad["get_saved_schedule"](pid)
    except Exception:  # noqa: BLE001
        pass
    delen = []
    if data and data.get("fetched_at"):
        delen.append(f"Stand opgehaald om {ad['format_time'](data['fetched_at'])}")
    if sched_at:
        delen.append(f"schema bijgewerkt op {ad['format_time'](sched_at, True)}")
    if delen:
        st.caption(" \u00b7 ".join(delen) + ".")
    for tijd, tekst in st.session_state.get(state_key) or []:
        st.caption(f"{tijd} \u2013 {tekst}")
    if st.session_state.get(pend_key):
        _pending_polling(ad, pid, url, reeks_url)
    if data:
        _render_report(consistency_report(data.get("standings"), fixtures))
