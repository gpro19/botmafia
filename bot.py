import random
import threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext

app = Flask(__name__)

# ===== GLOBAL STATE =====
game_data = {
    'game_state': False,
    'registration_state': False,
    'players': {},
    'quantity': 0,
    'used_ids': [],
    'roles': {},
    'koruptor_list': [],
    'current_phase': None,  # 'day' or 'night'
    'current_day': 1,
    'vote_results': {},
    'night_actions': {},
    'reg_message_id': None,
    'game_chat_id': None
}

# ===== CONSTANTS =====
BOT_TOKEN = "6864590652:AAHhkS03TwV-IvUET4iDnZf0Qh5YJLRMW-k"  # Ganti dengan token bot Anda
REQUIRED_PLAYERS = 5
LEADERS_KPK = ['jaksa', 'penyidik']
SPECIAL_KPK = ['whistleblower', 'analis']
SPECIAL_KORUPTOR = ['bosmafia']
OTHERS = ['wastafel']
ROLES_PRIORITY = ['wastafel', 'analis', 'whistleblower', 'koruptor', 'bosmafia', 'jaksa', 'penyidik']

ROLE_DISTRIBUTION = {
    5: '1 1 0 2 0 0',  # Format: leader_kpk kpk special_kpk koruptor special_koruptor others
    6: '1 1 1 2 0 0',
    7: '1 2 1 2 0 0',
    8: '1 2 1 2 1 0',
    9: '1 2 1 3 1 0',
    10: '1 3 1 3 1 0',
    11: '1 3 1 3 1 1',
    12: '1 4 1 3 1 1',
    13: '1 5 1 3 1 1',
    14: '1 5 1 4 1 1',
    15: '1 6 1 4 1 1',
    16: '1 6 1 5 1 1'
}

ROLE_GREETINGS = {
    "Jaksa": "🔍 Anda adalah JAKSA KPK! Tugas menangkap koruptor. Malam bisa menangkap atau memeriksa.",
    "Penyidik": "🕵️ Anda adalah PENYIDIK KPK! Malam bisa memeriksa apakah seseorang koruptor.",
    "Whistleblower": "🎭 Anda WHISTLEBLOWER! Bisa melindungi seseorang dari koruptor.",
    "Analis": "📊 Anda ANALIS KPK! Bisa memblokir kemampuan seseorang.",
    "Bosmafia": "💀 Anda BOS MAFIA! Bisa menyuap pemain untuk membatalkan voting.",
    "Wastafel": "🤷 Anda WASTAFEL! Bisa membunuh. Menang jika last survivor.", 
    "Koruptor": "🕶 Anda KORUPTOR! Bisa membunuh bersama rekan koruptor.",
    "KPK": "🛡 Anda ANGGOTA KPK. Tak ada skill khusus, suaramu penting."
}

# ===== PLAYER CLASS =====
class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name + (f' {user.last_name}' if user.last_name else '')
        self.username = user.username
        self.role = None
        self.is_alive = True
        self.can_vote = True
        self.is_protected = False
        self.is_blocked = False
        self.night_target = None

    def __str__(self):
        return f"[{self.name}](tg://user?id={self.id})"

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    return "Bot KPK vs Koruptor sedang aktif!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string, updater.bot)
        updater.dispatcher.process_update(update)
    return '', 200

# ===== TELEGRAM BOT COMMANDS =====
def start_command(update: Update, context: CallbackContext):
    if game_data['registration_state']:
        register_player(update, context)
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Halo! Untuk mulai game, admin harus menjalankan /game di grup"
        )

def game_command(update: Update, context: CallbackContext):
    if not game_data['game_state'] and not game_data['registration_state']:
        start_registration(update, context)
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Game sudah berjalan atau pendaftaran sedang aktif!"
        )

def begin_game_command(update: Update, context: CallbackContext):
    start_game(update, context)

def stop_command(update: Update, context: CallbackContext):
    if game_data['game_state'] or game_data['registration_state']:
        reset_game()
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Game dihentikan. Semua data telah direset."
        )
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Tidak ada game yang sedang berjalan."
        )

def reset_game():
    global game_data
    game_data = {
        'game_state': False,
        'registration_state': False,
        'players': {},
        'quantity': 0,
        'used_ids': [],
        'roles': {},
        'koruptor_list': [],
        'current_phase': None,
        'current_day': 1,
        'vote_results': {},
        'night_actions': {},
        'reg_message_id': None,
        'game_chat_id': None
    }

# ===== GAME LOGIC =====
def register_player(update: Update, context: CallbackContext):
    user = update.effective_user
    
    if user.id in game_data['used_ids']:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Anda sudah terdaftar!"
        )
        return
    
    game_data['players'][user.id] = Player(user)
    game_data['used_ids'].append(user.id)
    game_data['quantity'] += 1
    
    player_list = "\n".join(f"- {p.name}" for p in game_data['players'].values())
    
    context.bot.edit_message_text(
        chat_id=game_data['game_chat_id'],
        message_id=game_data['reg_message_id'],
        text=f"*🔄 REGISTRASI*\n\n"
             f"Terdaftar ({game_data['quantity']}):\n{player_list}\n\n"
             f"Butuh {max(0, REQUIRED_PLAYERS - game_data['quantity'])} pemain lagi",
        parse_mode='Markdown'
    )

def start_registration(update: Update, context: CallbackContext):
    game_data['registration_state'] = True
    game_data['game_chat_id'] = update.effective_chat.id
    
    msg = context.bot.send_message(
        chat_id=game_data['game_chat_id'],
        text="*🔄 REGISTRASI DIMULAI!*\n\n"
             "Kirim /start ke bot untuk mendaftar\n"
             f"Minimal pemain: {REQUIRED_PLAYERS}\n\n"
             "Terdaftar:\n- (Belum ada)",
        parse_mode='Markdown'
    )
    
    game_data['reg_message_id'] = msg.message_id
    context.bot.pin_chat_message(
        chat_id=game_data['game_chat_id'], 
        message_id=game_data['reg_message_id']
    )

def start_game(update: Update, context: CallbackContext):
    if game_data['quantity'] < REQUIRED_PLAYERS:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Pemain belum cukup! Butuh {REQUIRED_PLAYERS}, sekarang {game_data['quantity']}"
        )
        return
    
    game_data['registration_state'] = False
    game_data['game_state'] = True
    game_data['current_phase'] = 'night'
    
    context.bot.delete_message(
        chat_id=game_data['game_chat_id'], 
        message_id=game_data['reg_message_id']
    )
    
    distribute_roles()
    send_role_messages(context.bot)
    start_night(context.bot)

def distribute_roles():
    role_counts = list(map(int, ROLE_DISTRIBUTION[game_data['quantity']].split()))
    player_ids = list(game_data['players'].keys())
    random.shuffle(player_ids)
    
    game_data['roles'] = {'KPK': [], 'Koruptor': []}
    game_data['koruptor_list'] = []
    
    idx = 0
    
    # Leader KPK
    leaders = random.sample(LEADERS_KPK, role_counts[0])
    for role in leaders:
        role_name = role.capitalize()
        game_data['players'][player_ids[idx]].role = role_name
        game_data['roles'][role_name] = player_ids[idx]
        idx += 1
    
    # Anggota KPK
    for _ in range(role_counts[1]):
        game_data['players'][player_ids[idx]].role = 'KPK'
        game_data['roles']['KPK'].append(player_ids[idx])
        idx += 1
    
    # Special KPK
    specials = random.sample(SPECIAL_KPK, role_counts[2])
    for role in specials:
        role_name = role.capitalize()
        game_data['players'][player_ids[idx]].role = role_name
        game_data['roles'][role_name] = player_ids[idx]
        idx += 1
    
    # Koruptor
    for _ in range(role_counts[3]):
        game_data['players'][player_ids[idx]].role = 'Koruptor'
        game_data['roles']['Koruptor'].append(player_ids[idx])
        game_data['koruptor_list'].append(str(game_data['players'][player_ids[idx]]))
        idx += 1
    
    # Special Koruptor
    if role_counts[4] > 0:
        role_name = random.choice(SPECIAL_KORUPTOR).capitalize()
        game_data['players'][player_ids[idx]].role = role_name
        game_data['roles'][role_name] = player_ids[idx]
        game_data['koruptor_list'].append(str(game_data['players'][player_ids[idx]]))
        idx += 1
    
    # Others
    if role_counts[5] > 0:
        role_name = random.choice(OTHERS).capitalize()
        game_data['players'][player_ids[idx]].role = role_name
        game_data['roles'][role_name] = player_ids[idx]
        idx += 1

def send_role_messages(bot):
    for player_id, player in game_data['players'].items():
        role_msg = f"🎭 *PERAN ANDA:* {player.role}\n\n"
        role_msg += ROLE_GREETINGS.get(player.role, "Role tidak dikenali")
        
        if player.role == 'Koruptor' and len(game_data['roles']['Koruptor']) > 1:
            teammates = [
                str(game_data['players'][pid]) 
                for pid in game_data['roles']['Koruptor'] 
                if pid != player_id
            ]
            role_msg += f"\n\n🔮 Rekan koruptor Anda: {', '.join(teammates)}"
        
        bot.send_message(
            chat_id=player_id,
            text=role_msg,
            parse_mode='Markdown'
        )

# ===== GAME PHASES =====
def start_night(bot):
    game_data['current_phase'] = 'night'
    game_data['night_actions'] = {}
    
    bot.send_message(
        chat_id=game_data['game_chat_id'],
        text=f"🌑 *MALAM HARI #{game_data['current_day']}*\n\n"
             "Semua pemain tidur... Waktunya aksi rahasia!",
        parse_mode='Markdown'
    )
    
    # Reset status
    for player in game_data['players'].values():
        player.is_protected = False
        player.is_blocked = False
    
    # Aktifkan aksi peran sesuai prioritas
    for role in ROLES_PRIORITY:
        if role.capitalize() in game_data['roles']:
            if role == 'koruptor':
                start_koruptor_action(bot)
            elif role == 'jaksa':
                start_jaksa_action(bot)
            elif role == 'penyidik':
                start_penyidik_action(bot)
            elif role == 'whistleblower':
                start_whistleblower_action(bot)
            elif role == 'analis':
                start_analis_action(bot)
            elif role == 'bosmafia':
                start_bosmafia_action(bot)
            elif role == 'wastafel':
                start_wastafel_action(bot)

def start_day(bot):
    game_data['current_phase'] = 'day'
    game_data['vote_results'] = {}
    
    alive_players = [p for p in game_data['players'].values() if p.is_alive]
    
    if not alive_players:
        bot.send_message(
            chat_id=game_data['game_chat_id'],
            text="Semua pemain telah mati! Permainan berakhir."
        )
        reset_game()
        return
    
    keyboard = [[InlineKeyboardButton(p.name, callback_data=f"vote:{p.id}")] for p in alive_players]
    
    bot.send_message(
        chat_id=game_data['game_chat_id'],
        text=f"☀️ *SIANG HARI #{game_data['current_day']}*\n\n"
             f"Pemain yang masih hidup ({len(alive_players)}):\n"
             f"{', '.join(p.name for p in alive_players)}\n\n"
             "Voting untuk menangkap tersangka:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def end_day(context: CallbackContext):
    if not game_data['vote_results']:
        context.bot.send_message(
            chat_id=game_data['game_chat_id'],
            text="Tidak ada voting yang terjadi, malam pun tiba..."
        )
    else:
        # Hitung suara (hanya dari yang bisa vote)
        vote_count = {}
        for voter_id, target_id in game_data['vote_results'].items():
            if game_data['players'][voter_id].can_vote:
                vote_count[target_id] = vote_count.get(target_id, 0) + 1
        
        if vote_count:
            max_votes = max(vote_count.values())
            candidates = [tid for tid, cnt in vote_count.items() if cnt == max_votes]
            
            if len(candidates) == 1:  # Ada pemenang voting
                target_id = candidates[0]
                game_data['players'][target_id].is_alive = False
                context.bot.send_message(
                    chat_id=game_data['game_chat_id'],
                    text=f"⚖️ {game_data['players'][target_id].name} dihukum mati!\n"
                         f"Peran: {game_data['players'][target_id].role}"
                )
            else:  # Voting seri
                names = ', '.join(game_data['players'][tid].name for tid in candidates)
                context.bot.send_message(
                    chat_id=game_data['game_chat_id'],
                    text=f"Hasil voting seri antara: {names}\n"
                         "Tidak ada yang dihukum."
                )
    
    # Reset voting ability
    for player in game_data['players'].values():
        player.can_vote = True
    
    # Lanjut ke malam berikutnya
    game_data['current_day'] += 1
    start_night(context.bot)

# ===== ROLE ACTIONS =====
def start_koruptor_action(bot):
    targets = [
        p.id for p in game_data['players'].values() 
        if p.is_alive and p.role not in ['Koruptor', 'Bosmafia']
    ]
    
    if not targets:
        return
    
    keyboard = [[InlineKeyboardButton(game_data['players'][t].name, callback_data=f"kill:{t}")] for t in targets]
    
    for koruptor_id in game_data['roles']['Koruptor']:
        if game_data['players'][koruptor_id].is_alive:
            bot.send_message(
                chat_id=koruptor_id,
                text="Pilih target untuk dibunuh malam ini:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

def start_jaksa_action(bot):
    jaksa_id = game_data['roles']['Jaksa']
    
    if not game_data['players'][jaksa_id].is_alive:
        return
    
    keyboard = [
        [InlineKeyboardButton("Tangkap Seseorang", callback_data="jaksa_mode:arrest")],
        [InlineKeyboardButton("Periksa Identitas", callback_data="jaksa_mode:investigate")]
    ]
    
    bot.send_message(
        chat_id=jaksa_id,
        text="Aksi malam ini sebagai Jaksa:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# [Implementasi fungsi aksi lainnya...]

# ===== CALLBACK HANDLERS =====
def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in game_data['players']:
        query.answer("Anda tidak terdaftar dalam game ini!")
        return
    
    # Handle voting siang hari
    if data.startswith('vote:'):
        target_id = int(data.split(':')[1])
        if game_data['players'][target_id].is_alive:
            game_data['vote_results'][user_id] = target_id
            query.edit_message_text(text=f"✅ Anda memilih untuk menangkap {game_data['players'][target_id].name}")
        else:
            query.answer("Target sudah mati!")
    
    # Handle aksi malam hari
    elif data.startswith('kill:'):
        if 'koruptor' not in game_data['night_actions']:
            game_data['night_actions']['koruptor'] = []
        game_data['night_actions']['koruptor'].append(int(data.split(':')[1]))
        query.edit_message_text(text="✅ Pilihan dibunuh telah direkam")
    
    query.answer()

# ===== MAIN FUNCTION =====
def main():
    global updater
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("game", start_registration))
    dp.add_handler(CommandHandler("begin_game", start_game))
    dp.add_handler(CallbackQueryHandler(handle_callback))

    # Jalankan bot di thread terpisah
    threading.Thread(target=updater.start_polling).start()

    # Jalankan Flask
    app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    main()
