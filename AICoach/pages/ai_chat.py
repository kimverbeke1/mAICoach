"""
ai_chat.py - losse MatchFit AI Chat-pagina (AICoach/pages/).

PERF_TIMING_ROLLOUT_2026-09-29: timing toegevoegd rond het AI-antwoord
(handle_message), het enige zware deel van deze pagina.

LET OP: deze pagina staat NIET in de navigatie van streamlit_app.py (daar
enkel mAICoach en Padel Analysis). Met st.navigation wordt de map pages/
bovendien niet meer automatisch opgepikt. Ze draait dus enkel standalone
(`streamlit run AICoach/pages/ai_chat.py`) - en dan tekenen
perf.reset()/perf.render_panel() hieronder het paneel zelf. De chat IN de
app zit in training_dashboard.py (tab "AI Coach") en wordt daar gemeten.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

# perf_timing.py staat in de repo-root (ROOT hierboven staat al op sys.path).
try:
    import perf_timing as perf
except Exception:  # noqa: BLE001  pragma: no cover
    class _PerfNoop:
        @staticmethod
        def reset():
            pass

        @staticmethod
        def render_panel(**_kwargs):
            pass

        @staticmethod
        def step(_label):
            from contextlib import nullcontext
            return nullcontext()

    perf = _PerfNoop()

from AICoach.chat.ai_message_handler import (
    handle_message
)


st.set_page_config(
    page_title="MatchFit AI Chat",
    page_icon="🤖",
    layout="wide"
)

perf.reset()

st.title("🤖 MatchFit AI Coach")

st.caption(
    "Stel vragen over je trainingen."
)

if "messages" not in st.session_state:
    st.session_state.messages = []


for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )


question = st.chat_input(
    "Stel je vraag..."
)

if question:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": question
        }
    )

    with st.chat_message("user"):

        st.markdown(
            question
        )

    with st.chat_message(
        "assistant"
    ):

        with st.spinner(
            "Analyseren..."
        ):

            with perf.step("AI chat: handle_message (AI-antwoord)"):
                answer = handle_message(
                    question
                )

            st.markdown(
                answer
            )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

perf.render_panel()
