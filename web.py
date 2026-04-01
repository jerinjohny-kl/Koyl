import aiohttp
from aiohttp import web
import asyncio
from config import Config
import logging

logger = logging.getLogger(__name__)

async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    logger.info(f"Web server started on port {Config.PORT}")

async def ping_server():
    if not Config.PING_URL:
        logger.warning("No PING_URL provided, ping task disabled.")
        return

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(Config.PING_URL) as resp:
                    logger.info(f"Pinged {Config.PING_URL} - Status: {resp.status}")
        except Exception as e:
            logger.error(f"Ping failed: {e}")

        # Ping every 15 minutes
        await asyncio.sleep(15 * 60)

async def start_services():
    asyncio.create_task(start_web_server())
    asyncio.create_task(ping_server())
