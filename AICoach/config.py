from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent

ENV_FILE = ROOT / ".env"

load_dotenv(ENV_FILE)

INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY")
INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def validate():

    missing = []

    if not INTERVALS_API_KEY:
        missing.append("INTERVALS_API_KEY")

    if not INTERVALS_ATHLETE_ID:
        missing.append("INTERVALS_ATHLETE_ID")

    if missing:
        raise ValueError(
            f"Ontbrekende configuratie: {', '.join(missing)}"
        )
