"""
Testscript: haal de laatste 30 dagen wellness- en activiteitendata op
van Intervals.icu en toon een samenvatting.

Gebruik:
    python fetch_summary.py

Vereist een .env bestand (zie .env.example) met:
    INTERVALS_ATHLETE_ID=i675201
    INTERVALS_API_KEY=<jouw_key>
"""

from dotenv import load_dotenv

from intervals_icu_client import IntervalsIcuClient

load_dotenv()  # leest .env in dezelfde map


def main() -> None:
    client = IntervalsIcuClient()

    print("=== Wellness (laatste 30 dagen) ===")
    wellness = client.get_recent_wellness(days=30)
    if not wellness:
        print("Geen wellness-data gevonden voor deze periode.")
    for w in wellness[-7:]:  # toon de laatste 7 dagen
        print(
            f"{w.date}  fitness(ctl)={w.ctl}  fatigue(atl)={w.atl}  "
            f"form={w.form}  restingHR={w.resting_hr}  hrv={w.hrv}"
        )

    print("\n=== Activiteiten (laatste 30 dagen) ===")
    activities = client.get_recent_activities(days=30)
    print(f"Aantal activiteiten: {len(activities)}")
    for a in activities[:5]:
        print(
            f"{a.get('start_date_local', '?')}  {a.get('type', '?'):<10}  "
            f"{a.get('name', '')}"
        )


if __name__ == "__main__":
    main()
