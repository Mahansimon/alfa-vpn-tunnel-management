"""Rate limiting سبک با Redis و fallback حافظه محلی."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import RateLimited

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_memory: dict[str, deque[float]] = defaultdict(deque)
_redis_client = None


def parse_limit(spec: str) -> tuple[int, int]:
    """«10/5m» → (10, 300)"""
    count, _, window = spec.partition("/")
    window = window.strip() or "1m"
    unit = window[-1]
    amount = int(window[:-1] or 1)
    return int(count), amount * _UNITS.get(unit, 60)


async def _redis():
    global _redis_client
    if not settings.REDIS_ENABLED:
        return None
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis

            _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await _redis_client.ping()
        except Exception:
            _redis_client = False
    return _redis_client or None


async def check(key: str, spec: str) -> None:
    """اگر سقف رد شود، خطای 429 پرتاب می‌شود."""
    limit, window = parse_limit(spec)
    client = await _redis()
    if client:
        try:
            bucket = f"rl:{key}:{int(time.time() // window)}"
            current = await client.incr(bucket)
            if current == 1:
                await client.expire(bucket, window)
            if current > limit:
                raise RateLimited()
            return
        except RateLimited:
            raise
        except Exception:
            pass  # افت به حالت حافظه محلی
    now = time.time()
    hits = _memory[key]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= limit:
        raise RateLimited()
    hits.append(now)


async def reset(key: str) -> None:
    _memory.pop(key, None)
    client = await _redis()
    if client:
        try:
            async for k in client.scan_iter(f"rl:{key}:*"):
                await client.delete(k)
        except Exception:
            pass
