import os
import hmac
import hashlib
import aiosqlite
from flask import Flask, request, jsonify
import asyncio

app = Flask(__name__)

WHOP_SECRET = os.getenv("WHOP_WEBHOOK_SECRET", "luxebot_secret_123")
DB_PATH = "luxebot.db"


def verify_signature(payload, signature):
    expected = hmac.new(
        WHOP_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


async def add_premium(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO premium_servers (guild_id, expires_at) VALUES (?, '9999-12-31')",
            (guild_id,)
        )
        await db.commit()


async def remove_premium(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM premium_servers WHERE guild_id = ?",
            (guild_id,)
        )
        await db.commit()


@app.route("/webhook/whop", methods=["POST"])
def whop_webhook():
    signature = request.headers.get("X-Whop-Signature", "")
    payload = request.get_data()

    data = request.json
    event = data.get("event", "")
    metadata = data.get("data", {}).get("metadata", {})
    guild_id = metadata.get("guild_id")

    if not guild_id:
        return jsonify({"status": "no guild_id"}), 200

    try:
        guild_id = int(guild_id)
    except (ValueError, TypeError):
        return jsonify({"status": "invalid guild_id"}), 200

    loop = asyncio.new_event_loop()

    if event in ["membership.went_valid", "membership_activated"]:
        loop.run_until_complete(add_premium(guild_id))
        print(f"Added premium for guild {guild_id}")
    elif event in ["membership.went_invalid", "membership_deactivated",
                   "membership.deleted", "membership_cancel_at_period_end_changed"]:
        loop.run_until_complete(remove_premium(guild_id))
        print(f"Removed premium for guild {guild_id}")

    loop.close()
    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "LuxeBot"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
