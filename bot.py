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


def get_text():
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    return soup.get_text("\n", strip=True)


def find_live_matches(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    live = []

    for line in lines:
        minute_live = re.match(r"^\d{1,3}'", line)
        extra_live = re.match(r"^\d{1,3}\+'", line)
        halftime = line.startswith("Devre Arası")

        if minute_live or extra_live or halftime:
            live.append(line)

    return live


def run():
    print("GOL SINYAL BOTU BASLADI")
    print("Tarih:", datetime.now())

    try:
        text = get_text()
        matches = find_live_matches(text)

        print("CANLI MAC SAYISI:", len(matches))

        if not matches:
            print("SU AN CANLI MAC BULUNAMADI")

        for match in matches:
            print("CANLI:", match)

    except Exception as e:
        print("HATA:", type(e).__name__, str(e))


if __name__ == "__main__":
    run()

    while True:
        time.sleep(60)
