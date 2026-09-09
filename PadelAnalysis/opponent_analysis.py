"""Unified opponent team analysis, version 2."""
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
except Exception:
    taa = None

REPORTS_COLLECTION = "team_scouting_reports"
REPORT_VERSION = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_ts(value) -> str:
    if not value:
        return "onbekend"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


def _parse_simple_date(text) -> Optional[tuple]:
    if not text:
        return None
    text = str(text).strip()
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return tuple(map(int, match.groups()))
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if match:
        day, month, year = map(int, match.groups())
        return year, month, day
    return None


def _build_report(bundle: dict, opp: dict, all_docs: dict,
                  current_reeks_url: Optional[str], current_spelgroep_id: Optional[str] = None,
                  global_docs: Optional[dict] = None) -> dict:
    players = [
        od.build_player_summary(
            player["user_id"], player["name"], all_docs,
            current_reeks_url=current_reeks_url,
            current_spelgroep_id=current_spelgroep_id,
            global_docs=global_docs,
        )
        for player in (bundle.get("unique_players", []) or [])
    ]
    return {
        "report_version": REPORT_VERSION,
        "opponent_name": opp.get("name"), "opponent_ploeg_id": opp.get("ploeg_id"),
        "reeks_url": current_reeks_url, "spelgroep_id": current_spelgroep_id,
        "updated_at": _now_iso(), "players": players,
    }


def _save_report(report: dict) -> None:
    try:
        doc_id = str(report.get("opponent_ploeg_id") or "onbekend")
        fb.db.collection(REPORTS_COLLECTION).document(doc_id).set(fb.sanitize_for_firestore(report))
    except Exception:
        pass


def _load_report(ploeg_id: str) -> Optional[dict]:
    try:
        doc = fb.db.collection(REPORTS_COLLECTION).document(str(ploeg_id)).get()
        return doc.to_dict() if doc.exists else None
    except Exception:
        return None


def _needs_rebuild(report: Optional[dict], bundle: dict,
                   current_spelgroep_id: Optional[str] = None,
                   current_reeks_url: Optional[str] = None) -> bool:
    if not report or report.get("report_version") != REPORT_VERSION:
        return True
    if str(report.get("spelgroep_id") or "") != str(current_spelgroep_id or ""):
        return True
    if str(report.get("reeks_url") or "") != str(current_reeks_url or ""):
        return True
    known = {str(p.get("player_id")) for p in report.get("players", []) or []}
    current = {str(p["user_id"]) for p in bundle.get("unique_players", []) or []}
    return known != current


def _overview_row(summary: dict) -> dict:
    current, best = summary.get("current_rank"), summary.get("best_rank")
    partners = summary.get("partners") or []
    top_partner = "-"
    if partners:
        partner = partners[0]
        top_partner = f"{partner['Partner']} ({partner['Matches']}x, {partner['Winrate']})"
    return {
        "Naam": summary.get("name"),
        "Huidig": f"P{current}" if current is not None else "?",
        "Beste ooit": f"P{best}" if best is not None else "?",
        "Toppartner in deze poule": top_partner,
        "Matches in deze poule": summary.get("matches_relevant", 0),
        "Winst": summary.get("wins_relevant", 0),
        "Verlies": summary.get("losses_relevant", 0),
        "Winrate": summary.get("winrate_relevant", "-"),
    }


def _get_own_profiles() -> list[dict]:
    try:
        return [doc.to_dict() for doc in fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()]
    except Exception:
        return []


def _infer_recent_own_lineup(home_player_id: Optional[str]) -> dict[int, list[str]]:
    if not home_player_id:
        return {}
    try:
        import lineup_lab as ll
        profiles = _get_own_profiles()
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs = ll.get_docs_for_players(list(profile_ids))
        index = ll.build_encounter_index(docs)
        encounters = ll.list_encounters(index)
        own_keys = [key for key, _ in encounters if any(str(pid) == str(home_player_id) for pid, _ in index[key])]
        if not own_keys:
            return {}

        def encounter_date(key):
            dates = [_parse_simple_date(entry.get("match_date")) for _, entry in index[key]]
            return max((date for date in dates if date), default=(0, 0, 0))

        key = max(own_keys, key=encounter_date)
        boards = ll.reconstruct_boards(index[key]) or []
        lookup = {str(p.get("player_id")): p.get("display_name") or str(p.get("player_id")) for p in profiles}
        prefill = {}
        for number, board in enumerate(sorted(boards, key=lambda b: str(b.get("round_text") or "")), 1):
            pair = [lookup.get(str(pid), str(pid)) for pid in (board.get("pair") or [])]
            if pair:
                prefill[number] = pair[:2]
        return prefill
    except Exception:
        return {}


def _render_own_lineup_editor(home_player_id: Optional[str], key_prefix: str, ploeg_id: str) -> str:
    st.markdown("#### 🧩 Onze opstelling")
    st.caption("Voorstel gebaseerd op onze meest recente gekende interclubontmoeting. Vul ontbrekende dubbels zelf aan.")
    profiles = _get_own_profiles()
    if not profiles:
        st.info("Nog geen eigen spelers gekend. Voeg spelers toe via 'Speler toevoegen'.")
        return ""
    labels = sorted({p.get("display_name") or p.get("player_id") or "?" for p in profiles})
    options = [""] + labels
    prefill_key = f"{key_prefix}_lineup_prefill_v2_{ploeg_id}"
    if prefill_key not in st.session_state:
        st.session_state[prefill_key] = _infer_recent_own_lineup(home_player_id)
    prefill = st.session_state[prefill_key]
    number = st.number_input("Aantal dubbels in deze ontmoeting", min_value=1, max_value=8,
                             value=max(2, len(prefill)), step=1,
                             key=f"{key_prefix}_ndoubles_v2_{ploeg_id}")
    lines = []
    for index in range(1, int(number) + 1):
        default = prefill.get(index, ["", ""])
        while len(default) < 2:
            default.append("")
        left, right = st.columns(2)
        with left:
            a = st.selectbox(f"Dubbel {index} - speler A", options,
                             index=options.index(default[0]) if default[0] in options else 0,
                             key=f"{key_prefix}_double_{index}_a_v2_{ploeg_id}")
        with right:
            b = st.selectbox(f"Dubbel {index} - speler B", options,
                             index=options.index(default[1]) if default[1] in options else 0,
                             key=f"{key_prefix}_double_{index}_b_v2_{ploeg_id}")
        if a or b:
            lines.append(f"Dubbel {index}: {a or '?'} / {b or '?'}")
    return "\n".join(lines)


def _render_ai_section(report: dict, own_team_context: str, ploeg_id: str, key_prefix: str) -> None:
    st.markdown("#### 🤖 AI-inzichten")
    if taa is None:
        st.caption("AI-module niet beschikbaar.")
        return
    answer_key = f"{key_prefix}_answer_v2_{ploeg_id}"
    left, right = st.columns(2)
    with left:
        insights = st.button("💡 Genereer inzichten", key=f"{key_prefix}_insights_v2_{ploeg_id}", type="primary", use_container_width=True)
    with right:
        lineup = st.button("🧩 Stel onze opstelling voor", key=f"{key_prefix}_lineup_ai_v2_{ploeg_id}", use_container_width=True)
    if insights:
        try:
            st.session_state[answer_key] = taa.generate_insights(report)
        except Exception as exc:
            st.session_state[answer_key] = f"⚠️ Mislukt: {exc}"
    if lineup:
        try:
            st.session_state[answer_key] = taa.suggest_lineup(report, own_team_context=own_team_context or None)
        except Exception as exc:
            st.session_state[answer_key] = f"⚠️ Mislukt: {exc}"
    question = st.text_area("Jouw vraag", key=f"{key_prefix}_question_v2_{ploeg_id}", height=70,
                            placeholder="Bv. Wie is hun sterkste dubbel?")
    if st.button("💬 Vraag AI", key=f"{key_prefix}_ask_v2_{ploeg_id}"):
        if question.strip():
            try:
                st.session_state[answer_key] = taa.ask_about_team(question.strip(), report)
            except Exception as exc:
                st.session_state[answer_key] = f"⚠️ AI-vraag mislukt: {exc}"
        else:
            st.warning("Typ eerst een vraag.")
    if st.session_state.get(answer_key):
        st.markdown(st.session_state[answer_key])


def render_team_analysis(bundle: dict, opp: dict, all_docs: dict,
                         current_reeks_url: Optional[str] = None,
                         current_spelgroep_id: Optional[str] = None,
                         home_player_id: Optional[str] = None,
                         global_docs: Optional[dict] = None,
                         go_to_player_fn: Optional[Callable[[str], None]] = None,
                         key_prefix: str = "team_analysis") -> dict:
    ploeg_id = opp.get("ploeg_id")
    state_key = f"{key_prefix}_report_v2_{ploeg_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = _load_report(ploeg_id)
    report = st.session_state[state_key]
    if _needs_rebuild(report, bundle, current_spelgroep_id, current_reeks_url):
        report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
        _save_report(report)
        st.session_state[state_key] = report

    header, refresh = st.columns([4, 1])
    with header:
        st.markdown(f"### 📋 Analyse: {opp.get('name', '?')}")
        st.caption(f"Versie 2 · laatst berekend: {_format_ts(report.get('updated_at'))}")
    with refresh:
        if st.button("🔄 Verversen", key=f"{key_prefix}_refresh_v2_{ploeg_id}", use_container_width=True):
            report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
            _save_report(report)
            st.session_state[state_key] = report
            st.rerun()

    players = report.get("players", []) or []
    if not players:
        st.info("Nog geen spelersdata beschikbaar voor deze tegenploeg.")
        return report

    st.markdown("#### 📊 Overzicht")
    st.dataframe(pd.DataFrame([_overview_row(player) for player in players]),
                 use_container_width=True, hide_index=True,
                 height=min(360, 40 + 36 * len(players)))
    missing_pool_data = sum(1 for player in players if not player.get("poule_results_exact"))
    if missing_pool_data:
        st.warning(f"Voor {missing_pool_data} speler(s) konden geen matchrecords met zekerheid aan deze poule worden gekoppeld. Andere poules worden niet als fallback getoond.")

    st.markdown("#### 🔎 Detail per speler")
    names = [player.get("name", "?") for player in players]
    selected_name = st.selectbox("Bekijk details van:", names, key=f"{key_prefix}_detail_v2_{ploeg_id}")
    selected = next((player for player in players if player.get("name") == selected_name), None)
    if selected:
        od.render_player_summary_inline(selected)
        if go_to_player_fn and st.button("👁️ Volledige spelerpagina", key=f"{key_prefix}_jump_v2_{selected.get('player_id')}"):
            go_to_player_fn(selected.get("player_id"))

    st.divider()
    own_context = _render_own_lineup_editor(home_player_id, key_prefix, ploeg_id)
    st.divider()
    _render_ai_section(report, own_context, ploeg_id, key_prefix)
    return report
