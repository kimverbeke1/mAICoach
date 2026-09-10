"""
opponent_scout_ui.py - UI-blok voor de tegenstander-analyse bij 'Volgende match'.

Doel van dit bestand:
- 2026-09-09 (v1): de tussenstap verdwijnt. Na een klik op 'Tegenstander
  analyseren' wordt de opstelling van de tegenstander opgezocht EN worden de
  nog onbekende spelers meteen gescrapet, in een doorlopende
  voortgangsweergave (st.status).
- 2026-09-09 (v2): het volledige teamanalysescherm zit nu in
  opponent_analysis.render_team_analysis() (overzichtstabel, opstelling-editor,
  AI-sectie). Dit bestand geeft er nu ook spelgroep_id (voor precieze
  poule-filtering), home_player_id (voor de opstelling-editor) en een brede
  cache van alle gekende spelersdocumenten (voor een betere ranking-fallback)
  aan door. Daarnaast: optionele automatische klassementshistoriek-scrape
  (lokaal, per speler ~30-60s) zodat 'ranking onbekend' niet blijft hangen.

Op Streamlit Community Cloud kan de app zelf niet scrapen (geen Playwright/
browser). Daar wordt de bestaande GitHub Actions-trigger getoond in plaats van
een lokale scrape.

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

from datetime import datetime, timezone
from typing import Callable, Optional

import streamlit as st

import firebase_service as fb
import lineup_lab as ll
import opponent_analysis as oa
import opponent_scout as osc
import schedule_scraper as ss

try:  # cloud_helpers is optioneel aanwezig; nooit hard falen op import
    from cloud_helpers import is_scraping_available, render_cloud_scrape_trigger
except Exception:  # pragma: no cover
    def is_scraping_available() -> bool:
        return False

    def render_cloud_scrape_trigger(**_kwargs) -> None:
        st.caption("Cloud-trigger niet beschikbaar (cloud_helpers ontbreekt).")


@st.cache_data(ttl=300, show_spinner=False)
def _load_all_player_docs() -> dict:
    """Bredere set van ALLE gekende spelersdocumenten (niet enkel de
    tegenstander-roster), gebruikt als 'global_docs' voor de opportunistische
    ranking-fallback in opponent_dossier. Klein en goedkoop bij het huidige
    aantal spelers; 5 minuten gecached om herhaalde Firestore-reads binnen
    dezelfde sessie te vermijden."""
    try:
        docs = fb.db.collection(fb.PLAYERS_COLLECTION).stream()
        return {d.id: (d.to_dict() or {}) for d in docs}
    except Exception:
        return {}


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


def _ensure_klassement(player_ids: list[str], progress_label: str = "Klassement") -> None:
    """Haalt de klassementshistoriek op voor spelers die deze nog niet hebben.

    Enkel lokaal (Playwright vereist, zie is_scraping_available()). Duurt
    ongeveer 30-60s per speler; slaat spelers over die al klassement_history
    hebben, dus een herhaald bezoek kost niets voor reeds gekende spelers."""
    if not is_scraping_available():
        return

    to_fetch = []
    for pid in player_ids:
        try:
            prof = fb.get_player_profile(pid) or {}
        except Exception:
            prof = {}
        try:
            doc = fb.get_player(pid) or {}
        except Exception:
            doc = {}
        if not (doc.get("klassement_history") or prof.get("klassement_history")):
            to_fetch.append(pid)

    if not to_fetch:
        return

    try:
        from scrape_klassement import scrape_klassement, klassement_to_history_summary, extract_niveau_winrates
    except Exception as exc:
        st.caption(f"Klassement automatisch ophalen niet beschikbaar: {exc}")
        return

    progress = st.progress(0.0, text=f"{progress_label}: starten...")
    for i, pid in enumerate(to_fetch, start=1):
        progress.progress(i / len(to_fetch), text=f"{progress_label}: speler {i}/{len(to_fetch)}...")
        try:
            periods = scrape_klassement(str(pid))
            history = klassement_to_history_summary(periods)
            niveau_winrates = extract_niveau_winrates(periods)
            klass_data = {
                "history": history,
                "niveau_winrates": niveau_winrates,
                "raw_periods": periods,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            payload = {"klassement_history": fb.sanitize_for_firestore(klass_data)}
            fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(pid)).set(payload, merge=True)
            fb.db.collection(fb.PLAYERS_COLLECTION).document(str(pid)).set(payload, merge=True)
        except Exception as exc:
            st.write(f"Klassement ophalen mislukt voor speler {pid}: {exc}")
    progress.progress(1.0, text=f"{progress_label}: klaar.")
    _load_all_player_docs.clear()


def _run_scout_and_scrape(
    fixtures: list[dict],
    opp: dict,
    next_match: dict,
    lookback: int,
    auto_scrape: bool,
    fetch_klassement: bool,
) -> dict:
    """Zoekt de opstelling op, scrapet meteen de onbekende spelers en haalt
    optioneel ook de klassementshistoriek op."""
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
        if unknown:
            if not auto_scrape:
                st.write(
                    f"{len(unknown)} speler(s) nog niet gescrapet. Scrapen gebeurt hier "
                    "niet: deze omgeving heeft geen browser."
                )
            else:
                st.write(f"{len(unknown)} nieuwe speler(s) scrapen...")
                progress = st.progress(0.0, text="Starten...")

                def _callback(index: int, total: int, name: str) -> None:
                    fraction = index / total if total else 0.0
                    progress.progress(fraction, text=f"({index}/{total}) {name} scrapen...")

                try:
                    result = osc.scrape_new_opponent_players(
                        unknown, lookback_periods=1, delay=1.5, progress_callback=_callback,
                    )
                    progress.progress(1.0, text="Klaar.")
                    scraped = len(result.get("newly_scraped", []) or [])
                    failed = result.get("failed", []) or []
                    st.write(f"{scraped} gescrapet, {len(failed)} mislukt.")
                    for item in failed:
                        st.write(f"Mislukt: {item.get('name')} - {item.get('error')}")
                except Exception as exc:
                    progress.empty()
                    st.write(f"Scrapen mislukt: {exc}")
        else:
            st.write("Alle spelers zijn al gekend qua matchdata.")

        if fetch_klassement:
            st.write("Klassementshistoriek controleren/ophalen...")
            all_ids = [p["user_id"] for p in bundle.get("unique_players", []) or []]
            _ensure_klassement(all_ids, progress_label="Klassement")

        status.update(label="Analyse afgerond", state="complete")
        return bundle


def render_scout_block(
    sel_player_id: str,
    fixtures: list[dict],
    own_ploeg_id: str,
    reeks_url: Optional[str] = None,
    go_to_player_fn: Optional[Callable[[str], None]] = None,
    lookback: int = 1,
):
    """Toont de volgende match en het volledige tegenploeg-analysescherm."""
    team_fixtures = ss.get_team_fixtures(fixtures, own_ploeg_id)
    next_match = ss.get_next_match(team_fixtures)
    if not next_match:
        st.success("Geen nog te spelen wedstrijden gevonden voor dit schema.")
        return None

    opp = ss.opponent_of(next_match, own_ploeg_id)
    spelgroep_id = next_match.get("spelgroep_id")
    st.markdown(
        f"**{next_match['date_text']}** - tegen **{opp['name']}** "
        f"({next_match.get('poule_label', '')})"
    )

    scout_key = f"scout_{opp['ploeg_id']}_{next_match['date_text']}"
    can_scrape = is_scraping_available()

    fetch_klassement = False
    if not can_scrape:
        st.caption(
            "Deze omgeving kan zelf niet scrapen. Nieuwe spelers worden opgehaald "
            "via de achtergrondtaak op GitHub Actions."
        )
    else:
        fetch_klassement = st.checkbox(
            "📈 Ook klassementshistoriek ophalen (lokaal, ±30-60s per nog onbekende speler)",
            value=True, key=f"fetch_klassement_{sel_player_id}",
        )

    if st.button("🔍 Tegenstander analyseren", key=f"btn_scout_{sel_player_id}", type="primary"):
        st.session_state[scout_key] = _run_scout_and_scrape(
            fixtures, opp, next_match, lookback,
            auto_scrape=can_scrape, fetch_klassement=fetch_klassement,
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
    all_docs = ll.get_docs_for_players([p["user_id"] for p in unique_players])

    if unknown_ids:
        st.caption(f"⚠️ {len(unknown_ids)} speler(s) nog niet volledig gekend qua matchdata.")
        if not can_scrape:
            render_cloud_scrape_trigger(
                key_prefix=f"scout_scrape_{sel_player_id}",
                player_ids=",".join(sorted(unknown_ids)),
                mode="missing",
                label="🚀 Nieuwe tegenstanders ophalen",
            )

    global_docs = _load_all_player_docs()

    oa.render_team_analysis(
        bundle,
        opp,
        all_docs,
        current_reeks_url=reeks_url,
        current_spelgroep_id=spelgroep_id,
        home_player_id=sel_player_id,
        global_docs=global_docs,
        go_to_player_fn=go_to_player_fn,
        key_prefix=f"scout_team_{sel_player_id}",
    )

    return bundle, opp
