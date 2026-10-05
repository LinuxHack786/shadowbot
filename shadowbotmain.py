# bot.py — Waifu Collection Bot v16
# target: Python 3.11 · python-telegram-bot 21.x · Pillow 10+
import os, io, time, math, shutil, random, sqlite3, logging, threading
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

import httpx
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ConversationHandler, filters,
                          ContextTypes)

load_dotenv()

BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
BOT_USERNAME   = os.getenv("BOT_USERNAME", "YourBotUsername")
OWNER_ID       = int(os.getenv("OWNER_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "II_DEMONS_SHADOW_II")
SUPPORT_LINK   = "https://t.me/Demon_persnality"
SUPPORT_NAME   = "Demon Personality"
DB_PATH        = os.getenv("DB_PATH", "shadow.db")
LOG_LEVEL      = os.getenv("LOG_LEVEL", "INFO")
PORT           = int(os.getenv("PORT", "8080"))

BOT_START_TIME = time.time()
START_PHOTO    = "https://i.ibb.co/DHZbxsZ9/IMG-20260929-013718.jpg"

REQUIRED_CHANNELS = [
    ("@Abyss_diemension_Animes", "https://t.me/Abyss_diemension_Animes"),
    ("@Abyss_kdrama_main_channel", "https://t.me/Abyss_kdrama_main_channel"),
]

SPAWN_MESSAGE_THRESHOLD = 100
SPAWN_EXPIRY_SECONDS    = 300

DAILY_COINS     = 100
WEEKLY_COINS    = 2000
DAILY_COOLDOWN  = timedelta(hours=24)
WEEKLY_COOLDOWN = timedelta(days=7)
CLAIM_COOLDOWN  = timedelta(hours=24)

BACKUP_DIR = "backups"
AMODE_SERIES_PER_PAGE = 5
AMODE_CHARS_PER_SERIES = 8

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("waifu_bot")


RARITY_EMOJI = {
    "Common":"⚪","Uncommon":"🟢","Rare":"🔵","Epic":"🟣","Legendary":"🟠","Mythic":"🔴",
    "Summer":"🌊","Valentine":"💖","Christmas":"🎄","Halloween":"🎃","Easter":"🐰",
    "New Year":"🎆","Sakura":"🌸","Winter":"❄️","Ecchi":"😈","Yandere":"🔪",
    "Tsundere":"💢","Neko":"🐱","Maid":"🎀","Fox":"🦊","Angel":"😇","Demon":"👺",
    "Vampire":"🧛","Ninja":"🥷","Divine":"✨","Shadow":"🌑","Eternal":"♾️",
    "Cosmic":"🌌","God":"🪬","Supreme":"👑","Secret":"🔒","Exclusive":"💎","Limited":"⏳",
}

RARITY_ORDER = [
    "Exclusive","Secret","Limited","Supreme","God","Cosmic","Eternal","Shadow","Divine",
    "Vampire","Ninja","Demon","Angel","Fox","Maid","Neko","Tsundere","Yandere","Ecchi",
    "Winter","Sakura","New Year","Easter","Halloween","Christmas","Valentine","Summer",
    "Mythic","Legendary","Epic","Rare","Uncommon","Common",
]

RARITY_PRICE = {
    "Common":500,"Uncommon":1000,"Rare":2000,"Epic":4000,"Legendary":8000,"Mythic":15000,
    "Summer":5000,"Valentine":5000,"Christmas":5000,"Halloween":5000,"Easter":5000,
    "New Year":5000,"Sakura":5000,"Winter":5000,
    "Ecchi":6000,"Yandere":6000,"Tsundere":6000,"Neko":6000,"Maid":6000,"Fox":6000,
    "Angel":6000,"Demon":6000,"Vampire":6000,"Ninja":6000,
    "Divine":25000,"Shadow":25000,"Eternal":25000,"Cosmic":25000,"God":25000,"Supreme":25000,
    "Secret":50000,"Exclusive":50000,"Limited":50000,
}

def rarity_price(r): return RARITY_PRICE.get(r, 1000)
def gender_emoji(g): return "🌸" if g == "waifu" else "🗡️"
def gender_label(g): return "Waifu" if g == "waifu" else "Husbando"


# ═══════════════ DB ═══════════════
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def _auto_backup():
    if not os.path.exists(DB_PATH): return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(BACKUP_DIR, f"shadow_{stamp}.db")
        shutil.copy2(DB_PATH, dst)
        log.info(f"Auto-backup: {dst}")
        files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("shadow_")])
        for f in files[:-10]:
            try: os.remove(os.path.join(BACKUP_DIR, f))
            except Exception: pass
    except Exception as e:
        log.warning(f"auto-backup skipped: {e}")


def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            coins INTEGER DEFAULT 0, last_daily TEXT, last_weekly TEXT, last_claim TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS waifus (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, gender TEXT DEFAULT 'waifu',
            rarity TEXT DEFAULT 'Common', series TEXT DEFAULT '', series_order INTEGER DEFAULT 0,
            file_id TEXT, image_url TEXT, image_source TEXT, description TEXT,
            created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_waifus (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            waifu_id INTEGER NOT NULL, grabbed_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS spawns (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER,
            waifu_id INTEGER NOT NULL, spawned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT, status TEXT DEFAULT 'active', grabbed_by INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS group_counters (
            chat_id INTEGER PRIMARY KEY, msg_count INTEGER DEFAULT 0,
            total_spawns INTEGER DEFAULT 0, last_spawn TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        for tbl, col, typ in [
            ("players","coins","INTEGER DEFAULT 0"),
            ("players","last_daily","TEXT"),
            ("players","last_weekly","TEXT"),
            ("players","last_claim","TEXT"),
            ("waifus","series","TEXT DEFAULT ''"),
            ("waifus","series_order","INTEGER DEFAULT 0"),
        ]:
            try: c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError: pass
        try: c.execute("UPDATE players SET coins=0 WHERE coins IS NULL")
        except Exception: pass
        try: c.execute("UPDATE waifus SET series='Unknown Series' WHERE series IS NULL OR series=''")
        except Exception: pass
        try: c.execute("UPDATE waifus SET series_order=id WHERE series_order IS NULL OR series_order=0")
        except Exception: pass
    log.info("DB initialized")


def _now(): return datetime.now(timezone.utc)

def _parse_dt(s):
    if not s: return None
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception: return None


def get_or_create_player(uid, username=None, first_name=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        row = c.fetchone()
        if row:
            c.execute("""UPDATE players SET username=COALESCE(?,username),
                        first_name=COALESCE(?,first_name) WHERE user_id=?""",
                      (username, first_name, uid))
            c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
            return dict(c.fetchone())
        c.execute("INSERT INTO players (user_id, username, first_name, coins) VALUES (?,?,?,0)",
                  (uid, username, first_name))
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        return dict(c.fetchone())


def add_coins(user_id, amount):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE players SET coins = COALESCE(coins, 0) + ? WHERE user_id=?",
                  (amount, user_id))
        if c.rowcount == 0:
            c.execute("INSERT INTO players (user_id, coins) VALUES (?,?)", (user_id, amount))


def get_coins(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COALESCE(coins, 0) AS c FROM players WHERE user_id=?", (user_id,))
        row = c.fetchone()
        return row["c"] if row else 0


def is_admin(uid):
    if uid == OWNER_ID: return True
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM admins WHERE user_id=?", (uid,))
        return c.fetchone() is not None


def add_admin(uid, added_by):
    with get_conn() as conn:
        try:
            conn.execute("INSERT INTO admins (user_id, added_by) VALUES (?,?)", (uid, added_by))
            return True
        except sqlite3.IntegrityError: return False


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


def next_series_order(series):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(series_order) AS m FROM waifus WHERE series=?", (series,))
        row = c.fetchone()
        m = row["m"] if row and row["m"] is not None else 0
        return m + 1


def add_waifu(name="", gender="waifu", rarity="Common", file_id=None, image_url=None,
              description="", series="Unknown Series", series_order=None):
    if series_order is None: series_order = next_series_order(series)
    src = "file_id" if file_id else "url"
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO waifus (name, gender, rarity, series, series_order,
            file_id, image_url, image_source, description) VALUES (?,?,?,?,?,?,?,?,?)""",
            (name, gender, rarity, series, series_order, file_id, image_url, src, description))
        return c.lastrowid


def get_random_waifu(weighted=False):
    with get_conn() as conn:
        c = conn.cursor()
        if weighted:
            c.execute("""SELECT * FROM waifus WHERE active=1
                ORDER BY (CASE rarity
                    WHEN 'Common' THEN 50 WHEN 'Uncommon' THEN 25
                    WHEN 'Rare' THEN 12 WHEN 'Epic' THEN 6
                    WHEN 'Legendary' THEN 3 WHEN 'Mythic' THEN 2
                    ELSE 1 END) * RANDOM() DESC LIMIT 1""")
        else:
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


def get_all_waifus_by_rarity(rarity):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM waifus WHERE active=1 AND rarity=? ORDER BY id DESC", (rarity,))
        return [dict(r) for r in c.fetchall()]


def get_all_series():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT DISTINCT series FROM waifus
            WHERE active=1 AND series IS NOT NULL AND series != ''
            ORDER BY series""")
        return [r["series"] for r in c.fetchall()]


def delete_waifu(wid):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE waifus SET active=0 WHERE id=?", (wid,))


def set_waifu_series(wid, series):
    order = next_series_order(series)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE waifus SET series=?, series_order=? WHERE id=?", (series, order, wid))
        return c.rowcount > 0


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
        c.execute("""SELECT uw.id AS uw_id, uw.grabbed_at, w.id AS waifu_id, w.name, w.gender,
            w.rarity, w.series, w.series_order, w.file_id, w.image_url, w.image_source, w.description
            FROM user_waifus uw JOIN waifus w ON uw.waifu_id = w.id
            WHERE uw.user_id=? ORDER BY uw.grabbed_at DESC""", (user_id,))
        return [dict(r) for r in c.fetchall()]


def get_user_waifus_grouped(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT w.id AS waifu_id, w.name, w.gender, w.rarity, w.series,
            w.series_order, w.file_id, w.image_url, w.image_source, w.description,
            COUNT(uw.id) AS user_dup_count
            FROM user_waifus uw JOIN waifus w ON uw.waifu_id = w.id
            WHERE uw.user_id=?
            GROUP BY w.id
            ORDER BY w.series, w.series_order, w.rarity""", (user_id,))
        rows = [dict(r) for r in c.fetchall()]
    grouped = {}
    for r in rows:
        s = (r.get("series") or "Unknown Series").strip() or "Unknown Series"
        grouped.setdefault(s, []).append(r)
    return grouped


def get_series_totals(user_id=None):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT series, COUNT(*) AS total FROM waifus WHERE active=1 GROUP BY series")
        totals = {(r["series"] or "Unknown Series"): r["total"] for r in c.fetchall()}
        if user_id is None:
            return {s: (0, t) for s, t in totals.items()}
        c.execute("""SELECT w.series, COUNT(DISTINCT w.id) AS owned
            FROM user_waifus uw JOIN waifus w ON uw.waifu_id = w.id
            WHERE uw.user_id=? GROUP BY w.series""", (user_id,))
        owned = {(r["series"] or "Unknown Series"): r["owned"] for r in c.fetchall()}
        return {s: (owned.get(s, 0), t) for s, t in totals.items()}


def count_user_waifus(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_waifus WHERE user_id=?", (user_id,))
        return c.fetchone()[0]


def count_user_dups(user_id, waifu_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM user_waifus WHERE user_id=? AND waifu_id=?",
                  (user_id, waifu_id))
        return c.fetchone()[0]


def get_user_rarity_counts(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT w.rarity, COUNT(*) AS cnt FROM user_waifus uw
            JOIN waifus w ON uw.waifu_id=w.id WHERE uw.user_id=? GROUP BY w.rarity""", (user_id,))
        return {r["rarity"]: r["cnt"] for r in c.fetchall()}


def get_user_gender_counts(user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT w.gender, COUNT(*) AS cnt FROM user_waifus uw
            JOIN waifus w ON uw.waifu_id=w.id WHERE uw.user_id=? GROUP BY w.gender""", (user_id,))
        return {r["gender"]: r["cnt"] for r in c.fetchall()}


def get_all_rarity_counts():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT rarity, COUNT(*) AS cnt FROM waifus WHERE active=1 GROUP BY rarity")
        return {r["rarity"]: r["cnt"] for r in c.fetchall()}


def remove_user_waifu(uw_id, user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM user_waifus WHERE id=? AND user_id=?", (uw_id, user_id))
        return c.rowcount > 0


def find_user_waifu(user_id, waifu_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id AS uw_id FROM user_waifus WHERE user_id=? AND waifu_id=? LIMIT 1",
                  (user_id, waifu_id))
        row = c.fetchone()
        return dict(row) if row else None


def create_spawn(chat_id, waifu_id, expires_at):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO spawns (chat_id, waifu_id, expires_at) VALUES (?,?,?)",
                  (chat_id, waifu_id, expires_at))
        return c.lastrowid


def set_spawn_message(sid, mid):
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


def try_grab_spawn(spawn_id, user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET status='grabbed', grabbed_by=? WHERE id=? AND status='active'",
                  (user_id, spawn_id))
        if c.rowcount != 1: return False
        c.execute("INSERT INTO user_waifus (user_id, waifu_id) SELECT ?, waifu_id FROM spawns WHERE id=?",
                  (user_id, spawn_id))
        return True


def expire_spawns():
    now = _now().isoformat()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE spawns SET status='expired' WHERE status='active' AND expires_at<?", (now,))
        return c.rowcount


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
            total_spawns=total_spawns+1, last_spawn=CURRENT_TIMESTAMP WHERE chat_id=?""", (chat_id,))


def get_group_stats(chat_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT msg_count, total_spawns FROM group_counters WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        return dict(row) if row else {"msg_count": 0, "total_spawns": 0}


# ═══════════════ RENDER ═══════════════
_FONT_CHAIN = {
    "bold":    ["DejaVuSans-Bold.ttf", "arialbd.ttf", "NotoSans-Bold.ttf",
                "LiberationSans-Bold.ttf", "FreeSansBold.ttf"],
    "regular": ["DejaVuSans.ttf", "arial.ttf", "NotoSans-Regular.ttf",
                "LiberationSans-Regular.ttf", "FreeSans.ttf"],
}
_font_cache = {}

def _font(kind, size):
    key = (kind, size)
    if key in _font_cache: return _font_cache[key]
    for name in _FONT_CHAIN.get(kind, _FONT_CHAIN["regular"]):
        try:
            f = ImageFont.truetype(name, size); _font_cache[key] = f; return f
        except Exception: continue
    f = ImageFont.load_default(); _font_cache[key] = f; return f

BG        = (16, 16, 22)
CARD_BG   = (28, 24, 20)
HEADER_BG = (34, 28, 44)
INFO_BG   = (24, 24, 34)
GOLD      = (212, 175, 110)
GOLD_DARK = (90, 70, 38)
TEXT      = (236, 236, 244)
DIM       = (160, 160, 175)
DIVIDER   = (72, 72, 88)


def _fit_cover(img, w, h):
    img = img.convert("RGB")
    iw, ih = img.size
    if iw == 0 or ih == 0:
        return Image.new("RGB", (w, h), (40, 40, 50))
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    return img.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h))


async def _fetch_image(client, context, row, w, h):
    try:
        if row.get("image_source") == "url" and row.get("image_url"):
            r = await client.get(row["image_url"], timeout=20)
            raw = r.content
        elif row.get("file_id"):
            tg_file = await context.bot.get_file(row["file_id"])
            raw = bytes(await tg_file.download_as_bytearray())
        else:
            raise ValueError("no source")
        return _fit_cover(Image.open(io.BytesIO(raw)), w, h)
    except Exception as e:
        log.error(f"img fetch fail: {e}")
        ph = Image.new("RGB", (w, h), (45, 45, 55))
        d = ImageDraw.Draw(ph)
        d.text((w // 2 - 10, h // 2 - 15), "?",
               fill=(180, 180, 190), font=_font("bold", max(14, w // 5)))
        return ph


def _divider(draw, x1, x2, y):
    for dx in range(x1, x2, 14):
        draw.line([(dx, y), (min(dx + 8, x2), y)], fill=DIVIDER, width=2)


def _layout_for_total(total):
    if total <= 30:   return 4,  300, 400, 52, 42, 4
    if total <= 80:   return 5,  260, 347, 48, 40, 4
    if total <= 200:  return 8,  220, 293, 44, 36, 3
    if total <= 500:  return 12, 190, 253, 42, 34, 3
    if total <= 1500: return 16, 170, 227, 40, 32, 3
    if total <= 5000: return 20, 150, 200, 38, 30, 2
    return 25, 130, 173, 36, 28, 2


async def render_harem(context, client, grouped, series_totals):
    total_chars = sum(len(v) for v in grouped.values())
    cols, cell_w, cell_h, header_h, info_h, gap = _layout_for_total(total_chars)
    width = cols * cell_w
    blocks = []
    total_h = 20
    for series, items in grouped.items():
        owned, total = series_totals.get(series, (len(items), len(items)))
        rows_needed = math.ceil(len(items) / cols)
        block_h = header_h + 6 + info_h + 6 + rows_needed * (cell_h + gap) + gap
        blocks.append((series, items, owned, total, rows_needed))
        total_h += block_h
    canvas = Image.new("RGB", (width, total_h), BG)
    draw = ImageDraw.Draw(canvas)
    f_head = _font("bold", max(14, header_h - 22))
    f_info = _font("bold", max(12, info_h - 18))
    y = 10
    for series, items, owned, total, rows_needed in blocks:
        draw.rectangle([0, y, width, y + header_h], fill=HEADER_BG)
        draw.text((16, y + (header_h - f_head.size) // 2 + 2),
                  f">>  {series}   ({owned}/{total})", fill=GOLD, font=f_head)
        y += header_h
        _divider(draw, 0, width, y + 3); y += 6
        feat = items[0]
        dup = feat.get("user_dup_count", 1)
        info = (f"#{feat.get('series_order', 0)}  |  {feat.get('rarity', '')}  |  "
                f"{feat.get('name', '')}  (x{dup})")
        draw.rectangle([0, y, width, y + info_h], fill=INFO_BG)
        draw.text((16, y + (info_h - f_info.size) // 2 + 2), info, fill=TEXT, font=f_info)
        y += info_h
        _divider(draw, 0, width, y + 3); y += 6
        for idx, row in enumerate(items):
            r = idx // cols; col = idx % cols
            x = col * cell_w; cy = y + r * (cell_h + gap)
            thumb = await _fetch_image(client, context, row, cell_w - 6, cell_h - 6)
            canvas.paste(thumb, (x + 3, cy + 3))
        y += rows_needed * (cell_h + gap) + gap
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=82, optimize=True)
    buf.seek(0)
    is_tall = canvas.height > 9500 or canvas.width > 9500
    return buf, is_tall


CARD_W     = 880
CARD_IMG_H = 1080
TOP_H      = 52
BANNER_H   = 74
ROW_H      = 50
ROWS       = 4
INFO_H     = ROWS * ROW_H + 30


async def render_detail(context, client, row, banner_name, dup_count, series_pair, bot_username):
    H = TOP_H + CARD_IMG_H + BANNER_H + INFO_H
    canvas = Image.new("RGB", (CARD_W, H), CARD_BG)
    draw = ImageDraw.Draw(canvas)
    f_top    = _font("regular", 22)
    f_banner = _font("bold", 34)
    f_info   = _font("bold", 26)
    draw.rectangle([0, 0, CARD_W, TOP_H], fill=(38, 34, 28))
    draw.text((20, 14), f"via @{bot_username}", fill=DIM, font=f_top)
    img = await _fetch_image(client, context, row, CARD_W, CARD_IMG_H)
    canvas.paste(img, (0, TOP_H))
    y = TOP_H + CARD_IMG_H
    draw.rectangle([0, y, CARD_W, y + BANNER_H], fill=GOLD_DARK)
    draw.text((22, y + 20), f"{banner_name}'s harem", fill=GOLD, font=f_banner)
    y += BANNER_H
    draw.rectangle([0, y, CARD_W, y + INFO_H], fill=(34, 30, 24))
    rows = [
        ("🍀", f"Name:  {row.get('name','')}  (x{dup_count})"),
        ("💙", f"Rarity:  {row.get('rarity','')}"),
        ("🏵️", f"Anime:  {row.get('series','')}  ({series_pair[0]}/{series_pair[1]})"),
        ("🆔", f"{row.get('waifu_id', row.get('id',''))}  -  Needed for trading/gifting"),
    ]
    for i, (emj, txt) in enumerate(rows):
        ry = y + 16 + i * ROW_H
        draw.text((22, ry), f"{emj}  {txt}", fill=TEXT, font=f_info)
    draw.rectangle([0, 0, CARD_W - 1, H - 1], outline=GOLD, width=3)
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=86, optimize=True)
    buf.seek(0)
    return buf


# ═══════════════ HEALTH ═══════════════
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            up = int(time.time() - BOT_START_TIME)
            self.wfile.write(f'{{"status":"ok","uptime":{up}}}'.encode())
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *a, **k): pass


def start_health_server():
    try:
        srv = HTTPServer(("0.0.0.0", PORT), _HealthHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        log.info(f"Health server on :{PORT}")
    except Exception as e:
        log.warning(f"health server skipped: {e}")


# ═══════════════ HELPERS ═══════════════
async def is_joined(bot, uid):
    for ch, _ in REQUIRED_CHANNELS:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status not in ("creator", "administrator", "member", "restricted"):
                return False, f"You have not joined {ch}"
        except Exception as e:
            log.error(f"force-join {ch}: {e}")
            return False, f"Bot is not admin in {ch}"
    return True, "OK"


def kb_join():
    rows = [[InlineKeyboardButton(f"📢 {ch}", url=url)] for ch, url in REQUIRED_CHANNELS]
    rows.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
    return InlineKeyboardMarkup(rows)


def kb_start():
    bot_link = f"https://t.me/{BOT_USERNAME}?startgroup=true"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}")],
        [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK)],
        [InlineKeyboardButton("➕ Add Me To Your GC", url=bot_link)],
    ])


# ═══════════════ TEXTS ═══════════════
START_CAPTION = (
    "╔══════════════════════════════╗\n"
    "║   🌑  <b>WAIFU COLLECTION BOT</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🌸 <b>Welcome to the Harem, Hunter!</b>\n\n"
    "⚔️ <b>How to play:</b>\n"
    "▫️ A character appears every 100 group messages\n"
    "▫️ Spot the <b>name</b> and grab\n"
    "▫️ Open your collection with <b>/amode</b> or <b>/army</b>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>Quick Commands:</b>\n"
    "▫️ /arise &lt;name&gt; — Grab\n"
    "▫️ /amode — Text collection\n"
    "▫️ /army — Grid gallery\n"
    "▫️ /search &lt;name&gt; — Global search\n"
    "▫️ /gift — Gift a character\n"
    "▫️ /daily — 100 coins\n"
    "▫️ /weekly — 2000 coins\n"
    "▫️ /claim — Free random character\n"
    "▫️ /shop — Buy with coins\n"
    "▫️ /stats — Your stats\n"
    "▫️ /ping — Bot status\n"
    "▫️ /help — Full guide\n\n"
    f"💬 <b>Support:</b> <a href='{SUPPORT_LINK}'>{SUPPORT_NAME}</a>"
)

HELP_TEXT = (
    "╔══════════════════════════════╗\n"
    "║   📖  <b>HOW TO PLAY</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "1️⃣ Every 100 group messages, a character spawns\n"
    "2️⃣ The name is hidden — spot it from the image\n"
    "3️⃣ Type <code>/arise &lt;name&gt;</code> to grab\n"
    "4️⃣ Open your collection with <b>/amode</b> or <b>/army</b>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>PLAYER COMMANDS:</b>\n"
    "▫️ /arise &lt;name&gt; — Grab\n"
    "▫️ /amode — Text collection (rarity list)\n"
    "▫️ /army — Grid gallery (scrollable)\n"
    "▫️ /search &lt;name&gt; — Global search\n"
    "▫️ /gift &lt;user_id&gt; &lt;waifu_id&gt;\n"
    "▫️ /daily — Daily 100 coins\n"
    "▫️ /weekly — Weekly 2000 coins\n"
    "▫️ /claim — Free random character\n"
    "▫️ /shop — Buy characters with coins\n"
    "▫️ /balance — Coin balance\n"
    "▫️ /stats — Your stats\n"
    "▫️ /rank — Top collectors\n"
    "▫️ /rarity — Rarity stats\n"
    "▫️ /global — Bot global stats\n"
    "▫️ /check &lt;id&gt; — Character info\n"
    "▫️ /ping — Bot status\n"
    "▫️ /viewtime — Gate timer\n"
    "▫️ /help — This help"
)

OHELP_TEXT = (
    "╔══════════════════════════════╗\n"
    "║   👑  <b>OWNER / ADMIN HELP</b>   ║\n"
    "╚══════════════════════════════╝\n\n"
    "🛡️ <b>Character Management:</b>\n"
    "▫️ <code>/addshadow</code> — Add character\n"
    "   ├─ 📸 Pic → 📝 Name → 🌸 Gender → ⭐ Rarity → 📺 Series → 📖 Desc\n\n"
    "▫️ <code>/setseries</code> &lt;id&gt; &lt;name&gt; — Assign series\n"
    "▫️ <code>/waifulist</code> — All characters\n"
    "▫️ <code>/delwaifu</code> &lt;id&gt; — Delete\n"
    "▫️ <code>/status</code> — Bot stats\n"
    "▫️ <code>/backup</code> — Download DB backup\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "👑 <b>Owner Only:</b>\n"
    "▫️ <code>/addadmin</code> / <code>/removeadmin</code> / <code>/admins</code>"
)


# ═══════════════ COMMANDS ═══════════════
async def cmd_start(update, context):
    u = update.effective_user
    try: get_or_create_player(u.id, u.username, u.first_name)
    except Exception: pass
    try:
        await update.message.reply_photo(photo=START_PHOTO, caption=START_CAPTION,
            parse_mode="HTML", reply_markup=kb_start())
        return
    except Exception: pass
    try: await update.message.reply_text(START_CAPTION, parse_mode="HTML", reply_markup=kb_start())
    except Exception: pass


async def cmd_help(update, context):
    try:
        await update.message.reply_photo(photo=START_PHOTO, caption=HELP_TEXT,
            parse_mode="HTML", reply_markup=kb_start())
    except Exception:
        try: await update.message.reply_text(HELP_TEXT, parse_mode="HTML", reply_markup=kb_start())
        except Exception: pass


async def cmd_ohelp(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 <b>Not Authorized.</b>", parse_mode="HTML"); return
    await update.message.reply_text(OHELP_TEXT, parse_mode="HTML")


async def cmd_arise(update, context):
    chat = update.effective_chat
    u = update.effective_user
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ This command works in groups only."); return
    if not context.args:
        await update.message.reply_text("❌ Usage: <code>/arise &lt;name&gt;</code>", parse_mode="HTML"); return
    user_input = " ".join(context.args).strip().lower()
    active = get_active_spawn(chat.id)
    if not active:
        await update.message.reply_text("🌑 No active spawn. Wait for the next one."); return
    waifu = get_waifu(active["waifu_id"])
    if not waifu:
        await update.message.reply_text("❌ Character missing."); return
    correct = (waifu.get("name") or "").strip().lower()
    matched = (user_input == correct)
    if not matched and len(user_input) >= 3:
        cw = correct.split(); uw = user_input.split()
        if len(cw) >= 2:
            for w in uw:
                if len(w) >= 3 and w in cw:
                    matched = True; break
    if not matched:
        await update.message.reply_text("❌ Wrong name. Try again."); return
    if not try_grab_spawn(active["id"], u.id):
        await update.message.reply_text("⚡ Someone else grabbed it first."); return
    try: get_or_create_player(u.id, u.username, u.first_name)
    except Exception: pass
    rarity = waifu.get("rarity", "Common")
    re = RARITY_EMOJI.get(rarity, "⚪")
    ge = gender_emoji(waifu.get("gender", "waifu"))
    name = waifu.get("name") or "Character"
    total = count_user_waifus(u.id)
    cap = (
        "✨ <b>ARISE SUCCESS</b>\n\n"
        f"{ge} <b>{name}</b>\n"
        f"⭐ {re} <b>{rarity}</b>\n"
        f"👤 <code>{u.id}</code>  |  📦 Army: <b>{total}</b>"
    )
    photo = waifu["image_url"] if waifu["image_source"] == "url" else waifu["file_id"]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📖 View Collection", callback_data="amode_open:0")
    ]])
    try:
        await context.bot.send_photo(chat.id, photo, caption=cap, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await update.message.reply_text(cap, parse_mode="HTML", reply_markup=kb)


# ─── AMODE — text list collection ───
def _build_amode_text(user_obj, page=0):
    grouped = get_user_waifus_grouped(user_obj.id)
    if not grouped:
        return None, None, 0, 0
    series_list = list(grouped.items())
    total_pages = max(1, math.ceil(len(series_list) / AMODE_SERIES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    page_series = series_list[page * AMODE_SERIES_PER_PAGE:(page + 1) * AMODE_SERIES_PER_PAGE]
    totals_map = get_series_totals(user_obj.id)

    name = user_obj.first_name or "Hunter"
    total_waifus = sum(len(v) for _, v in series_list)

    lines = [
        f"🌸 <b>{name}'s Collection</b> — Page {page+1}/{total_pages}",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for series, items in page_series:
        owned, total = totals_map.get(series, (len(items), len(items)))
        lines.append(f"⛩️ <b>{series}</b> ({owned}/{total})")
        for w in items[:AMODE_CHARS_PER_SERIES]:
            re = RARITY_EMOJI.get(w.get("rarity", "Common"), "⚪")
            dup = w.get("user_dup_count", 1)
            lines.append(f"   {re} | <code>{w['waifu_id']}</code> | {w['name']} (x{dup})")
        if len(items) > AMODE_CHARS_PER_SERIES:
            lines.append(f"   <i>… +{len(items)-AMODE_CHARS_PER_SERIES} more</i>")
        lines.append("")

    # nav buttons
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"amode_page:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="amode_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"amode_page:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(f"📖 Army ({total_waifus})", callback_data="amode_show_army")])
    kb = InlineKeyboardMarkup(rows)

    text = "\n".join(lines)
    return text, kb, page, total_pages


async def cmd_amode(update, context):
    u = update.effective_user
    ok, reason = await is_joined(context.bot, u.id)
    if not ok:
        await update.message.reply_text(f"🔒 <b>Join both channels first.</b>\n\n⚠️ {reason}",
            parse_mode="HTML", reply_markup=kb_join()); return
    if count_user_waifus(u.id) == 0:
        await update.message.reply_text(
            "🌑 <b>Your collection is empty.</b>\n\nWait for a spawn and use /arise."); return
    text, kb, _, _ = _build_amode_text(u, page=0)
    if text is None:
        await update.message.reply_text("🌑 Empty."); return
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def _send_army_grid(chat_id, context, user_obj):
    """Full gallery grid image, no buttons, scrollable."""
    grouped = get_user_waifus_grouped(user_obj.id)
    if not grouped:
        await context.bot.send_message(chat_id, "🌑 Your army is empty.")
        return
    totals = get_series_totals(user_obj.id)
    client = context.bot_data.get("httpx")
    if client is None:
        client = httpx.AsyncClient()
        context.bot_data["httpx"] = client
    total = sum(len(v) for v in grouped.values())
    wait = await context.bot.send_message(
        chat_id, f"⏳ Rendering your army ({total} characters)...\n<i>Please wait.</i>",
        parse_mode="HTML")
    try:
        buf, is_tall = await render_harem(context, client, grouped, totals)
        try: await wait.delete()
        except Exception: pass
        # clean — no buttons, user scrolls top-to-bottom
        if is_tall:
            await context.bot.send_document(chat_id=chat_id, document=buf, filename="harem.jpg")
        else:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=buf)
            except Exception:
                buf.seek(0)
                await context.bot.send_document(chat_id=chat_id, document=buf, filename="harem.jpg")
    except Exception as e:
        log.error(f"harem render: {e}")
        try: await wait.edit_text("❌ Render failed.")
        except Exception: pass


async def cmd_army(update, context):
    u = update.effective_user
    ok, reason = await is_joined(context.bot, u.id)
    if not ok:
        await update.message.reply_text(f"🔒 <b>Join both channels first.</b>\n\n⚠️ {reason}",
            parse_mode="HTML", reply_markup=kb_join()); return
    if count_user_waifus(u.id) == 0:
        await update.message.reply_text(
            "🌑 <b>Your army is empty.</b>\n\nWait for a spawn and use /arise."); return
    await _send_army_grid(update.message.chat_id, context, u)


# ─── Search ───
async def cmd_search(update, context):
    u = update.effective_user
    if not context.args:
        await update.message.reply_text("📌 Usage: <code>/search &lt;name&gt;</code>", parse_mode="HTML"); return
    ok, reason = await is_joined(context.bot, u.id)
    if not ok:
        await update.message.reply_text(f"🔒 <b>Join both channels first.</b>\n\n⚠️ {reason}",
            parse_mode="HTML", reply_markup=kb_join()); return
    q = " ".join(context.args).strip().lower()
    all_w = get_all_waifus()
    if not all_w:
        await update.message.reply_text("🌑 No characters in DB yet."); return
    matches = [w for w in all_w if q in (w.get("name") or "").lower()]
    if not matches:
        await update.message.reply_text(f"❌ No match: <code>{q}</code>", parse_mode="HTML"); return
    user_waifus = get_user_waifus(u.id)
    owned_ids = {x["waifu_id"] for x in user_waifus}
    if len(matches) == 1:
        w = matches[0]
        rar = w.get("rarity", "Common")
        re = RARITY_EMOJI.get(rar, "⚪")
        ge = gender_emoji(w.get("gender", "waifu"))
        owned = w["id"] in owned_ids
        status = "✅ In your army" if owned else "❌ Not in your army"
        cap = (
            f"{ge} <b>{w.get('name','')}</b>\n"
            f"⭐ {re} <b>{rar}</b>\n"
            f"🆔 <code>{w['id']}</code>  |  📺 {w.get('series','')}\n"
            f"👥 Owners: {count_waifu_owners(w['id'])}\n"
            f"{status}"
        )
        photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
        try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
        except Exception: await update.message.reply_text(cap, parse_mode="HTML")
        return
    buttons = []; row = []
    for w in matches[:30]:
        name = w.get("name") or "?"
        re = RARITY_EMOJI.get(w.get("rarity", ""), "⚪")
        mark = "✅ " if w["id"] in owned_ids else ""
        row.append(InlineKeyboardButton(f"{mark}{re} {name[:16]}", callback_data=f"search_det:{w['id']}"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    await update.message.reply_text(
        f"🔍 Multiple matches for <code>{q}</code> ({len(matches)}):",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


# ─── Gift ───
async def cmd_gift(update, context):
    u = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text(
            "🎁 <b>Gift a character</b>\n\n"
            "<code>/gift &lt;user_id&gt; &lt;waifu_id&gt;</code>", parse_mode="HTML"); return
    try:
        target_id = int(context.args[0]); wid = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Numbers only."); return
    if target_id == u.id:
        await update.message.reply_text("😐 You cannot gift yourself."); return
    w = get_waifu(wid)
    if not w:
        await update.message.reply_text(f"❌ Character ID {wid} not found."); return
    match = find_user_waifu(u.id, wid)
    if not match:
        await update.message.reply_text(f"❌ <b>{w.get('name')}</b> is not in your army."); return
    try: await context.bot.get_chat(target_id)
    except Exception:
        await update.message.reply_text("❌ Target user not reachable."); return
    give_waifu_to_user(target_id, wid)
    remove_user_waifu(match["uw_id"], u.id)
    rar = w.get("rarity", "Common"); re = RARITY_EMOJI.get(rar, "⚪")
    ge = gender_emoji(w.get("gender", "waifu"))
    cap = (
        "🎁 <b>CHARACTER GIFTED</b>\n\n"
        f"👤 From: <code>{u.id}</code>  →  🎯 To: <code>{target_id}</code>\n"
        f"{ge} <b>{w.get('name')}</b>  |  ⭐ {re} {rar}\n"
        f"🆔 <code>{wid}</code>"
    )
    photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
    try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except Exception: await update.message.reply_text(cap, parse_mode="HTML")
    try:
        await context.bot.send_message(target_id,
            f"🎁 <b>You received a character!</b>\n\n"
            f"👤 From: <code>{u.id}</code>\n"
            f"{ge} <b>{w.get('name')}</b> ({re} {rar})\n"
            f"🆔 <code>{wid}</code>", parse_mode="HTML")
    except Exception: pass


# ─── Coins ───
async def cmd_balance(update, context):
    u = update.effective_user
    get_or_create_player(u.id, u.username, u.first_name)
    await update.message.reply_text(
        f"💰 <b>Balance:</b> <code>{get_coins(u.id)}</code> coins", parse_mode="HTML")


async def cmd_daily(update, context):
    u = update.effective_user
    p = get_or_create_player(u.id, u.username, u.first_name)
    last = _parse_dt(p.get("last_daily")); now = _now()
    if last and (now - last) < DAILY_COOLDOWN:
        left = DAILY_COOLDOWN - (now - last)
        h, rem = divmod(int(left.total_seconds()), 3600); m = rem // 60
        await update.message.reply_text(
            f"⏳ <b>Daily already claimed</b>\n"
            f"Come back in <b>{h}h {m}m</b>\n"
            f"Balance: <code>{get_coins(u.id)}</code>",
            parse_mode="HTML"); return
    add_coins(u.id, DAILY_COINS)
    with get_conn() as conn:
        conn.execute("UPDATE players SET last_daily=? WHERE user_id=?", (now.isoformat(), u.id))
    await update.message.reply_text(
        f"✅ <b>Daily claimed</b>\n"
        f"💰 +{DAILY_COINS} coins\n"
        f"💼 Balance: <b>{get_coins(u.id)}</b>\n"
        f"⏰ Next in 24h",
        parse_mode="HTML")


async def cmd_weekly(update, context):
    u = update.effective_user
    p = get_or_create_player(u.id, u.username, u.first_name)
    last = _parse_dt(p.get("last_weekly")); now = _now()
    if last and (now - last) < WEEKLY_COOLDOWN:
        left = WEEKLY_COOLDOWN - (now - last)
        d = left.days; h = left.seconds // 3600
        await update.message.reply_text(
            f"⏳ <b>Weekly already claimed</b>\n"
            f"Come back in <b>{d}d {h}h</b>\n"
            f"Balance: <code>{get_coins(u.id)}</code>",
            parse_mode="HTML"); return
    add_coins(u.id, WEEKLY_COINS)
    with get_conn() as conn:
        conn.execute("UPDATE players SET last_weekly=? WHERE user_id=?", (now.isoformat(), u.id))
    await update.message.reply_text(
        f"✅ <b>Weekly claimed</b>\n"
        f"💰 +{WEEKLY_COINS} coins\n"
        f"💼 Balance: <b>{get_coins(u.id)}</b>\n"
        f"⏰ Next in 7 days",
        parse_mode="HTML")


async def cmd_claim(update, context):
    u = update.effective_user
    p = get_or_create_player(u.id, u.username, u.first_name)
    last = _parse_dt(p.get("last_claim")); now = _now()
    if last and (now - last) < CLAIM_COOLDOWN:
        left = CLAIM_COOLDOWN - (now - last)
        h = left.seconds // 3600; m = (left.seconds % 3600) // 60
        await update.message.reply_text(
            f"⏳ <b>Claim on cooldown</b>\nCome back in <b>{h}h {m}m</b>",
            parse_mode="HTML"); return
    w = get_random_waifu(weighted=True)
    if not w:
        await update.message.reply_text("🌑 No characters in DB yet."); return
    give_waifu_to_user(u.id, w["id"])
    with get_conn() as conn:
        conn.execute("UPDATE players SET last_claim=? WHERE user_id=?", (now.isoformat(), u.id))
    rar = w.get("rarity", "Common"); re = RARITY_EMOJI.get(rar, "⚪")
    ge = gender_emoji(w.get("gender", "waifu"))
    cap = (
        "🎁 <b>CLAIM SUCCESS</b>\n\n"
        f"{ge} <b>{w.get('name','')}</b>\n"
        f"⭐ {re} <b>{rar}</b>\n"
        f"👤 <code>{u.id}</code>"
    )
    photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📖 View Collection", callback_data="amode_open:0")]])
    try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML", reply_markup=kb)
    except Exception: await update.message.reply_text(cap, parse_mode="HTML", reply_markup=kb)


async def cmd_shop(update, context):
    if context.args:
        rar = context.args[0].title()
        if rar not in RARITY_EMOJI:
            await update.message.reply_text("❌ Invalid rarity."); return
        ws = get_all_waifus_by_rarity(rar)
        if not ws:
            await update.message.reply_text(f"📭 No characters in {rar}."); return
        price = rarity_price(rar)
        buttons = []
        for w in ws[:60]:
            buttons.append([InlineKeyboardButton(
                f"{RARITY_EMOJI.get(rar,'⚪')} {w.get('name','?')[:22]} — {price}💰",
                callback_data=f"shop_buy:{w['id']}")])
        buttons.append([InlineKeyboardButton("🔙 Categories", callback_data="shop_cats")])
        await update.message.reply_text(
            f"🛒 <b>SHOP — {RARITY_EMOJI.get(rar,'⚪')} {rar}</b>\n💰 Price: <b>{price}</b> coins",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)); return
    counts = get_all_rarity_counts()
    buttons = []; row = []
    for r in RARITY_ORDER:
        if r not in counts: continue
        row.append(InlineKeyboardButton(f"{RARITY_EMOJI.get(r,'⚪')} {r} ({counts[r]})",
                                        callback_data=f"shop_cat:{r}"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    await update.message.reply_text("🛒 <b>SHOP</b>\n\nChoose a category to browse:",
                                    parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def cmd_stats(update, context):
    u = update.effective_user
    get_or_create_player(u.id, u.username, u.first_name)
    total = count_user_waifus(u.id); coins = get_coins(u.id)
    if total == 0:
        await update.message.reply_text(
            f"📊 <b>Your stats are empty.</b>\n💰 Coins: <b>{coins}</b>",
            parse_mode="HTML"); return
    gc = get_user_gender_counts(u.id); rc = get_user_rarity_counts(u.id)
    txt = (
        "╔══════════════════════════════╗\n"
        "║   📊  <b>MY STATS</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"👤 <code>{u.id}</code>\n💰 Coins: <b>{coins}</b>\n🌸 Total: <b>{total}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌸 Waifu: <b>{gc.get('waifu',0)}</b>  🗡️ Husbando: <b>{gc.get('husbando',0)}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n<b>RARITY BREAKDOWN</b>\n"
    )
    for r in RARITY_ORDER:
        if r in rc:
            re = RARITY_EMOJI.get(r, "⚪")
            txt += f"{re} {r}: <b>{rc[r]}</b>\n"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_rank(update, context):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, COUNT(*) AS cnt FROM user_waifus GROUP BY user_id ORDER BY cnt DESC LIMIT 10")
        rows = c.fetchall()
    if not rows:
        await update.message.reply_text("📭 No collections yet."); return
    txt = "🏆 <b>TOP COLLECTORS</b>\n\n"
    medals = ["🥇","🥈","🥉"]
    for i, r in enumerate(rows):
        try:
            user = await context.bot.get_chat(r["user_id"])
            name = user.first_name or f"User{r['user_id']}"
        except Exception: name = f"User{r['user_id']}"
        prefix = medals[i] if i < 3 else f"{i+1}."
        txt += f"{prefix} {name} — <b>{r['cnt']}</b> 🌸\n"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_rarity(update, context):
    counts = get_all_rarity_counts()
    if not counts:
        await update.message.reply_text("📭 No characters."); return
    total = sum(counts.values())
    txt = "💎 <b>RARITY STATS</b>\n\n"
    for r in RARITY_ORDER:
        if r in counts:
            re = RARITY_EMOJI.get(r, "⚪")
            txt += f"{re} {r}: <b>{counts[r]}</b>\n"
    txt += f"\n🌸 Total: <b>{total}</b>"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_global(update, context):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT chat_id) FROM group_counters"); groups = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM players"); users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM waifus WHERE active=1"); waifus = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM user_waifus"); collected = c.fetchone()[0]
    await update.message.reply_text(
        "🌍 <b>GLOBAL STATS</b>\n\n"
        f"💬 Groups: <b>{groups}</b>\n👥 Players: <b>{users}</b>\n"
        f"🌸 Characters: <b>{waifus}</b>\n📦 Collected: <b>{collected}</b>",
        parse_mode="HTML")


async def cmd_ping(update, context):
    start = time.time()
    msg = await update.message.reply_text("🏓 <b>Pinging...</b>", parse_mode="HTML")
    latency = int((time.time() - start) * 1000)
    up = int(time.time() - BOT_START_TIME)
    h, rem = divmod(up, 3600); m, s = divmod(rem, 60)
    up_str = f"{h}h {m}m" if h else (f"{m}m {s}s" if m else f"{s}s")
    await msg.edit_text(
        f"🏓 <b>PONG</b>\n\n⚡ Latency: <code>{latency} ms</code>\n"
        f"⏱️ Uptime: <code>{up_str}</code>\n🤖 ✅ Online", parse_mode="HTML")


async def cmd_viewtime(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Group only."); return
    if get_active_spawn(chat.id):
        await update.message.reply_text("⚠️ A spawn is already active."); return
    stats = get_group_stats(chat.id)
    cur = stats["msg_count"]; total = stats["total_spawns"]
    rem = max(0, SPAWN_MESSAGE_THRESHOLD - cur)
    pct = min(100, int((cur / SPAWN_MESSAGE_THRESHOLD) * 100))
    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    await update.message.reply_text(
        f"🌑 <b>GATE STATUS</b>\n\n📨 {cur}/{SPAWN_MESSAGE_THRESHOLD}\n"
        f"📊 <code>{bar}</code> {pct}%\n\n⏳ <b>{rem}</b> messages until next spawn\n"
        f"🎯 Total spawns: <b>{total}</b>", parse_mode="HTML")


async def cmd_check(update, context):
    if not context.args:
        await update.message.reply_text("📌 Usage: <code>/check &lt;id&gt;</code>", parse_mode="HTML"); return
    try: wid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid ID."); return
    w = get_waifu(wid)
    if not w:
        await update.message.reply_text(f"❌ ID {wid} not found."); return
    rar = w.get("rarity", "Common"); re = RARITY_EMOJI.get(rar, "⚪")
    ge = gender_emoji(w.get("gender", "waifu"))
    cap = (
        f"{ge} <b>{w.get('name','')}</b>\n"
        f"⭐ {re} <b>{rar}</b>\n"
        f"📺 {w.get('series','')}  |  🆔 <code>{w['id']}</code>\n"
        f"👥 Owners: {count_waifu_owners(wid)}"
    )
    photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
    try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except Exception: await update.message.reply_text(cap, parse_mode="HTML")


# ═══════════════ ADDSHADOW ═══════════════
ASK_PHOTO, ASK_NAME, ASK_GENDER, ASK_RARITY, ASK_SERIES, ASK_SERIES_NEW, ASK_DESC = range(7)


def _kb_series_choice():
    series_list = get_all_series()
    buttons = []; row = []
    for s in series_list[:24]:
        row.append(InlineKeyboardButton(s[:28], callback_data=f"series_pick:{s}"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("➕ New Series", callback_data="series_new")])
    buttons.append([InlineKeyboardButton("⏭ Skip (Unknown Series)", callback_data="series_pick:Unknown Series")])
    return InlineKeyboardMarkup(buttons)


def _kb_rarity():
    buttons = []; row = []
    for r, e in RARITY_EMOJI.items():
        row.append(InlineKeyboardButton(f"{e} {r}", callback_data=f"rarity:{r}"))
        if len(row) == 3: buttons.append(row); row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def addshadow_start(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only."); return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("📸 Send the image (photo, image file, or URL).")
    return ASK_PHOTO


async def addshadow_photo(update, context):
    fid = url = None
    if update.message.photo: fid = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type and \
         update.message.document.mime_type.startswith("image/"):
        fid = update.message.document.file_id
    elif update.message.text and update.message.text.startswith(("http://","https://")):
        url = update.message.text.strip()
    else:
        await update.message.reply_text("❌ Send a photo, image file, or URL."); return ASK_PHOTO
    context.user_data["file_id"] = fid; context.user_data["image_url"] = url
    await update.message.reply_text("📝 Send the character name.")
    return ASK_NAME


async def addshadow_name(update, context):
    if not update.message.text:
        await update.message.reply_text("❌ Send text."); return ASK_NAME
    name = update.message.text.strip()
    if not name or len(name) > 60:
        await update.message.reply_text("❌ 1-60 characters."); return ASK_NAME
    context.user_data["name"] = name
    await update.message.reply_text("🌸 Waifu or Husbando?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌸 Waifu", callback_data="gender:waifu"),
            InlineKeyboardButton("🗡️ Husbando", callback_data="gender:husbando")]]))
    return ASK_GENDER


async def addshadow_gender_cb(update, context):
    q = update.callback_query; await q.answer()
    g = q.data.split(":")[1]
    context.user_data["gender"] = g
    await q.edit_message_text(f"Type: {gender_label(g)}\n\n⭐ Choose rarity:", reply_markup=_kb_rarity())
    return ASK_RARITY


async def addshadow_gender_txt(update, context):
    if not update.message.text: return ASK_GENDER
    g = update.message.text.strip().lower()
    if g not in ("waifu","husbando"):
        await update.message.reply_text("❌ 'waifu' or 'husbando'."); return ASK_GENDER
    context.user_data["gender"] = g
    await update.message.reply_text(f"Type: {gender_label(g)}\n\n⭐ Choose rarity:", reply_markup=_kb_rarity())
    return ASK_RARITY


async def addshadow_rarity_cb(update, context):
    q = update.callback_query; await q.answer()
    r = q.data.split(":",1)[1]
    if r not in RARITY_EMOJI:
        await q.answer("Invalid!", show_alert=True); return ASK_RARITY
    context.user_data["rarity"] = r
    await q.edit_message_text(
        f"Rarity: {RARITY_EMOJI.get(r,'⚪')} {r}\n\n📺 Pick a series (tap) or add new:",
        reply_markup=_kb_series_choice())
    return ASK_SERIES


async def addshadow_rarity_txt(update, context):
    if not update.message.text: return ASK_RARITY
    r = update.message.text.strip().title()
    if r not in RARITY_EMOJI:
        await update.message.reply_text("❌ Invalid rarity."); return ASK_RARITY
    context.user_data["rarity"] = r
    await update.message.reply_text(
        f"Rarity: {RARITY_EMOJI.get(r,'⚪')} {r}\n\n📺 Pick a series (tap) or add new:",
        reply_markup=_kb_series_choice())
    return ASK_SERIES


async def addshadow_series_pick_cb(update, context):
    q = update.callback_query; await q.answer()
    series = q.data.split(":", 1)[1]
    context.user_data["series"] = series
    await q.edit_message_text(
        f"📺 Series: <b>{series}</b>\n\n📖 Now send the description.",
        parse_mode="HTML")
    return ASK_DESC


async def addshadow_series_new_cb(update, context):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("📺 Send the new series name:")
    return ASK_SERIES_NEW


async def addshadow_series_new_txt(update, context):
    if not update.message.text:
        await update.message.reply_text("❌ Send text."); return ASK_SERIES_NEW
    s = update.message.text.strip()
    if not s or len(s) > 80:
        await update.message.reply_text("❌ 1-80 characters."); return ASK_SERIES_NEW
    context.user_data["series"] = s
    await update.message.reply_text(
        f"📺 Series: <b>{s}</b>\n\n📖 Now send the description.",
        parse_mode="HTML")
    return ASK_DESC


async def addshadow_series_txt(update, context):
    if not update.message.text:
        await update.message.reply_text("❌ Send text or tap a button."); return ASK_SERIES
    s = update.message.text.strip()
    if s.lower() == "skip": s = "Unknown Series"
    if len(s) > 80:
        await update.message.reply_text("❌ Too long."); return ASK_SERIES
    context.user_data["series"] = s
    await update.message.reply_text(
        f"📺 Series: <b>{s}</b>\n\n📖 Now send the description.",
        parse_mode="HTML")
    return ASK_DESC


async def addshadow_desc(update, context):
    if not update.message.text:
        await update.message.reply_text("❌ Send text."); return ASK_DESC
    desc = update.message.text.strip()
    if not desc or len(desc) > 500:
        await update.message.reply_text("❌ 1-500 characters."); return ASK_DESC
    d = context.user_data
    mid = add_waifu(name=d.get("name",""), gender=d.get("gender","waifu"),
                    rarity=d.get("rarity","Common"), file_id=d.get("file_id"),
                    image_url=d.get("image_url"), description=desc,
                    series=d.get("series","Unknown Series"))
    photo = d.get("image_url") or d.get("file_id")
    rar = d.get("rarity","Common"); re = RARITY_EMOJI.get(rar,"⚪")
    ge = gender_emoji(d.get("gender","waifu"))
    cap = (
        "✅ <b>CHARACTER ADDED</b>\n\n"
        f"🆔 <code>{mid}</code>\n"
        f"{ge} {gender_label(d.get('gender','waifu'))}\n"
        f"🌸 <b>{d.get('name','')}</b>\n"
        f"⭐ {re} {rar}  |  📺 {d.get('series','')}"
    )
    try: await update.message.reply_photo(photo, caption=cap, parse_mode="HTML")
    except Exception: await update.message.reply_text(cap, parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END


async def addshadow_cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ═══════════════ ADMIN ═══════════════
async def cmd_waifulist(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only."); return
    ws = get_all_waifus()
    if not ws:
        await update.message.reply_text("📭 None."); return
    txt = f"🌸 <b>Characters ({len(ws)})</b>\n\n"
    for w in ws[:40]:
        re = RARITY_EMOJI.get(w.get("rarity","Common"), "⚪")
        ge = gender_emoji(w.get("gender","waifu"))
        txt += f"<code>{w['id']}</code> {ge}{re} {w.get('name','?')} — {w.get('series','')}\n"
    if len(ws) > 40: txt += f"\n<i>...and {len(ws)-40} more</i>"
    await update.message.reply_text(txt, parse_mode="HTML")


async def cmd_delwaifu(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only."); return
    if not context.args:
        await update.message.reply_text("📌 /delwaifu <id>", parse_mode="HTML"); return
    try: wid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid."); return
    if not get_waifu(wid):
        await update.message.reply_text(f"❌ ID {wid} not found."); return
    delete_waifu(wid)
    await update.message.reply_text(f"✅ Deleted ID {wid}")


async def cmd_setseries(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only."); return
    if len(context.args) < 2:
        await update.message.reply_text(
            "📌 <b>Usage:</b> <code>/setseries &lt;waifu_id&gt; &lt;series_name&gt;</code>\n"
            "Example: <code>/setseries 42 Classroom of the Elite</code>", parse_mode="HTML"); return
    try: wid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid waifu_id."); return
    series = " ".join(context.args[1:]).strip()
    if not series or len(series) > 80:
        await update.message.reply_text("❌ Series name 1-80 characters."); return
    w = get_waifu(wid)
    if not w:
        await update.message.reply_text(f"❌ ID {wid} not found."); return
    if set_waifu_series(wid, series):
        await update.message.reply_text(
            f"✅ Updated\n\n🆔 <code>{wid}</code>\n🌸 {w.get('name')}\n📺 {series}", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ Update failed.")


async def cmd_status(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only."); return
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM waifus WHERE active=1"); total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM user_waifus"); grabbed = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM players"); users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM spawns"); spawns = c.fetchone()[0]
    await update.message.reply_text(
        f"🗄️ <b>STATUS</b>\n\n🌸 Characters: <b>{total}</b>\n"
        f"🎯 Grabs: <b>{grabbed}</b>\n👥 Players: <b>{users}</b>\n⚡ Spawns: <b>{spawns}</b>",
        parse_mode="HTML")


async def cmd_backup(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only."); return
    if not os.path.exists(DB_PATH):
        await update.message.reply_text("❌ DB file not found."); return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(BACKUP_DIR, f"shadow_{stamp}.db")
        shutil.copy2(DB_PATH, dst)
        size_kb = os.path.getsize(dst) // 1024
        await update.message.reply_document(
            document=open(dst, "rb"), filename=f"shadow_{stamp}.db",
            caption=f"💾 <b>Backup created</b>\n\n📁 <code>{dst}</code>\n📦 Size: <b>{size_kb} KB</b>",
            parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Backup failed: {e}")


async def cmd_addadmin(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only."); return
    tid = tname = None
    if update.message.reply_to_message:
        tid = update.message.reply_to_message.from_user.id
        tname = update.message.reply_to_message.from_user.first_name
    elif context.args:
        try: tid = int(context.args[0]); tname = f"User {tid}"
        except ValueError:
            await update.message.reply_text("❌ Invalid ID."); return
    else:
        await update.message.reply_text("📌 Reply or give ID."); return
    if tid == OWNER_ID:
        await update.message.reply_text("❌ Owner is already admin."); return
    if add_admin(tid, update.effective_user.id):
        await update.message.reply_text(f"✅ Admin added: {tname} (<code>{tid}</code>)", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ Already admin.")


async def cmd_removeadmin(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only."); return
    tid = tname = None
    if update.message.reply_to_message:
        tid = update.message.reply_to_message.from_user.id
        tname = update.message.reply_to_message.from_user.first_name
    elif context.args:
        try: tid = int(context.args[0]); tname = f"User {tid}"
        except ValueError:
            await update.message.reply_text("❌ Invalid ID."); return
    else:
        await update.message.reply_text("📌 Reply or give ID."); return
    if remove_admin(tid):
        await update.message.reply_text(f"✅ Admin removed: {tname}")
    else:
        await update.message.reply_text("⚠️ Not an admin.")


async def cmd_admins(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only."); return
    admins = get_all_admins()
    txt = f"👑 <b>ADMINS</b>\n\n👤 Owner: <code>{OWNER_ID}</code>\n\n"
    for a in admins:
        try:
            u = await context.bot.get_chat(a["user_id"]); name = u.first_name
        except Exception: name = "Unknown"
        txt += f"▫️ {name} — <code>{a['user_id']}</code>\n"
    if not admins: txt += "📭 No additional admins."
    await update.message.reply_text(txt, parse_mode="HTML")


# ═══════════════ SPAWN ═══════════════
async def track_message(update, context):
    if update.effective_chat.type not in ("group","supergroup"): return
    if not update.effective_user or update.effective_user.is_bot: return
    chat_id = update.effective_chat.id
    if get_active_spawn(chat_id): return
    count = incr_msg(chat_id)
    if count >= SPAWN_MESSAGE_THRESHOLD:
        reset_msg(chat_id)
        await spawn_waifu(chat_id, context)


async def spawn_waifu(chat_id, context):
    w = get_random_waifu()
    if not w: return
    exp = (_now() + timedelta(seconds=SPAWN_EXPIRY_SECONDS)).isoformat()
    sid = create_spawn(chat_id, w["id"], exp)
    cap = (
        "🍀 <b>New Waifu Is Here, Hurry-Up!</b>\n"
        "Type <code>/arise &lt;name&gt;</code> To Add Her Into Your Harem"
    )
    photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
    try:
        msg = await context.bot.send_photo(chat_id=chat_id, photo=photo,
                                           caption=cap, parse_mode="HTML")
        set_spawn_message(sid, msg.message_id)
    except Exception as e:
        log.error(f"spawn fail: {e}")


async def expire_job(context):
    n = expire_spawns()
    if n: log.info(f"expired {n} spawns")


# ─── bot username mention → grid ───
async def on_bot_mention(update, context):
    msg = update.message
    if not msg or not msg.text:
        return
    uname_tag = f"@{BOT_USERNAME}"
    if uname_tag.lower() not in msg.text.lower():
        return
    u = msg.from_user
    if not u or u.is_bot:
        return
    try: get_or_create_player(u.id, u.username, u.first_name)
    except Exception: pass
    if count_user_waifus(u.id) == 0:
        try:
            await msg.reply_text("🌑 Your collection is empty. Use /arise to grab first.")
        except Exception: pass
        return
    await _send_army_grid(msg.chat_id, context, u)


# ═══════════════ CALLBACKS ═══════════════
async def callback_router(update, context):
    q = update.callback_query; await q.answer()
    data = q.data or ""

    if data == "check_join":
        ok, reason = await is_joined(context.bot, q.from_user.id)
        if ok:
            await q.answer("✅ Verified!", show_alert=True)
            try: await q.edit_message_text("🟢 Verified! Use /amode to open your collection.")
            except Exception: pass
        else:
            await q.answer(f"❌ {reason}", show_alert=True)
        return

    if data.startswith("amode_open:"):
        page = int(data.split(":")[1])
        u = q.from_user
        if count_user_waifus(u.id) == 0:
            await q.answer("Empty collection.", show_alert=True); return
        text, kb, _, _ = _build_amode_text(u, page=page)
        try:
            await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception: pass
        return

    if data.startswith("amode_page:"):
        page = int(data.split(":")[1])
        u = q.from_user
        text, kb, _, _ = _build_amode_text(u, page=page)
        if text is None:
            await q.answer("Empty.", show_alert=True); return
        try:
            await q.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            try: await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception: pass
        return

    if data == "amode_noop": return

    if data == "amode_show_army":
        await _send_army_grid(q.message.chat_id, context, q.from_user)
        return

    if data.startswith("search_det:"):
        wid = int(data.split(":")[1])
        w = get_waifu(wid)
        if not w:
            await q.answer("Not found.", show_alert=True); return
        rar = w.get("rarity","Common"); re = RARITY_EMOJI.get(rar,"⚪")
        ge = gender_emoji(w.get("gender","waifu"))
        cap = (
            f"{ge} <b>{w.get('name','')}</b>\n"
            f"⭐ {re} <b>{rar}</b>\n"
            f"📺 {w.get('series','')}\n"
            f"🆔 <code>{wid}</code>\n"
            f"👥 Owners: {count_waifu_owners(wid)}"
        )
        photo = w["image_url"] if w["image_source"] == "url" else w["file_id"]
        try: await q.message.reply_photo(photo, caption=cap, parse_mode="HTML")
        except Exception: await q.message.reply_text(cap, parse_mode="HTML")
        return

    if data == "shop_cats":
        counts = get_all_rarity_counts()
        buttons = []; row = []
        for r in RARITY_ORDER:
            if r not in counts: continue
            row.append(InlineKeyboardButton(f"{RARITY_EMOJI.get(r,'⚪')} {r} ({counts[r]})",
                                            callback_data=f"shop_cat:{r}"))
            if len(row) == 2: buttons.append(row); row = []
        if row: buttons.append(row)
        try: await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        except Exception: pass
        return

    if data.startswith("shop_cat:"):
        rar = data.split(":",1)[1]
        ws = get_all_waifus_by_rarity(rar)
        if not ws:
            await q.answer("Empty.", show_alert=True); return
        price = rarity_price(rar)
        buttons = []
        for w in ws[:60]:
            buttons.append([InlineKeyboardButton(
                f"{RARITY_EMOJI.get(rar,'⚪')} {w.get('name','?')[:22]} — {price}💰",
                callback_data=f"shop_buy:{w['id']}")])
        buttons.append([InlineKeyboardButton("🔙 Categories", callback_data="shop_cats")])
        try:
            await q.edit_message_text(
                f"🛒 <b>SHOP — {RARITY_EMOJI.get(rar,'⚪')} {rar}</b>\n💰 Price: <b>{price}</b> coins",
                parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception: pass
        return

    if data.startswith("shop_buy:"):
        wid = int(data.split(":")[1])
        w = get_waifu(wid)
        if not w:
            await q.answer("Character missing.", show_alert=True); return
        price = rarity_price(w.get("rarity","Common"))
        balance = get_coins(q.from_user.id)
        if balance < price:
            await q.answer(f"❌ Need {price} coins. You have {balance}.", show_alert=True); return
        add_coins(q.from_user.id, -price)
        give_waifu_to_user(q.from_user.id, wid)
        await q.answer(f"✅ Bought {w.get('name')} for {price} coins!", show_alert=True)
        return

    log.warning(f"unhandled callback: {data}")


# ═══════════════ MAIN ═══════════════
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing in .env"); return
    if not OWNER_ID:
        print("❌ OWNER_ID missing in .env"); return

    _auto_backup()
    init_db()
    start_health_server()

    app = Application.builder().token(BOT_TOKEN).build()

    # bot mention handler — runs in group 0, before tracking
    mention_pattern = f"@{BOT_USERNAME}"
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, on_bot_mention), group=0)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ohelp", cmd_ohelp))
    app.add_handler(CommandHandler("arise", cmd_arise))
    app.add_handler(CommandHandler("guess", cmd_arise))
    app.add_handler(CommandHandler("amode", cmd_amode))
    app.add_handler(CommandHandler("army", cmd_army))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("gift", cmd_gift))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("weekly", cmd_weekly))
    app.add_handler(CommandHandler("claim", cmd_claim))
    app.add_handler(CommandHandler("shop", cmd_shop))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("rarity", cmd_rarity))
    app.add_handler(CommandHandler("global", cmd_global))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("viewtime", cmd_viewtime))
    app.add_handler(CommandHandler("gate", cmd_viewtime))
    app.add_handler(CommandHandler("check", cmd_check))

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("waifulist", cmd_waifulist))
    app.add_handler(CommandHandler("delwaifu", cmd_delwaifu))
    app.add_handler(CommandHandler("setseries", cmd_setseries))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))
    app.add_handler(CommandHandler("admins", cmd_admins))

    addshadow_conv = ConversationHandler(
        entry_points=[CommandHandler("addshadow", addshadow_start)],
        states={
            ASK_PHOTO:      [MessageHandler(filters.PHOTO | filters.Document.IMAGE |
                                            (filters.TEXT & ~filters.COMMAND), addshadow_photo)],
            ASK_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_name)],
            ASK_GENDER:     [CallbackQueryHandler(addshadow_gender_cb, pattern=r"^gender:"),
                             MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_gender_txt)],
            ASK_RARITY:     [CallbackQueryHandler(addshadow_rarity_cb, pattern=r"^rarity:"),
                             MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_rarity_txt)],
            ASK_SERIES:     [CallbackQueryHandler(addshadow_series_pick_cb, pattern=r"^series_pick:"),
                             CallbackQueryHandler(addshadow_series_new_cb, pattern=r"^series_new$"),
                             MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_series_txt)],
            ASK_SERIES_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_series_new_txt)],
            ASK_DESC:       [MessageHandler(filters.TEXT & ~filters.COMMAND, addshadow_desc)],
        },
        fallbacks=[CommandHandler("cancel", addshadow_cancel)],
        per_user=True, per_chat=False,
    )
    app.add_handler(addshadow_conv)

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Sticker.ALL) & ~filters.COMMAND,
        track_message), group=1)

    if app.job_queue:
        app.job_queue.run_repeating(expire_job, interval=30, first=10)

    log.info("Waifu Bot v16 starting...")

    # Python 3.14 compatibility: explicitly create the main event loop
    # before python-telegram-bot's run_polling() accesses it.
    import asyncio

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
PY
