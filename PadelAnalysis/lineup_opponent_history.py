"""
lineup_opponent_history.py - Tegenstander-referentie: klassementsteksten,
uitslagenblad-rijen, eindscoreberekening, eerdere-ontmoetingen-dropdown en
match1/match2-frequentieanalyse.
Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27).
Zie de oorspronkelijke, monolithische versie van page_lineup_lab.py voor de
volledige historische toelichting bij elke fix in deze functies (o.a.
PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-26, PADEL_ANALYSIS_WINNER_COLUMN_
AND_TEAM_SCORE_2026-09-25, PADEL_ANALYSIS_OPPONENT_RANKS_IN_MATCH_TABLE_
2026-09-24, PADEL_ANALYSIS_FREQUENCY_ALL_FIXTURES_2026-09-22) - functioneel
ONGEWIJZIGD t.o.v. de vorige versie.
--------------------------------------------------------------------------
PADEL_ANALYSIS_PREVIOUS_FIXTURES_PAIR_COLUMNS_2026-10-10 (op verzoek van Kim:
"bij analyse van een ploeg, eerdere ontmoetingen mag je ook meer details geven
over tegen wie. Dus koppels van de geselecteerde ploeg in 1 kolom en
tegenstander koppel in 1 kolom. Van allebei klassement info en dan score en
winnaar etc.")
--------------------------------------------------------------------------
De tabel per eerdere ontmoeting had per rij vier kolommen (Speler 1,
Klassement 1, Speler 2, Klassement 2) en toonde enkel het koppel van de
GESCOUTE ploeg. Nu: Match | Koppel geselecteerde ploeg | Koppel tegenstander |
Score | Winnaar. Elk koppel staat in 1 cel, met per speler het klassement
("Naam (P200 · ps P180)"). Groen = de geselecteerde ploeg won deze match,
rood = verloren (ongewijzigd). Erboven staat welke ploeg welke is.
BEKENDE BEPERKING: het klassement van de TEGENSTANDER (other_pair) wordt enkel
getoond als de uitslagenblad-data dat per speler bevat (veld "ranking" of
"user_id"). Ontbreekt dat, dan staat enkel de naam en verschijnt onder de
tabel een melding - er wordt nooit een klassement verzonnen. De score staat
zoals ze op het uitslagenblad staat (niet omgedraaid).
Zichtbare tekst gebruikt "match/matchen" i.p.v. "bord/borden".
"""
import re
import streamlit as st
from dashboard_common import _clean_name
from lineup_scout import _cached_official_rank, _cached_own_player_rating


def _rank_text_for_opponent(player: dict) -> str:
    """Officieel klassement + padelstat playing strength van 1 tegenstander-
    speler, als korte tekst."""
    uid = str(player.get("user_id") or "")
    officieel = player.get("ranking")
    if not officieel and uid:
        rank = _cached_official_rank(uid)
        if rank is not None:
            officieel = f"P{int(rank)}"
    padelstat = _cached_own_player_rating(uid) if uid else None
    delen = [str(officieel) if officieel else "P?"]
    if padelstat is not None:
        delen.append(f"ps P{int(padelstat)}")
    return " / ".join(delen)


def _player_text(player: dict) -> tuple:
    """"Naam (P200 · ps P180)". Geeft (tekst, heeft_klassement_info). Zonder
    "ranking" en zonder "user_id" is er niets op te zoeken: dan enkel de naam."""
    naam = player.get("name", "?")
    if not (player.get("ranking") or player.get("user_id")):
        return naam, False
    info = _rank_text_for_opponent(player).replace(" / ", " \u00b7 ")
    return f"{naam} ({info})", True


def _pair_text(pair: list) -> tuple:
    """Koppel in 1 cel: "Speler A (P200) / Speler B (P100)". Geeft (tekst, alle_info)."""
    if not pair:
        return "onbekend", False
    delen, alle_info = [], True
    for p in pair:
        tekst, heeft_info = _player_text(p)
        delen.append(tekst)
        alle_info = alle_info and heeft_info
    return " / ".join(delen), alle_info


def _fixture_rows(
    boards: list, home_team: str = None, away_team: str = None,
    is_opponent_home: bool = None,
) -> list:
    """Zet de dubbels van 1 ontmoeting om naar tabelrijen: het koppel van de
    geselecteerde ploeg en het koppel van de tegenstander, elk in 1 cel, MET
    klassement. PADEL_ANALYSIS_PREVIOUS_FIXTURES_PAIR_COLUMNS_2026-10-10."""
    heeft_teaminfo = (
        home_team is not None and away_team is not None and is_opponent_home is not None
    )
    scouted_team = other_team = None
    if heeft_teaminfo:
        scouted_team = home_team if is_opponent_home else away_team
        other_team = away_team if is_opponent_home else home_team
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
        scout_txt, _scout_info = _pair_text(pair)
        other_txt, other_info = _pair_text(other_pair if len(other_pair) == 2 else [])
        rows.append({
            "Match": f"Rotatie {rot} - Match {m_in_rot}" if pos else "Match ?",
            "Koppel geselecteerde ploeg": scout_txt,
            "Koppel tegenstander": other_txt,
            "Score": b.get("score") or "onbekend",
            "Winnaar": winnaar_namen,
            "_opponent_won": opponent_won,
            "_scouted_team": scouted_team,
            "_other_team": other_team,
            "_other_info_missing": not other_info,
        })
    return rows


def _render_fixture_rows_table(rows: list) -> None:
    """Toont _fixture_rows()-resultaat met een groene rij zodra de GESCOUTE
    ploeg die match won, en een lichte rode tint wanneer zij hem verloor."""
    if not rows:
        st.info("Geen bruikbare dubbels in deze ontmoeting.")
        return
    scouted, other = rows[0].get("_scouted_team"), rows[0].get("_other_team")
    if scouted and other:
        st.markdown(f"**{scouted}** (geselecteerde ploeg) tegen **{other}**")
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
            "Groen = de geselecteerde ploeg won deze match - een gevaarlijk koppel om rekening mee te "
            "houden. Rood = zij verloren deze match. De score staat zoals op het uitslagenblad."
        )
        if any(r.get("_other_info_missing") for r in rows):
            st.caption(
                "Het klassement van (een deel van) de tegenstanders ontbreekt in de gegevens van het "
                "uitslagenblad - daar staat enkel de naam."
            )
    except Exception:
        st.dataframe(
            [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
            use_container_width=True, hide_index=True,
        )


def _parse_set_score(score_text: str):
    """Ontleedt 1 matchscore tot (sets_links, sets_rechts). None bij
    onleesbare tekst."""
    if not score_text:
        return None
    sets_links = sets_rechts = 0
    gevonden = False
    for token in re.split(r"[\s,]+", str(score_text).strip()):
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", token)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a == b:
            continue
        gevonden = True
        if a > b:
            sets_links += 1
        else:
            sets_rechts += 1
    if not gevonden:
        return None
    return sets_links, sets_rechts


def _fixture_final_score(
    fx: dict, boards: list, scouted_team_name: str, opponent_ploeg_id: str = None,
    fixture_bundle: dict = None,
):
    """Eindscore van 1 volledige ontmoeting: matchen/sets/spellen + winnaar."""
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


def _render_previous_opponent_lineup(bundle: dict, opp: dict = None, full_bundle: dict = None) -> None:
    """Eerdere ontmoetingen van de tegenstander, kiesbaar via dropdown."""
    source = full_bundle if (full_bundle or {}).get("previous_fixtures") else bundle
    previous_fixtures = (source or {}).get("previous_fixtures") or []
    if not previous_fixtures:
        return
    bruikbaar = []
    for fx_bundle in previous_fixtures:
        if fx_bundle.get("error") or not (fx_bundle.get("boards") or []):
            continue
        bruikbaar.append(fx_bundle)
    titel = f"Tegenstander - eerdere ontmoeting(en) ter referentie ({len(bruikbaar)})"
    with st.expander(titel, expanded=False):
        st.caption(
            "De opstelling die de TEGENSTANDER gebruikte in hun al gespeelde wedstrijden dit "
            "seizoen, met per speler het officiele klassement en (waar gekend) de padelstat "
            "playing strength. 'Rotatie X - Match Y' volgt de volgorde op het uitslagenblad."
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
                return f"{labels[i]} - {m[0]}-{m[1]}"
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
                titel_txt += f" - **{m[0]}-{m[1]}**"
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
            st.markdown(" \u00b7 ".join(delen))
            if score.get("winner"):
                st.success(f"Winnaar: **{score['winner']}**")
            st.caption(
                "Rechtstreeks van de 'Samenvatting'-sectie van het uitslagenblad - niet afgeleid "
                "uit de matchresultaten hieronder."
            )
        rows = _fixture_rows(
            bruikbaar[keuze].get("boards") or [],
            home_team=(score or {}).get("home_name"),
            away_team=(score or {}).get("away_name"),
            is_opponent_home=(score or {}).get("is_scouted_home"),
        )
        _render_fixture_rows_table(rows)


def _render_match1_frequency_opponent(bundle: dict, full_bundle: dict = None) -> None:
    """Match 1 / Match 2-frequentie per tegenstander-speler."""
    source = full_bundle if (full_bundle or {}).get("previous_fixtures") else bundle
    previous_fixtures = (source or {}).get("previous_fixtures") or []
    boards_met_positie = [
        b for fx in previous_fixtures for b in (fx.get("boards") or [])
        if b.get("board_position") is not None and len(b.get("opponent_pair") or []) == 2
    ]
    if not boards_met_positie:
        return
    tellingen, namen = {}, {}
    for b in boards_met_positie:
        pos = b["board_position"]
        is_eerste_match_van_rotatie = (pos % 2 == 1)
        for p in b["opponent_pair"]:
            uid = p.get("user_id")
            if not uid:
                continue
            namen[uid] = p.get("name", uid)
            tellingen.setdefault(uid, {"match1": 0, "match2": 0})
            if is_eerste_match_van_rotatie:
                tellingen[uid]["match1"] += 1
            else:
                tellingen[uid]["match2"] += 1
    n_fixtures = len(previous_fixtures)
    n_boards = len(boards_met_positie)
    with st.expander(
        f"Tegenstander - match 1 / match 2-frequentie per rotatie "
        f"(over {n_fixtures} ontmoeting(en), {n_boards} dubbel(s))",
        expanded=False,
    ):
        st.caption(
            "Hoe vaak elke tegenstander-speler de EERSTE match van een rotatie speelde (Match 1, "
            "Match 3, ...) versus de TWEEDE match van een rotatie (Match 2, Match 4, ...), over "
            "ALLE gekende, al gespeelde ontmoetingen van deze ploeg dit seizoen. Puur "
            "beschrijvend - geen voorspelling."
        )
        if n_fixtures <= 1:
            st.caption(
                "Slechts 1 ontmoeting gekend - gebaseerd op een enkel datapunt. Meer "
                "ontmoetingen verschijnen hier automatisch zodra deze ploeg er gespeeld heeft."
            )
        rows = []
        for uid, counts in sorted(tellingen.items(), key=lambda kv: -kv[1]["match1"]):
            totaal = counts["match1"] + counts["match2"]
            pct1 = round(100 * counts["match1"] / totaal, 0) if totaal else 0
            pct2 = round(100 * counts["match2"] / totaal, 0) if totaal else 0
            officieel = _cached_official_rank(str(uid))
            padelstat = _cached_own_player_rating(str(uid))
            rows.append({
                "Speler": namen.get(uid, uid),
                "Officieel": f"P{int(officieel)}" if officieel is not None else "?",
                "Padelstat": f"P{int(padelstat)}" if padelstat is not None else "-",
                "Match 1 (of 3, 5, ...)": f"{counts['match1']}x ({int(pct1)}%)",
                "Match 2 (of 4, 6, ...)": f"{counts['match2']}x ({int(pct2)}%)",
                "Totaal dubbels": totaal,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _most_recent_opponent_player_ids(bundle: dict) -> set:
    previous_fixtures = bundle.get("previous_fixtures") or []
    if not previous_fixtures:
        return set()
    most_recent = previous_fixtures[-1]
    boards = most_recent.get("boards") or []
    ids = set()
    for b in boards:
        for p in (b.get("opponent_pair") or []):
            uid = p.get("user_id")
            if uid:
                ids.add(str(uid))
    return ids
