"""دریافت متریک از Agent، محاسبه Health Score، تجمیع و پاک‌سازی."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.monitoring import Metric, MetricAggregate
from app.db.models.server import Server
from app.db.models.tunnel import Tunnel
from app.schemas.agent import AgentMetricsPayload

RANGE_WINDOWS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def percent(used: int | float, total: int | float) -> float:
    if not total:
        return 0.0
    return round(min(100.0, max(0.0, (used / total) * 100)), 2)


async def store_metrics(db: AsyncSession, server: Server, payload: AgentMetricsPayload) -> Metric:
    load = list(payload.load or [0, 0, 0]) + [0, 0, 0]
    metric = Metric(
        server_id=server.id,
        ts=payload.ts or datetime.now(timezone.utc),
        cpu_percent=payload.cpu_percent,
        load_1=load[0],
        load_5=load[1],
        load_15=load[2],
        ram_total=payload.ram_total,
        ram_used=payload.ram_used,
        swap_total=payload.swap_total,
        swap_used=payload.swap_used,
        disk_total=payload.disk_total,
        disk_used=payload.disk_used,
        net_rx_bytes=payload.net_rx_bytes,
        net_tx_bytes=payload.net_tx_bytes,
        net_rx_rate=payload.net_rx_rate,
        net_tx_rate=payload.net_tx_rate,
        packets_rx_rate=payload.packets_rx_rate,
        packets_tx_rate=payload.packets_tx_rate,
        uptime_seconds=payload.uptime_seconds,
    )
    db.add(metric)
    server.uptime_seconds = payload.uptime_seconds
    if payload.ram_total:
        server.ram_total_bytes = payload.ram_total
    if payload.disk_total:
        server.disk_total_bytes = payload.disk_total
    await db.flush()
    return metric


async def latest_metric(db: AsyncSession, server_id: str) -> Metric | None:
    return (
        await db.execute(
            select(Metric).where(Metric.server_id == server_id).order_by(Metric.ts.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def series(db: AsyncSession, server_id: str, range_key: str = "1h") -> list[dict]:
    window = RANGE_WINDOWS.get(range_key, RANGE_WINDOWS["1h"])
    since = datetime.now(timezone.utc) - window
    if window <= timedelta(hours=24):
        rows = (
            await db.execute(
                select(Metric)
                .where(Metric.server_id == server_id, Metric.ts >= since)
                .order_by(Metric.ts.asc())
                .limit(3000)
            )
        ).scalars().all()
        return [
            {
                "ts": r.ts,
                "cpu_percent": r.cpu_percent,
                "ram_percent": percent(r.ram_used, r.ram_total),
                "disk_percent": percent(r.disk_used, r.disk_total),
                "rx_rate": r.net_rx_rate,
                "tx_rate": r.net_tx_rate,
                "packets_rx_rate": r.packets_rx_rate,
                "packets_tx_rate": r.packets_tx_rate,
                "load_1": r.load_1,
            }
            for r in rows
        ]
    aggs = (
        await db.execute(
            select(MetricAggregate)
            .where(
                MetricAggregate.server_id == server_id,
                MetricAggregate.bucket >= since,
                MetricAggregate.period == ("hour" if window <= timedelta(days=7) else "day"),
            )
            .order_by(MetricAggregate.bucket.asc())
        )
    ).scalars().all()
    return [
        {
            "ts": a.bucket,
            "cpu_percent": a.cpu_avg,
            "ram_percent": a.ram_avg,
            "disk_percent": a.disk_avg,
            "rx_rate": a.rx_rate_avg,
            "tx_rate": a.tx_rate_avg,
            "packets_rx_rate": 0,
            "packets_tx_rate": 0,
            "load_1": 0,
        }
        for a in aggs
    ]


async def compute_health_score(db: AsyncSession, server: Server) -> float:
    """امتیاز سلامت ۰ تا ۱۰۰ بر اساس CPU، RAM، Disk، Agent، تونل‌ها."""
    if server.status == "offline":
        return 0.0
    score = 100.0
    metric = await latest_metric(db, server.id)
    if metric:
        cpu = metric.cpu_percent
        ram = percent(metric.ram_used, metric.ram_total)
        disk = percent(metric.disk_used, metric.disk_total)
        score -= max(0.0, cpu - 70) * 0.6
        score -= max(0.0, ram - 75) * 0.6
        score -= max(0.0, disk - 80) * 0.8
    else:
        score -= 20
    agent = server.agent
    if not agent or not agent.enrolled:
        score -= 25
    elif agent.last_heartbeat_at:
        gap = (datetime.now(timezone.utc) - agent.last_heartbeat_at).total_seconds()
        if gap > 120:
            score -= 15
    tunnels = (
        await db.execute(
            select(Tunnel.health, func.count())
            .where((Tunnel.source_server_id == server.id) | (Tunnel.destination_server_id == server.id))
            .group_by(Tunnel.health)
        )
    ).all()
    for health, count in tunnels:
        if health == "down":
            score -= 8 * count
        elif health == "degraded":
            score -= 4 * count
    if server.maintenance:
        score = min(score, 60)
    return round(max(0.0, min(100.0, score)), 1)


async def aggregate(db: AsyncSession, period: str = "hour") -> int:
    """متریک خام را در باکت‌های ساعتی/روزانه تجمیع می‌کند (idempotent)."""
    trunc = "hour" if period == "hour" else "day"
    since = datetime.now(timezone.utc) - (timedelta(days=2) if period == "hour" else timedelta(days=40))
    bucket = func.date_trunc(trunc, Metric.ts).label("bucket")
    rows = (
        await db.execute(
            select(
                Metric.server_id,
                bucket,
                func.avg(Metric.cpu_percent),
                func.max(Metric.cpu_percent),
                func.avg(Metric.ram_used * 100.0 / func.nullif(Metric.ram_total, 0)),
                func.avg(Metric.disk_used * 100.0 / func.nullif(Metric.disk_total, 0)),
                func.avg(Metric.net_rx_rate),
                func.avg(Metric.net_tx_rate),
                func.count(),
            )
            .where(Metric.ts >= since)
            .group_by(Metric.server_id, bucket)
        )
    ).all()
    written = 0
    for server_id, bkt, cpu_avg, cpu_max, ram_avg, disk_avg, rx, tx, samples in rows:
        existing = (
            await db.execute(
                select(MetricAggregate).where(
                    MetricAggregate.server_id == server_id,
                    MetricAggregate.bucket == bkt,
                    MetricAggregate.period == period,
                )
            )
        ).scalar_one_or_none()
        target = existing or MetricAggregate(server_id=server_id, bucket=bkt, period=period)
        target.cpu_avg = round(float(cpu_avg or 0), 2)
        target.cpu_max = round(float(cpu_max or 0), 2)
        target.ram_avg = round(float(ram_avg or 0), 2)
        target.disk_avg = round(float(disk_avg or 0), 2)
        target.rx_rate_avg = float(rx or 0)
        target.tx_rate_avg = float(tx or 0)
        target.samples = int(samples or 0)
        if existing is None:
            db.add(target)
        written += 1
    await db.flush()
    return written


async def cleanup(db: AsyncSession, raw_days: int, agg_days: int) -> int:
    now = datetime.now(timezone.utc)
    removed = 0
    res = await db.execute(delete(Metric).where(Metric.ts < now - timedelta(days=raw_days)))
    removed += res.rowcount or 0
    res = await db.execute(
        delete(MetricAggregate).where(MetricAggregate.bucket < now - timedelta(days=agg_days))
    )
    removed += res.rowcount or 0
    return removed
