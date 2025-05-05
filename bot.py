from flask import Flask
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext,
    MessageHandler, Filters
)
import threading
import logging

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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
            'warga': [],
            'kata_rahasia': None,
            'sedang_berlangsung': False,
            'fase': None,
            'deskripsi_pemain': {},
            'suara': {},
            'tereliminasi': [],
            'skor': {},
            'message_id': None  # Untuk menyimpan ID pesan voting terakhir
        }
    return games[chat_id]

def reset_game(chat_id):
    if chat_id in games:
        del games[chat_id]

def is_admin(update: Update, context: CallbackContext):
    """Cek apakah pengirim adalah admin grup"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    member = context.bot.get_chat_member(chat_id, user_id)
    return member.status in ['administrator', 'creator']

def is_private(update: Update):
    """Cek apakah pesan berasal dari chat privat"""
    return update.effective_chat.type == 'private'

# ===== COMMAND HANDLERS =====
def start(update: Update, context: CallbackContext):
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
    if is_private(update):
        update.message.reply_text("❌ Silakan gabung di grup yang sedang bermain!")
        return

    chat_id = update.effective_chat.id
    game = get_game(chat_id)

    if game['sedang_berlangsung']:
        update.message.reply_text("⚠️ Permainan sudah berjalan! Tunggu game selanjutnya.")
        return

    pemain = update.effective_user
    nama = pemain.first_name
    id_pemain = pemain.id

    if any(p['id'] == id_pemain for p in game['pemain']):
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
    if is_private(update):
        update.message.reply_text("❌ Hanya bisa dilakukan di grup!")
        return
        
    #if not is_admin(update, context):
        #update.message.reply_text("❌ Hanya admin yang bisa memulai permainan!")
        #return

    chat_id = update.effective_chat.id
    game = get_game(chat_id)

    if game['sedang_berlangsung']:
        update.message.reply_text("🔄 Permainan masih berjalan!")
        return

    jumlah_pemain = len(game['pemain'])
    
    if jumlah_pemain < 3:
        update.message.reply_text(
            "❌ Minimal 3 pemain untuk memulai!\n"
            f"Pemain saat ini: {jumlah_pemain}/3"
        )
        return
    
    # Reset state permainan
    game = get_game(chat_id)
    game.update({  # Hanya reset variabel tanpa menghapus pemain
        'spy': [],
        'warga': [],
        'kata_rahasia': None,
        'sedang_berlangsung': True,
        'fase': None,
        'deskripsi_pemain': {},
        'suara': {},
        'tereliminasi': [],
        'skor': {},
        'message_id': None
    })

    # Tentukan jumlah spy (1 untuk 3-4 pemain, 2 untuk 5+ pemain)
    num_spies = 1 if jumlah_pemain <= 4 else 2
    
    # Pilih spy secara acak
    all_players = game['pemain'].copy()
    random.shuffle(all_players)
    game['spy'] = all_players[:num_spies]
    game['warga'] = all_players[num_spies:]

    # Pilih kata rahasia
    kategori = random.choice(list(KATA.keys()))
    kata_warga = random.choice(KATA[kategori])
    kata_spy = random.choice(KATA[kategori])
    
    # Pastikan kata spy dan warga tidak sama
    while kata_spy == kata_warga:
        kata_spy = random.choice(KATA[kategori])
    
    game['kata_rahasia'] = {
        'warga': kata_warga,
        'spy': kata_spy,
        'kategori': kategori
    }

    # Kirim peran ke pemain (privat)
    for pemain in game['pemain']:
        try:
            if pemain in game['spy']:
                role_text = (
                    f"🔎 *Kamu adalah SPY!*\n"
                    f"Kategori: {game['kata_rahasia']['kategori']}\n"
                    f"Kata SPY: **{game['kata_rahasia']['spy']}**\n\n"
                    "Deskripsikan kata ini seolah-olah kamu adalah warga biasa!\n"
                    "Kamu TIDAK TAHU kata yang dimiliki warga!"
                )
            else:
                role_text = (
                    f"🏡 *Kamu adalah WARGA*\n"
                    f"Kategori: {game['kata_rahasia']['kategori']}\n"
                    f"Kata kamu: **{game['kata_rahasia']['warga']}**\n\n"
                    "Deskripsikan kata ini tanpa menyebut kata langsung!"
                )
            
            # Kirim pesan privat
            context.bot.send_message(
                chat_id=pemain['id'],
                text=role_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Gagal kirim pesan ke {pemain['nama']}: {e}")
            # Beri tahu di grup jika ada yang gagal
            update.message.reply_text(
                f"❌ Tidak bisa mengirim pesan ke {pemain['nama']}. "
                "Pastikan sudah memulai chat dengan bot!"
            )
            reset_game(chat_id)
            return

    # Info ke grup
    msg = update.message.reply_text(
        "🎭 *Peran sudah dibagikan!*\n"
        f"Spy: {len(game['spy'])} orang | Warga: {len(game['warga'])} orang\n\n"
        "⏳ *Fase Deskripsi dimulai!*\n"
        "Kirim deskripsi kata Anda via chat privat ke bot ini (waktu 35 detik).",
        parse_mode='Markdown'
    )

    game['fase'] = 'deskripsi'
    game['message_id'] = msg.message_id  # Simpan ID pesan untuk edit nanti
    
    # Timer fase deskripsi
    context.job_queue.run_once(
        lambda ctx: akhir_deskripsi(ctx, chat_id),
        35,
        context=chat_id,
        name=f"deskripsi_{chat_id}"
    )

def akhir_deskripsi(context: CallbackContext, chat_id):
    job = context.job
    game = get_game(chat_id)
    
    if not game['sedang_berlangsung'] or game['fase'] != 'deskripsi':
        return

    # Beri tahu di grup siapa yang belum mengirim deskripsi
    belum_kirim = []
    for pemain in game['pemain']:
        if pemain['id'] not in game['deskripsi_pemain'] and pemain not in game['tereliminasi']:
            belum_kirim.append(pemain['nama'])
    
    if belum_kirim:
        context.bot.send_message(
            chat_id=chat_id,
            text="❌ Pemain berikut belum mengirim deskripsi: " + ", ".join(belum_kirim)
        )

    # Kumpulkan deskripsi yang ada
    hasil_deskripsi = []
    for pemain in game['pemain']:
        if pemain['id'] in game['deskripsi_pemain']:
            hasil_deskripsi.append(
                f"▪️ {pemain['nama']}: {game['deskripsi_pemain'][pemain['id']]}"
            )
        else:
            hasil_deskripsi.append(f"▪️ {pemain['nama']}: ❌ Tidak mengirim")

    # Kirim hasil deskripsi
    try:
        if game['message_id']:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game['message_id'],
                text="📜 *Hasil Deskripsi:*\n" + "\n".join(hasil_deskripsi),
                parse_mode='Markdown'
            )
        else:
            game['message_id'] = context.bot.send_message(
                chat_id=chat_id,
                text="📜 *Hasil Deskripsi:*\n" + "\n".join(hasil_deskripsi),
                parse_mode='Markdown'
            ).message_id
    except Exception as e:
        logger.error(f"Gagal edit/send pesan deskripsi: {e}")
        game['message_id'] = None

    # Mulai fase voting
    game['fase'] = 'voting'
    pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
    
    if len(pemain_aktif) < 2:  # Minimal 2 pemain untuk voting
        cek_pemenang(context, chat_id)
        return

    # Buat keyboard voting
    keyboard = []
    row = []
    for i, p in enumerate(pemain_aktif):
        row.append(InlineKeyboardButton(p['nama'], callback_data=f"vote_{p['id']}"))
        if len(row) == 2:  # 2 tombol per baris
            keyboard.append(row)
            row = []
    if row:  # Tambahkan sisa tombol
        keyboard.append(row)

    try:
        if game['message_id']:
            msg = context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game['message_id'],
                text="🗳️ *Fase Voting!*\nPilih siapa yang menurutmu Spy!\nWaktu: 20 detik.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            msg = context.bot.send_message(
                chat_id=chat_id,
                text="🗳️ *Fase Voting!*\nPilih siapa yang menurutmu Spy!\nWaktu: 20 detik.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            game['message_id'] = msg.message_id
    except Exception as e:
        logger.error(f"Gagal kirim pesan voting: {e}")
        return

    # Timer fase voting
    context.job_queue.run_once(
        lambda ctx: akhir_voting(ctx, chat_id),
        20,
        context=chat_id,
        name=f"voting_{chat_id}"
    )

def handle_vote(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    voter_id = query.from_user.id
    chat_id = query.message.chat.id
    game = get_game(chat_id)

    if not game['sedang_berlangsung'] or game['fase'] != 'voting':
        query.edit_message_text("❌ Waktu voting sudah habis!")
        return

    # Cek apakah voter sudah tereliminasi
    if any(voter_id == p['id'] for p in game['tereliminasi']):
        query.answer("❌ Kamu sudah tereliminasi!", show_alert=True)
        return

    # Cek apakah voter sudah voting
    if voter_id in game['suara']:
        query.answer("⚠️ Kamu sudah voting sebelumnya!", show_alert=True)
        return

    try:
        # Parse data callback (format: vote_<player_id>)
        _, player_id_str = query.data.split('_')
        player_id = int(player_id_str)
        
        # Cari pemain yang dipilih
        terpilih = next((p for p in game['pemain'] if p['id'] == player_id and p not in game['tereliminasi']), None)
        
        if not terpilih:
            query.answer("❌ Pemain tidak valid!", show_alert=True)
            return

        # Catat voting
        game['suara'][voter_id] = terpilih
        query.answer(f"Kamu memilih: {terpilih['nama']}")
        
        # Beri feedback visual
        for voter in game['suara']:
            if voter == voter_id:
                context.bot.answer_callback_query(
                    callback_query_id=query.id,
                    text=f"Kamu memilih: {terpilih['nama']}",
                    show_alert=False
                )
                break

    except Exception as e:
        logger.error(f"Error handle vote: {e}")
        query.answer("❌ Error terjadi saat voting!", show_alert=True)

def akhir_voting(context: CallbackContext, chat_id):
    game = get_game(chat_id)
    
    if not game['sedang_berlangsung'] or game['fase'] != 'voting':
        return

    # Hitung suara
    hasil_voting = {}
    pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
    
    for p in pemain_aktif:
        hasil_voting[p['id']] = {'nama': p['nama'], 'suara': 0}
    
    for voted_player in game['suara'].values():
        hasil_voting[voted_player['id']]['suara'] += 1

    # Urutkan berdasarkan suara terbanyak
    ranking = sorted(hasil_voting.values(), key=lambda x: x['suara'], reverse=True)

    # Tampilkan hasil voting
    hasil_text = "📊 *Hasil Voting:*\n"
    for i, p in enumerate(ranking):
        hasil_text += f"• {p['nama']}: {p['suara']} suara\n"
    
    try:
        if game['message_id']:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game['message_id'],
                text=hasil_text,
                parse_mode='Markdown'
            )
        else:
            game['message_id'] = context.bot.send_message(
                chat_id=chat_id,
                text=hasil_text,
                parse_mode='Markdown'
            ).message_id
    except Exception as e:
        logger.error(f"Gagal edit/send hasil voting: {e}")

    # Tentukan pemain yang tereliminasi
    if not ranking or len(ranking) == 0:  # Tidak ada yang voting
        tereliminasi = None
    elif len(ranking) > 1 and ranking[0]['suara'] == ranking[1]['suara']:  # Seri
        nama_seri = ", ".join([p['nama'] for p in ranking if p['suara'] == ranking[0]['suara']])
        context.bot.send_message(
            chat_id=chat_id,
            text=f"🤝 *Hasil seri!* ({nama_seri})\nTidak ada yang tereliminasi.",
            parse_mode='Markdown'
        )
        tereliminasi = None
    else:  # Ada yang tereliminasi
        tereliminasi = next(p for p in pemain_aktif if p['id'] == ranking[0]['id'])
        game['tereliminasi'].append(tereliminasi)

        # Periksa apakah dia spy
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
    
    # Hitung pemain aktif dan spy tersisa
    pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
    jumlah_pemain = len(pemain_aktif)
    jumlah_spy = len(game['spy'])

    if jumlah_pemain == 0:
        # Kasus khusus jika semua tereliminasi
        teks = "🤷 *Permainan berakhir tanpa pemenang!*\nSemua pemain tereliminasi."
    elif jumlah_spy >= (jumlah_pemain - jumlah_spy):  # Spy menang
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
    elif jumlah_spy == 0:  # Warga menang
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
        
        # Timer fase deskripsi baru
        context.job_queue.run_once(
            lambda ctx: akhir_deskripsi(ctx, chat_id),
            35,
            context=chat_id,
            name=f"deskripsi_{chat_id}"
        )
        return

    # Jika permainan berakhir
    context.bot.send_message(
        chat_id=chat_id,
        text=teks,
        parse_mode='Markdown'
    )
    reset_game(chat_id)

def handle_deskripsi(update: Update, context: CallbackContext):
    if not is_private(update):
        return

    player_id = update.effective_user.id
    deskripsi = update.message.text
    
    # Cari game yang sedang berlangsung dengan pemain ini
    found = False
    for chat_id in games:
        game = games[chat_id]
        if game['sedang_berlangsung'] and game['fase'] == 'deskripsi':
            if any(p['id'] == player_id for p in game['pemain'] if p not in game['tereliminasi']):
                game['deskripsi_pemain'][player_id] = deskripsi
                update.message.reply_text("✅ Deskripsi kamu sudah tercatat!")
                found = True
                break
    
    if not found:
        update.message.reply_text("ℹ️ Tidak ada permainan yang membutuhkan deskripsi darimu.")

def cancel_game(update: Update, context: CallbackContext):
    if is_private(update):
        update.message.reply_text("❌ Hanya bisa dilakukan di grup!")
        return
        
    if not is_admin(update, context):
        update.message.reply_text("❌ Hanya admin yang bisa membatalkan permainan!")
        return

    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    
    if not game['sedang_berlangsung']:
        update.message.reply_text("❌ Tidak ada permainan yang berjalan!")
        return

    # Hapus semua job yang terkait dengan game ini
    current_jobs = context.job_queue.get_jobs_by_name(f"deskripsi_{chat_id}")
    current_jobs += context.job_queue.get_jobs_by_name(f"voting_{chat_id}")
    
    for job in current_jobs:
        job.schedule_removal()
    
    reset_game(chat_id)
    update.message.reply_text("🔴 Permainan dibatalkan!")

def daftar_pemain(update: Update, context: CallbackContext):
    if is_private(update):
        update.message.reply_text("❌ Hanya bisa dilakukan di grup!")
        return

    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    
    if not game['pemain']:
        update.message.reply_text("Belum ada pemain yang bergabung!")
        return
    
    daftar = "\n".join([f"{i+1}. {p['nama']}" for i, p in enumerate(game['pemain'])])
    update.message.reply_text(
        f"👥 Daftar Pemain ({len(game['pemain'])} orang):\n{daftar}"
    )

def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    
    if update and update.effective_message:
        update.effective_message.reply_text(
            "❌ Error terjadi. Silakan coba lagi atau mulai permainan baru."
        )

# ===== RUN BOT =====
def run_bot():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("gabung", gabung))
    dp.add_handler(CommandHandler("mulai", mulai_permainan))
    dp.add_handler(CommandHandler("cancel", cancel_game))
    dp.add_handler(CommandHandler("players", daftar_pemain))
    
    # Message handlers
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.private, handle_deskripsi))
    
    # Callback handlers
    dp.add_handler(CallbackQueryHandler(handle_vote, pattern=r"^vote_\d+$"))
    
    # Error handler
    dp.add_error_handler(error_handler)

    # Mulai bot
    updater.start_polling()
    updater.idle()

@app.route('/')
def home():
    return "Bot Tebak Spy sedang aktif!"

if __name__ == '__main__':
    # Jalankan bot Telegram di thread terpisah
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Jalankan Flask
    app.run(host='0.0.0.0', port=8000)
