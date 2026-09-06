"""
cloud_helpers.py — Streamlit Community Cloud detectie voor PadelAnalysis.

Playwright/Selenium-scraping (spelers zoeken/toevoegen op TVL, profielen
verversen, klassementshistoriek laden, nieuwe tegenstanders scrapen)
vereist browser-binaries die niet beschikbaar zijn op Streamlit Community
Cloud. Deze module bepaalt of scraping mogelijk is, zodat de UI de
betrokken knoppen kan verbergen op cloud en gewoon tonen op een lokale
machine (waar je normaal `streamlit run streamlit_app.py` draait).
"""

import os
import sys

_CLOUD_PATH_MARKERS = ("/mount/src/", "/home/adminuser/")


def is_scraping_available() -> bool:
    """
    True  -> lokaal: Playwright/browser-binaries worden verondersteld
             beschikbaar te zijn, scrape-knoppen tonen.
    False -> Streamlit Community Cloud (of expliciet uitgeschakeld):
             geen browser-binaries, scrape-knoppen verbergen.

    Detectie, in volgorde:
    1. Expliciete override via st.secrets["SCRAPING_AVAILABLE"] (bool) —
       handig om dit tijdelijk te forceren, ongeacht platform.
    2. Herkenning van het typische Streamlit Community Cloud-pad
       (/mount/src/... , gebruiker adminuser), zoals te zien in de
       tracebacks van deze app.
    3. Fallback: als het 'playwright' package niet importeerbaar is,
       is scraping sowieso niet mogelijk.
    """
    try:
        import streamlit as st
        if "SCRAPING_AVAILABLE" in st.secrets:
            return bool(st.secrets["SCRAPING_AVAILABLE"])
    except Exception:
        pass

    cwd = os.getcwd()
    script_path = str(sys.path[0] or "")
    if any(cwd.startswith(m) or script_path.startswith(m) for m in _CLOUD_PATH_MARKERS):
        return False

    try:
        import playwright  # noqa: F401
    except ImportError:
        return False

    return True


def scraping_unavailable_notice(feature: str = "Deze functie") -> None:
    """Toont een consistente uitleg wanneer scraping niet beschikbaar is (cloud)."""
    import streamlit as st
    st.info(
        f"🚫 {feature} vereist een browser (Playwright) en is niet beschikbaar in deze "
        f"cloud-omgeving. Voer dit lokaal uit (`streamlit run streamlit_app.py`) — nieuwe "
        f"of ververste data komt via Firestore automatisch ook hier terecht."
    )
