# -*- coding: utf-8 -*-
"""Gecombineerde hoofdingang voor mAICoach + PadelAnalysis.

Eén Streamlit-app, twee modules, schakelbaar via de sidebar:
- 🏃 Gezondheid : het mAICoach-dashboard (AICoach/dashboard/app.py).
- 🎾 Padel      : het PadelAnalysis-project (PadelAnalysis/dashboard.py).

PadelAnalysis is (nog) geen Python-package (geen __init__.py) en draait code op
module-niveau. Daarom laden we het via een pad-loader en zetten we de map op
sys.path, zodat de interne imports (firebase_service, scraper, ...) blijven werken.

Deploy-entrypoint op Streamlit Community Cloud: streamlit_app.py (projectroot).
"""

from pathlib import Path
import importlib
import importlib.util
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
PADEL_DIR = PROJECT_ROOT / "PadelAnalysis"

for path in (PROJECT_ROOT, PADEL_DIR):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

st.set_page_config(page_title="mAICoach", page_icon="🏃", layout="wide")


MODULES = {
    "🏃 Gezondheid": "health",
    "🎾 Padel": "padel",
}

with st.sidebar:
    st.markdown("## mAICoach")
    label = st.radio("Kies module", list(MODULES.keys()), index=0, key="active_module")
active_module = MODULES[label]


def render_health_module() -> None:
    from AICoach.dashboard.app import render_health_app

    render_health_app()


def _load_padel_dashboard():
    """Laad PadelAnalysis/dashboard.py als module (het is geen package)."""
    dashboard_path = PADEL_DIR / "dashboard.py"
    if not dashboard_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("padel_dashboard", dashboard_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["padel_dashboard"] = module
    spec.loader.exec_module(module)
    return module


def render_padel_module() -> None:
    try:
        module = _load_padel_dashboard()
    except Exception as exc:  # noqa: BLE001
        st.title("🎾 Padel")
        st.error("De padelmodule kon niet geladen worden.")
        with st.expander("Foutdetails"):
            st.code(str(exc))
        return

    if module is None:
        st.title("🎾 Padel")
        st.info("PadelAnalysis/dashboard.py niet gevonden in de projectroot.")
        return

    # Voorkeur: een expliciete renderfunctie in dashboard.py.
    for func_name in ("render_padel_app", "render_dashboard", "main"):
        func = getattr(module, func_name, None)
        if callable(func):
            func()
            return

    # Anders is dashboard.py waarschijnlijk al op module-niveau uitgevoerd bij
    # het laden hierboven, dus dan is er niets meer te doen.


if active_module == "health":
    render_health_module()
else:
    render_padel_module()
