"""اعلان ایمیلی با SMTP. تنظیمات از صفحه Settings خوانده می‌شود."""
from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services import settings_service
from app.services.notifiers.base import Notifier

log = get_logger("notify.email")


class EmailNotifier(Notifier):
    key = "email"

    async def send(self, db: AsyncSession, *, title: str, body: str, severity: str = "info", **kw) -> bool:
        host = await settings_service.get(db, "smtp_host", "")
        sender = await settings_service.get(db, "smtp_from", "")
        recipient = kw.get("to") or sender
        if not host or not sender or not recipient:
            return False
        port = int(await settings_service.get(db, "smtp_port", 587) or 587)
        user = await settings_service.get(db, "smtp_user", "") or ""
        password = await settings_service.get(db, "smtp_password", "") or ""

        message = EmailMessage()
        message["Subject"] = f"[{severity.upper()}] {title}"
        message["From"] = sender
        message["To"] = recipient
        message.set_content(body or title)

        def _send() -> bool:
            try:
                with smtplib.SMTP(host, port, timeout=20) as smtp:
                    smtp.starttls()
                    if user:
                        smtp.login(user, password)
                    smtp.send_message(message)
                return True
            except Exception as exc:  # pragma: no cover - وابسته به شبکه
                log.warning("email_failed", error=str(exc))
                return False

        return await asyncio.to_thread(_send)
