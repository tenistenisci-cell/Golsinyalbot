import os
import re
import time
import requests

# =========================================================
# AYARLAR
# =========================================================

POLL_SECONDS = 60

FS_HEADERS = {
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

# Bugünkü futbol maçları
LIVE_FEED_URL = (
    "https://local-global.flashscore.ninja/"
    "2/x/feed/f_1_0_3_en_1"
)

STAT_BASE_URL = (
    "https://local-global.flashscore.ninja/"
    "2/x/feed/df_st_1_"
)

session = requests.Session()
session.headers.update(FS_HEADERS)

# Railway Variables'da hangi isim kullanıldıysa onu yakalamaya çalışır
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
            "TELEGRAM AYARLARI YOK - MESAJ GONDERILMEDI",
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
                "text": message,
            },
            timeout=20,
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

        match_id = clean(fields.get("AA"))

        if not match_id:
            continue

        home = clean(fields.get("AE"))
        away = clean(fields.get("AF"))

        if not home or not away:
            continue

        status = clean(fields.get("AB"))

        # Flashscore: AB=2 canlı
        if status != "2":
            continue

        home_score = number(fields.get("AG"))
        away_score = number(fields.get("AH"))

        minute = number(fields.get("BA"))

        # Bazı canlı maçlarda BA boş olabilir.
        # Status canlı olduğu sürece maçı yine de kaybetmiyoruz.
        if minute is None:
            minute = 0

        matches.append(
            {
                "id": match_id,
                "home": home,
                "away": away,
                "home_score": int(home_score or 0),
                "away_score": int(away_score or 0),
                "minute": int(minute),
                "status": status,
            }
        )

    return matches


# =========================================================
# İSTATİSTİKLER
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
        "danger_home": None,
        "danger_away": None,
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
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


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

    if (
        "dangerous attacks" in name
        or "dangerous attack" in name
        or "tehlikeli atak" in name
    ):
        return "danger"

    return None


def save_stat(stats, kind, home, away):

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

    elif kind == "danger":
        stats["danger_home"] = h
        stats["danger_away"] = a


def get_stats(match_id):

    stats = empty_stats()

    url = STAT_BASE_URL + match_id

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

        # Flashscore statistik feedinde genel yapı:
        # SG = istatistik adı
        # SH = ev
        # SI = deplasman
        #
        # Blok blok okuyoruz.

        current_name = None
        current_home = None
        current_away = None

        parts = raw.split("¬")

        def flush_stat():

            nonlocal current_name
            nonlocal current_home
            nonlocal current_away

            if not current_name:
                return

            kind = stat_kind(current_name)

            if kind:
                save_stat(
                    stats,
                    kind,
                    current_home,
                    current_away
                )

        for part in parts:

            if "÷" not in part:
                continue

            key, value = part.split("÷", 1)

            key = key.lstrip("~").strip()
            value = clean(value)

            if key == "SG":

                flush_stat()

                current_name = value
                current_home = None
                current_away = None

            elif key == "SH":

                current_home = value

            elif key == "SI":

                current_away = value

        flush_stat()

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
# SİNYAL PUANI
# =========================================================

def calculate_signal(match, stats):

    minute = match["minute"]

    if minute < 20:
        return 0, []

    points = 0
    reasons = []

    xg_h = stats["xg_home"] or 0
    xg_a = stats["xg_away"] or 0

    shots_h = stats["shots_home"] or 0
    shots_a = stats["shots_away"] or 0

    sot_h = stats["sot_home"] or 0
    sot_a = stats["sot_away"] or 0

    big_h = stats["big_home"] or 0
    big_a = stats["big_away"] or 0

    corners_h = stats["corners_home"] or 0
    corners_a = stats["corners_away"] or 0

    danger_h = stats["danger_home"] or 0
    danger_a = stats["danger_away"] or 0

    total_xg = xg_h + xg_a
    total_shots = shots_h + shots_a
    total_sot = sot_h + sot_a
    total_big = big_h + big_a
    total_corners = corners_h + corners_a
    total_danger = danger_h + danger_a

    # xG
    if total_xg >= 2.0:
        points += 4
        reasons.append(f"xG {total_xg:.2f}")

    elif total_xg >= 1.3:
        points += 3
        reasons.append(f"xG {total_xg:.2f}")

    elif total_xg >= 0.8:
        points += 2
        reasons.append(f"xG {total_xg:.2f}")

    # İsabetli şut
    if total_sot >= 8:
        points += 4
        reasons.append(f"İsabetli şut {int(total_sot)}")

    elif total_sot >= 5:
        points += 3
        reasons.append(f"İsabetli şut {int(total_sot)}")

    elif total_sot >= 3:
        points += 2
        reasons.append(f"İsabetli şut {int(total_sot)}")

    # Toplam şut
    if total_shots >= 20:
        points += 3
        reasons.append(f"Şut {int(total_shots)}")

    elif total_shots >= 13:
        points += 2
        reasons.append(f"Şut {int(total_shots)}")

    elif total_shots >= 8:
        points += 1

    # Büyük şans
    if total_big >= 4:
        points += 3
        reasons.append(f"Büyük şans {int(total_big)}")

    elif total_big >= 2:
        points += 2
        reasons.append(f"Büyük şans {int(total_big)}")

    elif total_big >= 1:
        points += 1

    # Korner
    if total_corners >= 9:
        points += 2
        reasons.append(f"Korner {int(total_corners)}")

    elif total_corners >= 5:
        points += 1

    # Tehlikeli atak varsa
    if total_danger >= 80:
        points += 3
        reasons.append(
            f"Tehlikeli atak {int(total_danger)}"
        )

    elif total_danger >= 50:
        points += 2
        reasons.append(
            f"Tehlikeli atak {int(total_danger)}"
        )

    # Maçın ilerleyen bölümü
    if 55 <= minute <= 85:
        points += 1

    if 70 <= minute <= 88:
        points += 1

    # 0-0 veya tek fark sıkışık maç bonusu
    total_goals = (
        match["home_score"]
        + match["away_score"]
    )

    if total_goals <= 1 and minute >= 50:
        points += 1

    return points, reasons


# =========================================================
# SİNYAL MESAJI
# =========================================================

def make_message(match, stats, points, reasons):

    def val(x):
        if x is None:
            return "-"
        return str(x)

    text = (
        "🚨 GOL SİNYALİ 🚨\n\n"
        f"⚽ {match['home']} - {match['away']}\n"
        f"⏱ Dakika: {match['minute']}'\n"
        f"🥅 Skor: "
        f"{match['home_score']}-{match['away_score']}\n\n"
        f"📊 Sinyal puanı: {points}\n"
        f"xG: {val(stats['xg_home'])} - "
        f"{val(stats['xg_away'])}\n"
        f"Şut: {val(stats['shots_home'])} - "
        f"{val(stats['shots_away'])}\n"
        f"İsabetli: {val(stats['sot_home'])} - "
        f"{val(stats['sot_away'])}\n"
        f"Büyük şans: {val(stats['big_home'])} - "
        f"{val(stats['big_away'])}\n"
        f"Korner: {val(stats['corners_home'])} - "
        f"{val(stats['corners_away'])}"
    )

    if reasons:
        text += (
            "\n\n🔥 "
            + " | ".join(reasons)
        )

    return text


# =========================================================
# ANA DÖNGÜ
# =========================================================

print(
    "GOL SINYAL BOTU BASLADI",
    flush=True
)

print(
    "TELEGRAM TOKEN:",
    "VAR" if BOT_TOKEN else "YOK",
    flush=True
)

print(
    "TELEGRAM CHAT ID:",
    "VAR" if CHAT_ID else "YOK",
    flush=True
)

while True:

    try:

        live_matches = get_live_matches()

        print(
            "CANLI MAC SAYISI:",
            len(live_matches),
            flush=True
        )

        for match in live_matches:

            print(
                "\n-----------------------------",
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

            points, reasons = calculate_signal(
                match,
                stats
            )

            print(
                "SINYAL PUANI:",
                points,
                flush=True
            )

            # 7 puan ve üzeri güçlü sinyal
            if points >= 7:

                match_id = match["id"]

                last_minute = sent_signals.get(
                    match_id
                )

                # Aynı maça sürekli mesaj atmasın.
                # İlk sinyalden sonra en az 15 dk geçmeli.
                should_send = (
                    last_minute is None
                    or
                    match["minute"] - last_minute >= 15
                )

                if should_send:

                    message = make_message(
                        match,
                        stats,
                        points,
                        reasons
                    )

                    if send_telegram(message):

                        sent_signals[match_id] = (
                            match["minute"]
                        )

                        print(
                            "TELEGRAM SINYAL GONDERILDI",
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

    time.sleep(POLL_SECONDS)
