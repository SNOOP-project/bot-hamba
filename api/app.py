import json
import requests
import os
import sqlite3
from datetime import datetime
from telegram import Bot
from telegram.ext import Application

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Inisialisasi DB (pakai /tmp karena Vercel read-only selain /tmp)
def init_db():
    conn = sqlite3.connect('/tmp/agenda.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS agenda 
                 (id INTEGER PRIMARY KEY, 
                  judul TEXT, 
                  tgl TEXT, 
                  jam TEXT, 
                  sudah_dikirim_h1 INTEGER DEFAULT 0,
                  sudah_dikirim_2jam INTEGER DEFAULT 0,
                  sudah_dikirim_1jam INTEGER DEFAULT 0)''')
    conn.commit()
    return conn

def handle_command(text, chat_id):
    conn = init_db()
    c = conn.cursor()
    
    if text == '/start':
        return "Halo! Saya bot pengingat residen neurologi.\n\nPerintah:\n/tambah Judul | YYYY-MM-DD | HH:MM\n/list\n/hapus <id>"
    
    elif text.startswith('/tambah'):
        try:
            parts = text.replace('/tambah', '').strip().split('|')
            if len(parts) >= 3:
                judul = parts[0].strip()
                tgl = parts[1].strip()
                jam = parts[2].strip()
                c.execute("INSERT INTO agenda (judul, tgl, jam) VALUES (?,?,?)", 
                          (judul, tgl, jam))
                conn.commit()
                return f"✅ Agenda '{judul}' tgl {tgl} jam {jam} ditambahkan!"
            return "Format salah. Contoh: /tambah Ujian | 2026-05-20 | 13:00"
        except Exception as e:
            return f"Error: {e}"
    
    elif text == '/list':
        c.execute("SELECT id, judul, tgl, jam FROM agenda WHERE tgl >= date('now') ORDER BY tgl, jam LIMIT 10")
        agendas = c.fetchall()
        if agendas:
            hasil = "📋 AGENDA:\n"
            for id, judul, tgl, jam in agendas:
                hasil += f"{id}. {judul} - {tgl} jam {jam}\n"
            return hasil
        return "✅ Tidak ada agenda"
    
    elif text.startswith('/hapus'):
        parts = text.split()
        if len(parts) > 1:
            c.execute("DELETE FROM agenda WHERE id=?", (parts[1],))
            conn.commit()
            return f"✅ Agenda ID {parts[1]} dihapus"
        return "Format: /hapus <id>"
    
    conn.close()
    return "Perintah tidak dikenal. Gunakan: /tambah, /list, /hapus"

def handler(request, context):
    """Entry point Vercel"""
    
    # Handle POST dari Telegram
    if request.method == 'POST':
        body = json.loads(request.body)
        
        # Pesan dari user
        if 'message' in body:
            chat_id = body['message']['chat']['id']
            text = body['message'].get('text', '')
            
            response = handle_command(text, chat_id)
            
            # Kirim balasan ke Telegram
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={'chat_id': chat_id, 'text': response})
        
        # Handle cron job untuk pengingat (nanti)
        elif body.get('type') == 'reminder':
            # Proses pengingat otomatis
            pass
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'ok': True})
    }
