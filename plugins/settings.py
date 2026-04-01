from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply

from config import Config
from db import db
from plugins.commands import auth

@Client.on_message(filters.command("settings") & auth)
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

@Client.on_callback_query(auth)
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

@Client.on_message(filters.reply & auth)
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
