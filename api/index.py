import json
import httpx
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
APPSCRIPT_URL = os.getenv("APPSSCRIPT_URL")  # URL dari AppScript

def call_appscript(action, data=None):
    """Panggil Google AppScript"""
    payload = {"action": action}
    if data:
        payload.update(data)
    
    with httpx.Client(timeout=30.0) as client:
        response = client.post(APPSSCRIPT_URL, json=payload)
        return response.json()

def handle_command(text, chat_id):
    try:
        if text.startswith('/tambah'):
            parts = text.replace('/tambah', '').strip().split('|')
            if len(parts) >= 3:
                result = call_appscript('tambah', {
                    'judul': parts[0].strip(),
                    'tgl': parts[1].strip(),
                    'jam': parts[2].strip(),
                    'shift': parts[3].strip() if len(parts) > 3 else ""
                })
                return result.get('message', 'Error')
            return "Format: /tambah Judul | YYYY-MM-DD | HH:MM"
        
        elif text == '/list':
            result = call_appscript('list')
            if result.get('success') and result.get('agenda'):
                agenda_list = result['agenda']
                if agenda_list:
                    pesan = "📋 AGENDA:\n"
                    for a in agenda_list[:10]:
                        pesan += f"{a['id']}. {a['judul']} - {a['tgl']} jam {a['jam']}\n"
                    return pesan
                return "✅ Tidak ada agenda"
            return "Error mengambil data"
        
        elif text.startswith('/hapus'):
            parts = text.split()
            if len(parts) > 1:
                result = call_appscript('hapus', {'id': int(parts[1])})
                return result.get('message', 'Error')
            return "Format: /hapus <id>"
        
        return "Gunakan: /tambah, /list, /hapus"
    
    except Exception as e:
        return f"❌ Error: {str(e)}"

def proses_pengingat():
    """Dipanggil cron job setiap menit"""
    result = call_appscript('pengingat')
    if result.get('success') and result.get('notifikasi'):
        for notif in result['notifikasi']:
            kirim_notif_sync(notif)

def kirim_notif_sync(pesan):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    with httpx.Client() as client:
        client.post(url, json={'chat_id': CHAT_ID, 'text': pesan})

# WSGI app (sama persis seperti sebelumnya)
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
                    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                    with httpx.Client() as client:
                        client.post(url, json={'chat_id': chat_id, 'text': response_text})
            elif body.get('cron') == 'reminder':
                proses_pengingat()
        
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'OK']
    
    except Exception as e:
        print(f"Handler error: {e}")
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
        return [str(e).encode()]
