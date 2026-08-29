import os
import time
import requests
from datetime import datetime

# =========================================================
# AYARLAR
# =========================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CHECK_INTERVAL = 60

# Aynı sinyalin sürekli gitmesini engeller
sent_signals = set()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.sofascore.com/",
}


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN YOK", flush=True)
        return False

    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID YOK", flush=True)
        return False

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        r = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text
            },
            timeout=20
        )

        print(
            "TELEGRAM CEVAP:",
            r.status_code,
            r.text[:500],
            flush=True
        )

        if r.ok:
            print("TELEGRAM MESAJI GONDERILDI", flush=True)
            return True

        print("TELEGRAM MESAJI GONDERILEMEDI", flush=True)
        return False

    except Exception as e:
        print(
            "TELEGRAM GONDERIM HATASI:",
            type(e).__name__,
            str(e),
            flush=True
        )
        return False


# =========================================================
# SAYI DONUSTURME
# =========================================================

def num(value):
    if value is None:
        return 0

    try:
        value = str(value)
        value = value.replace("%", "")
        value = value.replace(",", ".")
        return float(value)
    except:
        return 0


# =========================================================
# CANLI MACLAR
# =========================================================

def get_live_matches():
    try:
        url = (
            "https://www.sofascore.com/api/v1/"
            "sport/football/events/live"
        )

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        print(
            "CANLI MAC HTTP:",
            r.status_code,
            flush=True
        )

        if not r.ok:
            return []

        data = r.json()

        events = data.get("events", [])

        live = []

        for event in events:
            status = event.get("status", {})
            status_type = status.get("type", "")

            if status_type not in (
                "inprogress",
                "halftime"
            ):
                continue

            live.append(event)

        return live

    except Exception as e:
        print(
            "CANLI MAC HATASI:",
            type(e).__name__,
            str(e),
            flush=True
        )
        return []


# =========================================================
# ISTATISTIK
# =========================================================

def get_stats(event_id):
    try:
        url = (
            "https://www.sofascore.com/api/v1/event/"
            f"{event_id}/statistics"
        )

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        if not r.ok:
            return None

        data = r.json()

        periods = data.get("statistics", [])

        if not periods:
            return None

        selected = None

        # Önce ALL istatistiğini bul
        for period in periods:
            if period.get("period") == "ALL":
                selected = period
                break

        # ALL yoksa ilk istatistik
        if selected is None:
            selected = periods[0]

        result = {
            "xg_home": 0,
            "xg_away": 0,
            "shots_home": 0,
            "shots_away": 0,
            "sot_home": 0,
            "sot_away": 0,
            "corners_home": 0,
            "corners_away": 0,
            "big_home": 0,
            "big_away": 0,
        }

        groups = selected.get("groups", [])

        for group in groups:
            items = group.get(
                "statisticsItems",
                []
            )

            for item in items:
                name = (
                    item.get("name", "")
                    .strip()
                    .lower()
                )

                home = item.get("home", 0)
                away = item.get("away", 0)

                if name in (
                    "expected goals",
                    "expected goals (xg)"
                ):
                    result["xg_home"] = num(home)
                    result["xg_away"] = num(away)

                elif name == "total shots":
                    result["shots_home"] = num(home)
                    result["shots_away"] = num(away)

                elif name == "shots on target":
                    result["sot_home"] = num(home)
                    result["sot_away"] = num(away)

                elif name == "corner kicks":
                    result["corners_home"] = num(home)
                    result["corners_away"] = num(away)

                elif name == "big chances":
                    result["big_home"] = num(home)
                    result["big_away"] = num(away)

        return result

    except Exception as e:
        print(
            "ISTATISTIK HATASI:",
            type(e).__name__,
            str(e),
            flush=True
        )
        return None


# =========================================================
# DAKIKA
# =========================================================

def get_minute(event):
    status = event.get("status", {})

    if status.get("type") == "halftime":
        return "Devre Arasi"

    description = status.get(
        "description",
        ""
    )

    if description:
        return description

    time_data = event.get("time", {})

    timestamp = time_data.get(
        "currentPeriodStartTimestamp"
    )

    if not timestamp:
        return "Canli"

    try:
        now = int(time.time())
        minute = int(
            (now - timestamp) / 60
        )

        period = event.get(
            "lastPeriod",
            ""
        )

        if period == "period2":
            minute += 45

        if minute < 0:
            return "Canli"

        if minute > 120:
            return "Canli"

        return f"{minute}'"

    except:
        return "Canli"


# =========================================================
# PUAN HESABI
# =========================================================

def calculate_score(stats):
    shots = (
        stats["shots_home"] +
        stats["shots_away"]
    )

    sot = (
        stats["sot_home"] +
        stats["sot_away"]
    )

    corners = (
        stats["corners_home"] +
        stats["corners_away"]
    )

    big = (
        stats["big_home"] +
        stats["big_away"]
    )

    xg = (
        stats["xg_home"] +
        stats["xg_away"]
    )

    score = 0

    # Şut
    if shots >= 10:
        score += 8
    if shots >= 15:
        score += 7
    if shots >= 20:
        score += 5

    # İsabetli şut
    if sot >= 4:
        score += 10
    if sot >= 6:
        score += 8
    if sot >= 8:
        score += 7

    # Büyük şans
    if big >= 1:
        score += 8
    if big >= 2:
        score += 8
    if big >= 3:
        score += 4

    # Korner
    if corners >= 5:
        score += 5
    if corners >= 8:
        score += 5

    # xG
    if xg >= 1.0:
        score += 8
    if xg >= 1.5:
        score += 7
    if xg >= 2.0:
        score += 5

    return min(score, 100)


# =========================================================
# MESAJ
# =========================================================

def make_message(
    home,
    away,
    minute,
    hs,
    as_,
    stats,
    score
):
    if score >= 60:
        title = "🟢 GUCLU GOL SINYALI"
    else:
        title = "⚠️ GOL IHTIMALI ARTIYOR"

    xg_home = stats["xg_home"]
    xg_away = stats["xg_away"]

    xg_text = (
        f"{xg_home:g} - {xg_away:g}"
        if xg_home > 0 or xg_away > 0
        else "VERI YOK"
    )

    big_home = stats["big_home"]
    big_away = stats["big_away"]

    return (
        f"{title}\n\n"
        f"⚽ {home} - {away}\n"
        f"⏱ Dakika: {minute}\n"
        f"📊 Skor: {hs}-{as_}\n"
        f"🎯 xG: {xg_text}\n"
        f"🥅 Sut: "
        f"{int(stats['shots_home'])} - "
        f"{int(stats['shots_away'])}\n"
        f"🎯 Isabetli: "
        f"{int(stats['sot_home'])} - "
        f"{int(stats['sot_away'])}\n"
        f"🔥 Buyuk sans: "
        f"{int(big_home)} - "
        f"{int(big_away)}\n"
        f"🚩 Korner: "
        f"{int(stats['corners_home'])} - "
        f"{int(stats['corners_away'])}\n"
        f"📈 Gol puani: {score}/100"
    )


# =========================================================
# TARAMA
# =========================================================

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

    matches = get_live_matches()

    print(
        "CANLI MAC SAYISI:",
        len(matches),
        flush=True
    )

    for event in matches:
        try:
            event_id = event.get("id")

            home = (
                event.get(
                    "homeTeam",
                    {}
                ).get(
                    "name",
                    "Ev Sahibi"
                )
            )

            away = (
                event.get(
                    "awayTeam",
                    {}
                ).get(
                    "name",
                    "Deplasman"
                )
            )

            home_score = (
                event.get(
                    "homeScore",
                    {}
                ).get(
                    "current",
                    0
                )
            )

            away_score = (
                event.get(
                    "awayScore",
                    {}
                ).get(
                    "current",
                    0
                )
            )

            minute = get_minute(event)

            print(
                "\n--------------------------",
                flush=True
            )

            print(
                "MAC:",
                home,
                "-",
                away,
                flush=True
            )

            print(
                "DAKIKA:",
                minute,
                flush=True
            )

            print(
                "SKOR:",
                f"{home_score}-{away_score}",
                flush=True
            )

            stats = get_stats(event_id)

            if not stats:
                print(
                    "ISTATISTIK: VERI YOK",
                    flush=True
                )
                continue

            print(
                "ISTATISTIK ALINDI",
                flush=True
            )

            print(
                "SUT:",
                int(stats["shots_home"]),
                "-",
                int(stats["shots_away"]),
                flush=True
            )

            print(
                "ISABETLI:",
                int(stats["sot_home"]),
                "-",
                int(stats["sot_away"]),
                flush=True
            )

            print(
                "BUYUK SANS:",
                int(stats["big_home"]),
                "-",
                int(stats["big_away"]),
                flush=True
            )

            print(
                "KORNER:",
                int(stats["corners_home"]),
                "-",
                int(stats["corners_away"]),
                flush=True
            )

            score = calculate_score(stats)

            print(
                "GOL PUANI:",
                score,
                flush=True
            )

            if score >= 60:
                level = "GUCLU"

            elif score >= 40:
                level = "NORMAL"

            else:
                print(
                    "BASKI YETERSIZ - TELEGRAM YOK",
                    flush=True
                )
                continue

            print(
                "SEVIYE:",
                level,
                flush=True
            )

            signal_key = (
                event_id,
                level,
                home_score,
                away_score
            )

            if signal_key in sent_signals:
                print(
                    "BU SINYAL DAHA ONCE GONDERILDI",
                    flush=True
                )
                continue

            message = make_message(
                home,
                away,
                minute,
                home_score,
                away_score,
                stats,
                score
            )

            print(
                "TELEGRAM GONDERME DENEMESI:",
                home,
                "-",
                away,
                flush=True
            )

            if send_telegram(message):
                sent_signals.add(signal_key)

        except Exception as e:
            print(
                "MAC ISLEME HATASI:",
                type(e).__name__,
                str(e),
                flush=True
            )


# =========================================================
# BASLANGIC
# =========================================================

print(
    "GOL SINYAL BOTU BASLADI",
    flush=True
)

print(
    "TELEGRAM TOKEN:",
    "VAR" if TELEGRAM_BOT_TOKEN else "YOK",
    flush=True
)

print(
    "TELEGRAM CHAT ID:",
    "VAR" if TELEGRAM_CHAT_ID else "YOK",
    flush=True
)

while True:
    try:
        scan()
    except Exception as e:
        print(
            "ANA DONGU HATASI:",
            type(e).__name__,
            str(e),
            flush=True
        )

    time.sleep(CHECK_INTERVAL)
