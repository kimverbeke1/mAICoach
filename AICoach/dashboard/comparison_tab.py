# -*- coding: utf-8 -*-
"""Aparte, sluitbare vergelijkings-tab voor mAICoach.

Wordt alleen getoond wanneer de gebruiker 2 activiteiten heeft geselecteerd en op
'Vergelijk in aparte tab' klikt. De AI-analyse start pas na een expliciete knop,
zodat het aanvinken van activiteiten geen wachttijd veroorzaakt.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from AICoach.activity_comparison import compare_selected_activities, comparison_frame
from AICoach.dashboard.data_loaders import load_activities_frame
from AICoach.dashboard.ui_helpers import render_assistant_answer


def _selected_ids() -> list[str]:
    values = st.session_state.get("activity_comparison_ids", [])
    return list(dict.fromkeys(str(value) for value in values))[:2]


def _close_comparison() -> None:
    st.session_state.comparison_active = False
    st.session_state.comparison_answer = ""
    st.session_state.comparison_messages = []
    st.session_state.activity_comparison_ids = []


def _overview(selected: pd.DataFrame) -> None:
    frame = comparison_frame(selected)
    columns = [
        column
        for column in [
            "date", "name", "sport", "distance_km", "duration_min",
            "avg_hr", "max_hr", "training_load", "efficiency",
        ]
        if column in frame.columns
    ]
    if columns:
        display = frame[columns].copy()
        if "date" in display.columns:
            display["date"] = pd.to_datetime(display["date"], errors="coerce").dt.strftime("%d/%m/%Y")
        if "efficiency" in display.columns:
            display["efficiency"] = pd.to_numeric(display["efficiency"], errors="coerce").round(4)
        st.dataframe(display, use_container_width=True, hide_index=True)


def render_comparison_tab() -> None:
    header = st.columns([8, 2])
    with header[0]:
        st.subheader("Vergelijking van 2 activiteiten")
        st.caption(
            "De AI gebruikt alleen deze 2 activiteiten, volledige streamdata, "
            "wellness van dezelfde en vorige dag, en Fitness/Fatigue/Form."
        )
    with header[1]:
        if st.button("Sluit vergelijking", use_container_width=True):
            _close_comparison()
            st.rerun()

    ids = _selected_ids()
    df = load_activities_frame()
    selected = df[df["id"].astype(str).isin(ids)].copy()
    order = {value: index for index, value in enumerate(ids)}
    selected["_order"] = selected["id"].astype(str).map(order)
    selected = selected.sort_values("_order").drop(columns="_order")

    if len(selected) != 2:
        st.warning("Selecteer exact 2 geldige activiteiten in het tabblad Activiteiten.")
        return

    _overview(selected)

    if not st.session_state.get("comparison_answer"):
        if st.button("Start AI-analyse", type="primary", use_container_width=True):
            with st.spinner("mAICoach vergelijkt de 2 activiteiten..."):
                answer = compare_selected_activities(selected)
            st.session_state.comparison_answer = answer
            st.session_state.comparison_messages = []
            st.rerun()

    answer = st.session_state.get("comparison_answer", "")
    if answer:
        render_assistant_answer(answer)
        st.markdown("#### Vervolgvragen")
        for message in st.session_state.get("comparison_messages", []):
            with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    render_assistant_answer(message["content"])
                else:
                    st.markdown(message["content"])
        question = st.chat_input(
            "Vraag bijvoorbeeld: wat is TRIMP of welke streamdata ondersteunt dit?",
            key="comparison_follow_up",
        )
        if question:
            messages = st.session_state.get("comparison_messages", [])
            conversation = "\n".join(f"{item['role']}: {item['content']}" for item in messages)
            with st.spinner("mAICoach bekijkt opnieuw de volledige vergelijkingscontext..."):
                follow_up = compare_selected_activities(
                    selected,
                    question=question,
                    previous_answer=answer,
                    conversation=conversation,
                )
            messages.extend([
                {"role": "user", "content": question},
                {"role": "assistant", "content": follow_up},
            ])
            st.session_state.comparison_messages = messages
            st.rerun()
