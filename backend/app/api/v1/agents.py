"""Endpointهای سمت Agent: ثبت‌نام (Registration)، Heartbeat و ارسال لاگ.

احراز هویت Agent:
- هدر Authorization: Bearer <agent_token>
- هدر X-Alfa-Server-Id برای یافتن رکورد (توکن به صورت رمزگذاری‌شده نگه داشته می‌شود)
- هدر X-Alfa-Signature: HMAC-SHA256 بدنه خام با کلید امضای اختصاصی سرور
- Rate limit اختصاصی برای این مسیرها
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import APP_VERSION, MIN_AGENT_VERSION, settings
from app.core.crypto import decrypt, encrypt, hash_token, new_token, verify_signature, verify_token
from app.core.deps import client_ip
from app.core.errors import Unauthorized
from app.core.ratelimit import check as rate_check
from app.db.models.server import Server, ServerAgent
from app.db.models.tunnel import Tunnel
from app.db.session import get_db
from app.schemas.agent import (
    AgentHeartbeat,
    AgentHeartbeatResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
)
from app.services import metrics_service, settings_service, traffic_service
from app.services.audit import add_log, push_notification, record_event
from app.services.realtime import hub

router = APIRouter(prefix="/agent", tags=["agent"])


def _version_ok(version: str) -> bool:
    def parse(value: str) -> tuple[int, ...]:
        try:
            return tuple(int(p) for p in value.split(".")[:3])
        except ValueError:
            return (0,)

    return parse(version) >= parse(MIN_AGENT_VERSION)


async def authenticate_agent(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
    x_alfa_server_id: str = Header(default=""),
    x_alfa_signature: str = Header(default=""),
) -> tuple[Server, ServerAgent]:
    await rate_check(f"agent:{client_ip(request)}", settings.AGENT_RATE_LIMIT)
    if not authorization.lower().startswith("bearer ") or not x_alfa_server_id:
        raise Unauthorized("اعتبارنامه Agent ارسال نشده است.")
    token = authorization.split(" ", 1)[1].strip()
    server = await db.get(Server, x_alfa_server_id)
    if server is None or server.agent is None or not server.agent.api_token_enc:
        raise Unauthorized("سرور ثبت‌شده‌ای برای این Agent وجود ندارد.")
    agent = server.agent
    if (decrypt(agent.api_token_enc) or "") != token:
        raise Unauthorized("توکن Agent معتبر نیست.")
    body = await request.body()
    secret = decrypt(agent.signing_secret_enc) or ""
    if secret and not verify_signature(secret, body.decode("utf-8") or "", x_alfa_signature):
        raise Unauthorized("امضای درخواست معتبر نیست.")
    return server, agent


@router.post("/register", response_model=AgentRegisterResponse)
async def register(payload: AgentRegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Agent با Enrollment Token خودش را ثبت می‌کند و توکن دائمی می‌گیرد."""
    await rate_check(f"agent-register:{client_ip(request)}", "20/10m")
    token_hash = hash_token(payload.enrollment_token)
    agent = (
        await db.execute(select(ServerAgent).where(ServerAgent.enrollment_token_hash == token_hash))
    ).scalar_one_or_none()
    if agent is None or not verify_token(payload.enrollment_token, agent.enrollment_token_hash):
        raise Unauthorized("توکن نصب معتبر نیست.")
    if agent.enrollment_expires_at and agent.enrollment_expires_at < datetime.now(timezone.utc):
        raise Unauthorized("توکن نصب منقضی شده است. از پنل توکن جدید بگیرید.")

    server = await db.get(Server, agent.server_id)
    system = payload.system
    server.hostname = system.hostname or server.hostname
    server.operating_system = system.os or server.operating_system
    server.kernel = system.kernel or server.kernel
    server.architecture = system.architecture or server.architecture
    server.cpu_cores = system.cpu_cores or server.cpu_cores
    server.cpu_model = system.cpu_model or server.cpu_model
    server.ram_total_bytes = system.ram_total or server.ram_total_bytes
    server.disk_total_bytes = system.disk_total or server.disk_total_bytes
    server.private_ip = system.private_ip or server.private_ip
    server.uptime_seconds = system.uptime_seconds or server.uptime_seconds
    server.status = "online"
    server.last_seen_at = datetime.now(timezone.utc)

    agent_token = new_token(40)
    signing_secret = new_token(32)
    agent.api_token_enc = encrypt(agent_token)
    agent.signing_secret_enc = encrypt(signing_secret)
    agent.enrolled = True
    agent.version = system.agent_version
    agent.capabilities = system.capabilities
    agent.compatible = _version_ok(system.agent_version)
    agent.token_issued_at = datetime.now(timezone.utc)
    agent.token_rotate_after = datetime.now(timezone.utc) + timedelta(days=settings.AGENT_TOKEN_ROTATION_DAYS)
    agent.last_heartbeat_at = datetime.now(timezone.utc)
    agent.endpoint = f"{server.ip_address}:{server.agent_port}"
    agent.enrollment_token_hash = "used"
    await db.flush()

    await record_event(
        db,
        target_type="server",
        target_id=server.id,
        kind="agent_registered",
        title=f"Agent روی «{server.name}» ثبت شد",
        detail=f"نسخه {system.agent_version} - {system.os} {system.architecture}",
    )
    await push_notification(
        db,
        kind="agent_registered",
        title=f"Agent سرور «{server.name}» متصل شد",
        body=f"{system.hostname} · {system.os} · {system.architecture}",
        severity="info",
        target_type="server",
        target_id=server.id,
    )
    if not agent.compatible:
        await push_notification(
            db,
            kind="agent_incompatible",
            title=f"نسخه Agent سرور «{server.name}» قدیمی است",
            body=f"نسخه {system.agent_version} با پنل {APP_VERSION} سازگار نیست؛ Agent را به‌روزرسانی کنید.",
            severity="warning",
            target_type="server",
            target_id=server.id,
        )
    await hub.publish("servers", "server.updated", {"id": server.id, "status": "online"})

    return AgentRegisterResponse(
        server_id=server.id,
        agent_token=agent_token,
        signing_secret=signing_secret,
        heartbeat_interval=int(await settings_service.get(db, "heartbeat_interval_seconds", 15) or 15),
        metrics_interval=int(await settings_service.get(db, "metrics_interval_seconds", 20) or 20),
        panel_version=APP_VERSION,
        rotate_after=agent.token_rotate_after,
    )


@router.post("/heartbeat", response_model=AgentHeartbeatResponse)
async def heartbeat(
    payload: AgentHeartbeat,
    auth: tuple[Server, ServerAgent] = Depends(authenticate_agent),
    db: AsyncSession = Depends(get_db),
):
    server, agent = auth
    now = datetime.now(timezone.utc)
    agent.last_heartbeat_at = now
    agent.version = payload.agent_version or agent.version
    agent.compatible = _version_ok(agent.version or "0")
    server.last_seen_at = now
    server.missed_heartbeats = 0
    if not server.maintenance:
        server.status = "online"

    if payload.system:
        server.hostname = payload.system.hostname or server.hostname
        server.private_ip = payload.system.private_ip or server.private_ip

    live_payload: dict = {"id": server.id, "status": server.status}
    if payload.metrics:
        metric = await metrics_service.store_metrics(db, server, payload.metrics)
        # ترافیک سرور از نرخ لحظه‌ای × بازه heartbeat محاسبه می‌شود
        interval = int(await settings_service.get(db, "heartbeat_interval_seconds", 15) or 15)
        await traffic_service.add_usage(
            db,
            "server",
            server.id,
            int(payload.metrics.net_rx_rate * interval),
            int(payload.metrics.net_tx_rate * interval),
            now,
        )
        live_payload.update(
            {
                "cpu_percent": metric.cpu_percent,
                "ram_percent": metrics_service.percent(metric.ram_used, metric.ram_total),
                "disk_percent": metrics_service.percent(metric.disk_used, metric.disk_total),
                "rx_rate": metric.net_rx_rate,
                "tx_rate": metric.net_tx_rate,
                "load_1": metric.load_1,
                "uptime_seconds": metric.uptime_seconds,
            }
        )

    for status in payload.tunnels:
        tunnel = await db.get(Tunnel, status.tunnel_id)
        if tunnel is None:
            continue
        previous = tunnel.health
        tunnel.health = status.health if status.health in ("up", "down", "degraded", "unknown") else "unknown"
        tunnel.latency_ms = status.latency_ms
        tunnel.packet_loss = status.packet_loss
        tunnel.jitter_ms = status.jitter_ms
        tunnel.uptime_seconds = status.uptime_seconds
        tunnel.last_health_at = now
        if status.bytes_rx or status.bytes_tx:
            await traffic_service.add_usage(
                db, "tunnel", tunnel.id, status.bytes_rx, status.bytes_tx, now
            )
        if previous != tunnel.health and tunnel.health == "down":
            await push_notification(
                db,
                kind="tunnel_down",
                title=f"تونل «{tunnel.name}» قطع شد",
                body=status.detail or "Agent وضعیت DOWN گزارش کرد.",
                severity="critical",
                target_type="tunnel",
                target_id=tunnel.id,
            )
        await hub.publish("tunnels", "tunnel.updated", {"id": tunnel.id, "health": tunnel.health})

    for entry in payload.logs[:200]:
        await add_log(
            db,
            source=str(entry.get("source", "agent"))[:24],
            message=str(entry.get("message", ""))[:4000],
            level=str(entry.get("level", "info"))[:16],
            server_id=server.id,
            tunnel_id=entry.get("tunnel_id"),
        )

    rotate = bool(agent.token_rotate_after and agent.token_rotate_after < now)
    new_agent_token = None
    if rotate:
        new_agent_token = new_token(40)
        agent.api_token_enc = encrypt(new_agent_token)
        agent.token_issued_at = now
        agent.token_rotate_after = now + timedelta(days=settings.AGENT_TOKEN_ROTATION_DAYS)

    await db.flush()
    await hub.publish("metrics", "metrics.tick", {"servers": [live_payload]})

    return AgentHeartbeatResponse(
        ok=True,
        server_status=server.status,
        rotate_token=rotate,
        new_token=new_agent_token,
        pending_actions=[],
        metrics_interval=int(await settings_service.get(db, "metrics_interval_seconds", 20) or 20),
        heartbeat_interval=int(await settings_service.get(db, "heartbeat_interval_seconds", 15) or 15),
    )


@router.get("/config")
async def agent_config(
    auth: tuple[Server, ServerAgent] = Depends(authenticate_agent),
    db: AsyncSession = Depends(get_db),
):
    """پیکربندی جاری Agent (بازه‌ها و سطح لاگ)."""
    server, agent = auth
    return {
        "server_id": server.id,
        "panel_version": APP_VERSION,
        "heartbeat_interval": int(await settings_service.get(db, "heartbeat_interval_seconds", 15) or 15),
        "metrics_interval": int(await settings_service.get(db, "metrics_interval_seconds", 20) or 20),
        "log_level": settings.LOG_LEVEL,
        "compatible": agent.compatible,
    }
