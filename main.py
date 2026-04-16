import discord
from discord.ext import commands
import asyncio
import database as db
from config import TOKEN, DEFAULT_PREFIX, BOT_COLOR

async def get_prefix(bot, message):
    if not message.guild:
        return DEFAULT_PREFIX
    prefix = await db.get_prefix(message.guild.id)
    return prefix

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

COGS = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.leveling",
    "cogs.features",
]

@bot.event
async def on_ready():
    print(f"LuxeBot is online as {bot.user}")
    print(f"Serving {len(bot.guilds)} servers")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name=f"{len(bot.guilds)} servers | !help"
    ))


@bot.event
async def on_guild_join(guild):
    await db.ensure_guild(guild.id)
    print(f"Joined server: {guild.name} ({guild.id})")
    async with aiosqlite.connect("luxebot.db") as db_conn:
        await db_conn.execute(
            "INSERT OR IGNORE INTO premium_servers (guild_id) VALUES (?)",
            (guild.id,)
        )
        await db_conn.commit()
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            e = discord.Embed(
                title="Thanks for adding LuxeBot!",
                description="Your **7-day free trial** is now active — all premium features unlocked!\n\nType `!help` to see all commands.\n\nAfter your trial, keep all features for **$5/month**:\nwhop.com/luxebot/luxebot-premium\n\nTo get started:\n`!setlog #channel` — mod log\n`!setwelcome #channel Welcome!` — welcome messages",
                color=BOT_COLOR
            )
            await channel.send(embed=e)
            break


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=discord.Embed(description="You don't have permission to use this command.", color=0xe74c3c))
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(embed=discord.Embed(description="Member not found. Make sure you @mention them or use their ID.", color=0xe74c3c))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=discord.Embed(description=f"Missing argument: `{error.param.name}`. Type `!help` for usage.", color=0xe74c3c))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=discord.Embed(description="Invalid argument. Type `!help` for correct usage.", color=0xe74c3c))
    else:
        print(f"Unhandled error: {error}")

async def main():
    await db.init_db()
    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                print(f"Loaded: {cog}")
            except Exception as e:
                print(f"Failed to load {cog}: {e}")
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
