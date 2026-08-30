"""اسکیماهای سرور و Agent."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, IPvAnyAddress, field_validator

from app.schemas.common import ORMModel


class ServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ip_address: str
    country: str = ""
    country_code: str = ""
    region: str = ""
    provider: str = ""
    operating_system: str = ""
    ssh_port: int = Field(default=22, ge=1, le=65535)
    agent_port: int = Field(default=9443, ge=1, le=65535)
    agent_use_tls: bool = True
    tags: list[str] = []
    description: str = ""
    group_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("ip_address")
    @classmethod
    def _valid_ip(cls, v: str) -> str:
        IPvAnyAddress(v)  # اعتبارسنجی؛ در صورت نامعتبر بودن خطا می‌دهد
        return v


class ServerUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    provider: str | None = None
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    agent_port: int | None = Field(default=None, ge=1, le=65535)
    agent_use_tls: bool | None = None
    tags: list[str] | None = None
    description: str | None = None
    group_id: str | None = None
    maintenance: bool | None = None
    latitude: float | None = None
    longitude: float | None = None


class AgentInfo(ORMModel):
    enrolled: bool = False
    version: str = ""
    compatible: bool = True
    last_heartbeat_at: datetime | None = None
    capabilities: list = []


class ServerOut(ORMModel):
    id: str
    name: str
    ip_address: str
    private_ip: str | None = None
    hostname: str | None = None
    country: str
    country_code: str
    region: str
    provider: str
    operating_system: str
    kernel: str
    architecture: str
    ssh_port: int
    agent_port: int
    tags: list = []
    description: str
    group_id: str | None
    status: str
    maintenance: bool
    health_score: float
    cpu_cores: int | None
    cpu_model: str | None
    ram_total_bytes: int | None
    disk_total_bytes: int | None
    uptime_seconds: int | None
    last_seen_at: datetime | None
    latitude: float | None
    longitude: float | None
    created_at: datetime
    agent: AgentInfo | None = None


class ServerCreated(BaseModel):
    server: ServerOut
    enrollment_token: str  # فقط یک بار نمایش داده می‌شود
    install_command: str


class ServerGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    color: str = ""


class ServerGroupOut(ORMModel):
    id: str
    name: str
    description: str
    color: str


class EnrollmentTokenOut(BaseModel):
    enrollment_token: str
    install_command: str
    expires_at: datetime | None = None
