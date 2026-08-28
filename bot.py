import re
import time
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


def to_number(text):
    try:
        return float(
            text.replace(",", ".")
            .replace("%", "")
            .strip()
        )
    except:
        return 0.0


def get_match_links():
    soup = get_soup(BASE_URL)
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)

        if "/mac/" not in href:
            continue

        if not re.fullmatch(r"\d+\s*-\s*\d+", text):
            continue

        if href.startswith("/"):
            href = BASE_URL.rstrip("/") + href

        if href not in [x["url"] for x in links]:
            links.append({
                "url": href,
                "score": text
            })

    return links


def get_stats(match_url):
    stats_url = match_url.rstrip("/") + "/?t=istatistik"

    soup = get_soup(stats_url)

    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    title = soup.find("h3")

    if title:
        match_name = title.get_text(" ", strip=True)
    else:
        match_name = "Bilinmeyen mac"

    wanted = {
        "Gol beklentisi (xG)": "xg",
        "Toplam şut": "shots",
        "İsabetli şut": "sot",
        "Büyük şans": "big",
        "Kornerler": "corners",
    }

    stats = {
        "xg": (0.0, 0.0),
        "shots": (0.0, 0.0),
        "sot": (0.0, 0.0),
        "big": (0.0, 0.0),
        "corners": (0.0, 0.0),
    }

    for i, line in enumerate(lines):

        if line not in wanted:
            continue

        if i == 0 or i + 1 >= len(lines):
            continue

        left = to_number(lines[i - 1])
        right = to_number(lines[i + 1])

        stats[wanted[line]] = (left, right)

    return match_name, stats


def calculate_signal(stats):

    total_xg = sum(stats["xg"])
    total_shots = sum(stats["shots"])
    total_sot = sum(stats["sot"])
    total_big = sum(stats["big"])
    total_corners = sum(stats["corners"])

    points = 0

    # xG
    if total_xg >= 2.0:
        points += 30
    elif total_xg >= 1.3:
        points += 22
    elif total_xg >= 0.8:
        points += 14
    elif total_xg >= 0.4:
        points += 7

    # Sut
    if total_shots >= 20:
        points += 25
    elif total_shots >= 14:
        points += 18
    elif total_shots >= 9:
        points += 10

    # Isabetli sut
    if total_sot >= 8:
        points += 25
    elif total_sot >= 5:
        points += 18
    elif total_sot >= 3:
        points += 10

    # Buyuk sans
    if total_big >= 4:
        points += 15
    elif total_big >= 2:
        points += 10
    elif total_big >= 1:
        points += 5

    # Korner
    if total_corners >= 10:
        points += 10
    elif total_corners >= 6:
        points += 6
    elif total_corners >= 3:
        points += 3

    return min(points, 100)


def run():

    print("\n==============================")
    print("GOL SINYAL TARAMASI")
    print("==============================")

    try:
        matches = get_match_links()

        print("BULUNAN MAC:", len(matches))

        for match in matches:

            try:
                name, stats = get_stats(match["url"])
                signal = calculate_signal(stats)

                print("\n------------------------------")
                print("MAC:", name)
                print("SKOR:", match["score"])

                print(
                    "xG:",
                    stats["xg"][0],
                    "-",
                    stats["xg"][1]
                )

                print(
                    "SUT:",
                    stats["shots"][0],
                    "-",
                    stats["shots"][1]
                )

                print(
                    "ISABETLI:",
                    stats["sot"][0],
                    "-",
                    stats["sot"][1]
                )

                print(
                    "BUYUK SANS:",
                    stats["big"][0],
                    "-",
                    stats["big"][1]
                )

                print(
                    "KORNER:",
                    stats["corners"][0],
                    "-",
                    stats["corners"][1]
                )

                print("GOL PUANI:", signal)

                if signal >= 70:
                    print("GOL SINYALI: COK GUCLU")

                elif signal >= 55:
                    print("GOL SINYALI: GUCLU")

                elif signal >= 40:
                    print("GOL IHTIMALI ARTIYOR")

                else:
                    print("BASKI YETERSIZ")

            except Exception as e:
                print("MAC HATASI:", str(e))

    except Exception as e:
        print("GENEL HATA:", str(e))


if __name__ == "__main__":

    while True:
        run()
        time.sleep(60)
