# -*- coding: utf-8 -*-
"""
cleanup_no_matches.py — verwijdert ALLE spelersprofielen die nog GEEN
gescrapete matchdata hebben (players-document ontbreekt, of heeft een lege
"matches"-lijst).

Locatie: PadelAnalysis/scraper/cleanup_no_matches.py
(naast cleanup_ghost_profiles.py / enrich_opponents.py / ci_scrape_all.py,
zelfde path-setup patroon)

--------------------------------------------------------------------------
WAAROM DIT EEN APART SCRIPT IS (i.p.v. cleanup_ghost_profiles.py uit te
breiden)
--------------------------------------------------------------------------
cleanup_ghost_profiles.py hanteert bewust STRENGE, meervoudige criteria
tegelijk (added_by-marker in {"auto_opponent_discovery","opponent_scout"}
OF "legacy zonder marker én zonder club", GEEN klassement, GEEN padelstat,
GEEN handmatige poule-URL, oud genoeg) - dat script is bedoeld om
voorzichtig ENKEL de onmiskenbaar overbodige, automatisch ontdekte
profielen op te ruimen, zonder ooit een bewust/handmatig toegevoegd
profiel te raken.

Kim vroeg nu expliciet iets BREDERS (chat 2026-09-20): "ik wil nog eens
alle spelers die nog geen gescrapete matchen hebben verwijderen" - dus
ÉÉN eenvoudig criterium ("heeft deze speler matchdata: ja/nee"), ONGEACHT
club, added_by-oorsprong, klassement/padelstat-status of leeftijd. Dit is
een bewust BREDER/ruimer criterium dan cleanup_ghost_profiles.py - vandaar
een apart script, i.p.v. de bestaande, strengere logica te verwateren of
per ongeluk twee verschillende opschoonbetekenissen door elkaar te
gebruiken.

--------------------------------------------------------------------------
WAT DIT SCRIPT WEL EN NIET VERWIJDERT
--------------------------------------------------------------------------
Verwijderd wordt ELK profiel in player_profiles waarvoor:
  - het bijhorende players-document NIET bestaat, OF
  - het bijhorende players-document bestaat, maar het "matches"-veld
    ontbreekt of leeg is (dus 0 gescrapete matchen) - ongeacht club,
    added_by, klassement/padelstat-status of leeftijd.

NOOIT verwijderd: het EIGEN profiel (home_player_id uit app_settings) -
een harde veiligheidsgrendel, ongeacht of dat toevallig ook geen matchdata
zou hebben (zou normaliter nooit voorkomen, maar wordt hoe dan ook nooit
aangeraakt).

⚠️ LET OP (bewust, op Kim's expliciet verzoek, GEEN extra filtering): dit
raakt ook profielen die WEL een club/added_by="manual" hebben, maar nog
nooit gescraped zijn (bv. een teamgenoot die je net handmatig toevoegde
maar nog niet verversL hebt). Twijfel je, gebruik dan eerst --dry-run (het
standaardgedrag) en controleer de lijst voor je --execute gebruikt.

⚠️ LET OP 2: als een verwijderde speler later opnieuw wordt ONTDEKT als
tegenstander/partner van iemand die je (opnieuw) scraped (zie
enrich_opponents.discover_opponent_players()), komt zijn/haar profiel
vanzelf terug - dit script is een EENMALIGE opruiming, geen permanente
uitsluiting. Dat is verwacht en normaal gedrag, geen bug.

Standaard draait dit script in --dry-run (enkel tonen, niets verwijderen).
Pas met --execute wordt er ook effectief verwijderd (uit zowel
player_profiles als players).

--------------------------------------------------------------------------
GEBRUIK
--------------------------------------------------------------------------
    python cleanup_no_matches.py --dry-run
    python cleanup_no_matches.py --execute
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
for _p in [str(_HERE), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402

logger = logging.getLogger(__name__)


def _norm_id(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _all_profiles() -> list:
    try:
        return fb.search_player_profiles("", limit=10_000) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Kon profielen niet lezen: {e}")
        return []


def _home_player_id() -> Optional[str]:
    """Nooit het eigen 'Dit ben ik'-profiel verwijderen — harde
    veiligheidsgrendel, los van de matchdata-check hieronder."""
    try:
        settings = fb.get_app_settings() or {}
        return _norm_id(settings.get("home_player_id")) or None
    except Exception:  # noqa: BLE001
        return None


def find_players_without_matches() -> list:
    """Vindt alle profielen ZONDER gescrapete matchdata (ongeacht club/
    added_by/leeftijd - zie module-docstring voor het verschil met
    cleanup_ghost_profiles.find_ghost_profiles()).
    Returns een lijst van dicts met diagnose-info (player_id, naam, club,
    added_by, reden) — puur informatief, geen extra filtercriterium."""
    home_id = _home_player_id()
    profiles = _all_profiles()
    kandidaten = []
    for profile in profiles:
        player_id = _norm_id(profile.get("player_id"))
        if not player_id:
            continue
        if home_id and player_id == home_id:
            continue  # eigen profiel: nooit aanraken, harde veiligheidsgrendel
        try:
            player_doc = fb.get_player(player_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{player_id}] Kon players-document niet lezen: {e}")
            continue
        if player_doc is None:
            reden = "geen players-document (nooit gescraped)"
        elif not player_doc.get("matches"):
            reden = "players-document bestaat, maar 0 matches"
        else:
            continue  # heeft wel degelijk matchdata -> overslaan
        kandidaten.append({
            "player_id": player_id,
            "naam": profile.get("display_name") or "(geen naam)",
            "club": profile.get("club") or "",
            "added_by": profile.get("added_by") or "(geen veld)",
            "reden": reden,
        })
    return kandidaten


def delete_players(kandidaten: list) -> dict:
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
        logger.info(f"[{pid}] Verwijderd: {k['naam']} ({k['reden']})")
    return samenvatting


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(
        description="Verwijdert ALLE spelersprofielen die nog geen gescrapete matchdata hebben."
    )
    parser.add_argument("--execute", action="store_true",
                        help="Verwijder de gevonden profielen ECHT. Zonder deze vlag: enkel tonen (dry-run).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Expliciet enkel tonen (is toch al het standaardgedrag zonder --execute).")
    args = parser.parse_args()

    kandidaten = find_players_without_matches()
    if not kandidaten:
        print("Geen spelers zonder matchdata gevonden.")
        sys.exit(0)

    print(f"\n{len(kandidaten)} speler(s) zonder gescrapete matchdata gevonden:\n")
    for k in sorted(kandidaten, key=lambda x: x["naam"]):
        print(
            f"  {k['player_id']:<12} {k['naam']:<30} club={k['club'] or '-':<20} "
            f"added_by={k['added_by']:<22} reden={k['reden']}"
        )

    if not args.execute:
        print(
            f"\nDit was een DRY-RUN — er is niets verwijderd. "
            f"Voer opnieuw uit met --execute om deze {len(kandidaten)} profiel(en) écht te verwijderen."
        )
        sys.exit(0)

    print(f"\n--execute opgegeven: {len(kandidaten)} profiel(en) worden nu verwijderd...")
    resultaat = delete_players(kandidaten)
    print(f"\nKlaar: {resultaat['verwijderd']} verwijderd, {resultaat['fout']} mislukt.")
