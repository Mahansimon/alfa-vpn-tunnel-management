"""تست محدودیت نرخ."""
from __future__ import annotations

import pytest

from app.core.errors import RateLimited
from app.core.ratelimit import check, parse_limit, reset


def test_parse_limit():
    assert parse_limit("10/5m") == (10, 300)
    assert parse_limit("300/1m") == (300, 60)
    assert parse_limit("5/1h") == (5, 3600)


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold():
    await reset("test-key")
    for _ in range(3):
        await check("test-key", "3/1m")
    with pytest.raises(RateLimited):
        await check("test-key", "3/1m")
    await reset("test-key")
    await check("test-key", "3/1m")
