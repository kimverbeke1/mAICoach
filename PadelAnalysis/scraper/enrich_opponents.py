"""
enrich_opponents.py — zorgt dat TEGENSTANDERS volwaardige spelers worden.
Locatie: PadelAnalysis/scraper/enrich_opponents.py
(naast scrape_player.py / ci_scrape_all.py, zelfde path-setup patroon)
--------------------------------------------------------------------------
HET PROBLEEM DAT DIT OPLOST
--------------------------------------------------------------------------
Na het ophalen van een poule-schema toonde de tegenploeg-overzichtstabel voor
verschillende spelers (De Purcq Hilde, Brede Hilde, Severine, ...):
  - geen playing strength   ("voer bulk_fetch_padelstat_ratings.py uit")
  - geen klassement, geen klassementshistoriek
  - geen winrate historiek, geen vaste partner historiek
Dat lijken drie losse problemen, maar het is EEN oorzaak. In
opponent_dossier.build_player_summary() staat:
    doc = fb.get_player(player_id) or all_docs.get(str(player_id)) or {}
    matches = doc.get("matches", []) or []
Heeft een tegenstander GEEN eigen document in de players-collectie, dan is
matches leeg. Gevolg, in cascade: winrate/partners/vorm/periodes leeg,
klassement + historiek leeg, playing strength leeg (want
bulk_fetch_padelstat_ratings loopt over fb.search_player_profiles() en die
speler heeft geen profiel).
De poule-scrape haalt enkel FIXTURES en NAMEN op; ze maakt geen spelers aan.
Tegenstanders bestonden dus enkel als naam in een uitslagenblad.
--------------------------------------------------------------------------
WAT DIT BESTAND DOET
--------------------------------------------------------------------------
1. discover_opponent_players()  - vindt alle tegenstanders/partners die in de
   matchrecords van onze eigen spelers voorkomen maar nog GEEN eigen
   player_profiles-document hebben.
2. ensure_profiles()            - maakt voor die spelers een profiel aan.
3. run_padelstat_for_players()  - haalt de padelstats.be playing strength op
   (en, sinds 2026-09-20, optioneel meteen ook het officiële TVL-klassement -
   zie verderop).
4. run_klassement_for_players() - haalt de TVL-klassementshistoriek op.
--------------------------------------------------------------------------
PADEL_ANALYSIS_AUTO_KLASSEMENT_2026-09-16
--------------------------------------------------------------------------
run_klassement_for_players(), zelfde opbouw als de bestaande lokale flow in
opponent_scout_ui.py (scrape_klassement() + klassement_to_history_summary()
+ extract_niveau_winrates() uit scrape_klassement.py).
--------------------------------------------------------------------------
PADEL_ANALYSIS_INTERCLUB_ONLY_DISCOVERY_2026-09-16 ("worst case")
--------------------------------------------------------------------------
discover_opponent_players() heeft een interclub_only-parameter (standaard
True): enkel matches met match_type == "interclub" leveren kandidaten op,
zodat jarenlange tornooihistoriek geen honderden irrelevante ghost-profielen
genereert. run_padelstat_for_players() en run_klassement_for_players()
geven bovendien spelers MET bestaande matchdata voorrang boven ghosts (zie
_prioritize()) wanneer een *_MAX-limiet spelers moet laten wachten.
--------------------------------------------------------------------------
PADEL_ANALYSIS_GHOST_CLEANUP_TIMESTAMP_2026-09-16
--------------------------------------------------------------------------
ensure_profiles() zet een "discovered_at"-tijdstempel op elk NIEUW
aangemaakt profiel, gebruikt door cleanup_ghost_profiles.py om te
onderscheiden tussen een écht irrelevant profiel en een net ontdekte
speler die nog geen kans kreeg om verrijkt te worden.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): "het padelstat getal zal voortdurend wijzigen. moet dus
regelmatig geupdate worden. checken als dat werkt". Antwoord: het werkte
NIET. run_padelstat_for_players() sloeg elke speler met EENMAAL een
gecachete rating (fb.get_padelstat_rating(...).get("rating") is not None)
voor ALTIJD over, tenzij refresh=True werd gezet -- en dat gebeurde nergens
automatisch in de reguliere CI-run. Een speler kreeg dus zijn/haar
padelstat-waarde precies EEN keer, nooit meer bijgewerkt, terwijl
padelstats.be die waarde continu herberekent op basis van nieuwe resultaten.
Fix, twee onderdelen:
  1. save_padelstat_rating() wordt nog steeds ONGEWIJZIGD aangeroepen. Het
     bestaande veld dat het als tijdstempel zet, heet -- geverifieerd in de
     ACTUELE firebase_service.py -- "fetched_at" (NIET "scraped_at", zoals
     bij klassement_history; de twee functies gebruiken bewust/toevallig een
     andere naam). Dit gebruiken we als staleness-tijdstempel in plaats van
     een apart nieuw veld te introduceren.
  2. run_padelstat_for_players() beschouwt een speler nu als "te verversen"
     als OFWEL er nog geen rating is, OFWEL de bestaande rating ouder is dan
     PADELSTAT_STALE_AFTER_DAYS (standaard 14 dagen). refresh=True blijft
     bestaan als "forceer ALLES te herdoen, ongeacht leeftijd" (traag, enkel
     voor handmatig gebruik) -- de nieuwe standaardwerking (refresh=False)
     doet nu automatisch OOK de verouderde ratings, niet enkel de volledig
     ontbrekende. _prioritize() geeft binnen de te-verversen-lijst nog steeds
     voorrang aan spelers met matchdata boven ghost-profielen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): "ik heb dit profiel verversen gekozen bij Stijn Mortier. Ik
zie dat de scraper heel wat spelers aan het verversen is (en niet Stijn
Mortier wegens beperking in aantal). [...] ik zie nu weer een heleboel
nieuwe spelers in mijn spelerslijst."
ROOT CAUSE (bevestigd in code, geen aanname):
De knop "Scrape deze speler nu" (cloud_helpers.render_full_player_scrape_
button()) triggert scrape-padel.yml met player_ids=<EEN speler>. Op de
GitHub Actions-runner draait dat ci_scrape_all.py met PLAYER_IDS=<die ene
speler>. ci_scrape_all.py roept ONVOORWAARDELIJK run_enrichment(player_ids)
aan zodra ENABLE_ENRICH=true (standaard), ONGEACHT hoeveel spelers er
gevraagd werden. Dat doet twee dingen tegelijk, voor DIE ENE speler:
  1. discover_opponent_players() vindt AL Stijn's tegenstanders/partners
     zonder eigen profiel uit ZIJN EIGEN interclub-matchgeschiedenis en
     maakt daar nieuwe "ghost"-profielen voor aan (ensure_profiles()) --
     dit verklaart "een heleboel nieuwe spelers in mijn spelerslijst".
  2. run_klassement_for_players() heeft, in tegenstelling tot
     run_padelstat_for_players(), GEEN staleness-check: _has_klassement()
     kijkt enkel OF er een klassement_history-veld bestaat, niet hoe OUD of
     correct die is. Stijn had al EENMAAL een (foutieve, P100) klassement_
     history staan -> hij werd dus als "al gekend, niets te doen" behandeld
     en NOOIT opnieuw geprobeerd, terwijl de NIEUW ontdekte ghost-profielen
     (die nog niets hebben) wel in de wachtrij kwamen en het gedeelde budget
     (KLASSEMENT_MAX_PER_RUN=8) opsouperen. Vandaar exact "veel spelers
     verversen, Stijn niet, wegens een limiet".
FIX: nieuwe functie run_single_player_refresh(player_id) hieronder. Wordt
gebruikt door ci_scrape_all.py zodra er EXACT 1 speler werd aangevraagd
(zie daar): GEEN discovery, GEEN nieuwe ghost-profielen, en een
GEFORCEERDE refresh (refresh=True, cache/staleness volledig genegeerd) van
ENKEL padelstat + klassement voor DIE ENE speler. Dit garandeert dat een
gerichte "ververs deze speler"-actie ook effectief ENKEL die speler
ververst, zoals bedoeld.
--------------------------------------------------------------------------
PADEL_ANALYSIS_OPPONENT_CLUB_CAPTURE_2026-09-19 (op verzoek van Kim: "jij
moet de code aanpassen zodat je de club meegeeft als je begin te scrapen")
--------------------------------------------------------------------------
BUG/BEPERKING (opgelost, best-effort): discover_opponent_players() haalde
tot nu toe UITSLUITEND player_id + naam uit de matchrecords van onze eigen
spelers. ensure_profiles() ONDERSTEUNDE al een club-parameter (zie
signatuur hieronder), maar enrich() riep die NOOIT aan met een effectieve
club -- nieuw ontdekte tegenstander-profielen kregen dus altijd
club="(leeg)". Gevolg, bevestigd in run_padelstat_for_players(): daar wordt
exact dit veld gebruikt om padelstats.be te doorzoeken
(ps.search_and_fetch_padelstat_rating(naam, club=club or None)) -- ZONDER
club kan de zoekfunctie twee gelijknamige spelers (bv. "Kim Verbeke" bij
Padel Factory vs. bij Tennis en Padel Pollare, een reëel, al bevestigd
scenario) niet van elkaar onderscheiden en loopt het risico de VERKEERDE
speler op te slaan.
FIX: elk matchrecord bevat een "encounter"-veld met de vorm
"<Ploeg A> / <Ploeg B>" (bevestigd in een echt matchrecord, bv.
"PADEL 4U2 GENT A / Padel Factory A"). Omdat we het CLUB-veld van onze
EIGEN speler al kennen (player_profiles.club, ingevuld bij het aanmaken van
onze eigen spelers), kunnen we bepalen welke van de twee ploegnamen "onze"
kant is, en dus welke de kant van de tegenstander/partner is.
_derive_opponent_club_from_encounter() doet dit, INCLUSIEF het wegknippen
van een eventuele losse team-letter op het einde ("Padel Factory A" ->
"Padel Factory"), zodat het resultaat vergelijkbaar is met de ALL-CAPS
clubnamen die elders al in player_profiles.club staan (bv. "PADEL FACTORY").
Dit blijft een HEURISTIEK op basis van tekstvergelijking, geen exacte
koppeling met een clubregister: als de eigen clubnaam niet duidelijk in
een van beide ploegnamen terug te vinden is, wordt GEEN club gegokt (liever
"onbekend" dan een foutieve club opslaan). discover_opponent_players()
geeft daarom voortaan {player_id: {"name": ..., "club": ... of None}}
terug (i.p.v. enkel de naam) -- ensure_profiles(), enrich() en de
--dry-run-uitvoer hieronder zijn hierop aangepast.
--------------------------------------------------------------------------
PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19 (op verzoek van Kim, chat
2026-09-19: "weer veel profielen die aangemaakt worden :-( bekijk dat
grondig dat dat niet meer gebeurt")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd via een echte, door Kim aangeleverde log): een
gewone `python ci_scrape_all.py`-run op slechts 4 spelers creëerde 141
nieuwe "ghost"-profielen in 1 keer. Het log toonde exact waarom:
    [1694372] 16 periodes te scrapen: [..., 'Resultaten van week 01/2017
    tot en met week 52/2017']
scrape_player.py haalt (terecht, voor de EIGEN speler) de VOLLEDIGE
matchhistoriek op, tot 2017 terug (9 jaar). discover_opponent_players()
scande tot nu toe ECHTER ALLE matches van player_ids, ONGEACHT hoe oud -
elke tegenstander uit elke periode, ook een tornooi/interclubmatch van 8
jaar geleden, werd als "te ontdekken" beschouwd. Vandaar 141 nieuwe
profielen na het verversen van 4 spelers: hun VOLLEDIGE carrière aan
tegenstanders werd in 1 klap (opnieuw) ontdekt.
FIX (destijds): discover_opponent_players() beperkt zich sindsdien, PER
SPELER, tot de `recent_periods_only` MEEST RECENTE periodes (standaard 2).
Zie PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20 hieronder voor de
VERVOLG-fix: deze recency-limiet alleen bleek NIET voldoende.
--------------------------------------------------------------------------
PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20 (op verzoek van Kim,
chat 2026-09-20: "bij de run padel scraper nog steeds probleem dat teveel
profielen toegevoegd worden" - 279 nieuwe profielen na een run van 5
spelers met amper +1/+2/+2/+1/+0 nieuwe matches)
--------------------------------------------------------------------------
ROOT CAUSE VAN DE 2026-09-19-FIX (bevestigd): de aanname achter
recent_periods_only was dat een "periode" een kort, afgebakend tijdvak is.
In werkelijkheid omvat EEN period_label zoals "Resultaten van week 27/2026
tot en met week 48/2026" een VOLLEDIG interclubseizoen (22 weken).
DISCOVERY_RECENT_PERIODS=2 betekende dus in de praktijk "scan zowat het
volledige huidige EN vorige seizoen van elke speler" (in Kim's log: 261
interclubmatchrijen over 5 spelers), ongeacht hoeveel daarvan effectief
NIEUW waren t.o.v. de vorige run. Vandaar 279 nieuwe profielen uit amper 6
nieuwe matches.
FIX: discover_opponent_players() accepteert nu een nieuwe, optionele
parameter `new_matches_by_player` ({player_id: [matchrecord, ...]}, zie
scrape_player.scrape_player()["new_matches_this_run"] en
ci_scrape_all.run_match_scrapes()). Is dit meegegeven EN bevat het een
(mogelijk lege) lijst voor een speler, dan wordt UITSLUITEND die lijst
gescand voor tegenstanders/partners voor die speler - i.p.v. alle matches
binnen de N meest recente period_labels. Bij een gewone dagelijkse
ververs-run (meestal 0-8 nieuwe matches per speler) betekent dit dus een
minieme scan, met vrijwel geen nieuwe ghost-profielen tot gevolg - exact
het gedrag dat Kim verwacht.
BELANGRIJKE UITZONDERING (bewust behouden): bij de EERSTE-ooit-scrape van
een EIGEN speler is "new_matches_this_run" per definitie de VOLLEDIGE
historiek (er was nog niets in Firestore om tegen te vergelijken) - dat is
correct en gewenst (een nieuwe eigen speler MAG zijn/haar volledige
tegenstander-cirkel laten ontdekken). Om te vermijden dat DIE ene, legitieme
situatie alsnog honderden ghost-profielen uit 2017 e.d. oplevert, wordt de
recent_periods_only-filter (2026-09-19-fix) HIERBOVENOP toegepast op de
matches-bron (nieuw OF, bij ontbreken van new_matches_by_player, de volledige
historiek) - de twee fixes zijn dus AANVULLEND, niet elkaars vervanging.
Ontbreekt new_matches_by_player volledig (None - bv. handmatig CLI-gebruik
via --dry-run of --all), dan blijft het OUDE gedrag (scan de volledige
matches van de speler, met recency-cap) intact - geen regressie voor die
paden.
--------------------------------------------------------------------------
PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20 (op verzoek van
Kim: "aangezien we toch al het padelstat klassement scrapen van padelstat.be
zou ik willen voorstellen om het officieel klassement ook al meteen van
daar te scrapen. Dan moet die scraping van 2 keer per jaar niet meer
gebeuren aangezien padelstat toch regelmatig refresht.")
--------------------------------------------------------------------------
padelstats_scraper.search_and_fetch_padelstat_rating() haalde AL het
officiële TVL-klassement op (het "matched_klassement"-veld, uit de "P200 •
CLUB"-tekst van de zoekresultaatkaart) - enkel werd dat tot nu toe nergens
opgeslagen. run_padelstat_for_players() roept nu, ONMIDDELLIJK na een
geslaagde padelstat-ophaling, ALS de kaart een klassement bevatte,
fb.save_official_klassement_from_padelstat() aan (zie firebase_service.py
voor de volledige toelichting/upsert-logica). Dit betekent dat ELKE
reguliere padelstat-verversing (die toch al voor alle spelers draait)
meteen ook het officiële klassement actueel houdt, ZONDER extra
Playwright-sessie - de aparte, tragere TVL-klassement-scraper
(scrape_klassement.py / run_klassement_for_players()) is daardoor niet
langer nodig als REGULIERE bron; zie ci_scrape_all.py voor de gewijzigde
ENABLE_KLASSEMENT-default (nu False) en de aanbeveling om die TVL-scrape
voortaan enkel nog incidenteel/handmatig (bv. 2x/jaar, voor de volledige
historiek-grafiek) te draaien.
--------------------------------------------------------------------------
PADEL_ANALYSIS_SPLIT_RATING_KLASSEMENT_UPDATE_2026-09-20 (op verzoek van
Kim: "ik wil het officiele klassement updaten van padelstat.be maar niet
het playing strength klassement!")
--------------------------------------------------------------------------
BEPERKING (opgelost): run_padelstat_for_players() sloeg tot nu toe, bij elke
GESLAAGDE padelstats.be-ophaling, ALTIJD zowel de playing strength
(fb.save_padelstat_rating(...rating...)) ALS - indien aanwezig - het
officiële klassement (fb.save_official_klassement_from_padelstat(...)) op.
Er was geen manier om er één van de twee te verversen zonder de andere aan
te raken - terwijl Kim expliciet vroeg om enkel het officiële klassement te
kunnen bijwerken.
BELANGRIJK OM TE BEGRIJPEN: beide waarden komen uit DEZELFDE padelstats.be-
paginabezoek (1 Playwright-sessie, geen aparte scrape mogelijk of nodig per
waarde) - het onderscheid zit dus NIET in WAT er gescraped wordt, maar in
WAT er nadien OPGESLAGEN wordt. Er is dus geen performantieverlies aan het
apart kunnen aan-/uitzetten van elk van de twee.
FIX: twee nieuwe, losse parameters op run_padelstat_for_players() (en
doorgegeven via enrich()/run_single_player_refresh()):
  - update_playing_strength: bool = True  -> bepaalt of save_padelstat_
    rating(...rating...) gebeurt.
  - update_official_klassement: bool = True -> bepaalt of save_official_
    klassement_from_padelstat(...) gebeurt (indien de kaart een klassement
    bevatte).
Beide DEFAULT True (ongewijzigd gedrag als je niets expliciet aanpast).
Zet je update_playing_strength=False, dan wordt de playing-strength-cache
(padelstat_cache-document) NIET aangeraakt voor deze run, maar het
officiële klassement (indien gevonden) alsnog bijgewerkt, en vice versa.
Nieuwe CLI-vlaggen: --no-playing-strength-update / --no-official-
klassement-update (zie __main__ hieronder).
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLUB_REQUIRED_FOR_PADELSTAT_2026-09-20 (op verzoek van Kim:
"bij refresh padelstat.be: als ik dat run dan weet die niet welke club de
speler toe behoort. klopt dat. [...] Mocht je het toch niet weten, gelieve
dan playing strength leeg te laten en te vragen om bij de speler de ploeg
op te geven of zoiets?")
--------------------------------------------------------------------------
BUG/RISICO (opgelost): run_padelstat_for_players() riep tot nu toe ALTIJD
ps.search_and_fetch_padelstat_rating(naam, club=club or None) aan, OOK
wanneer club leeg/onbekend was (club="" -> club=None doorgegeven). Bij een
naam die op padelstats.be meerdere keren voorkomt (bevestigd, reëel
scenario: "Kim Verbeke" bij zowel Padel Factory als Tennis en Padel
Pollare) kan de zoekfunctie dan NIET betrouwbaar disambigueren, met het
risico de VERKEERDE gelijknamige speler op te slaan als playing strength/
klassement van ONZE speler.
Kim's punt klopt bovendien: een speler komt in deze lijst terecht OMDAT die
relevant is voor een specifieke ploeg-analyse (via discover_opponent_
players()'s club-afleiding uit het "encounter"-veld, zie PADEL_ANALYSIS_
OPPONENT_CLUB_CAPTURE_2026-09-19 hierboven) - de club HOORT dus normaal al
gekend te zijn. Ontbreekt ze toch (bv. een ouder profiel van vóór die fix,
of een encounter waaruit geen club kon worden afgeleid), dan is BLIND
zoeken zonder club te riskant.
FIX: is voor een speler geen club gekend, dan wordt deze speler NIET meer
opgezocht op padelstats.be (geen playing strength, geen klassement voor
deze run) - in plaats daarvan wordt de speler opgenomen in een nieuwe
"club_onbekend"-lijst in de teruggegeven samenvatting, met een duidelijke
log-regel die vraagt om de club/ploeg voor deze speler in te stellen. Dit
geldt ook voor priority_ids (bv. een expliciete "ververs deze speler"-
aanvraag): beter een duidelijke "club ontbreekt"-melding dan een stilzwijgend
risico op een foutieve match.
"""
from __future__ import annotations

import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# --- path setup: zelfde patroon als scrape_player.py ---
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

logger = logging.getLogger(__name__)

# Maximaal aantal padelstats-ophalingen per run (snelheidsbegrenzing).
PADELSTAT_MAX_PER_RUN = 25
# Beleefde pauze tussen padelstats-bezoeken.
PADELSTAT_PAUSE_SECONDS = 1.5
# PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16: na hoeveel dagen een
# bestaande padelstat-rating als "verouderd" geldt en dus automatisch
# opnieuw wordt opgehaald, ook zonder refresh=True.
PADELSTAT_STALE_AFTER_DAYS = 14
# Klassement kost een volledige Playwright-sessie per speler, dus een
# beduidend lagere limiet dan padelstat.
KLASSEMENT_MAX_PER_RUN = 8
KLASSEMENT_MAX_PERIODS = 10
KLASSEMENT_PAUSE_SECONDS = 2.0
# PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: standaard aantal MEEST
# RECENTE periodes (per speler) waarbinnen discover_opponent_players() nog
# tegenstanders/partners als "nieuw te ontdekken" beschouwt. 2 = huidige +
# vorige seizoensperiode (ruwweg het afgelopen jaar). 0 = onbeperkt (oud
# gedrag, enkel voor bewust, gericht gebruik). Zie ook
# PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20 in de module-
# docstring: dit blijft bestaan als AANVULLENDE cap, vooral relevant bij een
# eerste-keer-scrape (waar "nieuw" = volledige historiek).
DISCOVERY_RECENT_PERIODS_DEFAULT = 2


def _norm_id(value) -> str:
    """Maakt id's vergelijkbaar ongeacht int/float/str-opslag ('123', 123.0)."""
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        cleaned = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: periode-recentheid
# bepalen aan de hand van period_label, zonder Streamlit/pandas-afhankelijkheid
# (dit is een scraper-bestand — lichte, lokale herimplementatie van hetzelfde
# "week X/JJJJ"-patroon dat opponent_dossier._period_sort_key() elders al
# gebruikt voor UI-weergave).
# ---------------------------------------------------------------------------
_PERIOD_WEEK_YEAR_RE = re.compile(r"week\s+(\d{1,2})/(\d{4})", re.IGNORECASE)


def _period_recency_key(period_label) -> tuple:
    """Sorteersleutel voor period_label, RECENTSTE HOOGST. Herkent hetzelfde
    'Resultaten van week X/JJJJ tot en met week Y/JJJJ'-formaat als de rest
    van het project. Onbekend/leeg formaat krijgt de laagste sleutel (0, 0),
    zodat het nooit per ongeluk als 'recent' meetelt."""
    text = str(period_label or "")
    weeks = _PERIOD_WEEK_YEAR_RE.findall(text)
    if weeks:
        # Sorteer op de EINDgrens van de periode (laatste match in de tekst).
        week, year = weeks[-1]
        return (int(year), int(week))
    return (0, 0)


def _recent_periods_for_player(matches: list, recent_periods_only: int) -> Optional[set]:
    """PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: geeft de set van
    `recent_periods_only` MEEST RECENTE, distincte period_label-waarden
    terug uit de matches van 1 speler, of None als er geen beperking moet
    gelden (recent_periods_only <= 0 -- oud, onbeperkt gedrag)."""
    if not recent_periods_only or recent_periods_only <= 0:
        return None
    distinct_labels = {m.get("period_label") for m in matches if m.get("period_label")}
    if not distinct_labels:
        # Geen enkele period_label bekend (onverwacht, ouder matchformaat?)
        # -- conservatief NIETS uitfilteren i.p.v. per ongeluk alles weg te
        # gooien.
        return None
    ordered = sorted(distinct_labels, key=_period_recency_key, reverse=True)
    return set(ordered[:recent_periods_only])


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_OPPONENT_CLUB_CAPTURE_2026-09-19: club afleiden uit het
# "encounter"-veld van een matchrecord.
# ---------------------------------------------------------------------------
_TEAM_LETTER_SUFFIX_RE = re.compile(r"\s+[A-Za-z]$")


def _normalize_club_text(text: str) -> str:
    """Normaliseert een clubnaam/ploegnaam voor VERGELIJKING (niet voor
    opslag): hoofdletters, ingekort van een eventuele losse team-letter op
    het einde ("Padel Factory A" -> "PADEL FACTORY"), overtollige spaties
    weg. Enkel gebruikt om te bepalen welke ploeghelft bij "onze" club
    hoort -- de uiteindelijk OPGESLAGEN clubnaam behoudt zijn originele
    schrijfwijze uit het "encounter"-veld (zie _derive_opponent_club_from_
    encounter())."""
    cleaned = _TEAM_LETTER_SUFFIX_RE.sub("", (text or "").strip())
    return " ".join(cleaned.upper().split())


def _strip_team_letter_suffix(text: str) -> str:
    """Knipt enkel de losse team-letter aan het einde weg ("Padel Factory A"
    -> "Padel Factory"), voor de OP TE SLAAN clubnaam (dus zonder de rest
    naar hoofdletters om te zetten -- dat gebeurt enkel in
    _normalize_club_text() voor de vergelijking zelf)."""
    return _TEAM_LETTER_SUFFIX_RE.sub("", (text or "").strip()).strip()


def _derive_opponent_club_from_encounter(encounter: str, own_club: str) -> Optional[str]:
    """PADEL_ANALYSIS_OPPONENT_CLUB_CAPTURE_2026-09-19: bepaalt de club van
    de TEGENOVERGESTELDE kant in een "encounter"-veld (vorm "<Ploeg A> /
    <Ploeg B>", bv. "PADEL 4U2 GENT A / Padel Factory A"), op basis van de
    reeds GEKENDE club van onze eigen speler (own_club, uit diens
    player_profiles.club).

    Retourneert de tegenstander-clubnaam (team-letter weggeknipt, originele
    schrijfwijze behouden) ZODRA precies één van de twee ploeghelften
    (genormaliseerd: hoofdletters, team-letter weg) overeenkomt met de
    genormaliseerde own_club. In elk ander geval (own_club onbekend,
    "encounter" niet in de verwachte vorm, geen EENDUIDIGE match, of BEIDE
    helften lijken op own_club) wordt None teruggegeven -- bewust GEEN club
    gokken bij twijfel."""
    if not own_club or not encounter or "/" not in encounter:
        return None
    parts = [p.strip() for p in encounter.split("/")]
    if len(parts) != 2 or not all(parts):
        return None
    own_norm = _normalize_club_text(own_club)
    if not own_norm:
        return None
    normalized = [_normalize_club_text(p) for p in parts]
    matches = [i for i, n in enumerate(normalized) if n == own_norm]
    if len(matches) != 1:
        # 0 matches: own_club komt in geen van beide helften voor (kan bv.
        # gebeuren als de teamnaam anders geschreven is dan de clubnaam).
        # 2 matches: beide helften zien er (na normalisatie) identiek uit --
        # in beide gevallen te onzeker om een kant te kiezen.
        return None
    own_idx = matches[0]
    opponent_idx = 1 - own_idx
    return _strip_team_letter_suffix(parts[opponent_idx]) or None


def _own_club_for_owner(owner_player_id: str) -> str:
    """Haalt de GEKENDE club van onze EIGEN speler op (player_profiles.club),
    nodig als referentiepunt om in _derive_opponent_club_from_encounter() te
    bepalen welke ploeghelft van "encounter" de tegenstander-kant is."""
    try:
        profile = fb.get_player_profile(owner_player_id) or {}
    except Exception:  # noqa: BLE001
        profile = {}
    return (profile.get("club") or "").strip()


# ---------------------------------------------------------------------------
# 1. Tegenstanders ontdekken
# ---------------------------------------------------------------------------
def _known_profile_ids() -> set:
    try:
        profiles = fb.search_player_profiles("", limit=10_000)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[enrich] Kon bestaande profielen niet lezen: {e}")
        return set()
    return {_norm_id(p.get("player_id")) for p in profiles if p.get("player_id")}


def discover_opponent_players(
    player_ids: list,
    include_partners: bool = True,
    interclub_only: bool = True,
    recent_periods_only: int = DISCOVERY_RECENT_PERIODS_DEFAULT,
    new_matches_by_player: Optional[dict] = None,
) -> dict:
    """Vind spelers die in de matchen van `player_ids` voorkomen als
    tegenstander (of partner) maar nog geen eigen profiel hebben.

    PADEL_ANALYSIS_INTERCLUB_ONLY_DISCOVERY_2026-09-16: interclub_only=True
    (standaard) beperkt de scan tot match_type == "interclub".

    PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20 (op verzoek van
    Kim: "nog steeds probleem dat teveel profielen toegevoegd worden"):
    new_matches_by_player (optioneel, {player_id: [matchrecord, ...]}) is
    de BELANGRIJKSTE nieuwe parameter. Is dit meegegeven EN bevat het een
    entry voor een speler (ongeacht of die lijst leeg is), dan wordt
    UITSLUITEND die lijst - de matches die DEZE RUN effectief nieuw zijn -
    gescand voor die speler, in plaats van alle matches binnen de N meest
    recente period_labels. Dit is de directe fix voor "279 nieuwe profielen
    na amper 6 nieuwe matches": een period_label omvat vaak een heel
    seizoen, terwijl de effectieve delta per run meestal maar een handvol
    matches is. Zie de module-docstring voor de volledige toelichting.

    Ontbreekt een speler in new_matches_by_player (of is de parameter zelf
    None), dan valt deze functie voor die speler terug op het OUDE gedrag
    (volledige matches van de speler, met recent_periods_only-cap) - geen
    regressie voor aanroepers die dit (nog) niet meegeven (bv. CLI/--dry-run).

    PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: recent_periods_only
    (standaard 2) blijft ALS AANVULLENDE cap gelden op de gekozen matches-
    bron hierboven (nieuw, of - bij ontbreken daarvan - de volledige
    historiek) - dit vangt met name de eerste-keer-scrape van een eigen
    speler op, waar "nieuw" toevallig de volledige, jarenlange historiek is.

    PADEL_ANALYSIS_OPPONENT_CLUB_CAPTURE_2026-09-19: geeft nu, naast de
    naam, ook een BEST-EFFORT club mee per ontdekte speler. Belangrijk
    onderscheid, want opp1/opp2 en partner staan NIET aan dezelfde kant:
      - opp1/opp2 (de TEGENSTANDER) krijgen een club afgeleid uit het
        "encounter"-veld van het matchrecord (zie
        _derive_opponent_club_from_encounter()) -- is geen club af te
        leiden (own_club onbekend, "encounter" ontbreekt/onduidelijk), dan
        blijft "club" gewoon None (exact het vorige gedrag, geen regressie).
      - de PARTNER speelt in HETZELFDE team als de owner-speler (bv. Stijn
        Mortier is een eigen ploegmaat, geen tegenstander) en krijgt daarom
        gewoon de reeds GEKENDE eigen club (own_club) rechtstreeks, zonder
        afleiding uit "encounter" nodig te hebben.

    Returns {player_id: {"name": str, "club": Optional[str]}} voor de
    ONTBREKENDE spelers.
    """
    known = _known_profile_ids()
    found: dict[str, dict] = {}
    overgeslagen_tornooi = 0
    overgeslagen_oud = 0
    own_club_cache: dict[str, str] = {}
    for pid in player_ids:
        owner_key = _norm_id(pid)
        # PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20: kies de
        # matches-BRON voor deze speler. new_matches_by_player heeft
        # voorrang zodra er expliciet een entry voor deze speler in staat
        # (ook als die entry een LEGE lijst is - dat betekent bewust "niets
        # nieuws deze run, dus niets te ontdekken").
        if new_matches_by_player is not None and owner_key in new_matches_by_player:
            all_matches = new_matches_by_player.get(owner_key) or []
            source_label = "nieuwe matches deze run"
        else:
            try:
                doc = fb.get_player(pid) or {}
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[enrich] [{pid}] kon document niet lezen: {e}")
                continue
            all_matches = doc.get("matches", []) or []
            source_label = "volledige historiek (fallback)"
        if owner_key not in own_club_cache:
            own_club_cache[owner_key] = _own_club_for_owner(owner_key)
        own_club = own_club_cache[owner_key]
        # PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: bepaal, VOOR
        # deze speler, welke periodes nog "recent genoeg" zijn om
        # tegenstanders uit te ontdekken. None = geen beperking (oud gedrag,
        # recent_periods_only=0 of geen enkele period_label gekend). Blijft
        # gelden ALS AANVULLENDE cap, ook op een new_matches_by_player-bron
        # (relevant bij een eerste-keer-scrape, zie docstring hierboven).
        allowed_periods = _recent_periods_for_player(all_matches, recent_periods_only)
        for match in all_matches:
            if interclub_only and match.get("match_type") != "interclub":
                overgeslagen_tornooi += 1
                continue
            if allowed_periods is not None and match.get("period_label") not in allowed_periods:
                overgeslagen_oud += 1
                continue
            # PADEL_ANALYSIS_OPPONENT_CLUB_CAPTURE_2026-09-19: opp1/opp2
            # staan bij de TEGENSTANDER (club afgeleid uit "encounter"),
            # maar de partner speelt in HETZELFDE team als de owner (bv.
            # "Stijn Mortier is 1 van mijn ploegmembers", eerder al
            # bevestigd) -- die krijgt dus own_club rechtstreeks, NIET de
            # afgeleide tegenstander-club. Zonder dit onderscheid zou een
            # eigen ploegmaat foutief de tegenstander-club krijgen.
            opponent_club = _derive_opponent_club_from_encounter(
                match.get("encounter") or "", own_club
            )
            paren = [
                (match.get("opp1_user_id"), match.get("opp1_name"), opponent_club),
                (match.get("opp2_user_id"), match.get("opp2_name"), opponent_club),
            ]
            if include_partners:
                paren.append((match.get("partner_user_id"), match.get("partner_name"), own_club or None))
            for raw_id, naam, club in paren:
                other_id = _norm_id(raw_id)
                if not other_id or not other_id.isdigit():
                    continue
                if other_id in known or other_id in found:
                    continue
                naam = (naam or "").strip()
                if not naam:
                    continue
                found[other_id] = {"name": naam, "club": club}
    if interclub_only and overgeslagen_tornooi:
        logger.info(
            f"[enrich] {overgeslagen_tornooi} tornooi-matchrij(en) overgeslagen bij "
            "het ontdekken van tegenstanders (interclub_only=True)."
        )
    if recent_periods_only and overgeslagen_oud:
        logger.info(
            f"[enrich] {overgeslagen_oud} matchrij(en) uit oudere periodes overgeslagen bij het "
            f"ontdekken van tegenstanders (enkel de {recent_periods_only} meest recente periode(s) "
            "per speler worden meegenomen)."
        )
    return found


# ---------------------------------------------------------------------------
# 2. Profielen aanmaken
# ---------------------------------------------------------------------------
def ensure_profiles(players: dict, club: Optional[str] = None) -> list:
    """Maak player_profiles-documenten aan voor de ontdekte spelers.

    PADEL_ANALYSIS_OPPONENT_CLUB_CAPTURE_2026-09-19: `players` verwacht nu
    het formaat {player_id: {"name": str, "club": Optional[str]}}, zoals
    teruggegeven door discover_opponent_players(). Voor achterwaartse
    compatibiliteit (bv. een toekomstige aanroeper die enkel namen kent)
    wordt een waarde die GEEN dict is (dus een kale string) nog steeds als
    "enkel naam, geen club" behandeld.
    Het optionele `club`-argument blijft bestaan als EXPLICIETE override die
    voor ALLE meegegeven spelers dezelfde club forceert (bv. bij een
    toekomstige "importeer volledige tegenploeg"-functie) -- heeft voorrang
    op de per-speler afgeleide club uit `players`.

    PADEL_ANALYSIS_GHOST_CLEANUP_TIMESTAMP_2026-09-16: discovered_at wordt
    hier gezet, enkel bij eerste aanmaak.

    Returns de lijst van aangemaakte player_id's.
    """
    aangemaakt = []
    discovered_at = _utc_now_iso()
    for player_id, info in (players or {}).items():
        if isinstance(info, dict):
            naam = info.get("name") or ""
            per_speler_club = info.get("club")
        else:
            naam = info or ""
            per_speler_club = None
        effectieve_club = club or per_speler_club
        payload = {
            "player_id": str(player_id),
            "display_name": naam,
            "added_by": "auto_opponent_discovery",
            "discovered_at": discovered_at,
        }
        if effectieve_club:
            payload["club"] = effectieve_club
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
                payload, merge=True
            )
            aangemaakt.append(str(player_id))
            club_log = f", club={effectieve_club}" if effectieve_club else ""
            logger.info(f"[enrich] Profiel aangemaakt: {naam} ({player_id}{club_log})")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[enrich] Kon profiel {naam} ({player_id}) niet aanmaken: {e}")
    return aangemaakt


# ---------------------------------------------------------------------------
# Gedeelde prioriteringshelper
# ---------------------------------------------------------------------------
def _has_matchdata(player_id: str) -> bool:
    """True als deze speler minstens 1 match heeft in zijn/haar players-doc."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        return False
    return bool(doc.get("matches"))


def _prioritize(candidates: list) -> list:
    """Sorteert een lijst van (player_id, ...)-tupels zodat spelers MET
    matchdata vooraan komen. Stabiele sort."""
    return sorted(candidates, key=lambda item: 0 if _has_matchdata(item[0]) else 1)


# ---------------------------------------------------------------------------
# 3. Padelstats playing strength (+ optioneel officieel klassement) ophalen
# ---------------------------------------------------------------------------
def _padelstat_is_stale(cached: Optional[dict], stale_after_days: int) -> bool:
    """PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16.
    True als er GEEN gecachete rating is, OF de rating ouder is dan
    stale_after_days. Kan geen leeftijd bepaald worden (geen scraped_at-veld
    -- bv. een heel oude, van vóór deze fix), dan wordt die conservatief ook
    als 'stale' behandeld: beter een keer te veel verversen dan een blijvend
    verouderd getal tonen."""
    if not cached or cached.get("rating") is None:
        return True
    # BELANGRIJK: firebase_service.save_padelstat_rating() zet dit veld als
    # "fetched_at" (geverifieerd in de actuele firebase_service.py) -- NIET
    # "scraped_at" zoals bij klassement_history. Twee verschillende
    # velden voor eenzelfde soort tijdstempel, per functie.
    fetched_at = _parse_iso(cached.get("fetched_at"))
    if fetched_at is None:
        return True
    age = datetime.now(timezone.utc) - fetched_at
    return age > timedelta(days=stale_after_days)


def run_padelstat_for_players(
    player_ids: list,
    refresh: bool = False,
    max_players: int = PADELSTAT_MAX_PER_RUN,
    pause_seconds: float = PADELSTAT_PAUSE_SECONDS,
    stale_after_days: int = PADELSTAT_STALE_AFTER_DAYS,
    priority_ids: Optional[set] = None,
    update_playing_strength: bool = True,
    update_official_klassement: bool = True,
) -> dict:
    """Haal de padelstats.be playing strength (en/of het officiële
    klassement) op voor deze spelers.

    PADEL_ANALYSIS_PADELSTAT_STALENESS_2026-09-16: refresh=False (standaard)
    haalt nu OOK spelers op wier bestaande rating ouder is dan
    stale_after_days (zie _padelstat_is_stale()) -- niet enkel spelers die
    nog nooit een rating kregen. refresh=True negeert de cache volledig
    (forceert iedereen, traag, enkel voor handmatig gebruik).

    Bij overschrijding van max_players krijgen spelers MET bestaande
    matchdata voorrang (zie _prioritize()).

    PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19: priority_ids
    (optioneel) is een set van player_id's die ALTIJD in te_doen terecht-
    komen (cache/staleness-check genegeerd VOOR DEZE SPELERS) en die bij het
    afkappen op max_players ALTIJD als eerste behandeld worden - zo kan een
    expliciet aangevraagde speler nooit door een gedeeld run-budget verdrongen
    worden door pas ontdekte ghost-profielen.

    PADEL_ANALYSIS_SPLIT_RATING_KLASSEMENT_UPDATE_2026-09-20 (op verzoek van
    Kim: "ik wil het officiele klassement updaten van padelstat.be maar niet
    het playing strength klassement!"): update_playing_strength en
    update_official_klassement (beide standaard True) bepalen ONAFHANKELIJK
    van elkaar wat er, NA een geslaagde padelstats.be-ophaling, effectief
    OPGESLAGEN wordt. Beide waarden komen uit DEZELFDE paginabezoek (geen
    extra scrape-kost om beide te controleren) - het onderscheid zit dus
    enkel in wat je nadien wil BEWAREN. Zet je update_playing_strength=False
    dan blijft de bestaande playing-strength-cache ongewijzigd, ongeacht wat
    er gevonden werd; zet je update_official_klassement=False dan blijft
    klassement_history ongewijzigd (ook als de kaart een klassement toonde).

    PADEL_ANALYSIS_CLUB_REQUIRED_FOR_PADELSTAT_2026-09-20 (op verzoek van
    Kim: "als ik dat run dan weet die niet welke club de speler toe
    behoort [...] gelieve dan playing strength leeg te laten en te vragen
    om bij de speler de ploeg op te geven"): een speler ZONDER gekende club
    wordt NIET meer opgezocht op padelstats.be (te riskant bij gelijknamige
    spelers - zie module-docstring). Zulke spelers komen in de nieuwe
    "club_onbekend"-lijst in de teruggegeven samenvatting terecht, met een
    duidelijke log-regel die vraagt om de club/ploeg voor die speler in te
    stellen. Dit geldt ook voor priority_ids.

    Returns: {"opgehaald": n, "cache": n, "niet_gevonden": n, "fout": n,
    "overgeslagen_limiet": n, "klassement_opgehaald": n,
    "club_onbekend": [{"player_id": ..., "name": ...}, ...]}.
    """
    priority_ids = {_norm_id(p) for p in (priority_ids or set())}
    samenvatting = {
        "opgehaald": 0, "cache": 0, "niet_gevonden": 0, "fout": 0,
        "overgeslagen_limiet": 0, "klassement_opgehaald": 0, "club_onbekend": [],
    }
    try:
        import padelstats_scraper as ps
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[padelstat] padelstats_scraper niet beschikbaar ({e}) — stap overgeslagen."
        )
        return samenvatting
    try:
        alle_profielen = {
            _norm_id(p.get("player_id")): p
            for p in fb.search_player_profiles("", limit=10_000)
            if p.get("player_id")
        }
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[padelstat] Kon profielen niet lezen: {e}")
        return samenvatting
    te_doen = []
    for pid in player_ids:
        key = _norm_id(pid)
        profiel = alle_profielen.get(key)
        if not profiel or not profiel.get("display_name"):
            continue
        is_priority = key in priority_ids
        if not refresh and not is_priority:
            try:
                cached = fb.get_padelstat_rating(key)
            except Exception:  # noqa: BLE001
                cached = None
            if not _padelstat_is_stale(cached, stale_after_days):
                samenvatting["cache"] += 1
                continue
        te_doen.append((key, profiel))
    if not te_doen:
        logger.info("[padelstat] Iedereen heeft al een actuele playing strength — niets te doen.")
        return samenvatting
    # PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19: priority_ids eerst,
    # daarna de bestaande matchdata-voorrang, als stabiele sort (dus binnen
    # elke groep blijft de oorspronkelijke volgorde behouden).
    te_doen = sorted(
        _prioritize(te_doen),
        key=lambda item: 0 if item[0] in priority_ids else 1,
    )
    if max_players and len(te_doen) > max_players:
        samenvatting["overgeslagen_limiet"] = len(te_doen) - max_players
        logger.info(
            f"[padelstat] {len(te_doen)} speler(s) te doen (nieuw of ouder dan "
            f"{stale_after_days} dagen), limiet is {max_players}. De overige "
            f"{samenvatting['overgeslagen_limiet']} volgen in een volgende run "
            "(prioriteit-spelers en spelers met matchdata kregen voorrang op ghost-profielen)."
        )
        te_doen = te_doen[:max_players]
    totaal = len(te_doen)
    logger.info(f"[padelstat] Playing strength ophalen/verversen voor {totaal} speler(s)…")
    for i, (player_id, profiel) in enumerate(te_doen, start=1):
        naam = profiel.get("display_name") or ""
        club = profiel.get("club") or ""
        prefix = f"[padelstat] ({i}/{totaal}) {naam}"
        # PADEL_ANALYSIS_CLUB_REQUIRED_FOR_PADELSTAT_2026-09-20: GEEN club
        # gekend -> NIET opzoeken (te riskant bij gelijknamige spelers).
        if not club:
            samenvatting["club_onbekend"].append({"player_id": player_id, "name": naam})
            logger.warning(
                f"{prefix} -> club onbekend, NIET opgezocht op padelstats.be. "
                f"Stel de club/ploeg in voor deze speler en probeer opnieuw."
            )
            continue
        try:
            gevonden = ps.search_and_fetch_padelstat_rating(naam, club=club)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{prefix} -> FOUT: {e}")
            samenvatting["fout"] += 1
            continue
        if not gevonden or gevonden.get("rating") is None:
            logger.info(f"{prefix} -> niet gevonden op padelstats.be")
            samenvatting["niet_gevonden"] += 1
            time.sleep(pause_seconds)
            continue
        club_niet_bevestigd = bool(gevonden.get("club_disambiguation_note"))
        if update_playing_strength:
            try:
                fb.save_padelstat_rating(
                    player_id,
                    gevonden.get("padelstat_id", ""),
                    gevonden.get("rating"),
                    gevonden.get("rating_source", "none"),
                    gevonden.get("raw_text_snippet", ""),
                    matched_klassement=gevonden.get("matched_klassement"),
                    club_confirmed=not club_niet_bevestigd,
                )
                samenvatting["opgehaald"] += 1
                vlag = " ⚠️ club niet bevestigd" if club_niet_bevestigd else ""
                logger.info(f"{prefix} -> P{gevonden['rating']}{vlag}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{prefix} -> opslaan playing strength mislukt: {e}")
                samenvatting["fout"] += 1
                time.sleep(pause_seconds)
                continue
        else:
            logger.info(f"{prefix} -> playing strength NIET opgeslagen (update_playing_strength=False)")
        # PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20: de
        # zoekresultaatkaart geeft vaak OOK het officiële klassement mee
        # (bv. "P200" in "P200 • PADEL FACTORY") - sla dat, indien aanwezig
        # EN update_official_klassement=True, meteen op als "Huidig
        # klassement" (zie firebase_service.py voor de upsert-logica die de
        # eventuele TVL-historiek ongemoeid laat).
        matched_klassement = gevonden.get("matched_klassement")
        if update_official_klassement and matched_klassement is not None:
            try:
                fb.save_official_klassement_from_padelstat(
                    player_id, matched_klassement, club_confirmed=not club_niet_bevestigd,
                )
                samenvatting["klassement_opgehaald"] += 1
                logger.info(f"{prefix} -> officieel klassement P{matched_klassement} (via padelstats.be)")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{prefix} -> officieel klassement opslaan mislukt: {e}")
        elif matched_klassement is not None:
            logger.info(f"{prefix} -> officieel klassement NIET opgeslagen (update_official_klassement=False)")
        time.sleep(pause_seconds)
    if samenvatting["club_onbekend"]:
        namen = ", ".join(f"{p['name']} ({p['player_id']})" for p in samenvatting["club_onbekend"])
        logger.warning(
            f"[padelstat] {len(samenvatting['club_onbekend'])} speler(s) overgeslagen wegens "
            f"onbekende club: {namen}. Stel de club/ploeg in voor deze speler(s) om playing "
            "strength/klassement alsnog te kunnen ophalen."
        )
    return samenvatting


# ---------------------------------------------------------------------------
# 4. Klassementshistoriek ophalen (TVL, volledige periodes)
# ---------------------------------------------------------------------------
def _has_klassement(player_id: str) -> bool:
    """Zelfde controle als opponent_scout_ui._ensure_klassement(): kijkt op
    ZOWEL het players- als het player_profiles-document."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:  # noqa: BLE001
        doc = {}
    try:
        prof = fb.get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        prof = {}
    return bool(doc.get("klassement_history") or prof.get("klassement_history"))


def run_klassement_for_players(
    player_ids: list,
    refresh: bool = False,
    max_players: int = KLASSEMENT_MAX_PER_RUN,
    max_periods: int = KLASSEMENT_MAX_PERIODS,
    pause_seconds: float = KLASSEMENT_PAUSE_SECONDS,
    priority_ids: Optional[set] = None,
) -> dict:
    """Haalt de VOLLEDIGE TVL-klassementshistoriek (meerdere periodes) op
    voor deze spelers, met dezelfde scrape_klassement.py-functies en
    opslagvorm als de bestaande lokale flow.

    PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_VIA_PADELSTAT_2026-09-20: sinds
    run_padelstat_for_players() het officiële klassement al meelevert
    (snapshot, geen historiek), is deze functie niet langer de ENIGE bron
    voor "Huidig klassement" - zie ci_scrape_all.py voor de gewijzigde
    ENABLE_KLASSEMENT-default (nu False in reguliere runs). Deze functie
    blijft ongewijzigd bestaan en nuttig voor de volledige
    historiek-grafiek (meerdere periodes), die padelstat NIET kan leveren -
    gebruik hem incidenteel/handmatig (bv. 2x/jaar, of via
    KLASSEMENT_REFRESH/ENABLE_KLASSEMENT=true op een bewust getriggerde run).

    LET OP (PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19): deze
    functie heeft, in tegenstelling tot run_padelstat_for_players(), GEEN
    staleness-check — _has_klassement() kijkt enkel OF er een klassement_
    history bestaat, niet hoe oud/correct die is. De priority_ids-parameter
    lost dit gericht op: voor die spelers wordt _has_klassement() genegeerd
    (altijd opnieuw ophalen) en krijgen ze voorrang bij het afkappen op
    max_players.

    Returns: {"opgehaald": n, "cache": n, "fout": n, "overgeslagen_limiet": n}.
    """
    priority_ids = {_norm_id(p) for p in (priority_ids or set())}
    samenvatting = {"opgehaald": 0, "cache": 0, "fout": 0, "overgeslagen_limiet": 0}
    try:
        from scrape_klassement import (
            scrape_klassement,
            klassement_to_history_summary,
            extract_niveau_winrates,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[klassement] scrape_klassement niet beschikbaar ({e}) — stap overgeslagen."
        )
        return samenvatting
    te_doen = []
    for pid in player_ids:
        key = _norm_id(pid)
        is_priority = key in priority_ids
        if not refresh and not is_priority and _has_klassement(key):
            samenvatting["cache"] += 1
            continue
        te_doen.append((key,))
    if not te_doen:
        logger.info("[klassement] Iedereen heeft al klassementshistoriek — niets te doen.")
        return samenvatting
    te_doen = _prioritize(te_doen)
    te_doen = [key for (key,) in te_doen]
    # PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19: priority_ids altijd
    # vooraan, ongeacht matchdata-voorrang, zodat ze nooit door het
    # max_players-budget verdrongen worden.
    te_doen = sorted(te_doen, key=lambda pid: 0 if pid in priority_ids else 1)
    if max_players and len(te_doen) > max_players:
        samenvatting["overgeslagen_limiet"] = len(te_doen) - max_players
        logger.info(
            f"[klassement] {len(te_doen)} speler(s) te doen, limiet is {max_players}. "
            f"De overige {samenvatting['overgeslagen_limiet']} volgen in een volgende run."
        )
        te_doen = te_doen[:max_players]
    totaal = len(te_doen)
    logger.info(f"[klassement] Klassementshistoriek ophalen voor {totaal} speler(s)…")
    for i, pid in enumerate(te_doen, start=1):
        prefix = f"[klassement] ({i}/{totaal}) speler {pid}"
        try:
            periods = scrape_klassement(pid, max_periods=max_periods, headless=True)
            history = klassement_to_history_summary(periods)
            niveau_winrates = extract_niveau_winrates(periods)
            klass_data = {
                "history": history,
                "niveau_winrates": niveau_winrates,
                "raw_periods": periods,
                "scraped_at": _utc_now_iso(),
            }
            payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(
                payload, merge=True
            )
            fb.db.collection(fb.PLAYERS_COLLECTION).document(str(pid)).set(
                payload, merge=True
            )
            samenvatting["opgehaald"] += 1
            huidig = history[0].get("klassement") if history else None
            logger.info(f"{prefix} -> {huidig or '?'} ({len(history)} periode(s))")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{prefix} -> FOUT: {e}")
            samenvatting["fout"] += 1
        if i < totaal:
            time.sleep(pause_seconds)
    return samenvatting


# ---------------------------------------------------------------------------
# Gecombineerde stap (wordt door ci_scrape_all.py aangeroepen)
# ---------------------------------------------------------------------------
def enrich(
    player_ids: list,
    do_discover: bool = True,
    do_padelstat: bool = True,
    padelstat_refresh: bool = False,
    padelstat_max: int = PADELSTAT_MAX_PER_RUN,
    padelstat_stale_after_days: int = PADELSTAT_STALE_AFTER_DAYS,
    update_playing_strength: bool = True,
    update_official_klassement: bool = True,
    do_klassement: bool = True,
    klassement_refresh: bool = False,
    klassement_max: int = KLASSEMENT_MAX_PER_RUN,
    interclub_only: bool = True,
    priority_ids: Optional[set] = None,
    discovery_recent_periods: int = DISCOVERY_RECENT_PERIODS_DEFAULT,
    new_matches_by_player: Optional[dict] = None,
) -> dict:
    """Volledige verrijkingsstap: tegenstanders ontdekken + profielen aanmaken
    + padelstats (optioneel incl. officieel klassement) ophalen/verversen +
    optioneel de volledige TVL-klassementshistoriek ophalen.

    priority_ids (optioneel, standaard None = ONGEWIJZIGD bulk-gedrag): een
    set van player_id's die, indien meegegeven, ALTIJD geforceerd ververst
    worden (cache/staleness genegeerd voor DIE spelers) en nooit door
    nieuw ontdekte ghost-profielen verdrongen worden bij het afkappen op
    *_max. Wordt NIET automatisch afgeleid van `player_ids` — bij een
    normale bulk-aanroep (bv. de dagelijkse cron met honderden spelers)
    blijft de bestaande cache/staleness-logica dus voor IEDEREEN gewoon
    gelden, precies zoals voorheen. Enkel run_single_player_refresh()
    hieronder geeft hier bewust EEN speler-id aan mee.

    PADEL_ANALYSIS_SPLIT_RATING_KLASSEMENT_UPDATE_2026-09-20:
    update_playing_strength/update_official_klassement worden rechtstreeks
    doorgegeven aan run_padelstat_for_players() - zie daar voor de volledige
    toelichting.

    PADEL_ANALYSIS_NEW_MATCHES_ONLY_DISCOVERY_2026-09-20: new_matches_by_
    player wordt rechtstreeks doorgegeven aan discover_opponent_players() -
    zie de module-docstring en discover_opponent_players() zelf voor de
    volledige toelichting bij het "279 nieuwe profielen na 6 nieuwe
    matches"-probleem dat dit oplost.

    Returns {"nieuwe_profielen": [...], "padelstat": {...}, "klassement": {...}}.
    """
    resultaat: dict = {"nieuwe_profielen": [], "padelstat": {}, "klassement": {}}
    if do_discover:
        ontbrekend = discover_opponent_players(
            player_ids, interclub_only=interclub_only,
            recent_periods_only=discovery_recent_periods,
            new_matches_by_player=new_matches_by_player,
        )
        if ontbrekend:
            met_club = sum(1 for info in ontbrekend.values() if info.get("club"))
            logger.info(
                f"[enrich] {len(ontbrekend)} tegenstander(s)/partner(s) zonder profiel gevonden "
                f"(interclub_only={interclub_only}, recent_periods_only={discovery_recent_periods}, "
                f"new_matches_by_player={'ja' if new_matches_by_player is not None else 'nee'}), "
                f"waarvan {met_club} met een afgeleide club."
            )
            resultaat["nieuwe_profielen"] = ensure_profiles(ontbrekend)
        else:
            logger.info("[enrich] Geen (nieuwe, recente) tegenstanders zonder profiel gevonden.")
    doelgroep = list(dict.fromkeys(
        [str(p) for p in player_ids] + resultaat["nieuwe_profielen"]
    ))
    if do_padelstat:
        resultaat["padelstat"] = run_padelstat_for_players(
            doelgroep, refresh=padelstat_refresh, max_players=padelstat_max,
            stale_after_days=padelstat_stale_after_days, priority_ids=priority_ids,
            update_playing_strength=update_playing_strength,
            update_official_klassement=update_official_klassement,
        )
    if do_klassement:
        resultaat["klassement"] = run_klassement_for_players(
            doelgroep, refresh=klassement_refresh, max_players=klassement_max,
            priority_ids=priority_ids,
        )
    return resultaat


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19
# ---------------------------------------------------------------------------
def run_single_player_refresh(
    player_id: str,
    refresh_padelstat: bool = True,
    refresh_klassement: bool = True,
    update_playing_strength: bool = True,
    update_official_klassement: bool = True,
) -> dict:
    """Ververst ALLEEN padelstat (optioneel incl. officieel klassement) +
    optioneel de volledige TVL-klassementshistoriek voor DEZE ENE speler, met
    refresh=True (cache/staleness volledig genegeerd, dus GEGARANDEERD een
    poging), en ZONDER enige discovery of nieuwe ghost-profielen aan te
    maken voor tegenstanders/partners.

    Gebruikt door ci_scrape_all.py wanneer er via de workflow-input
    (PLAYER_IDS) EXACT 1 speler werd aangevraagd (bv. de "Scrape deze
    speler nu"-knop) — dit is precies wat Kim vroeg: "bedoeling is dat
    enkel die speler ververst wordt (id speler meegeven)".

    PADEL_ANALYSIS_SPLIT_RATING_KLASSEMENT_UPDATE_2026-09-20:
    update_playing_strength/update_official_klassement worden doorgegeven
    aan run_padelstat_for_players() - zie daar voor de volledige toelichting.
    LET OP (PADEL_ANALYSIS_CLUB_REQUIRED_FOR_PADELSTAT_2026-09-20): ontbreekt
    de club van deze ene speler, dan wordt ook deze GERICHTE aanvraag
    overgeslagen (zie run_padelstat_for_players() - geldt ook voor
    priority_ids) - het resultaat-dict toont dit via "club_onbekend".

    Returns {"padelstat": {...}, "klassement": {...}} (zelfde vorm als de
    individuele run_*_for_players()-functies, met max_players=1)."""
    resultaat = {"padelstat": {}, "klassement": {}}
    key = _norm_id(player_id)
    if not key:
        logger.warning("[single-player] Geen geldige player_id meegegeven — niets gedaan.")
        return resultaat
    logger.info(f"[single-player] Losse-speler-verversing voor {key} — GEEN discovery, GEEN nieuwe profielen.")
    if refresh_padelstat:
        resultaat["padelstat"] = run_padelstat_for_players(
            [key], refresh=True, max_players=1, priority_ids={key},
            update_playing_strength=update_playing_strength,
            update_official_klassement=update_official_klassement,
        )
    if refresh_klassement:
        resultaat["klassement"] = run_klassement_for_players(
            [key], refresh=True, max_players=1, priority_ids={key},
        )
    return resultaat


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(
        description="Tegenstanders als speler aanmaken + padelstats/klassement ophalen."
    )
    parser.add_argument("player_ids", nargs="*", help="Eigen spelers om vanuit te vertrekken.")
    parser.add_argument("--all", action="store_true", help="Vertrek van ALLE gekende profielen.")
    parser.add_argument("--no-discover", action="store_true", help="Geen nieuwe profielen aanmaken.")
    parser.add_argument("--no-padelstat", action="store_true", help="Geen padelstats.be bezoeken (geen playing strength, geen officieel klassement via padelstat).")
    parser.add_argument("--no-klassement", action="store_true", help="Geen volledige TVL-klassementshistoriek ophalen.")
    # PADEL_ANALYSIS_SPLIT_RATING_KLASSEMENT_UPDATE_2026-09-20: losse
    # vlaggen om, BINNEN een padelstats.be-bezoek, één van beide waarden
    # niet op te slaan (zie run_padelstat_for_players()).
    parser.add_argument("--no-playing-strength-update", action="store_true",
                        help="Bezoek padelstats.be wel, maar sla de playing strength (rating) NIET op - enkel het officiële klassement (indien --no-official-klassement-update niet ook gezet is).")
    parser.add_argument("--no-official-klassement-update", action="store_true",
                        help="Bezoek padelstats.be wel, maar sla het officiële klassement NIET op - enkel de playing strength (indien --no-playing-strength-update niet ook gezet is).")
    parser.add_argument("--include-tournament", action="store_true",
                        help="Ontdek OOK tornooi-tegenstanders (standaard: enkel interclub).")
    parser.add_argument("--refresh", action="store_true", help="Negeer zowel de padelstats- als klassement-cache VOLLEDIG (forceer iedereen, traag).")
    parser.add_argument("--single-player", action="store_true",
                        help="PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19: ververs ENKEL de opgegeven speler (eerste positional arg), zonder discovery/nieuwe profielen.")
    parser.add_argument("--max", type=int, default=PADELSTAT_MAX_PER_RUN,
                        help=f"Max padelstats-ophalingen deze run (standaard {PADELSTAT_MAX_PER_RUN}).")
    parser.add_argument("--padelstat-stale-days", type=int, default=PADELSTAT_STALE_AFTER_DAYS,
                        help=f"Ververs padelstat automatisch na dit aantal dagen (standaard {PADELSTAT_STALE_AFTER_DAYS}).")
    parser.add_argument("--klassement-max", type=int, default=KLASSEMENT_MAX_PER_RUN,
                        help=f"Max klassement-ophalingen deze run (standaard {KLASSEMENT_MAX_PER_RUN}).")
    # PADEL_ANALYSIS_DISCOVERY_RECENCY_LIMIT_2026-09-19: nieuw CLI-argument,
    # zie module-docstring voor de volledige toelichting.
    parser.add_argument(
        "--discovery-recent-periods", type=int, default=DISCOVERY_RECENT_PERIODS_DEFAULT,
        help=(
            f"Beperk het ontdekken van nieuwe tegenstanders tot de N meest recente periodes per "
            f"speler (standaard {DISCOVERY_RECENT_PERIODS_DEFAULT}), als aanvullende cap op de "
            "new-matches-only-discovery. Zet op 0 voor het oude, onbeperkte gedrag."
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon enkel welke spelers zouden worden aangemaakt.")
    args = parser.parse_args()

    if args.single_player:
        if not args.player_ids:
            print("Geef exact 1 speler mee als positional argument bij --single-player.")
            sys.exit(1)
        res = run_single_player_refresh(
            args.player_ids[0],
            update_playing_strength=not args.no_playing_strength_update,
            update_official_klassement=not args.no_official_klassement_update,
        )
        print("\n=== Samenvatting (losse-speler-verversing) ===")
        print(f"Padelstat  : {res['padelstat']}")
        print(f"Klassement : {res['klassement']}")
        if res["padelstat"].get("club_onbekend"):
            print(
                f"\nLet op: club onbekend voor deze speler — playing strength/klassement NIET "
                "opgehaald. Stel eerst de club/ploeg in en probeer opnieuw."
            )
        sys.exit(0)

    if args.all or not args.player_ids:
        ids = [
            str(p.get("player_id"))
            for p in fb.search_player_profiles("", limit=10_000)
            if p.get("player_id")
        ]
        print(f"Vertrek van alle {len(ids)} gekende profielen.")
    else:
        ids = args.player_ids

    if args.dry_run:
        # CLI/--dry-run geeft bewust GEEN new_matches_by_player mee (die
        # bron bestaat enkel binnen eenzelfde ci_scrape_all.py-run) - dit
        # pad gebruikt dus altijd de oude, volledige-historiek-scan met
        # recency-cap, zoals voorheen.
        ontbrekend = discover_opponent_players(
            ids, interclub_only=not args.include_tournament,
            recent_periods_only=args.discovery_recent_periods,
        )
        print(f"\n{len(ontbrekend)} speler(s) zonder profiel (recent_periods_only={args.discovery_recent_periods}):\n")
        for pid, info in sorted(ontbrekend.items(), key=lambda kv: kv[1].get("name") or ""):
            club_txt = info.get("club") or "-"
            print(f"  {pid:<12} {info.get('name') or '':<30} club={club_txt}")
        sys.exit(0)

    res = enrich(
        ids,
        do_discover=not args.no_discover,
        do_padelstat=not args.no_padelstat,
        padelstat_refresh=args.refresh,
        padelstat_max=args.max,
        padelstat_stale_after_days=args.padelstat_stale_days,
        update_playing_strength=not args.no_playing_strength_update,
        update_official_klassement=not args.no_official_klassement_update,
        do_klassement=not args.no_klassement,
        klassement_refresh=args.refresh,
        klassement_max=args.klassement_max,
        interclub_only=not args.include_tournament,
        discovery_recent_periods=args.discovery_recent_periods,
    )
    print("\n=== Samenvatting ===")
    print(f"Nieuwe profielen : {len(res['nieuwe_profielen'])}")
    if res["padelstat"]:
        p = res["padelstat"]
        print(
            f"Padelstats       : {p.get('opgehaald', 0)} opgehaald/ververst, "
            f"{p.get('cache', 0)} nog actueel, {p.get('niet_gevonden', 0)} niet gevonden, "
            f"{p.get('fout', 0)} fout, waarvan {p.get('klassement_opgehaald', 0)} met officieel "
            "klassement meegenomen"
        )
        if p.get("overgeslagen_limiet"):
            print(f"                   {p['overgeslagen_limiet']} wachten op een volgende run")
        if p.get("club_onbekend"):
            namen = ", ".join(f"{x['name']} ({x['player_id']})" for x in p["club_onbekend"])
            print(f"                   {len(p['club_onbekend'])} overgeslagen wegens onbekende club: {namen}")
    if res["klassement"]:
        k = res["klassement"]
        print(
            f"Klassement (TVL) : {k.get('opgehaald', 0)} opgehaald, "
            f"{k.get('cache', 0)} uit cache, {k.get('fout', 0)} fout"
        )
        if k.get("overgeslagen_limiet"):
            print(f"                   {k['overgeslagen_limiet']} wachten op een volgende run")
    if res["nieuwe_profielen"]:
        print(
            f"\nLet op: de {len(res['nieuwe_profielen'])} nieuwe speler(s) hebben nog geen "
            "matchdata. Draai nu ci_scrape_all.py (MODE=new_users) om die op te halen."
        )
