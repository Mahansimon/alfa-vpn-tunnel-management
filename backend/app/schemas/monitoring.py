"""اسکیماهای متریک، ترافیک، هشدار، اعلان و سلامت."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MetricPoint(BaseModel):
    ts: datetime
    cpu_percent: float = 0
    ram_percent: float = 0
    disk_percent: float = 0
    rx_rate: float = 0
    tx_rate: float = 0
    packets_rx_rate: float = 0
    packets_tx_rate: float = 0
    load_1: float = 0


class ServerMetricsOut(BaseModel):
    server_id: str
    range: str
    points: list[MetricPoint]
    latest: dict[str, Any] = {}


class TrafficPoint(BaseModel):
    bucket: datetime
    bytes_rx: int = 0
    bytes_tx: int = 0


class TrafficSummary(BaseModel):
    scope: str
    scope_id: str | None = None
    bytes_rx: int = 0
    bytes_tx: int = 0
    bytes_total: int = 0
    points: list[TrafficPoint] = []


class DashboardOut(BaseModel):
    servers_total: int = 0
    servers_online: int = 0
    servers_offline: int = 0
    servers_warning: int = 0
    tunnels_total: int = 0
    tunnels_active: int = 0
    tunnels_failed: int = 0
    tunnels_degraded: int = 0
    cpu_avg: float = 0
    ram_avg: float = 0
    disk_avg: float = 0
    rx_rate: float = 0
    tx_rate: float = 0
    traffic_today_bytes: int = 0
    traffic_month_bytes: int = 0
    panel_uptime_seconds: int = 0
    health_score: float = 0
    unread_notifications: int = 0
    mock_mode: bool = False
    traffic_series: list[TrafficPoint] = []
    top_servers: list[dict[str, Any]] = []
    tunnel_health_breakdown: dict[str, int] = {}


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    metric: str
    operator: str = Field(default=">", pattern="^(>|<|>=|<=|==)$")
    threshold: float
    duration_seconds: int = Field(default=300, ge=0, le=86400)
    target_type: str = Field(default="server", pattern="^(server|tunnel|any)$")
    target_id: str | None = None
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    enabled: bool = True
    channels: list[str] = ["inapp"]
    cooldown_seconds: int = Field(default=900, ge=60, le=86400)


class AlertRuleOut(ORMModel):
    id: str
    name: str
    metric: str
    operator: str
    threshold: float
    duration_seconds: int
    target_type: str
    target_id: str | None
    severity: str
    enabled: bool
    channels: list
    cooldown_seconds: int
    created_at: datetime


class AlertOut(ORMModel):
    id: str
    rule_id: str | None
    target_type: str
    target_id: str | None
    state: str
    severity: str
    title: str
    message: str
    value: float | None
    breach_since: datetime | None
    resolved_at: datetime | None
    created_at: datetime


class NotificationOut(ORMModel):
    id: str
    kind: str
    severity: str
    title: str
    body: str
    target_type: str | None
    target_id: str | None
    read: bool
    created_at: datetime


class LogEntryOut(ORMModel):
    id: str
    server_id: str | None
    tunnel_id: str | None
    source: str
    level: str
    ts: datetime
    message: str


class HealthComponent(BaseModel):
    name: str
    status: str  # ok | degraded | down | unknown
    detail: str = ""
    latency_ms: float | None = None


class HealthOverview(BaseModel):
    status: str
    components: list[HealthComponent]
    panel_version: str
    checked_at: datetime


class SecurityOverview(BaseModel):
    https_enabled: bool
    two_factor_users: int
    total_users: int
    weak_password_users: int
    outdated_agents: int
    failed_logins_24h: int
    score: int
    findings: list[dict[str, Any]] = []
