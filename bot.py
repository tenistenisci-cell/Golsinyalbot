import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://m.flashscore.com.tr"

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


def get_live_urls():
    soup = get_soup(BASE_URL + "/")
    found = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        score = a.get_text(" ", strip=True)

        if "/mac/" not in href:
            continue

        if not re.fullmatch(r"\d+\s*-\s*\d+", score):
            continue

        # Bu skor linkinin ait olduğu en küçük maç satırını bul
        node = a
        live = False

        for _ in range(5):
            if node is None:
                break

            text = node.get_text(" ", strip=True)

            if re.search(r"\b\d{1,3}(?:\+)?'", text):
                live = True
                break

            if "Devre Arası" in text:
                live = True
                break

            node = node.parent

        if not live:
            continue

        if href.startswith("/"):
            url = BASE_URL + href
        else:
            url = href

        if url not in seen:
            seen.add(url)
            found.append(url)

    return found


def get_match_info(match_url):
    soup = get_soup(match_url)

    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    title = soup.find("h3")

    if title:
        name = title.get_text(" ", strip=True)
    else:
        name = "Bilinmeyen mac"

    score = "?"
    minute = "?"

    # Maç detay sayfasındaki skor
    for line in lines:
        m = re.match(r"^(\d+)\s*-\s*(\d+)", line)

        if m:
            score = f"{m.group(1)}-{m.group(2)}"
            break

    # Dakikayı doğrudan AYNI maçın detay sayfasından al
    full_text = " ".join(lines)

    minute_match = re.search(
        r"(?:1\.\s*yarı|2\.\s*yarı)\s*-\s*(\d{1,3}(?:\+)?)'",
        full_text,
        re.IGNORECASE
    )

    if minute_match:
        minute = minute_match.group(1) + "'"

    elif "Devre Arası" in full_text:
        minute = "Devre Arası"

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

        if i == 0 or i + 1 >= len(lines):
            continue

        left = to_number(lines[i - 1])
        right = to_number(lines[i + 1])

        if left is not None and right is not None:
            stats[wanted[line]] = (left, right)

    return stats


def total(value):
    if value is None:
        return None

    return value[0] + value[1]


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


def signal_text(points):
    if points >= 70:
        return "COK GUCLU"

    if points >= 55:
        return "GUCLU"

    if points >= 40:
        return "GOL IHTIMALI ARTIYOR"

    return "BASKI YETERSIZ"


def run():
    print(
        "\n===== GOL SINYAL TARAMASI =====",
        flush=True
    )

    try:
        urls = get_live_urls()

        print(
            "CANLI MAC SAYISI:",
            len(urls),
            flush=True
        )

        for url in urls:
            try:
                name, minute, score = get_match_info(url)
                stats = get_stats(url)
                points = calculate_signal(stats)

                block = (
                    "\n==============================\n"
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
