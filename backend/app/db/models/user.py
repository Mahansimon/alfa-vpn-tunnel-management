"""مدل‌های کاربر، نشست، توکن API و رخدادهای امنیتی."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk


class Role(Base, UUIDPk, Timestamps):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    label_fa: Mapped[str] = mapped_column(String(64), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)


class Permission(Base, UUIDPk, Timestamps):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description_fa: Mapped[str] = mapped_column(String(255), default="")


class RolePermission(Base, UUIDPk, Timestamps):
    __tablename__ = "role_permissions"
    role_name: Mapped[str] = mapped_column(String(32), index=True)
    permission_code: Mapped[str] = mapped_column(String(64), index=True)


class User(Base, UUIDPk, Timestamps):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(190), nullable=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="viewer", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tehran")
    locale: Mapped[str] = mapped_column(String(8), default="fa")
    theme: Mapped[str] = mapped_column(String(16), default="dark")

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )


class UserSession(Base, UUIDPk, Timestamps):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), default="")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="sessions", lazy="noload")


class ApiToken(Base, UUIDPk, Timestamps):
    __tablename__ = "api_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(12), default="")
    permissions_json: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class SecurityEvent(Base, UUIDPk, Timestamps):
    __tablename__ = "security_events"
    __table_args__ = (Index("ix_security_events_kind_created", "kind", "created_at"),)
    kind: Mapped[str] = mapped_column(String(48), index=True)  # failed_login, password_changed, ...
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="info")
