# -*- coding: utf-8 -*-

from AICoach.athlete_insight_generator import generate_athlete_insights
from AICoach.athlete_learning_engine import build_knowledge, save_knowledge
from AICoach.download_activity_streams import download_activity_streams
from AICoach.sync_activity_history import sync_activity_history
from AICoach.sync_wellness_history import sync_wellness_history


def run_step(name, function):
    print()
    print(name)
    print("=" * 60)
    try:
        result = function()
        print(result)
        return {"status": "success", "result": result}
    except Exception as exc:
        print(f"FOUT: {exc}")
        return {"status": "error", "error": str(exc)}


def refresh_knowledge():
    knowledge = build_knowledge()
    save_knowledge(knowledge)
    return {
        "knowledge_file": "data/athlete_knowledge.json",
        "activities": knowledge.get("data_quality", {}).get("activity_count", 0),
        "wellness_records": knowledge.get("data_quality", {}).get("wellness_count", 0),
    }


def refresh_all():
    results = {
        "activities": run_step("ACTIVITEITEN SYNCHRONISEREN", sync_activity_history),
        "wellness": run_step("WELLNESS SYNCHRONISEREN", sync_wellness_history),
        "streams": run_step("ACTIVITY STREAMS DOWNLOADEN", download_activity_streams),
        "knowledge": run_step("KENNISLAAG VERNIEUWEN", refresh_knowledge),
        "insights": run_step("AI-INSIGHTS GENEREREN", generate_athlete_insights),
    }
    results["success"] = all(
        step.get("status") == "success"
        for step in results.values()
        if isinstance(step, dict) and "status" in step
    )
    return results


def main():
    results = refresh_all()
    print()
    print("REFRESH VOLTOOID")
    print("=" * 60)
    print("Alle databronnen zijn vernieuwd." if results["success"] else "Minstens één stap gaf een fout.")
    print()


if __name__ == "__main__":
    main()
