from pathlib import Path
import json

from AICoach.intervals.client import IntervalsClient

OUTPUT_DIR = Path("data") / "daily_summaries"


def main():

    client = IntervalsClient()

    activity = client.get_latest_activity()

    if not activity:
        print("Geen activiteiten gevonden")
        return

    date_key = str(
        activity.get("start_date_local", "")
    )[:10]

    summary = {
        "date": date_key,
        "activity_name": activity.get("name"),
        "activity_type": activity.get("type"),
        "fitness": activity.get("icu_ctl"),
        "fatigue": activity.get("icu_atl"),
        "training_load": activity.get("icu_training_load"),
        "resting_hr": activity.get("icu_resting_hr"),
        "weight": activity.get("icu_weight"),
        "rpe": activity.get("icu_rpe"),
        "feel": activity.get("feel"),
        "hr_load": activity.get("hr_load"),
        "strain_score": activity.get("strain_score"),
        "distance": activity.get("distance"),
        "elapsed_time": activity.get("elapsed_time"),
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = OUTPUT_DIR / f"{date_key}.json"

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=== DAILY SUMMARY ===")
    print()

    for key, value in summary.items():
        print(f"{key}: {value}")

    print()
    print(f"Opgeslagen: {output_file}")


if __name__ == "__main__":
    main()