"""
lineup_retrospective.py - Nabeschouwing: per eerder gespeelde ontmoeting de
voorspelde winkans tegenover de echte uitslag, MET de padelstat-/officiële
klassementwaarden van TOEN (niet de huidige), plus een kalibratieblok over
alle gespeelde matchen samen met een instelbare winkansfactor.

--------------------------------------------------------------------------
PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03 (op verzoek van Kim: "het zou ook
handig zijn om al gespeelde matchen ook nog te kunnen analyseren maar dan
met de padelstat waardes van toen [...] in principe moet je dan enkel die
opstellen simuleren en eventueel tonen wat het betere alternatief was en
ook de winstpercentages aftoetsen met om te bekijken of de winstkansen wel
goed berekend werden [...] we hebben in het verleden al gekeken om dan ook
de factor voor berekening winst te visualiseren en aanpasbaar te maken")
--------------------------------------------------------------------------
BRONNEN VAN "DE WAARDEN VAN TOEN", in volgorde van betrouwbaarheid:
  1. Een momentopname uit lineup_plan_screen.py (collectie
     "lineup_snapshots"): de EXACTE padelstat-/klassementwaarden die de app
     gebruikte toen je die ontmoeting effectief plande. Enkel beschikbaar
     voor ontmoetingen waar je het planscherm gebruikte.
  2. firebase_service.get_padelstat_rating_at(player_id, datum): de
     padelstat-HISTORIEK (PADEL_ANALYSIS_PADELSTAT_HISTORY_2026-10-03),
     die vanaf de eerste refresh ERNA automatisch verder aangevuld wordt.
     Voor data van VOOR die historiek bestond, is er simpelweg niets.
  3. PADEL_ANALYSIS_RETRO_PADELSTAT_PRIORITY_2026-10-04 (zie verderop): de
     MEEST RECENTE padelstat-waarde, ongeacht of die exact op/voor de
     matchdatum ligt - enkel voor ONZE EIGEN spelers, enkel als stap 2 niets
     opleverde.
  4. Voor TEGENSTANDERS: het officiële klassement staat als tekst
     ("P200" e.d.) al IN het eigen matchrecord (opp1_ranking/opp2_ranking,
     zoals getoond op het uitslagenblad op dat moment) - dat is dus
     ALTIJD een waarde van toen, nooit de huidige. Voor onze EIGEN spelers
     is dit de ALLERLAATSTE terugval (zie punt 3 hierboven, die daar NU
     voor gaat).
--------------------------------------------------------------------------
WAAROM DIT BESTAND EIGEN ENCOUNTER/BOARD-RECONSTRUCTIE HEEFT (NIET
ll.build_encounter_index()/ll.reconstruct_boards() HERGEBRUIKT):
die twee functies in lineup_lab.py geven exact dezelfde GROEPERING
(match_date, encounter) en dedupe-sleutel (match_id + koppel) terug - dat
MOET identiek blijven, dus de logica hieronder is BEWUST een letterlijke
kopie daarvan - maar ze laten de "opp1_ranking"/"opp2_ranking"-tekstvelden
van elk matchrecord vallen, die hier net essentieel zijn (bron 4 hierboven).
Een lokale kopie die deze velden WEL meeneemt is veiliger dan de publieke
functies van lineup_lab.py aan te passen voor een gebruik dat buiten hun
oorspronkelijke scope valt.
--------------------------------------------------------------------------
KALIBRATIE: exact dezelfde methodologie als de eerdere validatie die tot
scale=207 leidde (zie lineup_lab.py, PADEL_ANALYSIS_WINPROB_CALIBRATION_
2026-09-22-commentaar): Brier-score, accuraatheid, en gemiddeld voorspeld
tegenover werkelijk gewonnen per kansklasse (bins van 10 procentpunt). De
schuifregelaar herberekent deze cijfers LIVE voor een gekozen factor, maar
wijzigt NERGENS de globale DEFAULT_WIN_PROBABILITY_SCALE die de rest van de
app gebruikt (lineup_lab.py, lineup_rotation.py) - dat blijft een BEWUSTE,
aparte stap mocht Kim de uitkomst willen overnemen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_PLAYER_FILTER_2026-10-04 (op verzoek van Kim: "ik wil
daar enkel matchen zien die de geselecteerde speler gespeeld heeft" - in de
vorige versie verschenen ook matchen van ANDERE spelers uit de club, bv.
damesmatchen, omdat render_retrospective_tab() docs ophaalde voor ALLE
profielen (tot 40) en de encounter-index over AL die spelers samen bouwde,
i.p.v. enkel de speler die bovenaan de pagina gekozen is)
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd: `render_retrospective_tab(profiles)` bouwde
`docs = ll.get_docs_for_players([alle 40 profile-ids])` en
`build_retro_encounter_index(docs)` groepeerde dan ALLE matchrecords van AL
die spelers samen, puur op (datum, encounter) - zonder te filteren op WIE
die match speelde. Zodra 2 verschillende spelers toevallig dezelfde
datum/encounter-tekst hadden (bv. een damesploeg en een herenploeg die
dezelfde speeldag een andere interclub-ontmoeting hadden), verschenen beide
in dezelfde (foute) groep, en dus ook in de dropdown van de gekozen speler.
FIX (sindsdien verder verfijnd, zie PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04
hieronder): render_retrospective_tab() filtert nog steeds EXPLICIET op een
GEKEND, GEKOZEN spelerspeloton - nooit meer "alle 40 profielen impliciet".
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_PERF_2026-10-04 (op verzoek van Kim, met meetgegevens:
"Totaal deze render: 263.47s [...] Zwaarste eigen tijd: SECTIE Nabeschouwing
- 78.82s" en een export met 1126 regels "Firestore: get_padelstat_rating")
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd door de meting: `_own_value_at()`/`_opponent_value_at()`
riepen `fb.get_padelstat_rating_at(player_id, datum)` aan - en DIE functie
doet intern `fb.get_padelstat_rating(player_id)`, dus EEN Firestore-
document-read - PER SPELER PER BORD PER VOORSPELLING. Met de kalibratie die
over alle ~300 ontmoetingen/1188 matchen van (destijds) alle 40 profielen
liep, gaf dat 1126 aparte reads van ~0.15-0.17s = ~184s, exact de gemeten
bottleneck (en de reden waarom de vorige tab lang "grayed out" bleef: dat is
normaal Streamlit-gedrag tijdens een trage render, geen apart defect).
FIX, data-ophalen en scale-afhankelijke berekening ONTKOPPELD:
  1. _collect_relevant_player_ids(index) verzamelt ALLE speler-id's (eigen +
     tegenstander) die voorkomen in de (nu al gefilterde) encounter-index.
  2. _load_padelstat_histories(player_ids) - EEN fb.get_padelstat_rating()
     per UNIEKE speler (dus 1x, niet per bord), @st.cache_data(ttl=300) -
     een schuifregelaar-beweging of nieuwe ontmoeting-keuze hergebruikt deze
     cache en doet dus GEEN nieuwe Firestore-reads meer.
  3. _rating_at_from_history(history, datum) - PURE (geen I/O) kopie van
     firebase_service.get_padelstat_rating_at()'s logica, werkend op de al
     ingeladen historiek-lijst.
  4. gather_raw_match_data(index, ...) verzamelt voor ELK bord de SCHAAL-
     ONAFHANKELIJKE ruwe data (our_avg/their_avg/actual_won) - dit gebeurt
     1x per sessie (gecached in st.session_state op een signatuur), NIET
     opnieuw bij elke schuifregelaar-beweging.
  5. score_raw_at_scale(raw_rows, scale) herberekent de winkans voor een
     GEKOZEN factor - een PURE, snelle berekening (geen I/O), dus de
     schuifregelaar en de hieronder beschreven auto-zoekfunctie zijn
     vrijwel instant.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_AUTOSCALE_2026-10-04 (op verzoek van Kim: "Kan je dan
al niet meteen zelf de beste winskansfactor kiezen om de beste brier score
te hebben ipv dat ik die manueel moet gaan verschuiven en dan (lang)
wachten om te zien of het beter is. Gewoon bvb met 1 knop een berekening
starten die een voorstel doet voor aanpassing die je dan kan bevestigen?")
--------------------------------------------------------------------------
find_best_scale(raw_rows) doorzoekt een reeks kandidaat-factoren (50 t.e.m.
400, stappen van 5) en berekent voor ELK de Brier-score - dankzij de
ontkoppeling hierboven is dit PUUR rekenwerk op de al opgehaalde ruwe data,
dus snel genoeg voor een knop-klik i.p.v. een aparte achtergrondtaak. De UI
toont het voorstel (nieuwe factor + Brier-score, naast de huidige) met een
aparte "Toepassen"-knop - de schuifregelaar verspringt dus nooit vanzelf,
Kim bevestigt expliciet voor de nieuwe waarde ingesteld wordt. Dit wijzigt,
net als de schuifregelaar zelf, ENKEL deze weergave - niet de globale
DEFAULT_WIN_PROBABILITY_SCALE.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_PADELSTAT_PRIORITY_2026-10-04 (op verzoek van Kim,
met screenshot: "ik zie dat je enkel officieel klassement in rekening
neemt, wat niet bruikbaar is. Je moet padelstat score gebruiken. Als je
het historisch niet hebt mag je eventueel wel de huidige waarde gebruiken
(zeker voor recente matchen)")
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd: `_own_value_at()` had voor ONZE EIGEN spelers maar 3
stappen: snapshot -> padelstat-historiek OP DATUM -> huidig OFFICIEEL
KLASSEMENT. Ontbrak er geen snapshot EN geen historiek-regel exact op/voor
de matchdatum (bv. omdat de historiek pas sinds kort wordt bijgehouden, zie
PADEL_ANALYSIS_PADELSTAT_HISTORY_2026-10-03 in firebase_service.py), dan
sprong de functie METEEN naar het officiële klassement - ook al was er
intussen gewoon een (recentere) padelstat-waarde gekend. FIX: een NIEUWE
tussenstap - _latest_rating_from_history() - geeft de MEEST RECENTE
padelstat-waarde uit de (al geladen) historiek-lijst terug, ongeacht of die
voor/na de matchdatum ligt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_FLAT_RATING_FALLBACK_2026-10-04 (op verzoek van Kim,
2e ronde, met screenshot: "op basis van welke waarden zegt dat onze
spelers geen padelstat waardes hebben?" - ondanks de fix hierboven bleef
dit voor bepaalde spelers optreden)
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd door firebase_service.save_padelstat_rating() na te
lezen: het "history"-veld wordt ENKEL gevuld/aangevuld OP HET MOMENT dat
save_padelstat_rating() voor een speler wordt AANGEROEPEN (dus bij een
refresh) - NIET met terugwerkende kracht voor spelers die sinds
PADEL_ANALYSIS_PADELSTAT_HISTORY_2026-10-03 nog niet opnieuw ververst
zijn. FIX: _load_padelstat_histories() geeft nu per speler een dict
{"history": [...], "flat_rating": rating_of_None, "flat_fetched_at": ...}
terug i.p.v. enkel een lijst - het vlakke "rating"-veld gaat NIET meer
verloren. Een nieuwe, gedeelde kernfunctie _padelstat_priority_rating()
doorloopt voor zowel eigen spelers als tegenstanders dezelfde 4 stappen:
  1. padelstat-historiek OP DATUM (exact, indien aanwezig);
  2. de meest recente padelstat-HISTORIEK-waarde (any datum);
  3. het vlakke, niet-gehistoriseerde "rating"-veld (NIEUW);
  4. de meegegeven terugval (eigen spelers: huidig officieel klassement;
     tegenstander: officieel klassement van het uitslagenblad van toen).
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_OPPONENT_PADELSTAT_2026-10-04 (op verzoek van Kim:
"bij tegenstanders zie ik ook 'officieel klassement van toen'. maar ik wil
padelstat klassement van toen (of huidig als je dat niet hebt). eigenlijk
moet de winstkans op dezelfde manier berekend worden dan bij de analyse")
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd: `_opponent_value_at()` probeerde NOOIT padelstat -
enkel snapshot -> padelstat-historiek-op-datum -> rechtstreeks het
officiële klassement van het uitslagenblad. FIX: _opponent_value_at()
gebruikt nu DEZELFDE _padelstat_priority_rating() als _own_value_at(), met
als ALLERLAATSTE terugval het officiële klassement van het uitslagenblad.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_SCALE_WIDGET_FIX_2026-10-04 (op verzoek van Kim, met
foutmelding: "StreamlitWidgetAlreadyInstantiatedError:
st.session_state['retro_scale'] cannot be modified after the widget with
that key is instantiated")
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd: de "Toepassen"-knop deed
`st.session_state["retro_scale"] = best["scale"]` NADAT de st.slider() met
key="retro_scale" al in DEZELFDE render geïnstantieerd was (de slider staat
hoger in de functie dan de knop) - Streamlit staat dat niet toe, ook al
volgt er meteen een st.rerun(): de controle gebeurt bij de toewijzing zelf,
niet pas bij de volgende render.
FIX: de knop gebruikt nu `on_click=_apply_best_scale_callback` met
`args=(best["scale"],)` i.p.v. een `if st.button(...): st.session_state[...] = ...`-
blok. Een on_click-callback draait VOOR de widgets van de volgende render
geïnstantieerd worden (dat is exact wat de officiële foutmelding zelf al
aanraadt), dus de toewijzing is daar wel toegelaten. Geen expliciete
st.rerun() meer nodig - Streamlit doet dat automatisch na een callback.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04 (op verzoek van Kim: "ik zie
enkel de matchen van mezelf. Ik wil ook die van mijn ploegmaten zien. Nog
meer data trouwens dat om te gebruiken. Dan kan je eindresultaat vergelijken
met voorspeld resultaat. Beste alternatief is altijd leeg" + de bijhorende
melding "we tonen bewust enkel matchen van Kim Verbeke [...] Een alternatief
vergt minstens 4 gekende eigen spelers van dezelfde dag")
--------------------------------------------------------------------------
ROOT CAUSE van "Beste alternatief altijd leeg": bevestigd, en inherent aan
de PADEL_ANALYSIS_RETRO_PLAYER_FILTER_2026-10-04-fix hierboven - die loste
de dames-matchen-bug terecht op door ENKEL het document van de GEKOZEN
speler op te halen, maar sloot daarmee ONBEDOELD ook de WEL gewenste
teamgenoten (dezelfde ontmoeting, andere koppels) uit. Met <4 gekende eigen
spelers per ontmoeting kan best_alternative_for_encounter() nooit een
alternatieve koppelverdeling berekenen (die heeft minstens 4 spelers nodig
om te herschikken) - en de kalibratie/"eindresultaat"-vraag hieronder heeft
om dezelfde reden nooit de VOLLEDIGE ontmoeting gekend.
FIX: `render_retrospective_tab()` bepaalt nu EERST, met een goedkope enkele
lookup van ENKEL `sel_player_id`, welke teamgenoten in diens matchen als
partner opduiken ("gedetecteerde ploegmaats"). Een multiselect ("Analyseer
ook de matchen van") laat Kim dat voorstel aanvullen/inperken - standaard
vooraf ingevuld met de gedetecteerde ploegmaats. Alle volgende stappen
(docs ophalen, encounter-index, padelstat-cache, ruwe data, kalibratie,
"beste alternatief") draaien op dat VOLLEDIGE, EXPLICIET gekozen peloton -
nooit meer impliciet "alle profielen", dus de dames-matchen-bug uit
PADEL_ANALYSIS_RETRO_PLAYER_FILTER_2026-10-04 kan niet terugkeren: een
match komt enkel binnen als minstens 1 van de EXPLICIET gekozen spelers
hem effectief speelde.
`build_retro_encounter_index()` heeft nu een `allowed_player_ids`-parameter
(een SET) i.p.v. het vroegere, enkelvoudige `sel_player_id` - met dezelfde
betekenis (None = geen filter, geef dit nooit mee vanuit de UI) maar nu
meerdere toegelaten spelers tegelijk. Een bord dat door 2 van de gekozen
teamgenoten gespeeld werd (elk vanuit hun eigen document) krijgt dankzij de
bestaande dedupe-sleutel (_board_dedupe_key(), gebaseerd op match_id/koppel,
niet op wie het document aanlevert) maar EENMAAL een plek in de index - geen
dubbele rijen.
Zodra zo een ontmoeting NU >=4 bekende eigen spelers heeft, werkt "Beste
alternatief" vanzelf (geen losse codewijziging nodig daar).
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_ENCOUNTER_OUTCOME_2026-10-04 (zelfde verzoek als
hierboven: "Dan kan je eindresultaat vergelijken met voorspeld resultaat")
--------------------------------------------------------------------------
NIEUW blok "Eindresultaat van de ontmoeting: voorspeld tegenover echt" -
enkel zinvol/getoond zodra ALLE boards van de gekozen ontmoeting gekend
zijn (typisch pas haalbaar met teamgenoten erbij, zie hierboven). Combineert
de per-bord voorspelde winkansen tot een voorspelde kans op 2/1/0
competitiepunten (_combine_boards_to_point_probs() - lokale, PURE kopie van
dezelfde combinatorische logica als lineup_rotation._match_outcome_point_
probabilities()/lineup_plan_screen._points(), BEWUST hier opnieuw
geschreven i.p.v. geïmporteerd - zie de uitleg bovenaan dit bestand over
waarom dit bestand zijn eigen, kleine kopieën van gedeelde rekenlogica
gebruikt i.p.v. afhankelijkheden op andere lineup_*-modules op te bouwen)
en vergelijkt dat met de ECHTE einduitslag (_actual_encounter_result() -
simpel telwerk op "won" per bord, enkel als ALLE boards een gekende
uitslag hebben). Is niet elk bord gekend, dan toont de sectie expliciet
hoeveel borden ontbreken i.p.v. een onvolledig of misleidend cijfer.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_ALT_REASON_2026-10-04 (gevonden tijdens het testen van
PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04 hierboven)
--------------------------------------------------------------------------
ROOT CAUSE: best_alternative_for_encounter() gaf in ALLE "niet gelukt"-
gevallen simpelweg None terug, en de UI toonde daarbij altijd dezelfde
tekst: "minder dan 4 spelers gekend". Dat klopte niet meer zodra er WEL
>=4 spelers gekend waren maar de optimalisatie zelf (ll.optimize_lineup_
vs_scenario) toch leeg teruggaf (bv. geen enkele combinatie binnen de
puntengrens) - de UI zou dan een AANTOONBAAR ONJUISTE oorzaak tonen.
FIX: de functie geeft nu ALTIJD een dict terug (nooit None) met een
"reason"-veld ("too_few_players" / "no_valid_combinations" / None bij
succes) en "n_players" - de UI toont per geval de juiste, specifieke
tekst i.p.v. 1 vaste aanname.
"""
import math
import re
from collections import defaultdict
from typing import Dict, List, Optional

import streamlit as st
import lineup_lab as ll
import firebase_service as fb

SNAPSHOT_COLLECTION = "lineup_snapshots"
_DEFAULT_SCALE = ll.DEFAULT_WIN_PROBABILITY_SCALE
_CALIBRATION_BIN_EDGES = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.0]
_SCALE_SEARCH_RANGE = list(range(50, 401, 5))  # PADEL_ANALYSIS_RETRO_AUTOSCALE_2026-10-04


# --------------------------------------------------------------- datums
def to_iso_date(date_text) -> Optional[str]:
    """TVL-datumtekst ("26/09/2026", "26-09-2026" of al ISO) -> "YYYY-MM-DD".
    Geeft None terug bij een onherkenbaar formaat (nooit een gok)."""
    if not date_text:
        return None
    s = str(date_text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


# ------------------------------------------------- encounter/board-reconstructie
# PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03: letterlijke kopie van de groepering/
# dedupe-logica in lineup_lab.py (_encounter_key/_board_dedupe_key/
# build_encounter_index/reconstruct_boards) - zie moduledocstring voor waarom
# dit NIET via die functies hergebruikt wordt (ze laten opp*_ranking vallen).
def _encounter_key(m: dict) -> tuple:
    return (m.get("match_date") or "", m.get("encounter") or "")


def _board_dedupe_key(m: dict, fallback_pid: str) -> str:
    mid = m.get("match_id")
    partner = m.get("partner_user_id")
    pair_key = "|".join(sorted([str(fallback_pid), str(partner)]))
    if mid:
        return f"mid:{mid}|pair:{pair_key}"
    return "fb:" + "|".join(str(x) for x in [
        m.get("match_date"), m.get("encounter"), m.get("round_text"),
        m.get("score"), pair_key,
    ])


def build_retro_encounter_index(docs: Dict[str, dict], allowed_player_ids=None) -> Dict[tuple, list]:
    """PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04: `allowed_player_ids` is nu
    een SET (meerdere toegelaten spelers) i.p.v. het vroegere enkelvoudige
    `sel_player_id` - zie moduledocstring. None = geen filter (nooit vanuit
    de UI meegeven - enkel ter beschikking voor eventueel ander gebruik)."""
    allowed = {str(p) for p in allowed_player_ids} if allowed_player_ids is not None else None
    index: Dict[tuple, list] = {}
    for pid, doc in docs.items():
        if allowed is not None and str(pid) not in allowed:
            continue
        for m in doc.get("matches", []) or []:
            if m.get("match_type") != "interclub":
                continue
            index.setdefault(_encounter_key(m), []).append((pid, m))
    return index


def list_retro_encounters(index: Dict[tuple, list]) -> List[tuple]:
    """Zelfde label-afleiding als ll.list_encounters(), meest recent eerst.
    Geeft (key, label, date) terug.
    PADEL_ANALYSIS_RETRO_SORT_FIX_2026-10-04 (op verzoek van Kim: "sortering
    van de matchen in de lijst moet volgens datum zijn. Nieuwste eerst."):
    ROOT CAUSE, bevestigd: de sortering gebruikte de RUWE datum-TEKST
    ("26/09/2026", dag-eerst) als sorteersleutel. Lexicografisch sorteren
    van dag-eerst-tekst geeft NIET de chronologische volgorde zodra de
    maand verschilt. FIX: sorteer op `to_iso_date(x[2])` (YYYY-MM-DD, wel
    correct lexicografisch sorteerbaar) i.p.v. de ruwe tekst."""
    items = []
    for key, entries in index.items():
        date, encounter = key
        reeks = None
        for _pid, m in entries:
            if m.get("reeks_name"):
                reeks = m.get("reeks_name")
                break
        label_parts = [p for p in [date, reeks, encounter] if p]
        label = " \u2014 ".join(label_parts) if label_parts else "Onbekende ontmoeting"
        items.append((key, label, date))
    items.sort(key=lambda x: to_iso_date(x[2]) or "", reverse=True)
    return [(k, lbl) for k, lbl, _ in items]


def reconstruct_boards_with_rankings(entries: list) -> List[dict]:
    """Zoals ll.reconstruct_boards(), maar behoudt ook opp1_ranking/
    opp2_ranking (tekst, bv. "P200") en match_date - nodig voor de
    retrospectieve voorspelling (zie moduledocstring).
    PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04: `entries` kan nu matchrecords
    van MEERDERE eigen spelers bevatten (1 ontmoeting, meerdere koppels) -
    de bestaande `_board_dedupe_key()` (gebaseerd op match_id/koppel, NIET
    op welk document het record aanlevert) zorgt dat elk bord nog steeds
    maar EENMAAL in de uitkomst verschijnt, ook als 2 teamgenoten hetzelfde
    bord elk vanuit hun eigen perspectief aanleveren."""
    seen = {}
    for pid, m in entries:
        key = _board_dedupe_key(m, pid)
        if key in seen:
            continue
        partner = m.get("partner_user_id")
        if not partner:
            continue
        seen[key] = {
            "pair": frozenset({str(pid), str(partner)}),
            "match_date": m.get("match_date"),
            "round_text": m.get("round_text"),
            "opp1_name": m.get("opp1_name"), "opp2_name": m.get("opp2_name"),
            "opp1_user_id": m.get("opp1_user_id"), "opp2_user_id": m.get("opp2_user_id"),
            "opp1_ranking": m.get("opp1_ranking"), "opp2_ranking": m.get("opp2_ranking"),
            "score": m.get("score"), "result": m.get("result"), "won": m.get("won"),
            "match_id": m.get("match_id"), "dedupe_key": key,
        }
    return list(seen.values())


# --------------------------------------------------------------- teamgenoten
def _detect_teammates(docs: Dict[str, dict], sel_player_id: str) -> set:
    """PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04 - zie moduledocstring: alle
    speler-id's die ooit als `partner_user_id` optraden in een interclub-
    match van `sel_player_id` - dit is het voorstel dat de multiselect
    standaard vooraf invult."""
    teammates = set()
    doc = docs.get(str(sel_player_id)) or {}
    for m in doc.get("matches", []) or []:
        if m.get("match_type") != "interclub":
            continue
        if m.get("partner_user_id"):
            teammates.add(str(m["partner_user_id"]))
    return teammates


# --------------------------------------------------------------- momentopnames
def _find_snapshot_for(date_text, opp_user_ids: set) -> Optional[dict]:
    """PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03: zoekt een momentopname
    (lineup_plan_screen.py) die bij deze datum en minstens 1 van deze
    tegenstander-id's hoort. Faalt altijd stil (None)."""
    iso = to_iso_date(date_text)
    if not iso:
        return None
    try:
        docs = fb.db.collection(SNAPSHOT_COLLECTION).limit(500).stream()
    except Exception:  # noqa: BLE001
        return None
    for doc in docs:
        data = doc.to_dict() or {}
        if to_iso_date(data.get("match_date")) != iso:
            continue
        opp_players = data.get("opponent_players") or {}
        if opp_user_ids and not (set(opp_players.keys()) & {str(u) for u in opp_user_ids if u}):
            continue
        return data
    return None


# --------------------------------------------------------------- padelstat-cache
def _collect_relevant_player_ids(index: dict) -> set:
    """PADEL_ANALYSIS_RETRO_PERF_2026-10-04: alle speler-id's (eigen +
    tegenstander) die ooit voorkomen in de meegegeven encounter-index -
    gebruikt om hun padelstat-historiek in EEN batch voor te laden (i.p.v.
    per bord/per match apart, zie moduledocstring)."""
    ids = set()
    for entries in index.values():
        for pid, m in entries:
            ids.add(str(pid))
            for veld in ("partner_user_id", "opp1_user_id", "opp2_user_id"):
                if m.get(veld):
                    ids.add(str(m[veld]))
    return ids


@st.cache_data(ttl=300, show_spinner=False)
def _load_padelstat_histories(player_ids: tuple) -> Dict[str, dict]:
    """PADEL_ANALYSIS_RETRO_PERF_2026-10-04 - zie moduledocstring: EEN
    fb.get_padelstat_rating()-aanroep per UNIEKE speler, 5 minuten gecached.
    Faalt een individuele speler, dan krijgt die gewoon een lege cache-entry
    (nooit de hele batch laten crashen).
    PADEL_ANALYSIS_RETRO_FLAT_RATING_FALLBACK_2026-10-04: geeft nu per
    speler een dict {"history": [...], "flat_rating", "flat_fetched_at"}
    terug i.p.v. enkel de "history"-lijst - zie moduledocstring voor
    waarom het vlakke "rating"-veld (spelers nog niet ge-migreerd naar
    de historiek) anders stil verloren ging."""
    out: Dict[str, dict] = {}
    for pid in player_ids:
        try:
            data = fb.get_padelstat_rating(pid) or {}
        except Exception:  # noqa: BLE001
            data = {}
        out[pid] = {
            "history": list(data.get("history") or []),
            "flat_rating": data.get("rating"),
            "flat_fetched_at": data.get("fetched_at"),
        }
    return out


def _rating_at_from_history(history: list, moment_iso: str) -> Optional[float]:
    """PADEL_ANALYSIS_RETRO_PERF_2026-10-04: PURE (geen I/O) kopie van
    firebase_service.get_padelstat_rating_at()'s logica, werkend op een AL
    ingeladen historiek-lijst - zie moduledocstring."""
    beste = None
    for regel in history:
        t = str(regel.get("fetched_at") or "")
        if t and t[:len(moment_iso)] <= moment_iso and (beste is None or t >= beste[0]):
            beste = (t, regel.get("rating"))
    return beste[1] if beste else None


def _latest_rating_from_history(history: list) -> Optional[float]:
    """PADEL_ANALYSIS_RETRO_PADELSTAT_PRIORITY_2026-10-04 - zie
    moduledocstring. De MEEST RECENTE padelstat-waarde in een historiek-
    lijst, ongeacht een datum-cutoff - gebruikt als terugval zodra er geen
    historiek-regel exact op/voor de matchdatum bestaat, maar er WEL ooit
    een padelstat-waarde gekend was (bv. pas sinds recent bijgehouden)."""
    if not history:
        return None
    beste = max(history, key=lambda r: str(r.get("fetched_at") or ""))
    rating = beste.get("rating")
    return float(rating) if rating is not None else None


def _padelstat_priority_rating(
    pid, date_text, ratings_cache: Dict[str, dict], fallback_value, fallback_label: str,
):
    """PADEL_ANALYSIS_RETRO_FLAT_RATING_FALLBACK_2026-10-04 /
    PADEL_ANALYSIS_RETRO_OPPONENT_PADELSTAT_2026-10-04 - zie moduledocstring.
    GEDEELDE prioriteitsketen, gebruikt door ZOWEL eigen spelers ALS
    tegenstanders (symmetrisch, net als de hoofdanalyse):
      1. padelstat-historiek OP DATUM (exact);
      2. meest recente padelstat-HISTORIEK-waarde (any datum - "huidig");
      3. het vlakke, niet-gehistoriseerde "rating"-veld (speler nog niet
         ge-migreerd naar de historiek-structuur);
      4. `fallback_value`/`fallback_label` - voor eigen spelers het huidige
         officiele klassement, voor tegenstanders het officiele klassement
         van het uitslagenblad van toen.
    Geeft (waarde, bron) terug; waarde is None als ECHT niets gekend is."""
    cache_entry = ratings_cache.get(str(pid)) or {}
    history = cache_entry.get("history") or []
    iso = to_iso_date(date_text)
    if iso:
        hist = _rating_at_from_history(history, iso)
        if hist is not None:
            return float(hist), "padelstat-historiek (op datum)"
    latest = _latest_rating_from_history(history)
    if latest is not None:
        return latest, "meest recente padelstat-historiek (geen regel exact op die datum - benadering)"
    flat = cache_entry.get("flat_rating")
    if flat is not None:
        return float(flat), "padelstat (nog geen historiek bijgehouden voor deze speler - huidige waarde)"
    if fallback_value is not None:
        return float(fallback_value), fallback_label
    return None, "onbekend"


# --------------------------------------------------------------- voorspelling
def _own_value_at(player_id, date_text, current_official_ranks: dict, snapshot_own: dict,
                  ratings_cache: Dict[str, dict]):
    """Effectieve rating van EEN eigen speler op `date_text` - zie
    moduledocstring voor de volgorde van bronnen. Geeft (waarde, bron) terug;
    waarde is None als er niets gekend is. GEEN Firestore-aanroep meer (zie
    PADEL_ANALYSIS_RETRO_PERF_2026-10-04) - `ratings_cache` is al voor de
    hele sessie opgehaald."""
    pid = str(player_id)
    if snapshot_own and pid in snapshot_own:
        v = snapshot_own[pid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    fallback = (current_official_ranks or {}).get(pid)
    return _padelstat_priority_rating(
        pid, date_text, ratings_cache, fallback,
        "huidig officieel klassement (laatste redmiddel, geen padelstat gekend)",
    )


def _opponent_value_at(user_id, ranking_text, date_text, snapshot_opp: dict,
                       ratings_cache: Dict[str, dict]):
    """Effectieve rating van EEN tegenstander-speler op `date_text`. GEEN
    Firestore-aanroep meer - zie _own_value_at().
    PADEL_ANALYSIS_RETRO_OPPONENT_PADELSTAT_2026-10-04: gebruikt nu DEZELFDE
    gedeelde _padelstat_priority_rating() als eigen spelers - zie
    moduledocstring."""
    uid = str(user_id) if user_id else None
    if snapshot_opp and uid and uid in snapshot_opp:
        v = snapshot_opp[uid]
        if v.get("padelstat") is not None:
            return float(v["padelstat"]), "momentopname (padelstat)"
        if v.get("official_rank") is not None:
            return float(v["official_rank"]), "momentopname (klassement)"
    if not uid:
        official = ll.parse_ranking(ranking_text)
        return (float(official), "officieel klassement (van toen, uit het uitslagenblad)") if official is not None else (None, "onbekend")
    official = ll.parse_ranking(ranking_text)
    return _padelstat_priority_rating(
        uid, date_text, ratings_cache, official,
        "officieel klassement (van toen, uit het uitslagenblad - laatste redmiddel, geen padelstat gekend)",
    )


def predict_board(
    board: dict, current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, snapshot: Optional[dict] = None,
) -> dict:
    """Herberekent de winkans voor EEN bord, met de waarden van toen."""
    date_text = board.get("match_date")
    p1, p2 = tuple(board["pair"])
    snap_own = (snapshot or {}).get("own_players") or {}
    snap_opp = (snapshot or {}).get("opponent_players") or {}
    our_vals = [_own_value_at(p, date_text, current_official_ranks, snap_own, ratings_cache) for p in (p1, p2)]
    their_vals = [
        _opponent_value_at(board.get("opp1_user_id"), board.get("opp1_ranking"), date_text, snap_opp, ratings_cache),
        _opponent_value_at(board.get("opp2_user_id"), board.get("opp2_ranking"), date_text, snap_opp, ratings_cache),
    ]
    our_known = [v for v, _ in our_vals if v is not None]
    their_known = [v for v, _ in their_vals if v is not None]
    our_avg = sum(our_known) / len(our_known) if our_known else None
    their_avg = sum(their_known) / len(their_known) if their_known else None
    wp = ll.estimate_win_probability(our_avg, their_avg, scale=scale)
    return {
        "pair": (p1, p2), "our_avg": our_avg, "their_avg": their_avg,
        "win_probability": wp, "risk_note": ll.risk_note_for_probability(wp),
        "our_sources": [s for _, s in our_vals], "their_sources": [s for _, s in their_vals],
        "actual_won": board.get("won"), "score": board.get("score"),
        "opp1_name": board.get("opp1_name"), "opp2_name": board.get("opp2_name"),
        "match_date": date_text,
    }


def predict_encounter(
    boards: list, current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, use_snapshot: bool = True,
) -> dict:
    """Voorspelt alle borden van 1 ontmoeting. Zoekt (indien gevraagd) 1x een
    momentopname voor de hele ontmoeting (alle borden delen dezelfde datum/
    tegenstander)."""
    snapshot = None
    if use_snapshot and boards:
        opp_ids = {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards}
        snapshot = _find_snapshot_for(boards[0].get("match_date"), opp_ids)
    predictions = [predict_board(b, current_official_ranks, ratings_cache, scale=scale, snapshot=snapshot) for b in boards]
    return {"boards": predictions, "snapshot_used": snapshot is not None}


# ------------------------------------------- volledige-ontmoeting-uitkomst
def _combine_boards_to_point_probs(win_probs: list) -> dict:
    """PADEL_ANALYSIS_RETRO_ENCOUNTER_OUTCOME_2026-10-04 - zie moduledocstring.
    PURE, lokale kopie van dezelfde combinatorische logica als lineup_
    rotation._match_outcome_point_probabilities()/lineup_plan_screen._points() -
    bewust hier opnieuw geschreven i.p.v. geïmporteerd (zie bovenaan dit
    bestand: geen afhankelijkheden op andere lineup_*-modules). `win_probs`
    mag None bevatten (onbekende winkans) - die telt als 50/50."""
    probs = [(0.5 if p is None else max(0.0, min(1.0, float(p)))) for p in win_probs]
    n = len(probs)
    if n == 0:
        return {"p2": 0.0, "p1": 0.0, "p0": 0.0}
    tot = {0: 1.0}
    for p in probs:
        nieuw = {}
        for k, pk in tot.items():
            nieuw[k] = nieuw.get(k, 0.0) + pk * (1.0 - p)
            nieuw[k + 1] = nieuw.get(k + 1, 0.0) + pk * p
        tot = nieuw
    half = n / 2.0
    p2 = sum(p for k, p in tot.items() if k > half)
    p1 = sum(p for k, p in tot.items() if k == half)
    p0 = max(0.0, 1.0 - p2 - p1)
    return {"p2": p2, "p1": p1, "p0": p0}


def _actual_encounter_result(boards: list) -> Optional[dict]:
    """PADEL_ANALYSIS_RETRO_ENCOUNTER_OUTCOME_2026-10-04: telt de echte
    uitslag van een VOLLEDIGE ontmoeting (alle boards). Geeft None terug als
    niet ELK bord een gekende "won"-waarde heeft - toon dan liever niets dan
    een onvolledig/misleidend cijfer."""
    if not boards:
        return None
    gewonnen = [b.get("won") for b in boards]
    if any(w is None for w in gewonnen):
        return None
    n_win = sum(1 for w in gewonnen if w)
    half = len(boards) / 2.0
    if n_win > half:
        uitkomst = "gewonnen"
    elif n_win == half:
        uitkomst = "gelijk"
    else:
        uitkomst = "verloren"
    return {"n_win": n_win, "n_boards": len(boards), "uitkomst": uitkomst}


# ------------------------------------------------ schaal-onafhankelijke ruwe data
def gather_raw_match_data(index: dict, current_official_ranks: dict, ratings_cache: Dict[str, dict]) -> list:
    """PADEL_ANALYSIS_RETRO_PERF_2026-10-04 - zie moduledocstring. Verzamelt
    voor ELK bord van ELKE ontmoeting in `index` de SCHAAL-ONAFHANKELIJKE
    ruwe data (our_avg/their_avg/actual_won) - dit is de enige stap die nog
    (gecachete) opzoekingen doet; de eigenlijke winkans voor een willekeurige
    factor is daarna een zuivere berekening via score_raw_at_scale()."""
    raw = []
    for entries in index.values():
        boards = reconstruct_boards_with_rankings(entries)
        if not boards:
            continue
        opp_ids = {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards}
        snapshot = _find_snapshot_for(boards[0].get("match_date"), opp_ids)
        snap_own = (snapshot or {}).get("own_players") or {}
        snap_opp = (snapshot or {}).get("opponent_players") or {}
        for board in boards:
            p1, p2 = tuple(board["pair"])
            date_text = board.get("match_date")
            our_vals = [_own_value_at(p, date_text, current_official_ranks, snap_own, ratings_cache) for p in (p1, p2)]
            their_vals = [
                _opponent_value_at(board.get("opp1_user_id"), board.get("opp1_ranking"), date_text, snap_opp, ratings_cache),
                _opponent_value_at(board.get("opp2_user_id"), board.get("opp2_ranking"), date_text, snap_opp, ratings_cache),
            ]
            our_known = [v for v, _ in our_vals if v is not None]
            their_known = [v for v, _ in their_vals if v is not None]
            raw.append({
                "pair": (p1, p2),
                "our_avg": (sum(our_known) / len(our_known)) if our_known else None,
                "their_avg": (sum(their_known) / len(their_known)) if their_known else None,
                "actual_won": board.get("won"), "score": board.get("score"),
                "opp1_name": board.get("opp1_name"), "opp2_name": board.get("opp2_name"),
                "match_date": date_text,
            })
    return raw


def score_raw_at_scale(raw_rows: list, scale: float) -> list:
    """Vult elke rij uit gather_raw_match_data() aan met win_probability
    voor EEN specifieke winkansfactor - pure berekening, geen I/O."""
    out = []
    for r in raw_rows:
        wp = ll.estimate_win_probability(r["our_avg"], r["their_avg"], scale=scale)
        out.append({**r, "win_probability": wp})
    return out


# --------------------------------------------------------------- kalibratie
def calibration_stats(predictions: list, bin_edges=None) -> Optional[dict]:
    """Brier-score, log loss, accuraatheid en per-kansklasse voorspeld vs.
    werkelijk - exact dezelfde methodologie als de eerdere, handmatige
    validatie die tot scale=207 leidde (zie lineup_lab.py)."""
    bin_edges = bin_edges or _CALIBRATION_BIN_EDGES
    usable = [p for p in predictions if p.get("win_probability") is not None and p.get("actual_won") is not None]
    n = len(usable)
    if n == 0:
        return None
    brier = sum((p["win_probability"] - (1.0 if p["actual_won"] else 0.0)) ** 2 for p in usable) / n
    eps = 1e-9
    log_loss = -sum(
        (1.0 if p["actual_won"] else 0.0) * math.log(max(p["win_probability"], eps))
        + (0.0 if p["actual_won"] else 1.0) * math.log(max(1.0 - p["win_probability"], eps))
        for p in usable
    ) / n
    accuracy = sum(1 for p in usable if (p["win_probability"] >= 0.5) == bool(p["actual_won"])) / n
    mean_pred = sum(p["win_probability"] for p in usable) / n
    mean_actual = sum(1.0 if p["actual_won"] else 0.0 for p in usable) / n
    bins = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        grp = [p for p in usable if lo <= p["win_probability"] < hi or (hi == 1.0 and p["win_probability"] == 1.0)]
        if grp:
            bins.append({
                "bereik": f"{lo * 100:.0f}-{hi * 100:.0f}%", "n": len(grp),
                "gem_voorspeld": sum(x["win_probability"] for x in grp) / len(grp) * 100,
                "werkelijk": sum(1 for x in grp if x["actual_won"]) / len(grp) * 100,
            })
    return {
        "n": n, "brier": brier, "log_loss": log_loss, "accuracy": accuracy,
        "mean_predicted": mean_pred, "mean_actual": mean_actual, "bins": bins,
    }


def find_best_scale(raw_rows: list, scale_range=None) -> dict:
    """PADEL_ANALYSIS_RETRO_AUTOSCALE_2026-10-04 - zie moduledocstring.
    Berekent de Brier-score voor elke kandidaat-factor in `scale_range`,
    PUUR in-memory (geen Firestore) - geeft {"best": {"scale", "brier"},
    "curve": [{"scale", "brier", "n"}, ...]} terug. "best" is None als er
    nergens genoeg data is om een Brier-score te berekenen."""
    scale_range = scale_range or _SCALE_SEARCH_RANGE
    curve = []
    best = None
    for s in scale_range:
        stats = calibration_stats(score_raw_at_scale(raw_rows, s))
        if stats is None:
            continue
        curve.append({"scale": s, "brier": stats["brier"], "n": stats["n"]})
        if best is None or stats["brier"] < best["brier"]:
            best = {"scale": s, "brier": stats["brier"]}
    return {"best": best, "curve": curve}


def logistic_curve(scale: float, diffs=None) -> list:
    """(diff, kans)-punten voor de visualisatie van de winkans-curve bij een
    gekozen `scale`."""
    diffs = diffs if diffs is not None else list(range(-400, 401, 10))
    return [(d, ll.estimate_win_probability(0.0, -float(d), scale=scale)) for d in diffs]


# --------------------------------------------------------------- beste alternatief
def best_alternative_for_encounter(
    boards: list, docs: Dict[str, dict], current_official_ranks: dict, ratings_cache: Dict[str, dict],
    scale: float = _DEFAULT_SCALE, top_n: int = 3,
) -> Optional[dict]:
    """Zoekt, MET de waarden van toen en ZONDER deze ontmoeting zelf in de
    synergie te laten meetellen (exclude_match_keys - geen lekkage van de
    uitkomst in de eigen voorspelling), de beste alternatieve koppelverdeling
    voor deze ontmoeting. Geeft altijd een dict terug (nooit None) met een
    "reason"-veld (None = gelukt; "too_few_players"; "no_valid_combinations")
    zodat de UI de ECHTE oorzaak kan tonen i.p.v. 1 generieke, soms
    misleidende melding - zie PADEL_ANALYSIS_RETRO_ALT_REASON_2026-10-04."""
    if not boards:
        return {"top": [], "actual": None, "reason": "too_few_players", "n_players": 0}
    players = sorted({str(p) for b in boards for p in b["pair"]})
    if len(players) < 4:
        return {"top": [], "actual": None, "reason": "too_few_players", "n_players": len(players)}
    required = ll.required_counts_from_boards(boards)
    exclude_keys = {b["dedupe_key"] for b in boards}
    synergy = ll.compute_pairwise_synergy(docs, players, exclude_match_keys=exclude_keys)
    synergy_fn = ll.make_pair_score_fn(synergy, docs)
    date_text = boards[0].get("match_date")
    snapshot = _find_snapshot_for(date_text, {b.get("opp1_user_id") for b in boards} | {b.get("opp2_user_id") for b in boards})
    snap_own = (snapshot or {}).get("own_players") or {}
    snap_opp = (snapshot or {}).get("opponent_players") or {}
    player_ratings = {}
    for pid in players:
        val, _ = _own_value_at(pid, date_text, current_official_ranks, snap_own, ratings_cache)
        if val is not None:
            player_ratings[pid] = val
    opponent_boards = []
    opponent_ratings = {}
    for b in boards:
        pair_info = []
        for idx, uid_key, ranking_key in ((0, "opp1_user_id", "opp1_ranking"), (1, "opp2_user_id", "opp2_ranking")):
            uid = b.get(uid_key)
            val, _ = _opponent_value_at(uid, b.get(ranking_key), date_text, snap_opp, ratings_cache)
            if uid and val is not None:
                opponent_ratings[str(uid)] = val
            pair_info.append({
                "user_id": uid, "name": b.get("opp1_name") if idx == 0 else b.get("opp2_name"),
                "ranking": b.get(ranking_key),
            })
        opponent_boards.append({"opponent_pair": pair_info})
    results, _truncated, _diag = ll.optimize_lineup_vs_scenario(
        players, required, synergy_fn, opponent_boards, player_ratings,
        player_official_ranks=current_official_ranks, opponent_ratings=opponent_ratings,
        top_n=top_n, win_probability_scale=scale,
    )
    if not results:
        return {"top": [], "actual": None, "reason": "no_valid_combinations", "n_players": len(players)}
    actual_key = tuple(sorted(tuple(sorted(b["pair"])) for b in boards))
    actual_result = next(
        (r for r in results if tuple(sorted(tuple(sorted(a["our_pair"])) for a in r["assignment"])) == actual_key),
        None,
    )
    return {"top": results, "actual": actual_result, "reason": None, "n_players": len(players)}


# --------------------------------------------------------------------------
# Streamlit-weergave
# --------------------------------------------------------------------------
def _pct(v) -> str:
    return f"{v * 100:.0f}%" if v is not None else "onbekend"


def _outcome_color(predicted_wp, actual_won) -> str:
    if predicted_wp is None or actual_won is None:
        return "gray"
    correct = (predicted_wp >= 0.5) == bool(actual_won)
    return "green" if correct else "red"


def _render_board_row(bp: dict, name_lookup: dict) -> None:
    p1, p2 = bp["pair"]
    ons = f"{name_lookup.get(p1, p1)} / {name_lookup.get(p2, p2)}"
    hen = f"{bp.get('opp1_name', '?')} / {bp.get('opp2_name', '?')}"
    kleur = _outcome_color(bp["win_probability"], bp["actual_won"])
    uitslag = "gewonnen" if bp["actual_won"] is True else ("verloren" if bp["actual_won"] is False else "onbekend")
    st.markdown(
        f"**{ons}** tegen **{hen}** ({bp.get('score') or '?'}) - "
        f"voorspeld :{kleur}[**{_pct(bp['win_probability'])}**] ({bp['risk_note']}), "
        f"echt **{uitslag}**"
    )
    with st.expander("Op basis van welke waarden?", expanded=False):
        st.caption(
            (f"Onze spelers: {bp['our_sources'][0]}, {bp['our_sources'][1]} "
             f"(gemiddeld {bp['our_avg']:.0f})") if bp.get("our_avg") is not None else "Onze spelers: onbekend"
        )
        st.caption(
            (f"Tegenstander: {bp['their_sources'][0]}, {bp['their_sources'][1]} "
             f"(gemiddeld {bp['their_avg']:.0f})") if bp.get("their_avg") is not None else "Tegenstander: onbekend"
        )


def _apply_best_scale_callback(new_scale: float) -> None:
    """PADEL_ANALYSIS_RETRO_SCALE_WIDGET_FIX_2026-10-04 - zie moduledocstring:
    MOET via on_click (draait voor de volgende render de slider-widget
    opnieuw instantieert), niet rechtstreeks na een if-st.button()-blok."""
    st.session_state["retro_scale"] = new_scale
    st.session_state.pop("retro_best_scale_result", None)


def render_retrospective_tab(profiles: list, sel_player_id) -> None:
    """PADEL_ANALYSIS_RETROSPECTIVE_2026-10-03 - zie moduledocstring. Enkel
    deze functie heeft Streamlit nodig; de rest van dit bestand is daar
    volledig los van (ook los testbaar).
    PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04: toont nu standaard ook de
    matchen van gedetecteerde teamgenoten (aanpasbaar via multiselect) -
    zie moduledocstring voor waarom dit de "Beste alternatief altijd
    leeg"-klacht oplost en meer kalibratiedata oplevert."""
    st.markdown('<div class="section-header">Nabeschouwing</div>', unsafe_allow_html=True)
    sel_player_id = str(sel_player_id)
    name_lookup = {str(p.get("player_id")): (p.get("display_name") or str(p.get("player_id"))) for p in profiles}
    sel_naam = name_lookup.get(sel_player_id, sel_player_id)

    # PADEL_ANALYSIS_RETRO_TEAMMATES_2026-10-04: eerst een goedkope lookup van
    # ENKEL sel_player_id om teamgenoten te detecteren (voorstel voor de
    # multiselect hieronder) - zie moduledocstring.
    with st.spinner(f"Matchen van {sel_naam} ophalen..."):
        sel_docs = ll.get_docs_for_players([sel_player_id])
    teammates = _detect_teammates(sel_docs, sel_player_id)
    teammate_options = [p for p in profiles if str(p.get("player_id")) in teammates]
    other_options = [p for p in profiles if str(p.get("player_id")) not in teammates
                     and str(p.get("player_id")) != sel_player_id]
    option_labels = [sel_naam] + [name_lookup.get(str(p.get("player_id")), "?") for p in teammate_options + other_options]
    label_to_id = {sel_naam: sel_player_id}
    label_to_id.update({name_lookup.get(str(p.get("player_id")), "?"): str(p.get("player_id")) for p in teammate_options})
    label_to_id.update({name_lookup.get(str(p.get("player_id")), "?"): str(p.get("player_id")) for p in other_options})
    default_labels = [sel_naam] + [name_lookup.get(str(p.get("player_id")), "?") for p in teammate_options]

    st.caption(
        f"Vergelijkt de voorspelde winkans met de echte uitslag van eerder gespeelde interclub-matchen, MET "
        "de padelstat-/klassementwaarden van TOEN (niet de huidige) waar bekend. Gebruik dit om te "
        "controleren of de winkans-formule klopt, en wat het betere alternatief geweest zou zijn."
    )
    gekozen_labels = st.multiselect(
        "Analyseer ook de matchen van",
        option_labels, default=default_labels, key=f"retro_teammates_{sel_player_id}",
        help=f"{sel_naam} staat er altijd bij. Standaard vooraf ingevuld met de teamgenoten waarmee "
             f"{sel_naam} al samenspeelde - voeg er gerust meer toe, of laat enkele weg. Meer spelers "
             "samen geven een vollediger beeld per ontmoeting (en maken 'Beste alternatief' en het "
             "eindresultaat hieronder vaker berekenbaar), maar dames- en herenmatchen blijven gescheiden: "
             "een match komt enkel mee als een van de hier gekozen spelers hem ECHT speelde.",
    )
    gekozen_ids = {label_to_id[lbl] for lbl in gekozen_labels if lbl in label_to_id} | {sel_player_id}

    if gekozen_ids == {sel_player_id}:
        docs = sel_docs
    else:
        with st.spinner("Matchen van de gekozen spelers ophalen..."):
            docs = ll.get_docs_for_players(sorted(gekozen_ids))

    index = build_retro_encounter_index(docs, allowed_player_ids=gekozen_ids)
    encounters = list_retro_encounters(index)
    if not encounters:
        st.info(f"Nog geen gespeelde interclub-ontmoetingen gevonden voor {sel_naam}.")
        return

    # Klassement-terugval ook voor alle gekozen spelers EN hun partners (niet enkel
    # sel_player_id zelf) - anders toont "Op basis van welke waarden?" onnodig "onbekend".
    own_side_ids = set(gekozen_ids)
    for entries in index.values():
        for _pid, m in entries:
            if m.get("partner_user_id"):
                own_side_ids.add(str(m["partner_user_id"]))
    current_official_ranks = {}
    try:
        from lineup_scout import _build_own_official_ranks_strict
        current_official_ranks = _build_own_official_ranks_strict(sorted(own_side_ids)) or {}
    except Exception:  # noqa: BLE001
        pass

    # PADEL_ANALYSIS_RETRO_PERF_2026-10-04: EEN batch-read per unieke speler,
    # 5 minuten gecached - geen Firestore-reads meer per bord/match hierna.
    player_ids = tuple(sorted(_collect_relevant_player_ids(index)))
    ratings_cache = _load_padelstat_histories(player_ids)

    # Schaal-ONAFHANKELIJKE ruwe data - 1x verzameld per sessie (hergebruikt bij
    # schuifregelaar-bewegingen en de "beste factor zoeken"-knop hieronder).
    raw_sig = (tuple(sorted(gekozen_ids)), player_ids)
    raw_key = f"retro_raw_{sel_player_id}"
    if st.session_state.get(raw_key + "_sig") != raw_sig:
        st.session_state[raw_key] = gather_raw_match_data(index, current_official_ranks, ratings_cache)
        st.session_state[raw_key + "_sig"] = raw_sig
    raw_rows = st.session_state[raw_key]

    labels = [lbl for _k, lbl in encounters]
    key_by_label = {lbl: k for k, lbl in encounters}
    gekozen_label = st.selectbox(
        "Kies een eerder gespeelde ontmoeting", labels, key="retro_pick_encounter",
    )
    gekozen_key = key_by_label[gekozen_label]
    boards = reconstruct_boards_with_rankings(index[gekozen_key])
    scale = st.session_state.get("retro_scale", _DEFAULT_SCALE)
    pred = predict_encounter(boards, current_official_ranks, ratings_cache, scale=scale)
    if pred["snapshot_used"]:
        st.success("Een eerdere momentopname van deze ontmoeting werd gevonden - de waarden van toen zijn exact.")
    st.markdown("#### Per match: voorspeld tegenover echt")
    for bp in pred["boards"]:
        _render_board_row(bp, name_lookup)

    # PADEL_ANALYSIS_RETRO_ENCOUNTER_OUTCOME_2026-10-04 - zie moduledocstring.
    st.divider()
    st.markdown("#### Eindresultaat van de ontmoeting: voorspeld tegenover echt")
    n_known_boards = len(boards)
    # PADEL_ANALYSIS_RETRO_ENCOUNTER_OUTCOME_2026-10-04: GEEN vast minimum (najaar heeft 4 borden,
    # voorjaar 6) - dat zou bij het andere formaat altijd ten onrechte "te weinig" tonen. Matchen
    # gebeuren wel altijd per 2 tegelijk (1 rotatie), dus een ONEVEN aantal is wel een hard signaal
    # van onvolledigheid.
    if n_known_boards < 2 or n_known_boards % 2 != 0:
        st.caption(
            f"We kennen {n_known_boards} van de borden van deze ontmoeting - te weinig (of een oneven "
            "aantal, wat altijd op een ontbrekend bord wijst) voor een betrouwbaar eindresultaat. Voeg "
            "hierboven bij 'Analyseer ook de matchen van' meer teamgenoten van die dag toe."
        )
    else:
        encounter_pp = _combine_boards_to_point_probs([bp["win_probability"] for bp in pred["boards"]])
        st.caption(
            f"Gebaseerd op {n_known_boards} gekende borden van deze ontmoeting - mogelijk een deel als "
            "niet alle teamgenoten van die dag hierboven geselecteerd zijn."
        )
        st.markdown(
            f"Voorspeld (op basis van {n_known_boards} gekende borden): "
            f":green[**{encounter_pp['p2'] * 100:.0f}% winst**] \u00b7 "
            f":orange[**{encounter_pp['p1'] * 100:.0f}% gelijk**] \u00b7 "
            f":red[**{encounter_pp['p0'] * 100:.0f}% verlies**]"
        )
        actual = _actual_encounter_result(boards)
        if actual is None:
            st.caption("De echte uitslag van 1 of meer van deze borden is niet gekend - geen vergelijking mogelijk.")
        else:
            st.markdown(
                f"Echt: **{actual['uitkomst']}** ({actual['n_win']} van {actual['n_boards']} borden gewonnen)."
            )

    st.divider()
    st.markdown("#### Beste alternatief (achteraf, met dezelfde waarden van toen)")
    with st.spinner("Alternatieven doorrekenen..."):
        alt = best_alternative_for_encounter(boards, docs, current_official_ranks, ratings_cache, scale=scale)
    if alt.get("reason") == "too_few_players":
        st.caption(
            f"Onvoldoende eigen spelers gekend voor deze ontmoeting ({alt.get('n_players', 0)} van de nodige "
            "4) - voeg hierboven bij 'Analyseer ook de matchen van' meer teamgenoten van die dag toe."
        )
    elif alt.get("reason") == "no_valid_combinations":
        st.caption(
            f"{alt.get('n_players', 0)} eigen spelers gekend, maar geen enkele reglementair geldige "
            "alternatieve koppelverdeling gevonden voor deze combinatie (bv. door de puntengrens)."
        )
    elif not alt.get("top"):
        st.caption("Geen alternatieven gevonden voor deze ontmoeting.")
    else:
        actual_ebw = alt["actual"]["expected_boards_won"] if alt["actual"] else None
        for rank, r in enumerate(alt["top"], start=1):
            pairs_txt = " \u00b7 ".join(
                f"{name_lookup.get(a['our_pair'][0], a['our_pair'][0])} / {name_lookup.get(a['our_pair'][1], a['our_pair'][1])}"
                for a in r["assignment"]
            )
            is_actual = alt["actual"] is not None and r is alt["actual"]
            label = " (zoals echt gespeeld)" if is_actual else ""
            st.write(f"**#{rank} - verwacht {r['expected_boards_won']:.2f} gewonnen matchen**{label}: {pairs_txt}")
        if actual_ebw is not None and alt["top"] and alt["top"][0]["expected_boards_won"] - actual_ebw >= 0.1:
            st.caption(
                f"Het beste alternatief lag {alt['top'][0]['expected_boards_won'] - actual_ebw:.2f} hoger "
                "dan de effectief gespeelde opstelling (verwachte gewonnen matchen)."
            )
        elif alt["actual"] is not None:
            st.caption("De effectief gespeelde opstelling was (zo goed als) de beste mogelijke keuze.")

    st.divider()
    namen_tekst = " / ".join(name_lookup.get(pid, pid) for pid in sorted(gekozen_ids))
    st.markdown(f"#### Kalibratie over alle gespeelde matchen van {namen_tekst}")
    st.caption(
        f"Hoe vaak klopte een voorspelling van bv. '60% winkans' ook echt? Gebruikt ALLE **{len(raw_rows)}** "
        f"interclub-matchen van de hierboven gekozen spelers die we kennen (niet enkel de bovenstaande "
        "ontmoeting). De Brier-score (lager is beter, 0 = perfect, 0.25 = niet beter dan een muntstuk) en de "
        "kans-klassen hieronder herberekenen INSTANT bij een andere factor - er gebeurt hierna geen enkele "
        "nieuwe Firestore-opvraging meer."
    )
    c_slider, c_curve = st.columns([2, 1])
    with c_slider:
        scale = st.slider(
            "Winkansfactor (hoe gevoelig de winkans reageert op het ratingverschil)",
            min_value=50, max_value=400, value=int(scale), step=5, key="retro_scale",
            help=f"Huidige app-standaard: {_DEFAULT_SCALE:.0f}. Een KLEINERE factor maakt elk ratingverschil "
                 "impactvoller (steilere curve); een GROTERE factor maakt de winkans voorzichtiger "
                 "(vlakkere curve). Dit wijzigt ENKEL de berekening hieronder, niet de rest van de app.",
        )
    with c_curve:
        st.caption(f"Bij 100 punten verschil: {_pct(ll.estimate_win_probability(0, -100, scale=scale))} winkans.")
    scored = score_raw_at_scale(raw_rows, scale)
    stats = calibration_stats(scored)
    if not stats:
        st.info("Nog geen matchen met zowel een gekende winkans als een gekende uitslag.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Brier-score", f"{stats['brier']:.3f}", help="Lager = beter. 0.25 = niet beter dan een muntstuk.")
    with c2:
        st.metric("Accuraatheid", f"{stats['accuracy'] * 100:.0f}%", help="Hoe vaak de favoriet (>=50%) ook echt won.")
    with c3:
        st.metric("Aantal matchen", f"{stats['n']}")
    if stats["brier"] >= 0.245:
        st.warning(
            f"Een Brier-score van {stats['brier']:.3f} ligt zeer dicht bij 0.25 - dat betekent dat de "
            "voorspelling hier amper beter is dan een muntje opgooien. Meer data (teamgenoten hierboven "
            "toevoegen) kan dit beeld scherper maken, maar wijst mogelijk ook op een factor die bijgesteld "
            "moet worden, of op wedstrijden waar de echte uitslag sterk afweek van het niveauverschil."
        )
    st.caption(
        f"Gemiddeld voorspeld: {stats['mean_predicted'] * 100:.0f}% - gemiddeld werkelijk gewonnen: "
        f"{stats['mean_actual'] * 100:.0f}%."
    )
    if stats["bins"]:
        st.dataframe(
            [{"Kansklasse": b["bereik"], "Aantal": b["n"], "Gem. voorspeld": f"{b['gem_voorspeld']:.0f}%",
              "Werkelijk gewonnen": f"{b['werkelijk']:.0f}%"} for b in stats["bins"]],
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "Idealiter liggen 'Gem. voorspeld' en 'Werkelijk gewonnen' per rij dicht bij elkaar. Een "
            "systematisch verschil (bv. bij lage kansklassen te hoog, bij hoge te laag) wijst op een "
            "factor die scherper of voorzichtiger zou moeten staan."
        )
    # PADEL_ANALYSIS_RETRO_AUTOSCALE_2026-10-04 - zie moduledocstring.
    st.divider()
    st.markdown("##### Beste winkansfactor automatisch zoeken")
    st.caption(
        "Zoekt, over alle bovenstaande matchen, de winkansfactor met de LAAGSTE Brier-score (dus de beste "
        "voorspelling) - puur rekenwerk op de al opgehaalde gegevens, dus snel. Je ziet het voorstel en "
        "bevestigt zelf voor het wordt toegepast; de schuifregelaar springt nooit vanzelf."
    )
    if st.button("Zoek beste winkansfactor", key="retro_find_best_scale"):
        with st.spinner("Factoren doorrekenen..."):
            st.session_state["retro_best_scale_result"] = find_best_scale(raw_rows)
    result = st.session_state.get("retro_best_scale_result")
    if result and result.get("best"):
        best = result["best"]
        if best["scale"] == int(scale):
            st.success(f"De huidige factor ({scale:.0f}) is al de beste in het doorzochte bereik (50-400, stap 5) - Brier {best['brier']:.3f}.")
        else:
            richting = "gevoeliger voor het ratingverschil (kleiner getal)" if best["scale"] < scale else "voorzichtiger (groter getal)"
            st.info(
                f"Voorstel: **{best['scale']}** (Brier **{best['brier']:.3f}**) in plaats van de huidige "
                f"**{int(scale)}** (Brier **{stats['brier']:.3f}**) - dat betekent een {richting} inschatting."
            )
            # PADEL_ANALYSIS_RETRO_SCALE_WIDGET_FIX_2026-10-04 - zie moduledocstring:
            # via on_click i.p.v. een if-st.button()-blok dat session_state["retro_scale"]
            # rechtstreeks zou zetten NA het al geïnstantieerde slider-widget hierboven.
            st.button(
                f"Toepassen: zet factor op {best['scale']}", key="retro_apply_best_scale",
                on_click=_apply_best_scale_callback, args=(best["scale"],),
            )
    elif result is not None:
        st.warning("Kon geen enkele factor beoordelen - onvoldoende matchen met een gekende uitslag.")
