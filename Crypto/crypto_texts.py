"""Alle uitlegteksten van de Crypto-pagina (tooltips, kolomuitleg, voorbeelden, oordeelregels)."""
from crypto_dip import EPISODE_GAP_DAYS, MIN_TRAIN_DAYS, MIN_WINDOW_DAYS, STABLE_DIP_SPREAD, STABLE_TARGET_RATIO

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
    "dip_hist": "Hoeveel jaar dagdata gebruikt wordt (8 jaar = ±2.925 dagen). De BACKTEST is korter: de eerste "
                "'referentie'-dagen (bv. 365) kunnen niet gebruikt worden omdat er dan nog geen top bekend is. "
                "Meer historiek = meer crashes en herstellen = meer bewijs, en ruimte voor meerdere testvensters. "
                "Jonge munten hebben vanzelf minder data (zie 'Dagen data').",
    "lookback": "REFERENTIE HOOGSTE PUNT = hoe ver de app terugkijkt om de 'top' te bepalen. Alle dalingen "
                "worden daaraan gemeten. Het is een MEEBEWEGEND venster: een oude piek valt na zoveel dagen weg.\n\n"
                "Voorbeeld: een munt piekte 6 maanden geleden op €100 en staat nu op €40.\n"
                "• Referentie 365 dagen → top €100 → daling −60% → bij koopdrempel −50%: in de koopzone.\n"
                "• Referentie 90 dagen → top van de laatste 90 dagen bv. €55 → daling −27% → niet in de koopzone.\n\n"
                "ADVIES: begin met 365 dagen (de 'jaarhoogte'). 180 = meer signalen, maar de top verdwijnt snel na "
                "een crash. 730 = enkel zinvol met 8 jaar historiek. Kies niet de waarde met het mooiste resultaat, "
                "maar kijk of het Oordeel per munt stabiel blijft bij 180, 365 en 730.",
    "amount": "Bedrag dat je per munt wil inzetten, standaard in één schijf. Alle €-kolommen rekenen hiermee. "
              "Koersdata komt van Coinbase (USD-markt; bestaat die niet: USDC of EUR). "
              "Wisselkoerseffecten €/$ worden genegeerd.",
    "mode": "OPTIMAAL PER MUNT: de app test per munt alle combinaties koopdrempel (30–85%) × winstdoel "
            "(10–100%) en kiest wat historisch het beste (en stabielste) rendement per jaar gaf. In elk testvenster "
            "wordt die zoektocht opnieuw gedaan op enkel de data vóór dat venster.\n\n"
            "VASTE WAARDEN: dezelfde koopdrempel en hetzelfde winstdoel voor alle munten (en in elk venster).\n\n"
            "Munten waarvoor je in 'Detail munt' eigen instellingen opsloeg, gebruiken altijd die.",
    "dip": "KOOPDREMPEL: koop pas als de slotkoers minstens dit % onder de top staat.",
    "target": "WINSTDOEL: verkoop zodra de koers dit % boven je aankoopprijs komt (vóór kosten).",
    "maxwait": "MAX. WACHTTIJD VOOR 'KANS' geldt ENKEL voor de kolommen Hersteld, Kans per keer, Kans per dag en "
               "Te recent. Niet voor backtest, testvensters, %/jaar of eindwaarde (die wachten onbeperkt).",
    "min_trades": "Optimalisatie negeert combinaties met minder afgeronde trades dan dit. "
                  "Voorkomt dat één toevallige gelukstreffer als 'beste' gekozen wordt.",
    "n_windows": "TESTVENSTERS: hoeveel opeenvolgende jaren (achteraan de historiek, het laatste eindigt vandaag) "
                 "blind getest worden. Per venster zoekt de app de beste instelling op ALLE data vóór dat jaar en "
                 "past ze dan toe op dat jaar zelf, met vers kapitaal.\n\n"
                 "Voorbeeld met 3: zoeken t/m 2023 → test 2024; zoeken t/m 2024 → test 2025; zoeken t/m 2025 → "
                 "test 2026. Meer vensters = meer trades en meer marktfases als bewijs, maar minder training voor "
                 f"het eerste venster. Een venster vraagt minstens {MIN_TRAIN_DAYS} dagen backtest ervoor en "
                 f"minstens {MIN_WINDOW_DAYS} dagen lengte; jonge munten krijgen dus minder of kortere vensters. "
                 "0 = test uit (dan geen oordeel).",
    "min_annual": "OORDEEL – minimum GEREALISEERD rendement per jaar over de testvensters om 🟢 te krijgen. "
                  "Ter vergelijking: sparen 2–3%, aandelen-ETF ±7–8% gemiddeld. Wijzigen herberekent niets: "
                  "het oordeel past zich meteen aan.",
    "min_real_trades": "OORDEEL – minimum aantal AFGERONDE (gekocht én verkocht) trades over alle testvensters "
                       "om 🟢 te krijgen. Eén of twee trades is een anekdote; 3+ begint te overtuigen.",
    "max_open_dd": "OORDEEL – hoe diep de laatste, nog open positie maximaal onder haar aankoopprijs mag staan "
                   "voor 🟢. Een open positie in de plus is geen probleem; dieper dan dit wordt 🟡 of 🟠.",
    "live_n": "Met je standaardinstellingen toont de app de nachtelijke tabel (meteen klaar). Wijzig je een "
              "reken-instelling, dan rekent de app zelf, voor de top van dit aantal munten (op 24u-volume).",
    "save_defaults": "Bewaart je huidige instellingen (behalve de kosten) als standaard in de database. De app start "
                     "voortaan daarmee, en de nachtelijke update rekent er ook mee, zodat de tabel met jouw "
                     "instellingen elke ochtend klaarstaat.",
    "ladder": "SCHIJVEN: standaard zit je hele bedrag in één schijf. Je kan rijen toevoegen om het te verdelen, "
              "bv. €2.500 bij −50% en €2.500 bij −65%. Elke schijf verkoopt apart bij het winstdoel. Meer schijven "
              "= een andere strategie dan in de tabel (zie de ⚠️ vergelijking onder '5. Resultaat').",
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
    "coinbase": "In welke markten je deze munt op Coinbase kan kopen (bv. EUR/USD/USDC). ⏸️ = handel staat "
                "tijdelijk uit. Controleer altijd in je eigen Coinbase-app.",
    "verdict": "OORDEEL OVER DE WERKWIJZE, gebaseerd op de 🧪 TESTVENSTERS (blind getest) en vooral op GEREALISEERDE "
               "winst. Het zegt NIET of je nu moet kopen (zie 'Koopzone nu?').\n"
               "🟢 Interessant – genoeg afgeronde trades, gerealiseerd rendement ≥ jouw minimum, stabiele instelling, "
               "meerderheid van de vensters positief, open positie niet te diep.\n"
               "🟡 Twijfel – iets ontbreekt (zie 'Waarom').\n"
               "⚪ Niets bewezen / Niet getest / Te weinig data.\n"
               "🟠 Onder water – laatste positie staat diep in het rood en er is te weinig gerealiseerde winst.\n"
               "🔴 Niet interessant – gerealiseerd én inclusief open positie verlies.\n"
               "De drempels stel je in bij ⚙️ Instellingen → Oordeel.",
    "why": "Korte reden achter het oordeel, met de cijfers erbij.",
    "now": "KOOPZONE NU? Puur mechanisch: staat de munt vandaag onder je koopdrempel?\n"
           "🛒 In koopzone = de regel zegt nu: koop.\n"
           "👀 Nog X% zakken = de munt moet eerst nog X% dalen.\n"
           "Een goede kandidaat om NU te kopen = 🛒 én een oordeel 🟢 (of 🟡).",
    "source": "Waar de instelling van vandaag vandaan komt: OPGESLAGEN (door jou in Detail munt), OPTIMAAL "
              "(historisch beste over de hele historiek) of VAST (jouw algemene instellingen). "
              "'Vast*' = optimalisatie vond te weinig trades, daarom vaste waarden gebruikt.",
    "dip_pct": "Koopdrempel VANDAAG: koop als de koers zoveel % onder de top staat. Dit is de instelling voor je "
               "echte orders.",
    "target_pct": "Winstdoel VANDAAG: verkoop bij zoveel % boven je aankoopprijs (vóór kosten).",
    "buy_level": "KOOP ONDER: de koers waaronder de regel vandaag koopt (top × (1 − koopdrempel)). Daalt de top "
                 "(oude piek valt uit het venster), dan schuift dit mee omlaag.",
    "sell_level": "VERKOOP BIJ: verkoopdoel als je op het koopniveau koopt (koopniveau × (1 + winstdoel)). "
                  "Koop je lager, dan ligt je verkoopdoel ook lager: altijd aankoopprijs + winstdoel.",
    "price_now": "Laatste slotkoers (dagcandle).",
    "current_dd_pct": "Hoe ver de koers NU onder de top staat.",
    "to_zone_pct": "Hoeveel de koers vanaf nu nog moet zakken tot de koopdrempel. 0 = zit nu in de koopzone.",
    "history_days": "Dagen koersgeschiedenis.",
    "episodes": f"Aantal AFZONDERLIJKE crashes (nieuwe keer pas na ≥10 procentpunt herstel boven de drempel of "
                f"{EPISODE_GAP_DAYS} dagen buiten de zone). 1–2 = te weinig bewijs, 5+ zegt iets.",
    "ep_text": "Bv. '12 van 19': van de keren in de zone met gekende afloop werd het winstdoel 12 keer gehaald "
               "binnen de max. wachttijd, als je kocht op de eerste dag in de zone.",
    "episode_hit_pct": "Zelfde als 'Hersteld' in %: elke keer weegt even zwaar.",
    "hit_rate_pct": "Kans per DAG: over alle koopzone-dagen.",
    "median_days": "Typische wachttijd tot het winstdoel (statistiek, niet de backtest).",
    "median_further_pct": "Hoeveel de koers ná aankoop typisch nog verder zakte vóór het herstel.",
    "worst_further_pct": "De SLECHTSTE keer: hoe diep je ná aankoop in het rood stond. Je stresstest.",
    "still_open": "Koopzone-dagen die te recent zijn om te beoordelen.",
    "dip_round_trips": "Afgeronde koop+verkoop-cycli in de backtest over de hele historiek.",
    "bt_start": "Startdatum van de backtest over de hele historiek.",
    "bt_years": "Duur van de backtest over de hele historiek.",
    "avg_hold_days": "Gemiddeld aantal dagen tussen aankoop en verkoop van de afgeronde trades.",
    "capital": "Ingezet bedrag voor deze munt (standaard één schijf).",
    "final_eur": "HELE HISTORIEK met de instelling van vandaag: wat je inzet nu waard zou zijn. Let op: die "
                 "instelling is gezocht op ditzelfde verleden, dus dit cijfer is te mooi. Geen verwachting voor de "
                 "toekomst; gebruik de 🧪 testvensters.",
    "profit_eur": "Eindwaarde min inzet (hele historiek).",
    "dip_annual_pct": "Hele historiek omgerekend naar %/jaar (achteraf afgesteld: te optimistisch).",
    "buy_hold_eur": "Alles kopen op de startdag en niets doen (hele historiek).",
    "invested_pct": "Deel van de tijd dat er geld in de munt zat.",
    "lowest_eur": "Laagste waarde van je inzet tijdens de backtest.",
    "open_cost_eur": "Wat je betaalde voor de nog niet verkochte aankoop (hele historiek).",
    "open_value_eur": "Wat die open aankoop vandaag waard is.",
    "open_result_eur": "Papieren winst/verlies op de open aankoop (hele historiek).",
    "open_result_pct": "Hetzelfde in %.",
    # testvensters
    "wf_settings": "Per testvenster de koopdrempel/winstdoel die gebruikt werd (bij 'Optimaal' telkens gezocht op "
                   "de data vóór dat venster), bv. '−60/+50 · −65/+50 · −60/+75'.",
    "stable_txt": f"STABIEL = de gevonden instellingen (per venster én vandaag) liggen dicht bij elkaar: koopdrempels "
                  f"hoogstens {STABLE_DIP_SPREAD * 100:.0f} procentpunt uit elkaar en het hoogste winstdoel hoogstens "
                  f"{STABLE_TARGET_RATIO:g}× het laagste. INSTABIEL = het optimum springt (bv. +100% → +10%): de "
                  "exacte getallen zijn dan niet betrouwbaar; zet er minder geld op.",
    "test_period": "Van het begin van het eerste tot het einde van het laatste testvenster (= vandaag).",
    "win_text": "In hoeveel testvensters het resultaat (incl. open positie) positief was.",
    "real_trades": "Afgeronde trades (gekocht én verkocht) over alle testvensters samen: het bewijs.",
    "real_total_pct": "GEREALISEERD resultaat over alle testvensters samen (vensters na elkaar geschakeld, telkens "
                      "vers kapitaal), ALSOF een open positie aan haar aankoopprijs verkocht werd. Enkel echte winst.",
    "real_annual_pct": "Gerealiseerd resultaat omgerekend naar %/jaar over de totale testduur. Dit cijfer gebruikt "
                       "het oordeel (bij een test korter dan een half jaar: het totaal).",
    "open_now_pct": "Staat de laatste aankoop in het laatste venster nog open: huidige stand t.o.v. aankoopprijs. "
                    "Leeg = geen open positie.",
    "total_annual_pct": "Testresultaat per jaar INCLUSIEF de open positie aan de koers van vandaag.",
    "bh_annual_pct": "Kopen&houden in dezelfde testvensters, per jaar: ter vergelijking.",
}

DIP_EXPLAIN = """
**Welke limieten gebruik je voor je echte orders?** De kolommen **Koopdrempel / Winstdoel** (en **Koop onder /
Verkoop bij** in koers) = de instelling van **vandaag**, gezocht op alle data tot nu. De **🧪 testvensters** zeggen
hoeveel je die werkwijze mag vertrouwen: ze tonen wat er gebeurde toen de app in het verleden telkens blind de beste
instelling koos en die op het jaar erna toepaste.

**Bron en opslag** — Koersen van **Coinbase** (USD; anders USDC of EUR), bewaard in de database; bij elke refresh komen
enkel de nieuwe dagen erbij. De berekende tabel wordt ook bewaard. Een nachtelijke update rekent de tabel met jouw
standaardinstellingen (*💾 Bewaar als standaard*) elke nacht opnieuw.

**Twee begrippen** — *Top*: hoogste koers van de laatste X dagen (meebewegend venster). *Koopzone*: slotkoers staat
minstens de koopdrempel onder die top.

**Oordeel en Koopzone nu?** — twee aparte vragen:
- **Oordeel** = *is de werkwijze voor deze munt betrouwbaar?* Gebaseerd op de testvensters, vooral op **gerealiseerde** winst.
- **Koopzone nu?** = *zegt de regel vandaag koop?*
- Kandidaat om **nu** te kopen = 🛒 **én** 🟢.

**🧪 Testvensters** (bv. 3): per jaarvenster wordt de beste instelling gezocht op alle data vóór dat jaar en blind
toegepast op dat jaar (vers kapitaal).
- **Instellingen per venster** — bv. *−60/+50 · −65/+50 · −60/+75*.
- **Stabiel?** — blijft de gevonden instelling dicht bij elkaar? Instabiel = de exacte getallen zijn niet betrouwbaar.
- **Positieve vensters** — bv. *2 van 3*.
- **Gerealiseerd trades / % / %/jaar** — enkel afgeronde trades: echte winst.
- **Open nu %** — de laatste, nog open positie (papier).
- **Totaal %/jaar** — inclusief open positie. **Kopen&houden %/jaar** — ter vergelijking.

**Hoeveel bewijs?** — *Dagen data*, *Keren in zone* (afzonderlijke crashes), *Hersteld (keren)*, *Mediaan dagen*,
*Typ./Ergste verdere daling* (je stresstest).

**Hele historiek** (*Eindwaarde, %/jaar, Kopen&houden €, Laagste waarde, Open: …*) — met de instelling van vandaag
over het hele verleden. Die instelling is op dit verleden afgesteld: mooi, maar **geen verwachting**.

⚠️ **Survivorship bias**: munten die naar nul gingen zitten niet in de data. ⚠️ Verleden ≠ toekomst.
"""

DIP_EXAMPLES = """
### 1. Welke limieten kies ik: die van de test of die van vandaag?
Die van **vandaag** (kolommen *Koopdrempel / Winstdoel*, of in koers *Koop onder / Verkoop bij*). De testvensters
controleren de **werkwijze** "zoek de beste instelling op het verleden en gebruik ze daarna", niet één vast getal.
Voorbeeld TRAC: in 08/2025 koos de werkwijze −65% / +100% en dat werkte daarna (+486%). Vandaag kiest dezelfde
werkwijze −55% / +10%: dat zijn je orders. Springt de instelling zo sterk, dan krijg je **⚠️ instabiel**: de getallen
zijn dan minder betrouwbaar, zet er minder geld op.

### 2. Meerdere testvensters
Munt met 8 jaar data, referentie 365 dagen, 3 vensters (cijfers ter illustratie):

| Venster | Gezocht op | Blind getest op | Instelling | Resultaat |
|---|---|---|---|---|
| 1 | 2019–2023 | 2024 | −60% / +50% | +40% gerealiseerd (2 trades) |
| 2 | 2019–2024 | 2025 | −65% / +50% | −10% (positie open) |
| 3 | 2019–2025 | 2026 → vandaag | −60% / +75% | +60% gerealiseerd (3 trades) |
| **Vandaag** | 2019–nu | – | **−60% / +50%** | → jouw limieten |

Positief in 2 van 3, 5 gerealiseerde trades, instelling stabiel rond −60% / +50%. Meer bewijs dan één testperiode.

### 3. Gerealiseerd versus open
5.000 € in een venster: trade 1 → 9.950 €, trade 2 → 19.800 €, daarna opnieuw gekocht en die positie staat +48%.
- **Gerealiseerd** = 19.800 € (alsof de open positie aan haar aankoopprijs verkocht werd): +296%.
- **Totaal** = 19.800 € × 1,48 ≈ 29.300 €: +486%, waarvan een deel op papier.
- Het oordeel kijkt naar **gerealiseerd**. Een open positie in de plus is geen minpunt; een open positie dieper dan je
  limiet (standaard −20%) wel.

### 4. Hoe lang is de backtest en waar liggen de vensters?
- Backtest = data − referentie. 8 jaar (±2.925 dagen) − 364 = ±2.560 dagen (±7 jaar).
- 3 vensters = de laatste 3 jaar; het eerste venster heeft ±4 jaar training.
- Jonge munt (bv. 900 dagen data): backtest ±535 dagen → na minstens 365 dagen training blijft er één kort venster
  (±170 dagen) over. Korter dan 90 dagen → niet getest.

### 5. Weinig trades: normaal?
Ja. Met een diepe koopdrempel en een groot winstdoel (bv. −65% / +100%) zijn 1–2 trades per jaar al veel. Kleine
winstdoelen (+10%) geven meer rondes, maar elke ronde kost 2× fee.

### 6. Referentie hoogste punt
Munt piekte 6 maanden geleden op €100, staat nu op €40, koopdrempel −50%: referentie 365 → top €100 → −60% →
koopzone ✅. Referentie 90 → top bv. €55 → −27% → ❌.

### 7. Koop bij −85% van de top, verkoop bij +20%: wanneer koop je opnieuw?
Top 100 → koop als de slotkoers ≤ 15 (bv. aan 14) → verkoop aan 14 × 1,20 = 16,8 → pas opnieuw kopen als de koers
weer ≤ 15 zakt terwijl de top nog 100 is. Valt de piek uit het venster, dan zakt de top en het koopniveau mee.

### 8. Eindwaarde in de tabel ≠ in Detail
Detail start met dezelfde instelling als de tabelrij (één schijf). Voeg je schijven toe of wijzig je drempel/doel, dan
is het een andere strategie; onder *5. Resultaat* staat dan een ⚠️ vergelijking.
"""

VERDICT_RULES = """
Het oordeel kijkt naar de **🧪 testvensters** (blind getest) en vooral naar **gerealiseerde** winst. De drie drempels
stel je zelf in (⚙️ Instellingen → *Oordeel*); wijzigen herberekent niets. Eerste regel die klopt wint:

| Oordeel | Voorwaarden |
|---|---|
| ⚪ **Te weinig data** | Minder dagen data dan referentie + 60 |
| ⚪ **Niet getest** | Geen testvenster mogelijk (reden in *Waarom*) |
| ⚪ **Niets bewezen** | In de testvensters nooit gekocht |
| 🟢 **Interessant** | ≥ *min. trades* afgeronde trades **én** gerealiseerd ≥ *min. %/jaar* **én** instelling niet instabiel **én** minstens de helft van de vensters positief **én** open positie niet dieper dan *max. diepte* |
| 🟠 **Onder water** | Laatste positie dieper dan *max. diepte* **en** te weinig gerealiseerde winst of trades |
| 🔴 **Niet interessant** | Gerealiseerd verlies **en** ook inclusief open positie geen winst |
| 🟡 **Twijfel** | Al de rest: de reden(en) staan in *Waarom* |

**Sortering:** 🟢 → 🟡 → ⚪ → 🟠 → 🔴, binnen elk niveau op gerealiseerd %/jaar.

**Koopzone nu?** is een aparte kolom. Kandidaat om nu te kopen = 🛒 én 🟢. Een 🟢 die nog 👀 is, volg je op.
Een 🟢 blijft een historische aanwijzing, geen garantie.
"""

GENERAL = """
**Kosten.** Elke trade betaalt 2× fee (koop + verkoop). Bij Coinbase intro als maker = ±0,5% per cyclus,
als taker ±1% + spread. Kleine winststappen worden zo grotendeels opgegeten.

**Grid (kort).** Koopt bij elke daling van de grid-stap, verkoopt bij dezelfde stijging. Werkt in een zijwaartse
markt; in een dalende markt zit je vast met verlies.

**Dip-kopen (lang).** Koopt enkel als de munt diep onder haar top staat en wacht op het winstdoel.
Weinig trades, grote stappen → kosten wegen nauwelijks. Standaard met je hele bedrag in één schijf.
"""
