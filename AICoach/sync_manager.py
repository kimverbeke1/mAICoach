from pathlib import Path
from datetime import datetime
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

HISTORY_DIR = ROOT / "data" / "history"


def latest_history_date():

    files = sorted(
        HISTORY_DIR.glob("*.json")
    )

    if not files:
        return None

    return datetime.strptime(
        files[-1].stem,
        "%Y-%m-%d"
    ).date()


def needs_refresh():

    latest = latest_history_date()

    if not latest:
        return True

    today = datetime.now().date()

    return latest < today


def refresh():

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "AICoach.refresh_all"
        ]
    )

    return result.returncode == 0


if __name__ == "__main__":

    print()

    print(
        "Latest:",
        latest_history_date()
    )

    print(
        "Needs refresh:",
        needs_refresh()
    )

    print()