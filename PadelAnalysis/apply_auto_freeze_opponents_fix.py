"""
apply_auto_freeze_opponents_fix.py - bevriest AUTOMATISCH (geen klik nodig)
het regulier bijwerken van tegenstander-spelers zodra er geen geplande
ontmoeting meer met hen is, en laat de padelstat/klassement-bulkverversing
zulke spelers overslaan.

Locatie: PadelAnalysis/apply_auto_freeze_opponents_fix.py  (eenmalig te
draaien, patcht 3 bestanden in 1 keer)

PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26 (op verzoek van Kim: "ik zit
te denken dat ik niet al die oude spelers van gespeelde matchen continu wil
updaten qua padelstat score etc [...] ivm automatische suggestie: ik zou
willen proberen om die klik te vermijden. gewoon automatisch afzetten als
match gespeeld is. als je toch analyse opnieuw start mag je terug laatste
data ophalen maar dan is dat niet automatisch, wat ok is")
--------------------------------------------------------------------------
ONTWERP (geen apart vinkje, geen klik - puur afgeleid uit reeds bestaande
poule-scheduledata):

Een tegenstander-speler is "klaar" (mag stoppen met REGULIER/BULK bijwerken)
zodra de ploeg waarin hij/zij gevonden werd GEEN niet-gespeelde fixture meer
heeft in een van de door Kim gevolgde poules (interclub_schedule). Dat is
precies wat discover_poule_players.py al per ploeg berekent (played=True/
False per fixture) - dit voegt enkel een schrijf-actie toe die de conclusie
vastlegt op het player_profiles-document zelf.

BELANGRIJK, en dit is de kern van "geen klik": dit draait AUTOMATISCH mee in
discover_poule_players.py, dat al bedoeld is om (via prescan-poule.yml, of
een toekomstige scheduler) periodiek te lopen. Elke run herstelt de
bevriezingsstatus VOLLEDIG vanuit de actuele poule-schema's:
  - Een ploeg met alle fixtures gespeeld -> al hun gekende spelers krijgen
    auto_update_frozen=True.
  - Een ploeg met nog minstens 1 ongespeelde fixture -> auto_update_frozen
    wordt expliciet op False gezet (zelf-herstellend: verandert de
    kalender - bv. een uitgestelde wedstrijd - dan ontdooit dit vanzelf,
    zonder enige handmatige actie).
Dit is dus GEEN eenmalige, permanente markering, maar een levende afgeleide
status die elke run opnieuw correct berekend wordt.

WAT "BEVROREN" BETEKENT (en niet betekent):
  - GEEN effect op de EXPLICIETE UI-acties ("🔍 Tegenstander analyseren",
    "🔄 Ontbrekende gegevens ophalen", "🔄 Ververs alles voor deze ploeg") -
    die blijven altijd verse data ophalen, ook voor een bevroren speler.
    Exact Kim's "als je toch analyse opnieuw start mag je terug laatste
    data ophalen [...] dat is niet automatisch, wat ok is".
  - WEL overgeslagen door de REGULIERE/GEPLANDE bulkverversing
    (enrich_opponents.run_padelstat_for_players()/run_klassement_for_
    players(), aangeroepen door ci_scrape_all.py se run_enrichment() -
    dus zowel de dagelijkse cron als prescan-poule.yml). Dit is precies
    waar Kim onnodige, herhaalde padelstat/klassement-scrapes van reeds
    uitgespeelde tegenstanders wil vermijden, en dit versnelt tegelijk een
    volgende NIEUWE ploeg-analyse (minder concurrentie om het gedeelde
    PADELSTAT_MAX/KLASSEMENT_MAX-run-budget).

DRIE BESTANDEN, IN SAMENHANG:

1. discover_poule_players.py: berekent per ploeg of ze nog een
   ongespeelde fixture hebben, en zet/verwijdert auto_update_frozen op elk
   gekend speler-profiel van die ploeg. GEEN extra Firestore-reads t.o.v.
   de bestaande discovery-scan - hergebruikt de al opgehaalde fixtures.

2. enrich_opponents.py: run_padelstat_for_players() en run_klassement_
   for_players() slaan een bevroren speler over, TENZIJ die speler in
   priority_ids zit (het bestaande mechanisme voor "forceer deze speler
   expliciet", al gebruikt door run_single_player_refresh()). Voor
   padelstat kost deze check 0 EXTRA Firestore-reads: het profiel wordt
   daar al in bulk ingelezen (alle_profielen). Voor klassement (dat geen
   bulk-profielenlijst heeft) 1 extra lichte read per kandidaat.

3. page_players.py: toont een klein, informatief label bij een bevroren
   speler - puur ter transparantie (Kim's eerder uitgesproken voorkeur om
   nooit iets stilzwijgend te verstoppen), geen actieknop.

GEBRUIK (PowerShell, vanuit PadelAnalysis of PadelAnalysis/scraper naargelang
het bestand):

    python apply_auto_freeze_opponents_fix.py \\
        --discover-file scraper/discover_poule_players.py \\
        --enrich-file scraper/enrich_opponents.py \\
        --players-file page_players.py
    # daarna hetzelfde met --apply

Idempotent per bestand. Maakt een back-up (.bak_<timestamp>) voor het
schrijven.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26"

# ═══════════════════════════════════════════════════════════════════════
# 1. discover_poule_players.py
# ═══════════════════════════════════════════════════════════════════════
DISCOVER_OLD_LOOP = '''    all_players: dict[str, str] = {}
    for i, (ploeg_id, info) in enumerate(teams.items(), start=1):
        logger.info(f"--- ({i}/{len(teams)}) {info['name']} ({info['poule_label']}) ---")
        try:
            found = discover_players_for_team(ploeg_id, info)
            logger.info(f"  -> {len(found)} speler(s) gevonden.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"  -> kon spelers niet ophalen: {e}")
            found = {}
        for pid, name in found.items():
            all_players.setdefault(pid, name)
        if i < len(teams):
            time.sleep(delay)'''

DISCOVER_NEW_LOOP = '''    all_players: dict[str, str] = {}
    frozen_count, unfrozen_count = 0, 0
    for i, (ploeg_id, info) in enumerate(teams.items(), start=1):
        logger.info(f"--- ({i}/{len(teams)}) {info['name']} ({info['poule_label']}) ---")
        try:
            found = discover_players_for_team(ploeg_id, info)
            logger.info(f"  -> {len(found)} speler(s) gevonden.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"  -> kon spelers niet ophalen: {e}")
            found = {}
        for pid, name in found.items():
            all_players.setdefault(pid, name)
        # PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26 (op verzoek van
        # Kim: "gewoon automatisch afzetten als match gespeeld is"): heeft
        # deze ploeg nog een NIET-gespeelde fixture in het gevolgde
        # poule-schema? Zo niet, dan mogen hun gekende spelers stoppen met
        # regulier/bulk bijwerken - een bewuste "analyseer opnieuw"-klik
        # blijft ze altijd gewoon verversen (zie enrich_opponents.py).
        # Zelf-herstellend: verandert de kalender alsnog (bv. een
        # uitgestelde wedstrijd), dan wordt dit bij de volgende run
        # automatisch weer ontdooid.
        if found:
            team_fixtures = ss.get_team_fixtures(info["fixtures"], ploeg_id)
            still_upcoming = any(not fx.get("played") for fx in team_fixtures)
            _mark_team_players_frozen_state(ploeg_id, list(found.keys()), still_upcoming)
            if still_upcoming:
                unfrozen_count += len(found)
            else:
                frozen_count += len(found)
        if i < len(teams):
            time.sleep(delay)
    if frozen_count or unfrozen_count:
        logger.info(
            f"Automatisch bijwerken: {frozen_count} speler(s) bevroren (geen geplande "
            f"ontmoeting meer), {unfrozen_count} speler(s) actief (nog minstens 1 geplande "
            "ontmoeting) - status is elke run opnieuw herberekend."
        )'''

DISCOVER_HELPER_ANCHOR = "def discover_all_poule_teams() -> dict:"

DISCOVER_HELPER = '''def _mark_team_players_frozen_state(
    ploeg_id: str, player_ids: list[str], still_upcoming: bool,
) -> None:
    """PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26: zet (of verwijdert)
    auto_update_frozen op elk speler-profiel van deze ploeg, gebaseerd op of
    de ploeg nog een NIET-gespeelde fixture heeft in een gevolgde poule.

    Dit is een LEVENDE, elke run herberekende status - geen eenmalige,
    permanente markering. still_upcoming=True zet auto_update_frozen
    expliciet terug op False (zelf-herstellend bij een gewijzigde
    kalender), still_upcoming=False zet het op True (regulier/bulk
    bijwerken van deze speler overslaan - zie enrich_opponents.py).

    Fouten per speler worden gelogd maar blokkeren de rest van de run niet
    - dit is een aanvullende optimalisatie, geen kritiek pad."""
    for pid in player_ids:
        try:
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(
                {
                    "auto_update_frozen": not still_upcoming,
                    "auto_update_frozen_reason": (
                        None if still_upcoming
                        else "geen geplande ontmoetingen meer in de gevolgde poules"
                    ),
                    "auto_update_frozen_via_ploeg_id": str(ploeg_id),
                    "auto_update_frozen_updated_at": _utc_now_iso(),
                },
                merge=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[{pid}] Kon auto_update_frozen-status niet bijwerken: {e}")


def discover_all_poule_teams() -> dict:'''


# ═══════════════════════════════════════════════════════════════════════
# 2. enrich_opponents.py
# ═══════════════════════════════════════════════════════════════════════
ENRICH_HELPER_ANCHOR = "def _has_matchdata(player_id: str) -> bool:"

ENRICH_HELPER = '''# PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26 (op verzoek van Kim: "ik
# zit te denken dat ik niet al die oude spelers van gespeelde matchen
# continu wil updaten qua padelstat score etc [...] gewoon automatisch
# afzetten als match gespeeld is"):
# discover_poule_players.py zet dit veld automatisch, elke run opnieuw
# herberekend uit de actuele poule-schema's (zie dat bestand voor de
# volledige toelichting) - GEEN handmatige markering.
def _is_frozen(profile_or_id) -> bool:
    """Aanvaardt ofwel een reeds opgehaald profiel-dict (0 extra reads,
    gebruikt in run_padelstat_for_players() waar het profiel toch al in
    bulk werd ingelezen) ofwel rechtstreeks een player_id (1 lichte
    Firestore-read, gebruikt in run_klassement_for_players() dat geen
    bulk-profielenlijst heeft)."""
    if isinstance(profile_or_id, dict):
        return bool(profile_or_id.get("auto_update_frozen"))
    try:
        prof = fb.get_player_profile(profile_or_id) or {}
    except Exception:  # noqa: BLE001
        return False
    return bool(prof.get("auto_update_frozen"))


def _has_matchdata(player_id: str) -> bool:'''

ENRICH_PADELSTAT_OLD = '''    samenvatting = {"opgehaald": 0, "cache": 0, "niet_gevonden": 0,
                     "fout": 0, "overgeslagen_limiet": 0,
                     "officieel_klassement": 0}'''

ENRICH_PADELSTAT_NEW = '''    samenvatting = {"opgehaald": 0, "cache": 0, "niet_gevonden": 0,
                     "fout": 0, "overgeslagen_limiet": 0,
                     "officieel_klassement": 0,
                     # PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26
                     "bevroren": 0}'''

ENRICH_PADELSTAT_LOOP_OLD = '''        is_priority = key in priority_ids
        if not refresh and not is_priority:
            try:
                cached = fb.get_padelstat_rating(key)
            except Exception:  # noqa: BLE001
                cached = None
            if not _padelstat_is_stale(cached, stale_after_days):
                samenvatting["cache"] += 1
                continue
        te_doen.append((key, profiel))'''

ENRICH_PADELSTAT_LOOP_NEW = '''        is_priority = key in priority_ids
        # PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26: een bevroren
        # speler wordt door de REGULIERE bulkverversing overgeslagen,
        # TENZIJ expliciet aangevraagd (priority_ids - hetzelfde mechanisme
        # dat run_single_player_refresh() al gebruikt om een gerichte
        # ververs-actie nooit te laten blokkeren). Geen extra Firestore-read:
        # `profiel` is hier al in bulk ingelezen.
        if not is_priority and _is_frozen(profiel):
            samenvatting["bevroren"] += 1
            continue
        if not refresh and not is_priority:
            try:
                cached = fb.get_padelstat_rating(key)
            except Exception:  # noqa: BLE001
                cached = None
            if not _padelstat_is_stale(cached, stale_after_days):
                samenvatting["cache"] += 1
                continue
        te_doen.append((key, profiel))'''

ENRICH_KLASSEMENT_OLD = '''    samenvatting = {"opgehaald": 0, "cache": 0, "fout": 0, "overgeslagen_limiet": 0}'''

ENRICH_KLASSEMENT_NEW = '''    # PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26
    samenvatting = {"opgehaald": 0, "cache": 0, "fout": 0, "overgeslagen_limiet": 0,
                     "bevroren": 0}'''

ENRICH_KLASSEMENT_LOOP_OLD = '''    te_doen = []
    for pid in player_ids:
        key = _norm_id(pid)
        is_priority = key in priority_ids
        if not refresh and not is_priority and _has_klassement(key):
            samenvatting["cache"] += 1
            continue
        te_doen.append((key,))'''

ENRICH_KLASSEMENT_LOOP_NEW = '''    te_doen = []
    for pid in player_ids:
        key = _norm_id(pid)
        is_priority = key in priority_ids
        # PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26: zie de uitgebreide
        # toelichting in run_padelstat_for_players() hierboven - zelfde
        # principe, hier 1 extra lichte read per kandidaat (geen
        # bulk-profielenlijst beschikbaar in deze functie).
        if not is_priority and _is_frozen(key):
            samenvatting["bevroren"] += 1
            continue
        if not refresh and not is_priority and _has_klassement(key):
            samenvatting["cache"] += 1
            continue
        te_doen.append((key,))'''


# ═══════════════════════════════════════════════════════════════════════
# 3. page_players.py
# ═══════════════════════════════════════════════════════════════════════
PLAYERS_OLD = '''    _render_player_ranking_summary(player_id)'''

PLAYERS_NEW = '''    _render_player_ranking_summary(player_id)
    # PADEL_ANALYSIS_AUTO_FREEZE_OPPONENTS_2026-09-26: puur informatief (geen
    # actieknop) - Kim's voorkeur om nooit iets stilzwijgend te verstoppen.
    # Status wordt automatisch bijgewerkt door discover_poule_players.py; een
    # nieuwe "Tegenstander analyseren"-klik ontdooit dit altijd vanzelf.
    if profile.get("auto_update_frozen"):
        st.caption(
            "🔒 Automatisch bijwerken gestopt — geen geplande ontmoetingen meer gevonden in de "
            "gevolgde poules. Een nieuwe analyse haalt gewoon weer verse gegevens op."
        )'''


def _patch_file(pad: Path, apply: bool, replacements: list, label: str) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False
    tekst = pad.read_text(encoding="utf-8")
    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False
    nieuw = tekst
    for old, new, naam in replacements:
        if old not in nieuw:
            print(f"  {pad.name}: KON '{naam}' NIET VINDEN IN VERWACHTE VORM - {label} niet gewijzigd.")
            return False
    for old, new, naam in replacements:
        nieuw = nieuw.replace(old, new, 1)
        print(f"  {pad.name}: {naam}: klaar om te patchen.")
    if not apply:
        print(f"  {pad.name}: DRY-RUN ({len(tekst)} -> {len(nieuw)} tekens).")
        return True
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pad.with_suffix(f".py.bak_{stempel}")
    shutil.copy2(pad, backup)
    pad.write_text(nieuw, encoding="utf-8")
    print(f"  {pad.name}: GEPATCHT. Back-up: {backup.name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Bevriest automatisch tegenstander-spelers zonder geplande ontmoeting."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--discover-file", default="discover_poule_players.py")
    parser.add_argument("--enrich-file", default="enrich_opponents.py")
    parser.add_argument("--players-file", default="page_players.py")
    args = parser.parse_args()

    print(f"Modus: {'TOEPASSEN' if args.apply else 'DRY-RUN (er wordt niets gewijzigd)'}\n")

    print(f"=== {args.discover_file} ===")
    r1 = _patch_file(
        Path(args.discover_file).resolve(), args.apply,
        [
            (DISCOVER_HELPER_ANCHOR, DISCOVER_HELPER, "helper _mark_team_players_frozen_state()"),
            (DISCOVER_OLD_LOOP, DISCOVER_NEW_LOOP, "main()-loop met freeze-marking"),
        ],
        "discover_poule_players.py",
    )

    print(f"\n=== {args.enrich_file} ===")
    r2 = _patch_file(
        Path(args.enrich_file).resolve(), args.apply,
        [
            (ENRICH_HELPER_ANCHOR, ENRICH_HELPER, "helper _is_frozen()"),
            (ENRICH_PADELSTAT_OLD, ENRICH_PADELSTAT_NEW, "padelstat-samenvatting +bevroren"),
            (ENRICH_PADELSTAT_LOOP_OLD, ENRICH_PADELSTAT_LOOP_NEW, "padelstat-loop: frozen-check"),
            (ENRICH_KLASSEMENT_OLD, ENRICH_KLASSEMENT_NEW, "klassement-samenvatting +bevroren"),
            (ENRICH_KLASSEMENT_LOOP_OLD, ENRICH_KLASSEMENT_LOOP_NEW, "klassement-loop: frozen-check"),
        ],
        "enrich_opponents.py",
    )

    print(f"\n=== {args.players_file} ===")
    r3 = _patch_file(
        Path(args.players_file).resolve(), args.apply,
        [(PLAYERS_OLD, PLAYERS_NEW, "bevroren-label")],
        "page_players.py",
    )

    print()
    if not (r1 or r2 or r3):
        print("Er is niets gewijzigd.")
        return
    if args.apply:
        for f in (args.discover_file, args.enrich_file, args.players_file):
            print(f'python -c "import ast; ast.parse(open(r\'{f}\', encoding=\'utf-8\').read()); '
                  f'print(\'{f} OK\')"')
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
