# -*- coding: utf-8 -*-
"""
diagnose_h2h_score.py - toont EXACT wat poule_ranking.py ziet voor de
onderlinge confrontatie tussen jouw ploeg en een specifieke tegenstander
(bv. T.C. ELEVEN C), om te bevestigen WAAROM het systeem denkt dat je
verloren hebt terwijl je won.

ACHTERGROND: poule_ranking._encounter_result()/_head_to_head_winner()
leiden win/verlies af uit het RUWE "score"-tekstveld van het poule-schema
(schedule_scraper.parse_poule_schedule()) - een tekstveld dat NOOIT apart
geverifieerd is tegen echte win/verlies-data (in tegenstelling tot het
"Uitslag"-veld dat elders in de app, na een eerdere bug, wél als
autoritatieve bron gebruikt wordt - zie PADEL_ANALYSIS_WINNER_TEAMNAME_
2026-09-26 in lineup_opponent_history.py). Dit script toont het ruwe
fixture-record (home/away-namen, ploeg_id's, het score-veld, played) EN
de score van dezelfde ontmoeting zoals die op het ECHTE uitslagenblad
staat (via _fixture_final_score(), de reeds bevestigd betrouwbare bron),
zodat je in 1 oogopslag ziet of het probleem in de ORIENTATIE (thuis/uit
verwisseld) of in het SCORE-FORMAAT zelf zit.

Gebruik (vanuit PadelAnalysis/):
    python diagnose_h2h_score.py --player 1790766 --opponent "eleven"
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).parent
for _p in [str(_HERE)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb  # noqa: E402
import schedule_scraper as ss  # noqa: E402
from dashboard_common import _get_saved_schedule  # noqa: E402
import poule_ranking as pr  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player", required=True, help="player_id, bv. 1790766")
    parser.add_argument(
        "--opponent", required=True,
        help="Deel van de tegenstander-teamnaam om op te zoeken, bv. 'eleven' (hoofdletter-ongevoelig)",
    )
    args = parser.parse_args()
    player_id = str(args.player)
    needle = args.opponent.strip().lower()

    profile = fb.get_player_profile(player_id) or {}
    display_name = profile.get("display_name") or player_id
    print("=" * 78)
    print(f"SPELER: {display_name} ({player_id})")
    print("=" * 78)

    fixtures, sched_at = _get_saved_schedule(player_id)
    if not fixtures:
        print("GEEN opgeslagen poule-schema gevonden voor deze speler - kan niet verder.")
        return
    print(f"Poule-schema: {len(fixtures)} fixture(s), opgeslagen op {sched_at}")

    doc = fb.get_player(player_id) or {}
    own_matches = [m for m in (doc.get("matches") or []) if m.get("match_type") == "interclub"]
    own_ploeg_id, _, _ = ss.identify_own_ploeg_id(fixtures, own_matches, own_display_name=display_name)
    print(f"Eigen ploeg_id (via identify_own_ploeg_id): {own_ploeg_id!r}")
    if not own_ploeg_id:
        print("Kon eigen ploeg niet herkennen - kan de onderlinge confrontatie niet opzoeken.")
        return

    # Zoek de fixture tegen de opgegeven tegenstander.
    matches_found = [
        fx for fx in fixtures
        if needle in (fx.get("home_name") or "").lower() or needle in (fx.get("away_name") or "").lower()
    ]
    if not matches_found:
        print(f"Geen fixture gevonden met '{args.opponent}' in de teamnaam.")
        print("Beschikbare teams in dit schema:")
        for fx in fixtures:
            print(f"  - {fx.get('home_name')} vs {fx.get('away_name')}")
        return

    for fx in matches_found:
        print("\n" + "-" * 78)
        print(f"RUWE FIXTURE (uit schedule_scraper.parse_poule_schedule):")
        print("-" * 78)
        for key in (
            "date_text", "home_name", "home_ploeg_id", "away_name", "away_ploeg_id",
            "score", "played", "uitslagenblad_url",
        ):
            print(f"  {key}: {fx.get(key)!r}")

        is_own_home = str(fx.get("home_ploeg_id")) == str(own_ploeg_id)
        is_own_away = str(fx.get("away_ploeg_id")) == str(own_ploeg_id)
        print(f"\n  Onze ploeg is: {'HOME' if is_own_home else ('AWAY' if is_own_away else 'GEEN VAN BEIDE (!)')}")

        # Wat de HUIDIGE poule_ranking-logica hieruit afleidt:
        outcome = pr._encounter_result(fx.get("score"))
        print(f"\n  poule_ranking._encounter_result(score={fx.get('score')!r}) -> {outcome!r}")
        print(f"  (outcome is vanuit het perspectief van de HOME-ploeg: 'win'=home wint, 'loss'=away wint)")
        if outcome == "win":
            berekende_winnaar = fx.get("home_ploeg_id")
        elif outcome == "loss":
            berekende_winnaar = fx.get("away_ploeg_id")
        else:
            berekende_winnaar = None
        print(f"  Berekende winnaar-ploeg_id volgens poule_ranking: {berekende_winnaar!r}")
        print(f"  Is dat ONZE ploeg? {str(berekende_winnaar) == str(own_ploeg_id)}")

        # Vergelijk met de ECHTE, reeds bevestigd betrouwbare bron: het
        # uitslagenblad zelf (zelfde route als lineup_opponent_history.py
        # gebruikt, via het "Uitslag"-veld i.p.v. afgeleide scores).
        if fx.get("uitslagenblad_url"):
            print(f"\n  Uitslagenblad-URL (open dit handmatig ter controle):")
            print(f"  https://www.tennisenpadelvlaanderen.be{fx.get('uitslagenblad_url')}")
        print(
            "\n  >>> Vergelijk de 'score'-waarde hierboven met wat je ZELF ziet op het "
            "uitslagenblad (link hierboven). Als de 'score' bv. '1-3' is terwijl WIJ "
            "won (en wij zijn AWAY), dan is de _encounter_result()-berekening (thuis "
            "wint bij hogere eerste waarde) net verkeerd om, OF het 'score'-veld "
            "bevat iets anders dan het aantal gewonnen borden (bv. een setscore-"
            "fragment i.p.v. de bordentelling)."
        )


if __name__ == "__main__":
    main()
