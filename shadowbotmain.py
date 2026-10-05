import asyncio
# ═══════════════════════════════════════════════════════════════════
# WAIFU/HUSBANDO COLLECTION BOT — v10.3 FINAL
# 33 Rarities + Global Search + Clean Army + Gift System
# ═══════════════════════════════════════════════════════════════════

import os
import threading
import time
import logging
import random
import sqlite3
import io
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==================== RENDER HEALTH SERVER ====================

class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ShadowBot is alive")

    def log_message(self, format, *args):
        pass


def start_render_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), RenderHealthHandler)
    logging.info(f"🌐 Render health server listening on port {port}")
    server.serve_forever()

# ===============================================================

from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ConversationHandler, filters, ContextTypes)

try:
    import httpx
    from PIL import Image, ImageDraw, ImageFont
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
OWNER_ID = int(os.getenv("OWNER_ID", "8344335776"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "II_DEMONS_SHADOW_II")
SUPPORT_LINK = "https://t.me/Demon_persnality"
SUPPORT_NAME = "Demon Personality"
DB_PATH = os.getenv("DB_PATH", "shadow.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

BOT_START_TIME = time.time()

START_PHOTO = "https://i.ibb.co/DHZbxsZ9/IMG-20260929-013718.jpg"
REQUIRED_CHANNELS = [
    ("@Abyss_diemension_Animes", "https://t.me/Abyss_diemension_Animes"),
    ("@Abyss_kdrama_main_channel", "https://t.me/Abyss_kdrama_main_channel"),
]
SPAWN_MESSAGE_THRESHOLD = 100
SPAWN_EXPIRY_SECONDS = 300
COLLAGE_PER_PAGE = 30
BUTTONS_PER_PAGE = 12

# ═══════════ 33 RARITIES ═══════════
RARITY_EMOJI = {
    "Common":    "⚪", "Uncommon":  "🟢", "Rare":      "🔵",
    "Epic":      "🟣", "Legendary": "🟠", "Mythic":    "🔴",
    "Summer":    "🌊", "Valentine": "💖", "Christmas": "🎄",
    "Halloween": "🎃", "Easter":    "🐰", "New Year":  "🎆",
    "Sakura":    "🌸", "Winter":    "❄️",
    "Ecchi":     "😈", "Yandere":   "🔪", "Tsundere":  "💢",
    "Neko":      "🐱", "Maid":      "🎀", "Fox":       "🦊",
    "Angel":     "😇", "Demon":     "👺", "Vampire":   "🧛",
    "Ninja":     "🥷",
    "Divine":    "✨", "Shadow":    "🌑", "Eternal":   "♾️",
    "Cosmic":    "🌌", "God":       "🪬", "Supreme":   "👑",
    "Secret":    "🔒", "Exclusive": "💎", "Limited":   "⏳",
}

RARITY_ORDER = [
    "Exclusive", "Secret", "Limited",
    "Supreme", "God", "Cosmic", "Eternal", "Shadow", "Divine",
    "Vampire", "Ninja", "Demon", "Angel",
    "Fox", "Maid", "Neko", "Tsundere", "Yandere", "Ecchi",
    "Winter", "Sakura", "New Year", "Easter", "Halloween",
    "Christmas", "Valentine", "Summer",
    "Mythic", "Legendary", "Epic", "Rare", "Uncommon", "Common",
]

ROAST_TEMPLATES = [
    "{name} ki aukaat nahi hai hunter banne ki, chai bana le.",
    "{name} ka face dekh ke monster bhi bhaag jaata hai.",
    "{name} ka IQ room temperature se bhi kam hai.",
    "{name} ko dekha toh lagta hai level up ka button skip kar diya.",
    "{name} ka shadow bhi usse muh chhupa ke chalta hai.",
    "{name} ke paas waifu hai lekin common sense nahi.",
    "{name} ki army me sirf 2 waifus hain — ek bhookha, ek tabahi.",
    "{name} ne system accept kiya, system ne reject kar diya.",
    "{name} ka combat log padha toh bot ne suicide note likh diya.",
    "{name} ki himmat dekh ke gate khud band ho gaya.",
    "{name} E-rank hunter hai lekin ego S-rank ka rakhta hai.",
    "{name} ne waifu grab ki toh waifu ne khud report kar di.",
    "{name} itna slow hai ki loading screen bhi wait karta hai.",
    "{name} ka naam sun ke monster ghar chala jaata hai.",
    "{name} ke harem me sirf body pillow hai.",
    "{name} ki photo dekh ke hunter association ne resign kar diya.",
    "{name} ka playstyle dekh ke tutorial bhi confuse ho gaya.",
    "{name} spawn hote hi waifu ne block kar diya.",
    "{name} ki typing speed itni slow hai, message delivery late hoti hai.",
    "{name} ko arise kiya toh shadow bhi fail ho gaya.",
]

ROAST_ENDINGS = [
    "💀 <i>Shots fired!</i>",
    "☠️ <i>Rest in pieces.</i>",
    "🩸 <i>That's gonna leave a scar.</i>",
    "⚰️ <i>Kya scene hai.</i>",
    "💥 <i>Boom.</i>",
    "🔥 <i>Fully burnt!</i>",
    "🥀 <i>Destroyed.</i>",
]

HYPE_LINES = [
    "Ek aur shikaar, ek aur jeet! 💫",
    "Ye waifu teri hui, Hunter! 🎯",
    "Kya baat hai, collection strong ho rahi hai! 🔥",
    "Sahi pakde hain! 👏",
    "System ne approve kar diya! ⚡",
    "Ye grab perfect tha! 💯",
    "Aur ek add ho gayi army me! 🎉",
    "Kya timing, kya luck! ✨",
]

RARITY_HERO = {
    "Supreme":   "👑  S U P R E M E   G R A B  👑",
    "God":       "🪬  G O D   T I E R   G R A B  🪬",
    "Cosmic":    "🌌  C O S M I C   G R A B  🌌",
    "Eternal":   "♾️  E T E R N A L   G R A B  ♾️",
    "Shadow":    "🌑  S H A D O W   G R A B  🌑",
    "Divine":    "✨  D I V I N E   G R A B  ✨",
    "Exclusive": "💎  E X C L U S I V E   G R A B  💎",
    "Secret":    "🔒  S E C R E T   G R A B  🔒",
    "Limited":   "⏳  L I M I T E D   G R A B  ⏳",
    "Mythic":    "🔥  M Y T H I C   G R A B  🔥",
    "Legendary": "⚡  L E G E N D A R Y  ⚡",
    "Epic":      "💜  E P I C   G R A B  💜",
    "Ecchi":     "😈  E C C H I   G R A B  😈",
    "Yandere":   "🔪  Y A N D E R E   G R A B  🔪",
    "Tsundere":  "💢  T S U N D E R E  💢",
    "Vampire":   "🧛  V A M P I R E   G R A B  🧛",
    "Demon":     "👺  D E M O N   G R A B  👺",
    "Angel":     "😇  A N G E L   G R A B  😇",
    "Ninja":     "🥷  N I N J A   G R A B  🥷",
    "Neko":      "🐱  N E K O   G R A B  🐱",
    "Maid":      "🎀  M A I D   G R A B  🎀",
    "Fox":       "🦊  F O X   G R A B  🦊",
}

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("waifu_bot")

_SPAWN_CACHE = {}


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
        c.execute("""CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS waifus (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, gender TEXT DEFAULT 'waifu', rarity TEXT DEFAULT 'Common', file_id TEXT, image_url TEXT, image_source TEXT, description TEXT, created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_waifus (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, waifu_id INTEGER NOT NULL, grabbed_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS spawns (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER, waifu_id INTEGER NOT NULL, spawned_at TEXT DEFAULT CURRENT_TIMESTAMP, expires_at TEXT, status TEXT DEFAULT 'active', grabbed_by INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS group_counters (chat_id INTEGER PRIMARY KEY, msg_count INTEGER DEFAULT 0, total_spawns INTEGER DEFAULT 0, last_spawn TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        for col, typ in [("name", "TEXT"), ("rarity", "TEXT DEFAULT 'Common'"), ("gender", "TEXT DEFAULT 'waifu'")]:
            try:
                c.execute(f"ALTER TABLE waifus ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass
    log.info("✅ DB initialized")


def gender_emoji(g): return "🌸" if g == "waifu" else "🗡️"
def gender_label(g): return "Waifu" if g == "waifu" else "Husbando"


def get_or_create_player(uid, username=None, first_name=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        row = c.fetchone()
        if row: return dict(row)
        c.execute("INSERT INTO players (user_id, username, first_name) VALUES (?,?,?)", (uid, username, first_name))
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        return dict(c.fetchone())


def is_admin(uid):
    if uid == OWNER_ID: return True
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
        c.execute("SELECT user_id FROM admins ORDER BY added_at DESC")
        return [dict(r) for r in c.fetchall()]


def add_waifu(name="", gender="waifu", rarity="Common", file_id=None, image_url=None, description=""):
    src = "file_id" if file_id else "url"
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO waifus (name, gender, rarity, file_id, image_url, image_source, description) VALUES (?,?,?,?,?,?,?)",
                  (name, gender, rarity, file_id, image_url, src, description))
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


def give_waifu_to_user(user_id, waifu_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO user_waifus (user_id, waifu_id) VALUES (?,?)", (user_id, waifu_id))


def get_user_waifus(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT uw.id AS uw_id, uw.grabbed_at, w.id AS waifu_id, w.name, w.gender, w.rarity, w.file_id, w.image_url, w.image_source, w.description FROM user_waifus uw JOIN waifus w ON uw.waifu_id = w.id WHERE uw.user_id=? ORDER BY uw.grabbed_at DESC""", (user_id,))
        return [dict(r) for r in c.fetchall()]


def get_user_waifu_detail(uw_id, user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT uw.id AS uw_id, uw.grabbed_at, w.id AS waifu_id, w.name, w.gender, w.rarity, w.file_id, w.image_url, w.image_source, w.description FROM user_waifus uw JOIN waifus w ON uw.waifu_id = w.id WHERE uw.id=? AND uw.user_id=?""", (uw_id, user_id))
        row = c.fetchone()
        return dict(row) if row else None


def remove_user_waifu(uw_id, user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM user_waifus WHERE id=? AND user_id=?", (uw_id, user_id))
        return c.rowcount > 0


def count_user_waifus(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_waifus WHERE user_id=?", (user_id,))
        return c.fetchone()[0]


def get_user_rarity_counts(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT w.rarity, COUNT(*) as cnt FROM user_waifus uw JOIN waifus w ON uw.waifu_id = w.id WHERE uw.user_id=? GROUP BY w.rarity""", (user_id,))
        return {r["rarity"]: r["cnt"] for r in c.fetchall()}


def get_user_gender_counts(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT w.gender, COUNT(*) as cnt FROM user_waifus uw JOIN waifus w ON uw.waifu_id = w.id WHERE uw.user_id=? GROUP BY w.gender""", (user_id,))
        return {r["gender"]: r["cnt"] for r in c.fetchall()}


def get_all_rarity_counts():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT rarity, COUNT(*) as cnt FROM waifus WHERE active=1 GROUP BY rarity")
        return {r["rarity"]: r["cnt"] for r in c.fetchall()}


def get_all_gender_counts():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT gender, COUNT(*) as cnt FROM waifus WHERE active=1 GROUP BY gender")
        return {r["gender"]: r["cnt"] for r in c.fetchall()}


def create_spawn(chat_id, waifu_id, expires_at):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO spawns (chat_id, waifu_id, expires_at) VALUES (?,?,?)", (chat_id, waifu_id, expires_at))
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
        if cached is None: return None
        if cached.get("status") == "active": return cached
        _SPAWN_CACHE.pop(chat_id, None)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM spawns WHERE chat_id=? AND status='active' ORDER BY id DESC LIMIT 1", (chat_id,))
        row = c.fetchone()
        result = dict(row) if row else None
        _SPAWN_CACHE[chat_id] = result
        return result


def close_spawn(sid, status="grabbed", grabbed_by=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET status=?, grabbed_by=? WHERE id=?", (status, grabbed_by, sid))
    _SPAWN_CACHE.clear()


def expire_spawns():
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET status='expired' WHERE status='active' AND expires_at<?", (now,))
        n = c.rowcount
    if n: _SPAWN_CACHE.clear()
    return n


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
        c.execute("UPDATE group_counters SET msg_count=0, total_spawns=total_spawns+1, last_spawn=CURRENT_TIMESTAMP WHERE chat_id=?", (chat_id,))


def get_group_stats(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT msg_count, total_spawns FROM group_counters WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        return dict(row) if row else {"msg_count": 0, "total_spawns": 0}


async def is_joined(bot, uid):
    for ch, _ in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status not in ("creator", "administrator", "member", "restricted"):
                return False, f"Tumne {ch} join nahi kiya"
        except Exception as e:
            log.error(f"Force-join failed for {ch}: {e}")
            return False, f"Bot {ch} ka admin nahi hai"
    return True, "OK"


JOIN_TEXT = "🔒 <b>Pehle dono channels join karo!</b>\n\nNeeche wale <b>dono channels</b> join karo, phir <b>'Maine Join Kar Liya'</b> button dabao:"


def kb_join():
    rows = [[InlineKeyboardButton(f"📢 {ch}", url=url)] for ch, url in REQUIRED_CHANNELS]
    rows.append([InlineKeyboardButton("✅ Maine Join Kar Liya", callback_data="check_join")])
    return InlineKeyboardMarkup(rows)


def kb_start():
    bot_link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}")],
        [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK)],
        [InlineKeyboardButton("➕ Add Me To Your GC", url=bot_link)],
    ])


# ═══════════ ARMY KEYBOARD — CLEAN (No filters, 2 per row) ═══════════
def kb_army(waifus, uid, page=0, rarity=None):
    buttons = []
    row = []
    for w in waifus[:BUTTONS_PER_PAGE]:
        name = w.get("name") or "Waifu"
        re = RARITY_EMOJI.get(w.get("rarity", ""), "⚪")
        ge = gender_emoji(w.get("gender", "waifu"))
        label = f"{ge} {re} {name[:14]}"
        row.append(InlineKeyboardButton(
            label,
            callback_data=f"army_det:{w['uw_id']}:0",
            style="primary"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🔍 Search Tips", callback_data="army_search_tip",
                              style="primary"),
        InlineKeyboardButton("🔙 Close", callback_data="army_close",
                              style="danger"),
    ])
    return InlineKeyboardMarkup(buttons)


def kb_army_paginated(waifus, uid, cp, tcp, rarity=None):
    kb = kb_army(waifus, uid, cp, rarity)
    if tcp > 1:
        nav = []
        if cp > 0:
            nav.append(InlineKeyboardButton("◀ Prev",
                                              callback_data=f"army_page:{cp-1}",
                                              style="primary"))
        nav.append(InlineKeyboardButton(f"📄 {cp+1}/{tcp}",
                                          callback_data="army_noop",
                                          style="primary"))
        if cp < tcp - 1:
            nav.append(InlineKeyboardButton("Next ▶",
                                              callback_data=f"army_page:{cp+1}",
                                              style="primary"))
        rows = list(kb.inline_keyboard)
        rows.insert(-1, nav)
        return InlineKeyboardMarkup(rows)
    return kb


def kb_rarity():
    buttons = []
    items = list(RARITY_EMOJI.items())
    for i in range(0, len(items), 3):
        row = []
        for rarity, emoji in items[i:i+3]:
            row.append(InlineKeyboardButton(f"{emoji} {rarity}", callback_data=f"rarity:{rarity}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def kb_gender():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌸 Waifu", callback_data="gender:waifu"),
         InlineKeyboardButton("🗡️ Husbando", callback_data="gender:husbando")],
    ])


async def create_army_collage(context, waifus, max_count=30):
    if not IMAGE_SUPPORT: return None
    waifus = waifus[:max_count]
    if not waifus: return None
    cols = 3
    cell_w, cell_h = 500, 700
    rows = (len(waifus) + cols - 1) // cols
    canvas = Image.new('RGB', (cols * cell_w, rows * cell_h), (15, 15, 25))
    draw = ImageDraw.Draw(canvas)
    try: font = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
    except:
        try: font = ImageFont.truetype("arial.ttf", 36)
        except: font = ImageFont.load_default()
    for idx, w in enumerate(waifus):
        r = idx // cols; col = idx % cols
        x = col * cell_w; y = r * cell_h
        try:
            if w["image_source"] == "url":
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(w["image_url"]); img_bytes = resp.content
            else:
                tg_file = await context.bot.get_file(w["file_id"]); img_bytes = bytes(await tg_file.download_as_bytearray())
            img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            img.thumbnail((cell_w - 20, cell_h - 100), Image.LANCZOS)
            px = x + (cell_w - img.width) // 2; py = y + (cell_h - 100 - img.height) // 2 + 10
            canvas.paste(img, (px, py))
            name = (w.get("name") or "Waifu")[:18]
            rarity = w.get("rarity", "Common"); gender = w.get("gender", "waifu")
            re = RARITY_EMOJI.get(rarity, "⚪"); ge = gender_emoji(gender)
            label = f"{ge} {re} {name}"
            draw.rectangle([x, y + cell_h - 80, x + cell_w, y + cell_h], fill=(30, 30, 45))
            try:
                bbox = draw.textbbox((0, 0), label, font=font); text_w = bbox[2] - bbox[0]
            except: text_w = len(label) * 18
            draw.text((x + (cell_w - text_w) // 2, y + cell_h - 60), label, fill=(255, 220, 240), font=font)
        except Exception as e:
            log.error(f"Collage item {idx}: {e}")
            draw.rectangle([x, y, x + cell_w, y + cell_h], fill=(50, 30, 30))
            draw.text((x + 30, y + cell_h // 2), "?", fill=(255, 255, 255), font=font)
    buf = io.BytesIO(); canvas.save(buf, format='JPEG', quality=82, optimize=True); buf.seek(0)
    return buf


START_CAPTION = (
    "╔══════════════════════════════╗\n"
    "║   🌑  <b>WAIFU COLLECTION BOT</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🌸 <b>Welcome to the Harem, Hunter!</b>\n\n"
    "⚔️ <b>Kaise khelna:</b>\n"
    "▫️ Group me 100 messages pe koi appear hoga\n"
    "▫️ Uska <b>naam dhundho</b> aur grab karo\n"
    "▫️ Apni collection <b>/army</b> se dekho\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>Quick Commands:</b>\n"
    "▫️ /arise &lt;name&gt; — Grab\n"
    "▫️ /army — Apni collection\n"
    "▫️ /search &lt;name&gt; — Global search\n"
    "▫️ /gift — Character gift karo\n"
    "▫️ /stats — Apni stats\n"
    "▫️ /roast — Roast karo\n"
    "▫️ /ping — Bot status\n"
    "▫️ /viewtime — Gate timer\n"
    "▫️ /help — Complete guide\n\n"
    f"💬 <b>Support:</b> <a href='{SUPPORT_LINK}'>{SUPPORT_NAME}</a>"
)


async def cmd_start(update, context):
    u = update.effective_user
    try: get_or_create_player(u.id, u.username, u.first_name)
    except: pass
    try:
        await update.message.reply_photo(photo=START_PHOTO, caption=START_CAPTION, parse_mode="HTML", reply_markup=kb_start(), read_timeout=15, write_timeout=15, connect_timeout=15)
        return
    except: pass
    try: await update.message.reply_text(START_CAPTION, parse_mode="HTML", reply_markup=kb_start())
    except: pass


HELP_TEXT = (
    "╔══════════════════════════════╗\n"
    "║   📖  <b>HOW TO PLAY</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🌑 <b>The Hunt Begins:</b>\n\n"
    "1️⃣ Group me har 100 messages pe koi appear hoga\n"
    "2️⃣ Waifu ya Husbando — dono ho sakte hain\n"
    "3️⃣ Spawn message me <b>naam nahi</b> likha hoga\n"
    "4️⃣ Description padho, <b>naam dhundho</b>\n"
    "5️⃣ Phir likho: <code>/arise &lt;name&gt;</code>\n"
    "6️⃣ <b>/army</b> se apni harem dekho\n\n"
    "💎 <b>33 Rarities:</b> ⚪🟢🔵🟣🟠🔴 🌊💖🎄🎃🐰🎆🌸❄️ 😈🔪💢🐱🎀🦊 😇👺🧛🥷 ✨🌑♾️🌌🪬👑 🔒💎⏳\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>PLAYER COMMANDS:</b>\n"
    "▫️ /start — Bot shuru\n"
    "▫️ /arise &lt;name&gt; — Grab\n"
    "▫️ /army — Apni gallery\n"
    "▫️ /search &lt;name&gt; — Global search\n"
    "▫️ /gift &lt;user_id&gt; &lt;waifu_id&gt; — Character gift karo\n"
    "▫️ /stats — Apni stats chart\n"
    "▫️ /roast — Kisi ko roast karo\n"
    "▫️ /ping — Bot latency check\n"
    "▫️ /viewtime — Gate timer\n"
    "▫️ /check &lt;id&gt; — Info\n"
    "▫️ /rank — Top collectors\n"
    "▫️ /rarity — Rarity stats\n"
    "▫️ /global — Bot global stats\n"
    "▫️ /help — Ye help"
)


async def cmd_help(update, context):
    try:
        await update.message.reply_photo(photo=START_PHOTO, caption=HELP_TEXT, parse_mode="HTML", reply_markup=kb_start(), read_timeout=15, write_timeout=15, connect_timeout=15)
    except:
        try: await update.message.reply_text(HELP_TEXT, parse_mode="HTML", reply_markup=kb_start())
        except: pass


OHELP_TEXT = (
    "╔══════════════════════════════╗\n"
    "║   👑  <b>OWNER / ADMIN HELP</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🛡️ <b>Character Management:</b>\n"
    "▫️ <code>/addshadow</code> — Naya character\n"
    "   ├─ 📸 Pic → 📝 Name → 🌸 Gender → ⭐ Rarity → 📖 Desc\n\n"
    "▫️ <code>/waifulist</code> — Saari list\n"
    "▫️ <code>/delwaifu &lt;id&gt;</code> — Delete\n"
    "▫️ <code>/status</code> — Total stats\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "👑 <b>Owner Only:</b>\n"
    "▫️ <code>/addadmin</code> / <code>/removeadmin</code> / <code>/admins</code>"
)


async def cmd_ohelp(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 <b>Not Authorized!</b>\n\nYe command sirf <b>Owner</b> aur <b>Admins</b> ke liye hai.", parse_mode="HTML")
        return
    await update.message.reply_text(OHELP_TEXT, parse_mode="HTML")


async def cmd_arise(update, context):
    chat = update.effective_chat
    u = update.effective_user
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Sirf group me.")
        return
    if not context.args:
        await update.message.reply_text("❌ <b>Naam likhna zaroori hai.</b>\n💡 <code>/arise &lt;name&gt;</code>", parse_mode="HTML")
        return
    user_input = " ".join(context.args).strip()
    if not user_input:
        await update.message.reply_text("❌ <b>Naam likhna zaroori hai.</b>")
        return
    active = get_active_spawn(chat.id)
    if not active:
        await update.message.reply_text("🌑 <b>Koi spawn nahi hai abhi.</b>\n<i>100 messages pe naya character aayega.</i>", parse_mode="HTML")
        return
    waifu = get_waifu(active["waifu_id"])
    if not waifu:
        await update.message.reply_text("❌ Character nahi mila.")
        return
    correct_name = (waifu.get("name") or "").strip()
    user_lower = user_input.strip().lower()
    correct_lower = correct_name.lower()
    matched = False
    if user_lower == correct_lower: matched = True
    else:
        cw = correct_lower.split(); uw = user_lower.split()
        if len(cw) >= 2:
            for w in uw:
                if w in cw: matched = True; break
        if not matched and len(uw) >= 2:
            if all(w in cw for w in uw): matched = True
    if not matched:
        await update.message.reply_text("❌ <b>Galat naam!</b> Sahi naam likho.", parse_mode="HTML")
        return
    give_waifu_to_user(u.id, waifu["id"])
    close_spawn(active["id"], "grabbed", u.id)
    rarity = waifu.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")
    gender = waifu.get("gender", "waifu")
    ge = gender_emoji(gender)
    glabel = gender_label(gender)
    name = waifu.get("name") or "Character"
    total_now = count_user_waifus(u.id)
    description = waifu.get("description", "")
    hero = RARITY_HERO.get(rarity, "✨  C H A R A C T E R   G R A B B E D  ✨")
    hype = random.choice(HYPE_LINES)
    cap = (
        f"╔══════════════════════════════════╗\n"
        f"   {hero}\n"
        f"╚══════════════════════════════════╝\n\n"
        f"        {ge} <b>{name}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎭 <b>Type:</b> {glabel}\n"
        f"⭐ <b>Rarity:</b> {re} <b>{rarity}</b>\n"
        f"📖 <b>Description:</b>\n"
        f"<i>{description}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💫 <i>\"{hype}\"</i>\n\n"
        f"📦 <b>Collection:</b> {total_now} waifus\n"
        f"🏆 <i>/army · /stats · /rank</i>"
    )
    photo = waifu["image_url"] if waifu["image_source"] == "url" else waifu["file_id"]
    try: await context.bot.send_photo(chat.id, photo, caption=cap, parse_mode="HTML")
    except: await update.message.reply_text(cap, parse_mode="HTML")


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
            "║  ⚠️  <b>ALREADY SPAWNED</b>  ║\n"
            "╚══════════════════════════════╝\n\n"
            f"⭐ Rarity: {re} <b>{rarity}</b>\n\n"
            "👇 <code>/arise &lt;name&gt;</code>",
            parse_mode="HTML"
        )
        return
    stats = get_group_stats(chat.id)
    cur = stats.get("msg_count", 0); total = stats.get("total_spawns", 0)
    remaining = max(0, SPAWN_MESSAGE_THRESHOLD - cur)
    pct = min(100, int((cur / SPAWN_MESSAGE_THRESHOLD) * 100))
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    txt = (
        "╔══════════════════════════════╗\n"
        "║   🌑  <b>GATE STATUS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"📨 <b>Messages:</b> {cur}/{SPAWN_MESSAGE_THRESHOLD}\n"
        f"📊 <code>{bar}</code> <b>{pct}%</b>\n\n"
        f"⏳ <b>{remaining}</b> messages baad spawn\n"
        f"🎯 Total Spawns: <b>{total}</b>"
    )
    await update.message.reply_text(txt, parse_mode="HTML")


async def show_army_page(chat_id, context, user_obj, rarity=None, page=0):
    all_w = get_user_waifus(user_obj.id)
    waifus = [w for w in all_w if w.get("rarity") == rarity] if rarity else all_w
    total = len(waifus)
    if total == 0:
        ft = f" ({rarity})" if rarity else ""
        await context.bot.send_message(chat_id, f"🌑 <b>Koi character nahi{ft}.</b>", parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Close", callback_data="army_close")]]))
        return
    start = page * COLLAGE_PER_PAGE; end = start + COLLAGE_PER_PAGE
    page_waifus = waifus[start:end]
    total_pages = (total + COLLAGE_PER_PAGE - 1) // COLLAGE_PER_PAGE
    r_counts = get_user_rarity_counts(user_obj.id); g_counts = get_user_gender_counts(user_obj.id)
    r_chart = "".join([f"{RARITY_EMOJI.get(r, '⚪')}{r_counts[r]}  " for r in RARITY_ORDER if r in r_counts])
    g_chart = ""
    if g_counts.get("waifu"): g_chart += f"🌸{g_counts['waifu']}  "
    if g_counts.get("husbando"): g_chart += f"🗡️{g_counts['husbando']}  "
    fl = rarity if rarity else "All"
    rf = RARITY_EMOJI.get(rarity, "🌈") if rarity else "🌈"
    om = f"<a href='tg://user?id={user_obj.id}'>{user_obj.first_name}</a>"
    oh = f" (@{user_obj.username})" if getattr(user_obj, "username", None) else ""
    caption = (
        "╔══════════════════════════════╗\n"
        "║   🌑  <b>ARMY</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👤 <b>Owner:</b> {om}{oh}\n"
        f"🆔 <b>User ID:</b> <code>{user_obj.id}</code>\n"
        f"🔍 <b>Filter:</b> {rf} {fl}\n"
        f"🌸 <b>Total:</b> {total}\n"
        f"📄 <b>Page:</b> {page+1}/{total_pages}\n\n"
        f"📊 {g_chart}\n📊 {r_chart}\n\n"
        "👇 <i>Kisi pe tap karo:</i>"
    )
    wait = await context.bot.send_message(chat_id, "⏳ <b>Loading...</b>", parse_mode="HTML")
    if IMAGE_SUPPORT and page_waifus:
        try:
            buf = await create_army_collage(context, page_waifus, max_count=COLLAGE_PER_PAGE)
            if buf:
                try: await wait.delete()
                except: pass
                btn_waifus = page_waifus[:BUTTONS_PER_PAGE]
                await context.bot.send_photo(chat_id=chat_id, photo=buf, caption=caption, parse_mode="HTML",
                    reply_markup=kb_army_paginated(btn_waifus, user_obj.id, page, total_pages, rarity))
                return
        except Exception as e: log.error(f"Collage fail: {e}")
    try: await wait.delete()
    except: pass
    btn_waifus = page_waifus[:BUTTONS_PER_PAGE]
    await context.bot.send_message(chat_id, caption, parse_mode="HTML",
        reply_markup=kb_army_paginated(btn_waifus, user_obj.id, page, total_pages, rarity))


async def cmd_army(update, context):
    u = update.effective_user
    ok, reason = await is_joined(context.bot, u.id)
    if not ok:
        await update.message.reply_text(f"🔒 <b>Pehle dono channels join karo!</b>\n\n⚠️ {reason}", parse_mode="HTML", reply_markup=kb_join())
        return
    total = count_user_waifus(u.id)
    if total == 0:
        await update.message.reply_text("🌑 <b>Tera Army khaali hai.</b>\n\n👉 Group me 100 msg ka wait kar\n👉 Spawn pe <b>/arise &lt;name&gt;</b> chala", parse_mode="HTML")
        return
    await show_army_page(update.message.chat_id, context, u, rarity=None, page=0)


async def cmd_search(update, context):
    u = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "📌 <b>Usage:</b> <code>/search &lt;name&gt;</code>\n"
            "📌 <b>Example:</b> <code>/search Rem</code>\n\n"
            "<i>Ye bot ki poori database me search karega — tumhari army me ho ya na ho.</i>",
            parse_mode="HTML"
        )
        return
    ok, reason = await is_joined(context.bot, u.id)
    if not ok:
        await update.message.reply_text(f"🔒 <b>Pehle dono channels join karo!</b>\n\n⚠️ {reason}", parse_mode="HTML", reply_markup=kb_join())
        return
    query = " ".join(context.args).strip().lower()
    all_waifus = get_all_waifus()
    if not all_waifus:
        await update.message.reply_text("🌑 <b>Bot me abhi koi character add nahi hua.</b>", parse_mode="HTML")
        return
    matches = [w for w in all_waifus if query in (w.get("name") or "").lower()]
    if not matches:
        await update.message.reply_text(f"❌ <b>No match found:</b> <code>{query}</code>", parse_mode="HTML")
        return
    user_waifus = get_user_waifus(u.id)
    owned_ids = {w["waifu_id"] for w in user_waifus}

    if len(matches) == 1:
        w = matches[0]
        rarity = w.get("rarity", "Common")
        re = RARITY_EMOJI.get(rarity, "⚪")
        gender = w.get("gender", "waifu")
        ge = gender_emoji(gender)
        glabel = gender_label(gender)
        wid = w["id"]
        owned = wid in owned_ids
        status_line = "✅ <b>Ye tumhari army me hai!</b>" if owned else "❌ <b>Ye tumhari army me nahi hai.</b>"
        total_owners = count_waifu_owners(wid)
        cap = (
            "╔══════════════════════════════╗\n"
            "║   🔍  <b>FOUND!</b>   ║\n"
            "╚══════════════════════════════╝\n\n"
            f"{ge} <b>Type:</b> {glabel}\n"
            f"🌸 <b>Name:</b> {w.get('name', 'Character')}\n"
            f"⭐ <b>Rarity:</b> {re} {rarity}\n"
            f"🆔 <b>Bot ID:</b> <code>{wid}</code>\n"
            f"👥 <b>Owners:</b> {total_owners} log\n\n"
            f"{status_line}\n\n"
            f"📖 <i>{w.get('description', '')}</i>"
        )
        action_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Open Army", callback_data="army_filter:all:0" if owned else "primary")],
            [InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME}")],
        ])
        photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
        try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML", reply_markup=action_kb)
        except: await update.message.reply_text(cap, parse_mode="HTML", reply_markup=action_kb)
        return

    txt = (
        "╔══════════════════════════════╗\n"
        "║   🔍  <b>MULTIPLE MATCHES</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🔍 Query: <code>{query}</code>\n"
        f"🌸 Found: <b>{len(matches)}</b>\n"
        f"<i>(✅ = tumhari army me hai)</i>\n\n"
        "👇 Kisi pe tap karo:"
    )
    buttons = []
    row = []
    for w in matches[:30]:
        name = w.get("name") or "Character"
        re = RARITY_EMOJI.get(w.get("rarity", ""), "⚪")
        ge = gender_emoji(w.get("gender", "waifu"))
        owned_mark = "✅ " if w["id"] in owned_ids else ""
        label = f"{owned_mark}{ge} {re} {name[:10]}"
        row.append(InlineKeyboardButton(label, callback_data=f"search_det:{w['id']}",
            style="success" if w["id"] in owned_ids else "primary"))
        if len(row) == 2:
            buttons.append(row); row = []
    if row: buttons.append(row)
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════ GIFT COMMAND ═══════════
async def cmd_gift(update, context):
    u = update.effective_user

    if len(context.args) < 2:
        await update.message.reply_text(
            "╔══════════════════════════════╗\n"
            "║   🎁  <b>GIFT A CHARACTER</b>   ║\n"
            "╚══════════════════════════════╝\n\n"
            "📌 <b>Usage:</b> <code>/gift &lt;user_id&gt; &lt;waifu_id&gt;</code>\n\n"
            "📌 <b>Example:</b>\n"
            "<code>/gift 8344335776 5</code>\n\n"
            "💡 <b>Kaise use kare:</b>\n"
            "▫️ <b>user_id</b> — jisko dena hai uska Telegram ID\n"
            "▫️ <b>waifu_id</b> — bot ID (jo /search ya /check me dikhti hai)\n\n"
            "<i>Pehle apne character ki Bot ID pata karo /search se.</i>",
            parse_mode="HTML"
        )
        return

    try:
        target_id = int(context.args[0])
        waifu_bot_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Valid numbers daal bhai.")
        return

    if target_id == u.id:
        await update.message.reply_text(
            "😐 <b>Khud ko gift?</b>\n<i>Behes ki baat hai...</i>",
            parse_mode="HTML"
        )
        return

    target_waifu = get_waifu(waifu_bot_id)
    if not target_waifu:
        await update.message.reply_text(
            f"❌ <b>Character ID {waifu_bot_id} nahi mili.</b>\n\n"
            f"<i>/search se dhundho sahi ID.</i>",
            parse_mode="HTML"
        )
        return

    giver_waifus = get_user_waifus(u.id)
    match = None
    for w in giver_waifus:
        if w["waifu_id"] == waifu_bot_id:
            match = w
            break

    if not match:
        await update.message.reply_text(
            f"❌ <b>Ye teri army me nahi hai!</b>\n\n"
            f"Character: <b>{target_waifu.get('name')}</b>\n"
            f"<i>Jo teri army me nahi hai, wo gift nahi kar sakta.</i>",
            parse_mode="HTML"
        )
        return

    give_waifu_to_user(target_id, waifu_bot_id)
    remove_user_waifu(match["uw_id"], u.id)

    rarity = target_waifu.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")
    gender = target_waifu.get("gender", "waifu")
    ge = gender_emoji(gender)
    name = target_waifu.get("name") or "Character"

    try:
        receiver = await context.bot.get_chat(target_id)
        receiver_name = receiver.first_name or f"User {target_id}"
    except Exception:
        receiver_name = f"User {target_id}"

    cap = (
        "╔══════════════════════════════╗\n"
        "║   🎁  <b>CHARACTER GIFTED!</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👤 <b>From:</b> {u.first_name}\n"
        f"🎯 <b>To:</b> {receiver_name}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{ge} <b>{name}</b>\n"
        f"⭐ Rarity: {re} <b>{rarity}</b>\n"
        f"🆔 ID: <code>{waifu_bot_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💫 <i>Character successfully transfer ho gayi!</i>"
    )

    photo = target_waifu["image_url"] if target_waifu["image_source"] == "url" else target_waifu["file_id"]
    try:
        await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(cap, parse_mode="HTML")

    try:
        await context.bot.send_message(
            target_id,
            f"🎁 <b>Tujhe ek character mili!</b>\n\n"
            f"👤 Giver: {u.first_name}\n"
            f"{ge} <b>{name}</b> ({re} {rarity})\n"
            f"🆔 <code>{waifu_bot_id}</code>\n\n"
            f"👇 <i>/army se check kar.</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass


async def cmd_roast(update, context):
    target_name = None; target_id = None
    if update.message.reply_to_message:
        t_user = update.message.reply_to_message.from_user
        target_name = t_user.first_name; target_id = t_user.id
    elif context.args:
        arg = " ".join(context.args).strip()
        target_name = arg[1:] if arg.startswith("@") else arg
    else:
        await update.message.reply_text("📌 Reply karke <code>/roast</code> ya <code>/roast @username</code>", parse_mode="HTML")
        return
    if target_id and target_id == update.effective_user.id:
        await update.message.reply_text("😐 <b>Khud ko roast?</b>\nThoda self-respect rakh bhai.", parse_mode="HTML")
        return
    roast_text = random.choice(ROAST_TEMPLATES).format(name=f"<b>{target_name}</b>")
    fire = "🔥" * random.randint(3, 6)
    ending = random.choice(ROAST_ENDINGS)
    txt = f"{fire}\n\n<b>🎯 TARGET:</b> {target_name}\n\n▫️ {roast_text}\n\n{ending}"
    if target_id:
        mention = f"<a href='tg://user?id={target_id}'>🎯</a>"
        await update.message.reply_text(f"{mention} {txt}", parse_mode="HTML")
    else:
        await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_stats(update, context):
    u = update.effective_user
    total = count_user_waifus(u.id)
    if total == 0:
        await update.message.reply_text("📊 <b>Teri stats khaali hai.</b>\n\nPehle grab kar <code>/arise &lt;name&gt;</code> se.", parse_mode="HTML")
        return
    rarity_counts = get_user_rarity_counts(u.id)
    gender_counts = get_user_gender_counts(u.id)
    txt = (
        "╔══════════════════════════════╗\n"
        "║   📊  <b>MY STATS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👤 <b>Hunter:</b> {u.first_name}\n"
        f"🆔 <b>User ID:</b> <code>{u.id}</code>\n"
        f"🌸 <b>Total Grabbed:</b> {total}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>🌸 GENDER BREAKDOWN</b>\n\n"
    )
    w_count = gender_counts.get("waifu", 0); h_count = gender_counts.get("husbando", 0)
    wpct = int((w_count / total) * 100) if total else 0
    hpct = int((h_count / total) * 100) if total else 0
    wbar = "█" * int(wpct / 5) + "░" * (20 - int(wpct / 5))
    hbar = "█" * int(hpct / 5) + "░" * (20 - int(hpct / 5))
    txt += f"🌸 <b>Waifu</b>\n   <code>{wbar}</code> <b>{w_count}</b> ({wpct}%)\n\n"
    txt += f"🗡️ <b>Husbando</b>\n   <code>{hbar}</code> <b>{h_count}</b> ({hpct}%)\n\n"
    txt += "━━━━━━━━━━━━━━━━━━━━━━\n<b>📈 RARITY CHART</b>\n\n"
    for rar in RARITY_ORDER:
        count = rarity_counts.get(rar, 0)
        if count > 0:
            pct = int((count / total) * 100)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            re = RARITY_EMOJI.get(rar, "⚪")
            txt += f"{re} <b>{rar}</b>\n   <code>{bar}</code> <b>{count}</b> ({pct}%)\n\n"
    txt += "━━━━━━━━━━━━━━━━━━━━━━\n💫 <i>\"Collection badhao!\"</i>"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_status(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin/owner.")
        return
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM waifus WHERE active=1")
        total = c.fetchone()[0]
    if total == 0:
        await update.message.reply_text("📭 Koi character add nahi hua abhi.")
        return
    rarity_counts = get_all_rarity_counts(); gender_counts = get_all_gender_counts()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_waifus")
        total_grabbed = c.fetchone()[0]
    txt = (
        "╔══════════════════════════════╗\n"
        "║   🗄️  <b>CHARACTER STATUS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🌸 <b>Total Added:</b> {total}\n"
        f"🎯 <b>Total Grabbed:</b> {total_grabbed}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n<b>📊 RARITY BREAKDOWN</b>\n\n"
    )
    for rar in RARITY_ORDER:
        count = rarity_counts.get(rar, 0)
        if count > 0:
            pct = int((count / total) * 100)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            re = RARITY_EMOJI.get(rar, "⚪")
            txt += f"{re} <b>{rar}</b>\n   <code>{bar}</code> <b>{count}</b> ({pct}%)\n\n"
    txt += "━━━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_check(update, context):
    if not context.args:
        await update.message.reply_text("📌 Usage: <code>/check &lt;id&gt;</code>", parse_mode="HTML")
        return
    try: wid = int(context.args[0])
    except: await update.message.reply_text("❌ Valid ID daal."); return
    w = get_waifu(wid)
    if not w:
        await update.message.reply_text(f"❌ ID {wid} nahi mili."); return
    owner_count = count_waifu_owners(wid)
    rarity = w.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")
    gender = w.get("gender", "waifu")
    ge = gender_emoji(gender)
    cap = (
        "╔══════════════════════════════╗\n"
        "║   🔍  <b>INFO</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"{ge} Type: <b>{gender_label(gender)}</b>\n"
        f"🌸 <b>{w.get('name', 'Unknown')}</b>\n"
        f"🆔 <b>Bot ID:</b> <code>{wid}</code>\n"
        f"⭐ Rarity: {re} <b>{rarity}</b>\n"
        f"👥 Owners: <b>{owner_count}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <i>{w.get('description', '')}</i>\n\n"
        f"<i>💡 /gift se isse kisi ko gift kar sakte ho</i>"
    )
    photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
    try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except: await update.message.reply_text(cap, parse_mode="HTML")


async def cmd_rank(update, context):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, COUNT(*) as cnt FROM user_waifus GROUP BY user_id ORDER BY cnt DESC LIMIT 10")
        rows = c.fetchall()
    if not rows:
        await update.message.reply_text("📭 Abhi koi collection nahi hai."); return
    txt = "╔══════════════════════════════╗\n║   🏆  <b>TOP COLLECTORS</b>   ║\n╚══════════════════════════════╝\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        try:
            user = await context.bot.get_chat(r["user_id"]); name = user.first_name or "Unknown"
        except: name = f"User {r['user_id']}"
        prefix = medals[i] if i < 3 else f"<b>{i+1}.</b>"
        txt += f"{prefix} {name} — <b>{r['cnt']}</b> 🌸\n"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_rarity(update, context):
    counts = get_all_rarity_counts()
    if not counts:
        await update.message.reply_text("📭 Abhi koi character nahi hai."); return
    total = sum(counts.values())
    max_rarity = max(counts, key=counts.get)
    txt = "╔══════════════════════════════╗\n║   💎  <b>RARITY STATS</b>   ║\n╚══════════════════════════════╝\n\n<i>\"Har rarity ka apna charm.\"</i>\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for rar in RARITY_ORDER:
        if rar in counts:
            re = RARITY_EMOJI.get(rar, "⚪")
            count = counts[rar]
            pct = int((count / total) * 100)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            mark = " 👑" if rar == max_rarity else ""
            txt += f"{re} <b>{rar}</b>{mark}\n   <code>{bar}</code> <b>{count}</b> ({pct}%)\n\n"
    txt += f"━━━━━━━━━━━━━━━━━━━━━━\n🌸 <b>Total:</b> {total}\n👑 <b>Most Common:</b> {RARITY_EMOJI.get(max_rarity, '⚪')} <b>{max_rarity}</b>"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_global(update, context):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT chat_id) FROM group_counters"); groups = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM players"); users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM waifus WHERE active=1"); waifus = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM user_waifus"); collected = c.fetchone()[0]
    txt = (
        "╔══════════════════════════════╗\n"
        "║   🌍  <b>GLOBAL STATS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"💬 <b>Groups:</b> {groups}\n"
        f"👥 <b>Players:</b> {users}\n"
        f"🌸 <b>Total Characters:</b> {waifus}\n"
        f"📦 <b>Collected:</b> {collected}"
    )
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_ping(update, context):
    start = time.time()
    msg = await update.message.reply_text("🏓 <b>Pinging...</b>", parse_mode="HTML")
    end = time.time()
    latency = int((end - start) * 1000)
    uptime_sec = int(time.time() - BOT_START_TIME)
    hours, rem = divmod(uptime_sec, 3600); mins, secs = divmod(rem, 60)
    if hours > 0: uptime_str = f"{hours}h {mins}m"
    elif mins > 0: uptime_str = f"{mins}m {secs}s"
    else: uptime_str = f"{secs}s"
    quality = "🟢 Excellent" if latency < 300 else ("🟡 Good" if latency < 800 else "🔴 Slow")
    txt = (
        "╔══════════════════════════════╗\n"
        "║   🏓  <b>PONG!</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"⚡ <b>Latency:</b> <code>{latency} ms</code>\n"
        f"📶 <b>Quality:</b> {quality}\n"
        f"⏱️ <b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"🤖 <b>Status:</b> ✅ Online"
    )
    await msg.edit_text(txt, parse_mode="HTML")


ASK_PHOTO, ASK_NAME, ASK_GENDER, ASK_RARITY, ASK_DESC = range(5)


async def addshadow_start(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin/owner."); return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("📸 <b>Pic bhej</b>\n\n<i>(HD image bhejo — bada dikhega!)</i>", parse_mode="HTML")
    return ASK_PHOTO


async def addshadow_photo(update, context):
    fid = url = None
    if update.message.photo: fid = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"): fid = update.message.document.file_id
    elif update.message.text and update.message.text.startswith(("http://", "https://")): url = update.message.text.strip()
    else:
        await update.message.reply_text("❌ Photo ya URL bhej."); return ASK_PHOTO
    context.user_data["file_id"] = fid; context.user_data["image_url"] = url
    await update.message.reply_text("📝 <b>Name bhej</b>", parse_mode="HTML")
    return ASK_NAME


async def addshadow_name(update, context):
    if not update.message.text:
        await update.message.reply_text("❌ Text bhej."); return ASK_NAME
    name = update.message.text.strip()
    if not name or len(name) > 60:
        await update.message.reply_text("❌ Name 1-60 chars. Dobara:"); return ASK_NAME
    context.user_data["name"] = name
    await update.message.reply_text("🌸 <b>Kya hai ye?</b>\n\n<i>Waifu ya Husbando?</i>", parse_mode="HTML", reply_markup=kb_gender())
    return ASK_GENDER


async def addshadow_gender_callback(update, context):
    q = update.callback_query; await q.answer()
    gender = q.data.split(":")[1]
    context.user_data["gender"] = gender
    await q.edit_message_text(f"{gender_emoji(gender)} <b>Type:</b> {gender_label(gender)}\n\n⭐ <b>Rarity chuno (33 options):</b>", parse_mode="HTML", reply_markup=kb_rarity())
    return ASK_RARITY


async def addshadow_gender_text(update, context):
    if not update.message.text: return ASK_GENDER
    g = update.message.text.strip().lower()
    if g not in ("waifu", "husbando"):
        await update.message.reply_text("❌ <b>Sirf 'waifu' ya 'husbando' likh.</b>"); return ASK_GENDER
    context.user_data["gender"] = g
    await update.message.reply_text(f"{gender_emoji(g)} <b>Type:</b> {gender_label(g)}\n\n⭐ <b>Rarity chuno (33 options):</b>", parse_mode="HTML", reply_markup=kb_rarity())
    return ASK_RARITY


async def addshadow_rarity_callback(update, context):
    q = update.callback_query; await q.answer()
    rarity = q.data.split(":", 1)[1]
    if rarity not in RARITY_EMOJI:
        await q.answer("❌ Invalid!", show_alert=True); return ASK_RARITY
    context.user_data["rarity"] = rarity
    await q.edit_message_text(f"⭐ Rarity: {RARITY_EMOJI.get(rarity, '⚪')} <b>{rarity}</b>\n\n📖 Ab <b>Description bhej</b>:\n\n<i>⚠️ Description me naam zaroor likho!</i>", parse_mode="HTML")
    return ASK_DESC


async def addshadow_rarity_text(update, context):
    if not update.message.text: return ASK_RARITY
    r = update.message.text.strip().title()
    if r not in RARITY_EMOJI:
        found = None
        for k in RARITY_EMOJI.keys():
            if k.lower() == r.lower(): found = k; break
        if not found:
            await update.message.reply_text("❌ <b>Invalid rarity.</b> Button se choose karo."); return ASK_RARITY
        r = found
    context.user_data["rarity"] = r
    await update.message.reply_text(f"⭐ Rarity: {RARITY_EMOJI.get(r, '⚪')} <b>{r}</b>\n\n📖 Ab <b>Description bhej</b>:", parse_mode="HTML")
    return ASK_DESC


async def addshadow_desc(update, context):
    if not update.message.text:
        await update.message.reply_text("❌ Text bhej."); return ASK_DESC
    desc = update.message.text.strip()
    if not desc or len(desc) > 500:
        await update.message.reply_text("❌ Description 1-500 chars. Dobara:"); return ASK_DESC
    fid = context.user_data.get("file_id"); url = context.user_data.get("image_url")
    name = context.user_data.get("name", ""); gender = context.user_data.get("gender", "waifu")
    rarity = context.user_data.get("rarity", "Common")
    mid = add_waifu(name=name, gender=gender, rarity=rarity, file_id=fid, image_url=url, description=desc)
    photo = url or fid
    re = RARITY_EMOJI.get(rarity, "⚪"); em = gender_emoji(gender)
    cap = (
        "╔══════════════════════════════╗\n"
        "║   ✅  <b>ADDED SUCCESSFULLY</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🆔 ID: <code>{mid}</code>\n"
        f"{em} Type: <b>{gender_label(gender)}</b>\n"
        f"🌸 Name: <b>{name}</b>\n"
        f"⭐ Rarity: {re} <b>{rarity}</b>\n"
        f"📖 <i>{desc}</i>"
    )
    try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except: await update.message.reply_text(cap, parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END


async def addshadow_cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def cmd_waifulist(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin/owner."); return
    ws = get_all_waifus()
    if not ws:
        await update.message.reply_text("📭 Koi character nahi."); return
    txt = f"🌸 <b>Characters ({len(ws)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for w in ws[:30]:
        re = RARITY_EMOJI.get(w.get("rarity", "Common"), "⚪")
        ge = gender_emoji(w.get("gender", "waifu"))
        name = w.get("name") or "Unknown"
        txt += f"🆔 <code>{w['id']}</code> {ge}{re} — {name}\n"
    if len(ws) > 30: txt += f"\n<i>...aur {len(ws)-30}</i>"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_delwaifu(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Sirf admin/owner."); return
    if not context.args:
        await update.message.reply_text("📌 /delwaifu <id>"); return
    try: wid = int(context.args[0])
    except: await update.message.reply_text("❌ Valid ID."); return
    w = get_waifu(wid)
    if not w:
        await update.message.reply_text(f"❌ ID {wid} nahi mili."); return
    delete_waifu(wid)
    await update.message.reply_text(f"✅ Deleted ID {wid}")


async def cmd_addadmin(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner."); return
    target_id = target_name = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name
    elif context.args:
        try: target_id = int(context.args[0]); target_name = f"User {target_id}"
        except: await update.message.reply_text("❌ Valid user ID daal ya reply kar."); return
    else:
        await update.message.reply_text("📌 Reply karke <code>/addadmin</code> ya ID daal.", parse_mode="HTML"); return
    if target_id == OWNER_ID:
        await update.message.reply_text("❌ Owner already admin hai."); return
    if add_admin(target_id, update.effective_user.id):
        await update.message.reply_text(f"✅ <b>Admin Added!</b>\n\n👤 {target_name}\n🆔 <code>{target_id}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ Ye already admin hai.")


async def cmd_removeadmin(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner."); return
    target_id = target_name = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name
    elif context.args:
        try: target_id = int(context.args[0]); target_name = f"User {target_id}"
        except: await update.message.reply_text("❌ Valid user ID daal."); return
    else:
        await update.message.reply_text("📌 Reply karke <code>/removeadmin</code> ya ID daal.", parse_mode="HTML"); return
    if remove_admin(target_id):
        await update.message.reply_text(f"✅ <b>Admin Removed</b>\n👤 {target_name}", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ Ye admin nahi hai.")


async def cmd_admins(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Sirf owner."); return
    admins = get_all_admins()
    txt = "╔══════════════════════════════╗\n║   👑  <b>ADMIN LIST</b>   ║\n╚══════════════════════════════╝\n\n"
    txt += f"👤 Owner: <code>{OWNER_ID}</code>\n\n"
    if not admins: txt += "📭 <i>Koi aur admin nahi hai.</i>"
    else:
        txt += f"<b>Total: {len(admins)}</b>\n\n"
        for a in admins:
            try:
                user = await context.bot.get_chat(a["user_id"]); name = user.first_name
            except: name = "Unknown"
            txt += f"▫️ {name} — <code>{a['user_id']}</code>\n"
    await update.message.reply_text(txt, parse_mode="HTML")


async def track_message(update, context):
    if update.effective_chat.type not in ("group", "supergroup"): return
    if update.effective_user and update.effective_user.is_bot: return
    chat_id = update.effective_chat.id
    if get_active_spawn(chat_id): return
    count = incr_msg(chat_id)
    if count >= SPAWN_MESSAGE_THRESHOLD:
        reset_msg(chat_id)
        await spawn_waifu(chat_id, context)


async def spawn_waifu(chat_id, context):
    waifu = get_random_waifu()
    if not waifu:
        log.warning("No characters in DB"); return
    exp = (datetime.now(timezone.utc) + timedelta(seconds=SPAWN_EXPIRY_SECONDS)).isoformat()
    sid = create_spawn(chat_id, waifu["id"], exp)
    rarity = waifu.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")
    gender = waifu.get("gender", "waifu")
    em = gender_emoji(gender)
    title = "🗡️  <b>A HUSBANDO HAS APPEARED</b>  🗡️" if gender == "husbando" else "🌸  <b>A WAIFU HAS APPEARED</b>  🌸"
    cap = (
        "╔══════════════════════════════╗\n"
        f"║   {title}   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"{em} Type: <b>{gender_label(gender)}</b>\n"
        f"⭐ Rarity: {re} <b>{rarity}</b>\n\n"
        f"📖 <i>{waifu.get('description', '')}</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>Naam dhundho, phir likho:</b>\n"
        "<code>/arise &lt;name&gt;</code>\n\n"
        f"⏰ <b>{SPAWN_EXPIRY_SECONDS // 60} min</b> me gayab!"
    )
    photo = waifu["image_url"] if waifu["image_source"] == "url" else waifu["file_id"]
    try:
        msg = await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=cap, parse_mode="HTML")
        set_spawn_message(sid, msg.message_id)
        log.info(f"Spawn {gender} {waifu['id']} in {chat_id}")
    except Exception as e: log.error(f"Spawn fail: {e}")


async def expire_job(context):
    n = expire_spawns()
    if n: log.info(f"Expired {n} spawns")


async def callback_router(update, context):
    q = update.callback_query; await q.answer()
    data = q.data or ""

    if data == "check_join":
        ok, reason = await is_joined(context.bot, q.from_user.id)
        if ok:
            await q.answer("✅ Verified!", show_alert=True)
            try: await q.edit_message_text("🟢 <b>Verified!</b> ✅\n\nAb /army chalao!", parse_mode="HTML")
            except: pass
        else: await q.answer(f"❌ {reason}", show_alert=True)
        return

    if data.startswith("army_page:"):
        page = int(data.split(":")[1])
        try: await q.message.delete()
        except: pass
        await show_army_page(q.message.chat_id, context, q.from_user, rarity=None, page=page)
        return

    if data.startswith("army_filter:"):
        parts = data.split(":")
        rarity = parts[1] if parts[1] != "all" else None
        page = int(parts[2]) if len(parts) > 2 else 0
        try: await q.message.delete()
        except: pass
        await show_army_page(q.message.chat_id, context, q.from_user, rarity=rarity, page=page)
        return

    if data.startswith("search_det:"):
        wid = int(data.split(":")[1])
        w = get_waifu(wid)
        if not w:
            await q.answer("❌ Not found!", show_alert=True); return
        rarity = w.get("rarity", "Common")
        re = RARITY_EMOJI.get(rarity, "⚪")
        gender = w.get("gender", "waifu")
        ge = gender_emoji(gender); glabel = gender_label(gender)
        name = w.get("name") or "Character"
        user_waifus = get_user_waifus(q.from_user.id)
        owned_ids = {x["waifu_id"] for x in user_waifus}
        owned = wid in owned_ids
        status_line = "✅ <b>Ye tumhari army me hai!</b>" if owned else "❌ <b>Ye tumhari army me nahi hai.</b>"
        total_owners = count_waifu_owners(wid)
        cap = (
            "╔══════════════════════════════╗\n"
            "║   🌸  <b>CHARACTER DETAIL</b>   ║\n"
            "╚══════════════════════════════╝\n\n"
            f"{ge} <b>Type:</b> {glabel}\n"
            f"🌸 <b>Name:</b> {name}\n"
            f"⭐ <b>Rarity:</b> {re} {rarity}\n"
            f"🆔 <b>Bot ID:</b> <code>{wid}</code>\n"
            f"👥 <b>Owners:</b> {total_owners} log\n\n"
            f"{status_line}\n\n"
            f"📖 <b>Description:</b>\n"
            f"<i>{w.get('description', '')}</i>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Army", callback_data="army_filter:all:0")],
        ])
        photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
        try: await q.message.delete()
        except: pass
        try: await context.bot.send_photo(q.message.chat_id, photo, caption=cap, parse_mode="HTML", reply_markup=kb)
        except: await context.bot.send_message(q.message.chat_id, cap, parse_mode="HTML", reply_markup=kb)
        return

    if data.startswith("army_det:"):
        parts = data.split(":")
        uw_id = int(parts[1])
        w = get_user_waifu_detail(uw_id, q.from_user.id)
        if not w:
            await q.answer("❌ Ye teri nahi hai!", show_alert=True); return
        rarity = w.get("rarity", "Common")
        re = RARITY_EMOJI.get(rarity, "⚪")
        gender = w.get("gender", "waifu")
        ge = gender_emoji(gender)
        name = w.get("name") or "Character"
        wid = w["waifu_id"]
        cap = (
            "╔══════════════════════════════╗\n"
            "║   🌸  <b>CHARACTER DETAIL</b>   ║\n"
            "╚══════════════════════════════╝\n\n"
            f"{ge} <b>Type:</b> {gender_label(gender)}\n"
            f"🌸 <b>Name:</b> {name}\n"
            f"⭐ <b>Rarity:</b> {re} {rarity}\n"
            f"🆔 <b>Bot ID:</b> <code>{wid}</code>\n"
            f"📖 <b>Description:</b>\n"
            f"<i>{w.get('description', '')}</i>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>/gift &lt;user_id&gt; {wid} se gift kar sakte ho</i>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="army_filter:all:0")],
        ])
        photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
        try: await q.message.delete()
        except: pass
        try: await context.bot.send_photo(q.message.chat_id, photo, caption=cap, parse_mode="HTML", reply_markup=kb)
        except: await context.bot.send_message(q.message.chat_id, cap, parse_mode="HTML", reply_markup=kb)
        return

    if data == "army_search_tip":
        try: await q.message.delete()
        except: pass
        await context.bot.send_message(q.message.chat_id,
            "╔══════════════════════════════╗\n"
            "║   🔍  <b>SEARCH TIPS</b>   ║\n"
            "╚══════════════════════════════╝\n\n"
            "📌 <b>Command:</b> <code>/search &lt;name&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "▫️ <code>/search Rem</code>\n"
            "▫️ <code>/search re</code>\n"
            "▫️ <code>/search sasuke</code>\n\n"
            "💡 <b>Global Search</b> — poori database me search!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Army", callback_data="army_filter:all:0")]
            ]))
        return

    if data == "army_stats_redirect":
        await q.answer("📊 /stats chalao!", show_alert=True); return
    if data == "army_noop": return
    if data == "army_close":
        try: await q.message.delete()
        except: pass
        return
    log.warning(f"Unhandled callback: {data}")


def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing in .env"); return
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("arise", cmd_arise))
    app.add_handler(CommandHandler("viewtime", cmd_viewtime))
    app.add_handler(CommandHandler("gate", cmd_viewtime))
    app.add_handler(CommandHandler("army", cmd_army))
    app.add_handler(CommandHandler("myshadow", cmd_army))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("gift", cmd_gift))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("roast", cmd_roast))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("rarity", cmd_rarity))
    app.add_handler(CommandHandler("global", cmd_global))

    app.add_handler(CommandHandler("ohelp", cmd_ohelp))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("waifulist", cmd_waifulist))
    app.add_handler(CommandHandler("delwaifu", cmd_delwaifu))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))
    app.add_handler(CommandHandler("admins", cmd_admins))

    addshadow_conv = ConversationHandler(
        entry_points=[CommandHandler("addshadow", addshadow_start)],
        states={
            ASK_PHOTO:  [MessageHandler(filters.PHOTO | filters.Document.IMAGE | filters.TEXT, addshadow_photo)],
            ASK_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_name)],
            ASK_GENDER: [CallbackQueryHandler(addshadow_gender_callback, pattern=r"^gender:"),
                          MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_gender_text)],
            ASK_RARITY: [CallbackQueryHandler(addshadow_rarity_callback, pattern=r"^rarity:"),
                          MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_rarity_text)],
            ASK_DESC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_desc)],
        },
        fallbacks=[CommandHandler("cancel", addshadow_cancel)],
        per_user=True, per_chat=False,
    )
    app.add_handler(addshadow_conv)
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.Sticker.ALL) & ~filters.COMMAND, track_message), group=1)

    if app.job_queue:
        app.job_queue.run_repeating(expire_job, interval=30, first=10)

    log.info("🌸 Waifu Bot v10.3 starting...")
    threading.Thread(target=start_render_health_server, daemon=True).start()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()