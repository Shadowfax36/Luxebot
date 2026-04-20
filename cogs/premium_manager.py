import discord
from discord.ext import commands, tasks
from datetime import datetime
import database as db


class PremiumManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_trials.start()

    def cog_unload(self):
        self.check_expired_trials.cancel()

    @tasks.loop(hours=24)
    async def check_expired_trials(self):
        print(f"[{datetime.utcnow()}] Running premium expiry check...")
        expired = await db.get_expired_trials()
        for row in expired:
            guild_id = row[0]
            await db.remove_premium(guild_id)
            guild = self.bot.get_guild(guild_id)
            if guild:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        embed = discord.Embed(
                            title="LuxeBot Trial Expired",
                            description=(
                                "Your 7-day free trial has ended.\n\n"
                                "To keep all premium features, subscribe for just **$5/month**:\n"
                                "https://whop.com/luxebot/luxebot-premium\n\n"
                                "Basic commands will still work. Thank you for trying LuxeBot!"
                            ),
                            color=0xFF6B6B
                        )
                        await channel.send(embed=embed)
                        break

    @check_expired_trials.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.command(name="premium")
    async def premium_status(self, ctx):
        is_prem = await db.is_premium(ctx.guild.id)
        if is_prem:
            embed = discord.Embed(
                title="LuxeBot Premium",
                description="This server has **premium access** active!",
                color=0xC9A84C
            )
        else:
            embed = discord.Embed(
                title="LuxeBot Premium",
                description=(
                    "This server does not have premium access.\n\n"
                    "Get premium for **$5/month**:\n"
                    "https://whop.com/luxebot/luxebot-premium"
                ),
                color=0xFF6B6B
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PremiumManager(bot))
