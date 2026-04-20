import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime

DB_PATH = "luxebot.db"
BOT_COLOR = 0xC9A84C


class Features(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Help ─────────────────────────────────────────────────

    @commands.command(name="help")
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="👑 LuxeBot Commands",
            description="Premium Discord management for $5/month.\nAll features included — no upsells.",
            color=BOT_COLOR
        )

        embed.add_field(name="🛡️ Moderation", value=(
            "`!ban` `!kick` `!mute` `!unmute`\n"
            "`!warn` `!warnings` `!clearwarnings`\n"
            "`!purge` `!setprefix` `!setlog`"
        ), inline=False)

        embed.add_field(name="🤖 AutoMod", value=(
            "`!automod spam/links/caps/badwords/mentions on/off`\n"
            "`!addbadword` `!removebadword`"
        ), inline=False)

        embed.add_field(name="⭐ Leveling", value=(
            "`!rank` `!leaderboard`\n"
            "`!setlevelrole` `!setlevelchannel`"
        ), inline=False)

        embed.add_field(name="👋 Welcome", value=(
            "`!setwelcome #channel <message>`\n"
            "`!setgoodbye` `!setjoinrole` `!testwelcome`"
        ), inline=False)

        embed.add_field(name="🎭 Reaction Roles", value=(
            "`!reactionrole` `!removereactionrole`\n"
            "`!listreactionroles`"
        ), inline=False)

        embed.add_field(name="⚙️ Custom Commands", value=(
            "`!addcommand` `!removecommand` `!listcommands`"
        ), inline=False)

        embed.add_field(name="🎉 Giveaways", value=(
            "`!gstart <time> <winners> <prize>` — start giveaway\n"
            "`!gend <message_id>` — end early\n"
            "`!greroll <message_id>` — reroll winner\n"
            "Example: `!gstart 1h 1 Nitro`"
        ), inline=False)

        embed.add_field(name="🎫 Tickets", value=(
            "`!ticket setup` — create ticket category\n"
            "`!ticket panel #channel` — send ticket panel\n"
            "`!ticket setrole @role` — set support role\n"
            "`!ticket setlogs #channel` — set log channel"
        ), inline=False)

        embed.add_field(name="📺 YouTube Alerts", value=(
            "`!youtube add <channel> #channel`\n"
            "`!youtube remove <channel>`\n"
            "`!youtube list`\n"
            "Example: `!youtube add MrBeast #alerts`"
        ), inline=False)

        embed.add_field(name="🟣 Twitch Alerts", value=(
            "`!twitch add <streamer> #channel`\n"
            "`!twitch remove <streamer>`\n"
            "`!twitch list`\n"
            "Example: `!twitch add pokimane #streams`"
        ), inline=False)

        embed.add_field(name="🟠 Reddit Alerts", value=(
            "`!reddit add <subreddit> #channel`\n"
            "`!reddit remove <subreddit>`\n"
            "`!reddit list`\n"
            "Example: `!reddit add gaming #reddit`"
        ), inline=False)

        embed.add_field(name="📊 Polls", value=(
            "`!poll <question>` — yes/no poll\n"
            "`!multipoll \"<question>\" option1 option2 ...`\n"
            "Example: `!poll Should we add a music channel?`"
        ), inline=False)

        embed.add_field(name="⏰ Scheduled Messages", value=(
            "`!schedule send #channel <time> <message>`\n"
            "`!schedule repeat #channel <interval> <message>`\n"
            "`!schedule list` `!schedule cancel <id>`\n"
            "Example: `!schedule send #general 1h Good morning!`"
        ), inline=False)

        embed.add_field(name="📢 Announcements", value=(
            "`!announce #channel <message>`\n"
            "`!embed \"<title>\" <description>`"
        ), inline=False)

        embed.add_field(name="🔧 Utility", value=(
            "`!ping` `!serverinfo` `!userinfo` `!premium` `!help`"
        ), inline=False)

        embed.set_footer(text="LuxeBot — Premium Discord Management • whop.com/luxebot/luxebot-premium")
        await ctx.send(embed=embed)

    # ── Welcome ───────────────────────────────────────────────

    @commands.command(name="setwelcome")
    @commands.has_permissions(manage_guild=True)
    async def setwelcome(self, ctx, channel: discord.TextChannel, *, message: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE guilds SET welcome_channel = ?, welcome_message = ? WHERE guild_id = ?",
                (channel.id, message, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(f"Welcome message set in {channel.mention}.\nVariables: `{{user}}` `{{server}}` `{{membercount}}`")

    @commands.command(name="setgoodbye")
    @commands.has_permissions(manage_guild=True)
    async def setgoodbye(self, ctx, channel: discord.TextChannel, *, message: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE guilds SET goodbye_message = ? WHERE guild_id = ?",
                (message, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(f"Goodbye message set in {channel.mention}.")

    @commands.command(name="setjoinrole")
    @commands.has_permissions(manage_guild=True)
    async def setjoinrole(self, ctx, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE guilds SET autorole = ? WHERE guild_id = ?",
                (role.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(f"Auto role set to {role.mention}. New members will receive this role.")

    @commands.command(name="testwelcome")
    @commands.has_permissions(manage_guild=True)
    async def testwelcome(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT welcome_channel, welcome_message FROM guilds WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row or not row[0]:
            await ctx.send("No welcome message set. Use `!setwelcome #channel <message>`")
            return

        channel = ctx.guild.get_channel(row[0])
        if not channel:
            await ctx.send("Welcome channel not found.")
            return

        message = row[1].replace("{user}", ctx.author.mention)
        message = message.replace("{server}", ctx.guild.name)
        message = message.replace("{membercount}", str(ctx.guild.member_count))

        embed = discord.Embed(description=message, color=BOT_COLOR)
        await channel.send(embed=embed)
        await ctx.send(f"Test welcome sent to {channel.mention}!")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT welcome_channel, welcome_message, autorole FROM guilds WHERE guild_id = ?",
                (member.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return

        if row[0] and row[1]:
            channel = member.guild.get_channel(row[0])
            if channel:
                message = row[1].replace("{user}", member.mention)
                message = message.replace("{server}", member.guild.name)
                message = message.replace("{membercount}", str(member.guild.member_count))
                embed = discord.Embed(description=message, color=BOT_COLOR)
                await channel.send(embed=embed)

        if row[2]:
            role = member.guild.get_role(row[2])
            if role:
                try:
                    await member.add_roles(role)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT welcome_channel, goodbye_message FROM guilds WHERE guild_id = ?",
                (member.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row or not row[1]:
            return

        channel = member.guild.get_channel(row[0])
        if channel:
            message = row[1].replace("{user}", member.name)
            message = message.replace("{server}", member.guild.name)
            message = message.replace("{membercount}", str(member.guild.member_count))
            embed = discord.Embed(description=message, color=0x95A5A6)
            await channel.send(embed=embed)

    # ── Reaction Roles ────────────────────────────────────────

    @commands.command(name="reactionrole")
    @commands.has_permissions(manage_guild=True)
    async def reactionrole(self, ctx, message_id: int, emoji: str, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, message_id, emoji, role.id)
            )
            await db.commit()

        try:
            for channel in ctx.guild.text_channels:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.add_reaction(emoji)
                    break
                except Exception:
                    continue
        except Exception:
            pass

        await ctx.send(f"Reaction role set! Reacting with {emoji} gives {role.mention}.")

    @commands.command(name="removereactionrole")
    @commands.has_permissions(manage_guild=True)
    async def removereactionrole(self, ctx, message_id: int, emoji: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                (ctx.guild.id, message_id, emoji)
            )
            await db.commit()
        await ctx.send(f"Reaction role removed for {emoji}.")

    @commands.command(name="listreactionroles")
    @commands.has_permissions(manage_guild=True)
    async def listreactionroles(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.send("No reaction roles set up.")
            return

        lines = [f"{r[1]} → <@&{r[2]}> (Message: {r[0]})" for r in rows]
        embed = discord.Embed(title="Reaction Roles", description="\n".join(lines), color=BOT_COLOR)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                (payload.guild_id, payload.message_id, str(payload.emoji))
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        role = guild.get_role(row[0])
        member = guild.get_member(payload.user_id)
        if role and member:
            try:
                await member.add_roles(role)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                (payload.guild_id, payload.message_id, str(payload.emoji))
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        role = guild.get_role(row[0])
        member = guild.get_member(payload.user_id)
        if role and member:
            try:
                await member.remove_roles(role)
            except Exception:
                pass

    # ── Custom Commands ───────────────────────────────────────

    @commands.command(name="addcommand")
    @commands.has_permissions(manage_guild=True)
    async def addcommand(self, ctx, command: str, *, response: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO custom_commands (guild_id, command, response) VALUES (?, ?, ?)",
                (ctx.guild.id, command.lower(), response)
            )
            await db.commit()
        await ctx.send(f"Custom command `!{command}` created!")

    @commands.command(name="removecommand")
    @commands.has_permissions(manage_guild=True)
    async def removecommand(self, ctx, command: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM custom_commands WHERE guild_id = ? AND command = ?",
                (ctx.guild.id, command.lower())
            )
            await db.commit()
        await ctx.send(f"Custom command `!{command}` removed.")

    @commands.command(name="listcommands")
    async def listcommands(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT command FROM custom_commands WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.send("No custom commands set up.")
            return

        commands_list = " ".join([f"`!{r[0]}`" for r in rows])
        embed = discord.Embed(title="Custom Commands", description=commands_list, color=BOT_COLOR)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT prefix FROM guilds WHERE guild_id = ?",
                (message.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        prefix = row[0] if row else "!"
        if not message.content.startswith(prefix):
            return

        cmd = message.content[len(prefix):].split()[0].lower()

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT response FROM custom_commands WHERE guild_id = ? AND command = ?",
                (message.guild.id, cmd)
            ) as cursor:
                row = await cursor.fetchone()

        if row:
            await message.channel.send(row[0])

    # ── Logging ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT log_channel FROM guilds WHERE guild_id = ?",
                (message.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row or not row[0]:
            return

        channel = message.guild.get_channel(row[0])
        if not channel:
            return

        embed = discord.Embed(
            title="Message Deleted",
            description=f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Content:** {message.content[:500] or 'No content'}",
            color=0xE74C3C,
            timestamp=datetime.utcnow()
        )
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content:
            return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT log_channel FROM guilds WHERE guild_id = ?",
                (before.guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row or not row[0]:
            return

        channel = before.guild.get_channel(row[0])
        if not channel:
            return

        embed = discord.Embed(
            title="Message Edited",
            description=f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n**Before:** {before.content[:300]}\n**After:** {after.content[:300]}",
            color=0xF39C12,
            timestamp=datetime.utcnow()
        )
        await channel.send(embed=embed)

    # ── Utility ───────────────────────────────────────────────

    @commands.command(name="ping")
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="Pong!",
            description=f"Latency: **{latency}ms**",
            color=BOT_COLOR
        )
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo")
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=BOT_COLOR, timestamp=datetime.utcnow())
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Channels", value=len(guild.channels))
        embed.add_field(name="Roles", value=len(guild.roles))
        embed.add_field(name="Owner", value=guild.owner.mention)
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @commands.command(name="userinfo")
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=str(member), color=BOT_COLOR, timestamp=datetime.utcnow())
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown")
        embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"))
        embed.add_field(name="Roles", value=len(member.roles) - 1)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Features(bot))
