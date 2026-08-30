"""اعلان تلگرام."""
from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services import settings_service
from app.services.notifiers.base import Notifier

log = get_logger("notify.telegram")


class TelegramNotifier(Notifier):
    key = "telegram"

    async def send(self, db: AsyncSession, *, title: str, body: str, severity: str = "info", **kw) -> bool:
        token = await settings_service.get(db, "telegram_bot_token", "")
        chat_id = await settings_service.get(db, "telegram_chat_id", "")
        if not token or not chat_id:
            return False
        icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}.get(severity, "ℹ️")
        text = f"{icon} <b>{title}</b>\n{body}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                )
            return resp.status_code == 200
        except httpx.HTTPError as exc:  # pragma: no cover
            log.warning("telegram_failed", error=str(exc))
            return False
