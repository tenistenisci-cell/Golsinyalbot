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


def flashscore_kontrol():
    print("GOL SINYAL BOTU BASLADI")
    print("Tarih:", datetime.now())

    try:
        response = requests.get(
            FLASHSCORE_URL,
            headers=HEADERS,
            timeout=20
        )

        print("HTTP:", response.status_code)
        print("Veri boyutu:", len(response.text))

        if response.status_code == 200:
            print("FLASHSCORE BAGLANTISI BASARILI")
        else:
            print("FLASHSCORE ERISIM HATASI")

    except Exception as e:
        print("HATA:", type(e).__name__, str(e))


if __name__ == "__main__":
    flashscore_kontrol()

    while True:
        time.sleep(60)
