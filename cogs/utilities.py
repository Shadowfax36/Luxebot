import discord
from discord.ext import commands, tasks
import aiosqlite
from datetime import datetime, timedelta

DB_PATH = "luxebot.db"


async def init_utils_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                message TEXT,
                send_at TEXT,
                repeat_seconds INTEGER DEFAULT 0,
                sent INTEGER DEFAULT 0
            )
        """)
        await db.commit()


def parse_duration(duration: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        return int(duration[:-1]) * units[duration[-1].lower()]
    except Exception:
        return 0


class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(init_utils_db())
        self.check_scheduled.start()

    def cog_unload(self):
        self.check_scheduled.cancel()

    # ── Polls ────────────────────────────────────────────────

    @commands.command(name="poll")
    async def poll(self, ctx, *, question: str):
        """Create a yes/no poll. Example: !poll Should we add a music channel?"""
        embed = discord.Embed(
            title="Poll",
            description=question,
            color=0x3498DB
        )
        embed.set_footer(text=f"Poll by {ctx.author.display_name}")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        await ctx.message.delete()

    @commands.command(name="multipoll")
    async def multipoll(self, ctx, question: str, *options):
        """Create a multi-option poll. Example: !multipoll "Favorite color?" Red Blue Green"""
        if len(options) < 2:
            await ctx.send("You need at least 2 options. Example: `!multipoll \"Question?\" Option1 Option2 Option3`")
            return
        if len(options) > 9:
            await ctx.send("Maximum 9 options.")
            return

        emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
        description = "\n".join(f"{emoji_numbers[i]} {opt}" for i, opt in enumerate(options))

        embed = discord.Embed(
            title=question,
            description=description,
            color=0x3498DB
        )
        embed.set_footer(text=f"Poll by {ctx.author.display_name}")
        msg = await ctx.send(embed=embed)

        for i in range(len(options)):
            await msg.add_reaction(emoji_numbers[i])
        await ctx.message.delete()

    # ── Scheduled Messages ────────────────────────────────────

    @commands.group(name="schedule", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def schedule(self, ctx):
        await ctx.send(
            "Commands:\n"
            "`!schedule send <#channel> <time> <message>` — send once after delay\n"
            "`!schedule repeat <#channel> <interval> <message>` — repeat on interval\n"
            "`!schedule list` — list scheduled messages\n"
            "`!schedule cancel <id>` — cancel a scheduled message\n\n"
            "Time examples: `30m`, `2h`, `1d`"
        )

    @schedule.command(name="send")
    @commands.has_permissions(manage_guild=True)
    async def schedule_send(self, ctx, channel: discord.TextChannel, delay: str, *, message: str):
        """Schedule a one-time message."""
        seconds = parse_duration(delay)
        if seconds == 0:
            await ctx.send("Invalid time. Use format like `30m`, `2h`, `1d`.")
            return
        send_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO scheduled_messages (guild_id, channel_id, message, send_at) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, channel.id, message, send_at)
            )
            await db.commit()
        embed = discord.Embed(
            title="Message Scheduled",
            description=f"I'll send your message to {channel.mention} in **{delay}**.",
            color=0x2ECC71
        )
        await ctx.send(embed=embed)

    @schedule.command(name="repeat")
    @commands.has_permissions(manage_guild=True)
    async def schedule_repeat(self, ctx, channel: discord.TextChannel, interval: str, *, message: str):
        """Schedule a repeating message."""
        seconds = parse_duration(interval)
        if seconds == 0:
            await ctx.send("Invalid interval. Use format like `30m`, `2h`, `1d`.")
            return
        send_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO scheduled_messages (guild_id, channel_id, message, send_at, repeat_seconds) VALUES (?, ?, ?, ?, ?)",
                (ctx.guild.id, channel.id, message, send_at, seconds)
            )
            await db.commit()
        embed = discord.Embed(
            title="Repeating Message Scheduled",
            description=f"I'll send your message to {channel.mention} every **{interval}**.",
            color=0x2ECC71
        )
        await ctx.send(embed=embed)

    @schedule.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def schedule_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, channel_id, message, send_at, repeat_seconds FROM scheduled_messages WHERE guild_id = ? AND sent = 0",
                (ctx.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await ctx.send("No scheduled messages.")
            return
        lines = []
        for row in rows:
            repeat = f" (repeats every {row[4]}s)" if row[4] else ""
            lines.append(f"**ID {row[0]}** → <#{row[1]}>{repeat}\n`{row[3][:16]}`\n_{row[2][:50]}_")
        embed = discord.Embed(
            title="Scheduled Messages",
            description="\n\n".join(lines),
            color=0x3498DB
        )
        await ctx.send(embed=embed)

    @schedule.command(name="cancel")
    @commands.has_permissions(manage_guild=True)
    async def schedule_cancel(self, ctx, msg_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE scheduled_messages SET sent = 1 WHERE id = ? AND guild_id = ?",
                (msg_id, ctx.guild.id)
            )
            await db.commit()
        await ctx.send(f"Cancelled scheduled message **#{msg_id}**.")

    @tasks.loop(seconds=30)
    async def check_scheduled(self):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, channel_id, message, repeat_seconds FROM scheduled_messages WHERE sent = 0 AND send_at <= ?",
                (now,)
            ) as cursor:
                rows = await cursor.fetchall()

        for msg_id, channel_id, message, repeat_seconds in rows:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(message)
                except Exception as e:
                    print(f"Scheduled message error: {e}")

            async with aiosqlite.connect(DB_PATH) as db:
                if repeat_seconds:
                    next_send = (datetime.utcnow() + timedelta(seconds=repeat_seconds)).isoformat()
                    await db.execute(
                        "UPDATE scheduled_messages SET send_at = ? WHERE id = ?",
                        (next_send, msg_id)
                    )
                else:
                    await db.execute(
                        "UPDATE scheduled_messages SET sent = 1 WHERE id = ?",
                        (msg_id,)
                    )
                await db.commit()

    @check_scheduled.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Utility commands ─────────────────────────────────────

    @commands.command(name="announce")
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, channel: discord.TextChannel, *, message: str):
        """Send an announcement to a channel."""
        embed = discord.Embed(
            description=message,
            color=0xC9A84C
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        await channel.send(embed=embed)
        await ctx.message.delete()

    @commands.command(name="embed")
    @commands.has_permissions(manage_guild=True)
    async def send_embed(self, ctx, title: str, *, description: str):
        """Send a custom embed. Example: !embed "Title" Description here"""
        embed = discord.Embed(title=title, description=description, color=0xC9A84C)
        await ctx.send(embed=embed)
        await ctx.message.delete()


async def setup(bot):
    await bot.add_cog(Utilities(bot))
