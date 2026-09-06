"""
cloud_helpers.py — Streamlit Community Cloud detectie voor PadelAnalysis.

Playwright/Selenium-scraping (spelers zoeken/toevoegen op TVL, profielen
verversen, klassementshistoriek laden, nieuwe tegenstanders scrapen)
vereist browser-binaries die niet beschikbaar zijn op Streamlit Community
Cloud. Deze module bepaalt of scraping mogelijk is, zodat de UI de
betrokken knoppen kan verbergen op cloud en gewoon tonen op een lokale
machine (waar je normaal `streamlit run streamlit_app.py` draait).

FIX 2026-09-06 — Cloud-scrape via GitHub Actions:
Sinds `.github/workflows/scrape-padel.yml` bestaat (een GitHub Actions
workflow die WEL Playwright kan draaien, op een ubuntu-latest runner),
kan de cloud-app die workflow op afstand triggeren via de GitHub REST
API (`workflow_dispatch`), zonder zelf een browser te starten. Dit
bestand voegt daarvoor `render_cloud_scrape_trigger()` toe: een kleine
UI-widget die (indien geconfigureerd) een knop toont om de workflow te
starten, en anders uitlegt hoe je dat kan configureren.

Vereiste Streamlit secret (naast de reeds bestaande FIREBASE_SERVICE_ACCOUNT_JSON
die de GitHub Actions workflow zelf gebruikt — dit is een ANDER secret,
specifiek voor de Streamlit Cloud-app om de GitHub API aan te spreken):

    [github]
    token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    repo  = "kimverbeke1/mAICoach"

Het token is een GitHub Personal Access Token met minstens 'Actions: Read
and write' rechten op deze repo (fine-grained token) of de klassieke
'repo' + 'workflow' scopes (classic token). Zonder dit secret toont de UI
gewoon uitleg i.p.v. een knop — er crasht niets.
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

    Detectie, in volgorde:
    1. Expliciete override via st.secrets["SCRAPING_AVAILABLE"] (bool) —
       handig om dit tijdelijk te forceren, ongeacht platform.
    2. Herkenning van het typische Streamlit Community Cloud-pad
       (/mount/src/... , gebruiker adminuser), zoals te zien in de
       tracebacks van deze app.
    3. Fallback: als het 'playwright' package niet importeerbaar is,
       is scraping sowieso niet mogelijk.
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


def scraping_unavailable_notice(feature: str = "Deze functie") -> None:
    """Toont een consistente uitleg wanneer scraping niet beschikbaar is (cloud)."""
    import streamlit as st
    st.info(
        f"🚫 {feature} vereist een browser (Playwright) en is niet beschikbaar in deze "
        f"cloud-omgeving. Voer dit lokaal uit (`streamlit run streamlit_app.py`) — nieuwe "
        f"of ververste data komt via Firestore automatisch ook hier terecht."
    )


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


def trigger_github_actions_scrape() -> tuple[bool, str]:
    """
    Start de bestaande GitHub Actions-workflow (scrape-padel.yml) op afstand
    via een `workflow_dispatch`-call naar de GitHub REST API. Dit draait GEEN
    Playwright binnen Streamlit zelf — het triggert enkel de externe workflow
    die dat wél kan (ubuntu-latest runner met `playwright install`).

    Returns (success, message).
    """
    import requests

    token, repo, workflow, ref = _get_github_settings()
    if not token:
        return False, (
            "Geen GitHub-token geconfigureerd. Voeg in Streamlit Cloud → Settings → "
            "Secrets een blok toe:\n\n"
            "[github]\ntoken = \"ghp_...\"\nrepo = \"" + DEFAULT_GITHUB_REPO + "\""
        )
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = requests.post(url, headers=headers, json={"ref": ref}, timeout=15)
    except Exception as e:
        return False, f"Kon de GitHub API niet bereiken: {e}"
    if resp.status_code == 204:
        run_url = f"https://github.com/{repo}/actions/workflows/{workflow}"
        return True, (
            f"✅ Workflow gestart. Volg de voortgang op [de Actions-tab]({run_url}) "
            f"— duurt meestal enkele minuten. Ververste data verschijnt via Firestore "
            f"automatisch in deze app (druk nadien even op 'Vernieuwen' in je browser)."
        )
    if resp.status_code == 401:
        return False, "Mislukt (401): het GitHub-token is ongeldig of verlopen."
    if resp.status_code == 403:
        return False, (
            "Mislukt (403): het GitHub-token heeft onvoldoende rechten. "
            "Vereist: 'Actions: Read and write' (fine-grained) of scope 'workflow' (classic)."
        )
    if resp.status_code == 404:
        return False, (
            f"Mislukt (404): workflow '{workflow}' of repo '{repo}' niet gevonden "
            f"(of het token heeft geen toegang tot deze repo)."
        )
    return False, f"Mislukt ({resp.status_code}): {resp.text[:300]}"


def render_cloud_scrape_trigger(key_prefix: str = "") -> None:
    """
    Toont, enkel relevant op cloud, een knop om de GitHub Actions scrape-
    workflow manueel te starten vanuit de app zelf. Als het GitHub-token nog
    niet geconfigureerd is, toont dit enkel duidelijke configuratie-uitleg
    (geen crash).

    Let op: de workflow ververst ALLE gekende spelers (niet enkel de speler
    die je op dat moment bekijkt), want scrape-padel.yml/ci_scrape_all.py is
    zo opgezet als periodieke onderhoudstaak, niet als per-speler actie.
    """
    import streamlit as st

    if not is_github_trigger_configured():
        st.caption(
            "ℹ️ Wil je scraping vanuit de cloud-app kunnen starten (via de bestaande "
            "GitHub Actions-workflow)? Voeg in **Streamlit Cloud → Settings → Secrets** "
            "een GitHub Personal Access Token toe:\n\n"
            "```\n[github]\ntoken = \"ghp_...\"\nrepo = \"" + DEFAULT_GITHUB_REPO + "\"\n```\n\n"
            "Token-rechten: 'Actions: Read and write' (fine-grained token, enkel voor deze repo)."
        )
        return

    st.caption(
        "▶️ Dit start de bestaande GitHub Actions-workflow (`scrape-padel.yml`) op een "
        "omgeving met Playwright. Ververst **alle gekende spelers**, duurt enkele minuten. "
        "Ververste data komt via Firestore automatisch in deze app terecht."
    )
    if st.button("▶️ Scrape starten via GitHub Actions (cloud)", key=f"{key_prefix}_gh_trigger"):
        with st.spinner("Workflow starten..."):
            ok, msg = trigger_github_actions_scrape()
        if ok:
            st.success(msg)
        else:
            st.error(msg)
