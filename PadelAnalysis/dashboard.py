"""
dashboard.py — PadelAnalysis v2 Streamlit dashboard: DUNNE ENTRYPOINT.

PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14 (op verzoek van Kim):
Dit bestand groeide tot ~1800 regels, wat elke aanpassing traag en
foutgevoelig maakte. Opgesplitst in:
  - dashboard_common.py         : gedeelde helpers/imports/CSS-achtige state
  - page_add_player.py          : "➕ Speler toevoegen"
  - page_lineup_lab.py          : "🧩 Opstelling-analyse" (incl. rotatieplanner)
  - player_dashboard_shared.py  : render_player_dashboard() - HERGEBRUIKT
                                   door zowel Mijn profiel als Spelers
  - page_my_profile.py          : "👤 Mijn profiel"
  - page_players.py             : "🔍 Spelers"

dashboard.py zelf doet enkel nog: st.set_page_config, CSS-injectie,
navigatie-knoppen, en de routing naar de juiste page_xxx()-functie.

Voordeel voor toekomstige wijzigingen: een aanpassing aan bv. enkel de
rotatieplanner raakt nu alleen page_lineup_lab.py (~450 regels) in plaats
van het volledige, vroegere dashboard.py (~1800 regels) - sneller en met
minder risico op onbedoelde neveneffecten in andere pagina's.
"""
import streamlit as st

import dashboard_common as dc  # zorgt voor path-setup + alle gedeelde imports
from page_add_player import page_add_player
from page_lineup_lab import page_lineup_lab
from page_my_profile import page_my_profile
from page_players import page_players

try:
    st.set_page_config(page_title="Padel Analysis", page_icon="🎾", layout="wide", initial_sidebar_state="collapsed")
except Exception:
    pass

# ─────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* Clean card-style metric */
[data-testid="stMetric"] {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 12px 16px;
    border-left: 4px solid #1a73e8;
}
[data-testid="stMetricLabel"] { font-size: 0.75rem; color: #666; }
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
/* Tab styling */
.stTabs [data-baseweb="tab"] { font-size: 0.85rem; padding: 6px 14px; }
.stTabs [aria-selected="true"] { border-bottom: 3px solid #1a73e8 !important; }
/* Win badge */
.badge-win  { background:#d4edda; color:#155724; border-radius:4px; padding:2px 8px; font-size:0.8rem; font-weight:600; }
.badge-loss { background:#f8d7da; color:#721c24; border-radius:4px; padding:2px 8px; font-size:0.8rem; font-weight:600; }
/* Section header */
.section-header { font-size:1.1rem; font-weight:700; margin-bottom:8px; color:#1a1a1a; border-bottom:2px solid #e0e0e0; padding-bottom:4px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Navigation
# ─────────────────────────────────────────────
PAGES = ["👤 Mijn profiel", "🔍 Spelers", "➕ Speler toevoegen", "🧩 Opstelling-analyse"]
if "page" not in st.session_state:
    st.session_state["page"] = PAGES[0]
nav_col = st.columns(len(PAGES))
for i, p in enumerate(PAGES):
    if nav_col[i].button(p, use_container_width=True,
                          type="primary" if st.session_state["page"] == p else "secondary"):
        st.session_state["page"] = p
        st.rerun()
st.divider()
page = st.session_state["page"]

# ─────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────
if page == "➕ Speler toevoegen":
    page_add_player()
elif page == "🧩 Opstelling-analyse":
    page_lineup_lab()
elif page == "👤 Mijn profiel":
    page_my_profile()
else:
    page_players()
