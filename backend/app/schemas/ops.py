"""اسکیماهای Audit، Deployment، Job، Setting و Backup."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AuditLogOut(ORMModel):
    id: str
    username: str
    user_id: str | None
    action: str
    server_id: str | None
    tunnel_id: str | None
    target: str
    result: str
    error: str
    ip: str | None
    created_at: datetime


class DeploymentLogOut(ORMModel):
    seq: int
    ts: datetime
    level: str
    message: str


class DeploymentOut(ORMModel):
    id: str
    kind: str
    tunnel_id: str | None
    server_id: str | None
    status: str
    phase: str
    progress: int
    dry_run: bool
    started_at: datetime | None
    finished_at: datetime | None
    error: str
    created_at: datetime


class DeploymentDetail(DeploymentOut):
    logs: list[DeploymentLogOut] = []


class JobOut(ORMModel):
    id: str
    kind: str
    status: str
    progress: int
    attempts: int
    error: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class SettingOut(BaseModel):
    key: str
    value: Any = None
    category: str = "general"
    is_secret: bool = False
    description_fa: str = ""


class SettingsUpdate(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class BackupOut(ORMModel):
    id: str
    filename: str
    size_bytes: int
    kind: str
    encrypted: bool
    checksum: str
    panel_version: str
    note: str
    created_at: datetime


class BackupCreate(BaseModel):
    kind: str = Field(default="full", pattern="^(full|database|config)$")
    note: str = ""


class RestoreRequest(BaseModel):
    backup_id: str
    confirm: bool = False
    backup_current_state: bool = True


class VersionInfo(BaseModel):
    panel: str
    backend: str
    frontend: str
    agent_min: str
    database: str
    environment: str


class UpdateCheckOut(BaseModel):
    component: str
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    checked_at: datetime
    detail: str = ""
