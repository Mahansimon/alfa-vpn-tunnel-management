"""Scheduler پس‌زمینه: heartbeat watchdog، تجمیع متریک، هشدارها، پاک‌سازی، پشتیبان‌گیری."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.server import Server
from app.db.models.tunnel import Tunnel
from app.db.session import SessionLocal
from app.services import alerting, backup_service, metrics_service, mock, settings_service, traffic_service
from app.services.audit import push_notification, record_event
from app.services.realtime import hub

log = get_logger("scheduler")

_tasks: list[asyncio.Task] = []
_started_at = datetime.now(timezone.utc)
_last_run: dict[str, datetime] = {}


def uptime_seconds() -> int:
    return int((datetime.now(timezone.utc) - _started_at).total_seconds())


def last_runs() -> dict[str, str]:
    return {k: v.isoformat() for k, v in _last_run.items()}


async def _loop(name: str, interval: int, func) -> None:
    """اجرای دوره‌ای یک وظیفه با مقاومت در برابر خطا."""
    await asyncio.sleep(3)
    while True:
        try:
            async with SessionLocal() as db:
                await func(db)
                await db.commit()
            _last_run[name] = datetime.now(timezone.utc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("scheduler_task_failed", task=name, error=str(exc))
        await asyncio.sleep(interval)


async def _heartbeat_watchdog(db) -> None:
    """اگر چند heartbeat پشت سر هم نرسید، سرور Offline می‌شود."""
    interval = int(await settings_service.get(db, "heartbeat_interval_seconds", 15) or 15)
    allowed = int(await settings_service.get(db, "offline_after_missed", 3) or 3)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=interval * allowed + 5)
    servers = (await db.execute(select(Server))).scalars().all()
    for server in servers:
        if server.maintenance:
            if server.status != "maintenance":
                server.status = "maintenance"
            continue
        agent = server.agent
        last = agent.last_heartbeat_at if agent else server.last_seen_at
        if last is None:
            if server.status not in ("pending", "offline"):
                server.status = "offline"
            continue
        if last < cutoff and server.status != "offline":
            server.status = "offline"
            server.missed_heartbeats += 1
            server.health_score = 0
            await record_event(
                db,
                target_type="server",
                target_id=server.id,
                kind="server_offline",
                title=f"سرور «{server.name}» آفلاین شد",
                severity="critical",
            )
            await push_notification(
                db,
                kind="server_offline",
                title=f"سرور «{server.name}» آفلاین شد",
                body="چند Heartbeat پشت سر هم دریافت نشد.",
                severity="critical",
                target_type="server",
                target_id=server.id,
            )
            await hub.publish("servers", "server.updated", {"id": server.id, "status": "offline"})
        elif last >= cutoff and server.status == "offline":
            server.status = "online"
            server.missed_heartbeats = 0
            await push_notification(
                db,
                kind="server_recovered",
                title=f"سرور «{server.name}» بازگشت",
                body="ارتباط Agent برقرار شد.",
                severity="info",
                target_type="server",
                target_id=server.id,
            )


async def _health_scores(db) -> None:
    servers = (await db.execute(select(Server))).scalars().all()
    payload = []
    for server in servers:
        server.health_score = await metrics_service.compute_health_score(db, server)
        payload.append({"id": server.id, "status": server.status, "health_score": server.health_score})
    tunnels = (await db.execute(select(Tunnel))).scalars().all()
    stale = datetime.now(timezone.utc) - timedelta(minutes=5)
    for tunnel in tunnels:
        if tunnel.state in ("deployed",) and (tunnel.last_health_at or stale) < stale:
            tunnel.health = "unknown"
    if payload:
        await hub.publish("servers", "servers.health", {"servers": payload})


async def _aggregate(db) -> None:
    await metrics_service.aggregate(db, "hour")
    await metrics_service.aggregate(db, "day")


async def _cleanup(db) -> None:
    raw_days = int(await settings_service.get(db, "metric_retention_days", 7) or 7)
    traffic_days = int(await settings_service.get(db, "traffic_retention_days", 365) or 365)
    log_days = int(await settings_service.get(db, "log_retention_days", 30) or 30)
    removed = await metrics_service.cleanup(db, raw_days, settings.METRIC_AGG_RETENTION_DAYS)
    removed += await traffic_service.cleanup(db, traffic_days)
    removed += await alerting.cleanup_resolved(db)
    from sqlalchemy import delete

    from app.db.models.ops import AuditLog, LogEntry

    cutoff = datetime.now(timezone.utc) - timedelta(days=log_days)
    res = await db.execute(delete(LogEntry).where(LogEntry.ts < cutoff))
    removed += res.rowcount or 0
    audit_cutoff = datetime.now(timezone.utc) - timedelta(days=max(log_days, 180))
    res = await db.execute(delete(AuditLog).where(AuditLog.created_at < audit_cutoff))
    removed += res.rowcount or 0
    if removed:
        log.info("cleanup_done", removed=removed)


async def _alerts(db) -> None:
    await alerting.evaluate(db)


async def _mock_tick(db) -> None:
    await mock.tick(db)
    servers = (await db.execute(select(Server))).scalars().all()
    live = []
    for server in servers:
        latest = await metrics_service.latest_metric(db, server.id)
        if latest:
            live.append(
                {
                    "id": server.id,
                    "cpu_percent": latest.cpu_percent,
                    "ram_percent": metrics_service.percent(latest.ram_used, latest.ram_total),
                    "disk_percent": metrics_service.percent(latest.disk_used, latest.disk_total),
                    "rx_rate": latest.net_rx_rate,
                    "tx_rate": latest.net_tx_rate,
                    "status": server.status,
                }
            )
    if live:
        await hub.publish("metrics", "metrics.tick", {"servers": live})


async def _auto_backup(db) -> None:
    if not bool(await settings_service.get(db, "backup_enabled", True)):
        return
    hours = int(await settings_service.get(db, "backup_interval_hours", 24) or 24)
    last = _last_run.get("auto_backup_done")
    if last and (datetime.now(timezone.utc) - last) < timedelta(hours=hours):
        return
    try:
        await backup_service.create_backup(db, kind="full", note="پشتیبان خودکار")
        _last_run["auto_backup_done"] = datetime.now(timezone.utc)
    except Exception as exc:
        log.warning("auto_backup_failed", error=str(exc))


def start() -> None:
    if not settings.SCHEDULER_ENABLED or _tasks:
        return
    jobs = [
        ("heartbeat_watchdog", 15, _heartbeat_watchdog),
        ("health_scores", 30, _health_scores),
        ("alerts", 30, _alerts),
        ("aggregate", 600, _aggregate),
        ("cleanup", 3600, _cleanup),
        ("auto_backup", 1800, _auto_backup),
    ]
    if mock.enabled():
        jobs.append(("mock_tick", max(5, settings.METRICS_INTERVAL_SECONDS), _mock_tick))
    for name, interval, func in jobs:
        _tasks.append(asyncio.create_task(_loop(name, interval, func), name=f"alfa:{name}"))
    log.info("scheduler_started", jobs=[j[0] for j in jobs])


async def stop() -> None:
    for task in _tasks:
        task.cancel()
    for task in _tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _tasks.clear()
