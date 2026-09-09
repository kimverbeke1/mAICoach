"""
backfill_missing_profiles.py - maakt ontbrekende player_profiles aan.

Achtergrond (2026-09-09):
scrape_new_opponent_players() in opponent_scout.py scrapet eerst de matchdata
naar de 'players'-collectie en schrijft daarna pas het profiel weg. Wordt die
tweede stap onderbroken, dan bestaat er wel een matchdocument maar geen profiel.
De tegenstander-analyse beschouwt zo'n speler dan telkens opnieuw als
"nog niet gescrapet".

Dit script zoekt alle player_ids die in 'players' zitten maar niet in
'player_profiles', haalt hun naam op uit de matchrecords van andere spelers
(partner_name / opp1_name / opp2_name bij het overeenkomstige user_id) en maakt
het ontbrekende profiel alsnog aan.

Gebruik (vanuit de map PadelAnalysis):
    python backfill_missing_profiles.py            # toont enkel wat er zou gebeuren
    python backfill_missing_profiles.py --apply    # schrijft de profielen weg
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb

_NAME_FIELDS = [
    ("partner_user_id", "partner_name"),
    ("opp1_user_id", "opp1_name"),
    ("opp2_user_id", "opp2_name"),
]


def find_missing_profile_ids() -> list[str]:
    player_ids = {doc.id for doc in fb.db.collection(fb.PLAYERS_COLLECTION).stream()}
    profile_ids = {doc.id for doc in fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()}
    return sorted(player_ids - profile_ids)


def collect_name_candidates(target_ids: set[str]) -> dict[str, Counter]:
    """Doorloop alle matchdocumenten en verzamel de namen per gezocht user_id."""
    candidates: dict[str, Counter] = {pid: Counter() for pid in target_ids}
    for doc in fb.db.collection(fb.PLAYERS_COLLECTION).stream():
        data = doc.to_dict() or {}
        for match in data.get("matches", []) or []:
            for id_field, name_field in _NAME_FIELDS:
                user_id = str(match.get(id_field) or "").strip()
                if user_id in candidates:
                    name = str(match.get(name_field) or "").strip()
                    if name:
                        candidates[user_id][name] += 1
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Maak ontbrekende player_profiles aan.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Schrijf de profielen effectief weg. Zonder deze vlag wordt enkel getoond wat er zou gebeuren.",
    )
    args = parser.parse_args()

    missing = find_missing_profile_ids()
    if not missing:
        print("Geen ontbrekende profielen gevonden. Niets te doen.")
        return 0

    print(f"{len(missing)} speler(s) zonder profiel: {', '.join(missing)}")
    print("Namen opzoeken in de matchrecords van alle spelers...")
    candidates = collect_name_candidates(set(missing))

    planned = []
    for player_id in missing:
        counter = candidates.get(player_id) or Counter()
        doc = fb.db.collection(fb.PLAYERS_COLLECTION).document(player_id).get().to_dict() or {}
        match_count = len(doc.get("matches", []) or [])
        if counter:
            name, hits = counter.most_common(1)[0]
            alternatives = [n for n, _ in counter.most_common()[1:]]
        else:
            name, hits, alternatives = f"Onbekende speler ({player_id})", 0, []

        planned.append((player_id, name, list(counter.keys())))
        print(f"\n  ID {player_id} - {match_count} matches")
        print(f"    naam: {name} ({hits} vermelding(en))")
        if alternatives:
            print(f"    andere schrijfwijzen gevonden: {', '.join(alternatives)}")
        if not counter:
            print("    LET OP: geen naam gevonden in andere matchdocumenten.")

    if not args.apply:
        print("\nDit was een simulatie. Voer opnieuw uit met --apply om weg te schrijven.")
        return 0

    print("\nProfielen wegschrijven...")
    for player_id, name, aliases in planned:
        try:
            fb.save_player_profile(
                player_id=str(player_id),
                display_name=name,
                aliases=aliases or [name],
            )
            print(f"  OK: {player_id} - {name}")
        except Exception as exc:
            print(f"  MISLUKT: {player_id} - {exc}")

    remaining = find_missing_profile_ids()
    if remaining:
        print(f"\nNog steeds zonder profiel: {', '.join(remaining)}")
    else:
        print("\nAlle spelers hebben nu een profiel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
