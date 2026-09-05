from pathlib import Path

content = '''import os
from dotenv import load_dotenv

load_dotenv()

INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY")
INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
'''

path = Path("AICoach/config.py")

path.write_text(
    content,
    encoding="utf-8"
)

print("✅ AICoach/config.py aangemaakt")