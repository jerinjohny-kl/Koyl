import asyncio
import os
import aiohttp
import logging
from utils import format_bytes, get_progress_bar
from config import Config
from pyrogram.errors import MessageNotModified
import time
import json
from qbittorrentapi import Client

logger = logging.getLogger(__name__)

class Aria2Downloader:
    def __init__(self, rpc_url="http://localhost:6800/jsonrpc"):
        self.rpc_url = rpc_url
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _rpc_call(self, method, params=None):
        payload = {
            "jsonrpc": "2.0",
            "id": "qwer",
            "method": method,
            "params": params or []
        }
        async with self.session.post(self.rpc_url, json=payload) as response:
            result = await response.json()
            return result.get("result")

    async def add_uri(self, uri, dir_path):
        return await self._rpc_call("aria2.addUri", [[uri], {"dir": dir_path}])

    async def get_status(self, gid):
        return await self._rpc_call("aria2.tellStatus", [gid])

    async def get_files(self, gid):
        return await self._rpc_call("aria2.getFiles", [gid])

    async def remove(self, gid):
        return await self._rpc_call("aria2.remove", [gid])

    async def close(self):
        if self._session:
            await self._session.close()

class QbitDownloader:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = Client(host='localhost:8080')
            self._client.auth_log_in()
        return self._client

    async def add_torrent(self, torrent_url, save_path):
        res = self.client.torrents_add(urls=torrent_url, save_path=save_path)
        # return first matched torrent hash in a sec (simplistic)
        await asyncio.sleep(2)
        torrents = self.client.torrents_info()
        # Find the latest added torrent
        if torrents:
            torrents = sorted(torrents, key=lambda x: x.added_on, reverse=True)
            return torrents[0].hash
        return None

    def get_status(self, hash_str):
        torrents = self.client.torrents_info(torrent_hashes=hash_str)
        if torrents:
            return torrents[0]
        return None

    def get_files(self, hash_str):
        return self.client.torrents_files(torrent_hash=hash_str)

class DownloadManager:
    def __init__(self):
        self.aria2 = Aria2Downloader()
        self.qbit = QbitDownloader()

    async def download(self, link, message, edit_interval=5):
        is_torrent = link.endswith('.torrent') or link.startswith('magnet:')
        download_dir = os.path.join(Config.DOWNLOAD_DIR, str(time.time()).replace('.', ''))
        os.makedirs(download_dir, exist_ok=True)

        last_edit = 0
        file_path = None

        if is_torrent:
            torrent_hash = await self.qbit.add_torrent(link, download_dir)
            if not torrent_hash:
                await message.edit_text("Failed to add torrent.")
                return None

            while True:
                status = self.qbit.get_status(torrent_hash)
                if not status:
                    break

                state = status.state
                progress = status.progress * 100
                dl_speed = format_bytes(status.dlspeed) + "/s"
                size = format_bytes(status.total_size)
                downloaded = format_bytes(status.completed)

                if time.time() - last_edit > edit_interval:
                    try:
                        bar = get_progress_bar(progress)
                        text = f"**Downloading Torrent:**\n{status.name}\n{bar} {progress:.2f}%\n"
                        text += f"**Size:** {size}\n**Downloaded:** {downloaded}\n**Speed:** {dl_speed}\n**State:** {state}"
                        await message.edit_text(text)
                        last_edit = time.time()
                    except MessageNotModified:
                        pass

                if state in ['error', 'missingFiles']:
                    await message.edit_text("Torrent download error.")
                    return None

                if progress >= 100:
                    break

                await asyncio.sleep(2)

            # get file path
            files = self.qbit.get_files(torrent_hash)
            if files:
                # Assuming single file for simplicity, or return directory if multiple
                if len(files) == 1:
                    file_path = os.path.join(download_dir, files[0].name)
                else:
                    file_path = download_dir # return dir for multifile

            await message.edit_text("Download completed! Processing...")
            return file_path

        else:
            gid = await self.aria2.add_uri(link, download_dir)
            if not gid:
                await message.edit_text("Failed to add direct link to Aria2.")
                return None

            while True:
                status = await self.aria2.get_status(gid)
                if not status:
                    break

                state = status.get('status')
                total_length = int(status.get('totalLength', 0))
                completed_length = int(status.get('completedLength', 0))
                download_speed = int(status.get('downloadSpeed', 0))

                if total_length > 0:
                    progress = (completed_length / total_length) * 100
                else:
                    progress = 0

                dl_speed = format_bytes(download_speed) + "/s"
                size = format_bytes(total_length)
                downloaded = format_bytes(completed_length)

                if time.time() - last_edit > edit_interval:
                    try:
                        bar = get_progress_bar(progress)
                        text = f"**Downloading Link:**\n{bar} {progress:.2f}%\n"
                        text += f"**Size:** {size}\n**Downloaded:** {downloaded}\n**Speed:** {dl_speed}\n**State:** {state}"
                        await message.edit_text(text)
                        last_edit = time.time()
                    except MessageNotModified:
                        pass

                if state == 'error':
                    await message.edit_text("Download error.")
                    return None

                if state == 'complete':
                    break

                await asyncio.sleep(2)

            files = await self.aria2.get_files(gid)
            if files and len(files) > 0 and 'path' in files[0]:
                file_path = files[0]['path']

            await message.edit_text("Download completed! Processing...")
            return file_path
