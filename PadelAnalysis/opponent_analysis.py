"""
opponent_analysis.py - samengevat analysescherm voor de volledige tegenploeg (v14).

PADEL_ANALYSIS_TWO_LAYER_2026-09-10
De overzichtstabel toont per speler ZOWEL de huidige poule als de historiek
uit vorige periodes, in aparte kolommen.

PADEL_ANALYSIS_PADELSTAT_ONLY_2026-09-13 (v7):
Overzichtstabel toont "Playing strength" rechtstreeks uit de gecachete
padelstats.be-waarde (via build_player_summary(), zie opponent_dossier.py).

PADEL_ANALYSIS_REMOVE_OWN_LINEUP_EDITOR_2026-09-13 (v8):
De "Onze opstelling"-sectie is volledig verwijderd - al gedekt door de
Opstelling-scenario's in dashboard.py.

PADEL_ANALYSIS_RENDER_SPLIT_2026-09-14 (v9, op verzoek van Kim):
Kim wil de Opstelling-scenario's + AI-functies BOVENAAN de pagina tonen, en
pas DAARONDER de overzichtstabel/detail-per-speler van de tegenploeg. Om
dashboard.py toe te laten die volgorde zelf te bepalen, is render_team_analysis()
opgesplitst in herbruikbare stukken die elk apart aanroepbaar zijn:
  - get_team_report(...)              : bouwt/cachet het rapport, geen UI.
  - render_team_header(...)           : titel + "Verversen"-knop, geeft
                                         het (evt. ververste) rapport terug.
  - render_ai_section(report, ...)    : "AI-inzichten" (was _render_ai_section,
                                         nu publiek zodat dashboard.py dit
                                         apart, HOGER op de pagina, kan tonen).
  - render_overview_and_detail(...)   : overzichtstabel + detail-per-speler.
render_team_analysis() blijft bestaan als dunne wrapper (roept alle
bovenstaande in de OUDE volgorde aan) voor eventuele andere/toekomstige
aanroepers die de vroegere volgorde verwachten - dashboard.py gebruikt sinds
deze versie de losse functies rechtstreeks, in de NIEUWE volgorde.

PADEL_ANALYSIS_REMOVE_JUMP_BUTTON_2026-09-14:
De "👁️ Volledige spelerpagina"-knop bij Detail-per-speler is verwijderd.
Verder in v9: "board" hernoemd naar "dubbel"; bordpositie-heuristiek
volledig verwijderd.

PADEL_ANALYSIS_TEAM_REPORT_STALE_CACHE_FIX_2026-09-17 (v10):
_underlying_data_is_fresher() zorgt dat het team-rapport automatisch
herbouwt zodra padelstat/klassement van een speler ondertussen ververst is.

PADEL_ANALYSIS_SPARK_QUOTA_CACHE_2026-09-17 (v11):
_underlying_data_is_fresher() gebruikt freshness_cache.py (sessie-lokale
TTL-cache) i.p.v. rechtstreekse Firestore-reads, om de Spark-plan-daglimiet
(50.000 reads) niet nodeloos te belasten.

--------------------------------------------------------------------------
PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18 (v12, op verzoek van Kim: "bij de
AI functie kan je zaken intypen in een prompt en dat werkt maar je kan niet
verder doorvragen in nieuwe prompt")
--------------------------------------------------------------------------
ROOT CAUSE (bevestigd in team_ai_advisor.py): elke "Vraag AI"-klik startte
een volledig nieuwe, contextloze OpenAI-conversatie - er werd nergens een
gespreksgeschiedenis bijgehouden of meegestuurd, dus een vervolgvraag werd
behandeld alsof het de EERSTE vraag was.
FIX: render_ai_section() is herschreven tot een ECHTE chat:
  - st.session_state houdt nu een `{key_prefix}_chat_history_v12_{ploeg_id}`-
    lijst bij van {"role": "user"/"assistant", "content": str}-dicts, in
    chronologische volgorde.
  - Bij elke nieuwe vraag wordt taa.ask_followup(question, report, history)
    aangeroepen MET de volledige, tot dan opgebouwde geschiedenis (zie
    team_ai_advisor.py, PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18) - het
    taalmodel "onthoudt" dus wat er eerder in dit gesprek gezegd is.
  - De VOLLEDIGE geschiedenis wordt getoond (met st.chat_message, zodat het
    er ook visueel als een doorlopend gesprek uitziet), niet enkel het
    laatste antwoord.
  - "💡 Genereer inzichten" blijft het GESPREK STARTEN (of herstarten) - het
    automatische inzicht wordt als eerste "assistant"-bericht toegevoegd aan
    een verse geschiedenis, zodat een vervolgvraag daar ook op kan
    voortbouwen.
  - Nieuwe knop "🗑️ Nieuw gesprek" wist de geschiedenis expliciet, voor als
    Kim bewust opnieuw wil beginnen (bv. na een sterk gewijzigde tegenstander-
    analyse) i.p.v. impliciet door te blijven bouwen op een inmiddels
    irrelevant gesprek.

--------------------------------------------------------------------------
PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19 (v13, op verzoek
van Kim: "Padelstat cijfers zouden wel scheduled moeten updaten. Ik wil dat
wel 1 keer per week op maandag maar ook als je op analyse ploeg drukt om
zeker de laatste waarde te hebben wanneer je dat doet.")
--------------------------------------------------------------------------
De "🔄 Verversen"-knop in render_team_header() herbouwde voorheen ENKEL het
rapport uit REEDS GECACHETE Firestore-waarden (build_player_summary() leest
gewoon de bestaande padelstat_rating/klassement_history uit) - er gebeurde
GEEN nieuwe scrape/verversing. Dat is precies wat Kim's melding "ook als je
op analyse ploeg drukt om zeker de laatste waarde te hebben" aankaart: een
klik op "Verversen" gaf geen enkele garantie dat de onderliggende padelstat-
waarde zelf recent was, enkel dat het RAPPORT de (mogelijk verouderde)
cache opnieuw inlas.
FIX: render_team_header() vraagt nu, bij elke klik op "🔄 Verversen", ook
EXPLICIET een geforceerde padelstat-verversing aan voor de volledige
tegenploeg-roster (via cloud_helpers.trigger_github_actions_scrape(),
force_all="true") - VOOR het rapport herbouwd wordt. Op Cloud (Kim's
gebruikelijke omgeving) is dit een ASYNCHRONE GitHub Actions-trigger (dus
met de gebruikelijke 1-3 minuten vertraging van workflow_dispatch, een
technische grens van GitHub Actions zelf, geen keuze) - het rapport dat
DIRECT na deze klik verschijnt gebruikt dus nog de vorige waarde, maar
_underlying_data_is_fresher() (zie hieronder, ongewijzigd) zorgt dat het
rapport zichzelf automatisch herbouwt zodra de verse waarde binnenkomt, bij
een volgende render van deze pagina. Dit is dezelfde asynchrone aanpak als
_ensure_fresh_padelstat_for_roster() in opponent_scout_ui.py (bij
"🔍 Tegenstander analyseren") - beide knoppen garanderen nu consistent een
verse-waarde-aanvraag.

--------------------------------------------------------------------------
PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19 (v14, op verzoek van Kim, chat
2026-09-19: "Ook wel handig om een link naar het klassement te hebben bij
de ploeganalyse. eventueel in aparte tab.")
--------------------------------------------------------------------------
Twee, elkaar aanvullende toevoegingen (bewust GEEN ingrijpende herstructurering
van de bestaande Overzicht/Detail-indeling, om niets te breken voor de
bestaande aanroepers - page_lineup_lab.py, poule_teams_ui.py - die
render_overview_and_detail() als 1 ondeelbaar blok aanroepen):
  1. De Overzichtstabel krijgt een NIEUWE "🔗 Klassement"-kolom
     (st.column_config.LinkColumn) - rechtstreeks klikbaar vanuit de tabel
     zelf, per speler. Gebruikt build_player_summary()'s (opponent_dossier.py)
     nieuwe "klassement_url"-veld - geen aparte URL-berekening hier nodig.
     Valt terug op een gewone tekstkolom (ruwe URL) als LinkColumn niet
     beschikbaar is (oudere Streamlit-versie) - nooit een harde crash.
  2. Nieuwe, aparte sectie "🔗 Alle klassement-links op TVL" (een
     st.expander, ingeklapt getoond onder de Overzichtstabel) die ELKE
     speler als een losse, klikbare link-knop toont - dit is de "eventueel
     in aparte tab"-optie die Kim noemde. Gekozen voor een expander i.p.v.
     een letterlijke st.tabs()-herstructurering van deze functie, om het
     bestaande Overzicht/Detail-gedrag 100% ongewijzigd te laten (lagere
     regressiekans) - zeg het gerust als een ECHTE aparte tab (st.tabs())
     hiervoor toch de voorkeur geniet, dat is een kleine aanpassing.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Callable, Optional
import pandas as pd
import streamlit as st
import firebase_service as fb
import opponent_dossier as od
import freshness_cache as fcache
try:
    import team_ai_advisor as taa
except Exception:  # pragma: no cover - AI-veld is optioneel, rest blijft werken
    taa = None
try:  # cloud_helpers is optioneel aanwezig; nooit hard falen op import
    from cloud_helpers import is_scraping_available, trigger_github_actions_scrape
except Exception:  # pragma: no cover
    def is_scraping_available() -> bool:
        return False
    def trigger_github_actions_scrape(**_kwargs):
        return False, "cloud_helpers ontbreekt"
REPORTS_COLLECTION = "team_scouting_reports"
REPORT_SCHEMA_VERSION = 8  # ongewijzigd datamodel; enkel rendering/cache-logica aangepast in v9-v14
PADELSTAT_WORKFLOW_FILE = "refresh-padelstat.yml"
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
def _format_ts(value) -> str:
    if not value:
        return "onbekend"
    try:
        cleaned = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)
def _parse_iso(value) -> Optional[datetime]:
    """PADEL_ANALYSIS_TEAM_REPORT_STALE_CACHE_FIX_2026-09-17: robuuste
    ISO-timestamp-parser."""
    if not value:
        return None
    try:
        cleaned = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
def _parse_simple_date(text) -> Optional[tuple]:
    if not text:
        return None
    text = str(text).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    return None
# ─────────────────────────────────────────────
# Rapport opbouwen / bewaren / laden
# ─────────────────────────────────────────────
def _build_report(
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str],
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
) -> dict:
    players = []
    for player in bundle.get("unique_players", []) or []:
        players.append(od.build_player_summary(
            player["user_id"], player["name"], all_docs,
            current_reeks_url=current_reeks_url,
            current_spelgroep_id=current_spelgroep_id,
            global_docs=global_docs,
        ))
    return {
        "opponent_name": opp.get("name"),
        "opponent_ploeg_id": opp.get("ploeg_id"),
        "reeks_url": current_reeks_url,
        "spelgroep_id": current_spelgroep_id,
        "updated_at": _now_iso(),
        "schema_version": REPORT_SCHEMA_VERSION,
        "players": players,
    }
def _save_report(report: dict) -> None:
    doc_id = str(report.get("opponent_ploeg_id") or "onbekend")
    try:
        fb.db.collection(REPORTS_COLLECTION).document(doc_id).set(
            fb.sanitize_for_firestore(report)
        )
    except Exception:
        pass  # Bewaren is comfort, geen blokkerende vereiste voor de UI.
def _load_report(ploeg_id: str) -> Optional[dict]:
    try:
        doc = fb.db.collection(REPORTS_COLLECTION).document(str(ploeg_id)).get()
        return doc.to_dict() if doc.exists else None
    except Exception:
        return None
def _underlying_data_is_fresher(report: dict, bundle: dict) -> bool:
    """PADEL_ANALYSIS_TEAM_REPORT_STALE_CACHE_FIX_2026-09-17, aangepast in
    PADEL_ANALYSIS_SPARK_QUOTA_CACHE_2026-09-17. Zie module-docstring."""
    report_updated = _parse_iso(report.get("updated_at"))
    if report_updated is None:
        return True
    for player in bundle.get("unique_players", []) or []:
        pid = str(player.get("user_id") or "")
        if not pid:
            continue
        freshness = fcache.get_freshness(pid)
        fetched_at = _parse_iso(freshness.get("padelstat_fetched_at"))
        if fetched_at and fetched_at > report_updated:
            return True
        scraped_at = _parse_iso(freshness.get("klassement_scraped_at"))
        if scraped_at and scraped_at > report_updated:
            return True
    return False
def _needs_rebuild(
    report: Optional[dict],
    bundle: dict,
    current_spelgroep_id: Optional[str] = None,
) -> bool:
    if not report:
        return True
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        return True
    if str(report.get("spelgroep_id") or "") != str(current_spelgroep_id or ""):
        return True
    known_ids = {str(p.get("player_id")) for p in report.get("players", []) or []}
    bundle_ids = {str(p["user_id"]) for p in bundle.get("unique_players", []) or []}
    if not bundle_ids.issubset(known_ids):
        return True
    if _underlying_data_is_fresher(report, bundle):
        return True
    return False
def get_team_report(
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
    key_prefix: str = "team_analysis",
) -> dict:
    """Bouwt/cachet het volledige team-scoutingrapport, ZONDER er iets van
    te tonen."""
    ploeg_id = opp.get("ploeg_id")
    state_key = f"{key_prefix}_report_v8_{ploeg_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = _load_report(ploeg_id)
    report = st.session_state[state_key]
    if _needs_rebuild(report, bundle, current_spelgroep_id):
        report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
        _save_report(report)
        st.session_state[state_key] = report
    return report
def _trigger_fresh_padelstat_for_team(bundle: dict) -> None:
    """PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19 (op verzoek
    van Kim: "ook als je op analyse ploeg drukt om zeker de laatste waarde
    te hebben wanneer je dat doet"): vraagt een GEFORCEERDE padelstat-
    verversing aan voor de volledige tegenploeg-roster, ONGEACHT bestaande
    cache. Op Cloud (gebruikelijke situatie) is dit een ASYNCHRONE GitHub
    Actions-trigger (workflow_dispatch, 1-3 minuten vertraging - een
    technische grens van GitHub Actions zelf); _underlying_data_is_fresher()
    zorgt dat het rapport zichzelf automatisch herbouwt zodra de verse
    waarde binnenkomt. Faalt dit stil (geen token geconfigureerd, workflow
    niet herkend, ...), dan wordt enkel een korte caption getoond - dit mag
    de rest van de 'Verversen'-actie nooit blokkeren."""
    players = bundle.get("unique_players", []) or []
    if not players:
        return
    if is_scraping_available():
        # Lokaal: laat de bestaande, uitgebreidere lokale ververs-flows
        # (opponent_scout_ui.py: "🔄 Ververs alles voor deze ploeg") dit
        # afhandelen - hier enkel een korte melding, geen dubbele scrape.
        st.caption("ℹ️ Lokaal: gebruik '🔄 Ververs alles voor deze ploeg' voor een volledige, synchrone verversing.")
        return
    player_ids_csv = ",".join(str(p["user_id"]) for p in players if p.get("user_id"))
    if not player_ids_csv:
        return
    ok, msg = trigger_github_actions_scrape(
        workflow_file=PADELSTAT_WORKFLOW_FILE,
        inputs={"player": player_ids_csv, "max": str(len(players)), "force_all": "true"},
    )
    if ok:
        st.caption(f"🎯 Padelstat-verversing gestart voor {len(players)} speler(s) (meestal 1-3 min).")
    else:
        st.caption(f"⚠️ Padelstat-verversing kon niet gestart worden: {msg}")
def render_team_header(
    report: dict,
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
    key_prefix: str = "team_analysis",
) -> dict:
    """Titel + 'Verversen'-knop. Geeft het (evt. na verversen NIEUWE) rapport
    terug.
    PADEL_ANALYSIS_PADELSTAT_WEEKLY_PLUS_ONDEMAND_2026-09-19: vraagt nu ook
    EXPLICIET een geforceerde padelstat-verversing aan (zie
    _trigger_fresh_padelstat_for_team()), vóór het rapport herbouwd wordt -
    zie module-docstring voor de volledige toelichting."""
    ploeg_id = opp.get("ploeg_id")
    state_key = f"{key_prefix}_report_v8_{ploeg_id}"
    header_col, refresh_col = st.columns([4, 1])
    with header_col:
        st.markdown(f"### 📋 Analyse: {opp.get('name', '?')}")
        st.caption(
            f"Poule {current_spelgroep_id or 'onbekend'} · "
            f"laatst berekend op {_format_ts(report.get('updated_at'))}"
        )
    with refresh_col:
        if st.button("🔄 Verversen", key=f"{key_prefix}_refresh_v8_{ploeg_id}", use_container_width=True):
            _trigger_fresh_padelstat_for_team(bundle)
            fcache.invalidate_all()
            report = _build_report(bundle, opp, all_docs, current_reeks_url, current_spelgroep_id, global_docs)
            _save_report(report)
            st.session_state[state_key] = report
            st.rerun()
    return report
# ─────────────────────────────────────────────
# Overzichtstabel (twee lagen naast elkaar + playing strength + klassement-link)
# ─────────────────────────────────────────────
def _overview_row(summary: dict) -> dict:
    current = summary.get("current_rank")
    best = summary.get("best_rank")
    best_text = f"P{best}" if best is not None else "?"
    best_when = summary.get("best_rank_when")
    if best_when and best is not None:
        best_text += f" ({best_when})"
    partners_now = summary.get("partners") or []
    partner_now = partners_now[0]["Partner"] if partners_now else "-"
    partners_hist = summary.get("partners_history") or []
    partner_hist = "-"
    if partners_hist:
        row = partners_hist[0]
        partner_hist = f"{row['Partner']} ({row['Matches']}x)"
    current_elo = summary.get("current_elo")
    if summary.get("elo_source") == "padelstat" and current_elo is not None:
        elo_text = f"P{current_elo}"
    else:
        elo_text = "-"
    return {
        "Naam": summary.get("name"),
        "Huidig": f"P{current}" if current is not None else "?",
        "Beste ooit": best_text,
        "Playing strength (padelstats.be)": elo_text,
        # PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19: ruwe URL hier - de
        # kolom zelf wordt in render_overview_and_detail() als klikbare
        # LinkColumn geconfigureerd (of, als fallback, gewoon als tekst-URL
        # getoond op een oudere Streamlit-versie).
        "Klassement": summary.get("klassement_url") or "",
        "Matchen deze poule": summary.get("matches_relevant", 0),
        "Winrate deze poule": summary.get("winrate_relevant", "-"),
        "Partner deze poule": partner_now,
        "Matchen historiek": summary.get("matches_history", 0),
        "Winrate historiek": summary.get("winrate_history", "-"),
        "Vaste partner historiek": partner_hist,
        "Vorm": summary.get("form_history", "-"),
    }
def _render_klassement_links_expander(players: list[dict]) -> None:
    """PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19 (op verzoek van Kim:
    "eventueel in aparte tab"): toont ELKE speler van de tegenploeg als een
    losse, klikbare link-knop naar de officiële TVL-klassementberekenings-
    pagina, verzameld in 1 overzichtelijke, ingeklapte sectie - een
    alternatief voor het los opzoeken van elke speler in "Detail per
    speler". Gebruikt st.link_button() (Streamlit >= 1.27) met een
    veilige markdown-fallback voor oudere versies."""
    with_link = [p for p in players if p.get("klassement_url")]
    if not with_link:
        return
    with st.expander(f"🔗 Alle klassement-links op TVL ({len(with_link)} van {len(players)} speler(s))", expanded=False):
        st.caption("Rechtstreekse links naar de officiële TVL-klassementberekeningspagina per speler.")
        cols = st.columns(3)
        for i, p in enumerate(with_link):
            with cols[i % 3]:
                label = f"🔗 {p.get('name', '?')}"
                url = p["klassement_url"]
                try:
                    st.link_button(label, url, use_container_width=True)
                except AttributeError:
                    st.markdown(f"[{label}]({url})")
def render_overview_and_detail(
    report: dict,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    key_prefix: str = "team_analysis",
) -> None:
    """Overzichtstabel + Detail-per-speler.
    PADEL_ANALYSIS_KLASSEMENT_LINK_2026-09-19: de Overzichtstabel toont nu
    ook een klikbare "🔗 Klassement"-kolom (LinkColumn), en eronder een
    inklapbare "🔗 Alle klassement-links op TVL"-sectie met alle spelers als
    losse link-knoppen (de "eventueel in aparte tab"-optie die Kim noemde -
    zie module-docstring voor waarom hier bewust voor een expander i.p.v.
    een letterlijke st.tabs()-herstructurering gekozen is)."""
    ploeg_id = report.get("opponent_ploeg_id")
    players = report.get("players", []) or []
    if not players:
        st.info("Nog geen spelersdata beschikbaar voor deze tegenploeg.")
        return
    st.markdown("#### 📊 Overzicht")
    overview_df = pd.DataFrame([_overview_row(p) for p in players])
    try:
        klassement_col_config = st.column_config.LinkColumn(
            "🔗 Klassement", display_text="Bekijk op TVL", help="Officiële TVL-klassementberekeningspagina",
        )
    except AttributeError:
        # Oudere Streamlit-versie zonder LinkColumn: gewone tekstkolom met
        # de ruwe URL - minder mooi, maar nooit een harde crash.
        klassement_col_config = None
    dataframe_kwargs = dict(
        use_container_width=True, hide_index=True,
        height=min(400, 40 + 36 * len(overview_df)),
    )
    if klassement_col_config is not None:
        dataframe_kwargs["column_config"] = {"Klassement": klassement_col_config}
    st.dataframe(overview_df, **dataframe_kwargs)
    _render_klassement_links_expander(players)
    missing_padelstat = sum(1 for p in players if p.get("elo_source") != "padelstat")
    if missing_padelstat:
        st.caption(
            f"🎯 'Playing strength' komt van padelstats.be. Voor {missing_padelstat} speler(s) hier nog "
            "niet opgehaald ('-' in de tabel) - dit wordt automatisch aangevuld door de wekelijkse "
            "achtergrondtaak, of forceer het meteen via '🔄 Verversen' hierboven."
        )
    played_now = sum(p.get("matches_relevant", 0) for p in players)
    total_history = sum(p.get("matches_history", 0) for p in players)
    if played_now == 0 and total_history:
        st.info(
            f"Deze ploeg heeft in de huidige poule nog geen gespeelde matchen in onze data. "
            f"De kolommen 'historiek' tonen {total_history} matchen uit vorige periodes - "
            "bruikbaar als niveau-inschatting, niet als stand in deze poule."
        )
    else:
        st.caption(
            "Kolommen 'deze poule' zijn strikt gefilterd op spelgroep-ID. "
            "Kolommen 'historiek' komen uit vorige periodes en andere poules."
        )
    st.markdown("#### 🔎 Detail per speler")
    names = [p.get("name", "?") for p in players]
    sel_name = st.selectbox("Bekijk details van:", names, key=f"{key_prefix}_detail_v8_{ploeg_id}")
    selected = next((p for p in players if p.get("name") == sel_name), None)
    if selected:
        od.render_player_summary_inline(selected)
# ─────────────────────────────────────────────
# Eigen-speler rating (gedeeld met dashboard.py's Opstelling-scenario's)
# ─────────────────────────────────────────────
def _get_own_profiles() -> list[dict]:
    try:
        return [d.to_dict() for d in fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).stream()]
    except Exception:
        return []
def get_own_player_rating(player_id: str) -> tuple[float, str]:
    """Geeft (sterkte, bron) terug voor één van ONZE spelers. Volgorde:
    1. padelstats.be, 2. officieel TVL-klassement, 3. neutrale default 200."""
    try:
        cached = fb.get_padelstat_rating(player_id)
    except Exception:
        cached = None
    if cached and cached.get("rating") is not None:
        return float(cached["rating"]), "padelstat"
    try:
        doc = fb.get_player(player_id) or {}
    except Exception:
        doc = {}
    try:
        profile_doc = fb.get_player_profile(player_id) or {}
    except Exception:
        profile_doc = {}
    ranking_doc = doc if doc.get("klassement_history") else profile_doc
    current_rank, _best, _when, _rows = od._history_summary(ranking_doc)
    if current_rank is not None:
        return float(current_rank), "official_klassement"
    return 200.0, "onbekend"
# ─────────────────────────────────────────────
# PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18
# AI-sectie: nu een ECHTE, doorlopende chat i.p.v. losse, contextloze vragen.
# ─────────────────────────────────────────────
def render_ai_section(report: dict, ploeg_id: str, key_prefix: str = "team_analysis") -> None:
    """PADEL_ANALYSIS_RENDER_SPLIT_2026-09-14: was _render_ai_section, nu
    PUBLIEK zodat dashboard.py dit apart en HOGER op de pagina kan tonen.
    PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18 (op verzoek van Kim: "zorg
    dat ik kan doorvragen"): houdt nu een chatgeschiedenis bij in
    st.session_state en stuurt die BIJ ELKE nieuwe vraag volledig mee naar
    team_ai_advisor.ask_followup(), zodat het taalmodel een samenhangend
    gesprek kan voeren i.p.v. elke vraag als geheel nieuw te behandelen.
    De volledige geschiedenis wordt ook zichtbaar getoond (st.chat_message),
    niet enkel het laatste antwoord."""
    st.markdown("#### 🤖 AI-inzichten over de tegenploeg")
    if taa is None:
        st.caption("AI-module niet beschikbaar (team_ai_advisor kon niet geladen worden).")
        return
    history_key = f"{key_prefix}_chat_history_v12_{ploeg_id}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []
    history: list = st.session_state[history_key]
    col_start, col_clear = st.columns([3, 1])
    with col_start:
        start_label = "💡 Genereer inzichten" if not history else "💡 Genereer inzichten (nieuw gesprek)"
        if st.button(start_label, key=f"{key_prefix}_insights_v12_{ploeg_id}", type="primary"):
            with st.spinner("AI analyseert de tegenploeg..."):
                try:
                    antwoord = taa.generate_insights(report)
                except Exception as exc:
                    antwoord = f"⚠️ Mislukt: {exc}"
            # PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18: dit automatische
            # inzicht wordt het EERSTE bericht van een verse geschiedenis,
            # zodat een vervolgvraag daarop kan voortbouwen.
            st.session_state[history_key] = [{"role": "assistant", "content": antwoord}]
            st.rerun()
    with col_clear:
        if history and st.button("🗑️ Nieuw gesprek", key=f"{key_prefix}_clear_chat_v12_{ploeg_id}"):
            st.session_state[history_key] = []
            st.rerun()
    # PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18: toon het VOLLEDIGE gesprek,
    # niet enkel het laatste antwoord - zo is meteen duidelijk waarop een
    # doorvraag verder bouwt.
    if history:
        st.caption("Gesprek tot nu toe:")
        for msg in history:
            role_label = "🙋 Jij" if msg["role"] == "user" else "🤖 AI"
            with st.container(border=True):
                st.markdown(f"**{role_label}**")
                st.markdown(msg["content"])
    st.caption("Stel een vraag of vraag door op het antwoord hierboven:")
    question = st.text_area(
        "Jouw vraag", key=f"{key_prefix}_question_v12_{ploeg_id}", height=70,
        label_visibility="collapsed",
        placeholder="Bv. Wie is hun sterkste dubbel? (of, na een eerder antwoord: 'en wat als die geblesseerd is?')",
    )
    if st.button("💬 Vraag AI", key=f"{key_prefix}_ask_v12_{ploeg_id}"):
        if not question.strip():
            st.warning("Typ eerst een vraag.")
        else:
            with st.spinner("AI denkt na..."):
                try:
                    antwoord = taa.ask_followup(question.strip(), report, history)
                except Exception as exc:
                    antwoord = f"⚠️ AI-vraag mislukt: {exc}"
            # PADEL_ANALYSIS_AI_FOLLOWUP_CHAT_2026-09-18: BEIDE berichten
            # (de vraag zelf, en het antwoord) worden toegevoegd aan de
            # geschiedenis, zodat de VOLGENDE doorvraag hier weer op kan
            # voortbouwen - anders zou de geschiedenis nooit groeien.
            st.session_state[history_key] = history + [
                {"role": "user", "content": question.strip()},
                {"role": "assistant", "content": antwoord},
            ]
            st.rerun()
# Alias voor achterwaartse compatibiliteit (was de interne naam vóór v9).
_render_ai_section = render_ai_section
# ─────────────────────────────────────────────
# Hoofdfunctie (dunne wrapper, oude volgorde - voor eventuele andere aanroepers)
# ─────────────────────────────────────────────
def render_team_analysis(
    bundle: dict,
    opp: dict,
    all_docs: dict,
    current_reeks_url: Optional[str] = None,
    current_spelgroep_id: Optional[str] = None,
    home_player_id: Optional[str] = None,
    global_docs: Optional[dict] = None,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    key_prefix: str = "team_analysis",
) -> dict:
    """Toont het volledige teamanalysescherm in de OUDE volgorde (header,
    overzicht+detail, AI) en geeft het gebruikte rapport terug."""
    report = get_team_report(
        bundle, opp, all_docs,
        current_reeks_url=current_reeks_url,
        current_spelgroep_id=current_spelgroep_id,
        global_docs=global_docs,
        key_prefix=key_prefix,
    )
    report = render_team_header(
        report, bundle, opp, all_docs,
        current_reeks_url=current_reeks_url,
        current_spelgroep_id=current_spelgroep_id,
        global_docs=global_docs,
        key_prefix=key_prefix,
    )
    render_overview_and_detail(report, go_to_player_fn=go_to_player_fn, key_prefix=key_prefix)
    st.divider()
    render_ai_section(report, opp.get("ploeg_id"), key_prefix=key_prefix)
    return report
