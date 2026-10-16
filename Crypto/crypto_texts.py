"""Alle uitlegteksten van de Crypto-pagina (tooltips, kolomuitleg, voorbeelden, oordeelregels)."""
from crypto_dip import EPISODE_GAP_DAYS

# --------------------------------------------------------------------------- uitleg instellingen
H = {
    "preset": "Kies je beurs. Coinbase intro: 0,25% maker / 0,50% taker. 'Eigen waarden' om zelf in te vullen.",
    "maker": "MAKER = limit-order die in het orderboek blijft staan ('koop als de prijs €X is'). "
             "Je voegt liquiditeit toe → lagere fee. Uitvoering niet gegarandeerd.",
    "taker": "TAKER = order die meteen uitgevoerd wordt aan de beste beschikbare prijs (market-order). "
             "Je neemt liquiditeit weg → hogere fee én je betaalt de spread.",
    "ordertype": "Grid- en dip-strategieën werken met vooraf gekende prijzen, dus limit-orders (maker) "
                 "zijn logisch. Kies taker als je met market-orders werkt.",
    "spread": "Extra kost per transactie bovenop de fee: verschil tussen koop- en verkoopprijs en "
              "slippage. Bij limit-orders ~0, bij market-orders op grote munten ~0,05–0,2%.",
    "interval": "Duur van één candle (koersbalkje). Kortere candles = meer detail, meer data (en langer laden: "
                "Coinbase geeft max. 300 candles per verzoek).",
    "days": "Hoeveel dagen geschiedenis geanalyseerd wordt.",
    "topn": "Aantal Coinbase-munten met het hoogste handelsvolume (laatste 24u) dat bekeken wordt.",
    "swing": "SWING-DREMPEL = enkel een meetlat, geen strategie. Telt hoe vaak de koers minstens dit % "
             "omkeert (bv. 3% omhoog na een dal). Hoe meer swings, hoe 'beweeglijker' de munt.",
    "step": "GRID-STAP = de strategie. Koop een deel telkens de koers dit % zakt; verkoop dat deel zodra "
            "het weer dit % gestegen is. Moet ruim boven 2× de kost per transactie liggen.",
    "levels": "Aantal koopniveaus onder de startprijs. Kapitaal wordt gelijk verdeeld. "
              "10 levels × 2% = grid dekt ±18% daling; zakt de koers dieper, dan zit je vast.",
    "dip_hist": "Hoeveel jaar dagdata gebruikt wordt (5 jaar = 1.830 dagen). De BACKTEST is korter: de eerste "
                "'referentie'-dagen (bv. 365) kunnen niet gebruikt worden omdat er dan nog geen top bekend is. "
                "Voorbeeld: 1.830 − 364 = 1.466 dagen backtest (±4 jaar). Jonge munten hebben minder data. "
                "Zie 'Dagen data', 'Start backtest' en 'Periode (jaar)' in de tabel.",
    "lookback": "REFERENTIE HOOGSTE PUNT = hoe ver de app terugkijkt om de 'top' te bepalen. Alle dalingen "
                "worden daaraan gemeten. Het is een MEEBEWEGEND venster: een oude piek valt na zoveel dagen weg.\n\n"
                "Voorbeeld: een munt piekte 6 maanden geleden op €100 en staat nu op €40.\n"
                "• Referentie 365 dagen → top €100 → daling −60% → bij koopdrempel −50%: in de koopzone.\n"
                "• Referentie 90 dagen → top van de laatste 90 dagen bv. €55 → daling −27% → niet in de koopzone.\n\n"
                "ADVIES: begin met 365 dagen (de 'jaarhoogte', een gangbare maat). 180 = meer signalen, maar de top "
                "verdwijnt snel na een crash. 730 = enkel zinvol met 8 jaar historiek (de backtest wordt korter en "
                "jonge munten vallen af). Kies niet de waarde met het mooiste resultaat (dat is bijsturen op het "
                "verleden), maar kijk of het Oordeel per munt stabiel blijft bij 180, 365 en 730. "
                "Opgeslagen instellingen gelden enkel bij de referentie waarmee ze bewaard werden.",
    "amount": "Bedrag dat je per munt wil inzetten, standaard in één schijf. Alle €-kolommen rekenen hiermee. "
              "Koersdata komt van Coinbase (USD-markt; bestaat die niet: USDC of EUR). "
              "Wisselkoerseffecten €/$ worden genegeerd.",
    "mode": "OPTIMAAL PER MUNT: de app test per munt alle combinaties koopdrempel (30–85%) × winstdoel "
            "(10–100%) en kiest wat historisch het beste (en stabielste) rendement per jaar gaf.\n\n"
            "VASTE WAARDEN: dezelfde koopdrempel en hetzelfde winstdoel voor alle munten.\n\n"
            "Munten waarvoor je in 'Detail munt' eigen instellingen opsloeg, gebruiken altijd die.",
    "dip": "KOOPDREMPEL: koop pas als de slotkoers minstens dit % onder de top staat.",
    "target": "WINSTDOEL: verkoop zodra de koers dit % boven je aankoopprijs komt (vóór kosten).",
    "maxwait": "MAX. WACHTTIJD VOOR 'KANS' geldt ENKEL voor de kolommen Hersteld, Kans per keer, Kans per dag en "
               "Te recent. Niet voor backtest, test, %/jaar of eindwaarde (die wachten onbeperkt).\n\n"
               "Voorbeeld: je koopt op −50%, winstdoel +30%, en het doel wordt pas na 400 dagen gehaald.\n"
               "• Wachttijd 365 → telt als NIET hersteld ❌\n"
               "• Wachttijd 730 → telt als hersteld ✅",
    "min_trades": "Optimalisatie negeert combinaties met minder afgeronde trades dan dit. "
                  "Voorkomt dat één toevallige gelukstreffer als 'beste' gekozen wordt.",
    "test_frac": "BETROUWBAARHEIDSTEST: het laatste deel van de BACKTEST wordt achtergehouden. De beste "
                 "koopdrempel en het beste winstdoel worden enkel op het eerste deel (TRAINING) gezocht en daarna "
                 "blind getest op het laatste deel (TEST).\n\n"
                 "Voorbeeld: backtest 1.466 dagen, test 30% → test = laatste 440 dagen (±1,2 jaar), "
                 "training = eerste 1.026 dagen (±2,8 jaar). 0% = test uit (sneller).\n\n"
                 "Werk je met 'Vaste waarden' of een opgeslagen instelling, dan wordt precies díe instelling "
                 "blind getest (er wordt dan niets opnieuw gezocht).",
    "ladder": "SCHIJVEN: standaard zit je hele bedrag in één schijf. Je kan rijen toevoegen om het te verdelen, "
              "bv. €500 bij −50% en €500 bij −65%. Zakt de koers dieper, dan koop je bij en wordt je gemiddelde "
              "aankoopprijs lager. Elke schijf verkoopt apart bij het winstdoel. Meer schijven = een andere "
              "strategie dan in de tabel (zie de ⚠️ vergelijking onder '4. Resultaat').",
}

# --------------------------------------------------------------------------- uitleg kolommen (tooltip)
C_HELP = {
    # grid
    "score": "Samengestelde score 0–100 binnen deze selectie (swings, weinig trend, grid-resultaat, volume).",
    "swings_per_week": "Aantal omkeringen ≥ swing-drempel per week.",
    "avg_swing_pct": "Gemiddelde grootte van zo'n omkering.",
    "efficiency": "Netto koersverschil ÷ totale afgelegde weg. ~0 = zijwaarts (goed voor grid), ~1 = sterke trend.",
    "autocorr_lag1": "Negatief = na een stijging volgt vaker een daling (terugkeer-gedrag, goed voor grid).",
    "grid_round_trips": "Aantal afgeronde koop+verkoop-cycli in de backtest.",
    "grid_net_pct": "Totaal resultaat ná kosten, incl. nog open posities aan de slotkoers.",
    "drift_pct": "Koersverandering over de hele periode.",
    "max_drawdown_pct": "Grootste daling vanaf een top in de periode.",
    "quote_vol_day_musd": "Gemiddeld handelsvolume per dag in miljoen (USD). Hoger = kleinere spread.",
    # dip
    "coinbase": "In welke markten je deze munt op Coinbase kan kopen (bv. EUR/USD/USDC). Alle munten in de lijst "
                "komen van Coinbase; ⏸️ = handel staat tijdelijk uit. Controleer altijd in je eigen Coinbase-app.",
    "verdict": "OORDEEL OVER DE STRATEGIE, enkel gebaseerd op de 🧪 TEST (data die de instelling niet zag). "
               "Het zegt NIET of je nu moet kopen (daarvoor is er de kolom 'Koopzone nu?') en het kijkt NIET naar "
               "de Eindwaarde van de hele historiek (die is achteraf geoptimaliseerd).\n"
               "🟢 Interessant – test positief, verslaat kopen&houden, minstens 1 afgeronde trade, ≥3 keren in zone.\n"
               "🟡 Twijfel – test positief, maar met een addertje (zie 'Waarom').\n"
               "⚪ Niets bewezen – in de test nooit gekocht, of geen test mogelijk.\n"
               "🟠 Onder water – in de test gekocht en nog niet hersteld: papieren verlies, geen bewijs van falen.\n"
               "🔴 Niet interessant – training al zonder winst, of test negatief zonder open positie.\n"
               "De tabel is op dit oordeel gesorteerd (beste bovenaan).",
    "why": "Korte reden achter het oordeel, met de cijfers erbij.",
    "now": "KOOPZONE NU? Puur mechanisch: staat de munt vandaag onder je koopdrempel?\n"
           "🛒 In koopzone = de regel zegt nu: koop.\n"
           "👀 Nog X% zakken = de munt moet eerst nog X% dalen (in % van de koers van vandaag).\n"
           "Een goede kandidaat om NU te kopen = 🛒 én een oordeel 🟢/🟡.",
    "source": "Waar de instellingen vandaan komen: OPGESLAGEN (door jou in Detail munt), OPTIMAAL "
              "(automatisch historisch beste) of VAST (jouw algemene instellingen). "
              "'Vast*' = optimalisatie vond te weinig trades, daarom vaste waarden gebruikt.",
    "dip_pct": "Gebruikte koopdrempel: koop als de koers zoveel % onder de top staat. Bij meerdere schijven: de eerste (minst diepe).",
    "target_pct": "Gebruikt winstdoel: verkoop bij zoveel % boven de aankoopprijs (vóór kosten).",
    "current_dd_pct": "Hoe ver de koers NU onder de top staat. Bv. −62% = 62% goedkoper dan het hoogste punt "
                      "van de referentieperiode. Let op: ook een korte piek telt als top.",
    "to_zone_pct": "Hoeveel de koers vanaf nu nog moet zakken tot de (eerste) koopdrempel. "
                   "0 = zit nu in de koopzone.",
    "history_days": "Dagen koersgeschiedenis. De eerste dagen (lengte referentieperiode) leveren geen signalen: "
                    "er is dan nog geen top om mee te vergelijken.",
    "episodes": f"Aantal AFZONDERLIJKE crashes: keren dat de munt in de koopzone kwam. Een nieuwe keer telt pas "
                f"als de koers eerst ≥10 procentpunt boven de koopdrempel hersteld is (drempel −50% → tot −40% of "
                f"beter) óf {EPISODE_GAP_DAYS} dagen buiten de zone bleef. Schommelen rond de drempel (−51%, −48%, "
                "−52%…) is dus dezelfde keer. 1–2 = te weinig bewijs, 5+ zegt iets.",
    "ep_text": "Bv. '12 van 19': van de keren in de zone waarvan de afloop al gekend is (19), werd het winstdoel "
               "12 keer gehaald binnen de max. wachttijd, als je kocht op de EERSTE dag in de zone. "
               "Verschil met 'Keren in zone' (bv. 23) = keren die te recent zijn om te beoordelen.",
    "episode_hit_pct": "Zelfde als 'Hersteld' in %. Eerlijker dan 'Kans per dag' omdat elke keer even zwaar weegt.",
    "hit_rate_pct": "Kans per DAG: op hoeveel % van alle koopzone-dagen werd het doel gehaald binnen de max. "
                    "wachttijd. Lange periodes in de zone wegen zwaarder; altijd samen bekijken met 'Keren in zone'.",
    "median_days": "STATISTIEK, niet de backtest: als je op een willekeurige koopzone-dag kocht, hoe lang duurde "
                   "het typisch tot het winstdoel (mediaan; enkel geslaagde keren). "
                   "Voor de echte looptijd van de backtest-trades: zie 'Gem. dagen/trade'.",
    "median_further_pct": "Hoeveel de koers ná aankoop typisch nog verder zakte vóór het herstel. "
                          "−20% = je stond eerst nog 20% in het rood.",
    "worst_further_pct": "De SLECHTSTE keer: hoe diep je ná aankoop in het rood stond. −78% = €1.000 was tijdelijk "
                         "€220 waard. Je stresstest: kan je dit uitzitten zonder te verkopen?",
    "still_open": "Koopzone-dagen die te recent zijn om te beoordelen (doel nog niet gehaald, wachttijd nog niet "
                  "om). Tellen niet mee in de kans-kolommen.",
    "dip_round_trips": "Aantal afgeronde koop+verkoop-cycli in de backtest (alle schijven samen).",
    "bt_start": "Startdatum van de backtest = eerste dag waarop er een 'top' gekend is "
                "(begin data + referentieperiode). Alle €-bedragen lopen van deze datum tot vandaag.",
    "bt_years": "Duur van de backtest in jaren (startdatum → vandaag). Eindwaarde, Winst en %/jaar slaan op deze periode. "
                "Verschillen die tussen munten? Dan zijn eindwaardes niet vergelijkbaar: gebruik %/jaar.",
    "avg_hold_days": "Gemiddeld aantal dagen tussen aankoop en verkoop van de afgeronde backtest-trades. "
                     "Het geld zit niet altijd vast: tussen trades staat het stil (zie Tijd belegd).",
    "capital": "Ingezet bedrag voor deze munt (standaard één schijf).",
    "final_eur": "Wat je inzet vandaag waard zou zijn met de strategie, ná kosten. = vrij geld + open positie aan de "
                 "koers van vandaag. De open positie zit hier DUS AL in; 'Open: vast' komt er niet bij.\n"
                 "Let op: bij 'Optimaal' zijn koopdrempel en winstdoel gezocht op ÉNKEL DEZE data (ook de test-"
                 "periode). Een hoge eindwaarde is dus deels achteraf geluk en bewijst niet dat het in de toekomst "
                 "werkt. Daarom kijkt het Oordeel naar de test, niet naar dit bedrag.",
    "profit_eur": "Eindwaarde min inzet.",
    "dip_annual_pct": "Eindwaarde omgerekend naar gemiddeld % per jaar over de backtest-periode (samengesteld): "
                      "Eindwaarde ≈ Inzet × (1 + %/jaar) ^ Periode in jaren. "
                      "Bv. €1.000 → €5.926 in 4 jaar ≈ 56%/jaar. Inclusief de tijd dat het geld stillag. "
                      "Gebruik dit om munten met een verschillende periode eerlijk te vergelijken.",
    "buy_hold_eur": "Wat je inzet waard zou zijn als je op de startdag van de backtest alles kocht en hield. "
                    "Dit is de lat: doet de strategie het slechter, dan was niets doen beter.",
    "invested_pct": "Deel van de tijd dat er geld in de munt zat. De rest staat het stil (en kan elders renderen). "
                    "Hoog kan ook betekenen: lang vastgezeten.",
    "lowest_eur": "Laagste waarde van je inzet ooit tijdens de backtest. Wat je op je slechtste moment zag.",
    "open_cost_eur": "Bedrag dat je betaalde voor de aankopen die nog niet verkocht zijn (herbelegde winst "
                     "inbegrepen). Is dus geen extra winst. Leeg = geen open positie.",
    "open_value_eur": "Wat die open aankopen vandaag waard zijn aan de huidige koers. Dit zit in de Eindwaarde.",
    "open_result_eur": "Winst (+) of verlies (−) in € op de open aankopen: Open waarde − Open vast, "
                       "aankoopkost inbegrepen (verkoopkost nog niet). Dit is NIET gerealiseerd: pas bij verkoop.",
    "open_result_pct": "Hetzelfde in %: huidige waarde t.o.v. aankoopbedrag van de open positie.",
    # betrouwbaarheidstest
    "wf_params": "Koopdrempel / winstdoel die in de test gebruikt werden. Modus 'Optimaal': het optimum dat in de "
                 "TRAININGSPERIODE alleen gevonden werd (kan verschillen van 'Koopdrempel %' en 'Winstdoel %', die "
                 "zijn gezocht op de hele historiek). Modus 'Vast' of 'Opgeslagen': jouw eigen instelling "
                 "(met vermelding 'jouw instelling').",
    "train_period": "Trainingsperiode: startmaand en duur. Hierop werden de instellingen gezocht.",
    "train_annual_pct": "Rendement per jaar in de TRAININGSPERIODE. Is altijd mooi, want de instellingen zijn juist "
                        "hierop gekozen (achteraf bekeken). Op zich zegt dit weinig.\n"
                        "Is de periode korter dan 0,5 jaar, dan staat er ⚠️ 'korte periode' bij: omrekenen naar een "
                        "jaar is dan niet betrouwbaar.",
    "test_period": "Testperiode: startmaand en duur, loopt tot vandaag. = de laatste X% van de backtest "
                   "(X instelbaar, standaard 30%). Deze data werd NIET gebruikt om te zoeken.",
    "test_status": "AFGEROND = in de test gekocht én verkocht. POSITIE OPEN = gekocht, winstdoel nog niet bereikt "
                   "(resultaat op papier). GEEN KOOPKANS = nooit in de koopzone geweest → 0%, bewijst niets.",
    "test_trades": "Afgeronde koop+verkoop-cycli in de testperiode.\n"
                   "0 + 'Geen koopkans' = nooit gekocht: niets bewezen.\n"
                   "0 + 'Positie open' = wel gekocht, doel nog niet bereikt: resultaat op papier.\n"
                   "1 = één voorbeeld, geen bewijs. 3+ = begint te overtuigen.\n"
                   "Veel (10+) = veel kleine rondes: let op kosten (2× fee per ronde).\n"
                   "Bij dip-kopen is weinig trades normaal: wachten op een diepe val + groot doel duurt maanden.",
    "test_pct": "Totaal resultaat over de HELE testperiode (niet per jaar) met de test-instelling, vers kapitaal, "
                "ná kosten, open positie aan de koers van vandaag.\n"
                "Voorbeeld: 39% → €1.000 werd in de testperiode €1.390. Bij 'Positie open' is een deel daarvan "
                "nog papieren winst (of papieren verlies). Dit is de EERLIJKSTE maat van de tabel.",
    "test_annual_pct": "Testresultaat omgerekend naar % per jaar (39% over 1,2 jaar ≈ 32%/jaar).\n"
                       "⚠️ Is de testperiode korter dan 0,5 jaar, dan staat er 'korte periode' bij: omrekenen naar "
                       "een jaar is dan niet betrouwbaar (39% over 0,4 jaar wordt ≈ 128%/jaar, terwijl er maar één "
                       "trade kan zijn). Kijk dan naar 'Test totaal %'. In de sortering telt bij een korte periode "
                       "het totaal, niet het omgerekende cijfer.",
    "test_eur": "Wat jouw bedrag per munt op het einde van de testperiode (vandaag) waard zou zijn.",
    "test_bh_pct": "Kopen&houden in dezelfde testperiode: de lat voor 'Test totaal %'.\n"
                   "Test 39% vs K&H 150% → strategie positief maar kopen&houden was veel beter (🟡).\n"
                   "Test 39% vs K&H −30% → strategie beschermde je tegen een daling (sterk 🟢).",
}

DIP_EXPLAIN = """
**Bron en opslag** — Alle koersen komen van **Coinbase** (USD-markt; bestaat die niet: USDC of EUR). De dagkoersen
worden bewaard (in de cloud: Firestore) en bij elke refresh komen enkel de nieuwe dagen erbij. Ook de berekende
tabel wordt bewaard: open je de pagina, dan staat de laatste tabel er meteen, met de datum waarop ze berekend werd.
Een nachtelijke update rekent de tabel met de standaardinstellingen elke nacht opnieuw.

**Twee begrippen** — *Top*: hoogste koers van de laatste X dagen (bv. 365), een **meebewegend venster**: een oude
piek valt na X dagen weg en dan wordt de top lager. *Koopzone*: een dag waarop de slotkoers minstens de koopdrempel
onder die top staat. De top staat per munt in *Detail munt*, blok *3. De regel in cijfers*.

**Oordeel, Koopzone nu? en Waarom** — twee aparte vragen:
- **Oordeel** = *is de strategie voor deze munt betrouwbaar?* Gebaseerd op de 🧪 test (data die de instelling nooit zag).
- **Koopzone nu?** = *zegt de regel vandaag koop?* Puur mechanisch: staat de koers onder je koopdrempel?
- Een goede kandidaat om **nu** te kopen = 🛒 in koopzone **én** oordeel 🟢/🟡.

De tabel staat gesorteerd: 🟢 bovenaan, 🔴 onderaan. Zie het blok *🧭 Hoe wordt het oordeel bepaald?*.

**Instellingen per munt**
- **Coinbase** — in welke markten je de munt kan kopen (EUR/USD/USDC/USDT).
- **Bron** — *Opgeslagen*: door jou bewaard in *Detail munt*. *Optimaal*: de app testte alle combinaties
  koopdrempel × winstdoel en koos de historisch beste. *Vast*: jouw algemene instellingen.
- **Koopdrempel % / Winstdoel %** — de waarden die voor deze munt gebruikt werden. Standaard zit het hele bedrag
  in **één schijf**.

**🧪 Betrouwbaarheidstest (training / test)** — is de instelling echt goed of gewoon achteraf geluk?
De BACKTEST wordt gesplitst, bv. 30% test:
`|——— TRAINING ±2,8 jaar ———|—— TEST ±1,2 jaar ——| vandaag`
1. Modus *Optimaal*: enkel in de **training** zoekt de app de beste koopdrempel en het beste winstdoel.
   Modus *Vast/Opgeslagen*: jouw instelling wordt zonder opnieuw te zoeken getest.
2. Die instelling wordt **blind** toegepast op de **test** (die data zag de zoektocht nooit), met vers kapitaal.
- **Training: drempel/doel** — de instelling die in de test gebruikt werd.
- **Training: periode / %/jaar** — wanneer en hoe goed. Altijd mooi, want hierop gekozen.
- **Test: periode** — van wanneer tot vandaag.
- **Test: status** — *Afgerond* (gekocht + verkocht), *Positie open* (gekocht, nog niet verkocht → op papier),
  *Geen koopkans* (nooit diep genoeg gezakt → 0%, dat bewijst niets).
- **Test trades** — aantal afgeronde koop+verkoop-rondes in de test (zie voorbeelden).
- **Test totaal % / %/jaar / eindwaarde €** — het **eerlijkste** cijfer. Vergelijk met **Test kopen&houden %**.
  Is de test korter dan 0,5 jaar, dan staat bij %/jaar **⚠️ korte periode**: omrekenen naar een jaar is dan niet
  betrouwbaar, kijk naar het totaal.

**Huidige toestand**
- **Nu onder top %** — hoeveel goedkoper dan het hoogste punt. −62% = 62% onder de top.
- **Nog te zakken %** — hoeveel de koers nog moet dalen tot de koopzone. 0 = nu kopen volgens de regel.

**Hoeveel bewijs?**
- **Dagen data** — lengte geschiedenis. De eerste *referentieperiode* dagen leveren geen signaal.
- **Keren in zone** — aantal afzonderlijke crashes. Een nieuwe keer telt pas als de koers eerst ≥10 procentpunt
  boven de koopdrempel hersteld is (drempel −50% → tot −40% of beter) of 30 dagen buiten de zone bleef.
  Schommelen rond de drempel (−51%, −48%, −52%…) is dezelfde keer. 1–2 = te weinig bewijs, 5+ begint iets te zeggen.
- **Te recent** — koopzone-dagen waarvan we de afloop nog niet kennen.

**Herstel na aankoop** *(wat gebeurde er als je op zo'n dag kocht?)*
- **Hersteld (keren)** — bv. *12 van 19*: van de 19 keren waarvan de afloop gekend is, werd het winstdoel 12 keer
  gehaald binnen de max. wachttijd. Keren in zone (bv. 23) min 19 = 4 keren die nog te recent zijn.
- **Kans per keer %** — hetzelfde in %. Elke keer weegt even zwaar → de eerlijkste kans.
- **Kans per dag %** — over alle koopzone-dagen. Een lange periode in de zone weegt hier zwaar.
- **Mediaan dagen** — *statistiek*: als je op een willekeurige koopzone-dag kocht, typische wachttijd tot het doel.
  Dit is **niet** de looptijd van de backtest-trades (zie *Gem. dagen/trade*).
- **Typ. verdere daling %** — hoeveel je ná aankoop meestal nog in het rood ging. Je koopt zelden de bodem.
- **Ergste verdere daling %** — de slechtste keer. Je **stresstest**: kan je dat uitzitten?

**Backtest met jouw bedrag** *(over de hele historiek: koop met het hele bedrag op de eerste koopzone-dag,
verkoop bij het winstdoel, opnieuw kopen als de koers nog in de zone staat, geen stop-loss, winst wordt
herbelegd, kosten inbegrepen)*
- **Start backtest / Periode (jaar)** — over welke periode alle €-bedragen gaan (start = begin data + referentieperiode).
- **Trades / Gem. dagen/trade** — afgeronde koop+verkoop-cycli en hun gemiddelde looptijd.
- **Inzet €** — totaal bedrag. *Detail munt* start met **dezelfde instelling als de tabelrij**, dus dezelfde
  Eindwaarde. Voeg je daar schijven toe of wijzig je ze, dan is het een andere strategie en toont de pagina een
  ⚠️ vergelijking met de tabel.
- **Eindwaarde € / Winst €** — wat het vandaag waard zou zijn, open positie aan de huidige koers.
  Bij *Optimaal* is dit achteraf geoptimaliseerd op dezelfde data: mooi, maar geen bewijs.
- **%/jaar** — eindwaarde omgerekend naar gemiddeld rendement per jaar over de *Periode*.
  Eindwaarde ≈ Inzet × (1 + %/jaar)^Periode.
- **Kopen&houden €** — alles kopen op de startdag en niets doen. **De lat** die de strategie moet halen.
- **Tijd belegd %** — hoe vaak er geld in de munt zat. De rest ligt stil.
- **Laagste waarde €** — je slechtste moment. Vergelijk met de laagste waarde van kopen&houden (Detail munt).
- **Open: vast €** — wat je betaalde voor de aankoop die nog niet verkocht is.
- **Open: waarde €** — wat dat vandaag waard is (zit al in de eindwaarde).
- **Open: resultaat € / %** — papieren winst of verlies op die open aankoop (nog niet gerealiseerd).

⚠️ **Survivorship bias**: munten die naar nul gingen zitten niet in de data → kansen zijn te optimistisch.
⚠️ **Optimaal = achteraf bekeken.** Daarom: kijk naar het Oordeel en de 🧪 test-kolommen, niet enkel naar %/jaar.
"""

DIP_EXAMPLES = """
### 1. Hoe lang is de backtest en hoe wordt de testperiode bepaald?
- **Historiek** (instelling, bv. 5 jaar) = hoeveel dagdata de app gebruikt. Jonge munten hebben minder (zie *Dagen data*).
- De eerste **referentie**-dagen (bv. 365) kunnen niet gebruikt worden: er is nog geen "top" om mee te vergelijken.
  **Backtest = data − referentie.**
- Voorbeeld: 5 jaar = 1.830 dagen − 364 = **1.466 dagen backtest** (±4 jaar).
- **Testperiode = laatste 30% daarvan** = 440 dagen (±1,2 jaar). Training = eerste 1.026 dagen (±2,8 jaar).
- Jongere munt: 913 dagen data → 549 dagen backtest (±1,5 jaar) → test van maar 165 dagen (±5,5 maand).
  Hoe korter de test, hoe kleiner de kans dat de munt in die periode ooit de koopzone bereikt.

### 2. Referentie hoogste punt
Een munt piekte 6 maanden geleden op €100 en staat nu op €40. Koopdrempel: −50%.

| Referentie | Top | Daling nu | In koopzone? |
|---|---|---|---|
| 365 dagen | €100 | −60% | ✅ ja |
| 90 dagen | bv. €55 | −27% | ❌ nee |

Langer = diepere "dips", minder signalen, kortere backtest (730 dagen laat van 5 jaar data nog ±3 jaar over).
Korter = vaker een signaal, maar de "val" is dan minder diep.

### 3. Max. wachttijd voor kans
Telt **enkel** voor *Hersteld, Kans per keer, Kans per dag, Te recent*. Niet voor backtest, test, %/jaar en eindwaarde.
Je koopt op −50%, doel +30%, en het doel wordt na 400 dagen gehaald:
wachttijd 365 → ❌ niet hersteld; wachttijd 730 → ✅ hersteld.

### 4. Test trades (aantal afgeronde koop+verkoop-rondes in de test)

| Test trades | Status | Betekenis |
|---|---|---|
| 0 | Geen koopkans | Nooit in de koopzone: er gebeurde niets. **Niets bewezen**, goed noch slecht. |
| 0 | Positie open | Wel gekocht, doel nog niet bereikt. Resultaat staat enkel op papier. |
| 1 | Afgerond | Eén geslaagde ronde: een voorbeeld, geen bewijs. |
| 3 | Afgerond | Drie keer gekocht én met winst verkocht: begint te overtuigen. |
| 15 | Afgerond | Veel kleine rondes (laag winstdoel). Let op de kosten: elke ronde kost 2× fee. |

Bij dip-kopen is een laag aantal normaal (wachten op een diepe val + groot doel duurt maanden). Laag = weinig
bewijs, niet per se slecht.

### 5. Test totaal (bv. 39%) en Test %/jaar
Je start de testperiode met vers kapitaal: €1.000. Op het einde (vandaag) is dat €1.390, na kosten.
Het is het totaal over de **hele testperiode**, niet per jaar: bij 1,2 jaar is dat ±32%/jaar (*Test %/jaar*).
Staat de status op *Positie open*, dan is een deel van die 39% nog papieren winst.

**Korte test (minder dan 0,5 jaar)?** Dan toont *Test %/jaar* het omgerekende cijfer mét **⚠️ korte periode**.
Voorbeeld: +39% over 0,49 jaar wordt omgerekend ±96%/jaar, over 0,40 jaar ±128%/jaar. Zo'n cijfer suggereert een
jaarrendement dat er niet is, zeker met één trade: gebruik het **totaal** (+39%). In de sortering telt bij een korte
test ook het totaal, zodat een korte test niet hoger eindigt dan een lange test met hetzelfde resultaat.

### 6. Test totaal vs. Test kopen&houden

| Test totaal | Kopen&houden | Lezing |
|---|---|---|
| +39% | +150% | Strategie won wel, maar doen niets deed veel beter → 🟡 |
| +39% | −30% | Strategie beschermde je tegen een daling → sterk 🟢 |
| +39% | +35% | Licht beter dan niets doen → 🟢 (bij genoeg bewijs) |
| −10% | +20% | Positie nog onder water (papieren verlies) → 🟠 |

Is kopen&houden veel hoger, dan **voegde de strategie in die periode niets toe** (maar ze verloor ook geen geld).
Drie nuances:
1. Kopen&houden weet je pas **achteraf**: je kon niet vooraf weten welke munt zou stijgen.
2. Kopen&houden zit altijd volledig in de munt en kan diep zakken. Vergelijk *Laagste waarde* van de strategie met die
   van kopen&houden (Detail munt).
3. De strategie koopt pas na een diepe val en mist dus per definitie stijgingen zonder val.

### 7. Eindwaarde, open vast, open waarde, open resultaat
Inzet €1.000 in één schijf (kosten weggelaten voor de eenvoud).
- Gekocht, +30% verkocht → €1.300 vrij → opnieuw gekocht en nog niet verkocht = **open positie**.
- Sinds de herkoop is de koers +10% gestegen.

| Kolom | Bedrag | Uitleg |
|---|---|---|
| Open: vast | €1.300 | Wat je betaalde voor de open positie |
| Open: waarde | €1.430 | Wat die vandaag waard is |
| Open: resultaat | +€130 (+10%) | Papieren winst = waarde − vast |
| **Eindwaarde** | **€1.430** | = vrij geld 0 + open waarde 1.430 |
| **Winst** | **€430** | = eindwaarde − inzet |

**Open: vast** moet je dus **niet** bij de winst optellen: de eindwaarde bevat de open positie al aan de koers van vandaag.

### 8. %/jaar versus eindwaarde: waarom hoger eindbedrag bij lager %/jaar?
**Eindwaarde ≈ Inzet × (1 + %/jaar)^Periode.** Een lager %/jaar over een langere periode geeft een hoger bedrag.

| Munt | Periode | %/jaar | Eindwaarde van €1.000 |
|---|---|---|---|
| A | 4,0 jaar | 40% | €3.842 |
| B | 1,5 jaar | 60% | €2.024 |

B heeft het hoogste %/jaar, A het hoogste eindbedrag: A liep gewoon langer. Vergelijk munten met een verschillende
*Periode (jaar)* daarom op **%/jaar**; eindwaardes zijn enkel vergelijkbaar bij dezelfde periode.

### 9. Eindwaarde €7.000 en toch 🟠 of 🔴: hoe kan dat?
De eindwaarde en het oordeel meten **niet hetzelfde**:

| | Eindwaarde (hele historiek) | Oordeel |
|---|---|---|
| Periode | alle ±4 jaar | enkel de **test** (laatste ±1,2 jaar) |
| Instelling | gezocht op **alle** data, ook de test | gezocht op de training, blind op de test |
| Open verlies | zit erin, maar is klein t.o.v. eerdere winsten | telt voluit mee |

Voorbeeld: €1.000 → €7.000 over 4 jaar, vooral dankzij trades in jaar 1 tot 3. In de test kocht de strategie 8 maanden
geleden op −50%, daarna zakte de koers nog 30% en er is geen herstel gekomen:
test = −30%, status *Positie open* → **🟠 Onder water**. De hele historiek was dus prima, maar de recentste periode
bevestigt het (nog) niet. Vergelijk de dagen dat de positie open staat met *Mediaan dagen* (typische wachttijd).

### 10. Koop bij −85% van de top, verkoop bij +20%: wanneer koop je opnieuw?
De **top** is de hoogste koers van de **laatste 365 dagen** (meebewegend venster). Hij hangt **niet** aan je laatste
verkoop. Neem top = 100, koopdrempel −85%, winstdoel +20%.

| Stap | Gebeurt | Uitleg |
|---|---|---|
| 1 | Koers zakt tot ≤ 15 (100 × 0,15) | Slotkoers staat ≥ 85% onder de top → **koop** (bv. aan 14) |
| 2 | Koers stijgt tot 14 × 1,20 = 16,8 | **Verkoop** aan de aankoopprijs + 20%, niet aan "15 + 20%" |
| 3 | Koers staat op 16,8 = 83% onder de top 100 | Nog **niet** ≤ 15 → **niet** opnieuw kopen |
| 4a | Koers zakt opnieuw tot ≤ 15 terwijl de top nog 100 is | **Opnieuw kopen**: dezelfde top, hetzelfde koopniveau |
| 4b | De piek van 100 is ouder dan 365 dagen | Die valt weg: top wordt bv. 40 → nieuw koopniveau 6 (40 × 0,15) |
| 4c | Koers klimt naar een nieuwe top van 200 | Koopniveau stijgt naar 30 (200 × 0,15) |

- **Een schijf is nooit dubbel belegd.** Na de verkoop kan er pas opnieuw gekocht worden op een volgende dag, als er weer aan de voorwaarde voldaan is.
- **Ja, je kan veel kopen en verkopen** als de koers lang rond het koopniveau schommelt: elke ronde levert ±20% min kosten.
- De aankoop gebeurt aan de **slotkoers van de dag** waarop de voorwaarde klopt: dat kan dus lager zijn dan het koopniveau.
- Het **koopniveau en de top van vandaag** staan per munt in *Detail munt* → *3. De regel in cijfers*, en als lijn in de grafiek.

### 11. Welke referentieperiode ("hoogste punt") kies je?
De referentie is een **meebewegend venster**: een piek telt maar zoveel dagen mee. Voorbeeld: koopdrempel −50%, een munt
piekte op €100, zakte naar €30 en blijft sindsdien rond €30–35 hangen.

| Referentie | Wat gebeurt er met de top | Koopzone? |
|---|---|---|
| 90 dagen | Na 3 maanden valt de €100-piek weg, top wordt ±€40 → daling nog maar −25% | Nauwelijks: je kocht vooral vroeg in de val |
| 365 dagen | Piek blijft een jaar de top → daling blijft ±−68% | Een jaar lang |
| 730 dagen | Piek blijft twee jaar de top | Twee jaar lang: veel dagen in de zone, maar ook lang "bijkopen" in een dalende munt |

**Advies:** begin met **365 dagen** (de "jaarhoogte"). Kies **180** voor meer signalen, **730** enkel met 8 jaar historiek.
Kies niet de waarde met het mooiste resultaat: dat is bijsturen op het verleden. Draai de analyse met 180, 365 en 730 en
vertrouw vooral de munten waarvan het **Oordeel stabiel** blijft. Opgeslagen instellingen gelden enkel bij de referentie
waarmee je ze bewaarde.

### 12. Eindwaarde in de tabel ≠ Eindwaarde in Detail: hoe kan dat?
*Detail munt* start altijd met **dezelfde instelling als de tabelrij** (één schijf), dus dezelfde Eindwaarde. Voeg je
schijven toe of wijzig je de drempel of het doel, dan is het een **andere strategie**: diepere schijven kopen zelden en
liggen lang stil. Dat spreidt het risico, maar geeft in goede periodes minder winst. Onder *4. Resultaat* staat dan een
⚠️ vergelijking met beide Eindwaardes; met **↩️ Zoals in de tabel** ga je terug.
"""

VERDICT_RULES = """
Het oordeel kijkt **enkel naar de 🧪 test** (data die de instelling nooit zag) en **niet naar de Eindwaarde** van de
hele historiek: die is bij *Optimaal* achteraf geoptimaliseerd op dezelfde data. Eerste regel die klopt wint:

| Oordeel | Voorwaarden |
|---|---|
| 🔴 **Niet interessant** | Training zelf al zonder winst (terwijl er wel gekocht werd), **of** test ≤ 0% terwijl er geen positie meer openstaat |
| ⚪ **Niets bewezen** | De munt bereikte in de test (of al in de training) nooit de koopdrempel: er werd nooit gekocht |
| ⚪ **Niet getest** | Test uit, of te weinig historiek om te splitsen (reden staat in *Waarom*) |
| 🟠 **Onder water** | Test ≤ 0% **en** positie nog open: de strategie kocht tijdens de val en de munt is nog niet hersteld (papieren verlies) |
| 🟡 **Twijfel** | Test positief, maar minstens één addertje: positie nog open (winst op papier), **of** kopen&houden deed beter, **of** minder dan 3 keer in de zone |
| 🟢 **Interessant** | Test positief, afgeronde trade(s), test ≥ kopen&houden, en ≥ 3 keer in de zone |

**Sortering:** 🟢 → 🟡 → ⚪ → 🟠 → 🔴, binnen elk niveau op *Test %/jaar* (hoogste eerst). Is de testperiode korter
dan 0,5 jaar (⚠️ korte periode), dan telt in plaats daarvan het *Test totaal %*.

**Waarom 🟠 en niet 🔴?** Een dip-strategie heeft geen stop-loss. Een negatieve test betekent dan bijna altijd: gekocht
tijdens de val en nog niet hersteld. Dat is geen bewijs dat de strategie faalt, maar wel een reëel risico.

**Koopzone nu?** is een aparte kolom: 🛒 = de munt staat vandaag onder je koopdrempel, 👀 = nog X% te zakken.
Een goede kandidaat om nu te kopen = 🛒 én oordeel 🟢 of 🟡. Een 🟢/🟡 die nog 👀 is, volg je op.

Een 🟢 blijft een historische aanwijzing, geen garantie. Klik een rij aan om de grafiek te bekijken.
"""

GENERAL = """
**Kosten.** Elke trade betaalt 2× fee (koop + verkoop). Bij Coinbase intro als maker = ±0,5% per cyclus,
als taker ±1% + spread. Kleine winststappen worden zo grotendeels opgegeten.

**Grid (kort).** Koopt bij elke daling van de grid-stap, verkoopt bij dezelfde stijging. Werkt in een zijwaartse
markt; in een dalende markt zit je vast met verlies.

**Dip-kopen (lang).** Koopt enkel als de munt diep onder haar top staat en wacht op het winstdoel.
Weinig trades, grote stappen → kosten wegen nauwelijks. Standaard met je hele bedrag in één schijf.
"""
