import aiosqlite
from datetime import datetime, timedelta

DB_PATH = "luxebot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '!',
                log_channel INTEGER,
                welcome_channel INTEGER,
                welcome_message TEXT,
                goodbye_message TEXT,
                mute_role INTEGER,
                autorole INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                reason TEXT,
                moderator_id INTEGER,
                timestamp TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_settings (
                guild_id INTEGER PRIMARY KEY,
                anti_spam INTEGER DEFAULT 0,
                anti_caps INTEGER DEFAULT 0,
                anti_links INTEGER DEFAULT 0,
                anti_mentions INTEGER DEFAULT 0,
                anti_raid INTEGER DEFAULT 0,
                spam_threshold INTEGER DEFAULT 5,
                caps_threshold INTEGER DEFAULT 70,
                mention_threshold INTEGER DEFAULT 5
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS levels (
                guild_id INTEGER,
                user_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
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
                command TEXT,
                response TEXT,
                PRIMARY KEY (guild_id, command)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_triggers (
                guild_id INTEGER,
                trigger TEXT,
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xp_cooldowns (
                guild_id INTEGER,
                user_id INTEGER,
                last_xp TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()


async def get_prefix(guild_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT prefix FROM guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "!"


async def ensure_guild(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO guilds (guild_id) VALUES (?)", (guild_id,))
        await db.execute("INSERT OR IGNORE INTO automod_settings (guild_id) VALUES (?)", (guild_id,))
        await db.commit()


async def get_guild_settings(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone()


async def update_guild_setting(guild_id: int, setting: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE guilds SET {setting} = ? WHERE guild_id = ?", (value, guild_id))
        await db.commit()


async def add_warning(guild_id: int, user_id: int, reason: str, moderator_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO warnings (guild_id, user_id, reason, moderator_id, timestamp) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, reason, moderator_id, datetime.utcnow().isoformat())
        )
        await db.commit()


async def get_warnings(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cursor:
            return await cursor.fetchall()


async def clear_warnings(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await db.commit()


async def get_automod_settings(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM automod_settings WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone()


async def update_automod_setting(guild_id: int, setting: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE automod_settings SET {setting} = ? WHERE guild_id = ?", (value, guild_id))
        await db.commit()


async def get_xp(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xp, level FROM levels WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row if row else (0, 0)


async def add_xp(guild_id: int, user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO levels (guild_id, user_id, xp, level) VALUES (?, ?, 0, 0)",
            (guild_id, user_id)
        )
        await db.execute(
            "UPDATE levels SET xp = xp + ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id)
        )
        await db.commit()


async def set_level(guild_id: int, user_id: int, level: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE levels SET level = ? WHERE guild_id = ? AND user_id = ?",
            (level, guild_id, user_id)
        )
        await db.commit()


async def get_leaderboard(guild_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, xp, level FROM levels WHERE guild_id = ? ORDER BY xp DESC LIMIT ?",
            (guild_id, limit)
        ) as cursor:
            return await cursor.fetchall()


async def get_level_roles(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level",
            (guild_id,)
        ) as cursor:
            return await cursor.fetchall()


async def add_level_role(guild_id: int, level: int, role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
            (guild_id, level, role_id)
        )
        await db.commit()


async def add_reaction_role(guild_id: int, message_id: int, emoji: str, role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
            (guild_id, message_id, emoji, role_id)
        )
        await db.commit()


async def get_reaction_role(guild_id: int, message_id: int, emoji: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
            (guild_id, message_id, emoji)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def add_custom_command(guild_id: int, command: str, response: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO custom_commands (guild_id, command, response) VALUES (?, ?, ?)",
            (guild_id, command, response)
        )
        await db.commit()


async def get_custom_command(guild_id: int, command: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT response FROM custom_commands WHERE guild_id = ? AND command = ?",
            (guild_id, command)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def add_badword(guild_id: int, word: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO badwords (guild_id, word) VALUES (?, ?)",
            (guild_id, word.lower())
        )
        await db.commit()


async def get_badwords(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT word FROM badwords WHERE guild_id = ?", (guild_id,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def remove_badword(guild_id: int, word: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM badwords WHERE guild_id = ? AND word = ?",
            (guild_id, word.lower())
        )
        await db.commit()


async def is_premium(guild_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT expires_at, trial_expires_at FROM premium_servers WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            expires_at, trial_expires_at = row
            now = datetime.utcnow().isoformat()
            if expires_at and expires_at > now:
                return True
            if trial_expires_at and trial_expires_at > now:
                return True
            return False


async def add_premium(guild_id: int, days: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if days:
            expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
        else:
            expires = "9999-12-31"
        await db.execute(
            "INSERT OR REPLACE INTO premium_servers (guild_id, expires_at) VALUES (?, ?)",
            (guild_id, expires)
        )
        await db.commit()


async def add_trial(guild_id: int, days: int = 7):
    trial_expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO premium_servers (guild_id, trial_expires_at) VALUES (?, ?)",
            (guild_id, trial_expires)
        )
        await db.commit()


async def remove_premium(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM premium_servers WHERE guild_id = ?", (guild_id,))
        await db.commit()


async def get_expired_trials():
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT guild_id FROM premium_servers
               WHERE (expires_at IS NULL OR expires_at < ?)
               AND trial_expires_at IS NOT NULL
               AND trial_expires_at < ?""",
            (now, now)
        ) as cursor:
            return await cursor.fetchall()


async def get_xp_cooldown(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_xp FROM xp_cooldowns WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_xp_cooldown(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO xp_cooldowns (guild_id, user_id, last_xp) VALUES (?, ?, ?)",
            (guild_id, user_id, datetime.utcnow().isoformat())
        )
        await db.commit()
