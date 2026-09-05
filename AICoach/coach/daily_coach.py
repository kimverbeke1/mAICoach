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