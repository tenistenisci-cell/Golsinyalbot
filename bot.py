import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

FLASHSCORE_URL = "https://m.flashscore.com.tr/"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get_matches():
    response = requests.get(
        FLASHSCORE_URL,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    print("GOL SINYAL BOTU BASLADI")
    print("Tarih:", datetime.now())
    print("FLASHSCORE MOBIL BAGLANTISI BASARILI")
    print(text[:5000])


if __name__ == "__main__":
    get_matches()

    while True:
        time.sleep(3600)
