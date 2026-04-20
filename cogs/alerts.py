import discord
from discord.ext import commands, tasks
import aiosqlite
import aiohttp
import xml.etree.ElementTree as ET

DB_PATH = "luxebot.db"


async def init_alerts_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS youtube_alerts (
                guild_id INTEGER,
                channel_id TEXT,
                channel_name TEXT,
                discord_channel INTEGER,
                last_video_id TEXT,
                PRIMARY KEY (guild_id, channel_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS twitch_alerts (
                guild_id INTEGER,
                streamer TEXT,
                discord_channel INTEGER,
                last_live INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, streamer)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reddit_alerts (
                guild_id INTEGER,
                subreddit TEXT,
                discord_channel INTEGER,
                last_post_id TEXT,
                PRIMARY KEY (guild_id, subreddit)
            )
        """)
        await db.commit()


class Alerts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(init_alerts_db())
        self.check_youtube.start()
        self.check_twitch.start()
        self.check_reddit.start()

    def cog_unload(self):
        self.check_youtube.cancel()
        self.check_twitch.cancel()
        self.check_reddit.cancel()

    # ── YouTube ──────────────────────────────────────────────

    @commands.group(name="youtube", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def youtube(self, ctx):
        embed = discord.Embed(
            title="YouTube Alerts",
            description=(
                "`!youtube add <channel> #discord-channel`\n"
                "`!youtube remove <channel>`\n"
                "`!youtube list`\n\n"
                "Examples:\n"
                "`!youtube add MrBeast #alerts`\n"
                "`!youtube add PewDiePie #videos`"
            ),
            color=0xFF0000
        )
        await ctx.send(embed=embed)

    @youtube.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def youtube_add(self, ctx, yt_channel: str, discord_channel: discord.TextChannel):
        yt_channel = yt_channel.strip()
        yt_channel = yt_channel.replace("https://", "").replace("http://", "")
        yt_channel = yt_channel.replace("youtube.com/", "").replace("www.", "")
        yt_channel = yt_channel.replace("@", "").strip("/")

        msg = await ctx.send(f"🔍 Looking up **{yt_channel}** on YouTube...")
        channel_id = await self.resolve_youtube_channel(yt_channel)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO youtube_alerts (guild_id, channel_id, channel_name, discord_channel) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, channel_id, yt_channel, discord_channel.id)
            )
            await db.commit()

        embed = discord.Embed(
            title="YouTube Alert Added",
            description=f"I'll post in {discord_channel.mention} when **{yt_channel}** uploads.\nChecking every 10 minutes.",
            color=0xFF0000
        )
        await msg.edit(content=None, embed=embed)

    @youtube.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def youtube_remove(self, ctx, yt_channel: str):
        yt_channel = yt_channel.strip().replace("@", "")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM youtube_alerts WHERE guild_id = ? AND channel_name = ?",
                (ctx.guild.id, yt_channel)
            )
            await db.commit()
        await ctx.send(f"Removed YouTube alert for `{yt_channel}`.")

    @youtube.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def youtube_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_name, discord_channel FROM youtube_alerts WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await ctx.send("No YouTube alerts set up. Use `!youtube add <channel> #channel`")
            return
        lines = [f"**{r[0]}** → <#{r[1]}>" for r in rows]
        embed = discord.Embed(title="YouTube Alerts", description="\n".join(lines), color=0xFF0000)
        await ctx.send(embed=embed)

    async def resolve_youtube_channel(self, handle: str):
        for url in [
            f"https://www.youtube.com/feeds/videos.xml?user={handle}",
            f"https://www.youtube.com/feeds/videos.xml?channel_id={handle}",
        ]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            root = ET.fromstring(text)
                            ns = {"yt": "http://www.youtube.com/xml/schemas/2015"}
                            cid = root.find("yt:channelId", ns)
                            if cid is not None:
                                return cid.text
            except Exception:
                pass
        return handle

    @tasks.loop(minutes=10)
    async def check_youtube(self):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, channel_id, channel_name, discord_channel, last_video_id FROM youtube_alerts"
            ) as cursor:
                rows = await cursor.fetchall()

        for guild_id, channel_id, channel_name, discord_channel_id, last_video_id in rows:
            try:
                text = None
                for url in [
                    f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
                    f"https://www.youtube.com/feeds/videos.xml?user={channel_name}",
                ]:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                text = await resp.text()
                                break

                if not text:
                    continue

                root = ET.fromstring(text)
                ns = {
                    "atom": "http://www.w3.org/2005/Atom",
                    "yt": "http://www.youtube.com/xml/schemas/2015",
                }
                entries = root.findall("atom:entry", ns)
                if not entries:
                    continue

                latest = entries[0]
                video_id_el = latest.find("yt:videoId", ns)
                title_el = latest.find("atom:title", ns)
                if video_id_el is None:
                    continue

                vid_id = video_id_el.text
                if vid_id == last_video_id:
                    continue

                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE youtube_alerts SET last_video_id = ? WHERE guild_id = ? AND channel_id = ?",
                        (vid_id, guild_id, channel_id)
                    )
                    await db.commit()

                if last_video_id is None:
                    continue

                channel = self.bot.get_channel(discord_channel_id)
                if not channel:
                    continue

                title = title_el.text if title_el is not None else "New Video"
                embed = discord.Embed(
                    title=f"New video from {channel_name}!",
                    description=f"**{title}**\nhttps://youtube.com/watch?v={vid_id}",
                    color=0xFF0000
                )
                embed.set_thumbnail(url=f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg")
                await channel.send(embed=embed)

            except Exception as e:
                print(f"YouTube check error for {channel_name}: {e}")

    @check_youtube.before_loop
    async def before_youtube(self):
        await self.bot.wait_until_ready()

    # ── Twitch ───────────────────────────────────────────────

    @commands.group(name="twitch", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def twitch(self, ctx):
        embed = discord.Embed(
            title="Twitch Alerts",
            description=(
                "`!twitch add <streamer> #discord-channel`\n"
                "`!twitch remove <streamer>`\n"
                "`!twitch list`\n\n"
                "Example: `!twitch add pokimane #streams`"
            ),
            color=0x9146FF
        )
        await ctx.send(embed=embed)

    @twitch.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def twitch_add(self, ctx, streamer: str, discord_channel: discord.TextChannel):
        streamer = streamer.lower().strip().replace("@", "")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO twitch_alerts (guild_id, streamer, discord_channel, last_live) VALUES (?, ?, ?, 0)",
                (ctx.guild.id, streamer, discord_channel.id)
            )
            await db.commit()
        embed = discord.Embed(
            title="Twitch Alert Added",
            description=f"I'll post in {discord_channel.mention} when **{streamer}** goes live.\nChecking every 5 minutes.",
            color=0x9146FF
        )
        await ctx.send(embed=embed)

    @twitch.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def twitch_remove(self, ctx, streamer: str):
        streamer = streamer.lower().strip().replace("@", "")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM twitch_alerts WHERE guild_id = ? AND streamer = ?",
                (ctx.guild.id, streamer)
            )
            await db.commit()
        await ctx.send(f"Removed Twitch alert for `{streamer}`.")

    @twitch.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def twitch_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT streamer, discord_channel FROM twitch_alerts WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await ctx.send("No Twitch alerts set up. Use `!twitch add <streamer> #channel`")
            return
        lines = [f"**{r[0]}** → <#{r[1]}>" for r in rows]
        embed = discord.Embed(title="Twitch Alerts", description="\n".join(lines), color=0x9146FF)
        await ctx.send(embed=embed)

    @tasks.loop(minutes=5)
    async def check_twitch(self):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, streamer, discord_channel, last_live FROM twitch_alerts"
            ) as cursor:
                rows = await cursor.fetchall()

        for guild_id, streamer, discord_channel_id, last_live in rows:
            try:
                url = f"https://decapi.me/twitch/live/{streamer}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        text = (await resp.text()).strip()

                is_live = streamer.lower() in text.lower() and "offline" not in text.lower()

                if is_live and not last_live:
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute(
                            "UPDATE twitch_alerts SET last_live = 1 WHERE guild_id = ? AND streamer = ?",
                            (guild_id, streamer)
                        )
                        await db.commit()
                    channel = self.bot.get_channel(discord_channel_id)
                    if channel:
                        embed = discord.Embed(
                            title=f"{streamer} is now LIVE on Twitch!",
                            description=f"https://twitch.tv/{streamer}",
                            color=0x9146FF
                        )
                        await channel.send(f"@everyone **{streamer}** is live!", embed=embed)

                elif not is_live and last_live:
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute(
                            "UPDATE twitch_alerts SET last_live = 0 WHERE guild_id = ? AND streamer = ?",
                            (guild_id, streamer)
                        )
                        await db.commit()

            except Exception as e:
                print(f"Twitch check error for {streamer}: {e}")

    @check_twitch.before_loop
    async def before_twitch(self):
        await self.bot.wait_until_ready()

    # ── Reddit ───────────────────────────────────────────────

    @commands.group(name="reddit", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def reddit(self, ctx):
        embed = discord.Embed(
            title="Reddit Alerts",
            description=(
                "`!reddit add <subreddit> #discord-channel`\n"
                "`!reddit remove <subreddit>`\n"
                "`!reddit list`\n\n"
                "Example: `!reddit add gaming #reddit`"
            ),
            color=0xFF4500
        )
        await ctx.send(embed=embed)

    @reddit.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def reddit_add(self, ctx, subreddit: str, discord_channel: discord.TextChannel):
        subreddit = subreddit.lower().replace("r/", "").strip()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO reddit_alerts (guild_id, subreddit, discord_channel) VALUES (?, ?, ?)",
                (ctx.guild.id, subreddit, discord_channel.id)
            )
            await db.commit()
        embed = discord.Embed(
            title="Reddit Alert Added",
            description=f"I'll post in {discord_channel.mention} when new posts appear in **r/{subreddit}**.\nChecking every 15 minutes.",
            color=0xFF4500
        )
        await ctx.send(embed=embed)

    @reddit.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def reddit_remove(self, ctx, subreddit: str):
        subreddit = subreddit.lower().replace("r/", "").strip()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM reddit_alerts WHERE guild_id = ? AND subreddit = ?",
                (ctx.guild.id, subreddit)
            )
            await db.commit()
        await ctx.send(f"Removed Reddit alert for **r/{subreddit}**.")

    @reddit.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def reddit_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT subreddit, discord_channel FROM reddit_alerts WHERE guild_id = ?",
                (ctx.guild.id,)
            ) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await ctx.send("No Reddit alerts set up. Use `!reddit add <subreddit> #channel`")
            return
        lines = [f"**r/{r[0]}** → <#{r[1]}>" for r in rows]
        embed = discord.Embed(title="Reddit Alerts", description="\n".join(lines), color=0xFF4500)
        await ctx.send(embed=embed)

    @tasks.loop(minutes=15)
    async def check_reddit(self):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT guild_id, subreddit, discord_channel, last_post_id FROM reddit_alerts"
            ) as cursor:
                rows = await cursor.fetchall()

        for guild_id, subreddit, discord_channel_id, last_post_id in rows:
            try:
                url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=1"
                headers = {"User-Agent": "LuxeBot/1.0"}
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                posts = data.get("data", {}).get("children", [])
                if not posts:
                    continue

                post = posts[0]["data"]
                post_id = post["id"]

                if post_id == last_post_id:
                    continue

                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE reddit_alerts SET last_post_id = ? WHERE guild_id = ? AND subreddit = ?",
                        (post_id, guild_id, subreddit)
                    )
                    await db.commit()

                if last_post_id is None:
                    continue

                channel = self.bot.get_channel(discord_channel_id)
                if not channel:
                    continue

                embed = discord.Embed(
                    title=post["title"][:256],
                    url=f"https://reddit.com{post['permalink']}",
                    description=f"Posted by u/{post['author']} in r/{subreddit}",
                    color=0xFF4500
                )
                if post.get("thumbnail") and post["thumbnail"].startswith("http"):
                    embed.set_thumbnail(url=post["thumbnail"])
                await channel.send(embed=embed)

            except Exception as e:
                print(f"Reddit check error for {subreddit}: {e}")

    @check_reddit.before_loop
    async def before_reddit(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Alerts(bot))
