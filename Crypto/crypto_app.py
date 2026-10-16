"""Lokale standalone runner:  streamlit run crypto_app.py  (vanuit de map Crypto)"""
import streamlit as st

st.set_page_config(page_title="Crypto", page_icon="🪙", layout="wide")

from crypto_ui import render_crypto_page  # noqa: E402

render_crypto_page()
