import os
import re
import time
import requests
from urllib.parse import urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup

BASE_URL = "https://m.flashscore.com.tr/"
LIVE_URL = "https://m.flashscore.com.tr/?s=2"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)

match_states = {}


def get_soup(url):
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def clean_match_url(url):
    url = urljoin(BASE_URL, url)
    p = urlsplit(url)

    path = p.path

    if not path.endswith("/"):
        path += "/"

    return urlunsplit((
        p.scheme,
        p.netloc,
        path,
        "",
        ""
    ))


def to_number(text):
    try:
        return float(
            text.replace(",", ".")
            .replace("%", "")
            .strip()
        )
    except:
        return None


def get_chat_id():
    if not TELEGRAM_BOT_TOKEN:
        return None

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/getUpdates"
        )

        r = requests.get(url, timeout=20)
        data = r.json()

        if not data.get("ok"):
            return None

        results = data.get("result", [])

        for item in reversed(results):
            message = item.get("message")

            if not message:
                continue

            chat = message.get("chat")

            if chat and chat.get("id"):
                return str(chat["id"])

    except Exception as e:
        print("CHAT ID HATASI:", e, flush=True)

    return None


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM TOKEN YOK", flush=True)
        return False

    chat_id = get_chat_id()

    if not chat_id:
        print("CHAT ID BULUNAMADI", flush=True)
        return False

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage"
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
            print("TELEGRAM MESAJI GONDERILDI", flush=True)
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
            e,
            flush=True
        )

    return False


def get_live_matches():
    soup = get_soup(LIVE_URL)

    lines = [
        x.strip()
        for x in soup.get_text("\n", strip=True).splitlines()
        if x.strip()
    ]

    live_rows = []

    for i, line in enumerate(lines):

        if not (
            re.fullmatch(r"\d{1,3}(?:\+)?'", line)
            or line == "Devre Arası"
        ):
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

    score_links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)

        if "/mac/" not in href:
            continue

        if not re.fullmatch(r"\d+\s*-\s*\d+", text):
            continue

        score_links.append({
            "a": a,
            "score": text,
            "url": clean_match_url(href)
        })

    for row in live_rows:

        for item in score_links:

            if item["score"] != row["score"]:
                continue

            node = item["a"]

            for _ in range(8):

                if node is None:
                    break

                nearby = node.get_text(" ", strip=True)

                if row["teams"] in nearby:
                    row["url"] = item["url"]
                    break

                node = node.parent

            if row["url"]:
                break

    return [
        x for x in live_rows
        if x["url"]
    ]


def get_stats(match_url):
    base = clean_match_url(match_url)
    stats_url = base + "?t=istatistik"

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

        left = to_number(lines[i - 1])
        right = to_number(lines[i + 1])

        if left is None or right is None:
            continue

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


def show(value):
    if value is None:
        return "VERI YOK"

    return f"{value[0]:g} - {value[1]:g}"


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
        return "🔥 COK GUCLU GOL BASKISI"

    if level == 2:
        return "🟢 GUCLU GOL BASKISI"

    if level == 1:
        return "⚠️ GOL IHTIMALI ARTIYOR"

    return "BASKI YETERSIZ"


def handle_signal(match, stats, points):
    key = match["url"]

    current_level = get_level(points)
    previous_level = match_states.get(key, 0)

    print(
        "SINYAL KONTROL:",
        match["teams"],
        "ESKI:",
        previous_level,
        "YENI:",
        current_level,
        "PUAN:",
        points,
        flush=True
    )

    if current_level == 0:
        match_states[key] = 0
        return

    if current_level == previous_level:
        return

    if current_level > previous_level or previous_level == 0:

        message = (
            f"{level_text(current_level)}\n\n"
            f"⚽ {match['teams']}\n"
            f"⏱ Dakika: {match['minute']}\n"
            f"📊 Skor: {match['score']}\n"
            f"🎯 xG: {show(stats['xg'])}\n"
            f"🥅 Sut: {show(stats['shots'])}\n"
            f"🎯 Isabetli: {show(stats['sot'])}\n"
            f"🔥 Buyuk sans: {show(stats['big'])}\n"
            f"🚩 Korner: {show(stats['corners'])}\n"
            f"📈 Gol puani: {points}/100"
        )

        print(
            "TELEGRAM GONDERME DENEMESI:",
            match["teams"],
            flush=True
        )

        success = send_telegram(message)

        if success:
            match_states[key] = current_level

            print(
                "SINYAL HAFIZAYA ALINDI:",
                current_level,
                flush=True
            )

    else:
        match_states[key] = current_level


def scan():
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

                print(
                    "\n==============================",
                    flush=True
                )

                print("MAC:", match["teams"], flush=True)
                print("DAKIKA:", match["minute"], flush=True)
                print("SKOR:", match["score"], flush=True)
                print("xG:", show(stats["xg"]), flush=True)
                print("SUT:", show(stats["shots"]), flush=True)
                print("ISABETLI:", show(stats["sot"]), flush=True)
                print("BUYUK SANS:", show(stats["big"]), flush=True)
                print("KORNER:", show(stats["corners"]), flush=True)
                print("GOL PUANI:", points, flush=True)
                print("SEVIYE:", level_text(get_level(points)), flush=True)

                handle_signal(
                    match,
                    stats,
                    points
                )

                print(
                    "==============================",
                    flush=True
                )

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

    if TELEGRAM_BOT_TOKEN:
        print(
            "TELEGRAM TOKEN OK",
            flush=True
        )
    else:
        print(
            "HATA: TELEGRAM_BOT_TOKEN BULUNAMADI",
            flush=True
        )

    while True:
        scan()
        time.sleep(60)
