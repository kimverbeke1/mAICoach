# -*- coding: utf-8 -*-
from pathlib import Path
import sys
import threading
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
# MATCHFITAI_NONBLOCKING_STARTUP_SYNC_2026-09-14
# BUG (opgelost): ensure_latest_data() riep _sync_once() rechtstreeks en
# SYNCHROON aan, VOOR er ook maar iets van de UI (tabs, data) getoond werd -
# ondanks de (misleidende) codecommentaar "UI eerst tonen; sync draait
# gecachet en blokkeert niet". _sync_once() is een st.cache_resource met
# ttl=1800 (30 minuten) - een PROCES-BREDE cache, gedeeld over alle sessies.
# Bij elke "koude start" (na 30 minuten inactiviteit, of - typischer op
# Streamlit Community Cloud - na een volledige herstart van de app door
# inactiviteit/redeploy) is die cache leeg, en moest de EERSTE bezoeker
# wachten tot sync_latest_data() volledig klaar was (intervals.icu-API-
# calls + bestandsschrijfacties), VOOR er iets op het scherm verscheen.
# Fix: de sync draait nu ECHT op de achtergrond (aparte thread). De UI
# rendert ONMIDDELLIJK met de data die al lokaal/in GCS aanwezig is (nooit
# leeg bij een normale, niet-eerste-ooit run). Zodra de achtergrond-sync
# klaar is, wordt dat gedetecteerd bij de eerstvolgende Streamlit-rerun
# (elke gebruikersinteractie triggert er sowieso een) en worden de
# data-caches dan pas geleegd + een expliciete rerun getriggerd.
#
# MATCHFITAI_AUTOSTART_FIRST_SYNC_2026-09-14 (aanvulling, op verzoek van Kim)
# BUG/BEPERKING (opgelost): op een VERSE cloud-container (of de allereerste
# ooit-run) bestaat er nog HELEMAAL GEEN lokale trainingshistoriek. In dat
# specifieke geval toonde de app "Geen trainingshistoriek gevonden" en bleef
# ze dat tonen totdat de gebruiker ZELF een interactie deed (bv. handmatig op
# "Nu verversen" klikken in de "Gegevens verversen"-expander) - want Streamlit
# voert de pagina enkel opnieuw uit bij een gebruikersinteractie, niet
# automatisch zodra een achtergrond-thread klaar is. Kim's melding: op de
# cloud zag hij deze lege staat, maar zodra hij zelf op "Nu verversen" klikte,
# verscheen de data WEL meteen (want de achtergrond-sync was intussen allang
# klaar, enkel de detectie ervan had een interactie nodig om te triggeren).
# Kim's verzoek: de achtergrond-sync-aanpak BEHOUDEN, maar bij het laden
# automatisch al "die knop indrukken" zodat de gebruiker dat niet zelf hoeft
# te doen.
# Fix: _await_first_sync_if_needed() wacht EENMALIG en BEGRENSD (maximaal
# _FIRST_SYNC_MAX_WAIT_SECONDS) op de achtergrond-thread, maar ENKEL als er
# nog GEEN lokale data bestaat (load_history().empty) - dat is het enige
# scenario waarin er sowieso niets zinvols te tonen valt zolang niet minstens
# een eerste sync is afgerond. Bestaat er al (evt. wat verouderde) lokale
# data, dan verandert er NIETS aan het bestaande, volledig niet-blokkerende
# gedrag hierboven. Bij een trage of falende eerste sync (langer dan de
# begrensde wachttijd) valt de code gewoon terug op de bestaande
# "Geen trainingshistoriek gevonden"-melding + de handmatige "Nu
# verversen"-knop blijft beschikbaar - de gebruiker raakt dus nooit
# onherstelbaar vast, enkel de typische, lichte incrementele sync
# (sync_latest.py noemt zichzelf expliciet "licht incrementeel") krijgt de
# kans om automatisch, zonder klik, op tijd klaar te zijn.
# --------------------------------------------------------------------------- #
_SYNC_MIN_INTERVAL_SECONDS = 1800  # 30 minuten, zelfde als de vorige ttl
_FIRST_SYNC_MAX_WAIT_SECONDS = 25  # begrensde, eenmalige wachttijd - nooit oneindig
_FIRST_SYNC_POLL_STEP_SECONDS = 2


def _sync_worker() -> None:
    """Draait in een aparte thread: doet de effectieve intervals.icu-sync.
    Schrijft het resultaat/eventuele fout naar een module-level dict
    (niet st.session_state - dat is niet thread-safe voor schrijven vanuit
    een andere thread dan de hoofd-Streamlit-thread)."""
    from AICoach.sync_latest import sync_latest_data
    try:
        sync_latest_data()
        _SYNC_STATE["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        _SYNC_STATE["status"] = "error"
        _SYNC_STATE["error"] = str(exc)


# Module-level (proces-breed) state van de lopende/laatste achtergrond-sync.
# Bewust GEEN st.session_state (niet thread-safe voor cross-thread writes).
_SYNC_STATE = {"status": "idle", "error": None, "thread": None}


def ensure_latest_data() -> None:
    """MATCHFITAI_NONBLOCKING_STARTUP_SYNC_2026-09-14: start de sync op de
    achtergrond als dat nog niet recent gebeurd is, en blokkeert NOOIT de
    render van de rest van de pagina. Detecteert bij elke aanroep (dus bij
    elke Streamlit-rerun) of een eerder gestarte achtergrond-sync intussen
    klaar is; zo ja, worden de data-caches geleegd en wordt éénmalig een
    rerun getriggerd zodat de verse data verschijnt."""
    import time
    last_started = st.session_state.get("_sync_last_started_at")
    now = time.monotonic()
    thread_running = _SYNC_STATE["thread"] is not None and _SYNC_STATE["thread"].is_alive()
    if not thread_running and (last_started is None or now - last_started > _SYNC_MIN_INTERVAL_SECONDS):
        _SYNC_STATE["status"] = "running"
        _SYNC_STATE["error"] = None
        thread = threading.Thread(target=_sync_worker, daemon=True)
        _SYNC_STATE["thread"] = thread
        thread.start()
        st.session_state["_sync_last_started_at"] = now
        st.session_state["_sync_awaiting_refresh"] = True
        return
    if st.session_state.get("_sync_awaiting_refresh") and _SYNC_STATE["status"] in ("done", "error"):
        st.session_state["_sync_awaiting_refresh"] = False
        if _SYNC_STATE["status"] == "error":
            st.session_state.startup_sync_error = _SYNC_STATE["error"]
        else:
            st.session_state.pop("startup_sync_error", None)
            st.cache_data.clear()
            st.rerun()


def _await_first_sync_if_needed() -> None:
    """MATCHFITAI_AUTOSTART_FIRST_SYNC_2026-09-14: zie de uitleg hierboven.
    Wacht eenmalig, begrensd (max _FIRST_SYNC_MAX_WAIT_SECONDS) op de door
    ensure_latest_data() gestarte achtergrond-thread, maar ENKEL wanneer er
    nog helemaal geen lokale trainingshistoriek bestaat. In elk ander geval
    (normale koude start met al bestaande, evt. wat verouderde lokale data)
    doet deze functie niets en blijft het bestaande, volledig
    niet-blokkerende gedrag ongewijzigd."""
    if not load_history().empty:
        return
    thread = _SYNC_STATE.get("thread")
    if thread is None or not thread.is_alive():
        return
    with st.spinner("Eerste synchronisatie met intervals.icu bezig (eenmalig, max ~25s)..."):
        waited = 0.0
        while thread.is_alive() and waited < _FIRST_SYNC_MAX_WAIT_SECONDS:
            thread.join(timeout=_FIRST_SYNC_POLL_STEP_SECONDS)
            waited += _FIRST_SYNC_POLL_STEP_SECONDS
    if _SYNC_STATE.get("status") == "done":
        st.session_state["_sync_awaiting_refresh"] = False
        st.session_state.pop("startup_sync_error", None)
        st.cache_data.clear()
        st.rerun()
    elif _SYNC_STATE.get("status") == "error":
        st.session_state["_sync_awaiting_refresh"] = False
        st.session_state["startup_sync_error"] = _SYNC_STATE.get("error")
    # Anders (nog steeds bezig na de begrensde wachttijd): gewoon doorgaan
    # naar de normale rendering. De achtergrond-thread loopt gewoon door; de
    # bestaande "Nu verversen"-knop of een volgende interactie pikt de
    # voltooiing later alsnog op via ensure_latest_data().


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
    """Bouwt de volledige mAICoach-pagina (titel, sync, tabs).
    Dit is de ENIGE plek waar de UI-structuur van de gezondheidsmodule wordt
    opgebouwd. Zowel de standalone uitvoering (streamlit run
    training_dashboard.py) als de gecombineerde app (via
    AICoach/dashboard/app.py -> health_page.py) roepen exact deze functie aan.
    MATCHFITAI_NONBLOCKING_STARTUP_SYNC_2026-09-14: ensure_latest_data()
    start nu enkel een achtergrondthread (of detecteert dat er eentje klaar
    is) - het blokkeert de render hieronder niet meer, ook niet bij een
    koude start.
    MATCHFITAI_AUTOSTART_FIRST_SYNC_2026-09-14: direct daarna wordt
    _await_first_sync_if_needed() aangeroepen - die doet NIETS zolang er al
    lokale data bestaat, maar wacht kort en begrensd op de allereerste sync
    als die data nog volledig ontbreekt (zie uitleg daar)."""
    try:
        st.set_page_config(page_title="mAICoach", page_icon="🏃", layout="wide")
    except Exception:
        pass
    _inject_css()
    st.title("🏃 mAICoach")
    # UI eerst tonen; sync draait nu ECHT op de achtergrond en blokkeert niet.
    ensure_latest_data()
    _await_first_sync_if_needed()
    if st.session_state.get("_sync_awaiting_refresh"):
        st.caption("🔄 Nieuwste gegevens worden op de achtergrond opgehaald...")
    context = build_context()
    st.caption(
        f"Actuele wellness: {context.get('current_date') or 'onbekend'} | "
        f"Laatste activiteit: {context.get('latest_activity', {}).get('date') or 'onbekend'}"
    )
    with st.expander("Gegevens verversen"):
        st.caption("De nieuwste gegevens worden automatisch opgehaald. Forceer hier indien nodig.")
        if st.button("Nu verversen"):
            st.cache_resource.clear()
            st.cache_data.clear()
            st.session_state.pop("dashboard_selected_date", None)
            st.session_state.pop("_sync_last_started_at", None)
            st.rerun()
        if st.session_state.get("startup_sync_error"):
            st.warning("Automatische synchronisatie gaf een melding:")
            st.code(st.session_state["startup_sync_error"])
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
