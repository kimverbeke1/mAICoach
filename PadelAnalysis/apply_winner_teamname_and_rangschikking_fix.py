"""
apply_winner_teamname_and_rangschikking_fix.py - toont de ploegnaam i.p.v.
spelersnamen bij "Winnaar" in de eerdere-ontmoetingen-tabel, en voegt een
link naar de officiele TVL-rangschikking toe aan de bestaande "Rangschikking"-tab.

Locatie: PadelAnalysis/apply_winner_teamname_and_rangschikking_fix.py
(eenmalig te draaien)

PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26 (op verzoek van Kim: "Bij winnaar
toon je de naam van de spelers bij de eerdere ontmoetingen. De ploegnaam is
daar beter maar is al goed dat het werkt :-)")
--------------------------------------------------------------------------
CONTEXT: de vorige fix (PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25)
loste de KERNBUG al op (scrape_uitslagenblad() las het echte "Uitslag"-veld
i.p.v. een niet-bestaande "W"/"V"-letter) en toonde daarna de NAMEN van het
winnende spelerskoppel. Dat is correct voor een bord, maar in de "eerdere
ontmoetingen"-tabel is de ploegnaam duidelijker: elke rij toont al de 2
spelersnamen apart in "Speler 1"/"Speler 2", dus een DERDE keer namen
tonen (nu in de kolom "Winnaar") voegt weinig toe. De ploegnaam
("K.T.C. DE WITTE KAPROENEN A" i.p.v. "Van Rossom Tim / Van Rossom Sam")
maakt in een oogopslag duidelijk WELKE ploeg dat bord won, zonder dat je de
namen in de 2 kolommen ernaast moet herkennen.

FIX: _fixture_final_score() geeft nu ook "is_scouted_home" terug (of de
GESCOUTE tegenstander in DEZE specifieke, historische ontmoeting de thuis-
of uitploeg was) - die berekening bestond al INTERN in de functie, maar
werd nooit doorgegeven. _fixture_rows() krijgt nu optioneel home_team/
away_team/is_opponent_home mee en toont daarmee de ploegnaam. Zonder die
extra info (bv. een ouder uitslagenblad zonder team-samenvatting) valt dit
terug op de spelersnamen - het bestaande, werkende gedrag blijft dus als
vangnet intact.

PADEL_ANALYSIS_RANGSCHIKKING_LINK_2026-09-26 (op verzoek van Kim: "zou ik
daar een extra tab willen met 'rangschikking' en daar gewoon in 1ste
instantie een link naar de rangschikking")
--------------------------------------------------------------------------
De tab "🏆 Rangschikking" bestaat AL (sub_rangschikking, roept
oa.render_ranking_tab() aan) - dit voegt enkel de gevraagde link TOE
bovenaan die tab, in plaats van een nieuwe tab te maken.

De rangschikking-URL (.../interclub-rangschikking?spelgroepId=X&pouleId=Y)
gebruikt DEZELFDE spelgroepId + pouleId als de al bekende poule/tabel-URL
(.../interclub-poule-tabel?afdelingId=..&spelgroepId=X&pouleId=Y) - die URL
is al gekend als `reeks_url` (automatisch gevonden of handmatig ingevuld
via "Volgende match"). Geen nieuwe scrape nodig: enkel de query-parameters
overnemen.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_winner_teamname_and_rangschikking_fix.py           # dry-run
    python apply_winner_teamname_and_rangschikking_fix.py --apply   # uitvoeren

Idempotent: een tweede run merkt dat de fix er al staat en doet niets.
Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26"

# ── 1. _fixture_final_score(): geeft nu ook is_scouted_home terug ──
FINAL_SCORE_PATTERN = re.compile(
    r"^def _fixture_final_score\(.*?(?=^def _render_previous_opponent_lineup\()",
    re.S | re.M,
)

FINAL_SCORE_NEW = '''def _fixture_final_score(
    fx: dict, boards: list, scouted_team_name: str, opponent_ploeg_id: str = None,
    fixture_bundle: dict = None,
):
    """Eindscore van 1 volledige ontmoeting: matchen/sets/spellen + winnaar.

    PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26 (op verzoek van Kim: "Bij
    winnaar toon je de naam van de spelers bij de eerdere ontmoetingen. De
    ploegnaam is daar beter"):
    ----------------------------------------------------------------------
    Geeft nu ook "is_scouted_home" mee terug: was de GESCOUTE tegenstander
    (scouted_team_name/opponent_ploeg_id) in DEZE historische ontmoeting de
    THUIS- of UITploeg? Die berekening bestond al intern in deze functie
    (nodig voor de bordentelling-terugval), maar werd nooit doorgegeven -
    _fixture_rows() kon daardoor de ploegnaam van de winnaar per bord niet
    tonen en viel terug op spelersnamen.

    Geeft een dict terug: {"home_name", "away_name", "matches", "sets",
    "games", "winner", "is_scouted_home"}.
    """
    fixture_bundle = fixture_bundle or {}
    home_name = fixture_bundle.get("home_team") or fx.get("home_name") or ""
    away_name = fixture_bundle.get("away_team") or fx.get("away_name") or ""
    winner = fixture_bundle.get("winner_team")

    matches_pair = fixture_bundle.get("team_score_matches")
    sets_pair = fixture_bundle.get("team_score_sets")
    games_pair = fixture_bundle.get("team_score_games")

    is_scouted_home = None
    if opponent_ploeg_id is not None:
        if str(fx.get("home_ploeg_id")) == str(opponent_ploeg_id):
            is_scouted_home = True
        elif str(fx.get("away_ploeg_id")) == str(opponent_ploeg_id):
            is_scouted_home = False
    if is_scouted_home is None and scouted_team_name and home_name:
        is_scouted_home = bool(
            _clean_name(scouted_team_name) in _clean_name(home_name)
            or _clean_name(home_name) in _clean_name(scouted_team_name)
        )

    if matches_pair is None:
        # Terugval (oud gedrag): tellen via de borden - enkel het aantal
        # gewonnen matchen is dan beschikbaar, geen sets/spellen.
        scouted_wins = sum(1 for b in boards if b.get("opponent_won") is True)
        other_wins = sum(1 for b in boards if b.get("opponent_won") is False)
        known = scouted_wins + other_wins
        if known == 0:
            return None
        matches_pair = (
            (scouted_wins, other_wins) if is_scouted_home else (other_wins, scouted_wins)
        )
        if not winner:
            if matches_pair[0] > matches_pair[1]:
                winner = home_name or None
            elif matches_pair[1] > matches_pair[0]:
                winner = away_name or None

    return {
        "home_name": home_name,
        "away_name": away_name,
        "matches": matches_pair,
        "sets": sets_pair,
        "games": games_pair,
        "winner": winner,
        "is_scouted_home": is_scouted_home,
    }


'''

# ── 2. _fixture_rows(): toont ploegnaam i.p.v. spelersnamen ──
FIXTURE_ROWS_PATTERN = re.compile(
    r"^def _fixture_rows\(.*?(?=^def _render_fixture_rows_table\()",
    re.S | re.M,
)

FIXTURE_ROWS_NEW = '''def _fixture_rows(
    boards: list, home_team: str = None, away_team: str = None,
    is_opponent_home: bool = None,
) -> list:
    """Zet de dubbels van 1 ontmoeting om naar tabelrijen, MET klassement.

    PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26 (op verzoek van Kim: "Bij
    winnaar toon je de naam van de spelers bij de eerdere ontmoetingen. De
    ploegnaam is daar beter"):
    ----------------------------------------------------------------------
    Elke rij toont al "Speler 1"/"Speler 2" apart - een DERDE keer namen
    tonen in de kolom "Winnaar" voegt weinig toe. De ploegnaam maakt in 1
    oogopslag duidelijk WELKE ploeg dat bord won, zonder de namen in de 2
    kolommen ernaast te moeten herkennen.

    FIX: is home_team/away_team/is_opponent_home meegegeven (zie
    _fixture_final_score(), die dit nu berekent), dan toont "Winnaar" de
    PLOEGNAAM. Ontbreekt die info (bv. een ouder uitslagenblad zonder
    team-samenvatting), dan valt dit terug op de spelersnamen - het
    bestaande, werkende gedrag blijft dus als vangnet intact."""
    heeft_teaminfo = (
        home_team is not None and away_team is not None and is_opponent_home is not None
    )
    rows = []
    for b in sorted(boards, key=lambda x: x.get("board_position") or 0):
        pair = b.get("opponent_pair") or []
        if len(pair) != 2:
            continue
        pos = b.get("board_position")
        rot = (int(pos) + 1) // 2 if pos else "?"
        m_in_rot = 1 if (pos and int(pos) % 2 == 1) else 2
        opponent_won = b.get("opponent_won")
        other_pair = b.get("other_pair") or []

        winnaar_namen = "Onbekend"
        if opponent_won is True:
            if heeft_teaminfo:
                winnaar_namen = home_team if is_opponent_home else away_team
            else:
                winnaar_namen = " / ".join(p.get("name", "?") for p in pair)
        elif opponent_won is False:
            if heeft_teaminfo:
                winnaar_namen = away_team if is_opponent_home else home_team
            elif len(other_pair) == 2:
                winnaar_namen = " / ".join(p.get("name", "?") for p in other_pair)

        rows.append({
            "Match": f"Rotatie {rot} — Match {m_in_rot}" if pos else "Match ?",
            "Speler 1": pair[0].get("name", "?"),
            "Klassement 1": _rank_text_for_opponent(pair[0]),
            "Speler 2": pair[1].get("name", "?"),
            "Klassement 2": _rank_text_for_opponent(pair[1]),
            "Score": b.get("score") or "onbekend",
            "Winnaar": winnaar_namen,
            "_opponent_won": opponent_won,  # intern: bepaalt de rijkleur, niet getoond
        })
    return rows


'''

# ── 3. _render_previous_opponent_lineup(): geeft team-info door aan _fixture_rows ──
PREV_LINEUP_ROWS_OLD = (
    '        rows = _fixture_rows(bruikbaar[keuze].get("boards") or [])\n'
    '        _render_fixture_rows_table(rows)'
)
PREV_LINEUP_ROWS_NEW = (
    '        # PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26: ploegnaam i.p.v.\n'
    '        # spelersnamen in de kolom "Winnaar" - zie _fixture_rows().\n'
    '        rows = _fixture_rows(\n'
    '            bruikbaar[keuze].get("boards") or [],\n'
    '            home_team=(score or {}).get("home_name"),\n'
    '            away_team=(score or {}).get("away_name"),\n'
    '            is_opponent_home=(score or {}).get("is_scouted_home"),\n'
    '        )\n'
    '        _render_fixture_rows_table(rows)'
)

# ── 4. Rangschikking-link: nieuwe helper + aanroep in de bestaande tab ──
RANGSCHIKKING_HELPER = '''

# ─────────────────────────────────────────────
# PADEL_ANALYSIS_RANGSCHIKKING_LINK_2026-09-26
# ─────────────────────────────────────────────
def _build_rangschikking_url(reeks_url: str) -> str | None:
    """Bouwt de link naar de officiele TVL-rangschikkingspagina van deze
    poule, op basis van de al gekende poule/tabel-URL (reeks_url).

    Gebruikt DEZELFDE spelgroepId + pouleId als die poule/tabel-URL - geen
    nieuwe scrape nodig, enkel de query-parameters overnemen. Geeft None
    terug als reeks_url ontbreekt of niet het verwachte formaat heeft (dan
    toont de aanroeper een duidelijke uitleg i.p.v. een kapotte link)."""
    if not reeks_url:
        return None
    try:
        from urllib.parse import urlparse, parse_qs, urlencode
        parsed = urlparse(reeks_url)
        qs = parse_qs(parsed.query)
        spelgroep_id = (qs.get("spelgroepId") or [None])[0]
        poule_id = (qs.get("pouleId") or [None])[0]
        if not spelgroep_id or not poule_id:
            return None
        base = "https://www.tennisenpadelvlaanderen.be/nl/clubdashboard/interclub-rangschikking"
        return f"{base}?{urlencode({'spelgroepId': spelgroep_id, 'pouleId': poule_id})}"
    except Exception:
        return None


def _render_rangschikking_link(reeks_url: str) -> None:
    """PADEL_ANALYSIS_RANGSCHIKKING_LINK_2026-09-26 (op verzoek van Kim:
    "zou ik daar een extra tab willen met rangschikking en daar gewoon in
    1ste instantie een link naar de rangschikking"):
    de tab "🏆 Rangschikking" bestaat al (roept oa.render_ranking_tab() aan
    - een eigen berekende tabel); dit voegt bovenaan die tab enkel de
    gevraagde rechtstreekse link naar de OFFICIELE TVL-pagina toe."""
    url = _build_rangschikking_url(reeks_url)
    if url:
        try:
            st.link_button("\\U0001F517 Bekijk de officiele rangschikking op TVL", url)
        except AttributeError:
            st.markdown(f"[\\U0001F517 Bekijk de officiele rangschikking op TVL]({url})")
        st.caption(url)
    else:
        st.info(
            "Kon de rangschikkingslink nog niet automatisch afleiden - het poule/tabel-schema "
            "moet eerst geladen zijn (zie 'Volgende match' hierboven)."
        )
    st.divider()

'''

SUB_RANGSCHIKKING_OLD = (
    '            with sub_rangschikking:\n'
    '                if report_for_ai is not None:\n'
    '                    oa.render_ranking_tab(report_for_ai)\n'
    '                else:\n'
    '                    st.info("Nog geen rapport beschikbaar voor deze tegenploeg.")'
)
SUB_RANGSCHIKKING_NEW = (
    '            with sub_rangschikking:\n'
    '                # PADEL_ANALYSIS_RANGSCHIKKING_LINK_2026-09-26: link naar\n'
    '                # de officiele TVL-rangschikking, bovenaan deze tab.\n'
    '                _render_rangschikking_link(reeks_url)\n'
    '                if report_for_ai is not None:\n'
    '                    oa.render_ranking_tab(report_for_ai)\n'
    '                else:\n'
    '                    st.info("Nog geen rapport beschikbaar voor deze tegenploeg.")'
)


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    m1 = FINAL_SCORE_PATTERN.search(tekst)
    if not m1:
        print("  KON _fixture_final_score() NIET AFBAKENEN - niets gewijzigd.")
        return False

    m2 = FIXTURE_ROWS_PATTERN.search(tekst)
    if not m2:
        print("  KON _fixture_rows() NIET AFBAKENEN - niets gewijzigd.")
        return False

    if PREV_LINEUP_ROWS_OLD not in tekst:
        print("  KON DE AANROEP VAN _fixture_rows() IN _render_previous_opponent_lineup() "
              "NIET VINDEN - niets gewijzigd.")
        return False

    if SUB_RANGSCHIKKING_OLD not in tekst:
        print("  KON HET sub_rangschikking-BLOK NIET VINDEN - niets gewijzigd.")
        return False

    if "def page_lineup_lab():" not in tekst:
        print("  KON page_lineup_lab() NIET VINDEN - niets gewijzigd.")
        return False

    stappen = [(m1, FINAL_SCORE_NEW, "_fixture_final_score"), (m2, FIXTURE_ROWS_NEW, "_fixture_rows")]
    nieuw = tekst
    for m, new_text, naam in sorted(stappen, key=lambda s: s[0].start(), reverse=True):
        nieuw = nieuw[:m.start()] + new_text + nieuw[m.end():]
        print(f"  {naam}: klaar om te vervangen.")

    nieuw = nieuw.replace(PREV_LINEUP_ROWS_OLD, PREV_LINEUP_ROWS_NEW, 1)
    print("  aanroep van _fixture_rows(): klaar om te vervangen.")

    nieuw = nieuw.replace(SUB_RANGSCHIKKING_OLD, SUB_RANGSCHIKKING_NEW, 1)
    print("  sub_rangschikking-tab: klaar om de link toe te voegen.")

    # Helper-functies invoegen vlak voor page_lineup_lab().
    invoegpunt = nieuw.index("def page_lineup_lab():")
    nieuw = nieuw[:invoegpunt] + RANGSCHIKKING_HELPER.lstrip("\n") + "\n" + nieuw[invoegpunt:]
    print("  _build_rangschikking_url() + _render_rangschikking_link(): klaar om toe te voegen.")

    if not apply:
        print(f"\n  {pad.name}: DRY-RUN, klaar om te patchen ({len(tekst)} -> {len(nieuw)} tekens).")
        return True

    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pad.with_suffix(f".py.bak_{stempel}")
    shutil.copy2(pad, backup)
    pad.write_text(nieuw, encoding="utf-8")
    print(f"\n  {pad.name}: GEPATCHT. Back-up: {backup.name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Toont ploegnaam bij Winnaar, en voegt een rangschikking-link toe."
    )
    parser.add_argument("--apply", action="store_true",
                        help="Voer de wijziging effectief uit (anders enkel tonen).")
    parser.add_argument("--file", default="page_lineup_lab.py",
                        help="Pad naar page_lineup_lab.py (standaard: huidige map).")
    args = parser.parse_args()

    pad = Path(args.file).resolve()
    print(f"Bestand: {pad}")
    print(f"Modus: {'TOEPASSEN' if args.apply else 'DRY-RUN (er wordt niets gewijzigd)'}\n")

    gelukt = _patch(pad, args.apply)

    print()
    if not gelukt:
        print("Er is niets gewijzigd.")
        return
    if args.apply:
        check_cmd = (
            "python -c \"import ast; ast.parse(open(r'"
            + pad.name
            + "', encoding='utf-8').read()); print('OK')\""
        )
        print("Klaar. Controleer met:")
        print(f"  {check_cmd}")
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
