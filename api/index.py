import json
import httpx
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
APPSSCRIPT_URL = os.getenv("APPSSCRIPT_URL")

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

def handle_command(text, chat_id):
    try:
        if text.startswith('/tambah'):
            parts = text.replace('/tambah', '').strip().split('|')
            if len(parts) >= 3:
                call_appscript('tambah', {  # ← tidak perlu cek response, AppScript yg kirim notif
                    'judul': parts[0].strip(),
                    'tgl': parts[1].strip(),
                    'jam': parts[2].strip(),
                    'shift': parts[3].strip() if len(parts) > 3 else ""
                })
                return None  # ← AppScript sudah kirim pesan ke Telegram
            return "Format: /tambah Judul | YYYY-MM-DD | HH:MM"
        
        elif text == '/list':
            call_appscript('list')  # ← AppScript langsung kirim list ke Telegram
            return None
        
        elif text.startswith('/hapus'):
            parts = text.split()
            if len(parts) > 1:
                call_appscript('hapus', {'id': int(parts[1])})  # ← sama
                return None
            return "Format: /hapus <id>"
        
        return "Gunakan: /tambah Judul | YYYY-MM-DD | HH:MM\n/list\n/hapus <id>"
    
    except Exception as e:
        return f"❌ Error: {str(e)}"

def kirim_pesan(chat_id, teks):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    with httpx.Client() as client:
        client.post(url, json={'chat_id': chat_id, 'text': teks})

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
                    response_text = handle_command(text, chat_id)
                    if response_text:  # ← hanya kirim kalau ada pesan (error/format salah)
                        kirim_pesan(chat_id, response_text)

            elif body.get('cron') == 'reminder':
                call_appscript('pengingat')  # ← AppScript yg kirim notif pengingat

        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'OK']

    except Exception as e:
        print(f"Handler error: {e}")
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
        return [str(e).encode()]
