"""اعلان Webhook با امضای HMAC."""
from __future__ import annotations

import json

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import sign_payload
from app.core.logging import get_logger
from app.services import settings_service
from app.services.notifiers.base import Notifier

log = get_logger("notify.webhook")


class WebhookNotifier(Notifier):
    key = "webhook"

    async def send(self, db: AsyncSession, *, title: str, body: str, severity: str = "info", **kw) -> bool:
        url = await settings_service.get(db, "webhook_url", "")
        if not url or not url.startswith(("http://", "https://")):
            return False
        secret = await settings_service.get(db, "webhook_secret", "") or ""
        payload = {
            "title": title,
            "body": body,
            "severity": severity,
            "kind": kw.get("kind", "alert"),
            "target_type": kw.get("target_type"),
            "target_id": kw.get("target_id"),
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-Alfa-Signature"] = sign_payload(secret, raw)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, content=raw.encode(), headers=headers)
            return 200 <= resp.status_code < 300
        except httpx.HTTPError as exc:  # pragma: no cover
            log.warning("webhook_failed", error=str(exc))
            return False
