import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://m.flashscore.com.tr"
LIVE_URL = BASE_URL + "/?s=2"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url):
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def number(text):
    try:
        return float(
            text.replace(",", ".")
            .replace("%", "")
            .strip()
        )
    except:
        return None


def find_homepage_minute(anchor):
    node = anchor

    for _ in range(6):
        if node is None:
            break

        text = node.get_text(" ", strip=True)

        m = re.search(
            r"(\d{1,3}(?:\+)?'|Devre Arası)",
            text
        )

        if m:
            return m.group(1)

        node = node.parent

    return None


def get_live_matches():
    soup = get_soup(LIVE_URL)

    matches = []
    seen = set()

    for a in soup.find_all("a", href=True):

        href = a.get("href", "")
        score = a.get_text(" ", strip=True)

        if "/mac/" not in href:
            continue

        if not re.fullmatch(r"\d+\s*-\s*\d+", score):
            continue

        if href.startswith("/"):
            url = BASE_URL + href
        else:
            url = href

        # Sadece maç kimliğine göre tek kayıt
        match_id = re.search(r"/mac/([^/]+)", url)

        if not match_id:
            continue

        match_id = match_id.group(1)

        if match_id in seen:
            continue

        seen.add(match_id)

        matches.append({
            "id": match_id,
            "url": url,
            "homepage_score": score,
            "homepage_minute": find_homepage_minute(a)
        })

    return matches


def get_match_info(match):
    soup = get_soup(match["url"])

    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    # Takım isimleri
    h3 = soup.find("h3")

    if h3:
        name = h3.get_text(" ", strip=True)
    else:
        name = "Bilinmeyen mac"

    # Skor
    score = match["homepage_score"]

    for line in lines:

        m = re.match(
            r"^(\d+)\s*-\s*(\d+)(?:\s*\([^)]*\))?$",
            line
        )

        if m:
            score = f"{m.group(1)}-{m.group(2)}"
            break

    # Dakika
    minute = None

    for line in lines:

        # Örnek: 1. yarı - 25'
        m = re.search(
            r"(?:1\.|2\.)\s*yarı\s*-\s*(\d{1,3}(?:\+)?)'",
            line,
            re.IGNORECASE
        )

        if m:
            minute = m.group(1) + "'"
            break

        if line == "Devre Arası":
            minute = "Devre Arası"
            break

    # Detay sayfasında bulunmazsa canlı liste dakikasını kullan
    if minute is None:
        minute = match["homepage_minute"]

    if minute is None:
        minute = "?"

    return name, minute, score


def get_stats(match_url):
    stats_url = match_url.rstrip("/") + "/?t=istatistik"

    soup = get_soup(stats_url)

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

        if i < 1 or i + 1 >= len(lines):
            continue

        left = number(lines[i - 1])
        right = number(lines[i + 1])

        if left is not None and right is not None:
            stats[wanted[line]] = (left, right)

    return stats


def stat_total(value):
    if value is None:
        return None

    return value[0] + value[1]


def calculate_signal(stats):
    points = 0

    xg = stat_total(stats["xg"])
    shots = stat_total(stats["shots"])
    sot = stat_total(stats["sot"])
    big = stat_total(stats["big"])
    corners = stat_total(stats["corners"])

    # xG
    if xg is not None:
        if xg >= 2.0:
            points += 30
        elif xg >= 1.3:
            points += 22
        elif xg >= 0.8:
            points += 14
        elif xg >= 0.4:
            points += 7

    # Toplam şut
    if shots is not None:
        if shots >= 20:
            points += 25
        elif shots >= 14:
            points += 18
        elif shots >= 9:
            points += 10

    # İsabetli şut
    if sot is not None:
        if sot >= 8:
            points += 25
        elif sot >= 5:
            points += 18
        elif sot >= 3:
            points += 10

    # Büyük şans
    if big is not None:
        if big >= 4:
            points += 15
        elif big >= 2:
            points += 10
        elif big >= 1:
            points += 5

    # Korner
    if corners is not None:
        if corners >= 10:
            points += 10
        elif corners >= 6:
            points += 6
        elif corners >= 3:
            points += 3

    return min(points, 100)


def show(value):
    if value is None:
        return "VERI YOK"

    return f"{value[0]:g} - {value[1]:g}"


def signal_text(points):
    if points >= 70:
        return "COK GUCLU"

    if points >= 55:
        return "GUCLU"

    if points >= 40:
        return "GOL IHTIMALI ARTIYOR"

    return "BASKI YETERSIZ"


def scan():
    print(
        "\n\n===== GOL SINYAL TARAMASI =====",
        flush=True
    )

    try:
        matches = get_live_matches()

        print(
            f"CANLI MAC SAYISI: {len(matches)}",
            flush=True
        )

        for match in matches:

            try:
                name, minute, score = get_match_info(match)

                stats = get_stats(match["url"])

                points = calculate_signal(stats)

                output = (
                    "\n==============================\n"
                    f"MAC ID: {match['id']}\n"
                    f"MAC: {name}\n"
                    f"DAKIKA: {minute}\n"
                    f"SKOR: {score}\n"
                    f"xG: {show(stats['xg'])}\n"
                    f"SUT: {show(stats['shots'])}\n"
                    f"ISABETLI: {show(stats['sot'])}\n"
                    f"BUYUK SANS: {show(stats['big'])}\n"
                    f"KORNER: {show(stats['corners'])}\n"
                    f"GOL PUANI: {points}\n"
                    f"SINYAL: {signal_text(points)}\n"
                    "=============================="
                )

                print(output, flush=True)

            except Exception as e:
                print(
                    f"MAC HATASI [{match['id']}]: "
                    f"{type(e).__name__}: {e}",
                    flush=True
                )

    except Exception as e:
        print(
            f"GENEL HATA: {type(e).__name__}: {e}",
            flush=True
        )


if __name__ == "__main__":

    while True:

        scan()

        # Her 60 saniyede yeniden canlı veri çek
        time.sleep(60)
