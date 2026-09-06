"""
scrape_jobs.py — gedeelde achtergrond-scrape-job registry voor PadelAnalysis.

Losstaand bestand (geen afhankelijkheid van dashboard.py of
player_inline_actions.py) zodat beide dit probleemloos kunnen importeren
zonder circulaire imports.

PADEL_ANALYSIS_BACKGROUND_SCRAPE_2026-09-06:
Scrapes lopen voortaan in een aparte Python-thread, ONAFHANKELIJK van welke
pagina je binnen de app bekijkt. Dashboard.py wisselt enkel welke
render-functie wordt aangeroepen binnen hetzelfde Streamlit-script/sessie --
st.session_state blijft daarbij gewoon behouden, dus een achtergrondthread
die al gestart is blijft gewoon doorlopen, ook als je ondertussen naar een
andere pagina/tab binnen de app klikt.

BELANGRIJKE REGEL: de achtergrondthread mag NOOIT rechtstreeks st.*-functies
aanroepen (dat werkt niet correct/veilig buiten de hoofd-scriptthread van
Streamlit -- "missing ScriptRunContext"-waarschuwingen/crashes). De thread
schrijft daarom enkel naar een gewoon Python-dict in st.session_state; het
hoofdscript (bij elke rerun, dus bij elke klik/navigatie) leest dat dict uit
en doet zelf alle st.*-aanroepen (progress bars, meldingen, ...).

BEPERKING: de voortgangsweergave ververst enkel bij een volgende Streamlit-
rerun (bv. een klik ergens, van pagina wisselen, een ander veld invullen).
Er is geen automatische live-refresh zonder een extra package zoals
streamlit-autorefresh (niet aangenomen als beschikbaar) -- de scrape zelf
loopt wel degelijk continu door op de achtergrond, ongeacht wat je
ondertussen in de browser doet. Een "🔄 Status verversen"-knop is voorzien
voor wie de voortgang tussentijds wil bekijken zonder van pagina te wisselen.

LET OP bij meerdere gelijktijdige scrapes: elke scrape start een volledige
Chromium-browser via Playwright. Meerdere spelers TEGELIJK op de achtergrond
verversen laat dus meerdere browsers parallel draaien (meer CPU/geheugen).
Voor een enkele gebruiker die af en toe klikt is dit geen probleem, maar
vermijd het bewust in bulk starten van veel gelijktijdige achtergrond-jobs.
"""
import threading
import time
import streamlit as st


def get_scrape_jobs() -> dict:
    if "scrape_jobs" not in st.session_state:
        st.session_state["scrape_jobs"] = {}
    return st.session_state["scrape_jobs"]


def is_scrape_running(player_id: str) -> bool:
    return get_scrape_jobs().get(str(player_id), {}).get("status") == "running"


def start_background_scrape(player_id: str, label: str, full: bool = False) -> bool:
    """
    Start een scrape op de achtergrond voor player_id. Returns False (en doet
    niets) als er al een job loopt voor deze speler -- voorkomt dubbele
    gelijktijdige scrapes van dezelfde speler.
    """
    jobs = get_scrape_jobs()
    pid = str(player_id)
    if jobs.get(pid, {}).get("status") == "running":
        return False
    jobs[pid] = {
        "status": "running",
        "label": label,
        "i": 0,
        "total": 0,
        "phase": "starting",
        "period_label": "",
        "error": None,
        "result_stats": None,
        "started_at": time.time(),
    }

    def _progress(i, total, plabel, status):
        job = jobs.get(pid)
        if job is not None:
            job["i"] = i
            job["total"] = total
            job["phase"] = status
            job["period_label"] = plabel

    def _run():
        try:
            from scrape_player import scrape_player as _scrape
            result = _scrape(
                pid,
                force_full_refresh=full,
                save_to_firebase=True,
                progress_callback=_progress,
            )
            job = jobs.get(pid)
            if job is not None:
                job["status"] = "done"
                job["result_stats"] = result.get("stats", {})
                job["error"] = result.get("error") or result.get("firebase_error")
        except Exception as e:
            job = jobs.get(pid)
            if job is not None:
                job["status"] = "error"
                job["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return True


def render_active_jobs_banner() -> None:
    """
    Toont, bovenaan elke pagina, de status van alle lopende/recent
    afgeronde achtergrond-scrapes. Moet aangeroepen worden vanuit
    dashboard.py, na de navigatiebalk en vóór de pagina-inhoud, zodat dit
    zichtbaar blijft ongeacht welke pagina je bekijkt.
    """
    jobs = get_scrape_jobs()
    if not jobs:
        return
    to_clear = []
    any_running = False
    for pid, job in list(jobs.items()):
        label = job.get("label") or pid
        status = job.get("status")
        if status == "running":
            any_running = True
            total = job.get("total") or 0
            i = job.get("i") or 0
            frac = min(1.0, i / total) if total else 0.0
            phase_txt = {
                "starting": "voorbereiden", "discovering": "periodes opzoeken",
                "fetching": "ophalen", "parsing": "verwerken",
            }.get(job.get("phase"), job.get("phase") or "bezig")
            suffix = f" ({i}/{total})" if total else ""
            period = job.get("period_label") or ""
            extra = f" — {period[:40]}" if period else ""
            st.info(
                f"🔄 **{label}** wordt ververst op de achtergrond — {phase_txt}{suffix}{extra}. "
                f"Je kan gerust verder klikken of van pagina wisselen."
            )
            st.progress(frac)
        elif status == "done":
            s = job.get("result_stats") or {}
            err = job.get("error")
            if err:
                st.warning(f"⚠️ **{label}**: verversen afgerond met een fout — {err}")
            else:
                st.success(
                    f"✅ **{label}**: verversen klaar — "
                    f"{s.get('total_matches','?')} matches, winrate {s.get('winrate','?')}%."
                )
            if st.button("Sluiten", key=f"dismiss_job_{pid}"):
                to_clear.append(pid)
        elif status == "error":
            st.error(f"❌ **{label}**: verversen mislukt — {job.get('error')}")
            if st.button("Sluiten", key=f"dismiss_job_err_{pid}"):
                to_clear.append(pid)
    for pid in to_clear:
        jobs.pop(pid, None)
    if any_running:
        if st.button("🔄 Status verversen", key="refresh_scrape_jobs_banner"):
            st.rerun()
    if jobs:
        st.divider()
