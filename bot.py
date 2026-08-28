import time
from datetime import datetime

import requests

FLASHSCORE_URL = "https://www.flashscore.com.tr/"


def test_flashscore():
    print("FLASHSCORE TESTI BASLADI")
    print("Tarih:", datetime.now())

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    }

    try:
        response = requests.get(
            FLASHSCORE_URL,
            headers=headers,
            timeout=20
        )

        print("HTTP durum kodu:", response.status_code)
        print("Alinan veri:", len(response.text), "karakter")

        if response.status_code == 200:
            print("FLASHSCORE BAGLANTISI BASARILI")
        else:
            print("FLASHSCORE ERISIM SAGLAMADI")

    except Exception as e:
        print("FLASHSCORE BAGLANTI HATASI")
        print(type(e).__name__, str(e))


if __name__ == "__main__":
    test_flashscore()

    while True:
        time.sleep(3600)
