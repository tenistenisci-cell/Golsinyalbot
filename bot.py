import os
import re
import time
import threading

import requests
import psycopg2


# =========================================================
# AYARLAR
# =========================================================

POLL_SECONDS = 60

SIGNAL_THRESHOLD = 68

# 68-74 arasi daha uzun bekle
NORMAL_CONFIRM_SECONDS = 90

# 75+ cok guclu sinyal
STRONG_CONFIRM_SECONDS = 60

GOAL_COOLDOWN_SECONDS = 300
TEMPO_MIN_SCORE = 4


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

DATABASE_URL = os.getenv("DATABASE_URL")


sent_signals = {}
last_scores = {}
goal_cooldowns = {}
match_history = {}
pending_signals = {}


# =========================================================
# LOG
# =========================================================

def log(*args):
    print(*args, flush=True)


# =========================================================
# POSTGRESQL
# =========================================================

def get_db_connection():

    if not DATABASE_URL:
        return None

    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )


def init_database():

    if not DATABASE_URL:

        log("DATABASE_URL YOK")
        return False

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        conn.commit()
        cur.close()
        conn.close()

        log("POSTGRESQL HAZIR")

        if CHAT_ID:

            try:

                owner_chat_id = int(
                    str(CHAT_ID).strip()
                )

                conn = get_db_connection()
                cur = conn.cursor()

                cur.execute(
                    """
                    INSERT INTO subscribers (
                        chat_id,
                        active
                    )
                    VALUES (%s, TRUE)
                    ON CONFLICT (chat_id)
                    DO NOTHING
                    """,
                    (owner_chat_id,)
                )

                conn.commit()
                cur.close()
                conn.close()

                log("ANA CHAT ID VERITABANINDA")

            except Exception as e:

                log(
                    "ANA CHAT ID KAYIT HATA:",
                    type(e).__name__,
                    str(e)
                )

        return True

    except Exception as e:

        log(
            "POSTGRESQL BASLATMA HATA:",
            type(e).__name__,
            str(e)
        )

        return False


def add_subscriber(
    chat_id,
    username=None,
    first_name=None
):

    try:

        conn = get_db_connection()

        if conn is None:
            return False

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO subscribers (
                chat_id,
                username,
                first_name,
                active
            )
            VALUES (%s, %s, %s, TRUE)

            ON CONFLICT (chat_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                active = TRUE,
                updated_at = NOW()
            """,
            (
                int(chat_id),
                username,
                first_name
            )
        )

        conn.commit()
        cur.close()
        conn.close()

        log(
            "KULLANICI AKTIF:",
            chat_id,
            username or ""
        )

        return True

    except Exception as e:

        log(
            "KULLANICI KAYIT HATA:",
            type(e).__name__,
            str(e)
        )

        return False


def remove_subscriber(chat_id):

    try:

        conn = get_db_connection()

        if conn is None:
            return False

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE subscribers
            SET
                active = FALSE,
                updated_at = NOW()
            WHERE chat_id = %s
            """,
            (int(chat_id),)
        )

        conn.commit()
        cur.close()
        conn.close()

        log(
            "KULLANICI PASIF:",
            chat_id
        )

        return True

    except Exception as e:

        log(
            "KULLANICI SILME HATA:",
            type(e).__name__,
            str(e)
        )

        return False


def subscriber_is_active(chat_id):

    try:

        conn = get_db_connection()

        if conn is None:
            return False

        cur = conn.cursor()

        cur.execute(
            """
            SELECT active
            FROM subscribers
            WHERE chat_id = %s
            """,
            (int(chat_id),)
        )

        row = cur.fetchone()

        cur.close()
        conn.close()

        return bool(
            row
            and row[0]
        )

    except Exception:
        return False


def get_active_chat_ids():

    try:

        conn = get_db_connection()

        if conn is None:
            raise RuntimeError(
                "DATABASE BAGLANTISI YOK"
            )

        cur = conn.cursor()

        cur.execute(
            """
            SELECT chat_id
            FROM subscribers
            WHERE active = TRUE
            ORDER BY created_at ASC
            """
        )

        rows = cur.fetchall()

        cur.close()
        conn.close()

        return [
            int(row[0])
            for row in rows
        ]

    except Exception as e:

        log(
            "KULLANICI LISTESI HATA:",
            type(e).__name__,
            str(e)
        )

        if CHAT_ID:

            try:

                return [
                    int(
                        str(CHAT_ID).strip()
                    )
                ]

            except Exception:
                pass

        return []


# =========================================================
# TELEGRAM
# =========================================================

def send_to_chat(
    chat_id,
    message
):

    if not BOT_TOKEN:
        return False

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message
            },
            timeout=20
        )

        if response.status_code == 200:
            return True


        if response.status_code == 403:

            remove_subscriber(
                chat_id
            )

            return False


        if response.status_code == 429:

            try:

                data = response.json()

                retry_after = int(
                    data.get(
                        "parameters",
                        {}
                    ).get(
                        "retry_after",
                        1
                    )
                )

                time.sleep(
                    min(
                        retry_after,
                        10
                    )
                )

                response = requests.post(
                    url,
                    data={
                        "chat_id": chat_id,
                        "text": message
                    },
                    timeout=20
                )

                return (
                    response.status_code
                    == 200
                )

            except Exception:
                return False


        log(
            "TELEGRAM HATA:",
            chat_id,
            response.status_code
        )

        return False

    except Exception as e:

        log(
            "TELEGRAM HATA:",
            type(e).__name__,
            str(e)
        )

        return False


def send_telegram(message):

    chat_ids = get_active_chat_ids()

    if not chat_ids:

        log(
            "AKTIF KULLANICI YOK"
        )

        return False


    success_count = 0


    for chat_id in chat_ids:

        if send_to_chat(
            chat_id,
            message
        ):

            success_count += 1


        time.sleep(
            0.05
        )


    log(
        "SINYAL GONDERILDI:",
        f"{success_count}/{len(chat_ids)}",
        "KULLANICI"
    )


    return (
        success_count > 0
    )


# =========================================================
# /START /STOP /STATUS
# =========================================================

def telegram_command_listener():

    if not BOT_TOKEN:

        log(
            "KOMUT DINLEYICI TOKEN YOK"
        )

        return


    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/getUpdates"
    )


    offset = None


    try:

        response = requests.get(
            url,
            params={
                "offset": -1,
                "timeout": 0
            },
            timeout=10
        )

        if response.status_code == 200:

            results = (
                response
                .json()
                .get(
                    "result",
                    []
                )
            )

            if results:

                offset = (
                    results[-1][
                        "update_id"
                    ]
                    + 1
                )

    except Exception:
        pass


    log(
        "TELEGRAM KOMUT DINLEYICI AKTIF"
    )


    while True:

        try:

            params = {
                "timeout": 25
            }

            if offset is not None:

                params[
                    "offset"
                ] = offset


            response = requests.get(
                url,
                params=params,
                timeout=35
            )


            if response.status_code != 200:

                time.sleep(
                    5
                )

                continue


            updates = (
                response
                .json()
                .get(
                    "result",
                    []
                )
            )


            for update in updates:

                offset = (
                    update[
                        "update_id"
                    ]
                    + 1
                )


                message = update.get(
                    "message"
                )

                if not message:
                    continue


                chat = message.get(
                    "chat",
                    {}
                )


                if (
                    chat.get(
                        "type"
                    )
                    != "private"
                ):
                    continue


                chat_id = chat.get(
                    "id"
                )

                if chat_id is None:
                    continue


                text = (
                    message.get(
                        "text"
                    )
                    or ""
                ).strip()


                if not text:
                    continue


                command = (
                    text
                    .split()[0]
                    .lower()
                    .split("@")[0]
                )


                user = message.get(
                    "from",
                    {}
                )


                username = user.get(
                    "username"
                )

                first_name = user.get(
                    "first_name"
                )


                if command == "/start":

                    saved = add_subscriber(
                        chat_id,
                        username,
                        first_name
                    )


                    if saved:

                        send_to_chat(
                            chat_id,
                            (
                                "✅ GOL SINYALLERI AKTIF\n\n"
                                "Guclu gol sinyalleri otomatik "
                                "olarak bu sohbete gelecek.\n\n"
                                "Sinyalleri durdurmak icin /stop"
                            )
                        )

                    else:

                        send_to_chat(
                            chat_id,
                            (
                                "⚠️ Kayit sirasinda gecici "
                                "bir sorun olustu.\n"
                                "Biraz sonra tekrar /start yaz."
                            )
                        )


                elif command == "/stop":

                    removed = remove_subscriber(
                        chat_id
                    )


                    if removed:

                        send_to_chat(
                            chat_id,
                            (
                                "⛔ GOL SINYALLERI DURDURULDU\n\n"
                                "Tekrar sinyal almak icin "
                                "/start yazabilirsin."
                            )
                        )


                elif command == "/status":

                    active = subscriber_is_active(
                        chat_id
                    )


                    if active:

                        send_to_chat(
                            chat_id,
                            "✅ Sinyal aboneligin aktif."
                        )

                    else:

                        send_to_chat(
                            chat_id,
                            (
                                "⛔ Sinyal aboneligin aktif degil.\n"
                                "Aktif etmek icin /start yaz."
                            )
                        )


        except Exception as e:

            log(
                "KOMUT DINLEYICI HATA:",
                type(e).__name__,
                str(e)
            )

            time.sleep(
                5
            )


# =========================================================
# YARDIMCI
# =========================================================

def clean(value):

    if value is None:
        return None

    value = str(value).strip()
    value = value.replace(
        "\xa0",
        " "
    )

    return (
        value
        if value
        else None
    )


def number(value):

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

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        value
    )

    if not m:
        return None

    try:
        return float(
            m.group()
        )

    except Exception:
        return None


def int_value(
    value,
    default=0
):

    n = number(
        value
    )

    if n is None:
        return default

    return int(
        n
    )


def parse_fields(block):

    result = {}

    for item in block.split(
        "¬"
    ):

        if "÷" not in item:
            continue

        key, value = item.split(
            "÷",
            1
        )

        key = (
            key
            .lstrip("~")
            .strip()
        )

        value = value.strip()

        if key:
            result[
                key
            ] = value

    return result


def is_valid_signal_minute(
    minute
):

    return (
        15 <= minute <= 38
        or
        55 <= minute <= 85
    )


def is_tracking_minute(
    minute
):

    return (
        10 <= minute <= 38
        or
        50 <= minute <= 85
    )


# =========================================================
# DAKIKA
# =========================================================

def calculate_minute(fields):

    ba = clean(
        fields.get(
            "BA"
        )
    )


    if ba:

        m = re.search(
            r"\d+",
            ba
        )

        if m:

            minute = int(
                m.group()
            )

            if 1 <= minute <= 130:
                return minute


    for key in [
        "BB",
        "BD",
        "BE",
        "BF"
    ]:

        value = clean(
            fields.get(
                key
            )
        )

        if not value:
            continue


        if not re.fullmatch(
            r"\d{1,3}",
            value
        ):
            continue


        minute = int(
            value
        )

        if 1 <= minute <= 130:
            return minute


    start_timestamp = number(
        fields.get(
            "AD"
        )
    )


    if start_timestamp:

        try:

            elapsed = int(
                (
                    time.time()
                    - start_timestamp
                )
                / 60
            )


            period = clean(
                fields.get(
                    "BC"
                )
            )


            period_normal = (
                period.lower()
                if period
                else ""
            )


            if elapsed <= 55:

                if elapsed < 1:
                    return 1

                return min(
                    elapsed,
                    45
                )


            calculated = (
                elapsed - 15
            )

            calculated = max(
                calculated,
                46
            )

            calculated = min(
                calculated,
                90
            )


            if (
                "half" in period_normal
                and
                "time" in period_normal
            ):
                return 45


            return calculated


        except Exception:
            pass


    return 0


# =========================================================
# CANLI MACLAR
# =========================================================

def get_live_matches():

    response = session.get(
        LIVE_FEED_URL,
        params={
            "_": int(
                time.time()
                * 1000
            )
        },
        headers={
            **HEADERS,
            "Cache-Control":
                "no-cache",
            "Pragma":
                "no-cache"
        },
        timeout=20
    )

    response.raise_for_status()

    matches = []


    for block in response.text.split(
        "~"
    ):

        fields = parse_fields(
            block
        )


        match_id = clean(
            fields.get(
                "AA"
            )
        )

        home = clean(
            fields.get(
                "AE"
            )
        )

        away = clean(
            fields.get(
                "AF"
            )
        )

        status = clean(
            fields.get(
                "AB"
            )
        )


        if (
            not match_id
            or not home
            or not away
            or status != "2"
        ):
            continue


        matches.append(
            {
                "id": match_id,
                "home": home,
                "away": away,

                "home_score":
                    int_value(
                        fields.get(
                            "AG"
                        )
                    ),

                "away_score":
                    int_value(
                        fields.get(
                            "AH"
                        )
                    ),

                "minute":
                    calculate_minute(
                        fields
                    ),

                "start":
                    fields.get(
                        "AD"
                    ),

                "period":
                    fields.get(
                        "BC"
                    ),
            }
        )


    return matches


# =========================================================
# SON SKOR KONTROLU
# =========================================================

def get_fresh_match_state(
    match_id
):

    try:

        response = session.get(
            LIVE_FEED_URL,
            params={
                "_": int(
                    time.time()
                    * 1000
                )
            },
            headers={
                **HEADERS,
                "Cache-Control":
                    "no-cache",
                "Pragma":
                    "no-cache"
            },
            timeout=20
        )


        if response.status_code != 200:
            return None


        for block in response.text.split(
            "~"
        ):

            fields = parse_fields(
                block
            )


            if clean(
                fields.get(
                    "AA"
                )
            ) != match_id:

                continue


            if clean(
                fields.get(
                    "AB"
                )
            ) != "2":

                return {
                    "live": False
                }


            return {
                "live": True,

                "home_score":
                    int_value(
                        fields.get(
                            "AG"
                        )
                    ),

                "away_score":
                    int_value(
                        fields.get(
                            "AH"
                        )
                    ),

                "minute":
                    calculate_minute(
                        fields
                    )
            }


        return None


    except Exception as e:

        log(
            "SON SKOR KONTROL HATA:",
            type(e).__name__,
            str(e)
        )

        return None


# =========================================================
# ISTATISTIK
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

    name = normalize_name(
        name
    )


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

    h = number(
        home
    )

    a = number(
        away
    )


    if (
        h is None
        or a is None
    ):
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


def get_stats(
    match_id
):

    stats = empty_stats()


    try:

        response = session.get(
            STAT_BASE_URL
            + match_id,
            params={
                "_": int(
                    time.time()
                    * 1000
                )
            },
            headers={
                **HEADERS,
                "Cache-Control":
                    "no-cache",
                "Pragma":
                    "no-cache"
            },
            timeout=20
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


        for part in raw.split(
            "¬"
        ):

            if "÷" not in part:
                continue


            key, value = part.split(
                "÷",
                1
            )


            key = (
                key
                .lstrip("~")
                .strip()
            )

            value = clean(
                value
            )


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

        log(
            "STAT HATA:",
            type(e).__name__,
            str(e)
        )

        return stats


# =========================================================
# ADAY OLUSTUKTAN SONRA YENI HUCUM VAR MI?
# =========================================================

def metric_total_or_none(
    stats,
    home_key,
    away_key
):

    home = stats.get(
        home_key
    )

    away = stats.get(
        away_key
    )

    if (
        home is None
        and
        away is None
    ):
        return None

    return (
        (home or 0)
        +
        (away or 0)
    )


def make_candidate_stats_snapshot(
    stats
):

    return {
        "xg":
            metric_total_or_none(
                stats,
                "xg_home",
                "xg_away"
            ),

        "shots":
            metric_total_or_none(
                stats,
                "shots_home",
                "shots_away"
            ),

        "sot":
            metric_total_or_none(
                stats,
                "sot_home",
                "sot_away"
            ),

        "big":
            metric_total_or_none(
                stats,
                "big_home",
                "big_away"
            ),

        "corners":
            metric_total_or_none(
                stats,
                "corners_home",
                "corners_away"
            ),
    }


def stat_delta(
    old_value,
    new_value
):

    if (
        old_value is None
        or
        new_value is None
    ):
        return 0

    return max(
        0,
        new_value
        - old_value
    )


def calculate_candidate_activity(
    old_snapshot,
    fresh_stats
):

    new_snapshot = (
        make_candidate_stats_snapshot(
            fresh_stats
        )
    )


    delta_xg = stat_delta(
        old_snapshot.get(
            "xg"
        ),
        new_snapshot.get(
            "xg"
        )
    )

    delta_shots = stat_delta(
        old_snapshot.get(
            "shots"
        ),
        new_snapshot.get(
            "shots"
        )
    )

    delta_sot = stat_delta(
        old_snapshot.get(
            "sot"
        ),
        new_snapshot.get(
            "sot"
        )
    )

    delta_big = stat_delta(
        old_snapshot.get(
            "big"
        ),
        new_snapshot.get(
            "big"
        )
    )

    delta_corners = stat_delta(
        old_snapshot.get(
            "corners"
        ),
        new_snapshot.get(
            "corners"
        )
    )


    activity_score = 0


    # +0.10 xG tek basina anlamli hareket
    if delta_xg >= 0.10:
        activity_score += 2


    # Tek normal sut zayif kanit.
    # Iki yeni sut daha guclu kanit.
    if delta_shots >= 2:
        activity_score += 2

    elif delta_shots >= 1:
        activity_score += 1


    # Bir isabetli sut tek basina yeterince guclu.
    if delta_sot >= 1:
        activity_score += 2


    # Buyuk sans cok guclu hareket.
    if delta_big >= 1:
        activity_score += 3


    # Korner destekleyici hareket.
    if delta_corners >= 2:
        activity_score += 2

    elif delta_corners >= 1:
        activity_score += 1


    # En az 2 puan istiyoruz.
    #
    # Ornek:
    # +1 isabetli = yeterli
    # +0.10 xG = yeterli
    # +1 buyuk sans = yeterli
    # +2 sut = yeterli
    # +1 sut +1 korner = yeterli
    # sadece +1 normal sut = yetersiz

    meaningful = (
        activity_score >= 2
    )


    details = {
        "xg":
            round(
                delta_xg,
                2
            ),

        "shots":
            int(
                delta_shots
            ),

        "sot":
            int(
                delta_sot
            ),

        "big":
            int(
                delta_big
            ),

        "corners":
            int(
                delta_corners
            ),

        "score":
            activity_score
    }


    return (
        meaningful,
        details
    )


# =========================================================
# ISTATISTIK GECMISI
# =========================================================

def stat_total(
    stats,
    home_key,
    away_key
):

    return (
        (stats.get(home_key) or 0)
        +
        (stats.get(away_key) or 0)
    )


def make_history_snapshot(
    match,
    stats
):

    return {
        "time": time.time(),
        "minute": match["minute"],

        "xg":
            stat_total(
                stats,
                "xg_home",
                "xg_away"
            ),

        "shots":
            stat_total(
                stats,
                "shots_home",
                "shots_away"
            ),

        "sot":
            stat_total(
                stats,
                "sot_home",
                "sot_away"
            ),

        "big":
            stat_total(
                stats,
                "big_home",
                "big_away"
            ),

        "corners":
            stat_total(
                stats,
                "corners_home",
                "corners_away"
            ),
    }


def find_history_baseline(
    history,
    now,
    minimum_age,
    maximum_age,
    target_age
):

    candidates = [
        item
        for item in history
        if (
            minimum_age
            <=
            now - item["time"]
            <=
            maximum_age
        )
    ]

    if not candidates:
        return None


    return min(
        candidates,
        key=lambda item: abs(
            (
                now
                - item["time"]
            )
            - target_age
        )
    )


# =========================================================
# SON 5-10 DK BASKI
# =========================================================

def calculate_recent_pressure(
    match,
    stats
):

    match_id = match["id"]
    now = time.time()


    current = make_history_snapshot(
        match,
        stats
    )


    history = match_history.setdefault(
        match_id,
        []
    )


    history[:] = [
        item
        for item in history
        if now - item["time"] <= 1200
    ]


    baseline = find_history_baseline(
        history,
        now,
        300,
        900,
        600
    )


    history.append(
        current
    )


    if baseline is None:
        return 0, None


    delta_xg = max(
        0,
        current["xg"]
        - baseline["xg"]
    )

    delta_shots = max(
        0,
        current["shots"]
        - baseline["shots"]
    )

    delta_sot = max(
        0,
        current["sot"]
        - baseline["sot"]
    )

    delta_big = max(
        0,
        current["big"]
        - baseline["big"]
    )

    delta_corners = max(
        0,
        current["corners"]
        - baseline["corners"]
    )


    pressure = 0


    if delta_xg >= 0.70:
        pressure += 12
    elif delta_xg >= 0.50:
        pressure += 10
    elif delta_xg >= 0.35:
        pressure += 8
    elif delta_xg >= 0.20:
        pressure += 5
    elif delta_xg >= 0.10:
        pressure += 3


    if delta_shots >= 7:
        pressure += 11
    elif delta_shots >= 5:
        pressure += 9
    elif delta_shots >= 4:
        pressure += 7
    elif delta_shots >= 3:
        pressure += 4
    elif delta_shots >= 2:
        pressure += 2


    if delta_sot >= 4:
        pressure += 13
    elif delta_sot >= 3:
        pressure += 10
    elif delta_sot >= 2:
        pressure += 8
    elif delta_sot >= 1:
        pressure += 4


    if delta_big >= 2:
        pressure += 7
    elif delta_big >= 1:
        pressure += 4


    if delta_corners >= 4:
        pressure += 4
    elif delta_corners >= 3:
        pressure += 3
    elif delta_corners >= 2:
        pressure += 2


    if (
        delta_shots >= 4
        and
        delta_sot >= 2
    ):
        pressure += 5


    if (
        delta_xg >= 0.35
        and
        delta_sot >= 2
    ):
        pressure += 5


    if (
        delta_big >= 1
        and
        delta_sot >= 2
    ):
        pressure += 4


    pressure = min(
        pressure,
        40
    )


    details = {
        "minutes":
            max(
                1,
                match["minute"]
                - baseline["minute"]
            ),

        "xg":
            round(
                delta_xg,
                2
            ),

        "shots":
            int(
                delta_shots
            ),

        "sot":
            int(
                delta_sot
            ),

        "big":
            int(
                delta_big
            ),

        "corners":
            int(
                delta_corners
            ),
    }


    return (
        pressure,
        details
    )


# =========================================================
# TEMPO
# =========================================================

def calculate_tempo_state(
    match_id
):

    history = match_history.get(
        match_id,
        []
    )


    if len(history) < 2:

        return {
            "ready": False,
            "ok": False,
            "dropped": False,
            "score": 0,
            "details": None
        }


    current = history[-1]
    now = current["time"]


    short_baseline = find_history_baseline(
        history[:-1],
        now,
        180,
        420,
        300
    )


    if short_baseline is None:

        return {
            "ready": False,
            "ok": False,
            "dropped": False,
            "score": 0,
            "details": None
        }


    recent_xg = max(
        0,
        current["xg"]
        - short_baseline["xg"]
    )

    recent_shots = max(
        0,
        current["shots"]
        - short_baseline["shots"]
    )

    recent_sot = max(
        0,
        current["sot"]
        - short_baseline["sot"]
    )

    recent_big = max(
        0,
        current["big"]
        - short_baseline["big"]
    )

    recent_corners = max(
        0,
        current["corners"]
        - short_baseline["corners"]
    )


    tempo_score = 0


    if recent_xg >= 0.35:
        tempo_score += 3
    elif recent_xg >= 0.20:
        tempo_score += 2
    elif recent_xg >= 0.10:
        tempo_score += 1


    if recent_shots >= 4:
        tempo_score += 3
    elif recent_shots >= 3:
        tempo_score += 2
    elif recent_shots >= 2:
        tempo_score += 1


    if recent_sot >= 2:
        tempo_score += 3
    elif recent_sot >= 1:
        tempo_score += 2


    if recent_big >= 1:
        tempo_score += 2


    if recent_corners >= 3:
        tempo_score += 2
    elif recent_corners >= 2:
        tempo_score += 1


    dead_tempo = (
        recent_xg < 0.08
        and recent_shots < 2
        and recent_sot < 1
        and recent_big < 1
        and recent_corners < 2
    )


    previous_baseline = find_history_baseline(
        history[:-1],
        now,
        480,
        720,
        600
    )


    tempo_dropped = False
    previous_intensity = None


    recent_intensity = (
        (recent_xg * 10)
        +
        (recent_shots * 1.2)
        +
        (recent_sot * 2.5)
        +
        (recent_big * 3.0)
        +
        (recent_corners * 0.7)
    )


    if previous_baseline is not None:

        previous_xg = max(
            0,
            short_baseline["xg"]
            - previous_baseline["xg"]
        )

        previous_shots = max(
            0,
            short_baseline["shots"]
            - previous_baseline["shots"]
        )

        previous_sot = max(
            0,
            short_baseline["sot"]
            - previous_baseline["sot"]
        )

        previous_big = max(
            0,
            short_baseline["big"]
            - previous_baseline["big"]
        )

        previous_corners = max(
            0,
            short_baseline["corners"]
            - previous_baseline["corners"]
        )


        previous_intensity = (
            (previous_xg * 10)
            +
            (previous_shots * 1.2)
            +
            (previous_sot * 2.5)
            +
            (previous_big * 3.0)
            +
            (previous_corners * 0.7)
        )


        if (
            previous_intensity >= 4.0
            and
            recent_intensity
            <
            previous_intensity * 0.45
        ):

            tempo_dropped = True


    tempo_ok = (
        tempo_score >= TEMPO_MIN_SCORE
        and not dead_tempo
        and not tempo_dropped
    )


    return {
        "ready": True,
        "ok": tempo_ok,
        "dropped": tempo_dropped,
        "score": tempo_score,

        "details": {
            "xg":
                round(
                    recent_xg,
                    2
                ),

            "shots":
                int(
                    recent_shots
                ),

            "sot":
                int(
                    recent_sot
                ),

            "big":
                int(
                    recent_big
                ),

            "corners":
                int(
                    recent_corners
                ),

            "dead":
                dead_tempo,

            "recent_intensity":
                round(
                    recent_intensity,
                    2
                ),

            "previous_intensity":
                (
                    round(
                        previous_intensity,
                        2
                    )
                    if previous_intensity
                    is not None
                    else None
                )
        }
    }


# =========================================================
# GOL PUANI
# =========================================================

def calculate_goal_score(
    match,
    stats,
    recent_pressure=0
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


    if corners >= 12:
        score += 7
    elif corners >= 9:
        score += 6
    elif corners >= 6:
        score += 4
    elif corners >= 4:
        score += 2


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


    score += recent_pressure


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

    if float(
        value
    ).is_integer():

        return str(
            int(value)
        )

    return str(
        round(
            value,
            2
        )
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
# BASLANGIC
# =========================================================

log(
    "GOL SINYAL BOTU BASLADI"
)

log(
    "SINYAL:",
    SIGNAL_THRESHOLD,
    "| TEMPO:",
    TEMPO_MIN_SCORE,
    "| 68-74 BEKLEME:",
    NORMAL_CONFIRM_SECONDS,
    "SN",
    "| 75+ BEKLEME:",
    STRONG_CONFIRM_SECONDS,
    "SN"
)

log(
    "DATABASE:",
    "VAR"
    if DATABASE_URL
    else "YOK"
)


init_database()


command_thread = threading.Thread(
    target=telegram_command_listener,
    daemon=True
)

command_thread.start()


# =========================================================
# ANA DONGU
# =========================================================

while True:

    try:

        matches = get_live_matches()

        log(
            "CANLI MAC:",
            len(matches)
        )


        active_match_ids = set()


        for match in matches:

            match_id = match["id"]

            active_match_ids.add(
                match_id
            )


            current_score = (
                match["home_score"],
                match["away_score"]
            )


            previous_score = last_scores.get(
                match_id
            )


            goal_just_happened = False


            if previous_score is None:

                last_scores[
                    match_id
                ] = current_score


            else:

                previous_total = (
                    previous_score[0]
                    +
                    previous_score[1]
                )

                current_total = (
                    current_score[0]
                    +
                    current_score[1]
                )


                if current_total > previous_total:

                    goal_just_happened = True


                    goal_cooldowns[
                        match_id
                    ] = (
                        time.time()
                        +
                        GOAL_COOLDOWN_SECONDS
                    )


                    match_history.pop(
                        match_id,
                        None
                    )

                    sent_signals.pop(
                        match_id,
                        None
                    )

                    pending_signals.pop(
                        match_id,
                        None
                    )


                    log(
                        "GOL:",
                        match["home"],
                        "-",
                        match["away"],
                        f"{previous_score[0]}-{previous_score[1]}",
                        "->",
                        f"{current_score[0]}-{current_score[1]}"
                    )


                last_scores[
                    match_id
                ] = current_score


            if not is_tracking_minute(
                match["minute"]
            ):

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            stats = get_stats(
                match_id
            )


            recent_pressure, pressure_details = (
                calculate_recent_pressure(
                    match,
                    stats
                )
            )


            tempo = calculate_tempo_state(
                match_id
            )


            if not is_valid_signal_minute(
                match["minute"]
            ):
                continue


            goal_score = calculate_goal_score(
                match,
                stats,
                recent_pressure
            )


            cooldown_until = (
                goal_cooldowns.get(
                    match_id,
                    0
                )
            )


            if time.time() < cooldown_until:

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            if goal_just_happened:
                continue


            if goal_score < SIGNAL_THRESHOLD:

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            if not tempo["ready"]:

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            if not tempo["ok"]:

                if match_id in pending_signals:

                    log(
                        "ADAY IPTAL TEMPO:",
                        match["home"],
                        "-",
                        match["away"]
                    )

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            previous = sent_signals.get(
                match_id
            )


            eligible_for_signal = False


            if previous is None:

                eligible_for_signal = True


            else:

                last_minute = previous[
                    "minute"
                ]

                last_score = previous[
                    "score"
                ]


                if (
                    match["minute"]
                    - last_minute
                    >= 15
                ):
                    eligible_for_signal = True


                if (
                    last_score < 75
                    and goal_score >= 75
                ):
                    eligible_for_signal = True


                if (
                    goal_score
                    >= last_score + 15
                ):
                    eligible_for_signal = True


            if not eligible_for_signal:

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            pending = pending_signals.get(
                match_id
            )


            # =================================================
            # YENI ADAY
            # =========================================================

            if pending is None:

                if goal_score >= 75:

                    confirm_seconds = (
                        STRONG_CONFIRM_SECONDS
                    )

                else:

                    confirm_seconds = (
                        NORMAL_CONFIRM_SECONDS
                    )


                pending_signals[
                    match_id
                ] = {
                    "created_at":
                        time.time(),

                    "score":
                        current_score,

                    "minute":
                        match["minute"],

                    "goal_score":
                        goal_score,

                    "tempo_score":
                        tempo["score"],

                    "confirm_seconds":
                        confirm_seconds,

                    # Aday olustugu andaki toplam
                    # istatistikleri sakla.
                    "stats_snapshot":
                        make_candidate_stats_snapshot(
                            stats
                        )
                }


                log(
                    "ADAY SINYAL:",
                    match["home"],
                    "-",
                    match["away"],
                    "| DK",
                    match["minute"],
                    "| PUAN",
                    goal_score,
                    "| TEMPO",
                    tempo["score"],
                    "| BEKLEME",
                    confirm_seconds,
                    "SN",
                    "| SKOR",
                    f"{current_score[0]}-{current_score[1]}"
                )

                continue


            pending_score = pending[
                "score"
            ]


            # =================================================
            # BEKLERKEN SKOR DEGISTI
            # =========================================================

            if current_score != pending_score:

                pending_signals.pop(
                    match_id,
                    None
                )


                pending_total = (
                    pending_score[0]
                    +
                    pending_score[1]
                )

                current_total = (
                    current_score[0]
                    +
                    current_score[1]
                )


                if current_total > pending_total:

                    goal_cooldowns[
                        match_id
                    ] = (
                        time.time()
                        +
                        GOAL_COOLDOWN_SECONDS
                    )

                    match_history.pop(
                        match_id,
                        None
                    )

                    last_scores[
                        match_id
                    ] = current_score


                    log(
                        "ADAY IPTAL: GOL OLDU",
                        match["home"],
                        "-",
                        match["away"]
                    )

                continue


            # =================================================
            # ADAYIN KENDI BEKLEME SURESI
            # =========================================================

            elapsed_candidate = (
                time.time()
                -
                pending["created_at"]
            )


            confirm_seconds = pending.get(
                "confirm_seconds",
                STRONG_CONFIRM_SECONDS
            )


            if (
                elapsed_candidate
                <
                confirm_seconds
            ):
                continue


            # =================================================
            # SON SKOR KONTROLU
            # =========================================================

            fresh = get_fresh_match_state(
                match_id
            )


            if (
                fresh is None
                or
                not fresh.get(
                    "live",
                    False
                )
            ):

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            fresh_score = (
                fresh["home_score"],
                fresh["away_score"]
            )


            pending_total = (
                pending_score[0]
                +
                pending_score[1]
            )

            fresh_total = (
                fresh_score[0]
                +
                fresh_score[1]
            )


            if fresh_total > pending_total:

                log(
                    "ADAY IPTAL:",
                    confirm_seconds,
                    "SN BEKLERKEN GOL",
                    match["home"],
                    "-",
                    match["away"]
                )


                goal_cooldowns[
                    match_id
                ] = (
                    time.time()
                    +
                    GOAL_COOLDOWN_SECONDS
                )


                match_history.pop(
                    match_id,
                    None
                )

                sent_signals.pop(
                    match_id,
                    None
                )

                pending_signals.pop(
                    match_id,
                    None
                )

                last_scores[
                    match_id
                ] = fresh_score

                continue


            if fresh_score != pending_score:

                pending_signals.pop(
                    match_id,
                    None
                )

                last_scores[
                    match_id
                ] = fresh_score

                continue


            fresh_minute = fresh[
                "minute"
            ]


            if not is_valid_signal_minute(
                fresh_minute
            ):

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            # =================================================
            # SON ISTATISTIK KONTROLU
            # =========================================================

            fresh_stats = get_stats(
                match_id
            )


            # =================================================
            # YENI: ADAYDAN SONRA HUCUM DEVAM ETTI MI?
            # =========================================================

            activity_ok, activity_details = (
                calculate_candidate_activity(
                    pending[
                        "stats_snapshot"
                    ],
                    fresh_stats
                )
            )


            if not activity_ok:

                log(
                    "ADAY IPTAL: YENI HUCUM YOK",
                    match["home"],
                    "-",
                    match["away"],
                    "| xG +",
                    activity_details["xg"],
                    "| SUT +",
                    activity_details["shots"],
                    "| ISABETLI +",
                    activity_details["sot"],
                    "| BUYUK +",
                    activity_details["big"],
                    "| KORNER +",
                    activity_details["corners"]
                )

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            log(
                "YENI HUCUM DOGRULANDI:",
                match["home"],
                "-",
                match["away"],
                "| xG +",
                activity_details["xg"],
                "| SUT +",
                activity_details["shots"],
                "| ISABETLI +",
                activity_details["sot"],
                "| BUYUK +",
                activity_details["big"],
                "| KORNER +",
                activity_details["corners"]
            )


            match["minute"] = (
                fresh_minute
            )

            match["home_score"] = (
                fresh["home_score"]
            )

            match["away_score"] = (
                fresh["away_score"]
            )


            # =================================================
            # SON BASKI + TEMPO
            # =========================================================

            final_recent_pressure, _ = (
                calculate_recent_pressure(
                    match,
                    fresh_stats
                )
            )


            final_tempo = calculate_tempo_state(
                match_id
            )


            if (
                not final_tempo["ready"]
                or
                not final_tempo["ok"]
            ):

                log(
                    "ADAY IPTAL: SON TEMPO",
                    match["home"],
                    "-",
                    match["away"]
                )

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            # =================================================
            # SON GOL PUANI
            # =========================================================

            final_goal_score = (
                calculate_goal_score(
                    match,
                    fresh_stats,
                    final_recent_pressure
                )
            )


            if (
                final_goal_score
                <
                SIGNAL_THRESHOLD
            ):

                log(
                    "ADAY IPTAL: SON PUAN",
                    final_goal_score,
                    match["home"],
                    "-",
                    match["away"]
                )

                pending_signals.pop(
                    match_id,
                    None
                )

                continue


            # =================================================
            # TELEGRAM
            # =========================================================

            message = make_signal_message(
                match,
                fresh_stats,
                final_goal_score
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
                        final_goal_score
                }


                last_scores[
                    match_id
                ] = (
                    match["home_score"],
                    match["away_score"]
                )


                log(
                    "SINYAL BASARILI:",
                    match["home"],
                    "-",
                    match["away"],
                    "| DK",
                    match["minute"],
                    "| PUAN",
                    final_goal_score,
                    "| BEKLEME",
                    confirm_seconds,
                    "SN"
                )


            pending_signals.pop(
                match_id,
                None
            )


        # =================================================
        # BITEN MACLARI TEMIZLE
        # =========================================================

        for old_id in list(
            match_history.keys()
        ):

            if old_id not in active_match_ids:

                match_history.pop(
                    old_id,
                    None
                )


        for old_id in list(
            sent_signals.keys()
        ):

            if old_id not in active_match_ids:

                sent_signals.pop(
                    old_id,
                    None
                )


        for old_id in list(
            last_scores.keys()
        ):

            if old_id not in active_match_ids:

                last_scores.pop(
                    old_id,
                    None
                )


        for old_id in list(
            goal_cooldowns.keys()
        ):

            if old_id not in active_match_ids:

                goal_cooldowns.pop(
                    old_id,
                    None
                )


        for old_id in list(
            pending_signals.keys()
        ):

            if old_id not in active_match_ids:

                pending_signals.pop(
                    old_id,
                    None
                )


    except Exception as e:

        log(
            "ANA HATA:",
            type(e).__name__,
            str(e)
        )


    time.sleep(
        POLL_SECONDS
    )
