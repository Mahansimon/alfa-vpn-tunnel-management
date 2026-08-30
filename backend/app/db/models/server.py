"""مدل‌های سرور، Agent، گروه سرور و رخدادها."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk

SERVER_STATUSES = ("online", "offline", "warning", "maintenance", "pending")


class ServerGroup(Base, UUIDPk, Timestamps):
    __tablename__ = "server_groups"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    color: Mapped[str] = mapped_column(String(16), default="")


class Server(Base, UUIDPk, Timestamps):
    __tablename__ = "servers"
    __table_args__ = (Index("ix_servers_status_country", "status", "country"),)

    name: Mapped[str] = mapped_column(String(120), index=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    private_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(190), nullable=True)
    country: Mapped[str] = mapped_column(String(64), default="", index=True)
    country_code: Mapped[str] = mapped_column(String(4), default="")
    region: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    operating_system: Mapped[str] = mapped_column(String(120), default="")
    kernel: Mapped[str] = mapped_column(String(120), default="")
    architecture: Mapped[str] = mapped_column(String(32), default="")
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    agent_port: Mapped[int] = mapped_column(Integer, default=9443)
    agent_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    group_id: Mapped[str | None] = mapped_column(
        ForeignKey("server_groups.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    health_score: Mapped[float] = mapped_column(Float, default=0.0)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # آخرین اطلاعات کشف‌شده توسط Agent
    cpu_cores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_model: Mapped[str | None] = mapped_column(String(190), nullable=True)
    ram_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    missed_heartbeats: Mapped[int] = mapped_column(Integer, default=0)

    # lazy="selectin" ضروری است: در محیط async دسترسی تنبل به relationship خطا می‌دهد
    agent: Mapped[ServerAgent | None] = relationship(
        back_populates="server", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class ServerAgent(Base, UUIDPk, Timestamps):
    """اطلاعات و اعتبارنامه‌های Agent نصب‌شده روی سرور."""

    __tablename__ = "server_agents"
    server_id: Mapped[str] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), unique=True, index=True
    )
    enrollment_token_hash: Mapped[str] = mapped_column(String(128), index=True)
    enrollment_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled: Mapped[bool] = mapped_column(Boolean, default=False)
    api_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # توکن Agent، رمزگذاری‌شده
    signing_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # کلید امضای درخواست
    token_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_rotate_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="")
    compatible: Mapped[bool] = mapped_column(Boolean, default=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tls_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    server: Mapped[Server] = relationship(back_populates="agent", lazy="noload")


class Event(Base, UUIDPk, Timestamps):
    """Timeline رخدادهای سرور/تونل."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_target_created", "target_type", "target_id", "created_at"),)
    target_type: Mapped[str] = mapped_column(String(16), index=True)  # server | tunnel | panel
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(190))
    detail: Mapped[str] = mapped_column(Text, default="")
