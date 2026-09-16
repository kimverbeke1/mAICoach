"""
page_lineup_lab.py — "🧩 Opstelling-analyse"-pagina (Volgende match,
Opstelling-scenario's, Rotatieplanner, Opgeslagen analyses).

PADEL_ANALYSIS_SPLIT_DASHBOARD_2026-09-14: losgemaakt uit dashboard.py,
ongewijzigde logica. Dit is bewust het GROOTSTE van de opgesplitste
bestanden (bevat de rotatieplanner-combinatoriek), maar nog altijd een
fractie van de oorspronkelijke ~1800-regel dashboard.py.

PADEL_ANALYSIS_MANUAL_POULE_URL_PERSIST_2026-09-15 (op verzoek van Kim):
Het invoerveld voor een handmatige poule-URL bewaarde vroeger naar het
AUTOMATISCHE Firestore-veld poule_reeks_url — exact hetzelfde veld dat
poule_playwright.update_player_poule() bij elke dagelijkse run zelf
overschrijft. Vervangen door manual_poule_input.render(), dat schrijft naar
poule_reeks_url_manual (heeft ALTIJD voorrang, ook bij force=True).
Aangeboden op drie plekken: geen URL gekend, ophalen mislukt, geen
wedstrijden gevonden — en (PADEL_ANALYSIS_MANUAL_POULE_URL_ALWAYS_AVAILABLE_
2026-09-15) OOK wanneer er al een (mogelijk verouderd) schema is en in de
"klik om te laden"-tak, ingeklapt, zodat het veld nooit onbereikbaar is.

PADEL_ANALYSIS_RENDER_ORDER_2026-09-15 (op verzoek van Kim):
Volgorde is nu Volgende match -> OVERZICHTSTABEL + detail per speler ->
Opstelling-scenario's + Rotatieplanner -> AI-inzichten. Was voorheen:
Volgende match -> Opstelling-scenario's -> AI -> Overzicht/detail
(helemaal onderaan). Kim wil eerst zien WIE de tegenstanders zijn
(klassement, playing strength, vorm) voordat de scenario-berekeningen
getoond worden.

--------------------------------------------------------------------------
PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost, kern van de fix zit in lineup_lab.py): de matchup-edge in de
Opstelling-scenario's gebruikte voor "ons" de padelstats.be playing strength
maar voor "hen" het officiële TVL-klassement uit het historische
uitslagenblad — twee VERSCHILLENDE meetsystemen tegenover elkaar.
Fix hier: een opponent_ratings-dict wordt EENMALIG opgebouwd uit
bundle["unique_players"] en meegegeven aan zowel de scenario-berekening als
de Rotatieplanner, samen met player_official_ranks. lineup_lab.
optimize_lineup_vs_scenario() kiest daarmee per bord een consistente schaal
i.p.v. twee schalen te mengen.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SYNERGY_CONFIDENCE_SHRINKAGE_2026-09-15 (op verzoek van Kim)
--------------------------------------------------------------------------
Geen wijziging hier nodig — synergy_fn komt nog steeds uit
ll.make_pair_score_fn(), maar die functie past sinds deze datum zelf
confidence-shrinkage toe.

--------------------------------------------------------------------------
PADEL_ANALYSIS_LINEUP_LOAD_PERSIST_FIX_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
BUG (opgelost, kern van de fix zit in dashboard_common.py): de "📅 Volgende
match laden"-knop riep enkel _load_poule_fixtures() aan — een kale
requests-fetch zonder poule_id-scoping, die BOVENDIEN nooit iets naar
Firestore schreef. Fix hier: de fetch-aanroep in
_render_volgende_match_and_scout() gebruikt nu dashboard_common.
_load_poule_schedule_robust(), die - wanneer lokaal scrapen beschikbaar is -
dezelfde Playwright-gebaseerde, pouleId-scopende, Firestore-persisterende
pijplijn gebruikt als poule_playwright.py.

--------------------------------------------------------------------------
PADEL_ANALYSIS_ALL_COMBINATIONS_AGGREGATE_2026-09-16 (op verzoek van Kim)
--------------------------------------------------------------------------
_SCENARIO_CANDIDATE_POOL (=400, gelijk aan de Rotatieplanner) wordt expliciet
meegegeven aan optimize_lineup_vs_scenario(), zodat ECHT alle haalbare
koppelverdelingen meedingen. _SCENARIO_SAVE_TOP_N=400 zodat alle berekende
opties ook effectief bewaard worden. De UI toont per scenario standaard de
beste 10, met een checkbox om alles te zien. Een "📊 Aggregaatscore over alle
scenario's"-sectie toont per unieke koppelverdeling het gemiddelde/min/max
over alle scenario's waarin ze voorkwam.

--------------------------------------------------------------------------
PADEL_ANALYSIS_SCENARIO_TRANSPARENCY_AND_HISTORY_2026-09-16 (op verzoek van
Kim, vervolgvragen op de vorige fix)
--------------------------------------------------------------------------
Drie samenhangende opmerkingen na het testen van de vorige fix:

1. "Ik zie ook nergens dat je alle mogelijke combinaties gecheckt hebt? wat
   als bvb bert niet met sam speelt maar bert met gregory."
   Dit was WEL al het geval (zie PADEL_ANALYSIS_ALL_COMBINATIONS_AGGREGATE_
   2026-09-16 hierboven: candidate_pool=400, en bij <=8 spelers zijn er
   hoogstens 105 mogelijke koppelverdelingen, dus altijd ALLES doorgerekend
   -- reken na: (n-1)!! voor n=8 is 105 <= 400). Het probleem was puur dat de
   app dit NERGENS expliciet bevestigde. Fix: een ALTIJD zichtbare caption
   (niet enkel bij >12 spelers zoals voorheen) die het exacte aantal
   mogelijke koppelverdelingen toont en expliciet zegt of ALLES doorgerekend
   werd.

2. "beetje domme tabel met min en max en gemiddelde hetzelfde" bij de
   aggregaatscore. Verklaring, geen bug: bij weinig scenario's (bv. 3) komt
   dezelfde VOLLEDIGE koppelverdeling zelden in meer dan 1 scenario voor als
   beste optie (elke tegenstander-opstelling vraagt een andere optimale
   eigen opstelling) - dan is gemiddelde=min=max wiskundig onvermijdelijk
   (er is maar 1 datapunt). Fix: de tabel sorteert nu EERST op "In #
   scenario's" (aflopend), zodat combinaties die WEL in meerdere scenario's
   opduiken - waar de spreiding dus betekenisvol is - bovenaan staan, met een
   samenvattende caption die expliciet zegt hoeveel combinaties dat zijn.

3. "kan je ook net gemakkelijk zie hoe de vorige match was (wie was 1ste en
   wie was 2de match van de rotatie?)" - i.h.k.v. het vermoeden dat Sam (P100,
   dus relatief zwak op de HOGER-IS-STERKER-schaal) normaal op een lager bord
   dan Match 1 zou moeten staan. Nieuw: _render_previous_own_lineup() toont,
   als losstaande referentiesectie, de ECHTE opstelling van de meest recente
   eigen interclubontmoeting - welk koppel op welk bord (via round_text),
   in bordvolgorde, met het officiële klassement van de sterkste speler per
   koppel - zodat je meteen kan aftoetsen of de 'sterkste koppel op Match 1'
   -regel overeenkomt met wat er in de praktijk gebeurde.
"""

import re

import streamlit as st
import dashboard_common as dc
from dashboard_common import (
    fb, ll, ss, osu, oa, taa, is_scraping_available, render_cloud_scrape_trigger,
    _parse_match_date, _format_scraped_at, _display_name, _go_to_player,
    _clean_name, _get_all_profiles, _get_saved_poule_url, _save_poule_url,
    _get_saved_schedule, _load_poule_fixtures, _load_poule_schedule_robust,
    _official_current_rank,
)

# PADEL_ANALYSIS_MANUAL_POULE_URL_PERSIST_2026-09-15: optionele import, zodat
# deze pagina blijft werken ook als het component (nog) niet mee gedeployed is.
try:
    import manual_poule_input
except Exception:  # noqa: BLE001  pragma: no cover
    manual_poule_input = None


# ─────────────────────────────────────────────
# Volgende match + scout-header
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Ontmoetingen ophalen...")
def _load_encounter_index(profile_ids: tuple):
    docs = ll.get_docs_for_players(list(profile_ids))
    index = ll.build_encounter_index(docs)
    return docs, index


def _render_manual_url_fallback(
    sel_player_id: str,
    sel_label: str,
    key_prefix: str,
    expanded: bool = True,
) -> None:
    """PADEL_ANALYSIS_MANUAL_POULE_URL_PERSIST_2026-09-15.

    Toont het component dat de poule-URL BLIJVEND bewaart. Valt terug op het
    oude (niet-blijvende) tekstveld als manual_poule_input niet beschikbaar is,
    zodat deze pagina nooit stukloopt op een ontbrekende module."""
    if manual_poule_input is not None:
        manual_poule_input.render(
            str(sel_player_id), player_name=sel_label,
            key_prefix=key_prefix, expanded=expanded,
        )
        return

    st.caption(
        "⚠️ Component manual_poule_input niet gevonden — de URL wordt bewaard in "
        "het automatische veld en kan door de volgende update overschreven worden."
    )
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"
    manual_url = st.text_input("Poule/tabel-URL (eenmalig)", key=f"manual_url_input_{sel_player_id}")
    if manual_url and st.button("Onthouden & laden", key=f"use_manual_url_{sel_player_id}", type="primary"):
        u = manual_url.strip()
        st.session_state[override_url_key] = u
        _save_poule_url(sel_player_id, u)
        st.session_state[load_key] = True
        st.rerun()


def _render_schema_refresh_button(sel_player_id: str) -> None:
    if is_scraping_available():
        return
    with st.expander("🔄 Schema nu verversen (via GitHub Actions)", expanded=False):
        st.caption(
            "Start meteen een update van je matchen én het poule-schema op de "
            "achtergrond (GitHub Actions). Duurt meestal enkele minuten; daarna "
            "verschijnt de nieuwe volgende match hier automatisch."
        )
        render_cloud_scrape_trigger(
            key_prefix=f"vm_schema_{sel_player_id}",
            player_ids=str(sel_player_id),
            mode="missing",
            label="🔄 Schema nu verversen",
        )


def _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches):
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14."""
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    home_ploeg_id, away_ploeg_id, matched_fx = ss.identify_own_ploeg_id(fixtures, own_interclub_matches)
    own_ploeg_id = st.session_state.get(override_team_key)
    if not own_ploeg_id and matched_fx:
        own_ploeg_id = matched_fx.get("resolved_own_ploeg_id")
    if not own_ploeg_id and matched_fx:
        opp_names_known = {_clean_name(m.get("opp1_name")) for m in own_interclub_matches if m.get("opp1_name")}
        if any(_clean_name(matched_fx["away_name"]) in n or n in _clean_name(matched_fx["away_name"]) for n in opp_names_known):
            own_ploeg_id = home_ploeg_id
        else:
            own_ploeg_id = away_ploeg_id
    if not own_ploeg_id:
        st.warning(
            "Kon niet automatisch bepalen welke ploeg dit is op de poule-pagina. "
            "Kies hieronder eenmalig je eigen team."
        )
        team_names = sorted({f["home_name"] for f in fixtures} | {f["away_name"] for f in fixtures})
        chosen_team = st.selectbox(
            "Jouw team in dit schema:", [""] + team_names, key=f"manual_team_pick_{sel_player_id}"
        )
        if chosen_team and st.button("Bevestigen", key=f"confirm_team_{sel_player_id}"):
            match = next((f for f in fixtures if f["home_name"] == chosen_team), None)
            pid = match["home_ploeg_id"] if match else None
            if not pid:
                match = next((f for f in fixtures if f["away_name"] == chosen_team), None)
                pid = match["away_ploeg_id"] if match else None
            if pid:
                st.session_state[override_team_key] = pid
                st.rerun()
        return None
    return own_ploeg_id


def _render_volgende_match_and_scout(sel_player_id: str, sel_label: str):
    """PADEL_ANALYSIS_SPLIT_HEADER_FROM_DETAILS_2026-09-14."""
    st.markdown('<div class="section-header">📅 Volgende match</div>', unsafe_allow_html=True)
    override_url_key = f"manual_reeks_url_{sel_player_id}"
    override_team_key = f"manual_own_ploeg_id_{sel_player_id}"
    load_key = f"vm_loaded_{sel_player_id}"
    _render_schema_refresh_button(sel_player_id)
    sel_doc = fb.get_player(sel_player_id)
    own_interclub_matches = [
        m for m in (sel_doc or {}).get("matches", [])
        if m.get("match_type") == "interclub"
    ]

    def _finish(fixtures, reeks_url_val):
        own_ploeg_id = _resolve_own_ploeg_id(sel_player_id, fixtures, own_interclub_matches)
        if not own_ploeg_id:
            return None
        header_result = osu.render_scout_header(
            sel_player_id=str(sel_player_id), fixtures=fixtures, own_ploeg_id=own_ploeg_id,
        )
        if not header_result:
            return None
        bundle, opp = header_result
        return bundle, opp, reeks_url_val, opp.get("spelgroep_id")

    saved_fixtures, sched_at = _get_saved_schedule(sel_player_id)
    if saved_fixtures:
        reeks_url = _get_saved_poule_url(sel_player_id) or ""
        if sched_at:
            st.caption(f"Schema automatisch opgehaald (via de dagelijkse update) op {_format_scraped_at(sched_at)}.")
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_saved", expanded=False)
        return _finish(saved_fixtures, reeks_url)

    ic_with_url = [m for m in own_interclub_matches if m.get("reeks_url")]
    auto_reeks_url = None
    if ic_with_url:
        most_recent = sorted(
            ic_with_url,
            key=lambda m: _parse_match_date(m.get("match_date")) or (0, 0, 0),
            reverse=True,
        )[0]
        auto_reeks_url = most_recent["reeks_url"]

    saved_url = _get_saved_poule_url(sel_player_id)
    reeks_url = st.session_state.get(override_url_key) or saved_url or auto_reeks_url

    if not reeks_url:
        st.info(
            f"Nog geen poule/tabel-schema gekend voor {sel_label}. Dit wordt normaal "
            "automatisch opgehaald door de dagelijkse update (of via de knop hierboven "
            "op de cloud). Je kan hieronder ook zelf de poule/tabel-link plakken — "
            "die wordt blijvend onthouden."
        )
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_nourl")
        return None

    if not st.session_state.get(load_key):
        src = "handmatig ingesteld" if (st.session_state.get(override_url_key) or saved_url) else "automatisch gevonden via je laatste interclubmatch"
        st.caption(f"Poule/tabel-link is {src}. Klik om je volgende match te laden.")
        cbtn1, cbtn2 = st.columns([1, 1])
        with cbtn1:
            if st.button("📅 Volgende match laden", key=f"load_vm_{sel_player_id}", type="primary"):
                st.session_state[load_key] = True
                st.rerun()
        with cbtn2:
            if st.button("✏️ Andere poule-link gebruiken", key=f"change_url_{sel_player_id}"):
                st.session_state.pop(override_url_key, None)
                _save_poule_url(sel_player_id, "")
                st.session_state.pop(load_key, None)
                st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_haveurl", expanded=False)
        return None

    with st.spinner("Wedstrijdschema ophalen..."):
        try:
            fixtures, fetch_error, meta = _load_poule_schedule_robust(sel_player_id, reeks_url)
        except Exception as e:
            fixtures, fetch_error, meta = [], str(e), None

    if meta is not None and fixtures and not fetch_error:
        st.session_state.pop(load_key, None)
        st.rerun()

    if fetch_error:
        st.warning(f"Kon het wedstrijdschema niet ophalen: {fetch_error}")
        if st.button("🔁 Opnieuw proberen", key=f"retry_vm_{sel_player_id}"):
            _load_poule_fixtures.clear()
            st.rerun()
        if st.button("✏️ Andere poule-link", key=f"reset_manual_{sel_player_id}"):
            st.session_state.pop(override_url_key, None)
            st.session_state.pop(override_team_key, None)
            _save_poule_url(sel_player_id, "")
            st.session_state.pop(load_key, None)
            st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_fetcherr")
        return None

    if not fixtures:
        st.warning("Geen wedstrijden gevonden op de poule-pagina (onverwachte paginastructuur?).")
        if st.button("🔁 Opnieuw proberen", key=f"retry_nofix_{sel_player_id}"):
            _load_poule_fixtures.clear()
            st.rerun()
        if st.button("✏️ Andere poule-link", key=f"reset_manual_nofix_{sel_player_id}"):
            st.session_state.pop(override_url_key, None)
            _save_poule_url(sel_player_id, "")
            st.session_state.pop(load_key, None)
            st.rerun()
        _render_manual_url_fallback(sel_player_id, sel_label, key_prefix="vm_nofix")
        return None

    return _finish(fixtures, reeks_url)


def _recent_own_lineup_player_ids(sel_player_id: str, profiles: list) -> set:
    """PADEL_ANALYSIS_SCENARIO_DEFAULT_RECENT_LINEUP_2026-09-10."""
    try:
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs, index = _load_encounter_index(profile_ids)
        all_encounters = ll.list_encounters(index)
        own_keys = [
            key for key, _ in all_encounters
            if any(pid == sel_player_id for pid, _ in index[key])
        ]
        if not own_keys:
            return set()

        def _encounter_date(key):
            dates = []
            for _, entry in index[key]:
                d = _parse_match_date(entry.get("match_date"))
                if d:
                    dates.append(d)
            return max(dates) if dates else (0, 0, 0)

        most_recent_key = max(own_keys, key=_encounter_date)
        boards = ll.reconstruct_boards(index[most_recent_key]) or []
        player_ids = set()
        for board in boards:
            for pid in (board.get("pair") or []):
                if pid:
                    player_ids.add(pid)
        return player_ids
    except Exception:
        return set()


# PADEL_ANALYSIS_SCENARIO_TRANSPARENCY_AND_HISTORY_2026-09-16
def _parse_round_number(text) -> int | None:
    """Haalt een bordnummer uit round_text (bv. 'Wedstrijd 2', 'Match 1',
    'Bord 3') zodat de effectieve opstelling van de vorige ontmoeting in de
    juiste volgorde getoond kan worden. Geeft None terug als er geen getal
    in de tekst staat -- die rij wordt dan gewoon achteraan gesorteerd."""
    if not text:
        return None
    m = re.search(r"(\d+)", str(text))
    return int(m.group(1)) if m else None


def _get_previous_own_encounter(sel_player_id: str, profiles: list):
    """PADEL_ANALYSIS_SCENARIO_TRANSPARENCY_AND_HISTORY_2026-09-16.

    Zoekt de meest recente interclubontmoeting van sel_player_id op (zelfde
    bron als _recent_own_lineup_player_ids) en reconstrueert de ECHTE
    opstelling: welk koppel speelde welk bord, in welke volgorde, en met
    welk resultaat. Bedoeld als referentiepunt om de 'sterkste koppel op
    Match 1'-regel te toetsen aan wat er in de praktijk gebeurde.

    Returns (label, boards). boards is een lijst van dicts (uitbreiding van
    ll.reconstruct_boards()'s resultaat met een extra "round_num"-veld),
    gesorteerd op rondenummer waar bekend. Geeft (None, []) terug als er
    niets gevonden wordt."""
    try:
        profile_ids = tuple(sorted(p.get("player_id") for p in profiles if p.get("player_id")))
        docs, index = _load_encounter_index(profile_ids)
        all_encounters = ll.list_encounters(index)
        own_keys_labels = [
            (key, label) for key, label in all_encounters
            if any(pid == sel_player_id for pid, _ in index[key])
        ]
        if not own_keys_labels:
            return None, []

        def _encounter_date(item):
            key = item[0]
            dates = []
            for _, entry in index[key]:
                d = _parse_match_date(entry.get("match_date"))
                if d:
                    dates.append(d)
            return max(dates) if dates else (0, 0, 0)

        most_recent_key, most_recent_label = max(own_keys_labels, key=_encounter_date)
        boards = ll.reconstruct_boards(index[most_recent_key]) or []
        for b in boards:
            b["round_num"] = _parse_round_number(b.get("round_text"))
        boards.sort(key=lambda b: (b["round_num"] is None, b["round_num"] or 0))
        return most_recent_label, boards
    except Exception:
        return None, []


def _render_previous_own_lineup(sel_player_id: str, profiles: list, name_lookup_global: dict) -> None:
    """PADEL_ANALYSIS_SCENARIO_TRANSPARENCY_AND_HISTORY_2026-09-16.

    Toont, als losstaande referentiesectie, de EFFECTIEVE opstelling van de
    meest recente eigen interclubontmoeting: welk koppel op welk bord, in
    bordvolgorde, met het officiële klassement van de sterkste speler per
    koppel -- zodat je kan aftoetsen of de 'sterkste koppel op Match 1'-regel
    overeenkomt met wat er in de praktijk gebeurde (bv. of een speler met een
    lager klassement zoals P100 wel degelijk op een lager bord stond)."""
    label, boards = _get_previous_own_encounter(sel_player_id, profiles)
    if not boards:
        return
    with st.expander(f"📋 Vorige ontmoeting ter referentie: {label}", expanded=False):
        st.caption(
            "De effectieve opstelling van jullie laatste interclubontmoeting, in bordvolgorde (waar "
            "bekend uit de TVL-data). Handig om te controleren of de 'sterkste koppel op Match 1'-regel "
            "overeenkomt met wat er in de praktijk gebeurde."
        )
        rows = []
        for b in boards:
            pair = tuple(b.get("pair") or ())
            if len(pair) != 2:
                continue
            p1, p2 = pair
            rank1 = _official_current_rank(p1) or 0
            rank2 = _official_current_rank(p2) or 0
            sterkste = max(rank1, rank2)
            bord_label = b.get("round_text") or "onbekend bord"
            if b.get("score"):
                resultaat = b["score"]
            elif b.get("won") is True:
                resultaat = "Gewonnen"
            elif b.get("won") is False:
                resultaat = "Verloren"
            else:
                resultaat = "?"
            rows.append({
                "Bord": bord_label,
                "Koppel": f"{name_lookup_global.get(p1, p1)} / {name_lookup_global.get(p2, p2)}",
                "Sterkste in koppel": f"P{int(sterkste)}" if sterkste else "onbekend",
                "Resultaat": resultaat,
            })
        if not rows:
            st.info("Geen volledige koppels teruggevonden voor deze ontmoeting.")
            return
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if all(r["Bord"] == "onbekend bord" for r in rows):
            st.caption(
                "⚠️ Geen rondenummer/bordlabel gekend in de brondata (round_text ontbreekt) — de "
                "volgorde hierboven is dus niet gegarandeerd de effectieve bordvolgorde."
            )


# PADEL_ANALYSIS_MATCHUP_SCALE_CONSISTENCY_2026-09-15
def _opponent_padelstat_ratings(bundle: dict) -> dict:
    """Bouwt {user_id: padelstat_rating} op voor ALLE tegenstander-spelers in
    de bundle (bundle["unique_players"])."""
    out = {}
    for p in bundle.get("unique_players", []) or []:
        uid = p.get("user_id")
        if not uid:
            continue
        try:
            rating = oa.get_own_player_rating(uid)[0]
        except Exception:
            rating = None
        if rating is not None:
            out[str(uid)] = rating
    return out


# ─────────────────────────────────────────────
# Rotatieplanner - combinatoriek
# PADEL_ANALYSIS_ROTATION_PLANNER_REDESIGN_2026-09-14
# ─────────────────────────────────────────────
def _count_perfect_matchings(n: int) -> int:
    """(n-1)!! - aantal mogelijke volledige koppelverdelingen van n spelers."""
    if n < 2 or n % 2 != 0:
        return 0
    result = 1
    k = n - 1
    while k > 0:
        result *= k
        k -= 2
    return result


_ROTATION_EXHAUSTIVE_LIMIT = 400


def _rank_pairs_by_official_rank(pairs: list, official_ranks: dict) -> list:
    """PADEL_ANALYSIS_MATCH1_STRONGEST_RULE_2026-09-14."""
    def pair_strength(pair):
        return max((official_ranks.get(pid) or 0) for pid in pair)
    return sorted(pairs, key=pair_strength, reverse=True)


def _generate_rotation_candidates(
    available_ids: list,
    synergy_fn,
    official_ranks: dict,
    excluded_pairs: set,
    opponent_boards=None,
    player_ratings=None,
    opponent_ratings=None,
    max_results: int = 10,
):
    """Genereert kandidaat-koppelverdelingen voor ÉÉN rotatie, EXHAUSTIEF
    voor kleine/gemiddelde groepen."""
    n = len(available_ids)
    if n < 2 or n % 2 != 0:
        return [], 0
    total_possible = _count_perfect_matchings(n)
    top_n = min(max(total_possible, 1), _ROTATION_EXHAUSTIVE_LIMIT)
    required = {pid: 1 for pid in available_ids}
    results = []
    if opponent_boards and player_ratings is not None:
        raw, truncated = ll.optimize_lineup_vs_scenario(
            available_ids, required, synergy_fn, opponent_boards, player_ratings,
            player_official_ranks=official_ranks, opponent_ratings=opponent_ratings,
            top_n=top_n, candidate_pool=_ROTATION_EXHAUSTIVE_LIMIT,
        )
        for option in raw:
            pairs = [frozenset(a["our_pair"]) for a in option["assignment"]]
            if any(p in excluded_pairs for p in pairs):
                continue
            pair_to_assignment = {frozenset(a["our_pair"]): a for a in option["assignment"]}
            ordered = _rank_pairs_by_official_rank(pairs, official_ranks)
            assignment_ordered = [pair_to_assignment[p] for p in ordered]
            results.append({
                "score": option["total_score"],
                "ordered_pairs": ordered,
                "assignment": assignment_ordered,
            })
    else:
        raw, truncated = ll.optimize_lineup(available_ids, required, synergy_fn, top_n=top_n)
        for score, pairs in raw:
            pairs_fs = [frozenset(p) for p in pairs]
            if any(p in excluded_pairs for p in pairs_fs):
                continue
            ordered = _rank_pairs_by_official_rank(pairs_fs, official_ranks)
            results.append({"score": score, "ordered_pairs": ordered, "assignment": None})
    results.sort(key=lambda r: -r["score"])
    return results[:max_results], total_possible


def _lineup_options_for_ai(candidates: list, name_lookup: dict) -> list:
    """Zet _generate_rotation_candidates()-resultaten om naar het formaat dat
    team_ai_advisor.analyze_lineup_options() verwacht."""
    out = []
    for cand in candidates:
        assignment = []
        if cand["assignment"]:
            for a in cand["assignment"]:
                assignment.append({
                    "our_pair": tuple(a["our_pair"]),
                    "synergy": a.get("synergy", 0.0),
                    "edge": a.get("edge", 0.0),
                    "opponent_board": a.get("opponent_board", {}),
                })
        else:
            for pair in cand["ordered_pairs"]:
                p1, p2 = tuple(pair)
                assignment.append({
                    "our_pair": (p1, p2),
                    "synergy": 0.0,
                    "edge": 0.0,
                    "opponent_board": {"opponent_pair": []},
                })
        out.append({"total_score": cand["score"], "assignment": assignment})
    return out


def _render_rotation_planner(
    available_ids: list,
    synergy_fn,
    official_ranks: dict,
    name_lookup_global: dict,
    opp: dict,
    opponent_boards=None,
    player_ratings=None,
    opponent_ratings=None,
    report_for_ai=None,
):
    """PADEL_ANALYSIS_ROTATION_PLANNER_REDESIGN_2026-09-14."""
    st.markdown('<div class="section-header">🔁 Rotatieplanner</div>', unsafe_allow_html=True)
    st.caption(
        "Alle mogelijke koppelverdelingen voor de eerstvolgende rotatie, gerangschikt van beste naar "
        "slechtste. Klik aan wie/welke combinatie effectief speelde (of zal spelen) om door te gaan naar "
        "de volgende rotatie - elke speler krijgt zo nooit twee keer dezelfde partner. De speler met het "
        "hoogste officiële klassement staat steeds op Match 1."
    )
    if len(available_ids) < 2 or len(available_ids) % 2 != 0:
        st.info("Selecteer een even aantal spelers (bij 'Beschikbare eigen spelers' hierboven) om de rotatieplanner te gebruiken.")
        return
    ploeg_id = opp["ploeg_id"]
    locked_key = f"rot_locked_v2_{ploeg_id}_{'_'.join(sorted(available_ids))}"
    if locked_key not in st.session_state:
        st.session_state[locked_key] = []
    locked_rotations = st.session_state[locked_key]
    for rot_idx, pairs in enumerate(locked_rotations, start=1):
        st.markdown(f"**Rotatie {rot_idx} (bevestigd):**")
        for match_idx, pair in enumerate(pairs, start=1):
            p1, p2 = tuple(pair)
            st.write(f"Match {match_idx}: {name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}")
        if st.button(f"✏️ Rotatie {rot_idx} wijzigen", key=f"rot_edit_v2_{ploeg_id}_{rot_idx}"):
            st.session_state[locked_key] = locked_rotations[: rot_idx - 1]
            st.rerun()
        st.markdown("---")
    excluded_pairs = {p for rot in locked_rotations for p in rot}
    next_rotation_num = len(locked_rotations) + 1
    candidates, total_possible = _generate_rotation_candidates(
        available_ids, synergy_fn, official_ranks, excluded_pairs,
        opponent_boards=opponent_boards, player_ratings=player_ratings,
        opponent_ratings=opponent_ratings,
        max_results=15,
    )
    if not candidates:
        if total_possible == 0:
            st.info("Geen geldige koppelverdeling meer mogelijk (oneven aantal spelers of geen spelers beschikbaar).")
        else:
            st.warning(
                f"Alle {total_possible} mogelijke koppelverdelingen voor deze groep zijn al gebruikt in "
                "eerdere rotaties (elke speler heeft dan al met elke andere speler samengespeeld). Geen "
                "nieuwe rotatie meer mogelijk zonder een partner te herhalen."
            )
        return
    st.markdown(f"**Rotatie {next_rotation_num} - kies de effectieve/geplande combinatie:**")
    if total_possible > len(candidates):
        st.caption(f"Top {len(candidates)} van {total_possible} mogelijke combinaties getoond (op score gerangschikt).")
    else:
        st.caption(f"Alle {total_possible} mogelijke combinaties voor deze rotatie, op score gerangschikt.")
    option_labels = []
    for i, cand in enumerate(candidates):
        parts = []
        for match_idx, pair in enumerate(cand["ordered_pairs"], start=1):
            p1, p2 = tuple(pair)
            parts.append(f"M{match_idx}: {name_lookup_global.get(p1,p1)}/{name_lookup_global.get(p2,p2)}")
        prefix = "★ " if i == 0 else ""
        option_labels.append(f"{prefix}{' | '.join(parts)}  (score {cand['score']:.3f})")
    chosen_idx = st.radio(
        "Combinaties", list(range(len(candidates))), format_func=lambda i: option_labels[i],
        key=f"rot_choice_v2_{ploeg_id}_{next_rotation_num}", label_visibility="collapsed",
    )
    chosen = candidates[chosen_idx]
    if chosen["assignment"]:
        with st.expander("Detail van de gekozen combinatie (synergie + matchup-edge per paar)", expanded=False):
            for match_idx, a in enumerate(chosen["assignment"], start=1):
                p1, p2 = a["our_pair"]
                opp_names = " / ".join(p.get("name", "?") for p in a.get("opponent_board", {}).get("opponent_pair", []))
                schaal = a.get("edge_scale")
                schaal_txt = {"padelstat": "playing strength", "official": "officieel klassement"}.get(schaal, schaal or "?")
                st.write(
                    f"Match {match_idx}: **{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
                    f"(synergie {a['synergy']}) — vs **{opp_names or 'onbekend'}** "
                    f"(matchup-edge {a['edge']:+.2f}, o.b.v. {schaal_txt})"
                )
    ai_key = f"rot_ai_v2_{ploeg_id}_{next_rotation_num}"
    if taa is not None and report_for_ai is not None:
        if st.button("🤖 AI-inzicht over deze combinaties", key=f"rot_ai_btn_v2_{ploeg_id}_{next_rotation_num}"):
            with st.spinner("AI analyseert de combinaties..."):
                try:
                    ai_options = _lineup_options_for_ai(candidates[:5], name_lookup_global)
                    st.session_state[ai_key] = taa.analyze_lineup_options(report_for_ai, ai_options, name_lookup_global)
                except Exception as exc:
                    st.session_state[ai_key] = f"⚠️ Mislukt: {exc}"
        if st.session_state.get(ai_key):
            st.markdown(st.session_state[ai_key])
    if st.button(f"✅ Bevestig rotatie {next_rotation_num}", key=f"rot_confirm_v2_{ploeg_id}_{next_rotation_num}", type="primary"):
        st.session_state[locked_key] = locked_rotations + [chosen["ordered_pairs"]]
        st.rerun()


# ─────────────────────────────────────────────
# Opstelling-scenario's
# ─────────────────────────────────────────────
_SCENARIO_CANDIDATE_POOL = 400
_SCENARIO_SAVE_TOP_N = 400
_SCENARIO_DISPLAY_DEFAULT_N = 10
_AGGREGATE_DISPLAY_DEFAULT_N = 20


def _aggregate_scenario_scores(scenarios: list) -> list:
    """PADEL_ANALYSIS_ALL_COMBINATIONS_AGGREGATE_2026-09-16, sortering
    aangepast in PADEL_ANALYSIS_SCENARIO_TRANSPARENCY_AND_HISTORY_2026-09-16.

    Bouwt, over ALLE scenario's heen, per unieke eigen koppelverdeling
    (de VOLLEDIGE toewijzing van paren over alle borden, niet één los paar)
    de lijst van scores waarin die combinatie voorkwam.

    Returns een lijst van (combo_key, {"avg","min","max","count"}), gesorteerd
    op AFLOPEND aantal scenario's waarin de combinatie voorkwam ("count"),
    en bij gelijke count op aflopend gemiddelde. Combinaties die in
    meerdere scenario's voorkwamen (dus een ECHT gemiddelde/spreiding
    hebben) staan zo altijd bovenaan; combinaties met count=1 (waarvoor
    avg=min=max wiskundig noodzakelijk gelijk zijn, want er is maar 1
    datapunt) komen onderaan."""
    scores_by_combo: dict = {}
    for entry in scenarios:
        for option in (entry.get("results") or []):
            pairs = sorted(
                tuple(sorted(a["our_pair"])) for a in option.get("assignment", []) or []
            )
            if not pairs:
                continue
            combo_key = tuple(pairs)
            scores_by_combo.setdefault(combo_key, []).append(option["total_score"])

    aggregated = []
    for combo_key, scores in scores_by_combo.items():
        aggregated.append((combo_key, {
            "avg": sum(scores) / len(scores),
            "min": min(scores),
            "max": max(scores),
            "count": len(scores),
        }))
    aggregated.sort(key=lambda item: (-item[1]["count"], -item[1]["avg"]))
    return aggregated


def _render_opstelling_scenario(bundle, opp, profiles, name_lookup_global, sel_player_id, report):
    """PADEL_ANALYSIS_LINEUP_SCENARIO_REDESIGN_2026-09-13 / _2026-09-14 /
    _ALL_COMBINATIONS_AGGREGATE_2026-09-16 / _SCENARIO_TRANSPARENCY_AND_
    HISTORY_2026-09-16."""
    st.divider()
    st.markdown('<div class="section-header">🧮 Opstelling-scenario\'s</div>', unsafe_allow_html=True)
    st.caption(
        "Per scenario (een eerdere opstelling van de tegenstander dit seizoen) berekenen we automatisch "
        "de beste opties voor onze eigen opstelling — over ALLE mogelijke koppelverdelingen heen. Geen "
        "voorspelling van wat ze NU zullen opstellen — wel een idee van de mogelijkheden op basis van wat "
        "ze eerder deden."
    )

    with st.expander("ℹ️ Wat betekenen synergie, matchup-edge, score en aggregaatscore?", expanded=False):
        st.markdown(
            "- **Synergie**: hoe goed dit koppel historisch samen presteert (confidence-shrinkage: "
            "hoe minder gezamenlijke wedstrijden, hoe meer teruggetrokken richting het individuele "
            "gemiddelde). Waarde tussen 0 en 1.\n"
            "- **Matchup-edge**: een ruwe inschatting van het krachtsverschil met het tegenstander-"
            "koppel op dat bord. Gebruikt padelstats.be playing strength voor BEIDE koppels zodra "
            "die voor de tegenstander gekend is; anders het officiële klassement voor BEIDE zijden — "
            "nooit een mix. Positief = wij naar verwachting sterker.\n"
            "- **Score**: synergie + matchup-edge, opgeteld over alle borden van dat ENE scenario.\n"
            "- **Aggregaatscore**: het gemiddelde van de score van een VOLLEDIGE koppelverdeling over "
            "ALLE scenario's waarin ze voorkwam. Combinaties die in meerdere scenario's opduiken staan "
            "bovenaan de tabel — daar is de spreiding (min/max) betekenisvol. Combinaties die maar in "
            "1 scenario voorkwamen hebben noodzakelijk avg=min=max (er is dan maar 1 datapunt) — dat "
            "is normaal bij weinig scenario's per tegenstander, geen fout."
        )

    own_candidates = sorted(profiles, key=lambda x: x.get("display_name") or "")
    own_labels = [_display_name(p) for p in own_candidates]
    own_label_to_id = {_display_name(p): p.get("player_id") for p in own_candidates}

    recent_ids = _recent_own_lineup_player_ids(sel_player_id, profiles)
    if recent_ids:
        default_labels = [lbl for lbl, pid in own_label_to_id.items() if pid in recent_ids]
        sel_label_self = next((lbl for lbl, pid in own_label_to_id.items() if pid == sel_player_id), None)
        if sel_label_self and sel_label_self not in default_labels:
            default_labels.append(sel_label_self)
        st.caption(f"Standaard vooraf geselecteerd: de spelers van jullie vorige interclubontmoeting ({len(default_labels)} speler(s)). Pas gerust aan.")
        if len(default_labels) < 4:
            st.warning(
                f"Slechts {len(default_labels)} speler(s) automatisch teruggevonden voor de vorige "
                "ontmoeting. Dit gebeurt als niet alle teamgenoten van die dag zelf al zijn toegevoegd "
                "via '➕ Speler toevoegen' - hun matchdata is dan nog onbekend. Vul de selectie hieronder "
                "gerust manueel aan met de ontbrekende teamgenoten."
            )
    else:
        default_labels = own_labels[: min(8, len(own_labels))]

    available_labels = st.multiselect(
        "Beschikbare eigen spelers", own_labels,
        default=default_labels,
        key="scenario_available_players",
    )
    if len(available_labels) < 2:
        st.info("Selecteer minstens 2 spelers om een opstelling te kunnen berekenen.")
        return
    available_ids = [own_label_to_id[lbl] for lbl in available_labels]

    # PADEL_ANALYSIS_SCENARIO_TRANSPARENCY_AND_HISTORY_2026-09-16: referentie
    # naar de ECHTE vorige opstelling, om de Match1-sterkste-regel te toetsen.
    _render_previous_own_lineup(sel_player_id, profiles, name_lookup_global)

    # PADEL_ANALYSIS_SCENARIO_TRANSPARENCY_AND_HISTORY_2026-09-16: ALTIJD
    # zichtbare bevestiging van de combinatorische dekking (was voorheen
    # enkel een waarschuwing bij >12 spelers, waardoor bij normale groepen
    # (bv. 8 spelers) nergens bevestigd werd dat ECHT alles doorgerekend
    # wordt -- vandaar Kim's twijfel of bv. Bert/Gregory wel overwogen werd).
    total_possible_combos = _count_perfect_matchings(len(available_ids))
    if total_possible_combos:
        if total_possible_combos <= _SCENARIO_CANDIDATE_POOL:
            st.caption(
                f"🔢 Er zijn **{total_possible_combos}** mogelijke koppelverdelingen voor deze "
                f"{len(available_ids)} spelers — ALLEMAAL worden per scenario doorgerekend "
                "(dus ook alternatieven zoals een ander koppel voor eenzelfde speler)."
            )
        else:
            st.caption(
                f"🔢 Er zijn **{total_possible_combos}** mogelijke koppelverdelingen voor deze "
                f"{len(available_ids)} spelers — de {_SCENARIO_CANDIDATE_POOL} beste (op eigen "
                "synergie) worden per scenario doorgerekend, niet letterlijk elke combinatie."
            )

    suggested_boards = max((len(fx.get("boards", [])) for fx in bundle.get("previous_fixtures", [])), default=6) or 6
    c1, c2 = st.columns(2)
    with c1:
        total_boards = st.number_input("Aantal wedstrijden deze ontmoeting", min_value=1, value=int(suggested_boards), step=1)
    with c2:
        st.caption(f"Voorstel gebaseerd op vorige ontmoeting van de tegenstander: {suggested_boards} wedstrijden.")

    default_max = max(1, -(-2 * total_boards // len(available_ids)))
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
        return

    if not bundle.get("previous_fixtures"):
        st.info("Geen scenario's beschikbaar (geen eerdere, al gespeelde wedstrijd van deze tegenstander gevonden).")
        return

    docs_for_synergy = ll.get_docs_for_players(available_ids)
    own_synergy = ll.compute_pairwise_synergy(docs_for_synergy, available_ids)
    synergy_fn = ll.make_pair_score_fn(own_synergy, docs_for_synergy)
    player_ratings = {pid: oa.get_own_player_rating(pid)[0] for pid in available_ids}
    official_ranks = {pid: (_official_current_rank(pid) or player_ratings.get(pid, 0)) for pid in available_ids}
    opponent_ratings = _opponent_padelstat_ratings(bundle)

    signature = (
        tuple(sorted(available_ids)),
        tuple(sorted(max_per_player.items())),
        int(total_boards),
        opp.get("ploeg_id"),
    )
    compute_key = f"scenario_results_{opp['ploeg_id']}"
    sig_key = f"scenario_signature_{opp['ploeg_id']}"
    needs_compute = st.session_state.get(sig_key) != signature
    recompute_clicked = st.button("🔄 Herberekenen", key=f"scenario_recompute_{opp['ploeg_id']}")

    if needs_compute or recompute_clicked:
        computed = []
        with st.spinner(f"Alle mogelijke koppelverdelingen doorrekenen (tot {_SCENARIO_CANDIDATE_POOL} kandidaten per scenario)..."):
            for s_idx, fx_bundle in enumerate(bundle["previous_fixtures"], start=1):
                boards = fx_bundle.get("boards", [])
                fx = fx_bundle.get("fixture", {})
                entry = {
                    "s_idx": s_idx, "fixture": fx, "boards_count": len(boards),
                    "error": fx_bundle.get("error"), "results": None, "truncated": False,
                }
                if not entry["error"] and boards:
                    results, truncated = ll.optimize_lineup_vs_scenario(
                        available_ids, max_per_player, synergy_fn, boards, player_ratings,
                        player_official_ranks=official_ranks, opponent_ratings=opponent_ratings,
                        top_n=_SCENARIO_SAVE_TOP_N, candidate_pool=_SCENARIO_CANDIDATE_POOL,
                    )
                    entry["results"] = results
                    entry["truncated"] = truncated
                computed.append(entry)
        st.session_state[compute_key] = {
            "opponent_name": opp.get("name"),
            "opponent_ploeg_id": opp.get("ploeg_id"),
            "available_ids": available_ids,
            "available_labels": available_labels,
            "total_boards": int(total_boards),
            "max_per_player": max_per_player,
            "scenarios": computed,
        }
        st.session_state[sig_key] = signature

    stored = st.session_state.get(compute_key)
    if stored:
        for entry in stored["scenarios"]:
            s_idx, fx, boards_count = entry["s_idx"], entry["fixture"], entry["boards_count"]
            with st.expander(
                f"Scenario {s_idx}: hun opstelling tegen {fx.get('home_name') if fx.get('away_ploeg_id')==opp['ploeg_id'] else fx.get('away_name')} "
                f"({fx.get('date_text','?')}) — {boards_count} wedstrijden",
                expanded=(s_idx == 1),
            ):
                if entry["error"]:
                    st.warning(entry["error"])
                    continue
                if not entry["results"]:
                    if boards_count == 0:
                        st.info("Geen bord-detail kunnen ophalen voor dit scenario.")
                    else:
                        st.warning("Geen geldige opstelling gevonden binnen deze beperkingen.")
                    continue
                if entry["truncated"]:
                    st.caption(
                        f"⚠️ Meer dan {_SCENARIO_CANDIDATE_POOL} mogelijke koppelverdelingen — resultaat "
                        "gebaseerd op de beste kandidaten binnen die zoekdiepte, niet letterlijk elke "
                        "denkbare combinatie."
                    )
                total_computed = len(entry["results"])
                show_all_key = f"scenario_showall_{opp['ploeg_id']}_{s_idx}"
                show_all = False
                if total_computed > _SCENARIO_DISPLAY_DEFAULT_N:
                    show_all = st.checkbox(
                        f"Toon alle {total_computed} berekende opties (i.p.v. de beste {_SCENARIO_DISPLAY_DEFAULT_N})",
                        key=show_all_key,
                    )
                display_results = entry["results"] if show_all else entry["results"][:_SCENARIO_DISPLAY_DEFAULT_N]
                if show_all:
                    st.caption(f"Alle {total_computed} berekende opties getoond.")
                elif total_computed > len(display_results):
                    st.caption(f"Beste {len(display_results)} van {total_computed} berekende opties getoond. Bij opslaan worden ALLE {total_computed} bewaard.")
                for opt_idx, option in enumerate(display_results, start=1):
                    label = f"**Optie {opt_idx}" + (" (beste)" if opt_idx == 1 else "") + f" — score {option['total_score']}**"
                    st.markdown(label)
                    for a in option["assignment"]:
                        p1, p2 = a["our_pair"]
                        opp_pair = a["opponent_board"]["opponent_pair"]
                        opp_names = " / ".join(p.get("name", "?") for p in opp_pair)
                        schaal = a.get("edge_scale")
                        schaal_txt = {"padelstat": "playing strength", "official": "officieel klassement"}.get(schaal, "")
                        schaal_suffix = f", o.b.v. {schaal_txt}" if schaal_txt else ""
                        st.write(
                            f"**{name_lookup_global.get(p1,p1)} / {name_lookup_global.get(p2,p2)}** "
                            f"(synergie {a['synergy']}) — vs **{opp_names}** (matchup-edge: {a['edge']:+.2f}{schaal_suffix})"
                        )
                    if opt_idx < len(display_results):
                        st.markdown("---")
                if taa is not None and report is not None:
                    ai_key = f"scenario_ai_{opp['ploeg_id']}_{s_idx}"
                    if st.button("🤖 AI-analyse van deze opties", key=f"scenario_ai_btn_{opp['ploeg_id']}_{s_idx}"):
                        with st.spinner("AI analyseert de opties..."):
                            try:
                                st.session_state[ai_key] = taa.analyze_lineup_options(
                                    report, display_results, name_lookup_global
                                )
                            except Exception as exc:
                                st.session_state[ai_key] = f"⚠️ Mislukt: {exc}"
                    if st.session_state.get(ai_key):
                        st.markdown(st.session_state[ai_key])

        st.divider()
        if st.button("💾 Deze analyse opslaan (alle berekende opties)", key=f"save_analysis_{opp['ploeg_id']}"):
            payload = {
                "opponent_name": stored["opponent_name"],
                "opponent_ploeg_id": stored["opponent_ploeg_id"],
                "own_player_ids": stored["available_ids"],
                "own_player_labels": stored["available_labels"],
                "total_boards": stored["total_boards"],
                "max_per_player": stored["max_per_player"],
                "scenarios": [
                    {
                        "s_idx": e["s_idx"],
                        "fixture_label": e["fixture"].get("date_text", "?"),
                        "boards_count": e["boards_count"],
                        "options": [
                            {
                                "total_score": opt["total_score"],
                                "assignment": [
                                    {
                                        "our_pair_labels": [
                                            name_lookup_global.get(a["our_pair"][0], a["our_pair"][0]),
                                            name_lookup_global.get(a["our_pair"][1], a["our_pair"][1]),
                                        ],
                                        "synergy": a["synergy"],
                                        "edge": a["edge"],
                                        "opponent_names": [p.get("name", "?") for p in a["opponent_board"]["opponent_pair"]],
                                    }
                                    for a in opt["assignment"]
                                ],
                            }
                            for opt in (e["results"] or [])
                        ],
                    }
                    for e in stored["scenarios"]
                ],
            }
            doc_id = fb.save_lineup_analysis(sel_player_id, payload)
            n_total_options = sum(len(s["options"]) for s in payload["scenarios"])
            st.success(f"Analyse opgeslagen ({n_total_options} opties over {len(payload['scenarios'])} scenario's). Te bekijken via het tabblad 'Opgeslagen analyses'.")

        st.divider()
        st.markdown("#### 📊 Aggregaatscore over alle scenario's")
        st.caption(
            "Voor elke eigen koppelverdeling die in minstens één scenario een geldig resultaat had: het "
            "gemiddelde van zijn score over alle scenario's waarin die combinatie voorkwam. Combinaties "
            "die in MEERDERE scenario's voorkwamen (kolom 'In # scenario's' > 1) staan bovenaan — daar "
            "zijn gemiddelde/min/max effectief informatief. Rijen met 'In # scenario's' = 1 hebben "
            "noodzakelijk een gelijk gemiddelde, minimum en maximum (er is dan maar 1 datapunt) — dat is "
            "normaal en verwacht bij weinig scenario's per tegenstander, geen fout in de berekening."
        )
        aggregate = _aggregate_scenario_scores(stored["scenarios"])
        if not aggregate:
            st.info("Nog geen combinaties met een geldig resultaat in minstens 1 scenario.")
        else:
            n_multi = sum(1 for _, info in aggregate if info["count"] > 1)
            if n_multi:
                st.caption(f"✅ {n_multi} van de {len(aggregate)} unieke koppelverdelingen kwamen in meerdere scenario's voor.")
            else:
                st.caption(
                    f"ℹ️ Geen enkele koppelverdeling kwam in meerdere scenario's als beste optie voor — "
                    f"met {sum(1 for e in stored['scenarios'] if e.get('results'))} scenario('s) is dat "
                    "niet ongewoon (elke tegenstander-opstelling vraagt typisch een andere optimale eigen "
                    "opstelling). Onderstaande rijen tonen dus stuk voor stuk de beste optie per scenario, "
                    "niet een cross-scenario-gemiddelde."
                )
            show_all_agg_key = f"scenario_agg_showall_{opp['ploeg_id']}"
            show_all_agg = False
            if len(aggregate) > _AGGREGATE_DISPLAY_DEFAULT_N:
                show_all_agg = st.checkbox(
                    f"Toon alle {len(aggregate)} combinaties (i.p.v. de beste {_AGGREGATE_DISPLAY_DEFAULT_N})",
                    key=show_all_agg_key,
                )
            weer_te_geven = aggregate if show_all_agg else aggregate[:_AGGREGATE_DISPLAY_DEFAULT_N]
            agg_rows = []
            for combo_key, info in weer_te_geven:
                pair_labels = " | ".join(
                    f"{name_lookup_global.get(p1, p1)}/{name_lookup_global.get(p2, p2)}"
                    for p1, p2 in combo_key
                )
                agg_rows.append({
                    "Koppelverdeling": pair_labels,
                    "Gem. score": round(info["avg"], 3),
                    "Min": round(info["min"], 3),
                    "Max": round(info["max"], 3),
                    "In # scenario's": info["count"],
                })
            st.dataframe(agg_rows, use_container_width=True, hide_index=True)
            if not show_all_agg and len(aggregate) > len(weer_te_geven):
                st.caption(f"Beste {len(weer_te_geven)} van {len(aggregate)} unieke koppelverdelingen getoond.")

    st.divider()
    chosen_scenario_boards = None
    if stored and stored["scenarios"]:
        scenario_pick_labels = ["Geen (enkel eigen synergie)"] + [
            f"Scenario {e['s_idx']}: {e['fixture'].get('date_text','?')}" for e in stored["scenarios"] if e.get("results")
        ]
        scenario_pick = st.selectbox(
            "Matchup-inschatting voor de Rotatieplanner op basis van:",
            scenario_pick_labels, key=f"rot_scenario_pick_{opp['ploeg_id']}",
        )
        if scenario_pick != scenario_pick_labels[0]:
            s_idx_pick = int(scenario_pick.split(":")[0].replace("Scenario ", ""))
            matching_entry = next((e for e in stored["scenarios"] if e["s_idx"] == s_idx_pick), None)
            if matching_entry:
                chosen_scenario_boards = None
                for fx_bundle in bundle["previous_fixtures"]:
                    if fx_bundle.get("fixture") is matching_entry["fixture"]:
                        chosen_scenario_boards = fx_bundle.get("boards")
                        break

    _render_rotation_planner(
        available_ids, synergy_fn, official_ranks, name_lookup_global, opp,
        opponent_boards=chosen_scenario_boards, player_ratings=player_ratings,
        opponent_ratings=opponent_ratings,
        report_for_ai=report,
    )


def _render_saved_lineup_analyses(name_lookup_global: dict):
    """Toont alle eerder opgeslagen opstelling-scenario-analyses."""
    st.markdown('<div class="section-header">💾 Opgeslagen opstelling-analyses</div>', unsafe_allow_html=True)
    st.caption("Analyses die je eerder opsloeg via '💾 Deze analyse opslaan' bij Opstelling-scenario's.")
    analyses = fb.list_lineup_analyses()
    if not analyses:
        st.info("Nog geen analyses opgeslagen. Bereken en sla een opstelling-scenario op via het tabblad 'Analyseren'.")
        return
    labels = []
    for a in analyses:
        owner_label = name_lookup_global.get(a.get("owner_player_id"), a.get("owner_player_id"))
        saved_at = _format_scraped_at(a.get("saved_at"))
        labels.append(f"{a.get('opponent_name', '?')} — {owner_label} — {saved_at}")
    chosen = st.selectbox("Kies een opgeslagen analyse", labels, key="saved_analysis_pick")
    idx = labels.index(chosen)
    analysis = analyses[idx]
    st.markdown(f"**Tegenstander:** {analysis.get('opponent_name', '?')}")
    st.caption(
        f"Opgeslagen op {_format_scraped_at(analysis.get('saved_at'))} · "
        f"eigen spelers: {', '.join(analysis.get('own_player_labels', []) or [])}"
    )
    for scenario in analysis.get("scenarios", []) or []:
        options = scenario.get("options") or []
        with st.expander(f"Scenario {scenario.get('s_idx')}: {scenario.get('fixture_label', '?')} — {scenario.get('boards_count', 0)} wedstrijden ({len(options)} opties opgeslagen)"):
            if not options:
                st.info("Geen resultaat opgeslagen voor dit scenario.")
                continue
            for opt_idx, option in enumerate(options, start=1):
                st.write(f"**Optie {opt_idx} — score {option.get('total_score')}**")
                for a in option.get("assignment", []) or []:
                    pair_labels = a.get("our_pair_labels") or ["?", "?"]
                    opp_names = " / ".join(a.get("opponent_names", []) or [])
                    st.write(
                        f"{pair_labels[0]} / {pair_labels[1]} (synergie {a.get('synergy')}) — "
                        f"vs {opp_names} (matchup-edge {a.get('edge', 0):+.2f})"
                    )
    if st.button("🗑️ Deze analyse verwijderen", key=f"delete_analysis_{analysis.get('_doc_id')}"):
        fb.delete_lineup_analysis(analysis["_doc_id"])
        st.success("Analyse verwijderd.")
        st.rerun()


def page_lineup_lab():
    """PADEL_ANALYSIS_RENDER_ORDER_2026-09-15 (op verzoek van Kim):
    Volgende match -> OVERZICHTSTABEL + detail per speler -> Opstelling-
    scenario's + Rotatieplanner -> AI-inzichten tegenploeg."""
    st.header("🧩 Opstelling-analyse")
    profiles = _get_all_profiles()
    if not profiles:
        st.info("Nog geen spelers in de database. Voeg eerst spelers toe via '➕ Speler toevoegen'.")
        return
    name_lookup_global = {p.get("player_id"): _display_name(p) for p in profiles}
    profile_map = {_display_name(p): p for p in sorted(profiles, key=lambda x: x.get("display_name") or "")}
    settings = fb.get_app_settings()
    home_id = settings.get("home_player_id")
    home_label = next((lbl for lbl, p in profile_map.items() if p.get("player_id") == home_id), None)
    labels = list(profile_map.keys())
    default_idx = labels.index(home_label) if home_label in labels else 0
    tab_analyse, tab_saved = st.tabs(["🔍 Analyseren", "💾 Opgeslagen analyses"])
    with tab_analyse:
        sel_label = st.selectbox("Toon analyse voor:", labels, index=default_idx, key="lineup_lab_sel_player")
        sel_profile = profile_map[sel_label]
        sel_player_id = sel_profile.get("player_id")
        scout_result = _render_volgende_match_and_scout(str(sel_player_id), sel_label)
        if scout_result:
            bundle, opp, reeks_url, spelgroep_id = scout_result
            report_for_ai = None
            if bundle.get("unique_players"):
                all_docs, global_docs = osu.prepare_team_docs(bundle, str(sel_player_id))
                report_for_ai = oa.get_team_report(
                    bundle, opp, all_docs,
                    current_reeks_url=reeks_url, current_spelgroep_id=spelgroep_id,
                    global_docs=global_docs, key_prefix=f"scout_team_{sel_player_id}",
                )
                report_for_ai = oa.render_team_header(
                    report_for_ai, bundle, opp, all_docs,
                    current_reeks_url=reeks_url, current_spelgroep_id=spelgroep_id,
                    global_docs=global_docs, key_prefix=f"scout_team_{sel_player_id}",
                )
            if report_for_ai is not None:
                oa.render_overview_and_detail(
                    report_for_ai, go_to_player_fn=_go_to_player,
                    key_prefix=f"scout_team_{sel_player_id}",
                )
                st.divider()
            _render_opstelling_scenario(
                bundle, opp, profiles, name_lookup_global, str(sel_player_id), report_for_ai
            )
            if report_for_ai is not None:
                st.divider()
                oa.render_ai_section(report_for_ai, opp.get("ploeg_id"), key_prefix=f"scout_team_{sel_player_id}")
    with tab_saved:
        _render_saved_lineup_analyses(name_lookup_global)
