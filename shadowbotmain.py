import os, random, sqlite3, asyncio, logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ConversationHandler, filters, ContextTypes)

load_dotenv()

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OWNER_ID = int(os.getenv("OWNER_ID", "8344335776"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "II_DEMONS_SHADOW_II")
DB_PATH = os.getenv("DB_PATH", "shadow.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

START_PHOTO = "https://i.ibb.co/DHZbxsZ9/IMG-20260929-013718.jpg"
REQUIRED_CHANNELS = [
    ("@Abyss_diemension_Animes", "https://t.me/Abyss_diemension_Animes"),
    ("@Abyss_kdrama_main_channel", "https://t.me/Abyss_kdrama_main_channel"),
]
SPAWN_MESSAGE_THRESHOLD = 100
SPAWN_EXPIRY_SECONDS = 60
VIEWTIME_COST = 5
ITEMS_PER_PAGE = 30

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("shadow_bot")

# ==================== AI ====================
AI_ENABLED = True
AI_FAILS = 0
ROAST_FALLBACK = [
    "{name} ka face dekh ke monster bhi bhaag jaata hai.",
    "{name} ki aukaat nahi hai hunter banne ki, chai bana le.",
    "{name} ka IQ room temperature se bhi kam hai.",
    "{name} ko dekha toh lagta hai level up ka button skip kar diya.",
    "{name} ka shadow bhi usse muh chhupa ke chalta hai.",
    "{name} ki army me sirf 2 shadows hain — ek bhookha, ek tabahi.",
    "{name} ne system accept kiya, system ne reject kar diya.",
    "{name} ka combat log padha toh AI ne suicide note likh diya.",
]
MONSTER_TAUNTS = [
    "Keekee! Fresh meat!", "Tera khoon mera dinner!",
    "Dum hai toh aa, hunter!", "Aaj teri haddi pasli nikalta hoon!",
    "Maut ka darr dikha du?",
]

_ai = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _ai = genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        log.warning(f"Gemini init failed: {e}")

async def _reenable_ai():
    global AI_ENABLED, AI_FAILS
    await asyncio.sleep(300)
    AI_ENABLED = True; AI_FAILS = 0

async def ai_or_fallback(prompt, fallback, timeout=5.0):
    global AI_ENABLED, AI_FAILS
    if not AI_ENABLED or not _ai:
        return random.choice(fallback)
    try:
        r = await asyncio.wait_for(_ai.generate_content_async(prompt), timeout=timeout)
        AI_FAILS = 0
        return r.text.strip()
    except Exception as e:
        AI_FAILS += 1
        log.warning(f"AI fail ({AI_FAILS}): {e}")
        if AI_FAILS >= 3:
            AI_ENABLED = False
            asyncio.create_task(_reenable_ai())
        return random.choice(fallback)

async def ai_roast(name):
    prompt = f"Savage Hinglish roast {name} ko 1-2 lines, funny, no slurs, no family."
    return await ai_or_fallback(prompt, [r.format(name=name) for r in ROAST_FALLBACK])

# ==================== DATABASE ====================
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY,
            username TEXT, first_name TEXT, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0,
            shadows INTEGER DEFAULT 0, essence INTEGER DEFAULT 100, phase INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS monsters (id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, rank TEXT NOT NULL, type TEXT NOT NULL, description TEXT,
            file_id TEXT, image_url TEXT, image_source TEXT, created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS player_monsters (id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL, monster_id INTEGER NOT NULL,
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS spawns (id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, message_id INTEGER, monster_id INTEGER NOT NULL,
            current_hp INTEGER, max_hp INTEGER, spawned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT, status TEXT DEFAULT 'active', claimed_by INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS combats (id INTEGER PRIMARY KEY AUTOINCREMENT,
            spawn_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, player_id INTEGER NOT NULL,
            player_hp INTEGER, player_max_hp INTEGER, player_mp INTEGER, player_max_mp INTEGER,
            monster_hp INTEGER, monster_max_hp INTEGER, turn INTEGER DEFAULT 1,
            capture_tries INTEGER DEFAULT 0, status TEXT DEFAULT 'active',
            started_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS group_counters (chat_id INTEGER PRIMARY KEY,
            msg_count INTEGER DEFAULT 0, total_spawns INTEGER DEFAULT 0, last_spawn TEXT)""")
    log.info("DB ready")

def get_or_create_player(uid, username=None, first_name=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        row = c.fetchone()
        if row: return dict(row)
        c.execute("INSERT INTO players (user_id, username, first_name) VALUES (?,?,?)",
                  (uid, username, first_name))
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        return dict(c.fetchone())

def deduct_essence(uid, amt):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT essence FROM players WHERE user_id=?", (uid,))
        row = c.fetchone()
        if not row or row["essence"] < amt: return False
        c.execute("UPDATE players SET essence=essence-? WHERE user_id=?", (amt, uid))
        return True

def add_essence(uid, amt):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE players SET essence=essence+? WHERE user_id=?", (amt, uid))

def add_xp(uid, amt):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE players SET xp=xp+? WHERE user_id=?", (amt, uid))
        c.execute("SELECT xp, level FROM players WHERE user_id=?", (uid,))
        row = c.fetchone()
        if row:
            nl = 1 + int((row["xp"] / 100) ** 0.7)
            if nl > row["level"]:
                c.execute("UPDATE players SET level=? WHERE user_id=?", (nl, uid))

def add_monster(name, rank, type_, desc, file_id=None, image_url=None, created_by=None):
    src = "file_id" if file_id else "url"
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO monsters (name, rank, type, description, file_id,
                     image_url, image_source, created_by) VALUES (?,?,?,?,?,?,?,?)""",
                  (name, rank, type_, desc, file_id, image_url, src, created_by))
        return c.lastrowid

def get_all_monsters():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM monsters WHERE active=1 ORDER BY id DESC")
        return [dict(r) for r in c.fetchall()]

def get_monster(mid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM monsters WHERE id=?", (mid,))
        row = c.fetchone()
        return dict(row) if row else None

def get_random_monster():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM monsters WHERE active=1 ORDER BY RANDOM() LIMIT 1")
        row = c.fetchone()
        return dict(row) if row else None

def delete_monster(mid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE monsters SET active=0 WHERE id=?", (mid,))

def total_monsters():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM monsters WHERE active=1")
        return c.fetchone()[0]

def give_monster(owner_id, monster_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO player_monsters (owner_id, monster_id) VALUES (?,?)",
                  (owner_id, monster_id))

def get_army(owner_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT pm.id AS pm_id, pm.owner_id, m.id AS monster_id, m.name,
                     m.rank, m.type, m.description, m.file_id, m.image_url, m.image_source
                     FROM player_monsters pm JOIN monsters m ON pm.monster_id=m.id
                     WHERE pm.owner_id=? ORDER BY pm.captured_at DESC""", (owner_id,))
        return [dict(r) for r in c.fetchall()]

def get_player_monster(pm_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT pm.id AS pm_id, pm.owner_id, m.id AS monster_id, m.name,
                     m.rank, m.type, m.description, m.file_id, m.image_url, m.image_source
                     FROM player_monsters pm JOIN monsters m ON pm.monster_id=m.id
                     WHERE pm.id=?""", (pm_id,))
        row = c.fetchone()
        return dict(row) if row else None

def create_spawn(chat_id, monster_id, expires_at, max_hp):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO spawns (chat_id, monster_id, expires_at, current_hp, max_hp)
                     VALUES (?,?,?,?,?)""", (chat_id, monster_id, expires_at, max_hp, max_hp))
        return c.lastrowid

def set_spawn_msg(sid, mid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET message_id=? WHERE id=?", (mid, sid))

def get_active_spawn(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT * FROM spawns WHERE chat_id=? AND status='active'
                     ORDER BY id DESC LIMIT 1""", (chat_id,))
        row = c.fetchone()
        return dict(row) if row else None

def get_spawn(sid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM spawns WHERE id=?", (sid,))
        row = c.fetchone()
        return dict(row) if row else None

def update_spawn_hp(sid, hp):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET current_hp=? WHERE id=?", (hp, sid))

def close_spawn(sid, status="claimed", claimed_by=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET status=?, claimed_by=? WHERE id=?",
                  (status, claimed_by, sid))

def expire_spawns():
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET status='expired' WHERE status='active' AND expires_at<?", (now,))
        return c.rowcount

def create_combat(spawn_id, chat_id, player_id, p_hp, p_mp, m_hp):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO combats (spawn_id, chat_id, player_id, player_hp,
                     player_max_hp, player_mp, player_max_mp, monster_hp, monster_max_hp)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (spawn_id, chat_id, player_id, p_hp, p_hp, p_mp, p_mp, m_hp, m_hp))
        return c.lastrowid

def get_combat(cid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM combats WHERE id=?", (cid,))
        row = c.fetchone()
        return dict(row) if row else None

def get_active_combat(spawn_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM combats WHERE spawn_id=? AND status='active'", (spawn_id,))
        row = c.fetchone()
        return dict(row) if row else None

def update_combat(cid, **kw):
    if not kw: return
    fields = ", ".join(f"{k}=?" for k in kw)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(f"UPDATE combats SET {fields} WHERE id=?", list(kw.values()) + [cid])

def end_combat(cid, status="won"):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE combats SET status=? WHERE id=?", (status, cid))

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
        c.execute("""UPDATE group_counters SET msg_count=0, total_spawns=total_spawns+1,
                     last_spawn=CURRENT_TIMESTAMP WHERE chat_id=?""", (chat_id,))

def get_group_stats(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM group_counters WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        return dict(row) if row else {"msg_count": 0, "total_spawns": 0}

def bot_stats():
    with get_conn() as conn:
        c = conn.cursor()
        out = {}
        for k, q in [("players","SELECT COUNT(*) FROM players"),
                     ("monsters","SELECT COUNT(*) FROM monsters WHERE active=1"),
                     ("captured","SELECT COUNT(*) FROM player_monsters"),
                     ("spawns","SELECT COUNT(*) FROM spawns"),
                     ("groups","SELECT COUNT(*) FROM group_counters")]:
            c.execute(q); out[k] = c.fetchone()[0]
        return out

def all_group_ids():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT chat_id FROM group_counters")
        return [r["chat_id"] for r in c.fetchall()]

RANK_STATS = {
    "E": {"hp":200,"atk":15,"def":8,"xp":35,"ess":15,"cap":90},
    "D": {"hp":350,"atk":25,"def":15,"xp":70,"ess":30,"cap":75},
    "C": {"hp":600,"atk":45,"def":25,"xp":120,"ess":55,"cap":60},
    "B": {"hp":1000,"atk":80,"def":40,"xp":220,"ess":100,"cap":45},
    "A": {"hp":1800,"atk":130,"def":65,"xp":400,"ess":180,"cap":30},
    "S": {"hp":3000,"atk":200,"def":100,"xp":800,"ess":350,"cap":15},
}
def m_stats(rank): return RANK_STATS.get(rank, RANK_STATS["E"])
def p_stats(level): return {"hp":100+level*10,"mp":50+level*5,"atk":10+level*3,"def":5+level*2}

# ==================== KEYBOARDS ====================
def kb_start():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 ▶️ START JOURNEY", callback_data="start_game")],
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}")],
        [InlineKeyboardButton("🟣 📖 How To Play", callback_data="howto"),
         InlineKeyboardButton("🔵 🎒 My Profile", callback_data="profile_btn")],
    ])

def kb_profile():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🐉 My Army", callback_data="army_redirect")],
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}")],
    ])

def kb_join():
    rows = [[InlineKeyboardButton(f"📢 {ch}", url=url)] for ch, url in REQUIRED_CHANNELS]
    rows.append([InlineKeyboardButton("🟢 ✅ Maine Join Kar Liya", callback_data="check_join")])
    return InlineKeyboardMarkup(rows)

def kb_spawn(sid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 ⚔️ Attack", callback_data=f"cb_attack:{sid}"),
         InlineKeyboardButton("🟢 🎯 Capture", callback_data=f"cb_capture:{sid}")],
        [InlineKeyboardButton("🔵 🛡️ Defend", callback_data=f"cb_defend:{sid}"),
         InlineKeyboardButton("⚪ 🏃 Flee", callback_data=f"cb_flee:{sid}")],
    ])

def kb_combat(sid, cap=False):
    lbl = "🟢 🎯 CAPTURE!" if cap else "⚪ 🎯 Capture"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 ⚔️ Attack", callback_data=f"cb_attack:{sid}"),
         InlineKeyboardButton("🔵 🔥 Skill", callback_data=f"cb_skill:{sid}")],
        [InlineKeyboardButton("🔵 🛡️ Defend", callback_data=f"cb_defend:{sid}"),
         InlineKeyboardButton(lbl, callback_data=f"cb_capture:{sid}")],
        [InlineKeyboardButton("⚪ 🏃 Flee", callback_data=f"cb_flee:{sid}")],
    ])

def kb_army(army, uid, page=0):
    st = page * ITEMS_PER_PAGE
    items = army[st:st+ITEMS_PER_PAGE]
    buttons, row = [], []
    for pm in items:
        lbl = f"{pm['rank']} {pm['name']}"
        if len(lbl) > 20: lbl = lbl[:18]+"…"
        row.append(InlineKeyboardButton(lbl, callback_data=f"army_show:{pm['pm_id']}"))
        if len(row) == 3: buttons.append(row); row = []
    if row: buttons.append(row)
    tp = (len(army)+ITEMS_PER_PAGE-1)//ITEMS_PER_PAGE
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"army_page:{uid}:{page-1}"))
    if tp > 1: nav.append(InlineKeyboardButton(f"📄 {page+1}/{tp}", callback_data="army_noop"))
    if page < tp-1: nav.append(InlineKeyboardButton("Next ▶", callback_data=f"army_page:{uid}:{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"army_page:{uid}:{page}")])
    return InlineKeyboardMarkup(buttons)

# ==================== FORCE JOIN ====================
async def is_joined(bot, uid):
    for ch, _ in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status not in ("creator","administrator","member","restricted"):
                return False
        except Exception:
            return False
    return True

JOIN_TEXT = ("🔒 <b>Army Dekhne Ke Liye Pehle Join Karo</b>\n\n"
             "Neeche wale <b>dono channels</b> join karo, phir "
             "<b>'Maine Join Kar Liya'</b> button dabao:")

# ==================== START ====================
START_CAPTION = (
    "🌑 <b>『 SHADOW MONARCH SYSTEM 』</b> 🌑\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "⚔️ <b>Ek nayi duniya me swagat hai, Hunter.</b>\n\n"
    "🗡️ Gates khul chuke hain.\n"
    "💀 Monsters jaag rahe hain.\n"
    "👑 Sirf ek hi <b>Shadow Monarch</b> ban sakta hai.\n\n"
    "<i>\"Arise.\"</i>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "🔹 Level up karo, monsters capture karo\n"
    "🔹 Shadows collect karo, PvP me logon ko haro\n"
    "🔹 Level 100 ke baad shuru hoti hai <b>asli journey</b>\n\n"
    "🌑 <i>Tera System activate ho chuka hai...</i>\n"
    "👇 Neeche se shuru kar:"
)

async def cmd_start(update, context):
    u = update.effective_user
    get_or_create_player(u.id, u.username, u.first_name)
    try:
        await update.message.reply_photo(photo=START_PHOTO, caption=START_CAPTION,
                                          parse_mode="HTML", reply_markup=kb_start())
    except Exception:
        await update.message.reply_text(START_CAPTION, parse_mode="HTML", reply_markup=kb_start())

async def cmd_profile(update, context):
    u = update.effective_user
    p = get_or_create_player(u.id, u.username, u.first_name)
    txt = (f"👤 <b>HUNTER PROFILE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
           f"🆔 <code>{u.id}</code>\n🌑 <b>{u.first_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
           f"⭐ Level: <b>{p['level']}</b>\n✨ XP: <b>{p['xp']}</b>\n"
           f"🌑 Shadows: <b>{p['shadows']}</b>\n💎 Essence: <b>{p['essence']}</b>\n"
           f"🎭 Phase: <b>{'Hunter Era' if p['phase']==1 else 'Monarch Era'}</b>\n"
           f"━━━━━━━━━━━━━━━━━━━━━━\n🌍 System Monsters: <b>{total_monsters()}</b>\n"
           f"👑 Owner: @{OWNER_USERNAME}")
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb_profile())

# ==================== ARMY ====================
async def cmd_army(update, context):
    u = update.effective_user
    if not await is_joined(context.bot, u.id):
        await update.message.reply_text(JOIN_TEXT, parse_mode="HTML", reply_markup=kb_join())
        return
    army = get_army(u.id)
    if not army:
        await update.message.reply_text(
            "🌑 <b>Tera Army khaali hai.</b>\n\n"
            "👉 Group me 100 msg ka wait kar\n"
            "👉 Monster spawn hone pe Attack kar\n"
            "👉 HP <20% pe Capture dabao\n"
            "👉 /army se dekh",
            parse_mode="HTML"
        )
        return
    txt = (
        f"🐉 <b>SHADOW ARMY — {u.first_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Total: <b>{len(army)}</b>\n\n"
        f"👇 Kisi monster pe tap karo:"
    )
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb_army(army, u.id, 0))


async def cb_army(q, context):
    data = q.data
    if data == "army_noop":
        return
    if data.startswith("army_show:"):
        pm_id = int(data.split(":")[1])
        mon = get_player_monster(pm_id)
        if not mon:
            await q.answer("❌ Nahi mila.", show_alert=True)
            return
        if mon["owner_id"] != q.from_user.id:
            await q.answer("❌ Ye tera monster nahi!", show_alert=True)
            return
        st = m_stats(mon["rank"])
        cap = (
            f"👹 <b>{mon['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐ Rank: <b>{mon['rank']}</b>\n"
            f"🎯 Type: <b>{mon['type']}</b>\n"
            f"👤 Owner: <b>{q.from_user.first_name}</b>\n"
            f"❤️ HP: <b>{st['hp']}</b> | ⚔️ ATK: <b>{st['atk']}</b> | 🛡️ DEF: <b>{st['def']}</b>\n"
            f"📖 <i>{mon['description']}</i>"
        )
        ph = mon["image_url"] if mon["image_source"] == "url" else mon["file_id"]
        try:
            await context.bot.send_photo(q.message.chat_id, ph, caption=cap, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(q.message.chat_id, cap, parse_mode="HTML")
        return
    if data.startswith("army_page:"):
        _, uid, pg = data.split(":")
        uid, pg = int(uid), int(pg)
        army = get_army(uid)
        if not army:
            await q.edit_message_text("🌑 Army khaali.")
            return
        txt = (
            f"🐉 <b>SHADOW ARMY</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 Total: <b>{len(army)}</b>\n\n"
            f"👇 Kisi pe tap karo:"
        )
        await q.edit_message_text(txt, parse_mode="HTML", reply_markup=kb_army(army, uid, pg))


# ==================== VIEWTIME ====================
async def cmd_viewtime(update, context):
    chat = update.effective_chat
    u = update.effective_user
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Sirf group me.")
        return
    active = get_active_spawn(chat.id)
    if active:
        mon = get_monster(active["monster_id"])
        await update.message.reply_text(
            f"⚠️ <b>Gate Already Open!</b>\n"
            f"👹 {mon['name']} ({mon['rank']}-Rank)\n"
            f"🎯 Attack/Capture button dabao!\n\n"
            f"<i>(Free check)</i>",
            parse_mode="HTML"
        )
        return
    p = get_or_create_player(u.id, u.username, u.first_name)
    if p["essence"] < VIEWTIME_COST:
        await update.message.reply_text(
            f"❌ <b>Not Enough Essence!</b>\n"
            f"💎 Tere paas: <b>{p['essence']}</b>\n"
            f"💰 Chahiye: <b>{VIEWTIME_COST}</b>",
            parse_mode="HTML"
        )
        return
    deduct_essence(u.id, VIEWTIME_COST)
    s = get_group_stats(chat.id)
    cur = s["msg_count"]
    rem = max(0, SPAWN_MESSAGE_THRESHOLD - cur)
    pct = min(100, int((cur / SPAWN_MESSAGE_THRESHOLD) * 100))
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    txt = (
        f"🌑 <b>GATE STATUS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📨 Messages: <b>{cur}</b>/{SPAWN_MESSAGE_THRESHOLD}\n"
        f"📊 <code>{bar}</code> <b>{pct}%</b>\n\n"
        f"⏳ <b>{rem}</b> messages baad gate khulega\n\n"
        f"🎯 Spawns: <b>{s.get('total_spawns', 0)}</b>\n"
        f"💎 Left: <b>{p['essence'] - VIEWTIME_COST}</b> | 💰 -{VIEWTIME_COST}"
    )
    await update.message.reply_text(txt, parse_mode="HTML")


# ==================== ROAST ====================
async def cmd_roast(update, context):
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user.first_name
    elif context.args:
        target = " ".join(context.args)
    else:
        await update.message.reply_text("📌 Reply karo ya /roast @user")
        return
    txt = await ai_roast(target)
    await update.message.reply_text(f"🔥 <b>{target}</b>\n{txt}", parse_mode="HTML")


# ==================== SPAWN ====================
async def track_message(update, context):
    if update.effective_chat.type not in ("group", "supergroup"):
        return
    if update.effective_user and update.effective_user.is_bot:
        return
    chat_id = update.effective_chat.id
    if get_active_spawn(chat_id):
        return
    count = incr_msg(chat_id)
    if count == SPAWN_MESSAGE_THRESHOLD - 10:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ <b>Gate Alert!</b>\n\nSirf <b>10 messages</b> baad gate khulega!",
                parse_mode="HTML"
            )
        except Exception:
            pass
    if count >= SPAWN_MESSAGE_THRESHOLD:
        reset_msg(chat_id)
        await spawn_monster(chat_id, context)


async def spawn_monster(chat_id, context):
    mon = get_random_monster()
    if not mon:
        log.warning("No monsters")
        return
    st = m_stats(mon["rank"])
    exp = (datetime.now(timezone.utc) + timedelta(seconds=SPAWN_EXPIRY_SECONDS)).isoformat()
    sid = create_spawn(chat_id, mon["id"], exp, st["hp"])
    cap = (
        f"⚠️ <b>GATE OPENED — {mon['rank']}-RANK</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👹 <b>{mon['name']}</b>\n"
        f"⭐ Rank: <b>{mon['rank']}</b>\n"
        f"🎯 Type: <b>{mon['type']}</b>\n"
        f"❤️ HP: <b>{st['hp']}</b> | ⚔️ ATK: <b>{st['atk']}</b>\n"
        f"📖 <i>{mon['description']}</i>\n\n"
        f"⏰ <b>{SPAWN_EXPIRY_SECONDS}s</b> me bhaag jaayega!"
    )
    ph = mon["image_url"] if mon["image_source"] == "url" else mon["file_id"]
    try:
        msg = await context.bot.send_photo(
            chat_id=chat_id, photo=ph, caption=cap,
            parse_mode="HTML", reply_markup=kb_spawn(sid)
        )
        set_spawn_msg(sid, msg.message_id)
        log.info(f"Spawn {mon['id']} in {chat_id} sid={sid}")
    except Exception as e:
        log.error(f"Spawn fail: {e}")


async def expire_job(context):
    n = expire_spawns()
    if n:
        log.info(f"Expired {n} spawns")


# ==================== COMBAT ====================
def hp_bar(hp, mx, ln=10):
    if mx <= 0:
        return "░" * ln
    f = max(0, min(ln, int((hp / mx) * ln)))
    return "█" * f + "░" * (ln - f)


def combat_text(pname, p_hp, p_mx, p_mp, mname, m_hp, m_mx, turn, lines, cap):
    txt = (
        f"⚔️ <b>COMBAT — {pname} vs {mname}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>{pname}</b>\n"
        f"HP <code>{hp_bar(p_hp, p_mx)}</code> {p_hp}/{p_mx}\n"
        f"MP <b>{p_mp}</b>\n\n"
        f"👹 <b>{mname}</b>\n"
        f"HP <code>{hp_bar(m_hp, m_mx)}</code> {m_hp}/{m_mx}\n"
    )
    if cap:
        txt += "\n🟢 <b>Capture UNLOCKED!</b>\n"
    txt += f"\n━━━━━━━━━━━━━━━━━━━━━━\n<b>Turn {turn}</b>\n"
    for ln in lines[-4:]:
        txt += f"➤ {ln}\n"
    return txt


async def handle_combat_action(q, context, action, spawn_id):
    u = q.from_user
    spawn = get_spawn(spawn_id)
    if not spawn or spawn["status"] != "active":
        await q.answer("⏰ Spawn expire!", show_alert=True)
        return
    if spawn["chat_id"] != q.message.chat.id:
        await q.answer("❌ Ye spawn iss group ka nahi.", show_alert=True)
        return
    mon = get_monster(spawn["monster_id"])
    if not mon:
        await q.answer("❌ Monster nahi.", show_alert=True)
        return
    pl = get_or_create_player(u.id, u.username, u.first_name)
    p_s = p_stats(pl["level"])
    m_s = m_stats(mon["rank"])

    combat = get_active_combat(spawn_id)
    if not combat:
        cid = create_combat(
            spawn_id, q.message.chat.id, u.id,
            p_s["hp"], p_s["mp"], spawn["current_hp"] or m_s["hp"]
        )
        combat = get_combat(cid)
    elif combat["player_id"] != u.id:
        await q.answer("❌ Ye combat kisi aur ka hai!", show_alert=True)
        return

    lines = []
    p_hp = combat["player_hp"]
    p_mx = combat["player_max_hp"]
    p_mp = combat["player_mp"]
    m_hp = combat["monster_hp"]
    m_mx = combat["monster_max_hp"]
    turn = combat["turn"] + 1
    cap_tries = combat["capture_tries"]
    skip_monster = False

    if action == "attack":
        dmg = max(5, p_s["atk"] - m_s["def"])
        crit = random.random() < 0.1
        if crit:
            dmg *= 2
        m_hp = max(0, m_hp - dmg)
        lines.append(f"⚔️ You attacked → <b>{dmg}</b>{' 💥CRIT!' if crit else ''}")
    elif action == "skill":
        if p_mp < 20:
            await q.answer("❌ MP kam! (20 chahiye)", show_alert=True)
            return
        p_mp -= 20
        dmg = max(10, int(p_s["atk"] * 2 - m_s["def"]))
        m_hp = max(0, m_hp - dmg)
        lines.append(f"🔥 Skill! → <b>{dmg}</b> (-20 MP)")
    elif action == "defend":
        lines.append("🛡️ Defended (next -50%)")
    elif action == "flee":
        if random.random() < 0.5:
            close_spawn(spawn_id, "fled", u.id)
            end_combat(combat["id"], "fled")
            await q.edit_message_caption(
                caption=f"🏃 <b>{u.first_name} bhaag gaya!</b>",
                parse_mode="HTML"
            )
            return
        lines.append("❌ Flee fail!")
    elif action == "capture":
        if m_hp > m_mx * 0.2:
            await q.answer("❌ HP 20% se zyada! Pehle attack.", show_alert=True)
            return
        if cap_tries >= 3:
            await q.answer("❌ 3 tries khatam!", show_alert=True)
            return
        cap_tries += 1
        if random.random() < (m_s["cap"] / 100.0):
            give_monster(u.id, mon["id"])
            close_spawn(spawn_id, "captured", u.id)
            end_combat(combat["id"], "captured")
            add_xp(u.id, m_s["xp"])
            add_essence(u.id, m_s["ess"])
            await q.edit_message_caption(
                caption=(
                    f"🎯 <b>CAPTURED!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👹 <b>{mon['name']}</b>\n"
                    f"⭐ {mon['rank']} | 🎯 {mon['type']}\n\n"
                    f"✅ +{m_s['xp']} XP | 💎 +{m_s['ess']} Essence\n"
                    f"🐉 Added to your Army!\n\n"
                    f"<i>/army se dekho</i>"
                ),
                parse_mode="HTML"
            )
            return
        else:
            lines.append(f"❌ Capture fail! ({3 - cap_tries} tries left)")
            enr = int(m_s["atk"] * 1.5)
            p_hp = max(0, p_hp - enr)
            lines.append(f"😡 Enrage hit → {enr} dmg")
            skip_monster = True

    if m_hp <= 0:
        close_spawn(spawn_id, "killed", u.id)
        end_combat(combat["id"], "killed")
        add_xp(u.id, m_s["xp"])
        add_essence(u.id, m_s["ess"])
        await q.edit_message_caption(
            caption=(
                f"💀 <b>MONSTER DEFEATED!</b>\n"
                f"👹 {mon['name']} haraya!\n\n"
                f"🎁 Loot:\n✨ +{m_s['xp']} XP | 💎 +{m_s['ess']} Essence"
            ),
            parse_mode="HTML"
        )
        return

    if not skip_monster:
        taunt = random.choice(MONSTER_TAUNTS)
        if random.random() < 0.5:
            try:
                taunt = await ai_or_fallback(
                    f"Ek {mon['name']} banke 1 line Hinglish taunt, max 10 words.",
                    MONSTER_TAUNTS,
                    timeout=3.0
                )
            except Exception:
                pass
        m_dmg = max(3, m_s["atk"] - p_s["def"])
        if action == "defend":
            m_dmg = m_dmg // 2
        p_hp = max(0, p_hp - m_dmg)
        lines.append(f"👹 <i>\"{taunt}\"</i>")
        lines.append(f"💥 Monster → <b>{m_dmg}</b> dmg")

    if p_hp <= 0:
        end_combat(combat["id"], "lost")
        close_spawn(spawn_id, "player_died", u.id)
        await q.edit_message_caption(
            caption=f"💀 <b>TU MAR GAYA!</b>\n{mon['name']} ne haraya.",
            parse_mode="HTML"
        )
        return

    update_combat(
        combat["id"],
        player_hp=p_hp, player_mp=p_mp, monster_hp=m_hp,
        turn=turn, capture_tries=cap_tries
    )
    update_spawn_hp(spawn_id, m_hp)
    cap = m_hp <= m_mx * 0.2
    new_txt = combat_text(u.first_name, p_hp, p_mx, p_mp, mon["name"], m_hp, m_mx, turn, lines, cap)
    try:
        await q.edit_message_caption(
            caption=new_txt,
            parse_mode="HTML",
            reply_markup=kb_combat(spawn_id, cap)
        )
    except Exception as e:
        log.error(f"edit fail: {e}")


# ==================== ADD SHADOW ====================
(ASK_NAME, ASK_RANK, ASK_TYPE, ASK_DESC, ASK_PHOTO) = range(5)
VALID_RANKS = {"E", "D", "C", "B", "A", "S"}
VALID_TYPES = {"Attack", "Decent", "Tank", "Support", "Speed", "Mage", "Assassin"}


async def addshadow_start(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner.")
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        "👹 <b>Naya Shadow</b>\n\n1️⃣ Naam bhej:",
        parse_mode="HTML"
    )
    return ASK_NAME


async def addshadow_name(update, context):
    n = update.message.text.strip()
    if not n or len(n) > 40:
        await update.message.reply_text("❌ 1-40 chars. Dobara:")
        return ASK_NAME
    context.user_data["m_name"] = n
    await update.message.reply_text("2️⃣ Rank (E/D/C/B/A/S):")
    return ASK_RANK


async def addshadow_rank(update, context):
    r = update.message.text.strip().upper()
    if r not in VALID_RANKS:
        await update.message.reply_text("❌ E/D/C/B/A/S. Dobara:")
        return ASK_RANK
    context.user_data["m_rank"] = r
    await update.message.reply_text("3️⃣ Type (Attack/Decent/Tank/Support/Speed/Mage/Assassin):")
    return ASK_TYPE


async def addshadow_type(update, context):
    t = update.message.text.strip().title()
    if t not in VALID_TYPES:
        await update.message.reply_text("❌ Valid type. Dobara:")
        return ASK_TYPE
    context.user_data["m_type"] = t
    await update.message.reply_text("4️⃣ 1-2 line description:")
    return ASK_DESC


async def addshadow_desc(update, context):
    d = update.message.text.strip()
    if not d or len(d) > 200:
        await update.message.reply_text("❌ 1-200 chars. Dobara:")
        return ASK_DESC
    context.user_data["m_desc"] = d
    await update.message.reply_text("5️⃣ Ab monster ki photo bhej:")
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
    d = context.user_data
    mid = add_monster(
        d["m_name"], d["m_rank"], d["m_type"], d["m_desc"],
        file_id=fid, image_url=url, created_by=update.effective_user.id
    )
    st = m_stats(d["m_rank"])
    cap = (
        f"✅ <b>Shadow Added!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: <code>{mid}</code>\n"
        f"👹 <b>{d['m_name']}</b>\n"
        f"⭐ {d['m_rank']} | 🎯 {d['m_type']}\n"
        f"❤️ HP: {st['hp']} | ⚔️ ATK: {st['atk']} | 🛡️ DEF: {st['def']}\n"
        f"📖 <i>{d['m_desc']}</i>"
    )
    ph = url or fid
    try:
        await update.message.reply_photo(ph, caption=cap, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(cap, parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END


async def addshadow_cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ==================== OWNER ====================
def is_owner(uid):
    return uid == OWNER_ID


async def cmd_monsters(update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Sirf owner.")
        return
    ms = get_all_monsters()
    if not ms:
        await update.message.reply_text("📭 Koi monster nahi.")
        return
    txt = f"👹 <b>Monsters ({len(ms)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for m in ms[:50]:
        txt += f"🆔 <code>{m['id']}</code> — <b>{m['name']}</b> ({m['rank']}, {m['type']})\n"
    if len(ms) > 50:
        txt += f"\n<i>...aur {len(ms) - 50}</i>"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_delmonster(update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Sirf owner.")
        return
    if not context.args:
        await update.message.reply_text("📌 /delmonster <id>")
        return
    try:
        mid = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Valid ID.")
        return
    mon = get_monster(mid)
    if not mon:
        await update.message.reply_text(f"❌ ID {mid} nahi.")
        return
    delete_monster(mid)
    await update.message.reply_text(f"✅ Deleted: <b>{mon['name']}</b>", parse_mode="HTML")


async def cmd_botstats(update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Sirf owner.")
        return
    s = bot_stats()
    txt = (
        f"📊 <b>BOT STATS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Players: <b>{s['players']}</b>\n"
        f"👹 Monsters: <b>{s['monsters']}</b>\n"
        f"🎯 Captured: <b>{s['captured']}</b>\n"
        f"⚠️ Spawns: <b>{s['spawns']}</b>\n"
        f"💬 Groups: <b>{s['groups']}</b>"
    )
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_broadcast(update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Sirf owner.")
        return
    if not context.args:
        await update.message.reply_text("📌 /broadcast <msg>")
        return
    msg = " ".join(context.args)
    sent, failed = 0, 0
    for cid in all_group_ids():
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=f"📢 <b>ANNOUNCEMENT</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n{msg}",
                parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ {sent} | ❌ {failed}")


# ==================== CALLBACK ROUTER ====================
async def callback_router(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data == "start_game":
        get_or_create_player(q.from_user.id, q.from_user.username, q.from_user.first_name)
        await q.edit_message_caption(
            caption="🌑 <b>System Activated!</b>\n\nUse /profile, /army, /roast",
            parse_mode="HTML"
        )
        return
    if data == "howto":
        txt = (
            "📖 <b>HOW TO PLAY</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ /profile — Stats\n"
            "2️⃣ /army — Monster collection\n"
            "3️⃣ /viewtime — Gate timer (-5💎)\n"
            "4️⃣ /roast — Roast someone\n\n"
            "🔸 100 msg pe monster spawn\n"
            "🔸 Attack karke HP kam karo\n"
            "🔸 Capture button (HP<20%)\n"
            "🔸 Army me add ho jaayega!"
        )
        await q.edit_message_text(txt, parse_mode="HTML")
        return
    if data == "profile_btn":
        p = get_or_create_player(q.from_user.id, q.from_user.username, q.from_user.first_name)
        txt = (
            f"👤 <b>PROFILE</b>\n"
            f"⭐ Lv <b>{p['level']}</b> | XP <b>{p['xp']}</b>\n"
            f"🌑 Shadows <b>{p['shadows']}</b> | 💎 <b>{p['essence']}</b>"
        )
        await q.edit_message_text(txt, parse_mode="HTML")
        return
    if data == "army_redirect":
        await q.edit_message_text("🐉 Use /army to view your army.")
        return
    if data == "check_join":
        if await is_joined(context.bot, q.from_user.id):
            await q.edit_message_text(
                "🟢 <b>Verified!</b> ✅\nAb /army chala.",
                parse_mode="HTML"
            )
        else:
            await q.answer("❌ Pehle dono channel join kar!", show_alert=True)
        return
    if data.startswith("army_"):
        await cb_army(q, context)
        return
    for pfx, act in [
        ("cb_attack:", "attack"),
        ("cb_skill:", "skill"),
        ("cb_defend:", "defend"),
        ("cb_capture:", "capture"),
        ("cb_flee:", "flee"),
    ]:
        if data.startswith(pfx):
            sid = int(data.split(":")[1])
            await handle_combat_action(q, context, act, sid)
            return
    log.warning(f"Unhandled: {data}")


# ==================== MAIN ====================
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing in .env")
        return
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("army", cmd_army))
    app.add_handler(CommandHandler("viewtime", cmd_viewtime))
    app.add_handler(CommandHandler("gate", cmd_viewtime))
    app.add_handler(CommandHandler("roast", cmd_roast))
    app.add_handler(CommandHandler("monsters", cmd_monsters))
    app.add_handler(CommandHandler("delmonster", cmd_delmonster))
    app.add_handler(CommandHandler("stats", cmd_botstats))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    addshadow_conv = ConversationHandler(
        entry_points=[CommandHandler("addshadow", addshadow_start)],
        states={
            ASK_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_name)],
            ASK_RANK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_rank)],
            ASK_TYPE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_type)],
            ASK_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_desc)],
            ASK_PHOTO: [MessageHandler(filters.PHOTO | filters.Document.IMAGE | filters.TEXT, addshadow_photo)],
        },
        fallbacks=[CommandHandler("cancel", addshadow_cancel)],
        per_user=True,
        per_chat=False,
    )
    app.add_handler(addshadow_conv)
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Sticker.ALL) & ~filters.COMMAND,
            track_message
        ),
        group=1
    )

    if app.job_queue:
        app.job_queue.run_repeating(expire_job, interval=30, first=10)

    log.info("🌑 Shadow Monarch Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()