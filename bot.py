from flask import Flask, request
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext,
    MessageHandler, Filters
)

import threading

# Inisialisasi Flask
app = Flask(__name__)
TOKEN = "6864590652:AAHhkS03TwV-IvUET4iDnZf0Qh5YJLRMW-k"  # Ganti dengan token bot Anda


# ===== KONFIGURASI =====
KATA = {
    "Restoran": ["Menu", "Pelayan", "Meja", "Piring", "Koki"],
    "Mall": ["Toko", "Promosi", "Escalator", "Food Court", "Parkir"],
    "Pasar": ["Pedagang", "Sayur", "Tawar", "Kerumunan", "Kios"],
    "Bandara": ["Check-in", "Bagasi", "Pramugari", "Boarding Pass", "Keamanan"]
}

# ===== STATUS PERMAINAN (PER GRUP) =====
games = {}

def get_game(chat_id):
    if chat_id not in games:
        games[chat_id] = {
            'pemain': [],
            'spy': [],
            'kata_rahasia': None,
            'sedang_berlangsung': False,
            'fase': None,
            'deskripsi_pemain': {},
            'suara': {},
            'tereliminasi': [],
            'skor': {}
        }
    return games[chat_id]

def reset_game(chat_id):
    games[chat_id] = {
        'pemain': [],
        'spy': [],
        'kata_rahasia': None,
        'sedang_berlangsung': False,
        'fase': None,
        'deskripsi_pemain': {},
        'suara': {},
        'tereliminasi': [],
        'skor': {}
    }

# ===== FUNGSI UTAMA =====
def mulai(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    update.message.reply_text(
        "🎮 *GAME TEBAK SPY*\n"
        "⚙️ **Cara Main:**\n"
        "1. Ketik `/gabung` untuk daftar\n"
        "2. Admin ketik `/mulai` untuk mulai permainan\n"
        "3. Bot akan membagikan peran (Spy/Warga)\n"
        "4. Deskripsikan kata rahasia tanpa bocorin!\n"
        "5. Voting untuk menemukan Spy!\n\n"
        "🏆 **Pemenang:**\n"
        "- Spy menang jika bertahan sampai akhir\n"
        "- Warga menang jika berhasil eliminasi semua Spy",
        parse_mode='Markdown'
    )

def gabung(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    game = get_game(chat_id)

    if game['sedang_berlangsung']:
        update.message.reply_text("⚠️ Permainan sudah berjalan! Tunggu game selanjutnya.")
        return

    pemain = update.effective_user
    nama = pemain.first_name
    id_pemain = pemain.id

    if id_pemain in [p['id'] for p in game['pemain']]:
        update.message.reply_text("😅 Kamu sudah terdaftar!")
        return

    if len(game['pemain']) >= 8:
        update.message.reply_text("🫣 Pemain sudah penuh (maks 8 orang)!")
        return

    game['pemain'].append({'id': id_pemain, 'nama': nama})
    update.message.reply_text(
        f"✅ {nama} bergabung! ({len(game['pemain'])}/8)\n"
        f"Admin kirim `/mulai` jika pemain cukup."
    )

def mulai_permainan(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    game = get_game(chat_id)

    if game['sedang_berlangsung']:
        update.message.reply_text("🔄 Permainan masih berjalan!")
        return

    jumlah_pemain = len(game['pemain'])
    
    # Validasi ketat jumlah pemain
    if jumlah_pemain < 3:
        update.message.reply_text(
            "❌ Minimal 3 pemain untuk memulai!\n"
            f"Pemain saat ini: {jumlah_pemain}/3"
        )
        return
    elif jumlah_pemain > 8:
        update.message.reply_text("❌ Maksimal 8 pemain!")
        return

    # Tetapkan jumlah spy (1 untuk 3-5 pemain, 2 untuk 6-8 pemain)
    jumlah_spy = 1 if jumlah_pemain <= 5 else 2
    
    # Memastikan jumlah spy tidak lebih dari jumlah pemain
    jumlah_spy = min(jumlah_spy, jumlah_pemain - 1)  # -1 untuk memastikan ada minimal 1 warga

    # Reset state permainan (TANPA menghapus pemain)
    reset_game(chat_id)
    game = get_game(chat_id)  # Ambil referensi terbaru
    game['sedang_berlangsung'] = True

    # Pilih spy secara acak
    game['spy'] = random.sample(game['pemain'], jumlah_spy)

    # Pilih kata rahasia
    kategori = random.choice(list(KATA.keys()))
    game['kata_rahasia'] = {
        'warga': random.choice(KATA[kategori]),
        'spy': random.choice(KATA[kategori]),
        'kategori': kategori
    }

    # Kirim peran SECARA PRIVAT ke setiap pemain
    for pemain in game['pemain']:
        try:
            if pemain in game['spy']:
                context.bot.send_message(
                    chat_id=pemain['id'],
                    text=(
                        f"🔎 *Kamu adalah SPY!*\n"
                        f"Kategori: {game['kata_rahasia']['kategori']}\n"
                        f"Kata SPY: **{game['kata_rahasia']['spy']}**\n\n"
                        "Deskripsikan kata ini seolah-olah kamu adalah warga biasa!\n"
                        "Kamu TIDAK TAHU kata yang dimiliki warga!"
                    ),
                    parse_mode='Markdown'
                )
            else:
                context.bot.send_message(
                    chat_id=pemain['id'],
                    text=(
                        f"🏡 *Kamu adalah WARGA*\n"
                        f"Kategori: {game['kata_rahasia']['kategori']}\n"
                        f"Kata kamu: **{game['kata_rahasia']['warga']}**\n\n"
                        "Deskripsikan kata ini tanpa menyebut kata langsung!"
                    ),
                    parse_mode='Markdown'
                )
        except Exception as e:
            print(f"Gagal mengirim pesan ke {pemain['nama']}: {e}")

    # Info ke grup
    update.message.reply_text(
        "🎭 *Peran sudah dibagikan!*\n"
        f"Spy: {len(game['spy'])} orang | Warga: {len(game['pemain']) - len(game['spy'])} orang\n\n"
        "⏳ *Fase Deskripsi dimulai!*\n"
        "Kirim deskripsi kata Anda via chat privat ke bot ini (waktu 35 detik).",
        parse_mode='Markdown'
    )

    game['fase'] = 'deskripsi'
    # Timer 35 detik untuk fase deskripsi
    context.job_queue.run_once(
        lambda ctx: akhir_deskripsi(ctx, chat_id), 
        35,
        context=chat_id
    )



def handle_deskripsi(update: Update, context: CallbackContext):
    if update.message.chat.type != 'private':
        return

    player_id = update.effective_user.id
    chat_id = None
    
    # Cari grup tempat pemain aktif
    for chat_id_game, game in games.items():
        if any(player['id'] == player_id for player in game['pemain']):
            chat_id = chat_id_game
            break
    
    if not chat_id:
        return

    game = get_game(chat_id)
    if game['fase'] != 'deskripsi':
        update.message.reply_text("🕒 Waktu deskripsi sudah habis!")
        return

    deskripsi = update.message.text
    game['deskripsi_pemain'][player_id] = deskripsi
    update.message.reply_text("✅ Deskripsi kamu sudah tercatat!")

def akhir_deskripsi(context: CallbackContext, chat_id):
    game = get_game(chat_id)

    # Kumpulkan deskripsi
    hasil_deskripsi = []
    for pemain in game['pemain']:
        if pemain['id'] in game['deskripsi_pemain']:
            hasil_deskripsi.append(
                f"▪️ {pemain['nama']}: {game['deskripsi_pemain'][pemain['id']]}"
            )
        else:
            hasil_deskripsi.append(f"▪️ {pemain['nama']}: ❌ Tidak mengirim")

    context.bot.send_message(
        chat_id=chat_id,
        text="📜 *Hasil Deskripsi:*\n" + "\n".join(hasil_deskripsi),
        parse_mode='Markdown'
    )

    # Mulai fase voting
    game['fase'] = 'voting'
    keyboard = [
        [InlineKeyboardButton(p['nama'], callback_data=str(i))]
        for i, p in enumerate(game['pemain'])
        if p not in game['tereliminasi']
    ]

    context.bot.send_message(
        chat_id=chat_id,
        text="🗳️ *Fase Voting!*\n"
             "Pilih siapa yang menurutmu Spy!\n"
             "Waktu: 20 detik.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

    # Timer fase voting
    context.job_queue.run_once(lambda ctx: akhir_voting(ctx, chat_id), 20)

def handle_vote(update: Update, context: CallbackContext):
    query = update.callback_query
    voter_id = query.from_user.id
    chat_id = query.message.chat.id
    game = get_game(chat_id)

    if game['fase'] != 'voting':
        query.answer("❌ Waktu voting sudah habis!")
        return

    if any(voter_id == p['id'] for p in game['tereliminasi']):
        query.answer("❌ Kamu sudah tereliminasi!")
        return

    if voter_id in game['suara']:
        query.answer("⚠️ Kamu sudah voting sebelumnya!")
        return

    try:
        voted_index = int(query.data)
        terpilih = game['pemain'][voted_index]
        game['suara'][voter_id] = terpilih
        query.answer(f"Kamu memilih: {terpilih['nama']}")
    except:
        query.answer("❌ Error, pilih kembali!")

def akhir_voting(context: CallbackContext, chat_id):
    game = get_game(chat_id)

    # Hitung suara
    hasil_voting = {}
    for pemain in game['pemain']:
        if pemain not in game['tereliminasi']:
            hasil_voting[pemain['nama']] = 0

    for voted_player in game['suara'].values():
        hasil_voting[voted_player['nama']] += 1

    # Urutkan berdasarkan suara terbanyak
    ranking = sorted(hasil_voting.items(), key=lambda x: x[1], reverse=True)

    # Tampilkan hasil voting
    hasil_text = "📊 *Hasil Voting:*\n"
    for nama, jumlah in ranking:
        hasil_text += f"• {nama}: {jumlah} suara\n"
    
    context.bot.send_message(
        chat_id=chat_id,
        text=hasil_text,
        parse_mode='Markdown'
    )

    # Periksa hasil
    if not ranking:  # Tidak ada yang memilih
        context.bot.send_message(
            chat_id=chat_id,
            text="🤷 *Tidak ada yang tereliminasi!* (Tidak ada voting)"
        )
    elif len(ranking) > 1 and ranking[0][1] == ranking[1][1]:  # Seri
        nama_seri = ", ".join([p[0] for p in ranking if p[1] == ranking[0][1]])
        context.bot.send_message(
            chat_id=chat_id,
            text=f"🤝 *Hasil seri!* ({nama_seri})\n"
                 "Tidak ada yang tereliminasi.",
            parse_mode='Markdown'
        )
    else:  # Eliminasi
        tereliminasi = next(p for p in game['pemain'] if p['nama'] == ranking[0][0])
        game['tereliminasi'].append(tereliminasi)

        # Periksa apakah spy tereliminasi
        is_spy = tereliminasi in game['spy']
        if is_spy:
            game['spy'].remove(tereliminasi)

        context.bot.send_message(
            chat_id=chat_id,
            text=f"☠️ *{tereliminasi['nama']} tereliminasi!* "
                 f"{'(Dia adalah Spy!)' if is_spy else ''}",
            parse_mode='Markdown'
        )

    # Cek kondisi kemenangan
    cek_pemenang(context, chat_id)

def cek_pemenang(context: CallbackContext, chat_id):
    game = get_game(chat_id)
    
    # Hitung pemain aktif
    pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
    jumlah_pemain = len(pemain_aktif)
    jumlah_spy = len(game['spy'])

    # Spy menang jika jumlah spy >= jumlah warga
    if jumlah_spy >= (jumlah_pemain - jumlah_spy):
        teks = f"🎭 *SPY MENANG!* 🎭\n\n"
        teks += f"🔎 Spy yang tersisa ({jumlah_spy}): " + ", ".join([s['nama'] for s in game['spy']]) + "\n"
        teks += f"📍 Kata Warga: {game['kata_rahasia']['warga']}\n"
        teks += f"🕵️ Kata Spy: {game['kata_rahasia']['spy']}\n\n"
        teks += "🏅 *Skor Akhir:*\n"

        for pemain in game['pemain']:
            if pemain in game['spy']:
                game['skor'][pemain['id']] = game['skor'].get(pemain['id'], 0) + 20
                teks += f"- {pemain['nama']}: +20 (Spy)\n"
            else:
                game['skor'][pemain['id']] = game['skor'].get(pemain['id'], 0) + 5
                teks += f"- {pemain['nama']}: +5\n"

    # Warga menang jika semua spy tereliminasi
    elif jumlah_spy == 0:
        teks = f"🏡 *WARGA MENANG!* 🏡\n\n"
        teks += f"✅ Semua Spy berhasil ditemukan!\n"
        teks += f"📍 Kata Rahasia: {game['kata_rahasia']['warga']}\n\n"
        teks += "🏅 *Skor Akhir:*\n"

        for pemain in game['pemain']:
            if pemain in game['tereliminasi']:
                game['skor'][pemain['id']] = game['skor'].get(pemain['id'], 0) + 0
                teks += f"- {pemain['nama']}: +0 (Tereliminasi)\n"
            else:
                game['skor'][pemain['id']] = game['skor'].get(pemain['id'], 0) + 10
                teks += f"- {pemain['nama']}: +10 (Warga)\n"
    
    else:  # Lanjut ronde berikutnya
        game['fase'] = 'deskripsi'
        game['deskripsi_pemain'] = {}
        game['suara'] = {}
        
        context.bot.send_message(
            chat_id=chat_id,
            text="🔄 *Memulai Ronde Baru!*\n"
                 "Deskripsikan kata kalian lagi (35 detik).",
            parse_mode='Markdown'
        )
        context.job_queue.run_once(lambda ctx: akhir_deskripsi(ctx, chat_id), 35)
        return

    # Jika permainan berakhir
    context.bot.send_message(
        chat_id=chat_id,
        text=teks,
        parse_mode='Markdown'
    )
    reset_game(chat_id)

# ===== COMMAND CANCEL =====
def cancel_game(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    game = get_game(chat_id)
    
    if not game['sedang_berlangsung']:
        update.message.reply_text("❌ Tidak ada permainan yang berjalan!")
        return
    
    reset_game(chat_id)
    update.message.reply_text("🔴 Permainan dibatalkan!")

# ===== RUN BOT =====

# Route untuk halaman utama Flask
@app.route('/')
def home():
    return "Bot Tebak Spy sedang aktif!"

# Fungsi untuk menjalankan bot Telegram
def run_bot():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Tambahkan handler (copy dari kode sebelumnya)
    dp.add_handler(CommandHandler("start", mulai))
    dp.add_handler(CommandHandler("gabung", gabung))
    dp.add_handler(CommandHandler("mulai", mulai_permainan))
    dp.add_handler(CommandHandler("cancel", cancel_game))
    dp.add_handler(CallbackQueryHandler(handle_vote))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_deskripsi))

    # Mulai polling
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    # Jalankan bot Telegram di thread terpisah
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    # Jalankan Flask
    app.run(host='0.0.0.0', port=8000)

