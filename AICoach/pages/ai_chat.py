from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from AICoach.chat.ai_message_handler import (
    handle_message
)


st.set_page_config(
    page_title="MatchFit AI Chat",
    page_icon="🤖",
    layout="wide"
)

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