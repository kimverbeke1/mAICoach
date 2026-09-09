"""
opponent_analysis.py - één samengevat analysescherm voor de volledige tegenploeg.

Doel (2026-09-09, v2), uitbreiding op opponent_scout_ui.render_scout_block:
- ÉÉN overzichtstabel met alle relevante data per speler (ranking, bordpositie,
  top-partner, matches/winrate binnen deze poule), in plaats van een lijst met
  per-speler-uitklappers die je stuk voor stuk moet openen.
- Optioneel, op aanvraag: volledig detail (rankingtijdlijn, alle partners,
  alle resultaten) voor ÉÉN gekozen speler via een dropdown.
- De analyse wordt bewaard in Firestore ('team_scouting_reports', 1 document
  per tegenploeg) en enkel herberekend als er nieuwe spelers bijkomen of van
  poule/reeks veranderd wordt.
- Een editor om de EIGEN ploegopstelling aan te duiden (board 1, board 2, ...),
  voorgesteld op basis van de meest recente eigen interclubmatch (best-effort,
  altijd aanpasbaar), gecombineerd met:
- Een AI-sectie: automatische inzichten, een vrij vraagveld, en een
  opstellingsvoorstel dat rekening houdt met de aangeduide eigen opstelling.

Gebruik (vanuit opponent_scout_ui.py):

    import opponent_analysis as oa
    oa.render_team_analysis(
        bundle, opp, all_docs,
        current_reeks_url=reeks_url,
        current_spelgroep_id=spelgroep_id,
        home_player_id=sel_player_id,
        global_docs=global_docs,
        go_to_player_fn=_go_to_player,
        key_prefix=f"scout_team_{sel_player_id}",
    )
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
REPORT_SCHEMA_VERSION = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_ts(value) -> str:
    if not value:
        return "onbekend"
    try:
        cleaned = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.strftime("%d/%m/%Y %H:%M")
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
        summary = od.build_player_summary(
            player["user_id"], player["name"], all_docs,
            current_reeks_url=current_reeks_url,
            current_spelgroep_id=current_spelgroep_id,
            global_docs=global_docs,
        )
        players.append(summary)
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


def _needs_rebuild(report: Optional[dict], bundle: dict, current_spelgroep_id: Optional[str] = None) -> bool:
    if not report:
        return True
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        return True
    if current_spelgroep_id and report.get("spelgroep_id") and str(report.get("spelgroep_id")) != str(current_spelgroep_id):
        return True
    known_ids = {p.get("player_id") for p in report.get("players", []) or []}
    bundle_ids = {p["user_id"] for p in bundle.get("unique_players", []) or []}
    return not bundle_ids.issubset(known_ids)


# ─────────────────────────────────────────────
# Overzichtstabel
# ─────────────────────────────────────────────
def _overview_row(summary: dict) -> dict:
    current = summary.get("current_rank")
    best = summary.get("best_rank")
    partners = summary.get("partners") or []
    top_partner = "-"
    if partners:
        p = partners[0]
        top_partner = f"{p['Partner']} ({p['Matches']}x, {p['Winrate']})"
    best_when = summary.get("best_rank_when")
    best_text = f"P{best}" if best is not None else "?"
    if best_when and best is not None:
        best_text += f" ({best_when})"
    return {
        "Naam": summary.get("name"),
        "Huidig": f"P{current}" if current is not None else "?",
        "Beste ooit": best_text,
        "Laatste partner (deze poule)": summary.get("latest_partner") or "-",
        "Top partner (deze poule)": top_partner,
        "Matches (deze poule)": summary.get("matches_relevant", 0),
        "Winrate (deze poule)": summary.get("winrate_relevant", "-"),
    }


# ─────────────────────────────────────────────
# Eigen opstelling - editor (voorgesteld o.b.v. laatste eigen interclubmatch)
# ─────────────────────────────────────────────
def _get_own_profiles() -> list[dict]:
    try:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        return [d.to_dict() for d in docs]
    except Exception:
        return []


def _infer_recent_own_lineup(home_player_id: Optional[str]) -> dict[int, list[str]]:
    """Best-effort: reconstrueert onze meest recente interclub-opstelling als
    prefill voor de opstelling-editor. Faalt dit om welke reden dan ook, dan
    wordt gewoon een lege prefill teruggegeven - de editor blijft dan gewoon
    volledig manueel bruikbaar, er wordt nooit gecrasht op deze stap."""
    if not home_player_id:
        return {}
    try:
        import lineup_lab as ll

        profiles = _get_own_profiles()
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs = ll.get_docs_for_players(list(profile_ids))
        index = ll.build_encounter_index(docs)
        all_encounters = ll.list_encounters(index)
        own_encounter_keys = [
            key for key, _ in all_encounters
            if any(pid == home_player_id for pid, _ in index[key])
        ]
        if not own_encounter_keys:
            return {}

        def _encounter_date(key):
            dates = []
            for _, entry in index[key]:
                d = _parse_simple_date(entry.get("match_date"))
                if d:
                    dates.append(d)
            return max(dates) if dates else (0, 0, 0)

        most_recent_key = sorted(own_encounter_keys, key=_encounter_date, reverse=True)[0]
        doubles = ll.reconstruct_boards(index[most_recent_key])
        name_lookup = {p.get("player_id"): (p.get("display_name") or p.get("player_id")) for p in profiles}

        prefill: dict[int, list[str]] = {}
        for i, double in enumerate(sorted(doubles, key=lambda b: (b.get("round_text") or "")), start=1):
            pair = double.get("pair") or []
            prefill[i] = [name_lookup.get(pid, pid) for pid in pair]
        return prefill
    except Exception:
        return {}


def _render_own_lineup_editor(home_player_id: Optional[str], key_prefix: str, ploeg_id: str) -> str:
    """Toont een editor voor onze eigen opstelling en geeft een platte
    tekstbeschrijving terug (gebruikt als context voor het AI-opstellingsadvies).
    Voorgesteld op basis van onze meest recente interclubmatch ('match 1' -
    reeds gespeeld), voor de aankomende ontmoeting ('match 2') - altijd
    aanpasbaar."""
    st.markdown("#### 🧩 Onze opstelling (voor AI-advies)")
    st.caption(
        "Standaard voorgesteld op basis van onze meest recente interclubmatch (indien gekend). "
        "Pas gerust aan naar wie effectief beschikbaar is voor deze ontmoeting."
    )

    profiles = _get_own_profiles()
    if not profiles:
        st.info("Nog geen eigen spelers gekend. Voeg spelers toe via '➕ Speler toevoegen'.")
        return ""

    labels = sorted({(p.get("display_name") or p.get("player_id") or "?") for p in profiles})
    label_options = [""] + labels

    prefill_key = f"{key_prefix}_lineup_prefill_{ploeg_id}"
    if prefill_key not in st.session_state:
        st.session_state[prefill_key] = _infer_recent_own_lineup(home_player_id)
    prefill = st.session_state[prefill_key]

    n_doubles = st.number_input(
        "Aantal dubbels in deze ontmoeting",
        min_value=1, max_value=8, value=max(2, len(prefill) or 2), step=1,
        key=f"{key_prefix}_nboards_{ploeg_id}",
    )

    lineup_lines = []
    for i in range(1, int(n_doubles) + 1):
        default_pair = prefill.get(i, ["", ""])
        default_a = default_pair[0] if len(default_pair) > 0 else ""
        default_b = default_pair[1] if len(default_pair) > 1 else ""
        c1, c2 = st.columns(2)
        with c1:
            a = st.selectbox(
                f"Dubbel {i} - speler A", label_options,
                index=label_options.index(default_a) if default_a in label_options else 0,
                key=f"{key_prefix}_board_{i}_a_{ploeg_id}",
            )
        with c2:
            b = st.selectbox(
                f"Dubbel {i} - speler B", label_options,
                index=label_options.index(default_b) if default_b in label_options else 0,
                key=f"{key_prefix}_board_{i}_b_{ploeg_id}",
            )
        if a or b:
            lineup_lines.append(f"Dubbel {i}: {a or '?'} / {b or '?'}")

    return "\n".join(lineup_lines)


# ─────────────────────────────────────────────
# AI-sectie
# ─────────────────────────────────────────────
def _render_ai_section(report: dict, own_team_context: str, ploeg_id: str, key_prefix: str) -> None:
    st.markdown("#### 🤖 AI-inzichten")

    if taa is None:
        st.caption("AI-module niet beschikbaar (team_ai_advisor kon niet geladen worden).")
        return

    answer_key = f"{key_prefix}_answer_{ploeg_id}"

    b1, b2 = st.columns(2)
    with b1:
        insights_clicked = st.button(
            "💡 Genereer inzichten", key=f"{key_prefix}_insights_{ploeg_id}",
            type="primary", use_container_width=True,
        )
    with b2:
        lineup_clicked = st.button(
            "🧩 Stel onze opstelling voor", key=f"{key_prefix}_lineup_ai_{ploeg_id}",
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
                st.session_state[answer_key] = taa.suggest_lineup(report, own_team_context=own_team_context or None)
            except Exception as exc:
                st.session_state[answer_key] = f"⚠️ Mislukt: {exc}"

    st.caption("Of stel een eigen vraag:")
    question_key = f"{key_prefix}_question_{ploeg_id}"
    question = st.text_area(
        "Jouw vraag", key=question_key, height=70,
        label_visibility="collapsed", placeholder="Bv. Wie is hun sterkste koppel?",
    )
    if st.button("💬 Vraag AI", key=f"{key_prefix}_ask_{ploeg_id}"):
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
    state_key = f"{key_prefix}_report_{ploeg_id}"

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
        st.caption(f"Laatst bijgewerkt op {_format_ts(report.get('updated_at'))} · bewaard, geen herberekening nodig bij volgend bezoek.")
    with refresh_col:
        if st.button("🔄 Verversen", key=f"{key_prefix}_refresh_{ploeg_id}", use_container_width=True):
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
        height=min(320, 40 + 36 * len(overview_df)),
    )
    st.caption("Partners, matches en winrate zijn strikt beperkt tot de geselecteerde poule.")

    st.markdown("#### 🔎 Detail per speler")
    names = [p.get("name", "?") for p in players]
    sel_name = st.selectbox("Bekijk details van:", names, key=f"{key_prefix}_detail_pick_{ploeg_id}")
    selected = next((p for p in players if p.get("name") == sel_name), None)
    if selected:
        od.render_player_summary_inline(selected)
        if go_to_player_fn and st.button(
            "👁️ Volledige spelerpagina (optioneel)",
            key=f"{key_prefix}_jump_{selected.get('player_id')}",
        ):
            go_to_player_fn(selected.get("player_id"))

    st.divider()
    own_team_context = _render_own_lineup_editor(home_player_id, key_prefix, ploeg_id)

    st.divider()
    _render_ai_section(report, own_team_context, ploeg_id, key_prefix)

    return report
