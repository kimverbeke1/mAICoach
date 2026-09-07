from __future__ import annotations
import inspect
import re
from typing import Any, Optional
import pandas as pd
import streamlit as st
import firebase_service as fb
import scrape_jobs as sj
# PADEL_ANALYSIS_COMPACT_INLINE_ACTIONS_V2
def _inject_compact_css() -> None:
    """Reduce whitespace around inline player action tables/popovers."""
    if st.session_state.get("_compact_inline_actions_css_loaded"):
        return
    st.session_state["_compact_inline_actions_css_loaded"] = True
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"] { gap: 0.25rem !important; }
        div[data-testid="stVerticalBlock"] { gap: 0.18rem !important; }
        div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.05rem !important; }
        div[data-testid="stCaptionContainer"] { margin-top: -0.15rem !important; }
        div.stButton > button,
        button[kind="secondary"],
        button[data-testid="stBaseButton-secondary"] {
            min-height: 1.55rem !important;
            padding: 0.10rem 0.35rem !important;
            font-size: 0.78rem !important;
            line-height: 1.05rem !important;
        }
        div[data-testid="stPopover"] button {
            min-height: 1.55rem !important;
            padding: 0.10rem 0.35rem !important;
            font-size: 0.78rem !important;
            line-height: 1.05rem !important;
        }
        .block-container div[data-testid="stElementContainer"] {
            margin-bottom: 0.05rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
# -----------------------------------------------------------------------------
# Normalization / lookup
# -----------------------------------------------------------------------------
def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()
def _strip_rank_suffix(value: str) -> str:
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
# -----------------------------------------------------------------------------
# PADEL_ANALYSIS_SEARCH_BEFORE_SCRAPE_FALLBACK_2026-09-06
# -----------------------------------------------------------------------------
def _split_name_guess(full_name: str) -> tuple[str, str]:
    """Beste-gok opsplitsing van een volledige naam in (voornaam, achternaam)."""
    parts = _clean(full_name).split()
    if len(parts) < 2:
        return "", _clean(full_name)
    return parts[-1], " ".join(parts[:-1])
def _render_search_and_link_fallback(display_name: str, key_prefix: str) -> None:
    # PADEL_ANALYSIS_CLOUD_SEARCH_FALLBACK_FIX_2026-09-07
    # BUG/wens (opgelost): op Streamlit Community Cloud toonde deze fallback
    # enkel de dode melding "Opzoeken op TVL kan enkel lokaal (vereist een
    # browser)" wanneer er nog geen player_id gekend was voor een naam. Dat
    # is technisch juist (de cloud-app zelf heeft geen Playwright/browser),
    # maar misleidend: het lijkt alsof je niets kunt doen, terwijl de app
    # WEL een externe GitHub Actions-workflow kan triggeren die dat op een
    # ubuntu-runner mét browser doet (zie cloud_helpers.py /
    # scrape-padel.yml). Vandaar dat "opzoeken vroeger al eens lukte".
    #
    # Fix: als scrapen lokaal niet kan (cloud) maar de GitHub-trigger wél
    # geconfigureerd is, tonen we nu een knop die de bestaande workflow start
    # in "new_users"-modus (spelers zoeken/toevoegen op TVL). Zo verdwijnt de
    # misleidende melding en kan het opzoeken/toevoegen ook vanaf de cloud.
    # We gebruiken ENKEL de reeds ondersteunde workflow-inputs (player_ids +
    # mode), zodat er niets aan de workflow-definitie hoeft te wijzigen.
    try:
        from cloud_helpers import is_scraping_available
    except Exception:
        is_scraping_available = lambda: True  # noqa: E731
    if not is_scraping_available():
        _render_cloud_search_trigger(display_name, key_prefix)
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
            # FIX 2026-09-06: ook hier achtergrond-scrape i.p.v. blokkerend.
            sj.start_background_scrape(str(cand_pid), cand_name, full=True)
            st.success(f"Gekoppeld. {cand_name} wordt nu op de achtergrond gescraped (zie melding bovenaan).")
            st.rerun()
def _render_cloud_search_trigger(display_name: str, key_prefix: str) -> None:
    """Cloud-variant van de opzoek-fallback: geen lokale browser, maar wel de
    bestaande GitHub Actions-workflow triggeren (indien geconfigureerd)."""
    try:
        from cloud_helpers import is_github_trigger_configured, render_cloud_scrape_trigger
    except Exception:
        is_github_trigger_configured = lambda: False  # noqa: E731
        render_cloud_scrape_trigger = None
    if not (render_cloud_scrape_trigger and is_github_trigger_configured()):
        # Geen GitHub-trigger geconfigureerd -> eerlijk blijven over de
        # cloud-beperking, maar met een duidelijk alternatief.
        st.caption(
            "Nieuwe spelers opzoeken vereist een browser en kan daarom niet "
            "rechtstreeks vanaf de cloud. Doe dit lokaal via '➕ Speler "
            "toevoegen', of configureer de GitHub Actions-trigger om het "
            "vanaf de cloud te kunnen starten."
        )
        return
    st.caption(
        f"'{_clean(display_name)}' is nog niet gekend. Op de cloud gebeurt het "
        "opzoeken/toevoegen via GitHub Actions (ubuntu-runner met browser)."
    )
    # "new_users"-modus laat de workflow nieuwe spelers zoeken/toevoegen op TVL.
    render_cloud_scrape_trigger(
        key_prefix=f"{key_prefix}_cloud_search",
        mode="new_users",
        label="🔍 Opzoeken & toevoegen via GitHub Actions",
    )
# -----------------------------------------------------------------------------
# Render components
# -----------------------------------------------------------------------------
def render_player_name_action(name: str, player_id: str, key_prefix: str) -> None:
    _inject_compact_css()
    raw_name = _clean(name) or "-"
    display_name = _strip_rank_suffix(raw_name) or raw_name
    if display_name == "-":
        st.caption("-")
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
    """
    PADEL_ANALYSIS_BACKGROUND_SCRAPE_2026-09-06:
    BUG/wens (opgelost): scrapes gestart vanuit een popover in een tabel
    blokkeerden voorheen de hele app tot ze klaar waren. Nu wordt de scrape
    gestart op de achtergrond (scrape_jobs.py); de popover sluit meteen (via
    st.rerun()) en de voortgang is zichtbaar via de banner bovenaan de
    pagina, ongeacht waar je nadien naartoe klikt.
    """
    if not status["known"]:
        st.caption("Geen bekende player_id voor deze naam.")
        _render_search_and_link_fallback(name, key_prefix)
        return
    is_running = sj.is_scrape_running(player_id)
    if is_running:
        st.caption("⏳ Wordt al ververst op de achtergrond — zie melding bovenaan de pagina.")
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
        sj.start_background_scrape(str(player_id), name, full=full)
        st.rerun()
def _dataframe_kwargs(**kwargs):
    """Use Streamlit's new width API, with fallback for older versions."""
    try:
        if "width" in inspect.signature(st.dataframe).parameters:
            kwargs["width"] = "stretch"
        else:
            kwargs["use_container_width"] = True
    except Exception:
        kwargs["use_container_width"] = True
    return kwargs
def render_dataframe_with_player_actions(
    df: pd.DataFrame,
    player_columns: list[str],
    profiles: Optional[list[dict]] = None,
    key_prefix: str = "inline_df_actions",
    height_limit: int = 60,
) -> None:
    """
    Render a compact, sortable table with interactive player-name actions.
    PADEL_ANALYSIS_TABLE_RENDER_FIX_2026-09-06:
    BUG (opgelost): deze tabel werd voorheen rij per rij opgebouwd met een
    APARTE st.columns()-aanroep voor de header EN nog eens een aparte
    st.columns()-aanroep per databader ("titels zweven boven de rijen").
    Streamlit behandelt elke st.columns()-aanroep als een onafhankelijk
    layout-blok; zodra de popover-knoppen in de datarijen een andere hoogte
    hadden dan de headertekst (wat bij deze speleracties-popovers vrijwel
    altijd het geval is), kwam de header visueel los van de rest van de
    tabel te staan.
    Fix: gebruik nu hetzelfde, al werkende patroon als de Match
    Explorer-tab (zie lineup_quick.py: _render_selectable_table_with_detail):
    één enkele st.dataframe(...) voor de volledige tabel (header en rijen
    horen dan gegarandeerd bij elkaar, correcte sortering inbegrepen), met
    rijselectie. Klik je op een rij, dan verschijnen de klikbare
    speleracties (scrape-status, refresh-knop, opzoeken...) voor de
    spelerskolommen van DIE rij eronder — functioneel identiek aan
    voorheen, maar zonder het layout-probleem.
    """
    _inject_compact_css()
    if df is None or df.empty:
        st.info("Geen data beschikbaar.")
        return
    lookup = build_profile_lookup(profiles)
    shown = df.head(height_limit).copy()
    if len(df) > height_limit:
        st.caption(f"Toont eerste {height_limit} van {len(df)} rijen voor interactieve speleracties.")
    shown = shown.reset_index(drop=True)
    visible_cols = [c for c in shown.columns if not c.endswith(" ID")]
    display_df = shown[visible_cols]
    event = st.dataframe(
        display_df,
        **_dataframe_kwargs(
            hide_index=True,
            height=min(360, 40 + len(display_df) * 36),
            on_select="rerun",
            selection_mode="single-row",
        ),
        key=f"{key_prefix}_table",
    )
    sel_rows = (event or {}).get("selection", {}).get("rows", [])
    if not sel_rows:
        st.caption("👉 Klik op een rij voor speleracties (scrape-status, refresh, opzoeken).")
        return
    idx = sel_rows[0]
    row = shown.iloc[idx]
    st.markdown("**Speleracties voor geselecteerde rij:**")
    relevant_player_cols = [c for c in player_columns if c in shown.columns]
    if not relevant_player_cols:
        return
    action_cols = st.columns(min(len(relevant_player_cols), 3) or 1)
    for i, col_name in enumerate(relevant_player_cols):
        with action_cols[i % len(action_cols)]:
            st.caption(col_name)
            value = _clean(row.get(col_name))
            pid_col = f"{col_name} ID"
            explicit_id = row.get(pid_col, "") if pid_col in shown.columns else ""
            pid = resolve_player_id(value, lookup, explicit_id)
            render_player_name_action(value, pid, key_prefix=f"{key_prefix}_detail_{idx}_{i}")
def render_matches_period_table(period_matches: pd.DataFrame, profiles: Optional[list[dict]], key_prefix: str) -> None:
    render_dataframe_with_player_actions(
        period_matches,
        player_columns=["Partner", "Tegenstander 1", "Tegenstander 2"],
        profiles=profiles,
        key_prefix=key_prefix,
        height_limit=100,
    )
