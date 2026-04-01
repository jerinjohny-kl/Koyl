from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply

from config import Config
from db import db

# Authorization filter
def auth_filter(_, __, message):
    if not Config.ADMIN_IDS:
        return True
    return message.from_user and message.from_user.id in Config.ADMIN_IDS

auth = filters.create(auth_filter)

@Client.on_message(filters.command("start") & auth)
async def start_cmd(client, message):
    await message.reply_text("Hello! I am a download bot. Send /help for more info.")

@Client.on_message(filters.command("help") & auth)
async def help_cmd(client, message):
    text = """
    **Commands:**
    /start - Start the bot
    /help - Show this help message
    /settings - Open user settings
    /l <link> [-n new_name.ext] - Download a link (torrent or direct)

    You can also send a photo to set it as a custom thumbnail.
    """
    await message.reply_text(text)

@Client.on_message(filters.photo & auth)
async def save_thumbnail(client, message):
    user_id = message.from_user.id
    photo = message.photo
    file_id = photo.file_id
    await db.update_user_pref(user_id, "thumbnail_id", file_id)
    await message.reply_text("Thumbnail saved successfully!")
