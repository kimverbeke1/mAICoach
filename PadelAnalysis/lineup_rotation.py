"""
lineup_rotation.py - Rotatieplanner: combinatoriek, bordvolgorde-regels
(art. 6.6 + padelstat-tiebreak), best/worst-case-variantenumeratie, en de
matchup-berekening per bord.
Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
Zie de oorspronkelijke, monolithische versie van page_lineup_lab.py voor de
volledige historische toelichting bij elke fix in deze functies - dit
bestand is functioneel ONGEWIJZIGD t.o.v. die vorige versie.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29 (op verzoek van Kim: "aantal matchen per ontmoeting in
rotaties is gedefinieerd normaal via het reglement. die parameters zijn niet
direct zichtbaar daar maar in de najaarsinterclub zijn het dus 2 rotaties
van 2 matchen.")
--------------------------------------------------------------------------
Het formaat van een ontmoeting staat in het reglement en is NIET af te
lezen op de TVL-pagina's die we scrapen. Tot nu toe raadde de app het
aantal matchen uit eerdere uitslagenbladen, met 6 als terugval - fout voor
de najaarsinterclub. De constanten hieronder zijn nu de ENIGE bron van
waarheid; page_lineup_lab.py, lineup_sandbox.py en team_ai_advisor.py
lezen ze hier. Bij een ander formaat (bv. een andere periode) volstaat het
deze drie regels aan te passen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29 (op verzoek van Kim: "zorg dat je bij de opstelling
aantal rotaties kan instellen. zal handig zijn voor in voorjaar waar het dan
3 rotaties is")
--------------------------------------------------------------------------
ROTATIONS_PER_ENCOUNTER is nu enkel de STANDAARDWAARDE (najaar: 2). Het
effectieve aantal rotaties wordt op de Opstelling-analyse-pagina gekozen
(page_lineup_lab.py) en doorgegeven aan de matchup-tabel, de
rotatieplanner en de sandbox. MATCHES_PER_ROTATION (2 matchen tegelijk per
rotatie) blijft vast.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29 (op verzoek van Kim)
--------------------------------------------------------------------------
De rotatieplanner kiest per rotatie nu EXACT 2 koppels uit de beschikbare
spelers, i.p.v. alle geselecteerde spelers in koppels te verdelen. Zie
_generate_rotation_candidates() voor de details. De oude hulpfuncties
(_count_perfect_matchings, _expand_tied_orderings) blijven staan maar
worden door de planner niet meer gebruikt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30 (op verzoek van Kim, na
brainstorm over de matchup-analyse: "puntensysteem. 0 bij verlies, 1 bij
gelijkspel en 2 bij winst" + "opoffer"-scenario's + weging op historische
tegenstander-opstellingen)
--------------------------------------------------------------------------
ROOT CAUSE van "3 bijna-identieke resultaten" (Kim's voorbeeld: Best 2.05 /
2.05 / 2.03): de matchup-tabel middelde elke eigen opstelling over ALLE
mogelijke tegenstander-opstellingen alsof die allemaal even waarschijnlijk
zijn, en gebruikte als maatstaf "verwacht aantal gewonnen matchen" (EBW) -
een getal dat niet zegt of dat een veilige 3-1 is of een muntstuk tussen
2-2 en 3-1.
FIX, twee nieuwe bouwstenen, VOLLEDIG LOS van de bestaande EBW-logica (die
blijft bestaan, ongewijzigd, als secundair/tiebreak-getal):
  1. _match_outcome_point_probabilities(win_probs) - NIEUW. Neemt de 4
     (of n) individuele winkansen van 1 opstelling tegen 1 specifiek
     tegenstander-scenario, en berekent EXACT (geen simulatie - bij 4
     onafhankelijke kansen zijn er maar 16 combinaties) de kans op elke
     mogelijke uitslag, opgeteld tot puntensysteem 0/1/2 (Kim, bevestigd
     2026-09-30: 0 bij verlies, 1 bij gelijkspel/2-2, 2 bij winst - dus
     MEER matchen gewonnen dan de tegenstander = 2, gelijk aantal = 1,
     MINDER = 0). Ontbrekende winkansen (None) worden behandeld als 50%
     voor deze berekening ALLEEN (net als een neutrale muntworp) - de
     aanroeper kan aan de hand van _n_missing_win_probs() zien hoeveel dat
     er waren, om desgewenst te waarschuwen.
  2. Weging van tegenstander-scenario's: elk "unique_opponent_lineups"-item
     (uit lineup_rotation._collect_unique_opponent_lineups(), dit seizoen)
     krijgt een gewicht i.p.v. gelijk te tellen - zie
     _opponent_lineup_weight(). Een lineup die de tegenstander al N keer
     zo speelde (in _dezelfde_ rotatie-positie: rotatie 1 blijft apart van
     rotatie 2, want dat is een ander tactisch signaal) weegt zwaarder dan
     een louter theoretische, nooit geobserveerde combinatie. AL het
     gewicht komt uit dit SEIZOEN (bundle.previous_fixtures) - "alle
     seizoenen" was Kim's uiteindelijke voorkeur, maar de app heeft op dit
     moment GEEN betrouwbare rotatiepositie-informatie over vorige
     seizoenen (enkel round_text zoals "poule - 5", geen rotatienummer).
     Zie de uitgebreide toelichting hierover in het gesprek van
     2026-09-30 (Kim akkoord: "optie 1" = nu bouwen met dit seizoen,
     architectuur zo dat vorige seizoenen er later gewoon bij kunnen).
     _opponent_lineup_weight() is BEWUST de enige plek die dit bepaalt,
     zodat een latere uitbreiding (vorige-seizoenen-data erbij) hier
     lokaal blijft.
  3. _aggregate_group_point_probabilities(rows, weights) - combineert de
     per-scenario resultaten van 1 groep (1 eigen opstelling) tot een
     GEWOGEN gemiddelde kans op 2/1/0 punten over alle doorgerekende
     tegenstander-scenario's van die groep. Dit wordt het NIEUWE
     hoofdgetal in lineup_matchup_table.py; de bestaande best/worst-EBW
     blijft daarnaast zichtbaar als secundair getal.
Niets van het bovenstaande verandert de REGLEMENT-laag (bordvolgorde,
puntengrens per rotatie - art. 6.6/2.1) of de bestaande EBW/win_probability-
berekening: dit is een PARALLELLE, aanvullende maatstaf.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30 (op verzoek van Kim: "Drie
beslissingskaarten + vastpinnen. Per rotatie tonen we niet 6+ rijen met
bijna-gelijke scores, maar maximaal 3 aanbevolen kaarten [...] koppelkeuze,
kans op winst van die match, impact op kans op totale ploegresultaat, korte
risiconotitie. De Rotatieplanner heeft al een vastpin-mechanisme
(locked_rotations) - dat hergebruiken we, alleen de kaarten en de sortering
veranderen.")
--------------------------------------------------------------------------
De rotatieplanner toonde tot nu toe een st.radio met ALLE (tot 15)
kandidaten als platte tekstregels, gerangschikt op EBW - exact het
"6+ bijna-identieke rijen"-probleem dat PADEL_ANALYSIS_POINT_PROBABILITY_
2026-09-30 hierboven al voor de matchup-tabel oploste, maar hier nog niet.
FIX, hergebruikt VOLLEDIG de bestaande punten-kans-infrastructuur
hierboven (_match_outcome_point_probabilities, _n_missing_win_probs) -
geen nieuwe kansberekening, enkel een nieuwe TOEPASSING ervan:
1. "Impact op het totale ploegresultaat" (niet enkel deze ene rotatie):
   _rank_and_label_candidates_for_cards() bouwt per kandidaat de volledige
   winkans-lijst van de ontmoeting: [reeds BEVESTIGDE rotaties se
   winkansen] + [deze kandidaat se 2 winkansen] + [nog niet geplande
   rotaties, als PLACEHOLDER]. _match_outcome_point_probabilities()
   behandelt elke onbekende/placeholder-waarde al automatisch als 50%
   (neutrale muntworp) - dat is dus PRECIES het gedrag dat "nog te plannen
   rotaties" nodig hebben, zonder enige nieuwe aanname te hoeven bouwen.
   NIEUW om dit mogelijk te maken: `locked_win_probs_key` (session_state)
   houdt naast locked_rotations/locked_opponents ook de effectief gebruikte
   winkansen per BEVESTIGDE rotatie bij (2 per rotatie, of [None, None] als
   toen geen tegenstander gekozen was) - dit bestond nog niet.
2. Drie kaarten i.p.v. een platte lijst van tot 15 opties:
   - "Aanbevolen": hoogste impact op de kans op 2 ploegpunten (P(2p)) voor
     de HELE ontmoeting - dit is dus NIET noodzakelijk de kandidaat met de
     hoogste EBW voor deze ene rotatie; net dat verschil maakt "opoffer"-
     achtige keuzes (bewust een zware match verliezen om de kans op
     ploegwinst elders te maximaliseren) zichtbaar i.p.v. weggefilterd.
   - "Veiligst": onder de kandidaten met BEIDE winkansen gekend, de
     kandidaat met de HOOGSTE MINIMALE winkans (vermijdt een bijna zekere
     nederlaag op 1 van de 2 matchen van deze rotatie).
   - "Alternatief": de eerstvolgende kandidaat (op impact P(2p)) met een
     ANDERE koppelverdeling dan de 2 kaarten hierboven (dedupe op de set
     van koppels, ongeacht bordvolgorde) - zodat de 3 kaarten een echt
     ander PROFIEL tonen, niet 3x hetzelfde koppel in een andere volgorde.
   Minder dan 3 zinvol te onderscheiden kandidaten -> minder kaarten, nooit
   een crash of een lege/dubbele kaart.
3. Risiconotitie per match: HERGEBRUIKT ll.risk_note_for_probability(),
   dezelfde functie die de rest van de app al gebruikt (_compute_matchup,
   _render_assignment_with_outcome) - geen nieuwe, inconsistente
   risico-schaal.
4. Vastpinnen: ONGEWIJZIGD hergebruikt. Een kaart-knop "Kies deze kaart"
   doet exact wat de oude "Bevestig rotatie N"-knop deed (toevoegen aan
   locked_key/opp_locked_key + st.rerun(scope="fragment")), enkel nu ook
   met het toevoegen aan het nieuwe locked_win_probs_key. De "Rotatie N
   wijzigen"-knop (hierboven, ONGEWIJZIGD in structuur) is uitgebreid zodat
   ze ook locked_win_probs_key mee terugdraait - anders zou een gewijzigde
   rotatie een verweesde, verouderde winkans-invoer achterlaten.
5. Voor wie toch de VOLLE lijst van tot 15 kandidaten wil zien (of een
   optie buiten de 3 kaarten wil kiezen): een expander "Alle N combinaties
   (geavanceerd)" met exact de oude radio+detail+"Bevestig rotatie N"-flow,
   ONGEWIJZIGD - dus geen functionaliteit verloren, enkel het STANDAARD
   pad is nu de 3 kaarten.
De AI-sectie (analyze_lineup_options op candidates[:5]) blijft ONGEWIJZIGD
werken op de volledige kandidatenlijst, niet enkel de 3 getoonde kaarten.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_CARDS_NEUTRAL_LABEL_2026-09-30 (op verzoek van Kim,
na het testen van de vorige versie: "31% 2p 38% 1p 31% 0p" zag er verdacht
uniform uit op alle 3 kaarten)
--------------------------------------------------------------------------
BEVESTIGD, geen bug: bij 4 matchen die elk nog volledig onbekend zijn
(geen enkele rotatie bevestigd, geen enkele winkans gekend), valt
_match_outcome_point_probabilities() voor elke ontbrekende match terug op
50% - het WISKUNDIG CORRECTE resultaat is dan exact C(4,2) x 0.5^4 = 37.5%
kans op 1 punt en symmetrisch 31.25%/31.25% voor 2/0 punten, ONGEACHT welke
kandidaat je bekijkt (elke kandidaat is dan even "onbekend"). Het getal was
dus niet fout, maar MISLEIDEND: het oogt als een onderscheidend resultaat
terwijl het in werkelijkheid "nog niets zinvols bekend" betekent.
FIX: _format_point_probs_short() en de kaart-caption in
_render_candidate_card() tonen nu expliciet "(nog neutraal - tegenstander
onbekend)" zodra de impact-berekening op ENKEL placeholders/onbekende
winkansen steunt (gedetecteerd via een nieuwe `is_neutral`-vlag op de
kaart, gezet in _rank_and_label_candidates_for_cards()) - i.p.v. de kansen
zonder context te tonen alsof ze al onderscheidend zijn.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_PLANNER_PRESETS_2026-09-30 (op verzoek van Kim,
bevestigd plan: "Snelkeuzes bovenaan, per rotatie: 'Zelfde opstelling als
vorige match X' (elke eerdere ontmoeting als aparte optie, geen lange
dropdown-lijst), plus eventueel andere zinvolle presets (bv. 'sterkste
bekende opstelling', 'meest recente')." + "Custom-modus: klik spelers een
voor een aan. Voor Match 1 worden enkel spelers getoond die volgens de
puntengrens daar mogen staan [...] Een gekozen speler bij Match 1
verdwijnt meteen uit de keuzelijst van Match 2." + "Rotatie 2 houdt
automatisch rekening met wie al samen speelde in Rotatie 1.")
--------------------------------------------------------------------------
LET OP: deze bouwsteen bleek een MISVERSTAND - zie
PADEL_ANALYSIS_ROTATION_OPPONENT_PRESETS_2026-09-30 VERDEROP, die
"1. SNELKEUZES" hieronder VERVANGT. De beschrijving hieronder blijft staan
als historisch record van WAT er eerst gebouwd was en WAAROM dat fout was;
"2. CUSTOM-MODUS" bleef ongewijzigd en klopt nog steeds.
1. SNELKEUZES (OUD, VERVANGEN - _own_previous_encounters_as_presets +
   _strongest_available_pairing, getoond via _render_rotation_quick_presets()):
   - Elke eerdere EIGEN ontmoeting van sel_player_id (via _load_encounter_
     index/ll.list_encounters/ll.reconstruct_boards - DEZELFDE functies die
     lineup_sandbox.py al gebruikt voor zijn "Onze vorige opstelling"-
     preset) wordt als EIGEN knop getoond, niet als dropdown - meest
     recente eerst (ll.list_encounters() sorteert al datum-aflopend, dus
     geen eigen datumsortering nodig). Per ontmoeting wordt enkel het stuk
     getoond dat bij de EERSTVOLGENDE rotatie hoort (board-index //
     MATCHES_PER_ROTATION).
   - "Sterkste beschikbare (Elo)": de 4 hoogst-gewaardeerde beschikbare
     spelers (player_ratings, terugval official_ranks_strict), simpel
     gesorteerd gepaard (1+2, 3+4) - een snelle, deterministische keuze.
   - Elke preset wordt, VOOR hij als knop verschijnt, gevalideerd: alle 4
     spelers moeten in `available_ids` zitten, budget > 0 hebben (indien
     player_budget gezet is), en het koppel mag niet al in `excluded_pairs`
     zitten. Ontbreekt iets, dan wordt de preset stil overgeslagen (met een
     opgeteld "N presets overgeslagen"-melding) i.p.v. een kapotte knop te
     tonen.
   - Een geldige preset-rotatie gaat VOOR het tonen nog door
     _rotation_order_variants() (DEZELFDE reglement-check als de rest van
     dit bestand: sterkste-eerst + puntengrens) - een preset die de
     puntengrens van de gekozen afdeling schendt, wordt dus NIET aangeboden
     (met uitleg waarom), in plaats van een ongeldige knop te tonen.
   - Klikken op een preset-knop berekent de winkansen tegen
     effective_opponent_boards (_compute_matchup, zelfde pad als de
     kaarten/"geavanceerd") en bevestigt de rotatie via DEZELFDE
     _bevestig_rotatie()-closure als de kaarten - dus identieke
     locked_rotations/locked_opponents/locked_win_probs-boekhouding.
   PROBLEEM (zie correctie verderop): dit toonde presets van ONZE EIGEN
   vorige opstellingen, ongeacht wie de tegenstander was - niet bruikbaar
   om te bepalen wat WIJ tegen DEZE specifieke tegenstander moeten doen.
2. CUSTOM-MODUS, klik-voor-klik (_render_custom_click_builder()) - BLIJFT
   ONGEWIJZIGD, zie de functie zelf verderop voor de volledige werking:
   HERGEBRUIKT de reeds berekende `candidates`-lijst (dezelfde lijst als de
   3 kaarten en de "geavanceerd"-radio) IN PLAATS VAN de puntengrens-logica
   te herimplementeren - elke candidate is al een volledig gevalideerde
   rotatie (reglement-volgorde + puntengrens + excluded_pairs + player_
   budget, precies zoals _generate_rotation_candidates() die opbouwt).
Beide bouwstenen staan in een eigen "Snelkeuzes" / "Zelf samenstellen"-
expander, VOOR de bestaande 3 kaarten - kiest de gebruiker niets in een van
beide, dan werken de kaarten en de "geavanceerd"-lijst exact zoals voorheen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PRESET_CONFIRM_ARITY_FIX_2026-09-30 (op verzoek van Kim:
"snelkeuze geeft TypeError [...] on_confirm(ordered_pairs, win_probs)" in
_render_rotation_quick_presets() regel 740)
--------------------------------------------------------------------------
ECHTE BUG, bevestigd: `_bevestig_rotatie()` (in _render_rotation_planner())
verwacht 3 argumenten (gekozen_pairs, opp_pairs_voor_log,
win_probs_deze_rotatie). De kaarten-knop riep ze correct met 3 argumenten
aan; de nieuwe _render_rotation_quick_presets() EN _render_custom_click_
builder() riepen `on_confirm(ordered_pairs, win_probs)` aan met slechts 2 -
`opp_pairs_voor_log` ontbrak, wat een TypeError gaf zodra een gebruiker een
preset of een custom-combinatie effectief bevestigde. Een render zonder
klik op "Kies"/"Bevestig" faalde niet, vandaar dat dit niet meteen opviel.
FIX: `_render_rotation_planner()` geeft nu een kleine wrapper-closure
`_on_confirm_2arg(ordered_pairs, win_probs)` door aan zowel
_render_rotation_quick_presets() als _render_custom_click_builder() in
plaats van rechtstreeks `_bevestig_rotatie` - deze wrapper vult
`opp_pairs_voor_log` (al berekend, identiek aan wat de kaarten-knop
gebruikt) automatisch aan en roept dan `_bevestig_rotatie()` met alle 3 de
argumenten aan. De kaarten-knop blijft ONGEWIJZIGD rechtstreeks
`_bevestig_rotatie()` met 3 argumenten aanroepen (die had immers al de
juiste arity). Getest: beide nieuwe paden bevestigen nu zonder
TypeError, met exact dezelfde locked_rotations/locked_opponents/locked_
win_probs-boekhouding als de kaarten.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_OPPONENT_PRESETS_2026-09-30 (op verzoek van Kim:
"je hebt de snelkeuzes bij de rotatieplanner verkeerd begrepen. ik wil
snelkeuzen van de tegenstander en dan bekijken wat wij daartegen kunnen
doen. nu zijn het snelkeuzes van mijn matchen")
--------------------------------------------------------------------------
CORRECTIE op PADEL_ANALYSIS_ROTATION_PLANNER_PRESETS_2026-09-30 hierboven:
de "Snelkeuzes"-sectie toonde presets van ONZE EIGEN vorige opstellingen
(_own_previous_encounters_as_presets, _strongest_available_pairing,
_render_rotation_quick_presets) - dat beantwoordt niet Kim's vraag.
Kim wil: snel de TEGENSTANDER-opstelling van een eerdere ontmoeting
invullen (i.p.v. 2x apart een koppel uit een lange dropdown te moeten
kiezen in "Wie stelt de tegenstander op..." hierboven), en dan zien wat
WIJ daar het beste tegenover kunnen zetten - dat laatste deel gebeurt al
automatisch zodra de tegenstander-opstelling gekend is (de 3 kaarten en
"Zelf samenstellen" rekenen dan al tegen die specifieke tegenstander).
FIX, VOLLEDIG VERWIJDERD (niet enkel verborgen, zie hieronder waarom):
  - _own_previous_encounters_as_presets(), _strongest_available_pairing(),
    _rotation_matches_format(), _eligible_presets(),
    _render_rotation_quick_presets() - allemaal verwijderd. Ze waren enkel
    gebouwd voor, en enkel gebruikt door, de foute "Snelkeuzes"-sectie op
    basis van ONZE eigen opstellingen - nergens anders in de app gebruikt,
    dus veilig te verwijderen i.p.v. dode code te laten liggen.
NIEUW, in de plaats:
  - _opponent_rotation_presets(bundle, next_rotation_num, pair_label_fn,
    known_labels): geeft per eerdere ontmoeting TEGEN DEZE tegenstander
    (via de reeds bestaande _historical_opponent_boards_list(bundle) en
    _rotation_boards_for(full_boards, next_rotation_num)) de 2 borden
    terug die bij de EERSTVOLGENDE rotatie horen - dus de tegenstander-
    koppels van Match 1 en Match 2 zoals ze die dag EFFECTIEF speelden.
    `pair_label_fn` is DEZELFDE _pair_label()-functie die de bestaande
    dropdowns hieronder al gebruiken (lokaal gedefinieerd in
    _render_rotation_planner(), binnen de "Wie stelt de tegenstander op"-
    expander) - dat garandeert dat de tekst die deze functie teruggeeft
    EXACT overeenkomt met een bestaande dropdown-optie in `paar_labels`,
    zodat het instellen van een preset (zie hieronder) altijd een geldige,
    reeds bestaande keuze treft. `known_labels` (paar_labels) wordt enkel
    gebruikt om historische matchups te NEGEREN wanneer 1 van de 2 spelers
    niet (meer) in het gekende tegenstander-roster zit (bv. iemand die
    intussen de ploeg verliet) - dan zou de preset-tekst toch niet in de
    dropdown-opties bestaan, en wordt de preset stil overgeslagen.
  - _render_opponent_quick_presets(...): tekent 1 knop per (bruikbare)
    historische ontmoeting, meest recent eerst (_historical_opponent_
    boards_list() geeft de fixtures in bundle.previous_fixtures-volgorde;
    dat is de scrape-volgorde, niet gegarandeerd datum-aflopend - daarom
    wordt hier, ANDERS dan bij de oude eigen-opstelling-presets,
    EXPLICIET gesorteerd op _parse_match_date(label) aflopend, met een
    stabiele terugval naar de oorspronkelijke volgorde bij een
    onherkenbare datum-tekst). Elke knop toont enkel de NAMEN (geen
    P-klassement/padelstat-cijfers, die horen al bij de dropdown-opties
    hieronder) voor een compacte knoptekst, bv. "Zoals op 12/09: Peeters/
    Janssens - Claes/Wouters".
  - KLIK-GEDRAG: i.p.v. een eigen, parallel bevestig-pad te bouwen (zoals
    de oude, foute presets deden - en waar de arity-bug net uit ontstond),
    vult een klik enkel de 2 BESTAANDE dropdown-selecties in
    (st.session_state[key_i] voor i=0,1 - dezelfde keys als de 2
    selectboxen hieronder) met de exacte preset-labels, en doet dan
    st.rerun(scope="fragment") - EXACT hetzelfde patroon als lineup_
    sandbox.py._apply_sandbox_preset(). Na de rerun lezen de bestaande
    selectboxen die ingevulde waarde uit, rotation_opponent_boards wordt
    net zoals bij een manuele keuze gevuld, en de bestaande candidates-
    berekening/kaarten/"Zelf samenstellen" draaien ONGEWIJZIGD verder op
    die tegenstander-opstelling. Er is dus GEEN aparte bevestig-closure
    nodig voor deze presets - vandaar dat de arity-bug hier NIET kan
    terugkeren: er wordt nergens een eigen on_confirm(...) meer
    aangeroepen voor dit pad.
  - PLAATSING: de nieuwe presets staan BOVENAAN, IN de bestaande "Wie
    stelt de tegenstander op in rotatie N?"-expander (vóór de 2
    bestaande dropdowns) - dus niet langer in een aparte "Snelkeuzes"-
    expander; de oude, verwijderde sectie stond er los van, wat het
    misverstand mee in de hand werkte (leek een ANDERE keuze dan de
    tegenstander-dropdowns, terwijl het dat net WEL had moeten zijn).
  - Klikt de gebruiker niets: de 2 dropdowns werken exact zoals voorheen,
    geen functionaliteit verloren.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01 (op verzoek van Kim, na het
gezamenlijk uitgetekende ontwerp - 1 sectie "Opstelling", sandbox weg,
eindpaneel na beide rotaties, "meest frequent"-snelkeuze data-gedreven
i.p.v. een vast aantal: "Dus daarom zit ik te denken aan verschillende
scenario's die automatisch al kunnen getest worden [...] je zou dus zeker
ook kans op 1,2 of 0 punten bij de rotatieplanner moeten tonen.")
--------------------------------------------------------------------------
Drie afzonderlijke toevoegingen, elk met een eigen reden:
1. EINDPANEEL (_render_encounter_summary()): zodra borden_bevestigd >=
   total_boards, toonde de code hiervoor ENKEL een st.success()-melding en
   dan een `return` - geen enkele samenvatting van de 4 matchen of de
   eind-puntenkans was zichtbaar. _render_encounter_summary() herrekent
   (via de reeds bestaande _match_outcome_point_probabilities()) de
   EXACTE P(2)/P(1)/P(0) over de effectief gekozen winkansen van ALLE
   bevestigde rotaties (locked_win_probs_per_rotation, plat gemaakt - GEEN
   placeholder/50% meer nodig, want alles ligt vast), en toont daarnaast
   elke match met de effectieve namen (locked_rotations/locked_opponents).
2. "MEEST FREQUENT"-SNELKEUZE (_opponent_rotation_frequent_preset()): Kim
   koos bewust GEEN vast aantal ("hangt af van wat zinvol is") - daarom is
   dit DATA-GEDREVEN: de functie telt, over ALLE historische ontmoetingen
   tegen deze tegenstander (dezelfde _opponent_rotation_presets()-data,
   hergebruikt, geen nieuwe databron), welke (Match 1-duo, Match 2-duo)-
   COMBINATIE op deze rotatie-positie het VAAKST voorkwam. Een extra knop
   verschijnt ENKEL als die frequentie >= 2 is (anders is het toeval, geen
   signaal) EN de combinatie nog niet toevallig IDENTIEK is aan de "zoals
   op [meest recente datum]"-knop die _render_opponent_quick_presets() al
   toont (geen zinloze dubbele knop). Bij 0 of 1 bruikbare "zoals op..."-
   presets kan er sowieso geen frequentie >= 2 bestaan, dus verschijnt de
   knop dan vanzelf niet - geen aparte lege-lijst-check nodig.
3. SANDBOX-PRESETS VERHUISD (_strongest_quartet_candidate(),
   _own_previous_rotation_pairs()): Kim bevestigde "sandbox weg" (punt 3)
   en vroeg de nuttige presets ("Ons sterkste 4 (Elo)", "Onze vorige
   opstelling") te verhuizen naar "Zelf samenstellen" (punt 4 van het
   plan), i.p.v. zomaar te verdwijnen. BEIDE functies zoeken een
   CANDIDATE die exact bij het voorstel past (via _find_matching_
   candidate(), dezelfde functie die de klik-voor-klik-modus al gebruikt)
   - bestaat die niet (bv. de puntengrens laat deze combinatie niet toe
   voor de gekozen afdeling, of 1 van de spelers is deze rotatie niet
   beschikbaar), dan toont de knop een duidelijke melding i.p.v. een
   ongeldige keuze te forceren. _own_previous_rotation_pairs() hergebruikt
   dezelfde bron als de vroegere lineup_sandbox._recent_own_lineup_boards()
   (_load_encounter_index/ll.list_encounters/ll.reconstruct_boards).
   lineup_sandbox.py en zijn aanroep in page_lineup_lab.py zijn hierdoor
   overbodig geworden en VERWIJDERD (git rm, zie de instructies bij
   oplevering) - functioneel is er dus NIETS verloren, enkel VERPLAATST
   naar waar het hoort: naast de andere opstelling-keuzes voor DEZE
   tegenstander, i.p.v. een volledig aparte, losstaande pagina-sectie.
   lineup_whatif.py (en zijn aanroep) is EVENEENS verwijderd - Kim: "die
   wat als: mijn winkans bij een andere partner mag weg" - dat bestand had
   geen andere afhankelijkheden, dus een zuivere verwijdering.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_PRESET_ORDER_BUG_2026-10-02 (op verzoek van Kim,
na het testen van build1: "nog steeds maar 1 snelkeuze")
--------------------------------------------------------------------------
ROOT CAUSE, bevestigd: `_pair_label(p1, p2)` (lokaal gedefinieerd in
_render_rotation_planner(), gebruikt voor zowel de 2 dropdowns als de
presets) is ORDE-GEVOELIG - het formatteert p1 EERST, dan p2. De dropdown-
opties (`alle_paren = itertools.combinations(unique_opp_players, 2)`)
leggen voor elk koppel een VASTE, aan de LIJSTVOLGORDE van
`unique_opp_players` gebonden volgorde vast - compleet onafhankelijk van
de volgorde waarin een HISTORISCHE wedstrijd diezelfde 2 spelers
vermeldde (die volgorde weerspiegelt de bordvolgorde van toen, bv.
sterkste eerst volgens art. 6.6). _opponent_rotation_presets() riep
`pair_label_fn(m1_pair[0], m1_pair[1])` aan met de HISTORISCHE volgorde,
en vergeleek de uitkomst via EXACTE STRING-gelijkheid met `known_labels`
(de dropdown-opties). Voor een koppel in de "verkeerde" volgorde t.o.v.
de dropdown genereerde dit een andere, niet-overeenkomende string - en
viel de preset dus ten onrechte weg als "speler niet gekend", ook al
stond diezelfde speler wel degelijk in de tegenstander-roster. Met
meestal maar 1-2 historische ontmoetingen per tegenstander was de kans
hoog dat dit de ENIGE overlevende preset liet zijn (of zelfs 0).
FIX: vervangt de string-vergelijking door een ID-GEBASEERDE lookup, die
per definitie orde-ONAFHANKELIJK is. `_render_rotation_planner()` bouwt
nu, naast `paar_labels`/`paar_map` (ongewijzigd, voor de dropdowns zelf),
ook `paar_label_by_uids = {frozenset({uid1, uid2}): label, ...}` - EEN
canonieke labeltekst per ONGEORDEND koppel spelers. Deze dict (niet
langer `pair_label_fn` + `known_labels`) wordt doorgegeven aan
_render_opponent_quick_presets()/_opponent_rotation_presets(), die nu de
frozenset van de 2 historische user_id's opzoekt in deze dict i.p.v. zelf
een nieuwe labeltekst te formatteren en die te vergelijken. Bestaat het
koppel niet (meer) in de huidige tegenstander-roster, dan geeft
.get() None terug en wordt de preset - exact zoals voorheen bedoeld -
stil overgeslagen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_CARDS_REQUIRE_OPPONENT_2026-10-02 (op verzoek van
Kim: "bij kaarten niet logisch om al iets te tonen als er nog geen
tegenstander is")
--------------------------------------------------------------------------
De 3 kaarten (Aanbevolen/Veiligst/Alternatief) werden al VOOR het kiezen
van een tegenstander-opstelling getoond, met een expliciete "(nog
neutraal - tegenstander onbekend)"-notitie (PADEL_ANALYSIS_ROTATION_
CARDS_NEUTRAL_LABEL_2026-09-30) zodra alle 3 kaarten toch dezelfde,
wiskundig correcte maar betekenisloze 50/50-verdeling toonden. Kim geeft
nu aan dat de kaarten in dat geval beter HELEMAAL niet getoond worden,
in plaats van getoond-maar-met-een-waarschuwing.
FIX: `_render_rotation_planner()` berekent nu `rot_boards_this_rotation =
_rotation_boards_for(effective_opponent_boards, next_rotation_num)` VOOR
de kaarten-sectie. Is dat None (geen tegenstander-opstelling gekend voor
DEZE rotatie - noch via de snelkeuzes, noch via de 2 dropdowns, noch via
een extern meegegeven `opponent_boards`), dan verschijnt enkel een korte
info-melding die uitlegt WAAROM er geen kaarten staan en WAT te doen
(eerst een tegenstander kiezen hierboven) - de kaarten-berekening
(_rank_and_label_candidates_for_cards) wordt dan niet eens uitgevoerd.
"Zelf samenstellen" (klik-voor-klik) en "Alle N combinaties (geavanceerd)"
blijven ONGEWIJZIGD altijd bruikbaar (ze toonden al geen misleidende
winkans-percentages zonder tegenstander - enkel een EBW/synergie-score,
of bij ontbrekende EBW een synergie-score i.p.v. een percentage) - Kim's
melding gold specifiek de 3 kaarten, dus enkel die sectie is aangepast.
--------------------------------------------------------------------------
PADEL_ANALYSIS_ROTATION_SCENARIO_CARDS_2026-10-02 (op verzoek van Kim:
"kaarten ook in lineup_rotation. qua scenario's kunnen we zo starten. hou
wel ook wat rekening met statistische gegevens zoals: persoon x speelt
bijna altijd met die persoon y. of persoon x speelt bijna altijd 1ste
match.")
--------------------------------------------------------------------------
Bovenaan "Wie stelt de tegenstander op in rotatie N?" staan nu
SCENARIO-KAARTEN: de 3 waarschijnlijkste tegenstander-opstellingen voor
DEZE rotatie volgens opponent_lineup_model.py (deelname + vaste koppels +
Match 1/2-voorkeur, met de art. 6.6-bordvolgorde, de puntengrens en - in
rotatie 2+ - zonder koppels die in deze ontmoeting al speelden). Per kaart:
de kans, de redenen in gewone taal, ONS BESTE ANTWOORD (hoogste kans op 2
ploegpunten voor de volledige ontmoeting, gegeven wat al vastligt) en een
knop "Gebruik dit scenario" die - net als de historische snelkeuzes - de 2
bestaande tegenstander-dropdowns invult (zelfde paar_label_by_uids-lookup,
geen apart bevestig-pad).
Daaronder een ROBUUST VOORSTEL: de eigen opstelling met de hoogste GEWOGEN
kans over de top-5 scenario's (gewicht = voorspelde kans), plus - indien
verschillend - de opstelling die de kans op MINSTENS 1 punt maximaliseert
(het "opofferen voor 1 punt"-profiel uit Kim's ontwerp). Zo kan Kim ook
VOOR de tegenstander bekend is al een onderbouwde keuze maken.
De zware berekening (alle eigen opties x 5 scenario's) wordt per rotatie
gecachet in session_state, met een signatuur op spelers/budget/vastgelegde
rotaties/klassementen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_LIST_2026-10-03 + PADEL_ANALYSIS_ROTATION_LEVEL_NUMBERS_2026-10-03
(op verzoek van Kim: snelkeuze "nog altijd maar 1 optie", id's i.p.v.
namen, scenario-kaarten en snelkeuzes spreken elkaar tegen, en "hoe kan je
die getallen al berekenen als rotatie 2 nog niet gecheckt is?")
--------------------------------------------------------------------------
1. De oorzaak van "maar 1 snelkeuze" zat NIET in dit bestand: de planner
   kreeg maar 1 eerdere ontmoeting - zie page_lineup_lab.py,
   PADEL_ANALYSIS_PLANNING_ALL_FIXTURES_2026-10-03.
2. EEN lijst tegenstander-scenario's: top 3 als kaarten, daaronder de
   overige waarschijnlijke opstellingen (tot 80% cumulatieve kans, max.
   15), elk met kans, ons beste antwoord, uitkomst en een "Gebruik"-knop.
   Effectief gespeelde opstellingen staan erin GEMARKEERD ("gespeeld op
   ...") en worden altijd getoond. De aparte "Zoals op ..."-snelkeuzes
   vallen weg (enkel nog terugval zonder model).
3. Namen: stats["names"] wordt aangevuld met de volledige roster - geen
   id's meer.
4. Eerlijke cijfers: in een NIET-laatste rotatie tonen kaarten en
   scenario's enkel de uitkomst van DEZE rotatie (2-0 / 1-1 / 0-2) en
   wordt "ons beste antwoord" gekozen op verwachte gewonnen matchen.
   De kans op ploegwinst/gelijk/verlies verschijnt pas in de laatste
   rotatie, waar ze exact is. Plannen over beide rotaties samen volgt in
   een volgende stap.
5. Betrouwbaarheidslabel (geen/laag/matig/goed) op basis van het aantal
   eerdere ontmoetingen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03 (op verzoek van Kim: "Twee rotaties samen
simuleren: akkoord, zo moet het" + "bij de rotatieplanner kan je dan een
scenario kiezen maar dat lijkt dan ergens los te staan van de andere
scenario's [...] effectief gewoon een scenario kunnen kiezen maar de
mogelijkheid hebben om vanuit dat scenario dan toch wijzigingen te doen door
manueel speler per speler aan te passen. Niet per koppel aanpassen")
--------------------------------------------------------------------------
1. ADAPTIEVE 2-ROTATIE-SIMULATIE (_two_rotation_plan): enkel bij het
   najaarsformaat (2 rotaties van 2 matchen) en in rotatie 1. Voor elke
   eigen rotatie-1-opstelling x elk waarschijnlijk tegenstander-scenario
   voor rotatie 1 wordt de VOLLEDIGE ontmoeting doorgerekend:
     - rotatie 2 kiezen WIJ pas na rotatie 1, als we de stand (2-0 / 1-1 /
       0-2) en hun rotatie-1-opstelling kennen: per stand wordt de beste
       eigen rotatie 2 gezocht, binnen de regels (koppels die al speelden
       vallen weg, speelbudget, puntengrens, art. 6.6);
     - hun rotatie 2 wordt voorspeld met hetzelfde statistisch model,
       zonder hun koppels uit rotatie 1;
     - winkansen hangen enkel af van (ons koppel, hun koppel) en worden 1x
       berekend en daarna hergebruikt.
   Resultaat: 3 PLANKAARTEN ("Meeste verwachte punten", "Grootste kans op
   winst", "Minstens 1 punt") met de rotatie-1-opstelling (label gespreid /
   opofferen), winst/gelijk/verlies voor de HELE ontmoeting, en het plan
   voor rotatie 2 per stand. Ze vervangen in rotatie 1 de kaarten per
   rotatie (die zouden de plankaarten tegenspreken). In de laatste rotatie
   blijft de exacte berekening zoals voorheen.
   Zodra een tegenstander-opstelling gekozen is, rekenen de plankaarten
   tegen precies die opstelling. "Ons beste antwoord" bij elk scenario is
   in deze modus ook een volledig plan (rotatie 1 + rotatie 2 per stand).
2. TEGENSTANDER PER SPELER: de 2 koppel-dropdowns zijn vervangen door 4
   speler-dropdowns (Match 1 speler 1/2, Match 2 speler 1/2). Een gekozen
   speler verdwijnt uit de andere dropdowns, en koppels die in deze
   ontmoeting al speelden worden niet aangeboden. "Gebruik dit scenario"
   vult de 4 dropdowns in - daarna kan je speler per speler aanpassen.
3. "Andere waarschijnlijke opstellingen" is inklapbaar, met in de titel het
   aantal en hun samengetelde kans. Het "Robuust voorstel" valt weg in de
   plan-modus (de plankaarten nemen die rol over).
"""
import itertools
from collections import Counter
import streamlit as st
try:
    import opponent_lineup_model as olm  # PADEL_ANALYSIS_ROTATION_SCENARIO_CARDS_2026-10-02
except Exception:  # noqa: BLE001  pragma: no cover
    olm = None
from dashboard_common import ll, taa, _parse_match_date
from lineup_scout import (
    _cached_official_rank, _cached_own_player_rating,
    _render_official_rank_warning, _format_points_bounds_diagnostic,
    _load_encounter_index,  # PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01: voor de overgenomen sandbox-preset "Onze vorige opstelling"
)
# PADEL_ANALYSIS_WINPROB_CALIBRATION_2026-09-22: zie lineup_lab.py voor de
# volledige toelichting bij de kalibratie van de winkans-formule.
# PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29: reglement najaarsinterclub = 2 rotaties x 2 matchen.
# PADEL_ANALYSIS_CONFIGURABLE_ROTATIONS_2026-09-29: standaardwaarde; instelbaar op de pagina (voorjaar: 3).
ROTATIONS_PER_ENCOUNTER = 2
ROTATIONS_MIN = 1
ROTATIONS_MAX = 4
MATCHES_PER_ROTATION = 2
MATCHES_PER_ENCOUNTER = ROTATIONS_PER_ENCOUNTER * MATCHES_PER_ROTATION
_WIN_PROB_DISCLAIMER = (
    "De winkans is een logistische schatting op het verschil in speelsterkte, "
    "gekalibreerd op 44 recent gespeelde dubbels (70% van de uitslagen juist voorspeld; "
    "Brier 0.195 tegenover 0.25 voor een muntstuk). Bij uitgesproken favorieten en "
    "underdogs is de schatting nog steeds aan de voorzichtige kant, en de steekproef is "
    "klein - richtinggevend signaal dus, geen garantie."
)
# -----------------------------------------------
# PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30 - zie moduledocstring.
# -----------------------------------------------
def _n_missing_win_probs(win_probs: list) -> int:
    """Aantal onbekende (None) winkansen in de lijst - de aanroeper kan dit
    gebruiken om te waarschuwen dat de puntenkans-berekening deels op een
    neutrale 50%-aanname steunt."""
    return sum(1 for p in win_probs if p is None)
def _match_outcome_point_probabilities(win_probs: list) -> dict:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: exacte kansverdeling op
    het PLOEGRESULTAAT (0/1/2 punten - Kim, bevestigd 2026-09-30) voor 1
    opstelling tegen 1 specifiek tegenstander-scenario, gegeven de
    individuele winkans per match.
    Puntensysteem: MEER matchen gewonnen dan de tegenstander -> 2 punten,
    EVENVEEL -> 1 punt, MINDER -> 0 punten. Bij een even aantal matchen (het
    gebruikelijke geval, bv. 4) is een gelijke stand (bv. 2-2) mogelijk en
    geeft 1 punt; bij een oneven aantal matchen kan dat niet voorkomen en is
    de kans op 1 punt dus 0.
    Berekent dit EXACT (geen Monte Carlo): met n individuele, onafhankelijke
    kansen zijn er 2^n mogelijke uitkomsten - voor de gebruikelijke n=4 is
    dat 16, dus dit is triviaal snel. Werkt voor elk aantal matchen (bv. 6
    bij een ander formaat), niet enkel 4.
    Ontbrekende winkansen (None - onvoldoende rating-data) worden voor DEZE
    berekening als 50% behandeld (neutrale muntworp), zodat de functie
    nooit crasht of None propageert. Gebruik _n_missing_win_probs() om te
    weten hoeveel dat er waren en dat eventueel apart te signaleren.
    Geeft {"p2": float, "p1": float, "p0": float} terug (som = 1.0)."""
    probs = [(0.5 if p is None else max(0.0, min(1.0, float(p)))) for p in win_probs]
    n = len(probs)
    if n == 0:
        return {"p2": 0.0, "p1": 0.0, "p0": 0.0}
    half = n / 2.0
    p2 = p1 = p0 = 0.0
    for outcome in itertools.product((0, 1), repeat=n):
        # outcome[i] == 1 betekent: wij winnen match i.
        prob = 1.0
        for won, p in zip(outcome, probs):
            prob *= p if won else (1.0 - p)
        wins = sum(outcome)
        if wins > half:
            p2 += prob
        elif wins == half:
            p1 += prob
        else:
            p0 += prob
    return {"p2": p2, "p1": p1, "p0": p0}
def _opponent_lineup_weight(info: dict) -> float:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: gewicht van 1
    tegenstander-scenario ("unique_opponent_lineups"-item) voor de gewogen
    puntenkans-aggregatie hieronder.
    Regel (dit seizoen, zie moduledocstring voor waarom): elke keer dat de
    tegenstander deze EXACTE koppelverdeling, IN DEZELFDE ROTATIE-POSITIE,
    dit seizoen effectief speelde (info["historical_count"], gezet door
    _collect_unique_opponent_lineups()) telt voor +1.0 gewicht bovenop een
    vaste BASIS van 1.0 die elk scenario al krijgt (ook een zuiver
    theoretisch, nooit geobserveerd scenario telt dus nog mee, maar wel
    veel lichter dan een herhaald patroon).
    Voorbeeld: nooit gespeeld -> gewicht 1.0. 1x gespeeld -> gewicht 2.0.
    3x gespeeld -> gewicht 4.0 (die combinatie weegt dan 4x zo zwaar als
    een nooit geobserveerde combinatie in het gewogen gemiddelde).
    BEWUST de ENIGE plek die dit bepaalt: een latere uitbreiding met
    vorige-seizoenen-data (zodra die met een betrouwbare rotatiepositie
    beschikbaar is) hoeft enkel deze functie aan te passen."""
    n_seen = int(info.get("historical_count", 0) or 0)
    return 1.0 + float(n_seen)
def _aggregate_group_point_probabilities(rows: list, weights: dict) -> dict:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: combineert de
    per-tegenstander-scenario resultaten van 1 groep (1 eigen opstelling,
    dus een lijst van matchup-dicts met een reeds berekende
    "point_probs"-veld) tot een GEWOGEN gemiddelde puntenkans over alle
    doorgerekende scenario's van die groep.
    `weights` is een dict {matchup_id(m): gewicht}, typisch gevuld via
    _opponent_lineup_weight() per onderliggend tegenstander-scenario - de
    aanroeper (lineup_matchup_table.py) kent de koppeling tussen elke rij en
    zijn tegenstander-scenario-sleutel, dit bestand niet.
    Geeft {"p2": float, "p1": float, "p0": float, "n_missing_ratings": int}
    terug. Bij een lege of ongewogen (totaalgewicht 0) invoer: alle kansen
    0.0 en n_missing_ratings 0, om de aanroeper nooit te laten crashen."""
    totaal_gewicht = 0.0
    p2 = p1 = p0 = 0.0
    n_missing = 0
    for m in rows:
        gewicht = weights.get(id(m), 1.0)
        pp = m.get("point_probs") or {}
        totaal_gewicht += gewicht
        p2 += gewicht * pp.get("p2", 0.0)
        p1 += gewicht * pp.get("p1", 0.0)
        p0 += gewicht * pp.get("p0", 0.0)
        n_missing += int(m.get("n_missing_win_probs", 0) or 0)
    if totaal_gewicht <= 0:
        return {"p2": 0.0, "p1": 0.0, "p0": 0.0, "n_missing_ratings": n_missing}
    return {
        "p2": p2 / totaal_gewicht,
        "p1": p1 / totaal_gewicht,
        "p0": p0 / totaal_gewicht,
        "n_missing_ratings": n_missing,
    }
# -----------------------------------------------
# PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30 - zie moduledocstring.
# -----------------------------------------------
_SAFE_CARD_MIN_WINPROB_GAP = 0.0  # placeholder-grens, zie _pick_safest_card (0 = gewoon de hoogste minimum-winkans)
def _format_point_probs_short(pp: dict, is_neutral: bool = False) -> str:
    """Korte, leesbare weergave van een puntenkans-dict voor op een kaart.
    Lokale kopie van dezelfde opmaak als lineup_matchup_table._format_point_probs()
    - NIET vandaar geimporteerd, om een cirkelvormige import te vermijden
    (lineup_matchup_table.py importeert AL van dit bestand).
    PADEL_ANALYSIS_ROTATION_CARDS_NEUTRAL_LABEL_2026-09-30: `is_neutral`
    voegt een expliciete waarschuwing toe zodra de kansen volledig op de
    50%-placeholder-aanname steunen (nog geen enkele echte winkans gekend)
    - zie moduledocstring voor waarom dit anders misleidend oogt."""
    if not pp:
        return "onbekend"
    basis = (
        f"{pp.get('p2', 0.0) * 100:.0f}% 2p \u00b7 {pp.get('p1', 0.0) * 100:.0f}% 1p \u00b7 "
        f"{pp.get('p0', 0.0) * 100:.0f}% 0p"
    )
    if is_neutral:
        return basis + " (nog neutraal - tegenstander onbekend)"
    return basis
def _impact_markdown(pp: dict) -> str:
    """PADEL_ANALYSIS_IMPACT_VISIBLE_2026-10-02 (Kim: "De ontmoeting
    resultaten mogen veel duidelijker getoond worden. Nu staat dat in het
    lichtgrijs in een kleinere font"): normale tekst, vet, met kleurcode."""
    if not pp:
        return "**Ontmoeting:** onbekend"
    p2, p1, p0 = (pp.get(k, 0.0) * 100 for k in ("p2", "p1", "p0"))
    return (
        f"**Ontmoeting:** :green[**{p2:.0f}% winst**] · :orange[**{p1:.0f}% gelijk**] · "
        f":red[**{p0:.0f}% verlies**]"
    )
def _candidate_pair_set_key(candidate: dict) -> frozenset:
    """Identificeert een kandidaat op ZIJN KOPPELS (ongeacht bordvolgorde) -
    gebruikt om de 3 kaarten van elkaar te onderscheiden op een echt ander
    profiel, niet enkel een omgewisselde Match 1/Match 2."""
    return frozenset(frozenset(p) for p in candidate.get("ordered_pairs", []))
def _candidate_win_probs(candidate: dict) -> list:
    """De 2 individuele winkansen van deze kandidaat-rotatie (None per match
    als de tegenstander voor deze rotatie nog niet gekozen is - _generate_
    rotation_candidates() geeft dan assignment=None terug)."""
    assignment = candidate.get("assignment")
    if not assignment:
        return [None, None]
    return [a.get("win_probability") for a in assignment]
def _impact_point_probs_for_candidate(
    candidate: dict, locked_win_probs: list, total_boards=None,
) -> dict:
    """PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30: puntenkans (P2/P1/P0) voor
    de VOLLEDIGE ontmoeting als je deze kandidaat kiest voor de eerstvolgende
    rotatie - dus [reeds bevestigde winkansen] + [deze kandidaat] + [nog te
    plannen rotaties, automatisch als 50/50 behandeld door
    _match_outcome_point_probabilities()]. Bij total_boards=None (formaat
    onbekend) wordt enkel over de tot nu toe gekende matchen gerekend -
    correct, maar dan zonder de placeholder voor toekomstige rotaties."""
    win_probs = list(locked_win_probs) + _candidate_win_probs(candidate)
    if total_boards is not None:
        ontbrekend = int(total_boards) - len(win_probs)
        if ontbrekend > 0:
            win_probs = win_probs + [None] * ontbrekend
    return _match_outcome_point_probabilities(win_probs)
def _impact_is_fully_neutral(candidate: dict, locked_win_probs: list, total_boards=None) -> bool:
    """PADEL_ANALYSIS_ROTATION_CARDS_NEUTRAL_LABEL_2026-09-30: True zodra
    GEEN ENKELE van de winkansen die de impact-berekening voedt gekend is
    (dus: geen bevestigde rotaties MET gekende winkans, en de tegenstander
    van deze kandidaat-rotatie ook nog niet gekozen) - in dat geval is de
    getoonde 31/38/31-achtige verdeling wiskundig correct maar betekenisloos
    (identiek voor elke kandidaat), en moet de UI dat expliciet zeggen i.p.v.
    de indruk te wekken dat de kaarten al onderscheidend zijn."""
    alle_gekend = list(locked_win_probs) + _candidate_win_probs(candidate)
    return len(alle_gekend) > 0 and all(p is None for p in alle_gekend)
def _pick_safest_card(evaluated: list, exclude_keys: set) -> dict:
    """Kandidaat (niet in exclude_keys) met de hoogste MINIMALE winkans over
    zijn 2 matchen - dus de kandidaat die het minst waarschijnlijk een bijna
    zekere nederlaag op 1 match oplevert. Enkel kandidaten waarvan BEIDE
    winkansen gekend zijn komen in aanmerking; is er geen enkele, dan wordt
    None teruggegeven (de aanroeper valt dan terug op de volgende
    beste-impact-kandidaat, zie _rank_and_label_candidates_for_cards)."""
    beste = None
    beste_min = None
    for ev in evaluated:
        if ev["pair_key"] in exclude_keys:
            continue
        wp = ev["win_probs"]
        if any(p is None for p in wp):
            continue
        minimum = min(wp)
        if beste_min is None or minimum > beste_min:
            beste_min, beste = minimum, ev
    return beste
def _rank_and_label_candidates_for_cards(
    candidates: list, locked_win_probs: list, total_boards=None, max_cards: int = 3,
    final_rotation: bool = True,
) -> list:
    """PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30: selecteert max. `max_cards`
    kandidaten uit `candidates` (reeds gesorteerd op EBW door
    _generate_rotation_candidates(), maar dat wordt hier NIET meer als
    hoofdsortering gebruikt) en labelt ze als "Aanbevolen"/"Veiligst"/
    "Alternatief". Zie moduledocstring voor de volledige toelichting.
    Geeft een lijst van max. `max_cards` dicts terug, elk met:
      "role", "candidate", "win_probs" (2 winkansen van DEZE rotatie),
      "risk_notes" (2 risiconotities, via ll.risk_note_for_probability),
      "impact" (puntenkans voor de VOLLEDIGE ontmoeting met deze keuze),
      "is_neutral" (PADEL_ANALYSIS_ROTATION_CARDS_NEUTRAL_LABEL_2026-09-30:
      True als "impact" volledig op de 50%-placeholder-aanname steunt),
      "pair_key" (voor dedupe/identificatie).
    Geeft nooit meer kaarten dan er ECHT onderscheiden kandidaten zijn -
    bij < max_cards kandidaten dus minder kaarten, nooit een lege/dubbele."""
    if not candidates:
        return []
    evaluated = []
    for cand in candidates:
        win_probs = _candidate_win_probs(cand)
        evaluated.append({
            "candidate": cand,
            "win_probs": win_probs,
            "risk_notes": [ll.risk_note_for_probability(wp) for wp in win_probs],
            "impact": _impact_point_probs_for_candidate(cand, locked_win_probs, total_boards),
            "is_neutral": _impact_is_fully_neutral(cand, locked_win_probs, total_boards),
            "pair_key": _candidate_pair_set_key(cand),
            # PADEL_ANALYSIS_ROTATION_LEVEL_NUMBERS_2026-10-03
            "rot_outcome": _match_outcome_point_probabilities(win_probs),
            "ebw": cand.get("expected_boards_won") or 0.0,
            "is_final_rotation": final_rotation,
        })
    # PADEL_ANALYSIS_ROTATION_LEVEL_NUMBERS_2026-10-03: in een NIET-laatste
    # rotatie is "kans op 2 ploegpunten" een gok (de rest telde als 50/50) -
    # rangschik dan op verwachte gewonnen matchen in DEZE rotatie (tiebreak:
    # kans op 2-0). Enkel in de laatste rotatie is de ontmoeting-kans exact.
    if final_rotation:
        sort_key = lambda ev: (ev["impact"]["p2"], ev["impact"]["p1"])  # noqa: E731
    else:
        sort_key = lambda ev: (ev["ebw"], ev["rot_outcome"]["p2"])  # noqa: E731
    by_impact = sorted(evaluated, key=sort_key, reverse=True)
    cards = []
    gekozen_keys = set()
    aanbevolen = by_impact[0]
    cards.append({**aanbevolen, "role": "Aanbevolen"})
    gekozen_keys.add(aanbevolen["pair_key"])
    if max_cards >= 2 and len(evaluated) > 1:
        veiligst = _pick_safest_card(evaluated, gekozen_keys)
        if veiligst is None:
            # Geen kandidaat met 2 gekende winkansen buiten "Aanbevolen" ->
            # val terug op de op-1-na-beste impact (nog steeds nuttig,
            # geen kaart weglaten enkel omdat "veiligst" strikt niet te
            # bepalen is).
            veiligst = next((ev for ev in by_impact if ev["pair_key"] not in gekozen_keys), None)
        if veiligst is not None and veiligst["pair_key"] not in gekozen_keys:
            cards.append({**veiligst, "role": "Veiligst"})
            gekozen_keys.add(veiligst["pair_key"])
    if max_cards >= 3 and len(evaluated) > len(cards):
        alternatief = next((ev for ev in by_impact if ev["pair_key"] not in gekozen_keys), None)
        if alternatief is not None:
            cards.append({**alternatief, "role": "Alternatief"})
            gekozen_keys.add(alternatief["pair_key"])
    return cards[:max_cards]
def _render_candidate_card(
    col, card: dict, name_lookup_global: dict, key_prefix: str,
) -> bool:
    """Tekent 1 beslissingskaart. Geeft True terug als de "Kies deze
    kaart"-knop deze render is aangeklikt (de aanroeper doet dan de
    bevestiging - dit bestand tekent enkel, het vastpinnen gebeurt in
    _render_rotation_planner(), waar de locked_*-session_state leeft)."""
    with col:
        with st.container(border=True):
            st.markdown(f"**{card['role']}**")
            cand = card["candidate"]
            for match_idx, pair in enumerate(cand["ordered_pairs"], start=1):
                p1, p2 = tuple(pair)
                wp = card["win_probs"][match_idx - 1]
                risk = card["risk_notes"][match_idx - 1]
                wp_txt = f"{int(round(wp * 100))}% winkans ({risk})" if wp is not None else "winkans onbekend (tegenstander niet gekozen)"
                st.write(
                    f"Match {match_idx}: **{name_lookup_global.get(p1, p1)} / "
                    f"{name_lookup_global.get(p2, p2)}** - {wp_txt}"
                )
            # PADEL_ANALYSIS_ROTATION_CARDS_NEUTRAL_LABEL_2026-09-30: is_neutral
            # doorgegeven aan _format_point_probs_short() i.p.v. de kansen
            # zonder context te tonen.
            # PADEL_ANALYSIS_ROTATION_LEVEL_NUMBERS_2026-10-03
            st.markdown(_rotation_outcome_markdown(card.get("rot_outcome") or {}))
            if card.get("is_final_rotation", True):
                st.markdown(_impact_markdown(card["impact"]))
            if card.get("is_neutral"):
                st.caption(
                    "Deze kaarten zijn nu nog gelijkwaardig omdat er nog geen enkele winkans gekend is "
                    "(tegenstander nog niet gekozen, geen rotatie bevestigd). Kies hieronder de "
                    "combinatie die je tactisch het beste lijkt - de impact-cijfers worden pas "
                    "onderscheidend zodra de tegenstander gekend is of een rotatie bevestigd wordt."
                )
            ebw = cand.get("expected_boards_won")
            if ebw is not None:
                st.caption(f"(EBW deze rotatie: {ebw:.2f})")
            return st.button("Kies deze kaart", key=f"{key_prefix}_pick", type="primary", use_container_width=True)
# -----------------------------------------------
# PADEL_ANALYSIS_ROTATION_OPPONENT_PRESETS_2026-09-30 - zie moduledocstring.
# (VERVANGT de eerder verwijderde, foute eigen-opstelling-presets van
# PADEL_ANALYSIS_ROTATION_PLANNER_PRESETS_2026-09-30.)
# -----------------------------------------------
def _opponent_rotation_presets(
    bundle: dict, next_rotation_num: int, paar_label_by_uids: dict,
    paar_label_by_names: dict = None, skipped: list = None,
) -> list:
    """Geeft per eerdere ontmoeting TEGEN DEZE tegenstander de 2 borden
    terug die bij de EERSTVOLGENDE rotatie horen, als bruikbare presets.
    PADEL_ANALYSIS_ROTATION_PRESET_ORDER_BUG_2026-10-02 (op verzoek van
    Kim: "nog steeds maar 1 snelkeuze") - zie moduledocstring voor de
    volledige root-cause-analyse. `paar_label_by_uids` is een dict
    {frozenset({uid1, uid2}): label} opgebouwd uit de DROPDOWN-opties
    zelf (dus altijd de canonieke, bestaande labeltekst voor dat koppel,
    ONGEACHT in welke volgorde de historische wedstrijd die 2 spelers
    vermeldde) - dit VERVANGT de vorige, ORDE-GEVOELIGE aanpak
    (pair_label_fn(m1_pair[0], m1_pair[1]) + string-vergelijking met
    known_labels), die voor een koppel in de "verkeerde" volgorde altijd
    een net andere string genereerde dan de dropdown-optie en zo bijna
    elke preset ten onrechte liet afvallen.
    Geeft een lijst van {"fixture_label": str, "m1_label": str,
    "m2_label": str, "m1_display": str, "m2_display": str} terug, meest
    recente ontmoeting eerst (best-effort datum-sortering, zie
    moduledocstring). Faalt altijd stil ([])."""
    try:
        historical = _historical_opponent_boards_list(bundle)
    except Exception:  # noqa: BLE001
        return []
    def _datum_sleutel(item):
        fixture_label, _ = item
        parsed = None
        try:
            parsed = _parse_match_date(fixture_label)
        except Exception:  # noqa: BLE001
            parsed = None
        return (parsed is not None, parsed or (0, 0, 0))
    historical_sorted = sorted(historical, key=_datum_sleutel, reverse=True)
    out = []
    for fixture_label, full_boards in historical_sorted:
        rot_boards = _rotation_boards_for(full_boards, next_rotation_num)
        if not rot_boards or len(rot_boards) != 2:
            continue
        m1_pair = (rot_boards[0].get("opponent_pair") or [])
        m2_pair = (rot_boards[1].get("opponent_pair") or [])
        if len(m1_pair) != 2 or len(m2_pair) != 2:
            if skipped is not None:
                skipped.append(f"{fixture_label}: onvolledige koppels op het uitslagenblad")
            continue
        m1_uids = frozenset(str(p.get("user_id")) for p in m1_pair)
        m2_uids = frozenset(str(p.get("user_id")) for p in m2_pair)
        m1_label = paar_label_by_uids.get(m1_uids)
        m2_label = paar_label_by_uids.get(m2_uids)
        # PADEL_ANALYSIS_PRESET_NAME_FALLBACK_2026-10-02: zelfde speler kan in
        # een ouder uitslagenblad een ANDERE id hebben (of geen) - val dan
        # terug op de naam.
        if paar_label_by_names:
            def _nk(pair):
                return frozenset(_norm_name(p.get("name")) for p in pair)
            if m1_label is None:
                m1_label = paar_label_by_names.get(_nk(m1_pair))
            if m2_label is None:
                m2_label = paar_label_by_names.get(_nk(m2_pair))
        if m1_label is None or m2_label is None:
            if skipped is not None:
                ontbr = [
                    p.get("name", "?") for p in (m1_pair if m1_label is None else []) + (m2_pair if m2_label is None else [])
                ]
                skipped.append(f"{fixture_label}: speler(s) niet in de huidige tegenstander-selectie ({', '.join(ontbr)})")
            # Minstens 1 speler zit niet (meer) in het gekende tegenstander-
            # roster - deze preset zou een niet-bestaande dropdown-optie
            # instellen, dus overslaan i.p.v. een kapotte knop te tonen.
            continue
        m1_namen = " / ".join(p.get("name", "?") for p in m1_pair)
        m2_namen = " / ".join(p.get("name", "?") for p in m2_pair)
        out.append({
            "fixture_label": fixture_label,
            "m1_label": m1_label, "m2_label": m2_label,
            "m1_display": m1_namen, "m2_display": m2_namen,
        })
    return out
def _norm_name(naam) -> str:
    return " ".join(str(naam or "").lower().split())
def _render_opponent_quick_presets(
    bundle: dict, next_rotation_num: int, paar_label_by_uids: dict,
    key_i0: str, key_i1: str, paar_label_by_names: dict = None,
) -> None:
    """PADEL_ANALYSIS_ROTATION_OPPONENT_PRESETS_2026-09-30 - zie
    moduledocstring. Tekent 1 knop per bruikbare historische ontmoeting
    tegen DEZE tegenstander. `key_i0`/`key_i1` zijn de EXACTE
    session_state-keys van de 2 bestaande "Tegenstander match 1/2"-
    dropdowns hieronder - een klik vult die rechtstreeks in en doet een
    st.rerun(scope="fragment"), net als lineup_sandbox.py's preset-knoppen.
    Geen eigen bevestig-pad: de bestaande dropdown-logica en alles wat
    daarop bouwt (candidates/kaarten/"Zelf samenstellen") werkt hierna
    ONGEWIJZIGD verder, exact zoals bij een manuele dropdown-keuze."""
    skipped = []
    presets = _opponent_rotation_presets(
        bundle, next_rotation_num, paar_label_by_uids, paar_label_by_names, skipped,
    )
    # PADEL_ANALYSIS_PRESET_NAME_FALLBACK_2026-10-02: zichtbaar WAAROM een
    # eerdere ontmoeting geen snelkeuze werd (evidence i.p.v. gissen).
    n_hist = len(_historical_opponent_boards_list(bundle))
    if skipped or n_hist != len(presets):
        with st.expander(f"Snelkeuzes: {len(presets)} van {n_hist} eerdere ontmoeting(en) bruikbaar", expanded=False):
            for regel in skipped:
                st.write(f"- {regel}")
            if not skipped and n_hist != len(presets):
                st.write("- Overige ontmoetingen hadden geen borden voor deze rotatie-positie.")
    if not presets:
        st.caption(
            "Nog geen snelkeuze beschikbaar voor deze rotatie-positie (geen eerdere ontmoeting "
            "tegen deze tegenstander met bekende opstelling op exact deze plaats)."
        )
        return
    st.caption("Snelkeuze: tegenstander-opstelling zoals in een eerdere ontmoeting -")
    for i, preset in enumerate(presets):
        knop_tekst = (
            f"Zoals op {preset['fixture_label']}: "
            f"M1 {preset['m1_display']}  -  M2 {preset['m2_display']}"
        )
        if st.button(
            knop_tekst,
            key=f"opp_preset_{next_rotation_num}_{i}",
            use_container_width=True,
        ):
            st.session_state[key_i0] = preset["m1_label"]
            st.session_state[key_i1] = preset["m2_label"]
            st.rerun(scope="fragment")
    # PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01: data-gedreven extra knop,
    # enkel als er een echt frequentie-signaal is - zie moduledocstring.
    frequent = _opponent_rotation_frequent_preset(presets)
    if frequent is not None:
        knop_tekst = (
            f"Meest frequent ({frequent['freq']}x): "
            f"M1 {frequent['m1_display']}  -  M2 {frequent['m2_display']}"
        )
        if st.button(
            knop_tekst,
            key=f"opp_preset_frequent_{next_rotation_num}",
            use_container_width=True,
        ):
            st.session_state[key_i0] = frequent["m1_label"]
            st.session_state[key_i1] = frequent["m2_label"]
            st.rerun(scope="fragment")
def _opponent_rotation_frequent_preset(presets: list) -> dict:
    """PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01 - zie moduledocstring.
    Neemt de output van _opponent_rotation_presets() (1 rij per historische
    ontmoeting tegen deze tegenstander, al gesorteerd meest-recent-eerst)
    en zoekt de (m1_label, m2_label)-COMBINATIE die het VAAKST voorkwam.
    Geeft None terug als:
      - er minder dan 2 presets zijn (geen zinvolle frequentie mogelijk);
      - de hoogste frequentie < 2 is (elke combinatie kwam maar 1x voor -
        geen signaal, puur toeval welke het eerst in de lijst staat);
      - de meest-frequente combinatie toevallig EXACT de eerste (dus meest
        recente) preset is - dan zou deze knop een zinloos duplicaat van
        "zoals op [meest recente datum]" zijn.
    Bij een gelijke frequentie tussen meerdere combinaties: Counter.most_
    common() geeft de eerst-ingevoegde volgorde als tiebreak, en presets
    is al gesorteerd op datum aflopend - dus bij een gelijke stand wint de
    meest recente combinatie, net als de rest van deze snelkeuze-sectie."""
    if len(presets) < 2:
        return None
    counter = Counter((p["m1_label"], p["m2_label"]) for p in presets)
    (m1, m2), freq = counter.most_common(1)[0]
    if freq < 2:
        return None
    meest_recent = presets[0]
    if (meest_recent["m1_label"], meest_recent["m2_label"]) == (m1, m2):
        return None
    match = next(p for p in presets if (p["m1_label"], p["m2_label"]) == (m1, m2))
    return {
        "m1_label": m1, "m2_label": m2,
        "m1_display": match["m1_display"], "m2_display": match["m2_display"],
        "freq": freq,
    }
def _match1_eligible_players(candidates: list) -> list:
    """Alle speler-id's die in minstens 1 candidate als lid van
    ordered_pairs[0] (Match 1) voorkomen - dus: kan volgens de reeds
    berekende, reglementair geldige candidates op Match 1 staan."""
    spelers = set()
    for cand in candidates:
        if cand.get("ordered_pairs"):
            spelers |= set(cand["ordered_pairs"][0])
    return sorted(spelers)
def _match1_partners_for(candidates: list, player_id: str) -> list:
    """Partners waarmee `player_id` SAMEN als ordered_pairs[0] (Match 1)
    voorkomt in minstens 1 candidate."""
    partners = set()
    for cand in candidates:
        if not cand.get("ordered_pairs"):
            continue
        duo_a = cand["ordered_pairs"][0]
        if player_id in duo_a:
            partners |= (set(duo_a) - {player_id})
    return sorted(partners)
def _match2_options_for_duo_a(candidates: list, duo_a: frozenset) -> list:
    """Unieke ordered_pairs[1]-koppels (Match 2) over alle candidates
    waarvan ordered_pairs[0] EXACT `duo_a` is."""
    opties = []
    gezien = set()
    for cand in candidates:
        if not cand.get("ordered_pairs"):
            continue
        if frozenset(cand["ordered_pairs"][0]) != duo_a:
            continue
        duo_b = frozenset(cand["ordered_pairs"][1])
        if duo_b in gezien:
            continue
        gezien.add(duo_b)
        opties.append(duo_b)
    return opties
def _find_matching_candidate(candidates: list, duo_a: frozenset, duo_b: frozenset):
    """De candidate waarvan (ordered_pairs[0], ordered_pairs[1]) exact
    (duo_a, duo_b) is. Geeft None terug als er (onverwacht) geen match is -
    de aanroeper moet dat defensief afhandelen."""
    for cand in candidates:
        if not cand.get("ordered_pairs"):
            continue
        if (
            frozenset(cand["ordered_pairs"][0]) == duo_a
            and frozenset(cand["ordered_pairs"][1]) == duo_b
        ):
            return cand
    return None
def _candidates_player_pool(candidates: list) -> set:
    """Alle speler-id's die in minstens 1 candidate voorkomen (Match 1 of
    Match 2 samen) - gebruikt om de 'sterkste 4'-preset te bepalen zonder
    spelers voor te stellen die voor deze rotatie toch niet beschikbaar
    zijn (budget op, of al gebruikt in een vorige rotatie)."""
    out = set()
    for cand in candidates:
        if cand.get("ordered_pairs"):
            for pair in cand["ordered_pairs"]:
                out |= set(pair)
    return out
def _strongest_quartet_candidate(candidates: list, player_ratings: dict, official_ranks_strict: dict):
    """PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01 - zie moduledocstring
    (sandbox-preset 'Ons sterkste 4 (Elo)', verhuisd van lineup_sandbox.py).
    Sorteert de spelers die in DEZE rotatie nog beschikbaar zijn
    (_candidates_player_pool) op playing strength (player_ratings, terugval
    official_ranks_strict), en zoekt onder `candidates` (al reglementair
    gevalideerd) de kandidaat die EXACT uit deze top-4 bestaat. Geeft None
    terug als er geen 4 beschikbare spelers zijn, of als geen enkele
    gevalideerde candidate exact deze 4 spelers gebruikt (bv. omdat geen
    enkele koppelverdeling van precies deze 4 de puntengrens haalt)."""
    pool = _candidates_player_pool(candidates)
    if len(pool) < 4:
        return None
    def _sterkte(pid):
        if player_ratings and player_ratings.get(pid) is not None:
            return player_ratings[pid]
        return official_ranks_strict.get(pid) or 0
    top4 = set(sorted(pool, key=_sterkte, reverse=True)[:4])
    for cand in candidates:
        if not cand.get("ordered_pairs"):
            continue
        spelers = {p for pair in cand["ordered_pairs"] for p in pair}
        if spelers == top4:
            return cand
    return None
def _own_previous_rotation_pairs(profiles: list, sel_player_id, next_rotation_num: int):
    """PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01 - zie moduledocstring
    (sandbox-preset 'Onze vorige opstelling', verhuisd van lineup_
    sandbox.py._recent_own_lineup_boards()). Geeft (duo_a, duo_b) van ONZE
    EIGEN vorige interclubontmoeting terug voor deze rotatie-positie, als 2
    frozensets - of None als er geen vorige ontmoeting gekend is, of als
    die niet genoeg borden had voor deze rotatie-positie. Faalt altijd
    stil (None), nooit een crash."""
    if not profiles or not sel_player_id:
        return None
    try:
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs, index = _load_encounter_index(profile_ids)
        all_encounters = ll.list_encounters(index)
        own_keys = [key for key, _ in all_encounters if any(pid == str(sel_player_id) for pid, _ in index[key])]
        if not own_keys:
            return None
        most_recent_key = own_keys[0]  # ll.list_encounters() sorteert al datum-aflopend
        boards = ll.reconstruct_boards(index[most_recent_key]) or []
        sorted_boards = sorted(boards, key=lambda b: b.get("board_position") or 0)
        pairs = [tuple(b.get("pair")) for b in sorted_boards if len(b.get("pair") or []) == 2]
        offset = (int(next_rotation_num) - 1) * MATCHES_PER_ROTATION
        if offset + 1 >= len(pairs):
            return None
        return frozenset(pairs[offset]), frozenset(pairs[offset + 1])
    except Exception:  # noqa: BLE001
        return None
def _render_own_lineup_quick_presets(
    candidates: list, profiles, sel_player_id, player_ratings: dict,
    official_ranks_strict: dict, next_rotation_num: int,
    key_m1p1: str, key_m1p2: str, key_m2p1: str, key_m2p2: str,
    name_lookup_global: dict,
) -> None:
    """PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01 - zie moduledocstring.
    Tekent de 2 overgenomen sandbox-presets BOVENAAN "Zelf samenstellen".
    Een klik vult de 4 BESTAANDE selectbox-keys van de klik-voor-klik-
    bouwer rechtstreeks in (zelfde patroon als de tegenstander-presets
    hierboven) en herlaadt - geen apart bevestig-pad, dus geen risico op
    de eerder gefixte arity-bug."""
    def _fill(duo_a, duo_b) -> None:
        p1a, p2a = tuple(duo_a)
        p1b, p2b = tuple(duo_b)
        st.session_state[key_m1p1] = name_lookup_global.get(p1a, p1a)
        st.session_state[key_m1p2] = name_lookup_global.get(p2a, p2a)
        st.session_state[key_m2p1] = name_lookup_global.get(p1b, p1b)
        st.session_state[key_m2p2] = name_lookup_global.get(p2b, p2b)
        st.rerun(scope="fragment")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Ons sterkste 4 (Elo)", key=f"own_preset_elo_{next_rotation_num}", use_container_width=True):
            sterkste = _strongest_quartet_candidate(candidates, player_ratings, official_ranks_strict)
            if sterkste is None:
                st.warning(
                    "Geen geldige rotatie gevonden met exact de 4 sterkste beschikbare spelers "
                    "(bv. de puntengrens van de gekozen afdeling laat deze combinatie niet toe)."
                )
            else:
                _fill(frozenset(sterkste["ordered_pairs"][0]), frozenset(sterkste["ordered_pairs"][1]))
    with col_b:
        if st.button("Onze vorige opstelling", key=f"own_preset_prev_{next_rotation_num}", use_container_width=True):
            vorige = _own_previous_rotation_pairs(profiles, sel_player_id, next_rotation_num)
            if vorige is None:
                st.warning("Geen vorige eigen opstelling gekend voor deze rotatie-positie.")
            else:
                duo_a, duo_b = vorige
                gevonden = _find_matching_candidate(candidates, duo_a, duo_b)
                if gevonden is None:
                    st.warning(
                        "Onze vorige opstelling op deze positie is nu niet geldig (bv. een speler is "
                        "deze rotatie niet beschikbaar, of het koppel speelde al in een eerdere rotatie)."
                    )
                else:
                    _fill(duo_a, duo_b)
def _render_custom_click_builder(
    candidates: list, name_lookup_global: dict, ploeg_id, next_rotation_num, on_confirm,
    profiles=None, sel_player_id=None, player_ratings: dict = None, official_ranks_strict: dict = None,
) -> None:
    """PADEL_ANALYSIS_ROTATION_PLANNER_PRESETS_2026-09-30 - zie
    moduledocstring voor de volledige toelichting. Bouwt EEN rotatie op uit
    de reeds berekende, gevalideerde `candidates`-lijst, klik voor klik.
    `on_confirm(ordered_pairs, win_probs)` is de 2-argumenten-wrapper rond
    _bevestig_rotatie() uit _render_rotation_planner() - zie
    PADEL_ANALYSIS_PRESET_CONFIRM_ARITY_FIX_2026-09-30.
    PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01: `profiles`/`sel_player_id`/
    `player_ratings`/`official_ranks_strict` zijn nieuw - enkel gebruikt
    voor de 2 overgenomen sandbox-presets bovenaan (zie moduledocstring).
    Zonder deze 4 argumenten (bv. een oudere aanroeper) vallen enkel die 2
    preset-knoppen weg; de rest van deze functie werkt ONGEWIJZIGD."""
    geen_keuze = "- Kies -"
    kp = f"custom_{ploeg_id}_{next_rotation_num}"
    key_m1p1_vooraf, key_m1p2_vooraf = f"{kp}_m1p1", f"{kp}_m1p2"
    key_m2p1_vooraf, key_m2p2_vooraf = f"{kp}_m2p1", f"{kp}_m2p2"
    if profiles is not None or player_ratings is not None:
        _render_own_lineup_quick_presets(
            candidates, profiles, sel_player_id, player_ratings or {}, official_ranks_strict or {},
            next_rotation_num, key_m1p1_vooraf, key_m1p2_vooraf, key_m2p1_vooraf, key_m2p2_vooraf,
            name_lookup_global,
        )
        st.divider()
    m1_opties = [geen_keuze] + [
        name_lookup_global.get(pid, pid) for pid in _match1_eligible_players(candidates)
    ]
    label_to_id = {name_lookup_global.get(pid, pid): pid for pid in _match1_eligible_players(candidates)}
    col1, col2 = st.columns(2)
    with col1:
        key_m1p1 = f"{kp}_m1p1"
        if st.session_state.get(key_m1p1) not in m1_opties:
            st.session_state[key_m1p1] = geen_keuze
        lbl_m1p1 = st.selectbox("Match 1 - speler 1", m1_opties, key=key_m1p1)
    m1p1_id = label_to_id.get(lbl_m1p1) if lbl_m1p1 != geen_keuze else None
    with col2:
        if m1p1_id is not None:
            partner_ids = _match1_partners_for(candidates, m1p1_id)
            m1p2_opties = [geen_keuze] + [name_lookup_global.get(pid, pid) for pid in partner_ids]
            partner_label_to_id = {name_lookup_global.get(pid, pid): pid for pid in partner_ids}
        else:
            m1p2_opties = [geen_keuze]
            partner_label_to_id = {}
        key_m1p2 = f"{kp}_m1p2"
        if st.session_state.get(key_m1p2) not in m1p2_opties:
            st.session_state[key_m1p2] = geen_keuze
        lbl_m1p2 = st.selectbox("Match 1 - speler 2", m1p2_opties, key=key_m1p2)
    m1p2_id = partner_label_to_id.get(lbl_m1p2) if lbl_m1p2 != geen_keuze else None
    duo_a = frozenset({m1p1_id, m1p2_id}) if (m1p1_id and m1p2_id) else None
    col3, col4 = st.columns(2)
    duo_b_opties = _match2_options_for_duo_a(candidates, duo_a) if duo_a else []
    m2_spelers = sorted({pid for duo_b in duo_b_opties for pid in duo_b})
    with col3:
        if duo_a is not None:
            m2p1_opties = [geen_keuze] + [name_lookup_global.get(pid, pid) for pid in m2_spelers]
            m2p1_label_to_id = {name_lookup_global.get(pid, pid): pid for pid in m2_spelers}
        else:
            m2p1_opties = [geen_keuze]
            m2p1_label_to_id = {}
        key_m2p1 = f"{kp}_m2p1"
        if st.session_state.get(key_m2p1) not in m2p1_opties:
            st.session_state[key_m2p1] = geen_keuze
        lbl_m2p1 = st.selectbox("Match 2 - speler 1", m2p1_opties, key=key_m2p1)
    m2p1_id = m2p1_label_to_id.get(lbl_m2p1) if lbl_m2p1 != geen_keuze else None
    with col4:
        if m2p1_id is not None:
            m2p2_ids = sorted({
                pid for duo_b in duo_b_opties for pid in duo_b
                if m2p1_id in duo_b and pid != m2p1_id
            })
            m2p2_opties = [geen_keuze] + [name_lookup_global.get(pid, pid) for pid in m2p2_ids]
            m2p2_label_to_id = {name_lookup_global.get(pid, pid): pid for pid in m2p2_ids}
        else:
            m2p2_opties = [geen_keuze]
            m2p2_label_to_id = {}
        key_m2p2 = f"{kp}_m2p2"
        if st.session_state.get(key_m2p2) not in m2p2_opties:
            st.session_state[key_m2p2] = geen_keuze
        lbl_m2p2 = st.selectbox("Match 2 - speler 2", m2p2_opties, key=key_m2p2)
    m2p2_id = m2p2_label_to_id.get(lbl_m2p2) if lbl_m2p2 != geen_keuze else None
    if not (duo_a and m2p1_id and m2p2_id):
        st.info("Kies hierboven alle 4 spelers om deze rotatie samen te stellen.")
        return
    duo_b = frozenset({m2p1_id, m2p2_id})
    gevonden = _find_matching_candidate(candidates, duo_a, duo_b)
    if gevonden is None:
        # Defensief: kan enkel gebeuren als candidates tussen 2 renders
        # wijzigde (bv. een andere instelling hierboven veranderde net).
        st.warning(
            "Deze combinatie kon niet teruggevonden worden in de berekende combinaties - "
            "wijzig een keuze hierboven om opnieuw te proberen."
        )
        return
    ordered_pairs = gevonden["ordered_pairs"]
    win_probs = [a.get("win_probability") for a in gevonden["assignment"]] if gevonden.get("assignment") else [None, None]
    ebw = gevonden.get("expected_boards_won")
    p1a, p2a = tuple(ordered_pairs[0])
    p1b, p2b = tuple(ordered_pairs[1])
    st.success(
        f"Match 1: **{name_lookup_global.get(p1a, p1a)} / {name_lookup_global.get(p2a, p2a)}**  -  "
        f"Match 2: **{name_lookup_global.get(p1b, p1b)} / {name_lookup_global.get(p2b, p2b)}**"
        + (f" (verwacht {ebw:.2f} gewonnen matchen)" if ebw is not None else "")
    )
    if st.button("Bevestig deze keuze", key=f"{kp}_confirm", type="primary"):
        on_confirm(ordered_pairs, win_probs)
# -----------------------------------------------
# Rotatieplanner - combinatoriek (1 rotatie tegelijk, ONGEWIJZIGD)
# -----------------------------------------------
def _count_perfect_matchings(n: int) -> int:
    if n < 2 or n % 2 != 0:
        return 0
    result = 1
    k = n - 1
    while k > 0:
        result *= k
        k -= 2
    return result
_ROTATION_EXHAUSTIVE_LIMIT = 400
# -----------------------------------------------
# Rotatie-bewuste enumeratie (rotatie-veilige koppelverdeling over ALLE
# borden van de ontmoeting)
# -----------------------------------------------
def _all_perfect_matchings_generic(seq: list) -> list:
    if len(seq) == 0:
        return [[]]
    if len(seq) % 2 != 0:
        return []
    first, rest = seq[0], seq[1:]
    out: list = []
    for i, partner in enumerate(rest):
        remaining = rest[:i] + rest[i + 1:]
        for sub in _all_perfect_matchings_generic(remaining):
            out.append([frozenset({first, partner})] + sub)
    return out
def _enumerate_rotation_aware_pairings(
    player_ids: list, required_counts: dict, call_budget: int = 300_000,
) -> tuple:
    total_slots = sum(required_counts.values())
    if total_slots == 0 or total_slots % 2 != 0:
        return [], False
    n_boards = total_slots // 2
    rotation_sizes = []
    remaining_boards = n_boards
    while remaining_boards > 0:
        take = min(MATCHES_PER_ROTATION, remaining_boards)  # PADEL_ANALYSIS_ENCOUNTER_FORMAT_2026-09-29
        rotation_sizes.append(take)
        remaining_boards -= take
    results: list = []
    seen_keys = set()
    calls = [0]
    truncated = [False]
    def backtrack(rotation_idx, remaining, used_partner_pairs, rotations_so_far):
        calls[0] += 1
        if calls[0] > call_budget:
            truncated[0] = True
            return
        if rotation_idx == len(rotation_sizes):
            key = tuple(
                tuple(sorted(tuple(sorted(pair)) for pair in rot))
                for rot in rotations_so_far
            )
            if key not in seen_keys:
                seen_keys.add(key)
                results.append([list(rot) for rot in rotations_so_far])
            return
        boards_needed = rotation_sizes[rotation_idx]
        players_needed = boards_needed * 2
        eligible = sorted(p for p in player_ids if remaining[p] > 0)
        if len(eligible) < players_needed:
            return
        for combo in itertools.combinations(eligible, players_needed):
            matchings = _all_perfect_matchings_generic(list(combo))
            for matching in matchings:
                if any(pair in used_partner_pairs for pair in matching):
                    continue
                for pair in matching:
                    for p in pair:
                        remaining[p] -= 1
                rotations_so_far.append(matching)
                new_used = used_partner_pairs | set(matching)
                backtrack(rotation_idx + 1, remaining, new_used, rotations_so_far)
                rotations_so_far.pop()
                for pair in matching:
                    for p in pair:
                        remaining[p] += 1
                if calls[0] > call_budget:
                    return
    backtrack(0, dict(required_counts), set(), [])
    return results, truncated[0]
def _default_opponent_max_per_player(chosen_opp_ids: list, needed_slots: int) -> dict:
    n = len(chosen_opp_ids)
    if n == 0:
        return {}
    base = needed_slots // n
    extra = needed_slots % n
    return {pid: base + (1 if i < extra else 0) for i, pid in enumerate(chosen_opp_ids)}
# -----------------------------------------------
# Bordvolgorde: officiele regel + padelstat-tie-breaker
# -----------------------------------------------
def _pair_official_sum(pair, official_ranks: dict) -> float:
    return sum((official_ranks.get(pid) or 0) for pid in pair)
def _pair_official_sum_safe(pair, official_ranks: dict) -> tuple:
    known = [official_ranks.get(pid) for pid in pair]
    is_compleet = all(v is not None for v in known)
    total = sum((v or 0) for v in known)
    return total, is_compleet
def _pair_padelstat_sum(pair, padelstat_ratings: dict) -> float:
    return sum((padelstat_ratings.get(pid) or 0) for pid in pair)
def _rank_pairs_with_padelstat_tiebreak(
    pairs: list, official_ranks: dict, padelstat_ratings: dict,
) -> list:
    def sort_key(pair):
        official_sum = _pair_official_sum(pair, official_ranks)
        padelstat_sum = _pair_padelstat_sum(pair, padelstat_ratings)
        return (official_sum, padelstat_sum)
    return sorted(pairs, key=sort_key, reverse=True)
def _rotation_has_missing_official_rank(duo_a, duo_b, official_ranks: dict) -> bool:
    _, complete_a = _pair_official_sum_safe(duo_a, official_ranks)
    _, complete_b = _pair_official_sum_safe(duo_b, official_ranks)
    return not (complete_a and complete_b)
def _order_rotations_with_tiebreak(
    rotation_structure: list, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
    ordered_pairs = []
    rotation_results = []
    all_valid = True
    for rotation in rotation_structure:
        if len(rotation) < 2:
            ordered_pairs.extend(rotation)
            rotation_results.append({"total_points": None, "valid": True, "reason": "onvolledige rotatie"})
            continue
        duo_a, duo_b = rotation[0], rotation[1]
        ranked = _rank_pairs_with_padelstat_tiebreak([duo_a, duo_b], official_ranks, padelstat_ratings)
        ordered_pairs.extend(ranked)
        total_points = _pair_official_sum(duo_a, official_ranks) + _pair_official_sum(duo_b, official_ranks)
        valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
        if rules is not None:
            lo, hi = rules["punten_min"], rules["punten_max"]
            if total_points < lo:
                valid, reason = False, f"{total_points:.0f} < min {lo}"
            elif total_points > hi:
                valid, reason = False, f"{total_points:.0f} > max {hi}"
            else:
                valid, reason = True, f"{total_points:.0f} punten (toegelaten: {lo}-{hi})"
        rotation_results.append({"total_points": total_points, "valid": valid, "reason": reason})
        if not valid:
            all_valid = False
    return {"ordered_pairs": ordered_pairs, "rotations": rotation_results, "all_valid": all_valid}
def _build_opponent_boards_and_points(
    rotation_structure: list, name_by_id: dict, rank_by_id: dict, padelstat_by_id: dict,
) -> list:
    ordered = _order_rotations_with_tiebreak(rotation_structure, rank_by_id, padelstat_by_id, rules=None)
    boards = []
    for pair in ordered["ordered_pairs"]:
        p1, p2 = tuple(pair)
        boards.append({"opponent_pair": [
            {"name": name_by_id.get(p1, p1), "user_id": p1,
             "ranking": (f"P{int(rank_by_id[p1])}" if rank_by_id.get(p1) is not None else None)},
            {"name": name_by_id.get(p2, p2), "user_id": p2,
             "ranking": (f"P{int(rank_by_id[p2])}" if rank_by_id.get(p2) is not None else None)},
        ]})
    return boards
def _generate_theoretical_opponent_boards_with_repeats(
    chosen_opp_players: list, opponent_max_per_player: dict, opponent_official_ranks: dict,
    opponent_padelstat_ratings: dict, max_variants: int,
) -> tuple:
    ids = [str(p["user_id"]) for p in chosen_opp_players]
    name_by_id = {str(p["user_id"]): p.get("name", str(p["user_id"])) for p in chosen_opp_players}
    structures, truncated = _enumerate_rotation_aware_pairings(ids, opponent_max_per_player)
    total_theoretical = len(structures)
    all_boards = []
    for structure in structures[:max_variants]:
        boards = _build_opponent_boards_and_points(structure, name_by_id, opponent_official_ranks, opponent_padelstat_ratings)
        all_boards.append(boards)
    meta = {
        "total_theoretical": total_theoretical,
        "truncated": truncated or total_theoretical > len(all_boards),
        "players_used": len(ids),
    }
    return all_boards, meta
def _historical_opponent_boards_list(bundle: dict) -> list:
    out = []
    for fx_bundle in bundle.get("previous_fixtures", []) or []:
        boards = fx_bundle.get("boards") or []
        fx = fx_bundle.get("fixture", {}) or {}
        if fx_bundle.get("error") or not boards:
            continue
        sorted_boards = sorted(boards, key=lambda b: b.get("board_position") or 0)
        label = fx.get("date_text") or "onbekende datum"
        out.append((label, sorted_boards))
    return out
def _opponent_lineup_key(boards: list):
    pairs = []
    for b in boards:
        uids = frozenset(str(p.get("user_id")) for p in (b.get("opponent_pair") or []) if p.get("user_id"))
        if len(uids) == 2:
            pairs.append(uids)
    if not pairs:
        return None
    return tuple(pairs)
def _collect_unique_opponent_lineups(historical_boards_with_labels: list, theoretical_boards: list) -> dict:
    unique: dict = {}
    for label, boards in historical_boards_with_labels:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        entry = unique.setdefault(key, {"boards": boards, "is_historical": False, "historical_labels": []})
        entry["is_historical"] = True
        entry["historical_labels"].append(label)
        entry["historical_count"] = entry.get("historical_count", 0) + 1
    for boards in theoretical_boards:
        key = _opponent_lineup_key(boards)
        if key is None:
            continue
        if key not in unique:
            unique[key] = {
                "boards": boards, "is_historical": False,
                "historical_labels": [], "historical_count": 0,
            }
    return unique
# -----------------------------------------------
# Best/worst-case variant-enumeratie
# -----------------------------------------------
def _rotation_order_variants(
    duo_a, duo_b, official_ranks: dict, padelstat_ratings: dict, rules=None,
) -> dict:
    """PADEL_ANALYSIS_MISSING_RANK_ORDER_BIAS_FIX_2026-09-21: zie de
    oorspronkelijke docstring in page_lineup_lab.py voor de volledige
    root-cause-analyse - functioneel ONGEWIJZIGD."""
    sum_a, complete_a = _pair_official_sum_safe(duo_a, official_ranks)
    sum_b, complete_b = _pair_official_sum_safe(duo_b, official_ranks)
    total_points = sum_a + sum_b
    rank_data_incomplete = not (complete_a and complete_b)
    valid, reason = True, f"{total_points:.0f} punten (geen reglement-check actief)"
    if rules is not None:
        lo, hi = rules["punten_min"], rules["punten_max"]
        if total_points < lo:
            valid, reason = False, f"{total_points:.0f} < min {lo}"
        elif total_points > hi:
            valid, reason = False, f"{total_points:.0f} > max {hi}"
        else:
            valid, reason = True, f"{total_points:.0f} punten (toegelaten: {lo}-{hi})"
    ranked = _rank_pairs_with_padelstat_tiebreak([duo_a, duo_b], official_ranks, padelstat_ratings)
    first_guess, second_guess = ranked[0], ranked[1]
    punten_txt = f"officieel {sum_a:.0f} vs {sum_b:.0f} punten"
    if rank_data_incomplete:
        onvolledig_txt = (
            f"{punten_txt} - ONVOLLEDIG officieel klassement (min. 1 speler ontbreekt): "
            "welk duo echt sterkst is, kan NIET betrouwbaar bepaald worden"
        )
        variants = [
            {
                "ordered_pairs": [first_guess, second_guess],
                "is_regulation_compliant": None,
                "rank_data_incomplete": True,
                "swap_label": onvolledig_txt + " - vermoedelijke volgorde o.b.v. padelstat, NIET bevestigd",
                "total_points": total_points, "valid": valid, "reason": reason,
            },
            {
                "ordered_pairs": [second_guess, first_guess],
                "is_regulation_compliant": None,
                "rank_data_incomplete": True,
                "swap_label": onvolledig_txt + " - omgekeerde volgorde, EVENZEER niet bevestigd",
                "total_points": total_points, "valid": valid, "reason": reason,
            },
        ]
        return {"variants": variants}
    is_tie = (sum_a == sum_b)
    compliant_first, compliant_second = first_guess, second_guess
    first_label = (
        f"gelijke officiele sterkte ({punten_txt}) - aanbevolen o.b.v. padelstat" if is_tie
        else f"{punten_txt} - sterkste eerst (art. 6.6)"
    )
    variants = [{
        "ordered_pairs": [compliant_first, compliant_second],
        "is_regulation_compliant": True,
        "rank_data_incomplete": False,
        "swap_label": first_label,
        "total_points": total_points, "valid": valid, "reason": reason,
    }]
    if is_tie:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": True,
            "rank_data_incomplete": False,
            "swap_label": f"gelijke officiele sterkte ({punten_txt}) - alternatieve, even geldige keuze",
            "total_points": total_points, "valid": valid, "reason": reason,
        })
    else:
        variants.append({
            "ordered_pairs": [compliant_second, compliant_first],
            "is_regulation_compliant": False,
            "rank_data_incomplete": False,
            "swap_label": (
                f"NIET reglementair ({punten_txt}, omgedraaid): het sterkere duo moet "
                "normaliter eerst spelen (art. 6.6)"
            ),
            "total_points": total_points, "valid": valid, "reason": reason,
        })
    return {"variants": variants}
def _enumerate_own_variant_combinations(
    rotation_structure: list, official_ranks: dict, padelstat_ratings: dict,
    rules=None, include_non_compliant: bool = False,
) -> list:
    per_rotation_variant_lists = []
    for rotation in rotation_structure:
        if len(rotation) < 2:
            per_rotation_variant_lists.append([{
                "ordered_pairs": list(rotation), "is_regulation_compliant": True,
                "swap_label": "", "total_points": None, "valid": True, "reason": "onvolledige rotatie",
                "rank_data_incomplete": False,
            }])
            continue
        duo_a, duo_b = rotation[0], rotation[1]
        result = _rotation_order_variants(duo_a, duo_b, official_ranks, padelstat_ratings, rules=rules)
        variants = result["variants"]
        if not include_non_compliant:
            variants = [v for v in variants if v["is_regulation_compliant"] is not False]
        per_rotation_variant_lists.append(variants)
    combinations = []
    for combo in itertools.product(*per_rotation_variant_lists):
        ordered_pairs = []
        rotations_info = []
        fully_compliant = True
        any_rank_data_incomplete = False
        for variant in combo:
            ordered_pairs.extend(variant["ordered_pairs"])
            rotations_info.append({
                "total_points": variant["total_points"], "valid": variant["valid"],
                "reason": variant["reason"], "swap_label": variant["swap_label"],
                "is_regulation_compliant": variant["is_regulation_compliant"],
                "rank_data_incomplete": variant.get("rank_data_incomplete", False),
            })
            if variant["is_regulation_compliant"] is False:
                fully_compliant = False
            if variant.get("rank_data_incomplete"):
                any_rank_data_incomplete = True
        combinations.append({
            "ordered_pairs": ordered_pairs, "rotations": rotations_info,
            "fully_compliant": fully_compliant,
            "rank_data_incomplete": any_rank_data_incomplete,
        })
    return combinations
def _compute_matchup(
    own_ordered_pairs: list, opp_boards: list,
    synergy_fn, player_ratings: dict, official_ranks_strict: dict, opponent_ratings: dict,
) -> dict:
    """PADEL_ANALYSIS_POINT_PROBABILITY_2026-09-30: berekent nu ook
    "point_probs" (exacte 2/1/0-puntenkans, zie
    _match_outcome_point_probabilities()) en "n_missing_win_probs" naast de
    bestaande, ONGEWIJZIGDE velden (assignment/expected_boards_won/
    total_score). De volgorde en inhoud van 'assignment' is exact hetzelfde
    als voorheen - enkel deze 2 nieuwe top-level velden zijn toegevoegd."""
    assignment = []
    expected_boards_won = 0.0
    total_score = 0.0
    win_probs_for_points = []
    n = min(len(own_ordered_pairs), len(opp_boards))
    for i in range(n):
        p1, p2 = tuple(own_ordered_pairs[i])
        syn = synergy_fn(p1, p2)
        board = opp_boards[i]
        opp_pair = board.get("opponent_pair", []) or []
        our_eff = [
            ll.effective_simulation_rating(p1, player_ratings, official_ranks_strict),
            ll.effective_simulation_rating(p2, player_ratings, official_ranks_strict),
        ]
        their_eff = [
            ll.effective_simulation_rating(
                p.get("user_id"), opponent_ratings,
                {p.get("user_id"): ll.parse_ranking(p.get("ranking"))},
            )
            for p in opp_pair
        ]
        our_eff_known = [v for v in our_eff if v is not None]
        their_eff_known = [v for v in their_eff if v is not None]
        our_avg = (sum(our_eff_known) / len(our_eff_known)) if our_eff_known else None
        their_avg = (sum(their_eff_known) / len(their_eff_known)) if their_eff_known else None
        edge = ll.matchup_edge(our_eff, their_eff)
        win_prob = ll.estimate_win_probability(our_avg, their_avg)
        win_probs_for_points.append(win_prob)
        if win_prob is not None:
            expected_boards_won += win_prob
        total_score += syn + edge
        assignment.append({
            "our_pair": (p1, p2),
            "synergy": round(syn, 3),
            "edge": round(edge, 3),
            "win_probability": round(win_prob, 3) if win_prob is not None else None,
            "risk_note": ll.risk_note_for_probability(win_prob),
            "our_effective_rating": round(our_avg, 1) if our_avg is not None else None,
            "their_effective_rating": round(their_avg, 1) if their_avg is not None else None,
            "opponent_board": board,
        })
    point_probs = _match_outcome_point_probabilities(win_probs_for_points)
    return {
        "assignment": assignment,
        "expected_boards_won": round(expected_boards_won, 2),
        "total_score": round(total_score, 3),
        "point_probs": point_probs,
        "n_missing_win_probs": _n_missing_win_probs(win_probs_for_points),
    }
def _expand_tied_orderings(
    results: list, official_ranks_strict: dict, padelstat_ratings: dict,
    tournament_rules_dict, excluded_pairs: set,
    opponent_boards=None, synergy_fn=None, player_ratings: dict = None,
    opponent_ratings: dict = None,
) -> tuple:
    """PADEL_ANALYSIS_ROTATION_TIE_VARIANTS_2026-09-25: zie de
    oorspronkelijke docstring in page_lineup_lab.py voor de volledige
    root-cause-analyse - functioneel ONGEWIJZIGD."""
    expanded = []
    seen_keys = set()
    for cand in results:
        pairs = list(cand["ordered_pairs"])
        n_rot = -(-len(pairs) // 2)
        variant_choices = []
        for r in range(n_rot):
            chunk = pairs[r * 2: r * 2 + 2]
            if len(chunk) < 2:
                variant_choices.append([tuple(chunk)])
                continue
            duo_a, duo_b = chunk[0], chunk[1]
            vr = _rotation_order_variants(duo_a, duo_b, official_ranks_strict, padelstat_ratings, rules=tournament_rules_dict)
            opts = [tuple(v["ordered_pairs"]) for v in vr["variants"] if v["is_regulation_compliant"] is not False]
            variant_choices.append(opts or [(duo_a, duo_b)])
        for combo in itertools.product(*variant_choices):
            new_pairs = [p for chunk in combo for p in chunk]
            if any(p in excluded_pairs for p in new_pairs):
                continue
            key = tuple(frozenset(p) for p in new_pairs)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if new_pairs == pairs:
                expanded.append(cand)
                continue
            if opponent_boards and player_ratings is not None and synergy_fn is not None:
                computed = _compute_matchup(
                    new_pairs, opponent_boards, synergy_fn, player_ratings,
                    official_ranks_strict, opponent_ratings or {},
                )
                expanded.append({
                    "expected_boards_won": computed["expected_boards_won"],
                    "score": computed["total_score"],
                    "ordered_pairs": new_pairs,
                    "assignment": computed["assignment"],
                    "rotations": cand.get("rotations"),
                })
            else:
                rotation_eval = ll.filter_and_order_lineup_by_rotations(
                    [frozenset(p) for p in new_pairs], official_ranks_strict, rules=tournament_rules_dict,
                )
                if tournament_rules_dict is not None and not rotation_eval["all_valid"]:
                    continue
                expanded.append({
                    "expected_boards_won": None,
                    "score": cand["score"],
                    "ordered_pairs": rotation_eval["ordered_pairs"],
                    "assignment": None,
                    "rotations": rotation_eval["rotations"],
                })
    return expanded
def _rotation_boards_for(opponent_boards, rotation_number: int):
    """PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29: geeft de tegenstander-borden voor DEZE rotatie
    terug (precies MATCHES_PER_ROTATION stuks), of None als die niet gekend
    zijn. Accepteert zowel enkel de borden van deze rotatie als de borden van
    de volledige ontmoeting (dan wordt het juiste stuk eruit gesneden)."""
    if not opponent_boards:
        return None
    boards = list(opponent_boards)
    if len(boards) == MATCHES_PER_ROTATION:
        return boards
    offset = (int(rotation_number) - 1) * MATCHES_PER_ROTATION
    stuk = boards[offset: offset + MATCHES_PER_ROTATION]
    return stuk if len(stuk) == MATCHES_PER_ROTATION else None
def _generate_rotation_candidates(
    available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
    opponent_boards=None, player_ratings=None, opponent_ratings=None,
    max_results=10, tournament_rules_dict=None,
    rotation_number: int = 1, player_budget: dict = None,
):
    """PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29 (op verzoek van Kim): kiest per rotatie EXACT
    MATCHES_PER_ROTATION (=2) koppels uit de beschikbare spelers.
    VOORHEEN deelde deze functie ALLE geselecteerde spelers in koppels in
    (perfect matching over de hele selectie): bij 6 spelers dus 3 koppels,
    terwijl een rotatie er maar 2 heeft - en een oneven aantal spelers
    blokkeerde de planner volledig.
    NU: elke combinatie van 4 spelers x elke manier om die in 2 koppels te
    verdelen (3 per combinatie) is een kandidaat, zolang:
      - geen van beide koppels al in een eerdere, bevestigde rotatie speelde
        (excluded_pairs - reglement: een koppel speelt maar 1 keer samen);
      - elke speler nog 'budget' heeft (player_budget: resterend aantal
        matchen per speler, uit 'max. matchen per speler' min wat al
        bevestigd is; None = geen beperking);
      - de puntengrens van de gekozen afdeling gerespecteerd wordt.
    De bordvolgorde (art. 6.6, sterkste duo op match 1, padelstat als
    tiebreak, beide volgordes bij gelijkspel of onvolledig klassement) komt
    uit _rotation_order_variants() - dezelfde regel als in de rest van de
    app. Zijn de tegenstanders van deze rotatie gekend, dan wordt
    gerangschikt op verwacht aantal gewonnen matchen; anders op synergie.
    Geeft (kandidaten[:max_results], totaal_mogelijk, diagnostiek) terug -
    hetzelfde contract als voorheen, zodat de UI ongewijzigd blijft."""
    per_rot = MATCHES_PER_ROTATION
    need = per_rot * 2
    eligible = sorted({
        str(p) for p in available_ids
        if player_budget is None or (player_budget.get(str(p), 0) or 0) > 0
    })
    if len(eligible) < need:
        return [], 0, None
    rot_boards = _rotation_boards_for(opponent_boards, rotation_number)
    padelstat = player_ratings or {}
    excluded = {frozenset(str(x) for x in p) for p in (excluded_pairs or set())}
    results = []
    seen = set()
    total_possible = 0
    excluded_by_rules = 0
    rotation_points_seen = []
    for combo in itertools.combinations(eligible, need):
        for matching in _all_perfect_matchings_generic(list(combo)):
            if any(pair in excluded for pair in matching):
                continue
            total_possible += 1
            duo_a, duo_b = matching[0], matching[1]
            variants = _rotation_order_variants(
                duo_a, duo_b, official_ranks_strict, padelstat, rules=tournament_rules_dict,
            )["variants"]
            variants = [v for v in variants if v["is_regulation_compliant"] is not False]
            if not variants:
                continue
            if variants[0].get("total_points") is not None:
                rotation_points_seen.append(variants[0]["total_points"])
            if tournament_rules_dict is not None and not variants[0]["valid"]:
                excluded_by_rules += 1
                continue
            for v in variants:
                pairs = [frozenset(p) for p in v["ordered_pairs"]]
                key = tuple(pairs)
                if key in seen:
                    continue
                seen.add(key)
                rot_info = [{
                    "total_points": v["total_points"], "valid": v["valid"],
                    "reason": v["reason"], "swap_label": v.get("swap_label", ""),
                    "is_regulation_compliant": v["is_regulation_compliant"],
                    "rank_data_incomplete": v.get("rank_data_incomplete", False),
                }]
                if rot_boards and player_ratings is not None:
                    computed = _compute_matchup(
                        pairs, rot_boards, synergy_fn, player_ratings,
                        official_ranks_strict, opponent_ratings or {},
                    )
                    results.append({
                        "expected_boards_won": computed["expected_boards_won"],
                        "score": computed["total_score"],
                        "ordered_pairs": pairs,
                        "assignment": computed["assignment"],
                        "rotations": rot_info,
                        "point_probs": computed.get("point_probs"),
                    })
                else:
                    score = sum(synergy_fn(*tuple(p)) for p in pairs)
                    results.append({
                        "expected_boards_won": None, "score": round(score, 3),
                        "ordered_pairs": pairs, "assignment": None,
                        "rotations": rot_info, "point_probs": None,
                    })
    results.sort(key=lambda r: (
        -(r["expected_boards_won"] if r["expected_boards_won"] is not None else -1),
        -r["score"],
    ))
    diagnostics = {
        "candidates_total": total_possible,
        "candidates_excluded_by_rules": excluded_by_rules,
        "rotation_points_seen": rotation_points_seen,
    }
    return results[:max_results], total_possible, diagnostics
def _lineup_options_for_ai(candidates: list, name_lookup: dict) -> list:
    out = []
    for cand in candidates:
        assignment = []
        if cand["assignment"]:
            for a in cand["assignment"]:
                assignment.append({
                    "our_pair": tuple(a["our_pair"]), "synergy": a.get("synergy", 0.0),
                    "edge": a.get("edge", 0.0), "opponent_board": a.get("opponent_board", {}),
                })
        else:
            for pair in cand["ordered_pairs"]:
                p1, p2 = tuple(pair)
                assignment.append({"our_pair": (p1, p2), "synergy": 0.0, "edge": 0.0, "opponent_board": {"opponent_pair": []}})
        out.append({"total_score": cand["score"], "assignment": assignment})
    return out
def _render_rotation_points_caption(rotations: list) -> None:
    if not rotations:
        return
    for i, rot in enumerate(rotations, start=1):
        if rot.get("total_points") is None:
            continue
        if rot.get("rank_data_incomplete"):
            st.caption(f"Rotatie {i}: {rot.get('reason', '')} - minstens 1 speler heeft nog geen bekend officieel klassement, deze volgorde is NIET betrouwbaar geverifieerd.")
            continue
        icon = "OK" if rot.get("valid", True) else "FOUT"
        st.caption(f"{icon} Rotatie {i}: {rot.get('reason', '')}")
def _render_assignment_with_outcome(assignment: list, name_lookup_global: dict) -> None:
    for a in assignment:
        p1, p2 = a["our_pair"]
        opp_pair = a["opponent_board"]["opponent_pair"]
        opp_names = " / ".join(p.get("name", "?") for p in opp_pair)
        wp = a.get("win_probability")
        risk = a.get("risk_note", "")
        our_r = a.get("our_effective_rating")
        their_r = a.get("their_effective_rating")
        if wp is not None:
            wp_txt = f"**{int(round(wp * 100))}% winkans** ({risk})"
        else:
            wp_txt = "winkans onbekend (onvoldoende rating-data)"
        rating_txt = ""
        if our_r is not None and their_r is not None:
            rating_txt = f" - inschatting {our_r:.0f} vs {their_r:.0f}"
        st.write(
            f"**{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
            f"(synergie {a['synergy']}) - vs **{opp_names}**: {wp_txt}{rating_txt}"
        )
def _render_encounter_summary(
    locked_rotations: list, locked_opponents: list, locked_win_probs_per_rotation: list,
    name_lookup_global: dict,
) -> None:
    """PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01 - zie moduledocstring.
    Toont, zodra ALLE rotaties van de ontmoeting bevestigd zijn, een
    eindsamenvatting: de 4 (of n) matchen op een rij, en de EXACTE P(2)/
    P(1)/P(0) over de VOLLEDIGE ontmoeting - hergebruikt
    _match_outcome_point_probabilities() met de effectief gekozen
    winkansen (GEEN placeholder/50% nodig, want alles ligt al vast)."""
    flat_win_probs = [wp for rotatie in locked_win_probs_per_rotation for wp in rotatie]
    pp = _match_outcome_point_probabilities(flat_win_probs)
    n_missing = _n_missing_win_probs(flat_win_probs)
    st.markdown("**Eindresultaat van deze ontmoeting:**")
    col_p2, col_p1, col_p0 = st.columns(3)
    with col_p2:
        st.metric("Kans 2p (winst)", f"{pp['p2'] * 100:.0f}%")
    with col_p1:
        st.metric("Kans 1p (gelijk)", f"{pp['p1'] * 100:.0f}%")
    with col_p0:
        st.metric("Kans 0p (verlies)", f"{pp['p0'] * 100:.0f}%")
    if n_missing:
        st.caption(
            f"{n_missing} match(en) zonder bekende winkans (tegenstander destijds niet gekozen) - "
            "geteld als 50/50 in bovenstaande kansen."
        )
    for rot_idx, pairs in enumerate(locked_rotations, start=1):
        opp_voor_rotatie = (
            locked_opponents[rot_idx - 1] if rot_idx - 1 < len(locked_opponents) else None
        )
        win_probs_voor_rotatie = (
            locked_win_probs_per_rotation[rot_idx - 1] if rot_idx - 1 < len(locked_win_probs_per_rotation) else [None, None]
        )
        for match_idx, pair in enumerate(pairs, start=1):
            p1, p2 = tuple(pair)
            ons = f"{name_lookup_global.get(p1, p1)} / {name_lookup_global.get(p2, p2)}"
            tegen = ""
            if opp_voor_rotatie and match_idx - 1 < len(opp_voor_rotatie):
                namen = [x.get("name", "?") for x in opp_voor_rotatie[match_idx - 1]]
                if namen:
                    tegen = f" - tegen **{' / '.join(namen)}**"
            wp = win_probs_voor_rotatie[match_idx - 1] if match_idx - 1 < len(win_probs_voor_rotatie) else None
            wp_txt = f" ({int(round(wp * 100))}% winkans)" if wp is not None else " (winkans onbekend)"
            st.write(f"Rotatie {rot_idx} - Match {match_idx}: **{ons}**{tegen}{wp_txt}")
# -----------------------------------------------
# PADEL_ANALYSIS_ROTATION_SCENARIO_CARDS_2026-10-02 - zie moduledocstring.
# -----------------------------------------------
_SCENARIO_CARDS_N = 3        # scenario-kaarten bovenaan
_SCENARIO_LIST_MAX = 15      # max. scenario's in totaal (kaarten + lijst)
_SCENARIO_LIST_COVERAGE = 0.80  # stop zodra de getoonde scenario's samen 80% kans dekken
_SCENARIO_POOL = 60          # zoveel scenario's opvragen bij het model
def _model_reliability(n_fix: int) -> tuple:
    """PADEL_ANALYSIS_SCENARIO_LIST_2026-10-03: eerlijk label voor hoe sterk
    de voorspelling onderbouwd is."""
    if n_fix <= 0:
        return "geen", "nog geen eerdere ontmoetingen gekend"
    if n_fix <= 2:
        return "laag", f"slechts {n_fix} eerdere ontmoeting(en) - de kansen zijn een ruwe indicatie"
    if n_fix <= 4:
        return "matig", f"{n_fix} eerdere ontmoetingen"
    return "goed", f"{n_fix} eerdere ontmoetingen"
def _rotation_outcome_markdown(pp: dict, prefix: str = "Deze rotatie") -> str:
    """PADEL_ANALYSIS_ROTATION_LEVEL_NUMBERS_2026-10-03 (Kim: "Hoe kan je
    eigenlijk die getallen al berekenen als rotatie 2 nog niet gecheckt
    is?"): uitkomst van ENKEL deze rotatie (2 matchen), geen 50/50-gok
    voor de rest van de ontmoeting."""
    if not pp:
        return f"**{prefix}:** onbekend"
    w2, w1, w0 = (pp.get(k, 0.0) * 100 for k in ("p2", "p1", "p0"))
    return (
        f"**{prefix}:** :green[**{w2:.0f}% 2-0**] · :orange[**{w1:.0f}% 1-1**] · "
        f":red[**{w0:.0f}% 0-2**]"
    )
def _scenario_boards(pairs: list, names: dict, ranks: dict) -> list:
    """2 tegenstander-koppels (frozensets van uids) -> bord-dicts in het
    formaat dat _compute_matchup() verwacht."""
    boards = []
    for pair in pairs:
        spelers = []
        for uid in sorted(pair):
            r = ranks.get(uid)
            spelers.append({
                "name": names.get(uid, uid), "user_id": uid,
                "ranking": f"P{int(r)}" if r is not None else None,
            })
        boards.append({"opponent_pair": spelers})
    return boards
def _impact_from_win_probs(locked_flat: list, win_probs: list, total_boards) -> dict:
    wps = list(locked_flat) + list(win_probs)
    if total_boards is not None and int(total_boards) > len(wps):
        wps += [None] * (int(total_boards) - len(wps))
    return _match_outcome_point_probabilities(wps)
def _historical_rotation_lineups(bundle: dict, rotation_num: int, roster: list) -> dict:
    """PADEL_ANALYSIS_SCENARIO_LIST_2026-10-03: {frozenset({m1, m2}): [datums]}
    van de opstellingen die de tegenstander op DEZE rotatie-positie
    effectief speelde. Spelers worden op id OF naam herkend (zelfde speler
    kan in een ouder uitslagenblad een ander id hebben)."""
    uids = {str(p.get("user_id")) for p in roster if p.get("user_id")}
    naam_naar_uid = {_norm_name(p.get("name")): str(p.get("user_id")) for p in roster if p.get("user_id")}
    def _uid(p):
        u = str(p.get("user_id") or "")
        if u in uids:
            return u
        return naam_naar_uid.get(_norm_name(p.get("name")))
    out = {}
    for label, boards in _historical_opponent_boards_list(bundle):
        rot = _rotation_boards_for(boards, rotation_num)
        if not rot or len(rot) != 2:
            continue
        pairs = []
        for b in rot:
            ids = [_uid(p) for p in (b.get("opponent_pair") or [])]
            if len(ids) != 2 or None in ids or ids[0] == ids[1]:
                break
            pairs.append(frozenset(ids))
        else:
            out.setdefault(frozenset(pairs), []).append(label)
    return out
def _compute_opponent_scenario_analysis(
    bundle, unique_opp_players, own_options, synergy_fn, player_ratings,
    official_ranks_strict, opponent_ratings, tournament_rules_dict,
    opp_excluded_pairs, locked_flat, total_boards, next_rotation_num=1,
) -> dict:
    """PADEL_ANALYSIS_SCENARIO_LIST_2026-10-03 - zie moduledocstring.
    Voorspelt de tegenstander-scenario's voor deze rotatie (EEN lijst, met
    de effectief gespeelde opstellingen gemarkeerd i.p.v. een aparte
    snelkeuze-lijst) en berekent per scenario ons beste antwoord."""
    stats = olm.build_opponent_stats(bundle, MATCHES_PER_ROTATION)
    # PADEL_ANALYSIS_SCENARIO_LIST_2026-10-03: namen ALTIJD uit de roster
    # aanvullen - voorheen kwamen enkel spelers uit de gelezen ontmoetingen
    # met naam door, de rest verscheen als id (bv. 1481849).
    roster_names = {
        str(p.get("user_id")): p.get("name") for p in unique_opp_players
        if p.get("user_id") and p.get("name") and p.get("name") != "?"
    }
    stats["names"] = {**stats["names"], **roster_names}
    names = stats["names"]
    roster_uids = [str(p.get("user_id")) for p in unique_opp_players if p.get("user_id")]
    opp_ranks = {u: _cached_official_rank(u) for u in roster_uids}
    opp_ps = {u: _cached_own_player_rating(u) for u in roster_uids}
    opp_ps = {k: v for k, v in opp_ps.items() if v is not None}
    def _order(pairs):
        return _rank_pairs_with_padelstat_tiebreak(pairs, opp_ranks, opp_ps)
    pred = olm.predict_rotation_scenarios(
        stats, unique_opp_players, _order, opp_ranks, rules=tournament_rules_dict,
        excluded_pairs=opp_excluded_pairs, top_n=_SCENARIO_POOL,
    )
    pool = pred["scenarios"]
    gespeeld = _historical_rotation_lineups(bundle, next_rotation_num, unique_opp_players)
    for scen in pool:
        scen["played_on"] = gespeeld.get(frozenset(scen["pairs"]), [])
    shown, cum = [], 0.0
    for scen in pool:
        if len(shown) >= _SCENARIO_LIST_MAX:
            break
        if len(shown) >= _SCENARIO_CARDS_N and cum >= _SCENARIO_LIST_COVERAGE:
            break
        shown.append(scen)
        cum += scen["prob"]
    for scen in pool:  # effectief gespeelde opstellingen altijd tonen
        if scen["played_on"] and scen not in shown:
            shown.append(scen)
            cum += scen["prob"]
    is_final = total_boards is not None and len(locked_flat) + MATCHES_PER_ROTATION >= int(total_boards)
    base = {
        "stats": stats, "scenarios": shown, "n_total": pred["n_total"],
        "coverage": cum, "is_final": is_final, "robust": None,
        "opp_ranks": opp_ranks, "opp_ps": opp_ps,  # PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03
    }
    if not shown or not own_options:
        return base
    tot_w = sum(s["prob"] for s in shown) or 1.0
    per_option = {}
    for scen in shown:
        boards = _scenario_boards(scen["pairs"], names, opp_ranks)
        beste = None
        for o_idx, pairs in enumerate(own_options):
            comp = _compute_matchup(
                pairs, boards, synergy_fn, player_ratings or {},
                official_ranks_strict, opponent_ratings or {},
            )
            wps = [a.get("win_probability") for a in comp["assignment"]]
            rot = _match_outcome_point_probabilities(wps)
            ebw = comp["expected_boards_won"]
            enc = _impact_from_win_probs(locked_flat, wps, total_boards) if is_final else None
            acc = per_option.setdefault(o_idx, {"ebw": 0.0, "rot": {"p2": 0.0, "p1": 0.0, "p0": 0.0},
                                                "enc": {"p2": 0.0, "p1": 0.0, "p0": 0.0}})
            w = scen["prob"] / tot_w
            acc["ebw"] += w * ebw
            for k in ("p2", "p1", "p0"):
                acc["rot"][k] += w * rot[k]
                if enc:
                    acc["enc"][k] += w * enc[k]
            # Niet-laatste rotatie: meeste verwachte gewonnen matchen. Laatste
            # rotatie: hoogste kans op ploegwinst (exact, rest ligt vast).
            sleutel = (enc["p2"], enc["p1"], ebw) if is_final else (ebw, rot["p2"])
            if beste is None or sleutel > beste["sleutel"]:
                beste = {"sleutel": sleutel, "pairs": pairs, "win_probs": wps,
                         "rot": rot, "enc": enc, "ebw": ebw}
        scen["best"] = beste
    if is_final:
        r_idx = max(per_option, key=lambda i: (per_option[i]["enc"]["p2"], per_option[i]["enc"]["p1"]))
    else:
        r_idx = max(per_option, key=lambda i: (per_option[i]["ebw"], per_option[i]["rot"]["p2"]))
    base["robust"] = {
        "pairs": own_options[r_idx], "ebw": per_option[r_idx]["ebw"],
        "rot": per_option[r_idx]["rot"], "enc": per_option[r_idx]["enc"] if is_final else None,
    }
    return base
def _pairs_txt(pairs, name_lookup_global) -> str:
    return "  -  ".join(
        f"M{i}: {' / '.join(name_lookup_global.get(u, u) for u in sorted(p))}"
        for i, p in enumerate(pairs, start=1)
    )
def _answer_txt(best: dict, name_lookup_global: dict) -> str:
    regels = []
    for m_idx, (pair, wp) in enumerate(zip(best["pairs"], best["win_probs"]), start=1):
        wp_txt = f"{wp * 100:.0f}%" if wp is not None else "?"
        regels.append(f"M{m_idx} {' / '.join(name_lookup_global.get(u, u) for u in sorted(pair))} ({wp_txt})")
    return " · ".join(regels)
def _render_opponent_scenario_cards(
    analysis: dict, name_lookup_global: dict, fill_fn, next_rotation_num: int, ploeg_id,
    plan: dict = None,
) -> None:
    """PADEL_ANALYSIS_SCENARIO_LIST_2026-10-03: EEN lijst tegenstander-
    scenario's (top 3 als kaarten, de rest inklapbaar), met de effectief
    gespeelde opstellingen gemarkeerd.
    PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03: `fill_fn(scen)` vult de 4 speler-dropdowns
    in (geeft False als een speler niet in de huidige selectie zit). Met
    `plan` (2-rotatie-modus) is "ons beste antwoord" een volledig plan."""
    stats = analysis["stats"]
    names = stats["names"]
    n_fix = stats.get("n_fixtures", 0)
    niveau, uitleg = _model_reliability(n_fix)
    st.markdown("**Verwachte tegenstander-opstellingen (deze rotatie)**")
    if n_fix == 0:
        st.info(
            "Nog geen eerdere ontmoetingen van deze tegenstander gekend - elke opstelling is even "
            "waarschijnlijk, dus het model kan (nog) niets voorspellen. Kies de tegenstander hieronder zelf."
        )
        return
    scenarios = analysis["scenarios"]
    if not scenarios:
        st.caption("Geen geldige tegenstander-opstelling gevonden voor deze rotatie.")
        return
    tekst = (
        f"Betrouwbaarheid: **{niveau}** ({uitleg}). Het model kijkt naar wie vaak meespeelt, wie vaak "
        f"samen speelt en wie meestal Match 1 of 2 speelt. {analysis['n_total']} mogelijke opstellingen "
        f"voor deze rotatie gescoord - hieronder de waarschijnlijkste, samen {analysis['coverage'] * 100:.0f}% van de kans."
    )
    (st.warning if niveau == "laag" else st.markdown)(tekst)
    is_final = analysis.get("is_final")
    plan_by_s = (plan or {}).get("per_scenario") or {}

    def _knop(scen, key, label):
        if st.button(label, key=key, use_container_width=True):
            if fill_fn(scen):
                st.rerun(scope="fragment")
            else:
                st.warning("Een speler van dit scenario zit niet in de huidige tegenstander-selectie.")

    def _tegen(scen, m_idx):
        return " / ".join(names.get(u, u) for u in sorted(scen["pairs"][m_idx]))

    def _antwoord(scen):
        key = tuple(frozenset(p) for p in scen["pairs"])
        pl = plan_by_s.get(key)
        if pl:
            st.markdown("Ons beste plan: **R1** " + _pairs_txt(pl["r1"], name_lookup_global))
            st.caption(_r2_plan_txt(pl["r2"], name_lookup_global))
            st.markdown(_impact_markdown(pl["enc"]))
            return
        best = scen.get("best")
        if best:
            st.markdown("Ons beste antwoord: " + _answer_txt(best, name_lookup_global))
            st.markdown(_rotation_outcome_markdown(best["rot"]))
            if is_final and best.get("enc"):
                st.markdown(_impact_markdown(best["enc"]))

    kaarten = scenarios[:_SCENARIO_CARDS_N]
    cols = st.columns(len(kaarten))
    for idx, (col, scen) in enumerate(zip(cols, kaarten)):
        with col:
            with st.container(border=True):
                gesp = f" · :blue[gespeeld op {', '.join(scen['played_on'])}]" if scen.get("played_on") else ""
                st.markdown(f"**Scenario {chr(65 + idx)}** - {scen['prob'] * 100:.0f}% kans{gesp}")
                st.write(f"Tegen M1: {_tegen(scen, 0)}")
                st.write(f"Tegen M2: {_tegen(scen, 1)}")
                if scen["reasons"]:
                    st.caption(" · ".join(scen["reasons"]))
                _antwoord(scen)
                _knop(scen, f"opp_scen_{ploeg_id}_{next_rotation_num}_{idx}", "Gebruik dit scenario")
    rest = scenarios[_SCENARIO_CARDS_N:]
    if rest:
        kans_rest = sum(sc["prob"] for sc in rest) * 100
        with st.expander(f"Andere waarschijnlijke opstellingen ({len(rest)}, samen {kans_rest:.0f}% kans)", expanded=False):
            for idx, scen in enumerate(rest, start=_SCENARIO_CARDS_N):
                c_kans, c_tegen, c_ons, c_knop = st.columns([1, 4, 6, 1.4])
                with c_kans:
                    st.markdown(f"**{scen['prob'] * 100:.0f}%**")
                with c_tegen:
                    gesp = f"  \n:blue[gespeeld op {', '.join(scen['played_on'])}]" if scen.get("played_on") else ""
                    st.markdown(f"M1 {_tegen(scen, 0)}  \nM2 {_tegen(scen, 1)}{gesp}")
                with c_ons:
                    _antwoord(scen)
                with c_knop:
                    _knop(scen, f"opp_scen_{ploeg_id}_{next_rotation_num}_{idx}", "Gebruik")
    robust = analysis.get("robust")
    if robust and not plan:
        st.success(
            f"**Robuust voorstel** (gewogen over deze {len(scenarios)} scenario's, samen "
            f"{analysis['coverage'] * 100:.0f}% kans): **{_pairs_txt(robust['pairs'], name_lookup_global)}** "
            f"- gemiddeld {robust['ebw']:.2f} gewonnen matchen in deze rotatie."
        )
        st.markdown(_rotation_outcome_markdown(robust["rot"], prefix="Robuust voorstel, deze rotatie"))
        if is_final and robust.get("enc"):
            st.markdown(_impact_markdown(robust["enc"]))
    st.divider()


# -----------------------------------------------
# PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03 - zie moduledocstring.
# -----------------------------------------------
_PLAN_R2_OPP_TOP = 8      # voorspelde tegenstander-opstellingen voor rotatie 2, per rotatie-1-scenario
_SACRIFICE_WP = 0.35      # gemiddelde winkans onder deze grens = "opofferen"
_PLAN_STRATEGIES = [
    ("pts", "Meeste verwachte punten"),
    ("win", "Grootste kans op winst"),
    ("safe", "Minstens 1 punt"),
]


def _wins_dist(a, b) -> list:
    a = 0.5 if a is None else a
    b = 0.5 if b is None else b
    return [(1 - a) * (1 - b), a * (1 - b) + b * (1 - a), a * b]


def _final_outcome(k: int, jdist: list, half: float) -> list:
    p2 = p1 = p0 = 0.0
    for j, pj in enumerate(jdist):
        t = k + j
        if t > half:
            p2 += pj
        elif t == half:
            p1 += pj
        else:
            p0 += pj
    return [p2, p1, p0]


def _plan_score(strategy: str, out: list) -> tuple:
    p2, p1, _ = out
    if strategy == "win":
        return (p2, p1)
    if strategy == "safe":
        return (p2 + p1, p2)
    return (2 * p2 + p1, p2)


def _r2_plan_txt(r2_by_k: dict, name_lookup_global: dict) -> str:
    stand = {2: "2-0", 1: "1-1", 0: "0-2"}
    delen = []
    for k in (2, 1, 0):
        pairs = r2_by_k.get(k)
        if pairs:
            delen.append(f"na {stand[k]}: " + " · ".join(
                "/".join(name_lookup_global.get(u, u) for u in sorted(p))
                for p in pairs
            ))
    return "Rotatie 2 - " + " | ".join(delen) if delen else ""


def _two_rotation_plan(
    available_ids, synergy_fn, official_ranks_strict, player_ratings, opponent_ratings,
    tournament_rules_dict, excluded_pairs, player_budget, analysis, unique_opp_players,
    opp_excluded_pairs, s1_list, total_boards,
) -> dict:
    """PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03 - zie moduledocstring. `s1_list` = [(pairs, kans)]
    voor de tegenstander in rotatie 1 (kansen worden hernormaliseerd)."""
    stats = analysis["stats"]
    opp_ranks = analysis.get("opp_ranks") or {}
    opp_ps = analysis.get("opp_ps") or {}
    half = int(total_boards) / 2.0
    tot = sum(p for _, p in s1_list) or 1.0
    s1_list = [(pairs, p / tot) for pairs, p in s1_list]

    def _order(pairs):
        return _rank_pairs_with_padelstat_tiebreak(pairs, opp_ranks, opp_ps)

    wp_cache = {}

    def wp(own_pair, opp_pair):
        key = (frozenset(own_pair), frozenset(opp_pair))
        if key not in wp_cache:
            ours = [ll.effective_simulation_rating(u, player_ratings or {}, official_ranks_strict) for u in own_pair]
            theirs = []
            for u in opp_pair:
                r = opp_ranks.get(u)
                theirs.append(ll.effective_simulation_rating(u, opponent_ratings or {}, {u: float(r) if r is not None else None}))
            ours = [v for v in ours if v is not None]
            theirs = [v for v in theirs if v is not None]
            wp_cache[key] = ll.estimate_win_probability(
                sum(ours) / len(ours) if ours else None, sum(theirs) / len(theirs) if theirs else None,
            )
        return wp_cache[key]

    own1, _, _ = _generate_rotation_candidates(
        available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
        opponent_boards=None, player_ratings=player_ratings, opponent_ratings=opponent_ratings,
        max_results=100_000, tournament_rules_dict=tournament_rules_dict,
        rotation_number=1, player_budget=player_budget,
    )
    own1 = [c["ordered_pairs"] for c in own1]

    r2_opp = []
    for pairs, _ in s1_list:
        pred = olm.predict_rotation_scenarios(
            stats, unique_opp_players, _order, opp_ranks, rules=tournament_rules_dict,
            excluded_pairs=set(opp_excluded_pairs or set()) | {frozenset(p) for p in pairs},
            top_n=_PLAN_R2_OPP_TOP,
        )["scenarios"]
        t2 = sum(x["prob"] for x in pred) or 1.0
        r2_opp.append([(x["pairs"], x["prob"] / t2) for x in pred])

    own2_cache = {}

    def own2(o1):
        key = tuple(frozenset(p) for p in o1)
        if key not in own2_cache:
            budget2 = None
            if player_budget is not None:
                budget2 = dict(player_budget)
                for p in o1:
                    for u in p:
                        budget2[str(u)] = budget2.get(str(u), 0) - 1
            opts, _, _ = _generate_rotation_candidates(
                available_ids, synergy_fn, official_ranks_strict,
                set(excluded_pairs or set()) | {frozenset(p) for p in o1},
                opponent_boards=None, player_ratings=player_ratings, opponent_ratings=opponent_ratings,
                max_results=100_000, tournament_rules_dict=tournament_rules_dict,
                rotation_number=2, player_budget=budget2,
            )
            own2_cache[key] = [c["ordered_pairs"] for c in opts]
        return own2_cache[key]

    results = []   # per o1: {"o1", "per_s": [...], "agg": {strat: [p2,p1,p0]}, "wp1": [m1, m2]}
    for o1 in own1:
        r2opts = own2(o1)
        if not r2opts:
            continue
        per_s, agg = [], {k: [0.0, 0.0, 0.0] for k, _ in _PLAN_STRATEGIES}
        wp1 = [0.0, 0.0]
        for si, (s1, ps1) in enumerate(s1_list):
            a, b = wp(o1[0], s1[0]), wp(o1[1], s1[1])
            wp1[0] += ps1 * (0.5 if a is None else a)
            wp1[1] += ps1 * (0.5 if b is None else b)
            dk = _wins_dist(a, b)
            jd = []
            for o2 in r2opts:
                mix = [0.0, 0.0, 0.0]
                for s2, ps2 in r2_opp[si]:
                    d = _wins_dist(wp(o2[0], s2[0]), wp(o2[1], s2[1]))
                    for j in range(3):
                        mix[j] += ps2 * d[j]
                jd.append(mix)
            res_s = {}
            for strat, _ in _PLAN_STRATEGIES:
                enc = [0.0, 0.0, 0.0]
                r2 = {}
                for k in range(3):
                    best = None
                    for idx, mix in enumerate(jd):
                        out = _final_outcome(k, mix, half)
                        sc = _plan_score(strat, out)
                        if best is None or sc > best[0]:
                            best = (sc, idx, out)
                    for i in range(3):
                        enc[i] += dk[k] * best[2][i]
                    r2[k] = r2opts[best[1]]
                res_s[strat] = {"enc": enc, "r2": r2}
                for i in range(3):
                    agg[strat][i] += ps1 * enc[i]
            per_s.append(res_s)
        results.append({"o1": o1, "per_s": per_s, "agg": agg, "wp1": wp1})
    if not results:
        return {}

    def _as_pp(v):
        return {"p2": v[0], "p1": v[1], "p0": v[2]}

    cards = []
    for strat, label in _PLAN_STRATEGIES:
        best = max(results, key=lambda r: _plan_score(strat, r["agg"][strat]))
        top_s = max(range(len(s1_list)), key=lambda i: s1_list[i][1])
        cards.append({
            "strategy": strat, "label": label, "r1": best["o1"], "enc": _as_pp(best["agg"][strat]),
            "r2": best["per_s"][top_s][strat]["r2"], "wp1": best["wp1"],
            "tag": "opofferen" if min(best["wp1"]) < _SACRIFICE_WP else "gespreid",
        })
    per_scenario = {}
    for si, (s1, _) in enumerate(s1_list):
        best = max(results, key=lambda r: _plan_score("pts", r["per_s"][si]["pts"]["enc"]))
        per_scenario[tuple(frozenset(p) for p in s1)] = {
            "r1": best["o1"], "r2": best["per_s"][si]["pts"]["r2"],
            "enc": _as_pp(best["per_s"][si]["pts"]["enc"]),
        }
    return {"cards": cards, "per_scenario": per_scenario, "n_r1": len(results), "n_s1": len(s1_list)}


def _render_plan_cards(plan: dict, name_lookup_global: dict, key_prefix: str, against_chosen: bool):
    """PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03: 3 plankaarten. Geeft de gekozen rotatie-1-
    opstelling terug (of None)."""
    cards = plan.get("cards") or []
    if not cards:
        return None
    # dezelfde opstelling onder meerdere strategieen = 1 kaart
    merged = []
    for c in cards:
        sleutel = tuple(frozenset(p) for p in c["r1"])
        for m in merged:
            if m["key"] == sleutel:
                m["labels"].append(c["label"])
                break
        else:
            merged.append({**c, "key": sleutel, "labels": [c["label"]]})
    tegen = "tegen de gekozen tegenstander-opstelling" if against_chosen else (
        f"gewogen over {plan.get('n_s1', 0)} waarschijnlijke tegenstander-opstellingen")
    st.markdown("**Plan voor de volledige ontmoeting (rotatie 1 + 2)**")
    st.caption(
        f"Elke kaart is een volledig plan, {tegen}. Rotatie 2 is adaptief: die kies je pas na rotatie 1, "
        "als je de stand kent - per stand staat de beste rotatie 2 (tegen hun waarschijnlijkste rotatie-1-"
        "opstelling). Koppels die al speelden, het speelbudget en de puntengrens worden gerespecteerd. "
        f"{plan.get('n_r1', 0)} eigen rotatie-1-opstellingen doorgerekend."
    )
    gekozen = None
    cols = st.columns(len(merged))
    for i, (col, c) in enumerate(zip(cols, merged)):
        with col:
            with st.container(border=True):
                st.markdown(f"**{' + '.join(c['labels'])}**")
                tag_kleur = "red" if c["tag"] == "opofferen" else "blue"
                st.markdown(f"Rotatie 1 · :{tag_kleur}[{c['tag']}]")
                for m_idx, (pair, w) in enumerate(zip(c["r1"], c["wp1"]), start=1):
                    st.write(f"M{m_idx}: **{' / '.join(name_lookup_global.get(u, u) for u in sorted(pair))}** ({w * 100:.0f}%)")
                st.markdown(_impact_markdown(c["enc"]))
                st.caption(_r2_plan_txt(c["r2"], name_lookup_global))
                if st.button("Kies rotatie 1 van dit plan", key=f"{key_prefix}_{i}", type="primary", use_container_width=True):
                    gekozen = c["r1"]
    return gekozen


@st.fragment
def _render_rotation_planner(
    available_ids, synergy_fn, official_ranks_strict, name_lookup_global, opp,
    opponent_boards=None, player_ratings=None, opponent_ratings=None,
    report_for_ai=None, tournament_rules_dict=None, rules_label=None,
    bundle=None, total_boards=None, max_per_player=None,
    profiles=None, sel_player_id=None,  # PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01: opnieuw ACTIEF gebruikt, voor de overgenomen sandbox-presets in "Zelf samenstellen"
):
    """PADEL_ANALYSIS_FRAGMENT_ISOLATION_2026-09-26: @st.fragment isoleert
    deze functie van een volledige pagina-rerun. Zie de oorspronkelijke
    docstring in page_lineup_lab.py voor de volledige toelichting bij elke
    eerdere fix - functioneel ONGEWIJZIGD."""
    st.markdown('<div class="section-header">Rotatieplanner</div>', unsafe_allow_html=True)
    regel_tekst = f" (volgens {rules_label})" if rules_label else ""
    st.caption(
        "Alle mogelijke koppelverdelingen voor de eerstvolgende rotatie, gerangschikt op VERWACHT "
        "AANTAL GEWONNEN MATCHEN (niet op een abstract scoregetal). Klik aan wie/welke combinatie "
        "effectief speelde om door te gaan naar de volgende rotatie. Het duo met de hoogste SOM van "
        f"de 2 OFFICIELE klassementen staat steeds op Match 1{regel_tekst} - de winkans-simulatie "
        "gebruikt daarnaast de padelstats.be playing strength waar bekend."
    )
    st.caption(_WIN_PROB_DISCLAIMER)
    _render_official_rank_warning(available_ids, official_ranks_strict, name_lookup_global)
    # PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29: per rotatie 2 koppels = 4 spelers nodig; een oneven
    # aantal geselecteerde spelers is geen probleem meer.
    if len(available_ids) < 2 * MATCHES_PER_ROTATION:
        st.info(f"Selecteer minstens {2 * MATCHES_PER_ROTATION} spelers om de rotatieplanner te gebruiken.")
        return
    ploeg_id = opp["ploeg_id"]
    locked_key = f"rot_locked_v3_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if locked_key not in st.session_state:
        st.session_state[locked_key] = []
    locked_rotations = st.session_state[locked_key]
    opp_locked_key = f"rot_locked_opp_v1_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if opp_locked_key not in st.session_state:
        st.session_state[opp_locked_key] = []
    locked_opponents = st.session_state[opp_locked_key]
    # PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30: winkansen van de reeds
    # BEVESTIGDE rotaties (2 per rotatie, [None, None] als toen geen
    # tegenstander gekozen was) - nodig om de "impact op de volledige
    # ontmoeting" van een NIEUWE kandidaat te kunnen berekenen. Nieuw t.o.v.
    # locked_rotations/locked_opponents; bestond nog niet.
    win_probs_locked_key = f"rot_locked_winprobs_v1_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if win_probs_locked_key not in st.session_state:
        st.session_state[win_probs_locked_key] = []
    locked_win_probs_per_rotation = st.session_state[win_probs_locked_key]
    for rot_idx, pairs in enumerate(locked_rotations, start=1):
        st.markdown(f"**Rotatie {rot_idx} (bevestigd):**")
        opp_voor_rotatie = (
            locked_opponents[rot_idx - 1] if rot_idx - 1 < len(locked_opponents) else None
        )
        for match_idx, pair in enumerate(pairs, start=1):
            p1, p2 = tuple(pair)
            ons = f"{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}"
            tegen = ""
            if opp_voor_rotatie and match_idx - 1 < len(opp_voor_rotatie):
                namen = [x.get("name", "?") for x in opp_voor_rotatie[match_idx - 1]]
                if namen:
                    tegen = f"  -  tegen **{' / '.join(namen)}**"
            st.write(f"Match {match_idx}: {ons}{tegen}")
        if st.button(f"Rotatie {rot_idx} wijzigen", key=f"rot_edit_v3_{ploeg_id}_{rot_idx}"):
            st.session_state[locked_key] = locked_rotations[: rot_idx - 1]
            st.session_state[opp_locked_key] = locked_opponents[: rot_idx - 1]
            # PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30: mee terugdraaien,
            # anders blijft er een verweesde, verouderde winkans-invoer staan.
            st.session_state[win_probs_locked_key] = locked_win_probs_per_rotation[: rot_idx - 1]
            st.rerun(scope="fragment")
        st.markdown("---")
    excluded_pairs = {p for rot in locked_rotations for p in rot}
    next_rotation_num = len(locked_rotations) + 1
    # PADEL_ANALYSIS_PLANNER_TWO_PAIRS_2026-09-29: resterend aantal matchen per speler = 'max. matchen
    # per speler' (instelling hierboven op de pagina) min wat al bevestigd is.
    player_budget = None
    if max_per_player:
        gebruikt = {}
        for rot in locked_rotations:
            for pair in rot:
                for pid in pair:
                    gebruikt[str(pid)] = gebruikt.get(str(pid), 0) + 1
        player_budget = {
            str(pid): int(max_per_player.get(pid, 0) or 0) - gebruikt.get(str(pid), 0)
            for pid in available_ids
        }
        opgebruikt = [
            name_lookup_global.get(pid, pid) for pid in available_ids
            if player_budget.get(str(pid), 0) <= 0
        ]
        if opgebruikt and locked_rotations:
            st.caption(
                "Niet meer beschikbaar in deze rotatie (max. aantal matchen bereikt): "
                + ", ".join(opgebruikt) + "."
            )
    borden_bevestigd = sum(len(rot) for rot in locked_rotations)
    if total_boards is not None and borden_bevestigd >= int(total_boards):
        st.success(
            f"Alle {int(total_boards)} wedstrijden van deze ontmoeting zijn ingedeeld "
            f"over {len(locked_rotations)} rotatie(s)."
        )
        # PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01: eindpaneel - zie
        # moduledocstring. Voorheen stopte de functie hier zonder enige
        # samenvatting te tonen.
        st.divider()
        _render_encounter_summary(
            locked_rotations, locked_opponents, locked_win_probs_per_rotation, name_lookup_global,
        )
        return
    unique_opp_players = (bundle or {}).get("unique_players") or []
    # PADEL_ANALYSIS_PLANNER_FOLLOWS_OPP_SELECTION_2026-10-02: volg de
    # selectie "Beschikbare tegenstander-spelers" uit de matchup-tabel, zodat
    # de planner (scenario's, dropdowns) meteen herrekent als je die wijzigt.
    gekozen_opp_namen = st.session_state.get(f"theoretical_opp_players_{ploeg_id}")
    if gekozen_opp_namen:
        gefilterd = [p for p in unique_opp_players if p.get("name", "?") in set(gekozen_opp_namen)]
        if len(gefilterd) >= 4:
            unique_opp_players = gefilterd
    rotation_opponent_boards = None
    analysis = {}  # PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03
    plan_mode = (
        olm is not None and total_boards is not None and int(total_boards) == 2 * MATCHES_PER_ROTATION
        and next_rotation_num == 1
    )
    if unique_opp_players:
        with st.expander(
            f"Wie stelt de tegenstander op in rotatie {next_rotation_num}?",
            expanded=True,
        ):
            st.caption(
                "Vul hier in wie de tegenstander in DEZE rotatie opstelt (of al opstelde). "
                "De winkansen van de combinaties hieronder worden daar meteen op herrekend. "
                "Laat je dit leeg, dan wordt enkel op eigen synergie gerangschikt (geen "
                "matchup-inschatting tegen een specifieke tegenstander)."
            )
            def _opp_pick_label(speler: dict) -> str:
                naam = speler.get("name", "?")
                uid = str(speler.get("user_id") or "")
                officieel = _cached_official_rank(uid) if uid else None
                padelstat = _cached_own_player_rating(uid) if uid else None
                delen = [f"P{int(officieel)}" if officieel is not None else "P?"]
                if padelstat is not None:
                    delen.append(f"ps {int(padelstat)}")
                return f"{naam} ({' \u00b7 '.join(delen)})"
            paar_frequentie = {}
            for fx_b in (bundle or {}).get("previous_fixtures", []) or []:
                for b in fx_b.get("boards", []) or []:
                    p = b.get("opponent_pair") or []
                    if len(p) == 2:
                        k = frozenset(str(x.get("user_id")) for x in p if x.get("user_id"))
                        if len(k) == 2:
                            paar_frequentie[k] = paar_frequentie.get(k, 0) + 1
            def _pair_label(p1: dict, p2: dict) -> str:
                uid1, uid2 = str(p1.get("user_id")), str(p2.get("user_id"))
                n = paar_frequentie.get(frozenset({uid1, uid2}), 0)
                badge = f"({n}x) " if n else ""
                return f"{badge}{_opp_pick_label(p1)} / {_opp_pick_label(p2)}"
            alle_paren = list(itertools.combinations(unique_opp_players, 2))
            alle_paren.sort(
                key=lambda pr: paar_frequentie.get(
                    frozenset({str(pr[0].get("user_id")), str(pr[1].get("user_id"))}), 0,
                ),
                reverse=True,
            )
            geen_keuze = "- Kies een koppel -"
            paar_labels = [geen_keuze] + [_pair_label(p1, p2) for p1, p2 in alle_paren]
            paar_map = {_pair_label(p1, p2): (p1, p2) for p1, p2 in alle_paren}
            # PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03: 4 speler-dropdowns i.p.v. 2 koppel-dropdowns.
            opp_pick_prefix = f"rot_opp_pl_v1_{ploeg_id}_{next_rotation_num}"
            opp_excluded_pairs_ui = set()
            for rot_opp in locked_opponents:
                for paar in rot_opp or []:
                    _u = frozenset(str(x.get("user_id")) for x in paar if x.get("user_id"))
                    if len(_u) == 2:
                        opp_excluded_pairs_ui.add(_u)
            _sel_uids = {str(p.get("user_id")) for p in unique_opp_players if p.get("user_id")}

            def _fill_opp_from_scenario(scen) -> bool:
                uids = [sorted(p) for p in scen["pairs"]]
                if any(u not in _sel_uids for pair in uids for u in pair):
                    return False
                obj = {str(p.get("user_id")): p for p in unique_opp_players if p.get("user_id")}
                for m in (0, 1):
                    for i in (0, 1):
                        st.session_state[f"{opp_pick_prefix}_{m}{i}"] = _opp_pick_label(obj[uids[m][i]])
                return True
            key_i0 = f"rot_opp_pick_pair_{ploeg_id}_{next_rotation_num}_0"
            key_i1 = f"rot_opp_pick_pair_{ploeg_id}_{next_rotation_num}_1"
            # PADEL_ANALYSIS_ROTATION_PRESET_ORDER_BUG_2026-10-02: ID-gebaseerde
            # lookup i.p.v. een string-vergelijking op (orde-gevoelige) labels -
            # zie moduledocstring en _opponent_rotation_presets(). Deze dict
            # geeft, voor elk koppel spelers dat in de dropdown bestaat, de
            # EXACTE, canonieke labeltekst terug - ongeacht in welke volgorde
            # een historische wedstrijd die 2 spelers vermeldde.
            paar_label_by_uids = {
                frozenset({str(p1.get("user_id")), str(p2.get("user_id"))}): _pair_label(p1, p2)
                for p1, p2 in alle_paren
            }
            paar_label_by_names = {
                frozenset({_norm_name(p1.get("name")), _norm_name(p2.get("name"))}): _pair_label(p1, p2)
                for p1, p2 in alle_paren
            }
            # PADEL_ANALYSIS_ROTATION_SCENARIO_CARDS_2026-10-02: scenario-
            # kaarten (statistisch model) bovenaan - zie moduledocstring.
            if olm is not None:
                opp_excluded_pairs = set()
                for rot_opp in locked_opponents:
                    for paar in rot_opp or []:
                        uids = frozenset(str(x.get("user_id")) for x in paar if x.get("user_id"))
                        if len(uids) == 2:
                            opp_excluded_pairs.add(uids)
                locked_flat = [wp for rot in locked_win_probs_per_rotation for wp in rot]
                scen_sig = (
                    tuple(sorted(available_ids)), next_rotation_num,
                    tuple(sorted(tuple(sorted(p)) for p in excluded_pairs)),
                    tuple(sorted(tuple(sorted(p)) for p in opp_excluded_pairs)),
                    tuple(sorted(player_budget.items())) if player_budget else None,
                    tuple(sorted(official_ranks_strict.items())),
                    tuple(sorted((player_ratings or {}).items())),
                    tuple(sorted((opponent_ratings or {}).items())),
                    tuple(str(p.get("user_id")) for p in unique_opp_players),
                    len((bundle or {}).get("previous_fixtures") or []),
                    tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
                    tuple(locked_flat),
                )
                scen_key = f"rot_scen_v2_{ploeg_id}_{next_rotation_num}"
                scen_sig_key = f"rot_scen_sig_v2_{ploeg_id}_{next_rotation_num}"
                if st.session_state.get(scen_sig_key) != scen_sig:
                    try:
                        own_all, _, _ = _generate_rotation_candidates(
                            available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
                            opponent_boards=None, player_ratings=player_ratings,
                            opponent_ratings=opponent_ratings, max_results=100_000,
                            tournament_rules_dict=tournament_rules_dict,
                            rotation_number=next_rotation_num, player_budget=player_budget,
                        )
                        own_options = [c["ordered_pairs"] for c in own_all]
                        st.session_state[scen_key] = _compute_opponent_scenario_analysis(
                            bundle, unique_opp_players, own_options, synergy_fn, player_ratings,
                            official_ranks_strict, opponent_ratings, tournament_rules_dict,
                            opp_excluded_pairs, locked_flat, total_boards,
                            next_rotation_num=next_rotation_num,
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.session_state[scen_key] = {"error": f"{type(exc).__name__}: {exc}"}
                    st.session_state[scen_sig_key] = scen_sig
                analysis = st.session_state.get(scen_key) or {}
                if analysis.get("error"):
                    st.caption(f"Scenario-voorspelling mislukt: {analysis['error']}")
                elif analysis:
                    # PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03: plan per scenario (2-rotatie-modus).
                    scen_plan = None
                    if plan_mode and analysis.get("scenarios"):
                        plan_sig = (scen_sig, "all")
                        pk = f"rot_plan_all_v1_{ploeg_id}"
                        if st.session_state.get(pk + "_sig") != plan_sig:
                            try:
                                st.session_state[pk] = _two_rotation_plan(
                                    available_ids, synergy_fn, official_ranks_strict, player_ratings,
                                    opponent_ratings, tournament_rules_dict, excluded_pairs, player_budget,
                                    analysis, unique_opp_players, opp_excluded_pairs,
                                    [(sc["pairs"], sc["prob"]) for sc in analysis["scenarios"]], total_boards,
                                )
                            except Exception as exc:  # noqa: BLE001
                                st.session_state[pk] = {"error": f"{type(exc).__name__}: {exc}"}
                            st.session_state[pk + "_sig"] = plan_sig
                        scen_plan = st.session_state.get(pk) or None
                        if scen_plan and scen_plan.get("error"):
                            st.caption(f"Plan-berekening mislukt: {scen_plan['error']}")
                            scen_plan = None
                    _render_opponent_scenario_cards(
                        analysis, name_lookup_global, _fill_opp_from_scenario,
                        next_rotation_num, ploeg_id, plan=scen_plan,
                    )
            # PADEL_ANALYSIS_SCENARIO_LIST_2026-10-03: de aparte "Zoals op ..."-
            # snelkeuzes zijn opgegaan in de scenario-lijst hierboven (effectief
            # gespeelde opstellingen staan daar gemarkeerd). Zonder model
            # (olm niet beschikbaar) blijven de oude snelkeuzes de terugval.
            # PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03: de oude "Zoals op ..."-terugval (zonder model)
            # werkte op de verdwenen koppel-dropdowns en is uitgeschakeld.
            # PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03: tegenstander PER SPELER kiezen - zie
            # moduledocstring. Vervangt de 2 koppel-dropdowns.
            uids_in_selectie = [str(p.get("user_id")) for p in unique_opp_players if p.get("user_id")]
            speler_obj = {str(p.get("user_id")): p for p in unique_opp_players if p.get("user_id")}
            label_van = {u: _opp_pick_label(speler_obj[u]) for u in uids_in_selectie}
            appear = ((analysis or {}).get("stats") or {}).get("appear") or {}
            volgorde = sorted(uids_in_selectie, key=lambda u: (-appear.get(u, 0), label_van[u]))
            uid_van = {v: k for k, v in label_van.items()}
            geen_speler = "- Kies speler -"
            sleutels = {(m, i): f"{opp_pick_prefix}_{m}{i}" for m in (0, 1) for i in (0, 1)}
            gekozen_uid = {}
            for (m, i), key in sleutels.items():
                v = st.session_state.get(key)
                if v in uid_van:
                    gekozen_uid[(m, i)] = uid_van[v]
            kolommen = st.columns(4)
            for slot_idx, ((m, i), key) in enumerate(sleutels.items()):
                elders = {u for s_, u in gekozen_uid.items() if s_ != (m, i)}
                partner = gekozen_uid.get((m, 1 - i))
                opties = [geen_speler] + [
                    label_van[u] for u in volgorde
                    if u not in elders and not (partner and frozenset({u, partner}) in opp_excluded_pairs_ui)
                ]
                if st.session_state.get(key) not in opties:
                    st.session_state[key] = geen_speler
                with kolommen[slot_idx]:
                    keuze = st.selectbox(f"Tegen M{m + 1} - speler {i + 1}", opties, key=key)
                if keuze != geen_speler:
                    gekozen_uid[(m, i)] = uid_van[keuze]
                else:
                    gekozen_uid.pop((m, i), None)
            if len(gekozen_uid) == 4:
                gekozen_paren = [
                    (speler_obj[gekozen_uid[(m, 0)]], speler_obj[gekozen_uid[(m, 1)]]) for m in (0, 1)
                ]
                rotation_opponent_boards = [
                    {"opponent_pair": list(gekozen_paren[0])},
                    {"opponent_pair": list(gekozen_paren[1])},
                ]
                st.caption("Winkansen en plannen hieronder zijn berekend tegen deze tegenstander-opstelling.")
            elif gekozen_uid:
                st.caption("Kies alle 4 tegenstander-spelers om de winkansen te herberekenen.")
    effective_opponent_boards = rotation_opponent_boards or opponent_boards
    # PADEL_ANALYSIS_ROTATION_CARDS_REQUIRE_OPPONENT_2026-10-02: bepaalt of
    # er voor DEZE rotatie al een tegenstander-opstelling gekend is - zie
    # moduledocstring. Gebruikt verderop om de 3 kaarten te verbergen
    # zolang dit None is (anders zijn alle kaarten toch neutraal 50/50).
    rot_boards_this_rotation = _rotation_boards_for(effective_opponent_boards, next_rotation_num)
    rot_cache_key = f"rot_candidates_v2_{ploeg_id}_{next_rotation_num}"
    rot_sig_key = f"rot_candidates_sig_v2_{ploeg_id}_{next_rotation_num}"
    rot_signature = (
        tuple(sorted(available_ids)),
        tuple(sorted(tuple(sorted(p)) for p in excluded_pairs)) if excluded_pairs else (),
        tuple(sorted(official_ranks_strict.items())),
        tuple(sorted(player_ratings.items())) if player_ratings else (),
        tuple(sorted(opponent_ratings.items())) if opponent_ratings else (),
        tuple(
            tuple(sorted(str(p.get("user_id")) for p in b.get("opponent_pair", [])))
            for b in (effective_opponent_boards or [])
        ),
        tuple(sorted(tournament_rules_dict.items())) if tournament_rules_dict else None,
        tuple(sorted(player_budget.items())) if player_budget else None,
    )
    if st.session_state.get(rot_sig_key) != rot_signature:
        st.session_state[rot_cache_key] = _generate_rotation_candidates(
            available_ids, synergy_fn, official_ranks_strict, excluded_pairs,
            opponent_boards=effective_opponent_boards, player_ratings=player_ratings,
            opponent_ratings=opponent_ratings, max_results=15,
            tournament_rules_dict=tournament_rules_dict,
            rotation_number=next_rotation_num, player_budget=player_budget,
        )
        st.session_state[rot_sig_key] = rot_signature
    candidates, total_possible, rotation_diagnostics = st.session_state[rot_cache_key]
    if not candidates:
        if total_possible == 0:
            st.info("Geen geldige koppelverdeling meer mogelijk.")
        elif tournament_rules_dict is not None:
            st.warning(
                f"Geen enkele van de {total_possible} mogelijke koppelverdelingen valt binnen de "
                "toegelaten puntengrens per rotatie voor de gekozen afdeling - of alle zijn al "
                "gebruikt. Overweeg een andere afdeling of spelersselectie."
            )
            diag_msg = _format_points_bounds_diagnostic(tournament_rules_dict, rotation_diagnostics)
            if diag_msg:
                st.caption(diag_msg)
        else:
            st.warning(f"Alle {total_possible} mogelijke koppelverdelingen zijn al gebruikt in eerdere rotaties.")
        return
    st.markdown(f"**Rotatie {next_rotation_num} - kies de effectieve/geplande combinatie:**")
    if tournament_rules_dict is not None:
        st.caption(f"{len(candidates)} geldige combinaties binnen de puntengrens (incl. beide volgordes bij gelijk klassement).")
    def _bevestig_rotatie(gekozen_pairs, opp_pairs_voor_log, win_probs_deze_rotatie) -> None:
        """PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30: gedeelde bevestig-
        logica - zowel de kaart-knoppen als de "geavanceerd"-fallback
        hieronder roepen dit aan, zodat er precies EEN plek is die de 3
        locked_*-lijsten synchroon houdt."""
        st.session_state[locked_key] = locked_rotations + [gekozen_pairs]
        st.session_state[opp_locked_key] = locked_opponents + [opp_pairs_voor_log]
        st.session_state[win_probs_locked_key] = locked_win_probs_per_rotation + [win_probs_deze_rotatie]
        st.rerun(scope="fragment")
    opp_pairs_voor_log = []
    if rotation_opponent_boards:
        opp_pairs_voor_log = [b.get("opponent_pair") or [] for b in rotation_opponent_boards]
    # PADEL_ANALYSIS_PRESET_CONFIRM_ARITY_FIX_2026-09-30: _bevestig_rotatie()
    # verwacht 3 argumenten. De custom-modus roept on_confirm(ordered_pairs,
    # win_probs) aan met slechts 2 - deze wrapper vult opp_pairs_voor_log
    # automatisch aan. De tegenstander-presets hierboven gebruiken deze
    # wrapper NIET MEER (PADEL_ANALYSIS_ROTATION_OPPONENT_PRESETS_2026-09-30):
    # zij vullen enkel de bestaande dropdown-selecties in en herladen.
    def _on_confirm_2arg(ordered_pairs, win_probs) -> None:
        _bevestig_rotatie(ordered_pairs, opp_pairs_voor_log, win_probs)
    # PADEL_ANALYSIS_ROTATION_OPPONENT_PRESETS_2026-09-30: de oude, foute
    # "Snelkeuzes"-expander (eigen-opstelling-presets) is VERWIJDERD - zie
    # moduledocstring. De tegenstander-snelkeuzes staan nu hierboven, IN de
    # "Wie stelt de tegenstander op..."-expander. Enkel "Zelf samenstellen"
    # (eigen koppelkeuze, klik-voor-klik) blijft hier staan.
    with st.expander("Zelf samenstellen (klik-voor-klik)", expanded=False):
        # PADEL_ANALYSIS_ROTATION_BUILD1_2026-10-01: profiles/sel_player_id/
        # player_ratings/official_ranks_strict actief doorgegeven voor de
        # overgenomen sandbox-presets - zie moduledocstring.
        _render_custom_click_builder(
            candidates, name_lookup_global, ploeg_id, next_rotation_num, _on_confirm_2arg,
            profiles=profiles, sel_player_id=sel_player_id,
            player_ratings=player_ratings, official_ranks_strict=official_ranks_strict,
        )
    # PADEL_ANALYSIS_ROTATION_CARDS_REQUIRE_OPPONENT_2026-10-02 (op verzoek
    # van Kim: "bij kaarten niet logisch om al iets te tonen als er nog
    # geen tegenstander is") - zie moduledocstring. Zonder een gekende
    # tegenstander-opstelling voor DEZE rotatie is elke kandidaat even
    # "onbekend" - de 3 kaarten zouden dan toch enkel een identieke,
    # betekenisloze 50/50-verdeling tonen (het is_neutral-label deed dat
    # eerder al zichtbaar, maar Kim geeft aan dat de kaarten dan beter
    # gewoon niet getoond worden i.p.v. getoond-maar-neutraal).
    # PADEL_ANALYSIS_TWO_ROTATION_PLAN_2026-10-03: in rotatie 1 van het najaarsformaat vervangen
    # de 3 plankaarten (volledige ontmoeting) de kaarten per rotatie.
    if plan_mode and analysis and not analysis.get("error") and analysis.get("scenarios"):
        if rot_boards_this_rotation:
            s1_list = [([frozenset(str(p.get("user_id")) for p in b.get("opponent_pair") or []) for b in rot_boards_this_rotation], 1.0)]
            plan_tag = tuple(tuple(sorted(p)) for p in s1_list[0][0])
        else:
            s1_list = [(sc["pairs"], sc["prob"]) for sc in analysis["scenarios"]]
            plan_tag = "all"
        pk = f"rot_plan_cards_v1_{ploeg_id}"
        sig = (rot_signature, plan_tag, len(analysis["scenarios"]))
        if st.session_state.get(pk + "_sig") != sig:
            try:
                st.session_state[pk] = _two_rotation_plan(
                    available_ids, synergy_fn, official_ranks_strict, player_ratings, opponent_ratings,
                    tournament_rules_dict, excluded_pairs, player_budget, analysis, unique_opp_players,
                    set(), s1_list, total_boards,
                )
            except Exception as exc:  # noqa: BLE001
                st.session_state[pk] = {"error": f"{type(exc).__name__}: {exc}"}
            st.session_state[pk + "_sig"] = sig
        plan = st.session_state.get(pk) or {}
        if plan.get("error"):
            st.warning(f"Plan-berekening mislukt: {plan['error']}")
        elif plan:
            r1 = _render_plan_cards(plan, name_lookup_global, f"rot_plan_pick_{ploeg_id}", bool(rot_boards_this_rotation))
            if r1 is not None:
                wps = [None, None]
                if rot_boards_this_rotation:
                    comp = _compute_matchup(
                        r1, rot_boards_this_rotation, synergy_fn, player_ratings or {},
                        official_ranks_strict, opponent_ratings or {},
                    )
                    wps = [x.get("win_probability") for x in comp["assignment"]]
                _bevestig_rotatie(r1, opp_pairs_voor_log, wps)
    elif not rot_boards_this_rotation:
        st.info(
            "Kies hierboven eerst de tegenstander-opstelling voor deze rotatie (via een snelkeuze of "
            "de 2 dropdowns) om de 3 aanbevolen kaarten te zien - zonder gekende tegenstander is elke "
            "combinatie nog even 'onbekend', dus zouden de kaarten toch enkel een neutrale 50/50-"
            "verdeling tonen. 'Zelf samenstellen' en 'Alle combinaties (geavanceerd)' hieronder blijven "
            "wel gewoon bruikbaar, gerangschikt op synergie."
        )
    else:
        # PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30: winkansen van de reeds
        # bevestigde rotaties, plat (2 per rotatie) - basis voor de "impact op
        # de volledige ontmoeting"-berekening per kandidaat hieronder.
        flat_locked_win_probs = [wp for rotatie in locked_win_probs_per_rotation for wp in rotatie]
        is_final_rot = total_boards is None or (
            borden_bevestigd + MATCHES_PER_ROTATION >= int(total_boards)
        )
        cards = _rank_and_label_candidates_for_cards(
            candidates, flat_locked_win_probs, total_boards=total_boards, max_cards=3,
            final_rotation=is_final_rot,
        )
        if is_final_rot:
            st.caption(
                f"De 3 kaarten zijn een selectie uit {len(candidates)} combinaties: 'Aanbevolen' = hoogste kans "
                "op ploegwinst voor de VOLLEDIGE ontmoeting (exact, de vorige rotaties liggen vast), 'Veiligst' "
                "= minste kans op een zware nederlaag in deze rotatie, 'Alternatief' = ander koppelprofiel."
            )
        else:
            st.caption(
                f"De 3 kaarten zijn een selectie uit {len(candidates)} combinaties: 'Aanbevolen' = meeste "
                "verwachte gewonnen matchen in DEZE rotatie, 'Veiligst' = minste kans op een zware nederlaag, "
                "'Alternatief' = ander koppelprofiel. De kans op ploegwinst wordt pas in de laatste rotatie "
                "getoond: die hangt af van wat je in de volgende rotatie(s) opstelt."
            )
        if not cards:
            st.info("Geen kaarten te tonen - te weinig onderscheiden combinaties.")
        else:
            card_cols = st.columns(len(cards))
            for col, card in zip(card_cols, cards):
                key_prefix = f"rot_card_v1_{ploeg_id}_{next_rotation_num}_{card['role']}"
                if _render_candidate_card(col, card, name_lookup_global, key_prefix):
                    _bevestig_rotatie(
                        card["candidate"]["ordered_pairs"], opp_pairs_voor_log, card["win_probs"],
                    )
    ai_key = f"rot_ai_v3_{ploeg_id}_{next_rotation_num}"
    if taa is not None and report_for_ai is not None:
        if st.button("AI-inzicht over deze combinaties", key=f"rot_ai_btn_v3_{ploeg_id}_{next_rotation_num}"):
            with st.spinner("AI analyseert de combinaties..."):
                try:
                    ai_options = _lineup_options_for_ai(candidates[:5], name_lookup_global)
                    st.session_state[ai_key] = taa.analyze_lineup_options(report_for_ai, ai_options, name_lookup_global)
                except Exception as exc:
                    st.session_state[ai_key] = f"Mislukt: {exc}"
        if st.session_state.get(ai_key):
            st.markdown(st.session_state[ai_key])
    # PADEL_ANALYSIS_ROTATION_CARDS_2026-09-30: de volledige, oude
    # radio+detail+bevestig-flow blijft ONGEWIJZIGD beschikbaar voor wie een
    # combinatie buiten de 3 kaarten wil kiezen - geen functionaliteit
    # verloren, enkel niet langer het standaard pad.
    with st.expander(f"Alle {len(candidates)} combinaties (geavanceerd)", expanded=False):
        option_labels = []
        for i, cand in enumerate(candidates):
            parts = []
            for match_idx, pair in enumerate(cand["ordered_pairs"], start=1):
                p1, p2 = tuple(pair)
                parts.append(f"M{match_idx}: {name_lookup_global.get(p1,p1)}/{name_lookup_global.get(p2,p2)}")
            prefix = "* " if i == 0 else ""
            ebw = cand.get("expected_boards_won")
            ebw_txt = f" (verwacht {ebw:.2f} gewonnen matchen)" if ebw is not None else f" (score {cand['score']:.3f})"
            option_labels.append(f"{prefix}{' | '.join(parts)}{ebw_txt}")
        chosen_idx = st.radio(
            "Combinaties", list(range(len(candidates))), format_func=lambda i: option_labels[i],
            key=f"rot_choice_v3_{ploeg_id}_{next_rotation_num}", label_visibility="collapsed",
        )
        chosen = candidates[chosen_idx]
        _render_rotation_points_caption(chosen.get("rotations"))
        if chosen["assignment"]:
            with st.expander("Detail van de gekozen combinatie (winkans per match)", expanded=True):
                _render_assignment_with_outcome(chosen["assignment"], name_lookup_global)
        if st.button(f"Bevestig rotatie {next_rotation_num}", key=f"rot_confirm_v3_{ploeg_id}_{next_rotation_num}", type="primary"):
            _bevestig_rotatie(chosen["ordered_pairs"], opp_pairs_voor_log, _candidate_win_probs(chosen))
