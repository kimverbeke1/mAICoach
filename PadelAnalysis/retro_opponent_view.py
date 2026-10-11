"""
retro_opponent_view.py - Nabeschouwing: de TEGENPLOEG van de gekozen ontmoeting tonen.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_PADELSTAT_COMPARE_2026-10-11 (op verzoek van Kim: "De nabeschouwing mag iets betere data tonen. Je
mag daar ook de spelerstabel van de tegenstander tonen zoals je bij de analyse doet. Je mag daar ook de vorige matchen van
die ploeg tonen zoals bij Analyse.")
--------------------------------------------------------------------------
Drie onderdelen, van licht naar zwaar:
  1. SPELERSTABEL (altijd): de tegenstanders uit de gekende matchen van deze ontmoeting, met hun klassement van toen (uit het
     uitslagenblad), de padelstat zoals die voor de wedstrijd gebruikt werd (waarde, meetdatum, soort) en hoeveel matchen ze
     speelden/wonnen. Komt volledig uit gegevens die de pagina al heeft - geen extra lezing.
  2. TEAMOVERZICHT (uitklapper): het opgeslagen teamrapport van die ploeg, met EXACT dezelfde tabel als bij Analyse
     (opponent_analysis.render_overview_tab). Dat rapport is berekend bij je laatste analyse van die ploeg; de waarden kunnen
     dus nieuwer zijn dan op de wedstrijddag (daarom staat de datum erbij). Is er geen opgeslagen rapport, dan ontbreekt dit blok.
  3. VORIGE ONTMOETINGEN (achter een vinkje): de eerdere ontmoetingen van die ploeg VOOR deze datum, met dezelfde functie als bij
     Analyse (lineup_opponent_history._render_previous_opponent_lineup). Achter een vinkje omdat het uitslagenbladen kan ophalen
     en de pagina anders trager wordt.
De tegenploeg wordt bepaald uit het opgeslagen poule-schema (vm_fixtures_<speler>): de ontmoeting van onze ploeg op die datum,
de andere kant is de tegenploeg. Alles faalt stil per onderdeel: een ontbrekend bestand of gegeven laat de rest gewoon staan.
De opmaak-functies komen uit lineup_retrospective.py (lui geimporteerd om een cirkelvormige import te vermijden).
"""
import re
from typing import Dict, List, Optional

import streamlit as st

_DATE_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def date_iso(text) -> Optional[str]:
    """"10/10/2026 14:00", "10-10-2026" of "2026-10-10" -> "2026-10-10"; onleesbaar -> None."""
    s = str(text or "").strip()
    m = _ISO_RE.match(s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = _DATE_RE.search(s)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


def _norm(text) -> str:
    return " ".join(str(text or "").lower().split())


def find_opponent_team(fixtures: list, own_ploeg_id, enc_date_text, enc_text: str = "") -> Optional[dict]:
    """De tegenploeg van onze ontmoeting op `enc_date_text`: {"ploeg_id", "name", "date_text", "own_home"} of None.
    Zijn er meerdere ontmoetingen van onze ploeg op die dag, dan wint die waarvan beide ploegnamen in de
    ontmoeting-tekst (`enc_text`, bv. "K.T.C. DE WITTE KAPROENEN A / Padel Factory B") voorkomen."""
    iso = date_iso(enc_date_text)
    own = str(own_ploeg_id or "")
    if not iso or not own:
        return None
    kandidaten = [
        fx for fx in fixtures or []
        if own in (str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id"))) and date_iso(fx.get("date_text")) == iso
    ]
    if not kandidaten:
        return None
    if len(kandidaten) > 1 and enc_text:
        tekst = _norm(enc_text)
        beter = [
            fx for fx in kandidaten
            if _norm(re.sub(r"^\d+\s+", "", str(fx.get("home_name") or ""))) in tekst
            and _norm(re.sub(r"^\d+\s+", "", str(fx.get("away_name") or ""))) in tekst
        ]
        kandidaten = beter or kandidaten
    fx = kandidaten[0]
    own_home = str(fx.get("home_ploeg_id")) == own
    return {
        "ploeg_id": str(fx.get("away_ploeg_id") if own_home else fx.get("home_ploeg_id")),
        "name": (fx.get("away_name") if own_home else fx.get("home_name")) or "tegenploeg",
        "date_text": fx.get("date_text") or enc_date_text,
        "own_home": own_home,
    }


def opponent_player_rows(pred_boards: list, fmt_val, fmt_date, kind_labels: dict) -> List[dict]:
    """Eén rij per tegenstander-speler uit de voorspelde matchen van deze ontmoeting (gesorteerd op padelstat, hoogste eerst).
    `pred_boards` = predict_board()-resultaten met "their_detail", "opp1_name"/"opp2_name"/"opp?_ranking" en "actual_won"
    (vanuit ONS standpunt; de tegenstander won dus als actual_won False is)."""
    spelers: Dict[str, dict] = {}
    for bp in pred_boards or []:
        details = bp.get("their_detail") or []
        for idx in (0, 1):
            naam = bp.get(f"opp{idx + 1}_name") or "?"
            uid = bp.get(f"opp{idx + 1}_user_id")
            sleutel = str(uid) if uid else f"n:{_norm(naam)}"
            detail = details[idx] if idx < len(details) else {}
            e = spelers.setdefault(sleutel, {
                "naam": naam, "klassement": bp.get(f"opp{idx + 1}_ranking") or "?", "detail": detail,
                "matchen": 0, "gewonnen": 0, "onbekend": 0,
            })
            e["matchen"] += 1
            won = bp.get("actual_won")
            if won is None:
                e["onbekend"] += 1
            elif won is False:
                e["gewonnen"] += 1
            if not e["detail"] and detail:
                e["detail"] = detail
    rijen = []
    for e in spelers.values():
        d = e["detail"] or {}
        rijen.append({
            "Speler": e["naam"],
            "Klassement (toen)": e["klassement"],
            "Padelstat": fmt_val(d) if d else "?",
            "Gemeten op": fmt_date(d.get("as_of")) if d.get("as_of") else "-",
            "Soort": kind_labels.get(d.get("kind"), d.get("kind") or "?") if d else "?",
            "Matchen": e["matchen"],
            "Gewonnen": e["gewonnen"] if not e["onbekend"] else "?",
            "_sort": d.get("value") if d.get("value") is not None else -1.0,
        })
    rijen.sort(key=lambda r: -r["_sort"])
    for r in rijen:
        r.pop("_sort")
    return rijen


def _context(sel_player_id, sel_naam):
    """(fixtures, own_ploeg_id) uit de sessie, anders uit de opgeslagen gegevens (zelfde bron als de sectie Rangschikking)."""
    fx_key = f"vm_fixtures_{sel_player_id}"
    own_key = f"vm_own_ploeg_id_{sel_player_id}"
    fixtures = st.session_state.get(fx_key) or []
    own = st.session_state.get(own_key)
    if not fixtures or not own:
        try:
            from lineup_scout import _known_ranking_context
            _url, known_fx, known_own = _known_ranking_context(str(sel_player_id), sel_naam)
            if known_fx and not st.session_state.get(fx_key):
                st.session_state[fx_key] = known_fx
            if known_own and not st.session_state.get(own_key):
                st.session_state[own_key] = known_own
            fixtures = st.session_state.get(fx_key) or []
            own = st.session_state.get(own_key)
        except Exception:  # noqa: BLE001
            pass
    return fixtures, own


def _saved_report(ploeg_id: str):
    """Het opgeslagen teamrapport van deze ploeg (1 lezing per sessie), of None."""
    key = f"retro_opp_report_{ploeg_id}"
    if key not in st.session_state:
        rapport = None
        try:
            from dashboard_common import oa
            laad = getattr(oa, "_load_report", None)
            rapport = laad(ploeg_id) if callable(laad) else None
        except Exception:  # noqa: BLE001
            rapport = None
        st.session_state[key] = rapport
    return st.session_state[key]


def render_opponent_section(sel_player_id, sel_naam, enc_key, pred_boards, name_lookup, profiles) -> None:
    """Toont de tegenploeg van de gekozen ontmoeting. `enc_key` = (datum-tekst, ontmoeting-tekst)."""
    import lineup_retrospective as lr
    fixtures, own_ploeg_id = _context(str(sel_player_id), sel_naam)
    team = find_opponent_team(fixtures, own_ploeg_id, enc_key[0], enc_key[1])
    st.divider()
    st.markdown("#### Tegenploeg" + (f": {team['name']}" if team else ""))
    rijen = opponent_player_rows(pred_boards, lr._fmt_val, lr._fmt_date, lr._KIND_LABELS)
    if rijen:
        st.dataframe(rijen, use_container_width=True, hide_index=True)
        st.caption(
            "Tegenstanders uit de gekende matchen van deze ontmoeting, met de padelstat die voor de wedstrijd gebruikt werd "
            "(\u2248 = benadering, zie 'Op basis van welke waarden?' bij elke match). Ontbreken er matchen, dan ontbreken ook "
            "hun spelers hier."
        )
    else:
        st.caption("Geen tegenstanders gekend voor deze ontmoeting.")
    if team is None:
        st.caption(
            "De tegenploeg kon niet bepaald worden uit het opgeslagen poule-schema (nog niet geladen of geen ontmoeting op "
            "deze datum). Open eerst de sectie 'Rangschikking' of 'Analyseren' voor deze speler."
        )
        return
    rapport = _saved_report(team["ploeg_id"])
    if rapport and (rapport.get("players") or []):
        with st.expander(f"Teamoverzicht van {team['name']} (zoals bij Analyse)", expanded=True):
            try:
                from dashboard_common import oa
                oa.render_overview_tab(rapport)
                bijgewerkt = rapport.get("updated_at")
                st.caption(
                    "Dit overzicht komt uit je laatste analyse van deze ploeg"
                    + (f" (berekend op {lr._fmt_date(bijgewerkt)})" if bijgewerkt else "")
                    + " en kan dus nieuwere waarden bevatten dan op de wedstrijddag - de tabel hierboven toont de waarden "
                    "van de wedstrijddag zelf."
                )
            except Exception as exc:  # noqa: BLE001
                st.caption(f"Het teamoverzicht kon niet getoond worden: {type(exc).__name__}: {exc}")
    else:
        st.caption(
            f"Geen opgeslagen teamoverzicht voor {team['name']} - dat verschijnt zodra je die ploeg bij 'Analyseren' hebt geanalyseerd."
        )
    toon = st.checkbox(
        f"Toon de vorige ontmoetingen van {team['name']} (zoals bij Analyse)",
        key=f"retro_opp_prev_show_{sel_player_id}_{team['ploeg_id']}_{date_iso(team['date_text'])}",
        help="Haalt de eerdere ontmoetingen van deze ploeg op (v\u00f3\u00f3r deze datum). Kan even duren.",
    )
    if not toon:
        return
    bundle_key = f"retro_opp_prev_bundle_{sel_player_id}_{team['ploeg_id']}_{date_iso(team['date_text'])}"
    if bundle_key not in st.session_state:
        try:
            from lineup_scout import _scout_team_all_fixtures
            with st.spinner("Vorige ontmoetingen ophalen..."):
                st.session_state[bundle_key] = _scout_team_all_fixtures(
                    fixtures, team["ploeg_id"], team["name"], team["date_text"],
                ) or {}
        except Exception as exc:  # noqa: BLE001
            st.caption(f"De vorige ontmoetingen konden niet opgehaald worden: {type(exc).__name__}: {exc}")
            return
    volledig = st.session_state.get(bundle_key) or {}
    if not volledig.get("previous_fixtures"):
        st.caption("Geen eerdere ontmoetingen van deze ploeg gevonden v\u00f3\u00f3r deze datum.")
        return
    try:
        from lineup_opponent_history import _render_previous_opponent_lineup
        _render_previous_opponent_lineup(
            {}, opp={"ploeg_id": team["ploeg_id"], "name": team["name"]}, full_bundle=volledig,
        )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"De vorige ontmoetingen konden niet getoond worden: {type(exc).__name__}: {exc}")
