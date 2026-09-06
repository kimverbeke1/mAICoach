from __future__ import annotations

import inspect
import re
from typing import Optional

import pandas as pd
import streamlit as st
import player_inline_actions as pia

import firebase_service as fb
import lineup_lab as ll


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _winrate_num(wins: int, losses: int) -> Optional[float]:
    known = wins + losses
    if known <= 0:
        return None
    return wins / known


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{round(value * 100, 1)}%"


def _winrate_str(wins: int, losses: int) -> str:
    return _pct(_winrate_num(wins, losses))


def _parse_rank(value) -> Optional[int]:
    """Parse P100/P200/... to int. Lower number means stronger ranking."""
    if value is None:
        return None
    m = re.search(r"(\d+)", str(value))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _format_rank(avg_rank: Optional[float]) -> str:
    if avg_rank is None:
        return "-"
    return f"P{int(round(avg_rank / 50) * 50)}"


def _match_date_key(m: dict) -> str:
    return str(m.get("match_date") or m.get("tournament_date_start") or "")


def _match_type_label(value: str) -> str:
    if value == "interclub":
        return "Interclub"
    if value == "tornooi":
        return "Tornooi"
    return value or "-"


def _result_char(m: dict) -> str:
    if m.get("result"):
        return str(m.get("result"))
    if m.get("won") is True:
        return "W"
    if m.get("won") is False:
        return "V"
    return "-"


def _partner_key(m: dict) -> str:
    """Stable key for grouping partner stats."""
    partner_pid = str(m.get("partner_user_id") or "").strip()
    if partner_pid:
        return f"id:{partner_pid}"
    partner_name = str(m.get("partner_name") or "").strip().lower()
    partner_name = re.sub(r"\s+", " ", partner_name)
    return f"name:{partner_name}"


def _dedupe_match_key(m: dict) -> str:
    """Dedupe only within the selected player's own document.

    The partner analysis must stay consistent with the selected player's match list.
    If Anneleen's player page shows 3 matches with Evy, this table should also show 3.
    """
    match_id = m.get("match_id")
    if match_id:
        return f"match_id:{match_id}"
    parts = [
        m.get("match_date") or m.get("tournament_date_start") or "",
        m.get("period_label") or "",
        m.get("reeks_name") or "",
        m.get("round_text") or "",
        m.get("partner_user_id") or m.get("partner_name") or "",
        m.get("opp1_name") or "",
        m.get("opp2_name") or "",
        m.get("score") or "",
    ]
    return "fallback:" + "|".join(str(x) for x in parts)


def _dataframe_kwargs(**kwargs):
    """Use Streamlit's new width API, with fallback for older versions."""
    try:
        if "width" in inspect.signature(st.dataframe).parameters:
            kwargs["width"] = "stretch"
        else:
            kwargs["use_container_width"] = True
    except Exception:
        kwargs["use_container_width"] = True
    return kwargs


def _partner_general_wr(partner_pid: str, docs: dict) -> tuple[Optional[float], int, int, int]:
    """Return partner's overall winrate from scraped partner document, if available."""
    if not partner_pid:
        return None, 0, 0, 0
    doc = docs.get(str(partner_pid)) or {}
    matches = doc.get("matches", []) or []
    stats = doc.get("stats", {}) or {}
    total = _safe_int(stats.get("total_matches"), len(matches))
    if total <= 0 and len(matches) <= 0:
        return None, 0, 0, 0
    wins = _safe_int(stats.get("wins"))
    losses = _safe_int(stats.get("losses"))
    wr = _winrate_num(wins, losses)
    return wr, total or len(matches), wins, losses


# -----------------------------------------------------------------------------
# Dataframe builders
# -----------------------------------------------------------------------------

def _available_players_df(docs: dict, selected_ids: list[str], name_lookup: dict) -> pd.DataFrame:
    """Only show players that actually have scraped match data."""
    rows = []
    for pid in selected_ids:
        pid = str(pid)
        doc = docs.get(pid) or {}
        matches = doc.get("matches", []) or []
        stats = doc.get("stats", {}) or {}
        total = _safe_int(stats.get("total_matches"), len(matches))
        if total <= 0 and len(matches) <= 0:
            continue
        wins = _safe_int(stats.get("wins"))
        losses = _safe_int(stats.get("losses"))
        rows.append({
            "Speler": name_lookup.get(pid, pid),
            "Matches": total or len(matches),
            "W": wins,
            "V": losses,
            "Winrate": _winrate_str(wins, losses),
            "Interclub": _safe_int(stats.get("interclub_matches")),
            "Tornooi": _safe_int(stats.get("tournament_matches")),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Interclub", "Matches"], ascending=[False, False])


def _recent_interclub_df(doc: dict, limit: int = 10) -> pd.DataFrame:
    matches = [m for m in (doc or {}).get("matches", []) or [] if m.get("match_type") == "interclub"]
    matches = sorted(matches, key=_match_date_key, reverse=True)[:limit]
    rows = []
    for m in matches:
        rows.append({
            "Datum": m.get("match_date") or "",
            "Reeks": m.get("reeks_name") or m.get("competition_name") or "",
            "Ronde": m.get("round_text") or "",
            "Partner": m.get("partner_name") or "",
            "Tegen": " / ".join([x for x in [m.get("opp1_name"), m.get("opp2_name")] if x]) or "",
            "Tegenstander 1": m.get("opp1_name") or "",
            "Tegenstander 1 ID": m.get("opp1_user_id") or m.get("opp1_id") or "",
            "Tegenstander 2": m.get("opp2_name") or "",
            "Tegenstander 2 ID": m.get("opp2_user_id") or m.get("opp2_id") or "",
            "Score": m.get("score") or "",
            "W/V": _result_char(m),
        })
    return pd.DataFrame(rows)


def _collect_partner_analysis_from_selected_doc(sel_doc: dict, docs: dict, match_type_filter: str = "Alle") -> pd.DataFrame:
    """Partner analysis based on selected player's own match list, enriched with scraped partner stats.

    Counts stay consistent with the selected player's player page. If a partner is scraped,
    we add partner general winrate and delta "with selected player vs partner overall".
    """
    acc: dict[str, dict] = {}
    seen = set()

    for m in (sel_doc or {}).get("matches", []) or []:
        if match_type_filter != "Alle" and m.get("match_type") != match_type_filter:
            continue

        partner_name = str(m.get("partner_name") or "").strip()
        partner_pid = str(m.get("partner_user_id") or "").strip()
        if not partner_name and not partner_pid:
            continue

        key = _dedupe_match_key(m)
        if key in seen:
            continue
        seen.add(key)

        partner_group = _partner_key(m)
        bucket = acc.setdefault(partner_group, {
            "Partner": partner_name or partner_pid or "Onbekende partner",
            "Partner ID": partner_pid,
            "Matches": 0,
            "W": 0,
            "V": 0,
            "Onbekend": 0,
            "rank_values": [],
            "strong_matches": 0,
            "strong_wins": 0,
            "best_win_rank": None,
            "last_dates": [],
            "last10": [],
            "interclub": 0,
            "tornooi": 0,
        })

        bucket["Matches"] += 1
        if m.get("match_type") == "interclub":
            bucket["interclub"] += 1
        elif m.get("match_type") == "tornooi":
            bucket["tornooi"] += 1

        if m.get("won") is True:
            bucket["W"] += 1
            won = True
        elif m.get("won") is False:
            bucket["V"] += 1
            won = False
        else:
            bucket["Onbekend"] += 1
            won = None

        ranks = [_parse_rank(m.get("opp1_ranking")), _parse_rank(m.get("opp2_ranking"))]
        ranks = [r for r in ranks if r is not None]
        if ranks:
            avg_match_rank = sum(ranks) / len(ranks)
            bucket["rank_values"].append(avg_match_rank)
            if avg_match_rank <= 200:
                bucket["strong_matches"] += 1
                if won is True:
                    bucket["strong_wins"] += 1
            if won is True:
                if bucket["best_win_rank"] is None or avg_match_rank < bucket["best_win_rank"]:
                    bucket["best_win_rank"] = avg_match_rank

        date_key = _match_date_key(m)
        if date_key:
            bucket["last_dates"].append(date_key)
        if won is True:
            bucket["last10"].append((date_key, "W"))
        elif won is False:
            bucket["last10"].append((date_key, "V"))

    rows = []
    for data in acc.values():
        wins = data["W"]
        losses = data["V"]
        known = wins + losses
        matches = data["Matches"]
        with_me_wr = _winrate_num(wins, losses)
        avg_rank = sum(data["rank_values"]) / len(data["rank_values"]) if data["rank_values"] else None

        partner_wr, partner_total, partner_w, partner_v = _partner_general_wr(data.get("Partner ID") or "", docs)
        delta = None
        if with_me_wr is not None and partner_wr is not None:
            delta = with_me_wr - partner_wr

        if data["last10"]:
            recent = sorted(data["last10"], key=lambda x: x[0] or "", reverse=True)[:10]
            last10 = "".join(x[1] for x in recent)
        else:
            last10 = "-"

        strong = "-"
        if data["strong_matches"]:
            strong = f"{data['strong_wins']}/{data['strong_matches']}"

        reliability = "Laag"
        if matches >= 10:
            reliability = "Hoog"
        elif matches >= 4:
            reliability = "Middel"

        rows.append({
            "Partner": data["Partner"],
            "Matches": matches,
            "W": wins,
            "V": losses,
            "Winrate met mij": _pct(with_me_wr),
            "Partner algemeen": _pct(partner_wr),
            "Partner matchen": partner_total if partner_total else "-",
            "Delta": _pct(delta) if delta is not None else "-",
            "Gem. tegenstand": _format_rank(avg_rank),
            "Sterkste winst": _format_rank(data["best_win_rank"]),
            "W tegen P<=200": strong,
            "Laatste 10": last10,
            "Laatste match": max(data["last_dates"]) if data["last_dates"] else "-",
            "Betrouwbaarheid": reliability,
        })

    if not rows:
        return pd.DataFrame()

    # Sort primarily on sufficient sample size and positive delta, but keep readable.
    df = pd.DataFrame(rows)
    df["_matches_sort"] = df["Matches"]
    df["_delta_sort"] = df["Delta"].apply(lambda x: float(str(x).replace("%", "")) if str(x).endswith("%") else -999)
    df = df.sort_values(["_matches_sort", "_delta_sort"], ascending=[False, False])
    return df.drop(columns=["_matches_sort", "_delta_sort"])


# -----------------------------------------------------------------------------
# Public render function used by dashboard.py
# -----------------------------------------------------------------------------

def render_lineup_quick_results(
    sel_player_id: str,
    sel_label: str,
    profiles: list,
    name_lookup_global: dict,
    display_name_fn,
):
    """Render useful analysis, consistently based on selected player's data but enriched with partner profile stats."""
    st.markdown("### ⚡ Snelle analyse op basis van huidige data")
    st.caption(
        "Partneranalyse telt matchen uit de matchlijst van de geselecteerde speler. "
        "Als de partner ook gescraped is, tonen we daarnaast zijn/haar algemene winrate en de delta."
    )

    all_ids = [str(p.get("player_id")) for p in profiles if p.get("player_id")]
    docs = ll.get_docs_for_players(all_ids)

    sel_player_id = str(sel_player_id)
    sel_doc = docs.get(sel_player_id) or fb.get_player(sel_player_id) or {}

    scraped_options = []
    for p in sorted(profiles, key=lambda x: x.get("display_name") or ""):
        pid = str(p.get("player_id") or "")
        if not pid:
            continue
        doc = docs.get(pid) or {}
        stats = doc.get("stats", {}) or {}
        total = _safe_int(stats.get("total_matches"), len(doc.get("matches", []) or []))
        if total > 0 or len(doc.get("matches", []) or []) > 0:
            scraped_options.append(display_name_fn(p))

    if not scraped_options:
        st.info("Er zijn nog geen gescrapete spelers met matchdata beschikbaar.")
        st.divider()
        return

    label_to_id = {display_name_fn(p): str(p.get("player_id")) for p in profiles if p.get("player_id")}
    default_labels = []
    if sel_label in scraped_options:
        default_labels.append(sel_label)
    default_labels += [lbl for lbl in scraped_options if lbl != sel_label][:7]

    selected_labels = st.multiselect(
        "Beschikbare spelers meenemen in overzicht",
        scraped_options,
        default=default_labels,
        key=f"quick_lineup_players_{sel_player_id}",
    )
    selected_ids = [label_to_id[lbl] for lbl in selected_labels if lbl in label_to_id]

    if len(selected_ids) < 1:
        st.info("Selecteer minstens 1 gescrapete speler.")
        st.divider()
        return

    overview_df = _available_players_df(docs, selected_ids, name_lookup_global)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Beschikbare spelersdata**")
        if overview_df.empty:
            st.info("Geen spelers met matchdata in deze selectie.")
        else:
            st.dataframe(
                overview_df,
                **_dataframe_kwargs(
                    hide_index=True,
                    height=min(360, 40 + len(overview_df) * 36),
                    column_config={
                        "Speler": st.column_config.TextColumn("Speler", width="large"),
                        "Winrate": st.column_config.TextColumn("Winrate", width="small"),
                    },
                ),
            )

    with c2:
        st.markdown(f"**Recente interclub van {sel_label}**")
        recent_df = _recent_interclub_df(sel_doc, limit=10)
        if recent_df.empty:
            st.info("Geen recente interclubmatches gevonden voor deze speler.")
        else:
            # PADEL_ANALYSIS_INLINE_RECENT_INTERCLUB_ACTIONS
            pia.render_dataframe_with_player_actions(
                recent_df,
                player_columns=["Partner", "Tegenstander 1", "Tegenstander 2"],
                profiles=None,
                key_prefix=f"recent_interclub_actions_{sel_player_id}",
                height_limit=20,
            )
            st.caption("Klassieke tabelweergave hieronder blijft beschikbaar voor overzicht.")
            st.dataframe(
                recent_df,
                **_dataframe_kwargs(
                    hide_index=True,
                    height=min(400, 40 + len(recent_df) * 38),
                    column_config={
                        "Reeks": st.column_config.TextColumn("Reeks", width="medium"),
                        "Partner": st.column_config.TextColumn("Partner", width="medium"),
                        "Tegen": st.column_config.TextColumn("Tegen", width="large"),
                        "Score": st.column_config.TextColumn("Score", width="large"),
                        "W/V": st.column_config.TextColumn("W/V", width="small"),
                    },
                ),
            )

    st.markdown(f"**Partneranalyse voor {sel_label}**")
    with st.expander("Uitleg partneranalyse", expanded=False):
        st.write(
            "Matches/W/V/Winrate met mij komen uitsluitend uit de matchlijst van de geselecteerde speler. "
            "Partner algemeen komt uit het profiel van de partner, als die partner gescraped is. "
            "Delta = winrate met mij minus partner algemene winrate. Positieve delta betekent dat het duo beter presteert dan de algemene partnerbaseline. "
            "Gebruik delta alleen met voldoende matchen; de kolom Betrouwbaarheid helpt daarbij."
        )

    match_type_choice = st.radio(
        "Wedstrijdtype partneranalyse",
        ["Alle", "interclub", "tornooi"],
        horizontal=True,
        format_func=lambda x: "Alle" if x == "Alle" else _match_type_label(x),
        key=f"quick_partner_type_{sel_player_id}",
    )

    partner_df = _collect_partner_analysis_from_selected_doc(sel_doc, docs, match_type_filter=match_type_choice)

    if partner_df.empty:
        st.info("Geen partnerhistoriek gevonden voor deze speler binnen de huidige data.")
    else:
        # PADEL_ANALYSIS_INLINE_PARTNER_ANALYSIS_ACTIONS
        pia.render_dataframe_with_player_actions(
            partner_df,
            player_columns=["Partner"],
            profiles=None,
            key_prefix=f"partner_analysis_actions_{sel_player_id}",
            height_limit=40,
        )
        st.caption("Klassieke tabelweergave hieronder blijft beschikbaar voor sortering/overzicht.")
        st.dataframe(
            partner_df,
            **_dataframe_kwargs(
                hide_index=True,
                height=min(560, 40 + len(partner_df) * 38),
                column_config={
                    "Partner": st.column_config.TextColumn("Partner", width="large"),
                    "Winrate met mij": st.column_config.TextColumn("Winrate met mij", width="small"),
                    "Partner algemeen": st.column_config.TextColumn("Partner algemeen", width="small"),
                    "Delta": st.column_config.TextColumn("Delta", width="small"),
                    "Gem. tegenstand": st.column_config.TextColumn("Gem. tegenstand", width="small"),
                    "Sterkste winst": st.column_config.TextColumn("Sterkste winst", width="small"),
                    "W tegen P<=200": st.column_config.TextColumn("W tegen P<=200", width="small"),
                    "Laatste 10": st.column_config.TextColumn("Laatste 10", width="small"),
                    "Betrouwbaarheid": st.column_config.TextColumn("Betrouwbaarheid", width="small"),
                },
            ),
        )

    st.divider()
