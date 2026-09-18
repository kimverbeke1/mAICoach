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

--------------------------------------------------------------------------
PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18 (op verzoek van Kim: "bij
elke speler die je ziet daar rechtstreeks gewoon te kunnen een scrape
starten. die scrape moet dan padelstat en TVL scrapen. Wel enkel TVL
scraping voor missing/laatste periode zoals vroeger al aangehaald")
--------------------------------------------------------------------------
Nieuwe functie: render_full_player_scrape_button(). Combineert, met ÉÉN
klik, TWEE afzonderlijke GitHub Actions-triggers voor exact 1 speler:
  1. scrape-padel.yml, mode="missing" — TVL-matchdata, enkel de ontbrekende
     periode(s)/de huidige actieve periode (scrape_player.py met
     strict_missing_only=True + refresh_recent=0 — zie scraper/
     scrape_player.py voor de volledige logica van wat "missing" precies
     betekent: de huidige periode via echte datumvergelijking, plus elke
     periode die nog nooit gescraped werd). Dit is HETZELFDE gedrag als de
     al bestaande "🔄 Schema nu verversen"/"Playing strength nu
     ophalen"-knoppen gebruiken voor mode="missing", nu ook hier
     hergebruikt — geen nieuwe TVL-scrapelogica, enkel een nieuwe
     aanroepplek.
  2. refresh-padelstat.yml, met inputs={"player": <id>, "max": "1",
     "force_all": "false"} — ververst de padelstats.be playing strength
     voor EXACT deze ene speler.

BELANGRIJKE AANNAME (graag door Kim te verifiëren tegen het echte
.github/workflows/refresh-padelstat.yml-bestand, dat ik niet zelf kon
inzien): het input-schema {"player": ..., "max": ..., "force_all": ...}
is overgenomen uit de module-docstring hierboven (PADEL_ANALYSIS_MULTI_
WORKFLOW_TRIGGER_2026-09-17). Klopt de exacte input-NAAM ("player" i.p.v.
bv. "player_id" of "player_ids") niet, dan zal GitHub de workflow_dispatch-
aanroep ofwel negeren ofwel met een 422-fout weigeren — in dat laatste
geval toont trigger_github_actions_scrape() de ruwe HTTP-statuscode terug,
wat een duidelijk signaal is om het input-schema te corrigeren.

Beide triggers gebeuren ONAFHANKELIJK van elkaar (2 aparte API-calls) —
als de ene mislukt (bv. workflow-bestand nog niet gepusht) blijft de
andere gewoon doorgaan; beide resultaten worden apart teruggemeld.
"""
import os
import sys

_CLOUD_PATH_MARKERS = ("/mount/src/", "/home/adminuser/")

DEFAULT_GITHUB_REPO = "kimverbeke1/mAICoach"
DEFAULT_WORKFLOW_FILE = "scrape-padel.yml"
DEFAULT_WORKFLOW_REF = "main"

# PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18: naam van de padelstat-
# workflow, zoals vermeld in de bestaande module-docstring hierboven. Pas
# dit aan als het echte bestand in .github/workflows/ een andere naam heeft.
PADELSTAT_WORKFLOW_FILE = "refresh-padelstat.yml"


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
    if resp.status_code == 422:
        return False, f"Mislukt (422): GitHub verwierp de inputs — controleer of het input-schema van '{workflow}' overeenkomt met wat hier verstuurd werd."
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


def render_full_player_scrape_button(
    player_id: str,
    player_name: str = "",
    key_prefix: str = "full_scrape",
) -> None:
    """
    PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18 (op verzoek van Kim):
    "bij elke speler die je ziet daar rechtstreeks gewoon te kunnen een
    scrape starten. die scrape moet dan padelstat en TVL scrapen. Wel enkel
    TVL scraping voor missing/laatste periode zoals vroeger al aangehaald."

    Toont, enkel relevant op cloud (net als render_cloud_scrape_trigger) en
    enkel als het GitHub-token geconfigureerd is, ÉÉN knop die met 1 klik
    BEIDE triggers uitvoert voor exact deze ene speler:
      1. scrape-padel.yml (mode="missing") - TVL-matchdata, enkel de
         ontbrekende/huidige periode (zie scraper/scrape_player.py:
         strict_missing_only + refresh_recent=0-logica).
      2. refresh-padelstat.yml - playing strength via padelstats.be.

    Beide triggers gebeuren als 2 onafhankelijke API-calls; als er 1 faalt
    (bv. het workflow-bestand staat nog niet in de repo) wordt dat apart
    gemeld, zonder de andere trigger te blokkeren.

    Bedoeld om herbruikbaar te zijn op ELKE plek waar een individuele
    speler getoond wordt (Team-analyse detail-per-speler, Opstelling-
    analyse, Spelers-pagina, Mijn profiel, ...) - zie opponent_dossier.py:
    render_player_summary_inline() voor de eerste, centrale integratie."""
    import streamlit as st
    if not is_github_trigger_configured():
        return
    label_naam = f" voor {player_name}" if player_name else ""
    if st.button(
        f"🔄 Scrape deze speler nu (TVL + padelstat){label_naam}",
        key=f"{key_prefix}_full_scrape_{player_id}",
        type="primary",
        help="Start 2 GitHub Actions-workflows op de achtergrond: TVL-matchdata "
             "(enkel ontbrekende/huidige periode) en padelstats.be playing strength. "
             "Duurt meestal enkele minuten.",
    ):
        with st.spinner("Bezig met starten..."):
            ok_tvl, msg_tvl = trigger_github_actions_scrape(
                player_ids=str(player_id), mode="missing",
            )
            ok_padelstat, msg_padelstat = trigger_github_actions_scrape(
                workflow_file=PADELSTAT_WORKFLOW_FILE,
                inputs={"player": str(player_id), "max": "1", "force_all": "false"},
            )
        st.markdown("**TVL-matchdata (missing/huidige periode):**")
        if ok_tvl:
            st.success(msg_tvl)
        else:
            st.error(msg_tvl)
        st.markdown("**Padelstats.be playing strength:**")
        if ok_padelstat:
            st.success(msg_padelstat)
        else:
            st.error(msg_padelstat)
            st.caption(
                "⚠️ Als dit blijft mislukken: controleer of '.github/workflows/"
                f"{PADELSTAT_WORKFLOW_FILE}' bestaat in de repo en of het input-schema "
                "overeenkomt met {\"player\": ..., \"max\": ..., \"force_all\": ...}."
            )
