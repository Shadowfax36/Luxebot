import os
import json
import aiosqlite
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
import requests
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET", "luxebot_dashboard_secret")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
DISCORD_API = "https://discord.com/api/v10"
DB_PATH = "luxebot.db"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_user_guilds():
    token = session.get("access_token")
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{DISCORD_API}/users/@me/guilds", headers=headers)
    if resp.status_code == 200:
        guilds = resp.json()
        # Only return guilds where user has MANAGE_GUILD permission
        return [g for g in guilds if (int(g["permissions"]) & 0x20) == 0x20]
    return []


@app.route("/")
def index():
    user = session.get("user")
    return render_template("index.html", user=user)


@app.route("/login")
def login():
    scope = "identify guilds"
    return redirect(
        f"https://discord.com/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={scope}"
    )


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect(url_for("index"))

    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(f"{DISCORD_API}/oauth2/token", data=data, headers=headers)

    if resp.status_code != 200:
        return redirect(url_for("index"))

    tokens = resp.json()
    access_token = tokens["access_token"]
    session["access_token"] = access_token

    user_resp = requests.get(
        f"{DISCORD_API}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if user_resp.status_code == 200:
        session["user"] = user_resp.json()

    return redirect(url_for("servers"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/servers")
@login_required
def servers():
    guilds = get_user_guilds()
    return render_template("servers.html", guilds=guilds, user=session.get("user"))


@app.route("/dashboard/<guild_id>")
@login_required
def dashboard(guild_id):
    import asyncio
    loop = asyncio.new_event_loop()

    async def get_settings():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT * FROM guilds WHERE guild_id = ?", (int(guild_id),)
            ) as cursor:
                guild_settings = await cursor.fetchone()
            async with db.execute(
                "SELECT * FROM automod_settings WHERE guild_id = ?", (int(guild_id),)
            ) as cursor:
                automod = await cursor.fetchone()
            async with db.execute(
                "SELECT guild_id, expires_at, trial_expires_at FROM premium_servers WHERE guild_id = ?",
                (int(guild_id),)
            ) as cursor:
                premium = await cursor.fetchone()
        return guild_settings, automod, premium

    guild_settings, automod, premium = loop.run_until_complete(get_settings())
    loop.close()

    # Get guild info from Discord
    token = session.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    guilds = get_user_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)

    if not guild:
        return redirect(url_for("servers"))

    is_premium = False
    if premium:
        now = datetime.utcnow().isoformat()
        if premium[1] and premium[1] > now:
            is_premium = True
        if premium[2] and premium[2] > now:
            is_premium = True

    return render_template(
        "dashboard.html",
        guild=guild,
        guild_id=guild_id,
        settings=guild_settings,
        automod=automod,
        is_premium=is_premium,
        user=session.get("user")
    )


@app.route("/dashboard/<guild_id>/save", methods=["POST"])
@login_required
def save_settings(guild_id):
    import asyncio
    data = request.json

    async def update():
        async with aiosqlite.connect(DB_PATH) as db:
            if "prefix" in data:
                await db.execute(
                    "UPDATE guilds SET prefix = ? WHERE guild_id = ?",
                    (data["prefix"], int(guild_id))
                )
            if "welcome_message" in data:
                await db.execute(
                    "UPDATE guilds SET welcome_message = ? WHERE guild_id = ?",
                    (data["welcome_message"], int(guild_id))
                )
            if "anti_spam" in data:
                await db.execute(
                    "UPDATE automod_settings SET anti_spam = ? WHERE guild_id = ?",
                    (1 if data["anti_spam"] else 0, int(guild_id))
                )
            if "anti_caps" in data:
                await db.execute(
                    "UPDATE automod_settings SET anti_caps = ? WHERE guild_id = ?",
                    (1 if data["anti_caps"] else 0, int(guild_id))
                )
            if "anti_links" in data:
                await db.execute(
                    "UPDATE automod_settings SET anti_links = ? WHERE guild_id = ?",
                    (1 if data["anti_links"] else 0, int(guild_id))
                )
            if "anti_mentions" in data:
                await db.execute(
                    "UPDATE automod_settings SET anti_mentions = ? WHERE guild_id = ?",
                    (1 if data["anti_mentions"] else 0, int(guild_id))
                )
            await db.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(update())
    loop.close()

    return jsonify({"status": "saved"})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "bot": "LuxeBot Dashboard"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
