# -*- coding: utf-8 -*-
"""
refresh_padelstat_only.py — geïsoleerd script dat de padelstats.be playing
strength ÉN het bijhorende officiële klassement (snapshot) van alle spelers
(eigen team + tegenstanders) controleert/herstelt. Doet niets met de
volledige TVL-klassementshistoriek (dat blijft scrape_klassement.py) of
poule-schema's.
Locatie: PadelAnalysis/scraper/refresh_padelstat_only.py
(naast enrich_opponents.py / ci_scrape_all.py, zelfde path-setup patroon)
--------------------------------------------------------------------------
WAAROM DIT EEN APART SCRIPT IS (bewust losgekoppeld van ci_scrape_all.py)
--------------------------------------------------------------------------
Op verzoek van Kim: de matchdata-scrape liep vast op de 30-minuten-limiet
van GitHub Actions naarmate de spelerslijst groeide, en "een speler
verversen" loste de padelstat-problemen niet op. Om dat laatste eerst apart,
gericht op te kunnen lossen (zonder te wachten op de bredere timeout-fix),
is dit een volledig zelfstandig script: eigen workflow, eigen tijdslimiet,
geen afhankelijkheid van scrape_player.py of poule_playwright.py.
--------------------------------------------------------------------------
WAAROM "VERVERSEN" TOT NU TOE NIET HIELP (kernprobleem, hier opgelost)
--------------------------------------------------------------------------
enrich_opponents.run_padelstat_for_players() (en dus ook de "Ververs alles"-
knop in opponent_scout_ui.py) doet, zonder force=True:
    cached = fb.get_padelstat_rating(pid)
    if cached and cached.get("rating") is not None:
        continue  # overslaan: "er staat al iets"
Dat "er staat al iets" is precies het probleem. Deze sessie zijn twee
bugs in padelstats_scraper.py opgelost die er eerder voor zorgden dat de
gevonden waarde VERKEERD kon zijn of de scrape gewoon MISLUKTE:
  - PADEL_ANALYSIS_PADELSTAT_CLUB_MATCH_BUG_2026-09-13: een fragiele,
    asymmetrische substring-vergelijking kon de verkeerde gelijknamige
    speler kiezen (bv. Carl Ide werd niet gekoppeld aan zijn eigen club).
  - PADEL_ANALYSIS_PADELSTAT_CONSENT_BANNER_REGRESSION_2026-09-16: de
    cookie-consent-banner op padelstats.be blokkeerde de zoekbalk, waardoor
    de scrape vastliep zonder ooit een waarde op te halen.
Elke speler wiens rating VOOR deze fixes werd opgehaald, kan dus een foute
of ontbrekende waarde hebben -- en een gewone refresh slaat die speler
STRUCTUREEL over, want er "staat al iets" (of het faalde stil).
Fix: dit script stempelt elke succesvolle opzoeking met een
PADELSTAT_LOGIC_VERSION-marker (padelstat_logic_version-veld op het
player_profiles-document). Bij elke run wordt een speler als "moet
gecontroleerd worden" beschouwd zodra:
  1. er helemaal geen rating bekend is, OF
  2. de opgeslagen padelstat_logic_version niet overeenkomt met de HUIDIGE
     versie hieronder (dus: nooit gecontroleerd MET de gerepareerde
     scraper) -- dit is het EENMALIGE zelfherstel-mechanisme dat oude,
     mogelijk foute waarden alsnog corrigeert, zonder dat Kim iets hoeft
     te doen, en daarna nooit meer onnodig, want eenmaal bijgewerkte
     spelers krijgen de nieuwe versie-marker en worden dus overgeslagen.
Verhoog PADELSTAT_LOGIC_VERSION wanneer er ooit weer een fix in
padelstats_scraper.py komt die een NIEUWE algehele hercontrole rechtvaardigt.
--------------------------------------------------------------------------
DAGELIJKS/UURLIJKS, MET EEN HARDE LIMIET PER RUN (batching)
--------------------------------------------------------------------------
Elke padelstat-opzoeking kost een volledige Playwright-sessie (~10-30s).
Om nooit tegen een workflow-timeout aan te lopen, verwerkt dit script
STANDAARD MAX 10 spelers per run (PADELSTAT_MAX, overschrijfbaar via env of
--max) — bedoeld om ELK UUR te draaien, zie
PADEL_ANALYSIS_HOURLY_TRICKLE_REFRESH_2026-09-20 hieronder.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MULTI_WORKFLOW_TRIGGER_2026-09-17 (op verzoek van Kim,
"dat moet wel werken via github actions... bekijk dat eens van dichterbij")
--------------------------------------------------------------------------
BUG/BEPERKING (opgelost): op Streamlit Cloud bestond GEEN ENKELE directe
manier om padelstat onmiddellijk te forceren voor een specifieke
tegenstander-ploeg -- de "🔄 Ververs alles voor deze ploeg"-knop in
opponent_scout_ui.py werd enkel getoond als is_scraping_available() True is
(nooit het geval op Cloud), en --player accepteerde tot nu maar 1 los ID.
Fix: --player accepteert nu ook een KOMMA-GESCHEIDEN lijst van player_id's
(bv. "111,222,333"), zodat een "🎯 Playing strength nu ophalen voor deze
ploeg"-knop in één workflow-run exact de tegenstander-roster kan targeten
via refresh-padelstat.yml se workflow_dispatch. Bij een expliciete
--player-lijst worden ALLE gevraagde spelers verwerkt, OOK als dat er meer
zijn dan --max (de max-cap geldt enkel voor de generieke, prioriteit-
gebaseerde selectie, niet voor een expliciet aangewezen doelgroep).
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLUB_OVERRIDE_2026-09-19 (op verzoek van Kim, chat
2026-09-19, na een handmatige run met "--player <5 ids van 1 ploeg>")
--------------------------------------------------------------------------
Kim's exacte melding, met bewijs uit de log:
    "Uitvoeren: python refresh_padelstat_only.py --max 5 --force-all
    --player 1467612,1510358,1462657,1226267,1624184
    [...]
    (1/5) De Somer Kurt (1226267, club='')...
    -> P430 — 2 kandidaten gevonden voor 'De Somer Kurt' (clubs:
    ['T.C. HALEN DE ZWALUW', 'LUDOVIEK PADEL']), maar geen club opgegeven
    om te disambigueren. Eerste resultaat gebruikt - geef het
    'club'-argument mee voor een zekere match."
FIX (destijds): optioneel --club-argument (of CLUB-env var). Wordt gebruikt
als disambiguatie-hint voor spelers in deze run die zelf nog geen club
hebben, en wordt eenmalig teruggeschreven naar hun profiel (_backfill_club())
zodat een volgende, --club-loze run diezelfde speler al met de juiste club
vindt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLUB_REQUIRED_TO_SCRAPE_2026-09-20 (op verzoek van Kim: "bij
refresh padelstat.be: als ik dat run dan weet die niet welke club de
speler toe behoort. [...] gelieve dan playing strength leeg te laten en te
vragen om bij de speler de ploeg op te geven of zoiets?")
--------------------------------------------------------------------------
FIX: een speler zonder GEKENDE club (existing_club leeg EN geen
club_override actief voor deze speler) wordt NIET meer opgezocht op
padelstats.be — te riskant bij gelijknamige spelers. Zulke spelers komen in
de "club_onbekend"-lijst in de samenvatting terecht, met een duidelijke
log-regel die vraagt om de club/ploeg voor deze speler in te stellen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_HOURLY_TRICKLE_REFRESH_2026-09-20 (op verzoek van Kim: "bij
veel scrapen riskeer ik blokkeren en ook te lange tijd. Periodiek mag mss
gewoon per uur 2 spelers ofzo van mijn ganse lijst? [...] Wel belangrijk om
scrape direct te stoppen als de data al actueel is")
--------------------------------------------------------------------------
FIX: needs_check() heeft een DERDE, tijdsgebaseerde trigger — een rating
die ouder is dan PADELSTAT_STALE_AFTER_DAYS (standaard 14 dagen) wordt
ALSNOG als "moet gecontroleerd worden" beschouwd, zelfs met een actuele
logic-version en een bekende rating. Dit maakt van dit script een echte,
DOORLOPENDE ververs-cyclus i.p.v. een eenmalige zelfherstel-actie. "STOP
DIRECT ALS DE DATA AL ACTUEEL IS" wordt hierdoor concreet ingevuld: een
speler die noch verouderd qua logic-version, noch zonder rating, noch ouder
dan de staleness-drempel is, wordt NOOIT in `te_verwerken` opgenomen — er
wordt dus ook NOOIT een Playwright-sessie voor hem/haar gestart. Dat is
doeltreffender dan een lopende scrape halverwege afbreken: hij wordt
gewoonweg nooit gestart.
--------------------------------------------------------------------------
PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_IN_SINGLE_REFRESH_2026-09-21 (op verzoek
van Kim: "die refresh knop [...] mag dan alles refreshen. padelstat
playing strength, officieel klassement en matchen")
--------------------------------------------------------------------------
BUG/GAT (opgelost): dit script (het script dat de "🎯 Playing strength nu
ophalen"-knop EN de per-speler-verversknop in de app effectief aanroepen)
sloeg tot nu toe UITSLUITEND de playing strength (fb.save_padelstat_rating,
enkel het "rating"-veld) op — ook al geeft padelstats_scraper.
search_and_fetch_padelstat_rating() AL het officiële klassement mee terug
(het "matched_klassement"-veld, uit de "P200 • CLUB"-tekst van de
zoekresultaatkaart). Dat officiële klassement werd dus stilzwijgend
GENEGEERD in dit specifieke script — enkel enrich_opponents.py (de bulk-
verrijkingsstap voor NIEUWE tegenstanders) sloeg het al wél op. Voor een
GERICHTE 1-speler- of 1-ploeg-refresh via de app (dit script) ontbrak het
dus.
FIX: refresh_one() slaat het officiële klassement nu ALTIJD mee op (via
firebase_service.save_padelstat_rating()'s nieuwe matched_klassement-
parameter, zie firebase_service.py) zodra de padelstats.be-kaart die
meegeeft — zonder enige extra Playwright-sessie, want dit komt uit
HETZELFDE paginabezoek dat toch al gebeurde voor de playing strength. Eén
enkele trigger van dit script (via de per-speler-knop of de uurlijkse
achtergrondtaak) houdt zo VOORTAAN zowel playing strength als het officiële
klassement-snapshot actueel.
--------------------------------------------------------------------------
PADEL_ANALYSIS_MISSING_REQUESTED_PLAYER_WARNING_2026-09-21 (op verzoek van
Kim: "ik zie bij refresh van ploeg bij padelstat dat 1 speler niet
meegenomen wordt: nochtans wel max: 5" — met --player 1467612,1510358,
1622012,1462657,1226267 (5 ID's), maar de log toonde "4 kandidaten,
waarvan 4 verwerkt")
--------------------------------------------------------------------------
ROOT CAUSE: select_players_to_process() se `only_player_id`-tak filterde
gewoon `profiles` op de gevraagde ID's (`matches = [p for p in profiles if
_norm_id(p.get("player_id")) in gevraagde_ids]`) — een gevraagd ID dat GEEN
player_profiles-document heeft (bv. een nog niet aangemaakt profiel voor
een nieuwe speler) viel daardoor STILZWIJGEND uit `matches` weg. Er was
geen enkele log-regel die zei WELK gevraagd ID ontbrak of WAAROM — de
samenvatting toonde gewoon "4 kandidaten" i.p.v. de gevraagde 5, zonder
enige aanwijzing.
FIX: select_players_to_process() berekent nu expliciet het verschil tussen
de gevraagde ID's en de teruggevonden ID's, en logt een duidelijke
waarschuwing met de exacte, ontbrekende player_id('s) zodra dit voorkomt —
zodat meteen duidelijk is of het om een ontbrekend profiel gaat (eerst
aanmaken/toevoegen als speler vóór een padelstat-refresh mogelijk is) i.p.v.
zelf te moeten tellen/vergelijken welke van de opgegeven ID's ontbreekt.
--------------------------------------------------------------------------
PADEL_ANALYSIS_BATCH_SIZE_INCREASE_2026-09-21 (op verzoek van Kim: "Je mag
dat maximum trouwens op 10 zetten. zal nodig zijn voor het najaar" — meer
spelers/tegenstanders om periodiek te verversen zodra de interclub-
competitie hervat)
--------------------------------------------------------------------------
FIX: DEFAULT_MAX_PER_RUN opgetrokken van 2 naar 10. Bij ~10-30s per speler
blijft een run van 10 spelers (~1,5-5 minuten) nog ruim binnen de
workflow-timeout van 10 minuten (zie refresh-padelstat.yml, waar de
workflow_dispatch-input 'max' en de cron-fallback consistent mee opgetrokken
zijn naar 10).
--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    python refresh_padelstat_only.py --dry-run
    python refresh_padelstat_only.py
    python refresh_padelstat_only.py --max 2                       (kleine batch)
    python refresh_padelstat_only.py --max 60
    python refresh_padelstat_only.py --player 1759548              (1 speler, altijd)
    python refresh_padelstat_only.py --player 111,222,333          (meerdere spelers, altijd)
    python refresh_padelstat_only.py --force-all --max 20          (iedereen herzien)
    python refresh_padelstat_only.py --player 111,222,333 --club "T.C. VOORBEELD"  (ploeg met gekende club)
    python refresh_padelstat_only.py --stale-days 30               (periodieke cyclus vertragen)
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

logger = logging.getLogger(__name__)

# Verhogen bij een volgende fix in padelstats_scraper.py die een nieuwe,
# algehele hercontrole van ALLE spelers rechtvaardigt (zelfherstel-trigger).
PADELSTAT_LOGIC_VERSION = "v2-clubwordmatch-consentretry-2026-09-16"
# PADEL_ANALYSIS_BATCH_SIZE_INCREASE_2026-09-21: 2 -> 10 (zie changelog hierboven).
DEFAULT_MAX_PER_RUN = 10
DEFAULT_PAUSE_SECONDS = 1.5
# PADEL_ANALYSIS_HOURLY_TRICKLE_REFRESH_2026-09-20: na hoeveel dagen een
# bestaande, actuele (juiste logic-version) rating ALSNOG als "te
# controleren" geldt — maakt van dit script een doorlopende ververs-cyclus
# i.p.v. een eenmalige zelfherstel-actie. Zelfde default als het analoge
# mechanisme in enrich_opponents.PADELSTAT_STALE_AFTER_DAYS.
DEFAULT_STALE_AFTER_DAYS = 14


def _norm_id(value) -> str:
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


def _all_profiles() -> list:
    try:
        return fb.search_player_profiles("", limit=10_000) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Kon profielen niet lezen: {e}")
        return []


def _rating_age_days(player_id: str) -> Optional[float]:
    """PADEL_ANALYSIS_HOURLY_TRICKLE_REFRESH_2026-09-20: leeftijd (in dagen)
    van de bestaande padelstat-rating, op basis van "fetched_at"
    (firebase_service.save_padelstat_rating() zet dit veld, NIET
    "scraped_at" zoals bij klassement_history). None als er geen rating of
    geen bruikbare tijdstempel bestaat."""
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:  # noqa: BLE001
        return None
    if not cached or cached.get("rating") is None:
        return None
    fetched_at = _parse_iso(cached.get("fetched_at"))
    if fetched_at is None:
        return None
    return (datetime.now(timezone.utc) - fetched_at).total_seconds() / 86400


def needs_check(
    profile: dict, force_all: bool = False, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> tuple[bool, str]:
    """Bepaalt of deze speler deze run gecontroleerd moet worden, en waarom.
    Returns (moet_gecontroleerd, reden). De reden wordt gebruikt om de
    prioriteitsvolgorde te bepalen (zie module-docstring).
    PADEL_ANALYSIS_HOURLY_TRICKLE_REFRESH_2026-09-20: nieuwe, DERDE trigger
    -- een rating die ouder is dan `stale_after_days` geldt ALSNOG als "te
    controleren", zelfs met een actuele logic-version en een bekende
    rating. Zonder dit zou het script, zodra iedereen ooit gecontroleerd
    is met de huidige PADELSTAT_LOGIC_VERSION, voor altijd niets meer
    doen -- playing strength zou dan nooit meer automatisch bijgewerkt
    worden."""
    if force_all:
        return True, "force-all"
    version = profile.get("padelstat_logic_version")
    if version != PADELSTAT_LOGIC_VERSION:
        return True, "verouderde-versie (mogelijk foute oude waarde)"
    player_id = _norm_id(profile.get("player_id"))
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:  # noqa: BLE001
        cached = None
    if not cached or cached.get("rating") is None:
        return True, "geen rating bekend"
    if stale_after_days and stale_after_days > 0:
        age_days = _rating_age_days(player_id)
        # Geen bruikbare leeftijd te bepalen (bv. ontbrekend fetched_at op
        # een heel oude rating) -> conservatief ALSNOG als verouderd
        # behandelen, analoog aan enrich_opponents._padelstat_is_stale().
        if age_days is None or age_days > stale_after_days:
            return True, "periodiek te verversen (rating ouder dan drempel)"
    return False, "al gecontroleerd met huidige scraper-versie, nog actueel"


def select_players_to_process(
    profiles: list,
    max_per_run: int,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> list:
    """Kiest WELKE spelers deze run verwerkt worden, met prioriteit voor
    zelfherstel (verouderde versie) boven nieuw-ontbrekend boven periodiek
    te verversen (verouderde rating).
    PADEL_ANALYSIS_MULTI_WORKFLOW_TRIGGER_2026-09-17: only_player_id
    ondersteunt ook een KOMMA-GESCHEIDEN lijst van player_id's. Deze spelers
    worden ALTIJD verwerkt, ongeacht max_per_run (die cap geldt enkel voor
    de generieke, prioriteit-gebaseerde selectie hieronder).
    PADEL_ANALYSIS_MISSING_REQUESTED_PLAYER_WARNING_2026-09-21 (op verzoek
    van Kim: "ik zie bij refresh van ploeg bij padelstat dat 1 speler niet
    meegenomen wordt"): een gevraagd ID zonder bijhorend player_profiles-
    document viel voorheen STILZWIJGEND weg. Nu wordt expliciet gelogd
    WELKE gevraagde ID('s) niet teruggevonden werden, zodat dit nooit meer
    onopgemerkt blijft."""
    if only_player_id:
        gevraagde_ids = {_norm_id(pid) for pid in str(only_player_id).split(",") if pid.strip()}
        matches = [p for p in profiles if _norm_id(p.get("player_id")) in gevraagde_ids]
        gevonden_ids = {_norm_id(p.get("player_id")) for p in matches}
        ontbrekend = gevraagde_ids - gevonden_ids
        if ontbrekend:
            logger.warning(
                f"⚠️ {len(ontbrekend)} aangevraagde speler(s) NIET gevonden in player_profiles "
                f"(geen bestaand profiel voor dit player_id, of het profiel mist een player_id-veld): "
                f"{', '.join(sorted(ontbrekend))}. Deze speler(s) worden deze run NIET verwerkt — maak "
                "eerst een profiel aan (bv. via 'Speler toevoegen' in de app) voor je opnieuw ververst."
            )
        return matches
    kandidaten = []
    for p in profiles:
        if not p.get("player_id") or not p.get("display_name"):
            continue
        moet, reden = needs_check(p, force_all=force_all, stale_after_days=stale_after_days)
        if moet:
            kandidaten.append((p, reden))
    prioriteit = {
        "force-all": 0,
        "verouderde-versie (mogelijk foute oude waarde)": 1,
        "geen rating bekend": 2,
        "periodiek te verversen (rating ouder dan drempel)": 3,
    }
    kandidaten.sort(key=lambda item: prioriteit.get(item[1], 9))
    return [p for p, _ in kandidaten[:max_per_run]]


def refresh_one(player_id: str, naam: str, club: str, dry_run: bool = False) -> dict:
    """Voert de effectieve padelstats.be-opzoeking uit voor 1 speler en
    stempelt het resultaat met PADELSTAT_LOGIC_VERSION (zelfherstel-marker),
    ONGEACHT of er al eerder een (mogelijk foute) waarde stond.
    PADEL_ANALYSIS_OFFICIAL_KLASSEMENT_IN_SINGLE_REFRESH_2026-09-21: slaat
    nu, naast de playing strength, ook het officiële klassement op zodra de
    padelstats.be-kaart dat meegeeft ("matched_klassement") — beide komen
    uit HETZELFDE paginabezoek, dus zonder extra Playwright-sessie. Zie
    firebase_service.save_padelstat_rating() voor de opslaglogica.
    LET OP: de club-verplichting (PADEL_ANALYSIS_CLUB_REQUIRED_TO_SCRAPE_
    2026-09-20) wordt VOOR deze functie gecontroleerd (in run()), niet hier."""
    import padelstats_scraper as pss  # lazy: enkel nodig als deze stap draait
    result = {"player_id": player_id, "naam": naam, "status": None, "rating": None, "klassement": None, "note": None}
    try:
        gevonden = pss.search_and_fetch_padelstat_rating(naam, club=club or None)
    except Exception as e:  # noqa: BLE001
        result["status"] = "fout"
        result["note"] = str(e)
        return result
    if not gevonden or gevonden.get("rating") is None:
        result["status"] = "niet_gevonden"
        if not dry_run:
            _stamp_checked(player_id, found=False)
        return result
    result["status"] = "opgehaald"
    result["rating"] = gevonden.get("rating")
    result["klassement"] = gevonden.get("matched_klassement")
    club_niet_bevestigd = bool(gevonden.get("club_disambiguation_note"))
    if club_niet_bevestigd:
        result["note"] = gevonden["club_disambiguation_note"]
    if not dry_run:
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
        except Exception as e:  # noqa: BLE001
            result["status"] = "opslaan_mislukt"
            result["note"] = str(e)
            return result
        _stamp_checked(player_id, found=True)
    return result


def _stamp_checked(player_id: str, found: bool) -> None:
    """Zet de versie-marker + tijdstempel, ONGEACHT of er een waarde
    gevonden werd -- ook 'niet gevonden' is een geldig, bewust resultaat dat
    niet elke run opnieuw geprobeerd hoeft te worden totdat de scraper zelf
    weer verandert (PADELSTAT_LOGIC_VERSION omhoog) of de periodieke
    staleness-drempel opnieuw verstrijkt."""
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
            {
                "padelstat_logic_version": PADELSTAT_LOGIC_VERSION,
                "padelstat_last_checked_at": _utc_now_iso(),
                "padelstat_last_result": "found" if found else "not_found",
            },
            merge=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[{player_id}] Kon versie-stempel niet wegschrijven: {e}")


def _backfill_club(player_id: str, club: str) -> None:
    """PADEL_ANALYSIS_CLUB_OVERRIDE_2026-09-19: schrijft de via --club/CLUB
    meegegeven waarde WEG naar het player_profiles-document, maar ENKEL voor
    spelers die nog GEEN eigen club hadden (de aanroeper in run() checkt dit
    vooraf) -- zodat een VOLGENDE, --club-loze run deze speler al met de
    juiste club vindt en de ambiguïteitswaarschuwing niet blijft terugkomen.
    Overschrijft NOOIT een reeds bekende club (die kan, bij dubbel-
    clublidmaatschap, bewust anders zijn dan de ploeg die je nu scrapet)."""
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
            {"club": club}, merge=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[{player_id}] Kon club niet backfillen: {e}")


def run(
    max_per_run: int = DEFAULT_MAX_PER_RUN,
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    force_all: bool = False,
    only_player_id: Optional[str] = None,
    club_override: Optional[str] = None,
    dry_run: bool = False,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> dict:
    """PADEL_ANALYSIS_CLUB_OVERRIDE_2026-09-19: `club_override` — indien
    meegegeven, gebruikt als disambiguatie-hint voor ELKE speler in deze run
    wiens EIGEN profiel nog geen club heeft (overschrijft nooit een reeds
    bekende, mogelijk andere club).
    PADEL_ANALYSIS_CLUB_REQUIRED_TO_SCRAPE_2026-09-20: is er, NA het
    toepassen van een eventuele club_override, ALSNOG geen club gekend voor
    een speler, dan wordt die speler NIET opgezocht op padelstats.be — te
    riskant bij gelijknamige spelers. Zulke spelers komen in de nieuwe
    "club_onbekend"-lijst in de samenvatting terecht.
    PADEL_ANALYSIS_HOURLY_TRICKLE_REFRESH_2026-09-20: `stale_after_days`
    bepaalt na hoeveel dagen een reeds actuele rating ALSNOG periodiek
    opnieuw gecontroleerd wordt (zie needs_check())."""
    profiles = _all_profiles()
    alle_kandidaten = [
        p for p in profiles
        if p.get("player_id") and p.get("display_name")
        and needs_check(p, force_all=force_all, stale_after_days=stale_after_days)[0]
    ] if not only_player_id else []
    te_verwerken = select_players_to_process(
        profiles, max_per_run, force_all=force_all, only_player_id=only_player_id,
        stale_after_days=stale_after_days,
    )
    logger.info(
        f"{len(profiles)} speler(s) totaal in player_profiles. "
        f"{len(alle_kandidaten) or len(te_verwerken)} kandidaat/kandidaten voor controle, "
        f"waarvan {len(te_verwerken)} deze run verwerkt worden (max={max_per_run})."
    )
    if club_override:
        logger.info(
            f"CLUB-override actief: '{club_override}' wordt gebruikt als disambiguatie-hint voor "
            "spelers in deze run die zelf nog geen club hebben (bestaande clubs blijven ongewijzigd)."
        )
    if dry_run:
        logger.info("--dry-run: er wordt NIETS gescrapet of weggeschreven, enkel getoond wie aan bod zou komen.")
        for p in te_verwerken:
            moet, reden = needs_check(p, force_all=force_all, stale_after_days=stale_after_days)
            club_status = "club bekend" if (p.get("club") or club_override) else "⚠️ CLUB ONBEKEND - zou overgeslagen worden"
            logger.info(
                f"  zou verwerkt worden: {p.get('display_name')} ({p.get('player_id')}) — "
                f"reden: {reden} — {club_status}"
            )
        return {
            "totaal_profielen": len(profiles),
            "kandidaten": len(alle_kandidaten),
            "deze_run": len(te_verwerken),
            "resultaten": [],
            "club_onbekend": [],
        }
    resultaten = []
    club_onbekend = []
    for i, p in enumerate(te_verwerken, start=1):
        pid = _norm_id(p.get("player_id"))
        naam = p.get("display_name") or pid
        existing_club = p.get("club") or ""
        club = existing_club or (club_override or "")
        if not club:
            club_onbekend.append({"player_id": pid, "naam": naam})
            logger.warning(
                f"({i}/{len(te_verwerken)}) {naam} ({pid}) -> club onbekend, NIET opgezocht op "
                "padelstats.be. Stel de club/ploeg in voor deze speler (bv. via de per-speler-"
                "verversknop) en probeer opnieuw."
            )
            continue
        used_override = bool(club_override and not existing_club)
        if used_override:
            _backfill_club(pid, club_override)
        override_label = " [club-override]" if used_override else ""
        logger.info(f"({i}/{len(te_verwerken)}) {naam} ({pid}, club='{club}'{override_label})...")
        r = refresh_one(pid, naam, club, dry_run=dry_run)
        resultaten.append(r)
        if r["status"] == "opgehaald":
            note = f" — {r['note']}" if r.get("note") else ""
            klassement_txt = f", officieel klassement P{r['klassement']}" if r.get("klassement") is not None else ""
            logger.info(f"  -> P{r['rating']}{klassement_txt}{note}")
        elif r["status"] == "niet_gevonden":
            logger.info("  -> niet gevonden op padelstats.be")
        else:
            logger.warning(f"  -> {r['status']}: {r.get('note')}")
        if i < len(te_verwerken):
            time.sleep(pause_seconds)
    if club_onbekend:
        namen = ", ".join(f"{x['naam']} ({x['player_id']})" for x in club_onbekend)
        logger.warning(
            f"{len(club_onbekend)} speler(s) overgeslagen wegens onbekende club: {namen}. "
            "Stel de club/ploeg in voor deze speler(s) om playing strength/klassement alsnog te "
            "kunnen ophalen."
        )
    samenvatting = {
        "totaal_profielen": len(profiles),
        "kandidaten": len(alle_kandidaten),
        "deze_run": len(te_verwerken),
        "opgehaald": sum(1 for r in resultaten if r["status"] == "opgehaald"),
        "opgehaald_met_klassement": sum(1 for r in resultaten if r["status"] == "opgehaald" and r.get("klassement") is not None),
        "niet_gevonden": sum(1 for r in resultaten if r["status"] == "niet_gevonden"),
        "fout": sum(1 for r in resultaten if r["status"] in ("fout", "opslaan_mislukt")),
        "club_onbekend": club_onbekend,
        "resterend_na_deze_run": max(0, len(alle_kandidaten) - len(te_verwerken) - len(club_onbekend)),
        "resultaten": resultaten,
    }
    return samenvatting


if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(
        description="Controleert/herstelt de padelstats.be playing strength + officieel klassement "
                    "van alle spelers, los van matchdata- of poule-scraping."
    )
    parser.add_argument("--max", type=int, default=int(os.environ.get("PADELSTAT_MAX", DEFAULT_MAX_PER_RUN)),
                        help=f"Max aantal spelers deze run (standaard {DEFAULT_MAX_PER_RUN}, of env PADELSTAT_MAX).")
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS,
                        help=f"Pauze in seconden tussen spelers (standaard {DEFAULT_PAUSE_SECONDS}).")
    parser.add_argument("--force-all", action="store_true",
                        help="Negeer de versie-marker EN de periodieke staleness-drempel, controleer IEDEREEN opnieuw (traag; gebruik samen met --max).")
    parser.add_argument("--player", type=str, default=None,
                        help="Enkel deze speler(s) controleren, altijd (player_id, of komma-gescheiden lijst).")
    parser.add_argument(
        "--club", type=str, default=(os.environ.get("CLUB", "").strip() or None),
        help="Club-naam als disambiguatie-hint voor spelers in deze run die zelf nog geen club hebben "
             "(overschrijft nooit een reeds bekende club). Nuttig wanneer je --player gebruikt voor een "
             "specifieke, gekende ploeg. Ook als env var CLUB bruikbaar.",
    )
    parser.add_argument(
        "--stale-days", type=int,
        default=int(os.environ.get("PADELSTAT_STALE_DAYS", DEFAULT_STALE_AFTER_DAYS)),
        help=(
            f"Na hoeveel dagen een reeds actuele rating ALSNOG periodiek opnieuw gecontroleerd "
            f"wordt (standaard {DEFAULT_STALE_AFTER_DAYS}, of env PADELSTAT_STALE_DAYS). Zet op 0 "
            "om deze periodieke herhaling uit te schakelen (enkel nog zelfherstel/nieuwe spelers)."
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon enkel wie verwerkt zou worden, scrape niets, schrijf niets weg.")
    args = parser.parse_args()
    resultaat = run(
        max_per_run=args.max,
        pause_seconds=args.pause,
        force_all=args.force_all,
        only_player_id=args.player,
        club_override=args.club,
        dry_run=args.dry_run,
        stale_after_days=args.stale_days,
    )
    print("\n=== Samenvatting padelstat + officieel klassement ===")
    print(f"Totaal profielen        : {resultaat['totaal_profielen']}")
    print(f"Kandidaten (nog te doen) : {resultaat['kandidaten']}")
    print(f"Verwerkt deze run        : {resultaat['deze_run']}")
    if not args.dry_run:
        print(f"  Opgehaald              : {resultaat.get('opgehaald', 0)} (waarvan {resultaat.get('opgehaald_met_klassement', 0)} met officieel klassement)")
        print(f"  Niet gevonden          : {resultaat.get('niet_gevonden', 0)}")
        print(f"  Fout                   : {resultaat.get('fout', 0)}")
        club_onbekend = resultaat.get("club_onbekend") or []
        if club_onbekend:
            namen = ", ".join(f"{x['naam']} ({x['player_id']})" for x in club_onbekend)
            print(f"  Club onbekend (overgeslagen): {len(club_onbekend)} — {namen}")
        print(f"Resterend na deze run    : {resultaat.get('resterend_na_deze_run', 0)}")
        if resultaat.get("resterend_na_deze_run", 0) > 0:
            print(
                f"\n{resultaat['resterend_na_deze_run']} speler(s) volgen bij de VOLGENDE "
                "run — verhoog --max om dit sneller in te lopen."
            )
