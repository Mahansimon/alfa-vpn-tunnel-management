"""حساب‌داری ترافیک: ثبت delta شمارنده‌ها در باکت‌های ساعتی و گزارش بازه‌ای."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.monitoring import TrafficRecord

UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def human_bytes(value: int | float, digits: int = 2) -> str:
    size = float(value or 0)
    idx = 0
    while size >= 1024 and idx < len(UNITS) - 1:
        size /= 1024
        idx += 1
    return f"{round(size, digits)} {UNITS[idx]}"


def hour_bucket(ts: datetime | None = None) -> datetime:
    ts = ts or datetime.now(timezone.utc)
    return ts.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def day_bucket(ts: datetime | None = None) -> datetime:
    return hour_bucket(ts).replace(hour=0)


async def add_usage(
    db: AsyncSession, scope: str, scope_id: str, bytes_rx: int, bytes_tx: int, ts: datetime | None = None
) -> None:
    """افزودن مصرف به باکت ساعتی و روزانه. مقادیر منفی نادیده گرفته می‌شوند."""
    if bytes_rx <= 0 and bytes_tx <= 0:
        return
    for period, bucket in (("hour", hour_bucket(ts)), ("day", day_bucket(ts))):
        row = (
            await db.execute(
                select(TrafficRecord).where(
                    TrafficRecord.scope == scope,
                    TrafficRecord.scope_id == scope_id,
                    TrafficRecord.period == period,
                    TrafficRecord.bucket == bucket,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(
                TrafficRecord(
                    scope=scope,
                    scope_id=scope_id,
                    period=period,
                    bucket=bucket,
                    bytes_rx=max(0, bytes_rx),
                    bytes_tx=max(0, bytes_tx),
                )
            )
        else:
            row.bytes_rx += max(0, bytes_rx)
            row.bytes_tx += max(0, bytes_tx)
    await db.flush()


def resolve_range(range_key: str, start: datetime | None = None, end: datetime | None = None):
    now = datetime.now(timezone.utc)
    today = day_bucket(now)
    mapping = {
        "today": (today, now),
        "yesterday": (today - timedelta(days=1), today),
        "7d": (today - timedelta(days=6), now),
        "30d": (today - timedelta(days=29), now),
        "month": (today.replace(day=1), now),
        "custom": (start or today, end or now),
    }
    return mapping.get(range_key, mapping["today"])


async def summary(
    db: AsyncSession,
    scope: str,
    scope_id: str | None,
    range_key: str = "today",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    since, until = resolve_range(range_key, start, end)
    period = "hour" if (until - since) <= timedelta(days=2) else "day"
    filters = [
        TrafficRecord.scope == scope,
        TrafficRecord.period == period,
        TrafficRecord.bucket >= since,
        TrafficRecord.bucket <= until,
    ]
    if scope_id:
        filters.append(TrafficRecord.scope_id == scope_id)
    rows = (
        await db.execute(
            select(TrafficRecord.bucket, func.sum(TrafficRecord.bytes_rx), func.sum(TrafficRecord.bytes_tx))
            .where(*filters)
            .group_by(TrafficRecord.bucket)
            .order_by(TrafficRecord.bucket.asc())
        )
    ).all()
    points = [{"bucket": b, "bytes_rx": int(rx or 0), "bytes_tx": int(tx or 0)} for b, rx, tx in rows]
    total_rx = sum(p["bytes_rx"] for p in points)
    total_tx = sum(p["bytes_tx"] for p in points)
    return {
        "scope": scope,
        "scope_id": scope_id,
        "bytes_rx": total_rx,
        "bytes_tx": total_tx,
        "bytes_total": total_rx + total_tx,
        "points": points,
    }


async def totals_by_scope(db: AsyncSession, scope: str, range_key: str = "today") -> list[dict]:
    since, until = resolve_range(range_key)
    period = "hour" if (until - since) <= timedelta(days=2) else "day"
    rows = (
        await db.execute(
            select(
                TrafficRecord.scope_id,
                func.sum(TrafficRecord.bytes_rx),
                func.sum(TrafficRecord.bytes_tx),
            )
            .where(
                TrafficRecord.scope == scope,
                TrafficRecord.period == period,
                TrafficRecord.bucket >= since,
                TrafficRecord.bucket <= until,
            )
            .group_by(TrafficRecord.scope_id)
        )
    ).all()
    return [
        {
            "scope_id": sid,
            "bytes_rx": int(rx or 0),
            "bytes_tx": int(tx or 0),
            "bytes_total": int((rx or 0) + (tx or 0)),
        }
        for sid, rx, tx in rows
    ]


async def cleanup(db: AsyncSession, days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    res = await db.execute(delete(TrafficRecord).where(TrafficRecord.bucket < cutoff))
    return res.rowcount or 0
