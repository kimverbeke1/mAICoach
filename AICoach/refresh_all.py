# -*- coding: utf-8 -*-
"""Centrale refresh voor mAICoach.

Volgorde en doel:
1. Wellness synchroniseren (data/wellness/wellness.json), incl. vandaag.
2. Optionele activiteiten-/streams-sync uitvoeren als die modules bestaan.
   (Bestaande functionaliteit blijft behouden; ontbrekende modules worden
    stilzwijgend overgeslagen zodat de refresh nooit crasht.)
3. History herbouwen (data/history/*.json) met build_history(), zodat het
   dashboard altijd de nieuwste dag toont. Dit was de ontbrekende stap
   waardoor het dashboard achterliep.
"""

from __future__ import annotations

import importlib


def _run_step(label: str, func) -> bool:
    print()
    print("=" * 60)
    print(label)
    print("=" * 60)
    try:
        func()
        return True
    except Exception as exc:  # noqa: BLE001 - refresh mag nooit hard falen
        print(f"[OVERGESLAGEN] {label}: {exc}")
        return False


def _run_optional_module(module_name: str, label: str) -> bool:
    """Voer <module>.main() uit als de module bestaat; sla anders stil over."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        print(f"[INFO] {label}: module '{module_name}' niet gevonden, overgeslagen.")
        return False
    main = getattr(module, "main", None)
    if not callable(main):
        print(f"[INFO] {label}: geen main() in '{module_name}', overgeslagen.")
        return False
    return _run_step(label, main)


def main() -> None:
    print()
    print("mAICoach - volledige data-refresh")

    # 1. Wellness (bevat elke dag, inclusief vandaag).
    from AICoach.sync_wellness_history import sync_wellness_history

    _run_step("WELLNESS SYNC", sync_wellness_history)

    # 2. Optionele activiteiten-/streams-sync (behoudt bestaande pipeline).
    #    Deze namen worden geprobeerd; niet-bestaande worden overgeslagen.
    _run_optional_module("AICoach.sync_activities", "ACTIVITIES SYNC")
    _run_optional_module("AICoach.download_activity_streams", "ACTIVITY STREAMS SYNC")
    _run_optional_module("AICoach.sync_latest_data", "FIRESTORE SYNC")

    # 3. History herbouwen (verplicht) -> lost de dashboard-sync definitief op.
    from AICoach.backfill_history import build_history

    _run_step("HISTORY REBUILD", build_history)

    print()
    print("Refresh voltooid.")


if __name__ == "__main__":
    main()
