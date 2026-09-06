# -*- coding: utf-8 -*-
"""Adapter die de mAICoach-gezondheidsmodule als functie aanbiedt.

Plaats dit bestand als: AICoach/dashboard/app.py

De gecombineerde hoofdingang (streamlit_app.py) roept render_health_app() aan.
Deze adapter hergebruikt de bestaande renderfuncties uit training_dashboard.py,
zodat je die logica niet hoeft te dupliceren.

BELANGRIJK: verwijder in training_dashboard.py de regel st.set_page_config(...)
of laat die staan uitsluitend wanneer je dat bestand nog los draait. De
gecombineerde app roept st.set_page_config al aan in streamlit_app.py. Twee keer
set_page_config in één run geeft een fout, daarom staat het hier NIET.
"""

from __future__ import annotations

import streamlit as st

from AICoach.context_builder import build_context
from AICoach.dashboard.training_dashboard import (
    ensure_latest_data,
    render_chat,
    render_dashboard,
)
from AICoach.dashboard.best_results_tab import render_best_results
from AICoach.dashboard.knowledge_tab import render_knowledge
from AICoach.dashboard.recovery_tab import render_recovery
from AICoach.dashboard.activities_tab import render_activities
from AICoach.saved_insights import render_saved_insights


def render_health_app() -> None:
    ensure_latest_data()

    st.title("🏃 mAICoach")

    context = build_context()
    st.caption(
        f"Actuele wellness: {context.get('current_date') or 'onbekend'} | "
        f"Laatste activiteit: "
        f"{context.get('latest_activity', {}).get('date') or 'onbekend'}"
    )

    if st.session_state.get("startup_sync_error"):
        with st.expander("Synchronisatie gaf een waarschuwing"):
            st.code(st.session_state["startup_sync_error"])

    (
        tab_dashboard,
        tab_chat,
        tab_recovery,
        tab_knowledge,
        tab_best,
        tab_activities,
    ) = st.tabs(
        [
            "Dashboard",
            "AI Coach",
            "Recovery",
            "Athlete Knowledge",
            "Beste resultaten",
            "Activiteiten",
        ]
    )

    with tab_dashboard:
        render_dashboard()
    with tab_chat:
        render_chat()
    with tab_recovery:
        render_recovery()
    with tab_knowledge:
        render_knowledge()
        st.divider()
        render_saved_insights()
    with tab_best:
        render_best_results()
    with tab_activities:
        render_activities()
