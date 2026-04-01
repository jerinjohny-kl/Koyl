from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.users = self.db.users

    async def get_user_prefs(self, user_id):
        user = await self.users.find_one({"_id": user_id})
        if not user:
            # Default preferences
            return {
                "_id": user_id,
                "output_type": "document", # 'document' or 'media'
                "thumbnail_id": None,      # telegram file id
                "regex_pattern": "",       # search pattern
                "regex_replace": "",       # replace string
                "caption_format": "<code>{filename}</code>\n\nDuration: {duration}\nAudio: {audio}\nSubtitles: {subtitle}"
            }
        return user

    async def update_user_pref(self, user_id, key, value):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {key: value}},
            upsert=True
        )

# Initialize database instance
db = Database(Config.MONGO_URI, Config.MONGO_DB_NAME)
