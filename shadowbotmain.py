import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ShadowBot is running")

    def log_message(self, format, *args):
        pass

def start_render_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), RenderHealthHandler)
    server.serve_forever()

if os.environ.get("PORT"):
    threading.Thread(target=start_render_health_server, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════
# WAIFU COLLECTION BOT — FINAL v5.0
# ═══════════════════════════════════════════════════════════════════

import os, random, sqlite3, logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ConversationHandler, filters, ContextTypes)

load_dotenv()

# ═══════════ CONFIG ═══════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
OWNER_ID = int(os.getenv("OWNER_ID", "8344335776"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "II_DEMONS_SHADOW_II")
SUPPORT_LINK = "https://t.me/Demon_persnality"
SUPPORT_NAME = "Demon Personality"
DB_PATH = os.getenv("DB_PATH", "shadow.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

START_PHOTO = "https://i.ibb.co/DHZbxsZ9/IMG-20260929-013718.jpg"
REQUIRED_CHANNELS = [
    ("@Abyss_diemension_Animes", "https://t.me/Abyss_diemension_Animes"),
    ("@Abyss_kdrama_main_channel", "https://t.me/Abyss_kdrama_main_channel"),
]
SPAWN_MESSAGE_THRESHOLD = 100
SPAWN_EXPIRY_SECONDS = 60
WAIFUS_PER_PAGE = 10

RARITY_EMOJI = {
    "Common": "⚪", "Uncommon": "🟢", "Rare": "🔵",
    "Epic": "🟣", "Legendary": "🟠", "Mythic": "🔴",
}

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("waifu_bot")

_SPAWN_CACHE = {}


# ═══════════ DATABASE ═══════════
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT, first_name TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS waifus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, rarity TEXT DEFAULT 'Common',
            file_id TEXT, image_url TEXT, image_source TEXT,
            description TEXT, created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS user_waifus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, waifu_id INTEGER NOT NULL,
            grabbed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS spawns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, message_id INTEGER,
            waifu_id INTEGER NOT NULL,
            spawned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT, status TEXT DEFAULT 'active',
            grabbed_by INTEGER
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS group_counters (
            chat_id INTEGER PRIMARY KEY,
            msg_count INTEGER DEFAULT 0,
            total_spawns INTEGER DEFAULT 0, last_spawn TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

        for col, typ in [("name", "TEXT"), ("rarity", "TEXT DEFAULT 'Common'")]:
            try:
                c.execute(f"ALTER TABLE waifus ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass

    log.info("✅ DB initialized")


# ═══════════ PLAYER HELPERS ═══════════
def get_or_create_player(uid, username=None, first_name=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        row = c.fetchone()
        if row:
            return dict(row)
        c.execute("INSERT INTO players (user_id, username, first_name) VALUES (?,?,?)",
                  (uid, username, first_name))
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        return dict(c.fetchone())


# ═══════════ ADMIN HELPERS ═══════════
def is_admin(uid):
    if uid == OWNER_ID:
        return True
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM admins WHERE user_id=?", (uid,))
        return c.fetchone() is not None


def add_admin(uid, added_by):
    with get_conn() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO admins (user_id, added_by) VALUES (?,?)", (uid, added_by))
            return True
        except sqlite3.IntegrityError:
            return False


def remove_admin(uid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE user_id=?", (uid,))
        return c.rowcount > 0


def get_all_admins():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, added_at FROM admins ORDER BY added_at DESC")
        return [dict(r) for r in c.fetchall()]


# ═══════════ WAIFU HELPERS ═══════════
def add_waifu(name="", rarity="Common", file_id=None, image_url=None, description=""):
    src = "file_id" if file_id else "url"
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO waifus (name, rarity, file_id, image_url, image_source, description)
                     VALUES (?,?,?,?,?,?)""",
                  (name, rarity, file_id, image_url, src, description))
        return c.lastrowid


def get_random_waifu():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM waifus WHERE active=1 ORDER BY RANDOM() LIMIT 1")
        row = c.fetchone()
        return dict(row) if row else None


def get_waifu(wid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM waifus WHERE id=?", (wid,))
        row = c.fetchone()
        return dict(row) if row else None


def get_all_waifus():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM waifus WHERE active=1 ORDER BY id DESC")
        return [dict(r) for r in c.fetchall()]


def delete_waifu(wid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE waifus SET active=0 WHERE id=?", (wid,))


def count_waifu_owners(wid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_waifus WHERE waifu_id=?", (wid,))
        return c.fetchone()[0]


# ═══════════ USER COLLECTION ═══════════
def give_waifu_to_user(user_id, waifu_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO user_waifus (user_id, waifu_id) VALUES (?,?)",
                  (user_id, waifu_id))


def get_user_waifus(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT uw.id AS uw_id, uw.grabbed_at,
                            w.id AS waifu_id, w.name, w.rarity, w.file_id,
                            w.image_url, w.image_source, w.description
                     FROM user_waifus uw
                     JOIN waifus w ON uw.waifu_id = w.id
                     WHERE uw.user_id=?
                     ORDER BY uw.grabbed_at DESC""", (user_id,))
        return [dict(r) for r in c.fetchall()]


def count_user_waifus(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_waifus WHERE user_id=?", (user_id,))
        return c.fetchone()[0]


# ═══════════ SPAWN HELPERS ═══════════
def create_spawn(chat_id, waifu_id, expires_at):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO spawns (chat_id, waifu_id, expires_at)
                     VALUES (?,?,?)""", (chat_id, waifu_id, expires_at))
        sid = c.lastrowid
    _SPAWN_CACHE.pop(chat_id, None)
    return sid


def set_spawn_message(sid, mid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET message_id=? WHERE id=?", (mid, sid))


def get_active_spawn(chat_id):
    if chat_id in _SPAWN_CACHE:
        cached = _SPAWN_CACHE[chat_id]
        if cached is None:
            return None
        if cached.get("status") == "active":
            return cached
        _SPAWN_CACHE.pop(chat_id, None)

    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT * FROM spawns WHERE chat_id=? AND status='active'
                     ORDER BY id DESC LIMIT 1""", (chat_id,))
        row = c.fetchone()
        result = dict(row) if row else None
        _SPAWN_CACHE[chat_id] = result
        return result


def close_spawn(sid, status="grabbed", grabbed_by=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET status=?, grabbed_by=? WHERE id=?",
                  (status, grabbed_by, sid))
    _SPAWN_CACHE.clear()


def expire_spawns():
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""UPDATE spawns SET status='expired'
                     WHERE status='active' AND expires_at<?""", (now,))
        n = c.rowcount
    if n:
        _SPAWN_CACHE.clear()
    return n


# ═══════════ GROUP COUNTERS ═══════════
def incr_msg(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT msg_count FROM group_counters WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO group_counters (chat_id, msg_count) VALUES (?,1)", (chat_id,))
            return 1
        nc = row["msg_count"] + 1
        c.execute("UPDATE group_counters SET msg_count=? WHERE chat_id=?", (nc, chat_id))
        return nc


def reset_msg(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""UPDATE group_counters SET msg_count=0,
                     total_spawns=total_spawns+1,
                     last_spawn=CURRENT_TIMESTAMP WHERE chat_id=?""", (chat_id,))


def get_group_stats(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT msg_count, total_spawns FROM group_counters WHERE chat_id=?",
                  (chat_id,))
        row = c.fetchone()
        return dict(row) if row else {"msg_count": 0, "total_spawns": 0}


# ═══════════ FORCE JOIN ═══════════
async def is_joined(bot, uid):
    for ch, _ in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status not in ("creator", "administrator", "member", "restricted"):
                return False, f"Tumne {ch} join nahi kiya"
        except Exception as e:
            log.error(f"Force-join check failed for {ch}: {e}")
            return False, f"Bot {ch} ka admin nahi hai"
    return True, "OK"


JOIN_TEXT = (
    "🔒 <b>Pehle dono channels join karo!</b>\n\n"
    "Neeche wale <b>dono channels</b> join karo, phir "
    "<b>'Maine Join Kar Liya'</b> button dabao:"
)


def kb_join():
    rows = [[InlineKeyboardButton(f"📢 {ch}", url=url, style="primary")]
            for ch, url in REQUIRED_CHANNELS]
    rows.append([InlineKeyboardButton("✅ Maine Join Kar Liya",
                                       callback_data="check_join", style="success")])
    return InlineKeyboardMarkup(rows)


# ═══════════ KEYBOARDS ═══════════
def kb_start():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}", style="primary")],
        [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK, style="success")],
        [InlineKeyboardButton("➕ Add Me To Your GC",
                              url=f"https://t.me/{BOT_USERNAME}?startgroup=true",
                              style="primary")],
    ])


def kb_help():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}", style="primary")],
        [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK, style="success")],
        [InlineKeyboardButton("➕ Add Me To Your GC",
                              url=f"https://t.me/{BOT_USERNAME}?startgroup=true",
                              style="primary")],
    ])


def kb_harem_open(uid, count):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🌸 Open Harem ({count})",
                              callback_data=f"harem_open:{uid}:0", style="success")],
    ])


def kb_harem_nav(uid, page, total_pages):
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"harem_page:{uid}:{page-1}",
                                         style="primary"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="harem_noop",
                                     style="primary"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"harem_page:{uid}:{page+1}",
                                         style="primary"))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton("🔙 Close", callback_data="harem_close", style="danger")],
    ])


def kb_rarity():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚪ Common", callback_data="rarity:Common", style="primary"),
            InlineKeyboardButton("🟢 Uncommon", callback_data="rarity:Uncommon", style="success"),
        ],
        [
            InlineKeyboardButton("🔵 Rare", callback_data="rarity:Rare", style="primary"),
            InlineKeyboardButton("🟣 Epic", callback_data="rarity:Epic", style="primary"),
        ],
        [
            InlineKeyboardButton("🟠 Legendary", callback_data="rarity:Legendary", style="success"),
            InlineKeyboardButton("🔴 Mythic", callback_data="rarity:Mythic", style="danger"),
        ],
    ])


# ═══════════ START ═══════════
START_CAPTION = (
    "╔══════════════════════════════╗\n"
    "║   🌑  <b>WAIFU COLLECTION BOT</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🌸 <b>Welcome to the Harem!</b>\n\n"
    "⚔️ <b>Kaise khelna:</b>\n"
    "▫️ Group me 100 messages pe waifu spawn hogi\n"
    "▫️ Uska <b>naam dhundho</b> aur grab karo\n"
    "▫️ Apni collection <b>/myshadow</b> se dekho\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>Quick Commands:</b>\n"
    "▫️ /arise &lt;name&gt; — Waifu grab\n"
    "▫️ /viewtime — Gate timer\n"
    "▫️ /myshadow — Harem dekho\n"
    "▫️ /check — Waifu info\n"
    "▫️ /rank — Top collectors\n"
    "▫️ /rarity — Rarity stats\n"
    "▫️ /global — Bot stats\n"
    "▫️ /help — Complete guide\n\n"
    f"💬 <b>Support:</b> <a href='{SUPPORT_LINK}'>{SUPPORT_NAME}</a>"
)


async def cmd_start(update, context):
    u = update.effective_user
    try:
        get_or_create_player(u.id, u.username, u.first_name)
    except Exception as e:
        log.error(f"Player create failed: {e}")

    try:
        await update.message.reply_photo(
            photo=START_PHOTO,
            caption=START_CAPTION,
            parse_mode="HTML",
            reply_markup=kb_start(),
            read_timeout=10,
            write_timeout=10,
            connect_timeout=10,
        )
    except Exception as e:
        log.error(f"Start photo failed: {e}")
        try:
            await update.message.reply_text(
                START_CAPTION, parse_mode="HTML", reply_markup=kb_start()
            )
        except Exception as e2:
            log.error(f"Start text also failed: {e2}")


# ═══════════ HELP ═══════════
HELP_TEXT = (
    "╔══════════════════════════════╗\n"
    "║   📖  <b>HOW TO PLAY</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🌑 <b>The Hunt Begins:</b>\n\n"
    "1️⃣ Group me har <b>100 messages</b> pe waifu spawn\n"
    "2️⃣ Spawn message me uska <b>naam nahi</b> likha hoga\n"
    "3️⃣ Description padho, <b>naam dhundho</b>\n"
    "4️⃣ Phir likho: <code>/arise &lt;name&gt;</code>\n"
    "5️⃣ Sahi naam = waifu tumhari!\n"
    "6️⃣ <b>/myshadow</b> se apni harem dekho\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>PLAYER COMMANDS:</b>\n"
    "▫️ /start — Bot shuru\n"
    "▫️ /arise &lt;name&gt; — Waifu grab\n"
    "▫️ /viewtime — Gate timer\n"
    "▫️ /myshadow — Apni harem\n"
    "▫️ /check &lt;id&gt; — Waifu info\n"
    "▫️ /rank — Top collectors\n"
    "▫️ /rarity — Rarity stats\n"
    "▫️ /global — Bot stats\n"
    "▫️ /help — Ye help"
)


async def cmd_help(update, context):
    try:
        await update.message.reply_photo(
            photo=START_PHOTO,
            caption=HELP_TEXT,
            parse_mode="HTML",
            reply_markup=kb_help(),
            read_timeout=10,
            write_timeout=10,
            connect_timeout=10,
        )
    except Exception as e:
        log.error(f"Help photo failed: {e}")
        try:
            await update.message.reply_text(
                HELP_TEXT, parse_mode="HTML", reply_markup=kb_help()
            )
        except Exception as e2:
            log.error(f"Help text also failed: {e2}")


# ═══════════ OHELP ═══════════
OHELP_TEXT = (
    "╔══════════════════════════════╗\n"
    "║   👑  <b>OWNER / ADMIN HELP</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🛡️ <b>Waifu Management:</b>\n"
    "▫️ <code>/addshadow</code> — Naya waifu add karo\n"
    "   ├─ 📸 Pic bhej\n"
    "   ├─ 📝 Name bhej\n"
    "   ├─ ⭐ Rarity chuno (button ya text)\n"
    "   └─ 📖 Description bhej\n\n"
    "▫️ <code>/waifulist</code> — Saari waifus list\n"
    "▫️ <code>/delwaifu &lt;id&gt;</code> — Waifu delete\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "👑 <b>Owner Only:</b>\n"
    "▫️ <code>/addadmin</code> — Reply ya <code>/addadmin &lt;id&gt;</code>\n"
    "▫️ <code>/removeadmin</code> — Admin hata do\n"
    "▫️ <code>/admins</code> — Saare admins list\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ <b>Important:</b>\n"
    "<i>Description me waifu ka naam zaroor likho!</i>\n"
    "<i>Jaise: \"Rem ek blue-haired maid hai\"</i>\n"
    "<i>Warna user /arise nahi kar payega.</i>"
)


async def cmd_ohelp(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "🚫 <b>Not Authorized!</b>\n\n"
            "Ye command sirf <b>Owner</b> aur <b>Admins</b> ke liye hai.",
            parse_mode="HTML"
        )
        return
    await update.message.reply_text(OHELP_TEXT, parse_mode="HTML")


# ═══════════ ARISE ═══════════
async def cmd_arise(update, context):
    chat = update.effective_chat
    u = update.effective_user

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Sirf group me.")
        return

    if not context.args:
        await update.message.reply_text(
            "╔══════════════════════════════╗\n"
            "║  ⚠️  <b>NAAM LIKHNA ZAROORI HAI</b>  ║\n"
            "╚══════════════════════════════╝\n\n"
            "🌑 <i>Yaha sab kuch naam se hi milta hai.</i>\n"
            "💡 <b>Usage:</b> <code>/arise &lt;name&gt;</code>\n"
            "📌 <b>Example:</b> <code>/arise Rem</code>\n\n"
            "<i>Spawn message ki description padho — naam wahi milega.</i>",
            parse_mode="HTML"
        )
        return

    user_input = " ".join(context.args).strip()
    if not user_input:
        await update.message.reply_text("❌ <b>Naam likhna zaroori hai.</b>")
        return

    active = get_active_spawn(chat.id)
    if not active:
        await update.message.reply_text(
            "🌑 <b>Koi waifu spawn nahi hai abhi.</b>\n"
            "<i>100 messages pe nayi waifu aayegi.</i>",
            parse_mode="HTML"
        )
        return

    waifu = get_waifu(active["waifu_id"])
    if not waifu:
        await update.message.reply_text("❌ Waifu nahi mili.")
        return

    correct_name = (waifu.get("name") or "").strip().lower()
    user_name_lower = user_input.lower()

    if user_name_lower != correct_name:
        await update.message.reply_text(
            "╔══════════════════════════════╗\n"
            "║   🚫  <b>GALAT NAAM  —  ARISE FAILED</b>   ║\n"
            "╚══════════════════════════════╝\n\n"
            f"👤 Tune likha: <code>{user_input}</code>\n"
            f"🔍 <i>Par ye naam kisi spawn se match nahi karta.</i>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <b>Kaise sahi kare:</b>\n"
            "▫️ Upar spawn message ki <b>description</b> padho\n"
            "▫️ Usme waifu ka naam chhupa hai\n"
            "▫️ Wahi naam <b>exactly</b> likho\n"
            "▫️ Case se farak nahi padta\n\n"
            "🎯 <b>Example:</b> <code>/arise Rem</code>",
            parse_mode="HTML"
        )
        return

    give_waifu_to_user(u.id, waifu["id"])
    close_spawn(active["id"], "grabbed", u.id)

    rarity = waifu.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")
    name = waifu.get("name") or "Waifu"
    total_now = count_user_waifus(u.id)

    if rarity == "Mythic":
        header = (
            "╔══════════════════════════════════╗\n"
            "║  🔥🔥  <b>M Y T H I C   G R A B</b>  🔥🔥  ║\n"
            "╚══════════════════════════════════╝\n\n"
            "🌟 <b>BHAI KYA MILA HAI TUJHE!</b>\n"
            "👑 Ye ek <b>MYTHIC</b> waifu hai — server pe sabse rare!\n"
        )
    elif rarity == "Legendary":
        header = (
            "╔══════════════════════════════════╗\n"
            "║  ⚡  <b>L E G E N D A R Y   G R A B</b>  ⚡  ║\n"
            "╚══════════════════════════════════╝\n\n"
            "🔥 <b>Wah bhai wah!</b>\n"
            "💎 Ye ek <b>Legendary</b> waifu hai — bohot lucky ho!\n"
        )
    elif rarity == "Epic":
        header = (
            "╔══════════════════════════════════╗\n"
            "║   ✨  <b>E P I C   G R A B</b>  ✨   ║\n"
            "╚══════════════════════════════════╝\n\n"
            "💜 <b>Kya baat hai!</b>\n"
            "🎯 Ye ek <b>Epic</b> waifu hai — solid grab!\n"
        )
    else:
        header = (
            "╔══════════════════════════════════╗\n"
            "║   ✨  <b>A R I S E   S U C C E S S</b>  ✨   ║\n"
            "╚══════════════════════════════════╝\n\n"
            f"🌑 <b>{u.first_name}</b> ne sahi naam likha!\n"
            "👤 Waifu tumhari hui — congratulations, Hunter!\n"
        )

    cap = (
        f"{header}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌸 <b>Name:</b> {name}\n"
        f"⭐ <b>Rarity:</b> {re} {rarity}\n"
        f"📖 <b>Description:</b>\n"
        f"<i>{waifu.get('description', '')}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Shadow Collection:</b> {total_now} waifus\n"
        f"🏆 <i>Rank dekhne ke liye /rank</i>\n"
        f"🌸 <i>Apni harem dekhne ke liye /myshadow</i>\n\n"
        "💫 <i>\"Har grab ek naya soldier hai army me.\"</i>"
    )

    photo = waifu["image_url"] if waifu["image_source"] == "url" else waifu["file_id"]
    try:
        await context.bot.send_photo(chat.id, photo, caption=cap, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(cap, parse_mode="HTML")


# ═══════════ VIEWTIME ═══════════
async def cmd_viewtime(update, context):
    chat = update.effective_chat

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Sirf group me chalti hai.")
        return

    active = get_active_spawn(chat.id)
    if active:
        waifu = get_waifu(active["waifu_id"])
        rarity = waifu.get("rarity", "Common")
        re = RARITY_EMOJI.get(rarity, "⚪")
        await update.message.reply_text(
            "╔══════════════════════════════╗\n"
            "║  ⚠️  <b>WAIFU ALREADY SPAWNED</b>  ║\n"
            "╚══════════════════════════════╝\n\n"
            f"⭐ Rarity: {re} <b>{rarity}</b>\n"
            f"📖 <i>{waifu.get('description', '')[:200]}</i>\n\n"
            "👇 Upar spawn message pe jaake grab karo:\n"
            "<code>/arise &lt;name&gt;</code>\n"
            "<i>Naam description me chhupa hai!</i>",
            parse_mode="HTML"
        )
        return

    stats = get_group_stats(chat.id)
    cur = stats.get("msg_count", 0)
    total = stats.get("total_spawns", 0)

    remaining = max(0, SPAWN_MESSAGE_THRESHOLD - cur)
    pct = min(100, int((cur / SPAWN_MESSAGE_THRESHOLD) * 100))
    filled = int(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)

    mins = remaining
    if mins < 60:
        time_est = f"{mins} min"
    else:
        h = mins // 60
        m = mins % 60
        time_est = f"~{h}h {m}m"

    txt = (
        "╔══════════════════════════════╗\n"
        "║   🌑  <b>GATE STATUS REPORT</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"📨 <b>Messages Sent:</b> {cur}/{SPAWN_MESSAGE_THRESHOLD}\n"
        f"📊 <b>Progress:</b>\n"
        f"   <code>{bar}</code>  <b>{pct}%</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>{remaining}</b> messages baad nayi waifu spawn hogi\n"
        f"🕐 <b>Estimated time:</b> <i>{time_est}</i>\n\n"
        f"🎯 <b>Total Spawns:</b> {total}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 <i>Chat karte raho — gate khud khul jaayega!</i>"
    )
    await update.message.reply_text(txt, parse_mode="HTML")


# ═══════════ MYSHADOW ═══════════
async def cmd_myshadow(update, context):
    u = update.effective_user

    ok, reason = await is_joined(context.bot, u.id)
    if not ok:
        await update.message.reply_text(
            f"🔒 <b>Pehle dono channels join karo!</b>\n\n⚠️ {reason}",
            parse_mode="HTML", reply_markup=kb_join()
        )
        return

    total = count_user_waifus(u.id)
    if total == 0:
        await update.message.reply_text(
            "🌑 <b>Tera Harem khaali hai.</b>\n\n"
            "👉 Group me 100 msg ka wait kar\n"
            "👉 Jab waifu spawn ho, uska naam dhundh aur <b>/arise</b> chala",
            parse_mode="HTML"
        )
        return

    txt = (
        "╔══════════════════════════════╗\n"
        "║   🌑  <b>HAREM FOLDER</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👤 <b>Owner:</b> {u.first_name}\n"
        f"🌸 <b>Total Waifus:</b> {total}\n\n"
        "👇 Neeche button dabao saari waifus dekhne ke liye:"
    )
    await update.message.reply_text(txt, parse_mode="HTML",
                                     reply_markup=kb_harem_open(u.id, total))


async def show_harem_gallery(q, context, uid, page=0):
    if q.from_user.id != uid:
        await q.answer("❌ Ye tera harem nahi hai!", show_alert=True)
        return

    waifus = get_user_waifus(uid)
    if not waifus:
        await q.answer("Harem khaali hai!", show_alert=True)
        return

    total = len(waifus)
    per_page = WAIFUS_PER_PAGE
    start = page * per_page
    end = start + per_page
    batch = waifus[start:end]
    total_pages = (total + per_page - 1) // per_page

    try:
        await q.message.delete()
    except Exception:
        pass

    header = (
        "╔══════════════════════════════╗\n"
        "║   🌑  <b>HAREM GALLERY</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🌸 <b>Total Waifus:</b> {total}\n"
        f"📄 <b>Page:</b> {page+1}/{total_pages}\n"
        f"👤 <b>Owner:</b> {q.from_user.first_name}\n\n"
        "👇 <i>Neeche tumhari saari waifus:</i>"
    )
    await context.bot.send_message(q.message.chat_id, header, parse_mode="HTML")

    media = []
    for w in batch:
        photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
        name = w.get("name") or "Waifu"
        rarity = w.get("rarity", "Common")
        re = RARITY_EMOJI.get(rarity, "⚪")
        desc = (w.get("description") or "")[:120]
        caption = (
            f"🌸 <b>{name}</b>\n"
            f"⭐ Rarity: {re} <b>{rarity}</b>\n\n"
            f"📖 <i>{desc}</i>"
        )
        media.append(InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"))

    try:
        await context.bot.send_media_group(q.message.chat_id, media)
    except Exception as e:
        log.error(f"Media group failed: {e}")
        for m in media:
            try:
                await context.bot.send_photo(q.message.chat_id, m.media,
                                              caption=m.caption, parse_mode="HTML")
            except Exception:
                pass

    await context.bot.send_message(
        q.message.chat_id,
        f"📄 <b>Page {page+1}/{total_pages}</b> — <i>Navigate karo:</i>",
        parse_mode="HTML",
        reply_markup=kb_harem_nav(uid, page, total_pages)
    )


# ═══════════ CHECK ═══════════
async def cmd_check(update, context):
    if not context.args:
        await update.message.reply_text(
            "📌 Usage: <code>/check &lt;waifu_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    try:
        wid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Valid ID daal.")
        return

    w = get_waifu(wid)
    if not w:
        await update.message.reply_text(f"❌ ID {wid} wali waifu nahi mili.")
        return

    owner_count = count_waifu_owners(wid)
    rarity = w.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")
    name = w.get("name") or "Unknown"

    cap = (
        "╔══════════════════════════════╗\n"
        "║   🔍  <b>WAIFU INFO</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🌸 <b>{name}</b>\n"
        f"🆔 ID: <code>{wid}</code>\n"
        f"⭐ Rarity: {re} <b>{rarity}</b>\n"
        f"👥 Owners: <b>{owner_count}</b> log ne liya\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <i>{w.get('description', '')}</i>"
    )
    photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
    try:
        await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(cap, parse_mode="HTML")


# ═══════════ RANK ═══════════
async def cmd_rank(update, context):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT user_id, COUNT(*) as cnt
                     FROM user_waifus
                     GROUP BY user_id
                     ORDER BY cnt DESC LIMIT 10""")
        rows = c.fetchall()

    if not rows:
        await update.message.reply_text("📭 Abhi koi collection nahi hai.")
        return

    txt = (
        "╔══════════════════════════════╗\n"
        "║   🏆  <b>TOP COLLECTORS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
    )
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        try:
            user = await context.bot.get_chat(r["user_id"])
            name = user.first_name or "Unknown"
        except Exception:
            name = f"User {r['user_id']}"
        prefix = medals[i] if i < 3 else f"<b>{i+1}.</b>"
        txt += f"{prefix} {name} — <b>{r['cnt']}</b> 🌸\n"

    await update.message.reply_text(txt, parse_mode="HTML")


# ═══════════ RARITY ═══════════
async def cmd_rarity(update, context):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT rarity, COUNT(*) as cnt
                     FROM waifus WHERE active=1
                     GROUP BY rarity""")
        rows = c.fetchall()

    if not rows:
        await update.message.reply_text("📭 Abhi koi waifu nahi hai.")
        return

    rarity_order = ["Mythic", "Legendary", "Epic", "Rare", "Uncommon", "Common"]
    counts = {r["rarity"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    max_rarity = max(counts, key=counts.get) if counts else None

    txt = (
        "╔══════════════════════════════╗\n"
        "║   💎  <b>RARITY STATISTICS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        "<i>\"Har rarity ka apna charm hai, Hunter.\"</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    for rar in rarity_order:
        if rar in counts:
            re = RARITY_EMOJI.get(rar, "⚪")
            count = counts[rar]
            pct = int((count / total) * 100)
            filled = int(pct / 5)
            bar = "█" * filled + "░" * (20 - filled)
            mark = " 👑" if rar == max_rarity else ""
            txt += (
                f"{re} <b>{rar}</b>{mark}\n"
                f"   <code>{bar}</code> <b>{count}</b> ({pct}%)\n\n"
            )

    txt += (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌸 <b>Total Waifus:</b> {total}\n"
        f"👑 <b>Most Common:</b> {RARITY_EMOJI.get(max_rarity, '⚪')} <b>{max_rarity}</b>\n\n"
        "<i>\"Collect them all, one by one.\"</i>"
    )

    await update.message.reply_text(txt, parse_mode="HTML")


# ═══════════ GLOBAL ═══════════
async def cmd_global(update, context):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT chat_id) FROM group_counters")
        groups = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM players")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM waifus WHERE active=1")
        waifus = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM user_waifus")
        collected = c.fetchone()[0]

    txt = (
        "╔══════════════════════════════╗\n"
        "║   🌍  <b>GLOBAL STATS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"💬 <b>Groups:</b> {groups}\n"
        f"👥 <b>Players:</b> {users}\n"
        f"🌸 <b>Total Waifus:</b> {waifus}\n"
        f"📦 <b>Collected:</b> {collected}\n"
    )
    await update.message.reply_text(txt, parse_mode="HTML")


# ═══════════ ADD SHADOW ═══════════
ASK_PHOTO, ASK_NAME, ASK_RARITY, ASK_DESC = range(4)


async def addshadow_start(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin/owner.")
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        "📸 <b>Pic bhej</b>\n\n<i>(Waifu ki image ya URL)</i>",
        parse_mode="HTML"
    )
    return ASK_PHOTO


async def addshadow_photo(update, context):
    fid = url = None
    if update.message.photo:
        fid = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type and \
            update.message.document.mime_type.startswith("image/"):
        fid = update.message.document.file_id
    elif update.message.text and update.message.text.startswith(("http://", "https://")):
        url = update.message.text.strip()
    else:
        await update.message.reply_text("❌ Photo ya URL bhej.")
        return ASK_PHOTO

    context.user_data["file_id"] = fid
    context.user_data["image_url"] = url
    await update.message.reply_text("📝 <b>Name bhej</b>", parse_mode="HTML")
    return ASK_NAME


async def addshadow_name(update, context):
    name = update.message.text.strip()
    if not name or len(name) > 60:
        await update.message.reply_text("❌ Name 1-60 chars. Dobara:")
        return ASK_NAME
    context.user_data["name"] = name
    await update.message.reply_text(
        "⭐ <b>Rarity chuno:</b>\n\n"
        "<i>Button dabao ya type karo:</i>\n"
        "<code>Common, Uncommon, Rare, Epic, Legendary, Mythic</code>",
        parse_mode="HTML",
        reply_markup=kb_rarity()
    )
    return ASK_RARITY


async def addshadow_rarity_callback(update, context):
    q = update.callback_query
    await q.answer()
    rarity = q.data.split(":")[1]
    context.user_data["rarity"] = rarity
    re = RARITY_EMOJI.get(rarity, "⚪")
    await q.edit_message_text(
        f"⭐ Rarity: {re} <b>{rarity}</b>\n\n"
        f"📖 Ab <b>Description bhej</b>:\n\n"
        f"<i>⚠️ Description me waifu ka naam zaroor likho!</i>\n"
        f"<i>Jaise: \"Rem ek blue-haired maid hai\"</i>",
        parse_mode="HTML"
    )
    return ASK_DESC


async def addshadow_rarity_text(update, context):
    r = update.message.text.strip().title()
    valid = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"]
    if r not in valid:
        await update.message.reply_text(
            f"❌ <b>Valid rarity likh:</b>\n"
            f"<code>{'</code>, <code>'.join(valid)}</code>",
            parse_mode="HTML"
        )
        return ASK_RARITY
    context.user_data["rarity"] = r
    re = RARITY_EMOJI.get(r, "⚪")
    await update.message.reply_text(
        f"⭐ Rarity: {re} <b>{r}</b>\n\n"
        f"📖 Ab <b>Description bhej</b>:\n\n"
        f"<i>⚠️ Description me waifu ka naam zaroor likho!</i>",
        parse_mode="HTML"
    )
    return ASK_DESC


async def addshadow_desc(update, context):
    desc = update.message.text.strip()
    if not desc or len(desc) > 500:
        await update.message.reply_text("❌ Description 1-500 chars. Dobara:")
        return ASK_DESC

    fid = context.user_data.get("file_id")
    url = context.user_data.get("image_url")
    name = context.user_data.get("name", "")
    rarity = context.user_data.get("rarity", "Common")

    mid = add_waifu(name=name, rarity=rarity, file_id=fid, image_url=url, description=desc)
    photo = url or fid
    re = RARITY_EMOJI.get(rarity, "⚪")

    cap = (
        "╔══════════════════════════════╗\n"
        "║   ✅  <b>WAIFU ADDED</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🆔 ID: <code>{mid}</code>\n"
        f"🌸 Name: <b>{name}</b>\n"
        f"⭐ Rarity: {re} <b>{rarity}</b>\n"
        f"📖 <i>{desc}</i>"
    )
    try:
        await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(cap, parse_mode="HTML")

    context.user_data.clear()
    return ConversationHandler.END


async def addshadow_cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ═══════════ WAIFULIST / DELWAIFU ═══════════
async def cmd_waifulist(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin/owner.")
        return
    ws = get_all_waifus()
    if not ws:
        await update.message.reply_text("📭 Koi waifu nahi.")
        return
    txt = f"🌸 <b>Waifus ({len(ws)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for w in ws[:30]:
        re = RARITY_EMOJI.get(w.get("rarity", "Common"), "⚪")
        name = w.get("name") or "Unknown"
        txt += f"🆔 <code>{w['id']}</code> {re} — {name}\n"
    if len(ws) > 30:
        txt += f"\n<i>...aur {len(ws)-30}</i>"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_delwaifu(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin/owner.")
        return
    if not context.args:
        await update.message.reply_text("📌 /delwaifu <id>")
        return
    try:
        wid = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Valid ID.")
        return
    w = get_waifu(wid)
    if not w:
        await update.message.reply_text(f"❌ ID {wid} nahi mili.")
        return
    delete_waifu(wid)
    await update.message.reply_text(f"✅ Deleted ID {wid}")


# ═══════════ ADMIN MANAGEMENT ═══════════
async def cmd_addadmin(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner.")
        return

    target_id = None
    target_name = None

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name
    elif context.args:
        try:
            target_id = int(context.args[0])
            target_name = f"User {target_id}"
        except ValueError:
            await update.message.reply_text("❌ Valid user ID daal ya reply kar.")
            return
    else:
        await update.message.reply_text(
            "📌 <b>Usage:</b>\n"
            "▫️ Reply karke <code>/addadmin</code>\n"
            "▫️ Ya <code>/addadmin &lt;user_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    if target_id == OWNER_ID:
        await update.message.reply_text("❌ Owner already admin hai.")
        return

    if add_admin(target_id, update.effective_user.id):
        await update.message.reply_text(
            f"✅ <b>Admin Added!</b>\n\n"
            f"👤 {target_name}\n"
            f"🆔 <code>{target_id}</code>\n\n"
            f"Ab ye bhi <code>/ohelp</code> use kar sakta hai.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ Ye already admin hai.")


async def cmd_removeadmin(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner.")
        return

    target_id = None
    target_name = None

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name
    elif context.args:
        try:
            target_id = int(context.args[0])
            target_name = f"User {target_id}"
        except ValueError:
            await update.message.reply_text("❌ Valid user ID daal ya reply kar.")
            return
    else:
        await update.message.reply_text(
            "📌 <b>Usage:</b>\n"
            "▫️ Reply karke <code>/removeadmin</code>\n"
            "▫️ Ya <code>/removeadmin &lt;user_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    if remove_admin(target_id):
        await update.message.reply_text(
            f"✅ <b>Admin Removed</b>\n👤 {target_name}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("⚠️ Ye admin nahi hai.")


async def cmd_admins(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner.")
        return

    admins = get_all_admins()
    txt = (
        "╔══════════════════════════════╗\n"
        "║   👑  <b>ADMIN LIST</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👤 Owner: <b>tu hi hai</b>\n"
        f"🆔 <code>{OWNER_ID}</code>\n\n"
    )
    if not admins:
        txt += "📭 <i>Koi aur admin nahi hai.</i>"
    else:
        txt += f"<b>Total Admins: {len(admins)}</b>\n\n"
        for a in admins:
            try:
                user = await context.bot.get_chat(a["user_id"])
                name = user.first_name
            except Exception:
                name = "Unknown"
            txt += f"▫️ {name} — <code>{a['user_id']}</code>\n"

    await update.message.reply_text(txt, parse_mode="HTML")


# ═══════════ SPAWN SYSTEM ═══════════
async def track_message(update, context):
    if update.effective_chat.type not in ("group", "supergroup"):
        return
    if update.effective_user and update.effective_user.is_bot:
        return

    chat_id = update.effective_chat.id
    if get_active_spawn(chat_id):
        return

    count = incr_msg(chat_id)

    if count >= SPAWN_MESSAGE_THRESHOLD:
        reset_msg(chat_id)
        await spawn_waifu(chat_id, context)


async def spawn_waifu(chat_id, context):
    waifu = get_random_waifu()
    if not waifu:
        log.warning("No waifus in DB")
        return

    exp = (datetime.now(timezone.utc) +
           timedelta(seconds=SPAWN_EXPIRY_SECONDS)).isoformat()
    sid = create_spawn(chat_id, waifu["id"], exp)

    rarity = waifu.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")

    cap = (
        "╔══════════════════════════════╗\n"
        "║  🌸  <b>A MYSTERIOUS WAIFU APPEARED</b>  ║\n"
        "╚══════════════════════════════╝\n\n"
        f"⭐ Rarity: {re} <b>{rarity}</b>\n\n"
        f"📖 <i>{waifu.get('description', '')}</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>Hunter ka kaam:</b>\n"
        "▫️ Uska <b>naam dhundho</b> (description me hint hai)\n"
        "▫️ Phir likho: <code>/arise &lt;name&gt;</code>\n"
        "▫️ Case se farak nahi padta\n"
        "▫️ Galat naam = No grab\n\n"
        f"⏰ <b>{SPAWN_EXPIRY_SECONDS}s</b> me gayab ho jaayegi!"
    )
    photo = waifu["image_url"] if waifu["image_source"] == "url" else waifu["file_id"]
    try:
        msg = await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=cap,
                                            parse_mode="HTML")
        set_spawn_message(sid, msg.message_id)
        log.info(f"Spawn waifu {waifu['id']} in {chat_id} sid={sid}")
    except Exception as e:
        log.error(f"Spawn fail: {e}")


async def expire_job(context):
    n = expire_spawns()
    if n:
        log.info(f"Expired {n} spawns")


# ═══════════ CALLBACK ROUTER ═══════════
async def callback_router(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "check_join":
        ok, reason = await is_joined(context.bot, q.from_user.id)
        if ok:
            await q.answer("✅ Verified!", show_alert=True)
            try:
                await q.edit_message_text(
                    "🟢 <b>Verified!</b> ✅\n\nAb /myshadow chalao!",
                    parse_mode="HTML"
                )
            except Exception:
                await context.bot.send_message(
                    q.message.chat_id,
                    "🟢 <b>Verified!</b> ✅\nAb /myshadow chalao.",
                    parse_mode="HTML"
                )
        else:
            await q.answer(f"❌ {reason}", show_alert=True)
        return

    if data.startswith("harem_open:"):
        parts = data.split(":")
        uid = int(parts[1])
        page = int(parts[2])
        await show_harem_gallery(q, context, uid, page)
        return

    if data.startswith("harem_page:"):
        parts = data.split(":")
        uid = int(parts[1])
        page = int(parts[2])
        await show_harem_gallery(q, context, uid, page)
        return

    if data == "harem_noop":
        return

    if data == "harem_close":
        try:
            await q.message.delete()
        except Exception:
            pass
        return

    log.warning(f"Unhandled callback: {data}")


# ═══════════ MAIN ═══════════
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing in .env")
        return

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Player Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("arise", cmd_arise))
    app.add_handler(CommandHandler("viewtime", cmd_viewtime))
    app.add_handler(CommandHandler("gate", cmd_viewtime))
    app.add_handler(CommandHandler("myshadow", cmd_myshadow))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("rarity", cmd_rarity))
    app.add_handler(CommandHandler("global", cmd_global))

    # Owner/Admin Commands
    app.add_handler(CommandHandler("ohelp", cmd_ohelp))
    app.add_handler(CommandHandler("waifulist", cmd_waifulist))
    app.add_handler(CommandHandler("delwaifu", cmd_delwaifu))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))
    app.add_handler(CommandHandler("admins", cmd_admins))

    # Add Shadow Conversation
    addshadow_conv = ConversationHandler(
        entry_points=[CommandHandler("addshadow", addshadow_start)],
        states={
            ASK_PHOTO:  [MessageHandler(filters.PHOTO | filters.Document.IMAGE | filters.TEXT,
                                         addshadow_photo)],
            ASK_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_name)],
            ASK_RARITY: [
                CallbackQueryHandler(addshadow_rarity_callback, pattern=r"^rarity:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_rarity_text),
            ],
            ASK_DESC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_desc)],
        },
        fallbacks=[CommandHandler("cancel", addshadow_cancel)],
        per_user=True,
        per_chat=False,
    )
    app.add_handler(addshadow_conv)

    # Callbacks
    app.add_handler(CallbackQueryHandler(callback_router))

    # Message tracker (LAST)
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Sticker.ALL) & ~filters.COMMAND,
            track_message
        ),
        group=1
    )

    if app.job_queue:
        app.job_queue.run_repeating(expire_job, interval=30, first=10)

    log.info("🌸 Waifu Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()