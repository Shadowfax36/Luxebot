import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import database as db
from config import BOT_COLOR

def parse_duration(duration: str) -> int:
    unit = duration[-1].lower()
    try:
        value = int(duration[:-1])
    except ValueError:
        return None
    if unit == 'm': return value * 60
    if unit == 'h': return value * 3600
    if unit == 'd': return value * 86400
    return None

def embed(title, description, color=BOT_COLOR):
    e = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    return e

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_log(self, guild, action, moderator, target, reason):
        g = await db.get_guild(guild.id)
        if g.get('log_channel'):
            channel = guild.get_channel(g['log_channel'])
            if channel:
                e = discord.Embed(title=f"Mod Action — {action}", color=BOT_COLOR, timestamp=datetime.utcnow())
                e.add_field(name="Moderator", value=moderator.mention, inline=True)
                e.add_field(name="Target", value=target.mention if hasattr(target, 'mention') else str(target), inline=True)
                e.add_field(name="Reason", value=reason, inline=False)
                await channel.send(embed=e)
        await db.log_mod_action(guild.id, action, moderator.id, target.id if hasattr(target, 'id') else 0, reason)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        try:
            await member.send(embed=embed("You were banned", f"You were banned from **{ctx.guild.name}**\nReason: {reason}", 0xe74c3c))
        except:
            pass
        await member.ban(reason=reason)
        await ctx.send(embed=embed("Banned", f"{member.mention} has been banned.\nReason: {reason}", 0xe74c3c))
        await self.send_log(ctx.guild, "BAN", ctx.author, member, reason)

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        try:
            await member.send(embed=embed("You were kicked", f"You were kicked from **{ctx.guild.name}**\nReason: {reason}", 0xe67e22))
        except:
            pass
        await member.kick(reason=reason)
        await ctx.send(embed=embed("Kicked", f"{member.mention} has been kicked.\nReason: {reason}", 0xe67e22))
        await self.send_log(ctx.guild, "KICK", ctx.author, member, reason)

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str = "10m", *, reason="No reason provided"):
        seconds = parse_duration(duration)
        if not seconds:
            return await ctx.send(embed=embed("Error", "Invalid duration. Use: 10m, 1h, 1d", 0xe74c3c))
        until = datetime.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=reason)
        await ctx.send(embed=embed("Muted", f"{member.mention} muted for {duration}.\nReason: {reason}", 0xe67e22))
        await self.send_log(ctx.guild, f"MUTE ({duration})", ctx.author, member, reason)

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(embed=embed("Unmuted", f"{member.mention} has been unmuted."))
        await self.send_log(ctx.guild, "UNMUTE", ctx.author, member, "Manual unmute")

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        warnings = await db.add_warning(ctx.guild.id, member.id)
        try:
            await member.send(embed=embed("Warning", f"You were warned in **{ctx.guild.name}**\nReason: {reason}\nTotal warnings: {warnings}", 0xe67e22))
        except:
            pass
        await ctx.send(embed=embed("Warning Issued", f"{member.mention} warned. Total warnings: **{warnings}**\nReason: {reason}", 0xe67e22))
        await self.send_log(ctx.guild, "WARN", ctx.author, member, reason)
        if warnings >= 5:
            await member.kick(reason="Auto-kick: 5 warnings reached")
            await ctx.send(embed=embed("Auto-Kicked", f"{member.mention} was auto-kicked for reaching 5 warnings.", 0xe74c3c))
        elif warnings >= 3:
            until = datetime.utcnow() + timedelta(hours=1)
            await member.timeout(until, reason="Auto-mute: 3 warnings reached")
            await ctx.send(embed=embed("Auto-Muted", f"{member.mention} was auto-muted for 1 hour (3 warnings reached).", 0xe67e22))

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def warnings(self, ctx, member: discord.Member):
        user = await db.get_user(ctx.guild.id, member.id)
        await ctx.send(embed=embed("Warnings", f"{member.mention} has **{user['warnings']}** warning(s)."))

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def clearwarnings(self, ctx, member: discord.Member):
        await db.clear_warnings(ctx.guild.id, member.id)
        await ctx.send(embed=embed("Warnings Cleared", f"All warnings for {member.mention} have been cleared."))

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        if amount > 100:
            return await ctx.send(embed=embed("Error", "Max 100 messages at a time.", 0xe74c3c))
        await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(embed=embed("Purged", f"Deleted **{amount}** messages."))
        await asyncio.sleep(3)
        await msg.delete()

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, prefix: str):
        await db.set_guild(ctx.guild.id, prefix=prefix)
        await ctx.send(embed=embed("Prefix Updated", f"Prefix changed to `{prefix}`"))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setlog(self, ctx, channel: discord.TextChannel):
        await db.set_guild(ctx.guild.id, log_channel=channel.id)
        await ctx.send(embed=embed("Log Channel Set", f"Mod logs will be sent to {channel.mention}"))

async def setup(bot):
    await bot.add_cog(Moderation(bot))
