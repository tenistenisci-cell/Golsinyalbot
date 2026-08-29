import re
import time
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
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


def get_text_before_score(score_link):
    """
    Skor linkinin hemen önündeki aynı satırı toplar.
    <br> görünce durur.
    Böylece ligler ve diğer maçlar birbirine karışmaz.
    """

    pieces = []

    sibling = score_link.previous_sibling

    while sibling is not None:

        if isinstance(sibling, Tag):

            # Önceki maçın satırına geçme
            if sibling.name == "br":
                break

            text = sibling.get_text(" ", strip=True)

            if text:
                pieces.append(text)

        elif isinstance(sibling, NavigableString):

            text = str(sibling).strip()

            if text:
                pieces.append(text)

        sibling = sibling.previous_sibling

    pieces.reverse()

    return " ".join(pieces).strip()


def parse_match_line(text):
    """
    Örnekler:

    52'Iwaki - Albirex Niigata
    90+'Benesov - Povltavska FA
    Devre Arası G-Osaka - Hiroshima
    Uzatma Eastern Suburbs K - Brisbane City K
    """

    text = " ".join(text.split())

    minute = None
    teams = None

    # DEVRE ARASI
    if text.startswith("Devre Arası"):

        minute = "Devre Arası"

        teams = text[len("Devre Arası"):].strip()

    # UZATMA
    elif text.startswith("Uzatma"):

        minute = "Uzatma"

        teams = text[len("Uzatma"):].strip()

    else:

        # 52'
        # 90'
        # 90+3'
        m = re.match(
            r"^(\d+(?:\+\d+)?')\s*(.+)$",
            text
        )

        if not m:
            return None

        minute = m.group(1)
        teams = m.group(2).strip()

    if " - " not in teams:
        return None

    home, away = teams.split(" - ", 1)

    home = home.strip()
    away = away.strip()

    if not home or not away:
        return None

    return {
        "minute": minute,
        "home": home,
        "away": away,
    }


def get_live_matches():

    try:

        r = session.get(
            LIVE_URL,
            timeout=25
        )

        print(
            "FLASHSCORE HTTP:",
            r.status_code,
            flush=True
        )

        if not r.ok:
            return []

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        matches = []

        seen_urls = set()

        # Skorlar maç detay linkleridir
        for score_link in soup.find_all(
            "a",
            href=True
        ):

            href = score_link.get(
                "href",
                ""
            )

            if "/mac/" not in href:
                continue

            score = score_link.get_text(
                " ",
                strip=True
            )

            # Sadece 0-0 / 2-1 vb skorlar
            if not re.fullmatch(
                r"\d+\s*-\s*\d+",
                score
            ):
                continue

            url = urljoin(
                BASE_URL,
                href
            )

            if url in seen_urls:
                continue

            # Skorun hemen önündeki maç satırı
            line = get_text_before_score(
                score_link
            )

            parsed = parse_match_line(
                line
            )

            if not parsed:
                continue

            seen_urls.add(url)

            matches.append({
                "home": parsed["home"],
                "away": parsed["away"],
                "minute": parsed["minute"],
                "score": score.replace(
                    " ",
                    ""
                ),
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


print(
    "CANLI MAC TEST BOTU BASLADI",
    flush=True
)


while True:

    try:

        matches = get_live_matches()

        print(
            "\n============================",
            flush=True
        )

        print(
            "CANLI MAC SAYISI:",
            len(matches),
            flush=True
        )

        print(
            "============================",
            flush=True
        )

        for match in matches:

            print(
                f"{match['minute']} | "
                f"{match['home']} - "
                f"{match['away']} | "
                f"{match['score']}",
                flush=True
            )

    except Exception as e:

        print(
            "ANA HATA:",
            type(e).__name__,
            str(e),
            flush=True
        )

    # Railway logunu şişirmesin
    time.sleep(60)
