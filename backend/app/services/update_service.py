"""بررسی و اجرای به‌روزرسانی پنل و Agent.

اصول: Version Check → Backup → Download/Verify → Install → Health Check → Rollback
هیچ به‌روزرسانی خودکار مخربی انجام نمی‌شود؛ همه مراحل ثبت و قابل بازگردانی‌اند.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import APP_VERSION
from app.core.logging import get_logger
from app.db.models.server import Server
from app.services import backup_service, settings_service
from app.services.agent_client import agent_client
from app.services.audit import add_log

log = get_logger("update")


def _parse_repo(url: str) -> str | None:
    if not url:
        return None
    cleaned = url.rstrip("/").removesuffix(".git")
    if "github.com" not in cleaned:
        return None
    parts = cleaned.split("github.com")[-1].strip(":/").split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def validate_repository(url: str) -> bool:
    """اعتبارسنجی ساده آدرس Repository (جلوگیری از ورودی نامعتبر/خطرناک)."""
    if not url:
        return True
    if not url.startswith(("https://", "git@", "ssh://")):
        return False
    return len(url) < 300 and " " not in url


async def check_panel_update(db: AsyncSession) -> dict:
    repo_url = await settings_service.get(db, "github_repository", "")
    token = await settings_service.get(db, "github_token", "")
    slug = _parse_repo(repo_url or "")
    result = {
        "component": "panel",
        "current_version": APP_VERSION,
        "latest_version": None,
        "update_available": False,
        "checked_at": datetime.now(timezone.utc),
        "detail": "",
    }
    if not slug:
        result["detail"] = (
            "آدرس Repository پنل در تنظیمات ← به‌روزرسانی وارد نشده است؛ بررسی نسخه انجام نشد."
        )
        return result
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"https://api.github.com/repos/{slug}/releases/latest", headers=headers)
        if resp.status_code == 404:
            result["detail"] = "این Repository هیچ Release منتشرشده‌ای ندارد."
            return result
        resp.raise_for_status()
        tag = (resp.json() or {}).get("tag_name") or ""
        result["latest_version"] = tag.lstrip("v")
        result["update_available"] = bool(result["latest_version"]) and result["latest_version"] != APP_VERSION
        result["detail"] = "بررسی انجام شد."
    except httpx.HTTPError as exc:
        result["detail"] = f"بررسی نسخه ناموفق بود: {str(exc)[:150]}"
    return result


async def check_agent_updates(db: AsyncSession) -> list[dict]:
    servers = (await db.execute(select(Server))).scalars().all()
    out = []
    for server in servers:
        agent = server.agent
        if not agent or not agent.enrolled:
            continue
        out.append(
            {
                "component": f"agent:{server.name}",
                "current_version": agent.version or "نامشخص",
                "latest_version": APP_VERSION,
                "update_available": (agent.version or "0") != APP_VERSION,
                "checked_at": datetime.now(timezone.utc),
                "detail": "",
            }
        )
    return out


async def update_agent(db: AsyncSession, server: Server, user_id: str | None = None) -> dict:
    """به‌روزرسانی Agent با پشتیبان‌گیری و Health Check و Rollback خودکار در Agent."""
    await add_log(db, source="panel", message=f"شروع به‌روزرسانی Agent روی «{server.name}»", server_id=server.id)
    result = await agent_client.call(
        server, "agent_update", {"target_version": APP_VERSION, "verify_checksum": True}, timeout=180
    )
    healthy = await agent_client.ping(server)
    if not result.ok or not healthy:
        await add_log(
            db,
            source="panel",
            level="error",
            message=f"به‌روزرسانی Agent روی «{server.name}» ناموفق بود: {result.error or 'Agent پاسخ نمی‌دهد'}",
            server_id=server.id,
        )
        return {"ok": False, "error": result.error or "Agent پس از به‌روزرسانی پاسخ نداد."}
    if server.agent:
        server.agent.version = result.data.get("version", APP_VERSION)
    await db.flush()
    return {"ok": True, "version": result.data.get("version", APP_VERSION)}


async def update_panel(db: AsyncSession, user_id: str | None = None) -> dict:
    """پنل روی سرور با اسکریپت update.sh به‌روزرسانی می‌شود؛ اینجا فقط پیش‌نیازها انجام می‌شود."""
    backup = await backup_service.create_backup(db, kind="full", note="پیش از به‌روزرسانی پنل", user_id=user_id)
    info = await check_panel_update(db)
    return {
        "ok": True,
        "backup_id": backup.id,
        "backup_file": backup.filename,
        "update_info": info,
        "next_step": "برای اعمال به‌روزرسانی روی سرور دستور «sudo bash scripts/update.sh» را اجرا کنید.",
    }
