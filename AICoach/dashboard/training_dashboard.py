# -*- coding: utf-8 -*-
from pathlib import Path
import sys
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from AICoach.chat.ai_message_handler import handle_message
from AICoach.context_builder import build_context
from AICoach.dashboard.activities_tab import render_activities
from AICoach.dashboard.best_results_tab import render_best_results
from AICoach.dashboard.charts import render_time_chart, selected_date_from_event
from AICoach.dashboard.comparison_tab import render_comparison_tab
from AICoach.dashboard.daily_update import render_daily_update
from AICoach.dashboard.data_loaders import load_history
from AICoach.dashboard.knowledge_tab import render_knowledge
from AICoach.dashboard.recovery_tab import render_recovery
from AICoach.dashboard.ui_helpers import (
    has_data,
    nearest_row,
    render_assistant_answer,
    render_selected_values,
)
from AICoach.persistent_data import mirror_history_to_local
from AICoach.saved_insights import render_saved_insights, save_insight


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.2rem;
            padding-top: 0.65rem;
            padding-bottom: 0.15rem;
            overflow-x: auto;
            overflow-y: visible;
        }
        .stTabs [data-baseweb="tab"] {
            height: auto;
            min-height: 3rem;
            padding: 0.72rem 0.85rem;
            white-space: nowrap;
        }
        .stTabs [data-baseweb="tab"] p {
            line-height: 1.25;
            margin: 0;
            overflow: visible;
        }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 0.65rem;
            padding: 0.65rem;
        }
        @media (max-width: 700px) {
            .block-container {
                padding-left: 0.55rem;
                padding-right: 0.55rem;
                padding-top: 0.8rem;
            }
            .stTabs [data-baseweb="tab"] {
                padding-left: 0.6rem;
                padding-right: 0.6rem;
                font-size: 0.88rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# MATCHFITAI_DROP_LIVE_SYNC_FROM_APP_2026-09-14 (op verzoek van Kim, na twee
# eerdere pogingen die het probleem niet oplosten - zie hieronder voor de
# volledige voorgeschiedenis):
#
# VOORGESCHIEDENIS:
# v1 (MATCHFITAI_NONBLOCKING_STARTUP_SYNC): ensure_latest_data() riep
# sync_latest_data() SYNCHROON aan bij elke koude start, wat de eerste render
# blokkeerde tot de volledige intervals.icu-sync klaar was (traag).
# v2 (MATCHFITAI_AUTOSTART_FIRST_SYNC): sync verplaatst naar een
# achtergrond-thread, met een begrensde wacht-lus als er nog geen lokale data
# was. Op Streamlit Community Cloud bleek dit ONBETROUWBAAR: Kim zag de
# spinner wel, maar nadien alsnog geen data - zelfs niet na een handmatige
# "Nu verversen"-klik.
#
# v3 (dit blok): de Streamlit-app doet ZELF NOOIT MEER een live
# intervals.icu-aanroep. Een APARTE, uur-gebaseerde GitHub Actions-workflow
# (.github/workflows/sync-mAIcoach.yml) doet de eigenlijke sync en schrijft
# naar GCS/Firestore. De app doet enkel nog een GOEDKOPE GCS-LEESoperatie
# (mirror_history_to_local()) om de laatst gesynchroniseerde data terug te
# spiegelen naar lokale bestanden.
#
# MATCHFITAI_CACHE_MIRROR_HISTORY_2026-09-14 (kritieke bugfix op v3):
# BUG (opgelost, gemeld door Kim): "gewoon iets switchen van pagina duurt
# terug lang laden" - ook binnen een AL ACTIEVE sessie (dus GEEN koude
# start/library-installatie, die hypothese werd expliciet uitgesloten omdat
# PadelAnalysis in dezelfde container wel steeds snel bleef). Oorzaak:
# mirror_history_to_local() had GEEN caching (bevestigd via
# `Select-String -Pattern "cache_data|cache_resource"` op
# AICoach/persistent_data.py - geen enkele treffer boven de functie). Ze werd
# hierdoor bij ELKE Streamlit-rerun opnieuw aangeroepen - dus bij elke
# tab-klik, elke interactie, elke keer dat de pagina opnieuw uitvoert - en
# deed dan telkens opnieuw een volledige GCS-netwerklezing (lokaal gemeten
# op ~1.15s; op Streamlit Cloud kennelijk merkbaar trager door hogere
# netwerklatentie tussen de cloud-regio en de GCS-opslag).
# Fix: de aanroep is nu gewrapt in _refresh_local_history_from_storage(),
# met een EIGEN, HANDMATIGE tijd-gebaseerde cache via st.session_state (geen
# st.cache_data-decorator op mirror_history_to_local() zelf, want die
# functie heeft neveneffecten - ze schrijft lokale bestanden weg - en
# st.cache_data is primair bedoeld voor functies die een waarde
# TERUGGEVEN op basis van hun argumenten, niet voor side-effect-only
# operaties). De GCS-lezing gebeurt zo nog maximaal 1x per
# _MIRROR_CACHE_SECONDS (5 minuten) per sessie, in plaats van bij elke
# rerun - ruim vers genoeg, aangezien de onderliggende data toch maar 1x
# per uur verandert (dankzij de nieuwe sync-workflow).
# --------------------------------------------------------------------------- #
_MIRROR_CACHE_SECONDS = 300  # 5 minuten - ruim vers genoeg t.o.v. de 1x/uur-sync-workflow


def _refresh_local_history_from_storage() -> None:
    """Spiegelt de laatst gesynchroniseerde geschiedenis van GCS/Firestore
    terug naar lokale bestanden. GEEN intervals.icu-aanroep - enkel een
    lezing van reeds bestaande, door de uur-gebaseerde GitHub Actions-
    workflow bijgewerkte opslag.

    MATCHFITAI_CACHE_MIRROR_HISTORY_2026-09-14: doet dit nu maximaal 1x per
    _MIRROR_CACHE_SECONDS per sessie (via een tijdstempel in
    st.session_state), in plaats van bij ELKE rerun - dat verklaarde de
    trage paginawissels op de cloud. Faalt de lezing om welke reden dan ook
    (bv. GCS niet bereikbaar), dan wordt dat opgevangen en blijft de app
    gewoon de reeds lokaal aanwezige data tonen - nooit een crash op deze
    stap, en de volgende poging gebeurt gewoon bij het verstrijken van de
    cache-termijn."""
    import time
    last_refreshed = st.session_state.get("_history_mirror_last_refreshed_at")
    now = time.monotonic()
    if last_refreshed is not None and now - last_refreshed < _MIRROR_CACHE_SECONDS:
        return
    try:
        mirror_history_to_local()
    except Exception as exc:  # noqa: BLE001
        st.session_state["history_refresh_error"] = str(exc)
    else:
        st.session_state.pop("history_refresh_error", None)
    st.session_state["_history_mirror_last_refreshed_at"] = now


def render_dashboard():
    df = load_history()
    context = build_context()
    render_daily_update()
    st.divider()
    if df.empty:
        st.warning("Geen trainingshistoriek gevonden.")
        return
    st.caption(
        f"Hersteldata: {context.get('current_date') or 'onbekend'} | "
        f"Trainingsstatus: {context.get('latest_training_status_date') or 'onbekend'}"
    )
    period_options = {"30 dagen": 30, "90 dagen": 90, "Dit jaar": 366, "Alles": len(df)}
    selected_period = st.selectbox("Periode", list(period_options), index=2, key="dashboard_period")
    view = df.tail(period_options[selected_period]).copy()
    latest_date = view["date"].max() if not view.empty else None
    selected_date = st.session_state.get("dashboard_selected_date")
    if selected_date is None:
        selected_date = latest_date
        st.session_state.dashboard_selected_date = latest_date
    selected_row = nearest_row(view, selected_date)
    render_selected_values(selected_row, ["fitness", "fatigue", "form", "training_load", "resting_hr"])
    event = render_time_chart(
        view,
        ["fitness", "fatigue", "form"],
        key="dashboard_fitness_chart",
        selected_date=selected_date,
        title="Fitness, Fatigue en Form",
        default_granularity="Dag",
    )
    event_date = selected_date_from_event(event)
    if event_date is not None and event_date != selected_date:
        st.session_state.dashboard_selected_date = event_date
        st.rerun()
    if has_data(view, "training_load"):
        render_time_chart(
            view,
            ["training_load"],
            key="dashboard_load_chart",
            selected_date=selected_date,
            title="Training load",
            default_granularity="Maand",
        )


def render_chat():
    st.subheader("mAICoach")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    _, clear_column = st.columns([8, 2])
    with clear_column:
        if st.button("Gesprek wissen", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
    for index, message in enumerate(st.session_state.chat_history):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_assistant_answer(message["content"])
                if st.button("Bewaar dit inzicht", key=f"save_chat_insight_{index}"):
                    save_insight(message["content"], source="AI Coach")
                    st.success("Inzicht bewaard bij je kennis.")
            else:
                st.markdown(message["content"])
    question = st.chat_input("Stel een vraag over je training, herstel of prestaties...")
    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("mAICoach analyseert je gegevens..."):
                answer = handle_message(question)
            render_assistant_answer(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()


def render_health_app() -> None:
    """Bouwt de volledige mAICoach-pagina (titel, data-verversing, tabs).
    Dit is de ENIGE plek waar de UI-structuur van de gezondheidsmodule wordt
    opgebouwd. Zowel de standalone uitvoering (streamlit run
    training_dashboard.py) als de gecombineerde app (via
    AICoach/dashboard/app.py -> health_page.py) roepen exact deze functie aan.
    MATCHFITAI_DROP_LIVE_SYNC_FROM_APP_2026-09-14: geen live intervals.icu-
    sync meer binnen de app zelf. De verse data komt van een aparte,
    uur-gebaseerde GitHub Actions-workflow.
    MATCHFITAI_CACHE_MIRROR_HISTORY_2026-09-14: de GCS-spiegeling gebeurt nu
    maximaal 1x per 5 minuten per sessie (zie
    _refresh_local_history_from_storage hierboven), zodat paginawisselen
    binnen een actieve sessie niet telkens een nieuwe, trage GCS-lezing
    triggert."""
    try:
        st.set_page_config(page_title="mAICoach", page_icon="🏃", layout="wide")
    except Exception:
        pass
    _inject_css()
    st.title("🏃 mAICoach")
    _refresh_local_history_from_storage()
    context = build_context()
    st.caption(
        f"Actuele wellness: {context.get('current_date') or 'onbekend'} | "
        f"Laatste activiteit: {context.get('latest_activity', {}).get('date') or 'onbekend'}"
    )
    st.caption(
        "Gegevens worden elk uur automatisch bijgewerkt op de achtergrond "
        "(via GitHub Actions) - hier steeds de laatst beschikbare synchronisatie."
    )
    if st.session_state.get("history_refresh_error"):
        with st.expander("⚠️ Kon de opslag niet verversen (details)"):
            st.code(st.session_state["history_refresh_error"])
    with st.expander("Gegevens verversen"):
        st.caption(
            "Haalt de laatst door de uur-gebaseerde achtergrondtaak gesynchroniseerde "
            "gegevens opnieuw op uit de opslag (geen live intervals.icu-aanroep hier)."
        )
        if st.button("Nu verversen"):
            st.cache_resource.clear()
            st.cache_data.clear()
            st.session_state.pop("dashboard_selected_date", None)
            # MATCHFITAI_CACHE_MIRROR_HISTORY_2026-09-14: forceert een
            # nieuwe GCS-lezing bij de eerstvolgende render, ook al is de
            # 5-minuten-cache-termijn nog niet verstreken.
            st.session_state.pop("_history_mirror_last_refreshed_at", None)
            st.rerun()
    tab_labels = ["Dashboard", "AI Coach", "Recovery", "Athlete Knowledge", "Beste resultaten", "Activiteiten"]
    comparison_active = bool(st.session_state.get("comparison_active"))
    if comparison_active:
        tab_labels.append("Vergelijking")
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        render_dashboard()
    with tabs[1]:
        render_chat()
    with tabs[2]:
        render_recovery()
    with tabs[3]:
        render_knowledge()
        st.divider()
        render_saved_insights()
    with tabs[4]:
        render_best_results()
    with tabs[5]:
        render_activities()
    if comparison_active:
        with tabs[6]:
            render_comparison_tab()


# Bouwt de pagina ALLEEN op wanneer dit bestand rechtstreeks wordt uitgevoerd
# (bv. `streamlit run AICoach/dashboard/training_dashboard.py`). Bij een
# `import` vanuit app.py (de gecombineerde app) blijft __name__ gelijk aan de
# modulenaam, niet "__main__", waardoor dit blok dan correct wordt
# overgeslagen en render_health_app() niet ongewild al bij import draait.
if __name__ == "__main__":
    render_health_app()
