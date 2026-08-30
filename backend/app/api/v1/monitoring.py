"""داشبورد، ترافیک، گزارش‌ها، لاگ‌ها، هشدارها و اعلان‌ها."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import Principal, client_ip, current_principal, require
from app.core.errors import NotFound
from app.core.rbac import Perm
from app.db.models.monitoring import Alert, AlertRule, Notification
from app.db.models.ops import LogEntry
from app.db.models.server import Server
from app.db.models.tunnel import Tunnel
from app.db.session import get_db
from app.schemas.common import OkResponse, Page, PageParams, paginate
from app.schemas.monitoring import (
    AlertOut,
    AlertRuleCreate,
    AlertRuleOut,
    DashboardOut,
    LogEntryOut,
    NotificationOut,
    TrafficSummary,
)
from app.services import metrics_service, mock, scheduler, traffic_service
from app.services.audit import record_audit

router = APIRouter(tags=["monitoring"])


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: AsyncSession = Depends(get_db), principal: Principal = Depends(require(Perm.METRICS_READ.value))
):
    servers = (await db.execute(select(Server))).scalars().all()
    tunnels = (await db.execute(select(Tunnel))).scalars().all()

    cpu_values, ram_values, disk_values, rx, tx = [], [], [], 0.0, 0.0
    top: list[dict] = []
    for server in servers:
        latest = await metrics_service.latest_metric(db, server.id)
        if not latest:
            continue
        ram = metrics_service.percent(latest.ram_used, latest.ram_total)
        disk = metrics_service.percent(latest.disk_used, latest.disk_total)
        cpu_values.append(latest.cpu_percent)
        ram_values.append(ram)
        disk_values.append(disk)
        rx += latest.net_rx_rate
        tx += latest.net_tx_rate
        top.append(
            {
                "id": server.id,
                "name": server.name,
                "country": server.country,
                "status": server.status,
                "cpu_percent": latest.cpu_percent,
                "ram_percent": ram,
                "disk_percent": disk,
                "rx_rate": latest.net_rx_rate,
                "tx_rate": latest.net_tx_rate,
                "health_score": server.health_score,
            }
        )
    top.sort(key=lambda item: item["cpu_percent"], reverse=True)

    today = await traffic_service.summary(db, "server", None, "today")
    month = await traffic_service.summary(db, "server", None, "month")
    unread = (
        await db.execute(
            select(func.count()).select_from(Notification).where(Notification.read.is_(False))
        )
    ).scalar() or 0

    breakdown: dict[str, int] = {"up": 0, "degraded": 0, "down": 0, "unknown": 0}
    for tunnel in tunnels:
        breakdown[tunnel.health if tunnel.health in breakdown else "unknown"] += 1

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    return DashboardOut(
        servers_total=len(servers),
        servers_online=sum(1 for s in servers if s.status == "online"),
        servers_offline=sum(1 for s in servers if s.status == "offline"),
        servers_warning=sum(1 for s in servers if s.status in ("warning", "maintenance")),
        tunnels_total=len(tunnels),
        tunnels_active=sum(1 for t in tunnels if t.state == "deployed" and t.health in ("up", "degraded")),
        tunnels_failed=sum(1 for t in tunnels if t.state == "failed" or t.health == "down"),
        tunnels_degraded=breakdown["degraded"],
        cpu_avg=avg(cpu_values),
        ram_avg=avg(ram_values),
        disk_avg=avg(disk_values),
        rx_rate=rx,
        tx_rate=tx,
        traffic_today_bytes=today["bytes_total"],
        traffic_month_bytes=month["bytes_total"],
        panel_uptime_seconds=scheduler.uptime_seconds(),
        health_score=round(sum(s.health_score for s in servers) / len(servers), 1) if servers else 0,
        unread_notifications=unread,
        mock_mode=mock.enabled(),
        traffic_series=today["points"],
        top_servers=top[:8],
        tunnel_health_breakdown=breakdown,
    )


@router.get("/traffic", response_model=TrafficSummary)
async def traffic(
    scope: str = Query(default="server", pattern="^(server|tunnel)$"),
    scope_id: str | None = Query(default=None),
    range: str = Query(default="today", pattern="^(today|yesterday|7d|30d|month|custom)$"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TRAFFIC_READ.value)),
):
    data = await traffic_service.summary(db, scope, scope_id, range, start, end)
    return TrafficSummary(**data)


@router.get("/reports/traffic")
async def traffic_report(
    scope: str = Query(default="server", pattern="^(server|tunnel)$"),
    range: str = Query(default="7d", pattern="^(today|yesterday|7d|30d|month)$"),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TRAFFIC_READ.value)),
):
    rows = await traffic_service.totals_by_scope(db, scope, range)
    names: dict[str, str] = {}
    if scope == "server":
        for server in (await db.execute(select(Server))).scalars():
            names[server.id] = server.name
    else:
        for tunnel in (await db.execute(select(Tunnel))).scalars():
            names[tunnel.id] = tunnel.name
    for row in rows:
        row["name"] = names.get(row["scope_id"], row["scope_id"])
        row["total_human"] = traffic_service.human_bytes(row["bytes_total"])
    rows.sort(key=lambda item: item["bytes_total"], reverse=True)
    return {"scope": scope, "range": range, "items": rows}


@router.get("/reports/traffic/export")
async def export_traffic(
    scope: str = Query(default="server", pattern="^(server|tunnel)$"),
    range: str = Query(default="7d", pattern="^(today|yesterday|7d|30d|month)$"),
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TRAFFIC_READ.value)),
):
    report = await traffic_report(scope=scope, range=range, db=db, _=None)  # type: ignore[arg-type]
    if format == "json":
        return report
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["name", "bytes_rx", "bytes_tx", "bytes_total", "total_human"])
    for row in report["items"]:
        writer.writerow(
            [row["name"], row["bytes_rx"], row["bytes_tx"], row["bytes_total"], row["total_human"]]
        )
    buffer.seek(0)
    filename = f"alfa-traffic-{scope}-{range}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/logs", response_model=Page[LogEntryOut])
async def list_logs(
    params: PageParams = Depends(),
    source: str | None = Query(default=None),
    level: str | None = Query(default=None),
    server_id: str | None = Query(default=None),
    tunnel_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.LOGS_READ.value)),
):
    query = select(LogEntry)
    if source:
        query = query.where(LogEntry.source == source)
    if level:
        query = query.where(LogEntry.level == level)
    if server_id:
        query = query.where(LogEntry.server_id == server_id)
    if tunnel_id:
        query = query.where(LogEntry.tunnel_id == tunnel_id)
    if since:
        query = query.where(LogEntry.ts >= since)
    if until:
        query = query.where(LogEntry.ts <= until)
    if params.search:
        query = query.where(LogEntry.message.ilike(f"%{params.search}%"))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(query.order_by(LogEntry.ts.desc()).offset(params.offset).limit(params.per_page))
    ).scalars().all()
    return paginate([LogEntryOut.model_validate(r) for r in rows], total, params)


@router.get("/logs/export")
async def export_logs(
    source: str | None = Query(default=None),
    server_id: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.LOGS_READ.value)),
):
    query = select(LogEntry)
    if source:
        query = query.where(LogEntry.source == source)
    if server_id:
        query = query.where(LogEntry.server_id == server_id)
    rows = (await db.execute(query.order_by(LogEntry.ts.desc()).limit(limit))).scalars().all()
    lines = [f"{r.ts.isoformat()} [{r.level.upper()}] [{r.source}] {r.message}" for r in rows]
    return StreamingResponse(
        iter(["\n".join(lines)]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="alfa-logs.txt"'},
    )


# ---------------- هشدارها ----------------


@router.get("/alert-rules", response_model=list[AlertRuleOut])
async def list_alert_rules(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.METRICS_READ.value))
):
    rows = (await db.execute(select(AlertRule).order_by(AlertRule.created_at.desc()))).scalars().all()
    return [AlertRuleOut.model_validate(r) for r in rows]


@router.post("/alert-rules", response_model=AlertRuleOut, status_code=201)
async def create_alert_rule(
    payload: AlertRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.ALERTS_MANAGE.value)),
):
    row = AlertRule(**payload.model_dump())
    db.add(row)
    await db.flush()
    await record_audit(
        db, action="alert_rule_created", user=actor.user, target=row.name, ip=client_ip(request)
    )
    return AlertRuleOut.model_validate(row)


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleOut)
async def update_alert_rule(
    rule_id: str,
    payload: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.ALERTS_MANAGE.value)),
):
    row = await db.get(AlertRule, rule_id)
    if row is None:
        raise NotFound("قاعده هشدار یافت نشد.")
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    await db.flush()
    return AlertRuleOut.model_validate(row)


@router.delete("/alert-rules/{rule_id}", response_model=OkResponse)
async def delete_alert_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.ALERTS_MANAGE.value)),
):
    row = await db.get(AlertRule, rule_id)
    if row is None:
        raise NotFound("قاعده هشدار یافت نشد.")
    await db.delete(row)
    return OkResponse(message="قاعده هشدار حذف شد.")


@router.get("/alerts", response_model=Page[AlertOut])
async def list_alerts(
    params: PageParams = Depends(),
    state: str | None = Query(default=None, pattern="^(firing|resolved)$"),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.METRICS_READ.value)),
):
    query = select(Alert)
    if state:
        query = query.where(Alert.state == state)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(query.order_by(Alert.created_at.desc()).offset(params.offset).limit(params.per_page))
    ).scalars().all()
    return paginate([AlertOut.model_validate(r) for r in rows], total, params)


# ---------------- اعلان‌ها ----------------


@router.get("/notifications", response_model=Page[NotificationOut])
async def list_notifications(
    params: PageParams = Depends(),
    unread_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(current_principal),
):
    query = select(Notification)
    if unread_only:
        query = query.where(Notification.read.is_(False))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(Notification.created_at.desc()).offset(params.offset).limit(params.per_page)
        )
    ).scalars().all()
    return paginate([NotificationOut.model_validate(r) for r in rows], total, params)


@router.get("/notifications/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), _: Principal = Depends(current_principal)):
    count = (
        await db.execute(
            select(func.count()).select_from(Notification).where(Notification.read.is_(False))
        )
    ).scalar() or 0
    return {"count": count}


@router.post("/notifications/{notification_id}/read", response_model=OkResponse)
async def mark_read(
    notification_id: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(current_principal)
):
    row = await db.get(Notification, notification_id)
    if row is None:
        raise NotFound("اعلان یافت نشد.")
    row.read = True
    return OkResponse(message="خوانده شد.")


@router.post("/notifications/read-all", response_model=OkResponse)
async def mark_all_read(db: AsyncSession = Depends(get_db), _: Principal = Depends(current_principal)):
    rows = (await db.execute(select(Notification).where(Notification.read.is_(False)))).scalars().all()
    for row in rows:
        row.read = True
    return OkResponse(message=f"{len(rows)} اعلان خوانده شد.")


@router.get("/search")
async def global_search(
    q: str = Query(min_length=1, max_length=80),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(current_principal),
):
    """جستجوی سراسری برای Command Palette (Ctrl+K)."""
    term = f"%{q}%"
    servers = (
        await db.execute(
            select(Server)
            .where(or_(Server.name.ilike(term), Server.ip_address.ilike(term), Server.country.ilike(term)))
            .limit(6)
        )
    ).scalars().all()
    tunnels = (
        await db.execute(select(Tunnel).where(Tunnel.name.ilike(term)).limit(6))
    ).scalars().all()
    logs = (
        await db.execute(
            select(LogEntry).where(LogEntry.message.ilike(term)).order_by(LogEntry.ts.desc()).limit(5)
        )
    ).scalars().all()
    return {
        "servers": [{"id": s.id, "name": s.name, "ip": s.ip_address, "status": s.status} for s in servers],
        "tunnels": [{"id": t.id, "name": t.name, "health": t.health, "type": t.type_key} for t in tunnels],
        "logs": [{"id": r.id, "message": r.message[:120], "ts": r.ts, "source": r.source} for r in logs],
    }


@router.get("/monitoring/live")
async def live_snapshot(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.METRICS_READ.value))
):
    """اسنپ‌شات آخرین وضعیت همه سرورها (وقتی WebSocket در دسترس نیست)."""
    servers = (await db.execute(select(Server))).scalars().all()
    out = []
    for server in servers:
        latest = await metrics_service.latest_metric(db, server.id)
        out.append(
            {
                "id": server.id,
                "name": server.name,
                "status": server.status,
                "health_score": server.health_score,
                "cpu_percent": latest.cpu_percent if latest else 0,
                "ram_percent": metrics_service.percent(latest.ram_used, latest.ram_total) if latest else 0,
                "disk_percent": metrics_service.percent(latest.disk_used, latest.disk_total) if latest else 0,
                "rx_rate": latest.net_rx_rate if latest else 0,
                "tx_rate": latest.net_tx_rate if latest else 0,
                "last_seen_at": server.last_seen_at,
            }
        )
    return {
        "servers": out,
        "generated_at": datetime.now(timezone.utc),
        "interval_seconds": settings.METRICS_INTERVAL_SECONDS,
        "stale_after_seconds": settings.AGENT_HEARTBEAT_INTERVAL * settings.AGENT_OFFLINE_AFTER_MISSED,
        "window": str(timedelta(seconds=settings.METRICS_INTERVAL_SECONDS)),
    }
