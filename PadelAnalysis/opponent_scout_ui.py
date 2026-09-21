
"""
opponent_scout_ui.py - UI-blok voor de tegenstander-analyse bij 'Volgende match'.
Doel van dit bestand:
- 2026-09-09 (v1): de tussenstap verdwijnt. Na een klik op 'Tegenstander
  analyseren' wordt de opstelling van de tegenstander opgezocht EN worden de
  nog onbekende spelers meteen gescrapet, in een doorlopende
  voortgangsweergave (st.status).
- 2026-09-09 (v2): het volledige teamanalysescherm zit in
  opponent_analysis.render_team_analysis() (overzichtstabel, opstelling-editor,
  AI-sectie). Dit bestand geeft er spelgroep_id, home_player_id en een brede
  cache van alle gekende spelersdocumenten aan door.
PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14 (v3, op verzoek van Kim):
Kim wil de Opstelling-scenario's + AI-functies (dashboard.py) BOVENAAN de
pagina tonen, en pas DAARONDER de overzichtstabel/detail-per-speler van de
tegenploeg. Opgesplitst in render_scout_header() + prepare_team_docs().
render_scout_block() blijft bestaan als dunne wrapper voor eventuele andere/
toekomstige aanroepers.
Op Streamlit Community Cloud kan de app zelf niet scrapen (geen Playwright/
browser). Daar wordt een achtergrondtaak getriggerd in plaats van een lokale
scrape.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG/ONTBREKENDE STAP (opgelost): na het toevoegen van een tegenstander-ploeg
(bv. via een handmatig ingegeven poule-URL, zie manual_poule_input.py) bleven
verschillende speelsters onvolledig: geen padelstat playing strength, soms
NUL matchhistoriek, bij sommigen ook geen huidig klassement. "Verversen"
loste dit niet op. Drie samenvallende oorzaken:
  1. _run_scout_and_scrape() riep NERGENS de padelstats.be-scraper aan.
  2. scrape_new_opponent_players() (opponent_scout.py) scrapet UITSLUITEND
     spelers zonder bestaand profiel.
  3. lookback_periods stond hardcoded op 1 (enkel de huidige periode).
Fix: een nieuwe, expliciete "Ververs alles voor deze ploeg"-knop
(render_team_refresh_button) die voor ALLE spelers in de tegenstander-
roster matchdata/padelstat/klassement herhaalt, ongeacht een bestaand
profiel.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17 (op verzoek van Kim,
"we draaien in rondjes")
--------------------------------------------------------------------------
BUG (opgelost, kritiek): _run_full_team_refresh() riep voorheen aan:
    fb.save_player_profile(pid, display_name=naam)
Zoals uitgebreid toegelicht in de moduledocstring van opponent_scout.py:
firebase_service.save_player_profile() zet "club" altijd expliciet in de
payload (als None bij ontbreken), en merge=True beschermt enkel velden die
NIET in de payload staan — dus een reeds bekende club werd bij ELKE klik op
"🔄 Ververs alles voor deze ploeg" stilzwijgend overschreven naar leeg.
Bovendien kreeg een via deze weg aangemaakt/aangeraakt profiel nooit een
"added_by"-marker, waardoor cleanup_ghost_profiles.py deze spelers niet kon
onderscheiden van bewust, handmatig toegevoegde spelers.
Fix: _run_full_team_refresh() gebruikt nu dezelfde
osc._ensure_profile_safe()-helper als opponent_scout.py
(scrape_new_opponent_players()), zodat club behouden blijft en added_by
consistent gezet wordt — één bron van waarheid voor deze logica i.p.v. ze
hier te dupliceren.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLOUD_KLASSEMENT_PADELSTAT_TRIGGER_2026-09-17 (op verzoek van
Kim: "moet wel werken via github actions... bekijk dat eens van dichterbij")
--------------------------------------------------------------------------
BUG (opgelost, kritiek): op Streamlit Cloud (waar Kim uitsluitend test) was
er GEEN ENKELE manier om klassement of padelstat onmiddellijk te forceren
voor een specifieke tegenstander-ploeg. Fix: directe trigger-knoppen voor
klassement/padelstat, elk met de EXACTE tegenstander-roster als 'player'-
input, zodat je niet op de achtergrond-cron hoeft te wachten.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19 (op verzoek van
Kim: "Padelstat cijfers zouden wel scheduled moeten updaten. Ik wil dat wel
1 keer per week op maandag maar ook als je op analyse ploeg drukt om zeker
de laatste waarde te hebben wanneer je dat doet.")
--------------------------------------------------------------------------
FIX: _run_scout_and_scrape() roept nu, ONVOORWAARDELIJK en ALTIJD (niet
enkel voor nog-onbekende spelers), een GEFORCEERDE padelstat-verversing aan
voor de volledige tegenstander-roster, zodra die gekend is — zie
PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19 hieronder voor een
BELANGRIJKE correctie hierop.
--------------------------------------------------------------------------
PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19 (op verzoek van Kim,
zie chat 2026-09-19: "Bij mijn nieuwe tegenstander analyseren heb ik gezien
dat refresh padelstat direct start maar met 0 spelers: totaal in
player_profiles. 0 kandidaat/kandidaten voor controle [...] Anderzijds zie
ik wel: nieuwe tegenstanders ophalen [...] Het zou beter zijn mocht je bij
'tegenstander analyseren' meteen al die zaken doet als dat nog niet
gebeurd is. Als je dan bvb een 2de maal de tegenstander analyseert moet je
enkel nog de playing strength refreshen en bekijken of er eventueel
matchen bij gekomen zijn.")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door Kim, na analyse van de code): voor een
COMPLEET NIEUWE tegenstander-ploeg (nog geen enkele speler heeft een
player_profiles-document) doet _run_scout_and_scrape() op Cloud GEEN
matchdata-scrape (dat vereist Playwright, enkel via een achtergrondtaak
mogelijk — zie prepare_team_docs()' "🚀 Nieuwe tegenstanders ophalen"-knop,
die pas verschijnt/geklikt moet worden NA deze functie). Maar
_ensure_fresh_padelstat_for_roster() werd tot nu toe ALTIJD, ongeacht of
de spelers al een profiel hadden, uitgevoerd — en die triggert
refresh-padelstat.yml met exact die (nog niet bestaande) speler-ID's.
refresh_padelstat_only.py zoekt enkel binnen AL BESTAANDE player_profiles-
documenten (search_player_profiles()) -> 0 matches, exact het "0
kandidaten"-resultaat dat Kim zag. De taak liep dus niet fout, ze kreeg
gewoon een volledig lege doelgroep mee.
FIX, twee onderdelen:
  1. _ensure_fresh_padelstat_for_roster() ontvangt nu ENKEL de spelers die
     AL een player_profiles-document hebben (unique_players wordt vooraf
     gesplitst in "known" en "new" via _is_known()) — voor gloednieuwe
     spelers is een aparte padelstat-trigger toch zinloos, want de
     matchdata-scrape (getriggerd via "🚀 Nieuwe tegenstanders ophalen")
     roept ONDERWEG sowieso AL enrich_opponents.enrich() aan, wat
     padelstat AL meeneemt voor elke nieuw ontdekte speler (zie
     ci_scrape_all.py: run_enrichment()) — geen dubbel werk, geen "0
     kandidaten"-verwarring meer.
  2. Als er nieuwe spelers zijn, toont _run_scout_and_scrape() nu een
     duidelijke melding dat hun playing strength/klassement AUTOMATISCH
     meekomt zodra de matchdata-verversing (hieronder) is opgehaald - dit
     lost meteen ook Kim's 2de punt op ("bij tegenstander analyseren meteen
     al die zaken doen als dat nog niet gebeurd is"): de bestaande "🚀
     Nieuwe tegenstanders ophalen"-knop in prepare_team_docs() dekt dit al
     volledig (1 klik = matchdata + padelstat + profiel-aanmaak voor alle
     nieuwe spelers), dus GEEN nieuwe knop nodig — enkel de verwarrende,
     dubbele/lege padelstat-trigger is weggehaald.
  3. Bij een HERHAALDE analyse (spelers al gekend) blijft het gedrag
     ONGEWIJZIGD: enkel een geforceerde playing-strength-verversing +
     (indien aangevinkt) klassement voor eventueel nog onvolledige
     spelers - exact Kim's gewenste "2de keer enkel het verschil".
--------------------------------------------------------------------------
PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_2026-09-19 (op verzoek van Kim: "in het
algemeen ook niet vermelden als dat nu via github is of niet. dat is niet
relevant voor de gebruiker. ook de tekst dat deze omgeving zelf niet kan
scrapen etc... is niet relevant voor de gebruiker")
--------------------------------------------------------------------------
ALLE tekst die de gebruiker in de lopende app te zien krijgt (st.caption/
st.write/st.warning/st.info/label/help-tooltips/button-tekst) is herzien:
geen vermelding meer van "GitHub Actions", "workflow", "deze omgeving kan
niet scrapen", "vereist een browser", enz. Interne code-commentaren/
docstrings (zoals dit blok) blijven WEL technisch correct, want die zijn
voor ontwikkeling, niet voor de eindgebruiker. De onderliggende logica
(can_scrape/is_scraping_available() als intern onderscheid tussen "hier
synchroon uitvoeren" vs. "op de achtergrond triggeren") is ONGEWIJZIGD -
enkel de zichtbare bewoording is aangepast.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C, op verzoek van Kim,
chat 2026-09-19)
--------------------------------------------------------------------------
Kim's melding, samengevat: "Bij mijn nieuwe tegenstander analyseren heb ik
gezien dat refresh padelstat direct start maar met 0 spelers [...] Het zou
beter zijn mocht je bij 'tegenstander analyseren' meteen al die zaken doet
als dat nog niet gebeurd is. Als je dan bvb een 2de maal de tegenstander
analyseert moet je enkel nog de playing strength refreshen en bekijken of
er eventueel matchen bij gekomen zijn."
VOORHEEN moest Kim, op Cloud, voor een onvolledige/nieuwe tegenstander-
ploeg tot DRIE aparte knoppen gebruiken: "🚀 Nieuwe tegenstanders ophalen"
(prepare_team_docs), "📈 Klassement nu ophalen" en "🎯 Playing strength nu
ophalen" (beide in render_scout_header). Onduidelijk was ook WANNEER welke
knop nog nodig was.
FIX: _render_unified_team_sync_trigger() vervangt alle drie door ÉÉN
knop, die zichzelf bij elke render herlabelt op basis van wat er ECHT nog
ontbreekt (via de nieuwe, gestructureerde _data_completeness()-helper per
speler):
  - Eerste analyse van een gloednieuwe ploeg (niemand gekend): de knop
    toont "Ontbrekende gegevens ophalen (N van N spelers)" en haalt in 1
    klik matchdata + klassement + playing strength op voor de VOLLEDIGE
    roster.
  - Latere analyses waarbij de ploeg grotendeels al gekend is: de knop
    toont enkel het werkelijke aantal onvolledige spelers (bv. "1 van 4")
    - typisch een nieuw ingevallen speler - en richt klassement-ophalen
    ENKEL op hen. Wedstrijdgegevens ("missing"-modus) worden WEL altijd
    voor de VOLLEDIGE roster mee getriggerd (goedkoop dankzij de
    bestaande up-to-date-skip-logica in ci_scrape_all.py), zodat nieuwe
    wedstrijden (en dus mogelijk nieuwe/andere spelers) automatisch
    gedetecteerd worden zonder dat Kim daar apart naar moet vragen.
  - Is de ploeg volledig up-to-date, dan toont de knop enkel nog
    "Controleren op nieuwe wedstrijden" (playing strength wordt sowieso al
    automatisch geforceerd ververst bij elke "Tegenstander analyseren"-
    klik, zie _ensure_fresh_padelstat_for_roster()).
Elke deelstap toont een levende "stap X van Y"-voortgang (hergebruik van
cloud_helpers._render_tracked_progress(), zie PADEL_ANALYSIS_UI_NEUTRAL_
LANGUAGE_AND_REAL_PROGRESS_2026-09-19 in cloud_helpers.py).
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19 (op verzoek van Kim,
chat 2026-09-19, na het analyseren van een handmatige refresh_padelstat_
only.py-run: "je weet toch welke ploeg je scrapet dus deze melding is
eigenlijk niet nodig als je meteen de juiste club meegeeft")
--------------------------------------------------------------------------
ROOT CAUSE: op de plekken waar dit bestand padelstat laat verversen voor
een VOLLEDIGE, GEKENDE tegenstander-roster (_ensure_fresh_padelstat_for_
roster() → refresh-padelstat.yml, en _ensure_padelstat() lokaal), werd de
club-naam UITSLUITEND per speler uit diens eigen, mogelijk lege Firestore-
profiel gelezen — ook al is op DEZE plekken de ploegnaam (`opp["name"]`)
altijd al bekend (we zijn immers een specifieke tegenstander-ploeg aan het
verversen). Dat ontbrekende gegeven veroorzaakte precies de "geen club
opgegeven om te disambigueren"-waarschuwing die Kim signaleerde in
refresh_padelstat_only.py se log (zie de uitgebreide toelichting daar,
PADEL_ANALYSIS_CLUB_OVERRIDE_2026-09-19).
FIX: _ensure_padelstat(), _ensure_fresh_padelstat_for_roster(),
_run_full_team_refresh() en _render_unified_team_sync_trigger() accepteren
nu allemaal een optionele `team_name`-parameter:
  - Lokaal (_ensure_padelstat): gebruikt als FALLBACK-hint wanneer het
    profiel van een individuele speler zelf geen club heeft (een reeds
    bekende, mogelijk andere club per speler blijft leidend — net als de
    club_override-logica in refresh_padelstat_only.py).
  - Cloud (_ensure_fresh_padelstat_for_roster / _render_unified_team_sync_
    trigger): meegegeven als het nieuwe "club"-workflow_dispatch-input van
    refresh-padelstat.yml (zie dat bestand + refresh_padelstat_only.py se
    --club/CLUB-override), zodat de achtergrondtaak dezelfde disambiguatie-
    hint krijgt als de lokale weg.
Beide call sites die de ploegnaam al kennen (render_scout_header() en
poule_teams_ui.py) geven nu team_name=opp["name"] door — geen enkele
andere aanroepplek hoeft aangepast te worden, en het gedrag blijft
ONGEWIJZIGD wanneer team_name niet meegegeven wordt (bv. een oudere
aanroeper).
--------------------------------------------------------------------------
PADEL_ANALYSIS_FALSE_MISSING_ON_READ_ERROR_FIX_2026-09-19 (op verzoek van
Kim: "en ik heb zogezegd 3 spelers zonder klassementshistoriek maar die
zijn er wel. de melding lijkt op 1ste zicht verkeerd" — gemeld bij het
ophalen van de data van de volgende tegenploeg)
--------------------------------------------------------------------------
BUG (opgelost): _data_completeness() ving fb.get_player()/fb.get_player_
profile()-uitzonderingen (bv. een tijdelijke Firestore-leesfout of een
quota-overschrijding — zie dezelfde dag al "429 Quota exceeded" bij
refresh_klassement_only.py na de enrich_opponents-bug met 269 nieuwe
profielen) stil op en liet doc/profile dan gewoon leeg ({}) achter. Gevolg:
missing_klassement (en missing_matchdata/missing_padelstat) kwam op True
te staan ALSOF de data écht ontbrak, terwijl de Firestore-read simpelweg
mislukte — exact wat Kim zag bij 3 spelers die wél een klassementshistoriek
hebben.
FIX: elke onderliggende read houdt nu apart bij of ze GESLAAGD is
(doc_ok/profile_ok/padelstat_ok). "missing_*" wordt voortaan ENKEL True als
de betrokken read(s) daadwerkelijk slaagden EN het veld effectief afwezig
bleek. Bij een mislukte read wordt in plaats daarvan "*_uncertain" gezet —
_has_incomplete_data() toont dat voortaan als een expliciete, eerlijke
"kon niet gecontroleerd worden (probeer later opnieuw)"-melding, i.p.v.
het te verwarren met een bevestigd ontbrekend gegeven.
_render_unified_team_sync_trigger() telt "uncertain"-spelers voortaan MEE
bij het bepalen wie een klassement-verversing moet krijgen (een herhaalde
poging is onschadelijk — een speler die de data al wél heeft, wordt door
refresh_klassement_only.py toch snel overgeslagen) zodat een tijdelijke
leesfout niet stilzwijgend onopgelost blijft.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21 (op verzoek van Kim,
chat 2026-09-21: "ik heb nu de ploeg KTC ISIS eens willen analyseren bij de
andere ploegen en was dat ooit al eens begonnen. ik heb een knop om
ontbrekende gegevens van 3 van de 6 spelers op te halen maar eigenlijk
moeten alle spelers ondertussen opnieuw kunnen gefreshed worden (te
bekijken dan tijdens scrapen zelf hoe ver je moet gaan.)")
--------------------------------------------------------------------------
CONTEXT (ter verduidelijking van wat Kim zag): het label "N van M spelers"
komt van _render_unified_team_sync_trigger() en telt ENKEL spelers waarvoor
_data_completeness() een BEVESTIGD of ONZEKER ontbrekend gegeven detecteert.
Matchdata (stap 1) en playing strength (stap 3) worden DAARONDER, in de
uitvoering zelf, altijd al voor de VOLLEDIGE roster getriggerd (mode=
"missing" resp. force_all="true") — enkel STAP 2 (officieel klassement) was
tot nu toe bewust beperkt tot de gedetecteerde "onvolledige" spelers, om
onnodige herhaalscrapes te vermijden voor spelers die de data al hadden.
Voor een ploeg waarvan de situatie ondertussen zichtbaar veranderd is (bv.
KTC ISIS, die intussen effectief matchen speelde terwijl de analyse nog
"nog geen matchen gespeeld" toonde - zie PADEL_ANALYSIS_STALE_SCHEDULE_
POULE_TEAM_FIX_2026-09-21 in poule_teams_ui.py voor die aparte, samenhangende
fix), is dat onderscheid niet altijd wenselijk: Kim wil dan de MOGELIJKHEID
om ECHT alle 6 spelers opnieuw te laten controleren, ook al leken ze al
volledig.
FIX: _render_unified_team_sync_trigger() toont nu, ALLEEN wanneer er
effectief al minstens 1 speler als volledig bekend gold (dus er sowieso al
een onderscheid "volledig" vs. "onvolledig" bestaat), een expliciete,
optionele checkbox:
    "🔁 Ook forceren voor spelers die al volledig leken (bv. na een
    gewijzigde ploegsituatie)"
(standaard UIT — het bestaande, goedkopere standaardgedrag verandert dus
niet ongevraagd). Vinkt Kim dit aan, dan:
  - klassement wordt aangevraagd voor de VOLLEDIGE roster (niet enkel de
    gedetecteerde onvolledige spelers), MET force_all="true" (dus ook een
    reeds aanwezige klassementswaarde wordt opnieuw gecontroleerd/
    ververst, i.p.v. stilzwijgend overgeslagen);
  - de knop-tekst en de help-tooltip maken expliciet duidelijk dat
    matchdata en playing strength サ hoe dan ook サ al voor de VOLLEDIGE
    roster gebeuren, zodat het onderscheid met klassement niet langer
    verwarrend is.
Dit is een BEWUST optionele, expliciete keuze (i.p.v. het standaardgedrag
zelf te wijzigen) omdat het structureel meer scrapewerk betekent (en dus
meer tijd/quota) voor spelers die normaliter al correct gekend zijn — Kim
kan dit per analyse zelf afwegen ("te bekijken dan tijdens scrapen zelf hoe
ver je moet gaan").
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Callable, Optional
import streamlit as st
import firebase_service as fb
import lineup_lab as ll
import opponent_analysis as oa
import opponent_scout as osc
import schedule_scraper as ss
try:  # cloud_helpers is optioneel aanwezig; nooit hard falen op import
    from cloud_helpers import (
        is_scraping_available,
        trigger_github_actions_scrape,
        is_github_trigger_configured,
        # PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19: hergebruikt voor de
        # nieuwe, gecombineerde "ontbrekende gegevens ophalen"-knop hieronder.
        _render_tracked_progress,
        DEFAULT_WORKFLOW_FILE,
        KLASSEMENT_WORKFLOW_FILE,
    )
except Exception:  # pragma: no cover
    def is_scraping_available() -> bool:
        return False
    def trigger_github_actions_scrape(**_kwargs):
        return False, "cloud_helpers ontbreekt"
    def is_github_trigger_configured() -> bool:
        return False
    def _render_tracked_progress(*_args, **_kwargs):
        return {"found": False, "status": "unknown"}
    DEFAULT_WORKFLOW_FILE = "scrape-padel.yml"
    KLASSEMENT_WORKFLOW_FILE = "refresh-klassement.yml"
# PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16: optionele import, zodat dit
# bestand blijft werken ook als padelstats_scraper (Playwright-afhankelijk)
# lokaal niet beschikbaar is -- exact hetzelfde patroon als cloud_helpers.
try:
    import padelstats_scraper as pss
except Exception:  # pragma: no cover
    pss = None
# PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19: naam van de
# padelstat-achtergrondtaak, zelfde als in cloud_helpers.py.
PADELSTAT_WORKFLOW_FILE = "refresh-padelstat.yml"
@st.cache_data(ttl=300, show_spinner=False)
def _load_all_player_docs() -> dict:
    """Bredere set van ALLE gekende spelersdocumenten (niet enkel de
    tegenstander-roster), gebruikt als 'global_docs' voor de opportunistische
    ranking-fallback in opponent_dossier. Klein en goedkoop bij het huidige
    aantal spelers; 5 minuten gecached om herhaalde Firestore-reads binnen
    dezelfde sessie te vermijden."""
    try:
        docs = fb.db.collection(fb.PLAYERS_COLLECTION).stream()
        return {d.id: (d.to_dict() or {}) for d in docs}
    except Exception:
        return {}
def load_all_player_docs() -> dict:
    """Publieke naam voor _load_all_player_docs(), zodat dashboard.py dit kan
    hergebruiken zonder een 'privé' (underscore-prefix) functie rechtstreeks
    aan te spreken."""
    return _load_all_player_docs()
def _is_known(player_id: str) -> bool:
    """Een speler geldt als gekend zodra er matchdata OF een profiel bestaat.
    PADEL_ANALYSIS_KNOWN_PLAYER_FIX_2026-09-09: enkel op get_player_profile()
    controleren was te streng."""
    try:
        if fb.get_player_profile(player_id):
            return True
    except Exception:
        pass
    try:
        doc = fb.get_player(player_id) or {}
        return bool(doc.get("matches"))
    except Exception:
        return False
def _unknown_players(bundle: dict) -> list[dict]:
    return [
        player
        for player in (bundle.get("unique_players", []) or [])
        if not _is_known(player["user_id"])
    ]
def _data_completeness(player_id: str) -> dict:
    """PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (op verzoek van Kim, zie
    Fase C): "Er bestaat al een 'onvolledige data'-check (_has_incomplete_
    data()) — die wil ik hergebruiken om automatisch te beslissen welke
    acties nodig zijn, i.p.v. enkel een waarschuwing te tonen"):
    GESTRUCTUREERDE versie van de vroegere _has_incomplete_data() — geeft nu
    per CATEGORIE (matchdata/klassement/padelstat) een boolean terug i.p.v.
    enkel een platte lijst leesbare redenen. Dit laat de aanroeper toe om
    per categorie een gerichte actie te ondernemen (bv. enkel klassement
    triggeren voor wie dat mist, i.p.v. blind alles opnieuw te doen) — de
    basis voor de nieuwe, gecombineerde "ontbrekende gegevens ophalen"-knop
    (_render_unified_team_sync_trigger) hieronder, die dit vervangt van de
    vroegere 3 losse knoppen ("Nieuwe tegenstanders ophalen" / "Klassement
    nu ophalen" / "Playing strength nu ophalen").
    PADEL_ANALYSIS_FALSE_MISSING_ON_READ_ERROR_FIX_2026-09-19 (op verzoek
    van Kim: "ik heb 3 spelers zonder klassementshistoriek maar die zijn er
    wel"):
    BUG (opgelost): een mislukte fb.get_player()/fb.get_player_profile()/
    fb.get_padelstat_rating()-aanroep (bv. een tijdelijke Firestore-leesfout
    of quota-druk) werd stil opgevangen en liet doc/profile/cached gewoon
    leeg achter — met als gevolg dat "missing_*" op True kwam te staan ALSOF
    de data écht ontbrak, terwijl de read simpelweg mislukte.
    FIX: elke read houdt nu apart bij of ze GESLAAGD is. "missing_*" is
    voortaan ENKEL True als de betrokken read(s) écht slaagden EN het veld
    effectief afwezig was. Bij een mislukte read wordt in plaats daarvan
    "*_uncertain" gezet (zie _has_incomplete_data() voor hoe dit als een
    eerlijke, aparte melding getoond wordt)."""
    doc, doc_ok = {}, True
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:
        doc, doc_ok = {}, False
    profile, profile_ok = {}, True
    try:
        profile = fb.get_player_profile(player_id) or {}
    except Exception:
        profile, profile_ok = {}, False
    # Matchdata staat enkel in de players-collectie (doc). Is die read
    # mislukt, dan weten we het gewoonweg niet — nooit "missing" claimen op
    # basis van een lege fallback die enkel een leesfout weerspiegelt.
    matchdata_present = bool(doc.get("matches"))
    missing_matchdata = doc_ok and not matchdata_present
    matchdata_uncertain = (not doc_ok) and not matchdata_present
    # Klassement kan in BEIDE collecties staan. Pas als BEIDE reads
    # slaagden en GEEN van beide het veld had, is "missing" bevestigd.
    klassement_present = bool(doc.get("klassement_history") or profile.get("klassement_history"))
    klassement_fully_checked = doc_ok and profile_ok
    missing_klassement = klassement_fully_checked and not klassement_present
    klassement_uncertain = (not klassement_fully_checked) and not klassement_present
    try:
        cached = fb.get_padelstat_rating(player_id)
        padelstat_present = bool(cached and cached.get("rating") is not None)
        missing_padelstat = not padelstat_present
        padelstat_uncertain = False
    except Exception:
        # Zelfde principe: een leesfout is geen bevestigde afwezigheid.
        missing_padelstat = False
        padelstat_uncertain = True
    return {
        "missing_matchdata": missing_matchdata,
        "missing_klassement": missing_klassement,
        "missing_padelstat": missing_padelstat,
        "matchdata_uncertain": matchdata_uncertain,
        "klassement_uncertain": klassement_uncertain,
        "padelstat_uncertain": padelstat_uncertain,
    }
def _has_incomplete_data(player_id: str) -> tuple[bool, list[str]]:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16.
    Beoordeelt of deze speler nog ONTBREKENDE data heeft, ONGEACHT of hij/zij
    al een profiel heeft (dat is precies wat de oude _is_known()-check niet
    deed). Returns (incompleet, redenen).
    PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19: nu een dunne wrapper rond
    _data_completeness() hierboven (leesbare-tekst-variant), zodat er nog
    steeds maar 1 bron van waarheid is voor 'wat betekent onvolledig'.
    PADEL_ANALYSIS_FALSE_MISSING_ON_READ_ERROR_FIX_2026-09-19: onderscheidt
    nu expliciet een BEVESTIGD ontbrekend gegeven ("geen klassementshistoriek")
    van een MISLUKTE controle ("kon niet gecontroleerd worden") — zie
    _data_completeness() voor de volledige toelichting. Dit voorkomt dat een
    tijdelijke leesfout ten onrechte als "data ontbreekt echt" gemeld wordt."""
    c = _data_completeness(player_id)
    redenen = []
    if c["missing_matchdata"]:
        redenen.append("geen matchhistoriek")
    elif c.get("matchdata_uncertain"):
        redenen.append("matchhistoriek kon niet gecontroleerd worden (probeer later opnieuw)")
    if c["missing_klassement"]:
        redenen.append("geen klassementshistoriek")
    elif c.get("klassement_uncertain"):
        redenen.append("klassementshistoriek kon niet gecontroleerd worden (probeer later opnieuw)")
    if c["missing_padelstat"]:
        redenen.append("geen padelstat playing strength")
    elif c.get("padelstat_uncertain"):
        redenen.append("playing strength kon niet gecontroleerd worden (probeer later opnieuw)")
    return bool(redenen), redenen
def _ensure_klassement(player_ids: list[str], progress_label: str = "Klassement") -> None:
    """Haalt de klassementshistoriek op voor spelers die deze nog niet hebben.
    Enkel lokaal (Playwright vereist, zie is_scraping_available()). Duurt
    ongeveer 30-60s per speler; slaat spelers over die al klassement_history
    hebben, dus een herhaald bezoek kost niets voor reeds gekende spelers.
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_2026-09-19: toont, op Cloud, nu een
    neutrale caption i.p.v. te verwijzen naar 'deze omgeving'/'browser'.
    LET OP (PADEL_ANALYSIS_KLASSEMENT_BIANNUAL_SCHEDULE_2026-09-19): deze
    functie blijft ONGEWIJZIGD gedrag vertonen (klassement ophalen voor
    spelers die het nog NOOIT hadden - dus vooral NIEUWE spelers). Het
    OFFICIËLE klassement van een reeds bekende speler wordt sinds deze
    versie NIET meer hier of via een losse-speler-refresh ververst, maar
    apart, 2x per jaar, voor de VOLLEDIGE spelerslijst (zie
    scraper/refresh_klassement_biannual.py)."""
    if not is_scraping_available():
        st.caption(
            "📈 Klassementshistoriek wordt automatisch op de achtergrond opgehaald, of forceer "
            "het meteen met de knop '📈 Klassement nu ophalen voor deze ploeg' hierboven."
        )
        return
    to_fetch = []
    for pid in player_ids:
        try:
            prof = fb.get_player_profile(pid) or {}
        except Exception:
            prof = {}
        try:
            doc = fb.get_player(pid) or {}
        except Exception:
            doc = {}
        if not (doc.get("klassement_history") or prof.get("klassement_history")):
            to_fetch.append(pid)
    if not to_fetch:
        return
    try:
        from scrape_klassement import scrape_klassement, klassement_to_history_summary, extract_niveau_winrates
    except Exception as exc:
        st.caption("Klassement automatisch ophalen is momenteel niet beschikbaar.")
        return
    progress = st.progress(0.0, text=f"{progress_label}: starten...")
    for i, pid in enumerate(to_fetch, start=1):
        progress.progress(i / len(to_fetch), text=f"{progress_label}: speler {i}/{len(to_fetch)}...")
        try:
            periods = scrape_klassement(str(pid))
            history = klassement_to_history_summary(periods)
            niveau_winrates = extract_niveau_winrates(periods)
            klass_data = {
                "history": history,
                "niveau_winrates": niveau_winrates,
                "raw_periods": periods,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(payload, merge=True)
            fb.db.collection(fb.PLAYERS_COLLECTION).document(str(pid)).set(payload, merge=True)
        except Exception as exc:
            st.write(f"Klassement ophalen mislukt voor speler {pid}.")
    progress.progress(1.0, text=f"{progress_label}: klaar.")
    _load_all_player_docs.clear()
def _ensure_padelstat(
    players: list[dict],
    progress_label: str = "Padelstat",
    force: bool = False,
    team_name: Optional[str] = None,
) -> dict:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16.
    Haalt de padelstats.be playing strength op voor elke speler in `players`
    ({"user_id":..., "name":...}). Slaat spelers met een gecachete rating
    over, tenzij force=True. Gebruikt hun club uit het Firestore-profiel
    (indien gekend) om gelijknamige spelers te disambigueren -- zelfde
    mechanisme als padelstats_scraper.search_and_fetch_padelstat_rating().
    Enkel lokaal beschikbaar (Playwright vereist).
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_2026-09-19: neutrale caption op Cloud.
    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19 (op verzoek van
    Kim: "je weet toch welke ploeg je scrapet"): nieuwe, optionele
    `team_name`-parameter — gebruikt als FALLBACK-disambiguatiehint zodra
    een individuele speler zelf nog GEEN club in zijn/haar profiel heeft.
    Een reeds bekende, mogelijk andere club (bv. bij dubbel-clublidmaat-
    schap) blijft altijd leidend en wordt NOOIT overschreven door deze
    fallback — exact hetzelfde voorzichtige override-principe als
    refresh_padelstat_only.py se --club/CLUB (zie dat bestand)."""
    result = {"opgehaald": 0, "cache": 0, "niet_gevonden": 0, "fout": 0}
    if not is_scraping_available() or pss is None:
        st.caption(
            "Playing strength wordt automatisch op de achtergrond opgehaald, of forceer het "
            "meteen met de knop '🎯 Playing strength nu ophalen voor deze ploeg' hierboven."
        )
        return result
    te_doen = []
    for p in players:
        pid = str(p["user_id"])
        if not force:
            try:
                cached = fb.get_padelstat_rating(pid)
            except Exception:
                cached = None
            if cached and cached.get("rating") is not None:
                result["cache"] += 1
                continue
        te_doen.append(p)
    if not te_doen:
        return result
    progress = st.progress(0.0, text=f"{progress_label}: starten...")
    for i, p in enumerate(te_doen, start=1):
        pid = str(p["user_id"])
        naam = p.get("name") or pid
        progress.progress(i / len(te_doen), text=f"{progress_label}: {naam} ({i}/{len(te_doen)})...")
        try:
            profiel = fb.get_player_profile(pid) or {}
        except Exception:
            profiel = {}
        existing_club = profiel.get("club") or ""
        # PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: team_name
        # is enkel een FALLBACK — een reeds bekende club van deze speler
        # blijft leidend.
        club = existing_club or (team_name or "")
        try:
            gevonden = pss.search_and_fetch_padelstat_rating(naam, club=club or None)
        except Exception as exc:
            st.write(f"Playing strength ophalen mislukt voor {naam}.")
            result["fout"] += 1
            continue
        if not gevonden or gevonden.get("rating") is None:
            st.write(f"Geen playing strength gevonden voor {naam}.")
            result["niet_gevonden"] += 1
            continue
        try:
            fb.save_padelstat_rating(
                pid,
                gevonden.get("padelstat_id", ""),
                gevonden.get("rating"),
                gevonden.get("rating_source", "none"),
                gevonden.get("raw_text_snippet", ""),
            )
            result["opgehaald"] += 1
            if gevonden.get("club_disambiguation_note"):
                st.caption(f"⚠️ {naam}: club niet met zekerheid bevestigd.")
        except Exception as exc:
            st.write(f"Playing strength opslaan mislukt voor {naam}.")
            result["fout"] += 1
    progress.progress(1.0, text=f"{progress_label}: klaar.")
    return result
def _ensure_fresh_padelstat_for_roster(
    unique_players: list[dict], auto_scrape: bool, team_name: Optional[str] = None,
) -> None:
    """PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19 (op verzoek
    van Kim: "ook als je op analyse ploeg drukt om zeker de laatste waarde
    te hebben wanneer je dat doet"): garandeert dat elke "Tegenstander
    analyseren"-klik een GEFORCEERDE padelstat-verversing aanvraagt voor de
    volledige tegenstander-roster, bovenop de wekelijkse achtergrondtaak.
    PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19: BELANGRIJK — de
    aanroeper (_run_scout_and_scrape hieronder) geeft hier ENKEL nog spelers
    aan mee die AL een player_profiles-document hebben (dus geen gloednieuwe
    tegenstanders meer). Zie de module-docstring voor de volledige uitleg
    van waarom dit nodig was ("0 kandidaten"-verwarring).
    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: nieuwe, optionele
    `team_name`-parameter — op Cloud meegegeven als het "club"-input van
    refresh-padelstat.yml (disambiguatie-hint voor spelers zonder eigen
    club, zie refresh_padelstat_only.py se --club/CLUB-override).
    Lokaal (auto_scrape True): synchroon, dus de rest van dit scherm toont
    meteen de nieuwste waarde. Op Cloud (auto_scrape False): een
    achtergrond-trigger (duurt doorgaans 1-3 minuten). In beide gevallen
    wordt dit STIL geprobeerd (geen blokkerende foutmelding) zodat een
    mislukte trigger de rest van de analyse niet verstoort."""
    if not unique_players:
        return
    if auto_scrape:
        st.write("Playing strength verversen (garandeert de meest recente waarde)...")
        _ensure_padelstat(unique_players, progress_label="Padelstat", force=True, team_name=team_name)
        return
    player_ids_csv = ",".join(str(p["user_id"]) for p in unique_players if p.get("user_id"))
    if not player_ids_csv:
        return
    inputs = {"player": player_ids_csv, "max": str(len(unique_players)), "force_all": "true"}
    if team_name:
        inputs["club"] = team_name
    ok, msg = trigger_github_actions_scrape(
        workflow_file=PADELSTAT_WORKFLOW_FILE,
        inputs=inputs,
    )
    if ok:
        st.write(f"🎯 Playing strength-verversing gestart voor {len(unique_players)} speler(s) (meestal 1-3 min).")
    else:
        st.write("⚠️ Playing strength-verversing kon niet gestart worden.")
def _run_scout_and_scrape(
    fixtures: list[dict],
    opp: dict,
    next_match: dict,
    lookback: int,
    auto_scrape: bool,
    fetch_klassement: bool,
) -> dict:
    """Zoekt de opstelling op, scrapet meteen de onbekende spelers en haalt
    optioneel ook de klassementshistoriek op.
    Dit blijft het SNELLE standaardpad (enkel nieuwe/onbekende spelers,
    1 periode terug). Voor een ploeg die de eerste keer onvolledig
    binnenkwam, gebruik i.p.v. dit de aparte "Ververs alles"-knop
    (render_team_refresh_button / _run_full_team_refresh).
    PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19 (op verzoek van
    Kim, zie module-docstring voor de volledige toelichting): splitst de
    tegenstander-roster nu op in "al gekende" (hebben al een profiel) en
    "gloednieuwe" spelers. De geforceerde playing-strength-verversing wordt
    ENKEL voor de al gekende spelers aangevraagd — voor gloednieuwe spelers
    is dat zinloos (ze hebben nog geen profiel om te verversen) én overbodig
    (de matchdata-verversing hieronder, of de "🚀 Nieuwe tegenstanders
    ophalen"-knop, haalt hun playing strength AUTOMATISCH mee op als
    onderdeel van dezelfde verwerking).
    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: geeft nu
    opp["name"] door aan _ensure_fresh_padelstat_for_roster() als
    disambiguatie-hint."""
    with st.status("Tegenstander analyseren...", expanded=True) as status:
        st.write("Vorige wedstrijd(en) van de tegenstander opzoeken...")
        bundle = osc.scout_opponent(
            fixtures,
            opp["name"],
            opp["ploeg_id"],
            next_match["date_text"],
            lookback=lookback,
        )
        if bundle.get("note"):
            st.write(bundle["note"])
            status.update(label="Analyse afgerond (beperkte data)", state="complete")
            return bundle
        found = len(bundle.get("unique_players", []) or [])
        st.write(f"{found} tegenstander-speler(s) gevonden.")
        unknown = _unknown_players(bundle)
        if unknown:
            if not auto_scrape:
                st.write(
                    f"{len(unknown)} speler(s) nog niet volledig gekend — hun matchdata en playing "
                    "strength worden automatisch samen opgehaald zodra je hieronder 'Nieuwe "
                    "tegenstanders ophalen' gebruikt."
                )
            else:
                st.write(f"{len(unknown)} nieuwe speler(s) scrapen...")
                progress = st.progress(0.0, text="Starten...")
                def _callback(index: int, total: int, name: str) -> None:
                    fraction = index / total if total else 0.0
                    progress.progress(fraction, text=f"({index}/{total}) {name} scrapen...")
                try:
                    result = osc.scrape_new_opponent_players(
                        unknown, lookback_periods=1, delay=1.5, progress_callback=_callback,
                    )
                    progress.progress(1.0, text="Klaar.")
                    scraped = len(result.get("newly_scraped", []) or [])
                    failed = result.get("failed", []) or []
                    st.write(f"{scraped} gescrapet, {len(failed)} mislukt.")
                    for item in failed:
                        st.write(f"Mislukt: {item.get('name')}")
                except Exception as exc:
                    progress.empty()
                    st.write("Scrapen mislukt.")
        else:
            st.write("Alle spelers zijn al gekend qua matchdata.")
        if fetch_klassement:
            st.write("Klassementshistoriek controleren/ophalen (enkel voor NOG NIET gekende spelers)...")
            all_ids = [p["user_id"] for p in bundle.get("unique_players", []) or []]
            _ensure_klassement(all_ids, progress_label="Klassement")
        # PADEL_ANALYSIS_NEW_TEAM_ZERO_CANDIDATES_FIX_2026-09-19: enkel de
        # AL GEKENDE spelers (bestaand profiel) krijgen hier een geforceerde
        # playing-strength-verversing — gloednieuwe spelers worden gedekt
        # door de matchdata-verversing hierboven/de aparte "Nieuwe
        # tegenstanders ophalen"-knop, die dit automatisch meeneemt.
        all_players = bundle.get("unique_players", []) or []
        unknown_ids = {p["user_id"] for p in unknown}
        known_players = [p for p in all_players if p["user_id"] not in unknown_ids]
        _ensure_fresh_padelstat_for_roster(known_players, auto_scrape=auto_scrape, team_name=opp.get("name"))
        status.update(label="Analyse afgerond", state="complete")
        return bundle
def _run_full_team_refresh(
    unique_players: list[dict],
    lookback_periods: int = 3,
    force: bool = False,
    team_name: Optional[str] = None,
) -> dict:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16.
    Voor ELKE speler in unique_players (ongeacht een reeds bestaand profiel):
      1. matchdata (her)scrapen met `lookback_periods` periodes;
      2. padelstat playing strength ophalen/vernieuwen;
      3. klassementshistoriek ophalen/vernieuwen (enkel indien nog NIET
         gekend - zie PADEL_ANALYSIS_KLASSEMENT_BIANNUAL_SCHEDULE_2026-09-19
         hierboven: het OFFICIËLE klassement van een reeds bekende speler
         wordt niet meer hier ververst, maar 2x/jaar voor de volledige lijst).
    Dit is de "trage maar volledige" tegenhanger van
    osc.scrape_new_opponent_players(), specifiek om spelers te herstellen die
    al een (onvolledig) profiel hebben -- exact het scenario dat de gewone
    'Tegenstander analyseren'-knop stil overslaat.
    PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17: gebruikt nu
    osc._ensure_profile_safe() i.p.v. een kale fb.save_player_profile()-
    aanroep, zodat een bestaande club nooit meer stilzwijgend gewist wordt
    en elk aangeraakt profiel een added_by-marker krijgt indien nog afwezig.
    Zie de uitgebreide toelichting in opponent_scout.py's moduledocstring.
    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: geeft team_name
    nu door aan _ensure_padelstat() als disambiguatie-fallback.
    LET OP: deze functie wordt enkel getoond/gebruikt als can_scrape True is
    (lokaal). Op Cloud gebruik i.p.v. hiervan de directe achtergrond-
    trigger-knoppen in render_scout_header()."""
    from scrape_player import scrape_player  # lazy: Playwright, zie osc.py
    result = {
        "totaal": len(unique_players),
        "matchdata_ok": 0,
        "matchdata_fout": [],
        "padelstat": {},
        "klassement_gestart": False,
    }
    st.write(f"Matchdata verversen voor {len(unique_players)} speler(s) (tot {lookback_periods} periode(s) terug)...")
    progress = st.progress(0.0, text="Starten...")
    for i, p in enumerate(unique_players, start=1):
        pid = str(p["user_id"])
        naam = p.get("name") or pid
        progress.progress(i / len(unique_players), text=f"({i}/{len(unique_players)}) {naam}...")
        try:
            scrape_player(
                pid,
                max_new_periods=lookback_periods,
                force_full_refresh=force,
                save_to_firebase=True,
            )
            osc._ensure_profile_safe(pid, naam)
            result["matchdata_ok"] += 1
        except Exception as exc:
            result["matchdata_fout"].append({"name": naam, "error": str(exc)})
    progress.progress(1.0, text="Matchdata: klaar.")
    st.write("Playing strength ophalen/vernieuwen...")
    result["padelstat"] = _ensure_padelstat(unique_players, progress_label="Padelstat", force=force, team_name=team_name)
    st.write("Klassementshistoriek ophalen/vernieuwen (enkel voor nog niet gekende spelers)...")
    all_ids = [p["user_id"] for p in unique_players]
    _ensure_klassement(all_ids, progress_label="Klassement")
    result["klassement_gestart"] = True
    return result
def _render_unified_team_sync_trigger(
    unique_players: list[dict], key_prefix: str, team_name: Optional[str] = None,
) -> dict:
    """PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C, op verzoek van
    Kim, chat 2026-09-19): "Het zou beter zijn mocht je bij 'tegenstander
    analyseren' meteen al die zaken doet als dat nog niet gebeurd is. Als je
    dan bvb een 2de maal de tegenstander analyseert moet je enkel nog de
    playing strength refreshen en bekijken of er eventueel matchen bij
    gekomen zijn."
    VERVANGT de vroegere _render_cloud_klassement_padelstat_triggers() (2
    losse knoppen: "📈 Klassement nu ophalen" / "🎯 Playing strength nu
    ophalen") EN de losse "🚀 Nieuwe tegenstanders ophalen"-knop in
    prepare_team_docs() door ÉÉN GECOMBINEERDE knop, die zichzelf elke keer
    opnieuw aanpast op basis van wat er ECHT nog ontbreekt (_data_
    completeness() per speler) — nooit 3 aparte acties meer nodig.
    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19 (op verzoek van
    Kim: "je weet toch welke ploeg je scrapet dus deze melding is eigenlijk
    niet nodig als je meteen de juiste club meegeeft"): nieuwe, optionele
    `team_name`-parameter. Wanneer meegegeven, wordt deze als "club"-input
    meegestuurd naar refresh-padelstat.yml (zie refresh_padelstat_only.py
    se --club/CLUB-override).
    PADEL_ANALYSIS_FALSE_MISSING_ON_READ_ERROR_FIX_2026-09-19: missing_
    klassement_ids/missing_matchdata_ids en n_incomplete tellen nu ook
    spelers mee waarvoor de completeness-check ONZEKER bleef (leesfout,
    zie _data_completeness()).
    --------------------------------------------------------------------
    PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21 (op verzoek van
    Kim, chat 2026-09-21: "ik heb nu de ploeg KTC ISIS eens willen
    analyseren [...] ik heb een knop om ontbrekende gegevens van 3 van de 6
    spelers op te halen maar eigenlijk moeten alle spelers ondertussen
    opnieuw kunnen gefreshed worden (te bekijken dan tijdens scrapen zelf
    hoe ver je moet gaan.)"):
    --------------------------------------------------------------------
    CONTEXT: matchdata (stap 1, mode="missing") en playing strength (stap 3,
    force_all="true") werden HIER AL ALTIJD voor de VOLLEDIGE roster
    getriggerd — enkel klassement (stap 2) was bewust beperkt tot de
    gedetecteerde onvolledige/onzekere spelers, om onnodige herhaalscrapes
    te vermijden. Voor een ploeg waarvan de situatie zichtbaar veranderd is
    (zoals KTC ISIS) wil Kim de MOGELIJKHEID om dat onderscheid opzij te
    zetten en ECHT alles opnieuw te laten controleren.
    FIX: toont, ENKEL wanneer er al minstens 1 speler als volledig gold (dus
    er een onderscheid "volledig"/"onvolledig" bestaat om te kunnen
    overrulen), een optionele checkbox "🔁 Ook forceren voor spelers die al
    volledig leken" (standaard UIT). Vinkt Kim dit aan, dan wordt klassement
    voor de VOLLEDIGE roster aangevraagd, MET force_all="true" (i.p.v. enkel
    de gedetecteerde onvolledige subset)."""
    if not unique_players:
        return {}
    all_ids = [str(p["user_id"]) for p in unique_players if p.get("user_id")]
    if not all_ids:
        return {}
    completeness = {pid: _data_completeness(pid) for pid in all_ids}
    missing_matchdata_ids = [
        pid for pid in all_ids
        if completeness[pid]["missing_matchdata"] or completeness[pid].get("matchdata_uncertain")
    ]
    missing_klassement_ids = [
        pid for pid in all_ids
        if completeness[pid]["missing_klassement"] or completeness[pid].get("klassement_uncertain")
    ]
    n_incomplete = len({
        pid for pid in all_ids
        if completeness[pid]["missing_matchdata"] or completeness[pid]["missing_klassement"]
        or completeness[pid]["missing_padelstat"] or completeness[pid].get("matchdata_uncertain")
        or completeness[pid].get("klassement_uncertain") or completeness[pid].get("padelstat_uncertain")
    })
    if n_incomplete:
        label = f"🔄 Ontbrekende gegevens ophalen ({n_incomplete} van {len(all_ids)} speler(s))"
        help_text = (
            "Haalt in 1 stap de nog ontbrekende wedstrijdgegevens, klassement en playing strength "
            "op voor deze ploeg. Wedstrijdgegevens en playing strength worden hoe dan ook voor de "
            "VOLLEDIGE roster gecontroleerd/ververst; enkel klassement richt zich standaard op de "
            f"{n_incomplete} speler(s) die nog effectief onvolledig zijn."
        )
    else:
        label = "🔄 Controleren op nieuwe wedstrijden"
        help_text = (
            "Deze ploeg is al volledig gekend. Controleert enkel of er intussen nieuwe "
            "wedstrijden bijkwamen (playing strength wordt sowieso al automatisch bij elke "
            "analyse ververst)."
        )
    # PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21: enkel tonen als
    # er sowieso al een onderscheid "volledig"/"onvolledig" bestaat (anders
    # is de checkbox zinloos - dan wordt toch al iedereen als onvolledig
    # behandeld).
    force_all_players = False
    n_already_complete = len(all_ids) - n_incomplete
    if n_incomplete and n_already_complete:
        force_all_players = st.checkbox(
            "🔁 Ook forceren voor spelers die al volledig leken (bv. na een gewijzigde ploegsituatie)",
            value=False, key=f"{key_prefix}_force_all_sync",
            help=(
                "Standaard wordt klassement enkel opnieuw gecontroleerd voor spelers waarvoor dat "
                "nog ontbreekt of onzeker is. Vink dit aan om klassement voor ALLE "
                f"{len(all_ids)} speler(s) van deze ploeg opnieuw te laten controleren/verversen, "
                "ook wie al volledig leek — handig als de situatie van de ploeg intussen "
                "zichtbaar veranderd is (bv. ze speelden ondertussen matchen)."
            ),
        )
        if force_all_players:
            label = f"🔄 Ontbrekende gegevens ophalen (+ alles forceren voor {len(all_ids)} speler(s))"
    if not is_github_trigger_configured():
        return {"missing_matchdata": len(missing_matchdata_ids), "missing_klassement": len(missing_klassement_ids)}
    if st.button(label, key=f"{key_prefix}_unified_sync", type="primary", help=help_text):
        # 1. Wedstrijdgegevens: ALTIJD voor de VOLLEDIGE roster ("missing"-
        #    modus slaat reeds actuele spelers snel over) — dit detecteert
        #    automatisch nieuwe wedstrijden EN nieuwe spelers.
        t0 = time.time()
        ok_match, _ = trigger_github_actions_scrape(player_ids=",".join(all_ids), mode="missing")
        ph_match = st.empty()
        if ok_match:
            _render_tracked_progress(DEFAULT_WORKFLOW_FILE, t0, ph_match, label_prefix="Wedstrijdgegevens: ")
        else:
            ph_match.error("Wedstrijdgegevens: kon niet gestart worden.")
        # 2. Klassement: standaard enkel voor wie dat nog effectief mist (of
        #    onzeker is) — TENZIJ force_all_players aangevinkt is, dan de
        #    VOLLEDIGE roster met force_all="true" (PADEL_ANALYSIS_TEAM_SYNC_
        #    FULL_FORCE_OPTION_2026-09-21).
        klassement_target_ids = all_ids if force_all_players else missing_klassement_ids
        if klassement_target_ids:
            t1 = time.time()
            ok_k, _ = trigger_github_actions_scrape(
                workflow_file=KLASSEMENT_WORKFLOW_FILE,
                inputs={
                    "player": ",".join(klassement_target_ids),
                    "max": str(len(klassement_target_ids)),
                    "force_all": "true" if force_all_players else "false",
                },
            )
            ph_k = st.empty()
            if ok_k:
                _render_tracked_progress(KLASSEMENT_WORKFLOW_FILE, t1, ph_k, label_prefix="Klassement: ")
            else:
                ph_k.error("Klassement: kon niet gestart worden.")
        # 3. Playing strength: geforceerd voor de VOLLEDIGE roster (garandeert
        #    een verse waarde, consistent met de bestaande "altijd verversen
        #    bij analyse"-regel — zie _ensure_fresh_padelstat_for_roster()).
        #    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: club-hint
        #    meegegeven wanneer team_name bekend is.
        t2 = time.time()
        padelstat_inputs = {"player": ",".join(all_ids), "max": str(len(all_ids)), "force_all": "true"}
        if team_name:
            padelstat_inputs["club"] = team_name
        ok_p, _ = trigger_github_actions_scrape(
            workflow_file=PADELSTAT_WORKFLOW_FILE,
            inputs=padelstat_inputs,
        )
        ph_p = st.empty()
        if ok_p:
            _render_tracked_progress(PADELSTAT_WORKFLOW_FILE, t2, ph_p, label_prefix="Playing strength: ")
        else:
            ph_p.error("Playing strength: kon niet gestart worden.")
        _load_all_player_docs.clear()
        # PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_REPORT_REFRESH_2026-09-19 (gevonden
        # bij het naast elkaar leggen van dit bestand en opponent_analysis.py,
        # op verzoek van Kim): opponent_analysis._underlying_data_is_fresher()
        # gebruikt freshness_cache.py — een SESSIE-LOKALE TTL-cache. Zonder
        # deze invalidatie zou het team-rapport hieronder de zonet
        # binnengekomen verse data NIET zien totdat die sessie-cache vanzelf
        # verloopt.
        try:
            import freshness_cache as fcache
            fcache.invalidate_all()
        except Exception:
            pass
        st.rerun()
    return {"missing_matchdata": len(missing_matchdata_ids), "missing_klassement": len(missing_klassement_ids)}
def render_scout_header(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    lookback: int = 1,
) -> Optional[tuple[dict, dict]]:
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: toont enkel de
    'volgende match'-titel, de klassement-checkbox en de 'Tegenstander
    analyseren'-knop; voert desgevallend scout+scrape+klassement-ophaal uit.
    PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16: toont daarnaast, zodra een
    bundle beschikbaar is, de aparte "🔄 Ververs alles voor deze ploeg"-knop
    (enkel lokaal, want scrapen vereist een browser).
    PADEL_ANALYSIS_CLOUD_KLASSEMENT_PADELSTAT_TRIGGER_2026-09-17: toont OP
    CLOUD (can_scrape False) i.p.v. daarvan de directe achtergrond-
    trigger-knoppen voor klassement/padelstat.
    PADEL_ANALYSIS_UI_NEUTRAL_LANGUAGE_2026-09-19: alle teksten neutraal
    gemaakt (geen "GitHub Actions"/"deze omgeving kan niet scrapen" meer).
    PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: geeft nu
    opp["name"] door als team_name aan _run_full_team_refresh() en
    _render_unified_team_sync_trigger(), zodat beide paden (lokaal en Cloud)
    de gekende ploegnaam als disambiguatie-hint kunnen gebruiken.
    Geeft (bundle, opp) terug zodra een bundle beschikbaar is, anders None."""
    team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id)
    next_match = ss.get_next_match(team_fixtures)
    if not next_match:
        st.success("Geen nog te spelen wedstrijden gevonden voor dit schema.")
        return None
    opp = ss.opponent_of(next_match, own_ploeg_id)
    opp["spelgroep_id"] = next_match.get("spelgroep_id")
    st.markdown(
        f"**{next_match['date_text']}** - tegen **{opp['name']}** "
        f"({next_match.get('poule_label', '')})"
    )
    scout_key = f"scout_{opp['ploeg_id']}_{next_match['date_text']}"
    can_scrape = is_scraping_available()
    fetch_klassement = False
    if not can_scrape:
        st.caption(
            "Nieuwe spelers en klassement worden automatisch op de achtergrond opgehaald, of "
            "forceer dat hieronder direct voor deze ploeg. Playing strength wordt bij elke "
            "analyse altijd automatisch geforceerd ververst voor spelers die al gekend zijn."
        )
    else:
        fetch_klassement = st.checkbox(
            "📈 Ook klassementshistoriek ophalen voor nog onbekende spelers (lokaal, ±30-60s per speler)",
            value=True, key=f"fetch_klassement_{sel_player_id}",
        )
    col_scout, col_refresh = st.columns([2, 2])
    with col_scout:
        if st.button("🔍 Tegenstander analyseren", key=f"btn_scout_{sel_player_id}", type="primary"):
            st.session_state[scout_key] = _run_scout_and_scrape(
                fixtures, opp, next_match, lookback,
                auto_scrape=can_scrape, fetch_klassement=fetch_klassement,
            )
    bundle = st.session_state.get(scout_key)
    # PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16: enkel tonen zodra er al
    # een bundle is (we moeten weten wie de spelers zijn) en enkel lokaal.
    with col_refresh:
        if bundle and bundle.get("unique_players") and can_scrape:
            if st.button(
                "🔄 Ververs alles voor deze ploeg",
                key=f"btn_full_refresh_{sel_player_id}",
                help=(
                    "Herhaalt matchdata (meerdere periodes) en playing strength voor ALLE spelers "
                    "van deze ploeg, ook wie al een (onvolledig) profiel heeft. Klassement enkel "
                    "voor wie dat nog nooit had. Trager dan 'Tegenstander analyseren', maar slaat "
                    "niemand over."
                ),
            ):
                with st.status("Volledige ploeg verversen...", expanded=True) as status:
                    refresh_result = _run_full_team_refresh(
                        bundle["unique_players"], lookback_periods=3, force=False, team_name=opp.get("name"),
                    )
                    p = refresh_result["padelstat"]
                    st.write(
                        f"Matchdata: {refresh_result['matchdata_ok']}/{refresh_result['totaal']} OK"
                        + (f", {len(refresh_result['matchdata_fout'])} mislukt" if refresh_result["matchdata_fout"] else "")
                    )
                    st.write(
                        f"Playing strength: {p.get('opgehaald', 0)} opgehaald, {p.get('cache', 0)} al gekend, "
                        f"{p.get('niet_gevonden', 0)} niet gevonden, {p.get('fout', 0)} fout"
                    )
                    for item in refresh_result["matchdata_fout"]:
                        st.write(f"⚠️ {item['name']}: kon niet ververst worden.")
                    status.update(label="Volledige ploeg ververst", state="complete")
                _load_all_player_docs.clear()
    st.divider()
    if bundle:
        # PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C): op Cloud
        # (can_scrape False) toont dit de gecombineerde "ontbrekende
        # gegevens ophalen"-knop, mét optionele "forceer alles"-checkbox
        # sinds PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21.
        if not can_scrape and bundle.get("unique_players"):
            _render_unified_team_sync_trigger(
                bundle["unique_players"], key_prefix=f"scout_{sel_player_id}", team_name=opp.get("name"),
            )
    if not bundle or not bundle.get("unique_players"):
        return (bundle, opp) if bundle else None
    return bundle, opp
def prepare_team_docs(
    bundle: dict, sel_player_id: str,
) -> tuple[dict, dict]:
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: toont de 'nog niet
    gekende spelers'-caption/achtergrond-trigger (indien van toepassing) en
    bouwt all_docs (matchdata van de tegenstander-roster) + global_docs
    (brede cache, voor de ranking-fallback in opponent_dossier). Geeft
    (all_docs, global_docs) terug voor gebruik door
    opponent_analysis.get_team_report().
    PADEL_ANALYSIS_TEAM_UNIFIED_SYNC_2026-09-19 (Fase C): de vroegere,
    aparte "🚀 Nieuwe tegenstanders ophalen"-knop is HIER WEGGEHAALD — die
    actie zit nu VOLLEDIG vervat in de gecombineerde knop hoger op de
    pagina (_render_unified_team_sync_trigger(), aangeroepen vanuit
    render_scout_header()), die matchdata + klassement + playing strength
    in 1 klik regelt zodra dat nog nodig is. Deze functie toont hier enkel
    nog een informatieve caption, geen actieknop meer (voorkomt 2 knoppen
    met overlappende functie op dezelfde pagina)."""
    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        return {}, {}
    unknown_ids = {player["user_id"] for player in _unknown_players(bundle)}
    all_docs = ll.get_docs_for_players([p["user_id"] for p in unique_players])
    if unknown_ids:
        st.caption(
            f"⚠️ {len(unknown_ids)} speler(s) nog niet volledig gekend qua matchdata — gebruik de "
            "knop '🔄 Ontbrekende gegevens ophalen' hierboven om dit (samen met klassement en "
            "playing strength) in 1 klik aan te vullen."
        )
    global_docs = _load_all_player_docs()
    return all_docs, global_docs
def render_scout_block(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    reeks_url: Optional[str] = None,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    lookback: int = 1,
):
    """Toont de volgende match en het volledige tegenploeg-analysescherm, in
    de OUDE volgorde (header, dan overzicht/detail/AI van de tegenploeg).
    PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: dashboard.py roept
    sinds deze versie render_scout_header()/prepare_team_docs() rechtstreeks
    aan, in een ANDERE volgorde. Deze functie blijft behouden voor eventuele
    andere/toekomstige aanroepers die de oorspronkelijke volgorde verwachten."""
    header_result = render_scout_header(sel_player_id, fixtures, own_ploeg_id, lookback=lookback)
    if not header_result:
        return None
    bundle, opp = header_result
    all_docs, global_docs = prepare_team_docs(bundle, sel_player_id)
    if not bundle.get("unique_players"):
        return bundle, opp
    oa.render_team_analysis(
        bundle,
        opp,
        all_docs,
        current_reeks_url=reeks_url,
        current_spelgroep_id=opp.get("spelgroep_id"),
        home_player_id=sel_player_id,
        global_docs=global_docs,
        go_to_player_fn=go_to_player_fn,
        key_prefix=f"scout_team_{sel_player_id}",
    )
    return bundle, opp
# PADEL_ANALYSIS_POULE_TEAMS_TAB_2026-09-19 (Fase D1, op verzoek van Kim:
# "Het zou ook handig zijn dat er een mogelijkheid is om al meteen ook
# andere ploegen van je poule al eens te bekijken. eventueel via apart
# tabblad."):
# Publieke naam voor _render_unified_team_sync_trigger() (Fase C), zodat de
# nieuwe poule_teams_ui.py dit kan HERGEBRUIKEN voor WILLEKEURIGE ploegen in
# de poule — niet enkel de eerstvolgende tegenstander. Dezelfde "ontbrekende
# gegevens ophalen"-logica (matchdata + klassement + playing strength, 1
# knop die zichzelf aanpast aan wat er nog ontbreekt, incl. de club-hint uit
# PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19, en sinds
# PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21 ook de optionele
# "forceer alles"-checkbox) hoort exact hetzelfde te werken voor een
# willekeurige poule-ploeg als voor de eerstvolgende tegenstander — geen
# duplicatie van die logica.
render_unified_team_sync_trigger = _render_unified_team_sync_trigger
