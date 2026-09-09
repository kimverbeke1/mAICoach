"""
opponent_scout_ui.py - UI-blok voor de tegenstander-analyse bij 'Volgende match'.

Doel van dit bestand (2026-09-09):
- De tussenstap verdwijnt. Na een klik op 'Tegenstander analyseren' wordt de
  opstelling van de tegenstander opgezocht EN worden de nog onbekende spelers
  meteen gescrapet, in een doorlopende voortgangsweergave (st.status).
- Op Streamlit Community Cloud kan de app zelf niet scrapen (geen Playwright/
  browser). Daar wordt de bestaande GitHub Actions-trigger getoond in plaats van
  een lokale scrape. Dat verklaart ook waarom de scrape-knop lokaal wel en op de
  cloud niet zichtbaar was.

Bedoeld om aangeroepen te worden vanuit dashboard.py, binnen
_resolve_and_render_next:

    import opponent_scout_ui as osu
    ...
    return osu.render_scout_block(
        sel_player_id=str(sel_player_id),
        fixtures=fixtures,
        own_ploeg_id=own_ploeg_id,
        reeks_url=reeks_url,
        go_to_player_fn=_go_to_player,
    )

Retourneert (bundle, opp) of None, exact zoals de vorige inline-implementatie,
zodat _render_opstelling_scenario ongewijzigd blijft werken.
"""
from __future__ import annotations

from typing import Callable, Optional

import streamlit as st

import firebase_service as fb
import lineup_lab as ll
import opponent_dossier as od
import opponent_scout as osc
import schedule_scraper as ss

try:  # cloud_helpers is optioneel aanwezig; nooit hard falen op import
    from cloud_helpers import is_scraping_available, render_cloud_scrape_trigger
except Exception:  # pragma: no cover
    def is_scraping_available() -> bool:
        return False

    def render_cloud_scrape_trigger(**_kwargs) -> None:
        st.caption("Cloud-trigger niet beschikbaar (cloud_helpers ontbreekt).")


def _is_known(player_id: str) -> bool:
    """Een speler geldt als gekend zodra er matchdata OF een profiel bestaat.

    PADEL_ANALYSIS_KNOWN_PLAYER_FIX_2026-09-09: enkel op get_player_profile()
    controleren was te streng. scrape_new_opponent_players() schrijft eerst de
    matchdata naar de 'players'-collectie en pas daarna het profiel; wordt die
    tweede stap onderbroken, dan bleef de speler eeuwig als 'nog niet gescrapet'
    staan en werd hij bij elke analyse opnieuw gescrapet.
    """
    try:
        if fb.get_player_profile(player_id):
            return True
    except Exception:
        pass
    try:
        doc = fb.get_player(player_id) or {}
        return bool(doc.get("matches"))
    except Exception:
        return False


def _unknown_players(bundle: dict) -> list[dict]:
    return [
        player
        for player in (bundle.get("unique_players", []) or [])
        if not _is_known(player["user_id"])
    ]


def _run_scout_and_scrape(
    fixtures: list[dict],
    opp: dict,
    next_match: dict,
    lookback: int,
    auto_scrape: bool,
) -> dict:
    """Zoekt de opstelling op en scrapet meteen de onbekende spelers."""
    with st.status("Tegenstander analyseren...", expanded=True) as status:
        st.write("Vorige wedstrijd(en) van de tegenstander opzoeken...")
        bundle = osc.scout_opponent(
            fixtures,
            opp["name"],
            opp["ploeg_id"],
            next_match["date_text"],
            lookback=lookback,
        )

        if bundle.get("note"):
            st.write(bundle["note"])
            status.update(label="Analyse afgerond (beperkte data)", state="complete")
            return bundle

        found = len(bundle.get("unique_players", []) or [])
        st.write(f"{found} tegenstander-speler(s) gevonden.")

        unknown = _unknown_players(bundle)
        if not unknown:
            st.write("Alle spelers zijn al gekend. Geen scrape nodig.")
            status.update(label="Analyse afgerond", state="complete")
            return bundle

        if not auto_scrape:
            st.write(
                f"{len(unknown)} speler(s) nog niet gescrapet. Scrapen gebeurt hier "
                "niet: deze omgeving heeft geen browser."
            )
            status.update(label="Analyse afgerond (scrape via GitHub Actions)", state="complete")
            return bundle

        st.write(f"{len(unknown)} nieuwe speler(s) scrapen...")
        progress = st.progress(0.0, text="Starten...")

        def _callback(index: int, total: int, name: str) -> None:
            fraction = index / total if total else 0.0
            progress.progress(fraction, text=f"({index}/{total}) {name} scrapen...")

        try:
            result = osc.scrape_new_opponent_players(
                unknown,
                lookback_periods=1,
                delay=1.5,
                progress_callback=_callback,
            )
        except Exception as exc:
            progress.empty()
            st.write(f"Scrapen mislukt: {exc}")
            status.update(label="Analyse afgerond, scrape mislukt", state="error")
            return bundle

        progress.progress(1.0, text="Klaar.")
        scraped = len(result.get("newly_scraped", []) or [])
        failed = result.get("failed", []) or []
        st.write(f"{scraped} gescrapet, {len(failed)} mislukt.")
        for item in failed:
            st.write(f"Mislukt: {item.get('name')} - {item.get('error')}")

        status.update(label="Analyse en scrape afgerond", state="complete")
        return bundle


def render_scout_block(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    reeks_url: Optional[str] = None,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    lookback: int = 1,
):
    """Toont de volgende match en de tegenstander-analyse in één stap."""
    team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id)
    next_match = ss.get_next_match(team_fixtures)
    if not next_match:
        st.success("Geen nog te spelen wedstrijden gevonden voor dit schema.")
        return None

    opp = ss.opponent_of(next_match, own_ploeg_id)
    st.markdown(
        f"**{next_match['date_text']}** - tegen **{opp['name']}** "
        f"({next_match.get('poule_label', '')})"
    )

    scout_key = f"scout_{opp['ploeg_id']}_{next_match['date_text']}"
    can_scrape = is_scraping_available()

    if not can_scrape:
        st.caption(
            "Deze omgeving kan zelf niet scrapen. Nieuwe spelers worden opgehaald "
            "via de achtergrondtaak op GitHub Actions."
        )

    if st.button("🔍 Tegenstander analyseren", key=f"btn_scout_{sel_player_id}", type="primary"):
        st.session_state[scout_key] = _run_scout_and_scrape(
            fixtures, opp, next_match, lookback, auto_scrape=can_scrape
        )

    bundle = st.session_state.get(scout_key)
    if not bundle:
        return None

    if bundle.get("note"):
        st.info(bundle["note"])
        st.caption(
            "Zonder historische tegenstander-data kan enkel de eigen ploeg-sterkte "
            "getoond worden, niet die van hen."
        )

    unique_players = bundle.get("unique_players", []) or []
    if not unique_players:
        return bundle, opp

    unknown_ids = {player["user_id"] for player in _unknown_players(bundle)}

    with st.expander(f"👥 Gevonden tegenstander-spelers ({len(unique_players)})", expanded=True):
        all_docs = ll.get_docs_for_players([p["user_id"] for p in unique_players])
        for player in unique_players:
            is_unknown = player["user_id"] in unknown_ids
            status_text = "❓ nog niet gescrapet" if is_unknown else "✅ gekend"
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"• {player['name']} - {status_text}")
            if not is_unknown:
                if c2.button("👁️ Bekijk", key=f"jump_opp_{sel_player_id}_{player['user_id']}"):
                    if go_to_player_fn:
                        go_to_player_fn(player["user_id"])
                with c3:
                    od.render_opponent_dossier_button(
                        player["user_id"],
                        player["name"],
                        all_docs,
                        current_reeks_url=reeks_url,
                        key_prefix="scout_dossier",
                    )

        if unknown_ids and not can_scrape:
            st.caption(
                f"{len(unknown_ids)} speler(s) konden hier niet gescrapet worden. "
                "Start de achtergrondtaak om ze toe te voegen."
            )
            render_cloud_scrape_trigger(
                key_prefix=f"scout_scrape_{sel_player_id}",
                player_ids=",".join(sorted(unknown_ids)),
                mode="missing",
                label="🚀 Nieuwe tegenstanders ophalen",
            )

    return bundle, opp
