import json
import logging

import redis.asyncio as redis

from core.config import REDIS_URL

logger = logging.getLogger(__name__)

_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(REDIS_URL, decode_responses=True)
    return _pool


async def get_prices(origin_iata: str) -> list[dict] | None:
    r = await get_redis()
    key = f"prices:{origin_iata}"
    data = await r.get(key)
    if data is None:
        return None
    return json.loads(data)


async def set_prices(origin_iata: str, data: list[dict]) -> None:
    r = await get_redis()
    key = f"prices:{origin_iata}"
    await r.set(key, json.dumps(data, ensure_ascii=False), ex=1800)


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
