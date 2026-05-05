"""
webhook.py — LuxeBot unified web process

Handles:
  - Discord OAuth2 login / server picker
  - Full dashboard UI (all settings sections)
  - Whop subscription webhooks
  - Internal bot API endpoints
  - Health check

Run as: python webhook.py
Railway: web dyno
"""

import os
import asyncio
import aiosqlite
import requests as req_lib
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template_string, request,
    redirect, url_for, session, jsonify, flash
)

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET", "luxebot_dashboard_secret_change_me")

# ── Config ────────────────────────────────────────────────────────────────────

DISCORD_CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI  = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
API_SECRET            = os.getenv("DASHBOARD_SECRET", "luxebot123")
OWNER_ID             = "1196910040364372028"  # Bryce — only user who can grant premium
WHOP_SECRET           = os.getenv("WHOP_WEBHOOK_SECRET", "luxebot_secret_123")
DISCORD_API           = "https://discord.com/api/v10"
BOT_TOKEN = os.getenv("DISCORD_TOKEN", "")
DB_PATH               = "luxebot.db"


# ── Async helper ──────────────────────────────────────────────────────────────

def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if key != API_SECRET:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def get_user_guilds():
    token = session.get("access_token")
    if not token:
        return []
    resp = req_lib.get(
        f"{DISCORD_API}/users/@me/guilds",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5
    )
    if resp.status_code == 200:
        guilds = resp.json()
        return [g for g in guilds if (int(g.get("permissions", 0)) & 0x20) == 0x20]
    return []


def guild_access_required(f):
    """Verify the logged-in user is an admin of the requested guild."""
    @wraps(f)
    def decorated(guild_id, *args, **kwargs):
        guilds = get_user_guilds()
        guild = next((g for g in guilds if g["id"] == guild_id), None)
        if not guild:
            return redirect(url_for("servers"))
        return f(guild_id, guild, *args, **kwargs)
    return decorated


# ── DB helpers (sync wrappers) ────────────────────────────────────────────────

# ── Discord Guild Data (channels + roles for picker) ─────────────────────────

_discord_cache: dict = {}          # { "channels:{id}": (data, expires_ts), ... }
_CACHE_TTL = 300                   # 5 minutes


def _discord_bot_get(path: str):
    """GET request to Discord API using the bot token. Returns parsed JSON or None."""
    if not BOT_TOKEN:
        return None
    try:
        resp = req_lib.get(
            f"{DISCORD_API}{path}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            timeout=5
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Discord API error ({path}): {e}")
    return None


def get_guild_channels(guild_id: str) -> list:
    """
    Returns text + category channels for the guild, sorted by position.
    Shape: [{"id": "...", "name": "...", "type": 0}]
    Cached for 5 minutes.
    """
    cache_key = f"channels:{guild_id}"
    now = datetime.utcnow().timestamp()
    if cache_key in _discord_cache:
        data, exp = _discord_cache[cache_key]
        if now < exp:
            return data

    raw = _discord_bot_get(f"/guilds/{guild_id}/channels")
    if raw is None:
        return []

    # Type 0 = text, type 2 = voice, type 4 = category, type 5 = news
    # Only show text-like channels (types 0 and 5) in channel pickers
    channels = [
        {"id": c["id"], "name": c["name"], "position": c.get("position", 0),
         "parent_id": c.get("parent_id"), "type": c["type"]}
        for c in raw if c["type"] in (0, 5)
    ]
    channels.sort(key=lambda c: c["position"])

    # Build category map for grouping
    categories = {
        c["id"]: c["name"]
        for c in raw if c["type"] == 4
    }

    # Attach category name for display
    for c in channels:
        c["category"] = categories.get(c["parent_id"], "")

    _discord_cache[cache_key] = (channels, now + _CACHE_TTL)
    return channels


def get_guild_roles(guild_id: str) -> list:
    """
    Returns guild roles sorted by position (highest first, skip @everyone).
    Shape: [{"id": "...", "name": "...", "color": 0}]
    Cached for 5 minutes.
    """
    cache_key = f"roles:{guild_id}"
    now = datetime.utcnow().timestamp()
    if cache_key in _discord_cache:
        data, exp = _discord_cache[cache_key]
        if now < exp:
            return data

    raw = _discord_bot_get(f"/guilds/{guild_id}/roles")
    if raw is None:
        return []

    roles = [
        {"id": r["id"], "name": r["name"], "color": r.get("color", 0),
         "position": r.get("position", 0)}
        for r in raw if r["name"] != "@everyone"
    ]
    roles.sort(key=lambda r: r["position"], reverse=True)

    _discord_cache[cache_key] = (roles, now + _CACHE_TTL)
    return roles


def invalidate_guild_discord_cache(guild_id: str):
    """Call after saving settings that might add/remove channels/roles."""
    _discord_cache.pop(f"channels:{guild_id}", None)
    _discord_cache.pop(f"roles:{guild_id}", None)


def db_get_guild(guild_id: int) -> dict:
    async def _fetch():
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)
            ) as c:
                row = await c.fetchone()
            async with db.execute(
                "SELECT * FROM automod_settings WHERE guild_id = ?", (guild_id,)
            ) as c:
                am = await c.fetchone()
            async with db.execute(
                "SELECT expires_at, trial_expires_at FROM premium_servers WHERE guild_id = ?", (guild_id,)
            ) as c:
                prem = await c.fetchone()
            async with db.execute(
                "SELECT * FROM ticket_settings WHERE guild_id = ?", (guild_id,)
            ) as c:
                tickets = await c.fetchone()
            async with db.execute(
                "SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level", (guild_id,)
            ) as c:
                level_roles = await c.fetchall()
            async with db.execute(
                "SELECT channel_name, discord_channel FROM youtube_alerts WHERE guild_id = ?", (guild_id,)
            ) as c:
                yt = await c.fetchall()
            async with db.execute(
                "SELECT streamer, discord_channel FROM twitch_alerts WHERE guild_id = ?", (guild_id,)
            ) as c:
                twitch = await c.fetchall()
            async with db.execute(
                "SELECT subreddit, discord_channel FROM reddit_alerts WHERE guild_id = ?", (guild_id,)
            ) as c:
                reddit = await c.fetchall()
            async with db.execute(
                "SELECT word FROM badwords WHERE guild_id = ?", (guild_id,)
            ) as c:
                badwords = await c.fetchall()
            async with db.execute(
                "SELECT command, response FROM custom_commands WHERE guild_id = ?", (guild_id,)
            ) as c:
                custom_cmds = await c.fetchall()
            async with db.execute(
                "SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ?", (guild_id,)
            ) as c:
                rr = await c.fetchall()
            async with db.execute(
                "SELECT guild_id, user_id, level FROM levels WHERE guild_id = ? ORDER BY xp DESC LIMIT 10", (guild_id,)
            ) as c:
                top_members = await c.fetchall()
            async with db.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = ?", (guild_id,)
            ) as c:
                warn_count = (await c.fetchone())[0]
        return row, am, prem, tickets, level_roles, yt, twitch, reddit, badwords, custom_cmds, rr, top_members, warn_count

    row, am, prem, tickets, level_roles, yt, twitch, reddit, badwords, custom_cmds, rr, top_members, warn_count = run_async(_fetch())

    now     = datetime.utcnow()
    now_iso = now.isoformat()
    is_premium     = False
    is_trial       = False
    trial_days_left = 0
    if prem:
        if prem[0] and prem[0] > now_iso:
            is_premium = True
        if prem[1] and prem[1] > now_iso:
            is_trial = True
            try:
                exp   = datetime.fromisoformat(prem[1])
                delta = exp - now
                trial_days_left = max(0, int(delta.total_seconds() // 86400))
            except Exception:
                trial_days_left = 0

    return {
        "guild_id":       guild_id,
        "prefix":         row["prefix"]          if row else "!",
        "log_channel":    row["log_channel"]      if row else None,
        "welcome_channel":row["welcome_channel"]  if row else None,
        "welcome_message":row["welcome_message"]  if row else "",
        "goodbye_message":row["goodbye_message"]  if row else "",
        "autorole":       row["autorole"]         if row else None,
        "automod": {
            "anti_spam":     bool(am[1]) if am else False,
            "anti_caps":     bool(am[2]) if am else False,
            "anti_links":    bool(am[3]) if am else False,
            "anti_mentions": bool(am[4]) if am else False,
            "anti_raid":     bool(am[5]) if am else False,
        },
        "tickets": {
            "category_id":  tickets["category_id"]  if tickets else None,
            "support_role": tickets["support_role"]  if tickets else None,
            "log_channel":  tickets["log_channel"]   if tickets else None,
        },
        "level_roles":    [{"level": r[0], "role_id": r[1]} for r in level_roles],
        "youtube_alerts": [{"channel": r[0], "discord_channel": r[1]} for r in yt],
        "twitch_alerts":  [{"streamer": r[0], "discord_channel": r[1]} for r in twitch],
        "reddit_alerts":  [{"subreddit": r[0], "discord_channel": r[1]} for r in reddit],
        "badwords":       [r[0] for r in badwords],
        "custom_commands":[{"command": r[0], "response": r[1]} for r in custom_cmds],
        "reaction_roles": [{"message_id": r[0], "emoji": r[1], "role_id": r[2]} for r in rr],
        "top_members":    list(top_members),
        "warn_count":     warn_count,
        "is_premium":     is_premium,
        "is_trial":       is_trial,
                "alert_count":    len(yt) + len(twitch) + len(reddit),
        "trial_days_left": trial_days_left,
    }


def db_save_section(guild_id: int, section: str, data: dict):
    async def _save():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,))
            await db.execute("INSERT OR IGNORE INTO automod_settings (guild_id) VALUES (?)", (guild_id,))

            if section == "general":
                if "prefix" in data:
                    await db.execute("UPDATE guilds SET prefix = ? WHERE guild_id = ?", (data["prefix"][:5], guild_id))
                # Accept either the select picker value or the manual text fallback
                raw_ch = data.get("log_channel") or data.get("log_channel_manual") or ""
                if raw_ch != "" or "log_channel" in data:
                    try:
                        val = int(raw_ch) if raw_ch else None
                    except (ValueError, TypeError):
                        val = None
                    await db.execute("UPDATE guilds SET log_channel = ? WHERE guild_id = ?", (val, guild_id))

            elif section == "welcome":
                if "welcome_channel" in data:
                    val = int(data["welcome_channel"]) if data["welcome_channel"] else None
                    await db.execute("UPDATE guilds SET welcome_channel = ? WHERE guild_id = ?", (val, guild_id))
                if "welcome_message" in data:
                    await db.execute("UPDATE guilds SET welcome_message = ? WHERE guild_id = ?", (data["welcome_message"], guild_id))
                if "goodbye_message" in data:
                    await db.execute("UPDATE guilds SET goodbye_message = ? WHERE guild_id = ?", (data["goodbye_message"], guild_id))
                if "autorole" in data:
                    val = int(data["autorole"]) if data["autorole"] else None
                    await db.execute("UPDATE guilds SET autorole = ? WHERE guild_id = ?", (val, guild_id))

            elif section == "automod":
                fields = ["anti_spam", "anti_caps", "anti_links", "anti_mentions", "anti_raid"]
                for field in fields:
                    if field in data:
                        val = 1 if data[field] else 0
                        await db.execute(f"UPDATE automod_settings SET {field} = ? WHERE guild_id = ?", (val, guild_id))
                if "badword_add" in data and data["badword_add"].strip():
                    word = data["badword_add"].strip().lower()
                    await db.execute("INSERT OR IGNORE INTO badwords (guild_id, word) VALUES (?, ?)", (guild_id, word))
                if "badword_remove" in data and data["badword_remove"].strip():
                    word = data["badword_remove"].strip().lower()
                    await db.execute("DELETE FROM badwords WHERE guild_id = ? AND word = ?", (guild_id, word))

            elif section == "tickets":
                await db.execute("INSERT OR IGNORE INTO ticket_settings (guild_id) VALUES (?)", (guild_id,))
                if "support_role" in data:
                    val = int(data["support_role"]) if data["support_role"] else None
                    await db.execute("UPDATE ticket_settings SET support_role = ? WHERE guild_id = ?", (val, guild_id))
                if "log_channel" in data:
                    val = int(data["log_channel"]) if data["log_channel"] else None
                    await db.execute("UPDATE ticket_settings SET log_channel = ? WHERE guild_id = ?", (val, guild_id))

            elif section == "leveling":
                if "level_role_add_level" in data and "level_role_add_role" in data:
                    try:
                        lvl = int(data["level_role_add_level"])
                        role = int(data["level_role_add_role"])
                        await db.execute(
                            "INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
                            (guild_id, lvl, role)
                        )
                    except (ValueError, TypeError):
                        pass
                if "level_role_remove" in data:
                    try:
                        lvl = int(data["level_role_remove"])
                        await db.execute("DELETE FROM level_roles WHERE guild_id = ? AND level = ?", (guild_id, lvl))
                    except (ValueError, TypeError):
                        pass

            elif section == "alerts":
                if "yt_remove" in data and data["yt_remove"].strip():
                    await db.execute("DELETE FROM youtube_alerts WHERE guild_id = ? AND channel_name = ?", (guild_id, data["yt_remove"].strip()))
                if "twitch_remove" in data and data["twitch_remove"].strip():
                    await db.execute("DELETE FROM twitch_alerts WHERE guild_id = ? AND streamer = ?", (guild_id, data["twitch_remove"].strip().lower()))
                if "reddit_remove" in data and data["reddit_remove"].strip():
                    sub = data["reddit_remove"].strip().lower().replace("r/", "")
                    await db.execute("DELETE FROM reddit_alerts WHERE guild_id = ? AND subreddit = ?", (guild_id, sub))

            elif section == "commands":
                if "cmd_remove" in data and data["cmd_remove"].strip():
                    await db.execute("DELETE FROM custom_commands WHERE guild_id = ? AND command = ?", (guild_id, data["cmd_remove"].strip().lower()))

            await db.commit()

    run_async(_save())

    # Invalidate Redis cache for affected keys
    try:
        async def _invalidate():
            from cache import invalidate_prefix, invalidate_guild_settings
            if section in ("general", "welcome", "tickets", "leveling"):
                await invalidate_guild_settings(guild_id)
            if section == "general" and "prefix" in data:
                await invalidate_prefix(guild_id)
        run_async(_invalidate())
    except Exception:
        pass


# ── Shared CSS / JS (injected into every page) ────────────────────────────────

BASE_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --gold:#C9A84C; --gold-dim:#C9A84C33; --gold-mid:#C9A84C88;
  --dark:#080808; --dark2:#0f0f0f; --dark3:#161616; --dark4:#1e1e1e;
  --text:#e8e8e8; --muted:#555; --muted2:#888;
  --green:#4ade80; --red:#ef4444; --blue:#60a5fa;
  --radius:10px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--dark);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh}
a{color:inherit;text-decoration:none}
body::before{content:'';position:fixed;inset:0;
  background-image:linear-gradient(rgba(201,168,76,.025) 1px,transparent 1px),
  linear-gradient(90deg,rgba(201,168,76,.025) 1px,transparent 1px);
  background-size:60px 60px;pointer-events:none;z-index:0}

/* Nav */
.topnav{display:flex;align-items:center;justify-content:space-between;
  padding:18px 40px;border-bottom:1px solid var(--dark4);position:relative;z-index:10}
.logo{font-family:'Bebas Neue',sans-serif;font-size:1.7rem;color:var(--gold);letter-spacing:3px}
.logo span{color:var(--text)}
.nav-actions{display:flex;align-items:center;gap:10px}
.btn{padding:9px 22px;border-radius:7px;font-family:'DM Sans',sans-serif;font-weight:600;
  font-size:.875rem;cursor:pointer;transition:all .2s;border:none;display:inline-flex;align-items:center;gap:6px}
.btn-gold{background:var(--gold);color:#000}
.btn-gold:hover{background:#e8c060;transform:translateY(-1px)}
.btn-outline{background:transparent;color:var(--gold);border:1px solid var(--gold-mid)}
.btn-outline:hover{background:var(--gold-dim)}
.btn-ghost{background:transparent;color:var(--muted2);border:1px solid var(--dark4)}
.btn-ghost:hover{color:var(--text);border-color:#333}
.btn-danger{background:rgba(239,68,68,.12);color:var(--red);border:1px solid rgba(239,68,68,.2)}
.btn-danger:hover{background:rgba(239,68,68,.2)}
.btn-sm{padding:6px 14px;font-size:.8rem}

/* Cards */
.card{background:var(--dark2);border:1px solid var(--dark4);border-radius:12px;padding:24px;margin-bottom:18px}
.card-title{font-weight:600;font-size:.95rem;margin-bottom:18px;display:flex;align-items:center;gap:8px}
.card-subtitle{font-size:.8rem;color:var(--muted2);margin-top:2px}

/* Form */
.form-group{margin-bottom:18px}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.form-row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
label.lbl{display:block;font-size:.78rem;font-weight:600;color:var(--muted2);
  letter-spacing:.8px;text-transform:uppercase;margin-bottom:7px}
.input{width:100%;padding:10px 14px;background:var(--dark3);border:1px solid var(--dark4);
  border-radius:8px;color:var(--text);font-family:'DM Sans',sans-serif;font-size:.9rem;transition:border-color .2s}
.input:focus{outline:none;border-color:var(--gold-mid)}
.input::placeholder{color:var(--muted)}
textarea.input{resize:vertical;min-height:80px;line-height:1.5}
.hint{font-size:.75rem;color:var(--muted);margin-top:5px}
.input-row{display:flex;gap:8px}
.input-row .input{flex:1}

/* Toggle */
.toggle-list{display:flex;flex-direction:column;gap:0}
.toggle-row{display:flex;align-items:center;justify-content:space-between;
  padding:14px 0;border-bottom:1px solid var(--dark4)}
.toggle-row:last-child{border-bottom:none}
.toggle-info h4{font-size:.875rem;font-weight:500;margin-bottom:2px}
.toggle-info p{font-size:.78rem;color:var(--muted2)}
.toggle{position:relative;width:44px;height:24px;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;inset:0;background:var(--dark4);border-radius:24px;transition:.2s}
.slider:before{content:'';position:absolute;height:18px;width:18px;left:3px;bottom:3px;
  background:var(--muted);border-radius:50%;transition:.2s}
.toggle input:checked+.slider{background:var(--gold-dim);border:1px solid var(--gold)}
.toggle input:checked+.slider:before{transform:translateX(20px);background:var(--gold)}

/* Badge */
.badge{display:inline-flex;align-items:center;gap:5px;padding:4px 12px;border-radius:20px;font-size:.75rem;font-weight:600;letter-spacing:.5px}
.badge-gold{background:var(--gold-dim);border:1px solid var(--gold);color:var(--gold)}
.badge-green{background:rgba(74,222,128,.1);border:1px solid rgba(74,222,128,.25);color:var(--green)}
.badge-muted{background:var(--dark3);border:1px solid var(--dark4);color:var(--muted2)}

/* Tag list */
.tag-list{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.tag{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;
  background:var(--dark3);border:1px solid var(--dark4);border-radius:20px;font-size:.8rem}
.tag .del{cursor:pointer;color:var(--muted2);font-size:.9rem;transition:color .15s}
.tag .del:hover{color:var(--red)}

/* Table */
.table{width:100%;border-collapse:collapse;font-size:.875rem}
.table th{text-align:left;padding:8px 12px;color:var(--muted2);font-size:.75rem;
  text-transform:uppercase;letter-spacing:.8px;border-bottom:1px solid var(--dark4)}
.table td{padding:10px 12px;border-bottom:1px solid var(--dark4)}
.table tr:last-child td{border-bottom:none}
.table tr:hover td{background:var(--dark3)}
code.cmd{background:var(--dark3);padding:3px 9px;border-radius:5px;font-size:.8rem;color:var(--gold)}

/* Stats */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:20px}
.stat{background:var(--dark2);border:1px solid var(--dark4);border-radius:10px;padding:18px}
.stat-val{font-family:'Bebas Neue',sans-serif;font-size:2rem;color:var(--gold);letter-spacing:1px}
.stat-lbl{font-size:.72rem;color:var(--muted2);text-transform:uppercase;letter-spacing:1px;margin-top:3px}

/* Toast */
.toast{position:fixed;bottom:24px;right:24px;padding:12px 22px;background:var(--green);
  color:#000;border-radius:8px;font-weight:700;font-size:.85rem;
  transform:translateY(80px);opacity:0;transition:all .3s;z-index:9999}
.toast.show{transform:translateY(0);opacity:1}
.toast.error{background:var(--red);color:#fff}

/* Alert banner */
.alert{padding:12px 16px;border-radius:8px;font-size:.85rem;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.alert-warn{background:rgba(201,168,76,.1);border:1px solid var(--gold-dim);color:var(--gold)}
.alert-info{background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.2);color:var(--blue)}

/* Empty state */
.empty{text-align:center;padding:40px 20px;color:var(--muted2);font-size:.875rem}
.empty .ico{font-size:2rem;margin-bottom:10px}

/* Save bar */
.save-bar{display:flex;align-items:center;justify-content:flex-end;gap:12px;
  padding-top:18px;margin-top:4px;border-top:1px solid var(--dark4)}

/* Sidebar layout */
.layout{display:flex;min-height:100vh}
.sidebar{width:230px;min-height:100vh;background:var(--dark2);border-right:1px solid var(--dark4);
  display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:100}
.sidebar-head{padding:20px 16px;border-bottom:1px solid var(--dark4)}
.sidebar-server{padding:14px 16px;border-bottom:1px solid var(--dark4);display:flex;align-items:center;gap:10px}
.srv-icon{width:34px;height:34px;border-radius:50%;border:1px solid var(--dark4);flex-shrink:0;object-fit:cover}
.srv-icon-ph{width:34px;height:34px;border-radius:50%;background:var(--dark3);
  display:flex;align-items:center;justify-content:center;
  font-family:'Bebas Neue',sans-serif;font-size:.9rem;color:var(--gold);flex-shrink:0}
.srv-name{font-size:.83rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sidebar-nav{flex:1;padding:12px 10px;display:flex;flex-direction:column;gap:1px;overflow-y:auto}
.nav-item{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:7px;
  cursor:pointer;font-size:.84rem;font-weight:500;color:var(--muted2);
  background:none;border:none;width:100%;text-align:left;transition:all .15s}
.nav-item:hover{background:var(--dark3);color:var(--text)}
.nav-item.active{background:var(--gold-dim);color:var(--gold)}
.nav-sep{height:1px;background:var(--dark4);margin:8px 10px}
.sidebar-foot{padding:14px 16px;border-top:1px solid var(--dark4)}
.main-content{margin-left:230px;flex:1;padding:32px 36px;max-width:calc(100vw - 230px)}
.page-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}
.page-title{font-family:'Bebas Neue',sans-serif;font-size:1.7rem;letter-spacing:2px}

/* Responsive */
@media(max-width:768px){
  .sidebar{transform:translateX(-100%);transition:.25s}
  .sidebar.open{transform:translateX(0)}
  .main-content{margin-left:0;max-width:100vw;padding:20px}
  .form-row,.form-row-3{grid-template-columns:1fr}
  .stats-grid{grid-template-columns:1fr 1fr}
}

/* Channel/Role picker */
select.input{appearance:none;-webkit-appearance:none;cursor:pointer;padding-right:32px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23888' d='M6 8L1 3h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
select.input option{background:#161616;color:#e8e8e8}
select.input optgroup{color:#555;font-style:normal;font-size:.8rem;font-weight:600}
.role-swatch{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
.picker-hint{font-size:.72rem;color:#555;margin-top:5px}
.manual-toggle{font-size:.72rem;color:#555;cursor:pointer;margin-top:4px;display:inline-block}
.manual-toggle:hover{color:#C9A84C}
.manual-input{display:none;margin-top:8px}
.manual-input.show{display:block}
</style>
"""

BASE_JS = """
<script>
function showSection(name, el) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const sec = document.getElementById('sec-' + name);
  if (sec) sec.classList.add('active');
  if (el) el.classList.add('active');
}

function toast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (type === 'error' ? ' error' : '');
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

async function saveSection(section) {
  const btn = document.getElementById('save-btn-' + section);
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

  const data = { section };
  const form = document.getElementById('form-' + section);
  if (form) {
    form.querySelectorAll('input,textarea,select').forEach(el => {
      if (!el.name) return;
      if (el.type === 'checkbox') data[el.name] = el.checked;
      else data[el.name] = el.value;
    });
  }

  try {
    const resp = await fetch(window.SAVE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    const json = await resp.json();
    if (resp.ok && json.status === 'saved') {
      toast('✓ Saved!');
    } else {
      toast(json.message || 'Save failed', 'error');
    }
  } catch(e) {
    toast('Network error', 'error');
  }

  if (btn) { btn.disabled = false; btn.textContent = 'Save Changes'; }
}

async function quickAction(action, payload) {
  const resp = await fetch(window.SAVE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section: action, ...payload })
  });
  const json = await resp.json();
  if (resp.ok && json.status === 'saved') {
    toast('✓ Done!');
    setTimeout(() => location.reload(), 600);
  } else {
    toast(json.message || 'Failed', 'error');
  }
}

async function refreshPickers() {
  try {
    const gid = window.location.pathname.split("\/")[2];
    const [chResp, roResp] = await Promise.all([
      fetch(`/api/guild/${gid}/channels`),
      fetch(`/api/guild/${gid}/roles`)
    ]);
    if (chResp.ok) window.GUILD_CHANNELS = await chResp.json();
    if (roResp.ok) window.GUILD_ROLES    = await roResp.json();
    // Re-build all pickers
    document.querySelectorAll('select[data-picker="channel"]').forEach(sel => {
      const cur = sel.value || sel.dataset.current;
      buildChannelSelect(sel, window.GUILD_CHANNELS, cur);
    });
    document.querySelectorAll('select[data-picker="role"]').forEach(sel => {
      const cur = sel.value || sel.dataset.current;
      buildRoleSelect(sel, window.GUILD_ROLES, cur);
    });
    toast("✓ Channels & roles refreshed!");
  } catch(e) {
    toast("Refresh failed", "error");
  }
}

function toggleManual(id) {
  const el = document.getElementById(id);
  el && el.classList.toggle('show');
}

// Build a channel <select> from the pre-loaded channels array
// Called once on page load to attach to all [data-picker="channel"] selects
function buildChannelSelect(sel, channels, currentId) {
  if (!channels || !channels.length) return;
  const grouped = {};
  channels.forEach(c => {
    const cat = c.category || 'Uncategorised';
    (grouped[cat] = grouped[cat] || []).push(c);
  });
  sel.innerHTML = '<option value="">— None —</option>';
  Object.entries(grouped).forEach(([cat, chs]) => {
    const grp = document.createElement('optgroup');
    grp.label = cat;
    chs.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = '# ' + c.name;
      if (c.id === String(currentId)) opt.selected = true;
      grp.appendChild(opt);
    });
    sel.appendChild(grp);
  });
}

function buildRoleSelect(sel, roles, currentId) {
  if (!roles || !roles.length) return;
  sel.innerHTML = '<option value="">— None —</option>';
  roles.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r.id;
    const hex = r.color ? '#' + r.color.toString(16).padStart(6, '0') : '#555';
    opt.textContent = r.name;
    opt.dataset.color = hex;
    if (r.id === String(currentId)) opt.selected = true;
    sel.appendChild(opt);
  });
}
</script>
"""


# ── HTML templates ─────────────────────────────────────────────────────────────

LANDING_HTML = BASE_CSS + """
<title>LuxeBot — Premium Discord Management</title>
<style>
.hero{display:flex;flex-direction:column;align-items:center;justify-content:center;
  min-height:85vh;text-align:center;padding:40px 20px;position:relative;z-index:1}
.hero-badge{display:inline-block;padding:5px 16px;border:1px solid var(--gold-dim);
  border-radius:20px;font-size:.75rem;color:var(--gold);letter-spacing:2px;
  text-transform:uppercase;margin-bottom:20px}
h1.hero-title{font-family:'Bebas Neue',sans-serif;font-size:clamp(3rem,8vw,6.5rem);
  line-height:.95;letter-spacing:2px;margin-bottom:20px}
h1 .gold{color:var(--gold)}
.hero-sub{font-size:1rem;color:var(--muted2);max-width:460px;line-height:1.7;margin-bottom:36px}
.hero-btns{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}
.orb{position:absolute;width:500px;height:500px;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,rgba(201,168,76,.05) 0%,transparent 70%)}
.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
  gap:16px;padding:40px;max-width:1100px;margin:0 auto;position:relative;z-index:1}
.feat{background:var(--dark2);border:1px solid var(--dark4);border-radius:12px;
  padding:24px;transition:all .3s}
.feat:hover{border-color:var(--gold-dim);transform:translateY(-3px)}
.feat-icon{font-size:1.8rem;margin-bottom:12px}
.feat h3{font-size:.9rem;font-weight:600;margin-bottom:6px}
.feat p{font-size:.82rem;color:var(--muted2);line-height:1.6}
footer{text-align:center;padding:32px;border-top:1px solid var(--dark4);
  color:var(--muted);font-size:.82rem;position:relative;z-index:1}
footer a{color:var(--gold)}
</style>
<body>
<nav class="topnav">
  <div class="logo">LUXE<span>BOT</span></div>
  <div class="nav-actions">
    {% if user %}
      <a href="/servers" class="btn btn-gold">My Servers</a>
      <a href="/logout" class="btn btn-outline">Logout</a>
    {% endif %}
  </div>
</nav>
<section class="hero">
  <div class="orb" style="top:-120px;left:-120px"></div>
  <div class="orb" style="bottom:-120px;right:-120px"></div>
  <div class="hero-badge">👑 Premium Discord Management</div>
  <h1 class="hero-title">The Bot Your<br>Server <span class="gold">Deserves</span></h1>
  <p class="hero-sub">Moderation, leveling, giveaways, tickets, YouTube, Twitch &amp; Reddit alerts — all for $5/month.</p>
  <div class="hero-btns">
    <a href="https://whop.com/luxebot/luxebot-premium" target="_blank"
       class="btn btn-gold" style="padding:13px 30px;font-size:1rem">👑 Get Premium — $5/month</a>
    {% if user %}
      <a href="/servers" class="btn btn-ghost" style="padding:13px 30px;font-size:.95rem">Manage My Servers</a>
    {% endif %}
  </div>
</section>
<section class="features">
  {% for icon,name,desc in [
    ('🛡️','Full Moderation','Ban, kick, mute, warn, purge — with auto-escalation.'),
    ('🤖','AutoMod','Anti-spam, anti-caps, link filter, bad words, anti-raid.'),
    ('⭐','Leveling','XP, leaderboards, level-up messages, role rewards.'),
    ('🎉','Giveaways','Start giveaways with one command. Auto-picks winners.'),
    ('🎫','Ticket System','One-click tickets with button panels and private channels.'),
    ('📺','Social Alerts','YouTube, Twitch, and Reddit alerts posted automatically.'),
  ] %}
  <div class="feat"><div class="feat-icon">{{icon}}</div><h3>{{name}}</h3><p>{{desc}}</p></div>
  {% endfor %}
</section>
<footer>LuxeBot — Premium Discord Management · <a href="https://whop.com/luxebot/luxebot-premium">Get Premium</a></footer>
</body>
"""

SERVERS_HTML = BASE_CSS + """
<title>Select Server — LuxeBot</title>
<style>
.container{max-width:900px;margin:0 auto;padding:48px 32px;position:relative;z-index:1}
.page-heading{font-family:'Bebas Neue',sans-serif;font-size:2.2rem;letter-spacing:2px;margin-bottom:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin-top:32px}
.scard{background:var(--dark2);border:1px solid var(--dark4);border-radius:12px;
  padding:22px;display:flex;flex-direction:column;align-items:center;gap:10px;
  transition:all .25s;cursor:pointer}
.scard:hover{border-color:var(--gold-mid);transform:translateY(-3px)}
.scard-icon{width:60px;height:60px;border-radius:50%;border:2px solid var(--dark4);object-fit:cover}
.scard-ph{width:60px;height:60px;border-radius:50%;background:var(--dark3);
  display:flex;align-items:center;justify-content:center;
  font-family:'Bebas Neue',sans-serif;font-size:1.3rem;color:var(--gold)}
.scard-name{font-weight:600;font-size:.9rem;text-align:center}
.ua-info{display:flex;align-items:center;gap:10px}
.ua-avatar{width:30px;height:30px;border-radius:50%;border:2px solid var(--dark4)}
.ua-name{font-size:.85rem;color:var(--muted2)}
</style>
<body>
<nav class="topnav">
  <a href="/" class="logo">LUXE<span>BOT</span></a>
  <div class="nav-actions">
    {% if user %}
    <div class="ua-info">
      {% if user.avatar %}
        <img src="https://cdn.discordapp.com/avatars/{{user.id}}/{{user.avatar}}.png" class="ua-avatar">
      {% endif %}
      <span class="ua-name">{{user.username}}</span>
    </div>
    {% endif %}
    <a href="/logout" class="btn btn-ghost btn-sm">Logout</a>
  </div>
</nav>
<div class="container">
  <div class="page-heading">Your Servers</div>
  <div style="color:var(--muted2);font-size:.875rem">Select a server to configure LuxeBot</div>
  {% if guilds %}
  <div class="grid">
    {% for g in guilds %}
    <a href="/dashboard/{{g.id}}" class="scard">
      {% if g.icon %}
        <img src="https://cdn.discordapp.com/icons/{{g.id}}/{{g.icon}}.png" class="scard-icon">
      {% else %}
        <div class="scard-ph">{{g.name[0]}}</div>
      {% endif %}
      <div class="scard-name">{{g.name}}</div>
      <div class="btn btn-gold btn-sm" style="width:100%;justify-content:center">Manage</div>
    </a>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty" style="margin-top:60px">
    <div class="ico">🤖</div>
    <div>No servers found where you have admin access and LuxeBot is added.</div>
    <a href="https://whop.com/luxebot/luxebot-premium" target="_blank"
       style="color:var(--gold);font-size:.85rem;margin-top:10px;display:inline-block">Add LuxeBot to a server →</a>
  </div>
  {% endif %}
</div>
</body>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
""" + BASE_CSS + BASE_JS + """
<title>{{guild.name}} — LuxeBot</title>
<style>
.section{display:none}.section.active{display:block}
.rr-row{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--dark4);font-size:.85rem}
.rr-row:last-child{border-bottom:none}
.pill{background:var(--dark3);padding:3px 10px;border-radius:12px;font-size:.78rem}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div class="sidebar" id="sidebar">
  <div class="sidebar-head">
    <a href="/" class="logo" style="font-size:1.4rem">LUXE<span>BOT</span></a>
  </div>
  <div class="sidebar-server">
    {% if guild.icon %}
      <img src="https://cdn.discordapp.com/icons/{{guild.id}}/{{guild.icon}}.png" class="srv-icon">
    {% else %}
      <div class="srv-icon-ph">{{guild.name[0]}}</div>
    {% endif %}
    <div class="srv-name">{{guild.name}}</div>
  </div>
  <nav class="sidebar-nav">
    <button class="nav-item active" onclick="showSection('overview',this)">📊 Overview</button>
    <button class="nav-item" onclick="showSection('general',this)">⚙️ General</button>
    <div class="nav-sep"></div>
    <button class="nav-item" onclick="showSection('welcome',this)">👋 Welcome &amp; Roles</button>
    <button class="nav-item" onclick="showSection('automod',this)">🤖 AutoMod</button>
    <button class="nav-item" onclick="showSection('tickets',this)">🎫 Tickets</button>
    <button class="nav-item" onclick="showSection('leveling',this)">⭐ Leveling</button>
    <button class="nav-item" onclick="showSection('alerts',this)">📺 Alerts</button>
    <button class="nav-item" onclick="showSection('reaction_roles',this)">🎭 Reaction Roles</button>
    <button class="nav-item" onclick="showSection('commands',this)">⌨️ Custom Commands</button>
  </nav>
  <div class="sidebar-foot">
    <a href="/servers" class="btn btn-ghost btn-sm" style="width:100%;justify-content:center">← All Servers</a>
  </div>
</div>

<!-- MAIN -->
<div class="main-content">

<!-- OVERVIEW -->
<div id="sec-overview" class="section active">
  <div class="page-head">
    <div class="page-title">Overview</div>
    {% if s.is_premium %}
      <span class="badge badge-gold">👑 Premium</span>
    {% elif s.is_trial %}
      <span class="badge badge-green">🕐 Trial — {{s.trial_days_left}}d left</span>
    {% else %}
      <span class="badge badge-muted" style="color:#ef4444;border-color:rgba(239,68,68,.3);background:rgba(239,68,68,.08)">⏰ Trial Expired</span>
    {% endif %}
  </div>
  <div class="stats-grid">
    <div class="stat"><div class="stat-val">{{s.prefix}}</div><div class="stat-lbl">Prefix</div></div>
    <div class="stat"><div class="stat-val">{{s.warn_count}}</div><div class="stat-lbl">Total Warnings</div></div>
    <div class="stat"><div class="stat-val">{{s.alert_count}}</div><div class="stat-lbl">Active Alerts</div></div>
    <div class="stat"><div class="stat-val">{{s.custom_commands|length}}</div><div class="stat-lbl">Custom Commands</div></div>
  </div>
  {% if not s.is_premium and not s.is_trial %}
  <div class="card" style="border-color:rgba(239,68,68,.3);background:rgba(239,68,68,.04)">
    <div class="card-title" style="color:#ef4444">⏰ Trial Expired</div>
    <p style="color:var(--muted2);font-size:.875rem;margin-bottom:16px">Your 7-day free trial has ended. Subscribe to restore all features.</p>
    <a href="https://whop.com/luxebot/luxebot-premium" target="_blank" class="btn btn-gold">Subscribe — $5/month</a>
  </div>
  {% elif s.is_trial %}
  <div class="card" style="border-color:var(--gold-dim)">
    <div class="card-title">👑 {{s.trial_days_left}} day{% if s.trial_days_left != 1 %}s{% endif %} left in your free trial</div>
    <p style="color:var(--muted2);font-size:.875rem;margin-bottom:16px">Subscribe now to keep all features after your trial ends. <strong>$5/month</strong> — no feature locks, no upsells.</p>
    <a href="https://whop.com/luxebot/luxebot-premium" target="_blank" class="btn btn-gold">Subscribe — $5/month</a>
  </div>
  {% endif %}
  <div class="card">
    <div class="card-title">🤖 AI Moderation</div>
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <span class="badge badge-green">Active</span>
      <span style="font-size:.85rem;color:var(--muted2)">Toxicity · Hate speech · Leet-speak evasion · Raid detection · Suspicious accounts</span>
    </div>
    <div style="margin-top:10px;font-size:.8rem;color:var(--muted2)">
      Use <code class="cmd">/aimod</code> in Discord to check live status and API call rate.
    </div>
  </div>
  <div class="card">
    <div class="card-title">⚡ Quick Links</div>
    <div style="margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="font-size:.8rem;color:var(--muted2)">Channel/role pickers loaded on page load · </span>
      <button class="btn btn-ghost btn-sm" onclick="refreshPickers()">🔄 Refresh Channels & Roles</button>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn btn-ghost btn-sm" onclick="showSection('welcome',document.querySelector('[onclick*=welcome]'))">Set Welcome Message</button>
      <button class="btn btn-ghost btn-sm" onclick="showSection('automod',document.querySelector('[onclick*=automod]'))">Configure AutoMod</button>
      <button class="btn btn-ghost btn-sm" onclick="showSection('tickets',document.querySelector('[onclick*=tickets]'))">Set Up Tickets</button>
      <button class="btn btn-ghost btn-sm" onclick="showSection('alerts',document.querySelector('[onclick*=alerts]'))">Add Alerts</button>
    </div>
  </div>
</div>

<!-- GENERAL -->
<div id="sec-general" class="section">
  <div class="page-head"><div class="page-title">General Settings</div></div>
  <form id="form-general">
  <div class="card">
    <div class="card-title">⚙️ Bot Configuration</div>
    <div class="form-row">
      <div class="form-group">
        <label class="lbl">Bot Prefix</label>
        <input class="input" name="prefix" value="{{s.prefix}}" maxlength="5" style="max-width:100px">
        <div class="hint">Used for legacy prefix commands (e.g. ! or ?)</div>
      </div>
      <div class="form-group">
        <label class="lbl">Mod Log Channel ID</label>
        <select class="input" name="log_channel" data-picker="channel" data-current="{{s.log_channel or ''}}">
          <option value="">— select a channel —</option>
        </select>
        <div class="manual-input" id="manual-log-channel">
          <input class="input" name="log_channel_manual" placeholder="or paste Channel ID">
        </div>
        <div class="hint">Message edits/deletes and mod actions are logged here</div>
      </div>
    </div>
    <div class="save-bar">
      <button type="button" id="save-btn-general" class="btn btn-gold" onclick="saveSection('general')">Save Changes</button>
    </div>
  </div>
  </form>
</div>

<!-- WELCOME -->
<div id="sec-welcome" class="section">
  <div class="page-head"><div class="page-title">Welcome &amp; Roles</div></div>
  <form id="form-welcome">
  <div class="card">
    <div class="card-title">👋 Welcome Message</div>
    <div class="form-row">
      <div class="form-group">
        <label class="lbl">Welcome Channel ID</label>
        <select class="input" name="welcome_channel" data-picker="channel" data-current="{{s.welcome_channel or ''}}">
          <option value="">— select a channel —</option>
        </select>
        <div class="picker-hint">Select the channel where welcome messages will be sent</div>
      </div>
      <div class="form-group">
        <label class="lbl">Auto Join Role ID</label>
        <select class="input" name="autorole" data-picker="role" data-current="{{s.autorole or ''}}">
          <option value="">— no auto role —</option>
        </select>
        <div class="picker-hint">Members get this role automatically when they join</div>
        <div class="hint">Assigned automatically when someone joins</div>
      </div>
    </div>
    <div class="form-group">
      <label class="lbl">Welcome Message</label>
      <textarea class="input" name="welcome_message" placeholder="Welcome {user} to {server}! You are member #{membercount}.">{{s.welcome_message or ''}}</textarea>
      <div class="hint">Variables: <code style="color:var(--gold)">{user}</code> <code style="color:var(--gold)">{server}</code> <code style="color:var(--gold)">{membercount}</code></div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">👋 Goodbye Message</div>
    <div class="form-group">
      <label class="lbl">Goodbye Message</label>
      <textarea class="input" name="goodbye_message" placeholder="{user} has left {server}. Goodbye!">{{s.goodbye_message or ''}}</textarea>
      <div class="hint">Sent in the welcome channel when a member leaves. Same variables apply.</div>
    </div>
    <div class="save-bar">
      <button type="button" id="save-btn-welcome" class="btn btn-gold" onclick="saveSection('welcome')">Save Changes</button>
    </div>
  </div>
  </form>
</div>

<!-- AUTOMOD -->
<div id="sec-automod" class="section">
  <div class="page-head"><div class="page-title">AutoMod</div></div>
  <form id="form-automod">
  <div class="card">
    <div class="card-title">🛡️ Filters</div>
    <div class="toggle-list">
      {% for field, label, desc in [
        ('anti_spam', 'Anti-Spam', 'Auto-mute members sending messages too rapidly'),
        ('anti_caps', 'Anti-Caps', 'Delete messages with excessive capital letters (>70%)'),
        ('anti_links', 'Anti-Links', 'Block non-moderators from posting URLs'),
        ('anti_mentions', 'Anti-Mention Spam', 'Mute members who mass-ping 5+ users at once'),
        ('anti_raid', 'Anti-Raid', 'Detect and slow join floods'),
      ] %}
      <div class="toggle-row">
        <div class="toggle-info"><h4>{{label}}</h4><p>{{desc}}</p></div>
        <label class="toggle">
          <input type="checkbox" name="{{field}}" {{'checked' if s.automod[field] else ''}}>
          <span class="slider"></span>
        </label>
      </div>
      {% endfor %}
    </div>
    <div class="save-bar">
      <button type="button" id="save-btn-automod" class="btn btn-gold" onclick="saveSection('automod')">Save Changes</button>
    </div>
  </div>
  </form>
  <div class="card">
    <div class="card-title">🚫 Bad Word Filter</div>
    {% if s.badwords %}
    <div class="tag-list" style="margin-bottom:16px">
      {% for w in s.badwords %}
      <div class="tag">
        <span>{{w}}</span>
        <span class="del" onclick="quickAction('automod',{badword_remove:{{w|tojson}}})">✕</span>
      </div>
      {% endfor %}
    </div>
    {% else %}
    <div class="empty"><div class="ico">🚫</div>No bad words configured</div>
    {% endif %}
    <div class="input-row" style="margin-top:12px">
      <input class="input" id="bw-input" placeholder="Add a word to block…">
      <button class="btn btn-gold" onclick="quickAction('automod',{badword_add:document.getElementById('bw-input').value})">Add</button>
    </div>
  </div>
</div>

<!-- TICKETS -->
<div id="sec-tickets" class="section">
  <div class="page-head"><div class="page-title">Ticket System</div></div>
  {% if not s.tickets.category_id %}
  <div class="alert alert-warn">⚠️ Ticket category not set up yet. Use <code class="cmd">/ticketsetup</code> in Discord to create the category, then configure it here.</div>
  {% endif %}
  <form id="form-tickets">
  <div class="card">
    <div class="card-title">🎫 Configuration</div>
    <div class="form-row">
      <div class="form-group">
        <label class="lbl">Support Role ID</label>
        <select class="input" name="support_role" data-picker="role" data-current="{{s.tickets.support_role or ''}}">
          <option value="">— select a role —</option>
        </select>
        <div class="picker-hint">This role can see and reply in all open tickets</div>
        <div class="hint">This role can see and respond to all tickets</div>
      </div>
      <div class="form-group">
        <label class="lbl">Ticket Log Channel ID</label>
        <select class="input" name="log_channel" data-picker="channel" data-current="{{s.tickets.log_channel or ''}}">
          <option value="">— select a channel —</option>
        </select>
        <div class="picker-hint">Closed ticket summaries are posted here</div>
        <div class="hint">Closed ticket summaries are sent here</div>
      </div>
    </div>
    <div class="alert alert-info" style="margin-top:4px">
      💡 Use <code class="cmd">/ticketpanel #channel</code> in Discord to post the ticket panel button.
    </div>
    <div class="save-bar">
      <button type="button" id="save-btn-tickets" class="btn btn-gold" onclick="saveSection('tickets')">Save Changes</button>
    </div>
  </div>
  </form>
</div>

<!-- LEVELING -->
<div id="sec-leveling" class="section">
  <div class="page-head"><div class="page-title">Leveling</div></div>
  <div class="card">
    <div class="card-title">🏆 Level Roles</div>
    {% if s.level_roles %}
    <table class="table">
      <thead><tr><th>Level</th><th>Role ID</th><th></th></tr></thead>
      <tbody>
        {% for lr in s.level_roles %}
        <tr>
          <td><span class="pill">Level {{lr.level}}</span></td>
          <td style="color:var(--muted2)">{{lr.role_id}}</td>
          <td><button class="btn btn-danger btn-sm" onclick="quickAction('leveling',{level_role_remove:{{lr.level|tojson}}})">Remove</button></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty"><div class="ico">⭐</div>No level roles configured</div>
    {% endif %}
  </div>
  <div class="card">
    <div class="card-title">➕ Add Level Role</div>
    <form id="form-leveling">
    <div class="form-row">
      <div class="form-group">
        <label class="lbl">Unlock Level</label>
        <input class="input" name="level_role_add_level" type="number" min="1" max="999" placeholder="e.g. 5">
      </div>
      <div class="form-group">
        <label class="lbl">Role ID</label>
        <select class="input" name="level_role_add_role" data-picker="role" data-current="">
          <option value="">— select a role —</option>
        </select>
        <div class="picker-hint">Select the role to award at this level</div>
      </div>
    </div>
    <div class="save-bar">
      <button type="button" id="save-btn-leveling" class="btn btn-gold" onclick="saveSection('leveling')">Add Role</button>
    </div>
    </form>
  </div>
  <div class="card">
    <div class="card-title">ℹ️ How XP Works</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:.85rem;color:var(--muted2)">
      <div style="background:var(--dark3);padding:14px;border-radius:8px">
        <div style="color:var(--gold);font-weight:600;margin-bottom:6px">📝 Message XP</div>
        15–25 XP per message · 60s cooldown<br>
        +25% streak bonus (3+ day streak)<br>
        +20% weekend bonus (Sat–Sun)<br>
        +50% server booster bonus<br>
        Per-channel multipliers supported
      </div>
      <div style="background:var(--dark3);padding:14px;border-radius:8px">
        <div style="color:var(--gold);font-weight:600;margin-bottom:6px">🎤 Voice XP</div>
        10 XP per minute in voice channels<br>
        Granted every 5 minutes (live)<br>
        Also granted when leaving voice<br>
        Capped at 500 XP per session<br>
        Weekend/booster bonuses apply
      </div>
    </div>
    <div style="margin-top:12px;font-size:.82rem;color:var(--muted2)">
      Role rewards <strong style="color:var(--text)">stack</strong> — members keep every role earned at prior levels.
      Use <code class="cmd">/setxpmultiplier #channel 2.0</code> to set per-channel multipliers.
      Use <code class="cmd">/setlevelmessage 10 "Congrats {user}!"</code> for custom milestone messages.
    </div>
  </div>
</div>

<!-- ALERTS -->
<div id="sec-alerts" class="section">
  <div class="page-head"><div class="page-title">Social Alerts</div></div>

  <!-- YouTube -->
  <div class="card">
    <div class="card-title">📺 YouTube Alerts</div>
    {% if s.youtube_alerts %}
    <table class="table">
      <thead><tr><th>Channel</th><th>Posts To</th><th></th></tr></thead>
      <tbody>
        {% for a in s.youtube_alerts %}
        <tr>
          <td>{{a.channel}}</td>
          <td style="color:var(--muted2)">#{{a.discord_channel}}</td>
          <td><button class="btn btn-danger btn-sm" onclick="quickAction('alerts',{yt_remove:{{a.channel|tojson}}})">Remove</button></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty"><div class="ico">📺</div>No YouTube alerts configured</div>
    {% endif %}
    <div class="alert alert-info" style="margin-top:12px">
      💡 Add alerts with <code class="cmd">/youtubealert MrBeast #alerts</code> in Discord
    </div>
  </div>

  <!-- Twitch -->
  <div class="card">
    <div class="card-title">🟣 Twitch Alerts</div>
    {% if s.twitch_alerts %}
    <table class="table">
      <thead><tr><th>Streamer</th><th>Posts To</th><th></th></tr></thead>
      <tbody>
        {% for a in s.twitch_alerts %}
        <tr>
          <td>{{a.streamer}}</td>
          <td style="color:var(--muted2)">#{{a.discord_channel}}</td>
          <td><button class="btn btn-danger btn-sm" onclick="quickAction('alerts',{twitch_remove:{{a.streamer|tojson}}})">Remove</button></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty"><div class="ico">🟣</div>No Twitch alerts configured</div>
    {% endif %}
    <div class="alert alert-info" style="margin-top:12px">
      💡 Add alerts with <code class="cmd">/twitchalert pokimane #streams</code> in Discord
    </div>
  </div>

  <!-- Reddit -->
  <div class="card">
    <div class="card-title">🟠 Reddit Alerts</div>
    {% if s.reddit_alerts %}
    <table class="table">
      <thead><tr><th>Subreddit</th><th>Posts To</th><th></th></tr></thead>
      <tbody>
        {% for a in s.reddit_alerts %}
        <tr>
          <td>r/{{a.subreddit}}</td>
          <td style="color:var(--muted2)">#{{a.discord_channel}}</td>
          <td><button class="btn btn-danger btn-sm" onclick="quickAction('alerts',{reddit_remove:{{a.subreddit|tojson}}})">Remove</button></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty"><div class="ico">🟠</div>No Reddit alerts configured</div>
    {% endif %}
    <div class="alert alert-info" style="margin-top:12px">
      💡 Add alerts with <code class="cmd">/redditalert gaming #reddit</code> in Discord
    </div>
  </div>
</div>

<!-- REACTION ROLES -->
<div id="sec-reaction_roles" class="section">
  <div class="page-head"><div class="page-title">Reaction Roles</div></div>
  <div class="card">
    {% if s.reaction_roles %}
    <div class="card-title">🎭 Active Reaction Roles</div>
    {% for rr in s.reaction_roles %}
    <div class="rr-row">
      <span style="font-size:1.2rem">{{rr.emoji}}</span>
      <span style="flex:1;color:var(--muted2)">→ Role <code class="cmd">{{rr.role_id}}</code> on message <code class="cmd">{{rr.message_id}}</code></span>
    </div>
    {% endfor %}
    {% else %}
    <div class="empty"><div class="ico">🎭</div>No reaction roles configured</div>
    {% endif %}
    <div class="alert alert-info" style="margin-top:16px">
      💡 Set up reaction roles with <code class="cmd">/reactionrole &lt;message_id&gt; 🎮 @role</code> in Discord
    </div>
  </div>
</div>

<!-- CUSTOM COMMANDS -->
<div id="sec-commands" class="section">
  <div class="page-head"><div class="page-title">Custom Commands</div></div>
  <div class="card">
    {% if s.custom_commands %}
    <div class="card-title">⌨️ Active Commands</div>
    <table class="table">
      <thead><tr><th>Command</th><th>Response</th><th></th></tr></thead>
      <tbody>
        {% for cmd in s.custom_commands %}
        <tr>
          <td><code class="cmd">!{{cmd.command}}</code></td>
          <td style="color:var(--muted2);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{cmd.response}}</td>
          <td><button class="btn btn-danger btn-sm" onclick="quickAction('commands',{cmd_remove:{{cmd.command|tojson}}})">Remove</button></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty"><div class="ico">⌨️</div>No custom commands configured</div>
    {% endif %}
    <div class="alert alert-info" style="margin-top:12px">
      💡 Add custom commands with <code class="cmd">/addcommand &lt;name&gt; &lt;response&gt;</code> in Discord
    </div>
  </div>
</div>

</div><!-- end main-content -->
</div><!-- end layout -->
<div class="toast" id="toast"></div>
<script>
window.SAVE_URL = '/dashboard/{{guild_id}}/save';
window.GUILD_CHANNELS = {{ channels | tojson }};
window.GUILD_ROLES = {{ roles | tojson }};
document.querySelectorAll('select[data-picker="channel"]').forEach(function(sel) {
  buildChannelSelect(sel, window.GUILD_CHANNELS, sel.dataset.current);
});
document.querySelectorAll('select[data-picker="role"]').forEach(function(sel) {
  buildRoleSelect(sel, window.GUILD_ROLES, sel.dataset.current);
});
document.querySelectorAll('select[data-picker]').forEach(function(sel) {
  if (sel.options.length <= 1 && sel.dataset.fallback) {
    var fb = document.getElementById(sel.dataset.fallback);
    if (fb) fb.classList.add('show');
  }
});
</script>
</body>
</html>
"""


# ── Routes — Public ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(LANDING_HTML, user=session.get("user"))


@app.route("/login")
def login():
    return redirect(
        f"https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
    )


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("index"))

    resp = req_lib.post(
        f"{DISCORD_API}/oauth2/token",
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )
    if resp.status_code != 200:
        return redirect(url_for("index"))

    tokens = resp.json()
    session["access_token"] = tokens["access_token"]

    user_resp = req_lib.get(
        f"{DISCORD_API}/users/@me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=5
    )
    if user_resp.status_code == 200:
        session["user"] = user_resp.json()

    return redirect(url_for("servers"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ── Routes — Dashboard ────────────────────────────────────────────────────────

@app.route("/servers")
@login_required
def servers():
    guilds = get_user_guilds()
    return render_template_string(SERVERS_HTML, guilds=guilds, user=session.get("user"))


@app.route("/dashboard/<guild_id>")
@login_required
@guild_access_required
def dashboard(guild_id, guild):
    s        = db_get_guild(int(guild_id))
    channels = get_guild_channels(guild_id)
    roles    = get_guild_roles(guild_id)
    return render_template_string(
        DASHBOARD_HTML,
        guild=guild,
        guild_id=guild_id,
        s=s,
        channels=channels,
        roles=roles,
        user=session.get("user")
    )


@app.route("/dashboard/<guild_id>/save", methods=["POST"])
@login_required
@guild_access_required
def save_settings(guild_id, guild):
    data = request.json or {}
    section = data.pop("section", None)
    if not section:
        return jsonify({"status": "error", "message": "No section specified"}), 400

    valid_sections = {"general", "welcome", "automod", "tickets", "leveling", "alerts", "commands"}
    if section not in valid_sections:
        return jsonify({"status": "error", "message": "Invalid section"}), 400

    try:
        db_save_section(int(guild_id), section, data)
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Routes — Bot API (internal, key-protected) ────────────────────────────────

@app.route("/api/guild/<guild_id>/channels")
@login_required
@guild_access_required
def api_guild_channels(guild_id, guild):
    """AJAX: return fresh channel list for a guild (used by JS picker refresh)."""
    invalidate_guild_discord_cache(guild_id)
    return jsonify(get_guild_channels(guild_id))


@app.route("/api/guild/<guild_id>/roles")
@login_required
@guild_access_required
def api_guild_roles(guild_id, guild):
    """AJAX: return fresh role list for a guild (used by JS picker refresh)."""
    invalidate_guild_discord_cache(guild_id)
    return jsonify(get_guild_roles(guild_id))


@app.route("/api/guild/<int:guild_id>/settings", methods=["GET"])
@require_api_key
def api_get_guild_settings(guild_id):
    try:
        s = db_get_guild(guild_id)
        return jsonify(s)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/guild/<int:guild_id>/settings", methods=["POST"])
@require_api_key
def api_save_guild_settings(guild_id):
    data = request.json or {}
    section = data.pop("section", "general")
    try:
        db_save_section(guild_id, section, data)
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/guild/<int:guild_id>/premium", methods=["GET"])
@require_api_key
def api_get_premium(guild_id):
    async def _fetch():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT expires_at, trial_expires_at FROM premium_servers WHERE guild_id = ?", (guild_id,)
            ) as c:
                return await c.fetchone()
    row = run_async(_fetch())
    now = datetime.utcnow().isoformat()
    is_premium = bool(row and ((row[0] and row[0] > now) or (row[1] and row[1] > now)))
    return jsonify({"guild_id": guild_id, "is_premium": is_premium})


@app.route("/api/cache/stats", methods=["GET"])
@require_api_key
def api_cache_stats():
    try:
        async def _stats():
            from cache import cache_stats
            return await cache_stats()
        return jsonify(run_async(_stats()))
    except Exception as e:
        return jsonify({"status": "unavailable", "error": str(e)})


# ── Routes — Whop Webhook ─────────────────────────────────────────────────────

def _verify_whop_signature(raw_body: bytes, secret: str) -> bool:
    """
    Verify Whop's webhook HMAC-SHA256 signature.

    Whop signs requests with:
      X-Whop-Signature: sha256=<hex_digest>

    The signature is computed over the raw request body using the
    WHOP_WEBHOOK_SECRET as the key.

    Returns True if valid (or if no secret is configured — for dev/testing).
    Returns False if the signature is present but doesn't match.
    """
    import hmac as _hmac
    import hashlib as _hashlib

    if not secret:
        # No secret configured — accept all (dev mode). Log a warning.
        print("[Whop] WARNING: WHOP_WEBHOOK_SECRET not set — skipping signature verification")
        return True

    sig_header = request.headers.get("X-Whop-Signature", "")
    if not sig_header:
        # Whop may also send X-Whop-Webhook-Secret (older API versions)
        # Fall back to a simple token comparison
        token_header = request.headers.get("X-Whop-Webhook-Secret", "")
        if token_header:
            return _hmac.compare_digest(token_header, secret)
        print("[Whop] No signature header present — rejecting")
        return False

    # Extract hex digest from "sha256=<hex>" format
    if sig_header.startswith("sha256="):
        provided_hex = sig_header[7:]
    else:
        provided_hex = sig_header

    expected = _hmac.new(
        secret.encode("utf-8"),
        raw_body,
        _hashlib.sha256
    ).hexdigest()

    valid = _hmac.compare_digest(provided_hex, expected)
    if not valid:
        print(f"[Whop] Signature mismatch — provided: {provided_hex[:16]}... expected: {expected[:16]}...")
    return valid


@app.route("/webhook/whop", methods=["POST"])
def whop_webhook():
    # ── 1. Verify signature before reading any data ───────────────────────────
    raw_body = request.get_data()  # Read raw bytes before json parsing
    if not _verify_whop_signature(raw_body, WHOP_SECRET):
        print("[Whop] Rejected — invalid signature")
        return jsonify({"error": "invalid signature"}), 401

    # ── 2. Parse payload ──────────────────────────────────────────────────────
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400

    event        = data.get("event", "")
    payload_data = data.get("data", {})
    metadata     = payload_data.get("metadata", {})
    guild_id_raw = metadata.get("guild_id")

    print(f"[Whop] Event: {event} | guild_id: {guild_id_raw}")

    if not guild_id_raw:
        return jsonify({"status": "no guild_id in metadata"}), 200

    try:
        guild_id = int(guild_id_raw)
    except (ValueError, TypeError):
        return jsonify({"status": "invalid guild_id"}), 200

    # ── 3. Validate membership data is consistent ─────────────────────────────
    # Whop sends the full membership object in data — use it to double-check
    # the purchase is for LuxeBot's product (not a spoofed webhook for another product)
    product_id = payload_data.get("product_id") or payload_data.get("product", {}).get("id", "")
    expected_product = os.getenv("WHOP_PRODUCT_ID", "")  # Set in Railway env
    if expected_product and product_id and str(product_id) != str(expected_product):
        print(f"[Whop] Product ID mismatch — got {product_id}, expected {expected_product}")
        return jsonify({"status": "product mismatch"}), 200

    # ── 4. Apply the action ───────────────────────────────────────────────────
    GRANT_EVENTS  = {"membership.went_valid", "membership_activated", "membership.created"}
    REVOKE_EVENTS = {
        "membership.went_invalid", "membership_deactivated",
        "membership.deleted", "membership_cancel_at_period_end_changed",
        "membership.expired",
    }

    if event in GRANT_EVENTS:
        async def _grant():
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """INSERT INTO premium_servers (guild_id, expires_at)
                       VALUES (?, '9999-12-31')
                       ON CONFLICT(guild_id) DO UPDATE SET expires_at = '9999-12-31'""",
                    (guild_id,)
                )
                await db.commit()
        run_async(_grant())
        print(f"[Whop] ✅ Premium GRANTED to guild {guild_id}")

    elif event in REVOKE_EVENTS:
        async def _revoke():
            async with aiosqlite.connect(DB_PATH) as db:
                # Clear paid premium but preserve trial record
                await db.execute(
                    "UPDATE premium_servers SET expires_at = NULL WHERE guild_id = ?",
                    (guild_id,)
                )
                await db.commit()
        run_async(_revoke())
        print(f"[Whop] ❌ Premium REVOKED for guild {guild_id}")

    else:
        print(f"[Whop] Unhandled event type: {event} — no action taken")

    # ── 5. Bust Redis cache ───────────────────────────────────────────────────
    try:
        async def _bust():
            from cache import invalidate_premium
            await invalidate_premium(guild_id)
        run_async(_bust())
    except Exception:
        pass

    return jsonify({"status": "ok", "event": event, "guild_id": guild_id}), 200

# ── Top.gg vote helpers ──────────────────────────────────────────────────────

def apply_vote_bonus(user_id: int):
    """
    Write a 12-hour 2x XP bonus for a user who just voted.
    Called from the top.gg webhook and optionally from the /vote command.
    """
    async def _write():
        from datetime import datetime, timedelta
        expires_at = (datetime.utcnow() + timedelta(hours=12)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            # Ensure the vote_bonuses table exists (created by leveling cog on bot start,
            # but webhook.py runs independently so we create it here too)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS vote_bonuses (
                    user_id INTEGER PRIMARY KEY,
                    expires_at TEXT
                )
            """)
            await db.execute(
                "INSERT OR REPLACE INTO vote_bonuses (user_id, expires_at) VALUES (?, ?)",
                (user_id, expires_at)
            )
            await db.commit()
    run_async(_write())


# ── Top.gg webhook ────────────────────────────────────────────────────────────

@app.route("/webhook/topgg", methods=["POST"])
def topgg_webhook():
    """
    Receives vote events from top.gg.

    Configure in top.gg bot settings:
      Webhook URL: https://your-domain.com/webhook/topgg
      Authorization: <TOPGG_WEBHOOK_SECRET env var>

    Payload (top.gg sends this):
      {
        "bot":       "bot_id",
        "user":      "user_id",
        "type":      "upvote" | "test",
        "isWeekend": true | false,
        "query":     ""
      }
    """
    # Verify top.gg webhook authorization header
    topgg_secret = os.getenv("TOPGG_WEBHOOK_SECRET", "")
    if topgg_secret:
        auth = request.headers.get("Authorization", "")
        if auth != topgg_secret:
            return jsonify({"error": "unauthorized"}), 401

    data    = request.json or {}
    user_id = data.get("user")
    vote_type = data.get("type", "upvote")
    is_weekend = data.get("isWeekend", False)

    if not user_id:
        return jsonify({"status": "missing user"}), 400

    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"status": "invalid user_id"}), 400

    if vote_type == "test":
        print(f"[top.gg] Test webhook received for user {uid}")
        return jsonify({"status": "ok", "type": "test"}), 200

    # Apply the vote bonus (12h double XP, or 24h on weekends)
    async def _apply():
        from datetime import datetime, timedelta
        # Weekend votes count double on top.gg — extend bonus to 24h
        hours = 24 if is_weekend else 12
        expires_at = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS vote_bonuses (
                    user_id INTEGER PRIMARY KEY,
                    expires_at TEXT
                )
            """)
            await db.execute(
                "INSERT OR REPLACE INTO vote_bonuses (user_id, expires_at) VALUES (?, ?)",
                (uid, expires_at)
            )
            await db.commit()

    run_async(_apply())

    duration_str = "24 hours (weekend!)" if is_weekend else "12 hours"
    print(f"[top.gg] Vote recorded: user {uid} — 2x XP for {duration_str}")

    return jsonify({"status": "ok", "user": uid, "duration": duration_str}), 200


# ── Admin: grant premium ──────────────────────────────────────────────────────

@app.route("/admin/grant-premium", methods=["GET", "POST"])
@login_required
def admin_grant_premium():
    """
    Hidden admin route — only accessible by the bot owner (Bryce).
    GET  → show form
    POST → grant premium to a guild_id with optional expiry
    """
    user = session.get("user", {})
    if str(user.get("id", "")) != OWNER_ID:
        # Return a generic 404 so the route isn't discoverable
        from flask import abort
        abort(404)

    message = None
    error   = None

    if request.method == "POST":
        guild_id_raw = request.form.get("guild_id", "").strip()
        days_raw     = request.form.get("days", "").strip()
        action       = request.form.get("action", "grant")

        try:
            guild_id = int(guild_id_raw)
        except (ValueError, TypeError):
            error = "Invalid guild ID."
            guild_id = None

        if guild_id and action == "grant":
            async def _grant():
                from datetime import datetime, timedelta
                async with aiosqlite.connect(DB_PATH) as db:
                    if days_raw and days_raw.isdigit():
                        expires = (datetime.utcnow() + timedelta(days=int(days_raw))).isoformat()
                    else:
                        expires = "9999-12-31"
                    await db.execute(
                        "INSERT OR REPLACE INTO premium_servers (guild_id, expires_at) VALUES (?, ?)",
                        (guild_id, expires)
                    )
                    await db.commit()
            run_async(_grant())
            # Bust Redis premium cache
            try:
                run_async(__import__("cache").invalidate_premium(guild_id))
            except Exception:
                pass
            expiry_label = f"{days_raw} days" if days_raw and days_raw.isdigit() else "lifetime"
            message = f"✅ Premium granted to guild {guild_id} ({expiry_label})."

        elif guild_id and action == "revoke":
            async def _revoke():
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("DELETE FROM premium_servers WHERE guild_id = ?", (guild_id,))
                    await db.commit()
            run_async(_revoke())
            try:
                run_async(__import__("cache").invalidate_premium(guild_id))
            except Exception:
                pass
            message = f"🗑️ Premium revoked for guild {guild_id}."

    # Fetch current premium list
    async def _list():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, expires_at, trial_expires_at FROM premium_servers ORDER BY expires_at DESC"
            ) as cursor:
                return await cursor.fetchall()
    premium_list = run_async(_list())

    html = BASE_CSS + f"""
<title>LuxeBot Admin</title>
<body>
<nav class="topnav">
  <div class="logo">LUXE<span>BOT</span> <span style="font-size:.9rem;color:var(--muted2)">ADMIN</span></div>
  <a href="/logout" class="btn btn-ghost btn-sm">Logout</a>
</nav>
<div style="max-width:700px;margin:40px auto;padding:0 24px;position:relative;z-index:1">
  <h2 style="font-family:'Bebas Neue',sans-serif;font-size:1.8rem;letter-spacing:2px;margin-bottom:24px">
    Grant Premium Access
  </h2>

  {"<div class='alert alert-info'>" + message + "</div>" if message else ""}
  {"<div class='alert' style='background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:#ef4444'>" + error + "</div>" if error else ""}

  <div class="card">
    <div class="card-title">➕ Grant / Revoke Premium</div>
    <form method="POST">
      <div class="form-row">
        <div class="form-group">
          <label class="lbl">Guild ID</label>
          <input class="input" name="guild_id" placeholder="Discord server ID" required>
        </div>
        <div class="form-group">
          <label class="lbl">Days (blank = lifetime)</label>
          <input class="input" name="days" placeholder="e.g. 30 — or leave blank">
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:4px">
        <button class="btn btn-gold" name="action" value="grant">Grant Premium</button>
        <button class="btn btn-danger" name="action" value="revoke">Revoke Premium</button>
      </div>
    </form>
  </div>

  <div class="card">
    <div class="card-title">📋 Current Premium Servers ({len(premium_list)})</div>
    {"<div class='empty'><div class='ico'>💎</div>No premium servers yet</div>" if not premium_list else ""}
    {"".join(
      f"<div style='display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--dark4);font-size:.85rem'>"
      f"<span style='color:var(--text)'>{r[0]}</span>"
      f"<span style='color:var(--muted2)'>{('Lifetime' if r[1] == '9999-12-31' else r[1][:10]) if r[1] else ''}"
      f"{'  (trial: ' + r[2][:10] + ')' if r[2] else ''}</span>"
      f"</div>"
      for r in premium_list
    )}
  </div>
</div>
</body>
"""
    return html

# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "LuxeBot Dashboard"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
