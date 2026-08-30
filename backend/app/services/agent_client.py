"""کلاینت امن ارتباط با Agent.

نکات امنیتی:
- فقط اکشن‌های allowlist‌شده ارسال می‌شوند (هیچ endpoint اجرای شل دلخواه وجود ندارد).
- هر درخواست با HMAC امضا می‌شود (Request Signing) و timestamp دارد (ضد Replay).
- TLS و Bearer Token اجباری است؛ تأیید گواهی از تنظیمات کنترل می‌شود.
- آدرس Agent فقط از رکورد سرور ساخته می‌شود (جلوگیری از SSRF با ورودی کاربر).
"""
from __future__ import annotations

import json
import time
import uuid

import httpx

from app.core.config import settings
from app.core.crypto import decrypt, sign_payload
from app.core.errors import AgentUnreachable, Forbidden
from app.core.logging import get_logger

log = get_logger("agent")

ALLOWED_ACTIONS: set[str] = {
    "ping",
    "system_info",
    "metrics",
    "service_start",
    "service_stop",
    "service_restart",
    "service_status",
    "tunnel_install",
    "tunnel_configure",
    "tunnel_remove",
    "tunnel_update",
    "tunnel_start",
    "tunnel_stop",
    "tunnel_restart",
    "tunnel_status",
    "tunnel_logs",
    "tunnel_metrics",
    "tunnel_health",
    "tunnel_rollback",
    "logs",
    "dependency_check",
    "firewall_plan",
    "agent_update",
    "agent_logs",
    "binary_install",
    "latency_probe",
}


class AgentResult(dict):
    """نتیجه اجرای اکشن روی Agent."""

    @property
    def ok(self) -> bool:
        return bool(self.get("ok"))

    @property
    def output(self) -> str:
        return str(self.get("output", ""))

    @property
    def error(self) -> str:
        return str(self.get("error", ""))

    @property
    def data(self) -> dict:
        return self.get("data") or {}


class AgentClient:
    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or settings.AGENT_REQUEST_TIMEOUT

    @staticmethod
    def base_url(server) -> str:
        scheme = "https" if getattr(server, "agent_use_tls", True) else "http"
        return f"{scheme}://{server.ip_address}:{server.agent_port}"

    @staticmethod
    def _credentials(server) -> tuple[str, str]:
        agent = getattr(server, "agent", None)
        if not agent or not agent.api_token_enc:
            raise AgentUnreachable("Agent روی این سرور ثبت نشده است. ابتدا Agent را نصب کنید.")
        return decrypt(agent.api_token_enc) or "", decrypt(agent.signing_secret_enc) or ""

    async def call(self, server, action: str, params: dict | None = None, timeout: int | None = None):
        if action not in ALLOWED_ACTIONS:
            raise Forbidden(f"اکشن «{action}» مجاز نیست.")
        token, secret = self._credentials(server)
        request_id = uuid.uuid4().hex
        body = {"action": action, "params": params or {}, "request_id": request_id, "ts": int(time.time())}
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Alfa-Signature": sign_payload(secret, raw),
            "X-Alfa-Request-Id": request_id,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url(server)}/v1/actions"
        try:
            async with httpx.AsyncClient(
                timeout=timeout or self.timeout, verify=settings.AGENT_TLS_VERIFY
            ) as client:
                resp = await client.post(url, content=raw.encode(), headers=headers)
        except httpx.HTTPError as exc:
            log.warning("agent_unreachable", server=server.id, action=action, error=str(exc))
            raise AgentUnreachable(
                f"ارتباط با Agent سرور «{server.name}» برقرار نشد: بررسی کنید سرویس alfa-agent فعال و "
                f"پورت {server.agent_port} باز باشد."
            ) from exc
        if resp.status_code == 401:
            raise AgentUnreachable("توکن Agent معتبر نیست. Agent را دوباره ثبت (register) کنید.")
        if resp.status_code >= 500:
            raise AgentUnreachable(f"Agent خطای داخلی داد (کد {resp.status_code}).")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AgentUnreachable("پاسخ Agent قابل خواندن نبود.") from exc
        return AgentResult(payload)

    async def ping(self, server) -> bool:
        try:
            result = await self.call(server, "ping", timeout=6)
            return result.ok
        except AgentUnreachable:
            return False


agent_client = AgentClient()
