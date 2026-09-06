from __future__ import annotations

import inspect
import re
from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st

import firebase_service as fb


PLAYER_NAME_FIELDS = [
    "partner", "partner_name", "tegenstander 1", "tegenstander 2", "tegenstander1", "tegenstander2",
    "opponent 1", "opponent 2", "opp1_name", "opp2_name", "opp1", "opp2",
    "speler", "player", "player_name", "display_name",
]
PLAYER_ID_FIELDS = [
    "partner_user_id", "partner_id", "player_id", "user_id", "opp1_user_id", "opp2_user_id",
]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm(value: Any) -> str:
    value = _clean(value).lower()
    value = re.sub(r"[^a-z0-9à-ÿ]+", " ", value)
    return _clean(value)


def _name_variants(name: str) -> set[str]:
    n = _norm(name)
    parts = n.split()
    variants = {n}
    if len(parts) == 2:
        variants.add(f"{parts[1]} {parts[0]}")
    return {v for v in variants if v}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _try_call_noargs(names: list[str]) -> Any:
    for name in names:
        fn = getattr(fb, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return None


def _load_profiles_from_firebase() -> list[dict]:
    data = _try_call_noargs([
        "get_player_profiles",
        "get_all_player_profiles",
        "list_player_profiles",
        "load_player_profiles",
        "get_players",
        "get_all_players",
    ])
    if data is None:
        return []
    if isinstance(data, dict):
        profiles = []
        for pid, profile in data.items():
            if isinstance(profile, dict):
                p = dict(profile)
                p.setdefault("player_id", str(pid))
                profiles.append(p)
        return profiles
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _profile_name(profile: dict) -> str:
    return _clean(
        profile.get("display_name")
        or profile.get("name")
        or profile.get("player_name")
        or profile.get("full_name")
        or profile.get("player_id")
    )


def _build_profile_lookup(known_profiles: Optional[list[dict]] = None) -> dict[str, dict]:
    profiles = known_profiles or []
    if not profiles:
        profiles = _load_profiles_from_firebase()

    lookup: dict[str, dict] = {}
    for p in profiles:
        if not isinstance(p, dict):
            continue
        pid = _clean(p.get("player_id") or p.get("user_id"))
        name = _profile_name(p)
        if not pid and not name:
            continue
        enriched = dict(p)
        if pid:
            enriched["player_id"] = pid
        for key in _name_variants(name):
            lookup[key] = enriched
        for alias in p.get("aliases", []) or []:
            for key in _name_variants(str(alias)):
                lookup[key] = enriched
    return lookup


def _status_for_player_id(player_id: str) -> dict:
    try:
        doc = fb.get_player(str(player_id)) or {}
    except Exception:
        doc = {}
    matches = doc.get("matches", []) or []
    stats = doc.get("stats", {}) or {}
    total = _safe_int(stats.get("total_matches"), len(matches))
    interclub = _safe_int(stats.get("interclub_matches"))
    tournament = _safe_int(stats.get("tournament_matches"))
    scraped_at = doc.get("scraped_at") or doc.get("last_updated") or doc.get("updated_at") or "-"
    is_scraped = total > 0 or len(matches) > 0
    return {
        "is_known": bool(player_id),
        "is_scraped": is_scraped,
        "matches": total or len(matches),
        "interclub": interclub,
        "tournament": tournament,
        "scraped_at": scraped_at,
    }


def _call_scrape_player(player_id: str, full: bool = False, progress_callback: Optional[Callable] = None) -> dict:
    from scrape_player import scrape_player

    sig = inspect.signature(scrape_player)
    supported = set(sig.parameters.keys())
    kwargs = {}
    if "player_id" in supported:
        kwargs["player_id"] = str(player_id)
    if "force_full_refresh" in supported:
        kwargs["force_full_refresh"] = bool(full)
    if "refresh_recent" in supported:
        kwargs["refresh_recent"] = 2 if not full else 999
    if "max_new_periods" in supported:
        kwargs["max_new_periods"] = None
    if "save_to_firebase" in supported:
        kwargs["save_to_firebase"] = True
    if "progress_callback" in supported and progress_callback is not None:
        kwargs["progress_callback"] = progress_callback

    if "player_id" in kwargs:
        return scrape_player(**kwargs)
    return scrape_player(str(player_id), **kwargs)


def _extract_players_from_df(df: pd.DataFrame) -> list[dict]:
    players: dict[str, dict] = {}
    if df is None or df.empty:
        return []

    columns_by_norm = {_norm(c): c for c in df.columns}
    relevant_name_cols = [columns_by_norm[c] for c in columns_by_norm if c in PLAYER_NAME_FIELDS or "tegenstander" in c or "partner" in c]

    for _, row in df.iterrows():
        for col in relevant_name_cols:
            name = _clean(row.get(col))
            if not name or name in {"-", "–", "None", "nan"}:
                continue
            key = _norm(name)
            players.setdefault(key, {"name": name, "player_id": None})
    return list(players.values())


def _extract_players_from_records(records: list[dict]) -> list[dict]:
    players: dict[str, dict] = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        row_norm = {_norm(k): k for k in row.keys()}
        for nk, k in row_norm.items():
            if nk in PLAYER_NAME_FIELDS or "tegenstander" in nk or "partner" in nk:
                name = _clean(row.get(k))
                if not name or name in {"-", "–", "None", "nan"}:
                    continue
                players.setdefault(_norm(name), {"name": name, "player_id": None})
    return list(players.values())


def collect_players_from_context(context: dict[str, Any]) -> list[dict]:
    """Collect player-like names from local variables in a dashboard render block."""
    found: dict[str, dict] = {}
    for _, value in context.items():
        if isinstance(value, pd.DataFrame):
            for item in _extract_players_from_df(value):
                found.setdefault(_norm(item["name"]), item)
        elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value[:5]):
            for item in _extract_players_from_records(value):
                found.setdefault(_norm(item["name"]), item)
    return list(found.values())


def render_player_action(name: str, player_id: Optional[str], key_prefix: str, profile_lookup: dict[str, dict]) -> None:
    resolved_pid = _clean(player_id)
    profile = None
    if not resolved_pid:
        for variant in _name_variants(name):
            profile = profile_lookup.get(variant)
            if profile:
                resolved_pid = _clean(profile.get("player_id") or profile.get("user_id"))
                break

    status = _status_for_player_id(resolved_pid) if resolved_pid else {
        "is_known": False,
        "is_scraped": False,
        "matches": 0,
        "interclub": 0,
        "tournament": 0,
        "scraped_at": "-",
    }

    c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 1.6])
    c1.write(f"**{name}**")
    if not resolved_pid:
        c2.warning("Niet gekoppeld")
        c3.write("-")
        c4.caption("Geen player_id")
        return

    if status["is_scraped"]:
        c2.success("Gescraped")
        c3.write(f"{status['matches']} matchen")
        label = "Refresh"
        full = False
    else:
        c2.warning("Niet gescraped")
        c3.write("0 matchen")
        label = "Scrape"
        full = True

    if c4.button(label, key=f"{key_prefix}_{resolved_pid}_{label.lower()}"):
        progress = st.empty()

        def _progress(i=None, total=None, label=None, phase=None):
            if total:
                progress.info(f"{name}: {i}/{total} - {label or ''}")
            elif label:
                progress.info(f"{name}: {label}")

        with st.spinner(f"{name} wordt gescraped..."):
            try:
                _call_scrape_player(resolved_pid, full=full, progress_callback=_progress)
                st.success(f"Klaar: {name}")
                st.rerun()
            except Exception as e:
                st.error(f"Scrape mislukt voor {name}: {type(e).__name__}: {e}")


def render_player_actions_from_context(
    context: dict[str, Any],
    known_profiles: Optional[list[dict]] = None,
    key_prefix: str = "player_actions",
    title: str = "Speleracties in deze tabel",
    max_players: int = 30,
) -> None:
    players = collect_players_from_context(context)
    if not players:
        return

    lookup = _build_profile_lookup(known_profiles)

    # Enrich and sort: unknown first, then non-scraped, then scraped.
    enriched = []
    for p in players:
        name = p["name"]
        pid = p.get("player_id")
        if not pid:
            for variant in _name_variants(name):
                prof = lookup.get(variant)
                if prof:
                    pid = _clean(prof.get("player_id") or prof.get("user_id"))
                    break
        status = _status_for_player_id(pid) if pid else {"is_scraped": False, "is_known": False, "matches": 0}
        enriched.append({"name": name, "player_id": pid, "status": status})

    enriched.sort(key=lambda x: (bool(x["player_id"]), x["status"].get("is_scraped", False), _norm(x["name"])))
    enriched = enriched[:max_players]

    with st.expander(title, expanded=True):
        st.caption("Per spelernaam in deze tabel: status + directe scrape/refresh actie. Scrapen vereist een gekende player_id.")
        for idx, item in enumerate(enriched):
            render_player_action(
                item["name"],
                item.get("player_id"),
                key_prefix=f"{key_prefix}_{idx}",
                profile_lookup=lookup,
            )
