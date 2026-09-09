# -*- coding: utf-8 -*-
"""
opponent_scout_ui.py
--------------------
PadelAnalysis - Compatibiliteitslaag voor de tegenstanderanalyse.

De volledige implementatie staat in opponent_analysis.py. Dit bestand bestaat
zodat bestaande imports/aanroepen in dashboard.py blijven werken, ongeacht
welke functienaam of signatuur daar gebruikt wordt.

Werkende aanroepen (allemaal dezelfde analyse):

    import opponent_scout_ui as scout
    scout.render_scout_block()
    scout.render_scout_block(match, team)          # extra args worden genegeerd
    scout.render_opponent_analysis("Kim Verbeke")
    scout.render()

Elke onbekende attribuutnaam die op render/show/draw/scout/opponent lijkt,
wordt automatisch naar dezelfde renderfunctie gemapt (zie __getattr__ onderaan).
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
        load_matches,
    )
except ImportError:  # bij lokaal draaien vanuit de PadelAnalysis-map
    from opponent_analysis import (  # type: ignore
        render_opponent_analysis as _render,
        render_player_card,
        detect_my_team,
        opponent_of,
        next_match,
        team_players,
        load_matches,
    )

DEFAULT_USER = "Kim Verbeke"


def render_opponent_analysis(*args: Any, **kwargs: Any) -> None:
    """
    Render de volledige tegenstanderanalyse (tabs, auto-scrape, opslag).

    Tolerant voor elke aanroepvorm van dashboard.py: een eerste positioneel
    argument dat een string is wordt als gebruikersnaam gebruikt, al de rest
    wordt genegeerd.
    """
    user_name = kwargs.pop("user_name", None) or kwargs.pop("user", None)

    if user_name is None:
        for arg in args:
            if isinstance(arg, str) and arg.strip():
                user_name = arg
                break

    return _render(user_name=user_name or DEFAULT_USER)


# --- Expliciete aliassen voor bekende namen in dashboard.py ----------------

render_scout_block = render_opponent_analysis
scout_block = render_opponent_analysis
render_opponent_scout = render_opponent_analysis
render_opponent_block = render_opponent_analysis
render_scout = render_opponent_analysis
render_block = render_opponent_analysis
render = render_opponent_analysis
show = render_opponent_analysis
main = render_opponent_analysis
app = render_opponent_analysis

__all__ = [
    "render_scout_block",
    "scout_block",
    "render_opponent_analysis",
    "render_opponent_scout",
    "render_opponent_block",
    "render_scout",
    "render_block",
    "render",
    "show",
    "main",
    "app",
    "render_player_card",
    "detect_my_team",
    "opponent_of",
    "next_match",
    "team_players",
    "load_matches",
]

# --- Vangnet: elke render-achtige naam mapt naar dezelfde functie ----------

_FALLBACK_HINTS = ("render", "show", "draw", "display", "scout", "opponent",
                   "block", "analyse", "analysis", "tegenstander", "ui", "page", "tab")


def __getattr__(name: str):
    """
    Wordt enkel aangeroepen als `name` niet bestaat in deze module.
    Voorkomt AttributeError bij afwijkende functienamen in dashboard.py.
    """
    if name.startswith("_"):
        raise AttributeError(f"module 'opponent_scout_ui' has no attribute '{name}'")
    if any(hint in name.lower() for hint in _FALLBACK_HINTS):
        return render_opponent_analysis
    raise AttributeError(f"module 'opponent_scout_ui' has no attribute '{name}'")


if __name__ == "__main__":
    import streamlit as st

    st.set_page_config(page_title="Tegenstanderanalyse", layout="wide")
    render_opponent_analysis()
