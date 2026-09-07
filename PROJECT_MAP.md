# Project Map — automatisch gegenereerd

Totaal aantal Python-bestanden: 110

> Gegenereerd met `generate_project_map.py`. Herrun dit script na grote wijzigingen om dit overzicht up-to-date te houden.


## 📁 (root)

### `create_activity_layer.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `create_ai_coach_files.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `create_ai_mvp.py`
⚠️ **SyntaxError: cannot assign to expression (<unknown>, line 128)**

### `create_config.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `create_core_v2.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Gebruikt eigen modules:** dotenv

### `create_matchfit_structure.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `create_snapshot_module.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `create_training_dashboard.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `debug_env.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Gebruikt eigen modules:** dotenv

### `fix_matchfit_files.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `generate_project_map.py`
- **Doel:** generate_project_map.py — genereert automatisch een overzicht (PROJECT_MAP.md)
- **Functies:** get_module_summary, first_line, build_project_map
- **Gebruikt eigen modules:** ast

### `streamlit_app.py`
- **Doel:** Gecombineerde hoofdingang: mAICoach (gezondheid) + Padel Analysis.

### `test.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.client, dotenv


## 📁 AICoach

### `__init__.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `activity_comparison.py`
- **Doel:** Vergelijkingsmotor voor MatchFitAI-activiteiten en herstelcontext.
- **Functies:** _number, _first, is_running_sport, calculate_running_efficiency, find_similar_activities, load_wellness_frame, _metric_summary, wellness_context, comparison_frame, build_ai_comparison_prompt, compare_selected_activities
- **Gebruikt eigen modules:** __future__, math

### `ai_analysis_data.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** load_json, number, text_date, date_year, first_value, calculate_form, load_history, load_activities, load_wellness, compact_activity, compact_wellness, compact_history, remove_empty_fields, current_year_records, build_ai_analysis_data
- **Gebruikt eigen modules:** math

### `app.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `app_config.py`
- **Doel:** Centrale configuratie/secrets voor mAICoach.
- **Functies:** _from_streamlit, get_secret, require_secret, use_real_ai
- **Gebruikt eigen modules:** __future__

### `athlete_insight_generator.py`
- **Doel:** Laat GPT zelf inzichten ontdekken uit de volledige ruwe mAICoach-data.
- **Functies:** load_json, clean_value, compact_records, extract_json_object, normalize_insights, _empty_payload, build_prompt, generate_athlete_insights, main
- **Gebruikt eigen modules:** AICoach.chat.ai_message_handler, __future__, ast, math

### `athlete_learning_engine.py`
- **Doel:** Feitelijke kennislaag voor mAICoach.
- **Functies:** load_json, number, rounded, mean, confidence, text_date, first_value, load_history, load_activities, load_wellness, activity_date, wellness_date, normalized_sport, is_running_sport, calculate_form, duration_seconds, format_duration, compact_wellness, wellness_index, previous_date_text, build_non_running_load_profiles, build_wellness_coverage, build_wellness_trends, best_10k, build_knowledge, save_knowledge, generate_athlete_knowledge, main
- **Gebruikt eigen modules:** math

### `backfill_history.py`
- **Doel:** Bouwt data/history/*.json op als een doorlopende dagreeks.
- **Functies:** _load_json, _first, _record_date, _wellness_by_date, _activities_by_date, build_history, main
- **Gebruikt eigen modules:** AICoach.intervals.client

### `config.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** validate
- **Gebruikt eigen modules:** dotenv

### `context_builder.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** load_json, record_date, first_value, numeric, load_history, load_activities, load_wellness, average, calculated_form, compact_wellness, build_context

### `download_activity_streams.py`
- **Doel:** Download en persisteer activity streams voor mAICoach.
- **Functies:** _load_activities, _activity_ids, ensure_local_stream, download_activity_streams, main
- **Gebruikt eigen modules:** AICoach.intervals.client, AICoach.persistent_data, __future__

### `gcs_store.py`
- **Doel:** Google Cloud Storage-laag voor mAICoach.
- **Functies:** _credentials_from_streamlit, _credentials_from_env_file, _bucket_name, get_bucket, gcs_available, read_text, write_text, read_json, write_json, delete_object, list_texts, object_exists
- **Gebruikt eigen modules:** AICoach.app_config, __future__, functools

### `persistent_data.py`
- **Doel:** Persistente cache voor mAICoach-data (history en activity streams) op GCS.
- **Functies:** backend, save_history_day, save_history_bulk, load_history_records, mirror_history_to_local, save_stream_csv, load_stream_csv, has_stream, delete_stream
- **Gebruikt eigen modules:** AICoach.gcs_store, __future__

### `refresh_all.py`
- **Doel:** Centrale refresh voor mAICoach.
- **Functies:** _run_step, _run_optional_module, main
- **Gebruikt eigen modules:** __future__, importlib

### `saved_insights.py`
- **Doel:** Persistente opslag van bewaarde inzichten voor mAICoach.
- **Functies:** _local_load, _local_write, _gcs_load, _gcs_write, storage_backend, load_saved_insights, save_insight, delete_insight, _date_label, render_saved_insights
- **Gebruikt eigen modules:** AICoach.gcs_store, __future__, uuid

### `science_knowledge.py`
- **Doel:** Wetenschappelijke kennisbank en vaste AI-regels voor mAICoach.
- **Functies:** load_science_knowledge, science_system_block
- **Gebruikt eigen modules:** __future__

### `storage.py`
- **Doel:** Persistente cloudopslag voor mAICoach (Google Cloud Storage).
- **Functies:** _load_bucket, _get_config, _service_account_info, is_enabled, download_file, upload_file, download_prefix, upload_dir
- **Gebruikt eigen modules:** __future__

### `sync_activity_history.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** configured_history_days, load_existing_activities, merge_activities, save_activities, sync_activity_history, main
- **Gebruikt eigen modules:** AICoach.intervals.client, dotenv

### `sync_latest.py`
- **Doel:** Lichte incrementele synchronisatie voor mAICoach.
- **Functies:** _activity_date, _last_date, _oldest_from, _load_json, _first, sync_latest_activities, sync_latest_wellness, rebuild_history_local, sync_latest_data, main
- **Gebruikt eigen modules:** AICoach.intervals.client, AICoach.persistent_data, AICoach.sync_activity_history, AICoach.sync_wellness_history

### `sync_manager.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** latest_history_date, needs_refresh, refresh
- **Gebruikt eigen modules:** subprocess

### `sync_wellness_history.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** history_days, load_existing, record_date, merge, save, sync_wellness_history, main
- **Gebruikt eigen modules:** AICoach.intervals.client, dotenv

### `training_summary.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.activities, collections

### `verify_firestore_history.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** firebase_service


## 📁 AICoach\chat

### `__init__.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `ai_analysis_data.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** load_json, number, text_date, date_year, first_value, calculate_form, load_history, load_activities, load_wellness, compact_activity, compact_wellness, compact_history, remove_empty_fields, current_year_records, build_ai_analysis_data
- **Gebruikt eigen modules:** math

### `ai_message_handler.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _system_prefix, _run_ai, build_prompt, build_activity_comparison_prompt, handle_message, compare_activities_with_ai
- **Gebruikt eigen modules:** AICoach.ai_analysis_data, AICoach.app_config, AICoach.context_builder

### `context_builder.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** load_json, record_date, first_value, numeric, load_history, load_activities, load_wellness, average, calculated_form, compact_wellness, build_context

### `messages_handler.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** load_recent_history, build_prompt, handle_message
- **Gebruikt eigen modules:** AICoach.context_builder, dotenv

### `refresh_all.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** run_step, refresh_knowledge, refresh_all, main
- **Gebruikt eigen modules:** AICoach.athlete_insight_generator, AICoach.athlete_learning_engine, AICoach.download_activity_streams, AICoach.sync_activity_history, AICoach.sync_wellness_history

### `test_chat.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.chat.ai_message_handler


## 📁 AICoach\coach

### `daily_coach.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.coach.insights

### `insights.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** load_latest, generate_insight

### `openai_coach.py`
⚠️ **SyntaxError: invalid non-printable character U+FEFF (<unknown>, line 1)**

### `refresh_all.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** run_step, main
- **Gebruikt eigen modules:** subprocess

### `sync_latest_data.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.firestore.firestore_service, AICoach.intervals.activities


## 📁 AICoach\dashboard

### `__init__.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `activities_tab.py`
- **Doel:** Activiteitenpagina van mAICoach.
- **Functies:** _row_by_id, _selected_ids, _toggle_selection, _apply_filters, _activity_summary, _open_detail, _start_comparison, _render_compare_bar, _render_list, _render_browser, render_activities
- **Gebruikt eigen modules:** AICoach.dashboard.activity_detail, AICoach.dashboard.data_loaders, AICoach.dashboard.ui_helpers, __future__

### `activity_detail.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _peer_label, _render_peer_selection, similar_activities, _first_column, _fetch_stream_frame, _x_axis, _render_stream_charts, _render_map, render_activity_detail
- **Gebruikt eigen modules:** AICoach.activity_comparison, AICoach.dashboard.charts, AICoach.dashboard.ui_helpers, __future__, io

### `app.py`
- **Doel:** Adapter die de mAICoach-gezondheidsmodule aanbiedt aan streamlit_app.py.
- **Gebruikt eigen modules:** AICoach.dashboard.training_dashboard, __future__

### `best_results_tab.py`
- **Doel:** Beste resultaten voor mAICoach.
- **Functies:** _date_label, _running_frame, best_pace_records, _best_row, _fmt, metric_records, _render_detail, _render_records_with_detail, render_best_results
- **Gebruikt eigen modules:** AICoach.dashboard.data_loaders, AICoach.dashboard.ui_helpers, __future__

### `charts.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** form_zone_for, selected_date_from_event, _data_date_range, aggregate_frame, _add_form_zones, configure_time_chart, render_time_chart
- **Gebruikt eigen modules:** AICoach.dashboard.ui_helpers

### `comparison_tab.py`
- **Doel:** Aparte, sluitbare vergelijkings-tab voor mAICoach.
- **Functies:** _selected_ids, _close_comparison, _overview, _run_analysis, render_comparison_tab
- **Gebruikt eigen modules:** AICoach.activity_comparison, AICoach.dashboard.data_loaders, AICoach.dashboard.ui_helpers, __future__

### `daily_update.py`
- **Doel:** Dagelijkse update voor mAICoach.
- **Functies:** _unique_key, _latest_and_previous, compute_daily_signals, _ai_period_prompt, render_daily_update
- **Gebruikt eigen modules:** AICoach.chat.ai_message_handler, AICoach.dashboard.charts, AICoach.dashboard.data_loaders, __future__

### `data_loaders.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** load_json, first_value, numeric, text_date, is_running_sport, load_history, load_wellness_frame, load_activities_frame
- **Gebruikt eigen modules:** math

### `health_page.py`
- **Doel:** Streamlit-pagina die de mAICoach-gezondheidsapp toont.
- **Gebruikt eigen modules:** AICoach.dashboard.app

### `knowledge_tab.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _load_insights_payload, _format_generated_at, _insight_as_text, _render_insight_card, _run_new_analysis, render_knowledge
- **Gebruikt eigen modules:** AICoach.saved_insights, __future__

### `recovery_tab.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** render_recovery
- **Gebruikt eigen modules:** AICoach.dashboard.charts, AICoach.dashboard.data_loaders, AICoach.dashboard.ui_helpers

### `training_dashboard.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _inject_css, _sync_once, ensure_latest_data, render_dashboard, render_chat, render_health_app
- **Gebruikt eigen modules:** AICoach.chat.ai_message_handler, AICoach.context_builder, AICoach.dashboard.activities_tab, AICoach.dashboard.best_results_tab, AICoach.dashboard.charts, AICoach.dashboard.comparison_tab, AICoach.dashboard.daily_update, AICoach.dashboard.data_loaders, AICoach.dashboard.knowledge_tab, AICoach.dashboard.recovery_tab, AICoach.dashboard.ui_helpers, AICoach.saved_insights

### `ui_helpers.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** has_data, display_value, is_running_sport, format_duration, format_pace, nearest_row, render_selected_values, render_assistant_answer

### `validate_dashboard.py`
- **Doel:** Valideer de modulaire MatchFitAI-dashboardstructuur en de dagelijkse datadekking.
- **Classes:** DailyStatus
- **Functies:** _finite_number, _first, _day_text, _record_day, _read_json, _records_from_json, _history_records, _merge_status, validate_files, validate_imports, validate_json_source, analyse_daily_status, inspect_activity_detail_readiness, main
- **Gebruikt eigen modules:** __future__, dataclasses, importlib, math


## 📁 AICoach\firestore

### `import_history.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** firebase_service

### `save_snapshot.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** save_snapshot, main
- **Gebruikt eigen modules:** AICoach.intervals.client, dotenv


## 📁 AICoach\intervals

### `__init__.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `activities.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Classes:** ActivityService
- **Gebruikt eigen modules:** AICoach.intervals.client

### `client.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Classes:** IntervalsClient
- **Gebruikt eigen modules:** AICoach.app_config, io

### `discover_endpoints.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.client, dotenv

### `get_activities.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.client

### `latest_activities.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.client

### `test_activities.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Gebruikt eigen modules:** dotenv


## 📁 AICoach\pages

### `ai_chat.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Gebruikt eigen modules:** AICoach.chat.ai_message_handler


## 📁 AICoach\snapshots

### `create_daily_snapshot.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** build_snapshot, main
- **Gebruikt eigen modules:** AICoach.intervals.client, AICoach.storage.snapshot_manager, dotenv

### `create_daily_summary.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.client

### `create_snapshot.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.client, AICoach.storage.snapshot_manager, dotenv

### `save_daily_summary_to_firestore.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** AICoach.intervals.client, firebase_service

### `save_snapshot.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** main
- **Gebruikt eigen modules:** firebase_service


## 📁 AICoach\storage

### `__init__.py`
- **Doel:** (geen docstring gevonden — doel onbekend)

### `snapshot_manager.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Classes:** SnapshotManager


## 📁 PadelAnalysis

### `ci_scrape_all.py`
- **Doel:** ci_scrape_all.py — GitHub Actions entrypoint voor het (op aanvraag) verversen
- **Functies:** get_all_player_ids, get_requested_player_ids, main
- **Gebruikt eigen modules:** firebase_service, logging, scrape_player

### `cloud_helpers.py`
- **Doel:** cloud_helpers.py — Streamlit Community Cloud detectie voor PadelAnalysis.
- **Functies:** is_scraping_available, _get_github_settings, is_github_trigger_configured, trigger_github_actions_scrape, render_cloud_scrape_trigger

### `create_training_snapshot.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** create_test_snapshot
- **Gebruikt eigen modules:** firebase_service

### `dashboard.py`
- **Doel:** dashboard.py  —  PadelAnalysis v2 Streamlit dashboard
- **Functies:** _clean, _parse_match_date, _format_scraped_at, _short_period_label, _period_sort_key, _display_name, _go_to_player, _scrape_progress_widget, _matches_to_df, _winrate_str, _render_metrics, _summarize_partner, _summarize_opponents, _render_table, _load_poule_fixtures, _clean_name, _get_all_profiles, page_add_player, _load_encounter_index, _render_volgende_match, page_lineup_lab, _render_refresh_controls, _render_player_dashboard, page_my_profile, page_players
- **Gebruikt eigen modules:** cloud_helpers, firebase_service, lineup_lab, lineup_quick, opponent_dossier, opponent_scout, player_inline_actions, schedule_scraper

### `firebase_service.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** utc_now_iso, convert_firestore_values, sanitize_for_firestore, normalize_name, normalize_search_key, build_minimal_defaults, _load_streamlit_secrets_credentials, _load_env_credentials, _load_local_file_credentials, _init_firebase, save_player, get_player, save_player_profile, get_player_profile, get_app_settings, save_app_settings, search_player_profiles, save_player_search_cache, get_player_search_cache, save_player_v2, delete_player

### `investigate_tournament_pipeline.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** clean, norm, write, html_to_text, context_snippets, call_fetch, try_parse_tournaments, summarize_matches, main
- **Gebruikt eigen modules:** __future__, importlib, inspect

### `lineup_lab.py`
- **Doel:** lineup_lab.py — Opstelling-analyse (Fase 1: retrospectieve test-tool)
- **Functies:** get_all_profiles, get_docs_for_players, _encounter_key, build_encounter_index, list_encounters, _board_dedupe_key, reconstruct_boards, required_counts_from_boards, compute_pairwise_synergy, compute_individual_winrate, find_player_ranking, make_pair_score_fn, optimize_lineup, score_actual_lineup, parse_ranking, matchup_edge, optimize_lineup_vs_scenario
- **Gebruikt eigen modules:** firebase_service, heapq, itertools

### `lineup_quick.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _safe_int, _winrate_num, _pct, _winrate_str, _parse_rank, _format_rank, _parse_match_date, _match_date_key, _match_type_label, _result_char, _dedupe_match_key, _dataframe_kwargs, _partner_general_wr, _available_players_df, _recent_interclub_df, _collect_partner_analysis_from_selected_doc, _render_selectable_table_with_detail, render_lineup_quick_results
- **Gebruikt eigen modules:** __future__, firebase_service, inspect, lineup_lab, player_inline_actions

### `manual_capture_padel_page.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** clean, save, main
- **Gebruikt eigen modules:** __future__, playwright.sync_api, urllib.parse

### `opponent_dossier.py`
- **Doel:** opponent_dossier.py — Volledig dossier van een individuele tegenstander,
- **Functies:** _parse_rank, _winrate_str, _best_rank_from_klassement_history, _best_rank_opportunistic, render_opponent_dossier, render_opponent_dossier_button
- **Gebruikt eigen modules:** __future__, firebase_service

### `opponent_scout.py`
- **Doel:** opponent_scout.py — haalt de individuele opstelling van een tegenstander uit
- **Functies:** _normalize, get_opponent_previous_fixtures, extract_opponent_lineup, scout_opponent, scrape_new_opponent_players
- **Gebruikt eigen modules:** firebase_service, schedule_scraper, scraper_v2

### `player_action_widget.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _clean, _norm, _name_variants, _safe_int, _try_call_noargs, _load_profiles_from_firebase, _profile_name, _build_profile_lookup, _status_for_player_id, _call_scrape_player, _extract_players_from_df, _extract_players_from_records, collect_players_from_context, render_player_action, render_player_actions_from_context
- **Gebruikt eigen modules:** __future__, firebase_service, inspect

### `player_inline_actions.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _inject_compact_css, _small_text, _small_header, _clean, _strip_rank_suffix, _norm, _variants, _safe_int, _try_call_noargs, _load_profiles_from_firebase, _candidate_names_from_profile, _profile_name, _profile_id, build_profile_lookup, resolve_player_id, player_status, _split_name_guess, _render_search_and_link_fallback, render_player_name_action, _render_action_body, render_dataframe_with_player_actions, render_matches_period_table
- **Gebruikt eigen modules:** __future__, firebase_service, inspect, scrape_jobs

### `player_scrape_status.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** _safe_int, _display_name, _scrape_status, _call_scrape_player, render_player_scrape_status
- **Gebruikt eigen modules:** __future__, firebase_service, inspect

### `player_search.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** log_line, clean_text, _fold, _title_from_search, normalize_name_parts, split_full_name, build_search_url, dismiss_cookie_banner_if_present, detect_robot_page, extract_player_id_from_url, _candidate_starts_with_exact_search_name, _exact_name_match, _club_match, _split_name_club_from_raw, parse_result_block, _candidate_from_url_and_meta, _dedupe, _filter_candidates, _save_profiles, _raw_candidate_elements, extract_candidates_from_page, click_search_button_if_needed, _install_resource_blocking, search_players
- **Gebruikt eigen modules:** __future__, firebase_service, playwright.sync_api, unicodedata, urllib.parse

### `schedule_scraper.py`
- **Doel:** schedule_scraper.py — haalt het publieke poule/tabel-schema op
- **Functies:** _param_from_url, _clean, fetch_poule_schedule_html, parse_poule_schedule, _find_preceding_label, _parse_date_text, identify_own_ploeg_id, get_team_fixtures, get_next_match, opponent_of
- **Gebruikt eigen modules:** bs4, urllib.parse

### `scrape_jobs.py`
- **Doel:** scrape_jobs.py — gedeelde achtergrond-scrape-job registry voor PadelAnalysis.
- **Functies:** get_scrape_jobs, is_scrape_running, start_background_scrape, render_active_jobs_banner
- **Gebruikt eigen modules:** threading

### `scrape_klassement.py`
- **Doel:** scrape_klassement.py — TVL padel klassementshistoriek scraper V3 compact
- **Functies:** _build_url, _clean, _progress, _safe_attr, _safe_text, _goto, _dismiss_cookies, _try_activate_padel_tab, _wait, _debug, _selects, _score, _get_sel, _options, _select, _pct, _smallint, _first, _rank, _cnt, _padel_form_html, _extract_selected_period_klassement_from_text, _extract_selected_period_klassement_from_html, _parse, scrape_klassement, klassement_to_history_summary, extract_niveau_winrates
- **Gebruikt eigen modules:** __future__, argparse, logging, playwright.sync_api, urllib.parse

### `training_firestore_test.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Gebruikt eigen modules:** firebase_service


## 📁 PadelAnalysis\debug_output

### `player_search.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** log_line, clean_text, split_name_for_tpv, build_search_url, dismiss_cookie_banner_if_present, detect_robot_page, extract_player_id_from_url, extract_candidates_from_page, click_search_button_if_needed, search_players
- **Gebruikt eigen modules:** firebase_service, playwright.sync_api, urllib.parse


## 📁 PadelAnalysis\scraper

### `__init__.py`
- **Doel:** Scraper package without import side effects.

### `ci_scrape_all.py`
- **Doel:** ci_scrape_all.py — GitHub Actions entrypoint voor het (op aanvraag) verversen
- **Functies:** get_all_player_ids, get_requested_player_ids, get_mode, filter_by_mode, scrape_kwargs_for_mode, main
- **Gebruikt eigen modules:** firebase_service, logging, scrape_player

### `fetch_period_playwright.py`
- **Doel:** fetch_period_playwright.py
- **Functies:** _activate_padel_results_tab, _build_url, _dismiss_cookies, _get_padel_period_select, _get_period_options, _wait_after_select, fetch_all_periods_html
- **Gebruikt eigen modules:** logging, playwright.sync_api

### `parser.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Functies:** parse_matches
- **Gebruikt eigen modules:** bs4

### `reset_test.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Gebruikt eigen modules:** firebase_service

### `scrape_player.py`
- **Doel:** scrape_player.py  —  Hoofdorchestrator voor PadelAnalysis
- **Functies:** _calc_stats, _match_identity, _dedupe, _periods_to_scrape, _merge_matches, scrape_player_current, _activate_padel_results_tab, scrape_player, scrape_players
- **Gebruikt eigen modules:** bs4, fetch_period_playwright, firebase_service, logging, scraper_v2

### `scraper_v2.py`
- **Doel:** scraper_v2.py - HTTP-based scraper voor tennisenpadelvlaanderen.be
- **Functies:** _utc_now, _clean, _user_id_from_url, _param_from_url, _parse_player_link, _get_html, get_padel_periods, fetch_period_html, _get_padel_section_container, parse_tournament_section, _parse_tournament_org_div, parse_interclub_section, _parse_interclub_details_div, _is_between, scrape_uitslagenblad, scrape_player, scrape_current_period
- **Gebruikt eigen modules:** bs4, logging, urllib.parse


## 📁 TrainingData

### `fetch_summary.py`
- **Doel:** Testscript: haal de laatste 30 dagen wellness- en activiteitendata op
- **Functies:** main
- **Gebruikt eigen modules:** dotenv, intervals_icu_client

### `intervals_icu_client.py`
- **Doel:** Intervals.icu API client voor MatchFitAI - TrainingData module.
- **Classes:** WellnessRecord, IntervalsIcuClient
- **Gebruikt eigen modules:** __future__, dataclasses

### `test.py`
- **Doel:** (geen docstring gevonden — doel onbekend)
- **Gebruikt eigen modules:** dotenv
