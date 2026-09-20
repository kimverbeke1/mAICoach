"""
opponent_dossier.py - scoutingdossier voor een tegenstander (v10).
PADEL_ANALYSIS_TWO_LAYER_2026-09-10
De strikte poulefilter uit v2 was correct maar leverde in de praktijk bijna
niets op: de huidige competitieperiode is pas gestart, dus tegenstanders
hebben er 1 a 2 matchen. Alle historiek zit in de vorige periode. v3 splitst
expliciet in TWEE lagen:
  1. HUIDIGE POULE  - strikt op spelgroep_id. Feitelijk, maar vaak dun.
  2. HISTORIEK      - alle overige interclubmatches, per periode gegroepeerd,
                      duidelijk gelabeld als context uit een andere poule.
PADEL_ANALYSIS_RANK_DIRECTION_FIX_2026-09-10 (v4):
In dit klassementsysteem geldt HOE HOGER HET GETAL, HOE BETER. "Beste ooit" =
het HOOGSTE getal, niet het laagste. De tijdlijngrafiek gebruikt een normale
(niet-omgekeerde) as.
PADEL_ANALYSIS_KLASSEMENT_LABEL_SHORTENING_2026-09-10 (v5):
De ruwe periode-omschrijving die TVL gebruikt (bv. "Startklassement" of
"Zomerklassement") wordt nu verkort tot "Start <jaar>" / "Zomer <jaar>" op de
grafiek-as en in de "beste klassement bereikt op"-tekst.
PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13 (v7, BELANGRIJKE WIJZIGING):
De eerder in v6 toegevoegde EIGEN Elo-berekening (elo_rating.compute_player_
elo) is VERWIJDERD uit dit bestand. Op uitdrukkelijk verzoek van Kim, na een
kalibratietest die aantoonde dat die eigen berekening structureel en
onoplosbaar afweek van de externe referentie padelstats.be (zie
elo_rating.py voor de volledige toelichting), wordt de 'playing strength'
nu UITSLUITEND gehaald uit de gecachete padelstats.be-waarde
(firebase_service.get_padelstat_rating), opgehaald via
padelstats_scraper.py / bulk_fetch_padelstat_ratings.py. Is die nog niet
opgehaald voor een speler, dan wordt dat EXPLICIET getoond ("nog niet
opgehaald") in plaats van een minder betrouwbaar eigen cijfer te tonen.
reeks_url is in de praktijk None in alle opgeslagen matchrecords; de filter
steunt daarom op spelgroep_id, met reeks_url enkel als optionele extra.
Bordpositie-heuristiek is verwijderd (was een telling van round_text en gaf
geen betrouwbare bordnummering).
--------------------------------------------------------------------------
PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18 (v8, op verzoek van Kim:
"bij elke speler die je ziet daar rechtstreeks gewoon te kunnen een scrape
starten. die scrape moet dan padelstat en TVL scrapen. Wel enkel TVL
scraping voor missing/laatste periode zoals vroeger al aangehaald")
--------------------------------------------------------------------------
render_player_summary_inline() is de EEN, centrale plek die "Detail per
speler" toont - hergebruikt door o.a. opponent_analysis.render_overview_
and_detail() (Team-analyse-detail), page_players.py en page_my_profile.py
(via player_dashboard_shared.py) en de Opstelling-analyse. Door de nieuwe
knop HIER toe te voegen (i.p.v. op elke aanroepplek apart), verschijnt
"bij elke speler die je ziet" in 1 keer, zonder elke pagina apart aan te
passen.
Nieuwe functie _render_scrape_button(): dunne wrapper rond
cloud_helpers.render_full_player_scrape_button() (1 knop, triggert BEIDE
GitHub Actions-workflows: TVL-matchdata met mode="missing" EN
padelstats.be playing strength, voor exact deze ene speler). Enkel
zichtbaar als een GitHub-token geconfigureerd staat (dus vooral relevant
op Streamlit Community Cloud, waar lokaal scrapen sowieso niet kan) - een
importfout van cloud_helpers blokkeert de rest van deze functie nooit
(lazy, defensieve import).
--------------------------------------------------------------------------
PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19 (v9, op verzoek van Kim, chat
2026-09-19: "Ook wel handig om een link naar het klassement te hebben bij
de ploeganalyse. eventueel in aparte tab.")
--------------------------------------------------------------------------
Nieuwe, kleine toevoeging: een klikbare link naar de OFFICIËLE TVL-
klassementberekeningspagina van een speler (dezelfde pagina die
scrape_klassement.py zelf bezoekt om de historiek op te halen - dus altijd
consistent met de brondata).
BELANGRIJK, wat dit mogelijk maakte: scrape_klassement.py importeerde tot
nu toe Playwright op MODULE-NIVEAU, wat betekende dat dit bestand (en elke
andere UI-module) scrape_klassement.py NOOIT rechtstreeks kon importeren
zonder de hele pagina te laten crashen op Streamlit Community Cloud (geen
Playwright daar). Sinds PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19 in
scrape_klassement.py zelf (de Playwright-import is daar nu LAZY, enkel
binnen scrape_klassement() zelf) is dat bestand overal veilig te
importeren - build_klassement_url() (nieuw, Playwright-vrij) kan dus hier
gewoon op module-niveau gebruikt worden.
klassement_link_url() hieronder is een DEFENSIEVE, foutbestendige wrapper
(geeft None terug bij elke onverwachte fout, i.p.v. de pagina te laten
crashen) - build_player_summary() neemt het resultaat op als
"klassement_url" in de teruggegeven dict, zodat zowel
render_player_summary_inline() (Detail per speler) als
opponent_analysis.py (Overzichtstabel + eventuele aparte tab) dit
rechtstreeks kunnen hergebruiken zonder de URL apart te herberekenen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19 (v10, op
verzoek van Kim, chat 2026-09-19: "ik merk nu plots bij mijn profiel dat ik
P100 zou zijn. dat klopt niet, ik ben P200. Ik wel virtueel P100 op dit
moment. bekijk of je dit goed ophaalt. andres is dat verkeerd vooralle
spelers")
--------------------------------------------------------------------------
ROOT CAUSE (zie scrape_klassement.py voor de volledige analyse, incl. de
officiële TVL-FAQ-bevestiging): Tennis en Padel Vlaanderen onderscheidt
EXPLICIET "vorig", "huidig" (officieel, geldig tot de eerstvolgende 2x/jaar-
berekening) en "virtueel" (voorspelling voor de VOLGENDE berekening,
gebaseerd op lopende resultaten) klassement. scrape_klassement.klassement_
to_history_summary() gaf voor de HUIDIGE periode tot nu toe het VIRTUELE/
vertekende cijfer (_dominant_level(), afgeleid uit een niveau_data-tabel die
- bevestigd via de officiële berekeningsmethode - systematisch richting
lagere niveaus vertekend is) terug als "klassement" i.p.v. het OFFICIËLE,
huidig geldige cijfer. Dit trof ALLE spelers (bevestigd: Kim's eigen vraag
"andres is dat verkeerd vooralle spelers" - JA), niet enkel Kim's profiel,
want render_player_summary_inline() hieronder is de ENE, centrale plek die
"Huidig klassement" toont doorheen de hele app.
FIX: _history_rows() geeft nu ook "virtueel_klassement" per rij door (nieuw
veld uit klassement_to_history_summary(), enkel gevuld voor de meest
recente/huidige periode). render_player_summary_inline() toont voortaan,
ALS er een afwijkend virtueel cijfer gekend is, dat APART en duidelijk
gelabeld naast (niet in plaats van) "Huidig klassement" - transparant, in
lijn met Kim's eerder al bevestigde voorkeur (zie PADEL_ANALYSIS_LINEUP_
TRANSPARENCY_2026-09-19 in page_lineup_lab.py) om een berekend/afgeleid
cijfer nooit stilzwijgend te verstoppen of te verwarren met het officiële.
"""
from __future__ import annotations
import re
from collections import Counter
from datetime import datetime
from typing import Optional
import pandas as pd
import streamlit as st
import firebase_service as fb
# PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19: nu veilig te importeren op
# module-niveau (ook op Streamlit Community Cloud), dankzij de lazy
# Playwright-import in scrape_klassement.py zelf. Toch defensief
# geïmporteerd (try/except), consistent met de rest van dit bestand se
# stijl (bv. _render_scrape_button() hieronder doet hetzelfde met
# cloud_helpers) - een onverwachte importfout in scrape_klassement.py mag
# nooit de rest van het dossier blokkeren.
try:
    import scrape_klassement as _sk
except Exception:  # noqa: BLE001  pragma: no cover
    _sk = None
_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11,
    "december": 12,
}
# Minimum aantal matchen voor een statistisch zinvolle winrate.
MIN_MATCHES_FOR_WINRATE = 3
# ─────────────────────────────────────────────
# Parsers / normalisatie
# ─────────────────────────────────────────────
def _parse_match_date(text) -> Optional[tuple]:
    if not text:
        return None
    text = str(text).strip()
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if match:
        return int(match.group(3)), int(match.group(2)), int(match.group(1))
    match = re.search(r"(\d{1,2})\s+([a-zA-Zàéè]+)\s+(\d{4})", text.lower())
    if match and match.group(2) in _DUTCH_MONTHS:
        return int(match.group(3)), _DUTCH_MONTHS[match.group(2)], int(match.group(1))
    return None
def _parse_rank(value) -> Optional[int]:
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else None
def _normalize_id(value) -> str:
    """Maakt spelgroep-ID's vergelijkbaar ongeacht of ze als int, float of
    string werden opgeslagen ('702074', 702074, 702074.0)."""
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text
def _period_sort_key(label) -> tuple:
    """Sorteert period_labels zoals 'Resultaten van week 27/2026 tot en met
    week 48/2026' chronologisch. Valt terug op alfabetisch bij onbekend
    formaat."""
    text = str(label or "")
    weeks = re.findall(r"week\s+(\d{1,2})/(\d{4})", text.lower())
    if weeks:
        # Sorteer op de EINDgrens van de periode: recentste periode eerst.
        week, year = weeks[-1]
        return 1, int(year), int(week), text
    years = re.findall(r"(20\d{2})", text)
    if years:
        return 1, int(years[-1]), 0, text
    return 0, 0, 0, text
def _short_klassement_label(periode: str) -> str:
    """PADEL_ANALYSIS_KLASSEMENT_LABEL_SHORTENING_2026-09-10.
    Verkort ruwe periode-omschrijvingen zoals 'Startklassement' of
    'Zomerklassement' tot 'Start <jaar>' / 'Zomer <jaar>', leesbaar als
    as-label op een grafiek. Als er geen jaartal in de brontekst zelf staat,
    wordt enkel het seizoenswoord getoond - er wordt nooit een jaartal
    verzonnen. Onbekende formaten worden ingekort in plaats van volledig
    getoond, zodat de as sowieso leesbaar blijft.
    """
    text = str(periode or "").strip()
    if not text:
        return ""
    lower = text.lower()
    year_match = re.search(r"(20\d{2})", text)
    year = year_match.group(1) if year_match else ""
    if "zomer" in lower or "summer" in lower:
        season = "Zomer"
    elif "start" in lower or "begin" in lower:
        season = "Start"
    else:
        return text if len(text) <= 18 else text[:15] + "..."
    return f"{season} {year}".strip()
def _is_interclub(match: dict) -> bool:
    value = str(match.get("match_type") or match.get("type") or "").strip().lower()
    return value == "interclub" or "interclub" in value
def _winrate_str(wins: int, losses: int) -> str:
    known = wins + losses
    return f"{round(wins / known * 100, 1)}%" if known else "-"
def _winrate_display(wins: int, losses: int) -> str:
    """Toont de winrate, maar markeert expliciet wanneer ze op te weinig
    matchen gebaseerd is om betekenis te hebben."""
    known = wins + losses
    if known == 0:
        return "-"
    text = _winrate_str(wins, losses)
    if known < MIN_MATCHES_FOR_WINRATE:
        return f"{text} ({known}x)"
    return text
def _format_fetched_at(value) -> str:
    """Kort, leesbaar formaat voor een ISO-timestamp (bv. padelstat
    fetched_at). Geeft de ruwe waarde terug als parsing faalt, zodat er
    nooit een onverwachte crash optreedt op een onverwacht formaat."""
    if not value:
        return "onbekend"
    try:
        cleaned = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%d/%m/%Y")
    except Exception:
        return str(value)
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19: link naar officiële TVL-pagina
# ─────────────────────────────────────────────
def klassement_link_url(player_id) -> Optional[str]:
    """Geeft de URL van de officiële TVL-klassementberekeningspagina terug
    voor deze speler, of None als scrape_klassement.py niet beschikbaar is
    of er iets onverwachts misloopt (nooit een blokkerende fout - dit is
    puur een handig extraatje, geen kritiek pad)."""
    if _sk is None or not player_id:
        return None
    try:
        return _sk.build_klassement_url(player_id)
    except Exception:
        return None
def _render_klassement_link_button(player_id, label: str = "🔗 Bekijk officieel klassement op TVL") -> None:
    """Toont, indien beschikbaar, een klikbare link naar de officiële TVL-
    klassementberekeningspagina van deze speler. Gebruikt st.link_button()
    (Streamlit >= 1.27) met een fallback naar een gewone markdown-link voor
    het geval een oudere Streamlit-versie draait - nooit een harde crash."""
    url = klassement_link_url(player_id)
    if not url:
        return
    try:
        st.link_button(label, url, use_container_width=False)
    except AttributeError:
        st.markdown(f"[{label}]({url})")
# ─────────────────────────────────────────────
# Klassementshistoriek
# LET OP: hoe HOGER het klassementsgetal, hoe BETER de speler.
# ─────────────────────────────────────────────
def _history_rows(doc: dict) -> list[dict]:
    """Leest klassement_history en sorteert RECENTSTE EERST (chronologisch,
    niet op ranggetal). Voegt 'periode_kort' toe voor leesbare as-labels.
    PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19: leest nu
    ook het (optionele) "virtueel_klassement"-veld per rij door (nieuw sinds
    scrape_klassement.klassement_to_history_summary() - enkel gevuld voor de
    meest recente/huidige periode)."""
    history_doc = (doc or {}).get("klassement_history") or {}
    rows = []
    for index, row in enumerate(history_doc.get("history") or []):
        rank = _parse_rank(
            row.get("klassement")
            or row.get("begin_klassement")
            or row.get("selected_period_klassement")
            or row.get("vorig_klassement")
            or row.get("berekend_klassement")
        )
        if rank is None:
            continue
        periode_raw = row.get("periode") or row.get("label") or row.get("periodeomschrijving") or ""
        virtueel_rank = _parse_rank(row.get("virtueel_klassement"))
        rows.append({
            "index": index,
            "datum": row.get("datum") or "",
            "periode": periode_raw,
            "periode_kort": _short_klassement_label(periode_raw),
            "rank": rank,
            # PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19:
            # None zodra virtueel_klassement ontbreekt OF gelijk is aan het
            # officiële cijfer (dan is er niets aparts te melden).
            "virtual_rank": virtueel_rank if (virtueel_rank is not None and virtueel_rank != rank) else None,
        })
        if rank is None:
            continue
    def sort_key(row):
        parsed = _parse_match_date(row.get("datum"))
        if parsed:
            return (2,) + parsed + (0,)
        period = _period_sort_key(row.get("periode"))
        if period[0]:
            return (1, period[1], period[2], 0, 0)
        # Onbekend formaat: bewaar de oorspronkelijke volgorde.
        return (0, 0, 0, 0, -row["index"])
    return sorted(rows, key=sort_key, reverse=True)
def _history_summary(doc: dict):
    """Geeft (huidig, beste, wanneer_beste, alle_rijen) terug.
    'beste' = HOOGSTE klassementsgetal (hoger = sterker)."""
    rows = _history_rows(doc)
    if not rows:
        return None, None, None, []
    current = rows[0]
    best = max(rows, key=lambda row: row["rank"])
    best_when = best.get("datum") or best.get("periode_kort") or best.get("periode")
    return current["rank"], best["rank"], best_when, rows
def _current_virtual_rank(history_rows: list[dict]) -> Optional[int]:
    """PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19: geeft
    het virtuele (voorspelde) klassement van de MEEST RECENTE periode terug,
    ENKEL als dat afwijkt van het officiële cijfer (anders niets te melden).
    history_rows is al recentste-eerst gesorteerd door _history_rows()."""
    if not history_rows:
        return None
    return history_rows[0].get("virtual_rank")
def _best_rank_from_klassement_history(doc: dict) -> Optional[int]:
    """Behouden voor compatibiliteit met bestaande aanroepen. Hoogste getal."""
    return max((row["rank"] for row in _history_rows(doc)), default=None)
def _best_rank_opportunistic(player_id: str, search_docs: dict) -> Optional[int]:
    """Leidt een klassement af uit matchrecords van ANDERE spelers waarin deze
    persoon als tegenstander voorkwam. Hoogste gevonden waarde = beste."""
    values = []
    target = _normalize_id(player_id)
    for doc in (search_docs or {}).values():
        for match in (doc or {}).get("matches", []) or []:
            if _normalize_id(match.get("opp1_user_id")) == target:
                rank = _parse_rank(match.get("opp1_ranking"))
            elif _normalize_id(match.get("opp2_user_id")) == target:
                rank = _parse_rank(match.get("opp2_ranking"))
            else:
                continue
            if rank is not None:
                values.append(rank)
    return max(values) if values else None
def _current_rank_fallback(player_id: str, matches: list[dict], search_docs: dict) -> Optional[int]:
    """Meest recente bekende klassement (chronologisch, niet op hoogte)."""
    dated = []
    target = _normalize_id(player_id)
    for doc in (search_docs or {}).values():
        for match in (doc or {}).get("matches", []) or []:
            rank = None
            if _normalize_id(match.get("opp1_user_id")) == target:
                rank = _parse_rank(match.get("opp1_ranking"))
            elif _normalize_id(match.get("opp2_user_id")) == target:
                rank = _parse_rank(match.get("opp2_ranking"))
            if rank is not None:
                date = _parse_match_date(match.get("match_date") or match.get("tournament_date_start")) or (0, 0, 0)
                dated.append((date, rank))
    if dated:
        return max(dated, key=lambda item: item[0])[1]
    for match in sorted(matches, key=lambda item: _parse_match_date(item.get("match_date")) or (0, 0, 0), reverse=True):
        rank = _parse_rank(match.get("ranking") or match.get("player_ranking"))
        if rank is not None:
            return rank
    return None
def _render_ranking_timeline(rows: list[dict]) -> None:
    if not rows:
        st.info("Nog geen klassementshistoriek opgeslagen voor deze speler.")
        return
    chart_rows = []
    for reverse_index, row in enumerate(reversed(rows)):
        # Voorkeur: echte datum (al kort). Anders: verkort seizoenslabel
        # ('Start 2025'/'Zomer 2025') in plaats van de lange ruwe tekst.
        label = row.get("datum") or row.get("periode_kort") or row.get("periode") or str(reverse_index + 1)
        chart_rows.append({"Moment": str(label), "Klassement": row["rank"]})
    chart = pd.DataFrame(chart_rows).set_index("Moment")
    st.caption("Hoger klassementscijfer betekent sterker.")
    try:
        import altair as alt
        source = chart.reset_index()
        visual = alt.Chart(source).mark_line(point=True).encode(
            x=alt.X("Moment:N", sort=None, title="Periode"),
            y=alt.Y("Klassement:Q", title="Klassement"),
            tooltip=["Moment:N", alt.Tooltip("Klassement:Q", format=".0f")],
        ).properties(height=240)
        st.altair_chart(visual, use_container_width=True)
    except Exception:
        st.line_chart(chart, height=240)
# ─────────────────────────────────────────────
# Tweelaagse poulefilter
# ─────────────────────────────────────────────
def split_matches(
    matches: list[dict],
    current_spelgroep_id: Optional[str] = None,
    current_reeks_url: Optional[str] = None,
) -> tuple[list[dict], list[dict], dict]:
    """Splitst interclubmatches in (huidige poule, historiek, meta).
    Laag 1 (huidige poule): strikt op spelgroep_id. Als er geen spelgroep_id
    meegegeven is, is deze laag leeg - er wordt NOOIT geraden.
    Laag 2 (historiek): alle overige interclubmatches. Dit is bewust GEEN
    fallback: beide lijsten worden apart teruggegeven zodat de UI ze apart en
    correct gelabeld kan tonen.
    """
    interclub = [match for match in matches if _is_interclub(match)]
    target_id = _normalize_id(current_spelgroep_id)
    target_url = str(current_reeks_url or "").strip().rstrip("/").lower()
    current: list[dict] = []
    history: list[dict] = []
    matched_on = "geen poulecontext"
    if target_id:
        for match in interclub:
            match_id = _normalize_id(
                match.get("spelgroep_id") or match.get("pool_id") or match.get("poule_id")
            )
            (current if match_id == target_id else history).append(match)
        if current:
            matched_on = "spelgroep_id"
    elif target_url:
        for match in interclub:
            match_url = str(match.get("reeks_url") or "").strip().rstrip("/").lower()
            (current if match_url and match_url == target_url else history).append(match)
        if current:
            matched_on = "reeks_url"
    else:
        history = list(interclub)
    if target_id and not current:
        matched_on = "poule herkend, nog geen matchen gespeeld"
    meta = {
        "matched_on": matched_on,
        "target_spelgroep_id": target_id or None,
        "interclub_total": len(interclub),
    }
    return current, history, meta
def _period_breakdown(matches: list[dict]) -> list[dict]:
    """Groepeert historiek per period_label + spelgroep_id, recentste eerst."""
    buckets: dict[tuple, dict] = {}
    for match in matches:
        label = str(match.get("period_label") or "Onbekende periode").strip()
        group = _normalize_id(match.get("spelgroep_id")) or "?"
        bucket = buckets.setdefault((label, group), {
            "Periode": label,
            "Poule": group,
            "Matches": 0,
            "W": 0,
            "V": 0,
        })
        bucket["Matches"] += 1
        if match.get("won") is True:
            bucket["W"] += 1
        elif match.get("won") is False:
            bucket["V"] += 1
    rows = list(buckets.values())
    for row in rows:
        row["Winrate"] = _winrate_display(row["W"], row["V"])
    return sorted(rows, key=lambda row: _period_sort_key(row["Periode"]), reverse=True)
def _partner_rows(matches: list[dict], limit: int = 5) -> list[dict]:
    buckets: dict[str, dict] = {}
    for match in matches:
        name = str(match.get("partner_name") or "").strip()
        if not name:
            continue
        bucket = buckets.setdefault(name, {"Partner": name, "Matches": 0, "W": 0, "V": 0})
        bucket["Matches"] += 1
        if match.get("won") is True:
            bucket["W"] += 1
        elif match.get("won") is False:
            bucket["V"] += 1
    rows = list(buckets.values())
    for row in rows:
        row["Winrate"] = _winrate_display(row["W"], row["V"])
    return sorted(rows, key=lambda row: (row["Matches"], row["W"]), reverse=True)[:limit]
def _result_rows(matches: list[dict], limit: Optional[int] = None) -> list[dict]:
    ordered = sorted(
        matches,
        key=lambda item: _parse_match_date(item.get("match_date")) or (0, 0, 0),
        reverse=True,
    )
    if limit:
        ordered = ordered[:limit]
    rows = []
    for match in ordered:
        rows.append({
            "Datum": match.get("match_date") or "",
            "Periode": match.get("period_label") or "",
            "Partner": match.get("partner_name") or "",
            "Tegen": " / ".join(v for v in [match.get("opp1_name"), match.get("opp2_name")] if v),
            "Score": match.get("score") or "",
            "W/V": match.get("result") or ("W" if match.get("won") is True else ("V" if match.get("won") is False else "-")),
        })
    return rows
def _form_string(matches: list[dict], limit: int = 8) -> str:
    """Recente vorm als leesbare reeks, recentste links (bv. 'W W V W')."""
    ordered = sorted(
        matches,
        key=lambda item: _parse_match_date(item.get("match_date")) or (0, 0, 0),
        reverse=True,
    )[:limit]
    marks = []
    for match in ordered:
        if match.get("won") is True:
            marks.append("W")
        elif match.get("won") is False:
            marks.append("V")
        else:
            marks.append("-")
    return " ".join(marks) if marks else "-"
# ─────────────────────────────────────────────
# Spelerssamenvatting (plat, opslagbaar in Firestore)
# ─────────────────────────────────────────────
def build_player_summary(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
) -> dict:
    """Berekent alle scoutinggegevens voor een speler in twee lagen.
    all_docs:    matchdocumenten van de tegenstander-roster (smal).
    global_docs: optioneel, alle gekende spelers - breder, gebruikt voor de
                 opportunistische ranking-fallback.
    PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19: geeft nu ook "klassement_url"
    mee terug - de link naar de officiële TVL-klassementberekeningspagina
    voor deze speler, zodat opponent_analysis.py (Overzichtstabel/aparte
    tab) dit rechtstreeks kunnen hergebruiken zonder de URL apart te
    herberekenen.
    PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19: geeft nu
    ook "current_virtual_rank" mee terug (het VOORSPELDE klassement voor de
    eerstvolgende officiële berekening, ENKEL gevuld als dat afwijkt van het
    officiële "current_rank") - zie module-docstring voor de volledige
    toelichting bij deze fix.
    """
    doc = fb.get_player(player_id) or all_docs.get(str(player_id)) or {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    ranking_doc = doc if doc.get("klassement_history") else profile_doc
    matches = doc.get("matches", []) or []
    current_matches, history_matches, meta = split_matches(
        matches, current_spelgroep_id, current_reeks_url
    )
    wins_cur = sum(1 for m in current_matches if m.get("won") is True)
    losses_cur = sum(1 for m in current_matches if m.get("won") is False)
    wins_hist = sum(1 for m in history_matches if m.get("won") is True)
    losses_hist = sum(1 for m in history_matches if m.get("won") is False)
    rank_search_docs = global_docs if global_docs else all_docs
    current_rank, best_rank, best_when, history_rows = _history_summary(ranking_doc)
    # PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19: het
    # virtuele cijfer wordt UITSLUITEND afgeleid uit de eigen, expliciet
    # gescrapete klassement_history (nooit uit de opportunistische
    # fallbacks hieronder, die berusten op tegenstander-matchrecords en dus
    # geen "virtueel_klassement"-concept kennen).
    current_virtual_rank = _current_virtual_rank(history_rows)
    current_rank = current_rank or _current_rank_fallback(player_id, matches, rank_search_docs)
    best_rank = best_rank or _best_rank_opportunistic(player_id, rank_search_docs)
    # 'beste' is het HOOGSTE getal (hoger = sterker), niet het laagste.
    if current_rank is not None and (best_rank is None or current_rank > best_rank):
        best_rank = current_rank
    # PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13: 'playing strength' komt nu
    # UITSLUITEND uit de gecachete padelstats.be-waarde. Geen eigen
    # berekening meer als fallback - is er niets gecached, dan blijft dit
    # veld gewoon None en toont de UI expliciet "nog niet opgehaald".
    try:
        padelstat = fb.get_padelstat_rating(player_id)
    except Exception:
        padelstat = None
    if padelstat and padelstat.get("rating") is not None:
        current_elo = padelstat["rating"]
        elo_source = "padelstat"
        elo_fetched_at = padelstat.get("fetched_at")
    else:
        current_elo = None
        elo_source = "none"
        elo_fetched_at = None
    return {
        "schema": 9,
        "player_id": str(player_id),
        "name": name,
        # Klassement
        "current_rank": current_rank,
        "best_rank": best_rank,
        "best_rank_when": best_when,
        # PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19: enkel
        # gevuld als het afwijkt van current_rank (zie _current_virtual_rank()).
        "current_virtual_rank": current_virtual_rank,
        "history": history_rows,
        "history_available": bool(history_rows),
        # PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19: link naar de officiële
        # TVL-berekeningspagina, defensief (None als niet beschikbaar).
        "klassement_url": klassement_link_url(player_id),
        # Playing strength (padelstats.be, extern - geen eigen berekening meer)
        "current_elo": current_elo,
        "elo_source": elo_source,
        "elo_fetched_at": elo_fetched_at,
        # Laag 1: huidige poule
        "matches_relevant": len(current_matches),
        "wins_relevant": wins_cur,
        "losses_relevant": losses_cur,
        "winrate_relevant": _winrate_display(wins_cur, losses_cur),
        "partners": _partner_rows(current_matches),
        "poule_results": _result_rows(current_matches),
        "poule_results_exact": bool(current_matches),
        "poule_matched_on": meta["matched_on"],
        "poule_spelgroep_id": meta["target_spelgroep_id"],
        # Laag 2: historiek uit vorige periodes
        "matches_history": len(history_matches),
        "wins_history": wins_hist,
        "losses_history": losses_hist,
        "winrate_history": _winrate_display(wins_hist, losses_hist),
        "partners_history": _partner_rows(history_matches),
        "history_results": _result_rows(history_matches, limit=15),
        "history_periods": _period_breakdown(history_matches),
        "form_history": _form_string(history_matches),
        # Totaal
        "matches_total": len(matches),
    }
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18: scrape-knop
# ─────────────────────────────────────────────
def _render_scrape_button(player_id: str, player_name: str, key_prefix: str) -> None:
    """Dunne, defensieve wrapper rond cloud_helpers.render_full_player_
    scrape_button(). Faalt de import (bv. cloud_helpers.py nog niet
    aanwezig), dan wordt dit stil overgeslagen - de rest van het dossier
    blijft gewoon werken, exact zoals de bestaande render_cloud_scrape_
    trigger()-aanroepen elders in het project dit al doen."""
    try:
        import cloud_helpers as ch
    except Exception:  # noqa: BLE001  pragma: no cover
        return
    ch.render_full_player_scrape_button(
        player_id, player_name=player_name, key_prefix=f"{key_prefix}_scrape",
    )
# ─────────────────────────────────────────────
# Inline renderer
# ─────────────────────────────────────────────
def render_player_summary_inline(summary: dict) -> None:
    """Toont build_player_summary()-resultaat meteen, in twee duidelijk
    gescheiden lagen.
    PADEL_ANALYSIS_PER_PLAYER_FULL_SCRAPE_2026-09-18 (op verzoek van Kim):
    toont bovenaan nu ook de "🔄 Scrape deze speler nu (TVL + padelstat)"-
    knop - deze functie is de centrale, hergebruikte plek voor "Detail per
    speler" over de hele app heen (Team-analyse, Opstelling-analyse,
    Spelers-pagina, Mijn profiel), dus deze ene toevoeging volstaat om de
    knop overal te laten verschijnen.
    PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19 (op verzoek van Kim): toont nu
    ook een klikbare link naar de officiële TVL-klassementberekeningspagina,
    naast de al bestaande klassementshistoriek-grafiek - handig om snel de
    brondata zelf te verifiëren of details te zien die niet in onze eigen
    samenvatting zitten.
    PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19 (op verzoek
    van Kim: "ik merk nu plots bij mijn profiel dat ik P100 zou zijn. dat
    klopt niet, ik ben P200. Ik wel virtueel P100 op dit moment"): "Huidig
    klassement" toont nu ALTIJD het OFFICIËLE cijfer (niet meer het
    vertekende, virtuele) - en toont, ENKEL als er een afwijkend virtueel
    cijfer gekend is, dat APART en duidelijk gelabeld als 5de metric,
    zodat dit onderscheid nooit meer verward kan worden."""
    player_id = summary.get("player_id")
    player_name = summary.get("name") or ""
    if player_id:
        _render_scrape_button(str(player_id), player_name, key_prefix=f"dossier_{player_id}")
    current_virtual = summary.get("current_virtual_rank")
    # PADEL_ANALYSIS_VIRTUAL_VS_OFFICIAL_KLASSEMENT_FIX_2026-09-19: 5 kolommen
    # i.p.v. 4 zodra er een afwijkend virtueel klassement gekend is, zodat
    # beide cijfers naast elkaar zichtbaar zijn - anders blijft het bestaande
    # 4-kolommen-gedrag ongewijzigd.
    if current_virtual is not None:
        c1, c2, c3, c4, c5 = st.columns(5)
    else:
        c1, c2, c3, c4 = st.columns(4)
        c5 = None
    current = summary.get("current_rank")
    best = summary.get("best_rank")
    c1.metric("Huidig klassement", f"P{current}" if current is not None else "Onbekend")
    c2.metric("Beste ooit", f"P{best}" if best is not None else "Onbekend")
    c3.metric("Matchen deze poule", summary.get("matches_relevant", 0))
    c4.metric("Matchen historiek", summary.get("matches_history", 0))
    if c5 is not None:
        c5.metric(
            "Virtueel klassement", f"P{current_virtual}",
            help=(
                "Voorspelling van TVL voor de EERSTVOLGENDE officiële klassementsberekening, "
                "gebaseerd op de tot nu toe behaalde resultaten deze periode. Dit is NOG NIET "
                "het officiële klassement (dat blijft 'Huidig klassement' hierboven) en kan bij "
                "de definitieve berekening nog afwijken."
            ),
        )
    if summary.get("best_rank_when"):
        st.caption(f"Beste klassement bereikt in/op: **{summary['best_rank_when']}**")
    # PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13: playing strength uitsluitend
    # via padelstats.be, geen eigen schatting meer.
    current_elo = summary.get("current_elo")
    if summary.get("elo_source") == "padelstat" and current_elo is not None:
        fetched = _format_fetched_at(summary.get("elo_fetched_at"))
        st.caption(
            f"🎯 Playing strength (padelstats.be): **P{current_elo}** (opgehaald op {fetched}). "
            "Onafhankelijke, externe schatting - geen officieel TVL-klassement."
        )
    else:
        st.caption(
            "🎯 Playing strength (padelstats.be): nog niet opgehaald voor deze speler."
        )
    st.markdown("##### 📈 Klassementshistoriek")
    # PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19: klikbare link naar de
    # officiële TVL-pagina, vlak bij de eigen klassementsgrafiek.
    if player_id:
        _render_klassement_link_button(player_id)
    _render_ranking_timeline(summary.get("history") or [])
    if not summary.get("history_available"):
        st.caption("Voor de volledige tijdlijn moet klassement_history voor deze speler nog gescrapet worden.")
    # ── Laag 1: huidige poule ──
    st.markdown("##### 🎯 Deze poule")
    poule_id = summary.get("poule_spelgroep_id")
    st.caption(f"Strikt gefilterd op spelgroep {poule_id or 'onbekend'} · {summary.get('poule_matched_on', '-')}")
    current_matches = summary.get("matches_relevant", 0)
    if current_matches:
        m1, m2 = st.columns(2)
        m1.metric(
            "Winrate deze poule",
            summary.get("winrate_relevant", "-"),
            f"{summary.get('wins_relevant', 0)}W - {summary.get('losses_relevant', 0)}V",
        )
        m2.metric("Gespeeld", current_matches)
        if current_matches < MIN_MATCHES_FOR_WINRATE:
            st.caption("Te weinig matchen voor een betrouwbare winrate. Gebruik vooral de historiek hieronder.")
        partners = summary.get("partners") or []
        if partners:
            st.markdown("**Partners deze poule**")
            st.dataframe(pd.DataFrame(partners), use_container_width=True, hide_index=True,
                         height=min(200, 40 + 36 * len(partners)))
        results = summary.get("poule_results") or []
        if results:
            st.markdown("**Resultaten deze poule**")
            st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True,
                         height=min(260, 40 + 36 * len(results)))
    else:
        st.info(
            "Deze speler heeft in de huidige poule nog geen gespeelde matchen in onze data. "
            "De historiek hieronder is voorlopig de beste scoutinginformatie."
        )
    # ── Laag 2: historiek ──
    st.markdown("##### 🗄️ Historiek uit vorige periodes")
    history_matches = summary.get("matches_history", 0)
    if not history_matches:
        st.info("Geen eerdere interclubmatches gekend voor deze speler.")
        return
    st.caption("Andere poules/periodes. Bruikbaar als inschatting van niveau en speelpatroon, niet als stand in de huidige poule.")
    h1, h2 = st.columns(2)
    h1.metric(
        "Winrate historiek",
        summary.get("winrate_history", "-"),
        f"{summary.get('wins_history', 0)}W - {summary.get('losses_history', 0)}V",
    )
    h2.metric("Recente vorm", summary.get("form_history", "-"))
    periods = summary.get("history_periods") or []
    if periods:
        st.markdown("**Per periode**")
        st.dataframe(pd.DataFrame(periods), use_container_width=True, hide_index=True,
                     height=min(200, 40 + 36 * len(periods)))
    partners_history = summary.get("partners_history") or []
    if partners_history:
        st.markdown("**Vaste partners in vorige periodes**")
        st.dataframe(pd.DataFrame(partners_history), use_container_width=True, hide_index=True,
                     height=min(220, 40 + 36 * len(partners_history)))
    history_results = summary.get("history_results") or []
    if history_results:
        with st.expander(f"Alle gekende resultaten uit vorige periodes ({len(history_results)} getoond)", expanded=False):
            st.dataframe(pd.DataFrame(history_results), use_container_width=True, hide_index=True,
                         height=min(420, 40 + 36 * len(history_results)))
# ─────────────────────────────────────────────
# Oudere knop-variant (compatibiliteit)
# ─────────────────────────────────────────────
def render_opponent_dossier(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    key_prefix: str = "opp_dossier",
    current_spelgroep_id: Optional[str] = None,
) -> None:
    doc = fb.get_player(player_id) or all_docs.get(str(player_id)) or {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    if not doc and not profile_doc:
        st.caption(f"Nog geen data gekend voor {name}. Scrape deze speler eerst.")
        _render_scrape_button(str(player_id), name, key_prefix=f"{key_prefix}_{player_id}_empty")
        return
    summary = build_player_summary(
        player_id, name, all_docs,
        current_reeks_url=current_reeks_url,
        current_spelgroep_id=current_spelgroep_id,
    )
    render_player_summary_inline(summary)
def render_opponent_dossier_button(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    key_prefix: str = "opp_dossier",
    current_spelgroep_id: Optional[str] = None,
) -> None:
    state_key = f"{key_prefix}_open_{player_id}"
    if st.button("🗂️ Dossier", key=f"{key_prefix}_btn_{player_id}"):
        st.session_state[state_key] = not st.session_state.get(state_key, False)
    if st.session_state.get(state_key):
        with st.container(border=True):
            st.markdown(f"### {name}")
            render_opponent_dossier(
                player_id, name, all_docs,
                current_reeks_url=current_reeks_url,
                key_prefix=f"{key_prefix}_{player_id}",
                current_spelgroep_id=current_spelgroep_id,
            )
