import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import aiosqlite
import database as db

BOT_COLOR = 0xC9A84C
DB_PATH   = "luxebot.db"
WHOP_URL  = "https://whop.com/luxebot/luxebot-premium"


class PremiumManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_expired_trials.start()

    def cog_unload(self):
        self.check_expired_trials.cancel()

    # ── Hourly expiry check ───────────────────────────────────────────────────

    @tasks.loop(hours=1)
    async def check_expired_trials(self):
        """
        Runs every hour. Finds guilds whose trial expired in the last 2 hours,
        sends a channel message AND a DM to the server owner, then marks as notified.
        Does NOT delete rows — is_premium() handles expiry via timestamp comparison.
        """
        now          = datetime.utcnow()
        now_iso      = now.isoformat()
        two_hours_ago = (now - timedelta(hours=2)).isoformat()

        async with aiosqlite.connect(DB_PATH) as db_conn:
            async with db_conn.execute(
                """SELECT guild_id, trial_expires_at FROM premium_servers
                   WHERE trial_expires_at IS NOT NULL
                   AND trial_expires_at <= ?
                   AND trial_expires_at >= ?
                   AND (expires_at IS NULL OR expires_at <= ?)
                   AND notified_trial_expire IS NULL""",
                (now_iso, two_hours_ago, now_iso)
            ) as cursor:
                expired = await cursor.fetchall()

            for guild_id, trial_expires_at in expired:
                await self._notify_expiry(guild_id)
                await db_conn.execute(
                    "UPDATE premium_servers SET notified_trial_expire = ? WHERE guild_id = ?",
                    (now_iso, guild_id)
                )

            await db_conn.commit()

    async def _notify_expiry(self, guild_id: int):
        """Send channel alert + DM to server owner when trial expires."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        channel_embed = discord.Embed(
            title="⏰ Your Free Trial Has Ended",
            description=(
                "Your **7-day free trial** of LuxeBot Premium has expired.\n\n"
                f"**Subscribe to keep all features:**\n"
                f"👑 [Subscribe for $5/month]({WHOP_URL})\n\n"
                "One flat price. No feature tiers. No upsells.\n"
                "Use `/trial` to check your status."
            ),
            color=0xFF6B6B
        )
        channel_embed.set_footer(text=f"LuxeBot Premium • {WHOP_URL}")

        # Post in first writable text channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(embed=channel_embed)
                except Exception:
                    pass
                break

        # DM the server owner
        await self._dm_owner(guild)

    async def _dm_owner(self, guild: discord.Guild):
        """DM the guild owner with trial expiry notice and payment instructions."""
        owner = guild.owner
        if not owner:
            try:
                owner = await self.bot.fetch_user(guild.owner_id)
            except Exception:
                return

        dm_embed = discord.Embed(
            title="⏰ Your LuxeBot Trial Has Expired",
            description=(
                f"Hey {owner.display_name}! Your **7-day free trial** of LuxeBot "
                f"in **{guild.name}** has ended.\n\n"
                "**To keep all features active:**"
            ),
            color=0xFF6B6B
        )
        dm_embed.add_field(
            name="👑 Subscribe Now",
            value=f"[{WHOP_URL}]({WHOP_URL})",
            inline=False
        )
        dm_embed.add_field(
            name="💰 Price",
            value="**$5/month** — all features, no paywalls, no upsells.",
            inline=False
        )
        dm_embed.add_field(
            name="✅ How to pay",
            value=(
                f"1. Go to [{WHOP_URL}]({WHOP_URL})\n"
                f"2. Complete checkout\n"
                f"3. Enter your server ID: `{guild.id}`\n"
                f"4. Premium activates within seconds via webhook"
            ),
            inline=False
        )
        dm_embed.add_field(
            name="🔍 Check status anytime",
            value="Run `/trial` in your server to see current status.",
            inline=False
        )
        dm_embed.set_footer(text="LuxeBot — Thank you for trying us out!")

        try:
            await owner.send(embed=dm_embed)
            print(f"[PremiumManager] DM sent to owner {owner} of {guild.name} ({guild.id})")
        except discord.Forbidden:
            # Owner has DMs disabled — log and move on
            print(f"[PremiumManager] Could not DM owner of {guild.name} ({guild.id}) — DMs disabled")
        except Exception as e:
            print(f"[PremiumManager] DM error for {guild.name}: {e}")

    @check_expired_trials.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Ensure schema columns exist ───────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        """Add notified_trial_expire column if it doesn't exist yet (safe migration)."""
        try:
            async with aiosqlite.connect(DB_PATH) as db_conn:
                await db_conn.execute(
                    "ALTER TABLE premium_servers ADD COLUMN notified_trial_expire TEXT"
                )
                await db_conn.commit()
        except Exception:
            pass  # Column already exists — expected on subsequent starts


async def setup(bot):
    await bot.add_cog(PremiumManager(bot))
