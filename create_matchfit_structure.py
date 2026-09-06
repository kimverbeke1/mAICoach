from pathlib import Path

ROOT = Path.cwd()

folders = [
    "AICoach",
    "AICoach/intervals",
    "AICoach/storage",
    "AICoach/coach",
    "AICoach/prompts",
    "AICoach/tests",
    "data",
    "docs",
]

files = {
    ".env": """INTERVALS_API_KEY=
INTERVALS_ATHLETE_ID=
OPENAI_API_KEY=
""",

    ".gitignore": """# Secrets
.env

# Python
__pycache__/
*.pyc

# Virtual envs
.venv/
venv/

# IDE
.vscode/
.idea/

# Data
data/

# Debug
debug_output/
debug_output_v2/

# Archives
archive/

# Databases
*.db
*.sqlite
*.sqlite3
""",

    "requirements.txt": """requests
python-dotenv
""",

    "AICoach/__init__.py": "",

    "AICoach/intervals/__init__.py": "",

    "AICoach/intervals/client.py": """import os
import requests


class IntervalsClient:

    def __init__(self):
        self.api_key = os.getenv("INTERVALS_API_KEY")
        self.athlete_id = os.getenv("INTERVALS_ATHLETE_ID")

        if not self.api_key:
            raise ValueError("INTERVALS_API_KEY ontbreekt")

        if not self.athlete_id:
            raise ValueError("INTERVALS_ATHLETE_ID ontbreekt")

    def get_athlete(self):

        url = f"https://intervals.icu/api/v1/athlete/{self.athlete_id}"

        response = requests.get(
            url,
            auth=("API_KEY", self.api_key),
            timeout=30
        )

        response.raise_for_status()

        return response.json()
""",

    "test.py": """from dotenv import load_dotenv

load_dotenv()

from AICoach.intervals.client import IntervalsClient


def main():

    client = IntervalsClient()

    athlete = client.get_athlete()

    print("\\n=== MATCHFIT AI ===\\n")

    print(f"ID: {athlete.get('id')}")
    print(f"Naam: {athlete.get('name')}")

    print("\\nVolledige response:\\n")
    print(athlete)


if __name__ == "__main__":
    main()
"""
}


for folder in folders:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

for filename, content in files.items():
    path = ROOT / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

print()
print("✅ MatchFitAI structuur aangemaakt")
print(f"📁 Locatie: {ROOT}")