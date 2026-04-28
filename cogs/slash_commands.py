import discord
from discord.ext import commands
from discord import app_commands
import database as db

BOT_COLOR = 0xC9A84C


class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Help ─────────────────────────────────────────────────

    @app_commands.command(name="help", description="Show all LuxeBot commands")
    async def slash_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="👑 LuxeBot Commands",
            description="Premium Discord management for $5/month.\nAll features included — no upsells.",
            color=BOT_COLOR
        )
        embed.add_field(name="🛡️ Moderation", value="`/ban` `/kick` `/mute` `/warn` `/warnings` `/purge`", inline=False)
        embed.add_field(name="⭐ Leveling", value="`/rank` `/leaderboard`", inline=False)
        embed.add_field(name="🎉 Giveaways", value="`/giveaway` — start a giveaway", inline=False)
        embed.add_field(name="📊 Polls", value="`/poll` — create a yes/no poll", inline=False)
        embed.add_field(name="🔧 Utility", value="`/ping` `/serverinfo` `/userinfo` `/premium`", inline=False)
        embed.add_field(name="🖥️ Dashboard", value="[Manage your server settings](https://luxebot-production.up.railway.app)", inline=False)
        embed.set_footer(text="LuxeBot • $5/month • whop.com/luxebot/luxebot-premium")
        await interaction.response.send_message(embed=embed)

    # ── Moderation ────────────────────────────────────────────

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="The member to ban", reason="Reason for the ban")
    @app_commands.default_permissions(ban_members=True)
    async def slash_ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="Member Banned",
            description=f"{member.mention} has been banned.\nReason: {reason}",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @app_commands.default_permissions(kick_members=True)
    async def slash_kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="Member Kicked",
            description=f"{member.mention} has been kicked.\nReason: {reason}",
            color=0xE67E22
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="mute", description="Timeout a member")
    @app_commands.describe(member="The member to mute", duration="Duration (e.g. 10m, 1h, 1d)", reason="Reason")
    @app_commands.default_permissions(moderate_members=True)
    async def slash_mute(self, interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "No reason provided"):
        from datetime import datetime, timedelta
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        try:
            seconds = int(duration[:-1]) * units[duration[-1].lower()]
        except Exception:
            seconds = 600
        until = datetime.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=reason)
        embed = discord.Embed(
            title="Member Muted",
            description=f"{member.mention} muted for {duration}.\nReason: {reason}",
            color=0x95A5A6
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await db.add_warning(interaction.guild.id, member.id, reason, interaction.user.id)
        warnings = await db.get_warnings(interaction.guild.id, member.id)
        embed = discord.Embed(
            title="Member Warned",
            description=f"{member.mention} warned. Total warnings: {len(warnings)}\nReason: {reason}",
            color=0xF39C12
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="warnings", description="View all warnings for a member")
    @app_commands.describe(member="The member to check warnings for")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = await db.get_warnings(interaction.guild.id, member.id)
        if not warns:
            embed = discord.Embed(
                title=f"Warnings for {member.display_name}",
                description="This member has no warnings. ✅",
                color=0x2ECC71
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        lines = []
        for i, w in enumerate(warns):
            # w: (id, guild_id, user_id, reason, moderator_id, timestamp)
            reason = w[3]
            mod_id = w[4]
            timestamp = w[5][:10] if w[5] else "unknown"
            lines.append(f"**{i+1}.** {reason} — by <@{mod_id}> on {timestamp}")
        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            description="\n".join(lines),
            color=0xF39C12
        )
        embed.set_footer(text=f"{len(warns)} warning(s) total")
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="purge", description="Delete a number of messages")
    @app_commands.describe(amount="Number of messages to delete")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_purge(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {amount} messages.", ephemeral=True)

    # ── Leveling ──────────────────────────────────────────────

    @app_commands.command(name="rank", description="Check your rank or another member's rank")
    @app_commands.describe(member="The member to check (leave empty for yourself)")
    async def slash_rank(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        xp, level = await db.get_xp(interaction.guild.id, member.id)
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        embed = discord.Embed(title=f"{member.display_name}'s Rank", color=BOT_COLOR)
        embed.add_field(name="Level", value=str(level))
        embed.add_field(name="XP", value=f"{xp}/{xp_needed}")
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Show the server XP leaderboard")
    async def slash_leaderboard(self, interaction: discord.Interaction):
        top = await db.get_leaderboard(interaction.guild.id, 10)
        if not top:
            await interaction.response.send_message("No one has earned XP yet!")
            return
        lines = []
        for i, (user_id, xp, level) in enumerate(top):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            lines.append(f"**{i+1}.** {name} — Level {level} ({xp} XP)")
        embed = discord.Embed(title=f"{interaction.guild.name} Leaderboard", description="\n".join(lines), color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    # ── Giveaway ──────────────────────────────────────────────

    @app_commands.command(name="giveaway", description="Start a giveaway")
    @app_commands.describe(duration="Duration (e.g. 1h, 30m, 1d)", winners="Number of winners", prize="What are you giving away?")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_giveaway(self, interaction: discord.Interaction, duration: str, winners: int, prize: str):
        from datetime import datetime, timedelta
        import aiosqlite
        import random

        units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        try:
            seconds = int(duration[:-1]) * units[duration[-1].lower()]
        except Exception:
            await interaction.response.send_message("Invalid duration. Use format like `1h`, `30m`, `1d`.", ephemeral=True)
            return

        ends_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        end_timestamp = int(datetime.utcnow().timestamp()) + seconds

        embed = discord.Embed(
            title=f"GIVEAWAY: {prize}",
            description=(
                f"React with 🎉 to enter!\n\n"
                f"**Winners:** {winners}\n"
                f"**Ends:** <t:{end_timestamp}:R>\n"
                f"**Hosted by:** {interaction.user.mention}"
            ),
            color=0xF1C40F
        )
        embed.set_footer(text="LuxeBot Giveaways")

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")

        async with aiosqlite.connect("luxebot.db") as db_conn:
            await db_conn.execute(
                "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, ends_at, host_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (interaction.guild.id, interaction.channel.id, msg.id, prize, winners, ends_at, interaction.user.id)
            )
            await db_conn.commit()

    # ── Poll ──────────────────────────────────────────────────

    @app_commands.command(name="poll", description="Create a yes/no poll")
    @app_commands.describe(question="The poll question")
    async def slash_poll(self, interaction: discord.Interaction, question: str):
        embed = discord.Embed(title="Poll", description=question, color=0x3498DB)
        embed.set_footer(text=f"Poll by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

    # ── Utility ───────────────────────────────────────────────

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def slash_ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="Pong!", description=f"Latency: **{latency}ms**", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Show server information")
    async def slash_serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        from datetime import datetime
        embed = discord.Embed(title=guild.name, color=BOT_COLOR, timestamp=datetime.utcnow())
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Channels", value=len(guild.channels))
        embed.add_field(name="Roles", value=len(guild.roles))
        embed.add_field(name="Owner", value=guild.owner.mention)
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Show user information")
    @app_commands.describe(member="The member to look up")
    async def slash_userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        from datetime import datetime
        embed = discord.Embed(title=str(member), color=BOT_COLOR, timestamp=datetime.utcnow())
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown")
        embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"))
        embed.add_field(name="Roles", value=len(member.roles) - 1)
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="premium", description="Check premium status for this server")
    async def slash_premium(self, interaction: discord.Interaction):
        is_prem = await db.is_premium(interaction.guild.id)
        if is_prem:
            embed = discord.Embed(
                title="LuxeBot Premium",
                description="This server has **premium access** active! ✅",
                color=BOT_COLOR
            )
        else:
            embed = discord.Embed(
                title="LuxeBot Premium",
                description="This server does not have premium access.\n\nGet premium for **$5/month**:\nhttps://whop.com/luxebot/luxebot-premium",
                color=0xFF6B6B
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dashboard", description="Get the link to the LuxeBot dashboard")
    async def slash_dashboard(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="LuxeBot Dashboard",
            description="Manage your server settings, view commands, configure automod and more:\n\nhttps://luxebot-production.up.railway.app",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(SlashCommands(bot))
