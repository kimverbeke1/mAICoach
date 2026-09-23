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
3. run_padelstat_for_players()  - haalt de padelstats.be playing strength op.
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
PADEL_ANALYSIS_DISCOVERY_HARD_GUARD_2026-09-23 (definitieve oplossing)
--------------------------------------------------------------------------
WAT ER TWEE KEER GEBEURDE: een run die enkel het KLASSEMENT van de BESTAANDE
spelers moest herstellen -

    python enrich_opponents.py --all --no-padelstat --refresh --klassement-max 50

- maakte ~1468 NIEUWE spelersprofielen aan.

WAAROM HET ZICH HERHAALDE, en dat is het belangrijkste inzicht: de eerste
fix bestond enkel uit het omdraaien van een DEFAULT (do_discover=False) en
een CLI-vlag. Die aanpak heeft twee zwaktes. Ze werkt niet als het bestand
niet gedeployed raakt (precies wat er gebeurde - aan de logoutput was dat
niet te zien), en ze pakt de ONDERLIGGENDE oorzaak niet aan: dat "--all"
veel te breed is.

DE ECHTE OORZAAK: "--all" vertrekt van ALLE gekende profielen. Maar een
groot deel daarvan zijn zelf al eerder ONTDEKTE TEGENSTANDERS. Hun
matchgeschiedenis bevat hun eigen tegenstanders - mensen die met jouw ploeg
niets te maken hebben. Discovery vanuit die profielen levert dus
tegenstanders-VAN-tegenstanders op, en dat groeit exponentieel: 38
vertrekpunten leverden 1468 profielen op.

VIER ONAFHANKELIJKE MAATREGELEN, zodat het nooit meer van 1 default afhangt:

  1. SCOPE (de kern, _filter_direct_seeds()): discovery vertrekt NOOIT nog
     vanuit een profiel dat zelf automatisch ontdekt is. Enkel jouw eigen,
     handmatig toegevoegde spelers dienen als vertrekpunt. Gevonden spelers
     zijn dan per definitie RECHTSTREEKSE tegenstanders. Deze filter zit in
     het pad zelf en is niet met een vlag te omzeilen.
  2. OPT-IN: enrich(do_discover=...) staat standaard op False en de CLI
     vraagt een expliciete "--discover".
  3. TWEEDE POORT: ensure_profiles() maakt enkel iets aan met een expliciete
     allow_create=True - ook als er ergens nog oude code draait.
  4. HARDE LIMIET: meer dan MAX_NEW_PROFILES_PER_RUN (40) nieuwe profielen
     in 1 run annuleert de VOLLEDIGE aanmaak, i.p.v. ze half uit te voeren.

Bovendien logt het script nu bij elke start zijn ENRICH_VERSION, zodat
meteen zichtbaar is welke versie draait - het ontbreken daarvan maakte de
vorige twee keer onnodig moeilijk te diagnosticeren.

OPRUIMEN: cleanup_discovered_profiles.py (naast dit bestand), dry-run by
default, filtert op added_by="auto_opponent_discovery" + discovered_at.

--------------------------------------------------------------------------
PADEL_ANALYSIS_DISCOVERY_CLUB_2026-09-23
--------------------------------------------------------------------------
Dezelfde run verklaarde ook de clubloze profielen: enrich() gaf de `club`
nooit door aan ensure_profiles(). Een speler zonder club wordt sinds
PADEL_ANALYSIS_CLUB_REQUIRED_TO_SCRAPE_2026-09-20 nooit automatisch
ververst, dus die profielen bleven permanent leeg. Zie ensure_profiles().
"""
from __future__ import annotations

import logging
import os
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


# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_DISCOVERY_HARD_GUARD_2026-09-23
# ---------------------------------------------------------------------------
# Versiestempel. Wordt bij ELKE run als eerste regel gelogd, zodat je in de
# output meteen ziet WELKE versie van dit bestand effectief draait. Reden:
# de discovery-fix van eerder vandaag bleek twee keer niet gedeployed, en dat
# was aan de logoutput niet te zien - je zag enkel opnieuw 1468 profielen
# verschijnen zonder enig spoor van de nieuwe code.
ENRICH_VERSION = "2026-09-23-hard-guard"

# Harde bovengrens op het aantal NIEUWE profielen dat een enkele run mag
# aanmaken. Wordt die overschreden, dan stopt de run ZONDER iets aan te maken
# (zie ensure_profiles()). Dit is een vangnet los van alle vlaggen: zelfs als
# discovery per ongeluk toch aan staat, kan een run nooit meer honderden
# profielen aanmaken voor je het doorhebt. Bewust laag: legitieme discovery
# via team-analyse gaat over 1 tegenstanderploeg, dus ~4-12 spelers.
MAX_NEW_PROFILES_PER_RUN = 40


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
# 1. Tegenstanders ontdekken
# ---------------------------------------------------------------------------
def _known_profile_ids() -> set:
    try:
        profiles = fb.search_player_profiles("", limit=10_000)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[enrich] Kon bestaande profielen niet lezen: {e}")
        return set()
    return {_norm_id(p.get("player_id")) for p in profiles if p.get("player_id")}


def _is_auto_discovered(player_id: str) -> bool:
    """True als dit profiel zelf ooit automatisch ontdekt is."""
    try:
        prof = fb.get_player_profile(player_id) or {}
    except Exception:  # noqa: BLE001
        return False
    return str(prof.get("added_by") or "") == "auto_opponent_discovery"


def _filter_direct_seeds(player_ids: list) -> list:
    """PADEL_ANALYSIS_DIRECT_OPPONENTS_ONLY_2026-09-23 (op verzoek van Kim:
    "De bedoeling is om enkel maar de rechtstreekse tegenstander als profiel
    te hebben en geen tegenstanders van tegenstanders").

    DIT IS DE KERN VAN HET PROBLEEM, en waarom het zich telkens herhaalde:
    "--all" vertrekt van ALLE gekende profielen. Maar een groot deel daarvan
    zijn zelf al eerder ONTDEKTE TEGENSTANDERS. Hun matchgeschiedenis bevat
    dus hun eigen tegenstanders - mensen die met jouw ploeg niets te maken
    hebben. Discovery vanuit die profielen levert per definitie
    tegenstanders-van-tegenstanders op, en dat groeit exponentieel: 38
    profielen leverden er zo 1468 op.

    De structurele regel is daarom: NOOIT vertrekken vanuit een profiel dat
    zelf automatisch ontdekt is. Enkel spelers die JIJ hebt toegevoegd (of
    die via team-analyse bewust zijn opgenomen) mogen als vertrekpunt
    dienen. Dan zijn de gevonden spelers per definitie RECHTSTREEKSE
    tegenstanders van jouw eigen spelers - precies wat je wil.

    Deze filter werkt ongeacht welke vlaggen er meegegeven worden; hij zit
    in het pad zelf en is dus niet per ongeluk te omzeilen.
    """
    direct, afgeleid = [], []
    for pid in player_ids:
        (afgeleid if _is_auto_discovered(str(pid)) else direct).append(str(pid))
    if afgeleid:
        logger.info(
            f"[enrich] {len(afgeleid)} vertrekpunt(en) overgeslagen omdat het zelf automatisch "
            "ontdekte tegenstanders zijn - discovery vanuit die profielen zou tegenstanders-"
            "VAN-tegenstanders opleveren (PADEL_ANALYSIS_DIRECT_OPPONENTS_ONLY_2026-09-23). "
            f"Er wordt vertrokken van {len(direct)} eigen/handmatig toegevoegde speler(s)."
        )
    return direct


def discover_opponent_players(
    player_ids: list,
    include_partners: bool = True,
    interclub_only: bool = True,
    direct_only: bool = True,
) -> dict:
    """Vind spelers die in de matchen van `player_ids` voorkomen als
    tegenstander (of partner) maar nog geen eigen profiel hebben.

    PADEL_ANALYSIS_INTERCLUB_ONLY_DISCOVERY_2026-09-16: interclub_only=True
    (standaard) beperkt de scan tot match_type == "interclub".

    PADEL_ANALYSIS_DIRECT_OPPONENTS_ONLY_2026-09-23: direct_only=True
    (standaard) negeert vertrekpunten die zelf automatisch ontdekt zijn -
    zie _filter_direct_seeds() hierboven voor de volledige uitleg.

    Returns {player_id: display_name} voor de ONTBREKENDE spelers.
    """
    if direct_only:
        player_ids = _filter_direct_seeds(player_ids)
    known = _known_profile_ids()
    found: dict[str, str] = {}
    overgeslagen_tornooi = 0
    for pid in player_ids:
        try:
            doc = fb.get_player(pid) or {}
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[enrich] [{pid}] kon document niet lezen: {e}")
            continue
        for match in doc.get("matches", []) or []:
            if interclub_only and match.get("match_type") != "interclub":
                overgeslagen_tornooi += 1
                continue
            paren = [
                (match.get("opp1_user_id"), match.get("opp1_name")),
                (match.get("opp2_user_id"), match.get("opp2_name")),
            ]
            if include_partners:
                paren.append((match.get("partner_user_id"), match.get("partner_name")))
            for raw_id, naam in paren:
                other_id = _norm_id(raw_id)
                if not other_id or not other_id.isdigit():
                    continue
                if other_id in known or other_id in found:
                    continue
                naam = (naam or "").strip()
                if naam:
                    found[other_id] = naam
    if interclub_only and overgeslagen_tornooi:
        logger.info(
            f"[enrich] {overgeslagen_tornooi} tornooi-matchrij(en) overgeslagen bij "
            "het ontdekken van tegenstanders (interclub_only=True)."
        )
    return found


# ---------------------------------------------------------------------------
# 2. Profielen aanmaken
# ---------------------------------------------------------------------------
def ensure_profiles(
    players: dict,
    club: Optional[str] = None,
    allow_create: bool = False,
    max_new: int = MAX_NEW_PROFILES_PER_RUN,
) -> list:
    """Maak player_profiles-documenten aan voor {player_id: naam}.

    PADEL_ANALYSIS_GHOST_CLEANUP_TIMESTAMP_2026-09-16: discovered_at wordt
    hier gezet, enkel bij eerste aanmaak.

    PADEL_ANALYSIS_DISCOVERY_HARD_GUARD_2026-09-23
    ----------------------------------------------------------------------
    Deze functie heeft nu TWEE onafhankelijke veiligheden, omdat een default-
    waarde alleen aantoonbaar niet volstond (de fix van vanochtend raakte
    twee keer niet gedeployed en het probleem herhaalde zich identiek):

      1. allow_create moet EXPLICIET True zijn. Standaard False. Roept iets
         deze functie per ongeluk aan - of draait er ergens nog oude code die
         de nieuwe parameter niet kent - dan wordt er niets aangemaakt en
         verschijnt er een duidelijke uitleg in de log.
      2. max_new begrenst het aantal profielen per run (standaard
         MAX_NEW_PROFILES_PER_RUN = 40). Wordt die grens overschreden, dan
         wordt de aanmaak VOLLEDIG GEANNULEERD - niet gedeeltelijk
         uitgevoerd. Honderden profielen tegelijk is nooit een legitieme
         situatie: echte discovery via team-analyse gaat over 1 ploeg, dus
         een handvol spelers. Zo'n aantal betekent per definitie dat de
         scope fout zit, en dan is half aanmaken erger dan niets doen.

    PADEL_ANALYSIS_DISCOVERY_CLUB_2026-09-23 (op verzoek van Kim: "ik heb
    redelijk wat spelers gevonden die geen ploeg hadden")
    ----------------------------------------------------------------------
    De `club`-parameter bestond al, maar enrich() gaf ze nooit mee - dus bleef
    ze altijd None en werd het veld nooit gezet. Gevolg: elk profiel uit die
    route kwam clubloos binnen, en een speler zonder club wordt sinds
    PADEL_ANALYSIS_CLUB_REQUIRED_TO_SCRAPE_2026-09-20 NOOIT automatisch
    ververst (voorzorg tegen gelijknamige spelers). Die profielen bleven dus
    permanent leeg, zonder zichtbare oorzaak. Er wordt nu expliciet gelogd
    wanneer profielen zonder club aangemaakt worden.

    Returns de lijst van aangemaakte player_id's.
    """
    players = players or {}
    if not players:
        return []

    if not allow_create:
        logger.warning(
            f"[enrich] ensure_profiles() aangeroepen voor {len(players)} speler(s) ZONDER "
            "allow_create=True - er wordt NIETS aangemaakt "
            "(PADEL_ANALYSIS_DISCOVERY_HARD_GUARD_2026-09-23). Dit is de veilige standaard: "
            "profielen aanmaken moet altijd een bewuste keuze zijn."
        )
        return []

    if len(players) > max_new:
        logger.error(
            f"[enrich] GESTOPT: er zouden {len(players)} nieuwe profielen aangemaakt worden, "
            f"meer dan de limiet van {max_new} (MAX_NEW_PROFILES_PER_RUN). Er is NIETS "
            "aangemaakt.\n"
            "    Zo'n aantal betekent vrijwel zeker dat de scope fout zit - bijvoorbeeld "
            "discovery vanuit tegenstander-profielen, wat tegenstanders-VAN-tegenstanders "
            "oplevert.\n"
            "    Bedoel je dit toch? Verhoog dan bewust --max-new-profiles."
        )
        return []

    aangemaakt = []
    discovered_at = _utc_now_iso()
    club = (club or "").strip() or None
    if not club:
        logger.warning(
            f"[enrich] LET OP: de {len(players)} profielen hieronder worden ZONDER club "
            "aangemaakt. Spelers zonder gekende club worden NOOIT automatisch ververst "
            "(padelstat/officieel klassement). Geef --club mee, of vul de club per speler "
            "in via de app (Spelers -> Club/ploeg)."
        )
    for player_id, naam in (players or {}).items():
        payload = {
            "player_id": str(player_id),
            "display_name": naam,
            "added_by": "auto_opponent_discovery",
            "discovered_at": discovered_at,
        }
        if club:
            payload["club"] = club
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
                payload, merge=True
            )
            aangemaakt.append(str(player_id))
            logger.info(f"[enrich] Profiel aangemaakt: {naam} ({player_id})")
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
# 3. Padelstats playing strength ophalen
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
) -> dict:
    """Haal de padelstats.be playing strength op voor deze spelers.

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

    Returns: {"opgehaald": n, "cache": n, "niet_gevonden": n, "fout": n,
    "overgeslagen_limiet": n}.
    """
    priority_ids = {_norm_id(p) for p in (priority_ids or set())}
    samenvatting = {"opgehaald": 0, "cache": 0, "niet_gevonden": 0,
                     "fout": 0, "overgeslagen_limiet": 0,
                     "officieel_klassement": 0}
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
        try:
            gevonden = ps.search_and_fetch_padelstat_rating(naam, club=club or None)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{prefix} -> FOUT: {e}")
            samenvatting["fout"] += 1
            continue
        if not gevonden or gevonden.get("rating") is None:
            logger.info(f"{prefix} -> niet gevonden op padelstats.be")
            samenvatting["niet_gevonden"] += 1
            time.sleep(pause_seconds)
            continue
        try:
            # PADEL_ANALYSIS_ENRICH_SNAPSHOT_FIX_2026-09-23: matched_klassement
            # en club_confirmed werden hier niet doorgegeven, waardoor
            # save_padelstat_rating() intern NOOIT
            # save_official_klassement_from_padelstat() aanriep -> "officieel
            # klassement via padelstat: 0" in elke CI-run, geen snapshot, en
            # dus viel de UI terug op de vertekende TVL-historiek.
            klassement = (
                gevonden.get("matched_klassement")
                or gevonden.get("klassement")
                or gevonden.get("official_klassement")
            )
            fb.save_padelstat_rating(
                player_id,
                gevonden.get("padelstat_id", ""),
                gevonden.get("rating"),
                gevonden.get("rating_source", "none"),
                gevonden.get("raw_text_snippet", ""),
                matched_klassement=klassement,
                club_confirmed=not gevonden.get("club_disambiguation_note"),
            )
            samenvatting["opgehaald"] += 1
            if klassement is not None:
                samenvatting["officieel_klassement"] = samenvatting.get("officieel_klassement", 0) + 1
            vlag = " ⚠️ club niet bevestigd" if gevonden.get("club_disambiguation_note") else ""
            klass_txt = f", officieel klassement P{klassement}" if klassement is not None else ""
            logger.info(f"{prefix} -> P{gevonden['rating']}{klass_txt}{vlag}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{prefix} -> opslaan mislukt: {e}")
            samenvatting["fout"] += 1
        time.sleep(pause_seconds)
    return samenvatting


# ---------------------------------------------------------------------------
# 4. Klassementshistoriek ophalen
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
    """Haalt de TVL-klassementshistoriek op voor deze spelers, met dezelfde
    scrape_klassement.py-functies en opslagvorm als de bestaande lokale flow.

    LET OP (PADEL_ANALYSIS_SINGLE_PLAYER_REFRESH_FIX_2026-09-19): deze
    functie heeft, in tegenstelling tot run_padelstat_for_players(), GEEN
    staleness-check — _has_klassement() kijkt enkel OF er een klassement_
    history bestaat, niet hoe oud/correct die is. Dit was de root cause van
    "Stijn Mortier wordt nooit ververst": hij had al éénmaal een (foutieve)
    klassement_history staan en werd dus permanent als 'cache' behandeld.
    De nieuwe priority_ids-parameter lost dit gericht op: voor die spelers
    wordt _has_klassement() genegeerd (altijd opnieuw ophalen) en krijgen ze
    voorrang bij het afkappen op max_players.

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
    # PADEL_ANALYSIS_DISCOVERY_OPT_IN_2026-09-23: was True - zie de
    # module-docstring voor het incident dat dit veroorzaakte.
    do_discover: bool = False,
    do_padelstat: bool = True,
    padelstat_refresh: bool = False,
    padelstat_max: int = PADELSTAT_MAX_PER_RUN,
    padelstat_stale_after_days: int = PADELSTAT_STALE_AFTER_DAYS,
    do_klassement: bool = True,
    klassement_refresh: bool = False,
    klassement_max: int = KLASSEMENT_MAX_PER_RUN,
    interclub_only: bool = True,
    priority_ids: Optional[set] = None,
    # PADEL_ANALYSIS_DISCOVERY_CLUB_2026-09-23: werd voorheen nooit
    # doorgegeven aan ensure_profiles(). Valt terug op de CLUB-
    # omgevingsvariabele, zodat de GitHub Actions-route dezelfde hint kan
    # gebruiken als refresh_padelstat_only.py.
    club: Optional[str] = None,
    max_new_profiles: int = MAX_NEW_PROFILES_PER_RUN,
) -> dict:
    """Volledige verrijkingsstap: tegenstanders ontdekken + profielen aanmaken
    + padelstats ophalen/verversen + klassementshistoriek ophalen.

    priority_ids (optioneel, standaard None = ONGEWIJZIGD bulk-gedrag): een
    set van player_id's die, indien meegegeven, ALTIJD geforceerd ververst
    worden (cache/staleness genegeerd voor DIE spelers) en nooit door
    nieuw ontdekte ghost-profielen verdrongen worden bij het afkappen op
    *_max. Wordt NIET automatisch afgeleid van `player_ids` — bij een
    normale bulk-aanroep (bv. de dagelijkse cron met honderden spelers)
    blijft de bestaande cache/staleness-logica dus voor IEDEREEN gewoon
    gelden, precies zoals voorheen. Enkel run_single_player_refresh()
    hieronder geeft hier bewust EEN speler-id aan mee.

    Returns {"nieuwe_profielen": [...], "padelstat": {...}, "klassement": {...}}.
    """
    resultaat: dict = {"nieuwe_profielen": [], "padelstat": {}, "klassement": {}}
    if do_discover:
        logger.warning(
            "[enrich] DISCOVERY STAAT AAN - er kunnen NIEUWE spelersprofielen aangemaakt worden. "
            "Is dat niet de bedoeling: onderbreek nu (Ctrl+C) en draai opnieuw zonder --discover."
        )
        club_hint = (club or os.environ.get("CLUB") or "").strip() or None
        ontbrekend = discover_opponent_players(player_ids, interclub_only=interclub_only)
        if ontbrekend:
            logger.info(
                f"[enrich] {len(ontbrekend)} rechtstreekse tegenstander(s)/partner(s) zonder "
                f"profiel gevonden (interclub_only={interclub_only})."
            )
            resultaat["nieuwe_profielen"] = ensure_profiles(
                ontbrekend, club=club_hint, allow_create=True, max_new=max_new_profiles,
            )
        else:
            logger.info("[enrich] Alle gekende tegenstanders hebben al een profiel.")
    doelgroep = list(dict.fromkeys(
        [str(p) for p in player_ids] + resultaat["nieuwe_profielen"]
    ))
    if do_padelstat:
        resultaat["padelstat"] = run_padelstat_for_players(
            doelgroep, refresh=padelstat_refresh, max_players=padelstat_max,
            stale_after_days=padelstat_stale_after_days, priority_ids=priority_ids,
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
) -> dict:
    """Ververst ALLEEN padelstat + klassement voor DEZE ENE speler, met
    refresh=True (cache/staleness volledig genegeerd, dus GEGARANDEERD een
    poging), en ZONDER enige discovery of nieuwe ghost-profielen aan te
    maken voor tegenstanders/partners.

    Gebruikt door ci_scrape_all.py wanneer er via de workflow-input
    (PLAYER_IDS) EXACT 1 speler werd aangevraagd (bv. de "Scrape deze
    speler nu"-knop) — dit is precies wat Kim vroeg: "bedoeling is dat
    enkel die speler ververst wordt (id speler meegeven)".

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

    # PADEL_ANALYSIS_DISCOVERY_HARD_GUARD_2026-09-23: als allereerste regel,
    # zodat je in de output meteen ziet of de nieuwe versie effectief draait.
    logger.info(f"[enrich] enrich_opponents.py versie {ENRICH_VERSION} "
                f"(discovery standaard UIT, max {MAX_NEW_PROFILES_PER_RUN} nieuwe profielen/run)")

    parser = argparse.ArgumentParser(
        description="Tegenstanders als speler aanmaken + padelstats/klassement ophalen."
    )
    parser.add_argument("player_ids", nargs="*", help="Eigen spelers om vanuit te vertrekken.")
    parser.add_argument("--all", action="store_true", help="Vertrek van ALLE gekende profielen.")
    # PADEL_ANALYSIS_DISCOVERY_OPT_IN_2026-09-23: was "--no-discover" (dus
    # discovery AAN tenzij je eraan dacht ze uit te zetten). Omgedraaid naar
    # een expliciete opt-in.
    parser.add_argument("--discover", action="store_true",
                        help="Maak WEL nieuwe profielen aan voor RECHTSTREEKSE tegenstanders/"
                             "partners zonder profiel (standaard UIT).")
    parser.add_argument("--no-discover", action="store_true",
                        help="Verouderd/genegeerd: discovery staat sinds 2026-09-23 standaard "
                             "al uit. Blijft aanvaard zodat bestaande scripts niet breken.")
    parser.add_argument("--club", default=None,
                        help="Club/ploeg die op NIEUW ontdekte profielen gezet wordt. Zonder dit "
                             "(of de CLUB-omgevingsvariabele) blijven die profielen clubloos en "
                             "worden ze NOOIT automatisch ververst.")
    parser.add_argument("--max-new-profiles", type=int, default=MAX_NEW_PROFILES_PER_RUN,
                        help=f"Harde limiet op nieuwe profielen per run (standaard "
                             f"{MAX_NEW_PROFILES_PER_RUN}). Wordt die overschreden, dan wordt er "
                             "NIETS aangemaakt.")
    parser.add_argument("--no-padelstat", action="store_true", help="Geen padelstats ophalen.")
    parser.add_argument("--no-klassement", action="store_true", help="Geen klassementshistoriek ophalen.")
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
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon enkel welke spelers zouden worden aangemaakt.")
    args = parser.parse_args()

    if args.single_player:
        if not args.player_ids:
            print("Geef exact 1 speler mee als positional argument bij --single-player.")
            sys.exit(1)
        res = run_single_player_refresh(args.player_ids[0])
        print("\n=== Samenvatting (losse-speler-verversing) ===")
        print(f"Padelstat  : {res['padelstat']}")
        print(f"Klassement : {res['klassement']}")
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
        ontbrekend = discover_opponent_players(ids, interclub_only=not args.include_tournament)
        print(f"\n{len(ontbrekend)} speler(s) zonder profiel:\n")
        for pid, naam in sorted(ontbrekend.items(), key=lambda kv: kv[1]):
            print(f"  {pid:<12} {naam}")
        sys.exit(0)

    res = enrich(
        ids,
        do_discover=args.discover and not args.no_discover,
        club=args.club,
        max_new_profiles=args.max_new_profiles,
        do_padelstat=not args.no_padelstat,
        padelstat_refresh=args.refresh,
        padelstat_max=args.max,
        padelstat_stale_after_days=args.padelstat_stale_days,
        do_klassement=not args.no_klassement,
        klassement_refresh=args.refresh,
        klassement_max=args.klassement_max,
        interclub_only=not args.include_tournament,
    )
    print("\n=== Samenvatting ===")
    print(f"Nieuwe profielen : {len(res['nieuwe_profielen'])}")
    if res["padelstat"]:
        p = res["padelstat"]
        print(
            f"Padelstats       : {p.get('opgehaald', 0)} opgehaald/ververst, "
            f"{p.get('cache', 0)} nog actueel, {p.get('niet_gevonden', 0)} niet gevonden, "
            f"{p.get('fout', 0)} fout"
        )
        if p.get("overgeslagen_limiet"):
            print(f"                   {p['overgeslagen_limiet']} wachten op een volgende run")
    if res["klassement"]:
        k = res["klassement"]
        print(
            f"Klassement       : {k.get('opgehaald', 0)} opgehaald, "
            f"{k.get('cache', 0)} uit cache, {k.get('fout', 0)} fout"
        )
        if k.get("overgeslagen_limiet"):
            print(f"                   {k['overgeslagen_limiet']} wachten op een volgende run")
    if res["nieuwe_profielen"]:
        print(
            f"\nLet op: de {len(res['nieuwe_profielen'])} nieuwe speler(s) hebben nog geen "
            "matchdata. Draai nu ci_scrape_all.py (MODE=new_users) om die op te halen."
        )
