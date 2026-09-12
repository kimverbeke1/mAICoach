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


# PADEL_ANALYSIS_DATE_PARSE_FIX
# Zelfde robuuste datum-parser als in dashboard.py (elk bestand houdt zijn
# eigen kleine kopie, geen extra gedeelde module nodig voor deze ene
# helper-functie). Nodig omdat een platte string-sort op "match_date"
# datums door elkaar zet zodra het formaat niet toevallig ISO is (bv.
# dd/mm/jjjj: "01/12/2026" komt string-alfabetisch VOOR "15/01/2026",
# terwijl december net de meest recente maand is).
_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def _parse_match_date(text) -> Optional[tuple]:
    if not text:
        return None
    text = str(text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (y, mo, d)
    m = re.search(r"(\d{1,2})\s+([a-zA-Zàéè]+)\s+(\d{4})", text.lower())
    if m:
        mo = _DUTCH_MONTHS.get(m.group(2))
        if mo:
            return (int(m.group(3)), mo, int(m.group(1)))
    return None


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


def _dedupe_match_key(m: dict) -> str:
    """Dedupe only within the selected player's own document."""
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
            "Speler ID": pid,
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
    # PADEL_ANALYSIS_DATE_SORT_FIX: was een platte string-sort op de ruwe
    # datumtekst (_match_date_key), wat "datums door elkaar" gaf zodra het
    # formaat niet toevallig ISO was. Nu een echte datum-parse, recentste
    # bovenaan; niet-herkende datums (zeldzaam) belanden onderaan.
    matches = sorted(matches, key=lambda m: _parse_match_date(_match_date_key(m)) or (0, 0, 0), reverse=True)[:limit]
    rows = []
    for m in matches:
        rows.append({
            "Datum": m.get("match_date") or "",
            "Reeks": m.get("reeks_name") or m.get("competition_name") or "",
            "Ronde": m.get("round_text") or "",
            "Partner": m.get("partner_name") or "",
            "Partner ID": m.get("partner_user_id") or "",
            "Tegenstander 1": m.get("opp1_name") or "",
            "Tegenstander 1 ID": m.get("opp1_user_id") or m.get("opp1_id") or "",
            "Tegenstander 2": m.get("opp2_name") or "",
            "Tegenstander 2 ID": m.get("opp2_user_id") or m.get("opp2_id") or "",
            "Score": m.get("score") or "",
            "W/V": _result_char(m),
        })
    return pd.DataFrame(rows)


def _collect_partner_analysis_from_selected_doc(
    sel_doc: dict,
    docs: dict,
    profiles_lookup: Optional[dict] = None,
    match_type_filter: str = "Alle",
) -> pd.DataFrame:
    """
    Partner analysis based on selected player's own match list, enriched with
    scraped partner stats.

    PADEL_ANALYSIS_PARTNER_GROUPING_FIX (bug: "winrate met mij" toonde 0%
    ondanks effectieve winsten met die partner, bv. Anneleen Gallant):
    Vroeger werd er gegroepeerd op partner_user_id ALS die aanwezig was in
    het match-record, anders op de (genormaliseerde) naam. Niet elk
    match-record heeft echter consequent een partner_user_id ingevuld (bv.
    oudere scrapes, of matches toegevoegd via de tegenstander-scout-flow) --
    hierdoor konden dezelfde partner in TWEE aparte rijen terechtkomen
    ("id:12345" voor de ene match, "name:anneleen gallant" voor de andere),
    met elk hun eigen (onvolledige, soms toevallig 0%) winst/verlies-telling.

    Fix: we lossen EERST een canoniek player_id op via de globale profiel-
    lookup (dezelfde naam-matching als de rest van de app, incl. naam-
    varianten/volgorde), en groeperen daarop. Enkel als er geen profiel-match
    mogelijk is (partner nog nooit toegevoegd/gescraped) vallen we terug op
    een naam-sleutel -- in dat geval blijft correcte totaaltelling sowieso
    afhankelijk van consistente naamschrijfwijze in de brondata.
    """
    profiles_lookup = profiles_lookup or {}
    acc: dict[str, dict] = {}
    seen = set()
    for m in (sel_doc or {}).get("matches", []) or []:
        if match_type_filter != "Alle" and m.get("match_type") != match_type_filter:
            continue
        partner_name = str(m.get("partner_name") or "").strip()
        partner_pid_raw = str(m.get("partner_user_id") or "").strip()
        if not partner_name and not partner_pid_raw:
            continue
        key = _dedupe_match_key(m)
        if key in seen:
            continue
        seen.add(key)

        canonical_pid = pia.resolve_player_id(partner_name, profiles_lookup, partner_pid_raw) if profiles_lookup else partner_pid_raw
        partner_group = f"id:{canonical_pid}" if canonical_pid else f"name:{pia._norm(partner_name)}"

        bucket = acc.setdefault(partner_group, {
            "Partner": partner_name or canonical_pid or "Onbekende partner",
            "Partner ID": canonical_pid or partner_pid_raw,
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
        # Naam kan per match licht verschillen in schrijfwijze; bewaar de
        # langste/meest volledige variant als weergavenaam.
        if partner_name and len(partner_name) > len(bucket["Partner"] or ""):
            bucket["Partner"] = partner_name

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
        with_me_wr = _winrate_num(wins, losses)
        avg_rank = sum(data["rank_values"]) / len(data["rank_values"]) if data["rank_values"] else None
        partner_wr, partner_total, partner_w, partner_v = _partner_general_wr(data.get("Partner ID") or "", docs)
        delta = None
        if with_me_wr is not None and partner_wr is not None:
            delta = with_me_wr - partner_wr
        if data["last10"]:
            # PADEL_ANALYSIS_DATE_SORT_FIX: ook hier recentste-eerst via
            # echte datum-parse i.p.v. string-sort.
            recent = sorted(data["last10"], key=lambda x: _parse_match_date(x[0]) or (0, 0, 0), reverse=True)[:10]
            last10 = "".join(x[1] for x in recent)
        else:
            last10 = "-"
        strong = "-"
        if data["strong_matches"]:
            strong = f"{data['strong_wins']}/{data['strong_matches']}"
        matches = data["Matches"]
        reliability = "Laag"
        if matches >= 10:
            reliability = "Hoog"
        elif matches >= 4:
            reliability = "Middel"
        last_match_sorted = sorted(data["last_dates"], key=lambda d: _parse_match_date(d) or (0, 0, 0), reverse=True)
        rows.append({
            "Partner": data["Partner"],
            "Partner ID": data.get("Partner ID") or "",
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
            "Laatste match": last_match_sorted[0] if last_match_sorted else "-",
            "Betrouwbaarheid": reliability,
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["_matches_sort"] = df["Matches"]
    df["_delta_sort"] = df["Delta"].apply(lambda x: float(str(x).replace("%", "")) if str(x).endswith("%") else -999)
    df = df.sort_values(["_matches_sort", "_delta_sort"], ascending=[False, False])
    return df.drop(columns=["_matches_sort", "_delta_sort"])


# -----------------------------------------------------------------------------
# Selectable table + detail pattern (consistent met dashboard.py's Match Explorer)
# -----------------------------------------------------------------------------

def _render_selectable_table_with_detail(
    df: pd.DataFrame,
    id_columns: list[str],
    profiles_lookup: dict,
    key_prefix: str,
    height: int = 360,
    column_config: Optional[dict] = None,
):
    """Toont een volledig-breed, sorteerbare tabel (alle kolommen zichtbaar,
    ID-kolommen verborgen). Klik op een rij om onderaan de details te zien
    met klikbare speleracties (popover met scrape/refresh-status) — dezelfde
    UX als de bestaande Match Explorer-tab.
    """
    if df.empty:
        st.info("Geen data beschikbaar.")
        return
    visible_cols = [c for c in df.columns if not c.endswith(" ID")]
    display_df = df[visible_cols]
    event = st.dataframe(
        display_df,
        **_dataframe_kwargs(
            hide_index=True,
            height=min(height, 40 + len(display_df) * 36),
            column_config=column_config or {},
            on_select="rerun",
            selection_mode="single-row",
        ),
        key=f"{key_prefix}_table",
    )
    sel_rows = (event or {}).get("selection", {}).get("rows", [])
    if not sel_rows:
        st.caption("👉 Klik op een rij voor speleracties (scrape-status, snel doorklikken).")
        return
    idx = sel_rows[0]
    row = df.iloc[idx]
    st.markdown("**Details van geselecteerde rij:**")
    detail_cols = st.columns(min(len(id_columns), 3) or 1)
    for i, col_name in enumerate(id_columns):
        if col_name not in df.columns:
            continue
        with detail_cols[i % len(detail_cols)]:
            st.caption(col_name)
            id_col = f"{col_name} ID"
            explicit_id = row.get(id_col, "") if id_col in df.columns else ""
            pid = pia.resolve_player_id(row.get(col_name, ""), profiles_lookup, explicit_id)
            pia.render_player_name_action(row.get(col_name, ""), pid, key_prefix=f"{key_prefix}_detail_{idx}_{i}")


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
    profiles_lookup = pia.build_profile_lookup(profiles)

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

    # ── Sectie 1: Beschikbare spelersdata (volledig-breed) ──
    st.markdown("#### Beschikbare spelersdata")
    overview_df = _available_players_df(docs, selected_ids, name_lookup_global)
    if overview_df.empty:
        st.info("Geen spelers met matchdata in deze selectie.")
    else:
        _render_selectable_table_with_detail(
            overview_df,
            id_columns=["Speler"],
            profiles_lookup=profiles_lookup,
            key_prefix=f"overview_{sel_player_id}",
            height=320,
            column_config={
                "Speler": st.column_config.TextColumn("Speler", width="large"),
                "Winrate": st.column_config.TextColumn("Winrate", width="small"),
            },
        )

    st.divider()

    # ── Sectie 2: Recente interclub van geselecteerde speler (volledig-breed) ──
    st.markdown(f"#### Recente interclub van {sel_label}")
    recent_df = _recent_interclub_df(sel_doc, limit=10)
    if recent_df.empty:
        st.info("Geen recente interclubmatches gevonden voor deze speler.")
    else:
        _render_selectable_table_with_detail(
            recent_df,
            id_columns=["Partner", "Tegenstander 1", "Tegenstander 2"],
            profiles_lookup=profiles_lookup,
            key_prefix=f"recent_ic_{sel_player_id}",
            height=360,
            column_config={
                "Reeks": st.column_config.TextColumn("Reeks", width="medium"),
                "Partner": st.column_config.TextColumn("Partner", width="medium"),
                "Score": st.column_config.TextColumn("Score", width="small"),
                "W/V": st.column_config.TextColumn("W/V", width="small"),
            },
        )

    st.divider()

    # ── Sectie 3: Partneranalyse (volledig-breed) ──
    st.markdown(f"#### Partneranalyse voor {sel_label}")
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
    partner_df = _collect_partner_analysis_from_selected_doc(
        sel_doc, docs, profiles_lookup=profiles_lookup, match_type_filter=match_type_choice
    )
    if partner_df.empty:
        st.info("Geen partnerhistoriek gevonden voor deze speler binnen de huidige data.")
    else:
        _render_selectable_table_with_detail(
            partner_df,
            id_columns=["Partner"],
            profiles_lookup=profiles_lookup,
            key_prefix=f"partner_analysis_{sel_player_id}",
            height=420,
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
        )
    st.divider()
