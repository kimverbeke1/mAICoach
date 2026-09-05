import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("INTERVALS_API_KEY")
athlete_id = os.getenv("INTERVALS_ATHLETE_ID")

oldest = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

url = (
    f"https://intervals.icu/api/v1/athlete/"
    f"{athlete_id}/activities"
)

params = {
    "oldest": oldest
}

response = requests.get(
    url,
    params=params,
    auth=("API_KEY", api_key),
    timeout=30
)

print()
print("URL:", response.url)
print("STATUS:", response.status_code)
print()

if response.ok:

    data = response.json()

    print("Aantal activiteiten:", len(data))

    if data:

        print()
        print("Eerste activiteit keys:")
        print()

        for key in sorted(data[0].keys()):
            print(key)

else:

    print(response.text)