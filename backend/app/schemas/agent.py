"""اسکیماهای پروتکل Agent (سمت پنل)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentSystemInfo(BaseModel):
    hostname: str = ""
    os: str = ""
    kernel: str = ""
    architecture: str = ""
    cpu_cores: int = 0
    cpu_model: str = ""
    ram_total: int = 0
    disk_total: int = 0
    public_ip: str = ""
    private_ip: str = ""
    uptime_seconds: int = 0
    agent_version: str = ""
    capabilities: list[str] = []


class AgentRegisterRequest(BaseModel):
    enrollment_token: str = Field(min_length=10)
    system: AgentSystemInfo


class AgentRegisterResponse(BaseModel):
    server_id: str
    agent_token: str
    signing_secret: str
    heartbeat_interval: int
    metrics_interval: int
    panel_version: str
    rotate_after: datetime | None = None


class AgentMetricsPayload(BaseModel):
    ts: datetime
    cpu_percent: float = 0
    load: list[float] = [0, 0, 0]
    ram_total: int = 0
    ram_used: int = 0
    swap_total: int = 0
    swap_used: int = 0
    disk_total: int = 0
    disk_used: int = 0
    net_rx_bytes: int = 0
    net_tx_bytes: int = 0
    net_rx_rate: float = 0
    net_tx_rate: float = 0
    packets_rx_rate: float = 0
    packets_tx_rate: float = 0
    uptime_seconds: int = 0


class AgentTunnelStatus(BaseModel):
    tunnel_id: str
    running: bool = False
    health: str = "unknown"
    latency_ms: float | None = None
    packet_loss: float | None = None
    jitter_ms: float | None = None
    uptime_seconds: int | None = None
    bytes_rx: int = 0
    bytes_tx: int = 0
    detail: str = ""


class AgentHeartbeat(BaseModel):
    agent_version: str = ""
    metrics: AgentMetricsPayload | None = None
    tunnels: list[AgentTunnelStatus] = []
    logs: list[dict[str, Any]] = []
    system: AgentSystemInfo | None = None


class AgentHeartbeatResponse(BaseModel):
    ok: bool = True
    server_status: str
    rotate_token: bool = False
    new_token: str | None = None
    pending_actions: list[dict[str, Any]] = []
    metrics_interval: int
    heartbeat_interval: int


class AgentActionRequest(BaseModel):
    """درخواستی که پنل به Agent می‌فرستد. فقط اکشن‌های allowlist‌شده."""

    action: str
    params: dict[str, Any] = {}
    request_id: str = ""
    timeout: int = 120


class AgentActionResult(BaseModel):
    ok: bool
    action: str
    output: str = ""
    error: str = ""
    data: dict[str, Any] = {}
    duration_ms: int = 0
