"""
team_freshness.py — PADEL_ANALYSIS_TEAM_FRESHNESS_CHECK_2026-09-19 (Fase D3,
op verzoek van Kim, chat 2026-09-19): "D3. Freshness-check bij elke analyse
i.p.v. enkel manueel verversen — gebaseerd op aantal matchen + tijdstip
laatste padelstat-check."

Doel: een team-analyse (zowel de eerstvolgende tegenstander in
opponent_scout_ui.py als een willekeurige poule-ploeg in poule_teams_ui.py)
toont voortaan AUTOMATISCH, zonder dat de gebruiker daar zelf naar moet
zoeken, of de getoonde data mogelijk verouderd is — op basis van TWEE
concrete, onafhankelijke signalen:

  1. AANTAL MATCHEN: heeft deze ploeg intussen MEER wedstrijden gespeeld dan
     waarop de huidige analyse gebaseerd is? Zo ja, dan kunnen er
     NIEUWE/ANDERE spelers meegespeeld hebben die nog niet in de huidige
     analyse zitten (exact Kim's aandachtspunt: "een ploeg kan plots extra
     spelers gebruikt hebben").
  2. TIJDSTIP LAATSTE PADELSTAT-CHECK: is de gecachete playing-strength-
     waarde van 1 of meer spelers in de roster ouder dan
     PADELSTAT_STALE_AFTER_DAYS? Dit is BEWUST dezelfde drempel/conventie
     als enrich_opponents.py se PADELSTAT_STALE_AFTER_DAYS (de wekelijkse
     achtergrondtaak en de nachtelijke poule-pre-scan, zie
     discover_poule_players.py / prescan-poule.yml) — dit bestand HERHAALT
     die waarde bewust als eigen constante (i.p.v. enrich_opponents.py te
     importeren, dat in scraper/ ligt en conceptueel scraper-georiënteerd
     is) zodat de Streamlit-UI dit puur als DATA-CHECK kan uitvoeren, zonder
     enige Playwright-afhankelijkheid — dit bestand doet zelf NOOIT iets
     scrapen, het leest enkel reeds gecachete Firestore-velden.

BELANGRIJK ONDERSCHEID met de reeds bestaande
opponent_analysis._underlying_data_is_fresher(): die functie detecteert of
het LOKAAL BEREKENDE RAPPORT (team_scouting_reports) achterloopt op reeds
ELDERS ververste onderliggende data (bv. na een achtergrond-verversing) —
dus "is mijn WEERGAVE up-to-date met wat we al weten". DEZE module
detecteert een ANDER soort veroudering: "is wat we WETEN zelf nog
betrouwbaar/actueel genoeg" (is de brondata bij padelstats.be intussen
veranderd, zijn er intussen nieuwe wedstrijden gespeeld). Beide zijn nodig
en vullen elkaar aan — dit bestand raakt _underlying_data_is_fresher() niet
aan.

Dit bestand triggert NOOIT zelf een verversing — het berekent enkel een
status en toont een informatieve banner. De effectieve actie blijft de
reeds bestaande, gecombineerde "🔄 Ontbrekende gegevens ophalen"-knop (Fase
C, opponent_scout_ui._render_unified_team_sync_trigger()) — deze module
nudge't de gebruiker enkel proactief naar die knop, in plaats van te
vertrouwen op het feit dat de gebruiker uit zichzelf op "Verversen" klikt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import streamlit as st

import firebase_service as fb

try:
    import schedule_scraper as ss
except Exception:  # pragma: no cover
    ss = None

# PADEL_ANALYSIS_TEAM_FRESHNESS_CHECK_2026-09-19: BEWUST dezelfde waarde als
# enrich_opponents.PADELSTAT_STALE_AFTER_DAYS (scraper/enrich_opponents.py) —
# hou deze twee constanten gesynchroniseerd als je de ene ooit aanpast.
PADELSTAT_STALE_AFTER_DAYS = 14

PRESCAN_STATE_COLLECTION = "app_state"
PRESCAN_STATE_DOC = "poule_prescan_state"


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        cleaned = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _padelstat_age_days(cached: Optional[dict]) -> Optional[float]:
    """Geeft de leeftijd (in dagen) van de gecachete padelstat-waarde terug,
    of None als er geen bruikbare rating/tijdstempel is."""
    if not cached or cached.get("rating") is None:
        return None
    fetched_at = _parse_iso(cached.get("fetched_at"))
    if fetched_at is None:
        return None
    age = datetime.now(timezone.utc) - fetched_at
    return age.total_seconds() / 86400.0


def stale_padelstat_players(
    unique_players: list[dict], stale_after_days: int = PADELSTAT_STALE_AFTER_DAYS,
) -> list[dict]:
    """Geeft de subset van `unique_players` terug ({"user_id":..., "name":...})
    waarvan de gecachete padelstat-waarde OUDER is dan `stale_after_days`, OF
    waarvoor helemaal geen tijdstempel gekend is (conservatief: liever een
    keer te veel als 'onzeker' gemeld dan een stilzwijgend verouderd getal).
    Spelers ZONDER enige rating worden hier NIET meegeteld — dat is een
    'ontbrekend'-geval (Fase C, _data_completeness()), geen 'verouderd'-geval."""
    stale = []
    for p in unique_players or []:
        pid = str(p.get("user_id") or "")
        if not pid:
            continue
        try:
            cached = fb.get_padelstat_rating(pid)
        except Exception:
            cached = None
        if not cached or cached.get("rating") is None:
            continue  # ontbrekend, geen 'verouderd' — hoort bij Fase C
        age_days = _padelstat_age_days(cached)
        if age_days is None or age_days > stale_after_days:
            stale.append(p)
    return stale


def team_played_count(fixtures: list[dict], ploeg_id: str) -> int:
    """Aantal AL GESPEELDE wedstrijden van deze ploeg volgens de meegegeven
    (live/actueel geladen) fixtures-lijst."""
    if ss is None or not fixtures or not ploeg_id:
        return 0
    team_fixtures = ss.get_team_fixtures(fixtures, ploeg_id)
    return sum(1 for fx in team_fixtures if fx.get("played"))


def team_freshness_status(
    unique_players: list[dict],
    fixtures: Optional[list[dict]] = None,
    ploeg_id: Optional[str] = None,
    known_played_count: Optional[int] = None,
    stale_after_days: int = PADELSTAT_STALE_AFTER_DAYS,
) -> dict:
    """Berekent de volledige freshness-status voor 1 ploeg-analyse.

    known_played_count: het aantal gespeelde wedstrijden waarop de HUIDIGE,
    al getoonde analyse gebaseerd is (bv. len(bundle["previous_fixtures"])
    bij een lookback=alle-gespeelde-wedstrijden-aanpak zoals in
    poule_teams_ui.py). Geef dit weg (None) als dat niet van toepassing is
    (bv. de eerstvolgende tegenstander gebruikt bewust een vaste lookback=1,
    dus een 'aantal matchen'-vergelijking is daar niet zinvol) — dan wordt
    enkel de padelstat-staleness gecontroleerd.

    Returns:
        {
          "stale_padelstat": [...],          # lijst spelers-dicts
          "stale_padelstat_count": int,
          "new_matches_detected": bool,
          "n_played_now": Optional[int],
          "n_played_known": Optional[int],
          "is_stale": bool,                  # samengevat, voor UI-gemak
        }
    """
    stale_players = stale_padelstat_players(unique_players, stale_after_days)
    new_matches_detected = False
    n_played_now = None
    if known_played_count is not None and fixtures is not None and ploeg_id:
        n_played_now = team_played_count(fixtures, ploeg_id)
        new_matches_detected = n_played_now > known_played_count
    return {
        "stale_padelstat": stale_players,
        "stale_padelstat_count": len(stale_players),
        "new_matches_detected": new_matches_detected,
        "n_played_now": n_played_now,
        "n_played_known": known_played_count,
        "is_stale": bool(stale_players) or new_matches_detected,
    }


def render_freshness_banner(status: dict, key_prefix: str = "") -> None:
    """Toont een korte, informatieve banner op basis van team_freshness_
    status(). Onderneemt zelf GEEN actie — verwijst enkel naar de bestaande
    '🔄 Ontbrekende gegevens ophalen'-knop verderop op de pagina."""
    if not status.get("is_stale"):
        return
    parts = []
    if status.get("new_matches_detected"):
        n_now = status.get("n_played_now")
        n_known = status.get("n_played_known")
        parts.append(
            f"deze ploeg speelde intussen {n_now} wedstrijd(en) (was {n_known} bij de laatste "
            "analyse) — mogelijk met nieuwe/andere spelers"
        )
    n_stale = status.get("stale_padelstat_count", 0)
    if n_stale:
        namen = ", ".join(p.get("name", "?") for p in status["stale_padelstat"][:5])
        extra = "" if n_stale <= 5 else f" en {n_stale - 5} andere(n)"
        parts.append(f"playing strength van {n_stale} speler(s) is ouder dan {PADELSTAT_STALE_AFTER_DAYS} dagen ({namen}{extra})")
    st.warning(
        "🔄 Deze analyse kan verouderd zijn: " + "; ".join(parts) + ". Gebruik de knop "
        "'🔄 Ontbrekende gegevens ophalen' hieronder om dit bij te werken."
    )


def get_last_prescan_summary() -> Optional[dict]:
    """PADEL_ANALYSIS_TEAM_FRESHNESS_CHECK_2026-09-19: leest het
    samenvattingsdocument dat discover_poule_players.py (Fase D2) na elke
    nachtelijke poule-pre-scan wegschrijft, voor een 'laatst automatisch
    ververst op...'-caption in de UI."""
    try:
        doc = fb.db.collection(PRESCAN_STATE_COLLECTION).document(PRESCAN_STATE_DOC).get()
        return doc.to_dict() if doc.exists else None
    except Exception:
        return None


def _format_ts(value) -> str:
    if not value:
        return "onbekend"
    try:
        cleaned = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


def render_last_prescan_caption() -> None:
    """Toont, indien beschikbaar, wanneer de nachtelijke poule-pre-scan
    (Fase D2) voor het laatst liep — puur informatief."""
    summary = get_last_prescan_summary()
    if not summary:
        return
    st.caption(
        f"ℹ️ Achtergrond-poule-scan laatst uitgevoerd op {_format_ts(summary.get('last_run_at'))} "
        f"({summary.get('teams_found', 0)} ploeg(en), {summary.get('players_found_total', 0)} speler(s) bekeken)."
    )
