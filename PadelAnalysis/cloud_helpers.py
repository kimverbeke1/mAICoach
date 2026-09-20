"""
cloud_helpers.py — Streamlit Community Cloud detectie voor PadelAnalysis.
Playwright/Selenium-scraping (spelers zoeken/toevoegen op TVL, profielen
verversen, klassementshistoriek laden, nieuwe tegenstanders scrapen)
vereist browser-binaries die niet beschikbaar zijn op Streamlit Community
Cloud. Deze module bepaalt of scraping mogelijk is, zodat de UI de
betrokken knoppen kan verbergen op cloud en gewoon tonen op een lokale
machine (waar je normaal `streamlit run streamlit_app.py` draait).
Cloud-verversing via een achtergronddienst:
Sinds `.github/workflows/scrape-padel.yml` bestaat (een achtergronddienst
die WEL Playwright kan draaien), kan de cloud-app die dienst op afstand
triggeren via een REST API-aanroep, zonder zelf een browser te starten.
`render_cloud_scrape_trigger()` toont daarvoor één simpele knop
("Data verversen"). Als de verbinding met de achtergronddienst nog niet
geconfigureerd is, verschijnt er gewoon niets.
Vereiste Streamlit secret (naast de reeds bestaande FIREBASE_SERVICE_ACCOUNT_JSON
die de achtergronddienst zelf gebruikt — dit is een ANDER secret,
specifiek voor de Streamlit Cloud-app om de achtergronddienst aan te spreken):
    [github]
    token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    repo  = "kimverbeke1/mAICoach"
Het token is een GitHub Personal Access Token met minstens 'Actions: Read
and write' rechten op deze repo (fine-grained token) of de klassieke
'repo' + 'workflow' scopes (classic token).
--------------------------------------------------------------------------
PADEL_ANALYSIS_MULTI_WORKFLOW_TRIGGER_2026-09-17 (op verzoek van Kim,
"dat moet wel werken via github actions... bekijk dat eens van dichterbij")
--------------------------------------------------------------------------
BUG/BEPERKING (opgelost): trigger_github_actions_scrape() en
render_cloud_scrape_trigger() konden UITSLUITEND scrape-padel.yml
(matchdata) triggeren — het workflow-bestand en de input-vorm
({"player_ids": ..., "mode": ...}) stonden hard gecodeerd. Ondertussen
bestaan er twee BIJKOMENDE, aparte workflows (refresh-padelstat.yml,
refresh-klassement.yml) met een EIGEN input-schema
({"player": ..., "max": ..., "force_all": ...}). Op Cloud kon Kim deze twee
dus enkel via de cron laten lopen, nooit direct voor een specifieke
tegenstander-ploeg triggeren.
Fix: beide functies hebben nu OPTIONELE `workflow_file`- en `inputs`-
parameters. Worden die niet meegegeven, dan is het gedrag EXACT hetzelfde
als voorheen (workflow uit st.secrets/DEFAULT_WORKFLOW_FILE,
inputs={"player_ids", "mode"}) — volledig achterwaarts compatibel met de
bestaande "🚀 Nieuwe tegenstanders ophalen"-knop. Wordt `inputs` wél
meegegeven, dan wordt die dict RECHTSTREEKS als workflow_dispatch-payload
gebruikt, ongeacht player_ids/mode.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18 (op verzoek van Kim: "bij
elke speler die je ziet daar rechtstreeks gewoon te kunnen een scrape
starten. die scrape moet dan padelstat en TVL scrapen. Wel enkel TVL
scraping voor missing/laatste periode zoals vroeger al aangehaald")
--------------------------------------------------------------------------
Nieuwe functie: render_full_player_scrape_button(). Combineert, met ÉÉN
klik, TWEE afzonderlijke achtergrond-triggers voor exact 1 speler:
  1. scrape-padel.yml, mode="missing" — TVL-matchdata, enkel de ontbrekende
     periode(s)/de huidige actieve periode.
  2. refresh-padelstat.yml, met inputs={"player": <id>, "max": "1",
     "force_all": "false"} — ververst de padelstats.be playing strength
     voor EXACT deze ene speler.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18 (op verzoek van Kim,
na het testen van de knop hierboven: "duurt eerst lang tegen dat je daar
kan op klikken. na het klikken lijkt er iets te gebeuren maar je heb niet
echt goeie feedback [...] lijkt eigenlijk niet gelukt. ik zie ook niets
verschijnen bij actions")
--------------------------------------------------------------------------
FIX (destijds): check_workflow_registered() (pre-flight check) +
st.session_state-persistentie van het laatste resultaat, zodat een pagina-
rerun de feedback niet meer kon laten verdwijnen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19 (op verzoek
van Kim, zie chat 2026-09-19)
--------------------------------------------------------------------------
Kim's melding, samengevat in 2 punten:
  1. "in het algemeen ook niet vermelden als dat nu via github is of niet.
     dat is niet relevant voor de gebruiker. ook de tekst dat deze
     omgeving zelf niet kan scrapen etc... is niet relevant voor de
     gebruiker." — ELKE tekst die de gebruiker in de lopende app ziet
     (st.caption/st.write/st.warning/st.success/st.error/label/help/
     button-tekst) mag NERGENS meer "GitHub", "workflow", "Actions",
     "deze omgeving kan niet scrapen" of vergelijkbaar jargon bevatten.
     Interne code-commentaren/docstrings (zoals deze) blijven WEL technisch
     correct, want die zijn voor ontwikkeling, niet voor de eindgebruiker.
  2. "Een beetje vervelend is dat je na het drukken op 'schema nu
     verversen' niet echt feedback krijgt van hoe ver github er mee staat
     en of hij nog bezig is of klaar is. [...] bvb gewoon stap 1 van X of
     zoiets zodat je toch enige voortgang ziet?" — een eenmalig "✅
     Getriggerd in 1.2s"-berichtje (render_cloud_scrape_trigger) ís geen
     voortgang, enkel een bevestiging dat de aanvraag vertrokken is. Dat
     probleem was al gedeeltelijk opgelost voor render_full_player_
     scrape_button() (sessie-persistente eindresultaten), maar NERGENS was
     er een tussentijdse "stap X van Y"-indicatie terwijl de achtergrond-
     taak nog liep.
FIX, twee onderdelen:
  - _find_run_started_after() / _get_run_step_progress(): NIEUWE, interne
    (niet UI-gerichte) helpers die, NA een geslaagde trigger, de recentste
    run van die achtergrondtaak opzoeken (op basis van het tijdstip van de
    trigger) en per stap (elke YAML-stap = 1 "step") aflezen of die
    voltooid, bezig, of nog niet gestart is.
  - _render_tracked_progress(): toont dit als een levende voortgangsbalk
    ("Stap 2 van 5 — <stapnaam>") in een st.empty()-placeholder, met een
    begrensde polling-lus (max ~4 minuten, elke 4s een check — ruim binnen
    de gebruikelijke 1-3 minuten wachttijd). Het EINDRESULTAAT (geslaagd/
    mislukt/duurt-langer-dan-verwacht) blijft nadien, net als voorheen,
    bewaard in st.session_state zodat een latere pagina-rerun de feedback
    niet kan laten verdwijnen.
  - render_cloud_scrape_trigger() en render_full_player_scrape_button()
    gebruiken deze nieuwe helper nu ALTIJD na een geslaagde trigger — dit
    is dus 1 centrale plek, dus ELKE bestaande aanroepplek (de "Schema nu
    verversen"-knop in page_lineup_lab.py, de klassement/playing-strength-
    knoppen in opponent_scout_ui.py, de ranking-knop in
    dashboard_common.py, ...) krijgt deze verbetering automatisch mee,
    zonder dat die aanroepplekken zelf hoeven te wijzigen.
  - check_workflow_registered() bestaat nog (intern, voor de pre-flight-
    check), maar de detail-strings zijn NEUTRAAL gemaakt (geen "GitHub",
    geen "workflow", geen "default branch" meer) — ook bij een falende
    pre-flight-check ziet de gebruiker enkel een neutrale melding.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PER_PLAYER_CLUB_REQUIRED_2026-09-20 (op verzoek van Kim: "Het
zou eigenlijk mss het eenvoudigste zijn dat je gemakkelijk op elke speler
een knop hebt om data te vernieuwen." — gecombineerd met de club-
verplichting die diezelfde dag is ingevoerd in refresh_padelstat_only.py:
"als ik dat run dan weet die niet welke club de speler toe behoort [...]
gelieve dan playing strength leeg te laten en te vragen om bij de speler de
ploeg op te geven of zoiets?")
--------------------------------------------------------------------------
ROOT CAUSE: render_full_player_scrape_button() triggerde de padelstat-
achtergrondtaak altijd zonder een "club"-input mee te geven. Sinds
refresh_padelstat_only.py een speler ZONDER gekende club nu bewust
OVERSLAAT (PADEL_ANALYSIS_CLUB_REQUIRED_TO_SCRAPE_2026-09-20, om een
verkeerde gelijknamige match te vermijden), zou een klik op deze knop voor
zo'n speler stilzwijgend NIETS opleveren voor de playing-strength-helft
(enkel een "club onbekend"-regel in de achtergrondtaak-log, die de
gebruiker in de app nooit ziet).
FIX: render_full_player_scrape_button() haalt nu eerst het bestaande
profiel op (fb.get_player_profile()). Heeft de speler AL een club, dan
verandert er niets (gedrag exact zoals voorheen). Ontbreekt de club, dan
toont de knop-sectie EERST een verplicht tekstinvoerveld ("Club/ploeg van
deze speler") — de "Scrape deze speler nu"-knop verschijnt pas zodra daar
iets is ingevuld, en die ingevulde waarde wordt meteen meegegeven als
"club"-input aan refresh-padelstat.yml (dezelfde workflow-input die de
YAML/het script al ondersteunden voor een hele ploeg, nu ook bruikbaar
voor 1 losse speler). Zo hoeft Kim nooit meer apart in de Spelers-pagina
naar een speler te zoeken om enkel een club in te vullen — dat gebeurt nu
inline, op de plek waar hij/zij de speler toch al aan het bekijken is.
"""
import os
import sys
import time
from datetime import datetime

_CLOUD_PATH_MARKERS = ("/mount/src/", "/home/adminuser/")
DEFAULT_GITHUB_REPO = "kimverbeke1/mAICoach"
DEFAULT_WORKFLOW_FILE = "scrape-padel.yml"
DEFAULT_WORKFLOW_REF = "main"
# PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18: naam van de padelstat-
# achtergrondtaak. Pas dit aan als het echte bestand in .github/workflows/
# een andere naam heeft.
PADELSTAT_WORKFLOW_FILE = "refresh-padelstat.yml"
# PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18: naam van de
# klassement-taak en van de speler-zoek-taak.
KLASSEMENT_WORKFLOW_FILE = "refresh-klassement.yml"
PLAYER_SEARCH_WORKFLOW_FILE = "search-player.yml"
# PADEL_ANALYSIS_SINGLE_PLAYER_KLASSEMENT_LATEST_ONLY_2026-09-19: bij een
# gerichte 1-speler-refresh volstaat de meest recente periode.
SINGLE_PLAYER_KLASSEMENT_MAX_PERIODS = "1"
# PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19: instellingen
# voor de begrensde voortgangs-poll-lus.
_POLL_INTERVAL_SECONDS = 4.0
_POLL_MAX_SECONDS = 240.0  # circa 4 minuten — ruim boven de gebruikelijke 1-3 min.
_RUN_LOOKUP_ATTEMPTS = 8
_RUN_LOOKUP_DELAY_SECONDS = 2.0


def is_scraping_available() -> bool:
    """
    True  -> lokaal: Playwright/browser-binaries worden verondersteld
             beschikbaar te zijn, scrape-knoppen tonen.
    False -> Streamlit Community Cloud (of expliciet uitgeschakeld):
             geen browser-binaries, scrape-knoppen verbergen.
    """
    try:
        import streamlit as st
        if "SCRAPING_AVAILABLE" in st.secrets:
            return bool(st.secrets["SCRAPING_AVAILABLE"])
    except Exception:
        pass
    cwd = os.getcwd()
    script_path = str(sys.path[0] or "")
    if any(cwd.startswith(m) or script_path.startswith(m) for m in _CLOUD_PATH_MARKERS):
        return False
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def _get_github_settings():
    """Leest [github] token/repo/workflow uit st.secrets. Geeft (token, repo, workflow, ref)."""
    try:
        import streamlit as st
        gh = st.secrets.get("github", {})
    except Exception:
        gh = {}
    token = gh.get("token") if hasattr(gh, "get") else None
    repo = (gh.get("repo") if hasattr(gh, "get") else None) or DEFAULT_GITHUB_REPO
    workflow = (gh.get("workflow") if hasattr(gh, "get") else None) or DEFAULT_WORKFLOW_FILE
    ref = (gh.get("ref") if hasattr(gh, "get") else None) or DEFAULT_WORKFLOW_REF
    return token, repo, workflow, ref


def is_github_trigger_configured() -> bool:
    """True als de verbinding met de achtergronddienst geconfigureerd is."""
    token, _repo, _workflow, _ref = _get_github_settings()
    return bool(token)


def check_workflow_registered(workflow_file: str) -> tuple[bool, str]:
    """
    Interne, read-only pre-flight check (GEEN nieuwe run) die bevestigt of
    deze achtergrondtaak momenteel bereikbaar/gereed is.
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19: de
    detail-strings zijn NEUTRAAL (geen "GitHub"/"workflow"/"default branch"
    meer) — deze functie blijft intern nuttig (bv. om vooraf te weten of een
    trigger zinvol is), maar alles wat de gebruiker uiteindelijk te zien
    krijgt moet via de aanroeper neutraal geformuleerd worden.
    Returns (gevonden, detail):
      - (True, "actief")        -> kan gestart worden.
      - (True, "state=<state>") -> bestaat, maar staat niet klaar.
      - (False, "<detail>")     -> niet bereikbaar of een andere fout.
    """
    import requests
    token, repo, _default_workflow, _ref = _get_github_settings()
    if not token:
        return False, "geen verbinding geconfigureerd"
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        return False, f"kon de achtergronddienst niet bereiken ({type(e).__name__})"
    if resp.status_code == 200:
        try:
            state = resp.json().get("state", "onbekend")
        except Exception:
            state = "onbekend"
        if state == "active":
            return True, "actief"
        return True, f"state={state} (waarschijnlijk nog niet bruikbaar)"
    if resp.status_code == 404:
        return False, "nog niet beschikbaar (nog niet volledig uitgerold)"
    if resp.status_code == 401:
        return False, "verbinding ongeldig of verlopen"
    if resp.status_code == 403:
        return False, "onvoldoende rechten"
    return False, f"onverwachte statuscode {resp.status_code}"


def trigger_github_actions_scrape(
    player_ids: str = "",
    mode: str = "missing",
    workflow_file: str | None = None,
    inputs: dict | None = None,
) -> tuple[bool, str]:
    """
    Start een achtergrondtaak op afstand. Dit draait GEEN Playwright binnen
    Streamlit zelf — het triggert enkel de externe dienst die dat wél kan.
    - workflow_file: optioneel, overschrijft welke achtergrondtaak
      getriggerd wordt (standaard: uit st.secrets['github']['workflow'] of
      DEFAULT_WORKFLOW_FILE, ONGEWIJZIGD gedrag).
    - inputs: optioneel, een dict die RECHTSTREEKS als input-payload
      gebruikt wordt. Wordt dit NIET meegegeven, dan wordt (net als
      voorheen) {"player_ids": ..., "mode": ...} gebruikt.
    Returns (success, message).
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19: het
    bericht bevat nog steeds de verstreken tijd (transparantie), maar
    vermeldt nergens meer "GitHub"/"workflow"/een link naar Actions — de
    aanroeper toont voortaan zelf de live voortgang via
    _render_tracked_progress().
    """
    import requests
    start = time.monotonic()
    token, repo, default_workflow, ref = _get_github_settings()
    workflow = workflow_file or default_workflow
    if not token:
        return False, "Geen verbinding geconfigureerd."
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload_inputs = inputs if inputs is not None else {"player_ids": player_ids or "", "mode": mode or "missing"}
    payload = {"ref": ref, "inputs": payload_inputs}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
    except requests.exceptions.Timeout:
        elapsed = time.monotonic() - start
        return False, f"Mislukt: geen reactie binnen 15s (time-out na {elapsed:.1f}s)."
    except requests.exceptions.ConnectionError as e:
        elapsed = time.monotonic() - start
        return False, f"Mislukt: kon geen verbinding maken na {elapsed:.1f}s."
    except Exception as e:
        elapsed = time.monotonic() - start
        return False, f"Mislukt: onverwachte fout na {elapsed:.1f}s."
    elapsed = time.monotonic() - start
    if resp.status_code == 204:
        return True, f"Gestart in {elapsed:.1f}s."
    if resp.status_code == 401:
        return False, f"Mislukt ({elapsed:.1f}s): de verbinding is ongeldig of verlopen."
    if resp.status_code == 403:
        return False, f"Mislukt ({elapsed:.1f}s): onvoldoende rechten."
    if resp.status_code == 404:
        return False, f"Mislukt ({elapsed:.1f}s): momenteel niet beschikbaar."
    if resp.status_code == 422:
        return False, f"Mislukt ({elapsed:.1f}s): de aanvraag werd geweigerd."
    return False, f"Mislukt ({elapsed:.1f}s)."


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19
# Interne helpers: live "stap X van Y"-voortgang, GEEN vermelding van GitHub.
# ---------------------------------------------------------------------------
def _iso_to_epoch(iso_str) -> float | None:
    if not iso_str:
        return None
    try:
        cleaned = str(iso_str).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).timestamp()
    except Exception:
        return None


def _find_run_started_after(workflow_file: str, after_epoch: float):
    """Polt de lijst van recente runs van deze achtergrondtaak tot er een
    run verschijnt die op of na `after_epoch` gestart is. Geeft de ruwe
    run-dict terug (of None als er binnen de pollingtijd niets verscheen —
    dat is geen fout, de taak kan alsnog gewoon lopen, enkel niet meteen
    zichtbaar)."""
    import requests
    token, repo, _, _ = _get_github_settings()
    if not token:
        return None
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    for _ in range(_RUN_LOOKUP_ATTEMPTS):
        try:
            resp = requests.get(url, headers=headers, params={"per_page": 5}, timeout=10)
            if resp.status_code == 200:
                runs = resp.json().get("workflow_runs", []) or []
                for run in runs:
                    created_epoch = _iso_to_epoch(run.get("created_at"))
                    # kleine marge (5s) voor kloktolerantie tussen onze eigen
                    # trigger-tijdstip en de servertijd van de achtergronddienst.
                    if created_epoch is not None and created_epoch >= after_epoch - 5:
                        return run
        except Exception:
            pass
        time.sleep(_RUN_LOOKUP_DELAY_SECONDS)
    return None


def _get_run_step_progress(run_id) -> dict | None:
    """Leest, voor 1 lopende/afgeronde run, het aantal voltooide stappen af
    t.o.v. het totaal (over de eerste job — al onze achtergrondtaken
    gebruiken telkens exact 1 job). Geeft None terug als dit niet kon
    worden opgehaald (bv. tijdelijk netwerkprobleem) — de aanroeper moet dit
    dan gewoon opnieuw proberen bij de volgende poll."""
    import requests
    token, repo, _, _ = _get_github_settings()
    if not token:
        return None
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        jobs = resp.json().get("jobs", []) or []
    except Exception:
        return None
    if not jobs:
        return None
    job = jobs[0]
    steps = job.get("steps", []) or []
    total = len(steps)
    done = sum(1 for s in steps if s.get("status") == "completed")
    current_step = None
    for s in steps:
        if s.get("status") != "completed":
            current_step = s.get("name")
            break
    if current_step is None and steps:
        current_step = steps[-1].get("name")
    return {
        "status": job.get("status"),
        "conclusion": job.get("conclusion"),
        "steps_total": total,
        "steps_done": done,
        "current_step": current_step,
    }


def _render_tracked_progress(workflow_file: str, trigger_epoch: float, placeholder, label_prefix: str = "") -> dict:
    """Toont een LEVENDE voortgangsbalk ("Stap X van Y — <stapnaam>") in
    `placeholder`, door de zonet gestarte achtergrondtaak op te zoeken en
    periodiek te bevragen (begrensde lus, max _POLL_MAX_SECONDS). Dit is
    een BLOKKERENDE aanroep (de pagina toont de voortgang live binnen deze
    ene klik, i.p.v. een enkel "gestart"-berichtje) — bewust gekozen zodat
    Kim exact ziet "stap 2 van 5" i.p.v. enkel een eenmalige bevestiging.
    Geeft een dict terug met het laatst gekende resultaat, zodat de
    aanroeper dit kan bewaren in st.session_state (blijft zichtbaar na een
    latere pagina-rerun)."""
    run = _find_run_started_after(workflow_file, trigger_epoch)
    if run is None:
        placeholder.info(f"{label_prefix}Bezig, voortgang nog niet zichtbaar...")
        return {"found": False, "status": "unknown"}
    run_id = run.get("id")
    deadline = time.monotonic() + _POLL_MAX_SECONDS
    last_progress = None
    while time.monotonic() < deadline:
        progress = _get_run_step_progress(run_id)
        if progress:
            last_progress = progress
            total = progress["steps_total"] or 1
            done = progress["steps_done"]
            step_label = progress.get("current_step") or ""
            frac = min(1.0, done / total)
            step_num = min(done + 1, total)
            status_txt = f"{label_prefix}Stap {step_num} van {total}"
            if step_label:
                status_txt += f" — {step_label}"
            placeholder.progress(frac, text=status_txt)
            if progress.get("status") == "completed":
                break
        time.sleep(_POLL_INTERVAL_SECONDS)
    if last_progress and last_progress.get("status") == "completed":
        if last_progress.get("conclusion") == "success":
            placeholder.success(f"{label_prefix}Klaar.")
            return {"found": True, "status": "success"}
        placeholder.warning(f"{label_prefix}Afgerond, maar mogelijk niet volledig gelukt.")
        return {"found": True, "status": "completed_with_issue"}
    placeholder.info(f"{label_prefix}Duurt langer dan verwacht — dit loopt op de achtergrond door en komt vanzelf binnen.")
    return {"found": True, "status": "still_running"}


def render_cloud_scrape_trigger(
    key_prefix: str = "",
    player_ids: str = "",
    mode: str = "missing",
    label: str = "🔄 Data verversen",
    workflow_file: str | None = None,
    inputs: dict | None = None,
    help_text: str | None = None,
) -> None:
    """
    Toont, enkel relevant op cloud, één eenvoudige knop om data te verversen
    (start op de achtergrond de bestaande verwerking). Als de verbinding nog
    niet geconfigureerd is, wordt er niets getoond.
    player_ids: leeg = alle spelers; of komma-gescheiden lijst voor specifieke
                speler(s) (bv. enkel de huidige speler verversen).
    mode:       "missing" (enkel ontbrekende periodes, standaard en snelst),
                "new_users", of "full".
    - workflow_file / inputs: zie trigger_github_actions_scrape(). Laat beide
      weg voor het ONGEWIJZIGDE, oorspronkelijke gedrag.
    - help_text: optionele tooltip op de knop (st.button(help=...)).
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19: toont nu,
    NA een geslaagde trigger, een LEVENDE "stap X van Y"-voortgangsbalk
    (_render_tracked_progress) i.p.v. enkel een eenmalig "gestart"-berichtje.
    Het eindresultaat blijft, net als voorheen, bewaard in st.session_state.
    """
    import streamlit as st
    if not is_github_trigger_configured():
        return
    result_key = f"{key_prefix}_last_result"
    if st.button(label, key=f"{key_prefix}_gh_trigger", type="primary", help=help_text):
        trigger_epoch = time.time()
        wf = workflow_file or _get_github_settings()[2] or DEFAULT_WORKFLOW_FILE
        with st.spinner("Bezig met starten..."):
            ok, msg = trigger_github_actions_scrape(
                player_ids=player_ids, mode=mode, workflow_file=workflow_file, inputs=inputs,
            )
        if not ok:
            st.session_state[result_key] = {
                "ok": False, "ts": time.strftime("%H:%M:%S"), "status": "failed",
            }
            st.error("Kon niet gestart worden. Probeer het later opnieuw.")
        else:
            placeholder = st.empty()
            outcome = _render_tracked_progress(wf, trigger_epoch, placeholder)
            st.session_state[result_key] = {
                "ok": True, "ts": time.strftime("%H:%M:%S"), "status": outcome.get("status"),
            }
    last = st.session_state.get(result_key)
    if last:
        st.caption(f"Laatste update: {last['ts']}")
        if not last["ok"]:
            st.error("Kon niet gestart worden. Probeer het later opnieuw.")
        elif last["status"] == "success":
            st.success("Data is ververst.")
        elif last["status"] == "still_running":
            st.info("Loopt nog op de achtergrond — de gegevens komen vanzelf binnen.")
        elif last["status"] == "completed_with_issue":
            st.warning("Afgerond, maar mogelijk niet volledig gelukt. Probeer het gerust opnieuw.")


def render_full_player_scrape_button(
    player_id: str,
    player_name: str = "",
    key_prefix: str = "full_scrape",
) -> None:
    """
    PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18 (op verzoek van Kim):
    "bij elke speler die je ziet daar rechtstreeks gewoon te kunnen een
    scrape starten. die scrape moet dan padelstat en TVL scrapen."
    Toont, enkel relevant op cloud en enkel als de verbinding geconfigureerd
    is, ÉÉN knop die met 1 klik BEIDE achtergrondtaken start voor exact deze
    ene speler: matchdata (ontbrekende/huidige periode) en playing strength.
    Het OFFICIËLE klassement wordt hier bewust NIET meegenomen — dat
    verandert maar 2x per jaar en wordt apart, voor de volledige
    spelerslijst, op de juiste momenten ververst.
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19: toont nu
    voor BEIDE triggers een levende "stap X van Y"-voortgangsbalk i.p.v.
    enkel een eenmalig "gestart"-berichtje + workflow-jargon. Er wordt
    nergens meer "GitHub"/"workflow" vermeld — enkel neutrale taal.
    PADEL_ANALYSIS_PER_PLAYER_CLUB_REQUIRED_2026-09-20 (op verzoek van Kim:
    "gemakkelijk op elke speler een knop hebt om data te vernieuwen" +
    "gelieve dan playing strength leeg te laten en te vragen om bij de
    speler de ploeg op te geven"): refresh_padelstat_only.py slaat een
    speler zonder gekende club sinds deze fix bewust over (om een verkeerde
    gelijknamige match te vermijden). Deze functie haalt daarom EERST het
    bestaande profiel op: heeft de speler al een club, verandert er niets;
    ontbreekt de club, dan verschijnt HIER, INLINE, een verplicht
    tekstinvoerveld — de scrape-knop wordt pas actief zodra daar iets is
    ingevuld, en die waarde wordt meteen als "club"-input meegegeven aan
    refresh-padelstat.yml (dezelfde workflow-input die al bestond voor een
    hele ploeg-refresh, hier gebruikt voor 1 losse speler)."""
    import streamlit as st
    import firebase_service as fb
    if not is_github_trigger_configured():
        return
    result_key = f"{key_prefix}_last_result_{player_id}"
    label_naam = f" voor {player_name}" if player_name else ""

    # PADEL_ANALYSIS_PER_PLAYER_CLUB_REQUIRED_2026-09-20: club vooraf
    # controleren, zodat we weten of het invoerveld getoond moet worden.
    try:
        existing_profile = fb.get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        existing_profile = {}
    existing_club = (existing_profile.get("club") or "").strip()

    club_to_use = existing_club
    if not existing_club:
        club_input_key = f"{key_prefix}_club_input_{player_id}"
        club_to_use = st.text_input(
            f"Club/ploeg van {player_name or 'deze speler'} (nog onbekend — nodig om de playing "
            "strength betrouwbaar op te zoeken bij gelijknamige spelers)",
            key=club_input_key,
            placeholder="Bv. Padel Factory",
        ).strip()
        if not club_to_use:
            st.caption(
                "ℹ️ Vul hierboven de club/ploeg in om de playing strength voor deze speler te kunnen "
                "verversen. De matchdata-verversing hieronder werkt ook zonder club."
            )

    if st.button(
        f"🔄 Scrape deze speler nu{label_naam}",
        key=f"{key_prefix}_full_scrape_{player_id}",
        type="primary",
        help=(
            "Ververst op de achtergrond de matchdata (enkel ontbrekende/huidige periode) en de "
            "playing strength voor deze speler. Duurt meestal enkele minuten. Het officiële "
            "klassement wordt hier bewust niet meegenomen — dat wordt apart, voor de volledige "
            "spelerslijst, op de juiste momenten ververst."
        ),
    ):
        trigger_epoch = time.time()
        tvl_workflow = _get_github_settings()[2] or DEFAULT_WORKFLOW_FILE
        tvl_registered, _ = check_workflow_registered(tvl_workflow)
        padelstat_registered, _ = check_workflow_registered(PADELSTAT_WORKFLOW_FILE)
        ok_tvl = ok_padelstat = False
        if tvl_registered:
            ok_tvl, _msg_tvl = trigger_github_actions_scrape(
                player_ids=str(player_id), mode="missing", workflow_file=tvl_workflow,
            )
        # PADEL_ANALYSIS_PER_PLAYER_CLUB_REQUIRED_2026-09-20: enkel de
        # padelstat-trigger starten als er een club bekend/ingevuld is —
        # anders zou refresh_padelstat_only.py deze speler toch weer
        # overslaan (club_onbekend), en zou de voortgangsbalk hieronder op
        # niets wachten.
        if not club_to_use:
            st.info(
                "Playing strength wordt overgeslagen zolang de club/ploeg hierboven niet is "
                "ingevuld. Matchdata wordt wel gewoon ververst."
            )
        elif padelstat_registered:
            padelstat_inputs = {"player": str(player_id), "max": "1", "force_all": "false"}
            if not existing_club:
                # Nieuw ingevulde club: meteen meegeven zodat refresh_
                # padelstat_only.py die als club_override kan gebruiken EN
                # eenmalig backfillen naar het profiel (zie dat bestand).
                padelstat_inputs["club"] = club_to_use
            ok_padelstat, _msg_padelstat = trigger_github_actions_scrape(
                workflow_file=PADELSTAT_WORKFLOW_FILE, inputs=padelstat_inputs,
            )
        status_tvl = status_padelstat = "failed"
        if ok_tvl:
            ph_tvl = st.empty()
            outcome_tvl = _render_tracked_progress(tvl_workflow, trigger_epoch, ph_tvl, label_prefix="Matchdata: ")
            status_tvl = outcome_tvl.get("status")
        else:
            st.error("Matchdata: kon niet gestart worden.")
        if ok_padelstat:
            ph_padelstat = st.empty()
            outcome_padelstat = _render_tracked_progress(
                PADELSTAT_WORKFLOW_FILE, trigger_epoch, ph_padelstat, label_prefix="Playing strength: ",
            )
            status_padelstat = outcome_padelstat.get("status")
        elif club_to_use:
            st.error("Playing strength: kon niet gestart worden.")
        st.session_state[result_key] = {
            "timestamp": time.strftime("%H:%M:%S"),
            "tvl_ok": ok_tvl, "tvl_status": status_tvl,
            "padelstat_ok": ok_padelstat, "padelstat_status": status_padelstat,
            "padelstat_skipped_no_club": not club_to_use,
        }
    # PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18: het laatst
    # bekende resultaat wordt ALTIJD opnieuw getoond, zodat een latere
    # pagina-rerun de feedback niet kan laten verdwijnen.
    last = st.session_state.get(result_key)
    if last:
        st.caption(f"Resultaat van de laatste poging, om {last['timestamp']}:")
        _status_labels = {
            "success": ("success", "Klaar."),
            "still_running": ("info", "Loopt nog op de achtergrond — komt vanzelf binnen."),
            "completed_with_issue": ("warning", "Afgerond, maar mogelijk niet volledig gelukt."),
            "unknown": ("info", "Bezig, voortgang nog niet zichtbaar..."),
            "failed": ("error", "Kon niet gestart worden."),
        }
        for veld_ok, veld_status, titel in (
            ("tvl_ok", "tvl_status", "Matchdata"),
            ("padelstat_ok", "padelstat_status", "Playing strength"),
        ):
            ok = last.get(veld_ok)
            if titel == "Playing strength" and last.get("padelstat_skipped_no_club"):
                st.info("**Playing strength**: overgeslagen (club/ploeg was niet ingevuld).")
                continue
            status = last.get(veld_status) if ok else "failed"
            kind, tekst = _status_labels.get(status, ("info", "Onbekende status."))
            renderer = {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}[kind]
            renderer(f"**{titel}**: {tekst}")
    st.caption(
        "ℹ️ Het officiële klassement wordt hier niet ververst — dat verandert maar 2x per jaar "
        "en wordt daarom apart, op de juiste momenten, voor de volledige spelerslijst ververst."
    )


def trigger_player_search(first_name: str, last_name: str, club: str = "") -> tuple[bool, str]:
    """
    PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18: dunne wrapper rond
    trigger_github_actions_scrape() die de speler-zoek-taak aanroept, voor
    het zoeken van een NOG ONBEKENDE speler op naam."""
    return trigger_github_actions_scrape(
        workflow_file=PLAYER_SEARCH_WORKFLOW_FILE,
        inputs={
            "first_name": first_name or "",
            "last_name": last_name or "",
            "club": club or "",
        },
    )


def render_cloud_player_search(
    key_prefix: str = "cloud_player_search",
    default_first: str = "",
    default_last: str = "",
    default_club: str = "",
) -> None:
    """
    PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18 (op verzoek van Kim):
    Cloud-tegenhanger van de lokale "🔍 Zoek op TVL-website"-flow in
    page_add_player.py. Triggert de speler-zoek-taak en toont, zodra
    beschikbaar, de kandidaten uit firebase_service.get_player_search_cache().
    Dit is ONVERMIJDELIJK een polling-flow (het resultaat komt pas na de
    zoekactie binnen): na het triggeren toont deze functie een
    "🔄 Resultaat ophalen"-knop, die de cache opnieuw uitleest tot er een
    resultaat is.
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_AND_REAL_PROGRESS_2026-09-19: alle
    teksten neutraal gemaakt (geen "GitHub Actions" meer).
    """
    import streamlit as st
    import firebase_service as fb
    if not is_github_trigger_configured():
        st.caption(
            "Nieuwe spelers zoeken is via deze weg nog niet beschikbaar. Doe dit lokaal via "
            "'➕ Speler toevoegen'."
        )
        return
    with st.form(f"{key_prefix}_form"):
        c1, c2, c3 = st.columns([2, 2, 2])
        first = c1.text_input("Voornaam", value=default_first, key=f"{key_prefix}_first")
        last = c2.text_input("Achternaam", value=default_last, key=f"{key_prefix}_last")
        club = c3.text_input("Club (optioneel)", value=default_club, key=f"{key_prefix}_club")
        submitted = st.form_submit_button(
            "🔍 Zoeken", use_container_width=True, type="primary",
        )
    trigger_key = f"{key_prefix}_triggered_at"
    query_key = f"{key_prefix}_query"
    candidates_key = f"{key_prefix}_candidates"
    if submitted:
        if not first.strip() and not last.strip():
            st.warning("Geef minstens een voornaam of achternaam in.")
        else:
            with st.spinner("Zoekopdracht starten..."):
                ok, msg = trigger_player_search(first.strip(), last.strip(), club.strip())
            if ok:
                st.session_state[trigger_key] = time.time()
                st.session_state[query_key] = {
                    "first": first.strip(), "last": last.strip(), "club": club.strip(),
                }
                st.session_state.pop(candidates_key, None)
                st.success(
                    "Zoekopdracht gestart. Klik hieronder op '🔄 Resultaat ophalen' zodra dit is "
                    "afgerond (meestal 1-3 minuten)."
                )
            else:
                st.error("Kon de zoekopdracht niet starten. Probeer het later opnieuw.")
    query = st.session_state.get(query_key)
    if not query:
        return
    st.caption(
        f"Laatste zoekopdracht: '{query['first']} {query['last']}'"
        + (f" ({query['club']})" if query["club"] else "")
    )
    if st.button("🔄 Resultaat ophalen", key=f"{key_prefix}_poll"):
        name_query = f"{query['first']} {query['last']}".strip()
        cached = fb.get_player_search_cache(name_query, query["club"] or None, sport="Padel")
        if not cached:
            st.info(
                "Nog geen resultaat gevonden. Dit loopt mogelijk nog — probeer het over een "
                "minuutje opnieuw."
            )
        else:
            st.session_state[candidates_key] = cached.get("candidates") or []
    candidates = st.session_state.get(candidates_key)
    if candidates is None:
        return
    if not candidates:
        st.caption("Geen spelers gevonden op TVL voor deze zoekopdracht.")
        return
    st.success(f"{len(candidates)} kandidaat(en) gevonden")
    for i, c in enumerate(candidates):
        name = c.get("display_name") or "?"
        club_str = c.get("club") or ""
        pid = c.get("player_id") or "?"
        url = c.get("dashboard_url") or ""
        with st.container(border=True):
            col_info, col_btn = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{name}**")
                st.caption(f"🏟️ {club_str} · ID: {pid}" if club_str else f"ID: {pid}")
                if url:
                    st.markdown(f"[Profiel op TVL ↗]({url})", unsafe_allow_html=False)
            with col_btn:
                already_added_key = f"{key_prefix}_added_{i}"
                if not st.session_state.get(already_added_key):
                    if st.button(
                        "➕ Toevoegen", key=f"{key_prefix}_add_{i}",
                        use_container_width=True, type="primary",
                    ):
                        fb.save_player_profile(
                            player_id=str(pid), display_name=name,
                            club=club_str or None, dashboard_url=url or None,
                            aliases=[name],
                        )
                        # PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17:
                        # zelfde marker als de lokale "➕ Speler toevoegen"-pagina,
                        # zodat cleanup_ghost_profiles.py deze speler nooit opruimt.
                        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(
                            {"added_by": "manual"}, merge=True,
                        )
                        st.session_state[already_added_key] = True
                        st.rerun()
        if st.session_state.get(f"{key_prefix}_added_{i}"):
            st.success(f"✅ {name} toegevoegd. Start hieronder de volledige verversing:")
            render_full_player_scrape_button(
                str(pid), player_name=name, key_prefix=f"{key_prefix}_scrape_{i}",
            )
