"""اعلان داخل پنل (Notification Center)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import push_notification
from app.services.notifiers.base import Notifier


class InAppNotifier(Notifier):
    key = "inapp"

    async def send(self, db: AsyncSession, *, title: str, body: str, severity: str = "info", **kw) -> bool:
        await push_notification(
            db,
            kind=kw.get("kind", "alert"),
            title=title,
            body=body,
            severity=severity,
            target_type=kw.get("target_type"),
            target_id=kw.get("target_id"),
        )
        return True
