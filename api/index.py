import json
import httpx
import os
import re
from datetime import datetime, timedelta

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
APPSSCRIPT_URL = os.getenv("APPSSCRIPT_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ============ HELPER ============

def parse_tanggal(teks):
    t = teks.lower()
    sekarang = datetime.now()

    if 'besok' in t:
        return (sekarang + timedelta(days=1)).strftime("%Y-%m-%d")
    if 'lusa' in t:
        return (sekarang + timedelta(days=2)).strftime("%Y-%m-%d")
    if any(k in t for k in ['hari ini', 'sekarang', 'today']):
        return sekarang.strftime("%Y-%m-%d")
    if 'minggu depan' in t:
        return (sekarang + timedelta(days=7)).strftime("%Y-%m-%d")

    match = re.search(r'(?:tanggal|tgl)\s+(\d{1,2})', t)
    if match:
        tgl = int(match.group(1))
        bulan = sekarang.month
        tahun = sekarang.year
        if tgl < sekarang.day:
            bulan += 1
            if bulan > 12:
                bulan = 1
                tahun += 1
        return f"{tahun}-{bulan:02d}-{tgl:02d}"

    return None


def deteksi_intent_lokal(text):
    t = text.lower()

    # ── HAPUS harus dicek PERTAMA sebelum list ──
    if re.search(r'hapus|delete', t):
        id_match = re.search(r'(?:nomor|no|id)\s*(\d+)', t)
        if id_match:
            return {"action": "hapus", "id": int(id_match.group(1))}

        tgl = parse_tanggal(t)
        if tgl:
            nama_match = re.search(r'hapus\s+(?:jadwal|agenda)?\s*(.+?)\s+(?:tanggal|tgl|besok|lusa|hari ini)', t)
            if nama_match:
                judul = nama_match.group(1).strip()
                return {"action": "cari_hapus", "judul": judul, "tgl": tgl}

        return None  # hapus tapi tidak jelas → Groq

    # ── TAMBAH harus dicek sebelum list ──
    if re.search(r'tambah|catat|masukin|input|buat', t):
        return None  # serahkan ke Groq

    # ── JADWAL KOSONG ──
    if any(k in t for k in ['kosong', 'libur', 'ga ada jaga', 'tidak ada jaga', 'bebas', 'free']):
        sekarang = datetime.now()
        return {"action": "jadwal_kosong", "bulan": sekarang.month, "tahun": sekarang.year}

    # ── LIST TANGGAL TERTENTU ──
    match_tgl = re.search(r'(?:tanggal|tgl)\s+(\d{1,2})', t)
    if match_tgl and any(k in t for k in ['jaga', 'ada', 'agenda', 'jadwal', 'apa', 'gimana']):
        tgl_num = int(match_tgl.group(1))
        sekarang = datetime.now()
        bulan = sekarang.month
        tahun = sekarang.year
        if tgl_num < sekarang.day:
            bulan += 1
            if bulan > 12:
                bulan = 1
                tahun += 1
        tgl_str = f"{tahun}-{bulan:02d}-{tgl_num:02d}"
        return {"action": "list_filter", "tgl": tgl_str}

    # ── LIST HARI INI ──
    kata_hari_ini = ['hari ini', 'sekarang', 'today']
    kata_list = ['agenda', 'jadwal', 'tampil', 'tunjuk', 'lihat', 'cek', 'ada apa', 'apa aja', 'apaan', 'list', 'jaga']
    if any(k in t for k in kata_hari_ini) and any(k in t for k in kata_list):
        return {"action": "list_hari_ini"}

    # ── LIST BESOK ──
    if 'besok' in t and any(k in t for k in kata_list):
        return {"action": "list_besok"}

    # ── LIST SEMUA ──
    if any(k in t for k in kata_list):
        return {"action": "list"}

    return None  # → Groq


# ============ GROQ ============

def tanya_groq(pesan_user):
    sekarang = datetime.now().strftime("%Y-%m-%d %H:%M")

    system_prompt = f"""Kamu adalah asisten jadwal pribadi. Tanggal dan waktu sekarang: {sekarang}.
Tugasmu: pahami pesan user dan return HANYA JSON, tidak ada teks lain.

Format JSON:
{{
  "action": "tambah" | "list_filter" | "jadwal_kosong" | "tidak_dikenal",
  "judul": "nama agenda (untuk tambah)",
  "tgl": "YYYY-MM-DD (untuk tambah dan list_filter)",
  "jam": "HH:MM (untuk tambah, format 24 jam)",
  "shift": "pagi/siang/malam (opsional)",
  "bulan": 5 (angka bulan, untuk jadwal_kosong),
  "tahun": 2026 (untuk jadwal_kosong),
  "pesan": "respon jika tidak_dikenal"
}}

Aturan:
- "besok" = +1 hari, "lusa" = +2 hari, "minggu depan" = +7 hari
- "sore" = 15:00, "pagi" = 09:00, "malam" = 19:00, "siang" = 12:00, "subuh" = 05:00
- Jika jam tidak disebut, gunakan 09:00
- "tgl 24", "tanggal 24 bulan ini", "24 mei" + kata tanya → list_filter
- "hari kosong", "jadwal kosong", "kapan libur" → jadwal_kosong
- Jika tidak jelas → tidak_dikenal"""

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
        "max_tokens": 200
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(GROQ_URL, headers=headers, json=body)
        result = response.json()
        raw = result["choices"][0]["message"]["content"].strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        return json.loads(raw)


# ============ APPSCRIPT ============

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


# ============ TELEGRAM ============

def kirim_pesan(chat_id, teks):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    with httpx.Client() as client:
        client.post(url, json={'chat_id': chat_id, 'text': teks})


# ============ HANDLER ============

def handle_message(text, chat_id):
    try:
        intent = deteksi_intent_lokal(text)

        if intent is None:
            intent = tanya_groq(text)

        action = intent.get("action")

        if action == "list":
            call_appscript("list")

        elif action == "list_hari_ini":
            tgl = datetime.now().strftime("%Y-%m-%d")
            call_appscript("list_filter", {"tgl": tgl})

        elif action == "list_besok":
            tgl = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            call_appscript("list_filter", {"tgl": tgl})

        elif action == "list_filter":
            call_appscript("list_filter", {"tgl": intent.get("tgl")})

        elif action == "jadwal_kosong":
            call_appscript("jadwal_kosong", {
                "bulan": intent.get("bulan", datetime.now().month),
                "tahun": intent.get("tahun", datetime.now().year)
            })

        elif action == "tambah":
            judul = intent.get("judul", "")
            tgl = intent.get("tgl", "")
            jam = intent.get("jam", "09:00")
            shift = intent.get("shift", "")

            if not judul or not tgl:
                kirim_pesan(chat_id, "⚠️ Maaf, sebutkan nama agenda dan tanggalnya ya.")
                return

            call_appscript("tambah", {
                "judul": judul,
                "tgl": tgl,
                "jam": jam,
                "shift": shift
            })

        elif action == "hapus":
            id_agenda = intent.get("id")
            if not id_agenda:
                kirim_pesan(chat_id, "⚠️ Sebutkan nomor agenda yang mau dihapus.\nKetik 'lihat agenda' dulu untuk lihat nomornya.")
                return
            call_appscript("hapus", {"id": int(id_agenda)})

        elif action == "cari_hapus":
            call_appscript("cari_hapus", {
                "judul": intent.get("judul"),
                "tgl": intent.get("tgl")
            })

        elif action == "tidak_dikenal":
            pesan = intent.get("pesan", "Maaf, saya tidak mengerti.\n\nCoba:\n- \"tambah rapat besok jam 2 siang\"\n- \"agenda hari ini\"\n- \"jadwal kosong bulan ini\"\n- \"hapus nomor 3\"")
            kirim_pesan(chat_id, pesan)

        else:
            kirim_pesan(chat_id, "Maaf, saya tidak mengerti permintaanmu.")

    except Exception as e:
        print(f"Error handle_message: {e}")
        kirim_pesan(chat_id, f"❌ Error: {str(e)}")


# ============ WSGI ============

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
