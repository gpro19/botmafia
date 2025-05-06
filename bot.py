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
from typing import Dict, Any
import base64

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
TOKEN = "7590020235:AAGRKmt_neQTk1bvM78ugivuH0qvivlh_3s"
# Game configuration
KATA = {
    "Restoran": ["Menu", "Pelayan", "Meja", "Piring", "Koki"],
    "Mall": ["Toko", "Promosi", "Escalator", "Food Court", "Parkir"],
    "Pasar": ["Pedagang", "Sayur", "Tawar", "Kerumunan", "Kios"],
    "Bandara": ["Check-in", "Bagasi", "Pramugari", "Boarding Pass", "Keamanan"]
}

# Game state management
games: Dict[int, Dict[str, Any]] = {}

def encode_chat_id(chat_id: int) -> str:
    """Encode chat_id to base64 without padding"""
    return base64.b64encode(f"{chat_id}".encode()).decode().rstrip("=")

def decode_chat_id(encoded: str) -> int:
    """Decode base64 string to chat_id"""
    padding = len(encoded) % 4
    if padding:
        encoded += "=" * (4 - padding)
    decoded = base64.b64decode(encoded.encode()).decode()
    return int(decoded)

def get_game(chat_id: int) -> Dict[str, Any]:
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
            'join_started': False,
            'pending_messages': [],
            'join_message_id': None,
            'jobs': []
        }
    return games[chat_id]

def reset_game(chat_id: int):
    """Reset game state and cancel all jobs"""
    game = get_game(chat_id)
    for job in game.get('jobs', []):
        job.schedule_removal()
    if chat_id in games:
        del games[chat_id]

def safe_send_message(context: CallbackContext, chat_id: int, text: str, **kwargs):
    """Send message with error handling"""
    try:
        return context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return None

def join_time_up(context: CallbackContext):
    """Handler ketika waktu gabung habis"""
    chat_id = context.job.context['chat_id']
    game = get_game(chat_id)
    
    if not game['join_started']:
        return

    # Cleanup messages
    for msg_id in game['pending_messages']:
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Gagal hapus pesan {msg_id}: {e}")

    game['pending_messages'] = []
    game['join_message_id'] = None
    game['join_started'] = False

    # Start game if enough players
    if len(game['pemain']) >= 3:
        context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Pendaftaran ditutup dengan {len(game['pemain'])} pemain!\n"
                 "⏳ Memulai permainan...",
            parse_mode='Markdown'
        )
        
        # Start game with short delay
        start_job = context.job_queue.run_once(
            lambda ctx: auto_start_game(ctx),
            2,
            context={'chat_id': chat_id},
            name=f"game_start_{chat_id}"
        )
        game['jobs'].append(start_job)
    else:
        context.bot.send_message(
            chat_id=chat_id,
            text="❌ Pendaftaran ditutup! Minimal 3 pemain diperlukan.",
            parse_mode='Markdown'
        )
        reset_game(chat_id)

def join_warning(context: CallbackContext):
    """Peringatan waktu gabung hampir habis"""
    chat_id = context.job.context['chat_id']
    game = get_game(chat_id)
    
    if not game['join_started']:
        return

    try:
        warning_msg = context.bot.send_message(
            chat_id=chat_id,
            text="⏰ *15 DETIK LAGI UNTUK BERGABUNG!* ⏰",
            parse_mode='Markdown'
        )
        game['pending_messages'].append(warning_msg.message_id)
    except Exception as e:
        logger.error(f"Gagal kirim peringatan: {e}")

def auto_start_game(context: CallbackContext):
    """Automatically start game after join timer ends"""
    try:
        # Extract chat_id from job context
        chat_id = context.job.context['chat_id']
        game = get_game(chat_id)
        
        if len(game['pemain']) < 3:
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Gagal memulai - minimal 3 pemain diperlukan!",
                parse_mode='Markdown'
            )
            reset_game(chat_id)
            return

        # Create simulated Update object (fake_update)
        class MockChat:
            def __init__(self, chat_id):
                self.id = chat_id
                self.type = 'group'

        class MockMessage:
            def __init__(self, chat_id):
                self.chat = MockChat(chat_id)
                self.chat_id = chat_id
                
            def reply_text(self, text, **kwargs):
                return context.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    **kwargs
                )

        fake_update = Update(
            update_id=0,
            message=MockMessage(chat_id)
        )

        # Call main game function with simulated update
        mulai_permainan(fake_update, context)

    except Exception as e:
        logger.error(f"Error in auto_start_game: {e}")
        context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Gagal memulai permainan secara otomatis. Silakan coba /mulai manual."
        )
        reset_game(chat_id)

def start(update: Update, context: CallbackContext):
    if context.args and context.args[0].startswith('join_'):
        join_request(update, context)
        return
        
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

    if not game['join_started']:
        game.update({
            'pemain': [],
            'pending_messages': [],
            'join_started': True,
            'jobs': []
        })

    # Generate join token with encoded chat_id
    encoded_chat_id = encode_chat_id(chat_id)
    join_token = f"join_{int(time.time())}_{encoded_chat_id}"
    
    keyboard = [[InlineKeyboardButton(
        "🎮 Gabung Permainan", 
        url=f"https://t.me/{context.bot.username}?start={join_token}"
    )]]
    
    if not game.get('join_message_id'):
        msg = update.message.reply_text(
            f"🎮 *PERMAINAN BARU DI GRUP INI!*\n"
            "⏱️ Waktu bergabung: 50 detik\n"
            "👥 Pemain: 0/8\n\n"
            "Klik tombol di bawah untuk bergabung:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        game['join_message_id'] = msg.message_id
        game['pending_messages'].append(msg.message_id)
    else:
        try:
            context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game['join_message_id'],
                text=f"🎮 *PERMAINAN BARU DI GRUP INI!*\n"
                     "⏱️ Waktu bergabung: 50 detik\n"
                     f"👥 Pemain: {len(game['pemain'])}/8\n\n"
                     "Klik tombol di bawah untuk bergabung:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Gagal update pesan gabung: {e}")

    # Cancel existing timers
    for job in game.get('jobs', []):
        job.schedule_removal()
    game['jobs'] = []

    # Schedule new timers
    timer_job = context.job_queue.run_once(
        join_time_up,
        50,
        context={'chat_id': chat_id},
        name=f"join_timer_{chat_id}"
    )
    game['jobs'].append(timer_job)

    warning_job = context.job_queue.run_once(
        join_warning,
        35,
        context={'chat_id': chat_id},
        name=f"join_warning_{chat_id}"
    )
    game['jobs'].append(warning_job)

     # Schedule auto start game
    start_job = context.job_queue.run_once(
        auto_start_game,
        52,  # 2 detik setelah timer gabung selesai
        context={'chat_id': chat_id},
        name=f"game_start_{chat_id}"
    )
    game['jobs'].append(start_job)

def join_request(update: Update, context: CallbackContext):
    if update.effective_chat.type != 'private':
        update.message.reply_text("⚠️ Silakan klik tombol dari grup tempat permainan berlangsung!")
        return

    try:
        token = context.args[0]
        parts = token.split('_')
        
        if len(parts) != 3 or parts[0] != "join":
            raise ValueError
            
        # Decode chat_id from base64
        encoded_chat_id = parts[2]
        chat_id = decode_chat_id(encoded_chat_id)

        # Validate token time (10 minute window)
        if abs(time.time() - int(parts[1])) > 600:
            update.message.reply_text("⌛ Link bergabung sudah kadaluarsa!")
            return

    except Exception as e:
        logger.error(f"Invalid join token: {e}")
        update.message.reply_text("❌ Link bergabung tidak valid!")
        return

    game = get_game(chat_id)
    
    if not game.get('join_started', False):
        update.message.reply_text("⌛ Waktu bergabung sudah habis!")
        return

    if game['sedang_berlangsung']:
        update.message.reply_text("⚠️ Permainan sudah berjalan!")
        return

    user = update.effective_user
    user_id = user.id
    username = user.first_name

    if any(p['id'] == user_id for p in game['pemain']):
        update.message.reply_text("😊 Kamu sudah terdaftar!")
        return

    if len(game['pemain']) >= 8:
        update.message.reply_text("🫣 Pemain sudah penuh (8/8)!")
        return

    game['pemain'].append({'id': user_id, 'nama': username})

    update.message.reply_text(
        f"✅ KAMU TELAH BERGABUNG!\n"
        f"Sekarang ada {len(game['pemain'])}/8 pemain.\n"
        "Kembali ke grup untuk menunggu permainan dimulai."
    )

    try:
        notify_msg = context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 [{username}](tg://user?id={user_id}) bergabung! ({len(game['pemain'])}/8)",
            parse_mode='Markdown'
        )
        game['pending_messages'].append(notify_msg.message_id)
    except Exception as e:
        logger.error(f"Gagal kirim notifikasi grup: {e}")

    try:
        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game['join_message_id'],
            text=f"🎮 *PERMAINAN BARU DI GRUP INI!*\n"
                 "⏱️ Waktu bergabung: 50 detik\n"
                 f"👥 Pemain: {len(game['pemain'])}/8\n\n"
                 "Klik tombol di bawah untuk bergabung:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🎮 Gabung Sekarang",
                    url=f"https://t.me/{context.bot.username}?start=join_{int(time.time())}_{encode_chat_id(chat_id)}"
                )
            ]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Gagal update pesan gabung: {e}")

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
        context={'chat_id': chat_id},  # Menggunakan dict untuk context
        name=f"deskripsi_{chat_id}"
    )

def akhir_deskripsi(context: CallbackContext):
    """Handler untuk akhir fase deskripsi"""
    try:
        chat_id = context.job.context['chat_id']
        game = get_game(chat_id)
        
        if not game['sedang_berlangsung'] or game['fase'] != 'deskripsi':
            return

        # Check for missing descriptions
        belum_kirim = []
        for pemain in game['pemain']:
            if (pemain['id'] not in game['deskripsi_pemain'] and 
                pemain not in game['tereliminasi']):
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
            safe_send_message(
                context,
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
            safe_send_message(
                context,
                chat_id=chat_id,
                text="📜 *Hasil Deskripsi:*\n" + "\n".join(hasil_deskripsi),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Gagal kirim hasil deskripsi: {e}")

        # Start voting phase
        game['fase'] = 'voting'
        pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
        
        if len(pemain_aktif) < 2:
            cek_pemenang(context, chat_id)
            return
        
        # Create voting buttons
        keyboard = []
        for p in pemain_aktif:
            btn_text = f"{p['nama']} (0)"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"vote_{p['id']}")])

        safe_send_message(
            context,
            chat_id=chat_id,
            text="🗳️ *Fase Voting!*\nPilih siapa yang menurutmu Spy!\nWaktu: 40 detik.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

        # Voting timer
        context.job_queue.run_once(
            lambda ctx: akhir_voting(ctx),
            40,
            context={'chat_id': chat_id},
            name=f"voting_{chat_id}"
        )

    except Exception as e:
        logger.error(f"Error in akhir_deskripsi: {e}")
        if 'chat_id' in locals():
            safe_send_message(
                context,
                chat_id=chat_id,
                text="⚠️ Terjadi kesalahan saat memproses deskripsi!"
            )

def handle_vote(update: Update, context: CallbackContext):
    try:
        query = update.callback_query
        query.answer()  # Jawab callback terlebih dahulu

        voter_id = query.from_user.id
        chat_id = query.message.chat.id
        game = get_game(chat_id)

        # Validasi status game
        if not game.get('sedang_berlangsung') or game.get('fase') != 'voting':
            query.answer(text="❌ Waktu voting sudah habis!", show_alert=False)
            return

        # Cek jika voter sudah tereliminasi
        if any(voter_id == p['id'] for p in game.get('tereliminasi', [])):
            query.answer(text="❌ Kamu sudah tereliminasi!", show_alert=False)
            return

        # Cek jika sudah vote
        if voter_id in game.get('suara', {}):
            current_choice = game['suara'][voter_id].get('nama', 'unknown')
            query.answer(text=f"⚠️ Kamu sudah memilih {current_choice}!", show_alert=False)
            return

        # Parse callback data
        try:
            _, player_id_str = query.data.split('_')
            player_id = int(player_id_str)
        except Exception as e:
            logger.error(f"Invalid callback data: {query.data}")
            query.answer(text="❌ Data vote tidak valid!", show_alert=False)
            return

        # Cari pemain yang dipilih
        terpilih = next(
            (p for p in game.get('pemain', []) 
             if p.get('id') == player_id and p not in game.get('tereliminasi', [])), 
            None
        )
        
        if not terpilih:
            query.answer(text="❌ Pemain tidak valid!", show_alert=False)
            return

        # Catat vote
        game.setdefault('suara', {})[voter_id] = terpilih
        
        # Hitung suara
        vote_count = {p['id']: 0 for p in game['pemain'] if p not in game['tereliminasi']}
        for v in game.get('suara', {}).values():
            if v and 'id' in v:
                vote_count[v['id']] += 1

        # Bangun keyboard baru
        keyboard = []
        for p in game['pemain']:
            if p not in game['tereliminasi']:
                count = vote_count.get(p['id'], 0)
                btn_text = f"{p['nama']} ({count})"
                callback = f"vote_{p['id']}"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback)])

        # Edit inline keyboard
        try:
            query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            query.answer(text=f"✅ Kamu memilih {terpilih['nama']}!")
        except Exception as e:
            logger.error(f"Gagal update reply markup: {e}")
            query.answer(text="❌ Gagal memperbarui pilihan.")

    except Exception as e:
        logger.error(f"Error in handle_vote: {e}")
        try:
            query.answer(text="❌ Terjadi kesalahan saat voting!")
        except:
            pass

def akhir_voting(context: CallbackContext):
    """Handler untuk akhir fase voting"""
    try:
        chat_id = context.job.context['chat_id']
        game = get_game(chat_id)
        
        if not game.get('sedang_berlangsung') or game.get('fase') != 'voting':
            return

        # Hitung hasil voting
        hasil_voting = {p['id']: {'nama': p['nama'], 'suara': 0} 
                       for p in game['pemain'] if p not in game['tereliminasi']}
        
        for v in game.get('suara', {}).values():
            if v and 'id' in v and v['id'] in hasil_voting:
                hasil_voting[v['id']]['suara'] += 1

        ranking = sorted(hasil_voting.values(), key=lambda x: x['suara'], reverse=True)

        # Tampilkan hasil
        hasil_text = "📊 *Hasil Voting:*\n"
        for p in ranking:
            hasil_text += f"• {p['nama']}: {p['suara']} suara\n"
        
        safe_send_message(
            context,
            chat_id=chat_id,
            text=hasil_text,
            parse_mode='Markdown'
        )

        # Tentukan yang tereliminasi
        if ranking and ranking[0]['suara'] > 0:
            if len(ranking) > 1 and ranking[0]['suara'] == ranking[1]['suara']:
                # Handle seri
                nama_seri = ", ".join([p['nama'] for p in ranking if p['suara'] == ranking[0]['suara']])
                safe_send_message(
                    context,
                    chat_id=chat_id,
                    text=f"🤝 *Hasil seri!* ({nama_seri})\nTidak ada yang tereliminasi.",
                    parse_mode='Markdown'
                )
            else:
                # Eliminasi pemain dengan suara terbanyak
                tereliminasi = next(
                    (p for p in game['pemain'] 
                     if p['id'] == ranking[0]['id'] and p not in game['tereliminasi']),
                    None
                )
                if tereliminasi:
                    game['tereliminasi'].append(tereliminasi)
                    is_spy = tereliminasi in game['spy']
                    if is_spy:
                        game['spy'].remove(tereliminasi)
                    
                    safe_send_message(
                        context,
                        chat_id=chat_id,
                        text=f"☠️ *{tereliminasi['nama']} tereliminasi!* "
                             f"{'(Dia adalah Spy!)' if is_spy else ''}",
                        parse_mode='Markdown'
                    )

        # Cek pemenang
        cek_pemenang(context, chat_id)

    except Exception as e:
        logger.error(f"Error in akhir_voting: {e}")
        if 'chat_id' in locals():
            safe_send_message(
                context,
                chat_id=chat_id,
                text="⚠️ Terjadi kesalahan dalam pemrosesan voting!"
            )

def cek_pemenang(context: CallbackContext, chat_id: int):
    """Cek kondisi kemenangan"""
    try:
        game = get_game(chat_id)
        
        # Hitung pemain aktif dan spy
        pemain_aktif = [p for p in game['pemain'] if p not in game['tereliminasi']]
        jumlah_pemain = len(pemain_aktif)
        jumlah_spy = len(game['spy'])

        if jumlah_pemain == 0:
            # Kasus semua tereliminasi
            teks = "🤷 *Permainan berakhir tanpa pemenang!*\nSemua pemain tereliminasi."
        elif jumlah_spy >= (jumlah_pemain - jumlah_spy):
            # Spy menang
            teks = f"🎭 *SPY MENANG!* 🎭\n\n"
            teks += f"🔎 Spy yang tersisa: " + ", ".join([s['nama'] for s in game['spy']]) + "\n"
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
        elif jumlah_spy == 0:
            # Warga menang
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
        else:
            # Lanjut ke ronde berikutnya
            game['fase'] = 'deskripsi'
            game['deskripsi_pemain'] = {}
            game['suara'] = {}
            
            safe_send_message(
                context,
                chat_id=chat_id,
                text="🔄 *Memulai Ronde Baru!*\n"
                     "Deskripsikan kata kalian lagi (35 detik).",
                parse_mode='Markdown'
            )
            
            # Timer deskripsi baru
            context.job_queue.run_once(
                lambda ctx: akhir_deskripsi(ctx),
                35,
                context={'chat_id': chat_id},
                name=f"deskripsi_{chat_id}"
            )
            return

        # Jika game berakhir
        safe_send_message(
            context,
            chat_id=chat_id,
            text=teks,
            parse_mode='Markdown'
        )
        reset_game(chat_id)

    except Exception as e:
        logger.error(f"Error in cek_pemenang: {e}")
        safe_send_message(
            context,
            chat_id=chat_id,
            text="⚠️ Terjadi kesalahan saat menentukan pemenang!"
        )
        reset_game(chat_id)

def handle_deskripsi(update: Update, context: CallbackContext):
    """Handler untuk menerima deskripsi dari pemain"""
    if update.effective_chat.type != 'private':
        return

    user_id = update.effective_user.id
    deskripsi = update.message.text
    
    # Cari game aktif yang mengandung pemain ini
    for chat_id in games:
        game = games[chat_id]
        if (game['sedang_berlangsung'] and 
            game['fase'] == 'deskripsi' and
            any(p['id'] == user_id for p in game['pemain'])):
            
            game['deskripsi_pemain'][user_id] = deskripei
            update.message.reply_text("✅ Deskripsi kamu sudah tercatat!")
            return
    
    update.message.reply_text("ℹ️ Tidak ada permainan yang membutuhkan deskripsi darimu.")

def cancel_game(update: Update, context: CallbackContext):
    """Handler untuk membatalkan game"""
    if update.effective_chat.type == 'private':
        update.message.reply_text("❌ Hanya bisa dilakukan di grup!")
        return

    chat_id = update.effective_chat.id
    game = get_game(chat_id)
    
    if not game['sedang_berlangsung']:
        update.message.reply_text("❌ Tidak ada permainan yang berjalan!")
        return

    # Hapus semua job terkait
    current_jobs = context.job_queue.get_jobs_by_name(f"deskripsi_{chat_id}")
    current_jobs += context.job_queue.get_jobs_by_name(f"voting_{chat_id}")
    
    for job in current_jobs:
        job.schedule_removal()
    
    reset_game(chat_id)
    update.message.reply_text("🔴 Permainan dibatalkan!")

def daftar_pemain(update: Update, context: CallbackContext):
    """Handler untuk menampilkan daftar pemain"""
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
    """Handler untuk error umum"""
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    
    if update and update.effective_message:
        update.effective_message.reply_text(
            "❌ Error terjadi. Silakan coba lagi atau mulai permainan baru."
        )
        if 'chat_id' in context.chat_data:
            reset_game(context.chat_data['chat_id'])

# Run bot
def run_bot():
    """Fungsi utama untuk menjalankan bot"""
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
    """Endpoint untuk health check"""
    return "Bot Tebak Spy sedang aktif!"

if __name__ == '__main__':
    # Jalankan bot Telegram di thread terpisah
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Jalankan Flask
    app.run(host='0.0.0.0', port=8000)
