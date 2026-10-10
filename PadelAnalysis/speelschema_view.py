"""
speelschema_view.py - Speelschema van een ploeg uit de poule (sectie
"Rangschikking" in page_lineup_lab.py).
--------------------------------------------------------------------------
PADEL_ANALYSIS_SCHEDULE_DETAILS_LINK_2026-10-10 (op verzoek van Kim: "bij
speelschema wil ik via een hyperlink naar de details van die match kunnen
springen. Je ging ook duidelijk scores thuis uit geven. Dus duidelijk tonen wie
er gewonnen is. Als de geselecteerde ploeg gewonnen is dan groen en anders
rood.")
--------------------------------------------------------------------------
Opgesplitst uit page_lineup_lab.py zodat de weergave los te testen is
(test_speelschema_en_koppels.py). Bron: het opgeslagen poule-schema (de lijst
fixtures die page_lineup_lab.py al in st.session_state bewaart). Per ontmoeting
bevat dat o.a. home/away_name, home/away_ploeg_id, date_text, played, score en
uitslagenblad_url (bv. "/interclub-uitslagenblad?spelgroepId=...&matchId=...").
SCOREVELD: "matchen / sets / games", telkens thuis - uit, bv.
"1-3 / 3-7 / 41-59". Die richting is bevestigd (fixture_uitslag_rapport.txt:
4 van 4 gespeelde ontmoetingen kloppen met de eigen gewonnen/verloren matchen,
en de stand uit de uitslagen klopt exact met de punten van TVL).
KLEUREN (gezien vanuit de GEKOZEN ploeg): groen = gewonnen, rood = verloren.
Een gelijkspel (2-2) is geen verlies en krijgt daarom een eigen kleur (oranje).
Een link naar de details staat enkel bij GESPEELDE ontmoetingen: een nog te
spelen ontmoeting heeft nog geen uitslagenblad om naar te springen.
"""
import re
import streamlit as st

TVL_BASE = "https://www.tennisenpadelvlaanderen.be"
_DATE_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:\D+(\d{1,2}):(\d{2}))?")
_SEG_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_KLEUR = {
    "gewonnen": "background-color: #d4edda",
    "verloren": "background-color: #f8d7da",
    "gelijk": "background-color: #fff3cd",
}
KOLOMMEN_GESPEELD = ["Datum", "Thuis", "Matchen", "Uit", "Winnaar", "Sets", "Games", "Details"]
KOLOMMEN_TE_SPELEN = ["Datum", "Thuis", "Uit"]


def sort_key(fx: dict) -> tuple:
    """Sorteersleutel (jaar, maand, dag, uur, minuut) uit date_text
    (bv. "11/10/2026 09:30"). Onleesbare datums komen achteraan."""
    m = _DATE_RE.search(str(fx.get("date_text") or ""))
    if not m:
        return (9999, 12, 31, 23, 59)
    d, mo, y, hh, mi = m.groups()
    return (int(y), int(mo), int(d), int(hh or 0), int(mi or 0))


def detail_url(fx: dict):
    """Volledige URL naar het uitslagenblad van deze ontmoeting, of None."""
    u = fx.get("uitslagenblad_url")
    if not u:
        return None
    u = str(u).strip()
    return u if u.startswith("http") else TVL_BASE + (u if u.startswith("/") else "/" + u)


def parse_uitslag(score_text):
    """"1-3 / 3-7 / 41-59" -> {"matches": (1, 3), "sets": (3, 7), "games": (41, 59)}
    (thuis - uit). Onleesbaar -> None (nooit een gok). Enkel "3-1" mag ook; sets
    en games zijn dan None."""
    if not score_text:
        return None
    segs = str(score_text).split("/")
    vals = []
    for s in segs:
        m = _SEG_RE.match(s)
        if not m:
            return None
        vals.append((int(m.group(1)), int(m.group(2))))
    return {
        "matches": vals[0],
        "sets": vals[1] if len(vals) > 1 else None,
        "games": vals[2] if len(vals) > 2 else None,
    }


def uitkomst_voor(fx: dict, team_id: str):
    """"gewonnen" / "verloren" / "gelijk" vanuit de gekozen ploeg, of None."""
    u = parse_uitslag(fx.get("score"))
    if u is None:
        return None
    mh, ma = u["matches"]
    if mh == ma:
        return "gelijk"
    thuis = str(fx.get("home_ploeg_id")) == str(team_id)
    gewonnen = (mh > ma) if thuis else (ma > mh)
    return "gewonnen" if gewonnen else "verloren"


def winnaar_naam(fx: dict) -> str:
    u = parse_uitslag(fx.get("score"))
    if u is None:
        return "-"
    mh, ma = u["matches"]
    if mh == ma:
        return "Gelijkspel"
    return (fx.get("home_name") if mh > ma else fx.get("away_name")) or "?"


def _paar(pair) -> str:
    return f"{pair[0]} - {pair[1]}" if pair else "-"


def rij_gespeeld(fx: dict, team_id: str) -> dict:
    u = parse_uitslag(fx.get("score"))
    return {
        "Datum": fx.get("date_text") or "?",
        "Thuis": fx.get("home_name") or "?",
        "Matchen": _paar(u["matches"]) if u else "-",
        "Uit": fx.get("away_name") or "?",
        "Winnaar": winnaar_naam(fx),
        "Sets": _paar(u["sets"]) if u and u["sets"] else "-",
        "Games": _paar(u["games"]) if u and u["games"] else "-",
        "Details": detail_url(fx),
        "_res": uitkomst_voor(fx, team_id),
    }


def rij_te_spelen(fx: dict) -> dict:
    return {
        "Datum": fx.get("date_text") or "?",
        "Thuis": fx.get("home_name") or "?",
        "Uit": fx.get("away_name") or "?",
    }


def teams_in_schema(fixtures: list) -> dict:
    """{ploeg_id: ploegnaam} van alle ploegen die in het schema voorkomen."""
    teams: dict = {}
    for fx in fixtures or []:
        for kant in ("home", "away"):
            tid, tnaam = fx.get(f"{kant}_ploeg_id"), fx.get(f"{kant}_name")
            if tid and tnaam:
                teams.setdefault(str(tid), tnaam)
    return teams


def _toon_tabel(rows: list, kolommen: list) -> None:
    """Toont de tabel met kleur per rij (enkel als er een '_res' is) en een
    klikbare link in de kolom 'Details'. Valt terug op een gewone tabel."""
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        styled = df.style
        if "_res" in df.columns:
            def _kleur(row):
                css = _KLEUR.get(row.get("_res"), "")
                return [css] * len(row)
            styled = df.style.apply(_kleur, axis=1)
        cfg = {}
        if "Details" in kolommen:
            try:
                cfg["Details"] = st.column_config.LinkColumn("Details", display_text="Bekijk")
            except Exception:  # noqa: BLE001
                cfg["Details"] = st.column_config.LinkColumn("Details")
        st.dataframe(styled, use_container_width=True, hide_index=True,
                     column_order=kolommen, column_config=cfg)
    except Exception:  # noqa: BLE001
        st.dataframe(
            [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
            use_container_width=True, hide_index=True,
        )


def render_speelschema(sel_player_id, saved_schedule_fn=None, format_ts_fn=None) -> None:
    """Speelschema van onze ploeg (standaard) of een andere ploeg uit de poule."""
    st.markdown("#### Speelschema")
    fixtures = st.session_state.get(f"vm_fixtures_{sel_player_id}") or []
    own_ploeg_id = st.session_state.get(f"vm_own_ploeg_id_{sel_player_id}")
    if not fixtures or not own_ploeg_id:
        st.info(
            "Het speelschema is nog niet gekend voor deze speler - dit wordt automatisch aangevuld "
            "zodra het poule-schema bekend is (normaal via de dagelijkse update)."
        )
        return
    own = str(own_ploeg_id)
    teams = teams_in_schema(fixtures)
    keuzes = [own] + sorted((t for t in teams if t != own), key=lambda t: teams[t].lower())
    labels = {t: (f"{teams.get(t, 'Onze ploeg')} (onze ploeg)" if t == own else teams[t]) for t in keuzes}
    team = str(
        st.selectbox(
            "Speelschema van", keuzes, format_func=lambda t: labels.get(t, t),
            key=f"speelschema_team_{sel_player_id}",
        ) if len(keuzes) > 1 else own
    )
    team_naam = teams.get(team, "de gekozen ploeg")
    mijn = [fx for fx in fixtures if team in (str(fx.get("home_ploeg_id")), str(fx.get("away_ploeg_id")))]
    if not mijn:
        st.info("Geen ontmoetingen van deze ploeg gevonden in het poule-schema.")
        return
    mijn.sort(key=sort_key)
    nog = [fx for fx in mijn if not fx.get("played")]
    gespeeld = [fx for fx in mijn if fx.get("played")]
    if nog:
        st.markdown(f"**Nog te spelen ({len(nog)})**")
        _toon_tabel([rij_te_spelen(fx) for fx in nog], KOLOMMEN_TE_SPELEN)
    else:
        st.success("Alle ontmoetingen in deze poule zijn gespeeld.")
    if gespeeld:
        st.markdown(f"**Al gespeeld ({len(gespeeld)})**")
        _toon_tabel([rij_gespeeld(fx, team) for fx in reversed(gespeeld)], KOLOMMEN_GESPEELD)
        st.caption(
            f"Matchen = uitslag thuis - uit. Groen = **{team_naam}** won, rood = verloren, oranje = gelijkspel. "
            "Via 'Bekijk' spring je naar het uitslagenblad van die ontmoeting op de TVL-site."
        )
    sched_at = None
    if saved_schedule_fn is not None:
        try:
            _fx_saved, sched_at = saved_schedule_fn(str(sel_player_id))
        except Exception:  # noqa: BLE001
            sched_at = None
    if sched_at:
        tekst = format_ts_fn(sched_at) if format_ts_fn else str(sched_at)
        st.caption(
            f"Schema laatst bijgewerkt op {tekst}. Een ontmoeting die net gespeeld "
            "is, staat tot de volgende update nog onder 'Nog te spelen'."
        )
