import discord
from discord.ext import commands
import aiosqlite

DB_PATH = "luxebot.db"


async def init_ticket_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                support_role INTEGER,
                log_channel INTEGER,
                ticket_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                user_id INTEGER,
                ticket_number INTEGER,
                closed INTEGER DEFAULT 0
            )
        """)
        await db.commit()


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open a Ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        cog = interaction.client.cogs.get("Tickets")
        if cog:
            await cog.create_ticket(interaction)


class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        cog = interaction.client.cogs.get("Tickets")
        if cog:
            await cog.close_ticket(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(init_ticket_db())
        self.bot.add_view(TicketView())
        self.bot.add_view(CloseView())

    @commands.group(name="ticket", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def ticket(self, ctx):
        await ctx.send("Commands: `!ticket setup`, `!ticket panel #channel`, `!ticket setrole @role`, `!ticket setlogs #channel`")

    @ticket.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup(self, ctx):
        category = await ctx.guild.create_category("Tickets")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO ticket_settings (guild_id, category_id) VALUES (?, ?)",
                (ctx.guild.id, category.id)
            )
            await db.commit()
        await ctx.send(f"Ticket category created: **{category.name}**. Now run `!ticket panel #channel` to set up the panel.")

    @ticket.command(name="setrole")
    @commands.has_permissions(manage_guild=True)
    async def ticket_setrole(self, ctx, role: discord.Role):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE ticket_settings SET support_role = ? WHERE guild_id = ?",
                (role.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(f"Support role set to {role.mention}.")

    @ticket.command(name="setlogs")
    @commands.has_permissions(manage_guild=True)
    async def ticket_setlogs(self, ctx, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE ticket_settings SET log_channel = ? WHERE guild_id = ?",
                (channel.id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(f"Ticket logs set to {channel.mention}.")

    @ticket.command(name="panel")
    @commands.has_permissions(manage_guild=True)
    async def ticket_panel(self, ctx, channel: discord.TextChannel):
        embed = discord.Embed(
            title="Support Tickets",
            description="Click the button below to open a support ticket.\nOur team will be with you shortly.",
            color=0x2ECC71
        )
        embed.set_footer(text=ctx.guild.name)
        await channel.send(embed=embed, view=TicketView())
        await ctx.send(f"Ticket panel sent to {channel.mention}.")

    async def create_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT category_id, support_role, ticket_count FROM ticket_settings WHERE guild_id = ?",
                (guild.id,)
            ) as cursor:
                settings = await cursor.fetchone()

        if not settings or not settings[0]:
            await interaction.followup.send("Tickets are not set up. Ask an admin to run `!ticket setup`.", ephemeral=True)
            return

        category_id, support_role_id, ticket_count = settings
        category = guild.get_channel(category_id)
        if not category:
            await interaction.followup.send("Ticket category not found.", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id FROM tickets WHERE guild_id = ? AND user_id = ? AND closed = 0",
                (guild.id, user.id)
            ) as cursor:
                existing = await cursor.fetchone()

        if existing:
            await interaction.followup.send(f"You already have an open ticket: <#{existing[0]}>", ephemeral=True)
            return

        ticket_num = (ticket_count or 0) + 1
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE ticket_settings SET ticket_count = ? WHERE guild_id = ?",
                (ticket_num, guild.id)
            )
            await db.commit()

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        if support_role_id:
            role = guild.get_role(support_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(
            f"ticket-{ticket_num:04d}",
            category=category,
            overwrites=overwrites
        )

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO tickets (guild_id, channel_id, user_id, ticket_number) VALUES (?, ?, ?, ?)",
                (guild.id, channel.id, user.id, ticket_num)
            )
            await db.commit()

        embed = discord.Embed(
            title=f"Ticket #{ticket_num:04d}",
            description=f"Hello {user.mention}! Support will be with you shortly.\n\nDescribe your issue and we'll help you out.",
            color=0x2ECC71
        )
        await channel.send(embed=embed, view=CloseView())
        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)

    async def close_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        guild = interaction.guild

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, user_id, ticket_number FROM tickets WHERE channel_id = ? AND closed = 0",
                (channel.id,)
            ) as cursor:
                ticket = await cursor.fetchone()

        if not ticket:
            await interaction.followup.send("This is not an open ticket.", ephemeral=True)
            return

        await db.execute("UPDATE tickets SET closed = 1 WHERE id = ?", (ticket[0],))

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE tickets SET closed = 1 WHERE id = ?", (ticket[0],))
            async with db.execute(
                "SELECT log_channel FROM ticket_settings WHERE guild_id = ?",
                (guild.id,)
            ) as cursor:
                settings = await cursor.fetchone()
            await db.commit()

        embed = discord.Embed(
            title="Ticket Closed",
            description=f"Ticket #{ticket[2]:04d} closed by {interaction.user.mention}",
            color=0xE74C3C
        )
        await channel.send(embed=embed)

        if settings and settings[0]:
            log_channel = guild.get_channel(settings[0])
            if log_channel:
                user = guild.get_member(ticket[1])
                log_embed = discord.Embed(
                    title=f"Ticket #{ticket[2]:04d} Closed",
                    description=f"**User:** {user.mention if user else ticket[1]}\n**Closed by:** {interaction.user.mention}\n**Channel:** {channel.name}",
                    color=0xE74C3C
                )
                await log_channel.send(embed=log_embed)

        await channel.delete()

    @ticket.command(name="close")
    @commands.has_permissions(manage_channels=True)
    async def ticket_close(self, ctx):
        await self.close_ticket_by_command(ctx)

    async def close_ticket_by_command(self, ctx):
        channel = ctx.channel
        guild = ctx.guild

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, user_id, ticket_number FROM tickets WHERE channel_id = ? AND closed = 0",
                (channel.id,)
            ) as cursor:
                ticket = await cursor.fetchone()

        if not ticket:
            await ctx.send("This is not an open ticket.")
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE tickets SET closed = 1 WHERE id = ?", (ticket[0],))
            await db.commit()

        await ctx.send("Closing ticket in 3 seconds...")
        import asyncio
        await asyncio.sleep(3)
        await channel.delete()


async def setup(bot):
    await bot.add_cog(Tickets(bot))
