import discord
from discord.ext import commands
import aiosqlite
from collections import defaultdict
from datetime import datetime, timedelta
import database as db

DB_PATH = "luxebot.db"
BOT_COLOR = 0xC9A84C

spam_tracker = defaultdict(list)
raid_tracker = []


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="automod")
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx, filter_type: str, toggle: str):
        settings_map = {
            "spam": "anti_spam", "links": "anti_links",
            "caps": "anti_caps", "badwords": "anti_spam",
            "mentions": "anti_mentions"
        }
        setting = settings_map.get(filter_type.lower())
        if not setting:
            await ctx.send("Valid types: spam, links, caps, badwords, mentions")
            return
        value = 1 if toggle.lower() == "on" else 0
        await db.update_automod_setting(ctx.guild.id, setting, value)
        await ctx.send(f"AutoMod `{filter_type}` turned {'on' if value else 'off'}.")

    @commands.command(name="addbadword")
    @commands.has_permissions(manage_guild=True)
    async def addbadword(self, ctx, *, word: str):
        await db.add_badword(ctx.guild.id, word.lower())
        await ctx.send(f"Added `{word}` to the bad word list.")

    @commands.command(name="removebadword")
    @commands.has_permissions(manage_guild=True)
    async def removebadword(self, ctx, *, word: str):
        await db.remove_badword(ctx.guild.id, word.lower())
        await ctx.send(f"Removed `{word}` from the bad word list.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        settings = await db.get_automod_settings(message.guild.id)
        if not settings:
            return

        _, anti_spam, anti_caps, anti_links, anti_mentions, anti_raid, spam_threshold, caps_threshold, mention_threshold = settings

        # Bad words
        badwords = await db.get_badwords(message.guild.id)
        if badwords:
            content_lower = message.content.lower()
            for word in badwords:
                if word in content_lower:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Bad word detected.", delete_after=3)
                    return

        # Caps filter
        if anti_caps and len(message.content) > 10:
            caps = sum(1 for c in message.content if c.isupper())
            if caps / len(message.content) * 100 > caps_threshold:
                await message.delete()
                await message.channel.send(f"{message.author.mention} Too many caps!", delete_after=3)
                return

        # Link filter
        if anti_links:
            if "http://" in message.content or "https://" in message.content or "discord.gg/" in message.content:
                if not message.author.guild_permissions.manage_messages:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Links are not allowed.", delete_after=3)
                    return

        # Mention spam
        if anti_mentions and len(message.mentions) >= mention_threshold:
            await message.delete()
            until = datetime.utcnow() + timedelta(minutes=5)
            await message.author.timeout(until, reason="Mention spam")
            await message.channel.send(f"{message.author.mention} Mention spam detected. Muted for 5 minutes.", delete_after=5)
            return

        # Spam detection
        if anti_spam:
            uid = message.author.id
            now = datetime.utcnow()
            spam_tracker[uid] = [t for t in spam_tracker[uid] if (now - t).seconds < 5]
            spam_tracker[uid].append(now)
            if len(spam_tracker[uid]) >= spam_threshold:
                until = datetime.utcnow() + timedelta(minutes=5)
                await message.author.timeout(until, reason="Spam detected")
                await message.channel.send(f"{message.author.mention} Spam detected. Muted for 5 minutes.", delete_after=5)
                spam_tracker[uid] = []


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
