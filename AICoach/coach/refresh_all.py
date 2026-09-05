import subprocess
import sys


def run_step(module_name):

    print()
    print("=" * 60)
    print(module_name)
    print("=" * 60)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            module_name
        ]
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Mislukt: {module_name}"
        )


def main():

    run_step(
        "AICoach.backfill_history"
    )

    run_step(
        "AICoach.firestore.import_history"
    )

    run_step(
        "AICoach.verify_firestore_history"
    )

    print()
    print("✅ MatchFit AI refresh voltooid")
    print()


if __name__ == "__main__":
    main()