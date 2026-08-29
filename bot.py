import os
import re
import time
import unicodedata
import requests
from urllib.parse import urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup


BASE_URL = "https://m.flashscore.com.tr/"
LIVE_URL = "https://m.flashscore.com.tr/?s=2"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 "
        "Chrome/120.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

session = requests.Session()
session.headers.update(HEADERS)

stats_cache = {}
signal_memory = {}

cached_chat_id = None

STATS_CACHE_SECONDS = 600


def normalize_text(text):
    text = str(text).strip().casefold()

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def get_soup(url):
    r = session.get(
        url,
        timeout=25
    )

    r.raise_for_status()

    return BeautifulSoup(
        r.text,
        "html.parser"
    )


def clean_match_url(url):
    url = urljoin(
        BASE_URL,
        url
    )

    p = urlsplit(url)

    path = p.path

    if not path.endswith("/"):
        path += "/"

    return urlunsplit(
        (
            p.scheme,
            p.netloc,
            path,
            "",
            ""
        )
    )


def to_number(text):
    if text is None:
        return None

    text = (
        str(text)
        .replace(",", ".")
        .replace("%", "")
        .strip()
    )

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not m:
        return None

    try:
        return float(
            m.group(0)
        )

    except Exception:
        return None


def get_chat_id():
    global cached_chat_id

    if TELEGRAM_CHAT_ID:
        return str(
            TELEGRAM_CHAT_ID
        )

    if cached_chat_id:
        return cached_chat_id

    if not TELEGRAM_BOT_TOKEN:
        return None

    try:
        url = (
            "https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/"
            "getUpdates"
        )

        r = requests.get(
            url,
            timeout=20
        )

        data = r.json()

        if not data.get("ok"):
            print(
                "GETUPDATES HATASI:",
                data,
                flush=True
            )
            return None

        results = data.get(
            "result",
            []
        )

        for item in reversed(results):
            message = (
                item.get("message")
                or item.get(
                    "channel_post"
                )
            )

            if not message:
                continue

            chat = message.get(
                "chat",
                {}
            )

            chat_id = chat.get(
                "id"
            )

            if chat_id is not None:
                cached_chat_id = str(
                    chat_id
                )

                print(
                    "CHAT ID BULUNDU",
                    flush=True
                )

                return cached_chat_id

    except Exception as e:
        print(
            "CHAT ID HATASI:",
            type(e).__name__,
            str(e),
            flush=True
        )

    return None


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        print(
            "TELEGRAM TOKEN YOK",
            flush=True
        )
        return False

    chat_id = get_chat_id()

    if not chat_id:
        print(
            "CHAT ID BULUNAMADI",
            flush=True
        )
        return False

    try:
        url = (
            "https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/"
            "sendMessage"
        )

        r = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text
            },
            timeout=20
        )

        if r.ok:
            print(
                "TELEGRAM MESAJI GONDERILDI",
                flush=True
            )
            return True

        print(
            "TELEGRAM HATASI:",
            r.status_code,
            r.text,
            flush=True
        )

    except Exception as e:
        print(
            "TELEGRAM GONDERIM HATASI:",
            type(e).__name__,
            str(e),
            flush=True
        )

    return False


def get_live_matches():
    soup = get_soup(
        LIVE_URL
    )

    lines = [
        x.strip()
        for x in soup.get_text(
            "\n",
            strip=True
        ).splitlines()
        if x.strip()
    ]

    live_rows = []

    for i, line in enumerate(lines):

        is_minute = bool(
            re.fullmatch(
                r"\d{1,3}(?:\+\d+)?'",
                line
            )
        )

        is_half = (
            line == "Devre Arası"
        )

        if not (
            is_minute
            or is_half
        ):
            continue

        minute = line
        teams = None
        score = None

        for x in lines[
            i + 1:i + 9
        ]:

            if (
                teams is None
                and " - " in x
            ):
                teams = x
                continue

            if (
                teams
                and re.fullmatch(
                    r"\d+\s*-\s*\d+",
                    x
                )
            ):
                score = x
                break

        if teams and score:
            live_rows.append(
                {
                    "minute": minute,
                    "teams": teams,
                    "score": score,
                    "url": None
                }
            )

    score_links = []

    for a in soup.find_all(
        "a",
        href=True
    ):
        href = a.get(
            "href",
            ""
        )

        text = a.get_text(
            " ",
            strip=True
        )

        if "/mac/" not in href:
            continue

        if not re.fullmatch(
            r"\d+\s*-\s*\d+",
            text
        ):
            continue

        score_links.append(
            {
                "a": a,
                "score": text,
                "url": clean_match_url(
                    href
                )
            }
        )

    used_urls = set()

    for row in live_rows:

        for item in score_links:

            if (
                item["url"]
                in used_urls
            ):
                continue

            if (
                item["score"]
                != row["score"]
            ):
                continue

            node = item["a"]

            found = False

            for _ in range(10):

                if node is None:
                    break

                nearby = node.get_text(
                    " ",
                    strip=True
                )

                if (
                    row["teams"]
                    in nearby
                ):
                    row["url"] = (
                        item["url"]
                    )

                    used_urls.add(
                        item["url"]
                    )

                    found = True
                    break

                node = node.parent

            if found:
                break

    return [
        x
        for x in live_rows
        if x["url"]
    ]


def empty_stats():
    return {
        "xg": None,
        "shots": None,
        "sot": None,
        "big": None,
        "corners": None,
    }


def has_any_stats(stats):
    return any(
        value is not None
        for value in stats.values()
    )


def parse_stats_page(soup):
    lines = [
        x.strip()
        for x in soup.get_text(
            "\n",
            strip=True
        ).splitlines()
        if x.strip()
    ]

    normalized = [
        normalize_text(x)
        for x in lines
    ]

    aliases = {
        "gol beklentisi (xg)": "xg",
        "gol beklentisi xg": "xg",
        "toplam sut": "shots",
        "isabetli sut": "sot",
        "buyuk sans": "big",
        "kornerler": "corners",
        "korner": "corners",
    }

    stats = empty_stats()

    for i, line in enumerate(
        normalized
    ):

        key = aliases.get(line)

        if not key:
            continue

        left = None
        right = None

        for distance in range(
            1,
            4
        ):
            index = i - distance

            if index < 0:
                break

            value = to_number(
                lines[index]
            )

            if value is not None:
                left = value
                break

        for distance in range(
            1,
            4
        ):
            index = i + distance

            if index >= len(lines):
                break

            value = to_number(
                lines[index]
            )

            if value is not None:
                right = value
                break

        if (
            left is not None
            and right is not None
        ):
            stats[key] = (
                left,
                right
            )

    return stats


def merge_stats(
    new_stats,
    old_stats
):
    result = empty_stats()

    for key in result:

        if (
            new_stats.get(key)
            is not None
        ):
            result[key] = (
                new_stats[key]
            )

        elif (
            old_stats
            and old_stats.get(key)
            is not None
        ):
            result[key] = (
                old_stats[key]
            )

    return result


def get_stats(match_url):
    match_url = clean_match_url(
        match_url
    )

    stats_urls = [
        match_url
        + "?t=istatistik",

        match_url.rstrip("/")
        + "/?t=istatistik",
    ]

    best_stats = empty_stats()

    for attempt in range(
        1,
        4
    ):

        print(
            "ISTATISTIK DENEME:",
            attempt,
            flush=True
        )

        for stats_url in stats_urls:

            try:
                r = session.get(
                    stats_url,
                    timeout=25,
                    headers=HEADERS
                )

                r.raise_for_status()

                soup = BeautifulSoup(
                    r.text,
                    "html.parser"
                )

                current = (
                    parse_stats_page(
                        soup
                    )
                )

                best_stats = (
                    merge_stats(
                        current,
                        best_stats
                    )
                )

                if has_any_stats(
                    best_stats
                ):
                    stats_cache[
                        match_url
                    ] = {
                        "time": time.time(),
                        "stats":
                        best_stats.copy()
                    }

                    print(
                        "ISTATISTIK ALINDI",
                        flush=True
                    )

                    return best_stats

            except Exception as e:

                print(
                    "ISTATISTIK HATASI:",
                    type(e).__name__,
                    str(e),
                    flush=True
                )

        if attempt < 3:
            time.sleep(2)

    cached = stats_cache.get(
        match_url
    )

    if cached:

        age = (
            time.time()
            - cached["time"]
        )

        if (
            age
            <= STATS_CACHE_SECONDS
        ):
            print(
                "SON BASARILI ISTATISTIK "
                "KULLANILIYOR",
                flush=True
            )

            return cached[
                "stats"
            ].copy()

    print(
        "BU MAC ICIN "
        "ISTATISTIK ALINAMADI",
        flush=True
    )

    return empty_stats()


def total(value):
    if value is None:
        return None

    return (
        value[0]
        + value[1]
    )


def calculate_signal(stats):
    points = 0

    xg = total(
        stats["xg"]
    )

    shots = total(
        stats["shots"]
    )

    sot = total(
        stats["sot"]
    )

    big = total(
        stats["big"]
    )

    corners = total(
        stats["corners"]
    )

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

    return min(
        points,
        100
    )


def show(value):
    if value is None:
        return "VERI YOK"

    return (
        f"{value[0]:g} - "
        f"{value[1]:g}"
    )


def get_level(points):
    if points >= 70:
        return 3

    if points >= 55:
        return 2

    if points >= 40:
        return 1

    return 0


def level_text(level):
    if level == 3:
        return (
            "🔥 COK GUCLU "
            "GOL SINYALI"
        )

    if level == 2:
        return (
            "🟢 GUCLU "
            "GOL SINYALI"
        )

    if level == 1:
        return (
            "⚠️ GOL IHTIMALI "
            "ARTIYOR"
        )

    return "BASKI YETERSIZ"


def repeat_seconds(level):
    if level == 3:
        return 300

    if level == 2:
        return 480

    if level == 1:
        return 900

    return 999999


def should_send_signal(
    match_url,
    level
):
    now = time.time()

    info = signal_memory.get(
        match_url
    )

    if not info:
        return True

    old_level = info.get(
        "level",
        0
    )

    last_sent = info.get(
        "last_sent",
        0
    )

    if level > old_level:
        return True

    wait = repeat_seconds(
        level
    )

    if (
        now - last_sent
        >= wait
    ):
        return True

    return False


def remember_signal(
    match_url,
    level
):
    signal_memory[
        match_url
    ] = {
        "level": level,
        "last_sent":
        time.time()
    }


def reset_signal_if_low(
    match_url,
    level
):
    if level == 0:
        signal_memory.pop(
            match_url,
            None
        )


def handle_signal(
    match,
    stats,
    points
):
    level = get_level(
        points
    )

    reset_signal_if_low(
        match["url"],
        level
    )

    if level == 0:
        print(
            "BASKI YETERSIZ - "
            "TELEGRAM YOK",
            flush=True
        )
        return

    if not should_send_signal(
        match["url"],
        level
    ):
        print(
            "TEKRAR SURESI "
            "DOLMADI",
            flush=True
        )
        return

    message = (
        f"{level_text(level)}"
        "\n\n"
        f"⚽ {match['teams']}\n"
        f"⏱ Dakika: "
        f"{match['minute']}\n"
        f"📊 Skor: "
        f"{match['score']}\n"
        f"🎯 xG: "
        f"{show(stats['xg'])}\n"
        f"🥅 Sut: "
        f"{show(stats['shots'])}\n"
        f"🎯 Isabetli: "
        f"{show(stats['sot'])}\n"
        f"🔥 Buyuk sans: "
        f"{show(stats['big'])}\n"
        f"🚩 Korner: "
        f"{show(stats['corners'])}\n"
        f"📈 Gol puani: "
        f"{points}/100"
    )

    print(
        "TELEGRAM GONDERME "
        "DENEMESI:",
        match["teams"],
        flush=True
    )

    success = send_telegram(
        message
    )

    if success:
        remember_signal(
            match["url"],
            level
        )


def remove_finished_matches(
    live_matches
):
    live_urls = {
        x["url"]
        for x in live_matches
    }

    for key in list(
        signal_memory.keys()
    ):

        if key not in live_urls:
            signal_memory.pop(
                key,
                None
            )

    for key in list(
        stats_cache.keys()
    ):

        if key not in live_urls:
            stats_cache.pop(
                key,
                None
            )


def scan():
    print(
        "\n==========================",
        flush=True
    )

    print(
        "YENI GOL SINYAL TARAMASI",
        flush=True
    )

    print(
        "==========================",
        flush=True
    )

    try:
        matches = (
            get_live_matches()
        )

        print(
            "CANLI MAC SAYISI:",
            len(matches),
            flush=True
        )

        remove_finished_matches(
            matches
        )

        for match in matches:

            try:
                stats = get_stats(
                    match["url"]
                )

                if not has_any_stats(
                    stats
                ):
                    print(
                        "\nMAC:",
                        match["teams"],
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

                    print(
                        "ISTATISTIK: "
                        "VERI YOK",
                        flush=True
                    )

                    print(
                        "SINYAL "
                        "HESAPLANMADI",
                        flush=True
                    )

                    continue

                points = (
                    calculate_signal(
                        stats
                    )
                )

                print(
                    "\n--------------------------",
                    flush=True
                )

                print(
                    "MAC:",
                    match["teams"],
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

                print(
                    "xG:",
                    show(
                        stats["xg"]
                    ),
                    flush=True
                )

                print(
                    "SUT:",
                    show(
                        stats["shots"]
                    ),
                    flush=True
                )

                print(
                    "ISABETLI:",
                    show(
                        stats["sot"]
                    ),
                    flush=True
                )

                print(
                    "BUYUK SANS:",
                    show(
                        stats["big"]
                    ),
                    flush=True
                )

                print(
                    "KORNER:",
                    show(
                        stats["corners"]
                    ),
                    flush=True
                )

                print(
                    "GOL PUANI:",
                    points,
                    flush=True
                )

                print(
                    "SEVIYE:",
                    level_text(
                        get_level(
                            points
                        )
                    ),
                    flush=True
                )

                handle_signal(
                    match,
                    stats,
                    points
                )

            except Exception as e:

                print(
                    "MAC HATASI:",
                    match.get(
                        "teams",
                        "BILINMEYEN"
                    ),
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

    print(
        "GOL SINYAL BOTU BASLADI",
        flush=True
    )

    if TELEGRAM_BOT_TOKEN:
        print(
            "TELEGRAM TOKEN OK",
            flush=True
        )
    else:
        print(
            "HATA: TELEGRAM_BOT_TOKEN "
            "BULUNAMADI",
            flush=True
        )

    while True:
        scan()
        time.sleep(60)
