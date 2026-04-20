import discord
from discord.ext import commands
from datetime import datetime, timedelta
import database as db

BOT_COLOR = 0xC9A84C


def xp_for_level(level):
    return 5 * (level ** 2) + 50 * level + 100


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        last_xp = await db.get_xp_cooldown(message.guild.id, message.author.id)
        if last_xp:
            last = datetime.fromisoformat(last_xp)
            if (datetime.utcnow() - last).seconds < 60:
                return

        import random
        xp_gain = random.randint(15, 25)
        await db.add_xp(message.guild.id, message.author.id, xp_gain)
        await db.set_xp_cooldown(message.guild.id, message.author.id)

        current_xp, current_level = await db.get_xp(message.guild.id, message.author.id)
        xp_needed = xp_for_level(current_level)

        if current_xp >= xp_needed:
            new_level = current_level + 1
            await db.set_level(message.guild.id, message.author.id, new_level)

            import aiosqlite
            async with aiosqlite.connect("luxebot.db") as conn:
                async with conn.execute(
                    "SELECT log_channel FROM guilds WHERE guild_id = ?",
                    (message.guild.id,)
                ) as cursor:
                    row = await cursor.fetchone()

            channel = message.channel
            embed = discord.Embed(
                title="Level Up!",
                description=f"{message.author.mention} reached **Level {new_level}**!",
                color=BOT_COLOR
            )
            await channel.send(embed=embed)

            level_roles = await db.get_level_roles(message.guild.id)
            for lvl, role_id in level_roles:
                if new_level >= lvl:
                    role = message.guild.get_role(role_id)
                    if role and role not in message.author.roles:
                        await message.author.add_roles(role)

    @commands.command(name="rank")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        xp, level = await db.get_xp(ctx.guild.id, member.id)
        xp_needed = xp_for_level(level)
        embed = discord.Embed(title=f"{member.display_name}'s Rank", color=BOT_COLOR)
        embed.add_field(name="Level", value=str(level))
        embed.add_field(name="XP", value=f"{xp}/{xp_needed}")
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="leaderboard")
    async def leaderboard(self, ctx):
        top = await db.get_leaderboard(ctx.guild.id, 10)
        if not top:
            await ctx.send("No one has earned XP yet!")
            return
        lines = []
        for i, (user_id, xp, level) in enumerate(top):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            lines.append(f"**{i+1}.** {name} — Level {level} ({xp} XP)")
        embed = discord.Embed(title=f"{ctx.guild.name} Leaderboard", description="\n".join(lines), color=BOT_COLOR)
        await ctx.send(embed=embed)

    @commands.command(name="setlevelrole")
    @commands.has_permissions(manage_guild=True)
    async def setlevelrole(self, ctx, level: int, role: discord.Role):
        await db.add_level_role(ctx.guild.id, level, role.id)
        await ctx.send(f"Members will receive {role.mention} when they reach level {level}.")

    @commands.command(name="setlevelchannel")
    @commands.has_permissions(manage_guild=True)
    async def setlevelchannel(self, ctx, channel: discord.TextChannel):
        await ctx.send(f"Level up messages will be sent in {channel.mention}.")


async def setup(bot):
    await bot.add_cog(Leveling(bot))
