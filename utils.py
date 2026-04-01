import math

def format_bytes(size):
    size = int(size)
    if not size:
        return "0 B"
    power = 1024
    n = 0
    power_labels = ["B", "KB", "MB", "GB", "TB"]
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

def get_progress_bar(percentage):
    # progress bar in blocks like ██████░░░░
    blocks = 10
    filled = int(round(blocks * percentage / 100.0))
    empty = blocks - filled
    return "█" * filled + "░" * empty

import re
import asyncio
import os
import json
import logging

logger = logging.getLogger(__name__)

async def get_media_info(file_path):
    """Uses ffprobe to extract video duration, audio, and subtitle languages."""
    info = {"duration": "Unknown", "audio": "Unknown", "subtitle": "None"}

    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,tags:stream_tags=language",
            "-of", "json", file_path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        data = json.loads(stdout.decode('utf-8'))

        if 'format' in data and 'duration' in data['format']:
            duration_sec = float(data['format']['duration'])
            # Convert to hh:mm:ss
            td = int(duration_sec)
            m, s = divmod(td, 60)
            h, m = divmod(m, 60)
            if h > 0:
                info["duration"] = f"{h:02d}:{m:02d}:{s:02d}"
            else:
                info["duration"] = f"{m:02d}:{s:02d}"

        audios = []
        subtitles = []

        if 'streams' in data:
            for stream in data['streams']:
                codec_type = stream.get('codec_type')
                lang = stream.get('tags', {}).get('language', 'Unknown')
                if codec_type == 'audio':
                    audios.append(lang)
                elif codec_type == 'subtitle':
                    subtitles.append(lang)

        if audios:
            info["audio"] = ", ".join(list(set(audios)))
        if subtitles:
            info["subtitle"] = ", ".join(list(set(subtitles)))

    except Exception as e:
        logger.error(f"Error getting media info for {file_path}: {e}")

    return info

def apply_regex(filename, pattern, replace):
    if not pattern:
        return filename
    try:
        new_name = re.sub(pattern, replace, filename)
        return new_name
    except re.error:
        return filename

def generate_caption(format_str, filename, media_info):
    try:
        caption = format_str.format(
            filename=filename,
            duration=media_info.get("duration", "Unknown"),
            audio=media_info.get("audio", "Unknown"),
            subtitle=media_info.get("subtitle", "None")
        )
        return caption
    except Exception as e:
        logger.error(f"Error formatting caption: {e}")
        return filename

async def take_screenshot(video_file, output_path):
    # take screenshot at 15% of video
    try:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", "00:00:05", "-i", video_file,
            "-vframes", "1", "-q:v", "2", output_path
        ]
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.communicate()
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.error(f"Error generating screenshot: {e}")
    return None
