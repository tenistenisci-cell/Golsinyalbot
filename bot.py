import os
import time
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

print("BOT BASLADI", flush=True)

if not TOKEN:
    print("HATA: TELEGRAM_BOT_TOKEN YOK", flush=True)

else:
    try:
        # Son Telegram mesajlarını al
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

        r = requests.get(url, timeout=20)
        data = r.json()

        print("GETUPDATES HTTP:", r.status_code, flush=True)

        if not data.get("ok"):
            print("TELEGRAM HATASI:", data, flush=True)

        else:
            updates = data.get("result", [])

            if not updates:
                print(
                    "MESAJ BULUNAMADI. TELEGRAM BOTUNA /start GONDER.",
                    flush=True
                )

            else:
                chat_id = None

                # En son mesajdan chat ID bul
                for update in reversed(updates):
                    msg = update.get("message")

                    if msg and msg.get("chat"):
                        chat_id = msg["chat"]["id"]
                        break

                if chat_id is None:
                    print("CHAT ID BULUNAMADI", flush=True)

                else:
                    print("CHAT ID BULUNDU", flush=True)

                    send_url = (
                        f"https://api.telegram.org/bot"
                        f"{TOKEN}/sendMessage"
                    )

                    response = requests.post(
                        send_url,
                        data={
                            "chat_id": chat_id,
                            "text": "✅ GOL SINYAL BOTU TELEGRAM TESTI BASARILI"
                        },
                        timeout=20
                    )

                    print(
                        "GONDERIM HTTP:",
                        response.status_code,
                        flush=True
                    )

                    print(
                        "GONDERIM CEVABI:",
                        response.text,
                        flush=True
                    )

    except Exception as e:
        print(
            "HATA:",
            type(e).__name__,
            str(e),
            flush=True
        )


# Railway container kapanmasın
while True:
    time.sleep(3600)
