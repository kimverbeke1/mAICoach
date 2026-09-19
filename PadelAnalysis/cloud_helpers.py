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
PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18 (op verzoek van Kim: "ik heb
terug teveel reads op firebase" (aparte fix, zie firebase_service.py) EN
"Nieuwe spelers zoeken/toevoegen vereist een browser (Playwright) en werkt
daarom structureel enkel lokaal [...] dat blijft zo, ongeacht configuratie.
Problemen bij proberen scrapen bij partner ook nog zelfde" — "bouw maar.
Padelstat en klassement moeten dan ook gescrapt worden.")
--------------------------------------------------------------------------
ROOT CAUSE: het zoeken van een NIEUWE (nog onbekende) speler op naam
(player_search.search_players(), Playwright) gebeurde tot nu toe ALLEEN
lokaal — page_add_player.py toonde op cloud onvoorwaardelijk "kan enkel
lokaal", ZONDER ooit de bestaande GitHub-trigger te overwegen. De knop
"🔍 Opzoeken & toevoegen via GitHub Actions" in player_inline_actions.py
bestond wel, maar triggerde in werkelijkheid gewoon scrape-padel.yml met
mode="new_users" (player_ids/mode-schema) — een workflow die ENKEL
player_id's kan verversen, nooit op naam kan zoeken. Die knop deed dus
NIET wat de tekst beloofde, met of zonder GitHub-token.

FIX (structureel, vergt een NIEUWE workflow — zie
.github/workflows/search-player.yml en scraper/search_new_player_ci.py):
  - Nieuwe workflow search-player.yml neemt first_name/last_name/club als
    workflow_dispatch-inputs, draait player_search.search_players() op een
    ubuntu-runner (Playwright, net als scrape-padel.yml), en cachet het
    resultaat in Firestore via firebase_service.save_player_search_cache()
    — DEZELFDE cache die de lokale zoekflow ook al vulde/las, dus dit werkt
    ongeacht waar de zoekopdracht is uitgevoerd (geen nieuwe collectie
    nodig).
  - trigger_player_search(): dunne wrapper rond
    trigger_github_actions_scrape() die deze nieuwe workflow aanroept.
  - render_cloud_player_search(): NIEUWE, herbruikbare UI-component
    (gebruikt door zowel page_add_player.py als player_inline_actions.py)
    die de workflow triggert, en vervolgens — via een simpele "Resultaat
    ophalen"-knop (polling, want een workflow_dispatch-run duurt meestal
    1-3 minuten) — fb.get_player_search_cache() uitleest en de gevonden
    kandidaten toont, net als de bestaande lokale flow. Bij "➕ Toevoegen"
    wordt het profiel aangemaakt EN wordt onmiddellijk
    render_full_player_scrape_button() getoond, zodat de nieuwe speler
    meteen TVL + padelstat + klassement kan laten scrapen (zie hieronder).
  - render_full_player_scrape_button() triggert nu DRIE workflows i.p.v.
    twee: naast TVL-matchdata (scrape-padel.yml) en padelstats.be playing
    strength (refresh-padelstat.yml) ook de TVL-klassementshistoriek
    (refresh-klassement.yml, met dezelfde {"player": ..., "max": "1",
    "force_all": "false"}-inputs als refresh-padelstat.yml — zie het echte
    .github/workflows/refresh-klassement.yml voor bevestiging van dit
    schema). Dit geldt dus ook voor ALLE bestaande aanroepplekken van deze
    knop (opponent_dossier.py: render_player_summary_inline(), gebruikt in
    Team-analyse, Opstelling-analyse, Spelers-pagina en Mijn profiel) —
    geen extra werk nodig om klassement daar ook toe te voegen.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SINGLE_PLAYER_KLASSEMENT_LATEST_ONLY_2026-09-19 (op verzoek
van Kim, EERSTE aanpassing - inmiddels TERUGGEDRAAID, zie de latere
PADEL_ANALYSIS_KLASSEMENT_BIANNUAL_SCHEDULE_2026-09-19 hieronder)
--------------------------------------------------------------------------
Kim's toenmalig verzoek: "goeie aanpassing om nu maar 1 speler te scrapen.
maar het officieel klassement is nog niet aangepast... Ik zou ook voor 1
speler de refresh padelstat en refresh klassement moeten runnen. refresh
klassement dan eigenlijk enkel de laatste waarde en niet de hele
geschiedenis." Dit werd toen opgelost door "max_periods": "1" mee te geven
aan de klassement-trigger in render_full_player_scrape_button().

--------------------------------------------------------------------------
PADEL_ANALYSIS_KLASSEMENT_BIANNUAL_SCHEDULE_2026-09-19 (op verzoek van Kim,
NIEUW inzicht dat de aanpak hierboven weer VERVANGT voor klassement)
--------------------------------------------------------------------------
Kim's vervolgmelding: "het officiële padelklassement [...] verandert
[...] 2 keer per jaar (zomer-/winterklassement, telkens rond de maandag
van ISO-week 27 resp. 49) [...] Bij een refresh van een speler moet je dus
het officiële klassement niet opnieuw scrapen voor die speler want dat
verandert maar 2 keer per jaar en dat gaan we oplossen met scheduled
scrape voor alle spelers in mijn database die al profieldata hebben."

FIX (vervangt de max_periods=1-aanpak hierboven): render_full_player_
scrape_button() triggert NU NOG MAAR TWEE workflows (TVL-matchdata +
padelstat) - de klassement-trigger is HIER VOLLEDIG WEGGEHAALD. Een nieuw,
apart script (scraper/refresh_klassement_biannual.py) + eigen workflow
(.github/workflows/refresh-klassement-biannual.yml) ververst voortaan het
officiële klassement van ALLE spelers met bestaande profieldata, maar
UITSLUITEND rond de 2 jaarlijkse momenten waarop TVL het zelf herberekent
- zie die bestanden voor de volledige (geverifieerde) datumwiskunde.
"De ganse historiek ophalen mag blijven zoals het is als je een speler
scrapt" (Kim's eigen woorden) blijft ONGEWIJZIGD gelden voor NIEUWE
spelers (via de bestaande enrich/discovery-flow en refresh_klassement_
only.py) - enkel de per-losse-speler-REFRESH-actie hier raakt klassement
voortaan nooit meer aan.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19 (op verzoek van
Kim: "Padelstat cijfers zouden wel scheduled moeten updaten. Ik wil dat wel
1 keer per week op maandag maar ook als je op analyse ploeg drukt om zeker
de laatste waarde te hebben wanneer je dat doet.")
--------------------------------------------------------------------------
Twee aparte, elkaar aanvullende mechanismen (dit bestand blijft
verantwoordelijk voor het TRIGGER-mechanisme zelf, niet voor WANNEER het
gebeurt):
  1. .github/workflows/refresh-padelstat.yml se cron is aangepast van
     DAGELIJKS naar WEKELIJKS (enkel maandag) - zie dat bestand.
  2. opponent_scout_ui.py (_run_scout_and_scrape(), de "🔍 Tegenstander
     analyseren"-knop) en opponent_analysis.py (render_team_header(), de
     "🔄 Verversen"-knop) roepen nu BEIDE, telkens geklikt, automatisch een
     GEFORCEERDE padelstat-verversing aan voor de betrokken tegenstander-
     roster (via trigger_github_actions_scrape() hier, met
     force_all="true") - lokaal gebeurt dit synchroon (_ensure_padelstat
     met force=True), op Cloud als een asynchrone GitHub Actions-trigger
     (dus met de gebruikelijke 1-3 minuten vertraging van workflow_
     dispatch, niet instant - dat is een technische grens van GitHub
     Actions zelf, geen keuze).

ROOT CAUSE #2 uit de vorige versie ("Dit profiel verversen heeft enkel de
scrape padel data gerund" — padelstat/klassement liepen blijkbaar NIET
mee): dit kan NIET bevestigd worden puur vanuit dit bestand, want
render_full_player_scrape_button() zelf triggerde toen wel degelijk alle
workflows. Twee mogelijke, niet onderling uitsluitende verklaringen:
  a) check_workflow_registered() gaf op het moment van die klik (False,
     "...") terug voor 1 of beide workflows (bv. nog niet als 'active'
     herkend door GitHub op dat moment) — dit wordt AL zichtbaar gemaakt
     in de bestaande UI-tekst ("workflow-check: ❌ NIET herkend — ...").
     Kim: controleer de melding die onder de knop verscheen na die klik.
  b) De concrete "Profiel verversen"-actie die toen gebruikt werd, was een
     ANDERE knop dan render_full_player_scrape_button() (bv. een aparte,
     eenvoudigere trigger elders in de app die enkel scrape-padel.yml
     aanroept). Ik heb geen zicht op elke plek in de app waar een
     "profiel verversen"-actie voorkomt — als dit een ANDERE knop was,
     deel dan gerust het bestand (bv. opponent_dossier.py of de
     Spelers-pagina) waar die vandaan komt, dan bekijk ik die gericht.
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
# PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18: naam van de
# klassement-workflow (bevestigd tegen het echte .github/workflows/
# refresh-klassement.yml-bestand) en van de nieuwe speler-zoek-workflow
# (nieuw bestand, zie .github/workflows/search-player.yml).
KLASSEMENT_WORKFLOW_FILE = "refresh-klassement.yml"
PLAYER_SEARCH_WORKFLOW_FILE = "search-player.yml"
# PADEL_ANALYSIS_SINGLE_PLAYER_KLASSEMENT_LATEST_ONLY_2026-09-19: bij een
# gerichte 1-speler-refresh volstaat de meest recente periode (de huidige
# officiële klassementswaarde) - de volledige historiek is voor dit
# doeleinde onnodig traag (elke periode = 1 aparte Playwright-selectie).
SINGLE_PLAYER_KLASSEMENT_MAX_PERIODS = "1"


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
    te meIden.
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

    LET OP (PADEL_ANALYSIS_SINGLE_PLAYER_KLASSEMENT_LATEST_ONLY_2026-09-19):
    deze GENERIEKE trigger triggert altijd maar ÉÉN workflow. Als "Profiel
    verversen" ergens in de app via DEZE functie loopt (i.p.v. via
    render_full_player_scrape_button() hieronder), dan verklaart dat exact
    Kim's observatie "Dit profiel verversen heeft enkel de scrape padel data
    gerund" — deze functie doet immers nooit automatisch ook padelstat/
    klassement. Gebruik in dat geval render_full_player_scrape_button()
    in plaats van (of aanvullend op) deze functie voor een "ververs deze
    speler volledig"-actie.
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

    PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18 (op verzoek van Kim:
    "Padelstat en klassement moeten dan ook gescrapt worden"): deze knop
    triggert nu DRIE onafhankelijke GitHub Actions-workflows i.p.v. twee:
      1. scrape-padel.yml (mode="missing") - TVL-matchdata, enkel de
         ontbrekende/huidige periode (zie scraper/scrape_player.py:
         strict_missing_only + refresh_recent=0-logica).
      2. refresh-padelstat.yml - playing strength via padelstats.be.
      3. refresh-klassement.yml - TVL-klassementshistoriek.

    PADEL_ANALYSIS_SINGLE_PLAYER_KLASSEMENT_LATEST_ONLY_2026-09-19 (op
    verzoek van Kim: "refresh klassement dan eigenlijk enkel de laatste
    waarde en niet de hele geschiedenis en dat dat dus ook alleen
    specifiek voor die speler"): de klassement-trigger geeft nu OOK
    "max_periods": SINGLE_PLAYER_KLASSEMENT_MAX_PERIODS (="1") mee. Zonder
    dit liet refresh-klassement.yml se eigen default (lege string = "alle
    periodes", zie refresh_klassement_only.py: DEFAULT_MAX_PERIODS_PER_
    PLAYER = None) een 1-speler-refresh ONNODIG de VOLLEDIGE historiek
    opnieuw ophalen (elke periode = 1 aparte, trage Playwright-selectie),
    terwijl voor een gerichte "ververs deze speler nu"-actie enkel de
    meest recente/actuele officiële klassementswaarde relevant is.
    Ter herinnering: --player/"player"-input in refresh_klassement_only.py
    forceert sowieso AL een verversing voor die ene speler, ONGEACHT
    versie-marker of cache (select_players_to_process() met only_player_id
    negeert needs_check() volledig) - dat deel werkte dus al correct; enkel
    de hoeveelheid periodes per keer was tot nu toe onnodig groot.

    Toont, enkel relevant op cloud (net als render_cloud_scrape_trigger) en
    enkel als het GitHub-token geconfigureerd is, ÉÉN knop die met 1 klik
    ALLE DRIE triggers uitvoert voor exact deze ene speler.

    Elke trigger gebeurt als aparte API-call; als er 1 faalt (bv. het
    workflow-bestand staat nog niet in de repo) wordt dat apart gemeld,
    zonder de andere triggers te blokkeren.

    Bedoeld om herbruikbaar te zijn op ELKE plek waar een individuele
    speler getoond wordt (Team-analyse detail-per-speler, Opstelling-
    analyse, Spelers-pagina, Mijn profiel, de nieuwe cloud-spelerzoek-flow
    in page_add_player.py/player_inline_actions.py, ...) - zie
    opponent_dossier.py: render_player_summary_inline() voor de eerste,
    centrale integratie.

    PADEL_ANALYSIS_SCRAPE_FEEDBACK_DIAGNOSTIC_2026-09-18: het resultaat van
    de LAATSTE klik wordt bewaard in st.session_state en bij ELKE render
    van de pagina opnieuw getoond (met tijdstip) - een pagina-rerun kan de
    feedback dus niet langer laten verdwijnen ("leek iets te gebeuren maar
    geen goede feedback"). Vóór de eigenlijke trigger-poging wordt bovendien
    EERST, via check_workflow_registered(), rechtstreeks bij GitHub
    geverifieerd of alle drie workflows daar effectief herkend worden - dat
    geeft een DEFINITIEF antwoord op de vraag "waarom zie ik niets in
    Actions?" (workflow onbekend bij GitHub vs. een andere fout).

    BELANGRIJK als "Dit profiel verversen" toch enkel matchdata blijkt te
    doen: dat betekent dat de knop die je gebruikte NIET deze functie is
    (deze functie triggert altijd alle drie). Controleer in dat geval welk
    ander bestand/knop je gebruikte (bv. een simpelere trigger via
    render_cloud_scrape_trigger(), of een lokale player_inline_actions.py-
    actie) — deel dat bestand zodat het gericht aangepast kan worden.
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
             "Duurt meestal enkele minuten. Het OFFICIËLE klassement wordt hier bewust "
             "NIET meegenomen (zie hieronder) - dat verandert maar 2x per jaar en wordt "
             "apart, geschikt getimed ververst voor de VOLLEDIGE spelerslijst.",
    ):
        with st.spinner("Stap 1/2: controleren of GitHub alle workflows herkent..."):
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
    st.caption(
        "ℹ️ Het OFFICIËLE TVL-klassement wordt hier NIET ververst — dat verandert maar 2x per "
        "jaar (zomer/winter) en wordt daarom apart, op de juiste momenten, voor de VOLLEDIGE "
        "spelerslijst ververst (zie refresh-klassement-biannual.yml)."
    )


def trigger_player_search(first_name: str, last_name: str, club: str = "") -> tuple[bool, str]:
    """
    PADEL_ANALYSIS_CLOUD_PLAYER_SEARCH_2026-09-18: dunne wrapper rond
    trigger_github_actions_scrape() die de NIEUWE search-player.yml-workflow
    aanroept (player_search.search_players() op een GitHub Actions-runner
    met Playwright), voor het zoeken van een NOG ONBEKENDE speler op naam.
    Dit is fundamenteel anders dan scrape-padel.yml/render_cloud_scrape_
    trigger(), die enkel bestaande player_id's kunnen verversen en dus nooit
    op naam konden zoeken."""
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
    page_add_player.py (die enkel werkt met Playwright, dus enkel lokaal).
    Triggert de nieuwe search-player.yml-workflow (Playwright op een GitHub
    Actions ubuntu-runner) en toont, zodra beschikbaar, de kandidaten uit
    firebase_service.get_player_search_cache() — DEZELFDE cache die de
    lokale flow ook al vult/leest (normalize_search_key(name_query, club,
    sport)), dus dit werkt ongeacht of de zoekopdracht lokaal of via deze
    workflow werd uitgevoerd.

    Een workflow_dispatch-run duurt meestal 1-3 minuten, dus dit is
    ONVERMIJDELIJK een polling-flow (i.p.v. de "vuur en vergeet"-triggers
    elders in dit bestand): na het triggeren toont deze functie een
    "🔄 Resultaat ophalen"-knop, die de cache opnieuw uitleest tot er een
    resultaat is.

    Bij "➕ Toevoegen" wordt het profiel aangemaakt (net als de lokale flow,
    inclusief added_by="manual" zodat cleanup_ghost_profiles.py deze speler
    nooit opruimt) EN wordt onmiddellijk render_full_player_scrape_button()
    getoond, zodat de nieuwe speler in 1 moeite door TVL + padelstat +
    klassement kan laten scrapen — op verzoek van Kim: "Padelstat en
    klassement moeten dan ook gescrapt worden."

    default_first/default_last/default_club: optionele voorinvulling van de
    zoekvelden (bv. vanuit player_inline_actions.py, waar al een gok naam
    bekend is uit een niet-gekoppelde partner/tegenstander-naam)."""
    import streamlit as st
    import firebase_service as fb
    if not is_github_trigger_configured():
        st.caption(
            "Nieuwe spelers zoeken vereist een browser en kan daarom niet "
            "rechtstreeks vanaf de cloud. Doe dit lokaal via '➕ Speler "
            "toevoegen', of configureer de GitHub Actions-trigger "
            "(st.secrets['github']) om het vanaf de cloud te kunnen starten."
        )
        return
    with st.form(f"{key_prefix}_form"):
        c1, c2, c3 = st.columns([2, 2, 2])
        first = c1.text_input("Voornaam", value=default_first, key=f"{key_prefix}_first")
        last = c2.text_input("Achternaam", value=default_last, key=f"{key_prefix}_last")
        club = c3.text_input("Club (optioneel)", value=default_club, key=f"{key_prefix}_club")
        submitted = st.form_submit_button(
            "🔍 Zoeken via GitHub Actions", use_container_width=True, type="primary",
        )
    trigger_key = f"{key_prefix}_triggered_at"
    query_key = f"{key_prefix}_query"
    candidates_key = f"{key_prefix}_candidates"
    if submitted:
        if not first.strip() and not last.strip():
            st.warning("Geef minstens een voornaam of achternaam in.")
        else:
            with st.spinner("Zoekopdracht starten op GitHub Actions..."):
                ok, msg = trigger_player_search(first.strip(), last.strip(), club.strip())
            if ok:
                st.session_state[trigger_key] = time.time()
                st.session_state[query_key] = {
                    "first": first.strip(), "last": last.strip(), "club": club.strip(),
                }
                st.session_state.pop(candidates_key, None)
                st.success(
                    f"{msg} Klik hieronder op '🔄 Resultaat ophalen' zodra de "
                    "workflow is afgerond (meestal 1-3 minuten, zie GitHub Actions)."
                )
            else:
                st.error(msg)
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
                "Nog geen resultaat gevonden. De workflow is mogelijk nog bezig — "
                "controleer desgewenst de voortgang op GitHub Actions en probeer het "
                "over een minuutje opnieuw."
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
            st.success(f"✅ {name} toegevoegd. Start hieronder de volledige scrape (TVL + padelstat + klassement):")
            render_full_player_scrape_button(
                str(pid), player_name=name, key_prefix=f"{key_prefix}_scrape_{i}",
            )
