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
        return None


def is_live_status(text):
    return bool(
        re.fullmatch(r"\d{1,3}(?:\+)?'", text)
        or text == "Devre Arası"
    )


def get_live_matches():
    soup = get_soup(BASE_URL)

    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    live_rows = []

    # Önce doğru dakika + takım + skor bul
    for i, line in enumerate(lines):

        if not is_live_status(line):
            continue

        minute = line
        teams = None
        score = None

        for x in lines[i + 1:i + 7]:

            if teams is None and " - " in x:
                teams = x
                continue

            if teams and re.fullmatch(r"\d+\s*-\s*\d+", x):
                score = x
                break

        if teams and score:
            live_rows.append({
                "minute": minute,
                "teams": teams,
                "score": score,
                "url": None
            })

    # Sonra takım + skor ile doğru maç linkini eşleştir
    score_links = []

    for a in soup.find_all("a", href=True):

        href = a["href"]
        text = a.get_text(" ", strip=True)

        if "/mac/" not in href:
            continue

        if not re.fullmatch(r"\d+\s*-\s*\d+", text):
            continue

        if href.startswith("/"):
            href = BASE_URL.rstrip("/") + href

        score_links.append((a, href, text))

    for row in live_rows:

        for a, href, score_text in score_links:

            if score_text != row["score"]:
                continue

            node = a

            for _ in range(7):

                if node is None:
                    break

                nearby = node.get_text(" ", strip=True)

                if row["teams"] in nearby:
                    row["url"] = href
                    break

                node = node.parent

            if row["url"]:
                break

    # Linki bulunabilenleri kullan
    return [
        x for x in live_rows
        if x["url"] is not None
    ]


def get_stats(match_url):

    url = match_url.rstrip("/") + "/?t=istatistik"
    soup = get_soup(url)

    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    wanted = {
        "Gol beklentisi (xG)": "xg",
        "Toplam şut": "shots",
        "İsabetli şut": "sot",
        "Büyük şans": "big",
        "Kornerler": "corners",
    }

    stats = {
        "xg": None,
        "shots": None,
        "sot": None,
        "big": None,
        "corners": None,
    }

    for i, line in enumerate(lines):

        if line not in wanted:
            continue

        if i == 0 or i + 1 >= len(lines):
            continue

        left = to_number(lines[i - 1])
        right = to_number(lines[i + 1])

        if left is not None and right is not None:
            stats[wanted[line]] = (left, right)

    return stats


def total(stat):

    if stat is None:
        return None

    return stat[0] + stat[1]


def calculate_signal(stats):

    points = 0

    xg = total(stats["xg"])
    shots = total(stats["shots"])
    sot = total(stats["sot"])
    big = total(stats["big"])
    corners = total(stats["corners"])

    if xg is not None:
        if xg >= 2.0:
            points += 30
        elif xg >= 1.3:
            points += 22
        elif xg >= 0.8:
            points += 14
        elif xg >= 0.4:
            points += 7

    if shots is not None:
        if shots >= 20:
            points += 25
        elif shots >= 14:
            points += 18
        elif shots >= 9:
            points += 10

    if sot is not None:
        if sot >= 8:
            points += 25
        elif sot >= 5:
            points += 18
        elif sot >= 3:
            points += 10

    if big is not None:
        if big >= 4:
            points += 15
        elif big >= 2:
            points += 10
        elif big >= 1:
            points += 5

    if corners is not None:
        if corners >= 10:
            points += 10
        elif corners >= 6:
            points += 6
        elif corners >= 3:
            points += 3

    return min(points, 100)


def show(stat):

    if stat is None:
        return "VERI YOK"

    return f"{stat[0]:g} - {stat[1]:g}"


def signal_text(score):

    if score >= 70:
        return "COK GUCLU"

    if score >= 55:
        return "GUCLU"

    if score >= 40:
        return "GOL IHTIMALI ARTIYOR"

    return "BASKI YETERSIZ"


def run():

    print(
        "\n===== GOL SINYAL TARAMASI =====",
        flush=True
    )

    try:

        matches = get_live_matches()

        print(
            "CANLI MAC SAYISI:",
            len(matches),
            flush=True
        )

        for match in matches:

            try:

                stats = get_stats(match["url"])
                points = calculate_signal(stats)

                block = (
                    "\n==============================\n"
                    f"MAC: {match['teams']}\n"
                    f"DAKIKA: {match['minute']}\n"
                    f"SKOR: {match['score']}\n"
                    f"xG: {show(stats['xg'])}\n"
                    f"SUT: {show(stats['shots'])}\n"
                    f"ISABETLI: {show(stats['sot'])}\n"
                    f"BUYUK SANS: {show(stats['big'])}\n"
                    f"KORNER: {show(stats['corners'])}\n"
                    f"GOL PUANI: {points}\n"
                    f"SINYAL: {signal_text(points)}\n"
                    "=============================="
                )

                print(block, flush=True)

            except Exception as e:

                print(
                    "MAC HATASI:",
                    type(e).__name__,
                    str(e),
                    flush=True
                )

    except Exception as e:

        print(
            "GENEL HATA:",
            type(e).__name__,
            str(e),
            flush=True
        )


if __name__ == "__main__":

    while True:
        run()
        time.sleep(60)
