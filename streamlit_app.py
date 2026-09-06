# -*- coding: utf-8 -*-
"""Gecombineerde hoofdingang: mAICoach (gezondheid) + Padel Analysis.

Dit is het ENIGE bestand dat st.set_page_config aanroept. Het toont een
navigatie waarmee je wisselt tussen de twee apps. Deploy met dit bestand als
'Main file path' op Streamlit Community Cloud.
"""

from pathlib import Path
import sys

import streamlit as st

# Zorg dat zowel de projectroot als de AICoach-map importeerbaar zijn.
PROJECT_ROOT = Path(__file__).resolve().parent
for extra_path in (PROJECT_ROOT, PROJECT_ROOT / "AICoach"):
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))

st.set_page_config(page_title="Kim | Apps", page_icon="🏠", layout="wide")

# Elke pagina is een apart script dat bij elke klik opnieuw draait.
health_page = st.Page(
    "AICoach/dashboard/health_page.py",
    title="mAICoach",
    icon="🏃",
    default=True,
)
padel_page = st.Page(
    "PadelAnalysis/dashboard.py",
    title="Padel Analysis",
    icon="🎾",
)

navigation = st.navigation({"Apps": [health_page, padel_page]})
navigation.run()
