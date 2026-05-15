import sqlite3
import asyncio
import os
from datetime import datetime, timedelta
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import schedule
import threading
import time

# ============ KONFIGURASI ============
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Inisialisasi DB
conn = sqlite3.connect("agenda.db", check_same_thread=False)
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

async def kirim_notif(pesan):
    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=pesan)

async def tambah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = ' '.join(context.args).split('|')
    if len(args) < 3:
        await update.message.reply_text("Format: /tambah Judul | YYYY-MM-DD | HH:MM")
        return
    
    judul = args[0].strip()
    tgl = args[1].strip()
    jam = args[2].strip()
    
    c.execute("INSERT INTO agenda (judul, tgl, jam) VALUES (?,?,?)", 
              (judul, tgl, jam))
    conn.commit()
    await update.message.reply_text(f"✅ Agenda '{judul}' tgl {tgl} jam {jam} ditambahkan!")

async def jaga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Format: /jaga [Pagi/Siang/Malam] | YYYY-MM-DD")
        return
    
    shift = args[0]
    tgl = args[1]
    jam = {"Pagi": "07:00", "Siang": "13:00", "Malam": "19:00"}.get(shift, "08:00")
    
    c.execute("INSERT INTO agenda (judul, tgl, jam, shift) VALUES (?,?,?,?)",
              (f"Jaga {shift}", tgl, jam, shift))
    conn.commit()
    await update.message.reply_text(f"✅ Shift {shift} tgl {tgl} jam {jam} ditambahkan!")

async def list_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c.execute("SELECT id, judul, tgl, jam FROM agenda WHERE tgl >= date('now') ORDER BY tgl, jam LIMIT 10")
    agendas = c.fetchall()
    if agendas:
        pesan = "📋 AGENDA MENDATANG:\n" + "\n".join([f"{id}. {j} - {t} jam {jm}" for id, j, t, jm in agendas])
    else:
        pesan = "✅ Tidak ada agenda mendatang"
    await update.message.reply_text(pesan)

async def hapus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: /hapus <id_agenda>")
        return
    id_agenda = context.args[0]
    c.execute("DELETE FROM agenda WHERE id=?", (id_agenda,))
    conn.commit()
    await update.message.reply_text(f"✅ Agenda ID {id_agenda} dihapus")

async def cek_pengingat():
    sekarang = datetime.now()
    
    c.execute("SELECT id, judul, tgl, jam, sudah_dikirim_h1, sudah_dikirim_2jam, sudah_dikirim_1jam FROM agenda")
    agendas = c.fetchall()
    
    for agenda in agendas:
        id_agenda, judul, tgl_str, jam_str, h1, dua_jam, satu_jam = agenda
        try:
            waktu_acara = datetime.strptime(f"{tgl_str} {jam_str}", "%Y-%m-%d %H:%M")
            selisih = (waktu_acara - sekarang).total_seconds() / 3600
            
            if 23 <= selisih < 24 and not h1:
                await kirim_notif(f"📅 PENGINGAT H-1\nJudul: {judul}\nBesok jam {jam_str}")
                c.execute("UPDATE agenda SET sudah_dikirim_h1=1 WHERE id=?", (id_agenda,))
                conn.commit()
            elif 1.9 <= selisih < 2.1 and not dua_jam:
                await kirim_notif(f"⚠️ 2 jam lagi!\n{judul} jam {jam_str}")
                c.execute("UPDATE agenda SET sudah_dikirim_2jam=1 WHERE id=?", (id_agenda,))
                conn.commit()
            elif 0.9 <= selisih < 1.1 and not satu_jam:
                await kirim_notif(f"🚨 1 JAM LAGI!🚨\n{judul} jam {jam_str}\nSiap-siap!")
                c.execute("UPDATE agenda SET sudah_dikirim_1jam=1 WHERE id=?", (id_agenda,))
                conn.commit()
        except:
            pass

async def daily_summary():
    hari_ini = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT judul, jam FROM agenda WHERE tgl=?", (hari_ini,))
    agendas = c.fetchall()
    
    if agendas:
        pesan = "📋 RINGKASAN AGENDA HARI INI:\n" + "\n".join([f"- {j[0]} jam {j[1]}" for j in agendas])
    else:
        pesan = "✅ Tidak ada agenda hari ini. Selamat istirahat!"
    
    await kirim_notif(pesan)

def jalan_schedule():
    schedule.every().day.at("05:00").do(lambda: asyncio.run(daily_summary()))
    schedule.every(1).minutes.do(lambda: asyncio.run(cek_pengingat()))
    
    while True:
        schedule.run_pending()
        time.sleep(30)

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("tambah", tambah))
    app.add_handler(CommandHandler("jaga", jaga))
    app.add_handler(CommandHandler("list", list_agenda))
    app.add_handler(CommandHandler("hapus", hapus))
    
    threading.Thread(target=jalan_schedule, daemon=True).start()
    
    print("Bot berjalan di Railway...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())