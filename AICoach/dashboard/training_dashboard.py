# -*- coding: utf-8 -*-

from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from AICoach.chat.ai_message_handler import handle_message
from AICoach.context_builder import build_context
from AICoach.dashboard.activities_tab import render_activities
from AICoach.dashboard.best_results_tab import render_best_results
from AICoach.dashboard.charts import render_time_chart, selected_date_from_event
from AICoach.dashboard.comparison_tab import render_comparison_tab
from AICoach.dashboard.daily_update import render_daily_update
from AICoach.dashboard.data_loaders import load_history
from AICoach.dashboard.knowledge_tab import render_knowledge
from AICoach.dashboard.recovery_tab import render_recovery
from AICoach.dashboard.ui_helpers import (
    has_data,
    nearest_row,
    render_assistant_answer,
    render_selected_values,
)
from AICoach.saved_insights import render_saved_insights, save_insight


try:
    st.set_page_config(page_title="mAICoach", page_icon="🏃", layout="wide")
except Exception:
    pass

st.markdown(
    """
    <style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.2rem;
        padding-top: 0.65rem;
        padding-bottom: 0.15rem;
        overflow-x: auto;
        overflow-y: visible;
    }
    .stTabs [data-baseweb="tab"] {
        height: auto;
        min-height: 3rem;
        padding: 0.72rem 0.85rem;
        white-space: nowrap;
    }
    .stTabs [data-baseweb="tab"] p {
        line-height: 1.25;
        margin: 0;
        overflow: visible;
    }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.22);
        border-radius: 0.65rem;
        padding: 0.65rem;
    }
    @media (max-width: 700px) {
        .block-container {
            padding-left: 0.55rem;
            padding-right: 0.55rem;
            padding-top: 0.8rem;
        }
        .stTabs [data-baseweb="tab"] {
            padding-left: 0.6rem;
            padding-right: 0.6rem;
            font-size: 0.88rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Lichte, gecachete opstart-sync.
# Draait maximaal één keer per 30 minuten (gedeeld over sessies) en blokkeert de
# UI niet bij elke rerun. Zo laadt de app op mobiel meteen door.
# --------------------------------------------------------------------------- #
@st.cache_resource(ttl=1800, show_spinner=False)
def _sync_once(bucket: str) -> dict:
    from AICoach.sync_latest import sync_latest_data

    return sync_latest_data()


def ensure_latest_data():
    # Draai de sync gecachet; bij fouten blijft de app gewoon werken met
    # de laatst beschikbare data.
    try:
        _sync_once("v1")
    except Exception as exc:  # noqa: BLE001
        st.session_state.startup_sync_error = str(exc)


def render_dashboard():
    df = load_history()
    context = build_context()

    render_daily_update()
    st.divider()

    if df.empty:
        st.warning("Geen trainingshistoriek gevonden.")
        return

    st.caption(
        f"Hersteldata: {context.get('current_date') or 'onbekend'} | "
        f"Trainingsstatus: {context.get('latest_training_status_date') or 'onbekend'}"
    )

    period_options = {"30 dagen": 30, "90 dagen": 90, "Dit jaar": 366, "Alles": len(df)}
    selected_period = st.selectbox("Periode", list(period_options), index=2, key="dashboard_period")
    view = df.tail(period_options[selected_period]).copy()

    latest_date = view["date"].max() if not view.empty else None
    selected_date = st.session_state.get("dashboard_selected_date")
    if selected_date is None:
        selected_date = latest_date
        st.session_state.dashboard_selected_date = latest_date
    selected_row = nearest_row(view, selected_date)
    render_selected_values(selected_row, ["fitness", "fatigue", "form", "training_load", "resting_hr"])

    event = render_time_chart(
        view,
        ["fitness", "fatigue", "form"],
        key="dashboard_fitness_chart",
        selected_date=selected_date,
        title="Fitness, Fatigue en Form",
        default_granularity="Dag",
    )
    event_date = selected_date_from_event(event)
    if event_date is not None and event_date != selected_date:
        st.session_state.dashboard_selected_date = event_date
        st.rerun()

    if has_data(view, "training_load"):
        render_time_chart(
            view,
            ["training_load"],
            key="dashboard_load_chart",
            selected_date=selected_date,
            title="Training load",
            default_granularity="Maand",
        )


def render_chat():
    st.subheader("mAICoach")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    _, clear_column = st.columns([8, 2])
    with clear_column:
        if st.button("Gesprek wissen", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    for index, message in enumerate(st.session_state.chat_history):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_assistant_answer(message["content"])
                if st.button("Bewaar dit inzicht", key=f"save_chat_insight_{index}"):
                    save_insight(message["content"], source="AI Coach")
                    st.success("Inzicht bewaard bij je kennis.")
            else:
                st.markdown(message["content"])

    question = st.chat_input("Stel een vraag over je training, herstel of prestaties...")
    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("mAICoach analyseert je gegevens..."):
                answer = handle_message(question)
            render_assistant_answer(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()


st.title("🏃 mAICoach")

# UI eerst tonen; sync draait gecachet en blokkeert niet.
ensure_latest_data()

context = build_context()
st.caption(
    f"Actuele wellness: {context.get('current_date') or 'onbekend'} | "
    f"Laatste activiteit: {context.get('latest_activity', {}).get('date') or 'onbekend'}"
)

with st.expander("Gegevens verversen"):
    st.caption("De nieuwste gegevens worden automatisch opgehaald. Forceer hier indien nodig.")
    if st.button("Nu verversen"):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.session_state.pop("dashboard_selected_date", None)
        st.rerun()
    if st.session_state.get("startup_sync_error"):
        st.warning("Automatische synchronisatie gaf een melding:")
        st.code(st.session_state["startup_sync_error"])

tab_labels = ["Dashboard", "AI Coach", "Recovery", "Athlete Knowledge", "Beste resultaten", "Activiteiten"]
comparison_active = bool(st.session_state.get("comparison_active"))
if comparison_active:
    tab_labels.append("Vergelijking")

tabs = st.tabs(tab_labels)

with tabs[0]:
    render_dashboard()
with tabs[1]:
    render_chat()
with tabs[2]:
    render_recovery()
with tabs[3]:
    render_knowledge()
    st.divider()
    render_saved_insights()
with tabs[4]:
    render_best_results()
with tabs[5]:
    render_activities()
if comparison_active:
    with tabs[6]:
        render_comparison_tab()
