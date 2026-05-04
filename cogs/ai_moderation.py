"""
ai_moderation.py — AI-powered moderation using Anthropic Claude

Layers on top of the existing rule-based automod with semantic understanding:
  - Toxicity detection (hate speech, threats, harassment)
  - Context-aware spam (evaded with leet-speak, spaces, etc.)
  - Raid detection (sudden join floods with similar account patterns)
  - Smart escalation (warn → mute → kick → ban based on severity)

Requires: ANTHROPIC_API_KEY env var
Falls back gracefully if API key not set or rate limited.
"""

import discord
from discord.ext import commands, tasks
import aiosqlite
import asyncio
import os
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict, deque
import database as db

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

BOT_COLOR = 0xC9A84C
DB_PATH = "luxebot.db"
AI_MODEL = "claude-haiku-3-5"  # Fast + cheap for real-time moderation

# ── Rate limiting for AI calls ────────────────────────────────────────────────
# We batch messages and only call Claude when rule-based checks pass.
# This keeps costs near zero for normal traffic.

_ai_call_times: deque = deque(maxlen=100)
AI_CALLS_PER_MINUTE = 20  # Safety ceiling


def _can_call_ai() -> bool:
    now = time.time()
    # Drop calls older than 60s
    while _ai_call_times and now - _ai_call_times[0] > 60:
        _ai_call_times.popleft()
    return len(_ai_call_times) < AI_CALLS_PER_MINUTE


def _record_ai_call():
    _ai_call_times.append(time.time())


# ── Raid detection state ──────────────────────────────────────────────────────

_join_tracker: dict = defaultdict(deque)  # guild_id -> deque of join timestamps


class AIModerator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = None
        if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            print("AI Moderation: Claude ready")
        else:
            print("AI Moderation: No API key — running in rule-based mode only")

        self.check_raid_decay.start()

    def cog_unload(self):
        self.check_raid_decay.cancel()

    # ── AI analysis ───────────────────────────────────────────────────────────

    async def analyze_message(self, content: str, context: str = "") -> dict:
        """
        Ask Claude to classify a message. Returns:
        {
            "action": "none" | "warn" | "delete" | "mute" | "ban",
            "reason": str,
            "severity": 1-10,
            "category": "toxicity" | "spam" | "harassment" | "threat" | "safe"
        }
        """
        if not self.client or not _can_call_ai():
            return {"action": "none", "reason": "", "severity": 0, "category": "safe"}

        _record_ai_call()

        prompt = f"""You are a Discord moderation system. Analyze this message and respond with JSON only.

Message: {content[:500]}
{f'Context: {context}' if context else ''}

Respond with exactly this JSON structure:
{{
  "action": "none" | "warn" | "delete" | "mute" | "ban",
  "reason": "brief reason",
  "severity": 1-10,
  "category": "toxicity" | "spam" | "harassment" | "threat" | "safe"
}}

Guidelines:
- "none" / "safe": normal conversation, mild rudeness, heated debate
- "warn" / severity 3-4: repeated mild toxicity, borderline content
- "delete" / severity 5-6: slurs, hate speech, explicit harassment
- "mute" / severity 7-8: serious threats, doxxing attempts, sustained harassment
- "ban" / severity 9-10: CSAM, credible violence threats, server raids

Be lenient. False positives hurt communities. When uncertain, choose "none"."""

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=AI_MODEL,
                    max_tokens=150,
                    messages=[{"role": "user", "content": prompt}]
                )
            )
            text = response.content[0].text.strip()
            # Extract JSON from response
            if "{" in text:
                text = text[text.index("{"):text.rindex("}")+1]
            result = json.loads(text)
            # Validate
            result["action"] = result.get("action", "none")
            result["severity"] = int(result.get("severity", 0))
            result["category"] = result.get("category", "safe")
            result["reason"] = result.get("reason", "")
            return result
        except Exception as e:
            print(f"AI Moderation analysis error: {e}")
            return {"action": "none", "reason": "", "severity": 0, "category": "safe"}

    async def analyze_username(self, username: str) -> dict:
        """Check if a joining username looks like a raid bot."""
        if not self.client or not _can_call_ai():
            return {"is_suspicious": False, "reason": ""}
        _record_ai_call()
        prompt = f"""Is this Discord username suspicious for a raid bot or spam account? Username: "{username}"
Reply with JSON: {{"is_suspicious": true/false, "reason": "brief reason"}}
Only flag clearly suspicious names (random chars, slurs, obvious spam patterns). When uncertain, say false."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=AI_MODEL,
                    max_tokens=80,
                    messages=[{"role": "user", "content": prompt}]
                )
            )
            text = response.content[0].text.strip()
            if "{" in text:
                text = text[text.index("{"):text.rindex("}")+1]
            return json.loads(text)
        except Exception:
            return {"is_suspicious": False, "reason": ""}

    # ── Action executor ───────────────────────────────────────────────────────

    async def execute_action(self, message: discord.Message, result: dict, source: str = "AI"):
        """Execute the moderation action and log it."""
        action   = result.get("action", "none")
        reason   = result.get("reason", "AI moderation")
        severity = result.get("severity", 0)
        category = result.get("category", "unknown")

        if action == "none":
            return

        guild   = message.guild
        member  = message.author
        channel = message.channel

        log_embed = discord.Embed(
            title=f"🤖 AI Mod — {action.upper()}",
            color=0xE74C3C if action in ("mute","ban") else 0xF39C12,
            timestamp=datetime.utcnow()
        )
        log_embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=True)
        log_embed.add_field(name="Channel", value=channel.mention, inline=True)
        log_embed.add_field(name="Category", value=category, inline=True)
        log_embed.add_field(name="Severity", value=f"{severity}/10", inline=True)
        log_embed.add_field(name="Source", value=source, inline=True)
        log_embed.add_field(name="Reason", value=reason, inline=False)
        log_embed.add_field(name="Message", value=message.content[:300] or "(empty)", inline=False)

        try:
            await message.delete()
        except Exception:
            pass

        if action == "warn":
            await db.add_warning(guild.id, member.id, f"[AI] {reason}", self.bot.user.id)
            warn_count = len(await db.get_warnings(guild.id, member.id))
            notify = await channel.send(
                f"{member.mention} ⚠️ Your message was removed: **{reason}**",
                delete_after=8
            )
            # Auto-escalate on repeat offenses
            if warn_count >= 5:
                await member.kick(reason="AI Mod: Auto-kick after 5 AI warnings")
                log_embed.title = "🤖 AI Mod — AUTO-KICK (5 warnings)"
            elif warn_count >= 3:
                until = datetime.utcnow() + timedelta(minutes=30)
                await member.timeout(until, reason="AI Mod: Auto-mute after 3 warnings")
                log_embed.title = "🤖 AI Mod — AUTO-MUTE (3 warnings)"

        elif action == "delete":
            await channel.send(
                f"{member.mention} Your message was removed for: **{reason}**",
                delete_after=6
            )

        elif action == "mute":
            duration = timedelta(hours=1) if severity <= 8 else timedelta(hours=24)
            try:
                await member.timeout(datetime.utcnow() + duration, reason=f"AI Mod: {reason}")
                await channel.send(
                    f"{member.mention} You have been muted for **{int(duration.total_seconds()//3600)}h**: {reason}",
                    delete_after=10
                )
            except discord.Forbidden:
                pass

        elif action == "ban":
            try:
                await guild.ban(member, reason=f"AI Mod: {reason}", delete_message_days=1)
                await channel.send(f"🔨 {member} was banned: {reason}", delete_after=10)
            except discord.Forbidden:
                pass

        # Send to log channel
        await self._send_log(guild, log_embed)

    async def _send_log(self, guild: discord.Guild, embed: discord.Embed):
        try:
            settings = await db.get_guild_settings(guild.id)
            if settings and settings[2]:  # log_channel
                ch = guild.get_channel(settings[2])
                if ch:
                    await ch.send(embed=embed)
        except Exception:
            pass

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return  # Don't moderate moderators

        content = message.content
        if not content or len(content) < 3:
            return

        guild_id = message.guild.id
        settings = await db.get_automod_settings(guild_id)
        if not settings:
            return

        # ── Rule-based pre-filter (fast, no API cost) ─────────────────────────
        # Only escalate to AI if content passes a suspicion threshold

        suspicion = 0
        flags = []

        # Bad words check (existing list)
        badwords = await db.get_badwords(guild_id)
        lower = content.lower()
        for word in badwords:
            if word in lower:
                suspicion += 4
                flags.append(f"bad word: {word}")
                break

        # Slur/toxicity signal words (lightweight regex-free check)
        SIGNAL_WORDS = [
            "kill yourself", "kys", "neck yourself", "rope yourself",
            "hate you", "doxx", "swat", "shoot", "bomb", "attack",
            "raid", "nigger", "faggot", "tranny", "chink", "spic",
        ]
        for sig in SIGNAL_WORDS:
            if sig in lower:
                suspicion += 5
                flags.append(f"signal: {sig}")
                break

        # Leet-speak evasion detection (e.g. k1ll, f@g, n1gg3r)
        LEET = str.maketrans("@013456789", "aoieasgbpg")
        unleet = lower.translate(LEET)
        for sig in SIGNAL_WORDS:
            if sig in unleet and sig not in lower:
                suspicion += 3
                flags.append("leet evasion")
                break

        # All-caps rage (only if AI enabled)
        if len(content) > 15 and sum(c.isupper() for c in content if c.isalpha()) / max(len([c for c in content if c.isalpha()]), 1) > 0.85:
            suspicion += 2
            flags.append("all caps")

        # Mention spam
        if len(message.mentions) >= 5:
            suspicion += 4
            flags.append(f"mass mention ({len(message.mentions)})")

        # Discord invite spam
        if "discord.gg/" in lower or "discord.com/invite/" in lower:
            if not message.author.guild_permissions.manage_guild:
                suspicion += 3
                flags.append("invite link")

        # Only call AI if suspicion score is high enough AND AI is available
        if suspicion >= 4 and self.client:
            context = f"Flags: {', '.join(flags)}" if flags else ""
            result = await self.analyze_message(content, context)
            if result["action"] != "none":
                await self.execute_action(message, result, source="AI+Rules")
                return

        # Lightweight action for high-confidence rule hits without AI
        if suspicion >= 7 and not self.client:
            # No AI available — use rules directly
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} Message removed: {', '.join(flags)}",
                    delete_after=5
                )
                await db.add_warning(guild_id, message.author.id, f"AutoMod: {', '.join(flags)}", self.bot.user.id)
            except Exception:
                pass

    # ── Raid detection ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = member.guild.id
        now = datetime.utcnow()

        q = _join_tracker[guild_id]
        q.append(now)

        # Trim entries older than 10 seconds
        while q and (now - q[0]).total_seconds() > 10:
            q.popleft()

        # Raid threshold: 8+ joins in 10 seconds
        if len(q) >= 8:
            await self._handle_raid(member.guild, list(q))

        # Account age check: accounts < 7 days old are suspicious
        account_age = (now - member.created_at.replace(tzinfo=None)).days
        if account_age < 7:
            # Check username with AI if available
            if self.client and _can_call_ai():
                result = await self.analyze_username(str(member))
                if result.get("is_suspicious"):
                    try:
                        embed = discord.Embed(
                            title="🤖 AI Mod — Suspicious Account",
                            description=f"{member.mention} (`{member.id}`) joined with a suspicious username.\n"
                                        f"Account age: **{account_age} days**\n"
                                        f"Reason: {result.get('reason', 'Unknown')}",
                            color=0xF39C12,
                            timestamp=now
                        )
                        await self._send_log(member.guild, embed)
                    except Exception:
                        pass

    async def _handle_raid(self, guild: discord.Guild, join_times: list):
        """Enable slowmode and alert mods when a raid is detected."""
        print(f"[AI Mod] Raid detected in {guild.name}: {len(join_times)} joins in 10s")

        embed = discord.Embed(
            title="🚨 RAID DETECTED",
            description=f"**{len(join_times)} accounts** joined in the last 10 seconds.\n"
                        f"Slowmode has been applied to all channels.\n"
                        f"Consider enabling community verification in Server Settings.",
            color=0xFF0000,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="LuxeBot AI Moderation")

        # Apply 2-minute slowmode to all text channels
        for channel in guild.text_channels:
            try:
                if channel.slowmode_delay == 0:
                    await channel.edit(slowmode_delay=120, reason="AI Mod: Raid protection")
            except Exception:
                pass

        await self._send_log(guild, embed)

    @tasks.loop(minutes=5)
    async def check_raid_decay(self):
        """Clean up old join tracker entries."""
        now = datetime.utcnow()
        for guild_id in list(_join_tracker.keys()):
            q = _join_tracker[guild_id]
            while q and (now - q[0]).total_seconds() > 60:
                q.popleft()

    @check_raid_decay.before_loop
    async def before_decay(self):
        await self.bot.wait_until_ready()




async def setup(bot):
    await bot.add_cog(AIModerator(bot))
