from dotenv import load_dotenv

load_dotenv()

from AICoach.intervals.client import IntervalsClient


def main():

    client = IntervalsClient()

    athlete = client.get_athlete()

    print("\n=== MATCHFIT AI ===\n")

    print(f"ID: {athlete.get('id')}")
    print(f"Naam: {athlete.get('name')}")

    print("\nVolledige response:\n")
    print(athlete)


if __name__ == "__main__":
    main()
