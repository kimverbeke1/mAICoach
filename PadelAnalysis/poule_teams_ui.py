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
    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}")
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    if not fixtures or not own_ploeg_id:
        st.info(
            "Laad eerst je poule-schema via '📅 Volgende match laden' in het tabblad '🔍 Analyseren' "
            "— dat schema wordt hier hergebruikt, zonder opnieuw te moeten ophalen."
        )
        return
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
    # — geen dubbele detectie-/trigger-logica.
    if not osu.is_scraping_available():
        osu.render_unified_team_sync_trigger(unique_players, key_prefix=key_prefix)

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
