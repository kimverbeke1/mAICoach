from dotenv import load_dotenv

load_dotenv()

from AICoach.intervals.client import IntervalsClient


def main():

    client = IntervalsClient()

    athlete = client.get_athlete()

    print()
    print("ATHLETE KEYS")
    print("=" * 50)

    for key in sorted(athlete.keys()):
        print(key)

    print()
    print("TOTAAL:", len(athlete))
    print()


if __name__ == "__main__":
    main()