"""
apply_uitslag_and_winner_fix.py - repareert de eindscore-weergave in
page_lineup_lab.py, nu de onderliggende bug in scraper_v2.py/opponent_scout.py
is opgelost (zie de fixes daar: PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25 en
PADEL_ANALYSIS_OTHER_PAIR_AND_TEAM_SCORE_2026-09-25).

Locatie: PadelAnalysis/apply_uitslag_and_winner_fix.py  (eenmalig te draaien,
NA scraper_v2.py en opponent_scout.py vervangen te hebben)

PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25 (op verzoek van Kim:
"vergeet die Elke Carrein dat was volgens mij wel al opgelost. De laatste
kolom met Resultaat toont nog steeds onbekend bij de opstelling analyse van
eerdere ontmoetingen. totaal resultaat met games en sets en totale score
wordt ook niet getoond. kolom resultaat moet kolom 'winnaar' worden waar de
naam van de ploeg komt die die match gewonnen heeft en die lijn in het groen
als het de ploeg is die de volgende tegenstander wordt [...] als extra test
wil ik zeker de naam van de kolom veranderen zodat ik daarmee ook extra kan
zien of de code effectief goed gecommit wordt")
--------------------------------------------------------------------------
ROOT CAUSE VAN "Resultaat: Onbekend" (grondig uitgezocht, niet langer een
vermoeden): scrape_uitslagenblad() in scraper_v2.py zocht per bord naar een
LOSSE LETTER "W"/"V" in de kolomtekst - die letters bestaan NERGENS op een
interclub-uitslagenblad. De echte kolom heet "Uitslag" (data-title="Uitslag")
en bevat een numeriek paar "0-1"/"1-0". "won" bleef daardoor ALTIJD None,
ongeacht hoe correct opponent_scout.py en page_lineup_lab.py daarna met dat
veld omgingen - ze kregen simpelweg nooit bruikbare invoer. Zie
scraper_v2.py voor de volledige analyse en fix, bevestigd tegen de ECHTE
HTML-structuur van een uitslagenblad (2 onafhankelijke bordrijen,
gecontroleerd tegen de <b class="bold">-winnaarmarkering die de site zelf
ook toont).

WAT DIT SCRIPT WIJZIGT (in page_lineup_lab.py, nu de brondata eindelijk
klopt):

1. _fixture_rows(): kolom "Resultaat" (Gewonnen/Verloren/Onbekend) wordt
   kolom "Winnaar", met de NAAM van de winnende DUO (niet enkel een
   ja/nee-label). Dit gebruikt het nieuwe "other_pair"-veld uit
   opponent_scout.py (de tot nu toe weggegooide, niet-gescoute kant van elk
   bord) zodat de winnaar-naam getoond kan worden ONGEACHT welke kant won.
   De rij wordt groen gekleurd wanneer de GESCOUTE ploeg (onze eerstvolgende
   tegenstander) dat bord won.

2. _render_fixture_rows_table(): kleurt op basis van dat nieuwe
   "opponent_won"-veld i.p.v. de tekstwaarde van "Resultaat" te vergelijken.

3. _fixture_final_score(): geeft nu een DICT terug met de ECHTE eindscore
   uit de "Samenvatting"-sectie van de pagina zelf (team_score_matches/
   sets/games, rechtstreeks gescrapet - zie scraper_v2.py) i.p.v. deze cijfers
   af te leiden door borden te tellen. Dat lost meteen ook "totaal resultaat
   met games en sets [...] wordt niet getoond" op: sets en spellen waren
   voorheen nergens beschikbaar, enkel het aantal gewonnen borden.

4. _render_previous_opponent_lineup(): toont nu het volledige lange formaat
   (Matchen X-Y, Sets X-Y, Spellen X-Y) plus de winnaar-naam in het groen.

5. Versiestempel PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25 -
   grep-baar, en de kolomnaamswijziging zelf ("Resultaat" -> "Winnaar") is
   Kim's eigen ingebouwde test: is de kolom na deployment nog "Resultaat",
   dan is deze fix niet aangekomen.

GEBRUIK (PowerShell, vanuit PadelAnalysis):

    python apply_uitslag_and_winner_fix.py           # dry-run
    python apply_uitslag_and_winner_fix.py --apply   # uitvoeren

Idempotent: een tweede run merkt dat de fix er al staat en doet niets.
Maakt een back-up (.bak_<timestamp>) voor het schrijven.
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

MARKER = "PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25"

# ── 1. _fixture_rows() + _render_fixture_rows_table(): functiegrens-gebaseerd ──
FIXTURE_ROWS_PATTERN = re.compile(
    r"^def _fixture_rows\(.*?(?=^def _parse_set_score\()",
    re.S | re.M,
)

FIXTURE_ROWS_NEW = '''def _fixture_rows(boards: list) -> list:
    """Zet de dubbels van 1 ontmoeting om naar tabelrijen, MET klassement.

    PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25 (op verzoek van
    Kim: "kolom resultaat moet kolom 'winnaar' worden waar de naam van de
    ploeg komt die die match gewonnen heeft en die lijn in het groen als
    het de ploeg is die de volgende tegenstander wordt"):
    ----------------------------------------------------------------------
    ROOT CAUSE van "Resultaat: Onbekend": scrape_uitslagenblad() zocht naar
    een niet-bestaande "W"/"V"-letter i.p.v. het echte "Uitslag"-veld
    (0-1/1-0) - zie PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25 in
    scraper_v2.py voor de volledige analyse en fix, bevestigd tegen de
    echte HTML. Met die fix is "opponent_won" hier eindelijk bruikbaar.

    FIX: kolom "Winnaar" toont nu de NAAM van de winnende duo (via het
    nieuwe "other_pair"-veld uit opponent_scout.py - de tot nu toe
    weggegooide, niet-gescoute kant van elk bord), niet enkel een
    Gewonnen/Verloren-label. Een apart "opponent_won"-veld per rij (bool of
    None) bepaalt de kleur in _render_fixture_rows_table() hieronder."""
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
        if opponent_won is True:
            winnaar_namen = " / ".join(p.get("name", "?") for p in pair)
        elif opponent_won is False and len(other_pair) == 2:
            winnaar_namen = " / ".join(p.get("name", "?") for p in other_pair)
        else:
            winnaar_namen = "Onbekend"
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


def _render_fixture_rows_table(rows: list) -> None:
    """PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25: toont
    _fixture_rows()-resultaat met een groene rij zodra de GESCOUTE ploeg
    (onze eerstvolgende tegenstander) dat bord won, en een lichte rode tint
    wanneer zij het verloren. "Onbekend" (geen leesbare score) blijft
    ongekleurd. Faalt de styling (bv. een oudere pandas/Streamlit-versie),
    dan valt dit terug op de gewone, ongekleurde tabel - nooit een crash
    voor een puur cosmetische toevoeging."""
    if not rows:
        st.info("Geen bruikbare dubbels in deze ontmoeting.")
        return
    zichtbare_kolommen = [k for k in rows[0].keys() if not k.startswith("_")]
    try:
        import pandas as _pd

        def _kleur_resultaat(row):
            if row.get("_opponent_won") is True:
                return ["background-color: #d4edda"] * len(row)
            if row.get("_opponent_won") is False:
                return ["background-color: #f8d7da"] * len(row)
            return [""] * len(row)

        df = _pd.DataFrame(rows)
        styled = df.style.apply(_kleur_resultaat, axis=1)
        st.dataframe(
            styled, use_container_width=True, hide_index=True,
            column_order=zichtbare_kolommen,
        )
        st.caption(
            "\\U0001F7E2 Groen = de GESCOUTE ploeg (onze eerstvolgende tegenstander) won dit bord - "
            "een gevaarlijk koppel om rekening mee te houden. \\U0001F534 Rood = zij verloren dit bord."
        )
    except Exception:
        st.dataframe(
            [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
            use_container_width=True, hide_index=True,
        )


'''

# ── 2. _fixture_final_score(): functiegrens-gebaseerd ──
FINAL_SCORE_PATTERN = re.compile(
    r"^def _fixture_final_score\(.*?(?=^def _render_previous_opponent_lineup\()",
    re.S | re.M,
)

FINAL_SCORE_NEW = '''def _fixture_final_score(
    fx: dict, boards: list, scouted_team_name: str, opponent_ploeg_id: str = None,
    fixture_bundle: dict = None,
):
    """Eindscore van 1 volledige ontmoeting: matchen/sets/spellen + winnaar.

    PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25 (op verzoek van
    Kim: "totaal resultaat met games en sets en totale score wordt ook niet
    getoond"):
    ----------------------------------------------------------------------
    ROOT CAUSE: deze functie leidde de eindscore voorheen af door borden te
    TELLEN (via opponent_won) - dat gaf enkel het aantal gewonnen MATCHEN,
    nooit Sets of Spellen, want die informatie zit niet op bordniveau
    samengevat. De ECHTE eindscore staat rechtstreeks op de pagina, in de
    "Samenvatting"-sectie (Uitslag/Sets/Spellen) - scrape_uitslagenblad()
    leest dit nu expliciet (zie PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25
    in scraper_v2.py) en opponent_scout.py geeft het door als
    fixture_bundle["team_score_matches"/"team_score_sets"/"team_score_games"].

    FIX: gebruikt nu RECHTSTREEKS die gescrapete team-niveau velden. Enkel
    als die (bv. bij een ouder, nog niet herscraped uitslagenblad)
    ontbreken, valt dit terug op de oude bordentelling - dan ontbreken Sets
    en Spellen noodgedwongen, maar het aantal gewonnen matchen blijft
    beschikbaar.

    Geeft een dict terug: {"home_name", "away_name", "matches", "sets",
    "games", "winner"} - "matches"/"sets"/"games" zijn elk (thuis, uit) of
    None, "winner" is de teamnaam of None.
    """
    fixture_bundle = fixture_bundle or {}
    home_name = fixture_bundle.get("home_team") or fx.get("home_name") or ""
    away_name = fixture_bundle.get("away_team") or fx.get("away_name") or ""
    winner = fixture_bundle.get("winner_team")

    matches_pair = fixture_bundle.get("team_score_matches")
    sets_pair = fixture_bundle.get("team_score_sets")
    games_pair = fixture_bundle.get("team_score_games")

    if matches_pair is None:
        # Terugval (oud gedrag): tellen via de borden - enkel het aantal
        # gewonnen matchen is dan beschikbaar, geen sets/spellen.
        scouted_wins = sum(1 for b in boards if b.get("opponent_won") is True)
        other_wins = sum(1 for b in boards if b.get("opponent_won") is False)
        known = scouted_wins + other_wins
        if known == 0:
            return None
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
    }


'''

# ── 3. _render_previous_opponent_lineup(): functiegrens-gebaseerd ──
PREV_LINEUP_PATTERN = re.compile(
    r"^def _render_previous_opponent_lineup\(.*?(?=^def _render_match1_frequency_opponent\()",
    re.S | re.M,
)

PREV_LINEUP_NEW = '''def _render_previous_opponent_lineup(bundle: dict, opp: dict = None, full_bundle: dict = None) -> None:
    """Eerdere ontmoetingen van de tegenstander, kiesbaar via dropdown.

    PADEL_ANALYSIS_WINNER_COLUMN_AND_TEAM_SCORE_2026-09-25 (op verzoek van
    Kim: "totaal resultaat met games en sets en totale score wordt ook niet
    getoond [...] Gewonnen ploeg kan je groen zetten ook"):
    toont nu het volledige lange formaat - Matchen X-Y, Sets X-Y, Spellen
    X-Y - plus de winnaar-naam apart, in het groen. Zie
    _fixture_final_score() voor waar deze cijfers nu vandaan komen
    (rechtstreeks van de pagina, niet langer afgeleid uit bordentelling).
    """
    source = full_bundle if (full_bundle or {}).get("previous_fixtures") else bundle
    previous_fixtures = (source or {}).get("previous_fixtures") or []
    if not previous_fixtures:
        return
    bruikbaar = []
    for fx_bundle in previous_fixtures:
        if fx_bundle.get("error") or not (fx_bundle.get("boards") or []):
            continue
        bruikbaar.append(fx_bundle)
    titel = f"\\U0001F4CB Tegenstander \\u2014 eerdere ontmoeting(en) ter referentie ({len(bruikbaar)})"
    with st.expander(titel, expanded=False):
        st.caption(
            "De opstelling die de TEGENSTANDER gebruikte in hun al gespeelde wedstrijden dit "
            "seizoen, met per speler het officiele klassement en (waar gekend) de padelstat "
            "playing strength. 'Rotatie X \\u2014 Match Y' volgt de volgorde op het uitslagenblad."
        )
        if not bruikbaar:
            st.info("Geen match-detail beschikbaar voor de gekende eerdere ontmoeting(en).")
            return
        scouted_name = (opp or {}).get("name") or ""
        opponent_ploeg_id = (opp or {}).get("ploeg_id")
        labels = []
        scores = []
        for fx_bundle in bruikbaar:
            fx = fx_bundle.get("fixture", {}) or {}
            datum = fx.get("date_text", "?")
            tegen = fx_bundle.get("home_team") or fx.get("home_name") or ""
            uit = fx_bundle.get("away_team") or fx.get("away_name") or ""
            wedstrijd = f" ({tegen} vs {uit})" if tegen and uit else ""
            labels.append(f"{datum}{wedstrijd}")
            score = _fixture_final_score(
                fx, fx_bundle.get("boards") or [], scouted_name,
                opponent_ploeg_id=opponent_ploeg_id, fixture_bundle=fx_bundle,
            )
            scores.append(score)
        if len(bruikbaar) > 1:
            def _label_met_eindscore(i):
                s = scores[i]
                if not s or not s.get("matches"):
                    return labels[i]
                m = s["matches"]
                return f"{labels[i]} \\u2014 {m[0]}-{m[1]}"
            keuze = st.selectbox(
                "Welke ontmoeting wil je bekijken?", list(range(len(bruikbaar))),
                format_func=_label_met_eindscore, index=len(bruikbaar) - 1,
                key=f"prev_fixture_pick_{id(source)}",
            )
        else:
            keuze = 0
            m = (scores[0] or {}).get("matches")
            titel_txt = f"**{labels[0]}**"
            if m:
                titel_txt += f" \\u2014 **{m[0]}-{m[1]}**"
            st.caption(f"Enige gekende ontmoeting: {titel_txt}")
        score = scores[keuze]
        if score and score.get("matches"):
            home, away = score["home_name"] or "?", score["away_name"] or "?"
            m = score["matches"]
            delen = [f"Matchen: {m[0]}-{m[1]}"]
            if score.get("sets"):
                s = score["sets"]
                delen.append(f"Sets: {s[0]}-{s[1]}")
            if score.get("games"):
                g = score["games"]
                delen.append(f"Spellen: {g[0]}-{g[1]}")
            st.markdown(f"**Eindscore: {home} - {away}**")
            st.markdown(" \\u00b7 ".join(delen))
            if score.get("winner"):
                st.success(f"\\U0001F7E2 Winnaar: **{score['winner']}**")
            st.caption(
                "Rechtstreeks van de 'Samenvatting'-sectie van het uitslagenblad - niet afgeleid "
                "uit de bordresultaten hieronder."
            )
        rows = _fixture_rows(bruikbaar[keuze].get("boards") or [])
        _render_fixture_rows_table(rows)


'''


def _patch(pad: Path, apply: bool) -> bool:
    if not pad.exists():
        print(f"  NIET GEVONDEN: {pad}")
        return False

    tekst = pad.read_text(encoding="utf-8")

    if MARKER in tekst:
        print(f"  {pad.name}: fix staat er al - overgeslagen.")
        return False

    if "PADEL_ANALYSIS_UITSLAG_FIELD_FIX_2026-09-25" not in _read_scraper_v2_marker(pad):
        print(f"  {pad.name}: WAARSCHUWING - scraper_v2.py lijkt de voorafgaande fix nog niet te "
              "bevatten. Dit script gaat toch door (page_lineup_lab.py staat los van scraper_v2.py "
              "als python-bestand), maar zonder die fix blijft 'opponent_won' leeg en verandert er "
              "voor jou zichtbaar niets. Controleer dat eerst.")

    stappen = []
    for naam, patroon in (
        ("_fixture_rows + _render_fixture_rows_table", FIXTURE_ROWS_PATTERN),
        ("_fixture_final_score", FINAL_SCORE_PATTERN),
        ("_render_previous_opponent_lineup", PREV_LINEUP_PATTERN),
    ):
        m = patroon.search(tekst)
        if not m:
            print(f"  KON '{naam}' NIET AFBAKENEN - niets gewijzigd.")
            return False
        stappen.append((naam, m))

    vervangingen = {
        "_fixture_rows + _render_fixture_rows_table": FIXTURE_ROWS_NEW,
        "_fixture_final_score": FINAL_SCORE_NEW,
        "_render_previous_opponent_lineup": PREV_LINEUP_NEW,
    }

    nieuw = tekst
    for naam, m in sorted(stappen, key=lambda s: s[1].start(), reverse=True):
        nieuw = nieuw[:m.start()] + vervangingen[naam] + nieuw[m.end():]
        print(f"  {naam}: klaar om te vervangen.")

    if not apply:
        print(f"\n  {pad.name}: DRY-RUN, klaar om te patchen ({len(tekst)} -> {len(nieuw)} tekens).")
        return True

    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = pad.with_suffix(f".py.bak_{stempel}")
    shutil.copy2(pad, backup)
    pad.write_text(nieuw, encoding="utf-8")
    print(f"\n  {pad.name}: GEPATCHT. Back-up: {backup.name}")
    return True


def _read_scraper_v2_marker(page_lineup_lab_pad: Path) -> str:
    scraper_pad = page_lineup_lab_pad.parent / "scraper" / "scraper_v2.py"
    if not scraper_pad.exists():
        scraper_pad = page_lineup_lab_pad.parent / "scraper_v2.py"
    if not scraper_pad.exists():
        return ""
    try:
        return scraper_pad.read_text(encoding="utf-8")
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Toont de winnaar-naam per bord en de echte team-eindscore (matchen/sets/spellen)."
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
        print()
        print("Kim's eigen test: open de app en controleer of de kolom nu 'Winnaar' heet")
        print("(niet meer 'Resultaat') - dat bevestigt dat deze fix effectief gedeployed is.")
    else:
        print("Dit was een dry-run. Draai opnieuw met --apply om het uit te voeren.")


if __name__ == "__main__":
    main()
