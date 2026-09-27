"""
lineup_rules.py - Reglement/afdeling-selector voor de Opstelling-analyse.

Opgesplitst uit page_lineup_lab.py (PADEL_ANALYSIS_MODULE_SPLIT_2026-09-27,
op verzoek van Kim: "dit is een groot bestand dus mss best om het eerst op
te splitsen in meerdere kleinere [...] zal aanpassingen in de toekomst
sneller maken"). Zie page_lineup_lab.py voor de volledige historische
toelichting bij elke fix - deze module bevat enkel de reglement-selector,
functioneel ONGEWIJZIGD t.o.v. de vorige, monolithische versie.
"""
import streamlit as st
from dashboard_common import fb

try:
    import tournament_rules as tr
except Exception:  # noqa: BLE001  pragma: no cover
    tr = None


# PADEL_ANALYSIS_SPEED_AUDIT_ROUND4_2026-09-26: doet 1 Firestore-read
# (get_player_profile), zonder cache. Aangeroepen vanuit
# _render_tournament_rules_selector(), die ONVOORWAARDELIJK aangeroepen
# wordt in _render_opstelling_scenario() - dus bij elke rerun.
@st.cache_data(ttl=300, show_spinner=False)
def _load_saved_rules_selection(sel_player_id: str, ploeg_id: str) -> dict:
    try:
        profile = fb.get_player_profile(sel_player_id) or {}
    except Exception:
        profile = {}
    by_team = profile.get("lineup_rules_selection_by_team") or {}
    if str(ploeg_id) in by_team:
        return by_team.get(str(ploeg_id)) or {}
    return profile.get("lineup_rules_selection") or {}


def _save_rules_selection(sel_player_id: str, ploeg_id: str, tournament: str, category: str, afdeling) -> None:
    try:
        fb.db.collection(fb.PLAYER_PROFILES_COLLECTION).document(str(sel_player_id)).set(
            {"lineup_rules_selection_by_team": {
                str(ploeg_id): {"tournament": tournament, "category": category, "afdeling": afdeling},
            }},
            merge=True,
        )
    except Exception:
        pass


def _render_tournament_rules_selector(ploeg_id: str, sel_player_id: str, available_official_ranks: list = None):
    if tr is None:
        st.caption("tournament_rules.py niet gevonden - reglement-gebaseerde puntenfilter niet beschikbaar.")
        return None, None
    saved = _load_saved_rules_selection(sel_player_id, ploeg_id)
    with st.expander("Reglement / afdeling (bepaalt de toegelaten puntengrenzen per rotatie)", expanded=False):
        tournaments = tr.list_tournaments()
        default_tournament = saved.get("tournament") if saved.get("tournament") in tournaments else tr.DEFAULT_TOURNAMENT
        default_tournament_idx = tournaments.index(default_tournament) if default_tournament in tournaments else 0
        tournament = st.selectbox(
            "Tornooi", tournaments, index=default_tournament_idx, key=f"rules_tournament_{ploeg_id}",
            help="Vandaag enkel Padel Senior Cup volledig ingevuld.",
        )
        categories = tr.list_categories(tournament)
        if not categories:
            st.warning(f"Nog geen categorieen ingevuld voor '{tournament}'.")
            return None, None
        default_category = saved.get("category") if saved.get("category") in categories else tr.DEFAULT_CATEGORY
        default_cat_idx = categories.index(default_category) if default_category in categories else 0
        category = st.selectbox("Categorie", categories, index=default_cat_idx, key=f"rules_category_{ploeg_id}")
        afdelingen = tr.list_afdelingen(tournament, category)
        if not afdelingen:
            st.warning(f"Nog geen afdelingen ingevuld voor '{tournament}' / {category}.")
            return None, None
        suggested_afdeling, suggestion_exact = (None, False)
        if available_official_ranks:
            suggested_afdeling, suggestion_exact = tr.suggest_afdeling(tournament, category, available_official_ranks)

        def _afdeling_label(a):
            base = tr.format_afdeling_label(tournament, category, a)
            if a == suggested_afdeling:
                tag = "aanbevolen o.b.v. team" if suggestion_exact else "dichtste match o.b.v. team, niet perfect"
                base += f"  * ({tag})"
            return base

        default_afdeling = saved.get("afdeling") if saved.get("afdeling") in afdelingen else None
        if default_afdeling is None and suggested_afdeling in afdelingen:
            default_afdeling = suggested_afdeling
        default_afd_idx = afdelingen.index(default_afdeling) if default_afdeling in afdelingen else 0
        afdeling = st.selectbox(
            "Afdeling", afdelingen, index=default_afd_idx, key=f"rules_afdeling_{ploeg_id}",
            format_func=_afdeling_label,
            help="* = automatisch voorgesteld op basis van het officiele klassement van de geselecteerde "
                 "eigen spelers - je kan dit hieronder altijd manueel overschrijven.",
        )
        rules = tr.get_afdeling_rules(tournament, category, afdeling)
        st.caption(tr.format_rules_caption(tournament, category, afdeling, rules))
        if suggested_afdeling is not None and afdeling != suggested_afdeling:
            st.caption(
                f"Let op: dit wijkt af van de automatische suggestie (afdeling {suggested_afdeling} "
                f"o.b.v. de geselecteerde spelers). Dat kan bewust zijn (ploeg speelt in een andere "
                "afdeling dan het klassement zou suggereren)."
            )
        elif suggested_afdeling is not None and not suggestion_exact:
            st.warning(
                f"Geen enkele afdeling dekt het officiele klassement van ALLE geselecteerde spelers "
                f"perfect - afdeling {suggested_afdeling} is de dichtste benadering. Controleer de "
                "teamsamenstelling of kies manueel een andere afdeling."
            )
        with st.expander("Volledige reglementstabel (alle afdelingen)", expanded=False):
            st.markdown(tr.format_full_rules_table_markdown(tournament, category))
        if saved.get("tournament") != tournament or saved.get("category") != category or saved.get("afdeling") != afdeling:
            _save_rules_selection(sel_player_id, ploeg_id, tournament, category, afdeling)
        return rules, f"{tournament} - {category}, afdeling {afdeling}"
