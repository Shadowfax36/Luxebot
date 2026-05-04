"""
leveling.py — Enhanced XP/leveling system

Why it beats MEE6:
  - XP multipliers (weekends, boosters, custom per-channel)
  - Voice XP: earn XP just by being in voice channels
  - Weekly/monthly XP resets with separate leaderboards
  - Role stacking: keep ALL earned roles, not just the latest
  - Level milestones with custom reward messages
  - Daily XP streaks: bonus for chatting every day
  - No paywalls — all features free
"""

import discord
from discord.ext import commands, tasks
import aiosqlite
import random
from datetime import datetime, timedelta
import database as db

BOT_COLOR = 0xC9A84C
DB_PATH = "luxebot.db"

# ── XP tuning ─────────────────────────────────────────────────────────────────
XP_MIN         = 15
XP_MAX         = 25
XP_COOLDOWN    = 60      # seconds between XP grants
VOICE_XP_RATE  = 10      # XP per minute in voice (granted every 5 min)
STREAK_BONUS   = 1.25    # 25% bonus XP for daily streak
BOOSTER_BONUS  = 1.50    # 50% bonus for server boosters
WEEKEND_BONUS  = 1.20    # 20% bonus on weekends


def xp_for_level(level: int) -> int:
    """XP needed to reach `level` from `level-1`. Smooth curve."""
    return 5 * (level ** 2) + 50 * level + 100


def total_xp_for_level(level: int) -> int:
    """Cumulative XP needed to reach `level` from 0."""
    return sum(xp_for_level(l) for l in range(1, level + 1))


def level_from_xp(xp: int) -> int:
    """Calculate level from raw XP total."""
    level = 0
    while xp >= xp_for_level(level + 1):
        xp -= xp_for_level(level + 1)
        level += 1
    return level


async def init_leveling_db():
    async with aiosqlite.connect(DB_PATH) as db_conn:
        # Streak tracking
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS xp_streaks (
                guild_id INTEGER,
                user_id INTEGER,
                streak_days INTEGER DEFAULT 1,
                last_date TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        # Voice XP tracking
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_sessions (
                guild_id INTEGER,
                user_id INTEGER,
                joined_at TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        # Weekly XP (resets every Monday)
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_xp (
                guild_id INTEGER,
                user_id INTEGER,
                xp INTEGER DEFAULT 0,
                week_start TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        # XP multipliers per channel
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS xp_multipliers (
                guild_id INTEGER,
                channel_id INTEGER,
                multiplier REAL DEFAULT 1.0,
                PRIMARY KEY (guild_id, channel_id)
            )
        """)
        # Level milestone messages
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS level_milestones (
                guild_id INTEGER,
                level INTEGER,
                message TEXT,
                PRIMARY KEY (guild_id, level)
            )
        """)
        # Vote bonus tracking (top.gg) — global per user, not per guild
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS vote_bonuses (
                user_id INTEGER PRIMARY KEY,
                expires_at TEXT
            )
        """)
        await db_conn.commit()


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(init_leveling_db())
        self.voice_xp_task.start()

    def cog_unload(self):
        self.voice_xp_task.cancel()

    # ── XP multiplier helpers ─────────────────────────────────────────────────

    async def get_xp_multiplier(self, member: discord.Member, channel_id: int) -> float:
        mult = 1.0

        # Weekend bonus
        if datetime.utcnow().weekday() >= 5:
            mult *= WEEKEND_BONUS

        # Booster bonus
        if member.premium_since:
            mult *= BOOSTER_BONUS

        # Per-channel multiplier
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT multiplier FROM xp_multipliers WHERE guild_id = ? AND channel_id = ?",
                (member.guild.id, channel_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    mult *= row[0]

        # Vote bonus (top.gg) — 2x XP for 12h after voting
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT expires_at FROM vote_bonuses WHERE user_id = ?",
                (member.id,)
            ) as cursor:
                vrow = await cursor.fetchone()
            if vrow and vrow[0] > datetime.utcnow().isoformat():
                mult *= 2.0

        return mult

    async def get_streak_multiplier(self, guild_id: int, user_id: int) -> float:
        today = datetime.utcnow().date().isoformat()
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT streak_days, last_date FROM xp_streaks WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                await db_conn.execute(
                    "INSERT INTO xp_streaks (guild_id, user_id, streak_days, last_date) VALUES (?, ?, 1, ?)",
                    (guild_id, user_id, today)
                )
                await db_conn.commit()
                return 1.0

            streak_days, last_date = row
            yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()

            if last_date == today:
                # Already tracked today
                return STREAK_BONUS if streak_days >= 3 else 1.0
            elif last_date == yesterday:
                # Streak continues
                new_streak = streak_days + 1
                await db_conn.execute(
                    "UPDATE xp_streaks SET streak_days = ?, last_date = ? WHERE guild_id = ? AND user_id = ?",
                    (new_streak, today, guild_id, user_id)
                )
                await db_conn.commit()
                return STREAK_BONUS if new_streak >= 3 else 1.0
            else:
                # Streak broken
                await db_conn.execute(
                    "UPDATE xp_streaks SET streak_days = 1, last_date = ? WHERE guild_id = ? AND user_id = ?",
                    (today, guild_id, user_id)
                )
                await db_conn.commit()
                return 1.0

    async def update_weekly_xp(self, guild_id: int, user_id: int, amount: int):
        week_start = (datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())).date().isoformat()
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT xp, week_start FROM weekly_xp WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
            if not row or row[1] != week_start:
                await db_conn.execute(
                    "INSERT OR REPLACE INTO weekly_xp (guild_id, user_id, xp, week_start) VALUES (?, ?, ?, ?)",
                    (guild_id, user_id, amount, week_start)
                )
            else:
                await db_conn.execute(
                    "UPDATE weekly_xp SET xp = xp + ? WHERE guild_id = ? AND user_id = ?",
                    (amount, guild_id, user_id)
                )
            await db_conn.commit()

    # ── Level up handler ──────────────────────────────────────────────────────

    async def handle_level_up(self, message: discord.Message, new_level: int):
        guild = message.guild
        member = message.author

        # Get level-up channel (falls back to message channel)
        settings = await db.get_guild_settings(guild.id)
        level_channel = None
        if settings and settings[2]:  # log_channel used for level announcements
            level_channel = guild.get_channel(settings[2])
        channel = level_channel or message.channel

        # Check for milestone message
        milestone_msg = None
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT message FROM level_milestones WHERE guild_id = ? AND level = ?",
                (guild.id, new_level)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    milestone_msg = row[0].replace("{user}", member.mention).replace("{level}", str(new_level))

        # Send level-up embed
        embed = discord.Embed(
            description=milestone_msg or f"🎉 {member.mention} reached **Level {new_level}**!",
            color=BOT_COLOR
        )

        # Show what's unlocked at this level
        level_roles = await db.get_level_roles(guild.id)
        unlocked = [guild.get_role(r) for lvl, r in level_roles if lvl == new_level]
        unlocked = [r for r in unlocked if r]
        if unlocked:
            embed.add_field(
                name="🎁 Role Unlocked",
                value=" ".join(r.mention for r in unlocked),
                inline=False
            )

        await channel.send(embed=embed)

        # Assign ALL earned roles (stacking — not just latest like MEE6 free tier)
        earned_roles = [
            guild.get_role(role_id)
            for lvl, role_id in level_roles
            if new_level >= lvl
        ]
        earned_roles = [r for r in earned_roles if r and r not in member.roles]
        if earned_roles:
            try:
                await member.add_roles(*earned_roles, reason=f"Level {new_level} role reward")
            except discord.Forbidden:
                pass

    # ── Message XP listener ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id  = message.guild.id
        user_id   = message.author.id
        channel_id = message.channel.id

        # Cooldown check
        last_xp = await db.get_xp_cooldown(guild_id, user_id)
        if last_xp:
            last = datetime.fromisoformat(last_xp)
            if (datetime.utcnow() - last).total_seconds() < XP_COOLDOWN:
                return

        # Calculate XP with multipliers
        base_xp = random.randint(XP_MIN, XP_MAX)
        channel_mult = await self.get_xp_multiplier(message.author, channel_id)
        streak_mult  = await self.get_streak_multiplier(guild_id, user_id)
        xp_gain = int(base_xp * channel_mult * streak_mult)

        # Add XP
        await db.add_xp(guild_id, user_id, xp_gain)
        await db.set_xp_cooldown(guild_id, user_id)
        await self.update_weekly_xp(guild_id, user_id, xp_gain)

        # Check level up
        current_xp, current_level = await db.get_xp(guild_id, user_id)
        xp_needed = xp_for_level(current_level + 1)
        if current_xp >= xp_needed:
            new_level = current_level + 1
            await db.set_level(guild_id, user_id, new_level)
            await self.handle_level_up(message, new_level)

    # ── Voice XP ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        if member.bot:
            return
        guild_id = member.guild.id
        user_id  = member.id
        now_iso  = datetime.utcnow().isoformat()

        async with aiosqlite.connect(DB_PATH) as db_conn:
            if after.channel and not before.channel:
                # Joined voice
                await db_conn.execute(
                    "INSERT OR REPLACE INTO voice_sessions (guild_id, user_id, joined_at) VALUES (?, ?, ?)",
                    (guild_id, user_id, now_iso)
                )
            elif not after.channel and before.channel:
                # Left voice — grant accumulated XP
                async with db_conn.execute(
                    "SELECT joined_at FROM voice_sessions WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id)
                ) as cursor:
                    row = await cursor.fetchone()
                if row:
                    joined = datetime.fromisoformat(row[0])
                    minutes = int((datetime.utcnow() - joined).total_seconds() / 60)
                    if minutes > 0:
                        xp = min(minutes * VOICE_XP_RATE, 500)  # Cap at 500 XP per session
                        await db.add_xp(guild_id, user_id, xp)
                        await self.update_weekly_xp(guild_id, user_id, xp)
                        # Check level up from voice
                        current_xp, current_level = await db.get_xp(guild_id, user_id)
                        if current_xp >= xp_for_level(current_level + 1):
                            new_level = current_level + 1
                            await db.set_level(guild_id, user_id, new_level)
                            channel = before.channel.guild.system_channel
                            if channel:
                                await channel.send(
                                    embed=discord.Embed(
                                        description=f"🎤 {member.mention} reached **Level {new_level}** from voice activity!",
                                        color=BOT_COLOR
                                    )
                                )
                    await db_conn.execute(
                        "DELETE FROM voice_sessions WHERE guild_id = ? AND user_id = ?",
                        (guild_id, user_id)
                    )
            await db_conn.commit()

    @tasks.loop(minutes=5)
    async def voice_xp_task(self):
        """Grant periodic XP to users currently in voice."""
        now = datetime.utcnow()
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute("SELECT guild_id, user_id, joined_at FROM voice_sessions") as cursor:
                rows = await cursor.fetchall()

        for guild_id, user_id, joined_at_str in rows:
            try:
                joined = datetime.fromisoformat(joined_at_str)
                minutes = int((now - joined).total_seconds() / 60)
                if minutes >= 5:
                    xp = VOICE_XP_RATE * 5  # 5 min worth
                    await db.add_xp(guild_id, user_id, xp)
                    # Update session start to now (rolling window)
                    async with aiosqlite.connect(DB_PATH) as db_conn2:
                        await db_conn2.execute(
                            "UPDATE voice_sessions SET joined_at = ? WHERE guild_id = ? AND user_id = ?",
                            (now.isoformat(), guild_id, user_id)
                        )
                        await db_conn2.commit()
            except Exception as e:
                print(f"Voice XP task error: {e}")

    @voice_xp_task.before_loop
    async def before_voice_xp(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Leveling(bot))
