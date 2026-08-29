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
    "Accept": "*/*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.flashscore.com.tr/",
    "Origin": "https://www.flashscore.com.tr",
    "x-fsign": "SW9D1eZo",
}

session = requests.Session()
session.headers.update(HEADERS)


def clean_text(value):
    if value is None:
        return None

    value = str(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()

    if not value:
        return None

    return value


def to_number(value):
    if value is None:
        return None

    value = clean_text(value)

    if not value:
        return None

    value = value.replace("%", "")
    value = value.replace(",", ".")

    m = re.search(r"-?\d+(?:\.\d+)?", value)

    if not m:
        return None

    try:
        return float(m.group())
    except Exception:
        return None


def get_text_before_score(score_link):
    pieces = []
    sibling = score_link.previous_sibling

    while sibling is not None:

        if isinstance(sibling, Tag):

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

    text = " ".join(pieces)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def get_match_id(href):
    if not href:
        return None

    patterns = [
        r"/match/[^/]+/([A-Za-z0-9]{8})",
        r"/match/([A-Za-z0-9]{8})",
        r"match/[^/]+/([A-Za-z0-9]{8})",
        r"match/([A-Za-z0-9]{8})",
    ]

    for pattern in patterns:

        m = re.search(pattern, href)

        if m:
            return m.group(1)

    parts = [
        x for x in href.split("/")
        if x
    ]

    for part in reversed(parts):

        part = part.split("?")[0]
        part = part.split("#")[0]

        if re.fullmatch(r"[A-Za-z0-9]{8}", part):
            return part

    return None


def parse_live_matches():
    response = session.get(
        LIVE_URL,
        timeout=20
    )

    print(
        "LIVE HTTP:",
        response.status_code,
        flush=True
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    matches = []

    score_links = soup.find_all(
        "a",
        href=re.compile(r"/match/")
    )

    seen = set()

    for link in score_links:

        href = link.get("href", "")

        match_id = get_match_id(href)

        if not match_id:
            continue

        if match_id in seen:
            continue

        score_text = clean_text(
            link.get_text(" ", strip=True)
        )

        if not score_text:
            continue

        score_match = re.search(
            r"(\d+)\s*[-:]\s*(\d+)",
            score_text
        )

        if not score_match:
            continue

        home_score = int(score_match.group(1))
        away_score = int(score_match.group(2))

        before = get_text_before_score(link)

        minute_match = re.search(
            r"(\d{1,3})['’]?",
            before or ""
        )

        if not minute_match:
            continue

        minute = int(minute_match.group(1))

        if minute < 1 or minute > 130:
            continue

        text_without_minute = re.sub(
            r"\b\d{1,3}['’]?\b",
            "",
            before or "",
            count=1
        )

        text_without_minute = clean_text(
            text_without_minute
        )

        home = None
        away = None

        if text_without_minute:

            separators = [
                " - ",
                " – ",
                " — ",
            ]

            for sep in separators:

                if sep in text_without_minute:

                    parts = text_without_minute.split(
                        sep,
                        1
                    )

                    home = clean_text(parts[0])
                    away = clean_text(parts[1])

                    break

        if not home or not away:

            parent_text = clean_text(
                link.parent.get_text(
                    " ",
                    strip=True
                )
            )

            if parent_text:

                temp = re.sub(
                    r"\b\d{1,3}['’]?\b",
                    "",
                    parent_text,
                    count=1
                )

                temp = re.sub(
                    r"\b\d+\s*[-:]\s*\d+\b",
                    "",
                    temp
                )

                temp = clean_text(temp)

                for sep in [
                    " - ",
                    " – ",
                    " — ",
                ]:

                    if sep in temp:

                        p = temp.split(
                            sep,
                            1
                        )

                        home = clean_text(p[0])
                        away = clean_text(p[1])

                        break

        if not home or not away:
            continue

        seen.add(match_id)

        matches.append({
            "match_id": match_id,
            "home": home,
            "away": away,
            "minute": minute,
            "home_score": home_score,
            "away_score": away_score,
            "url": urljoin(
                BASE_URL,
                href
            ),
        })

    return matches


def empty_stats():
    return {
        "xg_home": None,
        "xg_away": None,

        "shots_home": None,
        "shots_away": None,

        "sot_home": None,
        "sot_away": None,

        "big_home": None,
        "big_away": None,

        "corners_home": None,
        "corners_away": None,
    }


def normalize_stat_name(name):
    if not name:
        return ""

    name = name.lower()

    replacements = {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
    }

    for old, new in replacements.items():
        name = name.replace(
            old,
            new
        )

    return clean_text(name) or ""


def detect_stat_type(name):
    name = normalize_stat_name(name)

    if (
        "expected goals" in name
        or name == "xg"
        or "beklenen gol" in name
    ):
        return "xg"

    if (
        "shots on target" in name
        or "shots on goal" in name
        or "kaleyi bulan" in name
        or "isabetli sut" in name
    ):
        return "sot"

    if (
        "total shots" in name
        or name == "shots"
        or "toplam sut" in name
        or "sutlar" == name
    ):
        return "shots"

    if (
        "big chances" in name
        or "clear-cut chances" in name
        or "buyuk sans" in name
        or "net gol pozisyon" in name
    ):
        return "big"

    if (
        "corner kicks" in name
        or name == "corners"
        or "korner" in name
    ):
        return "corners"

    return None


def parse_flashscore_feed(text):
    stats = empty_stats()

    if not text:
        return stats

    # Flashscore feed ayırıcıları
    text = (
        text
        .replace("¬", "\n")
        .replace("~", "\n")
    )

    lines = [
        clean_text(x)
        for x in text.splitlines()
    ]

    lines = [
        x for x in lines
        if x
    ]

    # Örnek mantık:
    # SG÷Expected Goals (xG)¬SH÷1.21¬SI÷0.74
    #
    # veya
    # SG÷Shots on Target¬SH÷4¬SI÷2

    current_stat = None

    temp_home = None
    temp_away = None

    def save_current():

        nonlocal current_stat
        nonlocal temp_home
        nonlocal temp_away

        if not current_stat:
            return

        if temp_home is None or temp_away is None:
            return

        if current_stat == "xg":

            stats["xg_home"] = temp_home
            stats["xg_away"] = temp_away

        elif current_stat == "shots":

            stats["shots_home"] = temp_home
            stats["shots_away"] = temp_away

        elif current_stat == "sot":

            stats["sot_home"] = temp_home
            stats["sot_away"] = temp_away

        elif current_stat == "big":

            stats["big_home"] = temp_home
            stats["big_away"] = temp_away

        elif current_stat == "corners":

            stats["corners_home"] = temp_home
            stats["corners_away"] = temp_away

    for line in lines:

        if "÷" not in line:
            continue

        key, value = line.split(
            "÷",
            1
        )

        key = key.strip()
        value = clean_text(value)

        possible = detect_stat_type(
            value
        )

        if possible:

            save_current()

            current_stat = possible
            temp_home = None
            temp_away = None

            continue

        if not current_stat:
            continue

        # Flashscore istatistik feedlerinde
        # ev/deplasman değerleri farklı anahtarlarla gelebiliyor.
        #
        # En sık SH/SI veya SJ/SK görülüyor.

        if key in {
            "SH",
            "SJ",
            "SE",
            "SO",
        }:

            number = to_number(value)

            if number is not None:

                if temp_home is None:
                    temp_home = number

                elif temp_away is None:
                    temp_away = number

        elif key in {
            "SI",
            "SK",
            "SF",
            "SP",
        }:

            number = to_number(value)

            if number is not None:

                if temp_away is None:
                    temp_away = number

    save_current()

    # İkinci yöntem:
    # İstatistik adı + iki sayı aynı bölümdeyse yakala.

    wanted = [
        (
            "xg",
            [
                "expected goals",
                "beklenen gol",
                "xg",
            ]
        ),
        (
            "sot",
            [
                "shots on target",
                "shots on goal",
                "kaleyi bulan",
                "isabetli sut",
            ]
        ),
        (
            "shots",
            [
                "total shots",
                "toplam sut",
            ]
        ),
        (
            "big",
            [
                "big chances",
                "buyuk sans",
                "net gol pozisyon",
            ]
        ),
        (
            "corners",
            [
                "corner kicks",
                "corners",
                "korner",
            ]
        ),
    ]

    plain = normalize_stat_name(text)

    for stat_type, names in wanted:

        already = False

        if stat_type == "xg":
            already = (
                stats["xg_home"] is not None
                and stats["xg_away"] is not None
            )

        elif stat_type == "shots":
            already = (
                stats["shots_home"] is not None
                and stats["shots_away"] is not None
            )

        elif stat_type == "sot":
            already = (
                stats["sot_home"] is not None
                and stats["sot_away"] is not None
            )

        elif stat_type == "big":
            already = (
                stats["big_home"] is not None
                and stats["big_away"] is not None
            )

        elif stat_type == "corners":
            already = (
                stats["corners_home"] is not None
                and stats["corners_away"] is not None
            )

        if already:
            continue

        for name in names:

            pos = plain.find(name)

            if pos == -1:
                continue

            chunk = plain[
                pos:
                pos + 250
            ]

            numbers = re.findall(
                r"\d+(?:[.,]\d+)?",
                chunk
            )

            if len(numbers) < 2:
                continue

            a = to_number(numbers[0])
            b = to_number(numbers[1])

            if a is None or b is None:
                continue

            if stat_type == "xg":

                stats["xg_home"] = a
                stats["xg_away"] = b

            elif stat_type == "shots":

                stats["shots_home"] = a
                stats["shots_away"] = b

            elif stat_type == "sot":

                stats["sot_home"] = a
                stats["sot_away"] = b

            elif stat_type == "big":

                stats["big_home"] = a
                stats["big_away"] = b

            elif stat_type == "corners":

                stats["corners_home"] = a
                stats["corners_away"] = b

            break

    return stats


def get_match_stats(match_id):

    # Flashscore ayrıntılı istatistik feed'i
    urls = [
        (
            "https://local-global.flashscore.ninja/"
            "2/x/feed/df_st_1_"
            + match_id
        ),

        (
            "https://d.flashscore.com/"
            "x/feed/df_st_1_"
            + match_id
        ),
    ]

    last_status = None
    last_text = ""

    for url in urls:

        try:

            response = session.get(
                url,
                timeout=20,
                headers={
                    **HEADERS,
                    "x-fsign": "SW9D1eZo",
                    "Referer": (
                        "https://www.flashscore.com.tr/"
                        f"match/{match_id}/"
                    ),
                }
            )

            last_status = response.status_code
            last_text = response.text

            print(
                "STAT URL:",
                url,
                flush=True
            )

            print(
                "STAT HTTP:",
                response.status_code,
                flush=True
            )

            print(
                "STAT LENGTH:",
                len(response.text),
                flush=True
            )

            # İlk 200 karakteri logla.
            # Böylece yine veri gelmezse
            # ne döndüğünü direkt göreceğiz.
            print(
                "STAT RAW:",
                repr(response.text[:200]),
                flush=True
            )

            if response.status_code != 200:
                continue

            if not response.text.strip():
                continue

            if (
                "Unauthorized" in response.text
                or response.text.strip() == "401"
            ):
                continue

            stats = parse_flashscore_feed(
                response.text
            )

            if any(
                value is not None
                for value in stats.values()
            ):
                return stats

        except Exception as e:

            print(
                "STAT HATA:",
                type(e).__name__,
                str(e),
                flush=True
            )

    print(
        "STAT VERI BULUNAMADI:",
        match_id,
        "HTTP:",
        last_status,
        "UZUNLUK:",
        len(last_text),
        flush=True
    )

    return empty_stats()


print(
    "GOL SINYAL BOTU BASLADI",
    flush=True
)

while True:

    try:

        matches = parse_live_matches()

        print(
            "CANLI MAC SAYISI:",
            len(matches),
            flush=True
        )

        for match in matches:

            print(
                "\n--------------------------",
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
                str(match["minute"]) + "'",
                flush=True
            )

            print(
                "SKOR:",
                f'{match["home_score"]}-{match["away_score"]}',
                flush=True
            )

            print(
                "MATCH ID:",
                match["match_id"],
                flush=True
            )

            stats = get_match_stats(
                match["match_id"]
            )

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

    time.sleep(300)
