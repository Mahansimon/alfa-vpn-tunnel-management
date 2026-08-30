"""مدل‌های عملیاتی: Audit، Deployment، Job، Setting، Backup و Log."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk


class AuditLog(Base, UUIDPk, Timestamps):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_action_created", "action", "created_at"),)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64), index=True)
    server_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tunnel_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    target: Mapped[str] = mapped_column(String(190), default="")
    result: Mapped[str] = mapped_column(String(16), default="success")  # success | failure
    error: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Deployment(Base, UUIDPk, Timestamps):
    __tablename__ = "deployments"
    __table_args__ = (Index("ix_deploy_status_created", "status", "created_at"),)
    kind: Mapped[str] = mapped_column(String(32), default="tunnel_install")
    tunnel_id: Mapped[str | None] = mapped_column(
        ForeignKey("tunnels.id", ondelete="SET NULL"), nullable=True, index=True
    )
    server_id: Mapped[str | None] = mapped_column(
        ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending | running | success | failed | rolled_back | cancelled
    phase: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rollback_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class DeploymentLog(Base, UUIDPk):
    __tablename__ = "deployment_logs"
    __table_args__ = (Index("ix_deploy_logs_dep_seq", "deployment_id", "seq"),)
    deployment_id: Mapped[str] = mapped_column(ForeignKey("deployments.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text, default="")


class Job(Base, UUIDPk, Timestamps):
    """کارهای پس‌زمینه طولانی: build، install، backup، update."""

    __tablename__ = "jobs"
    kind: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    # queued | running | success | failed | cancelled | timeout
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Setting(Base, UUIDPk, Timestamps):
    """تنظیمات runtime پنل. مقادیر حساس رمزگذاری می‌شوند."""

    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(32), default="general")
    description_fa: Mapped[str] = mapped_column(String(255), default="")


class Backup(Base, UUIDPk, Timestamps):
    __tablename__ = "backups"
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(24), default="full")  # full | database | config
    encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    panel_version: Mapped[str] = mapped_column(String(32), default="")
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")


class LogEntry(Base, UUIDPk):
    """لاگ‌های جمع‌آوری‌شده از Agent/تونل/پنل برای نمایش در Log Viewer."""

    __tablename__ = "log_entries"
    __table_args__ = (Index("ix_logs_source_ts", "source", "ts"),)
    server_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tunnel_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(24), index=True)  # system | agent | tunnel | panel | deploy
    level: Mapped[str] = mapped_column(String(16), default="info", index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
