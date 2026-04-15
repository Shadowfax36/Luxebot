import discord
from discord.ext import commands
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
import database as db
from config import BOT_COLOR

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_tracker = defaultdict(list)
        self.raid_tracker = defaultdict(list)

    def embed(self, title, desc, color=0xe74c3c):
        return discord.Embed(title=title, description=desc, color=color, timestamp=datetime.utcnow())

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        g = await db.get_guild(message.guild.id)

        # Spam detection
        if g.get('automod_spam'):
            uid = (message.guild.id, message.author.id)
            now = datetime.utcnow()
            self.spam_tracker[uid] = [t for t in self.spam_tracker[uid] if (now - t).seconds < 5]
            self.spam_tracker[uid].append(now)
            if len(self.spam_tracker[uid]) > 5:
                try:
                    until = datetime.utcnow() + timedelta(minutes=10)
                    await message.author.timeout(until, reason="AutoMod: Spam detected")
                    await message.channel.send(embed=self.embed("AutoMod — Spam", f"{message.author.mention} muted 10 minutes for spamming."), delete_after=5)
                except:
                    pass
                self.spam_tracker[uid] = []
                return

        # Mention spam
        if g.get('automod_mentions') and len(message.mentions) > 5:
            await message.delete()
            await message.channel.send(embed=self.embed("AutoMod — Mention Spam", f"{message.author.mention} too many mentions in one message."), delete_after=5)
            return

        # Caps filter
        if g.get('automod_caps') and len(message.content) > 10:
            caps = sum(1 for c in message.content if c.isupper())
            if caps / len(message.content) > 0.7:
                await message.delete()
                await message.channel.send(embed=self.embed("AutoMod — Caps", f"{message.author.mention} please don't use excessive caps."), delete_after=5)
                return

        # Bad word filter
        if g.get('automod_badwords'):
            badwords = await db.get_badwords(message.guild.id)
            content_lower = message.content.lower()
            if any(word in content_lower for word in badwords):
                await message.delete()
                await message.channel.send(embed=self.embed("AutoMod — Language", f"{message.author.mention} that word isn't allowed here."), delete_after=5)
                return

        # Link filter
        if g.get('automod_links'):
            if "http://" in message.content or "https://" in message.content:
                if not message.author.guild_permissions.manage_messages:
                    await message.delete()
                    await message.channel.send(embed=self.embed("AutoMod — Links", f"{message.author.mention} links are not allowed."), delete_after=5)
                    return

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild_id = member.guild.id
        now = datetime.utcnow()
        self.raid_tracker[guild_id] = [t for t in self.raid_tracker[guild_id] if (now - t).seconds < 60]
        self.raid_tracker[guild_id].append(now)
        if len(self.raid_tracker[guild_id]) > 10:
            for channel in member.guild.text_channels:
                try:
                    await channel.edit(slowmode_delay=30)
                except:
                    pass
            g = await db.get_guild(guild_id)
            if g.get('log_channel'):
                log_ch = member.guild.get_channel(g['log_channel'])
                if log_ch:
                    await log_ch.send(embed=discord.Embed(
                        title="RAID ALERT",
                        description="10+ members joined in 60 seconds. Slowmode enabled on all channels.",
                        color=0xe74c3c
                    ))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx, setting: str, toggle: str):
        valid = {'spam': 'automod_spam', 'links': 'automod_links', 'caps': 'automod_caps',
                 'badwords': 'automod_badwords', 'mentions': 'automod_mentions'}
        if setting.lower() not in valid:
            return await ctx.send(embed=discord.Embed(description="Valid settings: spam, links, caps, badwords, mentions", color=0xe74c3c))
        val = 1 if toggle.lower() in ('on', 'enable', 'true') else 0
        await db.set_guild(ctx.guild.id, **{valid[setting.lower()]: val})
        status = "enabled" if val else "disabled"
        await ctx.send(embed=discord.Embed(description=f"AutoMod `{setting}` is now **{status}**.", color=BOT_COLOR))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def addbadword(self, ctx, *, word: str):
        await db.add_badword(ctx.guild.id, word)
        await ctx.send(embed=discord.Embed(description=f"Added `{word}` to bad words list.", color=BOT_COLOR))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def removebadword(self, ctx, *, word: str):
        await db.remove_badword(ctx.guild.id, word)
        await ctx.send(embed=discord.Embed(description=f"Removed `{word}` from bad words list.", color=BOT_COLOR))

async def setup(bot):
    await bot.add_cog(AutoMod(bot))
