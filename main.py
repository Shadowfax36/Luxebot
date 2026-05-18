import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timedelta
import database as db
from config import TOKEN, PREFIX, BOT_COLOR

COGS = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.leveling",
    "cogs.features",
    "cogs.premium_manager",
    "cogs.alerts",
    "cogs.giveaways",
    "cogs.tickets",
    "cogs.utilities",
    "cogs.slash_commands",
]


async def get_prefix(bot, message):
    if not message.guild:
        return PREFIX
    prefix = await db.get_prefix(message.guild.id)
    return prefix


bot = commands.Bot(
    command_prefix=get_prefix,
    intents=discord.Intents.all(),
    help_command=None
)


@bot.event
async def on_ready():
    await db.init_db()
    from cogs.alerts import init_alerts_db
    from cogs.giveaways import init_giveaway_db
    from cogs.tickets import init_ticket_db
    from cogs.utilities import init_utils_db
    await init_alerts_db()
    await init_giveaway_db()
    await init_ticket_db()
    await init_utils_db()

    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"Loaded: {cog}")
        except Exception as e:
            print(f"Failed to load {cog}: {e}")

    # Sync slash commands globally
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    print(f"LuxeBot is online as {bot.user}")
    print(f"Serving {len(bot.guilds)} servers")


@bot.event
async def on_guild_join(guild):
    await db.ensure_guild(guild.id)
    print(f"Joined server: {guild.name} ({guild.id})")
    trial_expires = (datetime.utcnow() + timedelta(days=7)).isoformat()
    async with aiosqlite.connect("luxebot.db") as db_conn:
        await db_conn.execute(
            "INSERT OR IGNORE INTO premium_servers (guild_id, trial_expires_at) VALUES (?, ?)",
            (guild.id, trial_expires)
        )
        await db_conn.commit()
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            e = discord.Embed(
                title="Thanks for adding LuxeBot!",
                description=(
                    "Your **7-day free trial** is now active — all premium features unlocked!\n\n"
                    "Type `/help` or `!help` to see all commands.\n\n"
                    "**Manage your server settings:**\n"
                    "https://luxebot-production.up.railway.app\n\n"
                    "After your trial, keep all features for **$5/month**:\n"
                    "whop.com/luxebot/luxebot-premium"
                ),
                color=BOT_COLOR
            )
            await channel.send(embed=e)
            break
    try:
        owner = guild.owner
        if owner:
            dm_embed = discord.Embed(
                title="Welcome to LuxeBot! Here is how to get set up",
                description=(
                    "Your **7-day free trial** is now active.\n\n"
                    "**Get set up in 3 steps:**\n\n"
                    "1. Run /automod to enable AI moderation\n"
                    "2. Run /leveling to turn on XP and role rewards\n"
                    "3. Run /ticket setup to create a support panel\n\n"
                    "**Full dashboard:**\n"
                    "https://luxebot-production.up.railway.app\n\n"
                    "Trial expires in 7 days. Keep all features for $5/month:\n"
                    "https://whop.com/luxebot/luxebot-premium\n\n"
                    "Need help? https://discord.gg/saTswBaM"
                ),
                color=BOT_COLOR
            )
            dm_embed.set_footer(text="LuxeBot - The bot your server deserves")
            await owner.send(embed=dm_embed)
    except discord.Forbidden:
        pass
    except Exception:
        pass
    try:

        owner = guild.owner

        if owner:

            dm_embed = discord.Embed(

                title="Welcome to LuxeBot! Here is how to get set up",

                description=(


                    "**Get set up in 3 steps:**\n\n"

                    "1. Run `/automod` to enable AI moderation\n"

                    "2. Run `/leveling` to turn on XP and role rewards\n"

                    "3. Run `/ticket setup` to create a support panel\n\n"

                    "**Full dashboard:**\n"

                    "https://luxebot-production.up.railway.app\n\n"

                    "Trial expires in 7 days. Keep all features for $5/month:\n"

                    "https://whop.com/luxebot/luxebot-premium\n\n"

                    "Need help? https://discord.gg/saTswBaM"

                ),

                color=BOT_COLOR

            )

            dm_embed.set_footer(text="LuxeBot — The bot your server deserves")

            await owner.send(embed=dm_embed)

    except discord.Forbidden:

        pass

    except Exception:

        pass



bot.run(TOKEN)
