# -*- coding: utf-8 -*-
"""Gecombineerde hoofdingang: mAICoach (gezondheid) + Padel Analysis.

Dit is het ENIGE bestand dat st.set_page_config aanroept. Het toont een
navigatie waarmee je wisselt tussen de twee apps. Deploy met dit bestand als
'Main file path' op Streamlit Community Cloud.

--------------------------------------------------------------------------
PERF_TIMING_ROLLOUT_2026-09-29 (op verzoek van Kim: laadtijd-meting over de
HELE app i.p.v. enkel op de Opstelling-analyse-pagina)
--------------------------------------------------------------------------
Dit bestand draait bij ELKE volledige run, voor elke pagina. Daarom staat
de timing hier EEN keer:
  - perf.begin_run()  : wist de metingen van de vorige run en start de klok;
  - perf.step(...)    : meet de volledige pagina (navigation.run());
  - perf.end_run()    : tekent het paneel "Laadtijd-analyse (debug)" onderaan
                        de pagina - voor mAICoach EN PadelAnalysis.
Pagina's die zelf nog perf.reset()/perf.render_panel() aanroepen (bv.
page_lineup_lab.py) worden daardoor automatisch no-ops - zie
perf_timing.py. Het verschil tussen "pagina: ..." en de som van de stappen
eronder is tijd die (nog) niet gemeten wordt - daar zoeken we in de
volgende ronde verder.

Uitschakelen: PERF_ENABLED = False bovenaan perf_timing.py.
"""

from pathlib import Path
import sys

import streamlit as st

# Zorg dat zowel de projectroot als de AICoach-map importeerbaar zijn.
PROJECT_ROOT = Path(__file__).resolve().parent
for extra_path in (PROJECT_ROOT, PROJECT_ROOT / "AICoach"):
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))

# PERF_TIMING_ROLLOUT_2026-09-29: perf_timing.py staat in de repo-root.
# Faalt de import toch, dan draait de app gewoon verder zonder metingen.
try:
    import perf_timing as perf
except Exception:  # noqa: BLE001  pragma: no cover
    perf = None

st.set_page_config(page_title="Kim | Apps", page_icon="🏠", layout="wide")

if perf is not None:
    perf.begin_run()

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

if perf is not None:
    with perf.step(f"pagina: {navigation.title}"):
        navigation.run()
    perf.end_run()
else:
    navigation.run()
