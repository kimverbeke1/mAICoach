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
4. GELIJKE STAND, 3 OF MEER PLOEGEN: ongewijzigd "onbepaald" - er is geen
   bevestigde regel. De volgorde blijft die van TVL en een melding zegt dat.
   Is de onderlinge ontmoeting nog niet gespeeld of was ze gelijk (2-2), dan
   blijft de TVL-volgorde ook staan, met een melding.
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
    if not score_text:
        return None
    m = re.match(r"^\s*(\d+)\s*[-/]\s*(\d+)\s*$", str(score_text).strip())
    if not m:
        return None
    home, away = int(m.group(1)), int(m.group(2))
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
def _parse_score(score_text) -> Optional[tuple]:
    """"3-1" / "3/1" -> (3, 1); onleesbaar -> None (nooit een gok)."""
    if not score_text:
        return None
    m = re.match(r"^\s*(\d+)\s*[-/]\s*(\d+)\s*$", str(score_text).strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))
def _boards_home_away(fx: dict, orientation: str) -> Optional[tuple]:
    """(borden thuisploeg, borden uitploeg) volgens de gegeven richting."""
    parsed = _parse_score(fx.get("score"))
    if parsed is None:
        return None
    a, b = parsed
    return (a, b) if orientation == _ORIENT_HOME_FIRST else (b, a)
def detect_score_orientation(standings: list, fixtures: list) -> Optional[str]:
    """Bepaalt in welke richting het "score"-veld van de fixtures gelezen moet
    worden, door de stand opnieuw uit de GESPEELDE fixtures te berekenen (in
    beide richtingen) en te vergelijken met de Punten die TVL zelf toont.
    Geeft "thuis-uit" of "uit-thuis" terug als PRECIES 1 richting op ALLE
    ploegen overeenkomt, anders None (geen/onbetrouwbare data, of beide
    richtingen passen) - dan wordt de onderlinge confrontatie niet gebruikt."""
    target = {}
    for s in standings or []:
        if s.get("ploeg_id") is None or s.get("punten") is None:
            return None
        target[str(s["ploeg_id"])] = int(s["punten"])
    if not target:
        return None
    played = [
        fx for fx in fixtures or []
        if fx.get("played")
        and str(fx.get("home_ploeg_id")) in target and str(fx.get("away_ploeg_id")) in target
    ]
    if not played:
        return None
    passend = []
    for orient in (_ORIENT_HOME_FIRST, _ORIENT_AWAY_FIRST):
        pts = {pid: 0 for pid in target}
        for fx in played:
            bh = _boards_home_away(fx, orient)
            if bh is None:
                continue
            h, a = str(fx["home_ploeg_id"]), str(fx["away_ploeg_id"])
            if bh[0] > bh[1]:
                pts[h] += WIN_POINTS
                pts[a] += LOSS_POINTS
            elif bh[0] < bh[1]:
                pts[a] += WIN_POINTS
                pts[h] += LOSS_POINTS
            else:
                pts[h] += DRAW_POINTS
                pts[a] += DRAW_POINTS
        if pts == target:
            passend.append(orient)
    return passend[0] if len(passend) == 1 else None
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
def order_standings_with_tiebreak(standings: list, fixtures: list) -> dict:
    """Sorteert de stand op punten, en bij een gelijke stand tussen EXACT 2
    ploegen op de onderlinge confrontatie. Geeft terug:
        {"rows": [standings-dicts + "rank"], "notes": [str],
         "orientation": str | None, "unresolved_boundary": bool}
    `unresolved_boundary` = True als een onbeslist gelijke stand over de grens
    van de doorgaande plaatsen (QUALIFYING_PLACES) heen loopt."""
    rows = [dict(s) for s in standings or []]
    rows.sort(key=lambda s: (-(s.get("punten") if s.get("punten") is not None else -1), s.get("plaats", 0)))
    notes: list = []
    orientation = detect_score_orientation(standings, fixtures)
    uitkomst: list = []
    unresolved_boundary = False
    i = 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1].get("punten") == rows[i].get("punten") and rows[i].get("punten") is not None:
            j += 1
        groep = rows[i:j + 1]
        eerste_rank, laatste_rank = i + 1, j + 1
        if len(groep) == 2:
            a, b = groep
            naam_a, naam_b = a.get("ploeg_naam"), b.get("ploeg_naam")
            if orientation is None:
                notes.append(
                    f"Gelijke stand tussen {naam_a} en {naam_b}: de onderlinge confrontatie kon niet "
                    "betrouwbaar toegepast worden (de uitslagen in het schema komen niet overeen met de punten) "
                    "- volgorde zoals TVL ze toont."
                )
                beslist = False
            else:
                bw = _h2h_boards(fixtures, a.get("ploeg_id"), b.get("ploeg_id"), orientation)
                if bw is None:
                    notes.append(
                        f"Gelijke stand tussen {naam_a} en {naam_b}: de onderlinge ontmoeting is nog niet "
                        "gespeeld - volgorde voorlopig zoals TVL ze toont."
                    )
                    beslist = False
                elif bw[0] == bw[1]:
                    notes.append(
                        f"Gelijke stand tussen {naam_a} en {naam_b}: de onderlinge ontmoeting eindigde gelijk "
                        f"({bw[0]}-{bw[1]}) - geen beslissing mogelijk, volgorde zoals TVL ze toont."
                    )
                    beslist = False
                else:
                    winnaar, verliezer = (a, b) if bw[0] > bw[1] else (b, a)
                    groep = [winnaar, verliezer]
                    notes.append(
                        f"Gelijke stand tussen {naam_a} en {naam_b}: {winnaar.get('ploeg_naam')} staat hoger "
                        f"door de onderlinge confrontatie ({max(bw)}-{min(bw)} gewonnen)."
                    )
                    beslist = True
            if not beslist and eerste_rank <= QUALIFYING_PLACES < laatste_rank:
                unresolved_boundary = True
        elif len(groep) >= 3:
            namen = ", ".join(g.get("ploeg_naam") or "?" for g in groep)
            notes.append(
                f"Gelijke stand tussen {len(groep)} ploegen ({namen}): daarvoor is geen onderlinge regel "
                "bevestigd - volgorde zoals TVL ze toont, controleer handmatig."
            )
            if eerste_rank <= QUALIFYING_PLACES < laatste_rank:
                unresolved_boundary = True
        uitkomst.extend(groep)
        i = j + 1
    for rank, s in enumerate(uitkomst, start=1):
        s["rank"] = rank
    return {"rows": uitkomst, "notes": notes, "orientation": orientation,
            "unresolved_boundary": unresolved_boundary}
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
        "de ploeg die de onderlinge confrontatie won hoger."
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
