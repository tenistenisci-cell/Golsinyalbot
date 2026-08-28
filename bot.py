import re
import time
from datetime import datetime

import requests

FLASHSCORE_URL = "https://www.flashscore.com.tr/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get_flashscore():
    response = requests.get(
        FLASHSCORE_URL,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()
    return response.text


def find_matches(html):
    matches = []

    pattern = r'"homeParticipantName":"([^"]+)".*?"awayParticipantName":"([^"]+)"'

    for home, away in re.findall(pattern, html):
        match = f"{home} - {away}"

        if match not in matches:
            matches.append(match)

    return matches


def run():
    print("GOL SINYAL BOTU BASLADI")
    print("Tarih:", datetime.now())

    try:
        html = get_flashscore()

        print("FLASHSCORE BAGLANTISI BASARILI")
        print("Veri boyutu:", len(html))

        matches = find_matches(html)

        print("Bulunan mac sayisi:", len(matches))

        for match in matches[:20]:
            print("MAC:", match)

    except Exception as e:
        print("HATA:")
        print(type(e).__name__, str(e))


if __name__ == "__main__":
    run()

    while True:
        time.sleep(3600)
