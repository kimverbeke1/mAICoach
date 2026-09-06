"""
dashboard.py  —  PadelAnalysis v2 Streamlit dashboard

Schema v2: matches zitten in doc.matches (niet doc.raw_data.matches)
Stats: total_matches, tournament_matches, interclub_matches, wins, losses, winrate
"""

import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st
from datetime import datetime
# Path setup
_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb
import lineup_lab as ll
import schedule_scraper as ss
import opponent_scout as osc
import lineup_quick as lq
import player_inline_actions as pia

try:
    st.set_page_config(page_title="Padel Analysis", page_icon="🎾", layout="wide", initial_sidebar_state="collapsed")
except Exception:
    pass

# ─────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* Clean card-style metric */
[data-testid="stMetric"] {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 12px 16px;
    border-left: 4px solid #1a73e8;
}
[data-testid="stMetricLabel"] { font-size: 0.75rem; color: #666; }
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }

/* Tab styling */
.stTabs [data-baseweb="tab"] { font-size: 0.85rem; padding: 6px 14px; }
.stTabs [aria-selected="true"] { border-bottom: 3px solid #1a73e8 !important; }

/* Win badge */
.badge-win  { background:#d4edda; color:#155724; border-radius:4px; padding:2px 8px; font-size:0.8rem; font-weight:600; }
.badge-loss { background:#f8d7da; color:#721c24; border-radius:4px; padding:2px 8px; font-size:0.8rem; font-weight:600; }

/* Section header */
.section-header { font-size:1.1rem; font-weight:700; margin-bottom:8px; color:#1a1a1a; border-bottom:2px solid #e0e0e0; padding-bottom:4px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _clean(text) -> str:
    return " ".join(str(text or "").split()).strip()


_SEASON_RANK = {"winter": 0, "voorjaar": 1, "lente": 1, "zomer": 2, "najaar": 3, "herfst": 3}
_MONTH_RANK = {
    "jan": 1, "feb": 2, "mrt": 3, "maart": 3, "apr": 4, "mei": 5, "jun": 6, "juni": 6,
    "jul": 7, "juli": 7, "aug": 8, "sep": 9, "sept": 9, "okt": 10, "nov": 11, "dec": 12,
}

def _format_scraped_at(value):
    """
    Formatteert een Firestore timestamp of ISO-string
    naar een leesbare datum/tijd.
    """
    if not value:
        return "onbekend"

    try:
        # datetime / Firestore timestamp
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y %H:%M")

        # ISO string
        if isinstance(value, str):
            cleaned = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            return dt.strftime("%d/%m/%Y %H:%M")

        return str(value)

    except Exception:
        return str(value)
    
def _short_period_label(label: str) -> str:
    return str(label or "").replace("Resultaten van ", "").strip()


def _period_sort_key(label: str):
    """
    Sorteersleutel (jaar, sub-rang) voor periode-labels. Robuust opgezet: we
    weten het exacte labelformaat niet 100% zeker, dus zoeken we naar een
    jaartal + een seizoens- of maandnaam ergens in de tekst, in plaats van een
    strikt patroon te verwachten. Onherkenbare labels belanden samen
    onderaan in plaats van de hele sortering te verstoren.
    """
    text = str(label or "").lower()
    year_m = re.search(r"(20\d{2})", text)
    year = int(year_m.group(1)) if year_m else 0
    sub_rank = next((r for kw, r in _SEASON_RANK.items() if kw in text), None)
    if sub_rank is None:
        sub_rank = next((r for kw, r in _MONTH_RANK.items() if kw in text), 50)
    return (year, sub_rank)


def _display_name(profile_or_id, name_lookup: Optional[dict] = None) -> str:
    """Geeft altijd een leesbare naam terug, nooit een blote ID, met een duidelijke fallback."""
    if isinstance(profile_or_id, dict):
        return profile_or_id.get("display_name") or f"Onbekende speler ({profile_or_id.get('player_id','?')})"
    pid = profile_or_id
    if name_lookup:
        name = name_lookup.get(pid)
        if name:
            return name
    return f"Onbekende speler ({pid})"


def _go_to_player(player_id: str):
    """Springt naar de Spelers-pagina met deze speler vooraf geselecteerd."""
    st.session_state["jump_to_player_id"] = str(player_id)
    st.session_state["page"] = "🔍 Spelers"
    st.rerun()


def _scrape_progress_widget(label_prefix: str = ""):
    """
    Maakt een Streamlit progress-bar + bijhorende callback compatibel met
    scrape_player(progress_callback=...). Toont WAT er bezig is (periode X/Y,
    bezig met ophalen/parsen), in plaats van enkel een statische spinner.
    """
    bar = st.progress(0.0, text=f"{label_prefix}Starten...")

    def _cb(i, total, label, status):
        if total > 0:
            frac = min(1.0, i / total)
        else:
            frac = 0.0
        status_txt = {
            "starting": "voorbereiden", "discovering": "periodes opzoeken",
            "fetching": "ophalen", "parsing": "verwerken", "ok": "klaar",
            "empty": "leeg", "error": "fout", "done": "klaar",
        }.get(status, status)
        suffix = f" ({i}/{total})" if total else ""
        bar.progress(frac, text=f"{label_prefix}{status_txt}{suffix} — {label[:50]}")

    return bar, _cb


def _matches_to_df(matches: list) -> pd.DataFrame:
    """Convert v2 match list to a clean DataFrame."""
    if not matches:
        return pd.DataFrame()
    rows = []
    for m in matches:
        rows.append({
            "type":            m.get("match_type", ""),
            "period":          _short_period_label(m.get("period_label", "")),
            "datum":           m.get("tournament_date_start") or m.get("match_date") or "",
            "week":            m.get("tournament_week") or "",
            "toernooi":        m.get("tournament_name") or m.get("competition_name") or "",
            "reeks":           m.get("reeks_name") or "",
            "ronde":           m.get("round_text") or "",
            "partner":         m.get("partner_name") or "",
            "partner_id":      m.get("partner_user_id") or "",
            "opp1":            m.get("opp1_name") or "",
            "opp1_id":         m.get("opp1_user_id") or "",
            "opp2":            m.get("opp2_name") or "",
            "opp2_id":         m.get("opp2_user_id") or "",
            "opp1_ranking":    m.get("opp1_ranking") or "",
            "opp2_ranking":    m.get("opp2_ranking") or "",
            "score":           m.get("score") or "",
            "result":          m.get("result") or "",
            "won":             m.get("won"),
            "reeks_url":       m.get("reeks_url") or "",
            "reeks_id":        m.get("reeks_id") or "",
            "tornooi_id":      m.get("tornooi_id") or "",
            "encounter":       m.get("encounter") or "",
            "uitslagenblad":   m.get("uitslagenblad_url") or "",
        })
    return pd.DataFrame(rows)


def _winrate_str(wins, losses) -> str:
    known = wins + losses
    if known == 0:
        return "–"
    return f"{round(wins / known * 100, 1)}%"


def _render_metrics(total, wins, losses, t_matches, ic_matches):
    cols = st.columns(5)
    cols[0].metric("Totaal matches", total)
    cols[1].metric("Winst", wins)
    cols[2].metric("Verlies", losses)
    cols[3].metric("Winrate", _winrate_str(wins, losses))
    cols[4].metric("Tornooi / Interclub", f"{t_matches} / {ic_matches}")


def _summarize_partner(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "partner" not in df.columns:
        return pd.DataFrame()
    sub = df[df["partner"].str.strip().ne("")].copy()
    if sub.empty:
        return pd.DataFrame()
    g = sub.groupby("partner").agg(
        matches=("won", "count"),
        wins=("won", lambda x: x.eq(True).sum()),
        losses=("won", lambda x: x.eq(False).sum()),
    ).reset_index()
    g["winrate"] = g.apply(lambda r: _winrate_str(r.wins, r.losses), axis=1)
    known = g["wins"] + g["losses"]
    g["_wr_num"] = g["wins"] / known.replace(0, 1)
    result = g.sort_values(["_wr_num", "matches"], ascending=[False, False]).drop(columns=["_wr_num"])
    return result


def _summarize_opponents(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for _, r in df.iterrows():
        for col in ["opp1", "opp2"]:
            name = str(r.get(col, "")).strip()
            if name:
                rows.append({"tegenstander": name, "won": r.get("won")})
    if not rows:
        return pd.DataFrame()
    tmp = pd.DataFrame(rows)
    g = tmp.groupby("tegenstander").agg(
        matches=("won", "count"),
        wins=("won", lambda x: x.eq(True).sum()),
        losses=("won", lambda x: x.eq(False).sum()),
    ).reset_index()
    g["winrate"] = g.apply(lambda r: _winrate_str(r.wins, r.losses), axis=1)
    known = g["wins"] + g["losses"]
    g["_wr_num"] = g["wins"] / known.replace(0, 1)
    result = g.sort_values(["_wr_num", "matches"], ascending=[False, False]).drop(columns=["_wr_num"])
    return result


def _render_table(df: pd.DataFrame, name_col: str, height=400):
    # PADEL_ANALYSIS_RENDER_TABLE_INLINE_ACTIONS
    if df.empty:
        st.info("Geen data beschikbaar.")
        return

    # The partner/opponent analysis tables use this shared renderer. Make the name
    # column interactive here so every partner/opponent table gets scrape/refresh.
    try:
        display_df = df.copy()
        id_candidates = [
            f"{name_col} ID", "Player ID", "player_id", "user_id", "partner_id",
            "partner_user_id", "opp1_id", "opp1_user_id", "opp2_id", "opp2_user_id",
        ]
        for id_col in id_candidates:
            if id_col in display_df.columns and f"{name_col} ID" not in display_df.columns:
                display_df[f"{name_col} ID"] = display_df[id_col]
                break

        pia.render_dataframe_with_player_actions(
            display_df,
            player_columns=[name_col],
            profiles=_get_all_profiles(),
            key_prefix=f"render_table_actions_{name_col}",
            height_limit=80,
        )
        return
    except Exception as e:
        st.warning(f"Interactieve speleracties niet beschikbaar: {type(e).__name__}: {e}")

    # Fallback to original dataframe behavior.
    st.dataframe(
        df,
        use_container_width=True,
        height=min(height, 40 + len(df) * 36),
        hide_index=True,
        column_config={
            name_col: st.column_config.TextColumn(name_col, width="large"),
            "matches": st.column_config.NumberColumn("M", width="small"),
            "wins":    st.column_config.NumberColumn("W", width="small"),
            "losses":  st.column_config.NumberColumn("L", width="small"),
            "winrate": st.column_config.TextColumn("WR", width="small"),
        },
    )


# ─────────────────────────────────────────────
# State helpers
# ─────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Wedstrijdschema ophalen...")
def _load_poule_fixtures(reeks_url: str):
    """Haalt en parset het publieke poule-schema. Returns (fixtures, error_message_or_None)."""
    try:
        html = ss.fetch_poule_schedule_html(reeks_url, delay=0.5)
        fixtures = ss.parse_poule_schedule(html)
        return fixtures, None
    except Exception as e:
        return [], str(e)


def _clean_name(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _get_all_profiles() -> list:
    try:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        return [d.to_dict() for d in docs]
    except Exception:
        return []


# ─────────────────────────────────────────────
# Navigation
# ─────────────────────────────────────────────

PAGES = ["👤 Mijn profiel", "🔍 Spelers", "➕ Speler toevoegen", "🧩 Opstelling-analyse"]

if "page" not in st.session_state:
    st.session_state["page"] = PAGES[0]

# Top nav bar
nav_col = st.columns(len(PAGES))
for i, p in enumerate(PAGES):
    if nav_col[i].button(p, use_container_width=True,
                          type="primary" if st.session_state["page"] == p else "secondary"):
        st.session_state["page"] = p
        st.rerun()

st.divider()
page = st.session_state["page"]


# ═══════════════════════════════════════════════
# PAGE: Speler toevoegen
# ═══════════════════════════════════════════════

def page_add_player():
    st.header("➕ Speler toevoegen")
    st.caption("Zoek een speler op de TVL-website en voeg hem/haar toe aan de database.")

    with st.form("search_form"):
        c1, c2, c3 = st.columns([2, 2, 2])
        first = c1.text_input("Voornaam")
        last  = c2.text_input("Achternaam")
        club  = c3.text_input("Club (optioneel)")
        submitted = st.form_submit_button("🔍 Zoek op TVL-website", use_container_width=True, type="primary")

    if submitted:
        if not _clean(first) and not _clean(last):
            st.warning("Geef minstens een voornaam of achternaam in.")
            return

        with st.spinner("Zoeken op tennisenpadelvlaanderen.be..."):
            try:
                from player_search import search_players
                candidates = search_players(
                    first_name=first, last_name=last,
                    club=_clean(club) or None,
                    headless=True, use_cache=False,
                )
                st.session_state["add_candidates"] = candidates
                st.session_state["add_search_done"] = True
            except Exception as e:
                st.error(f"Zoekfout: {e}")
                return

    candidates = st.session_state.get("add_candidates", [])
    if not st.session_state.get("add_search_done"):
        return

    if not candidates:
        st.warning("Geen spelers gevonden op TVL.")
        return

    st.success(f"{len(candidates)} kandidaat(en) gevonden")

    for i, c in enumerate(candidates):
        name = c.get("display_name") or "?"
        club_str = c.get("club") or ""
        pid = c.get("player_id") or "?"
        url = c.get("dashboard_url") or ""

        with st.container(border=True):
            col_info, col_btn = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{name}**")
                if club_str:
                    st.caption(f"🏟️ {club_str} · ID: {pid}")
                else:
                    st.caption(f"ID: {pid}")
                if url:
                    st.markdown(f"[Profiel op TVL ↗]({url})", unsafe_allow_html=False)
            with col_btn:
                scrape_key = f"scrape_{i}"
                do_scrape = st.checkbox("Direct scrapen", key=scrape_key, value=True)
                if st.button("➕ Toevoegen", key=f"add_{i}", use_container_width=True, type="primary"):
                    # Save profile
                    fb.save_player_profile(
                        player_id=str(pid),
                        display_name=name,
                        club=club_str or None,
                        dashboard_url=url or None,
                        aliases=[name],
                    )
                    if do_scrape:
                        bar, cb = _scrape_progress_widget(label_prefix=f"{name}: ")
                        try:
                            from scrape_player import scrape_player as _scrape
                            result = _scrape(str(pid), save_to_firebase=True, progress_callback=cb)
                            bar.progress(1.0, text="Klaar.")
                            s = result.get("stats", {})
                            st.success(
                                f"✅ {name} toegevoegd — "
                                f"{s.get('total_matches',0)} matches, "
                                f"winrate {s.get('winrate',0)}%"
                            )
                        except Exception as e:
                            st.warning(f"Profiel opgeslagen, scrape mislukt: {e}")
                    else:
                        st.success(f"✅ {name} toegevoegd (nog niet gescraped)")

    st.divider()
    st.subheader("🔄 Meerdere spelers verversen")
    st.caption("Voor onderhoud: vernieuw in bulk (enkel nieuwe periodes per speler, sequentieel met pauze).")
    all_profiles = _get_all_profiles()
    if all_profiles:
        bulk_options = {
            f"{_display_name(p)} ({p.get('player_id','?')})": p.get("player_id")
            for p in sorted(all_profiles, key=lambda x: x.get("display_name") or "")
        }
        bulk_chosen = st.multiselect("Kies spelers", list(bulk_options.keys()), key="bulk_scrape_select")

        if bulk_chosen and st.button("▶️ Verversen", type="primary", use_container_width=True):
            overall = st.progress(0.0, text="Starten...")
            for i, label in enumerate(bulk_chosen):
                mid = bulk_options[label]
                _, cb = _scrape_progress_widget(label_prefix=f"{label}: ")
                try:
                    from scrape_player import scrape_player as _scrape
                    result = _scrape(str(mid), force_full_refresh=False, save_to_firebase=True, progress_callback=cb)
                    s = result.get("stats", {})
                    st.write(f"  ✅ {label}: {s.get('total_matches',0)} matches, winrate {s.get('winrate',0)}%")
                except Exception as e:
                    st.write(f"  ❌ {label}: {e}")
                overall.progress((i + 1) / len(bulk_chosen), text=f"({i+1}/{len(bulk_chosen)}) spelers verwerkt")
            st.success("Bulk-verversing voltooid.")


# ═══════════════════════════════════════════════
# PAGE: Opstelling-analyse (Fase 1 — retrospectieve test-tool)
# ═══════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner="Ontmoetingen ophalen...")
def _load_encounter_index(profile_ids: tuple):
    docs = ll.get_docs_for_players(list(profile_ids))
    index = ll.build_encounter_index(docs)
    return docs, index


def page_lineup_lab():
    st.header("🧩 Opstelling-analyse")

    profiles = _get_all_profiles()
    if not profiles:
        st.info("Nog geen spelers in de database. Voeg eerst spelers toe via '➕ Speler toevoegen'.")
        return

    name_lookup_global = {p.get("player_id"): _display_name(p) for p in profiles}
    profile_map = {_display_name(p): p for p in sorted(profiles, key=lambda x: x.get("display_name") or "")}

    # ── Voor wie tonen we dit? ──
    settings = fb.get_app_settings()
    home_id = settings.get("home_player_id")
    home_label = next((lbl for lbl, p in profile_map.items() if p.get("player_id") == home_id), None)
    labels = list(profile_map.keys())
    default_idx = labels.index(home_label) if home_label in labels else 0

    sel_label = st.selectbox("Toon analyse voor:", labels, index=default_idx)
    sel_profile = profile_map[sel_label]
    sel_player_id = sel_profile.get("player_id")
    lq.render_lineup_quick_results(
        sel_player_id=str(sel_player_id),
        sel_label=sel_label,
        profiles=profiles,
        name_lookup_global=name_lookup_global,
        display_name_fn=_display_name,
    )


    # ═══════════════════════════════════════
    # Volgende match
    # ═══════════════════════════════════════
    st.markdown('<div class="section-header">📅 Volgende match</div>', unsafe_allow_html=True)

    sel_doc = fb.get_player(sel_player_id)
    own_interclub_matches = [
        m for m in (sel_doc or {}).get("matches", [])
        if m.get("match_type") == "interclub" and m.get("reeks_url")
    ]
    if not own_interclub_matches:
        st.info(f"Geen interclub-matches met een poule-link gevonden voor {sel_label}. Vernieuw dit profiel eerst.")
        return

    most_recent = sorted(own_interclub_matches, key=lambda m: m.get("match_date") or "", reverse=True)[0]
    reeks_url = most_recent["reeks_url"]

    try:
        fixtures, fetch_error = _load_poule_fixtures(reeks_url)
    except Exception as e:
        fixtures, fetch_error = [], str(e)

    if fetch_error:
        st.warning(f"Kon het wedstrijdschema niet ophalen: {fetch_error}")
        return
    if not fixtures:
        st.warning("Geen wedstrijden gevonden op de poule-pagina (onverwachte paginastructuur?).")
        return

    home_ploeg_id, away_ploeg_id, matched_fx = ss.identify_own_ploeg_id(fixtures, own_interclub_matches)
    own_ploeg_id = None
    if matched_fx:
        opp_names_known = {_clean_name(m.get("opp1_name")) for m in own_interclub_matches if m.get("opp1_name")}
        if any(_clean_name(matched_fx["away_name"]) in n or n in _clean_name(matched_fx["away_name"]) for n in opp_names_known):
            own_ploeg_id = home_ploeg_id
        else:
            own_ploeg_id = away_ploeg_id

    if not own_ploeg_id:
        st.warning(
            "Kon niet zeker bepalen welke ploeg dit is op de poule-pagina "
            "(geen overeenkomende datum/score gevonden)."
        )
        return

    team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id)
    next_match = ss.get_next_match(team_fixtures)

    if not next_match:
        st.success("Geen nog te spelen wedstrijden gevonden — seizoen is voorbij (of het schema toont nog niets).")
        return

    opp = ss.opponent_of(next_match, own_ploeg_id)
    st.markdown(f"**{next_match['date_text']}** — tegen **{opp['name']}** ({next_match['poule_label']})")

    scout_key = f"scout_{opp['ploeg_id']}_{next_match['date_text']}"
    if st.button("🔍 Tegenstander analyseren", key="btn_scout", type="primary"):
        with st.spinner("Vorige wedstrijd(en) van de tegenstander opzoeken..."):
            bundle = osc.scout_opponent(fixtures, opp["name"], opp["ploeg_id"], next_match["date_text"], lookback=1)
        st.session_state[scout_key] = bundle

    bundle = st.session_state.get(scout_key)
    if not bundle:
        st.stop()

    if bundle["note"]:
        st.info(bundle["note"])
        st.caption("Zonder historische tegenstander-data kan ik enkel jouw eigen ploeg-sterkte tonen, niet hen inschatten.")

    unknown = [p for p in bundle["unique_players"] if not fb.get_player_profile(p["user_id"])]
    if bundle["unique_players"]:
        with st.expander(f"👥 Gevonden tegenstander-spelers ({len(bundle['unique_players'])})", expanded=False):
            for p in bundle["unique_players"]:
                status = "❓ nog niet gescraped (ranking wel al gekend)" if p in unknown else "✅ volledig gekend"
                c1, c2 = st.columns([4, 1])
                c1.write(f"• {p['name']} — {status}")
                if p not in unknown:
                    if c2.button("👁️ Bekijk", key=f"jump_opp_{p['user_id']}"):
                        _go_to_player(p["user_id"])
            if unknown and st.button(f"📥 Scrape {len(unknown)} nieuwe tegenstander(s) (verrijkt toekomstige analyses)", key="btn_scrape_opp"):
                progress = st.progress(0.0, text="Starten...")
                def _cb(i, total, name):
                    progress.progress(i / total if total else 0, text=f"({i}/{total}) {name} scrapen...")
                result = osc.scrape_new_opponent_players(unknown, lookback_periods=1, delay=1.5, progress_callback=_cb)
                progress.progress(1.0, text="Klaar.")
                st.success(f"{len(result['newly_scraped'])} gescraped, {len(result['failed'])} mislukt.")
                st.rerun()

    st.divider()

    # ═══════════════════════════════════════
    # Scenario-analyse: onze beste tegenzet, per mogelijk tegenstander-scenario
    # ═══════════════════════════════════════
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "Per scenario (een eerdere opstelling van de tegenstander dit seizoen) tonen we apart wat dan "
        "jouw beste tegenzet zou zijn. Geen voorspelling van wat ze NU zullen opstellen — wel een idee "
        "van de mogelijkheden op basis van wat ze eerder deden."
    )

    own_candidates = sorted(profiles, key=lambda x: x.get("display_name") or "")
    own_labels = [_display_name(p) for p in own_candidates]
    own_label_to_id = {_display_name(p): p.get("player_id") for p in own_candidates}

    available_labels = st.multiselect(
        "Beschikbare eigen spelers", own_labels,
        default=own_labels[: min(8, len(own_labels))],
        key="scenario_available_players",
    )
    if len(available_labels) < 2:
        st.info("Selecteer minstens 2 spelers om een opstelling te kunnen berekenen.")
        st.stop()

    available_ids = [own_label_to_id[lbl] for lbl in available_labels]

    suggested_boards = max((len(fx.get("boards", [])) for fx in bundle.get("previous_fixtures", [])), default=6) or 6
    c1, c2 = st.columns(2)
    with c1:
        total_boards = st.number_input("Aantal wedstrijden deze ontmoeting", min_value=1, value=int(suggested_boards), step=1)
    with c2:
        st.caption(f"Voorstel gebaseerd op vorige ontmoeting van de tegenstander: {suggested_boards} wedstrijden.")

    default_max = max(1, -(-2 * total_boards // len(available_ids)))  # ceil(2*T / n)
    st.caption("Max. aantal wedstrijden per speler (wat als...): standaard gelijk verdeeld, zelf aanpasbaar (bv. 0 voor een afwezige speler).")
    cols = st.columns(min(len(available_ids), 6) or 1)
    max_per_player = {}
    for i, pid in enumerate(available_ids):
        with cols[i % len(cols)]:
            max_per_player[pid] = st.number_input(
                name_lookup_global.get(pid, pid), min_value=0, max_value=int(total_boards),
                value=min(default_max, int(total_boards)), step=1, key=f"scenario_max_{pid}",
            )

    total_slots = sum(max_per_player.values())
    if total_slots != 2 * total_boards:
        st.error(
            f"Het totaal aantal speler-plaatsen ({total_slots}) moet gelijk zijn aan 2× het aantal "
            f"wedstrijden ({2*total_boards}). Pas de aantallen per speler aan."
        )
        st.stop()

    if not bundle.get("previous_fixtures"):
        st.info("Geen scenario's beschikbaar (geen eerdere, al gespeelde wedstrijd van deze tegenstander gevonden).")
        st.stop()

    docs_for_synergy = ll.get_docs_for_players(available_ids)
    own_synergy = ll.compute_pairwise_synergy(docs_for_synergy, available_ids)
    synergy_fn = ll.make_pair_score_fn(own_synergy, docs_for_synergy)
    player_rankings = {pid: ll.find_player_ranking(pid, docs_for_synergy) for pid in available_ids}

    if st.button("🧮 Berekenen per scenario", type="primary"):
        for s_idx, fx_bundle in enumerate(bundle["previous_fixtures"], start=1):
            boards = fx_bundle.get("boards", [])
            fx = fx_bundle.get("fixture", {})
            with st.expander(
                f"Scenario {s_idx}: hun opstelling tegen {fx.get('home_name') if fx.get('away_ploeg_id')==opp['ploeg_id'] else fx.get('away_name')} "
                f"({fx.get('date_text','?')}) — {len(boards)} wedstrijden",
                expanded=(s_idx == 1),
            ):
                if fx_bundle.get("error"):
                    st.warning(fx_bundle["error"])
                    continue
                if not boards:
                    st.info("Geen bord-detail kunnen ophalen voor dit scenario.")
                    continue

                results, truncated = ll.optimize_lineup_vs_scenario(
                    available_ids, max_per_player, synergy_fn, boards, player_rankings, top_n=1,
                )
                if truncated:
                    st.caption("⚠️ Grote zoekruimte — resultaat gebaseerd op beperkte zoekdiepte.")
                if not results:
                    st.warning("Geen geldige opstelling gevonden binnen deze beperkingen.")
                    continue

                best = results[0]
                st.write(f"**Geschatte totaalscore: {best['total_score']}**")
                for a in best["assignment"]:
                    p1, p2 = a["our_pair"]
                    opp_pair = a["opponent_board"]["opponent_pair"]
                    opp_names = " / ".join(p.get("name", "?") for p in opp_pair)
                    bcol1, bcol2 = st.columns([3, 1])
                    with bcol1:
                        st.write(
                            f"**{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
                            f"(synergie {a['synergy']}) — vs **{opp_names}** (relatief voordeel: {a['edge']:+.2f})"
                        )
                    with bcol2:
                        if st.button("👁️ Bekijk", key=f"jump_{s_idx}_{p1}_{p2}"):
                            _go_to_player(p1)

    st.divider()

    # ═══════════════════════════════════════
    # Retrospectieve analyse (eerder gespeelde ontmoetingen van deze speler)
    # ═══════════════════════════════════════
    st.markdown('<div class="section-header">🕰️ Retrospectieve analyse</div>', unsafe_allow_html=True)
    name_lookup = name_lookup_global

    profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
    docs, index = _load_encounter_index(profile_ids)
    all_encounters = ll.list_encounters(index)

    # Enkel ontmoetingen waar de gekozen speler effectief in voorkwam
    own_encounters = [
        (key, lbl) for key, lbl in all_encounters
        if any(pid == sel_player_id for pid, _ in index[key])
    ]

    if not own_encounters:
        st.info(f"Geen eerder gespeelde interclub-ontmoetingen gevonden voor {sel_label}.")
        return

    labels2 = [lbl for _, lbl in own_encounters]
    chosen_label = st.selectbox("Kies een eerder gespeelde ontmoeting", labels2)
    key = next(k for k, lbl in own_encounters if lbl == chosen_label)

    entries = index[key]
    boards = ll.reconstruct_boards(entries)
    if not boards:
        st.warning("Kon geen geldige boards reconstrueren voor deze ontmoeting (ontbrekende data).")
        return

    actual_required = ll.required_counts_from_boards(boards)
    players = list(actual_required.keys())

    st.markdown('<div class="section-header">Werkelijk gespeelde opstelling</div>', unsafe_allow_html=True)
    board_rows = []
    for b in sorted(boards, key=lambda x: (x.get("round_text") or "")):
        p1, p2 = tuple(b["pair"])
        board_rows.append({
            "Ronde": b.get("round_text") or "–",
            "Koppel": f"{name_lookup.get(p1,p1)} / {name_lookup.get(p2,p2)}",
            "Tegen": f"{b.get('opp1_name','?')} / {b.get('opp2_name','?')}",
            "Score": b.get("score") or "–",
            "W/V": b.get("result") or "–",
        })
    st.dataframe(pd.DataFrame(board_rows), use_container_width=True, hide_index=True)

    exclude_keys = {b["dedupe_key"] for b in boards}
    synergy = ll.compute_pairwise_synergy(docs, players, exclude_match_keys=exclude_keys)
    score_fn = ll.make_pair_score_fn(synergy, docs)
    actual_score = ll.score_actual_lineup(boards, score_fn)

    st.metric(
        "Synergie-score van de werkelijke opstelling",
        actual_score,
        help="Som van de partner-winrates (of, bij gebrek aan gezamenlijke historie, het gemiddelde van "
             "de individuele winrates) van elk gespeeld koppel. Hoger = sterker op basis van historische data. "
             "De ontmoeting die je hier bekijkt is zelf uitgesloten uit deze berekening."
    )

    if st.button("🧮 Vergelijk met alternatieve opstellingen", type="secondary"):
        with st.spinner("Mogelijke opstellingen doorrekenen..."):
            results, truncated = ll.optimize_lineup(players, actual_required, score_fn, top_n=5)
        if truncated:
            st.caption("⚠️ Grote zoekruimte — resultaten gebaseerd op beperkte zoekdiepte.")
        if not results:
            st.warning("Geen geldige opstelling gevonden binnen deze beperkingen.")
        else:
            for rank, (score, pairs) in enumerate(results, start=1):
                delta = score - actual_score
                with st.expander(f"#{rank} — score {score} ({'+' if delta>=0 else ''}{delta:.2f} t.o.v. werkelijk)", expanded=(rank == 1)):
                    for pair in pairs:
                        p1, p2 = tuple(pair)
    st.divider()


# ═══════════════════════════════════════════════
# Gedeelde dashboard-weergave (gebruikt door Mijn profiel én Spelers)
# ═══════════════════════════════════════════════

def _render_refresh_controls(player_id: str, profile: dict, key_prefix: str):
    # PADEL_ANALYSIS_FIX_RC_COLUMNS
    rc1, rc2 = st.columns(2)

    with rc1:
        if st.button("🔄 Vernieuwen (enkel nieuwe periodes)", type="primary", key=f"{key_prefix}_refresh"):
            bar, cb = _scrape_progress_widget()
            try:
                from scrape_player import scrape_player as _scrape
                result = _scrape(str(player_id), force_full_refresh=False, save_to_firebase=True, progress_callback=cb)
                bar.progress(1.0, text="Klaar.")
                st.success(f"Klaar — {result.get('stats',{}).get('total_matches',0)} matches totaal.")
                st.rerun()
            except Exception as e:
                st.error(f"Mislukt: {e}")
    with rc2:
        with st.expander("⚙️ Debug: volledig herscrapen"):
            st.caption("Haalt ALLE periodes opnieuw op, niet enkel de nieuwe. Trager, normaal niet nodig.")
            if st.button("⚠️ Volledig herscrapen", key=f"{key_prefix}_full_refresh"):
                bar, cb = _scrape_progress_widget()
                try:
                    from scrape_player import scrape_player as _scrape
                    result = _scrape(str(player_id), force_full_refresh=True, save_to_firebase=True, progress_callback=cb)
                    bar.progress(1.0, text="Klaar.")
                    st.success(f"Klaar — {result.get('stats',{}).get('total_matches',0)} matches totaal.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Mislukt: {e}")


def _render_player_dashboard(player_id: str, profile: dict):
    """Stats + tabs voor één speler. Herbruikt door 'Mijn profiel' en 'Spelers'."""
    player_doc = fb.get_player(player_id)
    if not player_doc:
        st.warning("Geen data in Firebase voor deze speler. Gebruik de vernieuw-knop hierboven.")
        return

    matches = player_doc.get("matches", [])
    stats = player_doc.get("stats", {})
    df = _matches_to_df(matches)

    wins = int(stats.get("wins", 0))
    losses = int(stats.get("losses", 0))
    total = int(stats.get("total_matches", len(df)))
    t_count = int(stats.get("tournament_matches", 0))
    ic_count = int(stats.get("interclub_matches", 0))

    _render_metrics(total, wins, losses, t_count, ic_count)

    tab_overview, tab_explorer, tab_partners, tab_opponents, tab_klassement, tab_debug = st.tabs([
        "Overzicht", "Match Explorer", "Partners", "Tegenstanders", "📈 Klassement", "Debug"
    ])

    # ── Overzicht ──
    with tab_overview:
        if df.empty:
            st.info("Geen matches beschikbaar.")
        else:
            st.markdown('<div class="section-header">Per periode</div>', unsafe_allow_html=True)
            periods = df.groupby("period").agg(
                matches=("won", "count"),
                wins=("won", lambda x: x.eq(True).sum()),
                losses=("won", lambda x: x.eq(False).sum()),
            ).reset_index()
            periods["winrate"] = periods.apply(lambda r: _winrate_str(r.wins, r.losses), axis=1)
            periods = periods.sort_values("period", key=lambda s: s.map(_period_sort_key), ascending=False)
            periods = periods.reset_index(drop=True)

            st.caption("👉 Klik op een periode om de matches uit die periode te zien.")
            period_event = st.dataframe(
                periods, use_container_width=True, hide_index=True,
                height=min(400, 40 + len(periods) * 36),
                column_config={
                    "period":  st.column_config.TextColumn("Periode", width="large"),
                    "matches": st.column_config.NumberColumn("M", width="small"),
                    "wins":    st.column_config.NumberColumn("W", width="small"),
                    "losses":  st.column_config.NumberColumn("L", width="small"),
                    "winrate": st.column_config.TextColumn("Winrate", width="small"),
                },
                on_select="rerun", selection_mode="single-row", key=f"periods_table_{player_id}",
            )
            sel_rows = (period_event or {}).get("selection", {}).get("rows", [])
            if sel_rows:
                sel_period = periods.iloc[sel_rows[0]]["period"]
                st.markdown(f"**Matches in periode '{sel_period}':**")
                # PADEL_ANALYSIS_INLINE_PERIOD_MATCH_ACTIONS
                period_cols = [
                    "datum", "type", "reeks",
                    "partner", "partner_id",
                    "opp1", "opp1_id", "opp1_user_id",
                    "opp2", "opp2_id", "opp2_user_id",
                    "score", "result",
                ]
                period_cols = [c for c in period_cols if c in df.columns]
                period_matches = df[df["period"] == sel_period][period_cols].rename(columns={
                    "datum": "Datum", "type": "Type", "reeks": "Reeks",
                    "partner": "Partner", "partner_id": "Partner ID",
                    "opp1": "Tegenstander 1", "opp1_id": "Tegenstander 1 ID", "opp1_user_id": "Tegenstander 1 ID",
                    "opp2": "Tegenstander 2", "opp2_id": "Tegenstander 2 ID", "opp2_user_id": "Tegenstander 2 ID",
                    "score": "Score", "result": "W/V",
                })
                pia.render_matches_period_table(
                    period_matches,
                    profiles=_get_all_profiles(),
                    key_prefix=f"period_matches_{player_id}_{sel_rows[0]}",
                )

            st.markdown('<div class="section-header">Tornooi vs Interclub</div>', unsafe_allow_html=True)
            tc1, tc2 = st.columns(2)
            for col, label, filter_val in [(tc1, "Tornooi", "tornooi"), (tc2, "Interclub", "interclub")]:
                sub = df[df["type"] == filter_val]
                sub_w = int(sub["won"].eq(True).sum())
                sub_l = int(sub["won"].eq(False).sum())
                col.metric(f"{label} ({len(sub)})", _winrate_str(sub_w, sub_l), f"{sub_w}W – {sub_l}L")

    # ── Match Explorer ──
    with tab_explorer:
        if df.empty:
            st.info("Geen matches.")
        else:
            with st.expander("🔽 Filters", expanded=False):
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    type_opts = ["Alle"] + sorted(df["type"].unique().tolist())
                    sel_type = st.selectbox("Type", type_opts, key=f"flt_type_{player_id}")
                    period_opts = ["Alle"] + sorted(df["period"].unique().tolist(), key=_period_sort_key, reverse=True)
                    sel_period = st.selectbox("Periode", period_opts, key=f"flt_period_{player_id}")
                with fc2:
                    result_opts = ["Alle", "W", "V"]
                    sel_result = st.selectbox("Resultaat (W/V)", result_opts, key=f"flt_result_{player_id}")
                    partner_opts = ["Alle"] + sorted(df["partner"].replace("", pd.NA).dropna().unique().tolist())
                    sel_partner = st.selectbox("Partner", partner_opts, key=f"flt_partner_{player_id}")
                with fc3:
                    reeks_opts = ["Alle"] + sorted(df["reeks"].replace("", pd.NA).dropna().unique().tolist())
                    sel_reeks = st.selectbox("Reeks", reeks_opts, key=f"flt_reeks_{player_id}")
                    score_q = st.text_input("Zoek in score", key=f"flt_score_{player_id}")

            fdf = df.copy()
            if sel_type != "Alle":    fdf = fdf[fdf["type"] == sel_type]
            if sel_period != "Alle":  fdf = fdf[fdf["period"] == sel_period]
            if sel_result != "Alle":  fdf = fdf[fdf["result"] == sel_result]
            if sel_partner != "Alle": fdf = fdf[fdf["partner"] == sel_partner]
            if sel_reeks != "Alle":   fdf = fdf[fdf["reeks"] == sel_reeks]
            if score_q:               fdf = fdf[fdf["score"].str.contains(score_q, case=False, na=False)]

            fw = int(fdf["won"].eq(True).sum())
            fl = int(fdf["won"].eq(False).sum())
            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Matches", len(fdf))
            sm2.metric("W", fw)
            sm3.metric("L", fl)
            sm4.metric("Winrate", _winrate_str(fw, fl))

            show_cols = ["type", "datum", "period", "reeks", "ronde", "partner", "partner_id",
                         "opp1", "opp1_id", "opp1_ranking", "opp2", "opp2_id", "opp2_ranking", "result", "score"]
            show_cols = [c for c in show_cols if c in fdf.columns]
            fdf_display = fdf[show_cols].rename(columns={
                "type": "Type", "datum": "Datum", "period": "Periode",
                "reeks": "Reeks", "ronde": "Ronde", "partner": "Partner", "partner_id": "Partner ID",
                "opp1": "Tegenstander 1", "opp1_id": "Tegenstander 1 ID", "opp1_ranking": "R1",
                "opp2": "Tegenstander 2", "opp2_id": "Tegenstander 2 ID", "opp2_ranking": "R2",
                "result": "W/V", "score": "Score",
            })
            st.caption("👉 Klik op een rij om de details onderaan te tonen.")
            explorer_event = st.dataframe(
                fdf_display, use_container_width=True, hide_index=True,
                height=min(500, 40 + len(fdf) * 36),
                column_config={
                    "W/V": st.column_config.TextColumn("W/V", width="small"),
                    "Score": st.column_config.TextColumn("Score", width="small"),
                    "R1": st.column_config.TextColumn("R1", width="small"),
                    "R2": st.column_config.TextColumn("R2", width="small"),
                },
                on_select="rerun", selection_mode="single-row", key=f"match_explorer_table_{player_id}",
            )

            if not fdf.empty:
                st.markdown("---")
                st.markdown("**Match detail**")
                selected_rows = (explorer_event or {}).get("selection", {}).get("rows", [])
                if not selected_rows:
                    st.info("Klik op een rij in de tabel hierboven om de details te zien.")
                else:
                    idx = selected_rows[0]
                    row = fdf.iloc[idx]
                    dc1, dc2 = st.columns(2)
                    with dc1:
                        st.write(f"**Type:** {row.get('type','–')}")
                        st.write(f"**Datum:** {row.get('datum','–') or '–'}")
                        st.write(f"**Periode:** {row.get('period','–')}")
                        st.write(f"**Toernooi/Competitie:** {row.get('toernooi','–') or '–'}")
                        st.write(f"**Reeks:** {row.get('reeks','–') or '–'}")
                        st.write(f"**Ronde:** {row.get('ronde','–') or '–'}")
                    with dc2:
                        # PADEL_ANALYSIS_INLINE_SELECTED_MATCH_DETAILS
                        st.write("**Partner:**")
                        pia.render_player_name_action(
                            row.get('partner','–') or '–',
                            pia.resolve_player_id(row.get('partner','–') or '–', pia.build_profile_lookup(_get_all_profiles()), row.get('partner_id','')),
                            key_prefix=f"selected_match_{player_id}_{idx}_partner",
                        )
                        st.write("**Tegenstander 1:**")
                        pia.render_player_name_action(
                            f"{row.get('opp1','–')} ({row.get('opp1_ranking','?')})",
                            pia.resolve_player_id(row.get('opp1','–') or '–', pia.build_profile_lookup(_get_all_profiles()), row.get('opp1_id', row.get('opp1_user_id',''))),
                            key_prefix=f"selected_match_{player_id}_{idx}_opp1",
                        )
                        st.write("**Tegenstander 2:**")
                        pia.render_player_name_action(
                            f"{row.get('opp2','–')} ({row.get('opp2_ranking','?')})",
                            pia.resolve_player_id(row.get('opp2','–') or '–', pia.build_profile_lookup(_get_all_profiles()), row.get('opp2_id', row.get('opp2_user_id',''))),
                            key_prefix=f"selected_match_{player_id}_{idx}_opp2",
                        )
                        st.write(f"**Score:** {row.get('score','–')}")
                        result_badge = "win" if row.get("result") == "W" else "loss"
                        st.markdown(
                            f"**Resultaat:** <span class='badge-{result_badge}'>"
                            f"{'✅ Winst' if result_badge=='win' else '❌ Verlies'}</span>",
                            unsafe_allow_html=True,
                        )
                        if row.get("reeks_url"):
                            st.markdown(f"[📋 Poule/tabel ↗](https://www.tennisenpadelvlaanderen.be{row['reeks_url']})")
                        if row.get("uitslagenblad"):
                            st.markdown(f"[📄 Uitslagenblad ↗](https://www.tennisenpadelvlaanderen.be{row['uitslagenblad']})")

    # ── Partners ──
    with tab_partners:
        st.markdown('<div class="section-header">Partneranalyse</div>', unsafe_allow_html=True)
        partner_df = _summarize_partner(df)
        if not partner_df.empty:
            q = st.text_input("Zoek partner", placeholder="Filter...", label_visibility="collapsed", key=f"pq_{player_id}")
            if q:
                partner_df = partner_df[partner_df["partner"].str.contains(q, case=False, na=False)]
        _render_table(partner_df, "partner")

    # ── Tegenstanders ──
    with tab_opponents:
        st.markdown('<div class="section-header">Tegenstandersanalyse</div>', unsafe_allow_html=True)
        opp_df = _summarize_opponents(df)
        if not opp_df.empty:
            q = st.text_input("Zoek tegenstander", placeholder="Filter...", label_visibility="collapsed", key=f"oq_{player_id}")
            if q:
                opp_df = opp_df[opp_df["tegenstander"].str.contains(q, case=False, na=False)]
        _render_table(opp_df, "tegenstander")

    # ── Klassement ──
    with tab_klassement:
        st.markdown('<div class="section-header">📈 Klassementshistoriek</div>', unsafe_allow_html=True)
        profile_doc_for_klassement = fb.get_player_profile(player_id) or {}
        klassement_doc = (
            (player_doc or {}).get("klassement_history")
            or (profile_doc_for_klassement or {}).get("klassement_history")
            or (profile or {}).get("klassement_history")
        )

        if klassement_doc:
            # Toon samenvatting historiek
            history = klassement_doc.get("history", [])
            raw_periods = klassement_doc.get("raw_periods", []) or []
            if not history and raw_periods:
                raw_errors = [
                    p.get("error")
                    for p in raw_periods
                    if isinstance(p, dict) and p.get("error")
                ]
                if raw_errors:
                    st.warning(
                        "Klassementdata werd opgehaald, maar er zijn geen geldige historiekrecords. "
                        "Eerste fout uit raw_periods:"
                    )
                    st.code(str(raw_errors[0]))
                else:
                    st.info(
                        "Klassementdata is aanwezig, maar de compacte historiek is leeg. "
                        "Bekijk raw_periods in de Debug-tab."
                    )
            if history:
                normalized_history = []
                for row in history:
                    r = dict(row or {})
                    klassement_value = (
                        r.get("klassement")
                        or r.get("begin_klassement")
                        or r.get("vorig")
                        or r.get("vorig_klassement")
                    )
                    normalized_history.append({
                        "datum": r.get("datum") or r.get("date") or "",
                        "periode": r.get("periode") or r.get("omschrijving") or r.get("label"),
                        "klassement": klassement_value,
                    })

                hist_df = pd.DataFrame(normalized_history)
                wanted_cols = [c for c in ["datum", "periode", "klassement"] if c in hist_df.columns]
                hist_df = hist_df[wanted_cols]
                if "datum" in hist_df.columns:
                    hist_df = hist_df.sort_values("datum", ascending=False, na_position="last")

                st.caption("Klassement aan het begin van elke periode.")
                st.dataframe(
                    hist_df.rename(columns={
                        "datum": "Datum",
                        "periode": "Periode",
                        "klassement": "Klassement begin periode",
                    }),
                    use_container_width=True,
                    hide_index=True,
                    height=min(400, 40 + len(hist_df) * 36),
                )

            # Toon winrate per niveau
            niveau_data = klassement_doc.get("niveau_winrates", {})
            if niveau_data:
                st.markdown('<div class="section-header">Winrate per tegenstanderniveau</div>', unsafe_allow_html=True)
                niv_rows = [
                    {"Niveau": niv, "Gem. winrate": f"{v['winstratio_avg']}%" if v["winstratio_avg"] is not None else "?",
                     "Totaal matchen": v["total_matchen"]}
                    for niv, v in sorted(niveau_data.items(), key=lambda x: int(x[0][1:]))
                ]
                st.dataframe(pd.DataFrame(niv_rows), use_container_width=True, hide_index=True)

            scraped = _format_scraped_at(klassement_doc.get("scraped_at"))
            st.caption(f"Klassement gescraped op: {scraped}")

        else:
            st.info(
                "Nog geen klassementsdata beschikbaar. Klik hieronder om de klassementshistoriek te laden. "
                "Dit opent een browser en doorloopt alle beschikbare periodes (~30-60 seconden)."
            )

        if st.button("📥 Klassementshistoriek laden / verversen", key=f"load_klassement_{player_id}"):
            import sys
            _root = str(__import__("pathlib").Path(__file__).parent)
            if _root not in sys.path:
                sys.path.insert(0, _root + "/scraper")
                sys.path.insert(0, _root)
            from scrape_klassement import scrape_klassement, klassement_to_history_summary, extract_niveau_winrates
            bar, cb = _scrape_progress_widget(label_prefix="Klassement: ")
            try:
                periods = scrape_klassement(str(player_id), progress_callback=cb)
                bar.progress(1.0, text="Klaar.")
                history = klassement_to_history_summary(periods)
                niveau_winrates = extract_niveau_winrates(periods)
                import datetime
                klass_data = {
                    "history": history,
                    "niveau_winrates": niveau_winrates,
                    "raw_periods": periods,
                    "scraped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
                # Opslaan in beide collecties:
                # - player_profiles: profielmetadata
                # - players: wordt gebruikt door fb.get_player(player_id) in deze dashboard-render
                fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(payload, merge=True)
                fb.db.collection(fb.PLAYERS_COLLECTION).document(str(player_id)).set(payload, merge=True)
                if history:
                    st.success(f"Klaar — {len(history)} periodes geladen.")
                else:
                    st.warning(
                        f"Scrape afgerond, maar compacte historiek is leeg. "
                        f"Raw periodes: {len(periods)}. Bekijk de Klassement-tab of Debug-tab."
                    )
                st.rerun()
            except Exception as e:
                st.error(f"Mislukt: {e}")

    # ── Debug ──
    with tab_debug:
        st.json(player_doc, expanded=False)
        st.write(f"**Schema:** {player_doc.get('schema_version','?')}")
        st.write(f"**Periodes gescraped:** {player_doc.get('periods_scraped',[])}")
        st.write(f"**Periodes leeg:** {player_doc.get('periods_empty',[])}")
        st.write(f"**Periodes mislukt:** {player_doc.get('periods_failed',[])}")


# ═══════════════════════════════════════════════
# PAGE: Mijn profiel
# ═══════════════════════════════════════════════

def page_my_profile():
    st.header("👤 Mijn profiel")
    profiles = _get_all_profiles()

    if not profiles:
        st.info("Nog geen spelers in de database. Voeg jezelf eerst toe via '➕ Speler toevoegen'.")
        return

    profile_map = {
        f"{_display_name(p)} ({p.get('player_id','?')})": p
        for p in sorted(profiles, key=lambda x: x.get("display_name") or "")
    }
    settings = fb.get_app_settings()
    home_id = settings.get("home_player_id")

    if not home_id:
        st.caption("Stel hier eenmalig in wie jij bent.")
        pick_label = st.selectbox("Dit ben ik", [""] + list(profile_map.keys()), key="home_player_pick")
        if pick_label and st.button("💾 Instellen als 'mij'", type="primary"):
            fb.save_app_settings({"home_player_id": profile_map[pick_label]["player_id"]})
            st.rerun()
        return

    home_profile = next((p for p in profiles if p.get("player_id") == home_id), None)
    if not home_profile:
        st.warning("De ingestelde 'Dit ben ik'-speler werd niet terugvonden. Stel opnieuw in.")
        if st.button("Opnieuw instellen"):
            fb.save_app_settings({"home_player_id": None})
            st.rerun()
        return

    home_doc = fb.get_player(home_id)
    last_scraped = _format_scraped_at((home_doc or {}).get("scraped_at"))
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.subheader(_display_name(home_profile))
        st.caption(f"laatst gescraped: `{last_scraped}`")
    with hc2:
        if st.button("✏️ Wijzig wie ik ben"):
            fb.save_app_settings({"home_player_id": None})
            st.rerun()
    _render_refresh_controls(home_id, home_profile, key_prefix="myprofile")
    st.divider()
    _render_player_dashboard(home_id, home_profile)


# ═══════════════════════════════════════════════
# PAGE: Spelers (eender wie opzoeken)
# ═══════════════════════════════════════════════

def page_players():
    st.header("🔍 Spelers")
    profiles = _get_all_profiles()

    if not profiles:
        st.info("Nog geen spelers in de database. Voeg eerst spelers toe via '➕ Speler toevoegen'.")
        return

    profile_map = {
        f"{_display_name(p)} ({p.get('player_id','?')})": p
        for p in sorted(profiles, key=lambda x: x.get("display_name") or "")
    }

    search_q = st.text_input("🔍 Filter speler", placeholder="Typ naam of club...", label_visibility="collapsed")
    filtered_labels = [lbl for lbl in profile_map if not search_q or search_q.lower() in lbl.lower()]

    if not filtered_labels:
        st.warning("Geen spelers gevonden.")
        return

    # Sprong vanuit een andere pagina (bv. tegenstander-analyse) met een vooraf gekozen speler
    default_idx = 0
    jump_id = st.session_state.pop("jump_to_player_id", None)
    if jump_id:
        match_label = next((lbl for lbl, p in profile_map.items() if str(p.get("player_id")) == str(jump_id)), None)
        if match_label in filtered_labels:
            default_idx = filtered_labels.index(match_label)

    chosen_label = st.selectbox("Speler", filtered_labels, index=default_idx, label_visibility="collapsed")
    profile = profile_map[chosen_label]
    player_id = profile.get("player_id")

    _settings_now = fb.get_app_settings()
    _home_id_now = str(_settings_now.get("home_player_id") or "")
    _is_me = _home_id_now == str(player_id)

    hcol1, hcol2 = st.columns([5, 1])
    with hcol1:
        st.subheader(_display_name(profile))
        club = profile.get("club")
        if club:
            st.caption(f"🏟️ {club} · ID: {player_id}")
        if _is_me:
            st.caption("👤 Dit ben jij")

    with st.expander("⚠️ Speler verwijderen", expanded=False):
        st.warning(
            f"Speler '{_display_name(profile)}' definitief verwijderen?"
        )

        if st.button(
            "🗑️ Verwijder speler",
            key=f"delete_player_{player_id}",
            type="secondary",
        ):
            fb.delete_player(str(player_id))
            st.success("Speler verwijderd.")
            st.rerun()
    _render_refresh_controls(player_id, profile, key_prefix="players")
    st.divider()
    _render_player_dashboard(player_id, profile)


# ═══════════════════════════════════════════════
# RENDER
# ═══════════════════════════════════════════════

if page == "➕ Speler toevoegen":
    page_add_player()
elif page == "🧩 Opstelling-analyse":
    page_lineup_lab()
elif page == "👤 Mijn profiel":
    page_my_profile()
else:
    page_players()
