import discord
from discord.ext import commands
from datetime import datetime
import random
import database as db
from config import BOT_COLOR

XP_COOLDOWN = 60

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        key = (message.guild.id, message.author.id)
        now = datetime.utcnow().timestamp()
        if key in self.cooldowns and now - self.cooldowns[key] < XP_COOLDOWN:
            return
        self.cooldowns[key] = now
        xp_gain = random.randint(15, 25)
        new_level, leveled_up = await db.add_xp(message.guild.id, message.author.id, xp_gain)
        if leveled_up:
            g = await db.get_guild(message.guild.id)
            channel = message.guild.get_channel(g.get('level_channel')) or message.channel
            e = discord.Embed(
                title="Level Up!",
                description=f"{message.author.mention} reached **Level {new_level}**!",
                color=BOT_COLOR,
                timestamp=datetime.utcnow()
            )
            await channel.send(embed=e)
            role_id = await db.get_level_role(message.guild.id, new_level)
            if role_id:
                role = message.guild.get_role(role_id)
                if role:
                    try:
                        await message.author.add_roles(role, reason=f"Level {new_level} reward")
                    except:
                        pass

    @commands.command()
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user = await db.get_user(ctx.guild.id, member.id)
        import math
        next_level_xp = int(((user['level'] + 1) / 0.1) ** 2)
        e = discord.Embed(title=f"{member.display_name}'s Rank", color=BOT_COLOR, timestamp=datetime.utcnow())
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Level", value=str(user['level']), inline=True)
        e.add_field(name="XP", value=f"{user['xp']:,}", inline=True)
        e.add_field(name="XP to next level", value=f"{next_level_xp - user['xp']:,}", inline=True)
        await ctx.send(embed=e)

    @commands.command()
    async def leaderboard(self, ctx):
        top = await db.get_leaderboard(ctx.guild.id)
        e = discord.Embed(title=f"{ctx.guild.name} Leaderboard", color=BOT_COLOR, timestamp=datetime.utcnow())
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(top):
            member = ctx.guild.get_member(row['user_id'])
            name = member.display_name if member else f"Unknown ({row['user_id']})"
            prefix = medals[i] if i < 3 else f"`{i+1}.`"
            desc += f"{prefix} **{name}** — Level {row['level']} ({row['xp']:,} XP)\n"
        e.description = desc or "No data yet."
        await ctx.send(embed=e)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setlevelrole(self, ctx, level: int, role: discord.Role):
        await db.set_level_role(ctx.guild.id, level, role.id)
        e = discord.Embed(description=f"{role.mention} will be given at level **{level}**.", color=BOT_COLOR)
        await ctx.send(embed=e)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setlevelchannel(self, ctx, channel: discord.TextChannel):
        await db.set_guild(ctx.guild.id, level_channel=channel.id)
        e = discord.Embed(description=f"Level-up messages will go to {channel.mention}.", color=BOT_COLOR)
        await ctx.send(embed=e)

async def setup(bot):
    await bot.add_cog(Leveling(bot))
