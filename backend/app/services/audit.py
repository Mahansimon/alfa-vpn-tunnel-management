"""ثبت Audit Log، رخداد امنیتی، Event و Notification."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.monitoring import Notification
from app.db.models.ops import AuditLog, LogEntry
from app.db.models.server import Event
from app.db.models.user import SecurityEvent
from app.services.realtime import hub


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    user=None,
    username: str | None = None,
    server_id: str | None = None,
    tunnel_id: str | None = None,
    target: str = "",
    result: str = "success",
    error: str = "",
    ip: str | None = None,
    user_agent: str | None = None,
    payload: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=getattr(user, "id", None),
        username=username or getattr(user, "username", "system"),
        action=action,
        server_id=server_id,
        tunnel_id=tunnel_id,
        target=target,
        result=result,
        error=error[:4000],
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
        payload=_sanitize(payload or {}),
    )
    db.add(entry)
    await db.flush()
    return entry


def _sanitize(payload: dict) -> dict:
    """هیچ Secretی داخل Audit ذخیره نمی‌شود."""
    blocked = ("password", "token", "secret", "private_key", "certificate")
    clean: dict = {}
    for key, value in payload.items():
        if any(b in key.lower() for b in blocked):
            clean[key] = "***"
        elif isinstance(value, dict):
            clean[key] = _sanitize(value)
        else:
            clean[key] = value
    return clean


async def record_security_event(
    db: AsyncSession,
    kind: str,
    *,
    username: str | None = None,
    user_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: str = "",
    severity: str = "info",
) -> None:
    db.add(
        SecurityEvent(
            kind=kind,
            username=username,
            user_id=user_id,
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
            detail=detail,
            severity=severity,
        )
    )
    await db.flush()


async def record_event(
    db: AsyncSession,
    *,
    target_type: str,
    target_id: str | None,
    kind: str,
    title: str,
    detail: str = "",
    severity: str = "info",
) -> None:
    db.add(
        Event(
            target_type=target_type,
            target_id=target_id,
            kind=kind,
            title=title,
            detail=detail,
            severity=severity,
        )
    )
    await db.flush()


async def push_notification(
    db: AsyncSession,
    *,
    kind: str,
    title: str,
    body: str = "",
    severity: str = "info",
    target_type: str | None = None,
    target_id: str | None = None,
) -> Notification:
    note = Notification(
        kind=kind,
        title=title,
        body=body,
        severity=severity,
        target_type=target_type,
        target_id=target_id,
    )
    db.add(note)
    await db.flush()
    await hub.publish(
        "notifications",
        "notification.created",
        {
            "id": note.id,
            "kind": kind,
            "title": title,
            "body": body,
            "severity": severity,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return note


async def add_log(
    db: AsyncSession,
    *,
    source: str,
    message: str,
    level: str = "info",
    server_id: str | None = None,
    tunnel_id: str | None = None,
    ts: datetime | None = None,
) -> None:
    db.add(
        LogEntry(
            source=source,
            message=message[:8000],
            level=level,
            server_id=server_id,
            tunnel_id=tunnel_id,
            ts=ts or datetime.now(timezone.utc),
        )
    )
