"""Deployment Engine: نصب/حذف/به‌روزرسانی تونل با مراحل، لاگ زنده و Rollback.

قواعد:
- روی هر سرور همزمان فقط یک Deployment اجرا می‌شود (Locking).
- پیش از تغییر config، نسخه قبلی به عنوان revision نگه داشته می‌شود.
- در صورت شکست، تا حد امکان Rollback انجام می‌شود.
- همه مراحل به صورت زنده روی WebSocket منتشر می‌شوند.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.core.errors import Conflict, DeploymentFailed
from app.core.logging import get_logger
from app.db.models.ops import Deployment, DeploymentLog
from app.db.models.server import Server
from app.db.models.tunnel import Tunnel, TunnelConfig
from app.db.session import SessionLocal
from app.services.agent_client import agent_client
from app.services.audit import add_log, record_event
from app.services.realtime import hub
from app.tunnel_adapters.registry import build_adapter

log = get_logger("deploy")

_server_locks: dict[str, asyncio.Lock] = {}

PHASES = [
    ("validate", "اعتبارسنجی تنظیمات", 5),
    ("dependencies", "بررسی وابستگی‌ها", 15),
    ("download", "دریافت/آماده‌سازی منبع تونل", 35),
    ("configure", "نوشتن فایل‌های پیکربندی", 55),
    ("start", "راه‌اندازی سرویس", 75),
    ("health", "بررسی سلامت", 95),
    ("done", "پایان", 100),
]


def server_lock(server_id: str) -> asyncio.Lock:
    return _server_locks.setdefault(server_id, asyncio.Lock())


class DeploymentRunner:
    def __init__(self, deployment_id: str):
        self.deployment_id = deployment_id
        self.seq = 0

    async def log(self, db: AsyncSession, message: str, level: str = "info") -> None:
        self.seq += 1
        entry = DeploymentLog(
            deployment_id=self.deployment_id,
            seq=self.seq,
            ts=datetime.now(timezone.utc),
            level=level,
            message=message,
        )
        db.add(entry)
        await db.flush()
        await hub.publish(
            f"deployment:{self.deployment_id}",
            "deployment.log",
            {"seq": self.seq, "level": level, "message": message, "ts": entry.ts.isoformat()},
        )

    async def phase(self, db: AsyncSession, dep: Deployment, phase: str, progress: int, label: str) -> None:
        dep.phase = phase
        dep.progress = progress
        dep.status = "running"
        await db.flush()
        await hub.publish(
            f"deployment:{self.deployment_id}",
            "deployment.phase",
            {"phase": phase, "progress": progress, "label": label, "status": dep.status},
        )
        await self.log(db, f"[{progress}%] {label}")


async def create_deployment(
    db: AsyncSession,
    *,
    kind: str,
    tunnel: Tunnel | None,
    server: Server | None,
    user_id: str | None,
    dry_run: bool = False,
    payload: dict | None = None,
) -> Deployment:
    dep = Deployment(
        kind=kind,
        tunnel_id=tunnel.id if tunnel else None,
        server_id=server.id if server else None,
        status="pending",
        phase="queued",
        dry_run=dry_run,
        created_by=user_id,
        payload=payload or {},
    )
    db.add(dep)
    await db.flush()
    return dep


async def _active_config(db: AsyncSession, tunnel: Tunnel) -> TunnelConfig | None:
    return (
        await db.execute(
            select(TunnelConfig)
            .where(TunnelConfig.tunnel_id == tunnel.id, TunnelConfig.is_active.is_(True))
            .order_by(TunnelConfig.revision.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _split_secrets(config: dict) -> tuple[dict, dict]:
    from app.tunnel_adapters.base import SECRET_KEYS

    public = {k: v for k, v in config.items() if k not in SECRET_KEYS}
    secrets = {k: v for k, v in config.items() if k in SECRET_KEYS and v not in (None, "")}
    return public, secrets


async def save_config_revision(
    db: AsyncSession, tunnel: Tunnel, config: dict, user_id: str | None, note: str = ""
) -> TunnelConfig:
    """نسخه جدید config می‌سازد و نسخه قبلی را غیرفعال (اما نگه) می‌دارد."""
    current = await _active_config(db, tunnel)
    if current:
        current.is_active = False
    public, secrets = _split_secrets(config)
    revision = (current.revision + 1) if current else 1
    row = TunnelConfig(
        tunnel_id=tunnel.id,
        revision=revision,
        is_active=True,
        payload=public,
        secrets_enc=encrypt(json.dumps(secrets, ensure_ascii=False)) if secrets else None,
        created_by=user_id,
        note=note or f"revision {revision}",
    )
    db.add(row)
    await db.flush()
    return row


async def load_config(db: AsyncSession, tunnel: Tunnel) -> tuple[dict, dict]:
    row = await _active_config(db, tunnel)
    if not row:
        return {}, {}
    secrets = {}
    if row.secrets_enc:
        try:
            secrets = json.loads(decrypt(row.secrets_enc) or "{}")
        except (ValueError, TypeError):
            secrets = {}
    return dict(row.payload or {}), secrets


async def run_tunnel_deployment(deployment_id: str) -> None:
    """اجرای واقعی Deployment در پس‌زمینه (هر مرحله در تراکنش خودش)."""
    async with SessionLocal() as db:
        dep = await db.get(Deployment, deployment_id)
        if dep is None:
            return
        tunnel = await db.get(Tunnel, dep.tunnel_id) if dep.tunnel_id else None
        if tunnel is None:
            dep.status = "failed"
            dep.error = "تونل مورد نظر یافت نشد."
            await db.commit()
            return
        source = await db.get(Server, tunnel.source_server_id)
        destination = await db.get(Server, tunnel.destination_server_id)
        runner = DeploymentRunner(dep.id)
        dep.status = "running"
        dep.started_at = datetime.now(timezone.utc)
        await db.commit()

        lock = server_lock(source.id)
        if lock.locked():
            await runner.log(db, "سرور مبدأ در حال اجرای عملیات دیگری است؛ در صف انتظار.", "warning")
        async with lock:
            try:
                await _execute(db, runner, dep, tunnel, source, destination)
            except Exception as exc:  # rollback در صورت هر خطا
                dep.status = "failed"
                dep.error = str(exc)[:4000]
                dep.finished_at = datetime.now(timezone.utc)
                tunnel.state = "failed"
                tunnel.health = "down"
                await runner.log(db, f"خطا: {exc}", "error")
                await runner.log(db, "در حال بازگردانی تغییرات (Rollback)...", "warning")
                await _rollback(db, runner, tunnel, source, destination)
                await record_event(
                    db,
                    target_type="tunnel",
                    target_id=tunnel.id,
                    kind="deployment_failed",
                    title=f"استقرار تونل «{tunnel.name}» شکست خورد",
                    detail=str(exc)[:2000],
                    severity="critical",
                )
                from app.services.notifiers import dispatch

                await dispatch(
                    db,
                    title=f"استقرار تونل «{tunnel.name}» شکست خورد",
                    body=str(exc)[:500],
                    severity="critical",
                    channels=["inapp"],
                    kind="deployment_failed",
                    target_type="tunnel",
                    target_id=tunnel.id,
                )
                await db.commit()
                await hub.publish(
                    f"deployment:{dep.id}", "deployment.finished", {"status": "failed", "error": dep.error}
                )
                return
        await db.commit()


async def _execute(db, runner, dep, tunnel, source, destination) -> None:
    config, secrets = await load_config(db, tunnel)
    adapter = await build_adapter(db, tunnel.type_key, agent_client)

    await runner.phase(db, dep, PHASES[0][0], PHASES[0][2], PHASES[0][1])
    errors, warnings = adapter.validate_config({**config, **secrets})
    for warning in warnings:
        await runner.log(db, f"هشدار: {warning}", "warning")
    if errors:
        raise DeploymentFailed("؛ ".join(errors))

    if dep.dry_run:
        await runner.log(db, "حالت Dry Run: هیچ تغییری روی سرورها اعمال نشد.", "info")
        payload = adapter.build_payload(tunnel, config, secrets)
        await runner.log(db, "خلاصه عملیات: " + json.dumps(
            {"service": payload["service_name"], "source": payload["source"], "args": payload["args"]},
            ensure_ascii=False,
        ))
        dep.status = "success"
        dep.phase = "done"
        dep.progress = 100
        dep.finished_at = datetime.now(timezone.utc)
        await db.flush()
        await hub.publish(f"deployment:{dep.id}", "deployment.finished", {"status": "success"})
        return

    await runner.phase(db, dep, PHASES[1][0], PHASES[1][2], PHASES[1][1])
    for server in (source, destination):
        result = await adapter.dependency_check(server)
        if not result.ok:
            raise DeploymentFailed(
                f"وابستگی‌های لازم روی سرور «{server.name}» فراهم نیست: {result.error or result.output}"
            )
        await runner.log(db, f"وابستگی‌های سرور «{server.name}» تأیید شد.")

    await runner.phase(db, dep, PHASES[2][0], PHASES[2][2], PHASES[2][1])
    for server, peer, role_key in ((source, destination, "source"), (destination, source, "destination")):
        scoped = {
            **config,
            **secrets,
            "role": config.get(f"role_{role_key}", "client" if role_key == "source" else "server"),
            "peer_ip": peer.ip_address if peer else "",
        }
        result = await adapter.install(server, tunnel, scoped, secrets, dry_run=False)
        if not result.ok:
            raise DeploymentFailed(f"نصب روی «{server.name}» ناموفق بود: {result.error or result.output}")
        await runner.log(db, f"نصب روی «{server.name}»: {result.output[:500] or 'انجام شد'}")

    await runner.phase(db, dep, PHASES[3][0], PHASES[3][2], PHASES[3][1])
    for server, peer, role_key in ((source, destination, "source"), (destination, source, "destination")):
        scoped = {
            **config,
            **secrets,
            "role": config.get(f"role_{role_key}", "client" if role_key == "source" else "server"),
            "peer_ip": peer.ip_address if peer else "",
        }
        result = await adapter.configure(server, tunnel, scoped, secrets)
        if not result.ok:
            raise DeploymentFailed(f"پیکربندی «{server.name}» ناموفق بود: {result.error or result.output}")
        await runner.log(db, f"پیکربندی «{server.name}» نوشته شد.")

    await runner.phase(db, dep, PHASES[4][0], PHASES[4][2], PHASES[4][1])
    for server in (destination, source):  # ابتدا سمت شنونده
        result = await adapter.start(server, tunnel)
        if not result.ok:
            raise DeploymentFailed(f"راه‌اندازی روی «{server.name}» ناموفق بود: {result.error}")
        await runner.log(db, f"سرویس روی «{server.name}» فعال شد.")

    await runner.phase(db, dep, PHASES[5][0], PHASES[5][2], PHASES[5][1])
    health = await adapter.health_check(source, tunnel, config)
    data = health.data or {}
    tunnel.health = data.get("health", "unknown" if not health.ok else "up")
    tunnel.latency_ms = data.get("latency_ms")
    tunnel.packet_loss = data.get("packet_loss")
    tunnel.jitter_ms = data.get("jitter_ms")
    tunnel.last_health_at = datetime.now(timezone.utc)
    await runner.log(db, f"وضعیت سلامت تونل: {tunnel.health}")

    tunnel.state = "deployed"
    dep.status = "success"
    dep.phase = "done"
    dep.progress = 100
    dep.finished_at = datetime.now(timezone.utc)
    await add_log(db, source="deploy", message=f"تونل «{tunnel.name}» با موفقیت مستقر شد.", tunnel_id=tunnel.id)
    await record_event(
        db,
        target_type="tunnel",
        target_id=tunnel.id,
        kind="deployed",
        title=f"تونل «{tunnel.name}» مستقر شد",
        severity="info",
    )
    await db.flush()
    await hub.publish(f"deployment:{dep.id}", "deployment.finished", {"status": "success"})
    await hub.publish("tunnels", "tunnel.updated", {"id": tunnel.id, "state": tunnel.state,
                                                    "health": tunnel.health})


async def _rollback(db, runner, tunnel, source, destination) -> None:
    """تلاش برای بازگردانی: توقف سرویس و حذف پیکربندی نیمه‌کاره."""
    try:
        adapter = await build_adapter(db, tunnel.type_key, agent_client)
    except Exception:
        return
    for server in (source, destination):
        if server is None:
            continue
        try:
            await adapter.stop(server, tunnel)
            result = await agent_client.call(
                server, "tunnel_rollback", {"tunnel_id": tunnel.id, "service_name": tunnel.service_name}
            )
            await runner.log(
                db, f"بازگردانی روی «{server.name}»: {result.output[:300] or 'انجام شد'}", "warning"
            )
        except Exception as exc:
            await runner.log(db, f"بازگردانی روی «{server.name}» ناموفق: {exc}", "error")


async def run_action(db: AsyncSession, tunnel: Tunnel, action: str) -> dict:
    """اکشن‌های سریع تونل: start/stop/restart/status/logs."""
    if action not in {"start", "stop", "restart", "status", "logs", "health"}:
        raise Conflict("اکشن پشتیبانی نمی‌شود.")
    source = await db.get(Server, tunnel.source_server_id)
    destination = await db.get(Server, tunnel.destination_server_id)
    adapter = await build_adapter(db, tunnel.type_key, agent_client)
    config, _ = await load_config(db, tunnel)
    outputs: dict[str, str] = {}
    targets = (destination, source) if action in {"start", "restart"} else (source, destination)
    for server in targets:
        if server is None:
            continue
        if action == "logs":
            result = await adapter.logs(server, tunnel)
        elif action == "status":
            result = await adapter.status(server, tunnel)
        elif action == "health":
            result = await adapter.health_check(server, tunnel, config)
        else:
            result = await getattr(adapter, action)(server, tunnel)
        outputs[server.name] = result.output or result.error
    if action == "start":
        tunnel.state = "deployed"
    elif action == "stop":
        tunnel.state = "stopped"
        tunnel.health = "unknown"
    await db.flush()
    await hub.publish("tunnels", "tunnel.updated", {"id": tunnel.id, "state": tunnel.state})
    return outputs
