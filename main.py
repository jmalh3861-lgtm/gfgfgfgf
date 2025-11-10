"""
userbot.py - بوت تيليجرام للوساطة
يوفر جميع ميزات إدارة الوساطات مع دعم كامل للأوامر والتذكيرات التلقائية
"""

import os
import re
import json
import asyncio
import sqlite3
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.raw import functions as raw_functions, types as raw_types
from pyrogram.errors import RPCError

load_dotenv()

API_ID = 29181790
API_HASH = "94ab5d4154e81a5db294fe0dcd2dcb1b"
SESSION_NAME = "userbot_session"

MONITOR_CHAT = -1001703488065
ALERT_CHAT = "me"
POSTING_CHANNEL = -1002679021850

OWNER_USERNAMES = ["plyns", "h_7_m"]

APPROVE_KEYWORD = "موافق"
CMD_EPIC = "ايبك"
CMD_TIKTOK = "تيك تيك"
CMD_ROB = "روب"
CMD_NUMBER = "رقم"
CMD_DELIVER = "تسليم"
CMD_DONE = "انهاء"
CMD_LIST_MEDIATIONS = "الوساطات"
CMD_HELP = "الاوامر"
CMD_LAST_5 = "اخر 5"
CMD_POST_MEDIATIONS = "تنزيل الواسطات"
CMD_START_REMINDER = "بدا التذكير"
CMD_STOP_REMINDER = "توقيف التذكير"

DB_PATH = "userbot_mm.db"

EMOJI_CONFIG = {}
reminder_tasks = {}

def load_emojis():
    """Load emoji IDs from JSON file"""
    global EMOJI_CONFIG
    defaults = {
        "heart": {"id": 5301152643098357052},
        "check": {"id": 5303445769087366461},
        "deliver_warning": {"id": 5301152643098357052},
        "done": {"id": 5303445769087366461},
        "rating": {"id": 5301152643098357052},
        "market": {"id": 5300794855142733883}
    }
    
    try:
        with open("emojis.json", "r", encoding="utf-8") as f:
            EMOJI_CONFIG = json.load(f)
        
        required_keys = ["heart", "check", "deliver_warning", "done", "rating", "market"]
        missing_keys = [k for k in required_keys if k not in EMOJI_CONFIG or "id" not in EMOJI_CONFIG.get(k, {})]
        
        if missing_keys:
            print(f"⚠️ Missing emoji keys in emojis.json: {missing_keys}")
            for key in missing_keys:
                EMOJI_CONFIG[key] = defaults[key]
        
        print("✅ Emoji configuration loaded successfully")
    except FileNotFoundError:
        print("⚠️ emojis.json not found, using default emoji values")
        EMOJI_CONFIG = defaults
    except Exception as e:
        print(f"⚠️ Error loading emojis.json: {e}, using defaults")
        EMOJI_CONFIG = defaults

def get_emoji_id(key):
    """Get emoji ID by key with fallback"""
    emoji_id = EMOJI_CONFIG.get(key, {}).get("id", 0)
    if emoji_id == 0:
        print(f"⚠️ Warning: Emoji ID for '{key}' is 0 or missing")
    return emoji_id


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts_map (
            alert_msg_id INTEGER PRIMARY KEY,
            origin_chat_id INTEGER,
            origin_msg_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS mediations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin_chat_id INTEGER NOT NULL,
            origin_msg_id INTEGER NOT NULL,
            creator_user_id INTEGER,
            seller TEXT,
            buyer TEXT,
            seller_id INTEGER,
            buyer_id INTEGER,
            item TEXT,
            payment_method TEXT,
            amount TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP,
            completed_at TIMESTAMP,
            rating_msg_id INTEGER,
            seller_rated BOOLEAN DEFAULT 0,
            buyer_rated BOOLEAN DEFAULT 0,
            UNIQUE(origin_chat_id, origin_msg_id)
        );
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS posted_mediations (
            mediation_id INTEGER PRIMARY KEY,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mediation_id) REFERENCES mediations(id)
        );
    """)
    
    try:
        c.execute("SELECT creator_user_id FROM mediations LIMIT 1")
    except sqlite3.OperationalError:
        print("⚙️ Running migration: adding creator_user_id column...")
        c.execute("ALTER TABLE mediations ADD COLUMN creator_user_id INTEGER")
        conn.commit()
    
    try:
        c.execute("SELECT seller_id FROM mediations LIMIT 1")
    except sqlite3.OperationalError:
        print("⚙️ Running migration: adding seller_id column...")
        c.execute("ALTER TABLE mediations ADD COLUMN seller_id INTEGER")
        conn.commit()
    
    try:
        c.execute("SELECT buyer_id FROM mediations LIMIT 1")
    except sqlite3.OperationalError:
        print("⚙️ Running migration: adding buyer_id column...")
        c.execute("ALTER TABLE mediations ADD COLUMN buyer_id INTEGER")
        conn.commit()
    
    try:
        c.execute("SELECT rating_msg_id FROM mediations LIMIT 1")
    except sqlite3.OperationalError:
        print("⚙️ Running migration: adding rating_msg_id column...")
        c.execute("ALTER TABLE mediations ADD COLUMN rating_msg_id INTEGER")
        conn.commit()
    
    try:
        c.execute("SELECT seller_rated FROM mediations LIMIT 1")
    except sqlite3.OperationalError:
        print("⚙️ Running migration: adding seller_rated column...")
        c.execute("ALTER TABLE mediations ADD COLUMN seller_rated BOOLEAN DEFAULT 0")
        conn.commit()
    
    try:
        c.execute("SELECT buyer_rated FROM mediations LIMIT 1")
    except sqlite3.OperationalError:
        print("⚙️ Running migration: adding buyer_rated column...")
        c.execute("ALTER TABLE mediations ADD COLUMN buyer_rated BOOLEAN DEFAULT 0")
        conn.commit()
    
    conn.commit()
    conn.close()


def save_alert_mapping(alert_msg_id: int, origin_chat_id: int, origin_msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "REPLACE INTO alerts_map (alert_msg_id, origin_chat_id, origin_msg_id) VALUES (?, ?, ?)",
        (alert_msg_id, origin_chat_id, origin_msg_id)
    )
    conn.commit()
    conn.close()


def get_origin_by_alert(alert_msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT origin_chat_id, origin_msg_id FROM alerts_map WHERE alert_msg_id = ?", (alert_msg_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0]), int(row[1])
    return None


def save_mediation(origin_chat_id: int, origin_msg_id: int, parsed_data: dict, seller_id: int = None, buyer_id: int = None, creator_user_id: int = None):
    """Save or update mediation in database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT created_at FROM mediations WHERE origin_chat_id = ? AND origin_msg_id = ?",
              (origin_chat_id, origin_msg_id))
    existing = c.fetchone()
    
    if existing:
        c.execute("""
            UPDATE mediations 
            SET seller = ?, buyer = ?, seller_id = ?, buyer_id = ?, creator_user_id = ?, item = ?, payment_method = ?, amount = ?, status = ?
            WHERE origin_chat_id = ? AND origin_msg_id = ?
        """, (
            parsed_data.get("البايع", ""),
            parsed_data.get("المشتري", ""),
            seller_id,
            buyer_id,
            creator_user_id,
            parsed_data.get("السلعه", ""),
            parsed_data.get("طريقة الدفع", ""),
            parsed_data.get("المبلغ", ""),
            "active",
            origin_chat_id, origin_msg_id
        ))
    else:
        c.execute("""
            INSERT INTO mediations 
            (origin_chat_id, origin_msg_id, seller, buyer, seller_id, buyer_id, creator_user_id, item, payment_method, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            origin_chat_id, origin_msg_id,
            parsed_data.get("البايع", ""),
            parsed_data.get("المشتري", ""),
            seller_id,
            buyer_id,
            creator_user_id,
            parsed_data.get("السلعه", ""),
            parsed_data.get("طريقة الدفع", ""),
            parsed_data.get("المبلغ", ""),
            "active"
        ))
    
    conn.commit()
    conn.close()


def mark_mediation_delivered(origin_chat_id: int, origin_msg_id: int):
    """Mark mediation as delivered"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE mediations 
        SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP
        WHERE origin_chat_id = ? AND origin_msg_id = ?
    """, (origin_chat_id, origin_msg_id))
    conn.commit()
    conn.close()


def mark_mediation_completed(origin_chat_id: int, origin_msg_id: int, rating_msg_id: Optional[int] = None):
    """Mark mediation as completed"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if rating_msg_id:
        c.execute("""
            UPDATE mediations 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP, rating_msg_id = ?
            WHERE origin_chat_id = ? AND origin_msg_id = ?
        """, (rating_msg_id, origin_chat_id, origin_msg_id))
    else:
        c.execute("""
            UPDATE mediations 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE origin_chat_id = ? AND origin_msg_id = ?
        """, (origin_chat_id, origin_msg_id))
    conn.commit()
    conn.close()


async def update_rating_status_async(client: Client, origin_chat_id: int, origin_msg_id: int, user_id: int, username: str = None):
    """Update rating status for a user (async version with lazy creator resolution)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT seller_id, buyer_id, seller, buyer, creator_user_id FROM mediations WHERE origin_chat_id = ? AND origin_msg_id = ?",
              (origin_chat_id, origin_msg_id))
    row = c.fetchone()
    
    if row:
        seller_id, buyer_id, seller_text, buyer_text, creator_user_id = row
        matched_as_seller = False
        matched_as_buyer = False
        
        is_ana_seller = "أنا" in str(seller_text) or "انا" in str(seller_text)
        is_ana_buyer = "أنا" in str(buyer_text) or "انا" in str(buyer_text)
        
        if (is_ana_seller or is_ana_buyer) and not creator_user_id:
            try:
                origin_msg = await client.get_messages(origin_chat_id, message_ids=origin_msg_id)
                if origin_msg and origin_msg.from_user:
                    creator_user_id = origin_msg.from_user.id
                    c.execute("UPDATE mediations SET creator_user_id = ? WHERE origin_chat_id = ? AND origin_msg_id = ?",
                             (creator_user_id, origin_chat_id, origin_msg_id))
                    conn.commit()
                    print(f"📝 Backfilled creator_user_id: {creator_user_id}")
            except Exception as e:
                print(f"⚠️ Failed to backfill creator_user_id: {e}")
        
        if seller_id and seller_id == user_id:
            matched_as_seller = True
        elif is_ana_seller and creator_user_id and creator_user_id == user_id:
            c.execute("UPDATE mediations SET seller_id = ? WHERE origin_chat_id = ? AND origin_msg_id = ?",
                     (user_id, origin_chat_id, origin_msg_id))
            matched_as_seller = True
        elif seller_text and username and f"@{username}" in seller_text:
            c.execute("UPDATE mediations SET seller_id = ? WHERE origin_chat_id = ? AND origin_msg_id = ?",
                     (user_id, origin_chat_id, origin_msg_id))
            matched_as_seller = True
        
        if buyer_id and buyer_id == user_id:
            matched_as_buyer = True
        elif is_ana_buyer and creator_user_id and creator_user_id == user_id:
            c.execute("UPDATE mediations SET buyer_id = ? WHERE origin_chat_id = ? AND origin_msg_id = ?",
                     (user_id, origin_chat_id, origin_msg_id))
            matched_as_buyer = True
        elif buyer_text and username and f"@{username}" in buyer_text:
            c.execute("UPDATE mediations SET buyer_id = ? WHERE origin_chat_id = ? AND origin_msg_id = ?",
                     (user_id, origin_chat_id, origin_msg_id))
            matched_as_buyer = True
        
        if matched_as_seller:
            c.execute("UPDATE mediations SET seller_rated = 1 WHERE origin_chat_id = ? AND origin_msg_id = ?",
                     (origin_chat_id, origin_msg_id))
            print(f"✅ Seller {user_id} (@{username}) marked as rated")
        elif matched_as_buyer:
            c.execute("UPDATE mediations SET buyer_rated = 1 WHERE origin_chat_id = ? AND origin_msg_id = ?",
                     (origin_chat_id, origin_msg_id))
            print(f"✅ Buyer {user_id} (@{username}) marked as rated")
    
    conn.commit()
    conn.close()


def update_rating_status(origin_chat_id: int, origin_msg_id: int, user_id: int, username: str = None):
    """Sync wrapper for backward compatibility"""
    import asyncio
    asyncio.create_task(update_rating_status_async(app, origin_chat_id, origin_msg_id, user_id, username))


def get_rating_status(origin_chat_id: int, origin_msg_id: int):
    """Get rating status for a mediation"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT seller_rated, buyer_rated, rating_msg_id FROM mediations WHERE origin_chat_id = ? AND origin_msg_id = ?",
              (origin_chat_id, origin_msg_id))
    row = c.fetchone()
    conn.close()
    if row:
        return {"seller_rated": bool(row[0]), "buyer_rated": bool(row[1]), "rating_msg_id": row[2]}
    return None


def get_all_mediations(limit=50):
    """Get all mediations ordered by most recent first"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, seller, buyer, item, amount, status, created_at, delivered_at, completed_at
        FROM mediations
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_completed_mediations_with_links(limit=5):
    """Get completed mediations with origin message IDs for links"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, origin_chat_id, origin_msg_id, completed_at
        FROM mediations
        WHERE status = 'completed'
        ORDER BY completed_at DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_unposted_completed_mediations():
    """Get completed mediations that haven't been posted yet"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT m.id, m.origin_chat_id, m.origin_msg_id
        FROM mediations m
        LEFT JOIN posted_mediations pm ON m.id = pm.mediation_id
        WHERE m.status = 'completed' AND pm.mediation_id IS NULL
        ORDER BY m.completed_at ASC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def mark_mediation_posted(mediation_id: int):
    """Mark mediation as posted"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO posted_mediations (mediation_id) VALUES (?)", (mediation_id,))
    conn.commit()
    conn.close()


def get_mediation_count():
    """Get total count of completed mediations"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM mediations WHERE status = 'completed'")
    count = c.fetchone()[0]
    conn.close()
    return count


FIELD_NAMES = ["البايع", "المشتري", "السلعه", "طريقة الدفع", "المبلغ"]
USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{5,})")


def parse_mediation_text(text: str):
    """Parse mediation message text"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    data = {}
    for name in FIELD_NAMES:
        found = None
        for ln in lines:
            if ln.startswith(name):
                parts = ln.split(":", 1)
                if len(parts) > 1:
                    found = parts[1].strip()
                break
        if not found:
            return None
        data[name] = found

    seller = None
    buyer = None
    s_match = USERNAME_RE.search(data["البايع"])
    b_match = USERNAME_RE.search(data["المشتري"])
    if s_match:
        seller = "@" + s_match.group(1)
    if b_match:
        buyer = "@" + b_match.group(1)

    data["__seller_text"] = data["البايع"]
    data["__buyer_text"] = data["المشتري"]
    data["__seller_username"] = seller
    data["__buyer_username"] = buyer
    return data


app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)


async def resolve_owner_ids():
    owner_ids = set()
    for uname in OWNER_USERNAMES:
        try:
            user = await app.get_users(uname)
            owner_ids.add(user.id)
        except Exception as e:
            print(f"[WARN] failed to resolve owner username @{uname}: {e}")
    return owner_ids


async def is_alert_chat(client: Client, chat_id: int) -> bool:
    """Check if the given chat_id matches ALERT_CHAT"""
    if ALERT_CHAT == "me":
        me = await client.get_me()
        return chat_id == me.id
    else:
        return chat_id == int(ALERT_CHAT)


@app.on_message(filters.chat(MONITOR_CHAT) & filters.text)
async def monitor_handler(client: Client, message: Message):
    """Monitor chat for new mediations"""
    parsed = parse_mediation_text(message.text or "")
    if not parsed:
        return

    creator_user_id = message.from_user.id if message.from_user else None
    
    me = await client.get_me()
    if creator_user_id != me.id:
        return

    seller_username = parsed.get("__seller_username")
    buyer_username = parsed.get("__buyer_username")
    seller_id = None
    buyer_id = None
    
    if seller_username:
        try:
            seller_user = await client.get_users(seller_username)
            seller_id = seller_user.id
        except Exception as e:
            print(f"Failed to get seller user ID: {e}")
    
    if buyer_username:
        try:
            buyer_user = await client.get_users(buyer_username)
            buyer_id = buyer_user.id
        except Exception as e:
            print(f"Failed to get buyer user ID: {e}")

    alert_text = (
        "🚨 وساطة جديدة 🚨\n\n"
        f"البايع : {parsed['البايع']}\n"
        f"المشتري : {parsed['المشتري']}\n"
        f"السلعة : {parsed['السلعه']}\n"
        f"طريقة الدفع : {parsed['طريقة الدفع']}\n"
        f"المبلغ : {parsed['المبلغ']}\n\n"
        "رد 'موافق' هنا لإضافة الطرفين كجهات اتصال (MM+*)."
    )

    try:
        sent = await client.send_message(ALERT_CHAT, alert_text)
        save_alert_mapping(sent.id, message.chat.id, message.id)
        save_mediation(message.chat.id, message.id, parsed, seller_id, buyer_id, creator_user_id)
    except Exception as e:
        print("Failed to send alert:", e)


async def resolve_parties_from_origin(client: Client, origin_chat_id: int, origin_msg_id: int):
    try:
        origin_msg = await client.get_messages(origin_chat_id, message_ids=origin_msg_id)
    except Exception as e:
        return None, None, f"فشل جلب رسالة الوساطة الأصلية: {e}"

    parsed = parse_mediation_text(origin_msg.text or "")
    if not parsed:
        return None, None, "تعذر تحليل نص الوساطة في الرسالة الأصلية."

    seller = parsed.get("__seller_username")
    buyer = parsed.get("__buyer_username")
    seller_text = parsed.get("__seller_text", "")
    buyer_text = parsed.get("__buyer_text", "")

    origin_sender = origin_msg.from_user
    if "أنا" in seller_text or "انا" in seller_text:
        if origin_sender and origin_sender.username:
            seller = "@" + origin_sender.username
        elif origin_sender:
            seller = origin_sender.id
    if "أنا" in buyer_text or "انا" in buyer_text:
        if origin_sender and origin_sender.username:
            buyer = "@" + origin_sender.username
        elif origin_sender:
            buyer = origin_sender.id

    return seller, buyer, None


async def add_contact_try(client: Client, username_or_id):
    """Add contact with MM +*** prefix - using username/id only, ignoring phone number"""
    try:
        entity = None
        if isinstance(username_or_id, int):
            entity = await client.get_users(username_or_id)
        else:
            entity = await client.get_users(username_or_id)

        current_first_name = getattr(entity, "first_name", "") or ""
        current_last_name = getattr(entity, "last_name", "") or ""
        
        new_first_name = f"MM +*** {current_first_name}"
        new_last_name = current_last_name if current_last_name else ""

        try:
            await client.invoke(raw_functions.contacts.AddContact(
                id=await client.resolve_peer(entity.id),
                first_name=new_first_name,
                last_name=new_last_name,
                phone=""
            ))
            return True, f"تمت إضافة {getattr(entity,'username',entity.id)} بنجاح."
        except Exception as e1:
            try:
                await client.add_contact(entity.id, new_first_name, new_last_name or "")
                return True, f"تمت إضافة {getattr(entity,'username',entity.id)} (fallback)."
            except Exception as e2:
                return False, f"فشل إضافة جهة الاتصال: {e2}"
    except RPCError as e:
        return False, f"خطأ من Telegram: {e}"
    except Exception as e:
        return False, f"خطأ عام أثناء إضافة جهة الاتصال: {e}"


async def delete_contact_by_user(client: Client, username_or_id):
    """Delete a specific contact by username or user ID"""
    try:
        entity = None
        if isinstance(username_or_id, int):
            entity = await client.get_users(username_or_id)
        else:
            entity = await client.get_users(username_or_id)
        
        await client.invoke(raw_functions.contacts.DeleteContacts(
            id=[await client.resolve_peer(entity.id)]
        ))
        return True, f"تم حذف {getattr(entity,'username',entity.id)} من جهات الاتصال"
    except Exception as e:
        return False, f"فشل حذف جهة الاتصال: {e}"


async def reminder_task(client: Client, origin_chat_id: int, origin_msg_id: int, rating_msg_id: int):
    """Send reminders every 5 minutes until both parties have rated"""
    task_key = f"{origin_chat_id}_{origin_msg_id}"
    
    while task_key in reminder_tasks:
        await asyncio.sleep(300)
        
        if task_key not in reminder_tasks:
            break
        
        status = get_rating_status(origin_chat_id, origin_msg_id)
        if not status:
            break
        
        if status["seller_rated"] and status["buyer_rated"]:
            print(f"Both parties rated for mediation {task_key}, stopping reminders")
            break
        
        seller, buyer, err = await resolve_parties_from_origin(client, origin_chat_id, origin_msg_id)
        if err:
            break
        
        reminder_messages = []
        if not status["seller_rated"] and seller:
            reminder_messages.append(f"تقيـيمك علـى الوساطه يابـعدي 🍂 {seller}")
        if not status["buyer_rated"] and buyer:
            reminder_messages.append(f"تقيـيمك علـى الوساطه يابـعدي 🍂 {buyer}")
        
        if reminder_messages:
            reminder_text = "\n".join(reminder_messages)
            try:
                await client.send_message(
                    origin_chat_id, 
                    reminder_text,
                    reply_to_message_id=rating_msg_id
                )
            except Exception as e:
                print(f"Failed to send reminder: {e}")
    
    if task_key in reminder_tasks:
        del reminder_tasks[task_key]


async def post_mediations_task(client: Client):
    """Post completed mediations to channel every 5 minutes"""
    if not POSTING_CHANNEL:
        print("⚠️ POSTING_CHANNEL not configured, skipping posting task")
        return
    
    while True:
        await asyncio.sleep(300)
        
        unposted = get_unposted_completed_mediations()
        
        for mediation_id, origin_chat_id, origin_msg_id in unposted:
            try:
                origin_msg = await client.get_messages(origin_chat_id, message_ids=origin_msg_id)
                parsed = parse_mediation_text(origin_msg.text or "")
                
                if parsed:
                    total_count = get_mediation_count()
                    
                    heart_emoji = f'<emoji id="{get_emoji_id("heart")}">🫀</emoji>'
                    check_emoji = f'<emoji id="{get_emoji_id("check")}">✅</emoji>'
                    
                    hearts = " ".join([heart_emoji] * 8)
                    
                    post_text = (
                        f"MM Rep's | {total_count} {check_emoji}\n"
                        f"{hearts}\n"
                        f"https://t.me/{origin_msg.link.split('/')[-2]}/{origin_msg_id}"
                    )
                    
                    await client.send_message(
                        POSTING_CHANNEL,
                        post_text,
                        parse_mode=ParseMode.HTML
                    )
                    
                    mark_mediation_posted(mediation_id)
                    print(f"✅ Posted mediation {mediation_id} to channel")
                    await asyncio.sleep(2)
                    
            except Exception as e:
                print(f"Failed to post mediation {mediation_id}: {e}")


@app.on_message(filters.me & filters.private & filters.text)
async def alert_chat_handler(client: Client, message: Message):
    """Handle messages in ALERT_CHAT (Saved Messages)"""
    text = (message.text or "").strip()
    
    if not hasattr(app, "_owner_ids"):
        app._owner_ids = await resolve_owner_ids()

    sender = message.from_user
    sender_id = sender.id if sender else None

    if sender_id not in app._owner_ids:
        return

    if text == CMD_HELP:
        help_text = (
            "📋 <b>قائمة الأوامر</b> 📋\n\n"
            "<b>الأوامر الأساسية:</b>\n"
            "• <code>الاوامر</code> - عرض هذه القائمة\n"
            "• <code>الوساطات</code> - عرض جميع الوساطات\n"
            "• <code>اخر 5</code> - عرض روابط آخر 5 وساطات منتهية\n\n"
            "<b>أوامر الإدارة:</b>\n"
            "• <code>موافق</code> - إضافة جهات الاتصال (رد على وساطة)\n"
            "• <code>تسليم</code> - تأكيد التسليم\n"
            "• <code>انهاء</code> - إنهاء الوساطة وحذف جهات الاتصال\n\n"
            "<b>أوامر التذكير والنشر:</b>\n"
            "• <code>بدا التذكير</code> - بدء التذكير بالتقييم\n"
            "• <code>توقيف التذكير</code> - إيقاف التذكير بالتقييم\n"
            "• <code>تنزيل الواسطات</code> - بدء نشر الوساطات تلقائياً\n\n"
            "<b>أوامر الأسئلة:</b>\n"
            "• <code>ايبك</code> - أسئلة حسابات إيبك\n"
            "• <code>تيك تيك</code> - أسئلة حسابات تيك توك\n"
            "• <code>روب</code> - أسئلة حسابات روبلوكس\n"
            "• <code>رقم</code> - أسئلة أرقام الهواتف"
        )
        await client.send_message(ALERT_CHAT, help_text, parse_mode=ParseMode.HTML)
        return

    if text == CMD_LAST_5:
        mediations = get_completed_mediations_with_links(limit=5)
        
        if not mediations:
            await client.send_message(ALERT_CHAT, "لا توجد وساطات منتهية حالياً.")
            return
        
        response = "📊 <b>روابط آخر 5 وساطات منتهية</b> 📊\n\n"
        
        for i, med in enumerate(mediations, 1):
            med_id, origin_chat_id, origin_msg_id, completed_at = med
            
            try:
                chat_username = str(origin_chat_id).replace('-100', '')
                link = f"https://t.me/c/{chat_username}/{origin_msg_id}"
                response += f"{i}. <a href='{link}'>الوساطة #{med_id}</a>\n"
            except Exception as e:
                response += f"{i}. الوساطة #{med_id} (فشل إنشاء الرابط)\n"
        
        await client.send_message(ALERT_CHAT, response, parse_mode=ParseMode.HTML)
        return

    if text == CMD_POST_MEDIATIONS:
        if not POSTING_CHANNEL:
            await client.send_message(ALERT_CHAT, "⚠️ لم يتم تعيين قناة النشر (POSTING_CHANNEL) في ملف .env")
            return
        
        if not hasattr(app, "_posting_task") or app._posting_task is None:
            app._posting_task = asyncio.create_task(post_mediations_task(client))
            await client.send_message(ALERT_CHAT, "✅ تم بدء نظام تنزيل الواسطات التلقائي (كل 5 دقائق)")
        else:
            await client.send_message(ALERT_CHAT, "⚠️ نظام التنزيل قيد التشغيل بالفعل")
        return

    if text == CMD_LIST_MEDIATIONS:
        mediations = get_all_mediations(limit=50)
        
        if not mediations:
            await client.send_message(ALERT_CHAT, "لا توجد وساطات مسجلة حالياً.")
            return
        
        active = []
        delivered = []
        completed = []
        
        for med in mediations:
            med_id, seller, buyer, item, amount, status, created_at, delivered_at, completed_at = med
            
            med_text = (
                f"<b>#{med_id}</b>\n"
                f"البايع: {seller}\n"
                f"المشتري: {buyer}\n"
                f"السلعة: {item}\n"
                f"المبلغ: {amount}\n"
                f"التاريخ: {created_at[:16] if created_at else 'N/A'}"
            )
            
            if status == "completed":
                completed.append(med_text)
            elif status == "delivered":
                delivered.append(med_text)
            else:
                active.append(med_text)
        
        response = "📊 <b>قائمة الوساطات</b> 📊\n\n"
        
        if active:
            response += f"<b>🟢 نشطة ({len(active)}):</b>\n"
            response += "─" * 30 + "\n"
            for i, med in enumerate(active[:10], 1):
                response += f"{i}. {med}\n{'-' * 25}\n"
            if len(active) > 10:
                response += f"... و {len(active) - 10} أخرى\n"
            response += "\n"
        
        if delivered:
            response += f"<b>🟡 تم التسليم ({len(delivered)}):</b>\n"
            response += "─" * 30 + "\n"
            for i, med in enumerate(delivered[:5], 1):
                response += f"{i}. {med}\n{'-' * 25}\n"
            if len(delivered) > 5:
                response += f"... و {len(delivered) - 5} أخرى\n"
            response += "\n"
        
        if completed:
            response += f"<b>✅ منتهية ({len(completed)}):</b>\n"
            response += "─" * 30 + "\n"
            for i, med in enumerate(completed[:5], 1):
                response += f"{i}. {med}\n{'-' * 25}\n"
            if len(completed) > 5:
                response += f"... و {len(completed) - 5} أخرى\n"
        
        if len(response) > 4000:
            response = response[:3900] + "\n\n... (الرسالة طويلة جداً، تم الاختصار)"
        
        await client.send_message(ALERT_CHAT, response, parse_mode=ParseMode.HTML)
        return

    if text == APPROVE_KEYWORD:
        found = None
        async for prev in client.get_chat_history(ALERT_CHAT, limit=30):
            if prev.id == message.id:
                continue
            if prev.text and "وساطة جديدة" in prev.text:
                found = prev
                break
        if not found:
            await client.send_message(ALERT_CHAT, "لم أجد رسالة وساطة سابقة لأكمل الإجراء عليها.")
            return

        mapping = get_origin_by_alert(found.id)
        if mapping:
            origin_chat_id, origin_msg_id = mapping
        else:
            await client.send_message(ALERT_CHAT, "لا يوجد ارتباط محفوظ للرسالة — تأكد أن الرسالة أرسلت بواسطة البوت.")
            return

        seller, buyer, err = await resolve_parties_from_origin(client, origin_chat_id, origin_msg_id)
        if err:
            await client.send_message(ALERT_CHAT, err)
            return

        results = []
        if seller:
            ok, info = await add_contact_try(client, seller)
            results.append((seller, ok, info))
        else:
            results.append(("البايع", False, "لم يتم العثور على البايع"))
        if buyer:
            ok2, info2 = await add_contact_try(client, buyer)
            results.append((buyer, ok2, info2))
        else:
            results.append(("المشتري", False, "لم يتم العثور على المشتري"))

        lines = ["نتيجة محاولة إضافة جهات الاتصال:"]
        for who, ok, info in results:
            status = "✅ ناجح" if ok else "❌ فشل"
            lines.append(f"- {who} : {status} — {info}")
        await client.send_message(ALERT_CHAT, "\n".join(lines))
        return

    if text == CMD_START_REMINDER and message.reply_to_message:
        reply = message.reply_to_message
        origin_chat_id = None
        origin_msg_id = None

        mapping = get_origin_by_alert(reply.id)
        if mapping:
            origin_chat_id, origin_msg_id = mapping
        else:
            if reply.chat.id == MONITOR_CHAT:
                origin_chat_id, origin_msg_id = reply.chat.id, reply.id

        if not origin_chat_id or not origin_msg_id:
            await client.send_message(ALERT_CHAT, "ما قدرت أحدد رسالة الوساطة الأصلية.")
            return

        task_key = f"{origin_chat_id}_{origin_msg_id}"
        if task_key in reminder_tasks:
            await client.send_message(ALERT_CHAT, "⚠️ نظام التذكير قيد التشغيل بالفعل لهذه الوساطة")
            return

        seller, buyer, err = await resolve_parties_from_origin(client, origin_chat_id, origin_msg_id)
        if err:
            await client.send_message(ALERT_CHAT, err)
            return

        done_emoji = f'<emoji id="{get_emoji_id("done")}">✅</emoji>'
        rating_emoji = f'<emoji id="{get_emoji_id("rating")}">⚡️</emoji>'
        market_emoji = f'<emoji id="{get_emoji_id("market")}">⏰</emoji>'
        
        rating_message = (
            f"<b>MM Done</b> {done_emoji}\n"
            f"<b>Your rating for @h_7_m</b> {rating_emoji}\n\n"
            f"<b>Market MM @slomw</b> {market_emoji}\n\n"
            f"{seller} × {buyer}"
        )

        sent_rating = await client.send_message(
            origin_chat_id, 
            rating_message,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=origin_msg_id
        )
        
        mark_mediation_completed(origin_chat_id, origin_msg_id, sent_rating.id)
        
        reminder_tasks[task_key] = asyncio.create_task(
            reminder_task(client, origin_chat_id, origin_msg_id, sent_rating.id)
        )
        
        await client.send_message(ALERT_CHAT, "✅ تم بدء نظام التذكير (كل 5 دقائق حتى يقيم الطرفان)")
        return

    if text == CMD_STOP_REMINDER and message.reply_to_message:
        reply = message.reply_to_message
        origin_chat_id = None
        origin_msg_id = None

        mapping = get_origin_by_alert(reply.id)
        if mapping:
            origin_chat_id, origin_msg_id = mapping
        else:
            if reply.chat.id == MONITOR_CHAT:
                origin_chat_id, origin_msg_id = reply.chat.id, reply.id

        if not origin_chat_id or not origin_msg_id:
            await client.send_message(ALERT_CHAT, "ما قدرت أحدد رسالة الوساطة الأصلية.")
            return

        task_key = f"{origin_chat_id}_{origin_msg_id}"
        if task_key in reminder_tasks:
            del reminder_tasks[task_key]
            await client.send_message(ALERT_CHAT, "✅ تم إيقاف نظام التذكير لهذه الوساطة")
        else:
            await client.send_message(ALERT_CHAT, "⚠️ لا يوجد نظام تذكير نشط لهذه الوساطة")
        return

    if text == CMD_DONE and message.reply_to_message:
        reply = message.reply_to_message
        origin_chat_id = None
        origin_msg_id = None

        mapping = get_origin_by_alert(reply.id)
        if mapping:
            origin_chat_id, origin_msg_id = mapping
        else:
            if reply.chat.id == MONITOR_CHAT:
                origin_chat_id, origin_msg_id = reply.chat.id, reply.id

        if not origin_chat_id or not origin_msg_id:
            await client.send_message(ALERT_CHAT, "ما قدرت أحدد رسالة الوساطة الأصلية المرتبطة للانهاء.")
            return

        seller, buyer, err = await resolve_parties_from_origin(client, origin_chat_id, origin_msg_id)
        if err:
            await client.send_message(ALERT_CHAT, err)
            return

        results = []
        if seller:
            ok, info = await delete_contact_by_user(client, seller)
            results.append((seller, ok, info))
        if buyer:
            ok2, info2 = await delete_contact_by_user(client, buyer)
            results.append((buyer, ok2, info2))

        done_emoji = f'<emoji id="{get_emoji_id("done")}">✅</emoji>'
        rating_emoji = f'<emoji id="{get_emoji_id("rating")}">⚡️</emoji>'
        market_emoji = f'<emoji id="{get_emoji_id("market")}">⏰</emoji>'
        
        rating_message = (
            f"<b>MM Done</b> {done_emoji}\n"
            f"<b>Your rating for @h_7_m</b> {rating_emoji}\n\n"
            f"<b>Market MM @slomw</b> {market_emoji}\n\n"
            f"{seller} × {buyer}"
        )

        await client.send_message(
            ALERT_CHAT, 
            rating_message,
            parse_mode=ParseMode.HTML
        )
        
        mark_mediation_completed(origin_chat_id, origin_msg_id)
        
        lines = ["\n✅ تم إنهاء الوساطة وحذف جهات الاتصال:"]
        for who, ok, info in results:
            status = "✅" if ok else "❌"
            lines.append(f"{status} {who}: {info}")
        await client.send_message(ALERT_CHAT, "\n".join(lines))
        
        return

    if text == CMD_DELIVER and message.reply_to_message:
        reply = message.reply_to_message
        origin_chat_id = None
        origin_msg_id = None

        mapping = get_origin_by_alert(reply.id)
        if mapping:
            origin_chat_id, origin_msg_id = mapping
        else:
            if reply.chat.id == MONITOR_CHAT:
                origin_chat_id, origin_msg_id = reply.chat.id, reply.id

        if not origin_chat_id or not origin_msg_id:
            await client.send_message(ALERT_CHAT, "ما قدرت أحدد رسالة الوساطة الأصلية.")
            return

        try:
            origin_msg = await client.get_messages(origin_chat_id, message_ids=origin_msg_id)
        except Exception as e:
            await client.send_message(ALERT_CHAT, f"فشل جلب رسالة الوساطة: {e}")
            return

        parsed = parse_mediation_text(origin_msg.text or "")
        if not parsed:
            await client.send_message(ALERT_CHAT, "تعذر تحليل نص الوساطة")
            return

        seller = parsed.get("__seller_username")
        buyer = parsed.get("__buyer_username")
        seller_text = parsed.get("__seller_text", "")
        buyer_text = parsed.get("__buyer_text", "")

        origin_sender = origin_msg.from_user
        if "أنا" in seller_text or "انا" in seller_text:
            if origin_sender and origin_sender.username:
                seller = "@" + origin_sender.username
            elif origin_sender:
                seller = origin_sender.id
        if "أنا" in buyer_text or "انا" in buyer_text:
            if origin_sender and origin_sender.username:
                buyer = "@" + origin_sender.username
            elif origin_sender:
                buyer = origin_sender.id

        amount = parsed.get("المبلغ", "").strip()
        if not amount:
            await client.send_message(ALERT_CHAT, "لم أجد مبلغ واضح في رسالة الوساطة.")
            return

        warning_emoji = f'<emoji id="{get_emoji_id("deliver_warning")}">⚠️</emoji>'
        
        text_message = (
            f"وصـل مبلغ سلـمه • <b>{{طرفيـن صـورو فـيديو عنـد الاستـلام و التسـليم لـ تـجنب المـشاكل{warning_emoji}}}</b>\n( {seller} x {buyer} )"
        )

        await client.send_message(
            origin_chat_id,
            text_message,
            parse_mode=ParseMode.HTML
        )
        
        mark_mediation_delivered(origin_chat_id, origin_msg_id)
        await client.send_message(ALERT_CHAT, "✅ تم إرسال رسالة التسليم")
        return

    if text in [CMD_EPIC, CMD_TIKTOK, CMD_ROB, CMD_NUMBER]:
        seller = None
        buyer = None
        
        found = None
        async for prev in client.get_chat_history(ALERT_CHAT, limit=30):
            if prev.id == message.id:
                continue
            if prev.text and "وساطة جديدة" in prev.text:
                found = prev
                break
        
        if found:
            mapping = get_origin_by_alert(found.id)
            if mapping:
                origin_chat_id, origin_msg_id = mapping
                seller, buyer, _ = await resolve_parties_from_origin(client, origin_chat_id, origin_msg_id)
        
        parties_text = f"\n( {seller} x {buyer} )" if seller and buyer else ""
        
        questions_map = {
            CMD_EPIC: (
                "الحساب ضمان سحب وحظر مدى؟\n"
                "أساسي؟\n"
                "وش وضع إنشاء؟\n"
                "يربط كل شي؟\n"
                "هل قد جاه طلب استرداد؟\n"
                "وش دومين الحساب؟\n"
                "معاه ملف المعلومات وجاهزة؟\n"
                "ولا فيها مشاكل بالربط ولا مربوط برقم"
            ),
            CMD_TIKTOK: (
                "ضمان سحب وحظر مدى ومافيه ربط خارجي ولا مربوط برقم ولا مشاكل بالربط وسليم وانشاء ولالا"
            ),
            CMD_ROB: (
                "شحن محفظة؟\n"
                "ربط نظيف؟\n"
                "ضمان من التصفير؟"
            ),
            CMD_NUMBER: (
                "ضمان؟\n"
                "سحب؟\n"
                "حظر؟\n"
                "في شروط بينكم ولا؟"
            )
        }
        
        await client.send_message(ALERT_CHAT, questions_map[text] + parties_text)
        return


@app.on_message(filters.chat(MONITOR_CHAT) & filters.reply)
async def rating_detector(client: Client, message: Message):
    """Detect when users reply to rating messages to mark them as rated"""
    if not message.reply_to_message or not message.from_user:
        return
    
    reply_to_msg = message.reply_to_message
    reply_text = reply_to_msg.text or ""
    
    if "MM Done" in reply_text and "Your rating for" in reply_text:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT origin_chat_id, origin_msg_id FROM mediations WHERE rating_msg_id = ?",
                  (reply_to_msg.id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            origin_chat_id, origin_msg_id = row
            username = message.from_user.username if message.from_user else None
            await update_rating_status_async(client, origin_chat_id, origin_msg_id, message.from_user.id, username)
            print(f"✅ Detected rating from user {message.from_user.id} (@{username})")


@app.on_message(filters.text & filters.chat(MONITOR_CHAT) & ~filters.reply)
async def monitor_questions_handler(client: Client, message: Message):
    """Handle question commands in monitor chat without needing a reply"""
    text = (message.text or "").strip()
    
    questions_map = {
        CMD_EPIC: (
            "الحساب ضمان سحب وحظر مدى؟\n"
            "أساسي؟\n"
            "وش وضع إنشاء؟\n"
            "يربط كل شي؟\n"
            "هل قد جاه طلب استرداد؟\n"
            "وش دومين الحساب؟\n"
            "معاه ملف المعلومات وجاهزة؟\n"
            "ولا فيها مشاكل بالربط ولا مربوط برقم"
        ),
        CMD_TIKTOK: (
            "ضمان سحب وحظر مدى ومافيه ربط خارجي ولا مربوط برقم ولا مشاكل بالربط وسليم وانشاء ولالا"
        ),
        CMD_ROB: (
            "شحن محفظة؟\n"
            "ربط نظيف؟\n"
            "ضمان من التصفير؟"
        ),
        CMD_NUMBER: (
            "ضمان؟\n"
            "سحب؟\n"
            "حظر؟\n"
            "في شروط بينكم ولا؟"
        )
    }
    
    if text in questions_map:
        await client.send_message(message.chat.id, questions_map[text])


@app.on_message(filters.text & filters.chat(MONITOR_CHAT) & filters.reply)
async def monitor_reply_handler(client: Client, message: Message):
    """Handle commands in monitor chat when replying to a mediation message"""
    text = (message.text or "").strip()
    
    if not message.reply_to_message:
        return
    
    origin_chat_id = message.reply_to_message.chat.id
    origin_msg_id = message.reply_to_message.id
    
    try:
        origin_msg = await client.get_messages(origin_chat_id, message_ids=origin_msg_id)
    except Exception:
        return

    parsed = parse_mediation_text(origin_msg.text or "")
    if not parsed:
        return

    seller = parsed.get("__seller_username")
    buyer = parsed.get("__buyer_username")
    seller_text = parsed.get("__seller_text", "")
    buyer_text = parsed.get("__buyer_text", "")

    origin_sender = origin_msg.from_user
    if "أنا" in seller_text or "انا" in seller_text:
        if origin_sender and origin_sender.username:
            seller = "@" + origin_sender.username
        elif origin_sender:
            seller = origin_sender.id
    if "أنا" in buyer_text or "انا" in buyer_text:
        if origin_sender and origin_sender.username:
            buyer = "@" + origin_sender.username
        elif origin_sender:
            buyer = origin_sender.id

    def parties_bar(slr, byr):
        return f"( {slr} x {byr} )"

    if text == CMD_EPIC:
        reply_text = (
            "الحساب ضمان سحب وحظر مدى؟\n"
            "أساسي؟\n"
            "وش وضع إنشاء؟\n"
            "يربط كل شي؟\n"
            "هل قد جاه طلب استرداد؟\n"
            "وش دومين الحساب؟\n"
            "معاه ملف المعلومات وجاهزة؟\n"
            "ولا فيها مشاكل بالربط ولا مربوط برقم\n"
        )
        reply_text += parties_bar(seller, buyer)
        await client.send_message(origin_chat_id, reply_text)
        return

    if text == CMD_TIKTOK:
        reply_text = (
            "ضمان سحب وحظر مدى ومافيه ربط خارجي ولا مربوط برقم ولا مشاكل بالربط وسليم وانشاء ولالا\n"
        )
        reply_text += parties_bar(seller, buyer)
        await client.send_message(origin_chat_id, reply_text)
        return

    if text == CMD_ROB:
        reply_text = (
            "شحن محفظة؟\n"
            "ربط نظيف؟\n"
            "ضمان من التصفير؟\n"
        )
        reply_text += parties_bar(seller, buyer)
        await client.send_message(origin_chat_id, reply_text)
        return

    if text == CMD_NUMBER:
        reply_text = (
            "ضمان؟\n"
            "سحب؟\n"
            "حظر؟\n"
            "في شروط بينكم ولا؟\n"
        )
        reply_text += parties_bar(seller, buyer)
        await client.send_message(origin_chat_id, reply_text)
        return

    if text == CMD_DELIVER:
        amount = parsed.get("المبلغ", "").strip()
        if not amount:
            await client.send_message(origin_chat_id, "لم أجد مبلغ واضح في رسالة الوساطة.")
            return

        warning_emoji = f'<emoji id="{get_emoji_id("deliver_warning")}">⚠️</emoji>'
        
        text_message = (
            f"وصـل مبلغ سلـمه • <b>{{طرفيـن صـورو فـيديو عنـد الاستـلام و التسـليم لـ تـجنب المـشاكل{warning_emoji}}}</b>\n{parties_bar(seller, buyer)}"
        )

        await client.send_message(
            origin_chat_id,
            text_message,
            parse_mode=ParseMode.HTML
        )
        
        mark_mediation_delivered(origin_chat_id, origin_msg_id)
        return


async def startup():
    """Initialize the bot and resolve chat peers"""
    await app.start()
    print("✅ Bot started successfully")
    
    load_emojis()
    
    try:
        chat = await app.get_chat(MONITOR_CHAT)
        print(f"✅ Monitor chat resolved: {chat.title or chat.first_name or MONITOR_CHAT}")
    except Exception as e:
        print(f"⚠️ Warning: Could not resolve monitor chat: {e}")
        print("Make sure the bot account is a member of the monitor chat.")
    
    app._owner_ids = await resolve_owner_ids()
    print(f"✅ Resolved {len(app._owner_ids)} owner(s)")
    
    app._posting_task = None
    
    print("🎉 Bot is ready and listening for mediations!")
    await idle()
    await app.stop()


if __name__ == "__main__":
    init_db()
    print("✅ Database initialized")
    print("🚀 Starting userbot...")
    print(f"📡 Monitoring chat: {MONITOR_CHAT}")
    print(f"🔔 Alerts sent to: {ALERT_CHAT}")
    print(f"📢 Posting channel: {POSTING_CHANNEL}")
    app.run(startup())
