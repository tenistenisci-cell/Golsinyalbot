import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://m.flashscore.com.tr/"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get_lines():
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    return [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]


def is_live_status(text):
    return (
        re.fullmatch(r"\d{1,3}'", text)
        or re.fullmatch(r"\d{1,3}\+'", text)
        or text in ["Devre Arası", "Devre"]
    )


def find_live_matches(lines):
    matches = []

    for i, line in enumerate(lines):

        if not is_live_status(line):
            continue

        status = line
        teams = None
        score = None

        for x in lines[i + 1:i + 6]:

            if teams is None and " - " in x:
                teams = x
                continue

            if teams and re.fullmatch(r"\d+\s*-\s*\d+", x):
                score = x
                break

        if teams and score:
            matches.append({
                "status": status,
                "teams": teams,
                "score": score
            })

    return matches


def run():
    print("GOL SINYAL BOTU BASLADI")
    print("Tarih:", datetime.now())

    try:
        lines = get_lines()
        matches = find_live_matches(lines)

        print("CANLI MAC SAYISI:", len(matches))

        for match in matches:
            print("--------------------")
            print("DAKIKA:", match["status"])
            print("MAC:", match["teams"])
            print("SKOR:", match["score"])

    except Exception as e:
        print("HATA:", type(e).__name__, str(e))


if __name__ == "__main__":
    run()

    while True:
        time.sleep(60)
