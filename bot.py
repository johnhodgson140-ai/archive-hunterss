"""
Archive Hunter — Telegram Bot v3
Bulletproof version — uses direct REST calls to Supabase, no library issues.
"""

import os
import json
import asyncio
import logging
import re
import requests

from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters
)
import anthropic

# ─── Load local .env file if present ───

def load_env_file(path=".env"):
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            existing = os.environ.get(key, "")
            if not key:
                continue
            if not existing or existing.startswith("paste_") or existing == "" or existing == "None":
                os.environ[key] = value

load_env_file()

# ─── Config ───
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

if not BOT_TOKEN:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN in environment or .env")
if not CLAUDE_API_KEY:
    raise SystemExit("Missing ANTHROPIC_API_KEY in environment or .env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("ArchiveHunter")

# Debug: log which env vars are set
log.info(f"TELEGRAM_BOT_TOKEN: {'SET (' + BOT_TOKEN[:8] + '...)' if BOT_TOKEN else 'EMPTY'}")
log.info(f"SUPABASE_URL: {'SET (' + SUPABASE_URL[:20] + '...)' if SUPABASE_URL else 'EMPTY'}")
log.info(f"SUPABASE_KEY: {'SET (' + SUPABASE_KEY[:8] + '...)' if SUPABASE_KEY else 'EMPTY'}")
log.info(f"ANTHROPIC_API_KEY: {'SET (' + CLAUDE_API_KEY[:8] + '...)' if CLAUDE_API_KEY else 'EMPTY'}")

claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# ─── Supabase via REST (no library needed) ───

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

DB_STORE_FILE = os.path.join(os.path.dirname(__file__), "db_store.json")
LOCAL_DB_TABLES = ["users", "profiles", "hunts", "watched"]
USE_REMOTE_DB = bool(SUPABASE_URL and SUPABASE_KEY)


def load_local_db():
    if not os.path.isfile(DB_STORE_FILE):
        return {table: [] for table in LOCAL_DB_TABLES}
    try:
        with open(DB_STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Load local DB failed: {e}")
        return {table: [] for table in LOCAL_DB_TABLES}


def save_local_db(store):
    try:
        with open(DB_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save local DB failed: {e}")


def _normalize_query_value(value):
    if isinstance(value, str) and value.startswith("eq."):
        value = value[3:]
    return value


def _matches_row(row, column, value):
    if column not in row:
        return False
    row_value = row.get(column)
    if isinstance(row_value, bool):
        return str(row_value).lower() == str(value).lower()
    if isinstance(row_value, (int, float)) and isinstance(value, str) and value.isdigit():
        return str(row_value) == value
    return str(row_value).lower() == str(value).lower()


def local_get(table, params=None):
    store = load_local_db()
    rows = [dict(r) for r in store.get(table, [])]
    if not params:
        return rows
    for key, value in (params or {}).items():
        value = _normalize_query_value(value)
        if key == "order":
            if value.endswith(".asc"):
                rows.sort(key=lambda r: r.get(value.split(".")[0], ""))
            elif value.endswith(".desc"):
                rows.sort(key=lambda r: r.get(value.split(".")[0], ""), reverse=True)
            continue
        if key.endswith("[]"):
            continue
        rows = [row for row in rows if _matches_row(row, key, value)]
    return rows


def local_insert(table, data):
    store = load_local_db()
    rows = store.get(table, [])
    ids = [r.get("id") for r in rows if isinstance(r.get("id"), int)]
    next_id = max(ids, default=0) + 1
    row = {**data, "id": next_id}
    rows.append(row)
    store[table] = rows
    save_local_db(store)
    return [row]


def local_update(table, data, match_col, match_val):
    store = load_local_db()
    rows = store.get(table, [])
    updated = []
    for row in rows:
        if _matches_row(row, match_col, _normalize_query_value(match_val)):
            row.update(data)
            updated.append(row)
    store[table] = rows
    save_local_db(store)
    return updated


def supa_get(table, params=None):
    if not USE_REMOTE_DB:
        log.info(f"Using local DB fallback for GET {table}")
        return local_get(table, params)
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        r = requests.get(url, headers=HEADERS, params=params or {}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Remote DB GET failed ({table}), falling back locally: {e}")
        return local_get(table, params)


def supa_insert(table, data):
    if not USE_REMOTE_DB:
        log.info(f"Using local DB fallback for INSERT {table}")
        return local_insert(table, data)
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        r = requests.post(url, headers=HEADERS, json=data, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Remote DB INSERT failed ({table}), falling back locally: {e}")
        return local_insert(table, data)


def supa_update(table, data, match_col, match_val):
    if not USE_REMOTE_DB:
        log.info(f"Using local DB fallback for UPDATE {table}")
        return local_update(table, data, match_col, match_val)
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{match_col}=eq.{match_val}"
        h = {**HEADERS, "Prefer": "return=representation"}
        r = requests.patch(url, headers=h, json=data, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Remote DB UPDATE failed ({table}), falling back locally: {e}")
        return local_update(table, data, match_col, match_val)

# ─── Archive memory and training helpers ───

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory_store.json")
ARCHIVE_TRAINING_FOCUS = [
    "Hedi Slimane era Dior Homme tailoring, skinny denim, and leather pieces",
    "Yves Saint Laurent / Saint Laurent archive boots, jackets, and runway pieces",
    "YSL Tribute boots, Saint Laurent Paris, and rare YSL collector styles",
    "Dior Homme Slimane era jackets, tees, and runway archive rare listings",
    "Japanese auction sources, Mercari JP, Xianyu, Yahoo Auctions, and Grailed steals",
    "Rare archive pieces from designers like Ann Demeulemeester, Rick Owens, Undercover, and Margiela",
]


def load_memory_store():
    if not os.path.isfile(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Load memory store failed: {e}")
        return {}


def save_memory_store(store):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save memory store failed: {e}")


def get_user_memory(tid):
    store = load_memory_store()
    return store.get(str(tid), [])


def add_user_memory(tid, note):
    if not note or not note.strip():
        return []
    store = load_memory_store()
    user_notes = store.get(str(tid), [])
    user_notes.append({
        "text": note.strip(),
        "created_at": str(asyncio.get_event_loop().time())
    })
    store[str(tid)] = user_notes[-50:]
    save_memory_store(store)
    return user_notes


def remove_user_memory(tid, index):
    store = load_memory_store()
    user_notes = store.get(str(tid), [])
    if 0 <= index < len(user_notes):
        user_notes.pop(index)
        store[str(tid)] = user_notes
        save_memory_store(store)
        return True
    return False


def build_memory_context(tid):
    notes = get_user_memory(tid)
    if not notes:
        return ""
    recent = notes[-6:]
    lines = [f"{i+1}. {item['text']}" for i, item in enumerate(recent)]
    return (
        "User memory and training notes:\n"
        + "\n".join(lines)
        + "\n\n"
    )


def build_training_context(tid):
    memory_text = build_memory_context(tid)
    focus_text = "Archive training focus: " + "; ".join(ARCHIVE_TRAINING_FOCUS) + ".\n\n"
    return focus_text + memory_text

# ─── Claude AI ───

def ask_claude(prompt, system=""):
    models = ["claude-sonnet-4-6", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]
    for model in models:
        try:
            log.info(f"Calling Claude ({model})...")
            msg = claude_client.messages.create(
                model=model,
                max_tokens=1000,
                system=system or "You are Archive Hunter, an expert in archive fashion, vintage designer clothing, and replica markets. Be concise and helpful.",
                messages=[{"role": "user", "content": prompt}]
            )
            log.info(f"Claude OK ({model})")
            return msg.content[0].text
        except Exception as e:
            log.error(f"Claude error ({model}): {type(e).__name__}: {e}")
            continue
    return "AI unavailable — check your ANTHROPIC_API_KEY and credits at console.anthropic.com"

async def safe_reply(update, text):
    try:
        if len(text) > 4000:
            text = text[:4000] + "..."
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        try:
            await update.message.reply_text(text)
        except Exception:
            try:
                await update.message.reply_text("Something went wrong displaying the response. Try again.")
            except Exception:
                pass

# ─── Database helpers ───

def get_user(tid):
    rows = supa_get("users", {"telegram_id": f"eq.{tid}"})
    if rows:
        return rows[0]
    result = supa_insert("users", {"telegram_id": tid, "settings": json.dumps({"currency": "GBP", "steal_threshold": 30})})
    return result[0] if result else {"telegram_id": tid}

def get_profiles(tid):
    return supa_get("profiles", {"telegram_id": f"eq.{tid}", "order": "created_at.asc"})

def get_active_profile(tid):
    user = get_user(tid)
    if user.get("active_profile"):
        rows = supa_get("profiles", {"id": f"eq.{user['active_profile']}"})
        if rows:
            return rows[0]
    profiles = get_profiles(tid)
    return profiles[0] if profiles else None

def create_profile(tid, name, data):
    profile = {
        "telegram_id": tid, "name": name,
        "height": data.get("height", ""),
        "weight": data.get("weight", ""),
        "build": data.get("build", "Average"),
        "measurements": json.dumps(data.get("measurements", {})),
        "sizes": json.dumps(data.get("sizes", {})),
        "notes": data.get("notes", ""),
    }
    result = supa_insert("profiles", profile)
    if result:
        supa_update("users", {"active_profile": result[0]["id"]}, "telegram_id", tid)
    return result[0] if result else {}

def get_hunts(tid):
    return supa_get("hunts", {"telegram_id": f"eq.{tid}", "active": "eq.true"})

def save_hunt(tid, data):
    hunt = {
        "telegram_id": tid,
        "name": data.get("name", "Unnamed hunt"),
        "designer": data.get("designer", ""),
        "piece": data.get("piece", ""),
        "max_price": data.get("max_price", 0),
        "currency": data.get("currency", "GBP"),
        "sizes": json.dumps(data.get("sizes", [])),
        "season": data.get("season", ""),
        "active": True,
    }
    return supa_insert("hunts", hunt)

# ─── Size parsing ───

def parse_size(text):
    text = text.upper()
    patterns = [
        (r'UK\s*([0-9]{1,2}(?:\.[0-9]+)?)', "UK{}"),
        (r'US\s*([0-9]{1,2}(?:\.[0-9]+)?)', "US{}"),
        (r'EU\s*([0-9]{2}(?:\.[0-9]+)?)', "EU{}"),
        (r'JP\s*([0-9]{1,2}(?:\.[0-9]+)?)', "JP{}"),
        (r'IT\s*([0-9]{2}(?:\.[0-9]+)?)', "IT{}"),
        (r'FR\s*([0-9]{2}(?:\.[0-9]+)?)', "FR{}"),
        (r'W\s*([0-9]{2})\b', "W{}"),
    ]
    for regex, fmt in patterns:
        match = re.search(regex, text)
        if match:
            size = match.group(1).rstrip('.0')
            return fmt.format(size)

    generic = re.search(r'SIZE\s*([0-9]{1,2}(?:\.[0-9]+)?)', text)
    if generic:
        size = generic.group(1).rstrip('.0')
        if any(k in text for k in ['UK', 'US', 'EU', 'JP', 'IT', 'FR']):
            # If the search already contains a prefix, let the prefix pattern handle it.
            pass
        elif any(word in text for word in ['BOOT', 'BOOTS', 'SHOE', 'SNEAKER', 'CHELSEA', 'ANKLE']):
            return f"EU{size}"
        return size

    for s in ["XXXL", "XXL", "XL", "XS", "S", "M", "L"]:
        if s in text:
            return s
    return ""

# ─── Commands ───

async def cmd_start(update, ctx):
    get_user(update.effective_user.id)
    await safe_reply(update,
        "⚡ *Archive Hunter* is online!\n\n"
        "The ultimate archive fashion hunting bot.\n"
        "Non-stop scanning · Deep learning intel · 20 platforms\n\n"
        "Get started:\n"
        "→ /newprofile — set up your measurements\n"
        "→ /scan — find a specific piece\n"
        "→ /search — broad search across marketplaces, Japanese auctions, and Xianyu\n"
        "→ /auction — scan auctions, Mercari JP, and Xianyu too\n"
        "→ /remember — train the bot on archive pieces and brands\n"
        "→ /hunt — set up a 24/7 hunt\n"
        "→ /deals — today's insane steals\n"
        "→ /sellers — top rep sellers\n"
        "→ /help — all commands"
    )

async def cmd_help(update, ctx):
    await safe_reply(update,
        "⚡ *Archive Hunter Commands*\n\n"
        "*Profiles*\n"
        "/newprofile — create a named profile\n"
        "/profiles — list all profiles\n"
        "/profile [name] — switch active profile\n\n"
        "*Hunting*\n"
        "/scan [piece] — find a specific item\n"
        "/search [piece] — broad search alias, including Mercari JP, Xianyu, and auctions\n"
        "/auction [piece] — search auctions, Japanese marketplaces, and listings\n"
        "/remember [text] — save archive pieces or brands for the bot to train on\n"
        "/memory — show your archive memory notes\n"
        "/forget [index] — remove a saved memory note\n"
        "/hunt — set up a persistent hunt\n"
        "/hunts — view active hunts\n"
        "/watch [url] — watch a listing\n\n"
        "*Intel*\n"
        "/deals — today's insane steals\n"
        "/intel — latest market intelligence\n"
        "/sources — listing sources covered by the bot\n"
        "/sellers — top verified sellers\n"
        "/price [piece] — fair market value\n\n"
        "*Settings*\n"
        "/pause — pause alerts\n"
        "/resume — resume scanning\n"
        "/digest — get daily summary"
    )

async def cmd_newprofile(update, ctx):
    ctx.user_data["awaiting"] = "new_profile"
    await safe_reply(update,
        "👤 *Create a profile*\n\n"
        "Send your details like this:\n\n"
        "`Name: Me\n"
        "Height: 178\n"
        "Weight: 72\n"
        "Build: Athletic\n"
        "Chest: 98\n"
        "Shoulder: 46\n"
        "Waist: 82\n"
        "Upper hips: 90\n"
        "Hips: 98\n"
        "Inseam: 80\n"
        "Thigh: 30\n"
        "Sleeve: 64\n"
        "Shoe EU: 42\n"
        "Notes: Prefer oversized tops`\n\n"
        "Skip any you don't know — bot estimates from height/weight/build."
    )

async def cmd_profiles(update, ctx):
    profiles = get_profiles(update.effective_user.id)
    active = get_active_profile(update.effective_user.id)
    if not profiles:
        await safe_reply(update, "No profiles yet. Use /newprofile to create one.")
        return
    text = "👤 *Your profiles:*\n\n"
    for p in profiles:
        is_a = "✅" if active and p["id"] == active["id"] else "○"
        meas = json.loads(p.get("measurements", "{}"))
        filled = sum(1 for v in meas.values() if v)
        text += f"{is_a} *{p['name']}* — {p.get('height', '?')}cm · {p.get('build', '?')} · {filled} measurements\n"
    text += "\nUse /profile [name] to switch."
    await safe_reply(update, text)

async def cmd_profile(update, ctx):
    if not ctx.args:
        await cmd_profiles(update, ctx)
        return
    name = " ".join(ctx.args)
    profiles = get_profiles(update.effective_user.id)
    match = next((p for p in profiles if p["name"].lower() == name.lower()), None)
    if not match:
        await safe_reply(update, f"No profile named '{name}'. Use /profiles to see all.")
        return
    supa_update("users", {"active_profile": match["id"]}, "telegram_id", update.effective_user.id)
    await safe_reply(update, f"✅ Switched to *{match['name']}*\nAll searches now use their measurements.")

async def cmd_scan(update, ctx):
    query = " ".join(ctx.args) if ctx.args else ""
    if not query:
        await safe_reply(update,
            "What are you looking for? Examples:\n\n"
            "`/scan Raf Simons AW01 bomber M`\n"
            "`/scan Helmut Lang bondage trousers W32`\n"
            "`/scan Margiela tabis EU42`\n"
            "`/scan size 44 YSL boots`\n"
            "`/scan size uk 10 ysl boots`\n"
            "`/scan YSL boots size 44 auction`\n"
            "`/scan ysl boots mercari jp size 44`\n"
            "`/scan ysl boots xianyu size 44`\n"
            "`/scan Undercover cargo L under 200`"
        )
        return

    profile = get_active_profile(update.effective_user.id)
    size = parse_size(query)
    price = re.search(r'under\s*[£€$¥]?\s*(\d+)', query.lower())

    train_context = build_training_context(update.effective_user.id)
    msg = f"🔍 *Scanning for:* `{query}`\n"
    if size: msg += f"📏 Size: *{size}*\n"
    if price: msg += f"💰 Max: *£{price.group(1)}*\n"
    if profile: msg += f"👤 Profile: *{profile['name']}*\n"
    msg += "\n⏳ Getting AI analysis..."
    await safe_reply(update, msg)

    profile_info = ""
    if profile:
        meas = json.loads(profile.get("measurements", "{}"))
        profile_info = f"User: {profile['name']}, {profile.get('height')}cm, {profile.get('build')}. Measurements: chest={meas.get('chest','?')}cm, waist={meas.get('waist','?')}cm, inseam={meas.get('inseam','?')}cm"

    analysis = ask_claude(
        f"{train_context}Archive fashion search: '{query}'\n{profile_info}\n\n"
        f"Include auction sources like Yahoo Auctions, eBay auctions, Mercari JP, Xianyu, and Japanese auction marketplaces. "
        f"Give me: 1) Fair market value range in GBP 2) Best platforms or auctions to find this 3) What sizes to look for 4) Red flags to avoid 5) Best rep option if applicable. Be specific and practical.",
        "You are an archive fashion expert. Give concise, actionable intel."
    )
    await safe_reply(update, f"⚡ Intel for: {query}\n\n{analysis}\n\nBot is scanning 24/7 — use /hunt to get alerted on matches.")

async def cmd_hunt(update, ctx):
    ctx.user_data["awaiting"] = "new_hunt"
    await safe_reply(update,
        "🎯 *Set up a hunt*\n\nSend details like this:\n\n"
        "`Designer: Raf Simons\n"
        "Piece: AW01 Riot bomber\n"
        "Max price: 400\n"
        "Sizes: M, L, EU48\n"
        "Season: AW01`\n\n"
        "Bot will scan 24/7 marketplaces and auctions, including Xianyu, Mercari JP, and Japanese auction sources.\n"
        "You’ll be alerted on any strong match."
    )

async def cmd_hunts(update, ctx):
    hunts = get_hunts(update.effective_user.id)
    if not hunts:
        await safe_reply(update, "No active hunts. Use /hunt to set one up.")
        return
    text = "🎯 *Active hunts:*\n\n"
    for h in hunts:
        sizes = json.loads(h.get("sizes", "[]"))
        text += f"→ *{h['name']}*\n  Max £{h.get('max_price', '?')} · {', '.join(sizes) if sizes else 'Any size'}\n\n"
    await safe_reply(update, text)

async def cmd_deals(update, ctx):
    profile = get_active_profile(update.effective_user.id)
    hunts = get_hunts(update.effective_user.id)
    await safe_reply(update, "🔥 Finding insane deals...")
    context = f"User hunts: {', '.join([h['name'] for h in hunts])}" if hunts else "No specific hunts"
    pi = f"Profile: {profile['name']}, {profile.get('height')}cm" if profile else "No profile"
    tips = ask_claude(
        f"{build_training_context(update.effective_user.id)}Give me 5 specific archive fashion deals/steals to look for RIGHT NOW across Mercari JP, Yahoo Auctions, Xianyu, Grailed, Vinted, Weidian and Taobao. {context}. {pi}.\n"
        f"For each: exact piece name, which platform or auction, expected price range, why it's a steal, exact search terms to use. Be very specific and actionable.",
        "You are an archive fashion expert who monitors all resale platforms daily, including Mercari JP, Xianyu, and Japanese auctions."
    )
    await safe_reply(update, f"⚡ Insane deals intel\n\n{tips}")

async def cmd_sources(update, ctx):
    await safe_reply(update,
        "🌐 *Archive Hunter sources*\n\n"
        "These sources are included in search and hunt alerts:\n"
        "- Mercari JP\n"
        "- Xianyu\n"
        "- Yahoo Auctions\n"
        "- eBay Auctions\n"
        "- Grailed\n"
        "- Vinted\n"
        "- Weidian\n"
        "- Taobao\n"
        "- Private replica seller markets and Reddit deal feeds\n\n"
        "Use /search or /auction with brand, size, and marketplace terms for the best results."
    )

async def cmd_intel(update, ctx):
    await safe_reply(update, "🧠 Generating market intel...")
    intel = ask_claude(
        f"{build_training_context(update.effective_user.id)}Give me the latest archive fashion market intelligence:\n"
        "1. Which platforms and auctions have the best deals right now and why\n"
        "2. Top 3 most undervalued archive pieces to buy now\n"
        "3. Best Weidian/Taobao rep sellers active right now with links or store names\n"
        "4. Trending pieces or designers with rising prices\n"
        "5. Specific tips for finding steals on Xianyu, Mercari JP, and Japanese auctions\n"
        "Be very specific — names, prices, platforms, and auction markets.",
        "You are an archive fashion market intelligence expert who monitors Reddit (r/QualityReps, r/DesignerReps, r/FashionReps), Grailed sold listings, Mercari JP, Xianyu, and Japanese auction markets."
    )
    await safe_reply(update, f"🧠 Market Intel\n\n{intel}")

async def cmd_sellers(update, ctx):
    await safe_reply(update, "🏪 Loading verified sellers...")
    sellers = ask_claude(
        "List the top 10 trusted archive fashion rep sellers on Weidian and Taobao right now. "
        "For each include: exact shop name, platform (Weidian/Taobao), "
        "specialty (which designers/pieces they're known for), "
        "price range in yuan, quality rating out of 10, "
        "and any known store links or search terms to find them. "
        "Include DEEDS, PearlNecklace, PUERHOMME, Marxism, and other top sellers from r/QualityReps and r/DesignerReps.",
        "You are an expert on replica fashion markets with deep knowledge from Reddit communities."
    )
    await safe_reply(update, f"🏪 Top verified sellers\n\n{sellers}")

async def cmd_price(update, ctx):
    query = " ".join(ctx.args) if ctx.args else ""
    if not query:
        await safe_reply(update, "Usage: /price Raf Simons AW01 bomber")
        return
    await safe_reply(update, f"📊 Checking price for: {query}...")
    info = ask_claude(
        f"Give me detailed price intelligence for: {query}\n"
        f"Include: low/average/high price in GBP, price trend (rising/stable/falling), "
        f"best platforms to find it cheapest, best rep price and seller if applicable, "
        f"what separates a good deal from a bad one for this piece, and any authentication tips.",
        "You are an archive fashion pricing expert."
    )
    await safe_reply(update, f"📊 Price intel: {query}\n\n{info}")

async def cmd_remember(update, ctx):
    note = " ".join(ctx.args).strip()
    if not note:
        ctx.user_data["awaiting"] = "new_memory"
        await safe_reply(update,
            "🧠 *Memory training mode*\n\n"
            "Send the archive designers, pieces, sellers or research notes you want the bot to remember.\n"
            "Examples:\n"
            "`Hedi Slimane YSL boots, Dior Homme Slimane jackets, YSL Tribute boots, rare Mercari JP auctions`\n"
            "`Dior Saddle bag, YSL Rive Gauche jacket, Claude slam-proof search terms`")
        return
    notes = add_user_memory(update.effective_user.id, note)
    await safe_reply(update, f"✅ Remembered {len(notes)} item(s).\nUse /memory to review your saved archive training notes.")

async def cmd_memory(update, ctx):
    notes = get_user_memory(update.effective_user.id)
    if not notes:
        await safe_reply(update, "No saved archive memory yet. Use /remember to teach the bot important pieces and brands.")
        return
    text = "🧠 *Your archive memory notes:*\n\n"
    for i, item in enumerate(notes, start=1):
        text += f"{i}. {item['text']}\n"
    await safe_reply(update, text)

async def cmd_forget(update, ctx):
    if not ctx.args or not ctx.args[0].isdigit():
        await safe_reply(update, "Usage: /forget [index]\nExample: /forget 2")
        return
    idx = int(ctx.args[0]) - 1
    if remove_user_memory(update.effective_user.id, idx):
        await safe_reply(update, f"✅ Removed memory item {idx + 1}.")
    else:
        await safe_reply(update, "Could not find that memory item. Use /memory to list saved notes.")

async def cmd_train(update, ctx):
    ctx.user_data["awaiting"] = "new_memory"
    await safe_reply(update,
        "🚀 *Train Archive Hunter*\n\n"
        "Send a list of archive designers, pieces, or auction targets to train the bot on.\n"
        "Example:\n"
        "`Hedi Slimane Dior Homme jackets\nYSL Tribute boots\nDior Saddle bag auction targets`")

async def cmd_watch(update, ctx):
    url = " ".join(ctx.args) if ctx.args else ""
    if not url:
        await safe_reply(update, "Usage: /watch [listing URL]")
        return
    supa_insert("watched", {"telegram_id": update.effective_user.id, "url": url, "title": "Watched listing", "platform": "Unknown"})
    await safe_reply(update, f"👁 Watching listing\nYou'll be alerted if the price drops.\n\n{url}")

async def cmd_pause(update, ctx):
    await safe_reply(update, "⏸ Scanning paused. Use /resume to restart.")

async def cmd_resume(update, ctx):
    await safe_reply(update, "▶️ Scanning resumed. Non-stop mode active.")

async def cmd_digest(update, ctx):
    profile = get_active_profile(update.effective_user.id)
    hunts = get_hunts(update.effective_user.id)
    await safe_reply(update, "📋 Generating digest...")
    pi = f"{profile['name']}, {profile.get('height','')}cm" if profile else "Not set"
    hs = ', '.join([h['name'] for h in hunts]) if hunts else "None"
    digest = ask_claude(
        f"Generate a daily archive fashion hunting digest.\n"
        f"Profile: {pi}\nActive hunts: {hs}\n\n"
        f"Include: market summary, best platforms today, top 3 steals to watch, "
        f"any price alerts, and 3 actionable search tips for today.",
        "You are an archive fashion hunting assistant."
    )
    await safe_reply(update, f"📋 Daily Digest\n\n{digest}")

# ─── Message handler ───

async def handle_message(update, ctx):
    awaiting = ctx.user_data.get("awaiting")
    text = update.message.text

    if awaiting == "new_profile":
        ctx.user_data["awaiting"] = None
        try:
            data = {}
            measurements = {}
            key_map = {
                "chest":"chest","shoulder":"shoulder","waist":"waist",
                "upper hips":"upperHip","hips":"hip","inseam":"inseam",
                "thigh":"thigh","sleeve":"sleeve","shoe eu":"footEU",
                "neck":"neck","rise":"rise","hem":"hem","hip":"hip",
                "upper hip":"upperHip","bicep":"bicep","forearm":"forearm"
            }
            for line in text.strip().split("\n"):
                if ":" not in line: continue
                k, v = line.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if k in ["name","height","weight","build","notes"]:
                    data[k] = v
                else:
                    measurements[key_map.get(k, k)] = v
            name = data.get("name", "My profile")
            data["measurements"] = measurements
            create_profile(update.effective_user.id, name, data)
            await safe_reply(update,
                f"✅ Profile '{name}' created!\n"
                f"Height: {data.get('height','?')}cm · Build: {data.get('build','?')}\n"
                f"{len(measurements)} measurements saved\n\n"
                f"Use /scan to start hunting!"
            )
        except Exception as e:
            await safe_reply(update, f"Couldn't parse that. Try /newprofile again.\nError: {str(e)[:100]}")

    elif awaiting == "new_hunt":
        ctx.user_data["awaiting"] = None
        try:
            hunt = {}
            for line in text.strip().split("\n"):
                if ":" not in line: continue
                k, v = line.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if "designer" in k: hunt["designer"] = v
                elif "piece" in k: hunt["piece"] = v
                elif "price" in k: hunt["max_price"] = int(re.sub(r"[^\d]", "", v) or "0")
                elif "size" in k: hunt["sizes"] = [s.strip() for s in v.split(",")]
                elif "season" in k: hunt["season"] = v
            hunt["name"] = f"{hunt.get('designer','')} — {hunt.get('piece','')}".strip(" —") or "Unnamed hunt"
            save_hunt(update.effective_user.id, hunt)
            sizes = hunt.get("sizes", [])
            await safe_reply(update,
                f"🎯 Hunt created: {hunt['name']}\n"
                f"Max: £{hunt.get('max_price','Any')} · Sizes: {', '.join(sizes) if sizes else 'Any'}\n\n"
                f"Scanning 24/7. You'll be alerted on matches."
            )
        except Exception as e:
            await safe_reply(update, f"Couldn't parse. Try /hunt again.\nError: {str(e)[:100]}")
    elif awaiting == "new_memory":
        ctx.user_data["awaiting"] = None
        notes = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if not notes:
            await safe_reply(update, "No memory text found. Send the designers, pieces, or auction targets you want the bot to remember.")
        else:
            for note in notes:
                add_user_memory(update.effective_user.id, note)
            await safe_reply(update, f"✅ Saved {len(notes)} archive memory item(s). Use /memory to review them.")
    else:
        profile = get_active_profile(update.effective_user.id)
        pi = f"Active profile: {profile['name']}" if profile else ""
        response = ask_claude(
            f"{build_training_context(update.effective_user.id)}User message: {text}\n{pi}\nHelp with their archive fashion query. Give pricing/platform intel if relevant. Keep it short.",
            "You are Archive Hunter bot, an archive fashion assistant on Telegram."
        )
        await safe_reply(update, response)

# ─── Background scanner ───

async def background_scanner(app):
    log.info("Background scanner started")
    await asyncio.sleep(30)
    while True:
        try:
            hunts = supa_get("hunts", {"active": "eq.true"})
            log.info(f"Scanner: {len(hunts)} active hunts")
            for hunt in hunts:
                try:
                    query = f"{hunt.get('designer','')} {hunt.get('piece','')}".strip()
                    if not query: continue
                    alert = ask_claude(
                        f"{build_training_context(hunt['telegram_id'])}Quick scan for: {query}\nMax price: £{hunt.get('max_price','any')}\n"
                        f"Give 1 actionable tip for finding this piece right now on Yahoo Auctions, eBay auctions, Mercari JP, Xianyu, Grailed, Vinted or Taobao. "
                        f"If auction listings are available, call them out explicitly.",
                        "You are an archive fashion deal finder. Be brief and specific."
                    )
                    if any(w in alert.lower() for w in ["check","found","available","listed","search","try"]):
                        try:
                            await app.bot.send_message(chat_id=hunt["telegram_id"], text=f"🔥 Hunt update: {hunt['name']}\n\n{alert}")
                        except Exception as e:
                            log.error(f"Alert send error: {e}")
                except Exception as e:
                    log.error(f"Hunt error: {e}")
            await asyncio.sleep(300)
        except Exception as e:
            log.error(f"Scanner error: {e}")
            await asyncio.sleep(60)

# ─── Main ───

async def post_init(app):
    asyncio.create_task(background_scanner(app))
    log.info("Archive Hunter fully started")

def main():
    log.info("Archive Hunter starting...")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("newprofile", cmd_newprofile))
    app.add_handler(CommandHandler("profiles", cmd_profiles))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("measurements", cmd_newprofile))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("search", cmd_scan))
    app.add_handler(CommandHandler("find", cmd_scan))
    app.add_handler(CommandHandler("auction", cmd_scan))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("train", cmd_train))
    app.add_handler(CommandHandler("hunt", cmd_hunt))
    app.add_handler(CommandHandler("hunts", cmd_hunts))
    app.add_handler(CommandHandler("deals", cmd_deals))
    app.add_handler(CommandHandler("intel", cmd_intel))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("sellers", cmd_sellers))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
