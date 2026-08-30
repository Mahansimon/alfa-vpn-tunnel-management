"""ارتباط Agent با پنل: ثبت‌نام و Heartbeat (فقط با کتابخانه استاندارد)."""
from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.request

from alfa_agent import __version__, metrics
from alfa_agent.actions import capabilities
from alfa_agent.config import AgentConfig, State
from alfa_agent.security import sign

log = logging.getLogger("alfa-agent.client")


class PanelClient:
    def __init__(self, config: AgentConfig, state: State):
        self.config = config
        self.state = state
        self.log_buffer: list[dict] = []

    # ---------- ابزارها ----------
    def _context(self) -> ssl.SSLContext | None:
        if not self.config.panel_url.startswith("https"):
            return None
        context = ssl.create_default_context()
        if not self.config.verify_panel_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def _post(self, path: str, payload: dict, signed: bool = True, timeout: int = 30) -> dict:
        url = f"{self.config.panel_url}/api/v1{path}"
        raw = json.dumps(payload, ensure_ascii=False)
        headers = {"Content-Type": "application/json", "User-Agent": f"alfa-agent/{__version__}"}
        if signed:
            token = self.state.data.get("agent_token", "")
            secret = self.state.data.get("signing_secret", "")
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Alfa-Server-Id"] = self.state.data.get("server_id", "")
            headers["X-Alfa-Signature"] = sign(secret, raw)
        request = urllib.request.Request(url, data=raw.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout, context=self._context()) as response:
            return json.loads(response.read().decode() or "{}")

    # ---------- ثبت‌نام ----------
    def register(self, enrollment_token: str) -> dict:
        payload = {
            "enrollment_token": enrollment_token,
            "system": metrics.system_info(__version__, capabilities()),
        }
        data = self._post("/agent/register", payload, signed=False)
        self.state.set_credentials(data["server_id"], data["agent_token"], data["signing_secret"])
        self.state.data["heartbeat_interval"] = data.get("heartbeat_interval", 15)
        self.state.data["metrics_interval"] = data.get("metrics_interval", 20)
        self.state.data["panel_version"] = data.get("panel_version", "")
        self.state.save()
        log.info("registered server_id=%s", data["server_id"])
        return data

    # ---------- Heartbeat ----------
    def heartbeat(self, tunnel_statuses: list[dict] | None = None) -> dict:
        payload = {
            "agent_version": __version__,
            "metrics": metrics.collect(),
            "tunnels": tunnel_statuses or [],
            "logs": self.log_buffer[-50:],
            "system": metrics.system_info(__version__, capabilities()),
        }
        self.log_buffer.clear()
        try:
            data = self._post("/agent/heartbeat", payload)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            log.warning("heartbeat_rejected status=%s body=%s", exc.code, body)
            raise
        if data.get("rotate_token") and data.get("new_token"):
            self.state.data["agent_token"] = data["new_token"]
            self.state.save()
            log.info("agent token rotated")
        return data

    def buffer_log(self, message: str, level: str = "info", tunnel_id: str | None = None) -> None:
        self.log_buffer.append(
            {"source": "agent", "level": level, "message": message[:2000], "tunnel_id": tunnel_id,
             "ts": time.time()}
        )
