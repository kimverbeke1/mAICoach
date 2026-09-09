# -*- coding: utf-8 -*-
"""
opponent_analysis.py
--------------------
PadelAnalysis - Interclub tegenstanderanalyse.

Wijzigingen t.o.v. de vorige versie:
  * Geen "nog niet gescrapet" meer: bij het openen van de tegenstander wordt
    de scrape AUTOMATISCH gestart voor elke ontbrekende/onvolledige speler.
  * Alle scrape-/opslaglogica zit nu in player_store.py + player_scrape_adapter.py,
    zodat een dossier maar 1 keer gescrapet moet worden (TTL 21 dagen).
  * Toont per speler: huidige ranking, beste ranking ooit (+ datum),
    ranking-tijdlijn, vaste partners, resultaten binnen dezelfde poule.
  * Twee tabs: "Volgende Match" (1 actieve analyse) en "Interclub Historiek".

Inhaken:
    from PadelAnalysis.opponent_analysis import render_opponent_analysis
    render_opponent_analysis(user_name="Kim Verbeke")
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import streamlit as st

import player_scrape_adapter as adapter
import player_store as store

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------

MATCH_COLLECTIONS = ["interclub_matches", "matches", "interclubmatches", "wedstrijden"]
PREP_COLLECTION = "opponent_preparations"

HOME_TEAM_FIELDS = ["home_team", "thuisploeg", "team_home", "ploeg_thuis"]
AWAY_TEAM_FIELDS = ["away_team", "uitploeg", "team_away", "ploeg_uit"]
DATE_FIELDS = ["date", "datum", "match_date", "start_date", "speeldatum"]
POULE_FIELDS = ["poule", "reeks", "poule_name", "reeks_naam", "series"]
MY_TEAM_FIELDS = ["my_team", "eigen_ploeg", "team", "ploeg"]
NAME_FIELDS = ["name", "full_name", "player_name", "naam", "speler"]
URL_FIELDS = ["profile_url", "url", "link", "speler_url"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first(doc: Optional[Dict[str, Any]], fields: Iterable[str], default=None):
    if not isinstance(doc, dict):
        return default
    for f in fields:
        if doc.get(f) not in (None, "", [], {}):
            return doc[f]
    for nested in ("profile", "stats", "data", "info"):
        sub = doc.get(nested)
        if isinstance(sub, dict):
            for f in fields:
                if sub.get(f) not in (None, "", [], {}):
                    return sub[f]
    return default


def _to_date(value: Any) -> Optional[_dt.date]:
    if value in (None, "", []):
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


# ---------------------------------------------------------------------------
# Data laden
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def load_matches() -> List[Dict[str, Any]]:
    db = store.get_db()
    for name in MATCH_COLLECTIONS:
        try:
            docs = [{**d.to_dict(), "_doc_id": d.id}
                    for d in db.collection(name).limit(3000).stream()]
        except Exception:
            continue
        if docs:
            return docs
    return []


@st.cache_data(ttl=300, show_spinner=False)
def load_preparations() -> List[Dict[str, Any]]:
    try:
        return [{**d.to_dict(), "_doc_id": d.id}
                for d in store.get_db().collection(PREP_COLLECTION).stream()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Eigen ploeg / tegenstander
# ---------------------------------------------------------------------------

def detect_my_team(matches: List[Dict[str, Any]], user_name: str) -> Optional[str]:
    """Eigen ploeg = ploeg waarin de gebruiker het recentst gespeeld heeft."""
    user = _norm(user_name)
    played: List[Tuple[_dt.date, str]] = []
    for m in matches:
        team = _first(m, MY_TEAM_FIELDS)
        if not team:
            continue
        if user and user not in _norm(m):
            continue
        played.append((_to_date(_first(m, DATE_FIELDS)) or _dt.date(1900, 1, 1), str(team)))
    if not played:
        return None
    played.sort(key=lambda x: x[0], reverse=True)
    return played[0][1]


def opponent_of(match: Dict[str, Any], my_team: Optional[str]) -> Optional[str]:
    home, away = _first(match, HOME_TEAM_FIELDS), _first(match, AWAY_TEAM_FIELDS)
    if not home or not away:
        return away or home
    if my_team and _norm(my_team) in _norm(home):
        return away
    if my_team and _norm(my_team) in _norm(away):
        return home
    return away


def next_match(matches: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    today = _dt.date.today()
    upcoming = [(d, m) for m in matches if (d := _to_date(_first(m, DATE_FIELDS))) and d >= today]
    if not upcoming:
        return None
    upcoming.sort(key=lambda x: x[0])
    return upcoming[0][1]


def team_players(match: Dict[str, Any], team: str) -> List[Dict[str, Any]]:
    """Spelers (naam + eventuele url) van de opgegeven ploeg."""
    for key in ("opponent_players", "away_players", "home_players", "team_players",
                "players", "spelers", "lineup", "opstelling"):
        blob = match.get(key)
        if not blob:
            continue
        if isinstance(blob, dict):
            for tkey, names in blob.items():
                if _norm(team) in _norm(tkey) and names:
                    return [{"name": str(n), "url": None} if isinstance(n, str)
                            else {"name": str(_first(n, NAME_FIELDS)), "url": _first(n, URL_FIELDS)}
                            for n in names]
        if isinstance(blob, list):
            out: List[Dict[str, Any]] = []
            for item in blob:
                if isinstance(item, str):
                    out.append({"name": item, "url": None})
                elif isinstance(item, dict):
                    t = item.get("team") or item.get("ploeg")
                    if t and _norm(team) not in _norm(t):
                        continue
                    n = _first(item, NAME_FIELDS)
                    if n:
                        out.append({"name": str(n), "url": _first(item, URL_FIELDS)})
            if out:
                return out
    return []


# ---------------------------------------------------------------------------
# Weergave per speler
# ---------------------------------------------------------------------------

def _history_df(player: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    for h in player.get("ranking_history") or []:
        d = _to_date(h.get("date"))
        v = adapter.rank_value(h.get("ranking"))
        if d and v:
            rows.append({"Datum": d, "Klassement": h.get("ranking"), "Waarde": v})
    df = pd.DataFrame(rows)
    return df.sort_values("Datum") if not df.empty else df


def _partners_df(player: Dict[str, Any], top_n: int = 5) -> pd.DataFrame:
    rows = player.get("partners") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "matches" in df.columns:
        df = df.sort_values("matches", ascending=False).head(top_n)
        if "wins" in df.columns:
            df["Winrate"] = (df["wins"] / df["matches"] * 100).round(0).astype(int).astype(str) + "%"
        df = df.rename(columns={"partner": "Partner", "matches": "Matchen", "wins": "Gewonnen"})
    return df


def _poule_df(player: Dict[str, Any], poule: Optional[str]) -> pd.DataFrame:
    rows = []
    for m in player.get("matches") or []:
        if poule and _norm(m.get("poule")) != _norm(poule):
            continue
        rows.append({
            "Datum": _to_date(m.get("date")),
            "Tegenstander": m.get("opponent") or "",
            "Partner": m.get("partner") or "",
            "Resultaat": m.get("result") or ("W" if m.get("won") else "V" if m.get("won") is False else ""),
        })
    df = pd.DataFrame(rows)
    return df.sort_values("Datum", ascending=False) if not df.empty else df


def render_player_card(player: Dict[str, Any], poule: Optional[str]) -> None:
    hist = _history_df(player)
    best_date = _to_date(player.get("best_ranking_date"))

    c1, c2 = st.columns(2)
    c1.metric("Huidige ranking", str(player.get("current_ranking") or "onbekend"))
    c2.metric("Beste ranking ooit", str(player.get("best_ranking") or "onbekend"))
    if best_date:
        c2.caption(f"bereikt op {best_date.strftime('%d/%m/%Y')}")

    st.markdown("**Ranking evolutie**")
    if len(hist) < 2:
        st.caption("Nog onvoldoende rankinghistoriek voor een tijdlijn.")
    else:
        st.line_chart(hist.set_index("Datum")[["Waarde"]].rename(columns={"Waarde": "Klassement"}))
        st.caption("Lagere waarde = sterker klassement.")

    st.markdown("**Meest gespeelde partners**")
    partners = _partners_df(player)
    if partners.empty:
        st.caption("Geen partnergegevens gevonden.")
    else:
        st.dataframe(partners, hide_index=True, use_container_width=True)

    st.markdown("**Resultaten in deze poule**")
    res = _poule_df(player, poule)
    if res.empty:
        st.caption("Geen resultaten binnen deze poule gevonden.")
    else:
        st.dataframe(res, hide_index=True, use_container_width=True)

    st.caption(f"Laatst gescrapet: {str(player.get('last_scraped') or '?')[:16].replace('T', ' ')} "
               f"Â· bron: {player.get('scrape_source') or '?'}")


# ---------------------------------------------------------------------------
# Preparations
# ---------------------------------------------------------------------------

def save_preparation(match: Dict[str, Any], my_team: str, opponent: str,
                     player_names: List[str]) -> None:
    try:
        match_id = str(match.get("_doc_id") or match.get("match_id")
                       or f"{_first(match, DATE_FIELDS)}_{opponent}")
        store.get_db().collection(PREP_COLLECTION).document(store.slug(match_id)).set({
            "match_id": match_id,
            "date": str(_first(match, DATE_FIELDS)),
            "my_team": my_team,
            "opponent": opponent,
            "poule": _first(match, POULE_FIELDS),
            "player_names": player_names,
            "prepared_at": _dt.datetime.utcnow().isoformat(timespec="seconds"),
        }, merge=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _render_next_match(matches: List[Dict[str, Any]], user_name: str) -> None:
    m = next_match(matches)
    if not m:
        st.info("Geen toekomstige interclubmatch gevonden.")
        return

    my_team = detect_my_team(matches, user_name)
    if not my_team:
        teams = sorted({str(t) for mm in matches
                        for t in (_first(mm, HOME_TEAM_FIELDS), _first(mm, AWAY_TEAM_FIELDS)) if t})
        my_team = st.selectbox("Eigen ploeg kon niet automatisch bepaald worden:", teams)
    else:
        st.caption(f"Eigen ploeg automatisch bepaald: **{my_team}**")

    opponent = str(opponent_of(m, my_team) or "onbekend")
    date = _to_date(_first(m, DATE_FIELDS))
    poule = _first(m, POULE_FIELDS)

    st.subheader(f"{my_team}  vs  {opponent}")
    st.caption(" Â· ".join(x for x in [
        date.strftime("%d/%m/%Y") if date else None,
        f"Poule: {poule}" if poule else None] if x))

    roster = team_players(m, opponent)
    if not roster:
        st.warning("Geen opstelling van de tegenpartij in dit matchdocument. "
                   "Scrape eerst de poulepagina van deze reeks.")
        return

    force = st.button("Forceer herscrape van alle spelers",
                      help=f"Cache is normaal {store.SCRAPE_TTL_DAYS} dagen geldig")

    names = [r["name"] for r in roster]
    urls = {r["name"]: r.get("url") for r in roster if r.get("url")}

    bar = st.progress(0.0)
    status_box = st.empty()

    def _progress(i, n, name):
        bar.progress(i / max(n, 1))
        status_box.caption(f"Dossier ophalen: {name} ({i}/{n})")

    results = store.bulk_ensure(names, urls=urls, force=force, progress=_progress)
    bar.empty()
    status_box.empty()

    scraped = sum(1 for _, s in results.values() if s in ("scraped", "refreshed"))
    if scraped:
        st.success(f"{scraped} spelerdossier(s) gescrapet en opgeslagen â€” "
                   "de volgende keer laden ze direct uit de database.")

    if any(s == "no_scraper" for _, s in results.values()):
        st.error("Geen spelerscraper gevonden in het project.")
        with st.expander("Diagnose scraper"):
            st.json(adapter.diagnostics())

    save_preparation(m, str(my_team), opponent, names)

    for name in names:
        data, status = results[name]
        with st.expander(name, expanded=False):
            if not data:
                st.error(f"Geen gegevens beschikbaar ({status}).")
                continue
            if status == "failed":
                st.warning("Scrapen mislukt â€” onderstaande gegevens komen uit de database.")
            render_player_card(data, poule)


def _render_history() -> None:
    preps = load_preparations()
    if not preps:
        st.info("Nog geen eerdere voorbereidingen bewaard.")
        return
    preps.sort(key=lambda p: str(p.get("date") or ""), reverse=True)
    for p in preps:
        d = _to_date(p.get("date"))
        with st.expander(f"{d.strftime('%d/%m/%Y') if d else '?'} â€” "
                         f"{p.get('my_team')} vs {p.get('opponent')}"):
            st.caption(f"Poule: {p.get('poule') or 'onbekend'} Â· "
                       f"voorbereid op {str(p.get('prepared_at'))[:10]}")
            for name in p.get("player_names", []):
                data = store.get_player(name)
                st.markdown(f"**{name}** â€” huidige ranking: "
                            f"{(data or {}).get('current_ranking') or 'onbekend'}")


def render_opponent_analysis(user_name: str = "Kim Verbeke") -> None:
    st.header("Interclub â€” Tegenstanderanalyse")

    matches = load_matches()
    if not matches:
        st.error("Geen interclubmatchen gevonden in Firestore.")
        return

    tab_next, tab_hist = st.tabs(["Volgende Match", "Interclub Historiek"])
    with tab_next:
        _render_next_match(matches, user_name)
    with tab_hist:
        _render_history()


if __name__ == "__main__":
    st.set_page_config(page_title="Tegenstanderanalyse", layout="wide")
    render_opponent_analysis()
