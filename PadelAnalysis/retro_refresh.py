"""
retro_refresh.py - Nabeschouwing: ontbrekende matchen opsporen en de juiste spelers bijwerken.
--------------------------------------------------------------------------
PADEL_ANALYSIS_RETRO_REFRESH_2026-10-11 (op verzoek van Kim: "bij de nabeschouwing zag ik nu maar 1 match van de 4 [...]
ik had nochtans verversen schema gedaan. Mss moet er ergens een apart ververs knop bij nabeschouwing staan om specifiek
enkel die data te verversen?")
--------------------------------------------------------------------------
De knop "Schema nu verversen" werkt enkel voor de geselecteerde speler. Bij een lopende ontmoeting (bv. enkel rotatie 1
gespeeld) staat de andere match van die rotatie in de gegevens van twee ploeggenoten die niet met de geselecteerde speler
(of zijn partner) samenspeelden - hun profiel wordt dan nergens vernieuwd.
Deze module:
  1. compute_and_store(): bepaalt, met de al geladen documenten, het ploeg-roster en wie voor DEZE ontmoeting verouderd is
     (teammate_sync.roster_info_for_encounter) en bewaart dat in st.session_state;
  2. render_refresh_block(): toont wat er ontbreekt en wie bijgewerkt moet worden, met een knop "Teamgenoten bijwerken"
     (start de bestaande achtergrondtaak voor precies die spelers) en een knop "Gegevens opnieuw laden" die de gecachete
     gegevens wist zodat de nieuwe matchen verschijnen.
De zichtbare tekst vermijdt technisch jargon. De rekenlogica staat in teammate_sync.py (los te testen).
"""
import streamlit as st
import teammate_sync as ts

try:
    import cloud_helpers as ch
except Exception:  # noqa: BLE001  pragma: no cover
    ch = None

_INFO_PREFIX = "retro_refresh_info_"
_CACHE_PREFIXES = ("retro_teammates_cache_", "retro_teammates_debug_", _INFO_PREFIX)


def info_key(sel_player_id, enc_key) -> str:
    return f"{_INFO_PREFIX}{sel_player_id}_{enc_key}"


def compute_and_store(sel_player_id, enc_key, sel_doc, other_docs, profile_ids) -> dict:
    """Berekent en bewaart de ploeg-roster-info voor deze ontmoeting. Faalt nooit hard (geeft {"error": ...})."""
    sel_player_id = str(sel_player_id)
    docs = {str(k): v for k, v in (other_docs or {}).items()}
    docs[sel_player_id] = sel_doc or {}
    try:
        info = ts.roster_info_for_encounter(sel_player_id, enc_key, docs, profile_ids)
    except Exception as exc:  # noqa: BLE001
        info = {"error": f"{type(exc).__name__}: {exc}"}
    st.session_state[info_key(sel_player_id, enc_key)] = info
    return info


def clear_caches() -> None:
    """Wist de gecachete teamgenoten-gegevens zodat een verse lezing uit de database gebeurt."""
    for k in [k for k in list(st.session_state) if str(k).startswith(_CACHE_PREFIXES)]:
        st.session_state.pop(k, None)
    cleared = False
    try:
        import lineup_lab as ll
        fn = getattr(ll, "get_docs_for_players", None)
        if fn is not None and hasattr(fn, "clear"):
            fn.clear()
            cleared = True
    except Exception:  # noqa: BLE001
        pass
    try:
        from lineup_scout import _load_encounter_index
        _load_encounter_index.clear()
    except Exception:  # noqa: BLE001
        pass
    if not cleared:
        try:
            st.cache_data.clear()
        except Exception:  # noqa: BLE001
            pass


def _namen(ids, name_lookup) -> str:
    return ", ".join(name_lookup.get(str(p), str(p)) for p in ids)


def _body(sel_player_id, sel_naam, enc_key, name_lookup, info, odd: bool, n_known: int) -> None:
    sel_player_id = str(sel_player_id)
    kp = f"retro_refresh_{sel_player_id}_{abs(hash(enc_key)) % 10**8}"
    stale = list(info.get("stale") or []) if info and not info.get("error") else []
    geen_profiel = list(info.get("no_profile") or []) if info and not info.get("error") else []
    rest = list(info.get("have") or []) + list(info.get("fresh_without") or []) if info and not info.get("error") else []
    if info and info.get("error"):
        st.caption(f"De teamgenoten konden niet bepaald worden ({info['error']}). Alleen {sel_naam} kan bijgewerkt worden.")
    if stale:
        st.markdown(
            "Deze teamgenoten zijn niet meer bijgewerkt sinds deze ontmoeting en hebben ze (nog) niet in hun gegevens: "
            f"**{_namen(stale, name_lookup)}**."
        )
    elif odd:
        st.markdown(
            "Alle bekende teamgenoten zijn bijgewerkt na deze ontmoeting, of we weten niet wie de ontbrekende speler(s) zijn. "
            "Een vernieuwing van het hele team kan helpen."
        )
    else:
        st.caption(
            "Alle bekende teamgenoten staan al in de gegevens van deze ontmoeting. Speelde iemand mee die ontbreekt, "
            "dan kan je het hele team opnieuw laten bijwerken."
        )
    if geen_profiel:
        st.caption(
            f"Geen profiel gekend voor: {_namen(geen_profiel, name_lookup)} - die kunnen hier niet bijgewerkt worden; "
            "voeg ze toe via 'Speler toevoegen'."
        )
    st.caption(
        "De knop 'Schema nu verversen' werkt enkel voor de geselecteerde speler. Hier worden precies de spelers bijgewerkt "
        "die voor deze ontmoeting ontbreken."
    )
    alles = False
    if rest:
        alles = st.checkbox(
            f"Ook de andere teamgenoten bijwerken ({_namen(rest, name_lookup)}) - duurt langer", value=False,
            key=f"{kp}_all",
        )
    ids = [sel_player_id] + [p for p in stale if p != sel_player_id]
    if alles:
        ids += [p for p in rest if p not in ids]
    cols = st.columns([2, 2])
    with cols[0]:
        if ch is not None and ch.is_github_trigger_configured():
            ch.render_cloud_scrape_trigger(
                key_prefix=kp, player_ids=",".join(ids), mode="missing", label="🔄 Teamgenoten bijwerken",
                help_text=f"Werkt de matchgegevens bij van: {_namen(ids, name_lookup)}.",
            )
        else:
            st.info(
                "Bijwerken vanuit deze pagina is niet beschikbaar. Werk deze spelers handmatig bij (speler-id's): "
            )
            st.code(",".join(ids))
    with cols[1]:
        if st.button("Gegevens opnieuw laden", key=f"{kp}_reload",
                     help="Doe dit nadat het bijwerken klaar is, zodat de nieuwe matchen verschijnen."):
            clear_caches()
            st.rerun()


def render_refresh_block(sel_player_id, sel_naam, enc_key, name_lookup, n_known_boards: int) -> None:
    """Toont het blok 'matchen bijwerken'. Staat open met een waarschuwing als er matchen ontbreken (oneven of minder dan 2
    gekende matchen), anders ingeklapt."""
    info = st.session_state.get(info_key(sel_player_id, enc_key))
    odd = n_known_boards < 2 or n_known_boards % 2 != 0
    if odd:
        with st.container(border=True):
            st.markdown(f"**Er ontbreekt minstens 1 match van deze ontmoeting** (we kennen er {n_known_boards}).")
            _body(sel_player_id, sel_naam, enc_key, name_lookup, info, True, n_known_boards)
    else:
        with st.expander("Ontbreekt er een match? Teamgenoten bijwerken", expanded=False):
            _body(sel_player_id, sel_naam, enc_key, name_lookup, info, False, n_known_boards)
