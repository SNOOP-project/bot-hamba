import json
import httpx
import os
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
APPSSCRIPT_URL = os.getenv("APPSSCRIPT_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def tanya_groq(pesan_user):
    sekarang = datetime.now().strftime("%Y-%m-%d %H:%M")

    system_prompt = f"""Kamu adalah asisten jadwal pribadi. Tanggal dan waktu sekarang: {sekarang}.

Tugasmu: pahami pesan user dan return HANYA JSON, tidak ada teks lain.

Format JSON yang harus dikembalikan:
{{
  "action": "tambah" | "list" | "hapus" | "tidak_dikenal",
  "judul": "nama agenda (hanya untuk action tambah)",
  "tgl": "YYYY-MM-DD (hanya untuk action tambah, hitung dari tanggal sekarang)",
  "jam": "HH:MM (hanya untuk action tambah, format 24 jam)",
  "shift": "pagi/siang/malam (opsional, hanya jika user sebut shift)",
  "id": 123,
  "pesan": "respon natural jika tidak_dikenal"
}}

Aturan:
- "besok" = tanggal sekarang + 1 hari
- "lusa" = tanggal sekarang + 2 hari
- "minggu depan" = tanggal sekarang + 7 hari
- "sore" = 15:00, "pagi" = 09:00, "malam" = 19:00, "siang" = 12:00, "subuh" = 05:00
- Jika jam tidak disebutkan, gunakan 09:00
- Untuk list: apapun bermakna "lihat/tampilkan/cek agenda" -> action list
- Untuk hapus: butuh id dari user"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": pesan_user}
        ],
        "temperature": 0.1,
        "max_tokens": 300
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(GROQ_URL, headers=headers, json=body)
        result = response.json()
        raw = result["choices"][0]["message"]["content"].strip()

        # Bersihkan markdown code block jika ada
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        return json.loads(raw)


def call_appscript(action, data=None):
    payload = {"action": action}
    if data:
        payload.update(data)

    with httpx.Client(timeout=30.0) as client:
        url = APPSSCRIPT_URL
        for _ in range(5):
            response = client.post(url, json=payload, follow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                url = response.headers.get('location')
                continue
            break

        try:
            return response.json()
        except Exception:
            return {"success": False}


def kirim_pesan(chat_id, teks):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    with httpx.Client() as client:
        client.post(url, json={'chat_id': chat_id, 'text': teks})


def handle_message(text, chat_id):
    try:
        perintah = tanya_groq(text)
        action = perintah.get("action")

        if action == "tambah":
            judul = perintah.get("judul", "")
            tgl = perintah.get("tgl", "")
            jam = perintah.get("jam", "09:00")
            shift = perintah.get("shift", "")

            if not judul or not tgl:
                kirim_pesan(chat_id, "⚠️ Maaf, sebutkan nama agenda dan tanggalnya ya.")
                return

            call_appscript("tambah", {
                "judul": judul,
                "tgl": tgl,
                "jam": jam,
                "shift": shift
            })

        elif action == "list":
            call_appscript("list")

        elif action == "hapus":
            id_agenda = perintah.get("id")
            if not id_agenda:
                kirim_pesan(chat_id, "⚠️ Sebutkan nomor agenda yang mau dihapus. Ketik 'agenda apa aja' dulu untuk lihat nomornya.")
                return
            call_appscript("hapus", {"id": int(id_agenda)})

        elif action == "tidak_dikenal":
            pesan = perintah.get("pesan", "Maaf, saya tidak mengerti. Coba minta saya tambah, lihat, atau hapus agenda.")
            kirim_pesan(chat_id, pesan)

        else:
            kirim_pesan(chat_id, "Maaf, saya tidak mengerti permintaanmu.")

    except Exception as e:
        print(f"Error handle_message: {e}")
        kirim_pesan(chat_id, f"❌ Error: {str(e)}")


def app(environ, start_response):
    try:
        method = environ.get('REQUEST_METHOD', 'GET')
        if method == 'POST':
            content_length = int(environ.get('CONTENT_LENGTH', 0) or 0)
            raw_body = environ['wsgi.input'].read(content_length)
            if isinstance(raw_body, bytes):
                raw_body = raw_body.decode('utf-8')
            body = json.loads(raw_body)

            if 'message' in body:
                chat_id = body['message']['chat']['id']
                text = body['message'].get('text', '')
                if text:
                    handle_message(text, chat_id)

            elif body.get('cron') == 'reminder':
                call_appscript('pengingat')

        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'OK']

    except Exception as e:
        print(f"Handler error: {e}")
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
        return [str(e).encode()]
