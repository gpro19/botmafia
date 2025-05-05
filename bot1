from flask import Flask
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext,
    MessageHandler, Filters
)
import threading
import logging
from telegram.error import NetworkError
import time

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
TOKEN = "6864590652:AAGSggybrVFaeVxf350uN6ISbXNrFGaceN0"  # Replace token cokwith your actual token

# Game configuration
KATA = {
    "Restoran": ["Menu", "Pelayan", "Meja", "Piring", "Koki"],
    "Mall": ["Toko", "Promosi", "Escalator", "Food Court", "Parkir"],
    "Pasar": ["Pedagang", "Sayur", "Tawar", "Kerumunan", "Kios"],
    "Bandara": ["Check-in", "Bagasi", "Pramugari", "Boarding Pass", "Keamanan"]
}

# Game state management
games = {}

def safe_answer_callback(query, text=None, show_alert=False):
    """Safely answer callback query with retry logic"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return query.answer(text=text, show_alert=show_alert)
        except NetworkError as e:
            if attempt == max_retries - 1:
                raise
            # Exponential backoff with jitter
            sleep_time = (2 ** attempt) + random.random()
            time.sleep(sleep_time)

def safe_send_message(context, *args, **kwargs):
    """Safely send message with retry logic"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return context.bot.send_message(*args, **kwargs)
        except NetworkError as e:
            if attempt == max_retries - 1:
                raise
            sleep_time = (2 ** attempt) + random.random()
            time.sleep(sleep_time)



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
            'message_id': None
        }
    return games[chat_id]

def reset_game(chat_id):
    if chat_id in games:
        del games[chat_id]

# Command handlers
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
    if update.effective_chat.type == 'private':
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
    if update.effective_chat.type == 'private':
        update.message.reply_text("❌ Hanya bisa dilakukan di grup!")
        return

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
    
    # Reset game state
    game.update({
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

    # Determine number of spies
    num_spies = 1 if jumlah_pemain <= 4 else 2
    
    # Select spies randomly
    all_players = game['pemain'].copy()
    random.shuffle(all_players)
    game['spy'] = all_players[:num_spies]
    game['warga'] = all_players[num_spies:]

    # Select secret word
    kategori = random.choice(list(KATA.keys()))
    kata_warga = random.choice(KATA[kategori])
    kata_spy = random.choice(KATA[kategori])
    
    # Ensure spy and warga words are different
    while kata_spy == kata_warga:
        kata_spy = random.choice(KATA[kategori])
    
    game['kata_rahasia'] = {
        'warga': kata_warga,
        'spy': kata_spy,
        'kategori': kategori
    }

    # Send roles to players privately
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
            
            context.bot.send_message(
                chat_id=pemain['id'],
                text=role_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Gagal kirim pesan ke {pemain['nama']}: {e}")
            update.message.reply_text(
                f"❌ Tidak bisa mengirim pesan ke {pemain['nama']}. "
                "Pastikan sudah memulai chat dengan bot!"
            )
            reset_game(chat_id)
            return

    # Info to group
    msg = update.message.reply_text(
        "🎭 *Peran sudah dibagikan!*\n"
        f"Spy: {len(game['spy'])} orang | Warga: {len(game['warga'])} orang\n\n"
        "⏳ *Fase Deskripsi dimulai!*\n"
        "Kirim deskripsi kata Anda via chat privat ke bot ini (waktu 35 detik).",
        parse_mode='Markdown'
    )

    game['fase'] = 'deskripsi'
    game['message_id'] = msg.message_id
    
    # Description phase timer
    context.job_queue.run_once(
        lambda ctx: akhir_deskripsi(ctx, chat_id),
        35,
        context=chat_id,
        name=f"deskripsi_{chat_id}"
    )

def akhir_deskripsi(context: CallbackContext, chat_id):
    game = get_game(chat_id)
    
    if not game['sedang_berlangsung'] or game['fase'] != 'deskripsi':
        return

    # Check for missing descriptions
    belum_kirim = []
    for pemain in game['pemain']:
        if pemain['id'] not in game['deskripsi_pemain'] and pemain not in game['tereliminasi']:
            belum_kirim.append(pemain['nama'])
            game['deskripsi_pemain'][pemain['id']] = "❌ [Tidak memberikan deskripsi]"
            
            try:
                context.bot.send_message(
                    chat_id=pemain['id'],
                    text="⚠️ Kamu tidak mengirim deskripsi waktu fase deskripsi!\n"
                         "Kata kamu tetap akan diperlihatkan di grup dengan pesan default."
                )
            except Exception as e:
                logger.error(f"Gagal mengirim notifikasi ke {pemain['nama']}: {e}")

    if belum_kirim:
        context.bot.send_message(
            chat_id=chat_id,
            text="❌ Pemain berikut tidak mengirim deskripsi: " + ", ".join(belum_kirim)
        )

    # Compile descriptions
    hasil_deskripsi = []
    for pemain in game['pemain']:
        if pemain['id'] in game['deskripsi_pemain']:
            hasil_deskripsi.append(
                f"▪️ {pemain['nama']}: {game['deskripsi_pemain'][pemain['id']]}"
            )

    # Show descriptions to group
    try:
        if game['message_id']:
            #context.bot.edit_message_text(
                #chat_id=chat_id,
                #message_id=game['message_id'],
                #text="📜 *Hasil Deskripsi:*\n" + "\n".join(hasil_deskripsi),
                #parse_mode='Markdown'
            #)
            game['message_id'] = context.bot.send_message(
                chat_id=chat_id,
                text="📜 *Hasil Deskripsi:*\n" + "\n".join(hasil_deskripsi),
                parse_mode='Markdown'
            ).message_id
        else:
            game['message_id'] = context.bot.send_message(
                chat_id=chat_id,
                text="📜 *Hasil Deskripsi:*\n" + "\n".join(hasil_deskripsi),
                parse_mode='Markdown'
            ).message_id
    except Exception as e:
        logger.error(f"Gagal edit/send pesan deskripsi: {e}")
        game['message_id'] = None

    # Start voting phase
    game['fase'] = 'voting'
    pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
    
    if len(pemain_aktif) < 2:
        cek_pemenang(context, chat_id)
        return

    # Create vertical voting buttons
    keyboard = []
    for p in pemain_aktif:
        keyboard.append([InlineKeyboardButton(p['nama'], callback_data=f"vote_{p['id']}")])

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

    # Voting timer
    context.job_queue.run_once(
        lambda ctx: akhir_voting(ctx, chat_id),
        20,
        context=chat_id,
        name=f"voting_{chat_id}"
    )

def handle_vote(update: Update, context: CallbackContext):
    query = update.callback_query
    try:
        safe_answer_callback(query)  # First acknowledge the callback
        
        voter_id = query.from_user.id
        chat_id = query.message.chat.id
        game = get_game(chat_id)

        if not game.get('sedang_berlangsung') or game.get('fase') != 'voting':
            query.edit_message_text("❌ Waktu voting sudah habis!")
            return

        # Check if voter is eliminated
        if any(voter_id == p['id'] for p in game.get('tereliminasi', [])):
            safe_answer_callback(query, "❌ Kamu sudah tereliminasi!", show_alert=True)
            return

        # Check if already voted
        if voter_id in game.get('suara', {}):
            current_choice = game['suara'][voter_id].get('nama', 'unknown')
            safe_answer_callback(query, f"⚠️ Kamu sudah memilih {current_choice}!", show_alert=True)
            return

        # Parse callback data safely
        try:
            _, player_id_str = query.data.split('_')
            player_id = int(player_id_str)
        except (ValueError, AttributeError) as e:
            logger.error(f"Invalid callback data: {query.data}")
            safe_answer_callback(query, "❌ Invalid vote data!", show_alert=True)
            return

        # Find selected player safely
        terpilih = next((p for p in game.get('pemain', []) 
                        if p.get('id') == player_id and p not in game.get('tereliminasi', [])), None)
        
        if not terpilih:
            safe_answer_callback(query, "❌ Pemain tidak valid!", show_alert=True)
            return

        # Record vote
        game.setdefault('suara', {})[voter_id] = terpilih
        
        # Count votes with proper initialization
        vote_count = {p['id']: 0 for p in game.get('pemain', []) if p not in game.get('tereliminasi', [])}
        for v in game.get('suara', {}).values():
            if v and 'id' in v:
                vote_count[v['id']] = vote_count.get(v['id'], 0) + 1

        # Rebuild keyboard safely
        keyboard = []
        for p in game.get('pemain', []):
            if p not in game.get('tereliminasi', []):
                count = vote_count.get(p.get('id', 0), 0)
                is_voter_choice = voter_id in game.get('suara', {}) and game['suara'][voter_id].get('id') == p.get('id')
                text = f"{p.get('nama', 'Unknown')} {'✅' if is_voter_choice else ''} {count if count > 0 else ''}".strip()
                
                # Only include callback if not voted yet
                callback = f"vote_{p['id']}" if voter_id not in game.get('suara', {}) else None
                keyboard.append([InlineKeyboardButton(text, callback_data=callback)])

        # Update voting message safely
        try:
            query.edit_message_text(
                text="🗳️ *Fase Voting!*\nPilih siapa yang menurutmu Spy!\n✓ = pilihanmu | angka = jumlah vote",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            safe_answer_callback(query, f"✅ Kamu memilih {terpilih.get('nama', 'unknown')}!", show_alert=True)
        except Exception as e:
            logger.error(f"Error updating vote message: {e}")
            safe_answer_callback(query, "❌ Gagal memperbarui pilihan.", show_alert=True)

    except Exception as e:
        logger.error(f"Error in handle_vote: {e}")
        try:
            safe_answer_callback(query, "❌ Terjadi kesalahan saat voting!", show_alert=True)
        except:
            pass


def akhir_voting(context: CallbackContext, chat_id):
    try:
        game = get_game(chat_id)
        
        if not game.get('sedang_berlangsung') or game.get('fase') != 'voting':
            return

        # Initialize proper voting structure
        hasil_voting = {p.get('id'): {'nama': p.get('nama', 'Unknown'), 'suara': 0, 'id': p.get('id')} 
                       for p in game.get('pemain', []) if p not in game.get('tereliminasi', [])}
        
        # Count votes safely
        for v in game.get('suara', {}).values():
            if v and 'id' in v and v['id'] in hasil_voting:
                hasil_voting[v['id']]['suara'] += 1

        # Create sorted ranking safely
        ranking = sorted(hasil_voting.values(), key=lambda x: x.get('suara', 0), reverse=True)

        # Show voting results with proper error handling
        hasil_text = "📊 *Hasil Voting:*\n"
        for p in ranking:
            hasil_text += f"• {p.get('nama', 'Unknown')}: {p.get('suara', 0)} suara\n"
        
        # Send results safely
        try:
            if game.get('message_id'):
                context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=game['message_id'],
                    text=hasil_text,
                    parse_mode='Markdown'
                )
            else:
                game['message_id'] = safe_send_message(
                    context,
                    chat_id=chat_id,
                    text=hasil_text,
                    parse_mode='Markdown'
                ).message_id
        except Exception as e:
            logger.error(f"Error sending voting results: {e}")

        # Determine eliminated player safely
        tereliminasi = None
        try:
            if ranking and len(ranking) > 0:
                if len(ranking) > 1 and ranking[0].get('suara', 0) == ranking[1].get('suara', 0):
                    # Handle tie
                    nama_seri = ", ".join([p.get('nama', 'Unknown') for p in ranking 
                                         if p.get('suara', 0) == ranking[0].get('suara', 0)])
                    safe_send_message(
                        context,
                        chat_id=chat_id,
                        text=f"🤝 *Hasil seri!* ({nama_seri})\nTidak ada yang tereliminasi.",
                        parse_mode='Markdown'
                    )
                else:
                    # Single elimination
                    tereliminasi = next((p for p in game.get('pemain', []) 
                                       if p.get('id') == ranking[0].get('id') and 
                                       p not in game.get('tereliminasi', [])), None)
                    if tereliminasi:
                        game.setdefault('tereliminasi', []).append(tereliminasi)
                        is_spy = tereliminasi in game.get('spy', [])
                        if is_spy:
                            game['spy'].remove(tereliminasi)
                        
                        safe_send_message(
                            context,
                            chat_id=chat_id,
                            text=f"☠️ *{tereliminasi.get('nama', 'Pemain')} tereliminasi!* "
                                f"{'(Dia adalah Spy!)' if is_spy else ''}",
                            parse_mode='Markdown'
                        )
        except Exception as e:
            logger.error(f"Error determining elimination: {e}")
            safe_send_message(
                context,
                chat_id=chat_id,
                text="❌ Terjadi kesalahan saat menentukan eliminasi.",
                parse_mode='Markdown'
            )

        # Check win conditions
        cek_pemenang(context, chat_id)

    except Exception as e:
        logger.error(f"Error in akhir_voting: {e}")
        try:
            safe_send_message(
                context,
                chat_id=chat_id,
                text="⚠️ Terjadi kesalahan dalam pemrosesan voting.",
                parse_mode='Markdown'
            )
        except:
            pass


def cek_pemenang(context: CallbackContext, chat_id):
    game = get_game(chat_id)
    
    # Count remaining players and spies
    pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
    jumlah_pemain = len(pemain_aktif)
    jumlah_spy = len(game['spy'])

    if jumlah_pemain == 0:
        # Special case if all eliminated
        teks = "🤷 *Permainan berakhir tanpa pemenang!*\nSemua pemain tereliminasi."
    elif jumlah_spy >= (jumlah_pemain - jumlah_spy):  # Spies win
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
    elif jumlah_spy == 0:  # Villagers win
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
    else:  # Continue to next round
        game['fase'] = 'deskripsi'
        game['deskripsi_pemain'] = {}
        game['suara'] = {}
        
        context.bot.send_message(
            chat_id=chat_id,
            text="🔄 *Memulai Ronde Baru!*\n"
                 "Deskripsikan kata kalian lagi (35 detik).",
            parse_mode='Markdown'
        )
        
        # New description phase timer
        context.job_queue.run_once(
            lambda ctx: akhir_deskripsi(ctx, chat_id),
            35,
            context=chat_id,
            name=f"deskripsi_{chat_id}"
        )
        return

    # If game ended
    context.bot.send_message(
        chat_id=chat_id,
        text=teks,
        parse_mode='Markdown'
    )
    reset_game(chat_id)

def handle_deskripsi(update: Update, context: CallbackContext):
    if update.effective_chat.type != 'private':
        return

    player_id = update.effective_user.id
    deskripsi = update.message.text
    
    # Find active game with this player
    for chat_id in games:
        game = games[chat_id]
        if game['sedang_berlangsung'] and game['fase'] == 'deskripsi':
            if any(p['id'] == player_id for p in game['pemain'] if p not in game['tereliminasi']):
                game['deskripsi_pemain'][player_id] = deskripsi
                update.message.reply_text("✅ Deskripsi kamu sudah tercatat!")
                return
    
    update.message.reply_text("ℹ️ Tidak ada permainan yang membutuhkan deskripsi darimu.")

def cancel_game(update: Update, context: CallbackContext):
    if update.effective_chat.type == 'private':
        update.message.reply_text("❌ Hanya bisa dilakukan di grup!")
        return

    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    
    if not game['sedang_berlangsung']:
        update.message.reply_text("❌ Tidak ada permainan yang berjalan!")
        return

    # Remove all related jobs
    current_jobs = context.job_queue.get_jobs_by_name(f"deskripsi_{chat_id}")
    current_jobs += context.job_queue.get_jobs_by_name(f"voting_{chat_id}")
    
    for job in current_jobs:
        job.schedule_removal()
    
    reset_game(chat_id)
    update.message.reply_text("🔴 Permainan dibatalkan!")

def daftar_pemain(update: Update, context: CallbackContext):
    if update.effective_chat.type == 'private':
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

# Run bot
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

    # Start bot
    updater.start_polling()
    updater.idle()

@app.route('/')
def home():
    return "Bot Tebak Spy sedang aktif!"

if __name__ == '__main__':
    # Run Telegram bot in separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Run Flask
    app.run(host='0.0.0.0', port=8000)
