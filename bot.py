import asyncio
import logging
from pyrogram import Client

from config import Config
from web import start_services

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client(
    "telegram_bot",
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    plugins=dict(root="plugins")
)

if __name__ == "__main__":
    app.start()
    asyncio.get_event_loop().run_until_complete(start_services())
    app.stop()
    app.run()
