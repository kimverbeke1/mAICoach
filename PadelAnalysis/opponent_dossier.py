"""Opponent scouting dossier, version 2.

Key changes:
- ranking history sorted by actual date/period before choosing current rank;
- strict pool filtering, without falling back to another pool;
- tolerant ID and URL normalisation;
- partner, win-rate and result data all use the same filtered match set;
- misleading board-position heuristic removed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

import firebase_service as fb

_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10,
    "november": 11, "december": 12,
}


def _parse_match_date(value) -> Optional[tuple[int, int, int]]:
    if not value:
        return None
    text = str(value).strip()
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return tuple(map(int, match.groups()))
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if match:
        day, month, year = map(int, match.groups())
        return year, month, day
    match = re.search(r"(\d{1,2})\s+([a-zA-Zàéè]+)\s+(\d{4})", text.lower())
    if match and match.group(2) in _DUTCH_MONTHS:
        return int(match.group(3)), _DUTCH_MONTHS[match.group(2)], int(match.group(1))
    return None


def _parse_period_date(value, fallback_index: int = 0) -> tuple[int, int, int, int]:
    parsed = _parse_match_date(value)
    if parsed:
        return (*parsed, 0)
    text = str(value or "").lower()
    year_match = re.search(r"(20\d{2})", text)
    year = int(year_match.group(1)) if year_match else 0
    month = 0
    for label, number in _DUTCH_MONTHS.items():
        if label in text:
            month = number
            break
    quarter_match = re.search(r"(?:q|kwartaal\s*)([1-4])", text)
    if quarter_match and not month:
        month = int(quarter_match.group(1)) * 3
    return year, month, 0, -fallback_index


def _parse_rank(value) -> Optional[int]:
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _normalize_id(value) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text


def _normalize_url(value) -> str:
    return str(value or "").strip().rstrip("/").lower()


def _history_rows(doc: dict) -> list[dict]:
    source = (doc or {}).get("klassement_history") or {}
    rows = []
    for index, row in enumerate(source.get("history") or []):
        rank = _parse_rank(
            row.get("klassement") or row.get("begin_klassement")
            or row.get("selected_period_klassement") or row.get("vorig_klassement")
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
    return sorted(
        rows,
        key=lambda row: _parse_period_date(row.get("datum") or row.get("periode"), row["index"]),
        reverse=True,
    )


def _history_summary(doc: dict):
    rows = _history_rows(doc)
    if not rows:
        return None, None, None, []
    current = rows[0]
    best = min(rows, key=lambda row: row["rank"])
    return current["rank"], best["rank"], best.get("datum") or best.get("periode"), rows


def _best_rank_from_klassement_history(doc: dict) -> Optional[int]:
    return min((row["rank"] for row in _history_rows(doc)), default=None)


def _best_rank_opportunistic(player_id: str, search_docs: dict) -> Optional[int]:
    values = []
    for doc in (search_docs or {}).values():
        for match in (doc or {}).get("matches", []) or []:
            rank = None
            if _normalize_id(match.get("opp1_user_id")) == _normalize_id(player_id):
                rank = _parse_rank(match.get("opp1_ranking"))
            elif _normalize_id(match.get("opp2_user_id")) == _normalize_id(player_id):
                rank = _parse_rank(match.get("opp2_ranking"))
            if rank is not None:
                values.append(rank)
    return min(values) if values else None


def _current_rank_fallback(player_id: str, matches: list[dict], search_docs: dict) -> Optional[int]:
    dated = []
    for doc in (search_docs or {}).values():
        for match in (doc or {}).get("matches", []) or []:
            rank = None
            if _normalize_id(match.get("opp1_user_id")) == _normalize_id(player_id):
                rank = _parse_rank(match.get("opp1_ranking"))
            elif _normalize_id(match.get("opp2_user_id")) == _normalize_id(player_id):
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


def _is_interclub(match: dict) -> bool:
    value = str(match.get("match_type") or match.get("type") or "").strip().lower()
    return value == "interclub" or "interclub" in value


def _period_matches(matches: list[dict], current_reeks_url: Optional[str] = None,
                    current_spelgroep_id: Optional[str] = None) -> tuple[list[dict], bool, str]:
    """Return only matches proven to belong to the selected pool.

    Important: this function never falls back to a recent period, because that can
    leak partners and results from another pool.
    """
    interclub = [match for match in matches if _is_interclub(match)]
    target_id = _normalize_id(current_spelgroep_id)
    target_url = _normalize_url(current_reeks_url)

    if target_id:
        exact = [m for m in interclub if _normalize_id(m.get("spelgroep_id") or m.get("pool_id") or m.get("poule_id")) == target_id]
        if exact:
            return exact, True, "spelgroep_id"

        embedded = [m for m in interclub if target_id in _normalize_url(m.get("reeks_url") or m.get("url") or m.get("source_url"))]
        if embedded:
            return embedded, True, "spelgroep_id in URL"

    if target_url:
        exact = [m for m in interclub if _normalize_url(m.get("reeks_url") or m.get("url") or m.get("source_url")) == target_url]
        if exact:
            return exact, True, "reeks_url"

        # Compare meaningful IDs appearing in the URLs, rather than brittle full URLs.
        target_numbers = set(re.findall(r"\d{4,}", target_url))
        if target_numbers:
            related = []
            for match in interclub:
                candidate = _normalize_url(match.get("reeks_url") or match.get("url") or match.get("source_url"))
                if target_numbers.intersection(re.findall(r"\d{4,}", candidate)):
                    related.append(match)
            if related:
                return related, True, "ID uit reeks_url"

    # No pool context means we cannot safely claim that matches belong to this pool.
    return [], False, "geen exacte poulematch"


def _winrate_str(wins: int, losses: int) -> str:
    known = wins + losses
    return f"{round(wins / known * 100, 1)}%" if known else "-"


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
    for row in buckets.values():
        row["Winrate"] = _winrate_str(row["W"], row["V"])
    return sorted(buckets.values(), key=lambda row: (row["Matches"], row["W"]), reverse=True)[:limit]


def _render_ranking_timeline(rows: list[dict]) -> None:
    if not rows:
        st.info("Nog geen klassementshistoriek opgeslagen voor deze speler.")
        return
    chart_rows = [
        {"Moment": str(row.get("datum") or row.get("periode") or index + 1), "Klassement": row["rank"]}
        for index, row in enumerate(reversed(rows))
    ]
    try:
        import altair as alt
        source = pd.DataFrame(chart_rows)
        chart = alt.Chart(source).mark_line(point=True).encode(
            x=alt.X("Moment:N", sort=None, title="Periode"),
            y=alt.Y("Klassement:Q", scale=alt.Scale(reverse=True), title="P-klassement"),
            tooltip=["Moment:N", alt.Tooltip("Klassement:Q", format=".0f")],
        ).properties(height=240)
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.line_chart(pd.DataFrame(chart_rows).set_index("Moment"), height=240)


def build_player_summary(player_id: str, name: str, all_docs: dict,
                         current_reeks_url: Optional[str] = None,
                         current_spelgroep_id: Optional[str] = None,
                         global_docs: Optional[dict] = None) -> dict:
    doc = fb.get_player(player_id) or all_docs.get(str(player_id)) or {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    ranking_doc = doc if doc.get("klassement_history") else profile_doc
    matches = doc.get("matches", []) or []
    relevant, exact, filter_source = _period_matches(matches, current_reeks_url, current_spelgroep_id)
    wins = sum(1 for match in relevant if match.get("won") is True)
    losses = sum(1 for match in relevant if match.get("won") is False)
    search_docs = global_docs or all_docs
    current, best, best_when, history = _history_summary(ranking_doc)
    current = current or _current_rank_fallback(player_id, matches, search_docs)
    best = best or _best_rank_opportunistic(player_id, search_docs)
    if current is not None and (best is None or current < best):
        best = current

    results = []
    for match in sorted(relevant, key=lambda item: _parse_match_date(item.get("match_date")) or (0, 0, 0), reverse=True):
        results.append({
            "Datum": match.get("match_date") or "",
            "Partner": match.get("partner_name") or "",
            "Tegen": " / ".join(v for v in [match.get("opp1_name"), match.get("opp2_name")] if v),
            "Score": match.get("score") or "",
            "W/V": match.get("result") or ("W" if match.get("won") is True else ("V" if match.get("won") is False else "-")),
        })
    return {
        "player_id": str(player_id), "name": name,
        "current_rank": current, "best_rank": best, "best_rank_when": best_when,
        "matches_total": len(matches), "matches_relevant": len(relevant),
        "wins_relevant": wins, "losses_relevant": losses,
        "winrate_relevant": _winrate_str(wins, losses),
        "history": history, "history_available": bool(history),
        "partners": _partner_rows(relevant), "poule_results": results,
        "poule_results_exact": exact, "poule_filter_source": filter_source,
    }


def render_player_summary_inline(summary: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    current, best = summary.get("current_rank"), summary.get("best_rank")
    c1.metric("Huidig", f"P{current}" if current is not None else "Onbekend")
    c2.metric("Beste ooit", f"P{best}" if best is not None else "Onbekend")
    c3.metric("Matches in deze poule", summary.get("matches_relevant", 0))
    c4.metric("Winrate in deze poule", summary.get("winrate_relevant", "-"),
              f"{summary.get('wins_relevant', 0)}W - {summary.get('losses_relevant', 0)}V")
    if summary.get("best_rank_when"):
        st.caption(f"Beste klassement bereikt in/op: **{summary['best_rank_when']}**")
    if not summary.get("poule_results_exact"):
        st.warning("Geen matchrecords konden met zekerheid aan deze poule worden gekoppeld. Er worden bewust geen gegevens uit andere poules getoond.")

    st.markdown("##### 📈 Klassementshistoriek")
    _render_ranking_timeline(summary.get("history") or [])

    st.markdown("##### 🤝 Partners in deze poule")
    partners = summary.get("partners") or []
    if partners:
        st.dataframe(pd.DataFrame(partners), use_container_width=True, hide_index=True)
    else:
        st.info("Geen partnergegevens gevonden die met zekerheid bij deze poule horen.")

    st.markdown("##### 🎾 Resultaten in deze poule")
    results = summary.get("poule_results") or []
    if results:
        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
    else:
        st.info("Geen interclubmatches gevonden die met zekerheid bij deze poule horen.")


def render_opponent_dossier(player_id: str, name: str, all_docs: dict,
                            current_reeks_url: Optional[str] = None,
                            key_prefix: str = "opp_dossier", current_spelgroep_id: Optional[str] = None) -> None:
    summary = build_player_summary(player_id, name, all_docs, current_reeks_url, current_spelgroep_id)
    render_player_summary_inline(summary)


def render_opponent_dossier_button(player_id: str, name: str, all_docs: dict,
                                   current_reeks_url: Optional[str] = None,
                                   key_prefix: str = "opp_dossier", current_spelgroep_id: Optional[str] = None) -> None:
    state_key = f"{key_prefix}_open_{player_id}"
    if st.button("🗂️ Dossier", key=f"{key_prefix}_btn_{player_id}"):
        st.session_state[state_key] = not st.session_state.get(state_key, False)
    if st.session_state.get(state_key):
        with st.container(border=True):
            st.markdown(f"### {name}")
            render_opponent_dossier(player_id, name, all_docs, current_reeks_url, key_prefix, current_spelgroep_id)
