import re
import time
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from urllib.parse import urljoin, urlsplit

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


# =========================================================
# CANLI MAC SATIRINI OKU
# =========================================================

def get_text_before_score(score_link):
    pieces = []
    sibling = score_link.previous_sibling

    while sibling is not None:

        if isinstance(sibling, Tag):

            if sibling.name == "br":
                break

            text = sibling.get_text(
                " ",
                strip=True
            )

            if text:
                pieces.append(text)

        elif isinstance(
            sibling,
            NavigableString
        ):

            text = str(sibling).strip()

            if text:
                pieces.append(text)

        sibling = sibling.previous_sibling

    pieces.reverse()

    return " ".join(pieces).strip()


# =========================================================
# DAKIKA + TAKIMLAR
# =========================================================

def parse_match_line(text):
    text = " ".join(text.split())

    if text.startswith("Devre Arası"):

        minute = "Devre Arası"

        teams = text[
            len("Devre Arası"):
        ].strip()

    else:

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

    home, away = teams.split(
        " - ",
        1
    )

    home = home.strip()
    away = away.strip()

    if not home or not away:
        return None

    return {
        "minute": minute,
        "home": home,
        "away": away,
    }


# =========================================================
# CANLI MACLAR
# =========================================================

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


# =========================================================
# MATCH ID
# =========================================================

def get_match_id(match_url):
    try:

        path = urlsplit(
            match_url
        ).path

        parts = [
            x
            for x in path.split("/")
            if x
        ]

        if not parts:
            return None

        match_id = parts[-1]

        return match_id

    except Exception:
        return None


# =========================================================
# SAYI TEMIZLE
# =========================================================

def clean_number(value):

    if value is None:
        return None

    value = str(value)

    value = value.replace(
        "%",
        ""
    )

    value = value.replace(
        ",",
        "."
    )

    value = value.strip()

    try:

        number = float(value)

        if number.is_integer():
            return int(number)

        return number

    except Exception:

        return value


# =========================================================
# ISTATISTIK PARSER
# =========================================================

def parse_stats_feed(text):

    result = {
        "xg_home": None,
        "xg_away": None,
        "shots_home": None,
        "shots_away": None,
        "sot_home": None,
        "sot_away": None,
        "corners_home": None,
        "corners_away": None,
        "big_home": None,
        "big_away": None,
    }

    parts = text.split("~")

    current_name = None
    home_value = None
    away_value = None

    def save_stat(
        name,
        home,
        away
    ):

        if not name:
            return

        low = name.lower().strip()

        if (
            "expected goals" in low
            or "beklenen gol" in low
            or low == "xg"
        ):

            result["xg_home"] = clean_number(
                home
            )

            result["xg_away"] = clean_number(
                away
            )

        elif (
            "total shots" in low
            or "toplam şut" in low
            or low == "şutlar"
            or low == "shots"
        ):

            result["shots_home"] = clean_number(
                home
            )

            result["shots_away"] = clean_number(
                away
            )

        elif (
            "shots on target" in low
            or "isabetli şut" in low
        ):

            result["sot_home"] = clean_number(
                home
            )

            result["sot_away"] = clean_number(
                away
            )

        elif (
            "corner kicks" in low
            or "corners" in low
            or "korner" in low
        ):

            result["corners_home"] = clean_number(
                home
            )

            result["corners_away"] = clean_number(
                away
            )

        elif (
            "big chances" in low
            or "büyük şans" in low
            or "buyuk sans" in low
        ):

            result["big_home"] = clean_number(
                home
            )

            result["big_away"] = clean_number(
                away
            )

    for part in parts:

        if "÷" not in part:
            continue

        key, value = part.split(
            "÷",
            1
        )

        key = key.strip()
        value = value.strip()

        if key == "SA":

            if current_name is not None:

                save_stat(
                    current_name,
                    home_value,
                    away_value
                )

            current_name = value
            home_value = None
            away_value = None

        elif key == "SG":

            home_value = value

        elif key == "SH":

            away_value = value

    if current_name is not None:

        save_stat(
            current_name,
            home_value,
            away_value
        )

    return result


# =========================================================
# ISTATISTIK ISTEGI
# =========================================================

def get_statistics(match, show_raw=False):

    match_id = get_match_id(
        match["url"]
    )

    print(
        "MATCH ID:",
        match_id,
        flush=True
    )

    if not match_id:

        print(
            "MATCH ID BULUNAMADI",
            flush=True
        )

        return None

    urls = [
        (
            "https://2.flashscore.ninja/"
            f"2/x/feed/df_st_1_{match_id}"
        ),
        (
            "https://1.flashscore.ninja/"
            f"1/x/feed/df_st_1_{match_id}"
        ),
    ]

    for url in urls:

        try:

            r = session.get(
                url,
                headers={
                    **HEADERS,
                    "x-fsign": "SW9D1eZo",
                    "Referer": BASE_URL,
                },
                timeout=20
            )

            print(
                "STAT HTTP:",
                r.status_code,
                flush=True
            )

            if not r.ok:
                continue

            raw = r.text.strip()

            if not raw:

                print(
                    "STAT CEVABI BOS",
                    flush=True
                )

                continue

            if show_raw:

                print(
                    "\n========== HAM STAT VERISI ==========",
                    flush=True
                )

                print(
                    raw[:4000],
                    flush=True
                )

                print(
                    "========== HAM STAT SONU ==========\n",
                    flush=True
                )

            stats = parse_stats_feed(
                raw
            )

            return stats

        except Exception as e:

            print(
                "STAT HATASI:",
                type(e).__name__,
                str(e),
                flush=True
            )

    return None


# =========================================================
# TEST
# =========================================================

print(
    "HAM ISTATISTIK TEST BOTU BASLADI",
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

        raw_gosterildi = False

        # İlk 5 maçı dene.
        # HAM veri sadece bir kez yazılır.
        for match in matches[:5]:

            print(
                "\n----------------------------",
                flush=True
            )

            print(
                "MAC:",
                match["home"],
                "-",
                match["away"],
                flush=True
            )

            print(
                "DAKIKA:",
                match["minute"],
                flush=True
            )

            print(
                "SKOR:",
                match["score"],
                flush=True
            )

            stats = get_statistics(
                match,
                show_raw=not raw_gosterildi
            )

            if stats is None:

                print(
                    "ISTATISTIK: VERI YOK",
                    flush=True
                )

                continue

            if not raw_gosterildi:
                raw_gosterildi = True

            print(
                "xG:",
                stats["xg_home"],
                "-",
                stats["xg_away"],
                flush=True
            )

            print(
                "SUT:",
                stats["shots_home"],
                "-",
                stats["shots_away"],
                flush=True
            )

            print(
                "ISABETLI:",
                stats["sot_home"],
                "-",
                stats["sot_away"],
                flush=True
            )

            print(
                "BUYUK SANS:",
                stats["big_home"],
                "-",
                stats["big_away"],
                flush=True
            )

            print(
                "KORNER:",
                stats["corners_home"],
                "-",
                stats["corners_away"],
                flush=True
            )

    except Exception as e:

        print(
            "ANA HATA:",
            type(e).__name__,
            str(e),
            flush=True
        )

    # Logu şişirmemek için 5 dakika
    time.sleep(300)
