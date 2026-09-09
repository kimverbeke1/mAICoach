# -*- coding: utf-8 -*-
"""
opponent_scout_ui.py
--------------------
PadelAnalysis - Compatibiliteitslaag voor de tegenstanderanalyse.

De volledige implementatie staat in opponent_analysis.py. Dit bestand bestaat
enkel zodat bestaande imports in dashboard.py blijven werken, ongeacht welke
functienaam daar gebruikt wordt.

Alle onderstaande namen wijzen naar dezelfde renderfunctie:

    from opponent_scout_ui import render_opponent_analysis
    from opponent_scout_ui import render_opponent_scout
    from opponent_scout_ui import render
    from opponent_scout_ui import main
    from opponent_scout_ui import show
"""

from __future__ import annotations

from typing import Any

try:
    from PadelAnalysis.opponent_analysis import (  # type: ignore
        render_opponent_analysis as _render,
        render_player_card,
        detect_my_team,
        opponent_of,
        next_match,
        team_players,
    )
except ImportError:  # bij lokaal draaien vanuit de PadelAnalysis-map
    from opponent_analysis import (  # type: ignore
        render_opponent_analysis as _render,
        render_player_card,
        detect_my_team,
        opponent_of,
        next_match,
        team_players,
    )

DEFAULT_USER = "Kim Verbeke"


def render_opponent_analysis(user_name: str = DEFAULT_USER, **kwargs: Any) -> None:
    """Render de volledige tegenstanderanalyse (tabs + auto-scrape)."""
    return _render(user_name=user_name)


# Aliassen voor oudere/andere importnamen in dashboard.py
render_opponent_scout = render_opponent_analysis
render_scout = render_opponent_analysis
render = render_opponent_analysis
show = render_opponent_analysis
main = render_opponent_analysis
app = render_opponent_analysis

__all__ = [
    "render_opponent_analysis",
    "render_opponent_scout",
    "render_scout",
    "render",
    "show",
    "main",
    "app",
    "render_player_card",
    "detect_my_team",
    "opponent_of",
    "next_match",
    "team_players",
]


if __name__ == "__main__":
    import streamlit as st

    st.set_page_config(page_title="Tegenstanderanalyse", layout="wide")
    render_opponent_analysis()
