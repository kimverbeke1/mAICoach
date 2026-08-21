from bs4 import BeautifulSoup

def parse_matches(html):
    soup = BeautifulSoup(html, "html.parser")

    matches = []

    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")

        for row in rows[1:]:  # skip header
            cols = row.find_all("td")

            if len(cols) < 4:
                continue

            try:
                date = cols[0].get_text(strip=True)
                players = cols[1].get_text(strip=True)
                score = cols[2].get_text(strip=True)
                result = cols[3].get_text(strip=True)

                match = {
                    "date": date,
                    "players": players,
                    "score": score,
                    "won": "W" in result or "Win" in result
                }

                matches.append(match)

            except Exception:
                continue

    return matches
