from dotenv import load_dotenv
import os

load_dotenv()

print("API KEY FOUND:", bool(os.getenv("INTERVALS_API_KEY")))
print("ATHLETE ID :", os.getenv("INTERVALS_ATHLETE_ID"))