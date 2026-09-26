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
Ontbreekt de playing strength, dan verwees de caption hier vroeger naar een
lokaal commando ('python bulk_fetch_padelstat_ratings.py'). Dat is sinds
PADEL_ANALYSIS_AUTO_ENRICH_OPPONENTS_2026-09-15 achterhaald: de GitHub
Actions-workflow (ci_scrape_all.py -> enrich_opponents.enrich()) haalt dit
AUTOMATISCH op voor elke speler in de run, inclusief eigen spelers. De tekst
legt dat nu uit i.p.v. een lokale actie te vragen, en biedt (enkel zichtbaar
als een GitHub-token geconfigureerd staat) een knop om dit voor DEZE speler
onmiddellijk te forceren.
--------------------------------------------------------------------------
PADEL_ANALYSIS_LINEUP_LOAD_PERSIST_FIX_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost): de "📅 Volgende match laden"-knop in page_lineup_lab.py riep
enkel _load_poule_fixtures() aan — een kale requests-fetch zonder
poule_id-scoping, die BOVENDIEN nooit iets naar Firestore schreef. Twee
zichtbare gevolgen: (1) "Geen wedstrijden gevonden" voor teams die wél
degelijk een geldige poule-URL hadden (de TVL-poule-tabel is een
client-side gerenderde SPA; een kale requests.get() ziet de tabel niet),
en (2) zelfs bij een gelukte fetch moest er bij ELKE herstart van de app
opnieuw geklikt worden, want er werd niets bewaard.
Fix: _load_poule_schedule_robust(player_id, reeks_url) hieronder. Is lokaal
scrapen beschikbaar (is_scraping_available()), dan wordt volledig
gedelegeerd aan poule_playwright.update_player_poule(player_id) — DEZELFDE
functie die de GitHub Actions-workflow en manual_poule_input.py al gebruiken.
Die functie lost zelf, intern en robuuster, de vraag "welke poule-URL geldt
voor deze speler" op (manuele override > gecachete URL > afgeleid uit het
recentste interclub-uitslagenblad) — daarom wordt de meegegeven `reeks_url`
in dit pad NIET gebruikt; die parameter dient uitsluitend voor de
KALE-fallback hieronder. Slaagt de robuuste weg, dan staat het resultaat al
in Firestore (interclub_schedule enz.) en wordt het via _get_saved_schedule()
teruggelezen.
Is lokaal scrapen NIET beschikbaar (Streamlit Community Cloud) of faalt de
Playwright-weg onverwacht, dan valt deze functie terug op de oude, kale
_load_poule_fixtures(reeks_url) — geen persistentie, geen pouleId-scoping,
enkel een beste-poging live-fetch. page_lineup_lab.py herkent dit onderscheid
aan `meta`: None bij de kale fallback, een dict bij de geslaagde robuuste weg
(en herlaadt de pagina dan meteen, zodat een volgende sessie niet opnieuw
hoeft te klikken).
--------------------------------------------------------------------------
PADEL_ANALYSIS_OWN_CLUB_FIELD_2026-09-20 (op verzoek van Kim: "Die scrape
moet weten in welke ploeg ik speel. ik kan dat niet instellen. ik zie daar
geen veld voor. dat moet zichtbaar en wijzigbaar zijn. bijkomend zou je
normaal dat veld moeten kunnen automatisch detecteren als je weet dat
iemand voor een bepaalde ploeg speelt.")
--------------------------------------------------------------------------
ACHTERGROND: het "club"-veld op een player_profiles-document (bv. "PADEL
FACTORY") is GEEN cosmetisch detail - scraper/refresh_padelstat_only.py
WEIGERT sinds PADEL_ANALYSIS_CLUB_REQUIRED_TO_SCRAPE_2026-09-20 een speler
zonder gekende club zelfs maar op te zoeken op padelstats.be (te riskant
bij gelijknamige spelers), en enrich_opponents.run_padelstat_for_players()
gebruikt hetzelfde veld als disambiguatie-hint. Tot nu toe bestond er
ECHTER GEEN plek in de app om dit veld voor een EIGEN speler te bekijken
of te wijzigen - het werd enkel impliciet gezet bij het automatisch
ontdekken van TEGENSTANDERS (enrich_opponents.discover_opponent_players(),
via het "encounter"-veld). Een eigen speler zonder club (bv. Kim zelf, als
dat veld om welke reden dan ook leeg staat) werd daardoor STRUCTUREEL
overgeslagen bij elke padelstat/officieel-klassement-verversing, zonder
enige zichtbare oorzaak of manier om dit zelf te herstellen.
FIX, twee onderdelen:
  1. _render_club_editor() - een klein, herbruikbaar UI-blok (huidige club
     tonen + tekstveld + "Opslaan"-knop) - toegevoegd aan zowel "🔍
     Spelers" (page_players.py) als "👤 Mijn profiel" (page_my_profile.py),
     vlak onder de naam. Dit maakt het veld voor het eerst ZICHTBAAR EN
     WIJZIGBAAR voor elke speler, inclusief jezelf.
  2. _maybe_autodetect_own_club() - bedoeld om aangeroepen te worden vanuit
     page_lineup_lab.py zodra een speler se EIGEN ploeg in een specifieke
     poule herkend is (own_ploeg_id, via schedule_scraper.
     identify_own_ploeg_id() of de handmatige team-picker). Leidt de
     clubnaam af uit de herkende teamnaam (bv. "PADEL FACTORY A" ->
     "PADEL FACTORY", team-letter weggeknipt - zelfde heuristiek als
     enrich_opponents._strip_team_letter_suffix() voor tegenstanders,
     hier lokaal herimplementeerd zodat dashboard_common.py geen
     afhankelijkheid van de scraper-map/Playwright hoeft te krijgen).
     Slaat dit ENKEL automatisch op als de speler nog HELEMAAL GEEN club
     had (nooit een reeds bestaande, mogelijk bewust andere club
     overschrijven) - net als de analoge club-override-logica in
     refresh_padelstat_only.py/enrich_opponents.py.
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
    """KALE fallback: een simpele requests-fetch, ZONDER poule_id-scoping en
    ZONDER Firestore-persistentie. Gebruikt door
    _load_poule_schedule_robust() hieronder wanneer lokaal scrapen niet
    beschikbaar is (Streamlit Community Cloud) of de robuuste weg onverwacht
    faalt."""
    try:
        html = ss.fetch_poule_schedule_html(reeks_url, delay=0.5)
        fixtures = ss.parse_poule_schedule(html)
        return fixtures, None
    except Exception as e:
        return [], str(e)
def _load_poule_schedule_robust(player_id: str, reeks_url: str):
    """PADEL_ANALYSIS_LINEUP_LOAD_PERSIST_FIX_2026-09-16.
    Robuuste, persisterende manier om het wedstrijdschema van een speler op
    te halen wanneer de gebruiker op '📅 Volgende match laden' klikt.
    Is lokaal scrapen beschikbaar, dan wordt volledig gedelegeerd aan
    poule_playwright.update_player_poule(player_id) — dezelfde functie die
    de GitHub Actions-workflow en manual_poule_input.py al gebruiken. Die
    functie lost zelf, robuuster, op welke poule-URL geldt (manuele
    override > gecachete URL > afgeleid uit het recentste interclub-
    uitslagenblad), scopet op pouleId, en schrijft het resultaat naar
    Firestore. De meegegeven `reeks_url` wordt in dit pad NIET gebruikt —
    die dient uitsluitend voor de kale fallback hieronder.
    Is lokaal scrapen niet beschikbaar (cloud) of faalt de Playwright-weg
    onverwacht, dan valt dit terug op de oude _load_poule_fixtures(reeks_url)
    (geen persistentie, geen pouleId-scoping).
    Returns (fixtures, fetch_error, meta):
        fixtures    : lijst fixture-dicts, of [] bij een fout.
        fetch_error : None, of een leesbare foutmelding.
        meta        : None als de KALE fallback gebruikt werd (dus NIET
                      gepersisteerd naar Firestore); een dict (met o.a.
                      'poule_label', 'poule_id') als de robuuste,
                      persisterende pijplijn geslaagd is — page_lineup_lab.py
                      herlaadt de pagina in dat geval, zodat de volgende
                      doorloop het resultaat uit Firestore terugvindt.
    """
    if not is_scraping_available():
        fixtures, error = _load_poule_fixtures(reeks_url)
        return fixtures, error, None
    try:
        import poule_playwright as pp
    except Exception:
        # Playwright zou beschikbaar moeten zijn maar de module faalt toch
        # te importeren -> val terug op de kale weg i.p.v. hard te crashen.
        fixtures, error = _load_poule_fixtures(reeks_url)
        return fixtures, error, None
    try:
        result = pp.update_player_poule(str(player_id), headless=True)
    except Exception as e:
        # Onverwachte fout in de robuuste weg -> nog een kans via de kale
        # fallback, in plaats van de gebruiker meteen te laten vastlopen.
        fixtures, error = _load_poule_fixtures(reeks_url)
        if fixtures:
            return fixtures, None, None
        return [], str(e), None
    if result.get("error"):
        return [], result["error"], None
    fixtures, _sched_at = _get_saved_schedule(player_id)
    meta = {
        "poule_id": result.get("poule_id"),
        "poule_label": result.get("poule_label"),
        "fixtures_count": result.get("fixtures"),
        "source": result.get("source"),
    }
    return fixtures, None, meta
def _clean_name(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())
# PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26 (op verzoek van Kim: "bekijk
# nu eens grondig dat lange wachten bij alle acties. ik merk daar weinig tot
# geen verbetering"):
# ROOT CAUSE: _get_all_profiles() deed een VOLLEDIGE Firestore-collectiescan
# ZONDER enige cache, en page_lineup_lab() riep dit ONVOORWAARDELIJK aan
# BOVENAAN de functie - dus bij ELKE widget-interactie op de hele pagina
# (Streamlit voert bij elke klik het volledige script opnieuw uit). Met 45+
# profielen en groeiend was dit een zware, herhaalde netwerkkost die door
# geen van de eerdere caching-rondes in page_lineup_lab.py geraakt werd -
# die zitten in een ANDER bestand en cachen andere dingen (rating-lookups
# per speler, matchdocumenten van de geselecteerde spelers), niet deze
# volledige-collectie-scan.
#
# FIX: st.cache_data(ttl=300) - dezelfde 5-minuten-conventie als de
# bestaande caches. clear_all_profiles_cache() hieronder laat de bestaande
# "Ploeg opnieuw ophalen"-knop in page_lineup_lab.py deze cache mee legen,
# zodat een net toegevoegde/ontdekte speler niet tot 5 minuten onzichtbaar
# blijft na een expliciete ververs-actie.
@st.cache_data(ttl=300, show_spinner=False)
def _get_all_profiles_cached() -> list:
    try:
        docs = fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()
        profiles = [d.to_dict() for d in docs]
        return [
            p for p in profiles
            if p and (p.get("display_name") or p.get("player_id"))
        ]
    except Exception:
        return []


def _get_all_profiles() -> list:
    """PADEL_ANALYSIS_GHOST_PROFILE_FILTER_2026-09-12:
    Filtert documenten zonder display_name/player_id uit de Spelers-lijst.

    PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26: gaat nu door
    _get_all_profiles_cached() - zie de toelichting hierboven voor waarom
    dit de dominante bron van traagheid was."""
    return _get_all_profiles_cached()


def clear_all_profiles_cache() -> None:
    """PADEL_ANALYSIS_ALL_PROFILES_CACHE_2026-09-26: leegt de cache
    hierboven. Aan te roepen vanuit elke "ververs"-knop die een nieuw
    profiel kan hebben aangemaakt of gewijzigd (bv. "Ploeg opnieuw ophalen"
    in page_lineup_lab.py), zodat het resultaat niet tot 5 minuten
    onzichtbaar blijft na een expliciete gebruikersactie."""
    try:
        _get_all_profiles_cached.clear()
    except Exception:
        pass
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


# ─────────────────────────────────────────────
# PADEL_ANALYSIS_OFFICIAL_RANK_SOURCE_FIX_2026-09-24
# ─────────────────────────────────────────────
def _official_rank_from_padelstat_snapshot(player_id) -> Optional[float]:
    """Het HUIDIGE, OFFICIELE klassement uit de padelstat-snapshot.

    Dit is de enige bron die bewezen correct is voor beide geteste spelers
    (zie de toelichting in apply_klassement_source_fix.py). De TVL-
    historiekpagina mengt het officiele en het virtuele klassement door
    elkaar: bij de ene speler klopt selected_period_klassement, bij de
    andere vorig_klassement - er is geen regel die voor iedereen werkt.

    Geeft None terug zodra er nog geen snapshot is; de aanroeper valt dan
    terug op de historiek. Bewust foutbestendig: een onverwachte
    firebase_service-vorm mag nooit een pagina laten crashen.
    """
    if not player_id:
        return None
    pid = str(player_id)

    # 1) Expliciete accessor, indien aanwezig.
    for naam in ("get_official_klassement_via_padelstat",
                 "get_official_klassement",
                 "get_official_rank_via_padelstat"):
        functie = getattr(fb, naam, None)
        if not callable(functie):
            continue
        try:
            data = functie(pid) or {}
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, (int, float)):
            return float(data)
        if isinstance(data, dict):
            for veld in ("klassement", "official_klassement", "rank", "value"):
                waarde = data.get(veld)
                if waarde is not None:
                    try:
                        return float(od._parse_rank(waarde) if isinstance(waarde, str) else waarde)
                    except (TypeError, ValueError):
                        pass

    # 2) Rechtstreeks van het profieldocument, onder het veld dat
    #    save_official_klassement_from_padelstat() wegschrijft.
    veldnaam = getattr(fb, "OFFICIAL_KLASSEMENT_VIA_PADELSTAT_FIELD",
                       "official_klassement_via_padelstat")
    try:
        profiel = fb.get_player_profile(pid) or {}
    except Exception:  # noqa: BLE001
        profiel = {}
    ruw = profiel.get(veldnaam)
    if isinstance(ruw, dict):
        ruw = ruw.get("klassement") or ruw.get("value")
    if ruw is not None:
        try:
            return float(od._parse_rank(ruw) if isinstance(ruw, str) else ruw)
        except (TypeError, ValueError):
            pass
    return None

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

    # PADEL_ANALYSIS_OFFICIAL_RANK_SOURCE_FIX_2026-09-24: de padelstat-
    # snapshot krijgt voorrang. De TVL-historiek bleef hier het zichtbare
    # cijfer bepalen, en die mengt het officiele met het virtuele klassement
    # (Kim werd zo P300 getoond terwijl hij officieel P200 is). De historiek
    # blijft enkel terugval zolang er nog geen snapshot bestaat.
    # PADEL_ANALYSIS_OFFICIAL_RANK_TVL_FIRST_2026-09-25: de TVL-historiek is opnieuw de PRIMAIRE bron.
    # De padelstat-snapshot komt uit de zoekkaart ("P200 - CLUB",
    # matched_klassement) en loopt aantoonbaar achter: speler 1790766
    # kreeg daar P200 terwijl scrape_klassement.py (versie
    # 2026-09-23-official-first) correct P300 leest als
    # selected_period_klassement. De snapshot blijft enkel terugval
    # zolang er nog GEEN historiek bestaat voor deze speler.
    rows = od._history_rows(ranking_doc)
    if rows and rows[0].get("rank") is not None:
        try:
            return float(rows[0]["rank"])
        except (TypeError, ValueError):
            pass

    snapshot = _official_rank_from_padelstat_snapshot(player_id)
    if snapshot is not None:
        return snapshot

    return None
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_HISTORY_SNAPSHOT_ALIGN_2026-09-24
# ─────────────────────────────────────────────
def _virtual_rank(player_id: str, official: Optional[float]) -> Optional[int]:
    """Het VIRTUELE klassement van deze speler: TVL's voorspelling voor de
    eerstvolgende officiele berekening.

    Op verzoek van Kim ("mss ook wel interessant bij spelers en ploeganalyse
    om ook virtueel klassement te tonen [...] ik vermoed dat de data
    beschikbaar is maar niet getoond") - dat vermoeden klopte: het cijfer
    stond al in klassement_history, maar werd op deze pagina's nergens
    getoond.

    Geeft None zodra het niet afwijkt van het officiele cijfer; dan valt er
    niets aparts te melden en blijft de bestaande tweekolomsweergave staan.
    """
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:
        doc = {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    ranking_doc = doc if doc.get("klassement_history") else profile_doc

    try:
        rows = od._history_rows(ranking_doc)
    except Exception:
        return None
    if not rows:
        return None

    # Het cijfer dat de TVL-pagina voor de lopende periode toont.
    getoond = rows[0].get("rank")
    virtueel = rows[0].get("virtual_rank")

    if official is not None and getoond is not None and int(getoond) != int(official):
        # De historiek toont iets anders dan het officiele cijfer: dat
        # verschil IS de voorspelling (zie opponent_dossier.
        # _correct_history_with_snapshot() voor de volledige redenering).
        return int(getoond)
    if virtueel is not None and (official is None or int(virtueel) != int(official)):
        return int(virtueel)
    return None

def _render_player_ranking_summary(player_id: str) -> None:
    """PADEL_ANALYSIS_PLAYER_RANKING_SUMMARY_2026-09-16 (op verzoek van Kim):
    Toont het officiële TVL-klassement en de padelstats.be playing strength
    DUIDELIJK (st.metric, twee kolommen) voor een gegeven speler.
    PADEL_ANALYSIS_PADELSTAT_AUTOMATIC_CAPTION_2026-09-16: ontbreekt de
    playing strength, dan legt de caption uit dat dit AUTOMATISCH gebeurt via
    de reguliere sync, met (enkel zichtbaar als een GitHub-token
    geconfigureerd staat) een knop om dit voor DEZE speler onmiddellijk te
    forceren."""
    official = _official_current_rank(player_id)
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:
        cached = None
    padelstat = cached.get("rating") if cached else None
    # PADEL_ANALYSIS_HISTORY_SNAPSHOT_ALIGN_2026-09-24: een DERDE metric
    # "Virtueel klassement", maar enkel als er effectief een afwijkend
    # cijfer gekend is - anders blijft de bestaande, rustige
    # tweekolomsweergave staan i.p.v. een lege kolom te tonen.
    virtueel = _virtual_rank(player_id, official)
    if virtueel is not None:
        c1, c2, c3 = st.columns(3)
    else:
        c1, c2 = st.columns(2)
        c3 = None

    c1.metric(
        "Officieel klassement",
        f"P{int(official)}" if official is not None else "Onbekend",
        help=(
            "Het klassement dat NU officieel geldt, tot de eerstvolgende "
            "TVL-berekening (2x per jaar). Komt uit de padelstat-snapshot, de enige "
            "bron die hiervoor betrouwbaar gebleken is."
        ),
    )
    c2.metric(
        "Playing strength (padelstats.be)",
        f"P{padelstat}" if padelstat is not None else "Onbekend",
        help=(
            "Onafhankelijke, externe schatting van de speelsterkte door padelstats.be. "
            "Dit is GEEN TVL-klassement en heeft geen officiele waarde."
        ),
    )
    if c3 is not None:
        c3.metric(
            "Virtueel klassement", f"P{virtueel}",
            help=(
                "De voorspelling van TVL voor de EERSTVOLGENDE officiele "
                "klassementsberekening, op basis van de resultaten van deze periode. "
                "Nog niet geldig - het officiele klassement blijft wat links staat, "
                "en dit cijfer kan bij de definitieve berekening nog wijzigen."
            ),
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
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_OWN_CLUB_FIELD_2026-09-20: zie module-docstring hierboven
# voor de volledige achtergrond/root-cause-analyse.
# ─────────────────────────────────────────────
_TEAM_LETTER_SUFFIX_RE = re.compile(r"\s+[A-Za-z]$")
def _strip_team_letter_suffix(text: str) -> str:
    """Knipt een losse team-letter aan het einde weg ("Padel Factory A" ->
    "Padel Factory"). Lokale kopie van dezelfde heuristiek als
    scraper/enrich_opponents.py (daar voor TEGENSTANDERS, hier voor de
    EIGEN speler) - bewust hier gedupliceerd i.p.v. geïmporteerd, zodat dit
    UI-bestand geen afhankelijkheid van de Playwright-scraper-map krijgt."""
    return _TEAM_LETTER_SUFFIX_RE.sub("", (text or "").strip()).strip()
def _get_club(player_id: str) -> Optional[str]:
    """Geeft de huidige, opgeslagen club/ploeg van deze speler terug (of
    None als nog niet ingesteld)."""
    try:
        prof = fb.get_player_profile(player_id) or {}
    except Exception:
        prof = {}
    club = (prof.get("club") or "").strip()
    return club or None
def _save_club(player_id: str, club: str) -> None:
    """Slaat de club/ploeg van deze speler op (merge=True, raakt geen
    andere velden van het profiel)."""
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(player_id)).set(
            {"club": (club or "").strip()}, merge=True,
        )
    except Exception:
        pass
def _render_club_editor(player_id: str, profile: dict, key_prefix: str) -> None:
    """PADEL_ANALYSIS_OWN_CLUB_FIELD_2026-09-20 (op verzoek van Kim: "Die
    scrape moet weten in welke ploeg ik speel. ik kan dat niet instellen. ik
    zie daar geen veld voor. dat moet zichtbaar en wijzigbaar zijn."):
    Toont het huidige club/ploeg-veld van deze speler, ZICHTBAAR EN
    WIJZIGBAAR. Dit veld bepaalt of scraper/refresh_padelstat_only.py deze
    speler OVERHAUPT opzoekt op padelstats.be (zie PADEL_ANALYSIS_CLUB_
    REQUIRED_TO_SCRAPE_2026-09-20 aldaar - een speler zonder gekende club
    wordt daar NIET opgezocht, uit voorzorg tegen gelijknamige spelers bij
    andere clubs) en wordt ook gebruikt als disambiguatie-hint door
    padelstats_scraper.py/enrich_opponents.py.
    Ingeklapt getoond (expanded=False) zodra er al een club gekend is (dan
    is dit vooral een correctie-mogelijkheid), maar UITGEKLAPT (expanded=
    True) zodra er nog GEEN club gekend is - net op de plek waar dit het
    meest opvalt en het meest nodig is om in te vullen."""
    current = _get_club(player_id) or (profile.get("club") or "").strip() or None
    header = f"🏟️ Club/ploeg: {current}" if current else "🏟️ Club/ploeg (nog niet ingesteld ⚠️)"
    with st.expander(header, expanded=not bool(current)):
        st.caption(
            "Bepaalt bij welke club/ploeg deze speler gezocht wordt op padelstats.be (playing "
            "strength + officieel klassement, zie 'Officieel klassement' hieronder). Zonder "
            "gekende club wordt deze speler NIET automatisch ververst, om verwarring met "
            "gelijknamige spelers bij andere clubs te vermijden."
        )
        new_value = st.text_input(
            "Club/ploeg", value=current or "", key=f"{key_prefix}_club_input_{player_id}",
            placeholder="Bv. Padel Factory",
        )
        if st.button("💾 Club opslaan", key=f"{key_prefix}_club_save_{player_id}"):
            _save_club(player_id, new_value)
            st.success("Club opgeslagen.")
            st.rerun()
def _maybe_autodetect_own_club(player_id: str, fixtures: list, own_ploeg_id: Optional[str]) -> None:
    """PADEL_ANALYSIS_OWN_CLUB_FIELD_2026-09-20 (op verzoek van Kim:
    "bijkomend zou je normaal dat veld moeten kunnen automatisch
    detecteren als je weet dat iemand voor een bepaalde ploeg speelt"):
    Leidt, zodra de EIGEN ploeg in een specifieke poule herkend is
    (own_ploeg_id, via schedule_scraper.identify_own_ploeg_id() of de
    handmatige team-picker in page_lineup_lab.py._resolve_own_ploeg_id()),
    een club-naam af uit de bijhorende teamnaam (bv. "PADEL FACTORY A" ->
    "PADEL FACTORY") en slaat die ENKEL op als de speler nog GEEN club
    had. Overschrijft NOOIT een reeds ingestelde club (die kan bewust
    anders zijn, bv. bij dubbel-clublidmaatschap) - in dat geval gebeurt
    hier stilzwijgend niets. Bedoeld om aangeroepen te worden vanuit
    page_lineup_lab.py, waar fixtures/own_ploeg_id al gekend zijn zodra
    het wedstrijdschema geladen is."""
    if not own_ploeg_id or not fixtures:
        return
    if _get_club(player_id):
        return  # al gekend - nooit overschrijven.
    team_name = None
    for f in fixtures:
        if str(f.get("home_ploeg_id")) == str(own_ploeg_id):
            team_name = f.get("home_name")
            break
        if str(f.get("away_ploeg_id")) == str(own_ploeg_id):
            team_name = f.get("away_name")
            break
    if not team_name:
        return
    derived = _strip_team_letter_suffix(team_name)
    if not derived:
        return
    _save_club(player_id, derived)
    st.caption(f"ℹ️ Club automatisch ingesteld op '{derived}' (afgeleid van je teamnaam in deze poule).")
