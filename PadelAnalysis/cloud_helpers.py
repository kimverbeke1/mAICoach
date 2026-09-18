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

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18 (op verzoek van Kim,
na het testen van de knop hierboven: "duurt eerst lang tegen dat je daar
kan op klikken. na het klikken lijkt er iets te gebeuren maar je heb niet
echt goeie feedback [...] lijkt eigenlijk niet gelukt. ik zie ook niets
verschijnen bij actions")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door het echte .github/workflows/refresh-padelstat.yml
in te zien - het input-schema {"player","max","force_all"} bleek WEL
correct, dat was dus niet de oorzaak): het meest waarschijnlijke probleem
is dat een workflow_dispatch-aanroep via de API STILZWIJGEND een 404
teruggeeft (geen run, niets zichtbaar in Actions) als het aangeroepen
workflow-bestand nog niet op de 'main'-branch van GitHub zelf staat (een
bekende GitHub-eigenaardigheid: workflow_dispatch via de REST API werkt
ENKEL voor workflow-bestanden die GitHub al kent op de default branch -
lokaal/in OneDrive bestaan is niet voldoende, het moet ook echt gepusht
EN gemerged zijn). Kim's eigen bestanden waren op het moment van testen
mogelijk nog niet gepusht.

Twee bijkomende, structurele problemen die de "geen goede feedback"-klacht
zelfstandig verklaren, los van de 404-hypothese:
  1. st.success()/st.error() in Streamlit tonen enkel EENMALIG, binnen de
     render-cyclus van de klik zelf. Gebeurt er nadien, om eender welke
     reden, nog een st.rerun() (bv. door een andere widget-interactie
     elders op de pagina), dan verdwijnt de melding volledig - de
     gebruiker ziet dan "leek iets te gebeuren" gevolgd door niets.
  2. Er was geen enkele manier om, VOOR het effectief triggeren, te
     verifiëren of GitHub de workflow uberhaupt herkent - een fout kwam
     pas AAN HET LICHT na de mislukte poging zelf, zonder onderscheid
     tussen "workflow onbekend" en "andere fout".

FIX:
  - check_workflow_registered(workflow_file): NIEUWE functie, doet een
    read-only GET-aanroep naar de GitHub API (GEEN dispatch) om
    DEFINITIEF te bevestigen of een workflow-bestand herkend wordt op de
    default branch, VOOR er ooit een trigger-poging gebeurt. Dit
    onderscheidt meteen "workflow bestaat niet/nog niet gepusht" van
    "workflow bestaat wel, dispatch faalde om een andere reden".
  - trigger_github_actions_scrape(): geeft nu ALTIJD de verstreken tijd en
    (bij een fout) de ruwe HTTP-statuscode/foutdetail mee in het bericht,
    en onderscheidt expliciet een netwerktime-out van een verbindingsfout
    (i.p.v. beide als generieke "kon GitHub niet bereiken" te melden).
  - render_full_player_scrape_button(): het LAATSTE resultaat (per speler)
    wordt nu bewaard in st.session_state en bij ELKE render van de pagina
    opnieuw getoond (met tijdstip) - een pagina-rerun kan de feedback dus
    niet langer laten verdwijnen. Toont bovendien EERST het resultaat van
    check_workflow_registered() voor beide workflows, zodat Kim in 1 oogopslag
    ziet of het probleem 'workflow onbekend bij GitHub' is, nog vóór de
    eigenlijke trigger-poging.

--------------------------------------------------------------------------
PADEL_ANALYSIS_GENERIC_TRIGGER_FEEDBACK_PERSIST_2026-09-18 (op verzoek van
Kim: "er verschijnt een knop maar werkt niet" bij bv. een nog niet
gescrapete partner/tegenstander, en "bij Speler toevoegen staat geen knop
in de cloud versie")
--------------------------------------------------------------------------
BUG (opgelost, kritiek): de PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC-fix
hierboven (persistente feedback in st.session_state) werd ENKEL toegepast
in render_full_player_scrape_button(). De generieke, veel vaker gebruikte
render_cloud_scrape_trigger() — de functie achter "🚀 Nieuwe tegenstanders
ophalen", "📈 Klassement nu ophalen voor deze ploeg", "🎯 Playing strength
nu ophalen voor deze ploeg", "🔄 Alle spelers verversen" (Speler
toevoegen-pagina) en elke andere "Data verversen"-knop in de app — bleef
het OUDE gedrag hebben: st.success()/st.error() werd enkel getoond binnen
diezelfde render-cyclus, en verdween zodra er nadien nog een st.rerun()
gebeurde (bv. door een checkbox of ander widget elders op de pagina). Dat
verklaart exact "er verschijnt een knop maar werkt niet": de trigger liep
wel degelijk (of faalde met een duidelijke reden), maar de melding was
alweer weg tegen dat Kim keek.

Fix: render_cloud_scrape_trigger() bewaart het resultaat nu ook in
st.session_state (sleutel afgeleid van key_prefix) en toont het bij ELKE
render opnieuw, exact hetzelfde patroon als render_full_player_scrape_
button(). Dit lost het probleem op voor ALLE bestaande aanroepers zonder
dat die zelf iets hoeven aan te passen.

Tweede, apart probleem ("bij Speler toevoegen staat geen knop"): dat was
GEEN bug maar het correcte, doch onduidelijke gedrag — als er nog geen
[github]-token in de Streamlit Cloud secrets staat, toont
render_cloud_scrape_trigger() bewust HELEMAAL NIETS (geen knop, geen
uitleg). page_add_player.py toont daardoor op cloud geen enkele knop
zolang dat token ontbreekt, zonder dat duidelijk is WAAROM. Zie
page_add_player.py voor de expliciete uitleg die nu getoond wordt in dat
geval (los van deze module, die zelf bewust "stil" blijft zodat andere,
subtielere aanroepplekken geen ongewenste tekst tonen).
"""

import os
import sys
import time

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


def check_workflow_registered(workflow_file: str) -> tuple[bool, str]:
    """
    PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18: read-only
    pre-flight check (GEEN workflow_dispatch, GEEN nieuwe run) die
    rechtstreeks bij GitHub bevestigt of dit workflow-bestand ECHT
    herkend wordt op de default branch van de repo.

    Dit is de directe test voor de meest waarschijnlijke oorzaak van
    "niets verschijnt in Actions": workflow_dispatch via de REST API
    werkt ENKEL voor workflow-bestanden die GitHub al kent op de default
    branch (lokaal/in OneDrive bestaan is niet voldoende - het moet ook
    echt gepusht EN gemerged zijn naar bv. 'main').

    Returns (gevonden, detail):
      - (True, "actief")           -> workflow bestaat en kan getriggerd worden.
      - (True, "state=<state>")    -> workflow bestaat, maar staat NIET op
                                       'active' (bv. handmatig uitgeschakeld
                                       via GitHub UI) - dispatch zal dan
                                       waarschijnlijk ALSNOG mislukken.
      - (False, "<foutdetail>")    -> workflow NIET gevonden op de default
                                       branch, of een andere fout (token/
                                       netwerk) - detail bevat de reden.
    """
    import requests
    token, repo, _default_workflow, _ref = _get_github_settings()
    if not token:
        return False, "geen GitHub-token geconfigureerd"
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        return False, f"kon GitHub niet bereiken ({type(e).__name__}: {e})"
    if resp.status_code == 200:
        try:
            state = resp.json().get("state", "onbekend")
        except Exception:
            state = "onbekend"
        if state == "active":
            return True, "actief"
        return True, f"state={state} (waarschijnlijk NIET triggerbaar zolang dit niet 'active' is)"
    if resp.status_code == 404:
        return False, (
            f"GitHub kent '{workflow_file}' niet op de standaardbranch van '{repo}'. "
            "Meest waarschijnlijke oorzaak: het bestand staat lokaal/in OneDrive, maar is nog "
            "NIET gepusht+gemerged naar GitHub. Controleer via GitHub.com -> Actions: staat "
            "deze workflow in de linkerlijst?"
        )
    if resp.status_code == 401:
        return False, "GitHub-token ongeldig of verlopen"
    if resp.status_code == 403:
        return False, "GitHub-token heeft onvoldoende rechten"
    return False, f"onverwachte statuscode {resp.status_code}"


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

    PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18: het bericht bevat
    nu ALTIJD de verstreken tijd (transparantie: was het traag, of net heel
    snel mislukt?), en onderscheidt een netwerktime-out expliciet van een
    verbindingsfout, i.p.v. beide als generieke "kon GitHub niet bereiken"
    te melden.
    """
    import requests
    start = time.monotonic()
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
    except requests.exceptions.Timeout:
        elapsed = time.monotonic() - start
        return False, f"Mislukt: GitHub antwoordde niet binnen 15s (time-out na {elapsed:.1f}s)."
    except requests.exceptions.ConnectionError as e:
        elapsed = time.monotonic() - start
        return False, f"Mislukt: kon geen verbinding maken met GitHub na {elapsed:.1f}s ({e})."
    except Exception as e:
        elapsed = time.monotonic() - start
        return False, f"Mislukt: onverwachte fout na {elapsed:.1f}s ({type(e).__name__}: {e})."
    elapsed = time.monotonic() - start
    if resp.status_code == 204:
        run_url = f"https://github.com/{repo}/actions/workflows/{workflow}"
        return True, f"✅ Getriggerd in {elapsed:.1f}s. Volg de voortgang op [GitHub Actions]({run_url}) (duurt meestal enkele minuten)."
    if resp.status_code == 401:
        return False, f"Mislukt ({elapsed:.1f}s): het GitHub-token is ongeldig of verlopen."
    if resp.status_code == 403:
        return False, f"Mislukt ({elapsed:.1f}s): het GitHub-token heeft onvoldoende rechten."
    if resp.status_code == 404:
        return False, (
            f"Mislukt ({elapsed:.1f}s, HTTP 404): workflow '{workflow}' niet gevonden op de "
            f"standaardbranch van '{repo}'. Meest waarschijnlijke oorzaak: het bestand is nog "
            "niet gepusht+gemerged naar GitHub."
        )
    if resp.status_code == 422:
        try:
            detail = resp.json().get("message", "")
        except Exception:
            detail = ""
        return False, (
            f"Mislukt ({elapsed:.1f}s, HTTP 422): GitHub verwierp de inputs voor '{workflow}'"
            + (f" — {detail}" if detail else "")
            + ". Controleer of het input-schema overeenkomt met wat hier verstuurd werd."
        )
    return False, f"Mislukt ({elapsed:.1f}s, HTTP {resp.status_code})."


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
    technische uitleg meer in de hoofd-UI (zie de aanroeper zelf, bv.
    page_add_player.py, voor een expliciete uitleg in dat geval).

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

    PADEL_ANALYSIS_GENERIC_TRIGGER_FEEDBACK_PERSIST_2026-09-18 (op verzoek
    van Kim: "er verschijnt een knop maar werkt niet"): het resultaat van de
    LAATSTE klik wordt nu bewaard in st.session_state (per key_prefix) en bij
    ELKE render van de pagina opnieuw getoond — exact hetzelfde patroon als
    render_full_player_scrape_button(). Voorheen toonde deze functie
    st.success()/st.error() enkel binnen de render-cyclus van de klik zelf;
    een latere st.rerun() (bv. door een ander widget elders op de pagina)
    liet die melding stilzwijgend verdwijnen, wat aanvoelde als "de knop
    doet niets" terwijl de trigger wel degelijk gelukt of mislukt was.
    """
    import streamlit as st
    if not is_github_trigger_configured():
        return
    result_key = f"{key_prefix}_cloud_trigger_last_result"
    if st.button(label, key=f"{key_prefix}_gh_trigger", type="primary", help=help_text):
        with st.spinner("Bezig met starten..."):
            ok, msg = trigger_github_actions_scrape(
                player_ids=player_ids, mode=mode, workflow_file=workflow_file, inputs=inputs,
            )
        st.session_state[result_key] = {
            "timestamp": time.strftime("%H:%M:%S"),
            "ok": ok,
            "msg": msg,
        }
    # PADEL_ANALYSIS_GENERIC_TRIGGER_FEEDBACK_PERSIST_2026-09-18: altijd
    # opnieuw tonen, ook buiten de if-branch van de klik zelf, zodat een
    # latere rerun de feedback niet meer kan laten verdwijnen.
    last = st.session_state.get(result_key)
    if last:
        st.caption(f"Resultaat van de laatste poging, om {last['timestamp']}:")
        if last["ok"]:
            st.success(last["msg"])
        else:
            st.error(last["msg"])


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
    render_player_summary_inline() voor de eerste, centrale integratie.

    PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18: het resultaat van
    de LAATSTE klik wordt bewaard in st.session_state en bij ELKE render
    van de pagina opnieuw getoond (met tijdstip) - een pagina-rerun kan de
    feedback dus niet langer laten verdwijnen ("leek iets te gebeuren maar
    geen goede feedback"). Vóór de eigenlijke trigger-poging wordt bovendien
    EERST, via check_workflow_registered(), rechtstreeks bij GitHub
    geverifieerd of beide workflows daar effectief herkend worden - dat
    geeft een DEFINITIEF antwoord op de vraag "waarom zie ik niets in
    Actions?" (workflow onbekend bij GitHub vs. een andere fout).
    """
    import streamlit as st
    if not is_github_trigger_configured():
        return
    result_key = f"{key_prefix}_last_result_{player_id}"
    label_naam = f" voor {player_name}" if player_name else ""
    if st.button(
        f"🔄 Scrape deze speler nu (TVL + padelstat){label_naam}",
        key=f"{key_prefix}_full_scrape_{player_id}",
        type="primary",
        help="Start 2 GitHub Actions-workflows op de achtergrond: TVL-matchdata "
             "(enkel ontbrekende/huidige periode) en padelstats.be playing strength. "
             "Duurt meestal enkele minuten.",
    ):
        with st.spinner("Stap 1/2: controleren of GitHub beide workflows herkent..."):
            tvl_workflow = _get_github_settings()[2] or DEFAULT_WORKFLOW_FILE
            tvl_registered, tvl_reg_detail = check_workflow_registered(tvl_workflow)
            padelstat_registered, padelstat_reg_detail = check_workflow_registered(PADELSTAT_WORKFLOW_FILE)
        with st.spinner("Stap 2/2: workflows starten op GitHub..."):
            if tvl_registered:
                ok_tvl, msg_tvl = trigger_github_actions_scrape(
                    player_ids=str(player_id), mode="missing", workflow_file=tvl_workflow,
                )
            else:
                ok_tvl, msg_tvl = False, f"Overgeslagen — workflow niet herkend: {tvl_reg_detail}"
            if padelstat_registered:
                ok_padelstat, msg_padelstat = trigger_github_actions_scrape(
                    workflow_file=PADELSTAT_WORKFLOW_FILE,
                    inputs={"player": str(player_id), "max": "1", "force_all": "false"},
                )
            else:
                ok_padelstat, msg_padelstat = False, f"Overgeslagen — workflow niet herkend: {padelstat_reg_detail}"
        st.session_state[result_key] = {
            "timestamp": time.strftime("%H:%M:%S"),
            "tvl": (ok_tvl, msg_tvl, tvl_registered, tvl_reg_detail),
            "padelstat": (ok_padelstat, msg_padelstat, padelstat_registered, padelstat_reg_detail),
        }
    # PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18: het laatst bekende
    # resultaat wordt ALTIJD opnieuw getoond (niet enkel binnen de if-branch
    # van de klik zelf), zodat een latere pagina-rerun de feedback niet kan
    # laten verdwijnen.
    last = st.session_state.get(result_key)
    if last:
        st.caption(f"Resultaat van de laatste poging, om {last['timestamp']}:")
        ok_tvl, msg_tvl, tvl_registered, tvl_reg_detail = last["tvl"]
        ok_padelstat, msg_padelstat, padelstat_registered, padelstat_reg_detail = last["padelstat"]
        st.markdown(f"**TVL-matchdata** (workflow-check: {'✅ herkend' if tvl_registered else '❌ NIET herkend — ' + tvl_reg_detail}):")
        if ok_tvl:
            st.success(msg_tvl)
        else:
            st.error(msg_tvl)
        st.markdown(f"**Padelstats.be playing strength** (workflow-check: {'✅ herkend' if padelstat_registered else '❌ NIET herkend — ' + padelstat_reg_detail}):")
        if ok_padelstat:
            st.success(msg_padelstat)
        else:
            st.error(msg_padelstat)
        if not tvl_registered or not padelstat_registered:
            st.warning(
                "⚠️ Minstens 1 workflow wordt niet herkend door GitHub. Controleer op GitHub.com "
                "-> Actions of de betrokken workflow(s) in de linkerlijst staan — staan ze er niet, "
                "dan is het bestand nog niet gepusht+gemerged naar de standaardbranch."
            )
