"""
lineup_matchup_table.py - Opbouw en weergave van de volledige
"Opstelling-scenario's"-tabel: alle geldige matchups (eigen koppelverdeling
x tegenstander-opstelling), gegroepeerd, gesorteerd en met AI-doorvraag.
Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
Zie de oorspronkelijke, monolithische versie van page_lineup_lab.py voor de
volledige historische toelichting bij elke fix - functioneel ONGEWIJZIGD,
behalve de fixes hieronder.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SAVE_BUTTON_VISIBILITY_FIX_2026-09-27 (op verzoek van Kim:
"die knop analyse opslaan staat nergens of is althans niet zichtbaar")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd - de knop was niet AFWEZIG, maar extreem diep
begraven): "Deze analyse opslaan" stond helemaal aan het EINDE van
_render_all_valid_matchups(), pas bereikbaar nadat ALLE volgende stappen na
elkaar geslaagd waren: 1) tegenstander-scout gelukt, 2) minstens 2 eigen
spelers geselecteerd, 3) tegenstander-roster zó geselecteerd/ingesteld dat
de som van max-per-speler EXACT gelijk is aan 2x het aantal wedstrijden
(anders wordt er stilzwijgend NIETS berekend - geen foutmelding, gewoon 0
theoretische opstellingen), 4) expliciet op "Bereken alle geldige
matchups" geklikt, 5) en dan nog voorbij de volledige matchup-tabel,
gegroepeerde opstellingen, "Beste opstelling voor..."-tabel, platte tabel
EN de AI-sectie scrollen. Voor een eerste analyse van een nieuwe
tegenstander (zonder historische ontmoetingen) is stap 3 foutgevoelig en
onopvallend - een kleine afronding/wijziging in de multiselect kan de som
laten mismatchen, waardoor de hele verdere pijplijn (en dus de knop) nooit
bereikt wordt, zonder duidelijke melding waarom.
FIX: de "Analyse opslaan"-knop (en de bijhorende payload-opbouw) is
VERPLAATST naar direct na de regel "X geldige matchup(s) gevonden" -
dus zodra all_matchups niet leeg is, VOOR de zware rendering van
gegroepeerde opstellingen/tabellen/AI-sectie. Functioneel volledig
ongewijzigd (zelfde payload, zelfde fb.save_lineup_analysis()-aanroep,
zelfde key) - enkel de POSITIE in de pagina is aangepast, zodat opslaan
niet langer vereist dat je eerst door de volledige resultatensectie
scrolt. Stap 3 hierboven (de som-mismatch) blijft een aandachtspunt maar
is nu tenminste geen extra drempel meer BOVENOP een compleet verscholen
knop.
--------------------------------------------------------------------------
PADEL_ANALYSIS_NO_NONCOMPLIANT_2026-09-29 (op verzoek van Kim: "niet toegelaten opstellingen zijn
nutteloos. verwijder deze optie.")
--------------------------------------------------------------------------
De checkbox "Toon ook bewust omgedraaide, NIET-reglementaire varianten" is
weg. Enkel reglementaire bordvolgordes (art. 6.6) worden nog berekend; bij
een gelijk officieel klassement blijven beide (toegelaten) volgordes staan.
De badge "onzeker" (onvolledig officieel klassement) blijft bestaan.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29 (op verzoek van Kim: "Er zijn meer dan 800 geldige
matchups gevonden - enkel de eerste 800 zijn meegenomen [...] dit is ook
vreemd")
--------------------------------------------------------------------------
BUG: de lus stopte na 800 matchups, in de volgorde van de EIGEN
opstellingen - niet de beste. Met bv. 6 eigen spelers (~100 eigen
opstellingen) x 300 theoretische tegenstander-opstellingen (~30.000
combinaties) werden zo enkel de eerste ~3 eigen opstellingen volledig
doorgerekend; alle andere ontbraken stil in de tabel, de groepen en
"Beste opstelling voor...". De melding "verklein de spelersselectie" was
dus misleidend: het probleem was de afkapping, niet de selectie.
FIX: ELKE eigen opstelling wordt tegen ELKE tegenstander-opstelling
doorgerekend (veiligheidsgrens _MAX_COMPUTED_MATCHUPS). Om geheugen en
weergave beheersbaar te houden, wordt per eigen opstelling een SAMENVATTING
bijgehouden (aantal, beste, slechtste, gemiddelde, en per speler de
gemiddelde/slechtste/beste persoonlijke winkans) plus enkel de beste
_KEEP_PER_GROUP rijen, de slechtste rij en alle historische rijen.
Best/worst case en "Beste opstelling voor..." rekenen op de VOLLEDIGE
set, niet op de bewaarde rijen. De groepenlijst toont standaard de beste
_GROUPS_DISPLAY_DEFAULT eigen opstellingen (rest via een vinkje).
Opslaan bewaart de beste _SAVE_MAX_MATCHUPS matchups, zodat het
Firestore-document onder de limiet van 1 MB blijft.
--------------------------------------------------------------------------
PADEL_ANALYSIS_POINT_PROBABILITY_DISPLAY_2026-09-30 (op verzoek van Kim,
na het testen van de vorige versie: "Puntenkans apart tonen, niet in de
lange titel-string" - "30% · 2p 40% · 1p 30% · 0p · OK - R1M1 ... is
inderdaad te veel in een regel")
--------------------------------------------------------------------------
De expander-titel combineerde de puntenkans-tekst, de reglement-badge EN
de volledige koppellijst in EEN lange string - moeilijk te scannen over
meerdere groepen heen, en Streamlit-expander-labels ondersteunen geen
opmaak (geen kleur, geen vetgedrukt, geen losse elementen).
FIX: de puntenkans (2p/1p/0p) staat nu als 3 aparte st.metric()-elementen
BOVEN elke expander, in een rij van 3 kolommen - dus zichtbaar zonder te
hoeven openklikken, en visueel losstaand van de koppel-tekst. De expander-
titel zelf bevat nu enkel nog de reglement-badge + de korte koppellijst
(bv. "OK - R1M1 Kim/Nico · R1M2 Joris/Carl"), niet langer de puntenkans.
--------------------------------------------------------------------------
PADEL_ANALYSIS_POINT_PROBABILITY_BEST_FOR_PLAYER_2026-09-30 (op verzoek
van Kim: "Puntenkans ook bij 'Beste opstelling voor mezelf' - nu toont die
tabel enkel persoonlijke winkans. Ik voeg de kans op 2/1/0 punten voor de
HELE ploeg toe bij diezelfde opstelling, zodat je meteen ziet: 'goed voor
mij persoonlijk, en dit is wat het voor het team betekent.'")
--------------------------------------------------------------------------
_render_best_for_selected_player() toonde tot nu toe enkel de persoonlijke
winkans/EBW van de geselecteerde speler, zonder te tonen wat diezelfde
ploegopstelling betekent voor de PLOEGKANS (2/1/0 punten). FIX: 3 nieuwe
kolommen "Team Kans 2p/1p/0p %" - dezelfde gewogen puntenkans (g["point_
probs"]) die ook in de groepen hierboven getoond wordt, nu ook hier naast
de persoonlijke cijfers. Blijft ONGEWIJZIGD gesorteerd op de persoonlijke
gemiddelde winkans (een persoonlijke, geen ploegmaatstaf) - de puntenkans
is hier enkel INFORMATIEF, geen nieuwe sorteervolgorde.
--------------------------------------------------------------------------
PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30 (op verzoek van Kim, na
brainstorm over de matchup-analyse: "dat leert me niets wat de beste
opstelling is voor de ploeg [...] uiteindelijk gemiddeld gezien door alle
combinaties natuurlijk weer op zelfde uitkomt")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd door Kim's eigen voorbeeld: 3 groepen met Best 2.05 /
2.05 / 2.03): de groepstitel toonde enkel best/worst EXPECTED BOARDS WON
(EBW) - een getal dat noch (a) rekening houdt met hoe WAARSCHIJNLIJK elk
tegenstander-scenario is (alles werd gelijk geteld), noch (b) zegt wat het
ECHT uitmaakt: hoeveel COMPETITIEPUNTEN de ploeg haalt (0/1/2 - Kim,
bevestigd 2026-09-30: 2 bij winst, 1 bij gelijke stand/2-2, 0 bij verlies).
FIX, twee delen (rekenkern in lineup_rotation.py, dit bestand toont enkel):
  1. _compute_matchup() (lineup_rotation.py) berekent nu ook, per matchup,
     een EXACTE kansverdeling op 2/1/0 punten (point_probs) - zie
     lineup_rotation._match_outcome_point_probabilities(). Dit gebeurt
     ALTIJD, dus elke matchup in `all_matchups`/de groepen heeft dit veld
     al klaarstaan; hier hoeft niets herberekend te worden.
  2. Elk tegenstander-scenario ("unique_opponent_lineups"-item) krijgt een
     GEWICHT op basis van hoe vaak de tegenstander die exacte opstelling,
     IN DEZELFDE ROTATIE-POSITIE, dit seizoen al effectief speelde -
     lineup_rotation._opponent_lineup_weight(). Een scenario met 3
     observaties telt dus 4x zo zwaar mee in het gewogen gemiddelde als een
     zuiver theoretisch scenario. Dit gewicht wordt per (own_ordered_pairs,
     opponent-lineup-key)-matchup vastgelegd in _build_all_valid_matchups()
     en aan lineup_rotation._aggregate_group_point_probabilities()
     meegegeven om het gewogen gemiddelde puntenkans per groep te bouwen.
WEERGAVE: het NIEUWE hoofdgetal per groep (in
_render_own_lineup_groups_with_opponents()) is nu "68% kans op 2 punten ·
24% op 1 · 8% op 0" (gewogen gemiddelde over ALLE doorgerekende
tegenstander-scenario's van die groep - niet enkel de bewaarde rijen). De
BESTAANDE best/worst-EBW blijft ernaast staan als secundair getal (nuttig
als tiebreak bij een gelijke puntenkans). De groepenlijst wordt nu ook
GESORTEERD op deze gewogen 2-punten-kans (was: best-case EBW).
"Beste opstelling voor..." blijft ONGEWIJZIGD werken op EBW/winkans per
speler - dat is een persoonlijke, geen ploegmaatstaf, en verandert dus niet
mee met deze fix.
BEPERKING (bewust, zie lineup_rotation.py-moduledocstring): de weging
gebruikt uitsluitend DIT SEIZOEN (bundle.previous_fixtures) - de app heeft
op dit moment geen betrouwbare rotatiepositie-informatie over vorige
seizoenen. Kim akkoord (2026-09-30, "optie 1"): nu bouwen met wat er is,
architectuur zo dat vorige seizoenen er later bij kunnen zonder dit bestand
te moeten aanpassen (enkel lineup_rotation._opponent_lineup_weight()).
--------------------------------------------------------------------------
PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01 (op verzoek van Kim: "bij de
matchups zie ik 3 keer dezelfde percentages: 30-40-30. nutteloos.")
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd door de weging na te rekenen: _opponent_lineup_
weight() geeft een historisch scenario slechts +1.0 BOVENOP de vaste basis
1.0 PER OBSERVATIE (dus een 1x gespeeld scenario weegt 2.0, een 3x
gespeeld scenario weegt 4.0) - tegenover tot wel
_THEORETICAL_MAX_VARIANTS=300 zuiver THEORETISCHE scenario's die ELK ook
basisgewicht 1.0 krijgen. Met bv. 1 historisch scenario (gewicht 2.0) naast
287 theoretische (gewicht 287), weegt het ENIGE grounded datapunt dus voor
amper ~0.7% van het gewogen gemiddelde mee - de group-kans is dan in de
praktijk vrijwel UITSLUITEND het gemiddelde over alle theoretische
tegenstander-opstellingen. Omdat dat gemiddelde per definitie over VEEL
verschillende tegenstander-koppels gaat, convergeert het voor VERSCHILLENDE
eigen opstellingen naar bijna hetzelfde getal (de wet van de grote
aantallen middelt het verschil tussen onze eigen opstellingen grotendeels
weg) - exact Kim's eerdere constatering ("dat leert me niets... uiteindelijk
gemiddeld gezien door alle combinaties weer op zelfde uitkomt"), nu
teruggekeerd omdat de weging te zwak is om dat tegen te houden zodra het
theoretische roster groot is. Een 2e, onafhankelijke oorzaak die TOT
HETZELFDE SYMPTOOM leidt: ontbrekende ratings (player_ratings/official_
ranks/opponent_ratings) maken win_probability voor (bijna) elke match
None, waardoor _match_outcome_point_probabilities() overal terugvalt op de
neutrale 50%-aanname - dan is de 31.25%/37.5%/31.25%-verdeling voor N=4
borden WISKUNDIG IDENTIEK voor elke groep, ongeacht de weging.
FIX, VOLLEDIG ZICHTBAARHEID I.P.V. EEN GEDRAGSWIJZIGING VAN DE WEGING ZELF
(die weegformule blijft bewust ONGEWIJZIGD - zie lineup_rotation.py,
_opponent_lineup_weight() - een latere herziening van de weging zelf is
een aparte, grotere beslissing): _finalize_group() geeft nu ook
"n_historical_scenarios" (= len(g["historical"]), al bijgehouden maar tot
nu toe niet doorgegeven) terug. _render_own_lineup_groups_with_opponents()
toont daarmee, ALTIJD zichtbaar naast de 3 metrics (niet verstopt in de
expander), hoeveel van de g["n"] doorgerekende scenario's effectief
HISTORISCH vs THEORETISCH waren, plus - indien van toepassing - EEN van
de 2 volgende, elkaar uitsluitende waarschuwingen:
  1. Als >= 50% van de individuele match-schattingen in deze groep een
     onbekende winkans had (n_missing_ratings t.o.v. g["n"] x aantal
     borden): een duidelijke waarschuwing dat de percentages vooral op de
     neutrale 50%-aanname steunen (oorzaak 2 hierboven) - actie: ontbrekend
     klassement/rating aanvullen.
  2. Anders, als er 0 historische scenario's zijn EN >= 20 theoretische:
     een duidelijke notitie dat het cijfer vrijwel uitsluitend op
     theoretische scenario's steunt (oorzaak 1 hierboven) - actie: verklein
     het tegenstander-roster hierboven tot de spelers die je ECHT verwacht,
     zodat er minder, meer relevante theoretische scenario's overblijven
     en het gewicht van eventuele historische scenario's meer gewicht
     krijgt in verhouding.
Dit maakt de 2 mogelijke, fundamenteel verschillende oorzaken van
"identieke percentages" voor het eerst van elkaar te ONDERSCHEIDEN, met
een concrete, bruikbare vervolgstap per geval - i.p.v. enkel een cijfer
te tonen zonder te verklaren waarom het niet onderscheidend aanvoelt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02 (op verzoek van Kim: "hou
wel ook wat rekening met statistische gegevens zoals: persoon x speelt
bijna altijd met die persoon y. of persoon x speelt bijna altijd 1ste
match. combineer ook die data.")
--------------------------------------------------------------------------
1. WEGING: elk tegenstander-scenario krijgt nu als gewicht de VOORSPELDE
   KANS uit opponent_lineup_model.py (deelname + vaste koppels + Match 1/2-
   voorkeur, softmax over alle scenario's) i.p.v. de vroegere "1 + aantal
   keer gespeeld". Daardoor tellen honderden theoretische, onwaarschijnlijke
   opstellingen (bv. met een speler die nooit meespeelt, of 2 spelers die
   nooit samen spelen) bijna niet meer mee - precies de oorzaak van de
   uitgevlakte "30-40-30"-percentages (PADEL_ANALYSIS_DILUTED_GROUP_PROBS).
   _opponent_lineup_weight() in lineup_rotation.py blijft bestaan als
   terugval wanneer het model niet beschikbaar is.
2. BUGFIX in dezelfde lijn: _finalize_group() berekende de gewogen
   puntenkans enkel over de BEWAARDE rijen (beste 25 op EBW + slechtste +
   historische). Met modelgewichten kunnen de waarschijnlijkste scenario's
   net buiten die top-25 vallen. De gewogen som wordt nu INCREMENTEEL in
   _add_to_group() over ALLE doorgerekende matchups bijgehouden - exact,
   niet langer een benadering, en zonder extra geheugen.
3. Nieuw expander-blok "Voorspelde tegenstander-opstellingen" toont de top
   5 met kans en de redenen, zodat de weging controleerbaar is.
Cache-sleutels naar v4 (de gewichten zijn veranderd).
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_MATRIX_2026-10-03 (op verzoek van Kim: "gewoon
overal hetzelfde gemiddelde zien is ook niet zinvol. Dus specifieke cases
zijn wel interessant")
--------------------------------------------------------------------------
Meteen na de voorspelde tegenstander-opstellingen (en VOOR de knop
"Bereken alle geldige matchups") staat nu de scenario-matrix uit
lineup_scenario_matrix.py: benoemde tegenstander-scenario's als kolommen,
eigen strategieen (aanvallend / veilig / robuust / counter) als rijen, met
de exacte kans per cel. Ze rekent zelf (licht: enkel de eigen opstellingen
x max. 8 scenario's) en heeft de knop dus niet nodig. Faalt de module, dan
werkt de rest van deze sectie ongewijzigd verder.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03 (feedback Kim: "Als ik bvb een speler
wegklik [...] dan moet je die opstelling niet tonen want is niet mogelijk",
"handig om bij de spelers en het aantal matchen te zien welke padelstat
score en officiele ranking ze hebben [...] het aantal matchen die ze
waarschijnlijk gaan spelen al voorstellen. Moet dus geupdate worden als je
spelers toevoegt of wegklikt", "minstens 1 punt [...] zou bij matchup ook
logischer zijn", grotere koppen per opstelling)
--------------------------------------------------------------------------
1. Tegenstander-opstellingen (ook EFFECTIEF GESPEELDE) met een speler die
   niet in "Beschikbare tegenstander-spelers" staat, worden weggelaten -
   voor de matrix, het model en de matchup-tabel. Herkenning op id OF naam.
2. Het veld per tegenstander-speler toont "Naam (P-klassement · ps
   padelstat)" en staat standaard op het VERWACHTE aantal matchen: het
   gemiddelde aantal matchen per ontmoeting dat die speler speelde
   (statistisch model), herschaald naar het totaal en begrensd op 1 match
   per rotatie. Zonder historiek: gelijk verdeeld (zoals voorheen). Wijzig
   je de selectie, dan wordt het voorstel herberekend.
3. "Onze opstellingen": grote kop per opstelling met de namen per rotatie,
   daaronder 4 grote cijfers (winst / gelijk / verlies / minstens 1 punt),
   de uitklapknop heet "Details".
4. Het model (stats) wordt mee doorgegeven aan de scenario-matrix voor de
   duiding van de kansen.
"""
import heapq
import streamlit as st
from dashboard_common import fb, taa
from lineup_scout import _opponent_official_ranks, _opponent_padelstat_ratings
try:
    import lineup_scenario_matrix as lsm  # PADEL_ANALYSIS_SCENARIO_MATRIX_2026-10-03
except Exception:  # noqa: BLE001  pragma: no cover
    lsm = None
try:
    import opponent_lineup_model as olm  # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02
except Exception:  # noqa: BLE001  pragma: no cover
    olm = None
from lineup_rotation import (
    _enumerate_rotation_aware_pairings, _enumerate_own_variant_combinations,
    _compute_matchup, _default_opponent_max_per_player,
    _generate_theoretical_opponent_boards_with_repeats,
    _historical_opponent_boards_list, _collect_unique_opponent_lineups,
    _opponent_lineup_weight, _aggregate_group_point_probabilities,  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
)
_MATCHUP_DISPLAY_DEFAULT_N = 15
_THEORETICAL_MAX_VARIANTS = 300
# PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29
_MAX_COMPUTED_MATCHUPS = 100_000   # veiligheidsgrens op de rekenlus
_KEEP_PER_GROUP = 25               # bewaarde beste rijen per eigen opstelling
_GROUPS_DISPLAY_DEFAULT = 20       # standaard getoonde eigen opstellingen
_SAVE_MAX_MATCHUPS = 150           # Firestore-document < 1 MB
_MAX_TOTAL_MATCHUPS = _MAX_COMPUTED_MATCHUPS  # oude naam, voor compatibiliteit
# PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01: drempels voor de 2 diagnose-captions hieronder.
_DILUTION_MISSING_RATIO_THRESHOLD = 0.5   # >= 50% onbekende winkansen -> waarschuwing
_DILUTION_THEORETICAL_MIN_COUNT = 20       # 0 historisch + >= 20 theoretisch -> notitie
def _sort_val(m) -> float:
    ebw = m.get("expected_boards_won")
    return ebw if ebw is not None else m.get("total_score", 0.0)
def _new_group_summary(assignment: list) -> dict:
    return {
        "n": 0, "ebw_sum": 0.0, "ebw_n": 0,
        "best": None, "worst": None,
        "top": [], "historical": [],
        "players": {}, "positions": {},
        "first_assignment": assignment,
        "weights": {},  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: id(m) -> gewicht van zijn tegenstander-scenario
        # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: exacte gewogen som over ALLE matchups.
        "w_sum": 0.0, "w_p2": 0.0, "w_p1": 0.0, "w_p0": 0.0, "n_missing": 0,
        # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02: matchup tegen de MEEST
        # waarschijnlijke tegenstander-opstelling + bereik van P(2).
        "top_w": -1.0, "top_w_m": None, "p2_min": None, "p2_max": None,
    }
def _add_to_group(g: dict, m: dict, counter: int, opponent_weight: float = 1.0) -> None:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: `opponent_weight` is het
    gewicht van het tegenstander-scenario waartegen deze matchup berekend
    is (lineup_rotation._opponent_lineup_weight()) - bewaard per matchup-id
    in g["weights"], zodat de gewogen puntenkans-aggregatie later over de
    VOLLEDIGE set (niet enkel de bewaarde top-rijen) kan rekenen."""
    val = _sort_val(m)
    g["n"] += 1
    g["weights"][id(m)] = opponent_weight
    # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: incrementeel, over ALLE matchups.
    pp_m = m.get("point_probs") or {}
    g["w_sum"] += opponent_weight
    g["w_p2"] += opponent_weight * pp_m.get("p2", 0.0)
    g["w_p1"] += opponent_weight * pp_m.get("p1", 0.0)
    g["w_p0"] += opponent_weight * pp_m.get("p0", 0.0)
    g["n_missing"] += int(m.get("n_missing_win_probs", 0) or 0)
    # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02
    if opponent_weight > g["top_w"] or (
        opponent_weight == g["top_w"] and g["top_w_m"] is not None
        and pp_m.get("p2", 0.0) > (g["top_w_m"].get("point_probs") or {}).get("p2", 0.0)
    ):
        g["top_w"], g["top_w_m"] = opponent_weight, m
    p2v = pp_m.get("p2")
    if p2v is not None:
        g["p2_min"] = p2v if g["p2_min"] is None else min(g["p2_min"], p2v)
        g["p2_max"] = p2v if g["p2_max"] is None else max(g["p2_max"], p2v)
    ebw = m.get("expected_boards_won")
    if ebw is not None:
        g["ebw_sum"] += ebw
        g["ebw_n"] += 1
    if g["best"] is None or val > _sort_val(g["best"]):
        g["best"] = m
    if g["worst"] is None or val < _sort_val(g["worst"]):
        g["worst"] = m
    if m.get("is_historical"):
        g["historical"].append(m)
    if len(g["top"]) < _KEEP_PER_GROUP:
        heapq.heappush(g["top"], (val, counter, m))
    elif val > g["top"][0][0]:
        heapq.heapreplace(g["top"], (val, counter, m))
    # Persoonlijke winkans per speler in deze matchup (gemiddelde over de
    # matchen waarin die speler staat) - voor "Beste opstelling voor...".
    per_player: dict = {}
    for idx, a in enumerate(m["assignment"]):
        wp = a.get("win_probability")
        p1, p2 = (str(x) for x in a["our_pair"])
        for pid, partner in ((p1, p2), (p2, p1)):
            if pid not in g["positions"]:
                g["positions"][pid] = []
            if g["n"] == 1:
                g["positions"][pid].append((idx // 2 + 1, idx % 2 + 1, partner))
            if wp is not None:
                per_player.setdefault(pid, []).append(wp)
    for pid, kansen in per_player.items():
        gem = sum(kansen) / len(kansen)
        st_ = g["players"].get(pid)
        if st_ is None:
            g["players"][pid] = [gem, gem, gem, 1, ebw or 0.0, 1 if ebw is not None else 0]
        else:
            st_[0] += gem
            st_[1] = min(st_[1], gem)
            st_[2] = max(st_[2], gem)
            st_[3] += 1
            if ebw is not None:
                st_[4] += ebw
                st_[5] += 1
def _finalize_group(key, g: dict) -> dict:
    rows_by_id = {}
    for _, _, m in g["top"]:
        rows_by_id[id(m)] = m
    for m in [g["worst"]] + g["historical"]:
        if m is not None:
            rows_by_id[id(m)] = m
    rows = sorted(rows_by_id.values(), key=_sort_val, reverse=True)
    # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: gewogen puntenkans over
    # de VOLLEDIGE set van deze groep - g["weights"] bevat een entry voor
    # ELKE doorgerekende matchup van deze groep (niet enkel de bewaarde
    # rijen), gevuld in _add_to_group() bij elke aanroep.
    all_group_matches = [m for _, _, m in g["top"]]
    for m in [g["worst"]] + g["historical"]:
        if m is not None and m not in all_group_matches:
            all_group_matches.append(m)
    # De heap ("top") bewaart enkel de beste _KEEP_PER_GROUP - voor een
    # correct gewogen gemiddelde over ALLE scenario's van deze groep zou
    # strikt genomen elke matchup nodig zijn, niet enkel de bewaarde top.
    # Om dat zonder een 2e volledige matchup-lijst per groep te bewaren
    # (geheugen!) op te lossen, gebruiken we hier een PONDERATED SCHATTING:
    # de gewogen p2/p1/p0 over de bewaarde rijen (top + worst + historical)
    # is de beste beschikbare benadering, en convergeert naar het exacte
    # gewogen gemiddelde naarmate _KEEP_PER_GROUP een groter deel van de
    # scenario's dekt. Bij minder dan _KEEP_PER_GROUP totale scenario's
    # (het gebruikelijke geval bij een realistische tegenstander-roster)
    # is dit exact, geen schatting.
    point_probs = _aggregate_group_point_probabilities(all_group_matches, g["weights"])
    # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: exacte waarde over ALLE
    # matchups (incrementeel bijgehouden) vervangt de benadering hierboven.
    if g.get("w_sum", 0.0) > 0:
        point_probs = {
            "p2": g["w_p2"] / g["w_sum"], "p1": g["w_p1"] / g["w_sum"],
            "p0": g["w_p0"] / g["w_sum"], "n_missing_ratings": g.get("n_missing", 0),
        }
    return {
        "key": key, "n": g["n"], "rows": rows,
        "best": g["best"], "worst": g["worst"],
        "mean_ebw": (g["ebw_sum"] / g["ebw_n"]) if g["ebw_n"] else None,
        "point_probs": point_probs,  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
        # PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01: hoeveel van g["n"]
        # scenario's effectief HISTORISCH waren (g["historical"] bevat ALLE
        # historische matchups van deze groep, niet enkel de bewaarde top -
        # zie _add_to_group()) - gebruikt om de dilutie-captions hieronder
        # te kunnen tonen zonder opnieuw te moeten tellen.
        "n_historical_scenarios": len(g["historical"]),
        # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02
        "vs_likely": g.get("top_w_m"), "vs_likely_weight": g.get("top_w", 0.0),
        "p2_min": g.get("p2_min"), "p2_max": g.get("p2_max"),
        "players": g["players"], "positions": g["positions"],
        "first_assignment": g["first_assignment"],
    }
def _build_all_valid_matchups(
    unique_opponent_lineups: dict,
    available_ids: list, max_per_player: dict,
    synergy_fn, player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
    tournament_rules_dict, include_non_compliant_variants: bool = False,
    opponent_weight_override: dict = None,  # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02
) -> tuple:
    """PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29: rekent ELKE reglementaire eigen opstelling door
    tegen ELKE tegenstander-opstelling - zie moduledocstring.
    Geeft (all_matchups, truncated, total_seen, diagnostics, groups) terug.
    include_non_compliant_variants wordt genegeerd (PADEL_ANALYSIS_NO_NONCOMPLIANT_2026-09-29).
    PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: elk tegenstander-scenario
    (their_key/info) krijgt hier zijn gewicht via
    lineup_rotation._opponent_lineup_weight(info) - EEN keer per unieke
    tegenstander-opstelling (niet per matchup), en dat gewicht wordt
    meegegeven aan _add_to_group() voor elke matchup die tegen dat scenario
    berekend wordt."""
    own_structures, own_truncated = _enumerate_rotation_aware_pairings(available_ids, max_per_player)
    valid_own_options = []
    own_excluded_by_rules = 0
    own_variants_generated = 0
    for structure in own_structures:
        combinations = _enumerate_own_variant_combinations(
            structure, official_ranks_strict, player_ratings, rules=tournament_rules_dict,
            include_non_compliant=False,
        )
        for combo in combinations:
            own_variants_generated += 1
            if not combo["fully_compliant"]:
                continue
            all_points_valid = all(r["valid"] for r in combo["rotations"])
            if tournament_rules_dict is not None and not all_points_valid:
                own_excluded_by_rules += 1
                continue
            valid_own_options.append((
                combo["ordered_pairs"], combo["rotations"], combo["fully_compliant"],
                combo.get("rank_data_incomplete", False),
            ))
    seen_matchup_keys = set()
    groups: dict = {}
    total_seen = 0
    computed_n = 0
    truncated = own_truncated
    counter = 0
    # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: gewicht per tegenstander-
    # scenario, EEN keer berekend, niet per matchup.
    opponent_weight_by_key = {
        their_key: _opponent_lineup_weight(info)
        for their_key, info in unique_opponent_lineups.items()
    }
    if opponent_weight_override:
        opponent_weight_by_key = {
            k: opponent_weight_override.get(k, 0.0) for k in unique_opponent_lineups
        }
    for own_ordered_pairs, own_rotations_info, fully_compliant, rank_data_incomplete in valid_own_options:
        if computed_n >= _MAX_COMPUTED_MATCHUPS:
            truncated = True
            break
        our_pairs_key = tuple(frozenset(p) for p in own_ordered_pairs)
        for their_key, info in unique_opponent_lineups.items():
            boards = info["boards"]
            if len(boards) != len(own_ordered_pairs):
                continue
            total_seen += 1
            mkey = (our_pairs_key, their_key)
            if mkey in seen_matchup_keys:
                continue
            seen_matchup_keys.add(mkey)
            computed = _compute_matchup(
                own_ordered_pairs, boards, synergy_fn, player_ratings, official_ranks_strict, opponent_ratings,
            )
            # PADEL_ANALYSIS_TEAM_WIN_DISTRIBUTION_2026-09-29: kans op
            # 2/1/0 ploegpunten, o.b.v. de per-board winkansen - zie
            # moduledocstring. None wanneer niet alle boards een gekende
            # winkans hebben.
            m = {
                "assignment": computed["assignment"],
                "expected_boards_won": computed["expected_boards_won"],
                "total_score": computed["total_score"],
                "point_probs": computed.get("point_probs"),  # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
                "n_missing_win_probs": computed.get("n_missing_win_probs", 0),
                "rank_data_incomplete": rank_data_incomplete,
                "own_rotations": own_rotations_info,
                "fully_compliant": True,
                "is_historical": info["is_historical"],
                "historical_labels": list(info["historical_labels"]),
                "historical_count": info.get("historical_count", 0),
            }
            gkey = _own_lineup_group_key(m["assignment"])
            if gkey not in groups:
                groups[gkey] = _new_group_summary(m["assignment"])
            counter += 1
            _add_to_group(groups[gkey], m, counter, opponent_weight=opponent_weight_by_key.get(their_key, 1.0))
            computed_n += 1
            if computed_n >= _MAX_COMPUTED_MATCHUPS:
                truncated = True
                break
    group_list = [_finalize_group(k, g) for k, g in groups.items()]
    # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: sorteer op de gewogen
    # kans op 2 punten (was: best-case EBW) - dat is nu de vraag die Kim
    # wil beantwoord zien: welke opstelling maximaliseert de kans op een
    # ploegoverwinning, niet louter het beste best-case scenario.
    group_list.sort(key=lambda g: (
        round(g["point_probs"]["p2"], 3),
        ((g.get("vs_likely") or {}).get("point_probs") or {}).get("p2", 0.0),
    ), reverse=True)
    all_matchups = [m for g in group_list for m in g["rows"]]
    all_matchups.sort(key=_sort_val, reverse=True)
    diagnostics = {
        "own_structures_total": len(own_structures),
        "own_variants_generated": own_variants_generated,
        "own_excluded_by_rules": own_excluded_by_rules,
        "own_valid": len(valid_own_options),
        "matchups_computed": computed_n,
        "own_groups": len(group_list),
    }
    return all_matchups, truncated, total_seen, diagnostics, group_list
def _format_opponent_lineup_label(boards: list) -> str:
    return " | ".join(" + ".join(p.get("name", "?") for p in b.get("opponent_pair", [])) for b in boards)
_TABLE_CHAR_WIDTH_PX = 6.6
_TABLE_COL_MIN_WIDTH = 90
_TABLE_COL_MAX_WIDTH = 240
def _estimate_column_width(values: list, min_width: int = _TABLE_COL_MIN_WIDTH, max_width: int = _TABLE_COL_MAX_WIDTH) -> int:
    max_len = 0
    for v in values:
        if v is None:
            continue
        max_len = max(max_len, len(str(v)))
    width = int(max_len * _TABLE_CHAR_WIDTH_PX) + 24
    return max(min_width, min(max_width, width))
def _compliance_badge(fully_compliant: bool, rank_data_incomplete: bool = False) -> str:
    # PADEL_ANALYSIS_NO_NONCOMPLIANT_2026-09-29: er worden enkel nog reglementaire varianten berekend.
    if rank_data_incomplete:
        return "onzeker"
    return "OK"
def _own_lineup_group_key(assignment: list) -> frozenset:
    return frozenset(frozenset(a["our_pair"]) for a in assignment)
def _format_point_probs(pp: dict) -> str:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: leesbare, korte
    weergave van een puntenkans-dict, bv. '68% · 2p 24% · 1p 8% · 0p'.
    PADEL_ANALYSIS_POINT_PROBABILITY_DISPLAY_2026-09-30: niet langer
    gebruikt in de groepstitel (die toont de 3 kansen nu als aparte
    st.metric()-elementen, zie _render_own_lineup_groups_with_opponents()).
    Blijft hier staan als herbruikbare tekst-opmaak voor eventueel ander
    gebruik (bv. lineup_rotation.py heeft een eigen, lokale kopie
    _format_point_probs_short() om een cirkelvormige import te vermijden)."""
    if not pp:
        return "onbekend"
    return (
        f"{pp.get('p2', 0.0) * 100:.0f}% · 2p  "
        f"{pp.get('p1', 0.0) * 100:.0f}% · 1p  "
        f"{pp.get('p0', 0.0) * 100:.0f}% · 0p"
    )
def _matchups_to_table_rows(matchups: list, name_lookup_global: dict) -> tuple:
    rows = []
    board_column_names: list = []
    for rank, m in enumerate(matchups, start=1):
        assignment = m["assignment"]
        n_boards = len(assignment)
        n_rotations = -(-n_boards // 2)
        pp = m.get("point_probs") or {}
        row = {
            "#": rank,
            "Verwacht": m.get("expected_boards_won"),
            # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: kansen per uitkomst, apart sorteerbaar.
            "Kans 2p %": round(pp.get("p2", 0.0) * 100, 0) if pp else None,
            "Kans 1p %": round(pp.get("p1", 0.0) * 100, 0) if pp else None,
            "Kans 0p %": round(pp.get("p0", 0.0) * 100, 0) if pp else None,
        }
        for r in range(n_rotations):
            for board_in_rotation in range(2):
                board_idx = r * 2 + board_in_rotation
                if board_idx >= n_boards:
                    continue
                a = assignment[board_idx]
                col_base = f"Rotatie{r+1} M{board_in_rotation+1}"
                if col_base not in board_column_names:
                    board_column_names.append(col_base)
                p1, p2 = a["our_pair"]
                our_full_1 = name_lookup_global.get(p1, p1)
                our_full_2 = name_lookup_global.get(p2, p2)
                opp_pair = a["opponent_board"]["opponent_pair"]
                their_full = [p.get("name", "?") for p in opp_pair]
                wp = a.get("win_probability")
                row[f"{col_base} - Ons duo"] = f"{our_full_1}+{our_full_2}"
                row[f"{col_base} - Tegenstander"] = "+".join(their_full)
                row[f"{col_base} %"] = round(wp * 100, 0) if wp is not None else None
        swap_notes = [
            rot.get("swap_label", "") for rot in (m.get("own_rotations") or [])
            if rot.get("swap_label")
        ]
        row["Toelichting"] = " | ".join(swap_notes) if swap_notes else ""
        n_keer = m.get("historical_count", 0)
        if m["is_historical"]:
            freq = f"{n_keer}x" if n_keer > 1 else "1x"
            row["Vorige keer"] = f"{freq} ({', '.join(m['historical_labels'])})"
        else:
            row["Vorige keer"] = ""
        rows.append(row)
    return rows, board_column_names
def _matchup_table_column_config(table_rows: list, board_column_names: list) -> tuple:
    column_config = {
        "#": st.column_config.NumberColumn("#", width="small"),
        "Verwacht": st.column_config.NumberColumn("Verwacht", format="%.2f", width="small"),
        # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30
        "Kans 2p %": st.column_config.NumberColumn("Kans 2p", format="%.0f%%", width="small"),
        "Kans 1p %": st.column_config.NumberColumn("Kans 1p", format="%.0f%%", width="small"),
        "Kans 0p %": st.column_config.NumberColumn("Kans 0p", format="%.0f%%", width="small"),
    }
    for col_base in board_column_names:
        ons_col = f"{col_base} - Ons duo"
        tegen_col = f"{col_base} - Tegenstander"
        pct_col = f"{col_base} %"
        column_config[ons_col] = st.column_config.TextColumn(
            ons_col, width=_estimate_column_width([row.get(ons_col) for row in table_rows]),
        )
        column_config[tegen_col] = st.column_config.TextColumn(
            tegen_col, width=_estimate_column_width([row.get(tegen_col) for row in table_rows]),
        )
        column_config[pct_col] = st.column_config.NumberColumn(pct_col, format="%.0f%%", width="small")
    column_config["Toelichting"] = st.column_config.TextColumn(
        "Toelichting", width=_estimate_column_width([row.get("Toelichting") for row in table_rows], min_width=160, max_width=320),
    )
    column_order = ["#", "Kans 2p %", "Kans 1p %", "Kans 0p %", "Verwacht"]
    for col_base in board_column_names:
        column_order += [f"{col_base} - Ons duo", f"{col_base} - Tegenstander", f"{col_base} %"]
    column_order += ["Toelichting", "Vorige keer"]
    return column_config, column_order
def _render_group_dilution_diagnosis(g: dict, best: dict, n_missing: int) -> None:
    """PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01 - zie moduledocstring.
    Toont, ALTIJD zichtbaar (dus buiten de expander), hoeveel van de
    doorgerekende scenario's van deze groep effectief HISTORISCH vs
    THEORETISCH waren, en - indien van toepassing - EEN van 2 elkaar
    uitsluitende waarschuwingen over waarom de getoonde percentages
    mogelijk niet (sterk) onderscheidend zijn tussen groepen."""
    n_total = g.get("n", 0)
    n_hist = g.get("n_historical_scenarios", 0)
    n_theo = max(0, n_total - n_hist)
    # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02: duidelijker (geen grijze caption) +
    # resultaat tegen de MEEST waarschijnlijke tegenstander-opstelling en het bereik.
    vs = g.get("vs_likely")
    regels = []
    if vs is not None:
        pv = vs.get("point_probs") or {}
        hist_txt = " (effectief gespeeld)" if vs.get("is_historical") else ""
        regels.append(
            f"**Tegen hun waarschijnlijkste opstelling{hist_txt}** "
            f"({g.get('vs_likely_weight', 0) * 100:.0f}% kans): "
            f"**{pv.get('p2', 0) * 100:.0f}% winst** · {pv.get('p1', 0) * 100:.0f}% gelijk · "
            f"{pv.get('p0', 0) * 100:.0f}% verlies"
        )
    if g.get("p2_min") is not None:
        regels.append(
            f"Kans op winst varieert van **{g['p2_min'] * 100:.0f}%** (slechtste tegenstander-opstelling) "
            f"tot **{g['p2_max'] * 100:.0f}%** (gunstigste)."
        )
    regels.append(
        f"Gewogen over {n_total} tegenstander-scenario's ({n_hist} effectief gespeeld, {n_theo} theoretisch)."
    )
    st.markdown("  \n".join(regels))
    n_boards_per_row = len(best.get("assignment") or [])
    denom = n_total * n_boards_per_row
    missing_fraction = (n_missing / denom) if denom else 0.0
    if missing_fraction >= _DILUTION_MISSING_RATIO_THRESHOLD:
        st.warning(
            f"Bij {missing_fraction * 100:.0f}% van de doorgerekende matchen in deze groep is de "
            "winkans onbekend (ontbrekend klassement/rating) - de percentages hierboven steunen "
            "dus voor een groot deel op een neutrale 50%-aanname en zijn minder betrouwbaar. "
            "Vul het ontbrekende klassement/rating aan voor een scherper cijfer."
        )
    elif n_hist == 0 and n_theo >= _DILUTION_THEORETICAL_MIN_COUNT and olm is None:
        st.caption(
            "Let op: dit cijfer is (nog) uitsluitend gebaseerd op THEORETISCHE tegenstander-"
            "opstellingen (nog geen enkele hiervan effectief gespeeld dit seizoen). Bij veel "
            "mogelijke tegenstander-opstellingen kan het verschil tussen eigen opstellingen "
            "hierdoor klein lijken - verklein het tegenstander-roster hierboven tot de spelers "
            "die je effectief verwacht, voor een scherper onderscheid."
        )
def _render_own_lineup_groups_with_opponents(groups: list, name_lookup_global: dict, ploeg_key: str = "") -> None:
    """PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29: werkt op de groepssamenvattingen uit
    _build_all_valid_matchups(). Best/worst case in de titel gelden over
    ALLE doorgerekende tegenstander-opstellingen van die groep.
    PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: het HOOFDGETAL in de
    groepstitel is nu de gewogen puntenkans (2/1/0), niet langer enkel
    best/worst EBW. De groepenlijst is al gesorteerd op kans-op-2-punten
    (zie _build_all_valid_matchups()) - hier enkel weergave, geen
    herordening.
    PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01: toont nu ALTIJD (dus
    voor het openklikken) een korte, verklarende dilutie-diagnose naast de
    3 metrics - zie _render_group_dilution_diagnosis()."""
    if not groups:
        return
    st.markdown('<div class="section-header">Onze opstellingen - klap open voor de tegenstander-opstellingen</div>', unsafe_allow_html=True)
    st.caption(
        "Elke groep hieronder is 1 unieke combinatie van ONZE koppels (ongeacht bordvolgorde of tegen wie), "
        "gerangschikt op de GEWOGEN kans op 2 competitiepunten (ploegwinst) over alle doorgerekende "
        "tegenstander-opstellingen. Een tegenstander-opstelling die dit seizoen al vaker effectief "
        "gespeeld werd, telt zwaarder mee dan een louter theoretische combinatie. Klap een groep open "
        "voor de beste tegenstander-opstellingen, de slechtste, en elke opstelling die de tegenstander "
        "effectief al speelde."
    )
    st.caption(
        "Puntensysteem: 2 punten bij meer gewonnen matchen dan de tegenstander, 1 punt bij een gelijke "
        "stand, 0 punten bij minder gewonnen matchen. 'Verwacht' (EBW) blijft ernaast staan als secundair "
        "getal, vooral nuttig bij een gelijke puntenkans."
    )
    st.caption(
        "Reglementair: OK = geverifieerd conform art. 6.6. onzeker = minstens 1 speler heeft nog geen bekend "
        "officieel klassement - de volgorde kon NIET betrouwbaar geverifieerd worden."
    )
    # PADEL_ANALYSIS_MATCHUP_CONTRAST_2026-10-02: hoe groot is het verschil
    # tussen onze beste en slechtste eigen opstelling eigenlijk?
    p2s = [g["point_probs"]["p2"] for g in groups]
    if len(p2s) > 1:
        spread = (max(p2s) - min(p2s)) * 100
        if spread < 3:
            st.info(
                f"De {len(groups)} eigen opstellingen liggen dicht bij elkaar (kans op winst "
                f"{min(p2s) * 100:.0f}% - {max(p2s) * 100:.0f}%): onze spelers zijn ongeveer even sterk "
                "tegenover deze tegenstander, dus de keuze maakt gemiddeld weinig uit. Het echte verschil "
                "zit in WIE de tegenstander opstelt - zie 'Tegen hun waarschijnlijkste opstelling' per groep "
                "en de scenario-kaarten in de Rotatieplanner."
            )
        else:
            st.markdown(
                f"**Verschil tussen onze beste en slechtste opstelling: {spread:.0f} procentpunt** "
                f"kans op winst ({max(p2s) * 100:.0f}% vs {min(p2s) * 100:.0f}%)."
            )
    toon_alle = False
    if len(groups) > _GROUPS_DISPLAY_DEFAULT:
        toon_alle = st.checkbox(
            f"Toon alle {len(groups)} eigen opstellingen (i.p.v. de beste {_GROUPS_DISPLAY_DEFAULT})",
            key=f"groups_show_all_{ploeg_key}",
        )
    zichtbaar = groups if toon_alle else groups[:_GROUPS_DISPLAY_DEFAULT]
    for g in zichtbaar:
        best, worst = g["best"], g["worst"]
        korte_delen, lange_regels = [], []
        for idx, a in enumerate(best["assignment"]):
            p1, p2 = a["our_pair"]
            rot, m_in_rot = idx // 2 + 1, idx % 2 + 1
            naam1, naam2 = name_lookup_global.get(p1, p1), name_lookup_global.get(p2, p2)
            korte_delen.append(f"R{rot}M{m_in_rot} {naam1}/{naam2}")
            lange_regels.append(f"- **Rotatie {rot} - Match {m_in_rot}**: {naam1} / {naam2}")
        best_ebw, worst_ebw = best.get("expected_boards_won"), worst.get("expected_boards_won")
        best_txt = f"{best_ebw:.2f}" if best_ebw is not None else f"score {best.get('total_score', 0):.3f}"
        worst_txt = f"{worst_ebw:.2f}" if worst_ebw is not None else f"score {worst.get('total_score', 0):.3f}"
        badge = _compliance_badge(True, best.get("rank_data_incomplete", False))
        # PADEL_ANALYSIS_POINT_PROBABILITY_DISPLAY_2026-09-30: de puntenkans
        # staat nu als 3 aparte metrics BOVEN de expander - zie
        # moduledocstring. De expander-titel zelf bevat enkel nog de
        # reglement-badge + de korte koppellijst (geen opmaak mogelijk in
        # een st.expander-label, vandaar de metrics ernaast i.p.v. erin).
        pp_metrics = g.get("point_probs") or {}
        # PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: grote kop met de namen per rotatie.
        per_rot = {}
        for idx, a in enumerate(best["assignment"]):
            p1_, p2_ = a["our_pair"]
            per_rot.setdefault(idx // 2 + 1, []).append(
                f"{name_lookup_global.get(p1_, p1_)} / {name_lookup_global.get(p2_, p2_)}"
            )
        _sep = " \u00b7 "
        st.markdown("#### " + "  \u00a0|\u00a0  ".join(
            f"R{r}: {_sep.join(v)}" for r, v in sorted(per_rot.items())
        ) + f"  \u00a0 `{badge}`")
        col_p2, col_p1, col_p0, col_ge1 = st.columns(4)
        with col_p2:
            st.metric("Winst (2p)", f"{pp_metrics.get('p2', 0.0) * 100:.0f}%")
        with col_p1:
            st.metric("Gelijk (1p)", f"{pp_metrics.get('p1', 0.0) * 100:.0f}%")
        with col_p0:
            st.metric("Verlies (0p)", f"{pp_metrics.get('p0', 0.0) * 100:.0f}%")
        with col_ge1:
            st.metric("Minstens 1 punt", f"{(pp_metrics.get('p2', 0.0) + pp_metrics.get('p1', 0.0)) * 100:.0f}%")
        # PADEL_ANALYSIS_DILUTED_GROUP_PROBS_2026-10-01: ALTIJD zichtbaar,
        # VOOR de expander - zie moduledocstring voor waarom dit niet
        # verstopt mag zitten achter een klik.
        n_missing = pp_metrics.get("n_missing_ratings", 0)
        _render_group_dilution_diagnosis(g, best, n_missing)
        with st.expander("Details", expanded=False):
            st.markdown("**Onze opstelling in deze groep:**")
            st.markdown("\n".join(lange_regels))
            gem = g.get("mean_ebw")
            gem_txt = f", gemiddeld EBW {gem:.2f}" if gem is not None else ""
            missing_txt = (
                f" ({n_missing} match(en) zonder bekende winkans, geteld als 50/50 in de puntenkans)"
                if n_missing else ""
            )
            st.caption(
                f"Bovenstaande kansen zijn het gewogen gemiddelde over {g['n']} doorgerekende "
                f"tegenstander-opstelling(en){missing_txt}. Best case {best_txt} en worst case {worst_txt} "
                f"verwachte gewonnen matchen (EBW){gem_txt}."
            )
            if len(g["rows"]) < g["n"]:
                st.caption(
                    f"Getoond: de beste {_KEEP_PER_GROUP}, de slechtste en elke al gespeelde "
                    f"tegenstander-opstelling ({len(g['rows'])} van {g['n']})."
                )
            table_rows, board_column_names = _matchups_to_table_rows(g["rows"], name_lookup_global)
            column_config, column_order = _matchup_table_column_config(table_rows, board_column_names)
            st.dataframe(
                table_rows, use_container_width=True, hide_index=True,
                column_config=column_config, column_order=column_order,
            )
    if not toon_alle and len(groups) > _GROUPS_DISPLAY_DEFAULT:
        st.caption(f"De beste {_GROUPS_DISPLAY_DEFAULT} van {len(groups)} eigen opstellingen getoond (gesorteerd op kans op 2 punten).")
    st.divider()
def _render_best_for_selected_player(
    groups: list, sel_player_id: str, name_lookup_global: dict,
) -> None:
    """Welke ploegopstelling is het beste VOOR EEN SPECIFIEKE speler?
    PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29: rekent op de volledige groepsstatistieken (alle
    tegenstander-opstellingen), niet op de bewaarde rijen.
    De SORTERING blijft ONGEWIJZIGD op de persoonlijke gemiddelde winkans
    (een persoonlijke, geen ploegmaatstaf).
    PADEL_ANALYSIS_POINT_PROBABILITY_BEST_FOR_PLAYER_2026-09-30: toont nu
    ERNAAST ook de PLOEG-puntenkans (2/1/0) van diezelfde opstelling (uit
    g["point_probs"], dezelfde gewogen berekening als de groepen hierboven)
    - puur INFORMATIEF, verandert de sortering niet."""
    if not groups or not sel_player_id:
        return
    sel_id = str(sel_player_id)
    sel_naam = name_lookup_global.get(sel_id, sel_id)
    rijen = []
    for g in groups:
        stats = g["players"].get(sel_id)
        if not stats:
            continue
        som, laagste, hoogste, n, team_som, team_n = stats
        gemiddeld = som / n
        posities = g["positions"].get(sel_id) or []
        pos_txt = " + ".join(
            f"R{rot}M{m_in_rot} met {name_lookup_global.get(partner, partner)}"
            for rot, m_in_rot, partner in posities
        )
        opstelling_txt = " \u00b7 ".join(
            f"R{idx // 2 + 1}M{idx % 2 + 1} "
            f"{name_lookup_global.get(str(a['our_pair'][0]), a['our_pair'][0])}/"
            f"{name_lookup_global.get(str(a['our_pair'][1]), a['our_pair'][1])}"
            for idx, a in enumerate(g["first_assignment"])
        )
        team_gemiddeld = (team_som / team_n) if team_n else None
        # PADEL_ANALYSIS_POINT_PROBABILITY_BEST_FOR_PLAYER_2026-09-30:
        # dezelfde gewogen ploeg-puntenkans als in de groepen hierboven.
        pp = g.get("point_probs") or {}
        rijen.append({
            "Gemiddelde winkans": round(gemiddeld * 100, 1),
            "Slechtste geval": round(laagste * 100, 1),
            "Beste geval": round(hoogste * 100, 1),
            "Team gemiddeld": round(team_gemiddeld, 2) if team_gemiddeld is not None else None,
            "Team Kans 2p %": round(pp.get("p2", 0.0) * 100, 0) if pp else None,
            "Team Kans 1p %": round(pp.get("p1", 0.0) * 100, 0) if pp else None,
            "Team Kans 0p %": round(pp.get("p0", 0.0) * 100, 0) if pp else None,
            f"Positie van {sel_naam}": pos_txt,
            "Volledige ploegopstelling": opstelling_txt,
            "Tegenstander-scenario's": n,
        })
    if not rijen:
        st.info(
            f"{sel_naam} komt in geen enkele doorgerekende opstelling voor - selecteer "
            "deze speler hierboven bij 'Beschikbare eigen spelers' om deze tabel te vullen."
        )
        return
    rijen.sort(key=lambda r: r["Gemiddelde winkans"], reverse=True)
    st.markdown(
        f'<div class="section-header">Beste opstelling voor {sel_naam}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Alle doorgerekende ploegopstellingen waarin **{sel_naam}** meespeelt, gerangschikt op "
        "de GEMIDDELDE persoonlijke winkans over ALLE tegenstander-opstellingen - dus robuust "
        "tegen een verrassing van de tegenstander. 'Slechtste geval' toont hoe diep die kans kan "
        "zakken als de tegenstander de voor ons ongunstigste opstelling kiest."
    )
    st.caption(
        "'Team gemiddeld' is het verwacht aantal gewonnen matchen voor de HELE ploeg (niet enkel "
        f"{sel_naam}) bij dezelfde opstelling; 'Team Kans 2p/1p/0p' is de bijhorende gewogen kans op "
        "2/1/0 competitiepunten voor de HELE ploeg - zo zie je meteen of een opstelling die goed is "
        f"voor {sel_naam} persoonlijk, ook goed is voor het team, of net een compromis vereist."
    )
    try:
        import pandas as _pd
        df = _pd.DataFrame(rijen)
        styled = df.style.background_gradient(
            subset=["Gemiddelde winkans"], cmap="RdYlGn", vmin=0, vmax=100,
        ).format({
            "Gemiddelde winkans": "{:.1f}%",
            "Slechtste geval": "{:.1f}%",
            "Beste geval": "{:.1f}%",
            "Team gemiddeld": lambda v: f"{v:.2f}" if v is not None else "-",
            "Team Kans 2p %": lambda v: f"{v:.0f}%" if v is not None else "-",
            "Team Kans 1p %": lambda v: f"{v:.0f}%" if v is not None else "-",
            "Team Kans 0p %": lambda v: f"{v:.0f}%" if v is not None else "-",
        })
        st.dataframe(
            styled, use_container_width=True, hide_index=True,
            column_config={
                "Gemiddelde winkans": st.column_config.NumberColumn("Gem. winkans", width="small"),
                "Slechtste geval": st.column_config.NumberColumn("Worst", width="small"),
                "Beste geval": st.column_config.NumberColumn("Best", width="small"),
                "Team gemiddeld": st.column_config.NumberColumn("Team gem.", width="small"),
                # PADEL_ANALYSIS_POINT_PROBABILITY_BEST_FOR_PLAYER_2026-09-30
                "Team Kans 2p %": st.column_config.NumberColumn("Team 2p", format="%.0f%%", width="small"),
                "Team Kans 1p %": st.column_config.NumberColumn("Team 1p", format="%.0f%%", width="small"),
                "Team Kans 0p %": st.column_config.NumberColumn("Team 0p", format="%.0f%%", width="small"),
                "Tegenstander-scenario's": st.column_config.NumberColumn("Scen.", width="small"),
                "Volledige ploegopstelling": st.column_config.TextColumn(
                    "Volledige ploegopstelling", width="large",
                ),
            },
        )
    except Exception:
        st.dataframe(rijen, use_container_width=True, hide_index=True)
    beste = rijen[0]
    team_val = beste.get("Team gemiddeld")
    team_txt = f", team gemiddeld **{team_val:.2f}**" if team_val is not None else ""
    # PADEL_ANALYSIS_POINT_PROBABILITY_BEST_FOR_PLAYER_2026-09-30
    team_p2 = beste.get("Team Kans 2p %")
    team_pp_txt = f", team kans op 2 punten **{team_p2:.0f}%**" if team_p2 is not None else ""
    st.success(
        f"Beste voor {sel_naam}: **{beste['Volledige ploegopstelling']}** "
        f"- gemiddeld **{beste['Gemiddelde winkans']:.1f}%** winkans "
        f"(slechtste geval {beste['Slechtste geval']:.1f}%){team_txt}{team_pp_txt}."
    )
    st.divider()
def _render_save_analysis_button(
    all_matchups: list, opp: dict, available_ids: list, name_lookup_global: dict,
    total_boards, max_per_player: dict, sel_player_id,
) -> None:
    """PADEL_ANALYSIS_SAVE_BUTTON_VISIBILITY_FIX_2026-09-27: uitgelicht in
    een eigen functie zodat de knop VROEG in de resultatensectie kan
    verschijnen (direct na "X geldige matchup(s) gevonden"), i.p.v. pas na
    de volledige tabel/groepen/AI-sectie - zie de uitgebreide toelichting
    bovenaan dit bestand. Payload/opslag-logica zelf: ONGEWIJZIGD."""
    # PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29: enkel de beste _SAVE_MAX_MATCHUPS (Firestore < 1 MB).
    all_matchups = list(all_matchups)[:_SAVE_MAX_MATCHUPS]
    if st.button(f"Deze analyse opslaan (beste {len(all_matchups)} matchups)", key=f"save_all_matchups_{opp['ploeg_id']}"):
        payload = {
            "opponent_name": opp.get("name"), "opponent_ploeg_id": opp.get("ploeg_id"),
            "own_player_ids": available_ids,
            "own_player_labels": [name_lookup_global.get(pid, pid) for pid in available_ids],
            "total_boards": int(total_boards), "max_per_player": max_per_player,
            "scenarios": [
                {
                    "s_idx": rank, "fixture_label": (
                        f"Matchup #{rank}" + (f" (zoals gespeeld op {', '.join(m['historical_labels'])})" if m["is_historical"] else "")
                        + ("" if m.get("fully_compliant", True) else " [niet-reglementaire variant]")
                    ),
                    "boards_count": len(m["assignment"]),
                    "options": [{
                        "total_score": m["total_score"], "expected_boards_won": m.get("expected_boards_won"),
                        "point_probs": m.get("point_probs"),
                        "assignment": [
                            {
                                "our_pair_labels": [name_lookup_global.get(a["our_pair"][0], a["our_pair"][0]), name_lookup_global.get(a["our_pair"][1], a["our_pair"][1])],
                                "synergy": a["synergy"], "edge": a["edge"], "win_probability": a.get("win_probability"),
                                "opponent_names": [p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]],
                            } for a in m["assignment"]
                        ],
                    }],
                } for rank, m in enumerate(all_matchups, start=1)
            ],
        }
        doc_id = fb.save_lineup_analysis(sel_player_id, payload)
        st.success(f"Analyse opgeslagen ({len(all_matchups)} matchups).")
def _model_weights_for_lineups(bundle: dict, unique_opponent_lineups: dict) -> tuple:
    """PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: voorspelde kans per
    tegenstander-scenario. Geeft (weights {key: kans}, stats) of (None, None)."""
    if olm is None or not unique_opponent_lineups:
        return None, None
    try:
        stats = olm.build_opponent_stats(bundle)
        roster = {str(p.get("user_id")) for p in (bundle.get("unique_players") or []) if p.get("user_id")}
        for key in unique_opponent_lineups:
            for pair in key:
                roster |= set(pair)
        roster_uids = sorted(roster)
        logs = {
            key: olm.full_lineup_log_score(stats, list(key), roster_uids)
            for key in unique_opponent_lineups
        }
        return olm.softmax_weights(logs), stats
    except Exception:  # noqa: BLE001
        return None, None
def _render_predicted_opponent_lineups(unique_opponent_lineups: dict, weights: dict, stats: dict) -> None:
    """PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: top 5 voorspelde
    tegenstander-opstellingen met kans + redenen (controleerbare weging)."""
    if not weights:
        return
    top = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top5_share = sum(w for _, w in top)
    with st.expander(
        f"Voorspelde tegenstander-opstellingen (statistisch model, op basis van "
        f"{stats.get('n_fixtures', 0)} eerdere ontmoeting(en))", expanded=False,
    ):
        st.caption(
            "Het model combineert 3 eenvoudige signalen uit hun eerdere ontmoetingen: wie speelt vaak "
            "mee, wie speelt vaak SAMEN, en wie speelt meestal Match 1 of Match 2. Die kans is het "
            "gewicht van elk scenario in de puntenkansen hieronder. "
            f"De top 5 hieronder samen: {top5_share * 100:.0f}% van het totale gewicht."
        )
        for key, w in top:
            info = unique_opponent_lineups[key]
            hist = f" - effectief gespeeld ({', '.join(info['historical_labels'])})" if info.get("is_historical") else ""
            st.write(f"**{w * 100:.1f}%** - {_format_opponent_lineup_label(info['boards'])}{hist}")
            redenen = []
            for r in range(0, len(key) - 1, 2):
                redenen += olm.explain_rotation(stats, key[r], key[r + 1], max_reasons=2)
            uniek = list(dict.fromkeys(redenen))[:3]
            if uniek:
                st.caption(" · ".join(uniek))
def _expected_matches_per_player(bundle: dict, chosen_ids: list, needed: int, max_per: int) -> dict:
    """PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: verwacht aantal matchen per tegenstander-
    speler. Basis = gemiddeld aantal matchen per ontmoeting (model-stats),
    herschaald naar `needed` (largest remainder) en begrensd op `max_per`.
    Zonder historiek: None (de aanroeper valt terug op gelijk verdelen)."""
    if olm is None or not chosen_ids:
        return None
    try:
        stats = olm.build_opponent_stats(bundle)
    except Exception:  # noqa: BLE001
        return None
    n_fix = stats.get("n_fixtures", 0)
    if n_fix <= 0:
        return None
    raw = {}
    for u in chosen_ids:
        gem = stats["slot_total"].get(u, 0) / n_fix
        raw[u] = gem if gem > 0 else 0.25  # nooit gezien: kleine kans
    totaal = sum(raw.values()) or 1.0
    doel = {u: min(max_per, v * needed / totaal) for u, v in raw.items()}
    out = {u: int(v) for u, v in doel.items()}
    rest = needed - sum(out.values())
    volgorde = sorted(doel, key=lambda u: doel[u] - int(doel[u]), reverse=True)
    i = 0
    while rest > 0 and i < 10 * len(volgorde):
        u = volgorde[i % len(volgorde)]
        if out[u] < max_per:
            out[u] += 1
            rest -= 1
        i += 1
    return out


def _filter_lineups_to_roster(unique_opponent_lineups: dict, chosen_ids: set, chosen_names: set) -> dict:
    """PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: enkel opstellingen waarvan ELKE speler (op
    id of naam) in de gekozen tegenstander-selectie zit."""
    def _ok(p):
        return str(p.get("user_id")) in chosen_ids or " ".join(str(p.get("name") or "").lower().split()) in chosen_names
    return {
        k: v for k, v in unique_opponent_lineups.items()
        if all(_ok(p) for b in v.get("boards") or [] for p in (b.get("opponent_pair") or []))
    }


def _render_all_valid_matchups(
    bundle, opp, available_ids, max_per_player, total_boards, synergy_fn,
    player_ratings, official_ranks_strict, opponent_ratings, report,
    name_lookup_global, sel_player_id, tournament_rules_dict=None, rules_label=None,
):
    st.divider()
    st.markdown('<div class="section-header">Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "ALLE reglementair geldige, rotatie-veilige combinaties van onze opstelling tegen hun "
        "opstelling, in EEN tabel - klik op een kolomkop om te sorteren. De opstelling die de "
        "tegenstander vorige keer effectief speelde is gemarkeerd in de kolom 'Vorige keer'."
    )
    # PADEL_ANALYSIS_NO_NONCOMPLIANT_2026-09-29: enkel reglementaire opstellingen (checkbox verwijderd).
    include_non_compliant = False
    historical_boards_with_labels = _historical_opponent_boards_list(bundle)
    st.markdown("##### Tegenstander-roster voor theoretische scenario's")
    st.caption(
        "Kies WIE van de tegenstander waarschijnlijk beschikbaar is. We berekenen dan ALLE mogelijke "
        "opstellingen die zij daaruit kunnen vormen (officiele regel: hun sterkste duo - som van "
        "klassementen, met padelstat als tie-breaker bij gelijkspel - op Match 1, per rotatie) en "
        "voegen die toe aan de tabel hieronder."
    )
    unique_players = bundle.get("unique_players", []) or []
    theoretical_boards: list = []
    if not unique_players:
        st.info("Nog geen tegenstander-spelers gekend om theoretische opstellingen voor te berekenen.")
    else:
        opp_labels = [p.get("name", "?") for p in unique_players]
        opp_label_to_id = {p.get("name", "?"): str(p.get("user_id")) for p in unique_players}
        default_opp_labels = opp_labels
        st.caption(
            f"Standaard staan alle {len(opp_labels)} bekende tegenstander-spelers geselecteerd, zodat ALLE "
            "mogelijke opstellingen automatisch worden meegenomen. Verklein de lijst enkel als je zeker weet "
            "dat bepaalde spelers niet zullen meespelen."
        )
        chosen_opp_labels = st.multiselect(
            "Beschikbare tegenstander-spelers", opp_labels, default=default_opp_labels,
            key=f"theoretical_opp_players_{opp['ploeg_id']}",
        )
        chosen_opp_ids = [opp_label_to_id[lbl] for lbl in chosen_opp_labels]
        needed = 2 * total_boards
        if len(chosen_opp_ids) < 2:
            st.info(
                "Selecteer minstens 2 tegenstander-spelers om theoretische scenario's toe te voegen. "
                "De historische opstelling(en) blijven sowieso al in de tabel staan."
            )
        else:
            chosen_opp_players = [p for p in unique_players if str(p.get("user_id")) in chosen_opp_ids]
            opponent_official_ranks = _opponent_official_ranks(chosen_opp_ids)
            missing_opp_official = [pid for pid in chosen_opp_ids if pid not in opponent_official_ranks]
            if missing_opp_official:
                opp_names = [p.get("name", str(p.get("user_id"))) for p in chosen_opp_players if str(p.get("user_id")) in missing_opp_official]
                st.caption(
                    f"Geen officieel klassement gekend voor: {', '.join(opp_names)} - behandeld als "
                    "'onbekende sterkte' bij het genereren van theoretische opstellingen."
                )
            opponent_padelstat_ratings = _opponent_padelstat_ratings(bundle)
            # PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: voorstel op basis van het model, anders gelijk verdeeld.
            max_per_opp = max(1, int(total_boards) // 2)
            default_opp_max = (
                _expected_matches_per_player(bundle, chosen_opp_ids, needed, max_per_opp)
                or _default_opponent_max_per_player(chosen_opp_ids, needed)
            )
            roster_sig_key = f"opp_roster_sig_{opp['ploeg_id']}"
            roster_signature = (tuple(sorted(chosen_opp_ids)), int(total_boards))
            if st.session_state.get(roster_sig_key) != roster_signature:
                prefix = f"opp_max_v2_{opp['ploeg_id']}_"
                for stale_key in [k for k in list(st.session_state) if str(k).startswith(prefix)]:
                    st.session_state.pop(stale_key, None)
                st.session_state[roster_sig_key] = roster_signature
            st.caption(
                f"Verwacht aantal wedstrijden per tegenstander-speler (verdeeld over {needed} "
                "benodigde plaatsen - een speler mag, net als bij ons, meerdere matchen spelen met "
                "verschillende partners, maar nooit 2 GELIJKTIJDIGE matchen binnen dezelfde rotatie). "
                "Het voorstel is het VERWACHTE aantal matchen per speler (gemiddelde uit hun eerdere ontmoetingen, "
                "herschaald naar het totaal) en wordt herberekend zodra je de selectie hierboven wijzigt:"
            )
            # PADEL_ANALYSIS_OPP_MAX_DERIVED_2026-10-03 (Kim: "De maximum aantal wedstrijden
            # bij de tegenstander is eigenlijk niet meer echt relevant omdat we met
            # scenario's werken. Je kan die eventueel wel nog tonen"): geen invoervelden
            # meer - het verwachte aantal matchen per speler wordt afgeleid (historiek,
            # anders gelijk verdeeld) en enkel getoond.
            opponent_max_per_player = {pid: int(default_opp_max.get(pid, 0)) for pid in chosen_opp_ids}
            if sum(opponent_max_per_player.values()) != needed:
                opponent_max_per_player = {
                    pid: min(v, max_per_opp)
                    for pid, v in _default_opponent_max_per_player(chosen_opp_ids, needed).items()
                }
            delen = []
            for pid in sorted(chosen_opp_ids, key=lambda u: -opponent_max_per_player.get(u, 0)):
                naam = next((p.get("name", pid) for p in chosen_opp_players if str(p.get("user_id")) == pid), pid)
                rk, ps = opponent_official_ranks.get(pid), opponent_padelstat_ratings.get(pid)
                info = " · ".join(x for x in [f"P{int(rk)}" if rk is not None else "P?",
                                              f"ps {int(ps)}" if ps is not None else ""] if x)
                delen.append(f"{naam} ({info}): **{opponent_max_per_player.get(pid, 0)}**")
            st.markdown("Verwacht aantal matchen per tegenstander-speler: " + " · ".join(delen))
            opp_total_slots = sum(opponent_max_per_player.values())
            if opp_total_slots != needed:
                st.error(
                    f"Som van tegenstander-plaatsen ({opp_total_slots}) moet gelijk zijn aan 2x wedstrijden "
                    f"({needed}). Pas de aantallen hierboven aan."
                )
            else:
                compute_key = f"theoretical_boards_{opp['ploeg_id']}"
                meta_key = f"theoretical_boards_meta_{opp['ploeg_id']}"
                sig_key = f"theoretical_boards_sig_{opp['ploeg_id']}"
                signature = (tuple(sorted(chosen_opp_ids)), tuple(sorted(opponent_max_per_player.items())), int(total_boards))
                if st.session_state.get(sig_key) != signature:
                    lineups, meta = _generate_theoretical_opponent_boards_with_repeats(
                        chosen_opp_players, opponent_max_per_player, opponent_official_ranks,
                        opponent_padelstat_ratings, _THEORETICAL_MAX_VARIANTS,
                    )
                    st.session_state[compute_key] = lineups
                    st.session_state[meta_key] = meta
                    st.session_state[sig_key] = signature
                theoretical_boards = st.session_state.get(compute_key) or []
                meta = st.session_state.get(meta_key) or {"total_theoretical": 0, "truncated": False}
                st.caption(f"**{meta['total_theoretical']}** theoretische tegenstander-opstellingen mogelijk met deze verdeling.")
                if meta["truncated"]:
                    st.warning(f"Enkel de eerste {_THEORETICAL_MAX_VARIANTS} van {meta['total_theoretical']} worden berekend.")
    unique_opponent_lineups = _collect_unique_opponent_lineups(historical_boards_with_labels, theoretical_boards)
    # PADEL_ANALYSIS_ROSTER_AND_GROUPS_2026-10-03: niet-geselecteerde spelers -> opstelling weg.
    gekozen_namen = st.session_state.get(f"theoretical_opp_players_{opp['ploeg_id']}")
    if unique_players and gekozen_namen is not None:
        gekozen_ids = {str(p.get("user_id")) for p in unique_players if p.get("name", "?") in set(gekozen_namen)}
        gekozen_norm = {" ".join(str(n).lower().split()) for n in gekozen_namen}
        n_voor = len(unique_opponent_lineups)
        unique_opponent_lineups = _filter_lineups_to_roster(unique_opponent_lineups, gekozen_ids, gekozen_norm)
        if len(unique_opponent_lineups) < n_voor:
            st.caption(
                f"{n_voor - len(unique_opponent_lineups)} opstelling(en) weggelaten omdat er een niet-geselecteerde "
                "tegenstander-speler in staat (ook eerder effectief gespeelde opstellingen)."
            )
    if not unique_opponent_lineups:
        st.info("Nog geen tegenstander-opstelling gekend of berekend om tegen te analyseren.")
        return []
    # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: voorspelde kans per scenario.
    model_weights, model_stats = _model_weights_for_lineups(bundle, unique_opponent_lineups)
    if model_weights:
        _render_predicted_opponent_lineups(unique_opponent_lineups, model_weights, model_stats)
    # PADEL_ANALYSIS_SCENARIO_MATRIX_2026-10-03 - zie moduledocstring.
    if lsm is not None:
        try:
            lsm.render_scenario_matrix(
                unique_opponent_lineups, model_weights, available_ids, max_per_player,
                int(total_boards), synergy_fn, player_ratings, official_ranks_strict,
                opponent_ratings, tournament_rules_dict, name_lookup_global, str(opp["ploeg_id"]),
                model_stats=model_stats,
            )
        except Exception as exc:  # noqa: BLE001 - nooit de rest van de pagina breken
            st.warning(f"Scenario-analyse mislukt: {type(exc).__name__}: {exc}")
    settings_signature = (
        tuple(sorted(available_ids)),
        tuple(sorted(max_per_player.items())),
        int(total_boards),
        tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
        frozenset(unique_opponent_lineups.keys()),
    )
    ratings_signature = (
        tuple(sorted(player_ratings.items())),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(opponent_ratings.items())),
    )
    signature = (settings_signature, ratings_signature)
    # PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29: nieuwe sleutels - het resultaat heeft nu 5 delen.
    # PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: opnieuw nieuwe sleutels (v3), want elke matchup/groep
    # heeft nu ook "point_probs" - een oud, gecachet resultaat zonder dat veld zou de nieuwe kolommen
    # als "onbekend" tonen i.p.v. echt herberekend te worden.
    # PADEL_ANALYSIS_OPPONENT_LINEUP_MODEL_2026-10-02: v4 - andere weging.
    result_key = f"scenario_result_v4_{opp['ploeg_id']}"
    sig_key = f"scenario_result_sig_v4_{opp['ploeg_id']}"
    clicked = st.button(
        "Bereken alle geldige matchups", type="primary", key=f"compute_scenarios_{opp['ploeg_id']}",
        help="Berekent pas NA deze klik - wijzig gerust eerst alle instellingen hierboven zonder dat de "
             "pagina telkens opnieuw moet rekenen.",
    )
    if clicked:
        with st.spinner(f"Alle geldige matchups doorrekenen ({len(unique_opponent_lineups)} tegenstander-opstelling(en))..."):
            st.session_state[result_key] = _build_all_valid_matchups(
                unique_opponent_lineups, available_ids, max_per_player, synergy_fn,
                player_ratings, official_ranks_strict, opponent_ratings, tournament_rules_dict,
                include_non_compliant_variants=include_non_compliant,
                opponent_weight_override=model_weights,
            )
            st.session_state[sig_key] = signature
    stored = st.session_state.get(result_key)
    if stored is None:
        st.info("Stel hierboven alles in en klik op **'Bereken alle geldige matchups'** om de tabel te vullen.")
        return []
    stored_signature = st.session_state.get(sig_key)
    if stored_signature != signature:
        stored_settings = stored_signature[0] if stored_signature else None
        if stored_settings != settings_signature:
            st.warning(
                "De instellingen zijn gewijzigd sinds de laatste berekening - de tabel hieronder toont nog "
                "het VORIGE resultaat. Klik opnieuw op 'Bereken alle geldige matchups' om bij te werken."
            )
        else:
            st.warning(
                "De padelstat- en/of klassementwaarden zijn intussen ververst op de achtergrond sinds je "
                "laatste berekening - de tabel hieronder klopt dus mogelijk niet meer met de actuele data. "
                "Klik opnieuw op 'Bereken alle geldige matchups' om de analyse bij te werken."
            )
    all_matchups, truncated, total_seen, build_diag, groups = stored
    st.divider()
    n_hist = len(historical_boards_with_labels)
    n_theo = len(theoretical_boards)
    with st.expander("Diagnostiek: hoeveel combinaties werden er precies doorgerekend?", expanded=False):
        st.write(f"- Rotatie-veilige eigen koppelverdelingen (totaal enumereerd): **{build_diag['own_structures_total']}**")
        st.write(f"- Daaruit gegenereerde volgorde-varianten (incl. eventuele swap-varianten): **{build_diag['own_variants_generated']}**")
        st.write(f"- Daarvan uitgesloten door de reglementaire puntengrens: **{build_diag['own_excluded_by_rules']}**")
        st.write(f"- Reglementair geldige eigen combinaties (puntengrens OK): **{build_diag['own_valid']}**")
        st.write(f"- Historische tegenstander-opstellingen (al gespeeld dit seizoen): **{n_hist}**")
        st.write(f"- Theoretische tegenstander-opstellingen (uit de gekozen roster hierboven): **{n_theo}**")
        st.write(f"- Unieke tegenstander-opstellingen na samenvoegen (dubbels verwijderd): **{len(unique_opponent_lineups)}**")
        st.write(f"- Totaal doorgerekende matchup-kandidaten (voor ontdubbeling): **{total_seen}**")
        st.write(f"- Effectief doorgerekende matchups: **{build_diag.get('matchups_computed', 0)}**")
        st.write(f"- Unieke eigen opstellingen (groepen): **{build_diag.get('own_groups', 0)}**")
        st.write(f"- Bewaarde rijen (beste {_KEEP_PER_GROUP} + slechtste + historische per groep): **{len(all_matchups)}**")
        st.caption(
            "Puntenkans en de weging op historische tegenstander-opstellingen: zie de uitleg boven "
            "'Onze opstellingen' hieronder."
        )
        if n_theo == 0 and unique_players:
            st.warning(
                "Er werden 0 theoretische tegenstander-opstellingen meegenomen - controleer of hierboven "
                "voldoende tegenstander-spelers geselecteerd staan."
            )
    if truncated:
        st.warning(
            f"Meer dan {_MAX_COMPUTED_MATCHUPS:,} combinaties - de berekening werd daar gestopt. "
            "Verklein de spelersselectie of het tegenstander-roster voor een volledige dekking."
        )
    # PADEL_ANALYSIS_MATCHUPS_ALL_OWN_LINEUPS_2026-09-29: eerlijk aantal (alle eigen opstellingen doorgerekend).
    st.caption(
        f"**{build_diag.get('matchups_computed', 0):,}** matchups doorgerekend over "
        f"**{build_diag.get('own_groups', 0)}** eigen opstellingen, gesorteerd van hoogste naar laagste "
        "gewogen kans op 2 punten."
    )
    if not all_matchups:
        st.info(
            "Geen enkele matchup voldoet aan de reglementaire puntengrens per rotatie, of er is geen "
            "combinatie mogelijk zonder een speler dubbel in dezelfde rotatie te plaatsen. Controleer de "
            "gekozen afdeling en het aantal beschikbare spelers."
        )
        return []
    # PADEL_ANALYSIS_SAVE_BUTTON_VISIBILITY_FIX_2026-09-27: de "Analyse
    # opslaan"-knop staat nu HIER, meteen zodra all_matchups bevestigd
    # niet-leeg is - VOOR de zware rendering hieronder (gegroepeerde
    # opstellingen, "Beste voor..."-tabel, platte tabel, AI-sectie). Zie
    # de uitgebreide toelichting bovenaan dit bestand.
    _render_save_analysis_button(
        all_matchups, opp, available_ids, name_lookup_global, total_boards, max_per_player, sel_player_id,
    )
    st.divider()
    _render_own_lineup_groups_with_opponents(groups, name_lookup_global, ploeg_key=str(opp['ploeg_id']))
    _render_best_for_selected_player(groups, sel_player_id, name_lookup_global)
    with st.expander("Platte tabel (alle matchups los naast elkaar, sorteerbaar per kolom)", expanded=False):
        show_all_key = f"all_matchups_showall_{opp['ploeg_id']}"
        show_all = st.checkbox(
            f"Toon alle {len(all_matchups)} matchups (i.p.v. de beste {_MATCHUP_DISPLAY_DEFAULT_N})",
            key=show_all_key,
        ) if len(all_matchups) > _MATCHUP_DISPLAY_DEFAULT_N else False
        display_matchups = all_matchups if show_all else all_matchups[:_MATCHUP_DISPLAY_DEFAULT_N]
        table_rows, board_column_names = _matchups_to_table_rows(display_matchups, name_lookup_global)
        column_config, column_order = _matchup_table_column_config(table_rows, board_column_names)
        st.dataframe(
            table_rows, use_container_width=True, hide_index=True,
            column_config=column_config, column_order=column_order,
        )
        st.caption(
            "Elk speler-duo staat in zijn eigen kolom ('Ons duo' / 'Tegenstander'), naast een aparte "
            "winkans-kolom per match. 'Kans 2p/1p/0p' toont de exacte kans op dat aantal competitiepunten "
            "voor DEZE ene tegenstander-opstelling (dus ongewogen - de weging over alle scenario's zit "
            "enkel in de groepstitel hierboven). 'Rotatie1 M1' = Match 1 van rotatie 1 (sterkste duo volgens "
            "officieel klassement, art. 6.6), 'Rotatie1 M2' = Match 2, enz. De kolom 'Toelichting' toont de "
            "exacte officiele puntensom per duo die deze volgorde bepaalt (nooit de padelstat-score)."
        )
        if not show_all and len(all_matchups) > len(display_matchups):
            st.caption(f"Beste {len(display_matchups)} van {len(all_matchups)} matchups getoond - vink hierboven aan om alles te zien.")
    st.divider()
    ai_history_key = f"all_matchups_chat_history_v2_{opp['ploeg_id']}"
    if ai_history_key not in st.session_state:
        st.session_state[ai_history_key] = []
    ai_history = st.session_state[ai_history_key]
    if taa is not None and report is not None:
        col_ai_start, col_ai_clear = st.columns([3, 1])
        with col_ai_start:
            ai_start_label = "AI-inzicht over de beste matchups" if not ai_history else "AI-inzicht opnieuw genereren (nieuw gesprek)"
            if st.button(ai_start_label, key=f"all_matchups_ai_{opp['ploeg_id']}"):
                with st.spinner("AI analyseert..."):
                    try:
                        antwoord = taa.analyze_lineup_options(report, display_matchups[:5], name_lookup_global)
                    except Exception as exc:
                        antwoord = f"Mislukt: {exc}"
                st.session_state[ai_history_key] = [{"role": "assistant", "content": antwoord}]
                st.rerun()
        with col_ai_clear:
            if ai_history and st.button("Nieuw gesprek", key=f"all_matchups_ai_clear_{opp['ploeg_id']}"):
                st.session_state[ai_history_key] = []
                st.rerun()
        if ai_history:
            st.caption("Gesprek tot nu toe:")
            for msg in ai_history:
                role_label = "Jij" if msg["role"] == "user" else "AI"
                with st.container(border=True):
                    st.markdown(f"**{role_label}**")
                    st.markdown(msg["content"])
            followup_question = st.text_area(
                "Doorvraag", key=f"all_matchups_ai_followup_{opp['ploeg_id']}", height=70,
                label_visibility="collapsed", placeholder="Bv. En wat als Nico niet kan spelen?",
            )
            if st.button("Vraag door", key=f"all_matchups_ai_followup_btn_{opp['ploeg_id']}"):
                if not followup_question.strip():
                    st.warning("Typ eerst een vraag.")
                else:
                    with st.spinner("AI denkt na..."):
                        try:
                            vervolg = taa.analyze_lineup_options(
                                report, display_matchups[:5], name_lookup_global, history=ai_history,
                            )
                        except Exception as exc:
                            vervolg = f"Mislukt: {exc}"
                    st.session_state[ai_history_key] = ai_history + [
                        {"role": "user", "content": followup_question.strip()},
                        {"role": "assistant", "content": vervolg},
                    ]
                    st.rerun()
    return all_matchups
