# -*- coding: utf-8 -*-
"""
poule_ranking.py - PADEL_ANALYSIS_POULE_RANKING_SCENARIOS_2026-09-27 (op
verzoek van Kim: "effectief ook het scorebord van de poule te kunnen
scrapen op de pagina waar nu de link staat [...] Wat daar handig is, is
dat je dan meteen ook scenario's kan tonen hoe we kunnen doorgaan. de
eerste 2 van een poule gaan door. [...] als wij nog 2 keer winnen dan ga
je zeker door. Als je nog 1 keer wint, maar ploeg A doet dit en B dat dan
ga je ook door etc [...] bij gelijke eindscore [gaat] de ploeg door die
de onderlinge confrontatie gewonnen heeft.").
--------------------------------------------------------------------------
BRON: interclub-rangschikking-pagina - VOLLEDIG PUBLIEK, GEEN LOGIN NODIG
--------------------------------------------------------------------------
Bevestigd in de ruwe HTML zelf: `Liferay.ThemeDisplay.isSignedIn(): false`
en de pagina laadt de volledige rangschikkingstabel gewoon. Geen
authenticatie-omweg nodig - een kale requests.get() volstaat, net als bij
schedule_scraper.py's poule-schema-fetch.
De pagina-URL is opgebouwd uit exact dezelfde spelgroepId/pouleId-
parameters die _build_rangschikking_url() (page_lineup_lab.py) al langer
correct berekent uit de bestaande poule/tabel-URL - dat stuk hoeft dus
NIET aangepast te worden, enkel hergebruikt.
--------------------------------------------------------------------------
PUNTENSYSTEEM: WISKUNDIG GEVERIFIEERD, NIET AANGENOMEN
--------------------------------------------------------------------------
Uit de echte Poule Q-rangschikking (6 ploegen, elk 3 ontmoetingen gespeeld,
dus 9 ontmoetingen totaal dit seizoen):
    KON. DEINZE T.C. D            3 ontmoetingen, 4 punten
    T.C. ELEVEN C                 3 ontmoetingen, 4 punten
    Padel Factory B               3 ontmoetingen, 4 punten
    T.C. 'T LOBBEKE B             3 ontmoetingen, 3 punten
    K.T.C. DE WITTE KAPROENEN A   3 ontmoetingen, 2 punten
    LUDOVIEK Padel C              3 ontmoetingen, 1 punt
Som van alle punten = 18 = EXACT 9 ontmoetingen x 2 punten - dit klopt
ENKEL bij een systeem waar elke ontmoeting altijd samen 2 punten verdeelt:
    - WIN (3 of 4 van de 4 borden) = 2 punten, verlies = 0 punten
    - GELIJKSPEL (2-2 op de 4 borden) = 1 punt voor BEIDE ploegen
Deze som-check is een KEIHARDE wiskundige bevestiging, geen aanname - bij
eender welk ander puntensysteem (bv. 3-1-0, of 1-0) zou de som NIET exact
18 uitkomen bij deze concrete data. WIN_POINTS/DRAW_POINTS/LOSS_POINTS
hieronder zijn dus geverifieerd, niet gegokt.
--------------------------------------------------------------------------
KWALIFICATIE: "EERSTE 2 GAAN DOOR" - ALTIJD ZO IN DE POULEFASE
--------------------------------------------------------------------------
Bevestigd door Kim (2026-09-27): "eerste 2 gaan door is altijd zo in
poulefase." QUALIFYING_PLACES hieronder is dus een vaste constante (2),
niet per afdeling instelbaar - in tegenstelling tot de puntengrens-per-
rotatie-regels in tournament_rules.py, die WEL per afdeling verschillen.
--------------------------------------------------------------------------
TIE-BREAK: ONDERLINGE CONFRONTATIE (2-PLOEGEN-GEVAL, EXPLICIET GESCOPED)
--------------------------------------------------------------------------
Bij een gelijke eindstand tussen EXACT 2 ploegen: de ploeg die de
onderlinge ontmoeting (WIN, dus 2-0 of meer boardwinst) tussen die twee
ploegen won, gaat door. Deze module bepaalt dat rechtstreeks uit de
score van hun onderlinge fixture (schedule_scraper.parse_poule_schedule()
-resultaat) - GEEN aparte aanname, gewoon dezelfde brondata die de rest
van de app al gebruikt.
Bij een gelijke stand tussen 3 OF MEER ploegen is er geen door Kim
bevestigde regel voor de precieze cascade (kan per bond/reglement
verschillen: punten onderling, sets onderling, games onderling, ...).
Dit wordt EXPLICIET als "onbepaald - controleer handmatig" gerapporteerd
in plaats van een gok te presenteren als feit.
EERLIJKE, NOG OPEN KANTTEKENING (PADEL_ANALYSIS_H2H_SCORE_FIELD_UNVERIFIED_
2026-09-27, op melding van Kim: "systeem denkt dat wij verloren hebben
tegen TC eleven maar wij hebben gewonnen"): _encounter_result() hieronder
leidt win/verlies af uit het RUWE "score"-tekstveld van het poule-schema
(schedule_scraper.parse_poule_schedule()) - een veld dat, in tegenstelling
tot het "Uitslag"-veld dat elders in de app (lineup_opponent_history.py,
na een eerder vergelijkbare bug - PADEL_ANALYSIS_WINNER_TEAMNAME_2026-09-
26) als autoritatieve bron gebruikt wordt, NOOIT apart geverifieerd is
tegen echte win/verlies-uitkomsten. Zie diagnose_h2h_score.py voor een
gericht diagnosescript om de exacte oorzaak (orientatie thuis/uit
verwisseld, of een ander score-formaat dan verwacht) vast te stellen VOOR
dit blind te "fixen" - een gok zou hier net zo goed een nieuwe, andere bug
kunnen introduceren.
--------------------------------------------------------------------------
PADEL_ANALYSIS_THREAT_EXPLANATION_GENERALIZE_2026-09-27 (op verzoek van
Kim: "Nu vind ik de uitleg een beetje te simpel bij elke scenario [...]
Ik zoek dus eerder wat en/of statements maar dan duidelijk case by case
opgelijst")
--------------------------------------------------------------------------
ROOT CAUSE: de vorige "wat_nodig"-tekst voor de STRIKT-BOVEN-ONS-branch
("moet minstens X punt(en) minder halen dan hun maximum (Y) - bv.
minstens 1 resterende wedstrijd niet winnen") klopte TOEVALLIG bij PRECIES
1 resterende wedstrijd voor die concurrent, maar is WISKUNDIG ONVOLLEDIG/
verwarrend zodra een concurrent 2+ resterende wedstrijden heeft: "minstens
3 punten minder halen" kan bijvoorbeeld NOOIT met slechts 1 wedstrijd niet
winnen (dat scheelt maximaal 2 punten), maar de tekst suggereerde dat wel.
FIX: _describe_points_shed_requirement() hieronder berekent nu een EXACTE,
voor ELK aantal resterende wedstrijden correcte puntengrens ("mogen in
totaal hoogstens X punten halen over hun Y resterende wedstrijden, i.p.v.
hun rekenkundig maximum Z") - een AND/OF-vrije, maar wel altijd wiskundig
kloppende absolute grens, in plaats van een enkel "bv."-voorbeeld dat bij
meerdere resterende wedstrijden misleidend kan zijn.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RANKING_CACHE_2026-09-29
--------------------------------------------------------------------------
De rangschikking wordt 30 minuten gedeeld gecachet met st.cache_data. De
oude session_state-cache verdween bij elke F5. De interactieve fetch gebruikt
ook geen vaste time.sleep(1.0) meer; de algemene fetchfunctie behoudt haar
bestaande delay-parameter voor andere aanroepers.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RANKING_TIEBREAK_2026-10-10 (op verzoek van Kim: "bij
rangschikking hebben we kolommen. Plaats, ploeg, ontmoetingen, punten en
opmerking. Opmerking zal waarschijnlijk altijd leeg zijn of niet? ik wil ook
punten naast ploeg en pas daarna ontmoetingen. Als ploegen een gelijke stand
hebben moet je kijken naar het onderling resultaat. Wie dat gewonnen heeft
mag bovenaan staan van die 2.")
--------------------------------------------------------------------------
1. KOLOMMEN: Plaats - Ploeg - Punten - Ontmoetingen. De kolom "Opmerking"
   wordt enkel nog getoond als minstens 1 ploeg effectief een opmerking heeft
   (ik kan uit de code niet afleiden of TVL die ooit invult).
2. GELIJKE STAND, EXACT 2 PLOEGEN: de ploeg die de onderlinge ontmoeting won,
   staat boven. De getoonde plaats volgt die volgorde (en dus ook de groene
   "gaat door"-markering voor plaats 1 en 2).
3. DE OPEN KANTTEKENING HIERBOVEN (score-orientatie) IS NU OPGELOST DOOR
   ZELF-CONTROLE i.p.v. een gok: detect_score_orientation() rekent de
   stand opnieuw uit de gespeelde fixtures, in BEIDE mogelijke richtingen
   ("thuis-uit" en "uit-thuis"), en vergelijkt dat met de Punten die TVL zelf
   toont. Komt precies 1 richting volledig overeen, dan is die geverifieerd
   en wordt ze gebruikt. Komt geen of beide overeen, dan wordt de onderlinge
   confrontatie NIET toegepast en staat er een duidelijke melding - nooit
   een gok die een ploeg ten onrechte boven een andere zet.
3b. PADEL_ANALYSIS_RANKING_ORIENTATION_TOLERANT_2026-10-10 (Kim zag "de onderlinge
   confrontatie kon niet betrouwbaar toegepast worden"): de zelf-controle eiste
   dat ALLE ploegen exact overeenkwamen. Dat faalt zodra het opgeslagen schema
   maar 1 ontmoeting achterloopt op de live rangschikking van TVL, of 1 score
   onleesbaar is. Nu wint de richting met het kleinste totale puntenverschil
   (max. 4 punten, strikt beter dan de andere richting); orientation_diagnosis()
   geeft de details, test_poule_orientation.py toont ze voor de echte poule.
4. GELIJKE STAND, 3 OF MEER PLOEGEN: ongewijzigd "onbepaald" - er is geen
   bevestigde regel. De volgorde blijft die van TVL en een melding zegt dat.
   Is de onderlinge ontmoeting nog niet gespeeld of was ze gelijk (2-2), dan
   blijft de TVL-volgorde ook staan, met een melding.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RANKING_SCORE_FORMAT_2026-10-10 + _TIEBREAK_CRITERIA_ (Kim zag
"de onderlinge confrontatie kon niet betrouwbaar toegepast worden")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd met poule_orientation_rapport.txt): het scoreveld van
het poule-schema heeft drie delen "matchen / sets / games", bv.
"1-3 / 3-7 / 40-56". _parse_score() verwachtte enkel "3-1", dus ALLE 12
scores waren onleesbaar en de richting kon nooit bepaald worden. Met enkel de
eerste component is de richting "thuis-uit" exact bevestigd (verschil met de
punten van TVL = 0; "uit-thuis" = 8).
_parse_score_full() leest nu alle drie de delen (het oude formaat blijft
werken). Daardoor zijn ook sets en games beschikbaar voor de gelijke-stand-
regels die Kim aanreikte, bij gelijke punten, in volgorde:
  1. gewonnen matchen over de hele poule, 2. setsaldo, 3. gamesaldo,
  4. enkel bij exact 2 ploegen die dan nog gelijk staan: de onderlinge
     ontmoeting. Drie of meer ploegen die op alles gelijk staan: onbeslist.
TIEBREAK_H2H_FIRST_FOR_TWO = True laat bij exact 2 ploegen de onderlinge
ontmoeting eerst tellen (Kim's eerdere regel). LET OP: de aangereikte regels
zijn niet gecontroleerd tegen het officiele reglement; op Poule Q geven beide
volgordes een ander resultaat voor Deinze D en Lobbeke B. De volgorde die TVL
zelf toont is geen bewijs: binnen elke gelijke stand staan de ploegen op
oplopend ploegnummer (8005, 8076 / 8073, 8159, 8218).
"""
from __future__ import annotations
import itertools
import re
import time
from typing import Optional
import requests
import streamlit as st
from bs4 import BeautifulSoup
BASE_URL = "https://www.tennisenpadelvlaanderen.be"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"
# PADEL_ANALYSIS_POULE_RANKING_SCENARIOS_2026-09-27: wiskundig geverifieerd
# op de echte Poule Q-data (zie moduledocstring) - geen aanname.
WIN_POINTS = 2
DRAW_POINTS = 1
LOSS_POINTS = 0
# Bevestigd door Kim (2026-09-27): "eerste 2 gaan door is altijd zo in
# poulefase" - geen instelbare/per-afdeling waarde, in tegenstelling tot
# tournament_rules.py's puntengrens-per-rotatie.
QUALIFYING_PLACES = 2
# PADEL_ANALYSIS_QUALIFICATION_SCENARIOS_HIDDEN_2026-09-27 (op verzoek van
# Kim: "kan je nog eventjes de kwalificatiescenario's verbergen in de UI.
# Code mag voorlopig blijven. Ik kom daar later op terug."):
# Enkel de UI-sectie wordt verborgen - de volledige logica hierboven
# (compute_qualification_scenarios(), _describe_points_shed_requirement(),
# _head_to_head_winner(), ...) blijft ONGEWIJZIGD staan, klaar om later
# gewoon terug aan te zetten door deze vlag terug op True te zetten.
SHOW_QUALIFICATION_SCENARIOS = False
def fetch_poule_ranking_html(
    url: str,
    session: Optional[requests.Session] = None,
    delay: float = 1.0,
) -> str:
    """Haalt de rangschikkingspagina op. Publiek toegankelijk, geen login
    nodig (bevestigd: isSignedIn(): false in de pagina zelf)."""
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    if delay > 0:
        time.sleep(delay)
    full_url = url if url.startswith("http") else BASE_URL + url
    response = session.get(full_url, timeout=20)
    response.raise_for_status()
    return response.text
def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
def _param_from_url(href: Optional[str], param: str) -> Optional[str]:
    from urllib.parse import parse_qs, urlparse
    if not href:
        return None
    values = parse_qs(urlparse(href).query).get(param)
    return values[0] if values else None
def parse_poule_ranking(html: str) -> dict:
    """Parse de rangschikkingstabel + poule-metadata.
    Geeft een dict terug:
        {
            "poule_label": "Poule Q",
            "season": "2026", "period": "Najaar Padel",
            "category": "PADEL OPEN 40", "afdeling": "5",
            "standings": [
                {"plaats": 1, "ploeg_id": "337680",
                 "ploeg_naam": "8005 KON. DEINZE T.C. D",
                 "ontmoetingen": 3, "punten": 4, "opmerking": ""},
                ...
            ],
        }
    Geeft lege standings terug (met de rest van de metadata indien
    beschikbaar) als de tabel niet gevonden wordt - roept NOOIT een
    exception op voor een onverwachte paginastructuur, zodat de UI dit
    netjes als "geen data" kan tonen i.p.v. te crashen."""
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "poule_label": None, "season": None, "period": None,
        "category": None, "afdeling": None, "standings": [],
    }
    title = soup.find("h1", class_="page-title")
    if title is not None:
        text = _clean(title.get_text())
        m = re.search(r"Poule\s+([A-Z]{1,3})\b", text, re.IGNORECASE)
        result["poule_label"] = f"Poule {m.group(1).upper()}" if m else text
    for li in soup.find_all("li"):
        label_el = li.find(class_="list-label")
        value_el = li.find(class_="list-value")
        if label_el is None or value_el is None:
            continue
        label = _clean(label_el.get_text()).rstrip(":").lower()
        value = _clean(value_el.get_text())
        if label == "seizoen":
            result["season"] = value
        elif label == "periode":
            result["period"] = value
        elif label == "categorie":
            result["category"] = value
        elif label == "afdeling":
            # "5 ( - )" -> "5"
            m = re.match(r"(\S+)", value)
            result["afdeling"] = m.group(1) if m else value
    table = soup.find("table", attrs={"role": "grid"})
    if table is None:
        return result
    tbody = table.find("tbody")
    if tbody is None:
        return result
    standings = []
    for row in tbody.find_all("tr"):
        cells = {
            td.get("data-title"): td
            for td in row.find_all("td")
            if td.get("data-title")
        }
        if "Plaats" not in cells or "Ploeg" not in cells:
            continue
        plaats_text = _clean(cells["Plaats"].get_text())
        ploeg_cell = cells["Ploeg"]
        link = ploeg_cell.find("a")
        ploeg_naam = _clean((link or ploeg_cell).get_text())
        ploeg_id = _param_from_url(link.get("href") if link else None, "ploegId")
        ontmoetingen_text = _clean(cells.get("Aantal ontmoetingen", ploeg_cell).get_text()) \
            if "Aantal ontmoetingen" in cells else ""
        punten_text = _clean(cells.get("Punten", ploeg_cell).get_text()) if "Punten" in cells else ""
        opmerking_text = _clean(cells.get("Opmerking", ploeg_cell).get_text()) if "Opmerking" in cells else ""
        try:
            plaats = int(plaats_text)
        except ValueError:
            continue
        try:
            ontmoetingen = int(ontmoetingen_text)
        except ValueError:
            ontmoetingen = None
        try:
            punten = int(punten_text)
        except ValueError:
            punten = None
        standings.append({
            "plaats": plaats,
            "ploeg_id": ploeg_id,
            "ploeg_naam": ploeg_naam,
            "ontmoetingen": ontmoetingen,
            "punten": punten,
            "opmerking": opmerking_text or None,
        })
    result["standings"] = standings
    return result
def _encounter_result(score_text: Optional[str]) -> Optional[str]:
    """Leidt "win"/"draw"/"loss" (voor de THUISPLOEG) af uit de bordscore
    van 1 ontmoeting (bv. "4-0", "3-1", "2-2", "1-3", "0-4").
    Geeft None terug als de score niet leesbaar is (dan wordt deze
    ontmoeting overgeslagen i.p.v. een verzonnen resultaat te gebruiken).
    LET OP (PADEL_ANALYSIS_H2H_SCORE_FIELD_UNVERIFIED_2026-09-27): dit
    interpreteert het "score"-veld van schedule_scraper.parse_poule_
    schedule() als "aantal gewonnen borden thuis - aantal gewonnen borden
    uit". Dat veld is NOOIT apart geverifieerd tegen echte uitslagen (zie
    moduledocstring) - gebruik diagnose_h2h_score.py om dit te bevestigen
    voor een specifieke, betwiste ontmoeting voor je hierop een fix baseert.
    PADEL_ANALYSIS_RANKING_TIEBREAK_2026-10-10: de rangschikking zelf
    gebruikt hiervoor nu _parse_score() + detect_score_orientation()."""
    parsed = _parse_score(score_text)  # PADEL_ANALYSIS_RANKING_SCORE_FORMAT_2026-10-10
    if parsed is None:
        return None
    home, away = parsed
    if home > away:
        return "win"
    if home < away:
        return "loss"
    return "draw"
def _remaining_fixtures_by_team(fixtures: list) -> dict:
    """Groepeert de NOG NIET gespeelde fixtures per ploeg_id."""
    out: dict = {}
    for fx in fixtures or []:
        if fx.get("played"):
            continue
        for side in ("home_ploeg_id", "away_ploeg_id"):
            pid = fx.get(side)
            if pid:
                out.setdefault(str(pid), []).append(fx)
    return out
def _head_to_head_winner(fixtures: list, ploeg_id_a: str, ploeg_id_b: str) -> Optional[str]:
    """Geeft de ploeg_id terug die de ALREADY GESPEELDE onderlinge
    ontmoeting tussen deze 2 ploegen won, of None als ze nog niet
    (leesbaar) tegen elkaar gespeeld hebben."""
    for fx in fixtures or []:
        if not fx.get("played"):
            continue
        home, away = str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id"))
        if {home, away} != {str(ploeg_id_a), str(ploeg_id_b)}:
            continue
        outcome = _encounter_result(fx.get("score"))
        if outcome == "win":
            return home
        if outcome == "loss":
            return away
        return None  # gelijkspel -> geen "winnaar" van de onderlinge confrontatie
    return None
# ---------------------------------------------------------------------------
# PADEL_ANALYSIS_RANKING_TIEBREAK_2026-10-10 - zie moduledocstring.
# ---------------------------------------------------------------------------
_ORIENT_HOME_FIRST = "thuis-uit"
_ORIENT_AWAY_FIRST = "uit-thuis"
_SEG_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
def _parse_score_full(score_text) -> Optional[dict]:
    """Leest het scoreveld van het poule-schema. TVL levert "matchen / sets /
    games", bv. "1-3 / 3-7 / 40-56" (thuis-uit, tenzij de richting omgekeerd
    blijkt). Geeft {"matches": (a, b), "sets": (a, b) | None, "games": (a, b) |
    None} terug, of None als zelfs de matchen onleesbaar zijn (nooit een gok).
    Ook het oudere formaat "3-1" / "3/1" (enkel matchen) blijft werken.
    PADEL_ANALYSIS_RANKING_SCORE_FORMAT_2026-10-10."""
    if not score_text:
        return None
    text = str(score_text).strip()
    segs = [x for x in text.split("/")]
    if len(segs) >= 2 and all(_SEG_RE.match(x) for x in segs):
        vals = [tuple(int(g) for g in _SEG_RE.match(x).groups()) for x in segs]
        return {"matches": vals[0], "sets": vals[1] if len(vals) > 1 else None,
                "games": vals[2] if len(vals) > 2 else None}
    m = re.match(r"^\s*(\d+)\s*[-/]\s*(\d+)\s*$", text)
    if m:
        return {"matches": (int(m.group(1)), int(m.group(2))), "sets": None, "games": None}
    return None
def _parse_score(score_text) -> Optional[tuple]:
    """Enkel de MATCHEN-component: "3-1" / "1-3 / 3-7 / 40-56" -> (3, 1) / (1, 3)."""
    full = _parse_score_full(score_text)
    return full["matches"] if full else None
def _boards_home_away(fx: dict, orientation: str) -> Optional[tuple]:
    """(borden thuisploeg, borden uitploeg) volgens de gegeven richting."""
    parsed = _parse_score(fx.get("score"))
    if parsed is None:
        return None
    a, b = parsed
    return (a, b) if orientation == _ORIENT_HOME_FIRST else (b, a)
def orientation_diagnosis(standings: list, fixtures: list) -> dict:
    """Rekent de stand opnieuw uit de GESPEELDE fixtures, in beide richtingen,
    en vergelijkt met de Punten die TVL toont. Geeft per richting de berekende
    punten, het verschil per ploeg en het totale verschil terug - de basis voor
    detect_score_orientation() en voor test_poule_orientation.py.
    PADEL_ANALYSIS_RANKING_ORIENTATION_TOLERANT_2026-10-10."""
    target = {}
    namen = {}
    for s in standings or []:
        if s.get("ploeg_id") is None or s.get("punten") is None:
            continue
        target[str(s["ploeg_id"])] = int(s["punten"])
        namen[str(s["ploeg_id"])] = s.get("ploeg_naam")
    played = [
        fx for fx in fixtures or []
        if fx.get("played")
        and str(fx.get("home_ploeg_id")) in target and str(fx.get("away_ploeg_id")) in target
    ]
    onleesbaar = [fx for fx in played if _parse_score(fx.get("score")) is None]
    out = {"target": target, "namen": namen, "n_played": len(played),
           "onleesbaar": onleesbaar, "per_orient": {}}
    for orient in (_ORIENT_HOME_FIRST, _ORIENT_AWAY_FIRST):
        pts = {pid: 0 for pid in target}
        for fx in played:
            bh = _boards_home_away(fx, orient)
            if bh is None:
                continue
            h, a = str(fx["home_ploeg_id"]), str(fx["away_ploeg_id"])
            if bh[0] > bh[1]:
                pts[h] += WIN_POINTS
            elif bh[0] < bh[1]:
                pts[a] += WIN_POINTS
            else:
                pts[h] += DRAW_POINTS
                pts[a] += DRAW_POINTS
        diff = {pid: pts[pid] - target[pid] for pid in target}
        out["per_orient"][orient] = {
            "pts": pts, "diff": diff, "totaal_diff": sum(abs(v) for v in diff.values()),
        }
    return out
# Maximaal totaal punten-verschil (over alle ploegen samen) waarbij een richting
# nog als "bevestigd" geldt: 4 = ruimte voor 1 ontmoeting (2 punten per ploeg)
# die TVL al verwerkte en ons opgeslagen schema nog niet.
_MAX_ORIENT_DIFF = 4
def detect_score_orientation(standings: list, fixtures: list) -> Optional[str]:
    """Bepaalt in welke richting het "score"-veld van de fixtures gelezen moet
    worden. Geeft "thuis-uit" of "uit-thuis" terug als die richting de punten van
    TVL (vrijwel) volledig verklaart en duidelijk beter is dan de andere; anders
    None - dan wordt de onderlinge confrontatie niet gebruikt.
    PADEL_ANALYSIS_RANKING_ORIENTATION_TOLERANT_2026-10-10: voorheen moesten ALLE
    ploegen exact overeenkomen. Dat faalde zodra het opgeslagen schema even
    achterliep op de live rangschikking (een net gespeelde ontmoeting die TVL
    al telt, het schema nog niet). Nu telt de richting met het kleinste totale
    verschil, op voorwaarde dat dat verschil hoogstens _MAX_ORIENT_DIFF is en
    strikt kleiner dan dat van de andere richting."""
    diag = orientation_diagnosis(standings, fixtures)
    if not diag["target"] or not diag["n_played"]:
        return None
    d_thuis = diag["per_orient"][_ORIENT_HOME_FIRST]["totaal_diff"]
    d_uit = diag["per_orient"][_ORIENT_AWAY_FIRST]["totaal_diff"]
    if d_thuis == d_uit:
        return None
    beste, d_beste = (_ORIENT_HOME_FIRST, d_thuis) if d_thuis < d_uit else (_ORIENT_AWAY_FIRST, d_uit)
    return beste if d_beste <= _MAX_ORIENT_DIFF else None
def _h2h_boards(fixtures: list, a: str, b: str, orientation: str) -> Optional[tuple]:
    """(borden a, borden b) van de gespeelde onderlinge ontmoeting, of None."""
    for fx in fixtures or []:
        if not fx.get("played"):
            continue
        h, w = str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id"))
        if {h, w} != {str(a), str(b)}:
            continue
        bh = _boards_home_away(fx, orientation)
        if bh is None:
            return None
        return (bh[0], bh[1]) if h == str(a) else (bh[1], bh[0])
    return None
# PADEL_ANALYSIS_RANKING_TIEBREAK_CRITERIA_2026-10-10 (regels aangereikt door Kim):
# bij een gelijke stand op punten, in deze volgorde:
#   1. aantal gewonnen matchen (over alle ontmoetingen in de poule)
#   2. setsaldo (sets voor min sets tegen)
#   3. gamesaldo (games voor min games tegen)
#   4. enkel als daarna EXACT 2 ploegen overblijven die nog steeds op alles gelijk
#      staan: de onderlinge ontmoeting. 3 of meer: onbeslist.
# Zet op True om bij EXACT 2 ploegen gelijk de onderlinge ontmoeting EERST te
# laten tellen (Kim's eerste regel) - de criteria 1-3 gelden dan als terugval.
TIEBREAK_H2H_FIRST_FOR_TWO = False
_CRITERIA = (
    ("matches_won", "gewonnen matchen", False),
    ("sets_saldo", "setsaldo", True),
    ("games_saldo", "gamesaldo", True),
)
def _team_stats(standings: list, fixtures: list, orientation: str) -> dict:
    """Per ploeg: gewonnen matchen, setsaldo, gamesaldo uit de GESPEELDE
    fixtures. Een criterium is None zodra het voor een ploeg niet uit alle
    uitslagen af te leiden is (dan wordt het voor iedereen overgeslagen)."""
    ids = {str(s["ploeg_id"]) for s in standings if s.get("ploeg_id") is not None}
    stats = {pid: {"matches_won": 0, "sets_saldo": 0, "games_saldo": 0, "_sets_ok": True, "_games_ok": True}
             for pid in ids}
    for fx in fixtures or []:
        if not fx.get("played"):
            continue
        h, a = str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id"))
        if h not in ids or a not in ids:
            continue
        full = _parse_score_full(fx.get("score"))
        if full is None:
            continue
        flip = orientation == _ORIENT_AWAY_FIRST
        def _hm(pair):
            return (pair[1], pair[0]) if flip else pair
        mh, ma = _hm(full["matches"])
        stats[h]["matches_won"] += mh
        stats[a]["matches_won"] += ma
        for key, ok_key, comp in (("sets_saldo", "_sets_ok", "sets"), ("games_saldo", "_games_ok", "games")):
            if full[comp] is None:
                stats[h][ok_key] = stats[a][ok_key] = False
                continue
            vh, va = _hm(full[comp])
            stats[h][key] += vh - va
            stats[a][key] += va - vh
    for st_ in stats.values():
        if not st_.pop("_sets_ok"):
            st_["sets_saldo"] = None
        if not st_.pop("_games_ok"):
            st_["games_saldo"] = None
    return stats
def _fmt_signed(v) -> str:
    return f"{v:+d}"
def _explain(winner: dict, loser: dict, sw: dict, sl: dict, criteria: list) -> str:
    """Zegt welk criterium de doorslag gaf tussen twee ploegen."""
    gelijk = []
    for key, label, signed in criteria:
        vw, vl = sw.get(key), sl.get(key)
        if vw is None or vl is None:
            continue
        if vw != vl:
            tekst = f"{_fmt_signed(vw)} tegenover {_fmt_signed(vl)}" if signed else f"{vw} tegenover {vl}"
            voorloop = f"gelijk op {' en '.join(gelijk)}, " if gelijk else ""
            return f"{winner.get('ploeg_naam')} staat boven {loser.get('ploeg_naam')}: {voorloop}beslist door {label} ({tekst})."
        gelijk.append(label)
    return ""
def order_standings_with_tiebreak(standings: list, fixtures: list) -> dict:
    """Sorteert de stand op punten en lost een gelijke stand op met de criteria
    bovenaan (zie TIEBREAK_H2H_FIRST_FOR_TWO / _CRITERIA). Geeft terug:
        {"rows": [standings-dicts + "rank"], "notes": [str],
         "orientation": str | None, "unresolved_boundary": bool}
    `unresolved_boundary` = True als een onbeslist gelijke stand over de grens van
    de doorgaande plaatsen (QUALIFYING_PLACES) heen loopt."""
    rows = [dict(s) for s in standings or []]
    rows.sort(key=lambda s: (-(s.get("punten") if s.get("punten") is not None else -1), s.get("plaats", 0)))
    notes: list = []
    orientation = detect_score_orientation(standings, fixtures)
    stats = _team_stats(standings, fixtures, orientation) if orientation else {}
    uitkomst: list = []
    unresolved_boundary = False
    i = 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1].get("punten") == rows[i].get("punten") and rows[i].get("punten") is not None:
            j += 1
        groep = rows[i:j + 1]
        eerste_rank, laatste_rank = i + 1, j + 1
        onbeslist_groepen: list = []
        if len(groep) >= 2:
            namen = ", ".join(g.get("ploeg_naam") or "?" for g in groep)
            if orientation is None:
                notes.append(
                    f"Gelijke stand tussen {namen}: de uitslagen in het opgeslagen schema komen niet overeen "
                    "met de punten van TVL (schema niet up-to-date?) - volgorde zoals TVL ze toont."
                )
                onbeslist_groepen.append(list(groep))
            else:
                groep, beslist_notes, onbeslist_groepen = _resolve_tie_group(groep, stats, fixtures, orientation)
                notes.extend(beslist_notes)
        for og in onbeslist_groepen:
            ids_og = {id(x) for x in og}
            posities = [idx for idx, g_ in enumerate(groep) if id(g_) in ids_og]
            if posities:
                blok_eerste = eerste_rank + min(posities)
                blok_laatste = eerste_rank + max(posities)
                if blok_eerste <= QUALIFYING_PLACES < blok_laatste:
                    unresolved_boundary = True
        uitkomst.extend(groep)
        i = j + 1
    for rank, s in enumerate(uitkomst, start=1):
        s["rank"] = rank
    return {"rows": uitkomst, "notes": notes, "orientation": orientation,
            "unresolved_boundary": unresolved_boundary}
def _h2h_two(a: dict, b: dict, fixtures: list, orientation: str):
    """Onderlinge ontmoeting tussen exact 2 ploegen: (winnaar, verliezer, tekst) of None."""
    bw = _h2h_boards(fixtures, a.get("ploeg_id"), b.get("ploeg_id"), orientation)
    if bw is None or bw[0] == bw[1]:
        return None, bw
    w, l = (a, b) if bw[0] > bw[1] else (b, a)
    return (w, l, f"{max(bw)}-{min(bw)}"), bw
def _resolve_tie_group(groep: list, stats: dict, fixtures: list, orientation: str):
    """Geeft (geordende groep, notes, lijst onbeslist gebleven deelgroepen)."""
    notes: list = []
    onbeslist: list = []
    criteria = [
        c for c in _CRITERIA
        if all(stats.get(str(g.get("ploeg_id")), {}).get(c[0]) is not None for g in groep)
    ]
    if len(criteria) < len(_CRITERIA):
        ontbrekend = ", ".join(c[1] for c in _CRITERIA if c not in criteria)
        notes.append(f"Voor deze gelijke stand ontbreekt {ontbrekend} in het schema - dat criterium is overgeslagen.")
    if TIEBREAK_H2H_FIRST_FOR_TWO and len(groep) == 2:
        uit, bw = _h2h_two(groep[0], groep[1], fixtures, orientation)
        if uit:
            w, l, tekst = uit
            notes.append(f"{w.get('ploeg_naam')} staat boven {l.get('ploeg_naam')}: beslist door de onderlinge confrontatie ({tekst} gewonnen).")
            return [w, l], notes, onbeslist
    def sleutel(g):
        st_ = stats.get(str(g.get("ploeg_id")), {})
        return tuple(-(st_.get(c[0]) or 0) for c in criteria)
    gesorteerd = sorted(groep, key=sleutel)
    # Splits in blokken die op ALLE criteria gelijk staan
    blokken: list = []
    for g in gesorteerd:
        if blokken and sleutel(blokken[-1][0]) == sleutel(g):
            blokken[-1].append(g)
        else:
            blokken.append([g])
    resultaat: list = []
    for blok in blokken:
        if len(blok) == 2:
            uit, bw = _h2h_two(blok[0], blok[1], fixtures, orientation)
            if uit:
                w, l, tekst = uit
                notes.append(
                    f"{w.get('ploeg_naam')} staat boven {l.get('ploeg_naam')}: gelijk op "
                    f"{', '.join(c[1] for c in criteria)}, beslist door de onderlinge confrontatie ({tekst} gewonnen)."
                )
                resultaat.extend([w, l])
                continue
            reden = "de onderlinge ontmoeting is nog niet gespeeld" if bw is None else \
                f"de onderlinge ontmoeting eindigde gelijk ({bw[0]}-{bw[1]})"
            notes.append(
                f"Gelijke stand tussen {blok[0].get('ploeg_naam')} en {blok[1].get('ploeg_naam')} op alle criteria, en "
                f"{reden} - volgorde zoals TVL ze toont."
            )
            onbeslist.append(blok)
        elif len(blok) >= 3:
            notes.append(
                f"Gelijke stand tussen {', '.join(b.get('ploeg_naam') or '?' for b in blok)} op alle criteria "
                "(gewonnen matchen, setsaldo en gamesaldo) - daarvoor is geen verdere regel bevestigd, "
                "volgorde zoals TVL ze toont."
            )
            onbeslist.append(blok)
        resultaat.extend(blok)
    # Uitleg per beslissing tussen opeenvolgende ploegen die NIET gelijk stonden
    for k in range(len(resultaat) - 1):
        a_, b_ = resultaat[k], resultaat[k + 1]
        sa, sb = stats.get(str(a_.get("ploeg_id")), {}), stats.get(str(b_.get("ploeg_id")), {})
        if sleutel(a_) != sleutel(b_):
            tekst = _explain(a_, b_, sa, sb, criteria)
            if tekst:
                notes.append(tekst)
    return resultaat, notes, onbeslist
def _describe_points_shed_requirement(n_free_remaining: int, points_to_shed: int) -> str:
    """PADEL_ANALYSIS_THREAT_EXPLANATION_GENERALIZE_2026-09-27: vertaalt
    "moet X punten minder halen dan hun maximum" naar een EXACTE, voor élk
    aantal resterende wedstrijden correcte puntengrens - i.p.v. de vorige
    tekst ("bv. minstens 1 resterende wedstrijd niet winnen") die enkel
    bij PRECIES 1 resterende wedstrijd klopte en bij 2+ misleidend/
    onvolledig was. Zie moduledocstring voor de volledige toelichting."""
    if n_free_remaining <= 0:
        return (
            "hun puntentotaal ligt al vast (geen resterende wedstrijden meer in onze data) - "
            "controleer handmatig of dit overeenkomt met de werkelijke kalender."
        )
    max_possible = n_free_remaining * WIN_POINTS
    allowed_max = max(0, max_possible - points_to_shed)
    wedstrijden_woord = "wedstrijd" if n_free_remaining == 1 else "wedstrijden"
    return (
        f"mogen over hun resterende {n_free_remaining} {wedstrijden_woord} in totaal HOOGSTENS "
        f"{allowed_max} punt(en) halen (rekenkundig maximum: {max_possible}) om ons niet voorbij "
        f"te steken. Zodra ze samen {allowed_max + 1} punt(en) of meer halen, gaan zij ons voorbij "
        "- dat kan via elke combinatie van winst (2 punten), gelijkspel (1 punt) en verlies "
        "(0 punten) die samen op dat totaal uitkomt."
    )
def compute_qualification_scenarios(
    standings: list, fixtures: list, own_ploeg_id: str,
) -> dict:
    """Berekent, voor elke mogelijke combinatie van resultaten in de
    RESTERENDE wedstrijden van de EIGEN ploeg, of kwalificatie (top
    QUALIFYING_PLACES) GEGARANDEERD, ONMOGELIJK, of AFHANKELIJK van andere
    resultaten is.
    Zie moduledocstring voor de volledige, wiskundig geverifieerde
    onderbouwing van het puntensysteem en de kwalificatieregel.
    Geeft een dict terug:
        {
            "own_ploeg_id": ..., "own_ploeg_naam": ...,
            "n_remaining": int,
            "scenarios": [
                {
                    "own_results": ["win", "win"],  # per resterende match
                    "own_final_points": int,
                    "status": "gegarandeerd" | "onmogelijk" | "afhankelijk",
                    "threats": [
                        {"ploeg_id":..., "ploeg_naam":...,
                         "hun_max_punten": int,
                         "wat_nodig": "<uitleg>"},
                        ...
                    ],
                    "multi_way_tie_warning": bool,
                },
                ...
            ],
        }
    Geeft None terug (met een duidelijke reden) als own_ploeg_id niet in
    de standings voorkomt."""
    points_now = {str(s["ploeg_id"]): (s.get("punten") or 0) for s in standings if s.get("ploeg_id")}
    names = {str(s["ploeg_id"]): s.get("ploeg_naam") for s in standings if s.get("ploeg_id")}
    own_id = str(own_ploeg_id)
    if own_id not in points_now:
        return None
    remaining_by_team = _remaining_fixtures_by_team(fixtures)
    own_remaining = remaining_by_team.get(own_id, [])
    n_own_remaining = len(own_remaining)
    def _opponent_of(fx, pid):
        return str(fx["away_ploeg_id"]) if str(fx["home_ploeg_id"]) == pid else str(fx["home_ploeg_id"])
    own_remaining_opponents = [_opponent_of(fx, own_id) for fx in own_remaining]
    scenarios = []
    for own_results in itertools.product(["win", "draw", "loss"], repeat=n_own_remaining):
        own_added = sum(
            WIN_POINTS if r == "win" else DRAW_POINTS if r == "draw" else LOSS_POINTS
            for r in own_results
        )
        own_final = points_now[own_id] + own_added
        threats = []
        multi_way_tie_ids = set()
        for competitor_id, competitor_points in points_now.items():
            if competitor_id == own_id:
                continue
            competitor_remaining = remaining_by_team.get(competitor_id, [])
            # Is een van hun resterende wedstrijden TEGEN ONS? Dan ligt dat
            # resultaat al vast via own_results, niet vrij te winnen.
            fixed_bonus = 0
            n_free_remaining = 0
            for fx in competitor_remaining:
                opp = _opponent_of(fx, competitor_id)
                if opp == own_id:
                    idx = own_remaining_opponents.index(competitor_id)
                    own_r = own_results[idx]
                    # Vanuit COMPETITOR's perspectief is dit net omgekeerd.
                    fixed_bonus += (
                        LOSS_POINTS if own_r == "win" else
                        DRAW_POINTS if own_r == "draw" else
                        WIN_POINTS
                    )
                else:
                    n_free_remaining += 1
            competitor_ceiling = competitor_points + fixed_bonus + WIN_POINTS * n_free_remaining
            if competitor_ceiling > own_final:
                # PADEL_ANALYSIS_THREAT_EXPLANATION_GENERALIZE_2026-09-27:
                # exacte, voor elk aantal resterende wedstrijden correcte
                # puntengrens i.p.v. het vorige, enkel-bij-1-wedstrijd-
                # kloppende "bv." voorbeeld.
                threats.append({
                    "ploeg_id": competitor_id, "ploeg_naam": names.get(competitor_id, competitor_id),
                    "hun_max_punten": competitor_ceiling,
                    "wat_nodig": _describe_points_shed_requirement(
                        n_free_remaining, competitor_ceiling - own_final,
                    ),
                })
            elif competitor_ceiling == own_final:
                # Gelijke stand mogelijk - tie-break via onderlinge confrontatie.
                h2h_played = any(
                    {str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id"))} == {own_id, competitor_id}
                    and fx.get("played")
                    for fx in fixtures or []
                )
                if competitor_id in own_remaining_opponents:
                    # Onderlinge match zit in own_remaining -> het resultaat
                    # (vanuit ONS perspectief) ligt al vast via own_results.
                    # Enkel bij een GELIJKSPEL op die ene match is de
                    # tie-break-regel "wint de onderlinge confrontatie"
                    # zelf onbeslist; bij een eigen win/verlies daar is de
                    # winnaar van de onderlinge confrontatie net WEL
                    # eenduidig bekend.
                    idx = own_remaining_opponents.index(competitor_id)
                    own_r_hier = own_results[idx]
                    if own_r_hier == "draw":
                        threats.append({
                            "ploeg_id": competitor_id, "ploeg_naam": names.get(competitor_id, competitor_id),
                            "hun_max_punten": competitor_ceiling,
                            "wat_nodig": (
                                "gelijke eindstand na een GELIJKSPEL in de onderlinge confrontatie - "
                                "geen eenduidige tie-break-winnaar volgens de 'onderlinge confrontatie'-regel; "
                                "controleer het reglement voor de verdere tie-break (bv. sets/games)."
                            ),
                        })
                    elif own_r_hier == "loss":
                        # Wij verloren de onderlinge confrontatie -> zij
                        # winnen de tie-break -> blijft een threat.
                        threats.append({
                            "ploeg_id": competitor_id, "ploeg_naam": names.get(competitor_id, competitor_id),
                            "hun_max_punten": competitor_ceiling,
                            "wat_nodig": (
                                "gelijke eindstand, en zij wonnen de onderlinge confrontatie in dit scenario - "
                                "zij gaan dan door via de tie-break, tenzij dit scenario wijzigt."
                            ),
                        })
                    # own_r_hier == "win": wij wonnen de onderlinge
                    # confrontatie, dus WIJ winnen de tie-break - geen
                    # threat, niets toevoegen.
                elif h2h_played:
                    winner = _head_to_head_winner(fixtures, own_id, competitor_id)
                    if winner != own_id:
                        threats.append({
                            "ploeg_id": competitor_id, "ploeg_naam": names.get(competitor_id, competitor_id),
                            "hun_max_punten": competitor_ceiling,
                            "wat_nodig": (
                                "bij een gelijke eindstand wonnen ZIJ de onderlinge confrontatie - "
                                "moeten dus alsnog minder dan hun maximum halen om ons voor te blijven."
                            ),
                        })
                    # Zo niet (own_id wint h2h): geen threat, wij winnen de tie-break.
                else:
                    threats.append({
                        "ploeg_id": competitor_id, "ploeg_naam": names.get(competitor_id, competitor_id),
                        "hun_max_punten": competitor_ceiling,
                        "wat_nodig": (
                            "bij een gelijke eindstand is de onderlinge confrontatie nog niet gespeeld en "
                            "zit niet in onze resterende wedstrijden - tie-break nog onbepaald."
                        ),
                    })
        if len(threats) == 0 or len(threats) == 1:
            status = "gegarandeerd"
        elif n_own_remaining == 0 and own_final <= min(
            (points_now[c] for c in points_now if c != own_id), default=0,
        ) - 1:
            status = "onmogelijk"
        else:
            status = "afhankelijk"
        # Expliciete "onmogelijk"-detectie: zelfs met own_final vast (geen
        # resterende matchen meer), zijn er al >= QUALIFYING_PLACES
        # concurrenten met een HUIDIG (niet-hypothetisch) puntenaantal dat
        # own_final overtreft - dan is het gegarandeerd voorbij, ongeacht
        # wat de concurrenten nog doen.
        if n_own_remaining == 0:
            already_ahead = sum(
                1 for c, p in points_now.items() if c != own_id and p > own_final
            )
            if already_ahead >= QUALIFYING_PLACES:
                status = "onmogelijk"
        scenarios.append({
            "own_results": list(own_results),
            "own_final_points": own_final,
            "status": status,
            "threats": threats,
        })
    return {
        "own_ploeg_id": own_id,
        "own_ploeg_naam": names.get(own_id, own_id),
        "n_remaining": n_own_remaining,
        "scenarios": scenarios,
    }
def _build_ranking_url_from_reeks_url(reeks_url: str) -> Optional[str]:
    """Zelfde opbouw als _build_rangschikking_url() (page_lineup_lab.py) -
    hier lokaal herhaald zodat deze module ook zelfstandig (zonder die
    functie te moeten importeren) een geldige rangschikkings-URL kan
    opbouwen uit de al gekende poule/tabel-URL. Publiek toegankelijk
    (bevestigd: isSignedIn(): false), dus geen sessie/login nodig."""
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
        base = f"{BASE_URL}/nl/clubdashboard/interclub-rangschikking"
        return f"{base}?{urlencode({'spelgroepId': spelgroep_id, 'pouleId': poule_id})}"
    except Exception:
        return None
# ---------------------------------------------------------------------------
# UI: te integreren in page_lineup_lab.py, tab "Rangschikking"
# ---------------------------------------------------------------------------
_RESULT_LABEL = {"win": "Winst", "draw": "Gelijkspel", "loss": "Verlies"}
@st.cache_data(ttl=1800, show_spinner="Rangschikking ophalen...")
def _load_poule_ranking_cached(url: str) -> dict:
    """PADEL_ANALYSIS_RANKING_CACHE_2026-09-29: gedeelde cache van 30 min.
    Overleeft F5 en nieuwe sessies binnen hetzelfde Streamlit-proces.
    De interactieve fetch gebruikt geen kunstmatige vertraging; bij de oude
    code kostte delay=1.0 op elke nieuwe sessie exact 1 seconde wachttijd."""
    html = fetch_poule_ranking_html(url, delay=0.0)
    return parse_poule_ranking(html)
def render_poule_ranking_tab(reeks_url: str, fixtures: list, own_ploeg_id: str) -> None:
    """Toont de volledige rangschikkingstabel + kwalificatiescenario's voor
    de eigen ploeg. Bedoeld om aangeroepen te worden in het tabblad
    "Rangschikking" van page_lineup_lab.py.
    `fixtures`: dezelfde poule-fixtures-lijst die al in
    st.session_state[f"vm_fixtures_{sel_player_id}"] staat (het resultaat
    van schedule_scraper.parse_poule_schedule()) - geen nieuwe scrape
    nodig, enkel hergebruik.
    PADEL_ANALYSIS_RANKING_TIEBREAK_2026-10-10: kolommen Plaats - Ploeg -
    Punten - Ontmoetingen (Opmerking enkel als er iets in staat) en een
    gelijke stand wordt beslist door de onderlinge confrontatie."""
    url = _build_ranking_url_from_reeks_url(reeks_url)
    if not url:
        st.info(
            "Kon de rangschikkingslink nog niet automatisch afleiden - het poule/tabel-schema "
            "moet eerst geladen zijn (zie 'Volgende match' hierboven)."
        )
        return
    try:
        data = _load_poule_ranking_cached(url)
    except Exception as e:  # noqa: BLE001
        st.warning(f"Kon de rangschikking niet ophalen: {e}")
        if st.button("Opnieuw proberen", key=f"retry_ranking_{url}"):
            _load_poule_ranking_cached.clear()
            st.rerun()
        return
    standings = data.get("standings") or []
    if not standings:
        st.info("Nog geen rangschikkingsdata gevonden voor deze poule.")
        return
    meta_parts = [p for p in [data.get("season"), data.get("period"), data.get("category")] if p]
    if data.get("afdeling"):
        meta_parts.append(f"afdeling {data['afdeling']}")
    if meta_parts:
        st.caption(" \u00b7 ".join(meta_parts))
    try:
        ordered = order_standings_with_tiebreak(standings, fixtures)
    except Exception:  # noqa: BLE001 - de stand tonen mag nooit door de tie-break breken
        ordered = {"rows": [dict(s, rank=s["plaats"]) for s in standings], "notes": [],
                   "orientation": None, "unresolved_boundary": False}
    toon_opmerking = any((s.get("opmerking") or "").strip() for s in standings)
    rows = []
    for s in ordered["rows"]:
        is_own = str(s.get("ploeg_id")) == str(own_ploeg_id)
        rij = {
            "Plaats": s["rank"],
            "Ploeg": ("\u2192 " if is_own else "") + (s.get("ploeg_naam") or "?"),
            "Punten": s.get("punten"),
            "Ontmoetingen": s.get("ontmoetingen"),
        }
        if toon_opmerking:
            rij["Opmerking"] = s.get("opmerking") or ""
        rij["_is_own"] = is_own
        rij["_gaat_door"] = s["rank"] <= QUALIFYING_PLACES
        rows.append(rij)
    try:
        import pandas as _pd
        def _kleur(row):
            if row.get("_is_own"):
                return ["background-color: #cfe2ff; font-weight: 600"] * len(row)
            if row.get("_gaat_door"):
                return ["background-color: #d4edda"] * len(row)
            return [""] * len(row)
        zichtbaar = [k for k in rows[0].keys() if not k.startswith("_")]
        df = _pd.DataFrame(rows)
        styled = df.style.apply(_kleur, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True, column_order=zichtbaar)
    except Exception:  # noqa: BLE001
        st.dataframe(
            [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
            use_container_width=True, hide_index=True,
        )
    st.caption(
        f"Groen = plaats 1 t.e.m. {QUALIFYING_PLACES} (gaat door volgens de reglementaire regel "
        "'eerste 2 gaan door in de poulefase'). Blauw = onze eigen ploeg. Bij een gelijke stand staat "
        "de ploeg met de meeste gewonnen matchen hoger, daarna het setsaldo, dan het gamesaldo, en pas daarna de onderlinge confrontatie."
    )
    for note in ordered["notes"]:
        st.caption(f"\u2139\ufe0f {note}")
    if ordered["unresolved_boundary"]:
        st.warning(
            "Let op: de gelijke stand rond plaats 2/3 is nog niet beslist - wie doorgaat hangt nog af van "
            "de onderlinge confrontatie of een regel die we niet kunnen toepassen."
        )
    # PADEL_ANALYSIS_QUALIFICATION_SCENARIOS_HIDDEN_2026-09-27: sectie
    # tijdelijk verborgen op verzoek van Kim - zie de vlag hierboven bij
    # QUALIFYING_PLACES. De rangschikkingstabel hierboven blijft gewoon
    # zichtbaar; enkel het "Kwalificatiescenario's"-blok eronder wordt nu
    # overgeslagen.
    if not SHOW_QUALIFICATION_SCENARIOS:
        return
    st.divider()
    st.markdown("#### Kwalificatiescenario's")
    scenario_data = compute_qualification_scenarios(standings, fixtures, own_ploeg_id)
    if scenario_data is None:
        st.info("Onze eigen ploeg werd niet teruggevonden in deze rangschikking.")
        return
    n_remaining = scenario_data["n_remaining"]
    if n_remaining == 0:
        st.caption(
            "Onze ploeg heeft geen resterende wedstrijden meer in deze poule - de eindstand hierboven "
            "is (voor ons) definitief."
        )
    else:
        st.caption(
            f"Onze ploeg heeft nog **{n_remaining}** wedstrijd(en) te spelen in deze poule. Hieronder alle "
            f"{3 ** n_remaining} mogelijke combinaties van winst/gelijkspel/verlies, en of dat kwalificatie "
            f"(top {QUALIFYING_PLACES}) al dan niet garandeert."
        )
    volgorde = {"gegarandeerd": 0, "afhankelijk": 1, "onmogelijk": 2}
    scenarios_sorted = sorted(
        scenario_data["scenarios"],
        key=lambda s: (volgorde.get(s["status"], 3), -s["own_final_points"]),
    )
    status_kleur = {"gegarandeerd": "success", "afhankelijk": "warning", "onmogelijk": "error"}
    status_label = {
        "gegarandeerd": "Gegarandeerd door",
        "afhankelijk": "Afhankelijk van andere uitslagen",
        "onmogelijk": "Niet meer mogelijk",
    }
    for sc in scenarios_sorted:
        if n_remaining == 0:
            titel = f"Eindstand: {sc['own_final_points']} punten"
        else:
            resultaten_txt = " + ".join(_RESULT_LABEL[r] for r in sc["own_results"])
            titel = f"{resultaten_txt} \u2192 {sc['own_final_points']} punten"
        kleur_fn = getattr(st, status_kleur.get(sc["status"], "info"))
        with st.expander(f"{titel} - {status_label.get(sc['status'], sc['status'])}", expanded=False):
            kleur_fn(status_label.get(sc["status"], sc["status"]))
            if sc["threats"]:
                st.markdown("**Bepalende ploegen:**")
                for t in sc["threats"]:
                    st.write(f"- **{t['ploeg_naam']}** (max. haalbaar: {t['hun_max_punten']} punten) - {t['wat_nodig']}")
            elif sc["status"] == "gegarandeerd":
                st.caption("Geen enkele andere ploeg kan ons nog voorbijsteken in dit scenario.")
