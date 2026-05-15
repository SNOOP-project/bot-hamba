import json
import httpx
import asyncio
from datetime import datetime
import sqlite3
import os
from telegram import Bot

# Konfigurasi
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


def init_db():
    conn = sqlite3.connect('/tmp/agenda.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS agenda 
                 (id INTEGER PRIMARY KEY, 
                  judul TEXT, 
                  tgl TEXT, 
                  jam TEXT, 
                  shift TEXT, 
                  sudah_dikirim_h1 INTEGER DEFAULT 0,
                  sudah_dikirim_2jam INTEGER DEFAULT 0,
                  sudah_dikirim_1jam INTEGER DEFAULT 0)''')
    conn.commit()
    return conn


def kirim_notif_sync(pesan):
    """Kirim notifikasi ke Telegram via HTTP langsung (synchronous)."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    with httpx.Client() as client:
        client.post(url, json={'chat_id': CHAT_ID, 'text': pesan})


def proses_pengingat():
    conn = init_db()
    c = conn.cursor()
    sekarang = datetime.now()

    c.execute("SELECT id, judul, tgl, jam, sudah_dikirim_h1, sudah_dikirim_2jam, sudah_dikirim_1jam FROM agenda")
    agendas = c.fetchall()

    for agenda in agendas:
        id_agenda, judul, tgl_str, jam_str, h1, dua_jam, satu_jam = agenda
        try:
            waktu_acara = datetime.strptime(f"{tgl_str} {jam_str}", "%Y-%m-%d %H:%M")
            selisih = (waktu_acara - sekarang).total_seconds() / 3600

            if 23 <= selisih < 24 and not h1:
                kirim_notif_sync(f"⏰ Pengingat H-1\n📌 {judul}\n📅 {tgl_str} pukul {jam_str}")
                c.execute("UPDATE agenda SET sudah_dikirim_h1=1 WHERE id=?", (id_agenda,))
                conn.commit()

            elif 1.9 <= selisih < 2.1 and not dua_jam:
                kirim_notif_sync(f"⏰ Pengingat 2 Jam Lagi\n📌 {judul}\n📅 {tgl_str} pukul {jam_str}")
                c.execute("UPDATE agenda SET sudah_dikirim_2jam=1 WHERE id=?", (id_agenda,))
                conn.commit()

            elif 0.9 <= selisih < 1.1 and not satu_jam:
                kirim_notif_sync(f"⏰ Pengingat 1 Jam Lagi\n📌 {judul}\n📅 {tgl_str} pukul {jam_str}")
                c.execute("UPDATE agenda SET sudah_dikirim_1jam=1 WHERE id=?", (id_agenda,))
                conn.commit()

        except Exception as e:
            print(f"Error proses agenda {id_agenda}: {e}")

    conn.close()


def handle_command(text, chat_id):
    conn = init_db()
    c = conn.cursor()
    result = "Gunakan:\n/tambah Judul | YYYY-MM-DD | HH:MM\n/list\n/hapus <id>"

    try:
        if text.startswith('/tambah'):
            parts = text.replace('/tambah', '').strip().split('|')
            if len(parts) >= 3:
                judul = parts[0].strip()
                tgl = parts[1].strip()
                jam = parts[2].strip()
                c.execute("INSERT INTO agenda (judul, tgl, jam) VALUES (?,?,?)",
                          (judul, tgl, jam))
                conn.commit()
                result = f"✅ Agenda '{judul}' tgl {tgl} jam {jam} ditambahkan!"
            else:
                result = "Format: /tambah Judul | YYYY-MM-DD | HH:MM"

        elif text.startswith('/list'):
            c.execute("SELECT id, judul, tgl, jam FROM agenda WHERE tgl >= date('now') ORDER BY tgl, jam")
            agendas = c.fetchall()
            if agendas:
                result = "📋 AGENDA:\n" + "\n".join(
                    [f"{row[0]}. {row[1]} - {row[2]} jam {row[3]}" for row in agendas]
                )
            else:
                result = "✅ Tidak ada agenda"

        elif text.startswith('/hapus'):
            parts = text.split()
            if len(parts) > 1:
                c.execute("DELETE FROM agenda WHERE id=?", (parts[1],))
                conn.commit()
                result = f"✅ Agenda ID {parts[1]} dihapus"
            else:
                result = "Format: /hapus <id>"

    except Exception as e:
        result = f"❌ Error: {str(e)}"

    finally:
        conn.close()

    return result


def handler(request):
    try:
        # Parse body — bisa bytes atau string tergantung Vercel runtime
        raw_body = request.body
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode('utf-8')
        body = json.loads(raw_body)

        if request.method == 'POST':
            # Handle webhook dari Telegram
            if 'message' in body:
                chat_id = body['message']['chat']['id']
                text = body['message'].get('text', '')

                if text:
                    response_text = handle_command(text, chat_id)
                    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                    with httpx.Client() as client:
                        client.post(url, json={'chat_id': chat_id, 'text': response_text})

            # Handle cron job (pengingat)
            elif body.get('cron') == 'reminder':
                proses_pengingat()

    except Exception as e:
        print(f"Handler error: {e}")
        return {'statusCode': 500, 'body': str(e)}

    return {'statusCode': 200, 'body': 'OK'}
