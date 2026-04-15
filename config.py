import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DASHBOARD_SECRET = os.getenv("DASHBOARD_SECRET", "changeme")
DEFAULT_PREFIX = "!"
BOT_COLOR = 0xC9A84C
BOT_VERSION = "1.0.0"
