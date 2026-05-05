import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import aiosqlite
import database as db

BOT_COLOR = 0xC9A84C
DB_PATH = "luxebot.db"


class PremiumManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_trials.start()

    def cog_unload(self):
        self.check_expired_trials.cancel()

    @tasks.loop(hours=1)
    async def check_expired_trials(self):
        """
        Runs every hour. Finds guilds whose trial or paid subscription just expired
        and sends a notification. Does NOT delete rows — is_premium() handles expiry
        naturally by comparing timestamps.
        """
        now = datetime.utcnow().isoformat()

        # Find trials that expired in the last 2 hours (to avoid missing them if bot restarts)
        two_hours_ago = (datetime.utcnow() - timedelta(hours=2)).isoformat()

        async with aiosqlite.connect(DB_PATH) as db_conn:
            # Trial expired (no paid subscription covering it)
            async with db_conn.execute(
                """SELECT guild_id, trial_expires_at FROM premium_servers
                   WHERE trial_expires_at IS NOT NULL
                   AND trial_expires_at <= ?
                   AND trial_expires_at >= ?
                   AND (expires_at IS NULL OR expires_at <= ?)
                   AND notified_trial_expire IS NULL""",
                (now, two_hours_ago, now)
            ) as cursor:
                expired_trials = await cursor.fetchall()

            for row in expired_trials:
                guild_id, trial_expires_at = row
                await self._notify_expiry(guild_id, "trial")
                # Mark as notified so we don't spam
                await db_conn.execute(
                    "UPDATE premium_servers SET notified_trial_expire = ? WHERE guild_id = ?",
                    (now, guild_id)
                )

            await db_conn.commit()

    async def _notify_expiry(self, guild_id: int, expiry_type: str):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        if expiry_type == "trial":
            embed = discord.Embed(
                title="⏰ Your Free Trial Has Ended",
                description=(
                    "Your **7-day free trial** of LuxeBot Premium has expired.\n\n"
                    "**To keep all features active:**\n"
                    "👑 [Subscribe for $5/month](https://whop.com/luxebot/luxebot-premium)\n\n"
                    "Until then, slash commands and configuration will be limited.\n"
                    "Use `/trial` to check your status."
                ),
                color=0xFF6B6B
            )
            embed.set_footer(text="LuxeBot Premium • whop.com/luxebot/luxebot-premium")

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass
                break

    @check_expired_trials.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Ensure notified_trial_expire column exists ────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        """Add the notified_trial_expire column if it doesn't exist yet."""
        try:
            async with aiosqlite.connect(DB_PATH) as db_conn:
                await db_conn.execute(
                    "ALTER TABLE premium_servers ADD COLUMN notified_trial_expire TEXT"
                )
                await db_conn.commit()
        except Exception:
            pass  # Column already exists


async def setup(bot):
    await bot.add_cog(PremiumManager(bot))
