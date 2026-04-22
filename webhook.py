import os
import hmac
import hashlib
import aiosqlite
import asyncio
from flask import Flask, request, jsonify
from functools import wraps

app = Flask(__name__)

WHOP_SECRET = os.getenv("WHOP_WEBHOOK_SECRET", "luxebot_secret_123")
API_SECRET = os.getenv("DASHBOARD_SECRET", "luxebot123")
DB_PATH = "luxebot.db"


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if key != API_SECRET:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def run_async(coro):
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(coro)
    loop.close()
    return result


# ── Whop Webhook ─────────────────────────────────────────────

async def add_premium_db(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO premium_servers (guild_id, expires_at) VALUES (?, '9999-12-31')",
            (guild_id,)
        )
        await db.commit()


async def remove_premium_db(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM premium_servers WHERE guild_id = ?",
            (guild_id,)
        )
        await db.commit()


@app.route("/webhook/whop", methods=["POST"])
def whop_webhook():
    data = request.json or {}
    event = data.get("event", "")
    metadata = data.get("data", {}).get("metadata", {})
    guild_id = metadata.get("guild_id")

    if not guild_id:
        return jsonify({"status": "no guild_id"}), 200

    try:
        guild_id = int(guild_id)
    except (ValueError, TypeError):
        return jsonify({"status": "invalid guild_id"}), 200

    if event in ["membership.went_valid", "membership_activated"]:
        run_async(add_premium_db(guild_id))
        print(f"Added premium for guild {guild_id}")
    elif event in ["membership.went_invalid", "membership_deactivated",
                   "membership.deleted", "membership_cancel_at_period_end_changed"]:
        run_async(remove_premium_db(guild_id))
        print(f"Removed premium for guild {guild_id}")

    return jsonify({"status": "ok"}), 200


# ── Guild API ─────────────────────────────────────────────────

@app.route("/api/guild/<int:guild_id>/settings", methods=["GET"])
@require_api_key
def get_guild_settings(guild_id):
    async def fetch():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, prefix, log_channel, welcome_channel, welcome_message, goodbye_message, mute_role, autorole FROM guilds WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
            async with db.execute(
                "SELECT anti_spam, anti_caps, anti_links, anti_mentions, anti_raid FROM automod_settings WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                automod = await cursor.fetchone()
            async with db.execute(
                "SELECT expires_at, trial_expires_at FROM premium_servers WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                premium = await cursor.fetchone()
        return row, automod, premium

    row, automod, premium = run_async(fetch())

    from datetime import datetime
    is_premium = False
    if premium:
        now = datetime.utcnow().isoformat()
        if premium[0] and premium[0] > now:
            is_premium = True
        if premium[1] and premium[1] > now:
            is_premium = True

    return jsonify({
        "guild_id": guild_id,
        "prefix": row[1] if row else "!",
        "log_channel": row[2] if row else None,
        "welcome_channel": row[3] if row else None,
        "welcome_message": row[4] if row else "",
        "goodbye_message": row[5] if row else "",
        "mute_role": row[6] if row else None,
        "autorole": row[7] if row else None,
        "automod": {
            "anti_spam": bool(automod[0]) if automod else False,
            "anti_caps": bool(automod[1]) if automod else False,
            "anti_links": bool(automod[2]) if automod else False,
            "anti_mentions": bool(automod[3]) if automod else False,
            "anti_raid": bool(automod[4]) if automod else False,
        },
        "is_premium": is_premium
    })


@app.route("/api/guild/<int:guild_id>/settings", methods=["POST"])
@require_api_key
def save_guild_settings(guild_id):
    data = request.json or {}

    async def update():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,)
            )
            await db.execute(
                "INSERT OR IGNORE INTO automod_settings (guild_id) VALUES (?)", (guild_id,)
            )
            if "prefix" in data:
                await db.execute(
                    "UPDATE guilds SET prefix = ? WHERE guild_id = ?",
                    (data["prefix"], guild_id)
                )
            if "welcome_message" in data:
                await db.execute(
                    "UPDATE guilds SET welcome_message = ? WHERE guild_id = ?",
                    (data["welcome_message"], guild_id)
                )
            if "automod" in data:
                am = data["automod"]
                if "anti_spam" in am:
                    await db.execute(
                        "UPDATE automod_settings SET anti_spam = ? WHERE guild_id = ?",
                        (1 if am["anti_spam"] else 0, guild_id)
                    )
                if "anti_caps" in am:
                    await db.execute(
                        "UPDATE automod_settings SET anti_caps = ? WHERE guild_id = ?",
                        (1 if am["anti_caps"] else 0, guild_id)
                    )
                if "anti_links" in am:
                    await db.execute(
                        "UPDATE automod_settings SET anti_links = ? WHERE guild_id = ?",
                        (1 if am["anti_links"] else 0, guild_id)
                    )
                if "anti_mentions" in am:
                    await db.execute(
                        "UPDATE automod_settings SET anti_mentions = ? WHERE guild_id = ?",
                        (1 if am["anti_mentions"] else 0, guild_id)
                    )
            await db.commit()

    run_async(update())
    return jsonify({"status": "saved"})


@app.route("/api/guild/<int:guild_id>/premium", methods=["GET"])
@require_api_key
def get_premium_status(guild_id):
    async def fetch():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT expires_at, trial_expires_at FROM premium_servers WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                return await cursor.fetchone()

    from datetime import datetime
    row = run_async(fetch())
    now = datetime.utcnow().isoformat()
    is_premium = False
    if row:
        if row[0] and row[0] > now:
            is_premium = True
        if row[1] and row[1] > now:
            is_premium = True

    return jsonify({"guild_id": guild_id, "is_premium": is_premium})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "LuxeBot"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
