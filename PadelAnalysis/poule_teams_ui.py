"""
poule_teams_ui.py — "🌐 Andere ploegen"-tabblad in Opstelling-analyse.
PADEL_ANALYSIS_POULE_TEAMS_TAB_2026-09-19 (Fase D1, op verzoek van Kim, chat
2026-09-19: "Het zou ook handig zijn dat er een mogelijkheid is om al meteen
ook andere ploegen van je poule al eens te bekijken. eventueel via apart
tabblad.")
Doel: het volledige team-analysescherm (overzichtstabel, detail-per-speler,
AI-inzichten, "ontbrekende gegevens ophalen") dat vandaag enkel voor de
EERSTVOLGENDE tegenstander getoond wordt, ook beschikbaar maken voor OM HET
EVEN WELKE andere ploeg in dezelfde poule — zonder de bestaande logica te
dupliceren.
ONTWERPKEUZE: dit hergebruikt bewust de reeds bestaande, generieke bouwstenen
in plaats van een parallel scoutingpad te bouwen:
  - schedule_scraper.py se `fixtures` (al geparsed, al gecached via
    page_lineup_lab.py's "Volgende match") geeft de volledige poule-tabel,
    dus ALLE ploegen incl. hun ploeg_id, zonder extra scrape.
  - opponent_scout.scout_opponent() is al generiek genoeg: het bouwt een
    scouting-bundel voor OM HET EVEN WELKE opponent_ploeg_id — vandaag wordt
    dit enkel aangeroepen voor de eerstvolgende tegenstander
    (opponent_scout_ui._run_scout_and_scrape()), maar niets in de functie
    zelf is daartoe beperkt.
  - opponent_analysis.py se get_team_report()/render_team_header()/
    render_overview_and_detail()/render_ai_section() zijn al bundle-generiek
    (ze weten niets over "eerstvolgende tegenstander" specifiek).
  - opponent_scout_ui.render_unified_team_sync_trigger() (Fase C-alias voor
    _render_unified_team_sync_trigger) regelt de "ontbrekende gegevens
    ophalen"-knop al generiek per speler-roster.
Voor élke van deze bouwstenen is enkel een ANDERE `opp`-dict (ploeg_id/naam)
en een apart `key_prefix` nodig — geen enkele hoeft aangepast te worden.
AFHANKELIJKHEID VAN "Volgende match": om de volledige poule-tabel (fixtures)
en de eigen-ploeg-identificatie te kennen, moet de gebruiker eerst minstens
1x "📅 Volgende match laden" gebruikt hebben in het tabblad "🔍 Analyseren" —
page_lineup_lab.py bewaart die fixtures/own_ploeg_id sindsdien in
st.session_state (zie PADEL_ANALYSIS_POULE_TEAMS_TAB_2026-09-19 in dat
bestand). Is dat nog niet gebeurd, dan toont dit tabblad een duidelijke
verwijzing i.p.v. zelf een parallelle, dubbele scrape-flow op te zetten.
LOOKBACK: in tegenstelling tot de eerstvolgende tegenstander (waar 1-2
recente wedstrijden meestal volstaan) wil je van een WILLEKEURIGE poule-
ploeg typisch hun VOLLEDIGE seizoenshistoriek zien — er is immers geen
"eerstvolgende match"-datum die de blik natuurlijk beperkt. _team_lookback()
berekent daarom automatisch "alle tot nu toe gespeelde wedstrijden van deze
ploeg" i.p.v. een vast klein getal.
--------------------------------------------------------------------------
PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19 (op verzoek van Kim,
chat 2026-09-19: "je weet toch welke ploeg je scrapet dus deze melding is
eigenlijk niet nodig als je meteen de juiste club meegeeft")
--------------------------------------------------------------------------
render_unified_team_sync_trigger() krijgt hier nu team_name=chosen["name"]
mee — exact dezelfde club-disambiguatie-hint als in opponent_scout_ui.py se
render_scout_header(), zodat een padelstat-verversing voor een willekeurige
poule-ploeg (net als voor de eerstvolgende tegenstander) NOOIT meer de "geen
club opgegeven om te disambigueren"-waarschuwing hoeft te geven voor spelers
zonder eigen club-veld — de ploegnaam is hier immers altijd al gekend
(`chosen["name"]`), dus geen enkele reden om dat niet door te geven.
--------------------------------------------------------------------------
PADEL_ANALYSIS_STALE_SCHEDULE_POULE_TEAM_FIX_2026-09-21 (op verzoek van Kim,
chat 2026-09-21: "ik heb nu de ploeg KTC ISIS eens willen analyseren bij de
andere ploegen en was dat ooit al eens begonnen [...] er staat dan ook dat
deze ploeg nog geen matchen gespeeld heeft maar dat is niet waar. ondertussen
is die situatie al veranderd")
--------------------------------------------------------------------------
ROOT CAUSE: `fixtures` kwam hier UITSLUITEND uit st.session_state (
`vm_fixtures_{sel_player_id}`), een EENMALIGE snapshot die enkel gezet wordt
op het moment dat de gebruiker "📅 Volgende match laden" gebruikte in het
tabblad "🔍 Analyseren" (zie page_lineup_lab.py, `_finish()`). Die snapshot
wordt NOOIT automatisch ververst binnen deze sessie — ook niet door
opnieuw op "{team} analyseren" te klikken hieronder, want dat hergebruikte
gewoon dezelfde, mogelijk verouderde `fixtures`-variabele. Voor een ploeg
zoals KTC ISIS, die INTUSSEN al matchen speelde nadat het schema voor het
laatst geladen werd, bleef `scout_opponent()` daardoor keer op keer "geen
eerdere, al gespeelde wedstrijden gevonden" rapporteren — ook de freshness-
check (team_freshness.team_freshness_status()) kon dit niet detecteren,
want die vergelijkt enkel BINNEN diezelfde (stale) fixtures-lijst.
FIX, drie onderdelen:
  1. Vóór alles wordt de ACTUEEL PERSISTEERDE schedule opnieuw opgehaald via
     dashboard_common._get_saved_schedule() (dezelfde bron die de dagelijkse
     achtergrondtaak / een schema-verversing bijwerkt) — die wordt, indien
     beschikbaar, ALTIJD verkozen boven de eenmalige sessie-snapshot. Zo
     ziet dit tabblad automatisch de meest recente schema-stand, zonder dat
     de gebruiker terug naar "Volgende match laden" moet.
  2. Een nieuwe, expliciete "🔄 Schema nu verversen"-sectie (hergebruikt
     cloud_helpers.render_cloud_scrape_trigger(), net als in
     page_lineup_lab.py's `_render_schema_refresh_button()`) laat toe het
     schema DIRECT vanuit dit tabblad te forceren, zonder tabblad te
     wisselen.
  3. Toont de gebruiker, wanneer een bundle nog "geen matchen gespeeld"
     meldt TERWIJL het (nu verse) schema wél gespeelde wedstrijden toont
     voor deze ploeg, een EXPLICIETE melding dat de analyse verouderd is en
     een herhaalde klik op "analyseren" nodig heeft — i.p.v. de oude,
     mogelijk misleidende melding stilzwijgend te laten staan.
"""
from __future__ import annotations

from typing import Callable, Optional

import streamlit as st

import lineup_lab as ll
import opponent_analysis as oa
import opponent_scout as osc
import opponent_scout_ui as osu
import schedule_scraper as ss
import team_freshness as tf
from dashboard_common import _get_saved_schedule, _format_scraped_at, render_cloud_scrape_trigger


def _extract_poule_teams(fixtures: list[dict], own_ploeg_id: Optional[str]) -> list[dict]:
    """Geeft alle UNIEKE ploegen terug die in `fixtures` voorkomen (zowel
    thuis als uit), MET hun poule_label, gesorteerd op naam — de eigen ploeg
    wordt uitgesloten (die heeft al zijn eigen "Analyseren"-tabblad)."""
    teams: dict[str, dict] = {}
    for fx in fixtures or []:
        for side in ("home", "away"):
            ploeg_id = fx.get(f"{side}_ploeg_id")
            name = fx.get(f"{side}_name")
            if not ploeg_id or not name:
                continue
            ploeg_id = str(ploeg_id)
            if own_ploeg_id and ploeg_id == str(own_ploeg_id):
                continue
            if ploeg_id not in teams:
                teams[ploeg_id] = {
                    "ploeg_id": ploeg_id,
                    "name": name,
                    "poule_label": fx.get("poule_label") or "?",
                }
    return sorted(teams.values(), key=lambda t: (t["poule_label"], t["name"]))


def _team_lookback(fixtures: list[dict], ploeg_id: str) -> int:
    """PADEL_ANALYSIS_POULE_TEAMS_TAB_2026-09-19: geeft het aantal reeds
    GESPEELDE wedstrijden van deze ploeg terug — gebruikt als lookback voor
    scout_opponent(), zodat we hun VOLLEDIGE tot-nu-toe-gekende
    seizoenshistoriek meenemen (i.p.v. het vaste "1" dat voor de
    eerstvolgende tegenstander wordt gebruikt). Minstens 1, zodat
    scout_opponent() nooit met 0 aangeroepen wordt."""
    team_fixtures = ss.get_team_fixtures(fixtures, ploeg_id)
    played = sum(1 for fx in team_fixtures if fx.get("played"))
    return max(played, 1)


def _freshest_fixtures(sel_player_id: str, session_fixtures: list[dict]) -> tuple[list[dict], Optional[str]]:
    """PADEL_ANALYSIS_STALE_SCHEDULE_POULE_TEAM_FIX_2026-09-21: geeft de
    meest ACTUEEL PERSISTEERDE schedule terug (via
    dashboard_common._get_saved_schedule(), dezelfde bron die de dagelijkse
    achtergrondtaak/schema-verversing bijwerkt), MET terugval op de
    eenmalige sessie-snapshot (`session_fixtures`) als er nog geen
    persisteerde schedule beschikbaar is. Geeft (fixtures, laatst_ververst_op)
    terug — het 2de element is None als er geen persisteerde timestamp
    gekend is (dan tonen we ook geen "laatst bijgewerkt op"-caption)."""
    try:
        saved_fixtures, sched_at = _get_saved_schedule(sel_player_id)
    except Exception:
        saved_fixtures, sched_at = None, None
    if saved_fixtures:
        return saved_fixtures, sched_at
    return session_fixtures, None


def render_poule_teams_tab(
    sel_player_id: str,
    name_lookup_global: dict,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
) -> None:
    """Rendert het volledige "🌐 Andere ploegen"-tabblad."""
    st.markdown('<div class="section-header">🌐 Andere ploegen in je poule</div>', unsafe_allow_html=True)
    # PADEL_ANALYSIS_TEAM_FRESHNESS_CHECK_2026-09-19 (Fase D3): toont, indien
    # bekend, wanneer de nachtelijke achtergrond-poule-scan (Fase D2) voor
    # het laatst liep — puur informatief, geen actie.
    tf.render_last_prescan_caption()
    session_fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}")
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    if not session_fixtures or not own_ploeg_id:
        st.info(
            "Laad eerst je poule-schema via '📅 Volgende match laden' in het tabblad '🔍 Analyseren' "
            "— dat schema wordt hier hergebruikt, zonder opnieuw te moeten ophalen."
        )
        return
    # PADEL_ANALYSIS_STALE_SCHEDULE_POULE_TEAM_FIX_2026-09-21: gebruik de
    # meest actuele, PERSISTEERDE schedule i.p.v. blind te vertrouwen op de
    # eenmalige sessie-snapshot hierboven — zie module-docstring voor de
    # volledige toelichting (KTC ISIS-melding van Kim).
    fixtures, sched_at = _freshest_fixtures(sel_player_id, session_fixtures)
    if sched_at:
        st.caption(f"ℹ️ Poule-schema laatst automatisch bijgewerkt op {_format_scraped_at(sched_at)}.")
    with st.expander("🔄 Schema nu verversen", expanded=False):
        st.caption(
            "Ververst het wedstrijdschema van de volledige poule op de achtergrond. Gebruik dit als "
            "een ploeg hieronder een verouderde status toont (bv. 'nog geen matchen gespeeld' terwijl "
            "ze intussen wel al speelde(n))."
        )
        render_cloud_scrape_trigger(
            key_prefix=f"poule_schema_{sel_player_id}", player_ids=str(sel_player_id),
            mode="missing", label="🔄 Schema nu verversen",
        )
    teams = _extract_poule_teams(fixtures, own_ploeg_id)
    if not teams:
        st.info("Geen andere ploegen gevonden in dit poule-schema.")
        return
    st.caption(
        f"{len(teams)} andere ploeg(en) gevonden in je poule. Kies een ploeg om dezelfde analyse te "
        "zien als bij 'Volgende match' — overzicht, detail per speler, AI-inzichten."
    )
    team_labels = [f"{t['name']} ({t['poule_label']})" for t in teams]
    chosen_label = st.selectbox("Kies een ploeg:", team_labels, key=f"poule_team_pick_{sel_player_id}")
    chosen = teams[team_labels.index(chosen_label)]
    ploeg_id = chosen["ploeg_id"]
    key_prefix = f"poule_team_{ploeg_id}"
    # PADEL_ANALYSIS_POULE_TEAMS_TAB_2026-09-19: scout_opponent() is al
    # generiek — hergebruikt hier ONGEWIJZIGD, enkel met een ANDERE
    # ploeg_id/naam en een hogere lookback (volledige seizoenshistoriek
    # i.p.v. de "1" die voor de eerstvolgende tegenstander gebruikt wordt).
    bundle_key = f"poule_team_bundle_{ploeg_id}"
    # PADEL_ANALYSIS_TEAM_FRESHNESS_CHECK_2026-09-19 (Fase D3): bewaart HOEVEEL
    # gespeelde wedstrijden er waren op het moment van scouten — dit is het
    # ijkpunt waartegen we later (bij elke render) vergelijken of de ploeg
    # intussen NIEUWE wedstrijden speelde (zie team_freshness.py).
    known_played_key = f"poule_team_known_played_{ploeg_id}"
    lookback = _team_lookback(fixtures, ploeg_id)
    if st.button(f"🔍 {chosen['name']} analyseren", key=f"poule_team_analyze_{ploeg_id}", type="primary"):
        with st.spinner(f"Wedstrijden en opstelling van {chosen['name']} opzoeken..."):
            st.session_state[bundle_key] = osc.scout_opponent(
                fixtures, chosen["name"], ploeg_id, before_date_text="", lookback=lookback,
            )
            st.session_state[known_played_key] = lookback
    bundle = st.session_state.get(bundle_key)
    if not bundle:
        st.info(f"⬆️ Klik op '🔍 {chosen['name']} analyseren' om hun gegevens te bekijken.")
        return
    if bundle.get("note"):
        # PADEL_ANALYSIS_STALE_SCHEDULE_POULE_TEAM_FIX_2026-09-21: vóór we de
        # (mogelijk verouderde) "note" gewoon tonen, controleren we of het
        # NU verse schema deze ploeg toch al gespeelde wedstrijden toont —
        # zo ja, dan is de note zelf verouderd (gebaseerd op een eerdere,
        # inmiddels achterhaalde schedule-snapshot) en tonen we een
        # EXPLICIETE melding i.p.v. de gebruiker te laten geloven dat de
        # ploeg écht nog niets speelde.
        played_now = tf.team_played_count(fixtures, ploeg_id)
        if played_now > 0:
            st.warning(
                f"⚠️ Deze analyse toont nog: \"{bundle['note']}\" — maar het (zonet ververste) poule-schema "
                f"laat intussen {played_now} gespeelde wedstrijd(en) zien voor {chosen['name']}. Deze "
                f"analyse is dus verouderd. Klik hierboven opnieuw op '🔍 {chosen['name']} analyseren' "
                "om ze bij te werken."
            )
        else:
            st.info(bundle["note"])
        return
    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        st.info("Geen spelers gevonden voor deze ploeg.")
        return
    # PADEL_ANALYSIS_TEAM_FRESHNESS_CHECK_2026-09-19 (Fase D3, op verzoek van
    # Kim: "Freshness-check bij elke analyse i.p.v. enkel manueel verversen —
    # gebaseerd op aantal matchen + tijdstip laatste padelstat-check."):
    # controleert bij ELKE render (dus ook zonder een nieuwe klik) of (a) de
    # ploeg intussen meer wedstrijden speelde dan waarop deze analyse
    # gebaseerd is, en (b) de playing strength van 1 of meer spelers
    # verouderd is. Toont enkel een banner — de effectieve actie loopt via
    # de bestaande '🔄 Ontbrekende gegevens ophalen'-knop hieronder.
    # PADEL_ANALYSIS_STALE_SCHEDULE_POULE_TEAM_FIX_2026-09-21: gebruikt nu de
    # verse `fixtures` (zie hierboven), dus deze check kan NU ook effectief
    # nieuwe matchen detecteren die pas na de laatste sessie-snapshot bekend
    # raakten.
    freshness = tf.team_freshness_status(
        unique_players, fixtures=fixtures, ploeg_id=ploeg_id,
        known_played_count=st.session_state.get(known_played_key),
    )
    tf.render_freshness_banner(freshness, key_prefix=key_prefix)
    if freshness.get("new_matches_detected"):
        st.caption(
            f"↳ Klik opnieuw op '🔍 {chosen['name']} analyseren' hierboven om de nieuwe "
            "wedstrijd(en) en eventuele nieuwe spelers mee te nemen."
        )
    opp = {"name": chosen["name"], "ploeg_id": ploeg_id}
    # PADEL_ANALYSIS_POULE_TEAMS_TAB_2026-09-19: dezelfde "ontbrekende
    # gegevens ophalen"-knop als bij de eerstvolgende tegenstander (Fase C),
    # rechtstreeks hergebruikt via de publieke alias in opponent_scout_ui.py
    # — geen dubbele detectie-/trigger-logica. Sinds
    # PADEL_ANALYSIS_TEAM_SYNC_FULL_FORCE_OPTION_2026-09-21 (zie
    # opponent_scout_ui.py) toont deze knop ook een optionele "forceer voor
    # alle spelers"-checkbox, hier dus automatisch mee-hergebruikt.
    # PADEL_ANALYSIS_CLUB_HINT_FOR_TEAM_TRIGGERS_2026-09-19: geeft nu
    # team_name=chosen["name"] mee, zodat een padelstat-verversing voor deze
    # willekeurige poule-ploeg dezelfde club-disambiguatie-hint krijgt als
    # bij de eerstvolgende tegenstander (zie opponent_scout_ui.py).
    if not osu.is_scraping_available():
        osu.render_unified_team_sync_trigger(unique_players, key_prefix=key_prefix, team_name=chosen["name"])
    all_docs = ll.get_docs_for_players([p["user_id"] for p in unique_players])
    global_docs = osu.load_all_player_docs()
    report = oa.get_team_report(
        bundle, opp, all_docs,
        current_reeks_url=None, current_spelgroep_id=None,
        global_docs=global_docs, key_prefix=key_prefix,
    )
    report = oa.render_team_header(
        report, bundle, opp, all_docs,
        current_reeks_url=None, current_spelgroep_id=None,
        global_docs=global_docs, key_prefix=key_prefix,
    )
    oa.render_overview_and_detail(report, go_to_player_fn=go_to_player_fn, key_prefix=key_prefix)
    st.divider()
    oa.render_ai_section(report, ploeg_id, key_prefix=key_prefix)
