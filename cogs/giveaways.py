import discord
from discord.ext import commands, tasks
import aiosqlite
import random
from datetime import datetime, timedelta

DB_PATH = "luxebot.db"


async def init_giveaway_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                prize TEXT,
                winners INTEGER DEFAULT 1,
                ends_at TEXT,
                ended INTEGER DEFAULT 0,
                host_id INTEGER
            )
        """)
        await db.commit()


def parse_duration(duration: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        return int(duration[:-1]) * units[duration[-1].lower()]
    except Exception:
        return 0


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(init_giveaway_db())
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @commands.command(name="gstart")
    @commands.has_permissions(manage_guild=True)
    async def gstart(self, ctx, duration: str, winners: str, *, prize: str):
        """Start a giveaway. Example: !gstart 1h 1 Nitro"""
        if winners.endswith("w"):
            winner_count = int(winners[:-1])
        else:
            try:
                winner_count = int(winners)
            except ValueError:
                prize = f"{winners} {prize}"
                winner_count = 1

        seconds = parse_duration(duration)
        if seconds == 0:
            await ctx.send("Invalid duration. Use format like `1h`, `30m`, `1d`.")
            return

        ends_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()

        embed = discord.Embed(
            title=f"GIVEAWAY: {prize}",
            description=(
                f"React with 🎉 to enter!\n\n"
                f"**Winners:** {winner_count}\n"
                f"**Ends:** <t:{int(datetime.utcnow().timestamp()) + seconds}:R>\n"
                f"**Hosted by:** {ctx.author.mention}"
            ),
            color=0xF1C40F
        )
        embed.set_footer(text=f"Ends at {ends_at[:19]} UTC")

        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, ends_at, host_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ctx.guild.id, ctx.channel.id, msg.id, prize, winner_count, ends_at, ctx.author.id)
            )
            await db.commit()

        await ctx.message.delete()

    @commands.command(name="gend")
    @commands.has_permissions(manage_guild=True)
    async def gend(self, ctx, message_id: int):
        """End a giveaway early."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, channel_id, prize, winners FROM giveaways WHERE message_id = ? AND guild_id = ? AND ended = 0",
                (message_id, ctx.guild.id)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            await ctx.send("Giveaway not found or already ended.")
            return
        await self.end_giveaway(row[0], row[1], message_id, row[2], row[3])

    @commands.command(name="greroll")
    @commands.has_permissions(manage_guild=True)
    async def greroll(self, ctx, message_id: int):
        """Reroll a giveaway winner."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id, prize, winners FROM giveaways WHERE message_id = ? AND guild_id = ? AND ended = 1",
                (message_id, ctx.guild.id)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            await ctx.send("Ended giveaway not found.")
            return
        channel = self.bot.get_channel(row[0])
        if not channel:
            return
        try:
            msg = await channel.fetch_message(message_id)
            reaction = discord.utils.get(msg.reactions, emoji="🎉")
            if not reaction:
                await ctx.send("No reactions found.")
                return
            users = [u async for u in reaction.users() if not u.bot]
            if not users:
                await ctx.send("No valid entrants.")
                return
            winners = random.sample(users, min(row[2], len(users)))
            mentions = ", ".join(w.mention for w in winners)
            await channel.send(f"🎉 New winner(s) for **{row[1]}**: {mentions}!")
        except Exception as e:
            await ctx.send(f"Error: {e}")

    async def end_giveaway(self, giveaway_id, channel_id, message_id, prize, winner_count):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,))
            await db.commit()

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(message_id)
            reaction = discord.utils.get(msg.reactions, emoji="🎉")
            users = []
            if reaction:
                users = [u async for u in reaction.users() if not u.bot]

            if not users:
                embed = discord.Embed(
                    title=f"GIVEAWAY ENDED: {prize}",
                    description="No valid entrants.",
                    color=0x95A5A6
                )
                await msg.edit(embed=embed)
                await channel.send("No valid entrants for the giveaway.")
                return

            winners = random.sample(users, min(winner_count, len(users)))
            mentions = ", ".join(w.mention for w in winners)

            embed = discord.Embed(
                title=f"GIVEAWAY ENDED: {prize}",
                description=f"**Winners:** {mentions}",
                color=0x95A5A6
            )
            await msg.edit(embed=embed)
            await channel.send(f"🎉 Congratulations {mentions}! You won **{prize}**!")
        except Exception as e:
            print(f"Giveaway end error: {e}")

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, channel_id, message_id, prize, winners FROM giveaways WHERE ended = 0 AND ends_at <= ?",
                (now,)
            ) as cursor:
                rows = await cursor.fetchall()
        for row in rows:
            await self.end_giveaway(row[0], row[1], row[2], row[3], row[4])

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
