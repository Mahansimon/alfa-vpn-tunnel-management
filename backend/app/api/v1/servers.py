"""مدیریت سرورها، گروه‌ها، Agent و عملیات سرور."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.crypto import hash_token, new_token
from app.core.deps import Principal, client_ip, require
from app.core.errors import Conflict, NotFound
from app.core.rbac import Perm
from app.db.models.monitoring import Metric
from app.db.models.server import Event, Server, ServerAgent, ServerGroup
from app.db.models.tunnel import Tunnel
from app.db.session import get_db
from app.schemas.common import BulkAction, OkResponse, Page, PageParams, paginate
from app.schemas.servers import (
    EnrollmentTokenOut,
    ServerCreate,
    ServerCreated,
    ServerGroupCreate,
    ServerGroupOut,
    ServerOut,
    ServerUpdate,
)
from app.services import metrics_service
from app.services.agent_client import agent_client
from app.services.audit import record_audit, record_event
from app.services.realtime import hub

router = APIRouter(tags=["servers"])

ENROLLMENT_TTL_HOURS = 24


def install_command(token: str) -> str:
    """دستور نصب Agent که در پنل به کاربر نمایش داده می‌شود."""
    base = settings.PANEL_URL.rstrip("/")
    return (
        f"curl -fsSL {base}/install-agent.sh -o install-agent.sh && "
        f"sudo bash install-agent.sh --panel-url {base} --token {token}"
    )


async def _get_agent(db: AsyncSession, server_id: str) -> ServerAgent | None:
    """Agent را صریحاً با await می‌خواند تا MissingGreenlet رخ ندهد."""
    return (
        await db.execute(select(ServerAgent).where(ServerAgent.server_id == server_id))
    ).scalar_one_or_none()


async def _load_server(db: AsyncSession, server_id: str) -> Server | None:
    """سرور + Agent را با selectinload می‌آورد (بدون lazy load)."""
    return (
        await db.execute(
            select(Server)
            .options(selectinload(Server.agent))
            .where(Server.id == server_id)
        )
    ).scalar_one_or_none()


async def _issue_enrollment(db: AsyncSession, server: Server) -> str:
    """توکن enrollment برای نصب Agent صادر می‌کند."""
    token = new_token(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=ENROLLMENT_TTL_HOURS)

    # در async نباید server.agent را مستقیم بخوانیم (lazy load → MissingGreenlet)
    agent = await _get_agent(db, server.id)

    if agent is None:
        agent = ServerAgent(
            server_id=server.id,
            enrollment_token_hash=hash_token(token),
            enrollment_expires_at=expires,
            endpoint=f"{server.ip_address}:{server.agent_port}",
        )
        db.add(agent)
    else:
        agent.enrollment_token_hash = hash_token(token)
        agent.enrollment_expires_at = expires
        agent.enrolled = False

    await db.flush()
    return token


@router.get("/servers", response_model=Page[ServerOut])
async def list_servers(
    params: PageParams = Depends(),
    status: str | None = Query(default=None),
    country: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.SERVERS_READ.value)),
):
    query = select(Server).options(selectinload(Server.agent))
    if params.search:
        term = f"%{params.search}%"
        query = query.where(
            or_(
                Server.name.ilike(term),
                Server.ip_address.ilike(term),
                Server.country.ilike(term),
                Server.hostname.ilike(term),
            )
        )
    if status:
        query = query.where(Server.status == status)
    if country:
        query = query.where(Server.country == country)
    if group_id:
        query = query.where(Server.group_id == group_id)

    total = (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar() or 0

    sort_column = {
        "name": Server.name,
        "status": Server.status,
        "health": Server.health_score,
        "created_at": Server.created_at,
    }.get(params.sort or "created_at", Server.created_at)

    order = sort_column.asc() if params.order == "asc" else sort_column.desc()

    rows = (
        await db.execute(query.order_by(order).offset(params.offset).limit(params.per_page))
    ).scalars().all()

    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]

    return paginate([ServerOut.model_validate(r) for r in rows], total, params)


@router.post("/servers", response_model=ServerCreated, status_code=201)
async def create_server(
    payload: ServerCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SERVERS_WRITE.value)),
):
    duplicate = (
        await db.execute(select(Server).where(Server.ip_address == payload.ip_address))
    ).scalar_one_or_none()
    if duplicate:
        raise Conflict("سروری با این IP قبلاً ثبت شده است.")

    server = Server(**payload.model_dump(), status="pending")
    db.add(server)
    await db.flush()
    server_id = server.id

    token = await _issue_enrollment(db, server)

    await record_audit(
        db,
        action="server_created",
        user=actor.user,
        server_id=server_id,
        target=server.name,
        ip=client_ip(request),
    )
    await record_event(
        db,
        target_type="server",
        target_id=server_id,
        kind="created",
        title=f"سرور «{server.name}» ثبت شد",
    )

    # دوباره با selectinload بخوان تا MissingGreenlet ندهد
    loaded = await _load_server(db, server_id)
    if loaded is None:
        raise NotFound("سرور بعد از ثبت یافت نشد.")

    await hub.publish("servers", "server.created", {"id": server_id, "name": loaded.name})

    return ServerCreated(
        server=ServerOut.model_validate(loaded),
        enrollment_token=token,
        install_command=install_command(token),
    )


@router.get("/servers/{server_id}", response_model=ServerOut)
async def get_server(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.SERVERS_READ.value)),
):
    server = await _load_server(db, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")
    return ServerOut.model_validate(server)


@router.patch("/servers/{server_id}", response_model=ServerOut)
async def update_server(
    server_id: str,
    payload: ServerUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SERVERS_WRITE.value)),
):
    server = await db.get(Server, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(server, field, value)

    if "maintenance" in data:
        server.status = "maintenance" if data["maintenance"] else "pending"

    await db.flush()
    await record_audit(
        db,
        action="server_updated",
        user=actor.user,
        server_id=server.id,
        target=server.name,
        ip=client_ip(request),
        payload=data,
    )
    loaded = await _load_server(db, server.id)
    return ServerOut.model_validate(loaded or server)


@router.delete("/servers/{server_id}", response_model=OkResponse)
async def delete_server(
    server_id: str,
    request: Request,
    remove_agent: bool = Query(default=True, description="تلاش برای حذف Agent از سرور"),
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SERVERS_DELETE.value)),
):
    server = await db.get(Server, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")

    tunnels = (
        await db.execute(
            select(func.count())
            .select_from(Tunnel)
            .where(
                (Tunnel.source_server_id == server.id)
                | (Tunnel.destination_server_id == server.id)
            )
        )
    ).scalar() or 0
    if tunnels:
        raise Conflict(f"این سرور در {tunnels} تونل استفاده شده است. ابتدا تونل‌ها را حذف کنید.")

    name = server.name

    agent = await _get_agent(db, server.id)
    if remove_agent and agent is not None and agent.enrolled:
        try:
            await agent_client.call(server, "service_stop", {"service": "alfa-agent"})
        except Exception:
            pass

    await db.delete(server)
    await record_audit(
        db,
        action="server_deleted",
        user=actor.user,
        target=name,
        ip=client_ip(request),
        result="success",
    )
    await hub.publish("servers", "server.deleted", {"id": server_id})
    return OkResponse(message=f"سرور «{name}» حذف شد.")


@router.post("/servers/{server_id}/enrollment-token", response_model=EnrollmentTokenOut)
async def regenerate_enrollment_token(
    server_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SERVERS_WRITE.value)),
):
    server = await db.get(Server, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")

    token = await _issue_enrollment(db, server)
    agent = await _get_agent(db, server.id)

    await record_audit(
        db,
        action="enrollment_token_issued",
        user=actor.user,
        server_id=server.id,
        ip=client_ip(request),
    )
    return EnrollmentTokenOut(
        enrollment_token=token,
        install_command=install_command(token),
        expires_at=agent.enrollment_expires_at if agent else None,
    )


@router.get("/servers/{server_id}/metrics")
async def server_metrics(
    server_id: str,
    range: str = Query(default="1h", pattern="^(1h|6h|24h|7d|30d)$"),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.METRICS_READ.value)),
):
    server = await db.get(Server, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")

    points = await metrics_service.series(db, server_id, range)
    latest = await metrics_service.latest_metric(db, server_id)

    latest_payload = {}
    if latest:
        latest_payload = {
            "ts": latest.ts,
            "cpu_percent": latest.cpu_percent,
            "load": [latest.load_1, latest.load_5, latest.load_15],
            "ram_total": latest.ram_total,
            "ram_used": latest.ram_used,
            "ram_free": max(0, latest.ram_total - latest.ram_used),
            "swap_total": latest.swap_total,
            "swap_used": latest.swap_used,
            "disk_total": latest.disk_total,
            "disk_used": latest.disk_used,
            "disk_free": max(0, latest.disk_total - latest.disk_used),
            "net_rx_bytes": latest.net_rx_bytes,
            "net_tx_bytes": latest.net_tx_bytes,
            "rx_rate": latest.net_rx_rate,
            "tx_rate": latest.net_tx_rate,
            "uptime_seconds": latest.uptime_seconds,
        }

    return {
        "server_id": server_id,
        "range": range,
        "points": points,
        "latest": latest_payload,
        "system": {
            "hostname": server.hostname,
            "os": server.operating_system,
            "kernel": server.kernel,
            "architecture": server.architecture,
            "public_ip": server.ip_address,
            "private_ip": server.private_ip,
            "cpu_model": server.cpu_model,
            "cpu_cores": server.cpu_cores,
            "health_score": server.health_score,
            "status": server.status,
        },
    }


@router.get("/servers/{server_id}/events")
async def server_events(
    server_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.SERVERS_READ.value)),
):
    rows = (
        await db.execute(
            select(Event)
            .where(Event.target_type == "server", Event.target_id == server_id)
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "title": r.title,
            "detail": r.detail,
            "severity": r.severity,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/servers/{server_id}/actions/{action}")
async def server_action(
    server_id: str,
    action: str,
    request: Request,
    service: str | None = Query(default=None, description="نام سرویس برای اکشن‌های سرویس"),
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SERVERS_WRITE.value)),
):
    """اکشن‌های allowlist‌شده روی سرور. هیچ دستور دلخواهی پذیرفته نمی‌شود."""
    allowed = {
        "ping": ("ping", {}),
        "refresh": ("system_info", {}),
        "processes": ("logs", {"kind": "processes"}),
        "services": ("service_status", {"service": service or ""}),
        "service_start": ("service_start", {"service": service or ""}),
        "service_stop": ("service_stop", {"service": service or ""}),
        "service_restart": ("service_restart", {"service": service or ""}),
        "latency": ("latency_probe", {}),
    }
    if action not in allowed:
        raise Conflict("این اکشن پشتیبانی نمی‌شود.")

    server = await db.get(Server, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")

    agent_action, params = allowed[action]
    result = await agent_client.call(server, agent_action, params)

    if agent_action == "system_info" and result.ok:
        data = result.data
        server.hostname = data.get("hostname") or server.hostname
        server.operating_system = data.get("os") or server.operating_system
        server.kernel = data.get("kernel") or server.kernel
        server.architecture = data.get("architecture") or server.architecture
        server.cpu_cores = data.get("cpu_cores") or server.cpu_cores
        server.cpu_model = data.get("cpu_model") or server.cpu_model
        server.private_ip = data.get("private_ip") or server.private_ip
        await db.flush()

    await record_audit(
        db,
        action=f"server_{action}",
        user=actor.user,
        server_id=server.id,
        target=server.name,
        result="success" if result.ok else "failure",
        error=result.error,
        ip=client_ip(request),
    )
    return {
        "ok": result.ok,
        "output": result.output,
        "error": result.error,
        "data": result.data,
    }


@router.post("/servers/bulk", response_model=OkResponse)
async def bulk_servers(
    payload: BulkAction,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SERVERS_WRITE.value)),
):
    servers = (
        await db.execute(select(Server).where(Server.id.in_(payload.ids)))
    ).scalars().all()
    if not servers:
        raise NotFound("سروری یافت نشد.")

    if payload.action == "delete" and not actor.can(Perm.SERVERS_DELETE.value):
        raise Conflict("برای حذف سرور دسترسی لازم را ندارید.")

    done = 0
    for server in servers:
        if payload.action in ("maintenance_on", "maintenance_off"):
            server.maintenance = payload.action == "maintenance_on"
            server.status = "maintenance" if server.maintenance else "pending"
            done += 1
        elif payload.action == "restart":
            try:
                await agent_client.call(server, "service_restart", {"service": "alfa-agent"})
                done += 1
            except Exception:
                pass
        elif payload.action == "delete":
            await db.delete(server)
            done += 1

    await record_audit(
        db,
        action=f"servers_bulk_{payload.action}",
        user=actor.user,
        target=f"{done} سرور",
        ip=client_ip(request),
    )
    return OkResponse(message=f"عملیات روی {done} سرور انجام شد.")


# ---------------- گروه‌های سرور ----------------


@router.get("/server-groups", response_model=list[ServerGroupOut])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.SERVERS_READ.value)),
):
    rows = (await db.execute(select(ServerGroup).order_by(ServerGroup.name))).scalars().all()
    return [ServerGroupOut.model_validate(r) for r in rows]


@router.post("/server-groups", response_model=ServerGroupOut, status_code=201)
async def create_group(
    payload: ServerGroupCreate,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.SERVERS_WRITE.value)),
):
    exists = (
        await db.execute(select(ServerGroup).where(ServerGroup.name == payload.name))
    ).scalar_one_or_none()
    if exists:
        raise Conflict("گروهی با این نام وجود دارد.")
    group = ServerGroup(**payload.model_dump())
    db.add(group)
    await db.flush()
    return ServerGroupOut.model_validate(group)


@router.delete("/server-groups/{group_id}", response_model=OkResponse)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.SERVERS_WRITE.value)),
):
    group = await db.get(ServerGroup, group_id)
    if group is None:
        raise NotFound("گروه یافت نشد.")
    await db.delete(group)
    return OkResponse(message="گروه حذف شد.")


@router.get("/servers/{server_id}/processes")
async def server_processes(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.SERVERS_READ.value)),
):
    server = await db.get(Server, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")
    result = await agent_client.call(server, "logs", {"kind": "processes", "lines": 40})
    return {"ok": result.ok, "items": result.data.get("processes", []), "output": result.output}


@router.get("/servers/{server_id}/traffic-counters")
async def server_counters(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.METRICS_READ.value)),
):
    """آخرین شمارنده‌های خام شبکه (برای اشکال‌زدایی حساب‌داری ترافیک)."""
    rows = (
        await db.execute(
            select(Metric.ts, Metric.net_rx_bytes, Metric.net_tx_bytes)
            .where(Metric.server_id == server_id)
            .order_by(Metric.ts.desc())
            .limit(10)
        )
    ).all()
    return [{"ts": ts, "rx": rx, "tx": tx} for ts, rx, tx in rows]