import aiosqlite
import asyncio

DB_PATH = "luxebot.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '!',
                welcome_channel INTEGER,
                welcome_message TEXT DEFAULT 'Welcome {user} to {server}! You are member #{membercount}.',
                goodbye_channel INTEGER,
                goodbye_message TEXT DEFAULT 'Goodbye {user}, we will miss you!',
                log_channel INTEGER,
                join_role INTEGER,
                automod_spam INTEGER DEFAULT 1,
                automod_links INTEGER DEFAULT 0,
                automod_caps INTEGER DEFAULT 1,
                automod_badwords INTEGER DEFAULT 1,
                automod_mentions INTEGER DEFAULT 1,
                level_channel INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER,
                user_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS level_roles (
                guild_id INTEGER,
                level INTEGER,
                role_id INTEGER,
                PRIMARY KEY (guild_id, level)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id INTEGER,
                message_id INTEGER,
                emoji TEXT,
                role_id INTEGER,
                PRIMARY KEY (guild_id, message_id, emoji)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS custom_commands (
                guild_id INTEGER,
                trigger TEXT,
                response TEXT,
                PRIMARY KEY (guild_id, trigger)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mod_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                action TEXT,
                moderator_id INTEGER,
                target_id INTEGER,
                reason TEXT,
                timestamp TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS badwords (
                guild_id INTEGER,
                word TEXT,
                PRIMARY KEY (guild_id, word)
            )
        """)
	await db.execute("""
            CREATE TABLE IF NOT EXISTS premium_servers (
                guild_id INTEGER PRIMARY KEY,
                expires_at TEXT,
                trial_expires_at TEXT
            )
        """)           



async def get_prefix(guild_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT prefix FROM guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "!"

async def ensure_guild(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,))
        await db.commit()

async def get_guild(guild_id: int) -> dict:
    await ensure_guild(guild_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {}

async def set_guild(guild_id: int, **kwargs):
    await ensure_guild(guild_id)
    for key, value in kwargs.items():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"UPDATE guilds SET {key} = ? WHERE guild_id = ?", (value, guild_id))
            await db.commit()

async def get_user(guild_id: int, user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {}

async def add_xp(guild_id: int, user_id: int, xp: int) -> tuple:
    import math
    user = await get_user(guild_id, user_id)
    new_xp = user['xp'] + xp
    new_level = math.floor(0.1 * math.sqrt(new_xp))
    leveled_up = new_level > user['level']
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?",
                         (new_xp, new_level, guild_id, user_id))
        await db.commit()
    return new_level, leveled_up

async def add_warning(guild_id: int, user_id: int) -> int:
    user = await get_user(guild_id, user_id)
    new_warnings = user['warnings'] + 1
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET warnings = ? WHERE guild_id = ? AND user_id = ?",
                         (new_warnings, guild_id, user_id))
        await db.commit()
    return new_warnings

async def clear_warnings(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET warnings = 0 WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await db.commit()

async def get_leaderboard(guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT 10", (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def add_reaction_role(guild_id: int, message_id: int, emoji: str, role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO reaction_roles VALUES (?, ?, ?, ?)",
                         (guild_id, message_id, emoji, role_id))
        await db.commit()

async def get_reaction_role(guild_id: int, message_id: int, emoji: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
            (guild_id, message_id, emoji)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def get_all_reaction_roles(guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM reaction_roles WHERE guild_id = ?", (guild_id,)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def remove_reaction_role(guild_id: int, message_id: int, emoji: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
                         (guild_id, message_id, emoji))
        await db.commit()

async def add_custom_command(guild_id: int, trigger: str, response: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO custom_commands VALUES (?, ?, ?)", (guild_id, trigger, response))
        await db.commit()

async def remove_custom_command(guild_id: int, trigger: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM custom_commands WHERE guild_id = ? AND trigger = ?", (guild_id, trigger))
        await db.commit()

async def get_custom_commands(guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM custom_commands WHERE guild_id = ?", (guild_id,)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def get_custom_command(guild_id: int, trigger: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT response FROM custom_commands WHERE guild_id = ? AND trigger = ?",
                              (guild_id, trigger)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def add_badword(guild_id: int, word: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO badwords VALUES (?, ?)", (guild_id, word.lower()))
        await db.commit()

async def remove_badword(guild_id: int, word: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM badwords WHERE guild_id = ? AND word = ?", (guild_id, word.lower()))
        await db.commit()

async def get_badwords(guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT word FROM badwords WHERE guild_id = ?", (guild_id,)) as cursor:
            return [r[0] for r in await cursor.fetchall()]

async def log_mod_action(guild_id: int, action: str, moderator_id: int, target_id: int, reason: str):
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO mod_logs (guild_id, action, moderator_id, target_id, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, action, moderator_id, target_id, reason, datetime.utcnow().isoformat())
        )
        await db.commit()

async def is_premium(guild_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT guild_id FROM premium_servers WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone() is not None

async def set_level_role(guild_id: int, level: int, role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO level_roles VALUES (?, ?, ?)", (guild_id, level, role_id))
        await db.commit()

async def get_level_role(guild_id: int, level: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT role_id FROM level_roles WHERE guild_id = ? AND level = ?",
                              (guild_id, level)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
