import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timedelta
import database as db

BOT_COLOR = 0xC9A84C
DB_PATH = "luxebot.db"


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(title="Member Banned", description=f"{member.mention} has been banned.\nReason: {reason}", color=0xE74C3C)
        await ctx.send(embed=embed)
        await db.add_warning(ctx.guild.id, member.id, f"BANNED: {reason}", ctx.author.id)

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.kick(reason=reason)
        embed = discord.Embed(title="Member Kicked", description=f"{member.mention} has been kicked.\nReason: {reason}", color=0xE67E22)
        await ctx.send(embed=embed)

    @commands.command(name="mute")
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, duration: str = "10m", *, reason="No reason provided"):
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        try:
            seconds = int(duration[:-1]) * units[duration[-1].lower()]
        except Exception:
            seconds = 600

        until = datetime.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=reason)
        embed = discord.Embed(title="Member Muted", description=f"{member.mention} muted for {duration}.\nReason: {reason}", color=0x95A5A6)
        await ctx.send(embed=embed)

    @commands.command(name="unmute")
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        embed = discord.Embed(title="Member Unmuted", description=f"{member.mention} has been unmuted.", color=0x2ECC71)
        await ctx.send(embed=embed)

    @commands.command(name="warn")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await db.add_warning(ctx.guild.id, member.id, reason, ctx.author.id)
        warnings = await db.get_warnings(ctx.guild.id, member.id)
        count = len(warnings)
        embed = discord.Embed(title="Member Warned", description=f"{member.mention} warned. Total warnings: {count}\nReason: {reason}", color=0xF39C12)
        await ctx.send(embed=embed)

        if count >= 5:
            await member.kick(reason="Auto-kick: 5 warnings")
            await ctx.send(f"{member.mention} was auto-kicked for reaching 5 warnings.")
        elif count >= 3:
            until = datetime.utcnow() + timedelta(minutes=30)
            await member.timeout(until, reason="Auto-mute: 3 warnings")
            await ctx.send(f"{member.mention} was auto-muted for 30 minutes for reaching 3 warnings.")

    @commands.command(name="warnings")
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member):
        warns = await db.get_warnings(ctx.guild.id, member.id)
        if not warns:
            await ctx.send(f"{member.mention} has no warnings.")
            return
        lines = [f"{i+1}. {w[3]} — by <@{w[4]}>" for i, w in enumerate(warns)]
        embed = discord.Embed(title=f"Warnings for {member.display_name}", description="\n".join(lines), color=BOT_COLOR)
        await ctx.send(embed=embed)

    @commands.command(name="clearwarnings")
    @commands.has_permissions(manage_messages=True)
    async def clearwarnings(self, ctx, member: discord.Member):
        await db.clear_warnings(ctx.guild.id, member.id)
        await ctx.send(f"Cleared all warnings for {member.mention}.")

    @commands.command(name="purge")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"Deleted {amount} messages.")
        await msg.delete(delay=3)

    @commands.command(name="setprefix")
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, prefix: str):
        await db.update_guild_setting(ctx.guild.id, "prefix", prefix)
        await ctx.send(f"Prefix changed to `{prefix}`")

    @commands.command(name="setlog")
    @commands.has_permissions(manage_guild=True)
    async def setlog(self, ctx, channel: discord.TextChannel):
        await db.update_guild_setting(ctx.guild.id, "log_channel", channel.id)
        await ctx.send(f"Log channel set to {channel.mention}")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
