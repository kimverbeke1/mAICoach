from pathlib import Path

ROOT = Path.cwd()

AI_DIR = ROOT / "AICoach"

( AI_DIR / "coach" ).mkdir(parents=True, exist_ok=True)

files = {}

files["coach/insights.py"] = '''
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
'''

files["coach/daily_coach.py"] = '''
from AICoach.coach.insights import (
    load_latest,
    generate_insight,
)

def main():

    data = load_latest()

    print()
    print("=== MATCHFIT AI COACH ===")
    print()

    print(
        f"Fitness : {data.get('fitness')}"
    )

    print(
        f"Fatigue : {data.get('fatigue')}"
    )

    print(
        f"Load : {data.get('training_load')}"
    )

    print(
        f"Rest HR : {data.get('resting_hr')}"
    )

    print()

    for insight in generate_insight(data):
        print(f"✅ {insight}")

    print()

if __name__ == "__main__":
    main()
'''

for relative_path, content in files.items():

    file_path = AI_DIR / relative_path

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path.write_text(
        content.strip(),
        encoding="utf-8"
    )

    print(f"✅ {file_path}")

print()
print("AI Coach files aangemaakt")