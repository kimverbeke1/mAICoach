"""
bulk_fetch_padelstat_ratings.py - haalt de padelstats.be 'playing strength'
op voor ALLE spelers die al in onze eigen Firestore staan (player_profiles),
en cachet het resultaat per speler.

PADEL_ANALYSIS_PADELSTAT_BULK_FETCH_2026-09-13:
Dit is de logische vervolgstap op het individuele kalibratiescript
(compare_elo_vs_padelstat.py): in plaats van per speler manueel het
padelstats-ID te moeten opzoeken en invullen, doorloopt dit script gewoon
ALLE spelers die we al kennen (via hun display_name + club, beide al
aanwezig in ons eigen player_profiles-document) en gebruikt
padelstats_scraper.search_and_fetch_padelstat_rating() om automatisch de
juiste speler te vinden (club-disambiguatie gebeurt AUTOMATISCH met onze
eigen 'club'-veldwaarde, geen handmatige REFERENTIES-lijst meer nodig zoals
in compare_elo_vs_padelstat.py).

BELANGRIJK - snelheid en belasting:
Elke speler vereist twee volledige Playwright-paginabezoeken (zoeken +
profiel bezoeken), dus dit script is traag bij veel spelers (typisch
5-10 seconden per speler). Er zit een korte pauze tussen spelers ingebouwd
om de site niet nodeloos te belasten. Voor een eenmalige, incidentele
kalibratie-actie is dit aanvaardbaar; gebruik dit NIET als periodieke
achtergrondtaak.

Gebruik:
    python bulk_fetch_padelstat_ratings.py              (enkel nieuwe/nog niet gecachete spelers)
    python bulk_fetch_padelstat_ratings.py --refresh     (haalt IEDEREEN opnieuw op, negeert cache)
    python bulk_fetch_padelstat_ratings.py --limit 5      (test eerst met een klein aantal)

Na afloop: gebruik get_padelstat_ratings_summary() (of het overzicht dat dit
script zelf print) om de opgehaalde waarden te zien, en
compare_elo_vs_padelstat.py (of een vergelijkbaar overzicht) om ze naast onze
eigen Elo te leggen.
"""
from __future__ import annotations

import sys
import time

import firebase_service as fb
import padelstats_scraper as ps


def _parse_args() -> dict:
    args = sys.argv[1:]
    return {
        "refresh": "--refresh" in args,
        "limit": (
            int(args[args.index("--limit") + 1])
            if "--limit" in args and args.index("--limit") + 1 < len(args)
            else None
        ),
    }


def bulk_fetch(refresh: bool = False, limit: int | None = None, pause_seconds: float = 1.5) -> None:
    profiles = fb.search_player_profiles("", limit=10_000)
    # Alleen echte profielen (met een naam), consistent met de eerdere
    # ghost-profiel-filter in dashboard._get_all_profiles().
    profiles = [p for p in profiles if p.get("display_name") and p.get("player_id")]

    if limit:
        profiles = profiles[:limit]

    total = len(profiles)
    print(f"Te verwerken: {total} spelers (limit={limit or 'geen'}, refresh={refresh})")
    print("-" * 90)

    results = []
    for i, profile in enumerate(profiles, start=1):
        player_id = str(profile.get("player_id"))
        name = profile.get("display_name") or ""
        club = profile.get("club") or ""

        prefix = f"[{i}/{total}] {name} ({club or 'geen club gekend'})"

        if not refresh:
            cached = fb.get_padelstat_rating(player_id)
            if cached:
                print(f"{prefix} -> CACHE: P{cached.get('rating')} (bron: {cached.get('rating_source')})")
                results.append({"player_id": player_id, "name": name, **cached, "from_cache": True})
                continue

        try:
            found = ps.search_and_fetch_padelstat_rating(name, club=club or None)
        except Exception as exc:
            print(f"{prefix} -> FOUT: {exc}")
            results.append({"player_id": player_id, "name": name, "rating": None, "rating_source": "error", "error": str(exc)})
            continue

        if not found or found.get("rating") is None:
            note = (found or {}).get("club_disambiguation_note") or (found or {}).get("raw_text_snippet", "")
            print(f"{prefix} -> NIET GEVONDEN. {note[:120]}")
            results.append({"player_id": player_id, "name": name, "rating": None, "rating_source": "not_found"})
            time.sleep(pause_seconds)
            continue

        fb.save_padelstat_rating(
            player_id,
            found.get("padelstat_id", ""),
            found.get("rating"),
            found.get("rating_source", "none"),
            found.get("raw_text_snippet", ""),
        )

        note_flag = " ⚠️ (club niet bevestigd, controleer)" if found.get("club_disambiguation_note") else ""
        print(f"{prefix} -> P{found['rating']}{note_flag}")
        results.append({"player_id": player_id, "name": name, **found, "from_cache": False})

        time.sleep(pause_seconds)

    print("-" * 90)
    found_count = sum(1 for r in results if r.get("rating") is not None)
    print(f"Klaar: {found_count}/{total} spelers succesvol opgehaald/gecached.")

    unresolved = [r for r in results if r.get("rating") is None]
    if unresolved:
        print()
        print("Niet gevonden / mislukt:")
        for r in unresolved:
            print(f"  - {r['name']} ({r['player_id']}): {r.get('rating_source')}")

    flagged = [r for r in results if r.get("club_disambiguation_note") and not r.get("from_cache")]
    if flagged:
        print()
        print("⚠️ Gevonden maar club-match NIET bevestigd (controleer handmatig):")
        for r in flagged:
            print(f"  - {r['name']}: {r['club_disambiguation_note'][:150]}")


if __name__ == "__main__":
    opts = _parse_args()
    bulk_fetch(refresh=opts["refresh"], limit=opts["limit"])
