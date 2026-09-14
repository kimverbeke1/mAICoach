"""
opponent_analysis.py - samengevat analysescherm voor de volledige tegenploeg (v9).
PADEL_ANALYSIS_TWO_LAYER_2026-09-10
De overzichtstabel toont per speler ZOWEL de huidige poule als de historiek
uit vorige periodes, in aparte kolommen.
PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13 (v7):
Overzichtstabel toont "Playing strength" rechtstreeks uit de gecachete
padelstats.be-waarde (via build_player_summary(), zie opponent_dossier.py).
PADEL_ANALYSIS_REMOVE_OWN_LINEUP_EDITOR_2026-09-13 (v8):
De "Onze opstelling"-sectie is volledig verwijderd - al gedekt door de
Opstelling-scenario's in dashboard.py.
PADEL_ANALYSIS_RENDER_SPLIT_2026-09-14 (v9, op verzoek van Kim):
Kim wil de Opstelling-scenario's + AI-functies BOVENAAN de pagina tonen, en
pas DAARONDER de overzichtstabel/detail-per-speler van de tegenploeg. Om
dashboard.py toe te laten die volgorde zelf te bepalen, is render_team_analysis()
opgesplitst in herbruikbare stukken die elk apart aanroepbaar zijn:
  - get_team_report(...)              : bouwt/cachet het rapport, geen UI.
  - render_team_header(...)           : titel + "Verversen"-knop, geeft
                                         het (evt. ververste) rapport terug.
  - render_ai_section(report, ...)    : "AI-inzichten" (was _render_ai_section,
                                         nu publiek zodat dashboard.py dit
                                         apart, HOGER op de pagina, kan tonen).
  - render_overview_and_detail(...)   : overzichtstabel + detail-per-speler.
render_team_analysis() blijft bestaan als dunne wrapper (roept alle
bovenstaande in de OUDE volgorde aan) voor eventuele andere/toekomstige
aanroepers die de vroegere volgorde verwachten - dashboard.py gebruikt sinds
deze versie de losse functies rechtstreeks, in de NIEUWE volgorde.
PADEL_ANALYSIS_REMOVE_JUMP_BUTTON_2026-09-14:
De "👁️ Volledige spelerpagina"-knop bij Detail-per-speler is verwijderd (op
Kim's verzoek, consistent met het eerder al verwijderen van de vergelijkbare
"👁️ Bekijk"-knop bij de Opstelling-scenario's in dashboard.py - beide
voegden weinig toe binnen deze analyseschermen en maakten de UI drukker).
Verder in deze versie:
- "board" hernoemd naar "dubbel";
- bordpositie-heuristiek volledig verwijderd.
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
REPORT_SCHEMA_VERSION = 8  # ongewijzigd datamodel t.o.v. v8; enkel rendering opgesplitst in v9
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
def get_team_report(
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
    key_prefix: str = "team_analysis",
) -> dict:
    """PADEL_ANALYSIS_RENDER_SPLIT_2026-09-14: bouwt/cachet (via
    st.session_state, net als voorheen binnen render_team_analysis) het
    volledige team-scoutingrapport, ZONDER er iets van te tonen. Aparte
    functie zodat dashboard.py het rapport kan opvragen (bv. als AI-context
    voor de Opstelling-scenario's) VOORDAT de overzichtstabel/detail-per-
    speler getoond wordt."""
    ploeg_id = opp.get("ploeg_id")
    state_key = f"{key_prefix}_report_v8_{ploeg_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = _load_report(ploeg_id)
    report = st.session_state[state_key]
    if _needs_rebuild(report, bundle, current_spelgroep_id):
        report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
        _save_report(report)
        st.session_state[state_key] = report
    return report
def render_team_header(
    report: dict,
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
    key_prefix: str = "team_analysis",
) -> dict:
    """Titel + 'Verversen'-knop. Geeft het (evt. na verversen NIEUWE) rapport
    terug, zodat de aanroeper daarmee verder kan (bv. voor AI-context)."""
    ploeg_id = opp.get("ploeg_id")
    state_key = f"{key_prefix}_report_v8_{ploeg_id}"
    header_col, refresh_col = st.columns([4, 1])
    with header_col:
        st.markdown(f"### 📋 Analyse: {opp.get('name', '?')}")
        st.caption(
            f"Poule {current_spelgroep_id or 'onbekend'} · "
            f"laatst berekend op {_format_ts(report.get('updated_at'))}"
        )
    with refresh_col:
        if st.button("🔄 Verversen", key=f"{key_prefix}_refresh_v8_{ploeg_id}", use_container_width=True):
            report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
            _save_report(report)
            st.session_state[state_key] = report
            st.rerun()
    return report
# ─────────────────────────────────────────────
# Overzichtstabel (twee lagen naast elkaar + playing strength)
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
    current_elo = summary.get("current_elo")
    if summary.get("elo_source") == "padelstat" and current_elo is not None:
        elo_text = f"P{current_elo}"
    else:
        elo_text = "-"
    return {
        "Naam": summary.get("name"),
        "Huidig": f"P{current}" if current is not None else "?",
        "Beste ooit": best_text,
        "Playing strength (padelstats.be)": elo_text,
        "Matchen deze poule": summary.get("matches_relevant", 0),
        "Winrate deze poule": summary.get("winrate_relevant", "-"),
        "Partner deze poule": partner_now,
        "Matchen historiek": summary.get("matches_history", 0),
        "Winrate historiek": summary.get("winrate_history", "-"),
        "Vaste partner historiek": partner_hist,
        "Vorm": summary.get("form_history", "-"),
    }
def render_overview_and_detail(
    report: dict,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    key_prefix: str = "team_analysis",
) -> None:
    """Overzichtstabel + Detail-per-speler.
    PADEL_ANALYSIS_RENDER_SPLIT_2026-09-14: losgemaakt van render_team_analysis
    zodat dashboard.py dit NA de Opstelling-scenario's/AI-secties kan tonen.
    PADEL_ANALYSIS_REMOVE_JUMP_BUTTON_2026-09-14: de "👁️ Volledige
    spelerpagina"-knop is hier verwijderd (zie moduledocstring). go_to_player_fn
    wordt niet langer gebruikt binnen deze functie, maar blijft als
    (ongebruikte) parameter voor achterwaartse compatibiliteit met bestaande
    aanroepen."""
    ploeg_id = report.get("opponent_ploeg_id")
    players = report.get("players", []) or []
    if not players:
        st.info("Nog geen spelersdata beschikbaar voor deze tegenploeg.")
        return
    st.markdown("#### 📊 Overzicht")
    overview_df = pd.DataFrame([_overview_row(p) for p in players])
    st.dataframe(
        overview_df, use_container_width=True, hide_index=True,
        height=min(400, 40 + 36 * len(overview_df)),
    )
    missing_padelstat = sum(1 for p in players if p.get("elo_source") != "padelstat")
    if missing_padelstat:
        st.caption(
            f"🎯 'Playing strength' komt van padelstats.be. Voor {missing_padelstat} speler(s) hier nog "
            "niet opgehaald ('-' in de tabel) - voer bulk_fetch_padelstat_ratings.py uit om aan te vullen."
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
    sel_name = st.selectbox("Bekijk details van:", names, key=f"{key_prefix}_detail_v8_{ploeg_id}")
    selected = next((p for p in players if p.get("name") == sel_name), None)
    if selected:
        od.render_player_summary_inline(selected)
# ─────────────────────────────────────────────
# Eigen-speler rating (gedeeld met dashboard.py's Opstelling-scenario's)
# ─────────────────────────────────────────────
def _get_own_profiles() -> list[dict]:
    try:
        return [d.to_dict() for d in fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()]
    except Exception:
        return []
def get_own_player_rating(player_id: str) -> tuple[float, str]:
    """PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13: geeft (sterkte, bron) terug
    voor één van ONZE spelers. Volgorde: 1. padelstats.be, 2. officieel TVL-
    klassement, 3. neutrale default 200."""
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:
        cached = None
    if cached and cached.get("rating") is not None:
        return float(cached["rating"]), "padelstat"
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:
        doc = {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    ranking_doc = doc if doc.get("klassement_history") else profile_doc
    current_rank, _best, _when, _rows = od._history_summary(ranking_doc)
    if current_rank is not None:
        return float(current_rank), "official_klassement"
    return 200.0, "onbekend"
# ─────────────────────────────────────────────
# AI-sectie (vrije vragen + automatische inzichten over de TEGENPLOEG)
# ─────────────────────────────────────────────
def render_ai_section(report: dict, ploeg_id: str, key_prefix: str = "team_analysis") -> None:
    """PADEL_ANALYSIS_RENDER_SPLIT_2026-09-14: was _render_ai_section, nu
    PUBLIEK (geen underscore-prefix meer) zodat dashboard.py dit apart en
    HOGER op de pagina kan tonen, vóór de overzichtstabel/detail-per-speler."""
    st.markdown("#### 🤖 AI-inzichten over de tegenploeg")
    if taa is None:
        st.caption("AI-module niet beschikbaar (team_ai_advisor kon niet geladen worden).")
        return
    answer_key = f"{key_prefix}_answer_v8_{ploeg_id}"
    if st.button(
        "💡 Genereer inzichten", key=f"{key_prefix}_insights_v8_{ploeg_id}",
        type="primary",
    ):
        with st.spinner("AI analyseert de tegenploeg..."):
            try:
                st.session_state[answer_key] = taa.generate_insights(report)
            except Exception as exc:
                st.session_state[answer_key] = f"⚠️ Mislukt: {exc}"
    st.caption("Of stel een eigen vraag over de tegenploeg:")
    question = st.text_area(
        "Jouw vraag", key=f"{key_prefix}_question_v8_{ploeg_id}", height=70,
        label_visibility="collapsed", placeholder="Bv. Wie is hun sterkste dubbel?",
    )
    if st.button("💬 Vraag AI", key=f"{key_prefix}_ask_v8_{ploeg_id}"):
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
# Alias voor achterwaartse compatibiliteit (was de interne naam vóór v9).
_render_ai_section = render_ai_section
# ─────────────────────────────────────────────
# Hoofdfunctie (dunne wrapper, oude volgorde - voor eventuele andere aanroepers)
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
    """Toont het volledige teamanalysescherm in de OUDE volgorde (header,
    overzicht+detail, AI) en geeft het gebruikte rapport terug.
    PADEL_ANALYSIS_RENDER_SPLIT_2026-09-14: dashboard.py roept sinds deze
    versie de losse bouwstenen (get_team_report/render_team_header/
    render_ai_section/render_overview_and_detail) rechtstreeks aan, in een
    ANDERE volgorde (AI-secties eerst, details onderaan). Deze functie blijft
    behouden voor eventuele andere/toekomstige aanroepers die de oorspronkelijke
    volgorde verwachten.
    home_player_id wordt niet meer gebruikt (de eigen-opstelling-editor is
    verwijderd in v8) - blijft in de signatuur voor achterwaartse
    compatibiliteit."""
    report = get_team_report(
        bundle, opp, all_docs,
        current_reeks_url=current_reeks_url,
        current_spelgroep_id=current_spelgroep_id,
        global_docs=global_docs,
        key_prefix=key_prefix,
    )
    report = render_team_header(
        report, bundle, opp, all_docs,
        current_reeks_url=current_reeks_url,
        current_spelgroep_id=current_spelgroep_id,
        global_docs=global_docs,
        key_prefix=key_prefix,
    )
    render_overview_and_detail(report, go_to_player_fn=go_to_player_fn, key_prefix=key_prefix)
    st.divider()
    render_ai_section(report, opp.get("ploeg_id"), key_prefix=key_prefix)
    return report
