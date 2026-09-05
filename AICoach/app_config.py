# -*- coding: utf-8 -*-
"""Centrale configuratie/secrets voor mAICoach.

Werkt zowel lokaal (.env) als op Streamlit Community Cloud (st.secrets).
Volgorde van voorrang per sleutel:
1. Omgevingsvariabele (env / .env via python-dotenv)
2. st.secrets (Streamlit Cloud)

Gebruik in je code:
    from AICoach.app_config import get_secret, require_secret

    INTERVALS_API_KEY = require_secret("INTERVALS_API_KEY")
    OPENAI_MODEL = get_secret("OPENAI_MODEL", "gpt-5-mini")
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
except Exception:  # noqa: BLE001 - dotenv is optioneel in de cloud
    pass


def _from_streamlit(name: str):
    """Lees een sleutel uit st.secrets als Streamlit beschikbaar is."""
    try:
        import streamlit as st
    except Exception:  # noqa: BLE001
        return None
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # noqa: BLE001 - geen secrets.toml aanwezig
        return None
    return None


def get_secret(name: str, default=None):
    """Haal een secret/configuratie op met env-voorrang, dan st.secrets."""
    value = os.getenv(name)
    if value is not None and value != "":
        return value
    value = _from_streamlit(name)
    if value is not None and value != "":
        return value
    return default


def require_secret(name: str):
    """Zoals get_secret, maar geeft een duidelijke fout als de sleutel ontbreekt."""
    value = get_secret(name)
    if value is None or value == "":
        raise RuntimeError(
            f"Ontbrekende configuratie: '{name}'. Zet deze in je lokale .env of "
            f"in Streamlit Cloud onder App settings -> Secrets."
        )
    return value


def use_real_ai() -> bool:
    return str(get_secret("USE_REAL_AI", "false")).strip().lower() == "true"
