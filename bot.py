import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

MACKOLIK_URL = "https://www.mackolik.com/iddaa"


def get_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()
    return response.text


def test_mackolik():
    print("GOL SINYAL BOTU BASLADI")
    print("Tarih:", datetime.now())

    try:
        html = get_page(MACKOLIK_URL)

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        title = (
            soup.title.get_text(" ", strip=True)
            if soup.title
            else "Bilinmiyor"
        )

        print("Mackolik baglantisi BASARILI")
        print("Sayfa basligi:", title)
        print("Alinan veri:", len(html), "karakter")

    except Exception as e:
        print("Mackolik hatasi:")
        print(type(e).__name__, str(e))


if __name__ == "__main__":
    test_mackolik()

    while True:
        time.sleep(3600)
