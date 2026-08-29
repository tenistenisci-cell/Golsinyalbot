import os
import re
import time
from datetime import datetime, timezone

import requests


# =========================================================
# AYARLAR
# =========================================================

POLL_SECONDS = 60

LIVE_FEED_URL = (
    "https://local-global.flashscore.ninja/"
    "2/x/feed/f_1_0_3_en_1"
)

STAT_BASE_URL = (
    "https://local-global.flashscore.ninja/"
    "2/x/feed/df_st_1_"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Mobile Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
    "Referer": "https://www.flashscore.com/",
    "Origin": "https://www.flashscore.com",
    "x-fsign": "SW9D1eZo",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}

session = requests.Session()
session.headers.update(HEADERS)

BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
    or os.getenv("TOKEN")
)

CHAT_ID = (
    os.getenv("TELEGRAM_CHAT_ID")
    or os.getenv("CHAT_ID")
)

sent_signals = {}


# =========================================================
# YARDIMCI
# =========================================================

def clean(value):

    if value is None:
        return None

    value = str(value).strip()
    value = value.replace("\xa0", " ")

    return value if value else None


def number(value):

    if value is None:
        return None

    value = str(value)
    value = value.replace("%", "")
    value = value.replace(",", ".")

    m = re.search(r"-?\d+(?:\.\d+)?", value)

    if not m:
        return None

    try:
        return float(m.group())
    except Exception:
        return None


def int_value(value, default=0):

    n = number(value)

    if n is None:
        return default

    return int(n)


def parse_fields(block):

    result = {}

    for item in block.split("¬"):

        if "÷" not in item:
            continue

        key, value = item.split("÷", 1)

        key = key.lstrip("~").strip()
        value = value.strip()

        if key:
            result[key] = value

    return result


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:

        print(
            "TELEGRAM TOKEN/CHAT ID YOK",
            flush=True
        )

        return False

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=20
        )

        print(
            "TELEGRAM HTTP:",
            response.status_code,
            flush=True
        )

        if response.status_code != 200:

            print(
                "TELEGRAM HATA:",
                response.text[:300],
                flush=True
            )

            return False

        return True

    except Exception as e:

        print(
            "TELEGRAM HATA:",
            type(e).__name__,
            str(e),
            flush=True
        )

        return False


# =========================================================
# DAKİKA
# =========================================================

def calculate_minute(fields):

    # 1) Flashscore BA canlı dakika
    ba = clean(fields.get("BA"))

    if ba:

        m = re.search(
            r"\d+",
            ba
        )

        if m:

            minute = int(m.group())

            if 1 <= minute <= 130:
                return minute

    # 2) Bazı feedlerde farklı dakika alanları
    possible_keys = [
        "BB",
        "BD",
        "BE",
        "BF"
    ]

    for key in possible_keys:

        value = clean(
            fields.get(key)
        )

        if not value:
            continue

        m = re.fullmatch(
            r"\d{1,3}",
            value
        )

        if not m:
            continue

        minute = int(value)

        if 1 <= minute <= 130:
            return minute

    # 3) AD başlangıç zamanından yedek hesap
    start_timestamp = number(
        fields.get("AD")
    )

    if start_timestamp:

        try:

            now_timestamp = time.time()

            elapsed = int(
                (now_timestamp - start_timestamp)
                / 60
            )

            period = clean(
                fields.get("BC")
            )

            period_normal = (
                period.lower()
                if period
                else ""
            )

            # İlk yarı
            if elapsed <= 55:

                if elapsed < 1:
                    return 1

                return min(
                    elapsed,
                    45
                )

            # Devre arası tahmini 15 dk
            # İkinci yarıda gerçek oyun dakikasını üret
            calculated = elapsed - 15

            if calculated < 46:
                calculated = 46

            if calculated > 90:
                calculated = 90

            # Feed açıkça HT diyorsa
            if (
                "half" in period_normal
                and "time" in period_normal
            ):
                return 45

            return calculated

        except Exception:
            pass

    return 0


# =========================================================
# CANLI MAÇLAR
# =========================================================

def get_live_matches():

    response = session.get(
        LIVE_FEED_URL,
        timeout=20
    )

    print(
        "LIVE HTTP:",
        response.status_code,
        flush=True
    )

    response.raise_for_status()

    raw = response.text

    print(
        "LIVE LENGTH:",
        len(raw),
        flush=True
    )

    matches = []

    for block in raw.split("~"):

        fields = parse_fields(block)

        match_id = clean(
            fields.get("AA")
        )

        if not match_id:
            continue

        home = clean(
            fields.get("AE")
        )

        away = clean(
            fields.get("AF")
        )

        if not home or not away:
            continue

        status = clean(
            fields.get("AB")
        )

        # AB=2 canlı
        if status != "2":
            continue

        minute = calculate_minute(
            fields
        )

        matches.append(
            {
                "id": match_id,
                "home": home,
                "away": away,
                "home_score": int_value(
                    fields.get("AG")
                ),
                "away_score": int_value(
                    fields.get("AH")
                ),
                "minute": minute,
                "start": fields.get("AD"),
                "period": fields.get("BC"),
            }
        )

    return matches


# =========================================================
# İSTATİSTİK
# =========================================================

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


def normalize_name(text):

    if not text:
        return ""

    text = text.lower()

    replacements = {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "ç": "c",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def stat_kind(name):

    name = normalize_name(name)

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
    ):
        return "shots"

    if (
        "big chances" in name
        or "big chance" in name
        or "buyuk sans" in name
        or "clear-cut chances" in name
    ):
        return "big"

    if (
        "corner kicks" in name
        or "corners" in name
        or "korner" in name
    ):
        return "corners"

    return None


def save_stat(
    stats,
    kind,
    home,
    away
):

    h = number(home)
    a = number(away)

    if h is None or a is None:
        return

    if kind == "xg":

        stats["xg_home"] = h
        stats["xg_away"] = a

    elif kind == "shots":

        stats["shots_home"] = h
        stats["shots_away"] = a

    elif kind == "sot":

        stats["sot_home"] = h
        stats["sot_away"] = a

    elif kind == "big":

        stats["big_home"] = h
        stats["big_away"] = a

    elif kind == "corners":

        stats["corners_home"] = h
        stats["corners_away"] = a


def get_stats(match_id):

    stats = empty_stats()

    url = (
        STAT_BASE_URL
        + match_id
    )

    try:

        response = session.get(
            url,
            timeout=20
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

        if response.status_code != 200:
            return stats

        raw = response.text

        if not raw.strip():
            return stats

        current_name = None
        current_home = None
        current_away = None

        def flush_current():

            nonlocal current_name
            nonlocal current_home
            nonlocal current_away

            if not current_name:
                return

            kind = stat_kind(
                current_name
            )

            if kind:

                save_stat(
                    stats,
                    kind,
                    current_home,
                    current_away
                )

        for part in raw.split("¬"):

            if "÷" not in part:
                continue

            key, value = part.split(
                "÷",
                1
            )

            key = key.lstrip("~").strip()
            value = clean(value)

            if key == "SG":

                flush_current()

                current_name = value
                current_home = None
                current_away = None

            elif key == "SH":

                current_home = value

            elif key == "SI":

                current_away = value

        flush_current()

        return stats

    except Exception as e:

        print(
            "STAT HATA:",
            type(e).__name__,
            str(e),
            flush=True
        )

        return stats


# =========================================================
# 0 - 100 GOL PUANI
# =========================================================

def calculate_goal_score(
    match,
    stats
):

    minute = match["minute"]

    if minute <= 0:
        return 0

    xg = (
        (stats["xg_home"] or 0)
        +
        (stats["xg_away"] or 0)
    )

    shots = (
        (stats["shots_home"] or 0)
        +
        (stats["shots_away"] or 0)
    )

    sot = (
        (stats["sot_home"] or 0)
        +
        (stats["sot_away"] or 0)
    )

    big = (
        (stats["big_home"] or 0)
        +
        (stats["big_away"] or 0)
    )

    corners = (
        (stats["corners_home"] or 0)
        +
        (stats["corners_away"] or 0)
    )

    score = 0

    # -------------------------
    # xG maksimum 30
    # -------------------------

    if xg >= 3.0:
        score += 30

    elif xg >= 2.4:
        score += 27

    elif xg >= 1.8:
        score += 23

    elif xg >= 1.4:
        score += 19

    elif xg >= 1.0:
        score += 15

    elif xg >= 0.7:
        score += 10

    elif xg >= 0.4:
        score += 5


    # -------------------------
    # İsabetli maksimum 25
    # -------------------------

    if sot >= 10:
        score += 25

    elif sot >= 8:
        score += 22

    elif sot >= 6:
        score += 18

    elif sot >= 4:
        score += 14

    elif sot >= 3:
        score += 10

    elif sot >= 2:
        score += 6


    # -------------------------
    # Şut maksimum 18
    # -------------------------

    if shots >= 25:
        score += 18

    elif shots >= 20:
        score += 16

    elif shots >= 16:
        score += 13

    elif shots >= 12:
        score += 10

    elif shots >= 8:
        score += 6

    elif shots >= 5:
        score += 3


    # -------------------------
    # Büyük şans maksimum 15
    # -------------------------

    if big >= 5:
        score += 15

    elif big >= 4:
        score += 13

    elif big >= 3:
        score += 10

    elif big >= 2:
        score += 7

    elif big >= 1:
        score += 4


    # -------------------------
    # Korner maksimum 7
    # -------------------------

    if corners >= 12:
        score += 7

    elif corners >= 9:
        score += 6

    elif corners >= 6:
        score += 4

    elif corners >= 4:
        score += 2


    # -------------------------
    # Dakika baskısı maksimum 10
    # -------------------------

    if minute >= 86:
        score += 10

    elif minute >= 76:
        score += 8

    elif minute >= 66:
        score += 6

    elif minute >= 56:
        score += 5

    elif minute >= 46:
        score += 3

    elif minute >= 30:
        score += 2


    # -------------------------
    # Düşük skor bonusu
    # -------------------------

    total_goals = (
        match["home_score"]
        +
        match["away_score"]
    )

    if (
        total_goals == 0
        and minute >= 50
    ):
        score += 5

    elif (
        total_goals == 1
        and minute >= 55
    ):
        score += 3


    # -------------------------
    # Çok güçlü baskı bonusları
    # -------------------------

    if (
        xg >= 1.5
        and sot >= 5
        and shots >= 14
    ):
        score += 5

    if (
        big >= 2
        and sot >= 5
    ):
        score += 3


    return min(
        int(score),
        100
    )


# =========================================================
# MESAJ
# =========================================================

def display_value(value):

    if value is None:
        return "VERI YOK"

    if float(value).is_integer():
        return str(int(value))

    return str(
        round(value, 2)
    )


def make_signal_message(
    match,
    stats,
    score
):

    if score >= 75:

        title = (
            "🔥 COK GUCLU GOL SINYALI"
        )

    else:

        title = (
            "🟢 GUCLU GOL SINYALI"
        )

    return (
        f"{title}\n\n"
        f"⚽ {match['home']} - {match['away']}\n"
        f"⏱ Dakika: {match['minute']}'\n"
        f"📊 Skor: "
        f"{match['home_score']}-"
        f"{match['away_score']}\n"
        f"🎯 xG: "
        f"{display_value(stats['xg_home'])} - "
        f"{display_value(stats['xg_away'])}\n"
        f"🥅 Sut: "
        f"{display_value(stats['shots_home'])} - "
        f"{display_value(stats['shots_away'])}\n"
        f"🎯 Isabetli: "
        f"{display_value(stats['sot_home'])} - "
        f"{display_value(stats['sot_away'])}\n"
        f"🚩 Korner: "
        f"{display_value(stats['corners_home'])} - "
        f"{display_value(stats['corners_away'])}\n"
        f"🔥 Buyuk sans: "
        f"{display_value(stats['big_home'])} - "
        f"{display_value(stats['big_away'])}\n"
        f"📈 Gol puani: {score}/100"
    )


# =========================================================
# ANA DÖNGÜ
# =========================================================

print(
    "GOL SINYAL BOTU BASLADI",
    flush=True
)

print(
    "TELEGRAM TOKEN:",
    "VAR"
    if BOT_TOKEN
    else "YOK",
    flush=True
)

print(
    "TELEGRAM CHAT ID:",
    "VAR"
    if CHAT_ID
    else "YOK",
    flush=True
)

while True:

    try:

        matches = get_live_matches()

        print(
            "CANLI MAC SAYISI:",
            len(matches),
            flush=True
        )

        for match in matches:

            print(
                "\n-------------------------",
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
                f"{match['home_score']}-"
                f"{match['away_score']}",
                flush=True
            )

            print(
                "MATCH ID:",
                match["id"],
                flush=True
            )

            stats = get_stats(
                match["id"]
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

            goal_score = calculate_goal_score(
                match,
                stats
            )

            print(
                "GOL PUANI:",
                str(goal_score) + "/100",
                flush=True
            )

            # -----------------------------------
            # 55+ güçlü sinyal
            # 75+ çok güçlü
            # -----------------------------------

            if goal_score >= 55:

                match_id = match["id"]

                previous = sent_signals.get(
                    match_id
                )

                should_send = False

                if previous is None:

                    should_send = True

                else:

                    last_minute = previous[
                        "minute"
                    ]

                    last_score = previous[
                        "score"
                    ]

                    # 15 dakika geçtiyse tekrar
                    if (
                        match["minute"]
                        - last_minute
                        >= 15
                    ):
                        should_send = True

                    # Güçlüden çok güçlüye çıktıysa
                    if (
                        last_score < 75
                        and goal_score >= 75
                    ):
                        should_send = True

                    # Puan 15+ yükseldiyse
                    if (
                        goal_score
                        >= last_score + 15
                    ):
                        should_send = True

                if should_send:

                    message = (
                        make_signal_message(
                            match,
                            stats,
                            goal_score
                        )
                    )

                    sent = send_telegram(
                        message
                    )

                    if sent:

                        sent_signals[
                            match_id
                        ] = {
                            "minute":
                                match["minute"],

                            "score":
                                goal_score
                        }

                        print(
                            "SINyal TELEGRAMA GONDERILDI",
                            flush=True
                        )

            time.sleep(1)

    except Exception as e:

        print(
            "ANA HATA:",
            type(e).__name__,
            str(e),
            flush=True
        )

    print(
        "60 SANIYE BEKLENIYOR...",
        flush=True
    )

    time.sleep(
        POLL_SECONDS
    )
