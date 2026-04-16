from flask import Flask, request, jsonify
import aiosqlite
import asyncio
import hmac
import hashlib
import os
from datetime import datetime

app = Flask(__name__)

WHOP_SECRET = os.getenv("WHOP_WEBHOOK_SECRET", "your_whop_secret_here")
DB_PATH = "luxebot.db"

def verify_signature(payload, signature):
    expected = hmac.new(
        WHOP_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

async def add_premium(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO premium_servers (guild_id) VALUES (?)",
            (guild_id,)
        )
        await db.commit()
    print(f"[{datetime.utcnow()}] Added premium: guild {guild_id}")

async def remove_premium(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM premium_servers WHERE guild_id = ?",
            (guild_id,)
        )
        await db.commit()
    print(f"[{datetime.utcnow()}] Removed premium: guild {guild_id}")

@app.route("/webhook/whop", methods=["POST"])
def whop_webhook():
    signature = request.headers.get("X-Whop-Signature", "")
    payload = request.get_data()

    if not verify_signature(payload, signature):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json()
    event = data.get("event")
    membership = data.get("data", {})
    metadata = membership.get("metadata", {})
    guild_id = metadata.get("guild_id")

    if not guild_id:
        return jsonify({"error": "No guild_id in metadata"}), 400

    guild_id = int(guild_id)

    if event in ("membership.went_valid", "membership.created"):
        asyncio.run(add_premium(guild_id))
        return jsonify({"status": "premium added"}), 200

    elif event in ("membership.went_invalid", "membership.deleted", "membership.expired"):
        asyncio.run(remove_premium(guild_id))
        return jsonify({"status": "premium removed"}), 200

    return jsonify({"status": "event ignored"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
