"""Pagina 'Crypto' in de hoofdapp (streamlit_app.py). Geen st.set_page_config hier: dat doet de hoofdapp."""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from crypto_ui import render_crypto_page  # noqa: E402

render_crypto_page()
