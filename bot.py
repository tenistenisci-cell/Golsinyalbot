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


def get_live_matches():
    soup = get_soup(BASE_URL)
    matches = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)

        if "/mac/" not in href:
            continue

        if not re.fullmatch(r"\d+\s*-\s*\d+", text):
            continue

        if href.startswith("/"):
            href = BASE_URL.rstrip("/") + href

        parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""

        if href not in [x["url"] for x in matches]:
            matches.append({
                "url": href,
                "score": text,
                "raw": parent_text
            })

    return matches


def number(text):
    try:
        return float(text.replace(",", ".").replace("%", "").strip())
    except:
        return 0.0


def pair(text):
    m = re.fullmatch(r"([\d.,]+)\s*-\s*([\d.,]+)", text.strip())

    if not m:
        return None

    return number(m.group(1)), number(m.group(2))


def get_stats(match_url):
    url = match_url.rstrip("/") + "/?t=istatistik"
    soup = get_soup(url)

    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    title = soup.find("h3")
    match_name = title.get_text(" ", strip=True) if title else "Bilinmeyen maç"

    wanted = {
        "Gol beklentisi (xG)": "xg",
        "Toplam şut": "shots",
        "İsabetli şut": "sot",
        "Büyük şans": "big",
        "Kornerler": "corners",
    }

    stats = {
        "xg": (0, 0),
        "shots": (0, 0),
        "sot": (0, 0),
        "big": (0, 0),
        "corners": (0, 0),
    }

    for i, line in enumerate(lines):

        if line not in wanted:
            continue

        key = wanted[line]

        candidates = []

        if i > 0:
            candidates.append(lines[i - 1])

        if i + 1 < len(lines):
            candidates.append(lines[i + 1])

        if i + 2 < len(lines):
            candidates.append(lines[i + 2])

        for candidate in candidates:
            values = pair(candidate)

            if values:
                stats[key] = values
                break

    return match_name, stats


def calculate_signal(stats):
    xg = sum(stats["xg"])
    shots = sum(stats["shots"])
    sot = sum(stats["sot"])
    big = sum(stats["big"])
    corners = sum(stats["corners"])

    points = 0

    # xG
    if xg >= 2.0:
        points += 30
    elif xg >= 1.3:
        points += 22
    elif xg >= 0.8:
        points += 14
    elif xg >= 0.4:
        points += 7

    # Toplam şut
    if shots >= 20:
        points += 25
    elif shots >= 14:
        points += 18
    elif shots >= 9:
        points += 10

    # İsabetli şut
    if sot >= 8:
        points += 25
    elif sot >= 5:
        points += 18
    elif sot >= 3:
        points += 10

    # Büyük şans
    if big >= 4:
        points += 15
    elif big >= 2:
        points += 10
    elif big >= 1:
        points += 5

    # Korner
    if corners >= 10:
        points += 10
    elif corners >= 6:
        points += 6
    elif corners >= 3:
        points += 3

    return min(points, 100)


def run():
    print("\n==============================")
    print("GOL SINYAL TARAMASI")
    print("==============================")

    try:
        matches = get_live_matches()

        print("CANLI MAC:", len(matches))

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
                    print("🚨🚨 GOL SINYALI - COK GUCLU")

                elif signal >= 55:
                    print("🚨 GOL SINYALI - GUCLU")

                elif signal >= 40:
                    print("⚠️ GOL IHTIMALI ARTIYOR")

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
