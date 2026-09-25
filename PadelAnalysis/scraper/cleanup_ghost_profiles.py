"""
cleanup_ghost_profiles.py — verwijdert spelersprofielen die geen enkele
relevantie (meer) hebben.

Locatie: PadelAnalysis/scraper/cleanup_ghost_profiles.py
(naast enrich_opponents.py / ci_scrape_all.py, zelfde path-setup patroon)

--------------------------------------------------------------------------
GESCHIEDENIS
--------------------------------------------------------------------------
PADEL_ANALYSIS_INTERCLUB_ONLY_DISCOVERY_2026-09-16 loste de STRUCTURELE
oorzaak op (discover_opponent_players() ontdekt sindsdien enkel nog
interclub-tegenstanders, geen eenmalige tornooi-tegenstanders meer).

PADEL_ANALYSIS_SCOUT_GHOST_CLEANUP_2026-09-17 breidde de opruiming uit met
een tweede added_by-marker ("opponent_scout", naast "auto_opponent_
discovery"), voor profielen aangemaakt via de "Tegenstander analyseren"-knop.

--------------------------------------------------------------------------
PADEL_ANALYSIS_LEGACY_GHOST_NO_MARKER_2026-09-17 (op verzoek van Kim, tweede
keer deze dag)
--------------------------------------------------------------------------
BUG (opgelost): een dry-run op 17 september toonde "Geen spookprofielen
gevonden", terwijl check_player_data.py --team-of tegelijk 50+ spelers toonde
die VOLLEDIG leeg waren (geen matchdata, geen padelstat, geen klassement,
geen club) -- exact het soort profiel dat opgeruimd zou moeten worden.

Oorzaak: deze profielen zijn aangemaakt VOOR de added_by-markers uberhaupt
bestonden (dus vooraleer PADEL_ANALYSIS_SCOUT_PROFILE_INTEGRITY_2026-09-17 en
de eerdere PADEL_ANALYSIS_GHOST_CLEANUP_TIMESTAMP_2026-09-16 werden
toegevoegd). Ze hebben dus HELEMAAL GEEN added_by-veld. De vorige versie van
dit script behandelde "geen added_by-veld" bewust als "onbekende oorsprong,
dus NOOIT opruimen" -- een terechte voorzichtigheidsregel voor profielen die
mogelijk bewust/handmatig zijn aangemaakt, maar te streng voor deze
specifieke, overduidelijk lege categorie.

Fix: een TWEEDE, apart criterium (naast het bestaande AUTO_DISCOVERED_
MARKERS-pad) dat een profiel ZONDER added_by-veld ALSNOG als opruimbaar
beschouwt, MITS het aan ALLE ANDERE bestaande voorwaarden voldoet (geen
matchdata, geen padelstat, geen klassement, geen club, geen handmatige
poule-URL, oud genoeg). Een profiel zonder added_by MAAR met bijvoorbeeld een
club, of matchdata, of een klassement, wordt nog steeds NOOIT aangeraakt --
dat onderscheidt een oud ghost-profiel (zuiver een naam + player_id, verder
niets) van een oud, bewust/handmatig aangemaakt profiel (dat typisch wél een
club en/of matchdata heeft).

Zie find_ghost_profiles() voor de volledige, exacte logica.

--------------------------------------------------------------------------
WAT DIT SCRIPT WEL EN NIET VERWIJDERT
--------------------------------------------------------------------------
Verwijderd wordt een profiel dat:
  A) added_by in {"auto_opponent_discovery", "opponent_scout"}, OF
  B) HELEMAAL GEEN added_by-veld heeft EN ook GEEN club heeft (het
     "legacy ghost, van voor de added_by-markers"-pad);
  EN in BEIDE gevallen bijkomend:
  2. GEEN matches heeft op het bijhorende players-document;
  3. GEEN padelstat-rating en GEEN klassement_history heeft;
  4. NIET de opgeslagen poule_reeks_url_manual heeft ingesteld;
  5. Oud genoeg is (discovered_at ontbreekt OF ouder dan --min-age-days).

NOOIT verwijderd: added_by="manual", of een profiel zonder added_by-veld
dat WEL een club heeft (die combinatie wijst op een oud, bewust aangemaakt
profiel, niet op een automatisch ontdekte ghost).

Standaard draait dit script in --dry-run. Pas met --execute wordt er ook
effectief verwijderd (uit zowel player_profiles als players).

--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    python cleanup_ghost_profiles.py --dry-run
    python cleanup_ghost_profiles.py --execute
"""

from __future__ import annotations

import logging
import sys
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

DEFAULT_MIN_AGE_DAYS = 3

# Markers die expliciet aangeven dat een profiel automatisch ontdekt is.
AUTO_DISCOVERED_MARKERS = {"auto_opponent_discovery", "opponent_scout"}


def _norm_id(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


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


def _home_player_id() -> Optional[str]:
    """Nooit het eigen 'Dit ben ik'-profiel als ghost beschouwen — extra
    veiligheidslaag bovenop de added_by-check."""
    try:
        settings = fb.get_app_settings() or {}
        return _norm_id(settings.get("home_player_id")) or None
    except Exception:  # noqa: BLE001
        return None


def _is_eligible_by_origin(profile: dict) -> tuple[bool, str]:
    """PADEL_ANALYSIS_LEGACY_GHOST_NO_MARKER_2026-09-17.

    Beoordeelt UITSLUITEND de "oorsprong"-voorwaarde (los van de overige
    criteria zoals matchdata/padelstat/klassement, die apart gecontroleerd
    worden in find_ghost_profiles()). Returns (in_aanmerking, reden_label).

    Pad A: expliciete added_by-marker -> altijd in aanmerking.
    Pad B: HELEMAAL geen added_by-veld EN ook geen club -> waarschijnlijk een
           legacy ghost-profiel van voor de added_by-markers bestonden, dus
           ook in aanmerking. Een ontbrekend added_by-veld MET een club
           blijft wél buiten beschouwing (te onzeker: kan een oud, bewust
           toegevoegd profiel zijn)."""
    added_by = profile.get("added_by")
    if added_by in AUTO_DISCOVERED_MARKERS:
        return True, added_by

    if not added_by and not (profile.get("club") or "").strip():
        return True, "legacy_no_marker"

    return False, ""


def find_ghost_profiles(
    min_age_days: int = DEFAULT_MIN_AGE_DAYS,
) -> list:
    """Vindt alle profielen die aan ALLE criteria in de moduledocstring
    voldoen. Returns een lijst van dicts met diagnose-info."""
    now = datetime.now(timezone.utc)
    home_id = _home_player_id()
    profiles = _all_profiles()
    kandidaten = []

    for profile in profiles:
        player_id = _norm_id(profile.get("player_id"))
        if not player_id:
            continue
        if home_id and player_id == home_id:
            continue

        eligible, origin_reason = _is_eligible_by_origin(profile)
        if not eligible:
            continue

        if (profile.get("poule_reeks_url_manual") or "").strip():
            continue
        if profile.get("klassement_history"):
            continue

        try:
            padelstat = fb.get_padelstat_rating(player_id)
        except Exception:  # noqa: BLE001
            padelstat = None
        if padelstat and padelstat.get("rating") is not None:
            continue

        try:
            player_doc = fb.get_player(player_id) or {}
        except Exception:  # noqa: BLE001
            player_doc = {}
        if player_doc.get("matches"):
            continue
        if player_doc.get("klassement_history"):
            continue

        discovered_at_raw = profile.get("discovered_at")
        discovered_at = _parse_iso(discovered_at_raw)
        if discovered_at is not None:
            age_days = (now - discovered_at).total_seconds() / 86400
            if age_days < min_age_days:
                continue  # te recent -- geef een kans om nog gescraped te worden

        kandidaten.append({
            "player_id": player_id,
            "naam": profile.get("display_name") or "(geen naam)",
            "club": profile.get("club") or "",
            "added_by": profile.get("added_by") or "(geen veld)",
            "origin_reason": origin_reason,
            "discovered_at": discovered_at_raw or "onbekend",
        })

    return kandidaten


def delete_ghost_profiles(kandidaten: list) -> dict:
    """Verwijdert de gegeven profielen effectief uit ZOWEL player_profiles
    ALS players (indien aanwezig). Returns {"verwijderd": n, "fout": n}."""
    samenvatting = {"verwijderd": 0, "fout": 0}
    for k in kandidaten:
        pid = k["player_id"]
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(pid).delete()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{pid}] Verwijderen uit player_profiles mislukt: {e}")
            samenvatting["fout"] += 1
            continue
        try:
            fb.db.collection(fb.PLAYERS_COLLECTION).document(pid).delete()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[{pid}] Geen players-document om te verwijderen ({e}).")
        samenvatting["verwijderd"] += 1
        logger.info(f"[{pid}] Verwijderd: {k['naam']} (origin={k['origin_reason']})")
    return samenvatting


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(
        description="Ruim spelersprofielen op die geen enkele relevantie hebben."
    )
    parser.add_argument("--execute", action="store_true",
                        help="Verwijder de gevonden spookprofielen ECHT. Zonder deze vlag: enkel tonen (dry-run).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Expliciet enkel tonen (is toch al het standaardgedrag zonder --execute).")
    parser.add_argument("--min-age-days", type=int, default=DEFAULT_MIN_AGE_DAYS,
                        help=f"Minimale leeftijd in dagen voor recent ontdekte profielen (standaard {DEFAULT_MIN_AGE_DAYS}).")
    args = parser.parse_args()

    kandidaten = find_ghost_profiles(min_age_days=args.min_age_days)

    if not kandidaten:
        print("Geen spookprofielen gevonden die aan alle criteria voldoen.")
        sys.exit(0)

    print(f"\n{len(kandidaten)} spookprofiel(en) gevonden:\n")
    for k in sorted(kandidaten, key=lambda x: x["naam"]):
        print(
            f"  {k['player_id']:<12} {k['naam']:<30} club={k['club'] or '-':<20} "
            f"added_by={k['added_by']:<22} origin={k['origin_reason']:<20} discovered_at={k['discovered_at']}"
        )

    if not args.execute:
        print(
            f"\nDit was een DRY-RUN — er is niets verwijderd. "
            f"Voer opnieuw uit met --execute om deze {len(kandidaten)} profiel(en) écht te verwijderen."
        )
        sys.exit(0)

    print(f"\n--execute opgegeven: {len(kandidaten)} profiel(en) worden nu verwijderd...")
    resultaat = delete_ghost_profiles(kandidaten)
    print(f"\nKlaar: {resultaat['verwijderd']} verwijderd, {resultaat['fout']} mislukt.")
