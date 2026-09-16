"""
dashboard_common.py — gedeelde helpers, imports en state voor alle
PadelAnalysis-paginamodules.

PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14 (op verzoek van Kim):
dashboard.py was gegroeid tot ~1800 regels, wat elke wijziging traag en
foutgevoelig maakte (een volledige herschrijving was nodig per aanpassing).
Dit bestand bevat alle logica die door MEERDERE paginamodules gedeeld wordt:
  - alle externe module-imports (firebase_service, lineup_lab, enz.);
  - kleine, generieke helperfuncties (datum-parsing, naam-opzoek, tabellen);
  - profiel-/schedule-opzoekfuncties.

De paginamodules zelf:
  - page_add_player.py      : "➕ Speler toevoegen"
  - page_lineup_lab.py      : "🧩 Opstelling-analyse" (incl. rotatieplanner)
  - player_dashboard_shared.py : render_player_dashboard() - de tabs
    (Overzicht/Match Explorer/Partners/Tegenstanders/Klassement/Debug),
    HERGEBRUIKT door zowel "👤 Mijn profiel" als "🔍 Spelers".
  - page_my_profile.py      : "👤 Mijn profiel"
  - page_players.py         : "🔍 Spelers"

dashboard.py zelf is nu enkel nog de dunne entrypoint: st.set_page_config,
CSS, navigatie, en de routing naar page_xxx().

BELANGRIJK: dit bestand doet ZELF geen st.set_page_config()/CSS-injectie -
dat blijft in dashboard.py (het echte entrypoint-script), zodat het maar
één keer per app-run gebeurt, ongeacht welke pagina-modules geïmporteerd
worden.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PLAYER_RANKING_SUMMARY_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
Kim wil bij spelers duidelijk het huidige (officiële) klassement EN de
padelstats.be playing strength zien. Die weergave bestond al, maar enkel
lokaal in page_my_profile.py als _render_profile_ranking_summary()
(PADEL_ANALYSIS_MYPROFILE_RANKING_SUMMARY_2026-09-14) - dus zichtbaar op
"👤 Mijn profiel", maar NIET op "🔍 Spelers", waar je elke andere speler
bekijkt.

Fix: de functie is hierheen verplaatst (algemener bruikbaar, dus hernoemd
naar _render_player_ranking_summary(), zonder "profile" in de naam) zodat
BEIDE pagina's dezelfde, duidelijke weergave (st.metric, twee kolommen)
kunnen tonen zonder de logica te dupliceren. page_my_profile.py roept deze
gedeelde versie nu aan i.p.v. zijn eigen kopie; page_players.py roept ze
voor het eerst aan.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_AUTOMATIC_CAPTION_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
Kim's vraag: "bedoel was om dat niet lokaal te doen maar meteen mee te
scrapen. check als dat al gebeurd is." Antwoord: JA, dat is al gebouwd.
Sinds PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15 haalt
scraper/ci_scrape_all.py (via enrich_opponents.enrich()) de padelstats.be
playing strength AUTOMATISCH op voor élke speler in de run - en dat is niet
beperkt tot tegenstanders: enrich_opponents.enrich(player_ids, ...) gebruikt
diezelfde player_ids (bij een normale run: ALLE eigen spelers uit
player_profiles) als doelgroep voor de padelstat-stap. "python
bulk_fetch_padelstat_ratings.py" was het OUDE, handmatige pad van vóór die
datum en is voor normaal gebruik niet meer nodig.

BUG (verouderde tekst, opgelost): de caption hieronder verwees nog naar dat
oude, lokale commando, wat nu misleidend is - het geeft de indruk dat er
iets handmatigs moet gebeuren, terwijl de bedoeling exact het omgekeerde is
(automatisch via de GitHub Actions-sync).

Blijft een speler tóch zonder playing strength staan, dan is de meest
waarschijnlijke reden dat de workflow zelf nog niet (betrouwbaar) gedraaid
heeft voor die speler - zie de aparte, lopende fix van de GitHub Actions
schedule-trigger (vervangen door een externe GCP Cloud Scheduler-aanroep,
zie gcp-triggers/mAIcoach-sync-trigger/) - of dat PADELSTAT_MAX (standaard
25 per run) die speler nog niet bereikt heeft, of dat de speler simpelweg
niet gevonden wordt op padelstats.be (bv. Boerjan Senne, bevestigd
onvindbaar).

Fix: de caption legt nu uit dat dit AUTOMATISCH gebeurt via de reguliere
sync, en biedt (enkel als een GitHub-trigger geconfigureerd staat, via
cloud_helpers.render_cloud_scrape_trigger - toont zichzelf niet als dat niet
het geval is) een knop om dit ONMIDDELLIJK voor DEZE ENE speler te forceren,
i.p.v. te verwijzen naar een lokaal script.
"""
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st
from datetime import datetime

# --- Path setup: idempotent, mag door elke module die dit importeert
# opnieuw uitgevoerd worden (de if-check voorkomt duplicaten in sys.path). ---
_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "scraper")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import firebase_service as fb
import lineup_lab as ll
import schedule_scraper as ss
import opponent_scout as osc
import opponent_scout_ui as osu
import opponent_analysis as oa
import lineup_quick as lq
import player_inline_actions as pia
import opponent_dossier as od

try:
    import team_ai_advisor as taa
except Exception:  # pragma: no cover - AI-veld is optioneel, rest blijft werken
    taa = None

from cloud_helpers import is_scraping_available, render_cloud_scrape_trigger


# ─────────────────────────────────────────────
# Datum-/tekst-helpers
# ─────────────────────────────────────────────
def _clean(text) -> str:
    return " ".join(str(text or "").split()).strip()


# PADEL_ANALYSIS_PERIOD_SORT_FIX
_SEASON_START_MONTH = {
    "winter": 9,
    "najaar": 9, "herfst": 9,
    "zomer": 5,
    "lente": 3, "voorjaar": 3,
}
_MONTH_RANK = {
    "jan": 1, "feb": 2, "mrt": 3, "maart": 3, "apr": 4, "mei": 5, "jun": 6, "juni": 6,
    "jul": 7, "juli": 7, "aug": 8, "sep": 9, "sept": 9, "okt": 10, "nov": 11, "dec": 12,
}
_DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def _parse_match_date(text) -> Optional[tuple]:
    if not text:
        return None
    text = str(text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (y, mo, d)
    m = re.search(r"(\d{1,2})\s+([a-zA-Zàéè]+)\s+(\d{4})", text.lower())
    if m:
        mo = _DUTCH_MONTHS.get(m.group(2))
        if mo:
            return (int(m.group(3)), mo, int(m.group(1)))
    return None


def _format_scraped_at(value):
    if not value:
        return "onbekend"
    try:
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y %H:%M")
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
    text = str(label or "").lower()
    year_m = re.search(r"(20\d{2})", text)
    year = int(year_m.group(1)) if year_m else 0
    month = next((m for kw, m in _SEASON_START_MONTH.items() if kw in text), None)
    if month is None:
        month = next((m for kw, m in _MONTH_RANK.items() if kw in text), 6)
    return (year, month)


def _display_name(profile_or_id, name_lookup: Optional[dict] = None) -> str:
    if isinstance(profile_or_id, dict):
        return profile_or_id.get("display_name") or f"Onbekende speler ({profile_or_id.get('player_id','?')})"
    pid = profile_or_id
    if name_lookup:
        name = name_lookup.get(pid)
        if name:
            return name
    return f"Onbekende speler ({pid})"


def _go_to_player(player_id: str):
    st.session_state["jump_to_player_id"] = str(player_id)
    st.session_state["page"] = "🔍 Spelers"
    st.rerun()


def _scrape_progress_widget(label_prefix: str = ""):
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


# PADEL_ANALYSIS_STATS_FROM_MATCHES_FIX_2026-09-07
def _calc_stats_from_matches(matches: list) -> dict:
    matches = matches or []
    won = sum(1 for m in matches if m.get("won") is True)
    lost = sum(1 for m in matches if m.get("won") is False)
    total = len(matches)
    known = won + lost
    return {
        "total_matches": total,
        "wins": won,
        "losses": lost,
        "unknown": total - known,
        "winrate": round(won / known * 100, 1) if known else 0.0,
        "tournament_matches": sum(1 for m in matches if m.get("match_type") == "tornooi"),
        "interclub_matches": sum(1 for m in matches if m.get("match_type") == "interclub"),
    }


def _persist_stats_if_needed(player_id: str, player_doc: dict, live_stats: dict) -> None:
    """PADEL_ANALYSIS_STATS_SELFHEAL_2026-09-07."""
    stored = (player_doc or {}).get("stats", {}) or {}
    if int(stored.get("total_matches", -1)) == int(live_stats["total_matches"]):
        return
    try:
        fb.db.collection(fb.PLAYERS_COLLECTION).document(str(player_id)).set(
            {"stats": live_stats}, merge=True
        )
    except Exception:
        pass


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
        matches=("tegenstander", "size"),
        wins=("won", lambda x: x.eq(True).sum()),
        losses=("won", lambda x: x.eq(False).sum()),
    ).reset_index()
    g["winrate"] = g.apply(lambda r: _winrate_str(r.wins, r.losses), axis=1)
    known = g["wins"] + g["losses"]
    g["_wr_num"] = g["wins"] / known.replace(0, 1)
    result = g.sort_values(["_wr_num", "matches"], ascending=[False, False]).drop(columns=["_wr_num"])
    return result


def _render_table(df: pd.DataFrame, name_col: str, height=400):
    if df.empty:
        st.info("Geen data beschikbaar.")
        return
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
# State/profiel-helpers
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Wedstrijdschema ophalen...")
def _load_poule_fixtures(reeks_url: str):
    try:
        html = ss.fetch_poule_schedule_html(reeks_url, delay=0.5)
        fixtures = ss.parse_poule_schedule(html)
        return fixtures, None
    except Exception as e:
        return [], str(e)


def _clean_name(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _get_all_profiles() -> list:
    """PADEL_ANALYSIS_GHOST_PROFILE_FILTER_2026-09-12:
    Filtert documenten zonder display_name/player_id uit de Spelers-lijst."""
    try:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        profiles = [d.to_dict() for d in docs]
        return [
            p for p in profiles
            if p and (p.get("display_name") or p.get("player_id"))
        ]
    except Exception:
        return []


def _get_saved_poule_url(player_id: str) -> Optional[str]:
    try:
        prof = fb.get_player_profile(player_id) or {}
        return prof.get("poule_reeks_url") or None
    except Exception:
        return None


def _save_poule_url(player_id: str, url: str) -> None:
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
            {"poule_reeks_url": url}, merge=True
        )
    except Exception:
        pass


def _get_saved_schedule(player_id: str):
    try:
        prof = fb.get_player_profile(player_id) or {}
    except Exception:
        prof = {}
    fixtures = prof.get("interclub_schedule") or []
    if not isinstance(fixtures, list):
        fixtures = []
    return fixtures, prof.get("interclub_schedule_scraped_at")


def _official_current_rank(player_id: str) -> Optional[float]:
    """PADEL_ANALYSIS_MATCH1_STRONGEST_RULE_2026-09-14:
    Geeft het OFFICIËLE, HUIDIGE TVL-klassement terug voor een eigen speler -
    rechtstreeks uit diens klassement_history, NIET via padelstats.be. Wordt
    gebruikt door zowel page_lineup_lab.py (Match1-regel in de rotatieplanner)
    als _render_player_ranking_summary() hieronder (ranking-samenvatting,
    gebruikt door zowel page_my_profile.py als page_players.py) - vandaar hier
    in het gedeelde bestand geplaatst."""
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:
        doc = {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    ranking_doc = doc if doc.get("klassement_history") else profile_doc
    rows = od._history_rows(ranking_doc)
    return float(rows[0]["rank"]) if rows else None


def _render_player_ranking_summary(player_id: str) -> None:
    """PADEL_ANALYSIS_PLAYER_RANKING_SUMMARY_2026-09-16 (op verzoek van Kim):
    Toont het officiële TVL-klassement en de padelstats.be playing strength
    DUIDELIJK (st.metric, twee kolommen) voor een gegeven speler.

    Was voorheen een LOKALE functie in page_my_profile.py
    (_render_profile_ranking_summary, PADEL_ANALYSIS_MYPROFILE_RANKING_
    SUMMARY_2026-09-14), enkel zichtbaar op '👤 Mijn profiel'. Kim vroeg
    dezelfde, duidelijke weergave ook op '🔍 Spelers' - vandaar hierheen
    verplaatst (hernoemd, algemener) zodat BEIDE pagina's 'm kunnen
    hergebruiken zonder de logica te dupliceren.

    PADEL_ANALYSIS_PADELSTAT_AUTOMATIC_CAPTION_2026-09-16: ontbreekt de
    playing strength, dan verwees de caption hier vroeger naar een lokaal
    commando ('python bulk_fetch_padelstat_ratings.py'). Dat is sinds
    PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15 achterhaald: de
    GitHub Actions-workflow (ci_scrape_all.py -> enrich_opponents.enrich())
    haalt dit AUTOMATISCH op voor elke speler in de run, inclusief eigen
    spelers. De tekst legt dat nu uit i.p.v. een lokale actie te vragen, en
    biedt (enkel zichtbaar als een GitHub-token geconfigureerd staat) een
    knop om dit voor DEZE speler onmiddellijk te forceren."""
    official = _official_current_rank(player_id)
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:
        cached = None
    padelstat = cached.get("rating") if cached else None
    c1, c2 = st.columns(2)
    c1.metric("Officieel klassement", f"P{int(official)}" if official is not None else "Onbekend")
    c2.metric(
        "Playing strength (padelstats.be)",
        f"P{padelstat}" if padelstat is not None else "Onbekend",
    )
    if padelstat is None:
        st.caption(
            "Playing strength wordt normaal AUTOMATISCH opgehaald van padelstats.be bij "
            "elke reguliere data-update (geen lokale actie nodig). Staat ze hier nog op "
            "'Onbekend', dan is meestal de update nog niet (recent genoeg) gedraaid voor "
            "deze speler, of is deze speler niet gevonden op padelstats.be."
        )
        render_cloud_scrape_trigger(
            key_prefix=f"ranking_padelstat_{player_id}",
            player_ids=str(player_id),
            mode="missing",
            label="🔄 Playing strength nu ophalen",
        )
