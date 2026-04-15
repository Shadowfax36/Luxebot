import discord
from discord.ext import commands
from datetime import datetime
import database as db
from config import BOT_COLOR


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        g = await db.get_guild(member.guild.id)
        if g.get('welcome_channel'):
            channel = member.guild.get_channel(g['welcome_channel'])
            if channel:
                msg = g['welcome_message'].replace('{user}', member.mention)\
                    .replace('{server}', member.guild.name)\
                    .replace('{membercount}', str(member.guild.member_count))
                e = discord.Embed(description=msg, color=BOT_COLOR, timestamp=datetime.utcnow())
                e.set_author(name=f"Welcome to {member.guild.name}!", icon_url=member.display_avatar.url)
                e.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=e)
        if g.get('join_role'):
            role = member.guild.get_role(g['join_role'])
            if role:
                try:
                    await member.add_roles(role, reason="Auto join role")
                except:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        g = await db.get_guild(member.guild.id)
        if g.get('goodbye_channel'):
            channel = member.guild.get_channel(g['goodbye_channel'])
            if channel:
                msg = g['goodbye_message'].replace('{user}', str(member))\
                    .replace('{server}', member.guild.name)\
                    .replace('{membercount}', str(member.guild.member_count))
                e = discord.Embed(description=msg, color=0x95a5a6, timestamp=datetime.utcnow())
                e.set_author(name=f"{member} left the server.", icon_url=member.display_avatar.url)
                await channel.send(embed=e)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setwelcome(self, ctx, channel: discord.TextChannel, *, message: str):
        await db.set_guild(ctx.guild.id, welcome_channel=channel.id, welcome_message=message)
        await ctx.send(embed=discord.Embed(description=f"Welcome message set in {channel.mention}.\nMessage: {message}", color=BOT_COLOR))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setgoodbye(self, ctx, channel: discord.TextChannel, *, message: str):
        await db.set_guild(ctx.guild.id, goodbye_channel=channel.id, goodbye_message=message)
        await ctx.send(embed=discord.Embed(description=f"Goodbye message set in {channel.mention}.", color=BOT_COLOR))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setjoinrole(self, ctx, role: discord.Role):
        await db.set_guild(ctx.guild.id, join_role=role.id)
        await ctx.send(embed=discord.Embed(description=f"{role.mention} will be given to new members.", color=BOT_COLOR))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def testwelcome(self, ctx):
        g = await db.get_guild(ctx.guild.id)
        msg = g['welcome_message'].replace('{user}', ctx.author.mention)\
            .replace('{server}', ctx.guild.name)\
            .replace('{membercount}', str(ctx.guild.member_count))
        e = discord.Embed(description=msg, color=BOT_COLOR)
        e.set_author(name=f"Welcome to {ctx.guild.name}!", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=e)


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.member and payload.member.bot:
            return
        role_id = await db.get_reaction_role(payload.guild_id, payload.message_id, str(payload.emoji))
        if role_id:
            guild = self.bot.get_guild(payload.guild_id)
            role = guild.get_role(role_id)
            if role:
                try:
                    await payload.member.add_roles(role)
                except:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        role_id = await db.get_reaction_role(payload.guild_id, payload.message_id, str(payload.emoji))
        if role_id:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(role_id)
            if member and role:
                try:
                    await member.remove_roles(role)
                except:
                    pass

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def reactionrole(self, ctx, message_id: int, emoji: str, role: discord.Role):
        await db.add_reaction_role(ctx.guild.id, message_id, emoji, role.id)
        try:
            msg = await ctx.channel.fetch_message(message_id)
            await msg.add_reaction(emoji)
        except:
            pass
        await ctx.send(embed=discord.Embed(description=f"Reaction role set: React {emoji} to get {role.mention}.", color=BOT_COLOR))

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def removereactionrole(self, ctx, message_id: int, emoji: str):
        await db.remove_reaction_role(ctx.guild.id, message_id, emoji)
        await ctx.send(embed=discord.Embed(description=f"Reaction role removed.", color=BOT_COLOR))

    @commands.command()
    async def listreactionroles(self, ctx):
        rrs = await db.get_all_reaction_roles(ctx.guild.id)
        if not rrs:
            return await ctx.send(embed=discord.Embed(description="No reaction roles set.", color=BOT_COLOR))
        desc = "\n".join([f"{r['emoji']} → <@&{r['role_id']}> (Message: {r['message_id']})" for r in rrs])
        await ctx.send(embed=discord.Embed(title="Reaction Roles", description=desc, color=BOT_COLOR))


class CustomCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        g = await db.get_guild(message.guild.id)
        prefix = g.get('prefix', '!')
        if not message.content.startswith(prefix):
            return
        trigger = message.content[len(prefix):].split()[0].lower()
        response = await db.get_custom_command(message.guild.id, trigger)
        if response:
            await message.channel.send(response)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def addcommand(self, ctx, trigger: str, *, response: str):
        await db.add_custom_command(ctx.guild.id, trigger.lower(), response)
        await ctx.send(embed=discord.Embed(description=f"Command `{trigger}` added.", color=BOT_COLOR))

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def removecommand(self, ctx, trigger: str):
        await db.remove_custom_command(ctx.guild.id, trigger.lower())
        await ctx.send(embed=discord.Embed(description=f"Command `{trigger}` removed.", color=BOT_COLOR))

    @commands.command()
    async def listcommands(self, ctx):
        cmds = await db.get_custom_commands(ctx.guild.id)
        if not cmds:
            return await ctx.send(embed=discord.Embed(description="No custom commands yet.", color=BOT_COLOR))
        desc = "\n".join([f"`{c['trigger']}` → {c['response']}" for c in cmds])
        await ctx.send(embed=discord.Embed(title="Custom Commands", description=desc, color=BOT_COLOR))


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_log_channel(self, guild):
        g = await db.get_guild(guild.id)
        if g.get('log_channel'):
            return guild.get_channel(g['log_channel'])
        return None

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content:
            return
        ch = await self.get_log_channel(before.guild)
        if ch:
            e = discord.Embed(title="Message Edited", color=0x3498db, timestamp=datetime.utcnow())
            e.add_field(name="Author", value=before.author.mention, inline=True)
            e.add_field(name="Channel", value=before.channel.mention, inline=True)
            e.add_field(name="Before", value=before.content[:500] or "Empty", inline=False)
            e.add_field(name="After", value=after.content[:500] or "Empty", inline=False)
            await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return
        ch = await self.get_log_channel(message.guild)
        if ch:
            e = discord.Embed(title="Message Deleted", color=0xe74c3c, timestamp=datetime.utcnow())
            e.add_field(name="Author", value=message.author.mention, inline=True)
            e.add_field(name="Channel", value=message.channel.mention, inline=True)
            e.add_field(name="Content", value=message.content[:500] or "Empty", inline=False)
            await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        ch = await self.get_log_channel(guild)
        if ch:
            e = discord.Embed(title="Member Banned", description=f"{user} was banned.", color=0xe74c3c, timestamp=datetime.utcnow())
            await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        ch = await self.get_log_channel(channel.guild)
        if ch:
            e = discord.Embed(title="Channel Created", description=f"{channel.mention} was created.", color=0x2ecc71, timestamp=datetime.utcnow())
            await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        ch = await self.get_log_channel(channel.guild)
        if ch:
            e = discord.Embed(title="Channel Deleted", description=f"#{channel.name} was deleted.", color=0xe74c3c, timestamp=datetime.utcnow())
            await ch.send(embed=e)


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        e = discord.Embed(title="Pong!", description=f"Latency: **{round(self.bot.latency * 1000)}ms**", color=BOT_COLOR)
        await ctx.send(embed=e)

    @commands.command()
    async def serverinfo(self, ctx):
        g = ctx.guild
        e = discord.Embed(title=g.name, color=BOT_COLOR, timestamp=datetime.utcnow())
        e.set_thumbnail(url=g.icon.url if g.icon else None)
        e.add_field(name="Members", value=str(g.member_count), inline=True)
        e.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        e.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        e.add_field(name="Created", value=g.created_at.strftime("%b %d, %Y"), inline=True)
        e.add_field(name="Boost Level", value=str(g.premium_tier), inline=True)
        e.add_field(name="Owner", value=g.owner.mention if g.owner else "Unknown", inline=True)
        await ctx.send(embed=e)

    @commands.command()
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user = await db.get_user(ctx.guild.id, member.id)
        e = discord.Embed(title=str(member), color=BOT_COLOR, timestamp=datetime.utcnow())
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Joined", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown", inline=True)
        e.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"), inline=True)
        e.add_field(name="Level", value=str(user.get('level', 0)), inline=True)
        e.add_field(name="XP", value=f"{user.get('xp', 0):,}", inline=True)
        e.add_field(name="Warnings", value=str(user.get('warnings', 0)), inline=True)
        roles = [r.mention for r in member.roles[1:]]
        e.add_field(name="Roles", value=", ".join(roles[:5]) or "None", inline=False)
        await ctx.send(embed=e)

    @commands.command()
    async def premium(self, ctx):
        is_prem = await db.is_premium(ctx.guild.id)
        if is_prem:
            e = discord.Embed(title="LuxeBot Premium", description="This server has **Premium** unlocked. All features active.", color=BOT_COLOR)
        else:
            e = discord.Embed(title="LuxeBot Premium", color=BOT_COLOR)
            e.description = "Upgrade to unlock all features for **$3/month**.\n\nFree tier includes: Moderation + Welcome\nPremium adds: Leveling, AutoMod, Reaction Roles, Custom Commands, Logging\n\n[Upgrade on Whop.com](https://whop.com) ← add your link here"
        await ctx.send(embed=e)

    @commands.command()
    async def help(self, ctx):
        e = discord.Embed(title="LuxeBot Commands", color=BOT_COLOR, timestamp=datetime.utcnow())
        e.add_field(name="Moderation", value="`ban` `kick` `mute` `unmute` `warn` `warnings` `clearwarnings` `purge` `setprefix` `setlog`", inline=False)
        e.add_field(name="AutoMod", value="`automod [spam/links/caps/badwords/mentions] [on/off]` `addbadword` `removebadword`", inline=False)
        e.add_field(name="Leveling", value="`rank` `leaderboard` `setlevelrole` `setlevelchannel`", inline=False)
        e.add_field(name="Welcome", value="`setwelcome` `setgoodbye` `setjoinrole` `testwelcome`", inline=False)
        e.add_field(name="Reaction Roles", value="`reactionrole` `removereactionrole` `listreactionroles`", inline=False)
        e.add_field(name="Custom Commands", value="`addcommand` `removecommand` `listcommands`", inline=False)
        e.add_field(name="Utility", value="`ping` `serverinfo` `userinfo` `premium` `help`", inline=False)
        e.set_footer(text="LuxeBot — Premium Discord Management")
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Welcome(bot))
    await bot.add_cog(ReactionRoles(bot))
    await bot.add_cog(CustomCommands(bot))
    await bot.add_cog(Logging(bot))
    await bot.add_cog(Utility(bot))
