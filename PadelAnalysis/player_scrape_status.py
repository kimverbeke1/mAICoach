from __future__ import annotations

import inspect
from typing import Any, Callable, Optional

import streamlit as st

import firebase_service as fb


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _display_name(profile: dict | None, player_id: str) -> str:
    profile = profile or {}
    return (
        profile.get("display_name")
        or profile.get("name")
        or profile.get("player_name")
        or str(player_id)
    )


def _scrape_status(player_doc: dict | None) -> dict:
    if not player_doc:
        return {
            "is_scraped": False,
            "matches": 0,
            "interclub": 0,
            "tournament": 0,
            "scraped_at": None,
            "reason": "Nog geen player-document in Firebase.",
        }

    matches = player_doc.get("matches", []) or []
    stats = player_doc.get("stats", {}) or {}
    total_matches = _safe_int(stats.get("total_matches"), len(matches))
    interclub = _safe_int(stats.get("interclub_matches"))
    tournament = _safe_int(stats.get("tournament_matches"))
    scraped_at = (
        player_doc.get("scraped_at")
        or player_doc.get("last_updated")
        or player_doc.get("updated_at")
    )

    is_scraped = total_matches > 0 or len(matches) > 0
    return {
        "is_scraped": is_scraped,
        "matches": total_matches or len(matches),
        "interclub": interclub,
        "tournament": tournament,
        "scraped_at": scraped_at,
        "reason": None if is_scraped else "Player-document bestaat, maar bevat nog geen matchdata.",
    }


def _call_scrape_player(player_id: str, progress_callback: Optional[Callable] = None) -> dict:
    from scrape_player import scrape_player

    sig = inspect.signature(scrape_player)
    supported = set(sig.parameters.keys())

    kwargs = {}
    if "player_id" in supported:
        kwargs["player_id"] = str(player_id)
    if "force_full_refresh" in supported:
        kwargs["force_full_refresh"] = False
    if "refresh_recent" in supported:
        kwargs["refresh_recent"] = 2
    if "max_new_periods" in supported:
        kwargs["max_new_periods"] = None
    if "save_to_firebase" in supported:
        kwargs["save_to_firebase"] = True
    if "progress_callback" in supported and progress_callback is not None:
        kwargs["progress_callback"] = progress_callback

    if "player_id" in kwargs:
        return scrape_player(**kwargs)
    return scrape_player(str(player_id), **kwargs)


def render_player_scrape_status(player_id: str, profile: dict | None = None, key_prefix: str = "players") -> None:
    """Visible scrape status + direct scrape action."""
    player_id = str(player_id)

    # Make Streamlit keys unique even if the same player scrape-status block is
    # rendered more than once on the same page.
    occurrence_key = f"_scrape_status_occurrence_{key_prefix}_{player_id}"
    occurrence = int(st.session_state.get(occurrence_key, 0))
    st.session_state[occurrence_key] = occurrence + 1
    unique_prefix = f"{key_prefix}_{occurrence}"

    name = _display_name(profile, player_id)

    try:
        player_doc = fb.get_player(player_id)
    except Exception as e:
        st.warning(f"Scrape-status kon niet geladen worden voor {name}: {e}")
        return

    status = _scrape_status(player_doc)

    st.markdown("#### Scrape-status")
    st.caption(f"Statusblok: {key_prefix} / {player_id}")

    if status["is_scraped"]:
        st.success(
            f"Gescraped: {status['matches']} matchen "
            f"({status['interclub']} interclub, {status['tournament']} tornooi)."
        )
        if status.get("scraped_at"):
            st.caption(f"Laatst gescraped / bijgewerkt: {status['scraped_at']}")
    else:
        st.warning(f"{name} is nog niet gescraped of heeft nog geen matchdata.")
        if status.get("reason"):
            st.caption(status["reason"])

    c1, c2 = st.columns([1, 3])
    with c1:
        run = st.button(
            "Scrape nu" if status["is_scraped"] else "Scrape speler",
            key=f"{unique_prefix}_scrape_now_{player_id}",
            type="secondary" if status["is_scraped"] else "primary",
        )
    with c2:
        if status["is_scraped"]:
            st.caption("Gebruik dit als recente tornooien/interclubresultaten ontbreken.")
        else:
            st.caption("Haalt matchhistoriek op en slaat ze op in Firebase.")

    if not run:
        return

    progress = st.empty()

    def _progress(i=None, total=None, label=None, phase=None):
        try:
            if total:
                progress.info(f"Scraping {name}: {i}/{total} - {label or ''}")
            elif label:
                progress.info(f"Scraping {name}: {label}")
        except Exception:
            pass

    with st.spinner(f"{name} wordt gescraped..."):
        try:
            result = _call_scrape_player(player_id, progress_callback=_progress)
            updated_doc = fb.get_player(player_id)
            new_status = _scrape_status(updated_doc)
            st.success(
                f"Scrape klaar: {new_status['matches']} matchen "
                f"({new_status['interclub']} interclub, {new_status['tournament']} tornooi)."
            )
            if isinstance(result, dict) and result.get("error"):
                st.warning(f"Scraper gaf waarschuwing/fout terug: {result.get('error')}")
            st.rerun()
        except Exception as e:
            st.error(f"Scrape mislukt voor {name}: {e}")
