"""
freshness_cache.py — sessie-lokale, TTL-gebaseerde cache voor de padelstat/
klassement "is dit ondertussen ververst?"-check uit opponent_analysis.py.

Locatie: PadelAnalysis/freshness_cache.py (naast opponent_analysis.py)

--------------------------------------------------------------------------
PADEL_ANALYSIS_SPARK_QUOTA_CACHE_2026-09-17 (op verzoek van Kim: "ik zit op
Spark, bouw de gecachte laag")
--------------------------------------------------------------------------
WAAROM DIT NODIG IS
--------------------------------------------------------------------------
Kim gebruikt het Firebase SPARK-plan (het gratis tier). Concreet betekent
dat:
  - Firestore heeft een HARDE DAGLIMIET: 50.000 reads, 20.000 writes,
    20.000 deletes per dag (24u, Pacific Time). Erboven werkt de app
    gewoonweg niet meer tot de teller om middernacht resest - geen
    automatische facturering, een échte blokkade van de hele app.
  - Cloud Functions kunnen op Spark GEEN uitgaande netwerkverbindingen
    maken (dat vereist het betaalde Blaze-plan). Een eigen Cloud Function
    als klassement-scraper is dus GEEN optie - scrapen moet buiten
    Firebase gebeuren (GitHub Actions, zoals nu al voor padelstat en
    matchdata).

opponent_analysis._underlying_data_is_fresher() (PADEL_ANALYSIS_TEAM_REPORT_
STALE_CACHE_FIX_2026-09-17) doet voor ELKE speler in een tegenploeg 2
Firestore-reads (padelstat-rating + player-document voor klassement), bij
ELKE render van de pagina. Streamlit rerendert bij vrijwel elke widget-
interactie (elke klik, elke tekstinvoer, elke st.rerun()) - bij een team
van bv. 12 spelers is dat al 24 reads per rerun. Een gebruiker die tijdens
1 sessie een tiental keer interageert met de opstelling-analyse, produceert
zo 240+ reads - dat telt op bovenop ALLES ANDERS wat de app leest
(matchdata, poule-schema's, spelerslijsten, ...) en schaalt lineair met het
aantal spelers in de ploeg EN het aantal reruns.

--------------------------------------------------------------------------
DE OPLOSSING: EEN SESSIE-LOKALE TTL-CACHE (st.session_state, GEEN
st.cache_data)
--------------------------------------------------------------------------
Bewust GEEN st.cache_data gebruikt: die cachet GLOBAAL over ALLE
gebruikers/sessies heen, en biedt geen eenvoudige, gegarandeerde manier om
1 specifieke speler te "vergeten" na een refresh-actie (enkel de VOLLEDIGE
cache leegmaken via .clear()). Deze module gebruikt in plaats daarvan
st.session_state, zodat:
  1. binnen 1 sessie, binnen het TTL-venster (standaard 90s), een speler
     NOOIT twee keer bevraagd wordt, ongeacht hoeveel reruns er gebeuren
     (het belangrijkste quota-voordeel: de check kost normaliter maar 1x
     per speler per ~anderhalve minuut, niet 1x per klik);
  2. na een expliciete refresh-actie (bv. "Ververs alles voor deze ploeg")
     de cache voor PRECIES die speler (of de hele ploeg) onmiddellijk
     ongeldig gemaakt kan worden via invalidate()/invalidate_all(), zodat
     de UI de nieuwe data meteen ziet zonder op het TTL te moeten wachten;
  3. de cache automatisch verdwijnt bij een nieuwe browsersessie - geen
     risico op een voor altijd verouderde cache op langere termijn (dat is
     nu net wat deze laag moet helpen VOORKOMEN, niet veroorzaken).

BELANGRIJK - wat deze cache WEL en NIET beïnvloedt:
Deze cache wordt uitsluitend gebruikt voor de "moet het team-rapport
herbouwd worden?"-BESLISSING in opponent_analysis._underlying_data_is_
fresher(). De WERKELIJKE opbouw van het rapport (_build_report ->
opponent_dossier.build_player_summary) blijft rechtstreeks uit Firestore
lezen, ONGECACHET - dus zodra er effectief herbouwd wordt, zijn de getoonde
waarden altijd de actuele. Deze laag maakt enkel de "moet ik controleren of
er iets veranderd is?"-vraag zelf goedkoper, niet de data die uiteindelijk
getoond wordt.

Gebruik:
    import freshness_cache as fc
    info = fc.get_freshness("1759548")
    # {"padelstat_fetched_at": "...", "klassement_scraped_at": "..." }
    fc.invalidate("1759548")   # na een gerichte refresh van 1 speler
    fc.invalidate_all()        # na "Ververs alles voor deze ploeg"

--------------------------------------------------------------------------
PADEL_ANALYSIS_MISSING_FROM_GIT_2026-09-18 (op verzoek van Kim: "ik krijg
met de laatste commit nu error in cloud: ModuleNotFoundError: No module
named 'freshness_cache'")
--------------------------------------------------------------------------
ROOT CAUSE: dit bestand zelf bevat GEEN fout - het is inhoudelijk identiek
aan de versie die eerder al werd aangeleverd en getest. De fout wijst erop
dat freshness_cache.py wel op Kim's lokale schijf staat (opponent_analysis.py
importeert het en werkt lokaal), maar nooit werd toegevoegd aan de laatste
git-commit/-push - waardoor de cloud-deploy (die enkel bestanden ziet die
effectief in de repo staan) het bestand niet vindt. Dit is dus GEEN
codefix maar een committing-stap: zorg dat freshness_cache.py mee
opgenomen wordt in `git add` vóór de volgende push (zie de commit-
commando's onderaan het antwoord waarin dit bestand werd aangeleverd).
"""
from __future__ import annotations

import time
from typing import Optional

import streamlit as st

import firebase_service as fb

# Hoe lang een gecachet resultaat geldig blijft voor er opnieuw uit
# Firestore gelezen wordt. 90s is een compromis: lang genoeg om een reeks
# snelle reruns (bv. tijdens het invullen van de opstelling-scenario's) maar
# 1x te laten kosten, kort genoeg om een net ververste speler binnen
# dezelfde sessie toch vlot te zien verschijnen zonder handmatige actie.
DEFAULT_TTL_SECONDS = 90

_SESSION_KEY = "_freshness_cache_v1"


def _norm_id(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _store() -> dict:
    """Geeft de sessie-lokale cache-dict terug, aangemaakt bij eerste gebruik.
    Leeft in st.session_state, dus automatisch weg bij een nieuwe sessie."""
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = {}
    return st.session_state[_SESSION_KEY]


def get_freshness(player_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    """Geeft {"padelstat_fetched_at": ..., "klassement_scraped_at": ...}
    terug voor deze speler. Binnen het TTL-venster wordt dit uit de
    sessie-cache gehaald (0 Firestore-reads); daarbuiten wordt er 1x
    (2 Firestore-reads) opnieuw gelezen en het resultaat hercachet.

    Geeft nooit een exception door - bij een Firestore-fout wordt een lege
    dict teruggegeven (behandeld als 'niets bekend', dus conservatief) en
    NIET gecachet, zodat een volgende poging het gewoon opnieuw probeert."""
    pid = _norm_id(player_id)
    store = _store()
    entry = store.get(pid)
    now = time.monotonic()
    if entry is not None and (now - entry["checked_at"]) < ttl_seconds:
        return entry["data"]
    data = {"padelstat_fetched_at": None, "klassement_scraped_at": None}
    read_ok = True
    try:
        cached_padelstat = fb.get_padelstat_rating(pid)
        if cached_padelstat:
            data["padelstat_fetched_at"] = cached_padelstat.get("fetched_at")
    except Exception:  # noqa: BLE001
        read_ok = False
    try:
        player_doc = fb.get_player(pid) or {}
        klassement = player_doc.get("klassement_history")
        if isinstance(klassement, dict):
            data["klassement_scraped_at"] = klassement.get("scraped_at")
    except Exception:  # noqa: BLE001
        read_ok = False
    if read_ok:
        store[pid] = {"checked_at": now, "data": data}
    return data


def invalidate(player_id: str) -> None:
    """Maakt de cache voor 1 specifieke speler ongeldig, zodat de eerstvolgende
    get_freshness()-aanroep voor die speler gegarandeerd opnieuw uit
    Firestore leest, ongeacht het TTL-venster. Roep dit aan meteen na een
    gerichte refresh-actie voor die ene speler (bv. na een geslaagde
    padelstat- of klassement-scrape)."""
    _store().pop(_norm_id(player_id), None)


def invalidate_all() -> None:
    """Maakt de VOLLEDIGE sessie-cache ongeldig. Roep dit aan na een
    "Ververs alles voor deze ploeg"-actie, zodat de daaropvolgende
    freshness-check voor élke speler in die ploeg gegarandeerd de
    net-geschreven data ziet."""
    st.session_state[_SESSION_KEY] = {}


def cache_size() -> int:
    """Aantal spelers momenteel in de sessie-cache - vooral handig voor
    debug-doeleinden (bv. tonen in een expander tijdens ontwikkeling)."""
    return len(_store())
