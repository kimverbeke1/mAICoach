# -*- coding: utf-8 -*-
"""Adapter die de mAICoach-gezondheidsmodule aanbiedt aan streamlit_app.py.

Plaats dit bestand als: AICoach/dashboard/app.py

Herbruikt render_health_app() rechtstreeks uit training_dashboard.py, zodat er
maar één plek is waar de UI-structuur (titel, sync, tabs, vergelijkingstab)
gedefinieerd staat. Dat voorkomt dubbele rendering en zorgt dat losse en
gecombineerde uitvoering altijd identiek zijn.
"""

from __future__ import annotations

from AICoach.dashboard.training_dashboard import render_health_app

__all__ = ["render_health_app"]
