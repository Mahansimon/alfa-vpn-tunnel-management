"""پیکربندی Agent.

مقادیر از فایل /etc/alfa-agent/agent.env و وضعیت ثبت‌نام از
/var/lib/alfa-agent/state.json خوانده می‌شوند. هیچ مقداری hard-code نیست.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

ENV_FILE = os.environ.get("ALFA_AGENT_ENV", "/etc/alfa-agent/agent.env")
STATE_FILE = os.environ.get("ALFA_AGENT_STATE", "/var/lib/alfa-agent/state.json")
DEFAULT_DIRS = {
    "config": "/etc/alfa-agent",
    "state": "/var/lib/alfa-agent",
    "tunnels": "/etc/alfa/tunnels",
    "binaries": "/opt/alfa/tunnel-binaries",
    "build": "/var/lib/alfa-agent/build",
    "backup": "/var/lib/alfa-agent/backup",
    "logs": "/var/log/alfa-agent",
}


def _read_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass
class AgentConfig:
    panel_url: str = ""
    listen_host: str = "0.0.0.0"
    listen_port: int = 9443
    tls_cert: str = "/etc/alfa-agent/tls/agent.crt"
    tls_key: str = "/etc/alfa-agent/tls/agent.key"
    use_tls: bool = True
    heartbeat_interval: int = 15
    metrics_interval: int = 20
    log_level: str = "INFO"
    verify_panel_tls: bool = False
    dirs: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_DIRS))

    @classmethod
    def load(cls) -> AgentConfig:
        env = {**_read_env_file(ENV_FILE), **os.environ}
        return cls(
            panel_url=env.get("PANEL_URL", "").rstrip("/"),
            listen_host=env.get("AGENT_HOST", "0.0.0.0"),
            listen_port=int(env.get("AGENT_PORT", "9443")),
            tls_cert=env.get("AGENT_TLS_CERT", "/etc/alfa-agent/tls/agent.crt"),
            tls_key=env.get("AGENT_TLS_KEY", "/etc/alfa-agent/tls/agent.key"),
            use_tls=env.get("AGENT_USE_TLS", "true").lower() != "false",
            heartbeat_interval=int(env.get("HEARTBEAT_INTERVAL", "15")),
            metrics_interval=int(env.get("METRICS_INTERVAL", "20")),
            log_level=env.get("LOG_LEVEL", "INFO"),
            verify_panel_tls=env.get("VERIFY_PANEL_TLS", "false").lower() == "true",
            dirs={key: env.get(f"DIR_{key.upper()}", value) for key, value in DEFAULT_DIRS.items()},
        )


class State:
    """وضعیت ثبت‌نام Agent (server_id، توکن و کلید امضا)."""

    def __init__(self, path: str = STATE_FILE):
        self.path = path
        self.data: dict = {}
        self.load()

    def load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as handle:
                    self.data = json.load(handle)
            except (OSError, ValueError):
                self.data = {}
        return self.data

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    @property
    def registered(self) -> bool:
        return bool(self.data.get("server_id") and self.data.get("agent_token"))

    def set_credentials(self, server_id: str, token: str, signing_secret: str) -> None:
        self.data.update(
            {"server_id": server_id, "agent_token": token, "signing_secret": signing_secret}
        )
        self.save()
