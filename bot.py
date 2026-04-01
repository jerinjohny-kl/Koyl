import asyncio
import os
import time
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply
from pyrogram.errors import MessageNotModified

from config import Config
from db import db
from utils import get_media_info, apply_regex, generate_caption, format_bytes, get_progress_bar, take_screenshot
from downloader import DownloadManager
from web import start_services

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client(
    "telegram_bot",
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH
)

download_manager = DownloadManager()

# Authorization filter
def auth_filter(_, __, message):
    if not Config.ADMIN_IDS:
        return True
    return message.from_user and message.from_user.id in Config.ADMIN_IDS

auth = filters.create(auth_filter)

@app.on_message(filters.command("start") & auth)
async def start_cmd(client, message):
    await message.reply_text("Hello! I am a download bot. Send /help for more info.")

@app.on_message(filters.command("help") & auth)
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

@app.on_message(filters.photo & auth)
async def save_thumbnail(client, message):
    user_id = message.from_user.id
    photo = message.photo
    file_id = photo.file_id
    await db.update_user_pref(user_id, "thumbnail_id", file_id)
    await message.reply_text("Thumbnail saved successfully!")

@app.on_message(filters.command("settings") & auth)
async def settings_cmd(client, message):
    user_id = message.from_user.id
    prefs = await db.get_user_prefs(user_id)

    out_type = prefs.get("output_type", "document")
    thumb = "Set" if prefs.get("thumbnail_id") else "None"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Output: {out_type.capitalize()}", callback_data="toggle_output")],
        [InlineKeyboardButton(f"Thumbnail: {thumb}", callback_data="clear_thumb")],
        [InlineKeyboardButton("Set Regex Pattern", callback_data="set_regex")],
        [InlineKeyboardButton("Set Caption Format", callback_data="set_caption")]
    ])

    await message.reply_text("Settings:", reply_markup=keyboard)

@app.on_callback_query(auth)
async def cb_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data
    prefs = await db.get_user_prefs(user_id)

    if data == "toggle_output":
        new_type = "media" if prefs.get("output_type") == "document" else "document"
        await db.update_user_pref(user_id, "output_type", new_type)
        prefs["output_type"] = new_type

        out_type = prefs.get("output_type", "document")
        thumb = "Set" if prefs.get("thumbnail_id") else "None"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Output: {out_type.capitalize()}", callback_data="toggle_output")],
            [InlineKeyboardButton(f"Thumbnail: {thumb}", callback_data="clear_thumb")],
            [InlineKeyboardButton("Set Regex Pattern", callback_data="set_regex")],
            [InlineKeyboardButton("Set Caption Format", callback_data="set_caption")]
        ])
        await query.message.edit_reply_markup(reply_markup=keyboard)
        await query.answer("Output type toggled.")

    elif data == "clear_thumb":
        await db.update_user_pref(user_id, "thumbnail_id", None)
        prefs["thumbnail_id"] = None

        out_type = prefs.get("output_type", "document")
        thumb = "None"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Output: {out_type.capitalize()}", callback_data="toggle_output")],
            [InlineKeyboardButton(f"Thumbnail: {thumb}", callback_data="clear_thumb")],
            [InlineKeyboardButton("Set Regex Pattern", callback_data="set_regex")],
            [InlineKeyboardButton("Set Caption Format", callback_data="set_caption")]
        ])
        await query.message.edit_reply_markup(reply_markup=keyboard)
        await query.answer("Thumbnail cleared.")

    elif data == "set_regex":
        await query.message.reply_text("Please reply to this message with your regex pattern and replace string separated by |.\nExample: `pattern|replace`", reply_markup=ForceReply(selective=True))
        await query.answer()

    elif data == "set_caption":
        await query.message.reply_text("Please reply to this message with your HTML caption format.\nAvailable vars: {filename}, {duration}, {audio}, {subtitle}", reply_markup=ForceReply(selective=True))
        await query.answer()

@app.on_message(filters.reply & auth)
async def reply_handler(client, message):
    if not message.reply_to_message:
        return

    if not message.reply_to_message.reply_markup:
        return

    user_id = message.from_user.id
    text = message.text

    if "regex pattern" in message.reply_to_message.text.lower():
        parts = text.split("|")
        if len(parts) == 2:
            await db.update_user_pref(user_id, "regex_pattern", parts[0])
            await db.update_user_pref(user_id, "regex_replace", parts[1])
            await message.reply_text("Regex pattern and replace string updated.")
        else:
            await message.reply_text("Invalid format. Use `pattern|replace`.")

    elif "caption format" in message.reply_to_message.text.lower():
        await db.update_user_pref(user_id, "caption_format", text)
        await message.reply_text("Caption format updated.")

async def progress_for_pyrogram(current, total, ud_type, message, start_time):
    # Store last update time in message obj to avoid global state issues
    now = time.time()
    if not hasattr(message, "_last_update_time"):
        message._last_update_time = 0

    diff = now - start_time
    # Update every 5 seconds or if it's finished
    if (now - message._last_update_time > 5.0) or (current == total):
        message._last_update_time = now
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        time_to_completion = round((total - current) / speed) * 1000 if speed > 0 else 0
        progress_str = f"**{ud_type}**\n{get_progress_bar(percentage)} {percentage:.2f}%\n"
        progress_str += f"**Size:** {format_bytes(total)}\n"
        progress_str += f"**Uploaded:** {format_bytes(current)}\n"
        progress_str += f"**Speed:** {format_bytes(speed)}/s\n"
        try:
            await message.edit_text(progress_str)
        except MessageNotModified:
            pass

@app.on_message(filters.command("l") & auth)
async def download_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Provide a link. Usage: `/l <link> [-n new_name.ext]`")
        return

    text_content = args[1]

    link = text_content
    new_name = None

    if " -n " in text_content:
        parts = text_content.split(" -n ")
        link = parts[0]
        if len(parts) > 1:
            new_name = parts[1].strip()

    user_id = message.from_user.id
    prefs = await db.get_user_prefs(user_id)

    msg = await message.reply_text("Adding to download queue...")

    try:
        file_path = await download_manager.download(link, msg)
    except Exception as e:
        logger.error(f"Download failed: {e}")
        await msg.edit_text(f"Download failed: {e}")
        return

    if not file_path:
        return

    # Process multiple files if directory
    files_to_upload = []
    if os.path.isdir(file_path):
        for root, _, files in os.walk(file_path):
            for file in files:
                files_to_upload.append(os.path.join(root, file))
    else:
        files_to_upload.append(file_path)

    for file_to_upload in files_to_upload:
        await upload_file(client, msg, file_to_upload, user_id, prefs, new_name, msg.id)

async def upload_file(client, message, file_path, user_id, prefs, custom_name=None, message_id=None):
    original_filename = os.path.basename(file_path)

    # 1. Custom Name (-n)
    if custom_name:
        filename = custom_name
    else:
        filename = original_filename

    # 2. Apply Regex
    regex_pattern = prefs.get("regex_pattern")
    regex_replace = prefs.get("regex_replace")
    if regex_pattern:
        filename = apply_regex(filename, regex_pattern, regex_replace)

    # Check if we need to rename physically
    if filename != original_filename:
        new_file_path = os.path.join(os.path.dirname(file_path), filename)
        os.rename(file_path, new_file_path)
        file_path = new_file_path

    # Get Media Info
    media_info = await get_media_info(file_path)

    # Generate Caption
    caption_format = prefs.get("caption_format")
    caption = generate_caption(caption_format, filename, media_info)

    # Thumbnail
    thumb_path = None
    thumb_id = prefs.get("thumbnail_id")
    unique_suffix = f"{user_id}_{message_id}" if message_id else user_id
    if thumb_id:
        thumb_path = await client.download_media(thumb_id, file_name=f"thumb_{unique_suffix}.jpg")
    else:
        # Default fallback screenshot for video
        if file_path.endswith(('.mp4', '.mkv', '.avi')):
            thumb_path = await take_screenshot(file_path, f"screenshot_{unique_suffix}.jpg")

    output_type = prefs.get("output_type", "document")

    start_time = time.time()

    try:
        if output_type == "media" and file_path.endswith(('.mp4', '.mkv', '.avi')):
            duration_str = media_info.get("duration", "00:00:00")
            h, m, s = map(int, duration_str.split(':')) if ':' in duration_str else (0, 0, 0)
            duration_sec = h * 3600 + m * 60 + s

            await client.send_video(
                chat_id=message.chat.id,
                video=file_path,
                caption=caption,
                thumb=thumb_path,
                duration=duration_sec,
                supports_streaming=True,
                progress=progress_for_pyrogram,
                progress_args=("Uploading Video", message, start_time)
            )
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=file_path,
                caption=caption,
                thumb=thumb_path,
                progress=progress_for_pyrogram,
                progress_args=("Uploading Document", message, start_time)
            )
        await message.delete()
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        await message.edit_text(f"Upload failed: {e}")
    finally:
        # cleanup thumb
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        # cleanup file
        if os.path.exists(file_path):
            os.remove(file_path)


if __name__ == "__main__":
    app.start()
    asyncio.get_event_loop().run_until_complete(start_services())
    app.stop()
    app.run()
