import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
BOT_COLOR = 0xC9A84C
DB_PATH = "luxebot.db"
