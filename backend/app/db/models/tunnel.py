"""مدل‌های تونل، نسخه‌های config و قالب‌ها."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk

TUNNEL_STATES = ("draft", "deploying", "deployed", "failed", "stopped", "disabled", "maintenance")
TUNNEL_HEALTH = ("up", "degraded", "down", "unknown")


class TunnelType(Base, UUIDPk, Timestamps):
    """رجیستری انواع تونل. با Adapterهای کد همگام می‌شود."""

    __tablename__ = "tunnel_types"
    key: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    display_name_fa: Mapped[str] = mapped_column(String(120), default="")
    source_kind: Mapped[str] = mapped_column(String(16), default="binary")  # binary | repository
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    binary_path: Mapped[str] = mapped_column(String(255), default="")
    repository_url: Mapped[str] = mapped_column(String(255), default="")
    repository_ref: Mapped[str] = mapped_column(String(120), default="")
    binary_checksum: Mapped[str] = mapped_column(String(128), default="")
    version: Mapped[str] = mapped_column(String(48), default="")
    architectures: Mapped[list] = mapped_column(JSON, default=list)
    notes_fa: Mapped[str] = mapped_column(Text, default="")


class Tunnel(Base, UUIDPk, Timestamps):
    __tablename__ = "tunnels"
    __table_args__ = (Index("ix_tunnels_type_state", "type_key", "state"),)

    name: Mapped[str] = mapped_column(String(120), index=True)
    type_key: Mapped[str] = mapped_column(String(48), index=True)
    source_server_id: Mapped[str] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    destination_server_id: Mapped[str] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    health: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    packet_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    jitter_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # برای کنترل همزمانی (optimistic lock)
    service_name: Mapped[str] = mapped_column(String(120), default="")

    configs: Mapped[list[TunnelConfig]] = relationship(
        back_populates="tunnel",
        cascade="all, delete-orphan",
        order_by="TunnelConfig.revision.desc()",
        lazy="selectin",
    )


class TunnelConfig(Base, UUIDPk, Timestamps):
    """هر تغییر config یک revision جدید می‌سازد (Config Backup خودکار)."""

    __tablename__ = "tunnel_configs"
    tunnel_id: Mapped[str] = mapped_column(ForeignKey("tunnels.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # مقادیر عمومی
    secrets_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # مقادیر حساس، رمزگذاری‌شده
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")

    tunnel: Mapped[Tunnel] = relationship(back_populates="configs", lazy="noload")


class TunnelTemplate(Base, UUIDPk, Timestamps):
    __tablename__ = "tunnel_templates"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    type_key: Mapped[str] = mapped_column(String(48), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
