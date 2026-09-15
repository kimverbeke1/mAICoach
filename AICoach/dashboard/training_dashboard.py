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
from AICoach.persistent_data import mirror_all_to_local
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
# DATA-VERVERSING - VOORGESCHIEDENIS EN HUIDIGE AANPAK
#
# v1 (MATCHFITAI_NONBLOCKING_STARTUP_SYNC): ensure_latest_data() riep
# sync_latest_data() SYNCHROON aan bij elke koude start -> blokkeerde de
# eerste render tot de volledige intervals.icu-sync klaar was (traag).
# v2 (MATCHFITAI_AUTOSTART_FIRST_SYNC): sync in een achtergrond-thread, met
# een begrensde wacht-lus. Op Streamlit Community Cloud onbetrouwbaar
# gebleken: spinner verscheen wel, data niet - ook niet na handmatig
# verversen.
# v3 (MATCHFITAI_DROP_LIVE_SYNC_FROM_APP_2026-09-14): de app doet ZELF geen
# live intervals.icu-aanroep meer. Een aparte, uur-gebaseerde GitHub
# Actions-workflow (.github/workflows/sync-mAIcoach.yml) synchroniseert en
# schrijft naar GCS; de app leest enkel terug.
# v3.1 (MATCHFITAI_CACHE_MIRROR_HISTORY_2026-09-14): de terugleesoperatie
# gebeurde bij ELKE Streamlit-rerun (dus bij elke tab-klik) -> gecachet tot
# maximaal 1x per 5 minuten per sessie.
#
# MATCHFITAI_PERSIST_WELLNESS_ACTIVITIES_2026-09-15 (kritieke bugfix, dit blok):
# BUG (opgelost, gemeld door Kim): op de cloud toonde Dashboard wél data,
# maar Recovery én Activiteiten bleven LEEG. Oorzaak lag NIET hier maar in
# persistent_data.py: alleen history/ werd naar GCS gespiegeld, terwijl
# wellness.json (bron voor HRV/slaap in Recovery) en activities.json (bron
# voor de Activiteiten-tab) uitsluitend lokaal bestonden - en dus achterbleven
# op de GitHub Actions-runner die na de sync vernietigd wordt.
# Aanpassing hier: _refresh_local_history_from_storage() roept nu
# mirror_all_to_local() aan in plaats van mirror_history_to_local(), zodat
# alle drie de bronnen worden teruggezet. Zie persistent_data.py voor de
# volledige toelichting en de nieuwe save_wellness()/save_activities().
# --------------------------------------------------------------------------- #
_MIRROR_CACHE_SECONDS = 300  # 5 minuten - ruim vers genoeg t.o.v. de 1x/uur-sync-workflow


def _refresh_local_data_from_storage() -> None:
    """Spiegelt history, wellness én activities van GCS terug naar lokale
    bestanden. GEEN intervals.icu-aanroep - enkel een lezing van reeds
    bestaande, door de uur-gebaseerde GitHub Actions-workflow bijgewerkte
    opslag.

    Doet dit maximaal 1x per _MIRROR_CACHE_SECONDS per sessie (tijdstempel in
    st.session_state), in plaats van bij elke rerun - dat verklaarde eerder de
    trage paginawissels. Faalt de lezing (bv. GCS onbereikbaar), dan wordt dat
    opgevangen en blijft de app de reeds lokaal aanwezige data tonen; de
    volgende poging gebeurt bij het verstrijken van de cache-termijn."""
    import time
    last_refreshed = st.session_state.get("_data_mirror_last_refreshed_at")
    now = time.monotonic()
    if last_refreshed is not None and now - last_refreshed < _MIRROR_CACHE_SECONDS:
        return
    try:
        result = mirror_all_to_local()
    except Exception as exc:  # noqa: BLE001
        st.session_state["data_refresh_error"] = str(exc)
    else:
        st.session_state.pop("data_refresh_error", None)
        st.session_state["_last_mirror_result"] = result
    st.session_state["_data_mirror_last_refreshed_at"] = now


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
    AICoach/dashboard/app.py -> health_page.py) roepen exact deze functie aan."""
    try:
        st.set_page_config(page_title="mAICoach", page_icon="🏃", layout="wide")
    except Exception:
        pass
    _inject_css()
    st.title("🏃 mAICoach")
    _refresh_local_data_from_storage()
    context = build_context()
    st.caption(
        f"Actuele wellness: {context.get('current_date') or 'onbekend'} | "
        f"Laatste activiteit: {context.get('latest_activity', {}).get('date') or 'onbekend'}"
    )
    st.caption(
        "Gegevens worden elk uur automatisch bijgewerkt op de achtergrond "
        "(via GitHub Actions) - hier steeds de laatst beschikbare synchronisatie."
    )
    if st.session_state.get("data_refresh_error"):
        with st.expander("⚠️ Kon de opslag niet verversen (details)"):
            st.code(st.session_state["data_refresh_error"])
    with st.expander("Gegevens verversen"):
        st.caption(
            "Haalt de laatst door de uur-gebaseerde achtergrondtaak gesynchroniseerde "
            "gegevens opnieuw op uit de opslag (geen live intervals.icu-aanroep hier)."
        )
        last_result = st.session_state.get("_last_mirror_result")
        if last_result:
            st.caption(
                f"Laatst teruggezet uit opslag: {last_result.get('history', 0)} history-dagen, "
                f"{last_result.get('wellness', 0)} wellness-records, "
                f"{last_result.get('activities', 0)} activiteiten."
            )
        if st.button("Nu verversen"):
            st.cache_resource.clear()
            st.cache_data.clear()
            st.session_state.pop("dashboard_selected_date", None)
            # Forceert een nieuwe GCS-lezing, ook al is de 5-minuten-termijn
            # nog niet verstreken.
            st.session_state.pop("_data_mirror_last_refreshed_at", None)
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
