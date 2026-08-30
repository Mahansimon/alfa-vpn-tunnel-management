"""بررسی سلامت اجزای سیستم برای صفحه «سلامت سیستم» و endpointهای /health و /ready."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import APP_VERSION, MIN_AGENT_VERSION, settings
from app.db.models.server import Server, ServerAgent
from app.db.models.tunnel import Tunnel
from app.db.models.user import SecurityEvent, User
from app.services import scheduler
from app.services.realtime import hub


async def component_checks(db: AsyncSession) -> list[dict]:
    components: list[dict] = []

    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        components.append(
            {
                "name": "Database",
                "status": "ok",
                "detail": "PostgreSQL پاسخ می‌دهد.",
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        )
    except Exception as exc:
        components.append({"name": "Database", "status": "down", "detail": str(exc)[:200]})

    if settings.REDIS_ENABLED:
        start = time.perf_counter()
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await client.ping()
            await client.aclose()
            components.append(
                {
                    "name": "Redis",
                    "status": "ok",
                    "detail": "در دسترس",
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                }
            )
        except Exception as exc:
            components.append(
                {"name": "Redis", "status": "degraded", "detail": f"غیرقابل دسترس: {str(exc)[:120]}"}
            )

    components.append(
        {
            "name": "Scheduler",
            "status": "ok" if settings.SCHEDULER_ENABLED else "degraded",
            "detail": f"آخرین اجراها: {', '.join(scheduler.last_runs().keys()) or 'در حال شروع'}",
        }
    )
    components.append(
        {"name": "WebSocket", "status": "ok", "detail": f"{hub.count()} اتصال فعال"}
    )

    total_servers = (await db.execute(select(func.count()).select_from(Server))).scalar() or 0
    offline = (
        await db.execute(select(func.count()).select_from(Server).where(Server.status == "offline"))
    ).scalar() or 0
    components.append(
        {
            "name": "Servers",
            "status": "ok" if offline == 0 else ("degraded" if offline < total_servers else "down"),
            "detail": f"{total_servers} سرور، {offline} آفلاین",
        }
    )

    down_tunnels = (
        await db.execute(select(func.count()).select_from(Tunnel).where(Tunnel.health == "down"))
    ).scalar() or 0
    total_tunnels = (await db.execute(select(func.count()).select_from(Tunnel))).scalar() or 0
    components.append(
        {
            "name": "Tunnels",
            "status": "ok" if down_tunnels == 0 else "degraded",
            "detail": f"{total_tunnels} تونل، {down_tunnels} قطع",
        }
    )

    outdated = (
        await db.execute(
            select(func.count()).select_from(ServerAgent).where(ServerAgent.version < MIN_AGENT_VERSION)
        )
    ).scalar() or 0
    components.append(
        {
            "name": "Agents",
            "status": "ok" if outdated == 0 else "degraded",
            "detail": f"{outdated} Agent قدیمی",
        }
    )
    return components


async def overview(db: AsyncSession) -> dict:
    components = await component_checks(db)
    status = "ok"
    if any(c["status"] == "down" for c in components):
        status = "down"
    elif any(c["status"] == "degraded" for c in components):
        status = "degraded"
    return {
        "status": status,
        "components": components,
        "panel_version": APP_VERSION,
        "checked_at": datetime.now(timezone.utc),
    }


async def security_overview(db: AsyncSession) -> dict:
    users = (await db.execute(select(User))).scalars().all()
    total_users = len(users)
    two_factor = sum(1 for u in users if u.totp_enabled)
    must_change = sum(1 for u in users if u.must_change_password)
    outdated_agents = (
        await db.execute(
            select(func.count()).select_from(ServerAgent).where(ServerAgent.version < MIN_AGENT_VERSION)
        )
    ).scalar() or 0
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    failed = (
        await db.execute(
            select(func.count())
            .select_from(SecurityEvent)
            .where(SecurityEvent.kind == "failed_login", SecurityEvent.created_at >= since)
        )
    ).scalar() or 0

    from app.services import settings_service

    https_enabled = bool(await settings_service.get(db, "https_enabled", False))

    findings = []
    score = 100
    if not https_enabled:
        score -= 25
        findings.append({"key": "https", "severity": "critical", "message": "پنل بدون HTTPS سرو می‌شود."})
    if total_users and two_factor == 0:
        score -= 20
        findings.append({"key": "2fa", "severity": "warning", "message": "هیچ کاربری ۲FA فعال ندارد."})
    if must_change:
        score -= 10
        findings.append(
            {"key": "password", "severity": "warning", "message": f"{must_change} کاربر باید پسورد را عوض کند."}
        )
    if outdated_agents:
        score -= 15
        findings.append(
            {"key": "agent", "severity": "warning", "message": f"{outdated_agents} Agent نسخه قدیمی دارد."}
        )
    if failed > 20:
        score -= 10
        findings.append(
            {"key": "failed_login", "severity": "warning", "message": f"{failed} تلاش ناموفق ورود ثبت شده."}
        )
    return {
        "https_enabled": https_enabled,
        "two_factor_users": two_factor,
        "total_users": total_users,
        "weak_password_users": must_change,
        "outdated_agents": outdated_agents,
        "failed_logins_24h": failed,
        "score": max(0, score),
        "findings": findings,
    }
