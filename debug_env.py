from dotenv import find_dotenv, load_dotenv
import os

env_file = find_dotenv()

print("ENV FILE =", env_file)

load_dotenv(env_file)

print("INTERVALS_API_KEY =", os.getenv("INTERVALS_API_KEY"))
print("INTERVALS_ATHLETE_ID =", os.getenv("INTERVALS_ATHLETE_ID"))