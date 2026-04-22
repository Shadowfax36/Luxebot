import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET", "luxebot_dashboard_secret")

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
BOT_API_URL = os.getenv("BOT_API_URL", "")
API_SECRET = os.getenv("DASHBOARD_SECRET", "luxebot123")
DISCORD_API = "https://discord.com/api/v10"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def bot_api(method, path, data=None):
    if not BOT_API_URL:
        return None
    try:
        headers = {"X-API-Key": API_SECRET, "Content-Type": "application/json"}
        url = f"{BOT_API_URL}{path}"
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=5)
        else:
            resp = requests.post(url, headers=headers, json=data, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Bot API error: {e}")
    return None


def get_user_guilds():
    token = session.get("access_token")
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{DISCORD_API}/users/@me/guilds", headers=headers)
    if resp.status_code == 200:
        guilds = resp.json()
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
    guilds = get_user_guilds()
    guild = next((g for g in guilds if g["id"] == guild_id), None)
    if not guild:
        return redirect(url_for("servers"))

    settings = bot_api("GET", f"/api/guild/{guild_id}/settings") or {
        "prefix": "!",
        "welcome_message": "",
        "automod": {
            "anti_spam": False,
            "anti_caps": False,
            "anti_links": False,
            "anti_mentions": False,
        },
        "is_premium": False
    }

    return render_template(
        "dashboard.html",
        guild=guild,
        guild_id=guild_id,
        settings=settings,
        automod=settings.get("automod", {}),
        is_premium=settings.get("is_premium", False),
        user=session.get("user")
    )


@app.route("/dashboard/<guild_id>/save", methods=["POST"])
@login_required
def save_settings(guild_id):
    data = request.json or {}
    result = bot_api("POST", f"/api/guild/{guild_id}/settings", data)
    if result:
        return jsonify({"status": "saved"})
    return jsonify({"status": "error", "message": "Could not reach bot API"}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok", "bot": "LuxeBot Dashboard"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
