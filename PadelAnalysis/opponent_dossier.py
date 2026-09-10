"""
opponent_dossier.py - compact scoutingdossier voor een tegenstander.

Toont (build_player_summary / render_player_summary_inline):
- huidig klassement, beste klassement en datum/periode van die piek;
- klassementshistoriek als tijdlijn;
- bordpositie-heuristiek (hoe vaak board 1, board 2, ... gespeeld);
- meest gebruikte partners;
- interclubresultaten - allemaal beperkt tot DEZE poule/periode.

PADEL_ANALYSIS_RELEVANCE_FIX_2026-09-09:
Partners, bordpositie en resultaten werden voorheen berekend over ALLE
matches van een speler (ongeacht seizoen of poule), waardoor irrelevante data
verscheen (bv. een partner uit een andere poule/tornooi, of een partnertelling
die veel hoger lag dan het aantal effectief gespeelde interclubontmoetingen
deze poule). Fix: _period_matches() filtert nu eerst op spelgroep_id (het
exacte poule-ID), dan pas op reeks_url, dan pas op de meest recente
period_label als laatste redmiddel - en partners/bordpositie/resultaten worden
allemaal berekend op basis van datzelfde gefilterde resultaat.

PADEL_ANALYSIS_RANKING_LOOKUP_FIX_2026-09-09:
De opportunistische ranking-fallback (ranking afleiden uit matchrecords van
ANDERE spelers die deze persoon als tegenstander hadden) zocht voorheen enkel
binnen de smalle set van de tegenstander-ploeg zelf - spelers die zelden of
nooit tegen elkaar spelen (het zijn ploegmaats). build_player_summary()
aanvaardt nu een optionele 'global_docs' parameter (alle gekende spelers) om
die zoekruimte te verbreden.
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


def _history_rows(doc: dict) -> list[dict]:
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
            "datum": row.get("datum"),
            "periode": row.get("periode") or row.get("label") or row.get("periodeomschrijving") or "",
            "rank": rank,
        })
    return rows


def _history_summary(doc: dict):
    rows = _history_rows(doc)
    if not rows:
        return None, None, None, []
    current = rows[0]
    best = min(rows, key=lambda row: row["rank"])
    return current["rank"], best["rank"], best.get("datum") or best.get("periode"), rows


def _best_rank_from_klassement_history(doc: dict) -> Optional[int]:
    """Behouden voor compatibiliteit met bestaande aanroepen."""
    rows = _history_rows(doc)
    return min((row["rank"] for row in rows), default=None)


def _best_rank_opportunistic(player_id: str, search_docs: dict) -> Optional[int]:
    """Doorzoekt matchrecords van andere spelers naar een ranking die voor
    player_id werd opgetekend (als hij/zij daar als tegenstander verscheen).
    search_docs moet een zo breed mogelijke set van spelerdocumenten zijn -
    hoe breder, hoe groter de kans dat player_id daar effectief in voorkomt."""
    values = []
    for doc in search_docs.values():
        for match in (doc or {}).get("matches", []) or []:
            if str(match.get("opp1_user_id")) == str(player_id):
                rank = _parse_rank(match.get("opp1_ranking"))
            elif str(match.get("opp2_user_id")) == str(player_id):
                rank = _parse_rank(match.get("opp2_ranking"))
            else:
                continue
            if rank is not None:
                values.append(rank)
    return min(values) if values else None


def _current_rank_fallback(player_id: str, matches: list[dict], search_docs: dict) -> Optional[int]:
    dated = []
    for doc in search_docs.values():
        for match in (doc or {}).get("matches", []) or []:
            rank = None
            if str(match.get("opp1_user_id")) == str(player_id):
                rank = _parse_rank(match.get("opp1_ranking"))
            elif str(match.get("opp2_user_id")) == str(player_id):
                rank = _parse_rank(match.get("opp2_ranking"))
            if rank is not None:
                dated.append((_parse_match_date(match.get("match_date") or match.get("tournament_date_start")) or (0, 0, 0), rank))
    if dated:
        return sorted(dated, reverse=True)[0][1]
    for match in sorted(matches, key=lambda item: _parse_match_date(item.get("match_date")) or (0, 0, 0), reverse=True):
        rank = _parse_rank(match.get("ranking") or match.get("player_ranking"))
        if rank is not None:
            return rank
    return None


def _winrate_str(wins: int, losses: int) -> str:
    known = wins + losses
    return f"{round(wins / known * 100, 1)}%" if known else "-"


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


def _partner_rows(matches: list[dict], limit: int = 5) -> list[dict]:
    buckets = {}
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
        row["Winrate"] = _winrate_str(row["W"], row["V"])
    return sorted(rows, key=lambda row: (row["Matches"], row["W"]), reverse=True)[:limit]



def _period_matches(
    matches: list[dict],
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
) -> tuple[list[dict], bool]:
    """Filtert tot de interclubmatches die relevant zijn voor DEZE poule.

    Volgorde van precisie: spelgroep_id (het exacte poule-ID) > reeks_url >
    meest recente period_label als laatste redmiddel (kan meerdere poules
    omvatten en is dus minder precies)."""
    interclub = [match for match in matches if match.get("match_type") == "interclub"]
    if current_spelgroep_id:
        exact = [m for m in interclub if str(m.get("spelgroep_id") or "") == str(current_spelgroep_id)]
        if exact:
            return exact, True
    if current_reeks_url:
        exact = [match for match in interclub if match.get("reeks_url") == current_reeks_url]
        if exact:
            return exact, True
    labels = [match.get("period_label") for match in interclub if match.get("period_label")]
    if labels:
        latest = sorted(set(labels), reverse=True)[0]
        return [match for match in interclub if match.get("period_label") == latest], False
    return interclub, False


def render_opponent_dossier(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    key_prefix: str = "opp_dossier",
) -> None:
    """Oudere, klik-op-knop variant. Behouden voor compatibiliteit."""
    doc = fb.get_player(player_id) or all_docs.get(str(player_id)) or {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    if not doc and not profile_doc:
        st.caption(f"Nog geen data gekend voor {name}. Scrape deze speler eerst.")
        return

    ranking_doc = doc if doc.get("klassement_history") else profile_doc
    matches = doc.get("matches", []) or []
    stats = doc.get("stats", {}) or {}
    wins = int(stats.get("wins", sum(1 for match in matches if match.get("won") is True)) or 0)
    losses = int(stats.get("losses", sum(1 for match in matches if match.get("won") is False)) or 0)
    total = len(matches)

    current, best, best_when, history = _history_summary(ranking_doc)
    current = current or _current_rank_fallback(player_id, matches, all_docs)
    best = best or _best_rank_opportunistic(player_id, all_docs)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Huidig", f"P{current}" if current is not None else "Onbekend")
    c2.metric("Beste ooit", f"P{best}" if best is not None else "Onbekend")
    c3.metric("Matches gekend", total)
    c4.metric("Winrate", _winrate_str(wins, losses), f"{wins}W - {losses}V")
    if best_when:
        st.caption(f"Beste klassement bereikt in/op: **{best_when}**")

    st.markdown("#### Klassementshistoriek")
    _render_ranking_timeline(history)

    st.markdown("#### Meest gebruikte partners")
    partners = _partner_rows(matches)
    if partners:
        st.dataframe(pd.DataFrame(partners), use_container_width=True, hide_index=True, height=min(260, 40 + 36 * len(partners)))
    else:
        st.info("Nog geen partnerhistoriek gekend voor deze speler.")

    st.markdown("#### Resultaten in deze interclubpoule/periode")
    relevant, exact = _period_matches(matches, current_reeks_url)
    if relevant and not exact:
        st.caption("Geen exacte reeks_url-match gevonden. Daarom wordt de meest recente gekende interclubperiode getoond.")
    if not relevant:
        st.info("Geen interclubmatches gekend voor deze speler.")
        return
    rows = []
    for match in sorted(relevant, key=lambda item: _parse_match_date(item.get("match_date")) or (0, 0, 0), reverse=True):
        rows.append({
            "Datum": match.get("match_date") or "",
            "Partner": match.get("partner_name") or "",
            "Tegen": " / ".join(value for value in [match.get("opp1_name"), match.get("opp2_name")] if value),
            "Score": match.get("score") or "",
            "W/V": match.get("result") or ("W" if match.get("won") is True else ("V" if match.get("won") is False else "-")),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(320, 40 + 36 * len(rows)))


def render_opponent_dossier_button(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    key_prefix: str = "opp_dossier",
) -> None:
    state_key = f"{key_prefix}_open_{player_id}"
    if st.button("🗂️ Dossier", key=f"{key_prefix}_btn_{player_id}"):
        st.session_state[state_key] = not st.session_state.get(state_key, False)
    if st.session_state.get(state_key):
        with st.container(border=True):
            st.markdown(f"### {name}")
            render_opponent_dossier(
                player_id,
                name,
                all_docs,
                current_reeks_url=current_reeks_url,
                key_prefix=f"{key_prefix}_{player_id}",
            )


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_INLINE_SUMMARY_2026-09-09 (v2, relevantie-fix)
# Plat, opslagbaar dict + inline renderer. Alle secties (partners,
# bordpositie, resultaten) zijn nu beperkt tot DEZE poule/periode.
# ─────────────────────────────────────────────
def build_player_summary(
    player_id: str,
    name: str,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
) -> dict:
    """Berekent alle scoutinggegevens voor één speler als plat dict.

    all_docs: matchdocumenten van de tegenstander-ploeg-roster (smal).
    global_docs: optioneel, matchdocumenten van ALLE gekende spelers - breder,
    gebruikt voor de opportunistische ranking-fallback (zie module-docstring).
    """
    doc = fb.get_player(player_id) or all_docs.get(str(player_id)) or {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}

    ranking_doc = doc if doc.get("klassement_history") else profile_doc
    matches = doc.get("matches", []) or []

    relevant_matches, poule_exact = _period_matches(matches, current_reeks_url, current_spelgroep_id)
    wins_rel = sum(1 for m in relevant_matches if m.get("won") is True)
    losses_rel = sum(1 for m in relevant_matches if m.get("won") is False)

    rank_search_docs = global_docs if global_docs else all_docs
    current, best, best_when, history_rows = _history_summary(ranking_doc)
    current = current or _current_rank_fallback(player_id, matches, rank_search_docs)
    best = best or _best_rank_opportunistic(player_id, rank_search_docs)

    partners = _partner_rows(relevant_matches)

    poule_rows = []
    for match in sorted(relevant_matches, key=lambda item: _parse_match_date(item.get("match_date")) or (0, 0, 0), reverse=True):
        poule_rows.append({
            "Datum": match.get("match_date") or "",
            "Partner": match.get("partner_name") or "",
            "Tegen": " / ".join(v for v in [match.get("opp1_name"), match.get("opp2_name")] if v),
            "Score": match.get("score") or "",
            "W/V": match.get("result") or ("W" if match.get("won") is True else ("V" if match.get("won") is False else "-")),
        })

    return {
        "player_id": str(player_id),
        "name": name,
        "current_rank": current,
        "best_rank": best,
        "best_rank_when": best_when,
        "matches_total": len(matches),
        "matches_relevant": len(relevant_matches),
        "wins_relevant": wins_rel,
        "losses_relevant": losses_rel,
        "winrate_relevant": _winrate_str(wins_rel, losses_rel),
        "history": history_rows,
        "history_available": bool(history_rows),
        "partners": partners,

        "poule_results": poule_rows,
        "poule_results_exact": poule_exact,
    }


def render_player_summary_inline(summary: dict) -> None:
    """Toont build_player_summary()-resultaat meteen, zonder extra klik."""
    c1, c2, c3, c4 = st.columns(4)
    current = summary.get("current_rank")
    best = summary.get("best_rank")
    c1.metric("Huidig", f"P{current}" if current is not None else "Onbekend")
    c2.metric("Beste ooit", f"P{best}" if best is not None else "Onbekend")
    c3.metric("Matches (deze poule)", summary.get("matches_relevant", 0))
    c4.metric(
        "Winrate (deze poule)",
        summary.get("winrate_relevant", "-"),
        f"{summary.get('wins_relevant', 0)}W - {summary.get('losses_relevant', 0)}V",
    )
    if summary.get("best_rank_when"):
        st.caption(f"Beste klassement bereikt in/op: **{summary['best_rank_when']}**")
    if summary.get("matches_total", 0) != summary.get("matches_relevant", 0):
        st.caption(f"({summary.get('matches_total', 0)} matches gekend in totaal, over alle periodes/poules heen.)")

    st.markdown("##### 📈 Klassementshistoriek")
    _render_ranking_timeline(summary.get("history") or [])
    if not summary.get("history_available"):
        st.caption("Voor de volledige tijdlijn moet klassement_history voor deze speler nog opgeslagen worden.")


    st.markdown("##### 🤝 Meest gebruikte partners (deze poule/periode)")
    partners = summary.get("partners") or []
    if partners:
        st.dataframe(pd.DataFrame(partners), use_container_width=True, hide_index=True, height=min(220, 40 + 36 * len(partners)))
    else:
        st.info("Nog geen partnerhistoriek gekend binnen deze poule/periode.")

    st.markdown("##### 🎾 Resultaten in deze interclubpoule/periode")
    poule_rows = summary.get("poule_results") or []
    if poule_rows and not summary.get("poule_results_exact"):
        st.caption("Geen exacte match op poule/reeks gevonden. Meest recente gekende interclubperiode getoond.")
    if poule_rows:
        st.dataframe(pd.DataFrame(poule_rows), use_container_width=True, hide_index=True, height=min(280, 40 + 36 * len(poule_rows)))
    else:
        st.info("Geen interclubmatches gekend voor deze speler binnen deze poule/periode.")
