"""معماری کانال‌های اعلان. افزودن کانال جدید = یک کلاس + ثبت در CHANNELS."""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


class Notifier(ABC):
    key: str = "base"

    @abstractmethod
    async def send(self, db: AsyncSession, *, title: str, body: str, severity: str = "info", **kw) -> bool:
        ...

    async def is_enabled(self, db: AsyncSession) -> bool:
        from app.services import settings_service

        channels = await settings_service.get(db, "notify_channels", ["inapp"]) or []
        return self.key in channels
