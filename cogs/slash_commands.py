import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import database as db

BOT_COLOR = 0xC9A84C
DB_PATH = "luxebot.db"


def parse_duration(duration: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        return int(duration[:-1]) * units[duration[-1].lower()]
    except Exception:
        return 0


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
        embed.add_field(name="🛡️ Moderation", value="`/ban` `/kick` `/mute` `/unmute` `/warn` `/warnings` `/clearwarnings` `/purge`", inline=False)
        embed.add_field(name="🤖 AutoMod", value="`/automod` `/addbadword` `/removebadword`", inline=False)
        embed.add_field(name="👋 Welcome", value="`/setwelcome` `/setgoodbye` `/setjoinrole` `/testwelcome`", inline=False)
        embed.add_field(name="🎭 Reaction Roles", value="`/reactionrole` `/removereactionrole` `/listreactionroles`", inline=False)
        embed.add_field(name="⚙️ Custom Commands", value="`/addcommand` `/removecommand` `/listcommands`", inline=False)
        embed.add_field(name="⭐ Leveling", value="`/rank` `/leaderboard` `/setlevelrole` `/setlevelchannel`", inline=False)
        embed.add_field(name="🎉 Giveaways", value="`/giveaway` `/gend` `/greroll`", inline=False)
        embed.add_field(name="🎫 Tickets", value="`/ticketsetup` `/ticketpanel` `/ticketsetrole` `/ticketsetlogs`", inline=False)
        embed.add_field(name="📺 Alerts", value="`/youtubealert` `/twitchalert` `/redditalert` + remove/list variants", inline=False)
        embed.add_field(name="📊 Polls", value="`/poll` `/multipoll`", inline=False)
        embed.add_field(name="⏰ Scheduled", value="`/schedulesend` `/schedulerepeat` `/schedulelist` `/schedulecancel`", inline=False)
        embed.add_field(name="📢 Utility", value="`/announce` `/embed` `/ping` `/serverinfo` `/userinfo` `/premium`", inline=False)
        embed.add_field(name="🖥️ Dashboard", value="[Manage your server settings](https://luxebot-production.up.railway.app)", inline=False)
        embed.set_footer(text="LuxeBot • $5/month • whop.com/luxebot/luxebot-premium")
        await interaction.response.send_message(embed=embed)

    # ── Moderation ────────────────────────────────────────────

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="The member to ban", reason="Reason for the ban")
    @app_commands.default_permissions(ban_members=True)
    async def slash_ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(title="Member Banned", description=f"{member.mention} has been banned.\nReason: {reason}", color=0xE74C3C)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @app_commands.default_permissions(kick_members=True)
    async def slash_kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.kick(reason=reason)
        embed = discord.Embed(title="Member Kicked", description=f"{member.mention} has been kicked.\nReason: {reason}", color=0xE67E22)
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
        embed = discord.Embed(title="Member Muted", description=f"{member.mention} muted for {duration}.\nReason: {reason}", color=0x95A5A6)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unmute", description="Remove a timeout from a member")
    @app_commands.describe(member="The member to unmute")
    @app_commands.default_permissions(moderate_members=True)
    async def slash_unmute(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None)
        embed = discord.Embed(title="Member Unmuted", description=f"{member.mention} has been unmuted.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await db.add_warning(interaction.guild.id, member.id, reason, interaction.user.id)
        warnings = await db.get_warnings(interaction.guild.id, member.id)
        embed = discord.Embed(title="Member Warned", description=f"{member.mention} warned. Total warnings: {len(warnings)}\nReason: {reason}", color=0xF39C12)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="warnings", description="View all warnings for a member")
    @app_commands.describe(member="The member to check warnings for")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = await db.get_warnings(interaction.guild.id, member.id)
        if not warns:
            embed = discord.Embed(title=f"Warnings for {member.display_name}", description="This member has no warnings. ✅", color=0x2ECC71)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        lines = []
        for i, w in enumerate(warns):
            reason = w[3]
            mod_id = w[4]
            timestamp = w[5][:10] if w[5] else "unknown"
            lines.append(f"**{i+1}.** {reason} — by <@{mod_id}> on {timestamp}")
        embed = discord.Embed(title=f"Warnings for {member.display_name}", description="\n".join(lines), color=0xF39C12)
        embed.set_footer(text=f"{len(warns)} warning(s) total")
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member")
    @app_commands.describe(member="The member to clear warnings for")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = await db.get_warnings(interaction.guild.id, member.id)
        if not warns:
            embed = discord.Embed(title="No Warnings to Clear", description=f"{member.mention} has no warnings.", color=0x95A5A6)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await db.clear_warnings(interaction.guild.id, member.id)
        embed = discord.Embed(title="Warnings Cleared", description=f"Cleared **{len(warns)}** warning(s) for {member.mention}.", color=0x2ECC71)
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="purge", description="Delete a number of messages")
    @app_commands.describe(amount="Number of messages to delete (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def slash_purge(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"Deleted {amount} messages.", ephemeral=True)

    # ── AutoMod ───────────────────────────────────────────────

    @app_commands.command(name="automod", description="Toggle an AutoMod filter on or off")
    @app_commands.describe(filter_type="Filter to toggle: spam, links, caps, mentions", toggle="on or off")
    @app_commands.choices(
        filter_type=[
            app_commands.Choice(name="spam", value="spam"),
            app_commands.Choice(name="links", value="links"),
            app_commands.Choice(name="caps", value="caps"),
            app_commands.Choice(name="mentions", value="mentions"),
        ],
        toggle=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    @app_commands.default_permissions(manage_guild=True)
    async def slash_automod(self, interaction: discord.Interaction, filter_type: str, toggle: str):
        settings_map = {"spam": "anti_spam", "links": "anti_links", "caps": "anti_caps", "mentions": "anti_mentions"}
        setting = settings_map[filter_type]
        value = 1 if toggle == "on" else 0
        await db.update_automod_setting(interaction.guild.id, setting, value)
        embed = discord.Embed(
            title="AutoMod Updated",
            description=f"`{filter_type}` filter turned **{toggle}**.",
            color=BOT_COLOR if value else 0x95A5A6
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="addbadword", description="Add a word to the bad word filter")
    @app_commands.describe(word="The word to block")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_addbadword(self, interaction: discord.Interaction, word: str):
        await db.add_badword(interaction.guild.id, word.lower())
        embed = discord.Embed(title="Bad Word Added", description=f"Added `{word.lower()}` to the filter.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="removebadword", description="Remove a word from the bad word filter")
    @app_commands.describe(word="The word to remove")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_removebadword(self, interaction: discord.Interaction, word: str):
        await db.remove_badword(interaction.guild.id, word.lower())
        embed = discord.Embed(title="Bad Word Removed", description=f"Removed `{word.lower()}` from the filter.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Welcome ───────────────────────────────────────────────

    @app_commands.command(name="setwelcome", description="Set the welcome message and channel for new members")
    @app_commands.describe(channel="Channel to send welcome messages in", message="Welcome message. Use {user}, {server}, {membercount}")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_setwelcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "UPDATE guilds SET welcome_channel = ?, welcome_message = ? WHERE guild_id = ?",
                (channel.id, message, interaction.guild.id)
            )
            await db_conn.commit()
        embed = discord.Embed(title="Welcome Message Set", description=f"Sending to {channel.mention}.\n\n**Message:**\n{message}", color=BOT_COLOR)
        embed.set_footer(text="Variables: {user} {server} {membercount}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setgoodbye", description="Set the goodbye message for members who leave")
    @app_commands.describe(channel="Channel to send goodbye messages in", message="Goodbye message. Use {user}, {server}, {membercount}")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_setgoodbye(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "UPDATE guilds SET goodbye_message = ? WHERE guild_id = ?",
                (message, interaction.guild.id)
            )
            await db_conn.commit()
        embed = discord.Embed(title="Goodbye Message Set", description=f"Sending to {channel.mention}.\n\n**Message:**\n{message}", color=BOT_COLOR)
        embed.set_footer(text="Variables: {user} {server} {membercount}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setjoinrole", description="Set a role to automatically assign to new members")
    @app_commands.describe(role="The role to give new members when they join")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_setjoinrole(self, interaction: discord.Interaction, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("UPDATE guilds SET autorole = ? WHERE guild_id = ?", (role.id, interaction.guild.id))
            await db_conn.commit()
        embed = discord.Embed(title="Auto Role Set", description=f"New members will receive {role.mention} on join.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="testwelcome", description="Send a test welcome message to verify your setup")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_testwelcome(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute("SELECT welcome_channel, welcome_message FROM guilds WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                row = await cursor.fetchone()
        if not row or not row[0]:
            await interaction.response.send_message("No welcome message set. Use `/setwelcome` first.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(row[0])
        if not channel:
            await interaction.response.send_message("Welcome channel not found — use `/setwelcome` to set a new one.", ephemeral=True)
            return
        message = row[1].replace("{user}", interaction.user.mention).replace("{server}", interaction.guild.name).replace("{membercount}", str(interaction.guild.member_count))
        embed = discord.Embed(description=message, color=BOT_COLOR)
        await channel.send(embed=embed)
        await interaction.response.send_message(f"Test welcome sent to {channel.mention}!", ephemeral=True)

    # ── Reaction Roles ────────────────────────────────────────

    @app_commands.command(name="reactionrole", description="Assign a role to users who react with an emoji on a message")
    @app_commands.describe(message_id="ID of the message", emoji="The emoji users react with", role="The role to assign")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_reactionrole(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid message ID.", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, msg_id, emoji, role.id)
            )
            await db_conn.commit()
        for channel in interaction.guild.text_channels:
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.add_reaction(emoji)
                break
            except Exception:
                continue
        embed = discord.Embed(title="Reaction Role Set", description=f"Reacting with {emoji} on message `{msg_id}` assigns {role.mention}.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="removereactionrole", description="Remove a reaction role from a message")
    @app_commands.describe(message_id="ID of the message", emoji="The emoji to remove")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_removereactionrole(self, interaction: discord.Interaction, message_id: str, emoji: str):
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid message ID.", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (interaction.guild.id, msg_id, emoji))
            await db_conn.commit()
        embed = discord.Embed(title="Reaction Role Removed", description=f"Removed reaction role for {emoji} on message `{msg_id}`.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="listreactionroles", description="List all reaction roles in this server")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_listreactionroles(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute("SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No reaction roles set up.", ephemeral=True)
            return
        lines = [f"{r[1]} → <@&{r[2]}> (Message ID: `{r[0]}`)" for r in rows]
        embed = discord.Embed(title="Reaction Roles", description="\n".join(lines), color=BOT_COLOR)
        embed.set_footer(text=f"{len(rows)} reaction role(s)")
        await interaction.response.send_message(embed=embed)

    # ── Custom Commands ───────────────────────────────────────

    @app_commands.command(name="addcommand", description="Add a custom command for this server")
    @app_commands.describe(command="The command name (without prefix)", response="What the bot replies with")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_addcommand(self, interaction: discord.Interaction, command: str, response: str):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO custom_commands (guild_id, command, response) VALUES (?, ?, ?)",
                (interaction.guild.id, command.lower(), response)
            )
            await db_conn.commit()
        embed = discord.Embed(title="Custom Command Created", description=f"Command `!{command.lower()}` will reply:\n{response}", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="removecommand", description="Remove a custom command from this server")
    @app_commands.describe(command="The command name to remove")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_removecommand(self, interaction: discord.Interaction, command: str):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("DELETE FROM custom_commands WHERE guild_id = ? AND command = ?", (interaction.guild.id, command.lower()))
            await db_conn.commit()
        embed = discord.Embed(title="Custom Command Removed", description=f"Removed `!{command.lower()}`.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="listcommands", description="List all custom commands for this server")
    async def slash_listcommands(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute("SELECT command FROM custom_commands WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No custom commands set up.", ephemeral=True)
            return
        commands_list = " ".join([f"`!{r[0]}`" for r in rows])
        embed = discord.Embed(title="Custom Commands", description=commands_list, color=BOT_COLOR)
        embed.set_footer(text=f"{len(rows)} command(s)")
        await interaction.response.send_message(embed=embed)

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

    @app_commands.command(name="setlevelrole", description="Assign a role when members reach a certain level")
    @app_commands.describe(level="The level at which the role is awarded", role="The role to assign")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_setlevelrole(self, interaction: discord.Interaction, level: int, role: discord.Role):
        await db.add_level_role(interaction.guild.id, level, role.id)
        embed = discord.Embed(
            title="Level Role Set",
            description=f"Members will receive {role.mention} when they reach **level {level}**.",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setlevelchannel", description="Set the channel where level-up messages are sent")
    @app_commands.describe(channel="The channel for level-up announcements")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_setlevelchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("UPDATE guilds SET log_channel = ? WHERE guild_id = ?", (channel.id, interaction.guild.id))
            await db_conn.commit()
        embed = discord.Embed(
            title="Level-Up Channel Set",
            description=f"Level-up messages will be sent in {channel.mention}.",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setxpmultiplier", description="Set an XP multiplier for a specific channel")
    @app_commands.describe(channel="The channel to boost", multiplier="e.g. 2.0 for double XP")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_setxpmultiplier(self, interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
        if multiplier < 0.1 or multiplier > 10.0:
            await interaction.response.send_message("Multiplier must be between 0.1 and 10.0.", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO xp_multipliers (guild_id, channel_id, multiplier) VALUES (?, ?, ?)",
                (interaction.guild.id, channel.id, multiplier)
            )
            await db_conn.commit()
        embed = discord.Embed(
            title="XP Multiplier Set",
            description=f"{channel.mention} now gives **{multiplier}x** XP per message.",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setlevelmessage", description="Set a custom announcement for a specific level")
    @app_commands.describe(level="The level to customise", message="Use {user} and {level} as variables")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_setlevelmessage(self, interaction: discord.Interaction, level: int, message: str):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO level_milestones (guild_id, level, message) VALUES (?, ?, ?)",
                (interaction.guild.id, level, message)
            )
            await db_conn.commit()
        embed = discord.Embed(
            title="Level Milestone Set",
            description=f"Custom message at **level {level}**:\n{message}",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="givexp", description="Grant XP to a member")
    @app_commands.describe(member="The member to award", amount="Amount of XP to grant")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_givexp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount < 1 or amount > 100000:
            await interaction.response.send_message("Amount must be between 1 and 100,000.", ephemeral=True)
            return
        await db.add_xp(interaction.guild.id, member.id, amount)
        xp, level = await db.get_xp(interaction.guild.id, member.id)
        embed = discord.Embed(
            title="XP Granted",
            description=f"Gave **{amount:,} XP** to {member.mention}.\nThey now have **{xp:,} XP** (Level {level}).",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="resetxp", description="Reset a member's XP to zero")
    @app_commands.describe(member="The member to reset")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_resetxp(self, interaction: discord.Interaction, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "DELETE FROM levels WHERE guild_id = ? AND user_id = ?",
                (interaction.guild.id, member.id)
            )
            await db_conn.commit()
        try:
            from cache import invalidate_xp
            await invalidate_xp(interaction.guild.id, member.id)
        except Exception:
            pass
        embed = discord.Embed(
            title="XP Reset",
            description=f"Reset all XP for {member.mention}.",
            color=0x95A5A6
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="aimod", description="Check AI moderation status for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_aimod(self, interaction: discord.Interaction):
        ai_cog = self.bot.cogs.get("AIModerator")
        ai_on  = bool(ai_cog and ai_cog.client)
        # _ai_call_times is module-level in ai_moderation.py
        try:
            from cogs.ai_moderation import _ai_call_times
            call_count = len(_ai_call_times)
        except Exception:
            call_count = 0
        embed = discord.Embed(
            title="🤖 AI Moderation Status",
            color=BOT_COLOR if ai_on else 0x95A5A6
        )
        embed.add_field(name="Status",            value="✅ Active" if ai_on else "⚠️ Rule-based only (set ANTHROPIC_API_KEY)", inline=False)
        embed.add_field(name="Model",             value="claude-haiku-3-5" if ai_on else "N/A", inline=True)
        embed.add_field(name="API Calls (60s)",   value=str(call_count), inline=True)
        embed.add_field(name="Rate Limit",        value="20/min", inline=True)
        embed.add_field(
            name="Catches",
            value="• Toxicity & hate speech\n• Leet-speak evasion\n• Mass mentions\n• Invite spam\n• Raid detection\n• Suspicious new accounts",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Giveaways ─────────────────────────────────────────────

    @app_commands.command(name="giveaway", description="Start a giveaway")
    @app_commands.describe(duration="Duration (e.g. 1h, 30m, 1d)", winners="Number of winners", prize="What are you giving away?")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_giveaway(self, interaction: discord.Interaction, duration: str, winners: int, prize: str):
        from datetime import datetime, timedelta
        seconds = parse_duration(duration)
        if seconds == 0:
            await interaction.response.send_message("Invalid duration. Use format like `1h`, `30m`, `1d`.", ephemeral=True)
            return
        ends_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        end_timestamp = int(datetime.utcnow().timestamp()) + seconds
        embed = discord.Embed(
            title=f"GIVEAWAY: {prize}",
            description=f"React with 🎉 to enter!\n\n**Winners:** {winners}\n**Ends:** <t:{end_timestamp}:R>\n**Hosted by:** {interaction.user.mention}",
            color=0xF1C40F
        )
        embed.set_footer(text="LuxeBot Giveaways")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, ends_at, host_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (interaction.guild.id, interaction.channel.id, msg.id, prize, winners, ends_at, interaction.user.id)
            )
            await db_conn.commit()

    @app_commands.command(name="gend", description="End a giveaway early")
    @app_commands.describe(message_id="The message ID of the giveaway to end")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_gend(self, interaction: discord.Interaction, message_id: str):
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid message ID.", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT id, channel_id, prize, winners FROM giveaways WHERE message_id = ? AND guild_id = ? AND ended = 0",
                (msg_id, interaction.guild.id)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            await interaction.response.send_message("Giveaway not found or already ended.", ephemeral=True)
            return
        await interaction.response.defer()
        giveaway_cog = self.bot.cogs.get("Giveaways")
        if giveaway_cog:
            await giveaway_cog.end_giveaway(row[0], row[1], msg_id, row[2], row[3])
        await interaction.followup.send("Giveaway ended!", ephemeral=True)

    @app_commands.command(name="greroll", description="Reroll the winner of an ended giveaway")
    @app_commands.describe(message_id="The message ID of the ended giveaway")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_greroll(self, interaction: discord.Interaction, message_id: str):
        import random
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("Invalid message ID.", ephemeral=True)
            return
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT channel_id, prize, winners FROM giveaways WHERE message_id = ? AND guild_id = ? AND ended = 1",
                (msg_id, interaction.guild.id)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            await interaction.response.send_message("Ended giveaway not found.", ephemeral=True)
            return
        channel = self.bot.get_channel(row[0])
        if not channel:
            await interaction.response.send_message("Channel not found.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            msg = await channel.fetch_message(msg_id)
            reaction = discord.utils.get(msg.reactions, emoji="🎉")
            if not reaction:
                await interaction.followup.send("No reactions found on that message.", ephemeral=True)
                return
            users = [u async for u in reaction.users() if not u.bot]
            if not users:
                await interaction.followup.send("No valid entrants.", ephemeral=True)
                return
            new_winners = random.sample(users, min(row[2], len(users)))
            mentions = ", ".join(w.mention for w in new_winners)
            await channel.send(f"🎉 New winner(s) for **{row[1]}**: {mentions}!")
            await interaction.followup.send("Rerolled!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    # ── Tickets ───────────────────────────────────────────────

    @app_commands.command(name="ticketsetup", description="Create the ticket category for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_ticketsetup(self, interaction: discord.Interaction):
        await interaction.response.defer()
        category = await interaction.guild.create_category("Tickets")
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO ticket_settings (guild_id, category_id) VALUES (?, ?)",
                (interaction.guild.id, category.id)
            )
            await db_conn.commit()
        embed = discord.Embed(
            title="Ticket System Set Up",
            description=f"Created **Tickets** category.\nNow run `/ticketpanel` in your desired channel to post the panel.",
            color=0x2ECC71
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="ticketpanel", description="Send the ticket panel to a channel")
    @app_commands.describe(channel="Channel to send the ticket panel in")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_ticketpanel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        tickets_cog = self.bot.cogs.get("Tickets")
        if not tickets_cog:
            await interaction.response.send_message("Tickets cog not loaded.", ephemeral=True)
            return
        from cogs.tickets import TicketView
        embed = discord.Embed(
            title="Support Tickets",
            description="Click the button below to open a support ticket.\nOur team will be with you shortly.",
            color=0x2ECC71
        )
        embed.set_footer(text=interaction.guild.name)
        await channel.send(embed=embed, view=TicketView())
        embed_conf = discord.Embed(title="Ticket Panel Sent", description=f"Panel posted in {channel.mention}.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed_conf)

    @app_commands.command(name="ticketsetrole", description="Set the support role that can see all tickets")
    @app_commands.describe(role="The support role")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_ticketsetrole(self, interaction: discord.Interaction, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("UPDATE ticket_settings SET support_role = ? WHERE guild_id = ?", (role.id, interaction.guild.id))
            await db_conn.commit()
        embed = discord.Embed(title="Support Role Set", description=f"{role.mention} will have access to all tickets.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ticketsetlogs", description="Set the channel where closed ticket logs are sent")
    @app_commands.describe(channel="The log channel")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_ticketsetlogs(self, interaction: discord.Interaction, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("UPDATE ticket_settings SET log_channel = ? WHERE guild_id = ?", (channel.id, interaction.guild.id))
            await db_conn.commit()
        embed = discord.Embed(title="Ticket Logs Set", description=f"Closed ticket logs will be sent to {channel.mention}.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    # ── Alerts — YouTube ──────────────────────────────────────

    @app_commands.command(name="youtubealert", description="Add a YouTube channel alert")
    @app_commands.describe(yt_channel="YouTube channel name or handle (e.g. MrBeast)", discord_channel="Discord channel to post alerts in")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_youtubealert(self, interaction: discord.Interaction, yt_channel: str, discord_channel: discord.TextChannel):
        yt_channel = yt_channel.strip().replace("https://", "").replace("http://", "").replace("youtube.com/", "").replace("www.", "").replace("@", "").strip("/")
        await interaction.response.defer()
        alerts_cog = self.bot.cogs.get("Alerts")
        channel_id = await alerts_cog.resolve_youtube_channel(yt_channel) if alerts_cog else yt_channel
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO youtube_alerts (guild_id, channel_id, channel_name, discord_channel) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, channel_id, yt_channel, discord_channel.id)
            )
            await db_conn.commit()
        embed = discord.Embed(title="YouTube Alert Added", description=f"I'll post in {discord_channel.mention} when **{yt_channel}** uploads.", color=0xFF0000)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="youtubealertremove", description="Remove a YouTube channel alert")
    @app_commands.describe(yt_channel="YouTube channel name to remove")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_youtubealertremove(self, interaction: discord.Interaction, yt_channel: str):
        yt_channel = yt_channel.strip().replace("@", "")
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("DELETE FROM youtube_alerts WHERE guild_id = ? AND channel_name = ?", (interaction.guild.id, yt_channel))
            await db_conn.commit()
        embed = discord.Embed(title="YouTube Alert Removed", description=f"Removed alert for `{yt_channel}`.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="youtubealertlist", description="List all YouTube alerts for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_youtubealertlist(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute("SELECT channel_name, discord_channel FROM youtube_alerts WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No YouTube alerts set up.", ephemeral=True)
            return
        lines = [f"**{r[0]}** → <#{r[1]}>" for r in rows]
        embed = discord.Embed(title="YouTube Alerts", description="\n".join(lines), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

    # ── Alerts — Twitch ───────────────────────────────────────

    @app_commands.command(name="twitchalert", description="Add a Twitch streamer alert")
    @app_commands.describe(streamer="Twitch username", discord_channel="Discord channel to post alerts in")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_twitchalert(self, interaction: discord.Interaction, streamer: str, discord_channel: discord.TextChannel):
        streamer = streamer.lower().strip().replace("@", "")
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO twitch_alerts (guild_id, streamer, discord_channel, last_live) VALUES (?, ?, ?, 0)",
                (interaction.guild.id, streamer, discord_channel.id)
            )
            await db_conn.commit()
        embed = discord.Embed(title="Twitch Alert Added", description=f"I'll post in {discord_channel.mention} when **{streamer}** goes live.", color=0x9146FF)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="twitchalertremove", description="Remove a Twitch streamer alert")
    @app_commands.describe(streamer="Twitch username to remove")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_twitchalertremove(self, interaction: discord.Interaction, streamer: str):
        streamer = streamer.lower().strip().replace("@", "")
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("DELETE FROM twitch_alerts WHERE guild_id = ? AND streamer = ?", (interaction.guild.id, streamer))
            await db_conn.commit()
        embed = discord.Embed(title="Twitch Alert Removed", description=f"Removed alert for `{streamer}`.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="twitchalertlist", description="List all Twitch alerts for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_twitchalertlist(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute("SELECT streamer, discord_channel FROM twitch_alerts WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No Twitch alerts set up.", ephemeral=True)
            return
        lines = [f"**{r[0]}** → <#{r[1]}>" for r in rows]
        embed = discord.Embed(title="Twitch Alerts", description="\n".join(lines), color=0x9146FF)
        await interaction.response.send_message(embed=embed)

    # ── Alerts — Reddit ───────────────────────────────────────

    @app_commands.command(name="redditalert", description="Add a Reddit subreddit alert")
    @app_commands.describe(subreddit="Subreddit name (without r/)", discord_channel="Discord channel to post alerts in")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_redditalert(self, interaction: discord.Interaction, subreddit: str, discord_channel: discord.TextChannel):
        subreddit = subreddit.lower().replace("r/", "").strip()
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT OR REPLACE INTO reddit_alerts (guild_id, subreddit, discord_channel) VALUES (?, ?, ?)",
                (interaction.guild.id, subreddit, discord_channel.id)
            )
            await db_conn.commit()
        embed = discord.Embed(title="Reddit Alert Added", description=f"I'll post in {discord_channel.mention} when new posts appear in **r/{subreddit}**.", color=0xFF4500)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="redditalertremove", description="Remove a Reddit subreddit alert")
    @app_commands.describe(subreddit="Subreddit name to remove (without r/)")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_redditalertremove(self, interaction: discord.Interaction, subreddit: str):
        subreddit = subreddit.lower().replace("r/", "").strip()
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("DELETE FROM reddit_alerts WHERE guild_id = ? AND subreddit = ?", (interaction.guild.id, subreddit))
            await db_conn.commit()
        embed = discord.Embed(title="Reddit Alert Removed", description=f"Removed alert for **r/{subreddit}**.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="redditalertlist", description="List all Reddit alerts for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_redditalertlist(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute("SELECT subreddit, discord_channel FROM reddit_alerts WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No Reddit alerts set up.", ephemeral=True)
            return
        lines = [f"**r/{r[0]}** → <#{r[1]}>" for r in rows]
        embed = discord.Embed(title="Reddit Alerts", description="\n".join(lines), color=0xFF4500)
        await interaction.response.send_message(embed=embed)

    # ── Polls ─────────────────────────────────────────────────

    @app_commands.command(name="poll", description="Create a yes/no poll")
    @app_commands.describe(question="The poll question")
    async def slash_poll(self, interaction: discord.Interaction, question: str):
        embed = discord.Embed(title="Poll", description=question, color=0x3498DB)
        embed.set_footer(text=f"Poll by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

    @app_commands.command(name="multipoll", description="Create a poll with multiple options")
    @app_commands.describe(
        question="The poll question",
        option1="Option 1", option2="Option 2",
        option3="Option 3 (optional)", option4="Option 4 (optional)",
        option5="Option 5 (optional)", option6="Option 6 (optional)",
        option7="Option 7 (optional)", option8="Option 8 (optional)",
        option9="Option 9 (optional)"
    )
    async def slash_multipoll(self, interaction: discord.Interaction, question: str, option1: str, option2: str,
                               option3: str = None, option4: str = None, option5: str = None,
                               option6: str = None, option7: str = None, option8: str = None, option9: str = None):
        options = [o for o in [option1, option2, option3, option4, option5, option6, option7, option8, option9] if o]
        emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
        description = "\n".join(f"{emoji_numbers[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title=question, description=description, color=0x3498DB)
        embed.set_footer(text=f"Poll by {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        for i in range(len(options)):
            await msg.add_reaction(emoji_numbers[i])

    # ── Scheduled Messages ────────────────────────────────────

    @app_commands.command(name="schedulesend", description="Schedule a one-time message to be sent later")
    @app_commands.describe(channel="Channel to send the message in", delay="How long to wait (e.g. 30m, 2h, 1d)", message="The message to send")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_schedulesend(self, interaction: discord.Interaction, channel: discord.TextChannel, delay: str, message: str):
        from datetime import datetime, timedelta
        seconds = parse_duration(delay)
        if seconds == 0:
            await interaction.response.send_message("Invalid time. Use format like `30m`, `2h`, `1d`.", ephemeral=True)
            return
        send_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT INTO scheduled_messages (guild_id, channel_id, message, send_at) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, channel.id, message, send_at)
            )
            await db_conn.commit()
        embed = discord.Embed(title="Message Scheduled", description=f"Will send in {channel.mention} in **{delay}**.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="schedulerepeat", description="Schedule a repeating message")
    @app_commands.describe(channel="Channel to send in", interval="How often to send (e.g. 1h, 6h, 1d)", message="The message to repeat")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_schedulerepeat(self, interaction: discord.Interaction, channel: discord.TextChannel, interval: str, message: str):
        from datetime import datetime, timedelta
        seconds = parse_duration(interval)
        if seconds == 0:
            await interaction.response.send_message("Invalid interval. Use format like `1h`, `6h`, `1d`.", ephemeral=True)
            return
        send_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute(
                "INSERT INTO scheduled_messages (guild_id, channel_id, message, send_at, repeat_seconds) VALUES (?, ?, ?, ?, ?)",
                (interaction.guild.id, channel.id, message, send_at, seconds)
            )
            await db_conn.commit()
        embed = discord.Embed(title="Repeating Message Set", description=f"Sending in {channel.mention} every **{interval}**.", color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="schedulelist", description="List all scheduled messages for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_schedulelist(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                "SELECT id, channel_id, message, send_at, repeat_seconds FROM scheduled_messages WHERE guild_id = ? AND sent = 0",
                (interaction.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No scheduled messages.", ephemeral=True)
            return
        lines = [f"**ID {r[0]}** → <#{r[1]}> {'🔁 repeating' if r[4] else '📬 one-time'}\n_{r[2][:60]}_" for r in rows]
        embed = discord.Embed(title="Scheduled Messages", description="\n\n".join(lines), color=BOT_COLOR)
        embed.set_footer(text=f"{len(rows)} scheduled message(s)")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="schedulecancel", description="Cancel a scheduled message by its ID")
    @app_commands.describe(msg_id="The ID of the scheduled message (from /schedulelist)")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_schedulecancel(self, interaction: discord.Interaction, msg_id: int):
        async with aiosqlite.connect(DB_PATH) as db_conn:
            await db_conn.execute("UPDATE scheduled_messages SET sent = 1 WHERE id = ? AND guild_id = ?", (msg_id, interaction.guild.id))
            await db_conn.commit()
        embed = discord.Embed(title="Scheduled Message Cancelled", description=f"Cancelled message **#{msg_id}**.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)

    # ── Announcements ─────────────────────────────────────────

    @app_commands.command(name="announce", description="Send an announcement embed to a channel")
    @app_commands.describe(channel="Channel to announce in", message="The announcement text")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_announce(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        embed = discord.Embed(description=message, color=BOT_COLOR)
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await channel.send(embed=embed)
        await interaction.response.send_message(f"Announcement sent to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="embed", description="Send a custom embed with a title and description")
    @app_commands.describe(title="The embed title", description="The embed description")
    @app_commands.default_permissions(manage_guild=True)
    async def slash_embed(self, interaction: discord.Interaction, title: str, description: str):
        embed = discord.Embed(title=title, description=description, color=BOT_COLOR)
        await interaction.response.send_message(embed=embed)

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
            embed = discord.Embed(title="LuxeBot Premium", description="This server has **premium access** active! ✅", color=BOT_COLOR)
        else:
            embed = discord.Embed(title="LuxeBot Premium", description="This server does not have premium access.\n\nGet premium for **$5/month**:\nhttps://whop.com/luxebot/luxebot-premium", color=0xFF6B6B)
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="trial", description="Check your free trial or premium status")
    async def slash_trial(self, interaction: discord.Interaction):
        status = await db.get_premium_status(interaction.guild.id)
        kind   = status["type"]
        days   = status["days_left"]
        hours  = status["hours_left"]
        expires = status["expires_at"]

        if kind == "premium" and expires == "lifetime":
            embed = discord.Embed(
                title="👑 LuxeBot Premium",
                description="This server has **lifetime premium** access. All features permanently unlocked.",
                color=BOT_COLOR
            )

        elif kind == "premium":
            embed = discord.Embed(title="👑 LuxeBot Premium — Active", color=BOT_COLOR)
            embed.add_field(name="Status", value="✅ Premium active", inline=True)
            embed.add_field(name="Expires", value=f"`{expires}`", inline=True)
            embed.add_field(name="Time remaining", value=f"**{days}d {hours}h**", inline=True)
            embed.set_footer(text="Manage at whop.com/luxebot/luxebot-premium")

        elif kind == "trial":
            total_hours     = 7 * 24
            remaining_hours = days * 24 + hours
            filled = int((remaining_hours / total_hours) * 20)
            bar = "█" * filled + "░" * (20 - filled)

            color = 0xEF4444 if days == 0 else (0xF97316 if days <= 2 else BOT_COLOR)
            embed = discord.Embed(title="🕐 Free Trial — Active", color=color)
            embed.add_field(name="Trial expires", value=f"`{expires}`", inline=True)
            embed.add_field(name="Time remaining", value=f"**{days}d {hours}h**", inline=True)
            embed.add_field(
                name="Progress",
                value=f"`{bar}` {remaining_hours}h of {total_hours}h remaining",
                inline=False
            )
            embed.add_field(
                name="Keep all features after trial",
                value="[👑 Subscribe for $5/month](https://whop.com/luxebot/luxebot-premium)",
                inline=False
            )
            if days == 0:
                embed.set_footer(text="⚠️ Trial expires today — subscribe now to avoid interruption!")
            elif days <= 2:
                embed.set_footer(text=f"⚠️ Expires in {days}d {hours}h — subscribe to keep access")
            else:
                embed.set_footer(text="LuxeBot Premium • $5/month • all features included")

        elif kind == "expired":
            embed = discord.Embed(
                title="⏰ Trial Expired",
                description=(
                    "Your 7-day free trial has ended.\n\n"
                    "**Subscribe to restore all features:**\n"
                    "👑 [Get Premium — $5/month](https://whop.com/luxebot/luxebot-premium)\n\n"
                    "One flat price. No feature tiers. No upsells."
                ),
                color=0xFF6B6B
            )
            embed.set_footer(text="whop.com/luxebot/luxebot-premium")

        else:  # "none"
            embed = discord.Embed(
                title="No Trial Found",
                description=(
                    "No trial or premium record found for this server.\n\n"
                    "This shouldn't happen — LuxeBot grants a trial automatically on join.\n"
                    "Please contact support or subscribe directly:\n"
                    "👑 [Get Premium — $5/month](https://whop.com/luxebot/luxebot-premium)"
                ),
                color=0x95A5A6
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dashboard", description="Get the link to the LuxeBot dashboard")
    async def slash_dashboard(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="LuxeBot Dashboard",
            description="Manage your server settings, view commands, configure automod and more:\n\nhttps://luxebot-production.up.railway.app",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed)


    # ── Vote ──────────────────────────────────────────────────

    @app_commands.command(name="vote", description="Vote for LuxeBot on top.gg and get 2x XP for 12 hours")
    async def slash_vote(self, interaction: discord.Interaction):
        import os, aiohttp, aiosqlite
        from datetime import datetime, timedelta

        bot_id  = os.getenv("DISCORD_BOT_ID", "")
        topgg_token = os.getenv("TOPGG_TOKEN", "")
        vote_url = f"https://top.gg/bot/{bot_id}/vote" if bot_id else "https://top.gg/bot/luxebot/vote"
        user_id  = interaction.user.id

        # Check if user has an active vote bonus already
        async with aiosqlite.connect("luxebot.db") as db:
            async with db.execute(
                "SELECT expires_at FROM vote_bonuses WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()

        now = datetime.utcnow().isoformat()
        active_bonus = row and row[0] > now

        # Check top.gg API for recent vote (only if we have a token)
        has_voted_api = False
        if topgg_token and bot_id:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"https://top.gg/api/bots/{bot_id}/check?userId={user_id}",
                        headers={"Authorization": topgg_token},
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            has_voted_api = bool(data.get("voted", 0))
            except Exception:
                pass  # API unreachable — fall back to DB state

        embed = discord.Embed(title="🗳️ Vote for LuxeBot", color=0xC9A84C)
        embed.set_footer(text="Votes reset every 12 hours on top.gg")

        if active_bonus:
            # Already has active bonus from a confirmed vote
            expires = datetime.fromisoformat(row[0])
            remaining = expires - datetime.utcnow()
            hours   = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            embed.description = (
                f"✅ **You already voted!** Your 2x XP bonus is active.\n\n"
                f"⏱️ Expires in: **{hours}h {minutes}m**\n\n"
                f"Vote again after your bonus expires:\n{vote_url}"
            )
            embed.color = 0x4ade80
        elif has_voted_api:
            # Voted via API check but bonus not yet in DB (edge case)
            async with aiosqlite.connect("luxebot.db") as db:
                expires_at = (datetime.utcnow() + timedelta(hours=12)).isoformat()
                await db.execute(
                    "INSERT OR REPLACE INTO vote_bonuses (user_id, expires_at) VALUES (?, ?)",
                    (user_id, expires_at)
                )
                await db.commit()
            embed.description = (
                f"✅ **Thank you for voting!** 2x XP is now active for **12 hours**.\n\n"
                f"Your vote helps LuxeBot reach more servers 🚀\n\n"
                f"[Vote again in 12 hours]({vote_url})"
            )
            embed.color = 0x4ade80
        else:
            embed.description = (
                f"**Voting takes 10 seconds and gives you 2x XP for 12 hours!**\n\n"
                f"🔗 [Click here to vote]({vote_url})\n\n"
                f"**Rewards:**\n"
                f"• 🌟 2x XP on all messages for 12 hours\n"
                f"• 🎤 2x Voice XP for 12 hours\n"
                f"• Stacks with streak, booster, and weekend bonuses\n\n"
                f"Your bonus is applied automatically when the vote is confirmed."
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


    # ── Owner: grant premium ──────────────────────────────────

    @app_commands.command(name="grantpremium", description="Grant premium to a server (owner only)")
    @app_commands.describe(
        guild_id="The server ID to grant premium to (leave blank for this server)",
        days="Number of days (leave blank for lifetime)"
    )
    async def slash_grantpremium(self, interaction: discord.Interaction,
                                  guild_id: str = None, days: int = None):
        OWNER_ID = "1196910040364372028"
        if str(interaction.user.id) != OWNER_ID:
            await interaction.response.send_message(
                "❌ This command is restricted to the bot owner.",
                ephemeral=True
            )
            return

        import aiosqlite
        from datetime import datetime, timedelta

        target_id = int(guild_id) if guild_id else interaction.guild.id

        if days and days > 0:
            expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
            expiry_label = f"{days} day{'s' if days != 1 else ''}"
        else:
            expires = "9999-12-31"
            expiry_label = "lifetime"

        async with aiosqlite.connect("luxebot.db") as db:
            await db.execute(
                "INSERT OR REPLACE INTO premium_servers (guild_id, expires_at) VALUES (?, ?)",
                (target_id, expires)
            )
            await db.commit()

        # Bust Redis cache if available
        try:
            from cache import invalidate_premium
            await invalidate_premium(target_id)
        except Exception:
            pass

        embed = discord.Embed(
            title="👑 Premium Granted",
            description=(
                f"**Server ID:** `{target_id}`\n"
                f"**Duration:** {expiry_label}\n"
                f"**Expires:** {'Never' if expires == '9999-12-31' else expires[:10]}"
            ),
            color=0xC9A84C
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommands(bot))
