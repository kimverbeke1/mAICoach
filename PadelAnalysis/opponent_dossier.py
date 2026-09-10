"""
opponent_dossier.py - scoutingdossier voor een tegenstander (v3).

PADEL_ANALYSIS_TWO_LAYER_2026-09-10
Waarom deze versie bestaat:
De strikte poulefilter uit v2 was correct maar leverde in de praktijk bijna
niets op: de huidige competitieperiode (bv. spelgroep 702074/702079, weken
27/2026 - 48/2026) is pas gestart, dus tegenstanders hebben er 1 a 2 matchen.
Alle historiek zit in de vorige periode (bv. spelgroep 673692). v2 verborg die
volledig, v1 mengde ze stilzwijgend onder "deze poule" - beide fout.

v3 splitst expliciet in TWEE lagen:
  1. HUIDIGE POULE  - strikt op spelgroep_id. Feitelijk, maar vaak dun.
  2. HISTORIEK      - alle overige interclubmatches, per periode gegroepeerd,
                      duidelijk gelabeld als context uit een andere poule.
Beide lagen worden apart berekend en apart getoond. Er wordt nooit stilzwijgend
teruggevallen van laag 1 op laag 2.

reeks_url is in de praktijk None in alle opgeslagen matchrecords; de filter
steunt daarom op spelgroep_id, met reeks_url enkel als optionele extra.

Bordpositie-heuristiek is verwijderd (was een telling van round_text en gaf
geen betrouwbare bordnummering).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

import pandas as pd
import streamlit as st

import firebase_service as fb

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


def _period_start_key(label) -> tuple:
    """Startgrens van een periode, gebruikt om de huidige periode te herkennen."""
    text = str(label or "")
    weeks = re.findall(r"week\s+(\d{1,2})/(\d{4})", text.lower())
    if weeks:
        week, year = weeks[0]
        return int(year), int(week)
    return 0, 0


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


# ─────────────────────────────────────────────
# Klassementshistoriek
# ─────────────────────────────────────────────
def _history_rows(doc: dict) -> list[dict]:
    """Leest klassement_history en sorteert RECENTSTE EERST.

    v2-fix behouden: vroeger werd rows[0] blind als 'huidig' genomen, wat fout
    is zodra de bron oud->nieuw aanlevert.
    """
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
        rows.append({
            "index": index,
            "datum": row.get("datum") or "",
            "periode": row.get("periode") or row.get("label") or row.get("periodeomschrijving") or "",
            "rank": rank,
        })

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
    rows = _history_rows(doc)
    if not rows:
        return None, None, None, []
    current = rows[0]
    best = min(rows, key=lambda row: row["rank"])
    return current["rank"], best["rank"], best.get("datum") or best.get("periode"), rows


def _best_rank_from_klassement_history(doc: dict) -> Optional[int]:
    """Behouden voor compatibiliteit met bestaande aanroepen."""
    return min((row["rank"] for row in _history_rows(doc)), default=None)


def _best_rank_opportunistic(player_id: str, search_docs: dict) -> Optional[int]:
    """Leidt een klassement af uit matchrecords van ANDERE spelers waarin deze
    persoon als tegenstander voorkwam. search_docs moet zo breed mogelijk zijn."""
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
    return min(values) if values else None


def _current_rank_fallback(player_id: str, matches: list[dict], search_docs: dict) -> Optional[int]:
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
        label = row.get("datum") or row.get("periode") or str(reverse_index + 1)
        chart_rows.append({"Moment": str(label), "Klassement": row["rank"]})
    chart = pd.DataFrame(chart_rows).set_index("Moment")
    st.caption("Lager klassementscijfer betekent sterker. De Y-as wordt daarom omgekeerd weergegeven waar ondersteund.")
    try:
        import altair as alt
        source = chart.reset_index()
        visual = alt.Chart(source).mark_line(point=True).encode(
            x=alt.X("Moment:N", sort=None, title="Periode"),
            y=alt.Y("Klassement:Q", scale=alt.Scale(reverse=True), title="P-klassement"),
            tooltip=["Moment:N", alt.Tooltip("Klassement:Q", format=".0f")],
        ).properties(height=240)
        st.altair_chart(visual, use_container_width=True)
    except Exception:
        st.line_chart(chart, height=240)


# ─────────────────────────────────────────────
# Tweelaagse poulefilter (kern van v3)
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
    current_rank = current_rank or _current_rank_fallback(player_id, matches, rank_search_docs)
    best_rank = best_rank or _best_rank_opportunistic(player_id, rank_search_docs)
    if current_rank is not None and (best_rank is None or current_rank < best_rank):
        best_rank = current_rank

    return {
        "schema": 3,
        "player_id": str(player_id),
        "name": name,

        # Klassement
        "current_rank": current_rank,
        "best_rank": best_rank,
        "best_rank_when": best_when,
        "history": history_rows,
        "history_available": bool(history_rows),

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
# Inline renderer
# ─────────────────────────────────────────────
def render_player_summary_inline(summary: dict) -> None:
    """Toont build_player_summary()-resultaat meteen, in twee duidelijk
    gescheiden lagen."""
    c1, c2, c3, c4 = st.columns(4)
    current = summary.get("current_rank")
    best = summary.get("best_rank")
    c1.metric("Huidig klassement", f"P{current}" if current is not None else "Onbekend")
    c2.metric("Beste ooit", f"P{best}" if best is not None else "Onbekend")
    c3.metric("Matchen deze poule", summary.get("matches_relevant", 0))
    c4.metric("Matchen historiek", summary.get("matches_history", 0))

    if summary.get("best_rank_when"):
        st.caption(f"Beste klassement bereikt in/op: **{summary['best_rank_when']}**")

    st.markdown("##### 📈 Klassementshistoriek")
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
