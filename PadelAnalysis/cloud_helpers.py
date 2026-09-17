"""
cloud_helpers.py — Streamlit Community Cloud detectie voor PadelAnalysis.

Playwright/Selenium-scraping (spelers zoeken/toevoegen op TVL, profielen
verversen, klassementshistoriek laden, nieuwe tegenstanders scrapen)
vereist browser-binaries die niet beschikbaar zijn op Streamlit Community
Cloud. Deze module bepaalt of scraping mogelijk is, zodat de UI de
betrokken knoppen kan verbergen op cloud en gewoon tonen op een lokale
machine (waar je normaal `streamlit run streamlit_app.py` draait).

Cloud-scrape via GitHub Actions:
Sinds `.github/workflows/scrape-padel.yml` bestaat (een GitHub Actions
workflow die WEL Playwright kan draaien, op een ubuntu-latest runner),
kan de cloud-app die workflow op afstand triggeren via de GitHub REST
API (`workflow_dispatch`), zonder zelf een browser te starten.
`render_cloud_scrape_trigger()` toont daarvoor één simpele knop
("Data verversen"). Als het GitHub-token nog niet geconfigureerd is,
verschijnt er gewoon niets (geen technische uitleg meer in de hoofd-UI —
dat hoort thuis in de code/documentatie, niet in de app zelf).

Vereiste Streamlit secret (naast de reeds bestaande FIREBASE_SERVICE_ACCOUNT_JSON
die de GitHub Actions workflow zelf gebruikt — dit is een ANDER secret,
specifiek voor de Streamlit Cloud-app om de GitHub API aan te spreken):
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
bestaan er twee BIJKOMENDE, aparte dagelijkse workflows
(refresh-padelstat.yml, refresh-klassement.yml) met een EIGEN
input-schema ({"player": ..., "max": ..., "force_all": ...}). Op Cloud kon
Kim deze twee dus enkel via de dagelijkse cron laten lopen, nooit direct
voor een specifieke tegenstander-ploeg triggeren.

Fix: beide functies hebben nu OPTIONELE `workflow_file`- en `inputs`-
parameters. Worden die niet meegegeven, dan is het gedrag EXACT hetzelfde
als voorheen (workflow uit st.secrets/DEFAULT_WORKFLOW_FILE,
inputs={"player_ids", "mode"}) — volledig achterwaarts compatibel met de
bestaande "🚀 Nieuwe tegenstanders ophalen"-knop. Wordt `inputs` wél
meegegeven, dan wordt die dict RECHTSTREEKS als workflow_dispatch-payload
gebruikt, ongeacht player_ids/mode — zo kan dezelfde functie nu ook
refresh-klassement.yml/refresh-padelstat.yml aansturen met hun eigen
input-namen, vanuit opponent_scout_ui.py.
"""
import os
import sys

_CLOUD_PATH_MARKERS = ("/mount/src/", "/home/adminuser/")
DEFAULT_GITHUB_REPO = "kimverbeke1/mAICoach"
DEFAULT_WORKFLOW_FILE = "scrape-padel.yml"
DEFAULT_WORKFLOW_REF = "main"


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
    """True als er een GitHub-token in st.secrets['github']['token'] staat."""
    token, _repo, _workflow, _ref = _get_github_settings()
    return bool(token)


def trigger_github_actions_scrape(
    player_ids: str = "",
    mode: str = "missing",
    workflow_file: str | None = None,
    inputs: dict | None = None,
) -> tuple[bool, str]:
    """
    Start een GitHub Actions-workflow op afstand via een `workflow_dispatch`-
    call naar de GitHub REST API. Dit draait GEEN Playwright binnen
    Streamlit zelf — het triggert enkel de externe workflow die dat wél kan
    (ubuntu-latest runner met `playwright install`).

    PADEL_ANALYSIS_MULTI_WORKFLOW_TRIGGER_2026-09-17:
    - workflow_file: optioneel, overschrijft welk workflow-bestand
      getriggerd wordt (standaard: uit st.secrets['github']['workflow'] of
      DEFAULT_WORKFLOW_FILE = "scrape-padel.yml", ONGEWIJZIGD gedrag).
    - inputs: optioneel, een dict die RECHTSTREEKS als workflow_dispatch-
      'inputs'-payload gebruikt wordt (bv. {"player": "111,222", "max": "5"}
      voor refresh-klassement.yml/refresh-padelstat.yml, die een ANDER
      input-schema hebben dan scrape-padel.yml). Wordt dit NIET meegegeven,
      dan wordt (net als voorheen) {"player_ids": ..., "mode": ...} gebruikt
      — volledig achterwaarts compatibel.

    Returns (success, message).
    """
    import requests
    token, repo, default_workflow, ref = _get_github_settings()
    workflow = workflow_file or default_workflow
    if not token:
        return False, "Geen GitHub-token geconfigureerd."
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
    except Exception as e:
        return False, f"Kon GitHub niet bereiken: {e}"
    if resp.status_code == 204:
        run_url = f"https://github.com/{repo}/actions/workflows/{workflow}"
        return True, f"✅ Data wordt ververst. Volg de voortgang op [GitHub Actions]({run_url}) (duurt meestal enkele minuten)."
    if resp.status_code == 401:
        return False, "Mislukt: het GitHub-token is ongeldig of verlopen."
    if resp.status_code == 403:
        return False, "Mislukt: het GitHub-token heeft onvoldoende rechten."
    if resp.status_code == 404:
        return False, f"Mislukt: workflow '{workflow}' of repo '{repo}' niet gevonden. Staat het bestand in .github/workflows/ en is het al gepusht naar '{ref}'?"
    return False, f"Mislukt ({resp.status_code})."


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
    (start op de achtergrond de bestaande GitHub Actions-workflow). Als het
    GitHub-token nog niet geconfigureerd is, wordt er niets getoond — geen
    technische uitleg meer in de hoofd-UI.

    player_ids: leeg = alle spelers; of komma-gescheiden lijst voor specifieke
                speler(s) (bv. enkel de huidige speler verversen).
    mode:       "missing" (enkel ontbrekende periodes, standaard en snelst),
                "new_users", of "full".

    PADEL_ANALYSIS_MULTI_WORKFLOW_TRIGGER_2026-09-17:
    - workflow_file / inputs: zie trigger_github_actions_scrape(). Laat beide
      weg voor het ONGEWIJZIGDE, oorspronkelijke gedrag (scrape-padel.yml
      met player_ids/mode). Geef ze mee om een ANDERE workflow met een eigen
      input-schema te triggeren (bv. refresh-klassement.yml).
    - help_text: optionele tooltip op de knop (st.button(help=...)).
    """
    import streamlit as st
    if not is_github_trigger_configured():
        return
    if st.button(label, key=f"{key_prefix}_gh_trigger", type="primary", help=help_text):
        with st.spinner("Bezig met starten..."):
            ok, msg = trigger_github_actions_scrape(
                player_ids=player_ids, mode=mode, workflow_file=workflow_file, inputs=inputs,
            )
        if ok:
            st.success(msg)
        else:
            st.error(msg)
