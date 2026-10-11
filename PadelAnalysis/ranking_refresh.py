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
        "local_available": lambda: False,
        "local_refresh": None,
        "github_configured": lambda: False,
        "trigger_github": None,
        "track_progress": None,
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
            t0 = time.time()
            ok, msg = ch.trigger_github_actions_scrape(player_ids=str(pid), mode="missing")
            wf = ch._get_github_settings()[2] or ch.DEFAULT_WORKFLOW_FILE
            return ok, msg, wf, t0
        ad["trigger_github"] = _trigger
        ad["track_progress"] = getattr(ch, "_render_tracked_progress", None)
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


def _refresh_schedule(ad: dict, pid: str, reeks_url: str, note: Callable[[str], None]) -> bool:
    """Haalt het schema opnieuw op bij TVL (oorzaak 3). True als het resultaat klaar is, anders False (met een toelichting)."""
    if ad["local_available"]() and callable(ad.get("local_refresh")):
        with st.spinner("Schema ophalen bij TVL..."):
            try:
                _fx, err, _meta = ad["local_refresh"](pid, reeks_url)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
        if err:
            note(f"Schema ophalen bij TVL mislukt: {err}")
            return False
        note("Schema opnieuw opgehaald bij TVL.")
        return True
    if not ad["github_configured"]() or not callable(ad.get("trigger_github")):
        note(
            "Het schema kan niet bij TVL opgehaald worden: er is geen verbinding met de achtergronddienst ingesteld "
            "(Streamlit-secret [github])."
        )
        return False
    ok, msg, wf, t0 = ad["trigger_github"](pid)
    if not ok:
        extra = " Controleer of het GitHub-token in de Streamlit-secrets nog geldig is." if "verlopen" in str(msg) else ""
        note(f"Schema-update kon niet gestart worden: {msg}{extra}")
        return False
    note("Schema-update gestart op de achtergrond (duurt ongeveer 3 tot 5 minuten).")
    track = ad.get("track_progress")
    if not callable(track):
        note("Klik over enkele minuten opnieuw op 'Ververs rangschikking' om het resultaat in te lezen.")
        return False
    placeholder = st.empty()
    try:
        outcome = track(wf, t0, placeholder) or {}
    except Exception as exc:  # noqa: BLE001
        note(f"De voortgang kon niet gevolgd worden ({type(exc).__name__}). Klik straks opnieuw op 'Ververs rangschikking'.")
        return False
    status = outcome.get("status")
    if status == "success":
        note("Schema-update klaar.")
        return True
    if status == "still_running":
        note("De schema-update loopt nog. Klik over enkele minuten opnieuw op 'Ververs rangschikking' om het resultaat in te lezen.")
    elif status == "completed_with_issue":
        note("De schema-update is afgerond maar mogelijk niet volledig gelukt - het ingelezen schema kan nog oud zijn.")
    else:
        note("De voortgang van de schema-update was niet te volgen. Klik straks opnieuw op 'Ververs rangschikking'.")
    return False


def run_refresh(ad: dict, pid: str, reeks_url: str, url: str, force_schedule: bool) -> list:
    """De verversactie. Geeft het logboek [(tijd, tekst)] terug."""
    log: list = []

    def note(tekst: str) -> None:
        # Belgische tijd, zoals de ophaaltijd van de stand (de server draait in UTC).
        log.append((ad["format_time"](datetime.now(timezone.utc)), tekst))

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
    if force_schedule or (report and report["needs_schedule_refresh"]):
        if report and report["needs_schedule_refresh"] and not force_schedule:
            note(f"TVL telt meer ontmoetingen dan ons schema kent (bij {', '.join(report['schema_achter'])}) - schema wordt opnieuw opgehaald.")
        if _refresh_schedule(ad, pid, reeks_url, note):
            _clear_app_caches(ad, pid)
            try:
                data = ad["load_ranking"](url)
            except Exception:  # noqa: BLE001
                pass
            fixtures, sched_at = _reload_schedule(ad, pid)
            note(f"Nieuw schema ingelezen (bijgewerkt op {ad['format_time'](sched_at, True)}).")
    return log


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
            "ons schema gespeeld zijn. Klik op **Ververs rangschikking** om het schema bij TVL op te halen."
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
    """Verversknop + diagnose, bedoeld boven de stand in de sectie "Rangschikking" van page_lineup_lab.py."""
    ad = adapters or default_adapters()
    pid = str(player_id)
    url = ad["ranking_url"](reeks_url)
    if not url:
        return
    state_key = f"rank_refresh_log_{pid}"
    c1, c2, _c3 = st.columns([2, 2, 3])
    with c1:
        klik = st.button(
            "\U0001F504 Ververs rangschikking", key=f"rank_refresh_btn_{pid}", type="primary",
            help="Haalt de stand (punten) opnieuw op bij TVL en leest het speelschema opnieuw in. Loopt ons schema achter op "
                 "TVL, dan wordt het schema meteen bij TVL vernieuwd.",
        )
    with c2:
        forceer = st.button(
            "\U0001F4C5 Schema ook bij TVL ophalen", key=f"rank_refresh_sched_btn_{pid}",
            help="Haalt het poule-schema ALTIJD opnieuw op bij TVL (ongeveer 3 tot 5 minuten), ook als alles klopt.",
        )
    if klik or forceer:
        st.session_state[state_key] = run_refresh(ad, pid, reeks_url, url, force_schedule=bool(forceer))
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
    if data:
        _render_report(consistency_report(data.get("standings"), fixtures))
