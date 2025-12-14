import redis.asyncio as redis
import json
from app.config import settings
from typing import Optional, Any

class RedisClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        try:
            self.client = redis.from_url(
                settings.REDIS_URL,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                encoding="utf-8",
                decode_responses=True
            )
            print("✅ Redis connection established")
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            self.client = None
    
    async def get(self, key: str) -> Optional[str]:
        if not self.client:
            return None
        try:
            return await self.client.get(key)
        except Exception:
            return None
    
    async def setex(self, key: str, ttl: int, value: Any) -> bool:
        if not self.client:
            return False
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            await self.client.setex(key, ttl, value)
            return True
        except Exception:
            return False
    
    async def delete(self, *keys) -> int:
        if not self.client:
            return 0
        try:
            return await self.client.delete(*keys)
        except Exception:
            return 0
    
    async def exists(self, key: str) -> bool:
        if not self.client:
            return False
        try:
            return await self.client.exists(key) > 0
        except Exception:
            return False
    
    async def incr(self, key: str) -> int:
        if not self.client:
            return 0
        try:
            return await self.client.incr(key)
        except Exception:
            return 0
    
    async def expire(self, key: str, ttl: int) -> bool:
        if not self.client:
            return False
        try:
            return await self.client.expire(key, ttl)
        except Exception:
            return False
    
    async def lpush(self, key: str, *values) -> int:
        if not self.client:
            return 0
        try:
            return await self.client.lpush(key, *values)
        except Exception:
            return 0
    
    async def ltrim(self, key: str, start: int, end: int) -> bool:
        if not self.client:
            return False
        try:
            await self.client.ltrim(key, start, end)
            return True
        except Exception:
            return False

# Create singleton instance
redis_client = RedisClient()