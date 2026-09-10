"""
opponent_analysis.py - samengevat analysescherm voor de volledige tegenploeg (v4).

Ongewijzigd t.o.v. v3, behalve dat dit bestand nu samenhoort met de
klassement-richtingfix in opponent_dossier.py (hoger getal = beter). Dit
bestand doet zelf geen rank-vergelijkingen, het toont enkel wat
build_player_summary() teruggeeft.

PADEL_ANALYSIS_TWO_LAYER_2026-09-10
De overzichtstabel toont per speler ZOWEL de huidige poule als de historiek
uit vorige periodes, in aparte kolommen.

Verder in deze versie:
- "board" hernoemd naar "dubbel";
- bordpositie-heuristiek volledig verwijderd;
- de opstelling-editor toont altijd minstens 2 dubbels.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd
import streamlit as st

import firebase_service as fb
import opponent_dossier as od

try:
    import team_ai_advisor as taa
except Exception:  # pragma: no cover - AI-veld is optioneel, rest blijft werken
    taa = None

REPORTS_COLLECTION = "team_scouting_reports"
REPORT_SCHEMA_VERSION = 4  # v4-datamodel; verhoogd om oude rapporten te forceren


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_ts(value) -> str:
    if not value:
        return "onbekend"
    try:
        cleaned = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


def _parse_simple_date(text) -> Optional[tuple]:
    if not text:
        return None
    text = str(text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    return None


# ─────────────────────────────────────────────
# Rapport opbouwen / bewaren / laden
# ─────────────────────────────────────────────
def _build_report(
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str],
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
) -> dict:
    players = []
    for player in bundle.get("unique_players", []) or []:
        players.append(od.build_player_summary(
            player["user_id"], player["name"], all_docs,
            current_reeks_url=current_reeks_url,
            current_spelgroep_id=current_spelgroep_id,
            global_docs=global_docs,
        ))
    return {
        "opponent_name": opp.get("name"),
        "opponent_ploeg_id": opp.get("ploeg_id"),
        "reeks_url": current_reeks_url,
        "spelgroep_id": current_spelgroep_id,
        "updated_at": _now_iso(),
        "schema_version": REPORT_SCHEMA_VERSION,
        "players": players,
    }


def _save_report(report: dict) -> None:
    doc_id = str(report.get("opponent_ploeg_id") or "onbekend")
    try:
        fb.db.collection(REPORTS_COLLECTION).document(doc_id).set(
            fb.sanitize_for_firestore(report)
        )
    except Exception:
        pass  # Bewaren is comfort, geen blokkerende vereiste voor de UI.


def _load_report(ploeg_id: str) -> Optional[dict]:
    try:
        doc = fb.db.collection(REPORTS_COLLECTION).document(str(ploeg_id)).get()
        return doc.to_dict() if doc.exists else None
    except Exception:
        return None


def _needs_rebuild(
    report: Optional[dict],
    bundle: dict,
    current_spelgroep_id: Optional[str] = None,
) -> bool:
    if not report:
        return True
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        return True
    if str(report.get("spelgroep_id") or "") != str(current_spelgroep_id or ""):
        return True
    known_ids = {str(p.get("player_id")) for p in report.get("players", []) or []}
    bundle_ids = {str(p["user_id"]) for p in bundle.get("unique_players", []) or []}
    return not bundle_ids.issubset(known_ids)


# ─────────────────────────────────────────────
# Overzichtstabel (twee lagen naast elkaar)
# ─────────────────────────────────────────────
def _overview_row(summary: dict) -> dict:
    current = summary.get("current_rank")
    best = summary.get("best_rank")

    best_text = f"P{best}" if best is not None else "?"
    best_when = summary.get("best_rank_when")
    if best_when and best is not None:
        best_text += f" ({best_when})"

    partners_now = summary.get("partners") or []
    partner_now = partners_now[0]["Partner"] if partners_now else "-"

    partners_hist = summary.get("partners_history") or []
    partner_hist = "-"
    if partners_hist:
        row = partners_hist[0]
        partner_hist = f"{row['Partner']} ({row['Matches']}x)"

    return {
        "Naam": summary.get("name"),
        "Huidig": f"P{current}" if current is not None else "?",
        "Beste ooit": best_text,
        "Matchen deze poule": summary.get("matches_relevant", 0),
        "Winrate deze poule": summary.get("winrate_relevant", "-"),
        "Partner deze poule": partner_now,
        "Matchen historiek": summary.get("matches_history", 0),
        "Winrate historiek": summary.get("winrate_history", "-"),
        "Vaste partner historiek": partner_hist,
        "Vorm": summary.get("form_history", "-"),
    }


# ─────────────────────────────────────────────
# Eigen opstelling - editor
# ─────────────────────────────────────────────
def _get_own_profiles() -> list[dict]:
    try:
        return [d.to_dict() for d in fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()]
    except Exception:
        return []


def _infer_recent_own_lineup(home_player_id: Optional[str]) -> dict[int, list[str]]:
    """Best-effort reconstructie van onze meest recente interclubopstelling als
    prefill. Faalt dit, dan blijft de editor gewoon volledig manueel bruikbaar -
    er wordt nooit gecrasht op deze stap."""
    if not home_player_id:
        return {}
    try:
        import lineup_lab as ll
        profiles = _get_own_profiles()
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs = ll.get_docs_for_players(list(profile_ids))
        index = ll.build_encounter_index(docs)
        all_encounters = ll.list_encounters(index)
        own_keys = [
            key for key, _ in all_encounters
            if any(str(pid) == str(home_player_id) for pid, _ in index[key])
        ]
        if not own_keys:
            return {}

        def _encounter_date(key):
            dates = []
            for _, entry in index[key]:
                parsed = _parse_simple_date(entry.get("match_date"))
                if parsed:
                    dates.append(parsed)
            return max(dates) if dates else (0, 0, 0)

        most_recent = max(own_keys, key=_encounter_date)
        doubles = ll.reconstruct_boards(index[most_recent]) or []
        name_lookup = {
            str(p.get("player_id")): (p.get("display_name") or str(p.get("player_id")))
            for p in profiles
        }
        prefill: dict[int, list[str]] = {}
        for i, double in enumerate(sorted(doubles, key=lambda b: str(b.get("round_text") or "")), start=1):
            pair = [name_lookup.get(str(pid), str(pid)) for pid in (double.get("pair") or [])]
            if pair:
                prefill[i] = pair[:2]
        return prefill
    except Exception:
        return {}


def _render_own_lineup_editor(home_player_id: Optional[str], key_prefix: str, ploeg_id: str) -> str:
    """Editor voor onze eigen opstelling; geeft een platte tekstbeschrijving
    terug die als context naar het AI-opstellingsadvies gaat."""
    st.markdown("#### 🧩 Onze opstelling")
    st.caption(
        "Voorgesteld op basis van onze meest recente gekende interclubontmoeting. "
        "Vul aan of pas aan naar wie effectief beschikbaar is."
    )
    profiles = _get_own_profiles()
    if not profiles:
        st.info("Nog geen eigen spelers gekend. Voeg spelers toe via '➕ Speler toevoegen'.")
        return ""

    labels = sorted({(p.get("display_name") or p.get("player_id") or "?") for p in profiles})
    options = [""] + labels

    prefill_key = f"{key_prefix}_lineup_prefill_v4_{ploeg_id}"
    if prefill_key not in st.session_state:
        st.session_state[prefill_key] = _infer_recent_own_lineup(home_player_id)
    prefill = st.session_state[prefill_key]

    if prefill and len(prefill) < 2:
        st.caption(
            "Slechts één dubbel kon gereconstrueerd worden uit de laatste ontmoeting. "
            "Vul de overige zelf aan."
        )

    n_doubles = st.number_input(
        "Aantal dubbels in deze ontmoeting",
        min_value=1, max_value=8, value=max(2, len(prefill)), step=1,
        key=f"{key_prefix}_ndoubles_v4_{ploeg_id}",
    )

    lines = []
    for i in range(1, int(n_doubles) + 1):
        pair = list(prefill.get(i, []))
        while len(pair) < 2:
            pair.append("")
        c1, c2 = st.columns(2)
        with c1:
            a = st.selectbox(
                f"Dubbel {i} - speler A", options,
                index=options.index(pair[0]) if pair[0] in options else 0,
                key=f"{key_prefix}_double_{i}_a_v4_{ploeg_id}",
            )
        with c2:
            b = st.selectbox(
                f"Dubbel {i} - speler B", options,
                index=options.index(pair[1]) if pair[1] in options else 0,
                key=f"{key_prefix}_double_{i}_b_v4_{ploeg_id}",
            )
        if a or b:
            lines.append(f"Dubbel {i}: {a or '?'} / {b or '?'}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# AI-sectie
# ─────────────────────────────────────────────
def _render_ai_section(report: dict, own_team_context: str, ploeg_id: str, key_prefix: str) -> None:
    st.markdown("#### 🤖 AI-inzichten")
    if taa is None:
        st.caption("AI-module niet beschikbaar (team_ai_advisor kon niet geladen worden).")
        return

    answer_key = f"{key_prefix}_answer_v4_{ploeg_id}"
    b1, b2 = st.columns(2)
    with b1:
        insights_clicked = st.button(
            "💡 Genereer inzichten", key=f"{key_prefix}_insights_v4_{ploeg_id}",
            type="primary", use_container_width=True,
        )
    with b2:
        lineup_clicked = st.button(
            "🧩 Stel onze opstelling voor", key=f"{key_prefix}_lineup_ai_v4_{ploeg_id}",
            use_container_width=True,
        )

    if insights_clicked:
        with st.spinner("AI analyseert de tegenploeg..."):
            try:
                st.session_state[answer_key] = taa.generate_insights(report)
            except Exception as exc:
                st.session_state[answer_key] = f"⚠️ Mislukt: {exc}"

    if lineup_clicked:
        with st.spinner("Opstellingsvoorstel opstellen..."):
            try:
                st.session_state[answer_key] = taa.suggest_lineup(
                    report, own_team_context=own_team_context or None
                )
            except Exception as exc:
                st.session_state[answer_key] = f"⚠️ Mislukt: {exc}"

    st.caption("Of stel een eigen vraag:")
    question = st.text_area(
        "Jouw vraag", key=f"{key_prefix}_question_v4_{ploeg_id}", height=70,
        label_visibility="collapsed", placeholder="Bv. Wie is hun sterkste dubbel?",
    )
    if st.button("💬 Vraag AI", key=f"{key_prefix}_ask_v4_{ploeg_id}"):
        if not question.strip():
            st.warning("Typ eerst een vraag.")
        else:
            with st.spinner("AI denkt na..."):
                try:
                    st.session_state[answer_key] = taa.ask_about_team(question.strip(), report)
                except Exception as exc:
                    st.session_state[answer_key] = f"⚠️ AI-vraag mislukt: {exc}"

    if st.session_state.get(answer_key):
        st.markdown("##### Antwoord")
        st.markdown(st.session_state[answer_key])


# ─────────────────────────────────────────────
# Hoofdfunctie
# ─────────────────────────────────────────────
def render_team_analysis(
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    home_player_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    key_prefix: str = "team_analysis",
) -> dict:
    """Toont het volledige teamanalysescherm en geeft het gebruikte rapport terug."""
    ploeg_id = opp.get("ploeg_id")
    state_key = f"{key_prefix}_report_v4_{ploeg_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = _load_report(ploeg_id)
    report = st.session_state[state_key]

    if _needs_rebuild(report, bundle, current_spelgroep_id):
        report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
        _save_report(report)
        st.session_state[state_key] = report

    header_col, refresh_col = st.columns([4, 1])
    with header_col:
        st.markdown(f"### 📋 Analyse: {opp.get('name', '?')}")
        st.caption(
            f"Poule {current_spelgroep_id or 'onbekend'} · "
            f"laatst berekend op {_format_ts(report.get('updated_at'))}"
        )
    with refresh_col:
        if st.button("🔄 Verversen", key=f"{key_prefix}_refresh_v4_{ploeg_id}", use_container_width=True):
            report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
            _save_report(report)
            st.session_state[state_key] = report
            st.rerun()

    players = report.get("players", []) or []
    if not players:
        st.info("Nog geen spelersdata beschikbaar voor deze tegenploeg.")
        return report

    st.markdown("#### 📊 Overzicht")
    overview_df = pd.DataFrame([_overview_row(p) for p in players])
    st.dataframe(
        overview_df, use_container_width=True, hide_index=True,
        height=min(400, 40 + 36 * len(overview_df)),
    )

    played_now = sum(p.get("matches_relevant", 0) for p in players)
    total_history = sum(p.get("matches_history", 0) for p in players)
    if played_now == 0 and total_history:
        st.info(
            f"Deze ploeg heeft in de huidige poule nog geen gespeelde matchen in onze data. "
            f"De kolommen 'historiek' tonen {total_history} matchen uit vorige periodes - "
            "bruikbaar als niveau-inschatting, niet als stand in deze poule."
        )
    else:
        st.caption(
            "Kolommen 'deze poule' zijn strikt gefilterd op spelgroep-ID. "
            "Kolommen 'historiek' komen uit vorige periodes en andere poules."
        )

    st.markdown("#### 🔎 Detail per speler")
    names = [p.get("name", "?") for p in players]
    sel_name = st.selectbox("Bekijk details van:", names, key=f"{key_prefix}_detail_v4_{ploeg_id}")
    selected = next((p for p in players if p.get("name") == sel_name), None)
    if selected:
        od.render_player_summary_inline(selected)
        if go_to_player_fn and st.button(
            "👁️ Volledige spelerpagina",
            key=f"{key_prefix}_jump_v4_{selected.get('player_id')}",
        ):
            go_to_player_fn(selected.get("player_id"))

    st.divider()
    own_team_context = _render_own_lineup_editor(home_player_id, key_prefix, ploeg_id)
    st.divider()
    _render_ai_section(report, own_team_context, ploeg_id, key_prefix)
    return report
