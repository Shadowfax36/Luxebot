import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import aiosqlite

DB_PATH = "luxebot.db"

class PremiumManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_premium.start()

    def cog_unload(self):
        self.check_expired_premium.cancel()

    @tasks.loop(hours=24)
    async def check_expired_premium(self):
        print(f"[{datetime.utcnow()}] Running premium expiry check...")
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, trial_expires_at FROM premium_servers WHERE trial_expires_at IS NOT NULL"
            ) as cursor:
                rows = await cursor.fetchall()

        now = datetime.utcnow()
        for row in rows:
            guild_id, expires_at = row
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at)
                    if now > expiry:
                        await self.remove_expired(guild_id)
                except Exception as e:
                    print(f"Error checking expiry for {guild_id}: {e}")

    async def remove_expired(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM premium_servers WHERE guild_id = ?",
                (guild_id,)
            )
            await db.commit()
        print(f"[{datetime.utcnow()}] Removed expired premium for guild {guild_id}")
        guild = self.bot.get_guild(guild_id)
        if guild:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    e = discord.Embed(
                        title="Your LuxeBot trial has ended",
                        description="Your 7-day free trial has expired.\n\nTo keep all premium features, upgrade for just **$5/month**:\nwhop.com/luxebot/luxebot-premium\n\nWithout premium, moderation commands still work but leveling, automod, reaction roles, custom commands and logging are paused.",
                        color=0xe74c3c
                    )
                    try:
                        await channel.send(embed=e)
                    except:
                        pass
                    break

    @check_expired_premium.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(PremiumManager(bot))
