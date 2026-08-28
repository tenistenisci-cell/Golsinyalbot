import time
from datetime import datetime

import requests

TEST_URL = "https://example.com"


def test_connection():
    print("GOL SINYAL BOTU BASLADI")
    print("Tarih:", datetime.now())

    try:
        response = requests.get(
            TEST_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )

        response.raise_for_status()

        print("Internet baglantisi BASARILI")
        print("HTTP durum kodu:", response.status_code)

    except Exception as e:
        print("Baglanti hatasi:")
        print(type(e).__name__, str(e))


if __name__ == "__main__":
    test_connection()

    while True:
        time.sleep(3600)
