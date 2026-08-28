import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://m.flashscore.com.tr/"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def get_live_match_links():
    soup = get_soup(BASE_URL)
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/mac/" not in href:
            continue

        text = a.get_text(" ", strip=True)

        if not re.fullmatch(r"\d+\s*-\s*\d+", text):
            continue

        if href.startswith("/"):
            href = BASE_URL.rstrip("/") + href

        if href not in links:
            links.append(href)

    return links


def get_stats(match_url):
    stats_url = match_url.rstrip("/") + "/?t=istatistik"

    soup = get_soup(stats_url)
    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    wanted = [
        "Gol beklentisi (xG)",
        "Toplam şut",
        "İsabetli şut",
        "Büyük şans",
        "Kornerler",
        "Rakip ceza sahasında topla buluşma",
    ]

    found = {}

    for i, line in enumerate(lines):
        if line in wanted and i > 0 and i + 1 < len(lines):
            left = lines[i - 1]
            right = lines[i + 1]

            found[line] = (left, right)

    title = soup.find("h3")
    match_name = title.get_text(" ", strip=True) if title else match_url

    return match_name, found


def run():
    print("CANLI ISTATISTIK TESTI BASLADI")
    print("Tarih:", datetime.now())

    try:
        links = get_live_match_links()

        print("BULUNAN MAC LINKI:", len(links))

        for url in links[:3]:
            match_name, stats = get_stats(url)

            print("--------------------")
            print("MAC:", match_name)

            for name, values in stats.items():
                print(name + ":", values[0], "-", values[1])

    except Exception as e:
        print("HATA:", type(e).__name__, str(e))


if __name__ == "__main__":
    run()

    while True:
        time.sleep(3600)
