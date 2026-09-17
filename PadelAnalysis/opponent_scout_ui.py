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
browser). Daar wordt de bestaande GitHub Actions-trigger getoond in plaats van
een lokale scrape.

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
voor een specifieke tegenstander-ploeg:
  1. De "🔄 Ververs alles voor deze ploeg"-knop werd enkel getoond
     `if ... and can_scrape` — op Cloud is can_scrape ALTIJD False, dus die
     knop verscheen daar NOOIT, ook niet als een placeholder/uitleg.
  2. _ensure_klassement() sloeg intern stilzwijgend alles over zodra
     is_scraping_available() False was (`if not is_scraping_available():
     return`) — GEEN caption, GEEN foutmelding, gewoon niets. Vergelijk dit
     met _ensure_padelstat(), die op zijn minst een caption toont
     ("niet beschikbaar in deze omgeving") — klassement deed zelfs dat niet.
  3. Zelfs de checkbox "📈 Ook klassementshistoriek ophalen" werd enkel
     getoond `else:` (dus enkel als can_scrape True is) — op Cloud is er dus
     ook geen enkele indicatie dat klassement iets is wat je zou kunnen
     aanvinken.
Ondertussen bestaan er, naast scrape-padel.yml (matchdata), TWEE aparte
dagelijkse GitHub Actions-workflows die dit WEL server-side afhandelen:
refresh-padelstat.yml en refresh-klassement.yml (elk met zelfherstel voor
respectievelijk foute/verouderde padelstat-waarden en de "Huidige pagina"-
lege klassement-noodgreep uit de cookiebanner-bug in scrape_klassement.py).
Op Cloud was er echter geen DIRECTE manier om die workflows voor een
specifieke ploeg te triggeren zonder op de dagelijkse cron te wachten.

Fix, drie onderdelen:
  1. cloud_helpers.render_cloud_scrape_trigger()/trigger_github_actions_
     scrape() zijn generiek gemaakt (workflow_file/inputs-parameters, zie
     dat bestand) zodat ELKE workflow met een EIGEN input-schema getriggerd
     kan worden, niet enkel scrape-padel.yml.
  2. render_scout_header() toont nu, WANNEER can_scrape False is (dus op
     Cloud, altijd) EN er al een bundle met tegenstander-spelers bekend is,
     twee directe trigger-knoppen: "📈 Klassement nu ophalen voor deze
     ploeg" (refresh-klassement.yml) en "🎯 Playing strength nu ophalen
     voor deze ploeg" (refresh-padelstat.yml) — elk met de EXACTE
     tegenstander-roster als 'player'-input, zodat je niet 24u op de cron
     hoeft te wachten.
  3. _ensure_klassement() toont nu, i.p.v. stil niets te doen, een
     expliciete caption die uitlegt dat klassement op Cloud via de
     dagelijkse achtergrondtaak (of de directe knop hierboven) binnenkomt.

Beide nieuwe scripts (refresh_klassement_only.py, refresh_padelstat_only.py)
ondersteunen sinds deze fix een KOMMA-GESCHEIDEN --player-lijst, zodat één
workflow-run exact de gevraagde tegenstander-roster target, ongeacht de
normale --max-batchgrootte-cap.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

import streamlit as st

import firebase_service as fb
import lineup_lab as ll
import opponent_analysis as oa
import opponent_scout as osc
import schedule_scraper as ss

try:  # cloud_helpers is optioneel aanwezig; nooit hard falen op import
    from cloud_helpers import is_scraping_available, render_cloud_scrape_trigger
except Exception:  # pragma: no cover
    def is_scraping_available() -> bool:
        return False

    def render_cloud_scrape_trigger(**_kwargs) -> None:
        st.caption("Cloud-trigger niet beschikbaar (cloud_helpers ontbreekt).")

# PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16: optionele import, zodat dit
# bestand blijft werken ook als padelstats_scraper (Playwright-afhankelijk)
# lokaal niet beschikbaar is -- exact hetzelfde patroon als cloud_helpers.
try:
    import padelstats_scraper as pss
except Exception:  # pragma: no cover
    pss = None


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


def _has_incomplete_data(player_id: str) -> tuple[bool, list[str]]:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16.
    Beoordeelt of deze speler nog ONTBREKENDE data heeft, ONGEACHT of hij/zij
    al een profiel heeft (dat is precies wat de oude _is_known()-check niet
    deed). Returns (incompleet, redenen)."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:
        doc = {}
    try:
        profile = fb.get_player_profile(player_id) or {}
    except Exception:
        profile = {}
    redenen = []
    if not doc.get("matches"):
        redenen.append("geen matchhistoriek")
    if not (doc.get("klassement_history") or profile.get("klassement_history")):
        redenen.append("geen klassementshistoriek")
    heeft_padelstat = False
    try:
        cached = fb.get_padelstat_rating(player_id)
        heeft_padelstat = bool(cached and cached.get("rating") is not None)
    except Exception:
        heeft_padelstat = False
    if not heeft_padelstat:
        redenen.append("geen padelstat playing strength")
    return bool(redenen), redenen


def _ensure_klassement(player_ids: list[str], progress_label: str = "Klassement") -> None:
    """Haalt de klassementshistoriek op voor spelers die deze nog niet hebben.
    Enkel lokaal (Playwright vereist, zie is_scraping_available()). Duurt
    ongeveer 30-60s per speler; slaat spelers over die al klassement_history
    hebben, dus een herhaald bezoek kost niets voor reeds gekende spelers.

    PADEL_ANALYSIS_CLOUD_KLASSEMENT_PADELSTAT_TRIGGER_2026-09-17: toont nu,
    i.p.v. STIL niets te doen op Cloud, een expliciete caption die uitlegt
    dat klassement daar via de dagelijkse achtergrondtaak (refresh-
    klassement.yml) of de directe knop in render_scout_header() binnenkomt.
    Dit was voorheen de ENIGE plek in dit bestand die op Cloud he-le-maal
    niets liet blijken — zelfs _ensure_padelstat() toonde al langer een
    caption in datzelfde geval."""
    if not is_scraping_available():
        st.caption(
            "📈 Klassementshistoriek wordt op deze omgeving niet lokaal opgehaald (vereist een "
            "browser). Dit gebeurt automatisch via de dagelijkse achtergrondtaak, of forceer het "
            "meteen met de knop '📈 Klassement nu ophalen voor deze ploeg' hierboven."
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
        st.caption(f"Klassement automatisch ophalen niet beschikbaar: {exc}")
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
            st.write(f"Klassement ophalen mislukt voor speler {pid}: {exc}")
    progress.progress(1.0, text=f"{progress_label}: klaar.")
    _load_all_player_docs.clear()


def _ensure_padelstat(
    players: list[dict],
    progress_label: str = "Padelstat",
    force: bool = False,
) -> dict:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16.
    Haalt de padelstats.be playing strength op voor elke speler in `players`
    ({"user_id":..., "name":...}). Slaat spelers met een gecachete rating
    over, tenzij force=True. Gebruikt hun club uit het Firestore-profiel
    (indien gekend) om gelijknamige spelers te disambigueren -- zelfde
    mechanisme als padelstats_scraper.search_and_fetch_padelstat_rating().
    Enkel lokaal beschikbaar (Playwright vereist)."""
    result = {"opgehaald": 0, "cache": 0, "niet_gevonden": 0, "fout": 0}
    if not is_scraping_available() or pss is None:
        st.caption(
            "Padelstat automatisch ophalen niet beschikbaar in deze omgeving (vereist een lokale "
            "browser). Dit gebeurt automatisch via de dagelijkse achtergrondtaak, of forceer het "
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
        club = profiel.get("club") or ""
        try:
            gevonden = pss.search_and_fetch_padelstat_rating(naam, club=club or None)
        except Exception as exc:
            st.write(f"Padelstat ophalen mislukt voor {naam}: {exc}")
            result["fout"] += 1
            continue
        if not gevonden or gevonden.get("rating") is None:
            st.write(f"Geen padelstat gevonden voor {naam}.")
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
                st.caption(f"⚠️ {naam}: {gevonden['club_disambiguation_note']}")
        except Exception as exc:
            st.write(f"Padelstat opslaan mislukt voor {naam}: {exc}")
            result["fout"] += 1
    progress.progress(1.0, text=f"{progress_label}: klaar.")
    return result


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
    (render_team_refresh_button / _run_full_team_refresh)."""
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
                    f"{len(unknown)} speler(s) nog niet gescrapet. Scrapen gebeurt hier "
                    "niet: deze omgeving heeft geen browser."
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
                        st.write(f"Mislukt: {item.get('name')} - {item.get('error')}")
                except Exception as exc:
                    progress.empty()
                    st.write(f"Scrapen mislukt: {exc}")
        else:
            st.write("Alle spelers zijn al gekend qua matchdata.")
        if fetch_klassement:
            st.write("Klassementshistoriek controleren/ophalen...")
            all_ids = [p["user_id"] for p in bundle.get("unique_players", []) or []]
            _ensure_klassement(all_ids, progress_label="Klassement")
        status.update(label="Analyse afgerond", state="complete")
        return bundle


def _run_full_team_refresh(
    unique_players: list[dict],
    lookback_periods: int = 3,
    force: bool = False,
) -> dict:
    """PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16.
    Voor ELKE speler in unique_players (ongeacht een reeds bestaand profiel):
      1. matchdata (her)scrapen met `lookback_periods` periodes;
      2. padelstat playing strength ophalen/vernieuwen;
      3. klassementshistoriek ophalen/vernieuwen.
    Dit is de "trage maar volledige" tegenhanger van
    osc.scrape_new_opponent_players(), specifiek om spelers te herstellen die
    al een (onvolledig) profiel hebben -- exact het scenario dat de gewone
    'Tegenstander analyseren'-knop stil overslaat.
    PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17: gebruikt nu
    osc._ensure_profile_safe() i.p.v. een kale fb.save_player_profile()-
    aanroep, zodat een bestaande club nooit meer stilzwijgend gewist wordt
    en elk aangeraakt profiel een added_by-marker krijgt indien nog afwezig.
    Zie de uitgebreide toelichting in opponent_scout.py's moduledocstring.
    LET OP: deze functie wordt enkel getoond/gebruikt als can_scrape True is
    (lokaal). Op Cloud gebruik i.p.v. hiervan de directe GitHub Actions-
    trigger-knoppen in render_scout_header() (PADEL_ANALYSIS_CLOUD_
    KLASSEMENT_PADELSTAT_TRIGGER_2026-09-17)."""
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
    st.write("Padelstat playing strength ophalen/vernieuwen...")
    result["padelstat"] = _ensure_padelstat(unique_players, progress_label="Padelstat", force=force)
    st.write("Klassementshistoriek ophalen/vernieuwen...")
    all_ids = [p["user_id"] for p in unique_players]
    _ensure_klassement(all_ids, progress_label="Klassement")
    result["klassement_gestart"] = True
    return result


def _render_cloud_klassement_padelstat_triggers(unique_players: list[dict]) -> None:
    """PADEL_ANALYSIS_CLOUD_KLASSEMENT_PADELSTAT_TRIGGER_2026-09-17.

    Toont, enkel wanneer scraping hier niet lokaal beschikbaar is (dus op
    Cloud) EN er al een tegenstander-roster gekend is, twee directe
    trigger-knoppen om refresh-klassement.yml en refresh-padelstat.yml
    ONMIDDELLIJK te starten voor EXACT deze ploeg — i.p.v. te moeten wachten
    op de eerstvolgende dagelijkse cron-run. Verschijnt enkel als er een
    GitHub-token geconfigureerd is (render_cloud_scrape_trigger regelt dat
    zelf, toont anders gewoon niets)."""
    if not unique_players:
        return
    player_ids_csv = ",".join(str(p["user_id"]) for p in unique_players if p.get("user_id"))
    if not player_ids_csv:
        return
    col_klass, col_padelstat = st.columns(2)
    with col_klass:
        render_cloud_scrape_trigger(
            key_prefix="scout_klassement_trigger",
            workflow_file="refresh-klassement.yml",
            inputs={"player": player_ids_csv, "max": str(len(unique_players)), "force_all": "false"},
            label="📈 Klassement nu ophalen voor deze ploeg",
            help_text=(
                "Start refresh-klassement.yml op GitHub Actions voor exact deze tegenstander-spelers "
                "(duurt meestal enkele minuten, i.p.v. te wachten op de dagelijkse run)."
            ),
        )
    with col_padelstat:
        render_cloud_scrape_trigger(
            key_prefix="scout_padelstat_trigger",
            workflow_file="refresh-padelstat.yml",
            inputs={"player": player_ids_csv, "max": str(len(unique_players)), "force_all": "false"},
            label="🎯 Playing strength nu ophalen voor deze ploeg",
            help_text=(
                "Start refresh-padelstat.yml op GitHub Actions voor exact deze tegenstander-spelers."
            ),
        )


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
    CLOUD (can_scrape False) i.p.v. daarvan de directe GitHub Actions-
    trigger-knoppen voor klassement/padelstat (_render_cloud_klassement_
    padelstat_triggers()).
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
            "Deze omgeving kan zelf niet scrapen. Nieuwe spelers, playing strength en klassement "
            "worden opgehaald via de dagelijkse achtergrondtaken op GitHub Actions, of forceer dat "
            "hieronder direct voor deze ploeg."
        )
    else:
        fetch_klassement = st.checkbox(
            "📈 Ook klassementshistoriek ophalen (lokaal, ±30-60s per nog onbekende speler)",
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
                    "Herhaalt matchdata (meerdere periodes), padelstat en "
                    "klassement voor ALLE spelers van deze ploeg, ook wie al "
                    "een (onvolledig) profiel heeft. Trager dan 'Tegenstander "
                    "analyseren', maar slaat niemand over."
                ),
            ):
                with st.status("Volledige ploeg verversen...", expanded=True) as status:
                    refresh_result = _run_full_team_refresh(
                        bundle["unique_players"], lookback_periods=3, force=False,
                    )
                    p = refresh_result["padelstat"]
                    st.write(
                        f"Matchdata: {refresh_result['matchdata_ok']}/{refresh_result['totaal']} OK"
                        + (f", {len(refresh_result['matchdata_fout'])} mislukt" if refresh_result["matchdata_fout"] else "")
                    )
                    st.write(
                        f"Padelstat: {p.get('opgehaald', 0)} opgehaald, {p.get('cache', 0)} al gekend, "
                        f"{p.get('niet_gevonden', 0)} niet gevonden, {p.get('fout', 0)} fout"
                    )
                    for item in refresh_result["matchdata_fout"]:
                        st.write(f"⚠️ {item['name']}: {item['error']}")
                    status.update(label="Volledige ploeg ververst", state="complete")
                _load_all_player_docs.clear()
                st.rerun()

    if not bundle:
        return None
    if bundle.get("note"):
        st.info(bundle["note"])
        st.caption(
            "Zonder historische tegenstander-data kan enkel de eigen ploeg-sterkte "
            "getoond worden, niet die van hen."
        )

    # PADEL_ANALYSIS_CLOUD_KLASSEMENT_PADELSTAT_TRIGGER_2026-09-17: op Cloud
    # (can_scrape False) tonen we hier de directe GitHub Actions-triggers
    # i.p.v. de lokale "Ververs alles"-knop hierboven, die op Cloud nooit
    # verschijnt.
    if bundle.get("unique_players") and not can_scrape:
        _render_cloud_klassement_padelstat_triggers(bundle["unique_players"])

    # PADEL_ANALYSIS_TEAM_FULL_REFRESH_2026-09-16: signaleer expliciet als
    # er, ondanks een bestaande bundle, nog spelers met onvolledige data
    # tussen zitten -- dit is precies het signaal dat "Ververs alles" nodig
    # heeft, zonder dat je zelf per speler moet controleren.
    if bundle.get("unique_players"):
        onvolledig = []
        for pl in bundle["unique_players"]:
            incompleet, redenen = _has_incomplete_data(pl["user_id"])
            if incompleet:
                onvolledig.append((pl.get("name") or pl["user_id"], redenen))
        if onvolledig:
            with st.expander(f"⚠️ {len(onvolledig)} speler(s) met onvolledige data", expanded=False):
                for naam, redenen in onvolledig:
                    st.write(f"- **{naam}**: {', '.join(redenen)}")
                if can_scrape:
                    st.caption("Gebruik de knop '🔄 Ververs alles voor deze ploeg' hierboven om dit op te lossen.")
                else:
                    st.caption(
                        "Gebruik de knoppen '📈 Klassement nu ophalen' / '🎯 Playing strength nu ophalen' "
                        "hierboven om dit direct op te lossen, of wacht op de dagelijkse achtergrondtaak."
                    )

    return bundle, opp


def prepare_team_docs(
    bundle: dict,
    sel_player_id: str,
) -> tuple[dict, dict]:
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14: toont de 'nog niet
    gekende spelers'-caption/cloud-trigger (indien van toepassing) en bouwt
    all_docs (matchdata van de tegenstander-roster) + global_docs (brede
    cache, voor de ranking-fallback in opponent_dossier). Geeft
    (all_docs, global_docs) terug voor gebruik door
    opponent_analysis.get_team_report()."""
    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        return {}, {}
    unknown_ids = {player["user_id"] for player in _unknown_players(bundle)}
    all_docs = ll.get_docs_for_players([p["user_id"] for p in unique_players])
    if unknown_ids:
        st.caption(f"⚠️ {len(unknown_ids)} speler(s) nog niet volledig gekend qua matchdata.")
        if not is_scraping_available():
            render_cloud_scrape_trigger(
                key_prefix=f"scout_scrape_{sel_player_id}",
                player_ids=",".join(sorted(unknown_ids)),
                mode="missing",
                label="🚀 Nieuwe tegenstanders ophalen",
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
