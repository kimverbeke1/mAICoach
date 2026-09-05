from pathlib import Path
import json

HISTORY_DIR = Path("data/history")

def load_latest():
    files = sorted(HISTORY_DIR.glob("*.json"))

    if not files:
        return None

    latest = files[-1]

    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_insight(data):

    fitness = data.get("fitness")
    fatigue = data.get("fatigue")
    resting_hr = data.get("resting_hr")

    insights = []

    if fitness and fatigue:

        if fatigue > fitness + 10:
            insights.append(
                "Herstel aanbevolen. Fatigue ligt duidelijk boven fitness."
            )

        elif fitness > fatigue:
            insights.append(
                "Goede belastbaarheid. Je fitness ligt hoger dan je fatigue."
            )

    if resting_hr:
        insights.append(
            f"Huidige rusthartslag: {resting_hr} bpm."
        )

    return insights

if __name__ == "__main__":

    data = load_latest()

    print()
    print("=== DAILY INSIGHT ===")
    print()

    for line in generate_insight(data):
        print("-", line)