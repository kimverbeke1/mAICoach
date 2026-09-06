from __future__ import annotations
import inspect
import re
from typing import Any, Optional
import pandas as pd
import streamlit as st
import firebase_service as fb

# PADEL_ANALYSIS_COMPACT_INLINE_ACTIONS_V2
def _inject_compact_css() -> None:
    """Reduce whitespace around inline player action tables/popovers."""
    if st.session_state.get("_compact_inline_actions_css_loaded"):
        return
    st.session_state["_compact_inline_actions_css_loaded"] = True
    st.markdown(
        """
        <style>
        /* Compact dataframe-like rows built with st.columns */
        div[data-testid="stHorizontalBlock"] { gap: 0.25rem !important; }
        div[data-testid="stVerticalBlock"] { gap: 0.18rem !important; }
        /* Compact markdown/caption text inside inline action rows */
        div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.05rem !important; }
        div[data-testid="stCaptionContainer"] { margin-top: -0.15rem !important; }
        /* Compact Streamlit buttons, including popover trigger buttons */
        div.stButton > button,
        button[kind="secondary"],
        button[data-testid="stBaseButton-secondary"] {
            min-height: 1.55rem !important;
            padding: 0.10rem 0.35rem !important;
            font-size: 0.78rem !important;
            line-height: 1.05rem !important;
        }
        /* Reduce vertical whitespace around popover buttons */
        div[data-testid="stPopover"] button {
            min-height: 1.55rem !important;
            padding: 0.10rem 0.35rem !important;
            font-size: 0.78rem !important;
            line-height: 1.05rem !important;
        }
        /* Remove excessive spacing around row-level elements */
        .block-container div[data-testid="stElementContainer"] {
            margin-bottom: 0.05rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def _small_text(value) -> None:
    txt = _clean(value) if '_clean' in globals() else str(value or "")
    st.markdown(f"<small>{txt if txt else '-'}</small>", unsafe_allow_html=True)

def _small_header(value) -> None:
    st.markdown(f"<small><b>{value}</b></small>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Normalization / lookup
# -----------------------------------------------------------------------------
def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()

def _strip_rank_suffix(value: str) -> str:
    # e.g. "Benoot Daan (P200)" -> "Benoot Daan"
    return re.sub(r"\s*\([^)]*\)\s*$", "", _clean(value)).strip()

def _norm(value: Any) -> str:
    value = _strip_rank_suffix(str(value or "")).lower()
    value = re.sub(r"[^a-z0-9à-ÿ]+", " ", value)
    return _clean(value)

def _variants(name: str) -> set[str]:
    base = _norm(name)
    parts = base.split()
    out = {base}
    if len(parts) == 2:
        out.add(f"{parts[1]} {parts[0]}")
    if len(parts) > 2:
        # Also try first token moved to end and last token moved to front.
        out.add(" ".join(parts[1:] + parts[:1]))
        out.add(" ".join(parts[-1:] + parts[:-1]))
    return {x for x in out if x}

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
        out = []
        for pid, profile in data.items():
            if isinstance(profile, dict):
                p = dict(profile)
                p.setdefault("player_id", str(pid))
                out.append(p)
        return out
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    return []

def _candidate_names_from_profile(profile: dict) -> list[str]:
    """Extract all plausible display names from profile/player documents.
    Some scraped player documents do not have a top-level display_name, but store it
    under profile/name fields, metadata, or in a nested player_profile object.
    """
    candidates: list[str] = []
    keys = [
        "display_name", "name", "player_name", "full_name", "naam",
        "fullName", "displayName", "speler", "speler_naam",
    ]
    def add(v):
        s = _clean(v)
        if s and s not in candidates and not s.isdigit():
            candidates.append(s)
    for k in keys:
        add(profile.get(k))
    for nested_key in ["profile", "player_profile", "metadata", "info", "person", "player"]:
        nested = profile.get(nested_key)
        if isinstance(nested, dict):
            for k in keys:
                add(nested.get(k))
    # If first/last name fields exist, combine both orders.
    first = _clean(profile.get("first_name") or profile.get("firstname") or profile.get("voornaam"))
    last = _clean(profile.get("last_name") or profile.get("lastname") or profile.get("achternaam"))
    if first and last:
        add(f"{first} {last}")
        add(f"{last} {first}")
    return candidates

def _profile_name(profile: dict) -> str:
    return _clean(
        profile.get("display_name")
        or profile.get("name")
        or profile.get("player_name")
        or profile.get("full_name")
        or profile.get("player_id")
    )

def _profile_id(profile: dict) -> str:
    return _clean(profile.get("player_id") or profile.get("user_id") or profile.get("id"))

def build_profile_lookup(profiles: Optional[list[dict]] = None) -> dict[str, dict]:
    if not profiles:
        profiles = _load_profiles_from_firebase()
    lookup: dict[str, dict] = {}
    for profile in profiles or []:
        if not isinstance(profile, dict):
            continue
        pid = _profile_id(profile)
        name = _profile_name(profile)
        if not pid and not name:
            continue
        p = dict(profile)
        if pid:
            p["player_id"] = pid
        for key in _variants(name):
            lookup[key] = p
        for alias in profile.get("aliases", []) or []:
            for key in _variants(str(alias)):
                lookup[key] = p
    return lookup

def resolve_player_id(name: str, lookup: dict[str, dict], explicit_id: Any = None) -> str:
    explicit = _clean(explicit_id)
    if explicit and explicit.lower() not in {"nan", "none", "-", "–", "?"}:
        return explicit
    for key in _variants(name):
        profile = lookup.get(key)
        if profile:
            return _profile_id(profile)
    return ""

# -----------------------------------------------------------------------------
# Scrape / status
# -----------------------------------------------------------------------------
def player_status(player_id: str) -> dict:
    if not player_id:
        return {"known": False, "scraped": False, "matches": 0, "label": "Niet gekoppeld"}
    try:
        doc = fb.get_player(str(player_id)) or {}
    except Exception:
        doc = {}
    matches = doc.get("matches", []) or []
    stats = doc.get("stats", {}) or {}
    total = _safe_int(stats.get("total_matches"), len(matches))
    scraped = total > 0 or len(matches) > 0
    return {
        "known": True,
        "scraped": scraped,
        "matches": total or len(matches),
        "interclub": _safe_int(stats.get("interclub_matches")),
        "tournament": _safe_int(stats.get("tournament_matches")),
        "label": "Gescraped" if scraped else "Niet gescraped",
        "scraped_at": doc.get("scraped_at") or doc.get("last_updated") or doc.get("updated_at") or "-",
    }

def _call_scrape(player_id: str, full: bool, progress_callback=None) -> dict:
    from scrape_player import scrape_player
    sig = inspect.signature(scrape_player)
    supported = set(sig.parameters.keys())
    kwargs = {}
    if "player_id" in supported:
        kwargs["player_id"] = str(player_id)
    if "force_full_refresh" in supported:
        kwargs["force_full_refresh"] = bool(full)
    if "refresh_recent" in supported:
        # Actual refresh window is decided centrally by scrape_player based on latest known match period.
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

# -----------------------------------------------------------------------------
# PADEL_ANALYSIS_SEARCH_BEFORE_SCRAPE_FALLBACK_2026-09-06
# Nieuw: als een speler ECHT geen gekoppelde player_id heeft (geen profiel EN
# geen expliciete ID meegekregen vanuit de match-data), toonden we voorheen
# enkel "Geen bekende player_id. Voeg deze speler eerst toe via speler
# zoeken." zonder verdere actie -- de gebruiker moest dan zelf naar de
# "Speler toevoegen"-pagina navigeren. Dit voegt een directe "🔍 Opzoeken op
# TVL"-knop toe die de speler eerst opzoekt (net als op de "Speler
# toevoegen"-pagina), een profiel aanmaakt bij een treffer, en daarna
# meteen de normale scrape-flow aanbiedt -- allemaal inline, zonder te
# moeten wisselen van pagina. Vereist een lokale/Playwright-omgeving,
# net als de rest van de zoekfunctionaliteit.
# -----------------------------------------------------------------------------
def _split_name_guess(full_name: str) -> tuple[str, str]:
    """Beste-gok opsplitsing van een volledige naam in (voornaam, achternaam).
    TVL-namen verschijnen vaak als 'Achternaam Voornaam'; we proberen daarom
    het LAATSTE woord als voornaam en de rest als achternaam (meest gangbare
    Belgische weergave op tennisenpadelvlaanderen.be), maar de zoekfunctie
    zelf matcht doorgaans op beide velden samen, dus een exacte opsplitsing
    is niet kritiek -- dit is enkel een startpunt voor de gebruiker."""
    parts = _clean(full_name).split()
    if len(parts) < 2:
        return "", _clean(full_name)
    return parts[-1], " ".join(parts[:-1])

def _render_search_and_link_fallback(display_name: str, key_prefix: str) -> None:
    try:
        from cloud_helpers import is_scraping_available
    except Exception:
        is_scraping_available = lambda: True  # noqa: E731 — als cloud_helpers ontbreekt, toch tonen
    if not is_scraping_available():
        st.caption("Opzoeken op TVL kan enkel lokaal (vereist een browser).")
        return
    search_key = f"{key_prefix}_search_results"
    if st.button("🔍 Opzoeken op TVL", key=f"{key_prefix}_search_btn"):
        guess_first, guess_last = _split_name_guess(display_name)
        with st.spinner(f"'{display_name}' opzoeken op tennisenpadelvlaanderen.be..."):
            try:
                from player_search import search_players
                candidates = search_players(
                    first_name=guess_first, last_name=guess_last,
                    club=None, headless=True, use_cache=False,
                )
                st.session_state[search_key] = candidates
            except Exception as e:
                st.error(f"Zoekfout: {e}")
                st.session_state[search_key] = []
    candidates = st.session_state.get(search_key)
    if candidates is None:
        return
    if not candidates:
        st.caption("Geen resultaten gevonden. Probeer het eventueel manueel via '➕ Speler toevoegen'.")
        return
    for i, c in enumerate(candidates[:5]):
        cand_name = c.get("display_name") or "?"
        cand_club = c.get("club") or ""
        cand_pid = c.get("player_id") or ""
        cand_url = c.get("dashboard_url") or ""
        label = f"{cand_name}" + (f" ({cand_club})" if cand_club else "")
        if st.button(f"➕ {label} — koppelen en scrapen", key=f"{key_prefix}_link_{i}"):
            fb.save_player_profile(
                player_id=str(cand_pid),
                display_name=cand_name,
                club=cand_club or None,
                dashboard_url=cand_url or None,
                aliases=[cand_name, display_name],
            )
            with st.spinner(f"{cand_name} wordt gescraped..."):
                try:
                    _call_scrape(cand_pid, full=True)
                    st.success("Gekoppeld en gescraped.")
                    st.rerun()
                except Exception as e:
                    st.warning(f"Gekoppeld, maar scrape mislukt: {e}")

# -----------------------------------------------------------------------------
# Render components
# -----------------------------------------------------------------------------
def render_player_name_action(name: str, player_id: str, key_prefix: str) -> None:
    _inject_compact_css()
    raw_name = _clean(name) or "-"
    display_name = _strip_rank_suffix(raw_name) or raw_name
    if display_name == "-":
        _small_text("-")
        return
    status = player_status(player_id)
    icon = "✅" if status["scraped"] else ("⚠️" if status["known"] else "❓")
    label = f"{display_name} {icon}"
    if hasattr(st, "popover"):
        with st.popover(label, use_container_width=True):
            _render_action_body(display_name, player_id, status, key_prefix)
    else:
        st.write(label)
        _render_action_body(display_name, player_id, status, key_prefix)

def _render_action_body(name: str, player_id: str, status: dict, key_prefix: str) -> None:
    if not status["known"]:
        # FIX 2026-09-06: i.p.v. hier dood te lopen, bieden we nu een directe
        # "eerst opzoeken op TVL"-actie aan (zie _render_search_and_link_fallback),
        # zodat de gebruiker niet meer manueel naar "Speler toevoegen" hoeft.
        st.caption("Geen bekende player_id voor deze naam.")
        _render_search_and_link_fallback(name, key_prefix)
        return
    if status["scraped"]:
        st.caption(
            f"Gescraped: {status['matches']} matchen. Refresh haalt op vanaf de periode van de laatst bekende match."
        )
        st.caption(f"Interclub: {status.get('interclub', 0)} | Tornooi: {status.get('tournament', 0)}")
        action = "Refresh vanaf laatste match"
        full = False
    else:
        st.caption("Nog niet gescraped")
        action = "Scrape alle data"
        full = True
    if st.button(action, key=f"{key_prefix}_{player_id}_{'full' if full else 'refresh'}"):
        progress = st.empty()
        def _progress(i=None, total=None, label=None, phase=None):
            if total:
                progress.info(f"{name}: {i}/{total} - {label or ''}")
            elif label:
                progress.info(f"{name}: {label}")
        with st.spinner(f"{name} wordt verwerkt..."):
            try:
                _call_scrape(player_id, full=full, progress_callback=_progress)
                st.success("Klaar")
                st.rerun()
            except Exception as e:
                st.error(f"Mislukt: {type(e).__name__}: {e}")

def render_dataframe_with_player_actions(
    df: pd.DataFrame,
    player_columns: list[str],
    profiles: Optional[list[dict]] = None,
    key_prefix: str = "inline_df_actions",
    height_limit: int = 60,
) -> None:
    """Render a compact dataframe-like table with interactive player name cells."""
    _inject_compact_css()
    if df is None or df.empty:
        st.info("Geen data beschikbaar.")
        return
    lookup = build_profile_lookup(profiles)
    shown = df.head(height_limit).copy()
    if len(df) > height_limit:
        st.caption(f"Toont eerste {height_limit} van {len(df)} rijen voor interactieve speleracties.")
    cols = list(shown.columns)
    # Hide ID columns from visual table, but keep them for lookup.
    visible_cols = [c for c in cols if not c.endswith(" ID")]
    weights = []
    for c in visible_cols:
        if c in player_columns:
            weights.append(1.6)
        elif c.lower() in {"score", "w/v", "result", "r1", "r2"}:
            weights.append(0.65)
        elif c.lower() in {"periode"}:
            weights.append(1.6)
        else:
            weights.append(1.0)
    header = st.columns(weights, gap="small")
    for col, label in zip(header, visible_cols):
        _small_header(label)
    for ridx, row in shown.reset_index(drop=True).iterrows():
        row_cols = st.columns(weights, gap="small")
        for cidx, col_name in enumerate(visible_cols):
            value = _clean(row.get(col_name))
            with row_cols[cidx]:
                if col_name in player_columns:
                    pid_col = f"{col_name} ID"
                    explicit_id = row.get(pid_col, "") if pid_col in shown.columns else ""
                    pid = resolve_player_id(value, lookup, explicit_id)
                    render_player_name_action(value, pid, f"{key_prefix}_{ridx}_{cidx}")
                else:
                    _small_text(value if value else "-")

def render_matches_period_table(period_matches: pd.DataFrame, profiles: Optional[list[dict]], key_prefix: str) -> None:
    render_dataframe_with_player_actions(
        period_matches,
        player_columns=["Partner", "Tegenstander 1", "Tegenstander 2"],
        profiles=profiles,
        key_prefix=key_prefix,
        height_limit=100,
    )
