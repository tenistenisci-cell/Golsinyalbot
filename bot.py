import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://m.flashscore.com.tr/"
LIVE_URL = "https://m.flashscore.com.tr/?s=2"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def get_live_matches():
    try:
        r = session.get(LIVE_URL, timeout=25)

        print("FLASHSCORE HTTP:", r.status_code, flush=True)

        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        matches = []

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")

            # Canlı maç detay linkleri /mac/... biçiminde
            if "/mac/" not in href:
                continue

            score = a.get_text(" ", strip=True)

            # Skor formatı değilse geç
            if not score or "-" not in score:
                continue

            parent = a.parent

            if parent is None:
                continue

            text = parent.get_text(" ", strip=True)

            # Takım isimlerini ve dakikayı parent metninden alacağız
            if score not in text:
                continue

            before_score = text.rsplit(score, 1)[0].strip()

            # Örnek:
            # 52'Iwaki - Albirex Niigata
            # Devre Arası Iwaki - Albirex Niigata

            minute = ""

            if "Devre Arası" in before_score:
                minute = "Devre Arası"
                teams_text = before_score.replace(
                    "Devre Arası",
                    "",
                    1
                ).strip()

            elif "Uzatma" in before_score:
                minute = "Uzatma"
                teams_text = before_score.replace(
                    "Uzatma",
                    "",
                    1
                ).strip()

            else:
                import re

                m = re.match(
                    r"^(\d+(?:\+\d+)?')(.+)$",
                    before_score
                )

                if not m:
                    continue

                minute = m.group(1)
                teams_text = m.group(2).strip()

            if " - " not in teams_text:
                continue

            home, away = teams_text.split(" - ", 1)

            home = home.strip()
            away = away.strip()

            if not home or not away:
                continue

            url = urljoin(BASE_URL, href)

            # Aynı maç iki kere eklenmesin
            if any(x["url"] == url for x in matches):
                continue

            matches.append({
                "home": home,
                "away": away,
                "minute": minute,
                "score": score,
                "url": url,
            })

        return matches

    except Exception as e:
        print(
            "CANLI MAC HATASI:",
            type(e).__name__,
            str(e),
            flush=True
        )
        return []


print("CANLI MAC TEST BOTU BASLADI", flush=True)

while True:
    print(
        "\n==============================",
        flush=True
    )

    print(
        "YENI CANLI MAC TARAMASI",
        flush=True
    )

    matches = get_live_matches()

    print(
        "CANLI MAC SAYISI:",
        len(matches),
        flush=True
    )

    for match in matches:
        print(
            f"{match['minute']} | "
            f"{match['home']} - {match['away']} | "
            f"{match['score']}",
            flush=True
        )

    # Railway loglarını şişirmemek için 60 saniye
    time.sleep(60)
