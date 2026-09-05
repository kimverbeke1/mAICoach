# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from AICoach.saved_insights import save_insight

ROOT = Path(__file__).resolve().parents[2]
INSIGHTS_FILE = ROOT / "data" / "athlete_insights.json"

CONFIDENCE_ICONS = {
    "hoog": "🟢",
    "redelijk": "🟢",
    "middelmatig": "🟡",
    "laag": "🟠",
    "onvoldoende": "⚪",
}


def _load_insights_payload() -> dict:
    """Lees athlete_insights.json (of val terug op een leeg payload)."""
    try:
        import json

        payload = json.loads(INSIGHTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(payload, list):
        return {"insights": payload}
    return payload if isinstance(payload, dict) else {}


def _format_generated_at(value):
    if not value:
        return "onbekend"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)


def _insight_as_text(insight: dict) -> str:
    """Bouw een leesbare tekst van een inzicht om te kunnen bewaren."""
    lines = [f"**{insight.get('title') or 'Inzicht'}**", insight.get("meaning") or ""]
    advice = insight.get("actionable_advice")
    if advice:
        lines.append(f"Actie: {advice}")
    evidence = insight.get("evidence") or []
    if evidence:
        lines.append("Onderbouwing: " + "; ".join(str(item) for item in evidence))
    return "\n".join(line for line in lines if line)


def _render_insight_card(number, insight):
    confidence = str(insight.get("confidence") or "onvoldoende").lower()
    icon = CONFIDENCE_ICONS.get(confidence, "⚪")
    title = insight.get("title") or f"Inzicht {number}"
    meaning = insight.get("meaning") or "Nog geen duidelijke praktische betekenis."
    cluster = insight.get("sport_or_cluster") or "Algemeen"
    sample_size = insight.get("sample_size")
    advice = insight.get("actionable_advice")
    evidence = insight.get("evidence") or []
    limitations = insight.get("limitations") or []

    with st.container(border=True):
        st.markdown(f"#### {icon} {title}")
        meta = [cluster]
        if sample_size:
            meta.append(f"{sample_size} sessies")
        meta.append(f"betrouwbaarheid: {confidence}")
        st.caption(" · ".join(str(part) for part in meta))
        st.markdown(meaning)
        if advice:
            st.markdown(f"**Wat je hiermee kunt doen:** {advice}")
        if evidence or limitations:
            with st.expander("Onderbouwing en beperkingen"):
                if evidence:
                    st.markdown("**Onderbouwing**")
                    for item in evidence:
                        st.markdown(f"- {item}")
                if limitations:
                    st.markdown("**Beperkingen**")
                    for item in limitations:
                        st.markdown(f"- {item}")
        if st.button("Bewaar dit inzicht", key=f"save_knowledge_insight_{number}"):
            save_insight(_insight_as_text(insight), source="Athlete Knowledge", title=title)
            st.success("Inzicht bewaard bij je kennis.")


def _run_new_analysis():
    """Roep de AI-analyse over alle data aan en bewaar het resultaat in athlete_insights.json."""
    from AICoach.athlete_insight_generator import generate_athlete_insights

    return generate_athlete_insights()


def render_knowledge():
    st.subheader("Athlete Knowledge")
    st.caption(
        "mAICoach analyseert al je activiteiten en wellnessdata en zoekt zelf naar "
        "bruikbare, stuurbare patronen."
    )

    action_left, action_right = st.columns([3, 7])
    with action_left:
        run_now = st.button("Nieuwe analyse op al mijn data", type="primary", use_container_width=True)
    if run_now:
        with st.spinner("mAICoach analyseert je volledige data. Dit kan even duren..."):
            try:
                st.session_state.knowledge_analysis_result = _run_new_analysis()
                st.session_state.knowledge_analysis_error = None
            except Exception as exc:  # noqa: BLE001
                st.session_state.knowledge_analysis_error = str(exc)
        st.rerun()

    if st.session_state.get("knowledge_analysis_error"):
        st.error("De analyse kon niet worden voltooid.")
        with st.expander("Foutdetails"):
            st.code(st.session_state["knowledge_analysis_error"])

    payload = _load_insights_payload()
    headline = payload.get("headline")
    generated_at = payload.get("generated_at")
    insights = payload.get("insights") or []
    next_focus = payload.get("next_focus")

    if generated_at:
        st.caption(f"Laatste analyse: {_format_generated_at(generated_at)}")

    if headline:
        st.markdown(f"**{headline}**")

    if not insights:
        st.info(
            "Er zijn nog geen inzichten. Klik op 'Nieuwe analyse op al mijn data' "
            "om mAICoach je gegevens te laten analyseren."
        )
        return

    for number, insight in enumerate(insights, start=1):
        _render_insight_card(number, insight)

    if next_focus:
        st.caption(f"Volgende focus: {next_focus}")
