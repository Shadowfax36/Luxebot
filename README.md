# LuxeBot — Premium Discord Bot

A full-featured Discord bot that replaces MEE6 at $3-5/month per server.

---

## STEP 1 — Get Your Bot Token

1. Go to https://discord.com/developers/applications
2. Click "New Application" — name it "LuxeBot"
3. Click "Bot" in the left sidebar
4. Click "Reset Token" and copy the token
5. Scroll down and enable ALL Privileged Gateway Intents:
   - Presence Intent ✓
   - Server Members Intent ✓
   - Message Content Intent ✓
6. Save changes

---

## STEP 2 — Set Up Your .env File

1. Copy .env.example and rename it to .env
2. Paste your token:
   DISCORD_TOKEN=paste_your_token_here
   DASHBOARD_SECRET=make_up_any_random_string

---

## STEP 3 — Install Python Dependencies

Make sure Python 3.11+ is installed. Then run:

   pip install -r requirements.txt

---

## STEP 4 — Run the Bot Locally

   python main.py

You should see:
   LuxeBot is online as LuxeBot#1234
   Serving 0 servers

---

## STEP 5 — Invite Bot to Your Server

1. Go to https://discord.com/developers/applications
2. Click your app → OAuth2 → URL Generator
3. Check "bot" under Scopes
4. Check "Administrator" under Bot Permissions
5. Copy the generated URL and open it in your browser
6. Select your server and click Authorize

---

## STEP 6 — Deploy to Railway (Free Hosting)

1. Go to https://railway.app and create a free account
2. Click "New Project" → "Deploy from GitHub repo"
   (Or use "Deploy from template" → upload your folder)
3. Add environment variables:
   - DISCORD_TOKEN = your token
   - DASHBOARD_SECRET = your secret
4. Railway auto-detects the Procfile and runs the bot 24/7
5. Free tier gives you $5/month of credit — enough for this bot

---

## STEP 7 — Set Up Whop.com for Payments

1. Go to https://whop.com and create a seller account
2. Create a product called "LuxeBot Premium" at $3-5/month
3. In the product settings, add a Discord bot webhook
4. When someone pays, Whop automatically adds them to your premium list
5. In database.py, the premium_servers table stores premium guild IDs
6. Add Whop's guild_id to premium_servers to unlock all features

---

## COMMANDS REFERENCE

### Moderation (requires Kick/Ban permissions)
- !ban @user [reason]
- !kick @user [reason]
- !mute @user [10m/1h/1d] [reason]
- !unmute @user
- !warn @user [reason]
- !warnings @user
- !clearwarnings @user
- !purge [number]
- !setprefix [prefix]
- !setlog #channel

### AutoMod (requires Manage Server)
- !automod spam on/off
- !automod links on/off
- !automod caps on/off
- !automod badwords on/off
- !automod mentions on/off
- !addbadword [word]
- !removebadword [word]

### Leveling
- !rank [@user]
- !leaderboard
- !setlevelrole [level] @role
- !setlevelchannel #channel

### Welcome (requires Manage Server)
- !setwelcome #channel [message]
  Variables: {user} {server} {membercount}
- !setgoodbye #channel [message]
- !setjoinrole @role
- !testwelcome

### Reaction Roles (requires Manage Roles)
- !reactionrole [message_id] [emoji] @role
- !removereactionrole [message_id] [emoji]
- !listreactionroles

### Custom Commands (requires Manage Server)
- !addcommand [trigger] [response]
- !removecommand [trigger]
- !listcommands

### Utility
- !ping
- !serverinfo
- !userinfo [@user]
- !premium
- !help

---

## MONETIZATION

Free tier: Moderation + Welcome only
Premium ($3-5/month): All features

To manually add a premium server, run this SQL:
INSERT INTO premium_servers (guild_id) VALUES (YOUR_GUILD_ID_HERE);

---

## SELLING YOUR BOT

1. List on top.gg — massive discovery platform for Discord bots
2. Post in Discord server listing subreddits
3. Reach out to gaming servers with 1000+ members directly
4. Price: $3/month (undercut MEE6's $12/month — easy sell)
