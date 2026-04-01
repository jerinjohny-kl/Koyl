import asyncio
import os
import time
import logging
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified

from config import Config
from db import db
from utils import get_media_info, apply_regex, generate_caption, format_bytes, get_progress_bar, take_screenshot
from downloader import DownloadManager

from plugins.commands import auth

logger = logging.getLogger(__name__)

download_manager = DownloadManager()

async def progress_for_pyrogram(current, total, ud_type, message, start_time):
    # Store last update time in message obj to avoid global state issues
    now = time.time()
    if not hasattr(message, "_last_update_time"):
        message._last_update_time = 0

    diff = now - start_time
    # Update every 10 seconds or if it's finished
    if (now - message._last_update_time > 10.0) or (current == total):
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

@Client.on_message(filters.command("l") & auth)
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
