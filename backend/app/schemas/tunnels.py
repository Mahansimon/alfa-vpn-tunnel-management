"""اسکیماهای تونل."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TunnelTypeOut(BaseModel):
    key: str
    display_name: str
    display_name_fa: str
    source_kind: str  # binary | repository
    configured: bool
    requires: list[str] = []
    capabilities: list[str] = []
    config_schema: list[dict[str, Any]] = []
    notes_fa: str = ""
    version: str = ""


class TunnelTypeConfigure(BaseModel):
    """محل ورود مسیر Binary یا آدرس Repository هر تونل."""

    binary_path: str | None = None
    repository_url: str | None = None
    repository_ref: str | None = None
    binary_checksum: str | None = None
    version: str | None = None
    notes_fa: str | None = None


class TunnelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type_key: str
    source_server_id: str
    destination_server_id: str
    config: dict[str, Any] = {}
    secrets: dict[str, str] = {}
    tags: list[str] = []
    description: str = ""
    deploy_now: bool = False
    dry_run: bool = False


class TunnelUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    secrets: dict[str, str] | None = None
    tags: list[str] | None = None
    description: str | None = None
    enabled: bool | None = None
    maintenance: bool | None = None
    version: int | None = None  # برای کنترل تضاد همزمانی


class TunnelOut(ORMModel):
    id: str
    name: str
    type_key: str
    source_server_id: str
    destination_server_id: str
    state: str
    health: str
    enabled: bool
    maintenance: bool
    tags: list = []
    description: str
    latency_ms: float | None
    packet_loss: float | None
    jitter_ms: float | None
    uptime_seconds: int | None
    last_health_at: datetime | None
    version: int
    service_name: str
    created_at: datetime
    config: dict[str, Any] = {}
    source_server_name: str | None = None
    destination_server_name: str | None = None


class TunnelValidateResult(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {}


class TunnelTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type_key: str
    payload: dict[str, Any] = {}
    description: str = ""


class TunnelTemplateOut(ORMModel):
    id: str
    name: str
    type_key: str
    payload: dict
    description: str
    created_at: datetime


class TopologyNode(BaseModel):
    id: str
    label: str
    kind: str = "server"
    country: str = ""
    status: str = "offline"
    health_score: float = 0
    tunnels: int = 0


class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    type_key: str
    health: str
    state: str
    latency_ms: float | None = None
    bytes_total: int = 0


class TopologyOut(BaseModel):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
