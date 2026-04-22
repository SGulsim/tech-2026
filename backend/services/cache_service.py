from typing import Optional

import redis.asyncio as aioredis

from core.logging import get_logger

logger = get_logger(__name__)

_BROWSE_KEY = "browse:{user_id}"
_BROWSE_TTL = 3600
_REFILL_THRESHOLD = 3


class CacheService:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _key(self, user_id: int) -> str:
        return _BROWSE_KEY.format(user_id=user_id)

    async def get_next_profile_id(self, user_id: int) -> Optional[int]:
        val = await self.redis.lpop(self._key(user_id))
        return int(val) if val is not None else None

    async def queue_size(self, user_id: int) -> int:
        return await self.redis.llen(self._key(user_id))

    async def needs_refill(self, user_id: int) -> bool:
        return (await self.queue_size(user_id)) < _REFILL_THRESHOLD

    async def fill_queue(self, user_id: int, profile_ids: list[int]) -> None:
        if not profile_ids:
            return
        key = self._key(user_id)
        pipe = self.redis.pipeline()
        for pid in profile_ids:
            pipe.rpush(key, pid)
        pipe.expire(key, _BROWSE_TTL)
        await pipe.execute()
        logger.info("browse_cache_filled", user_id=user_id, count=len(profile_ids))

    async def clear_queue(self, user_id: int) -> None:
        await self.redis.delete(self._key(user_id))
        logger.info("browse_cache_cleared", user_id=user_id)
