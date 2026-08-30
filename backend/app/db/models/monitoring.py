"""مدل‌های متریک، ترافیک، هشدار و اعلان."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk


class Metric(Base, UUIDPk):
    """متریک خام. با Retention کوتاه نگه داشته می‌شود."""

    __tablename__ = "metrics"
    __table_args__ = (Index("ix_metrics_server_ts", "server_id", "ts"),)

    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cpu_percent: Mapped[float] = mapped_column(Float, default=0)
    load_1: Mapped[float] = mapped_column(Float, default=0)
    load_5: Mapped[float] = mapped_column(Float, default=0)
    load_15: Mapped[float] = mapped_column(Float, default=0)
    ram_total: Mapped[int] = mapped_column(BigInteger, default=0)
    ram_used: Mapped[int] = mapped_column(BigInteger, default=0)
    swap_total: Mapped[int] = mapped_column(BigInteger, default=0)
    swap_used: Mapped[int] = mapped_column(BigInteger, default=0)
    disk_total: Mapped[int] = mapped_column(BigInteger, default=0)
    disk_used: Mapped[int] = mapped_column(BigInteger, default=0)
    net_rx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    net_tx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    net_rx_rate: Mapped[float] = mapped_column(Float, default=0)
    net_tx_rate: Mapped[float] = mapped_column(Float, default=0)
    packets_rx_rate: Mapped[float] = mapped_column(Float, default=0)
    packets_tx_rate: Mapped[float] = mapped_column(Float, default=0)
    uptime_seconds: Mapped[int] = mapped_column(BigInteger, default=0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class MetricAggregate(Base, UUIDPk):
    """متریک تجمیع‌شده (ساعتی/روزانه) برای نمودارهای بازه بلند."""

    __tablename__ = "metric_aggregates"
    __table_args__ = (
        Index("ix_metric_agg_server_bucket", "server_id", "bucket", "period", unique=True),
    )
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(8), default="hour")  # hour | day
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cpu_avg: Mapped[float] = mapped_column(Float, default=0)
    cpu_max: Mapped[float] = mapped_column(Float, default=0)
    ram_avg: Mapped[float] = mapped_column(Float, default=0)
    disk_avg: Mapped[float] = mapped_column(Float, default=0)
    rx_rate_avg: Mapped[float] = mapped_column(Float, default=0)
    tx_rate_avg: Mapped[float] = mapped_column(Float, default=0)
    samples: Mapped[int] = mapped_column(Integer, default=0)


class TrafficRecord(Base, UUIDPk):
    """حساب‌داری ترافیک به تفکیک سرور/تونل و بازه زمانی."""

    __tablename__ = "traffic_records"
    __table_args__ = (
        Index("ix_traffic_scope_bucket", "scope", "scope_id", "bucket", "period", unique=True),
    )
    scope: Mapped[str] = mapped_column(String(8), index=True)  # server | tunnel
    scope_id: Mapped[str] = mapped_column(String(32), index=True)
    period: Mapped[str] = mapped_column(String(8), default="hour")  # hour | day
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bytes_rx: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_tx: Mapped[int] = mapped_column(BigInteger, default=0)


class AlertRule(Base, UUIDPk, Timestamps):
    __tablename__ = "alert_rules"
    name: Mapped[str] = mapped_column(String(120))
    metric: Mapped[str] = mapped_column(String(48))  # cpu_percent, ram_percent, disk_percent, latency_ms...
    operator: Mapped[str] = mapped_column(String(4), default=">")  # > | < | >= | <= | ==
    threshold: Mapped[float] = mapped_column(Float, default=90)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=300)
    target_type: Mapped[str] = mapped_column(String(16), default="server")  # server | tunnel | any
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)  # inapp | email | telegram | webhook
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=900)


class Alert(Base, UUIDPk, Timestamps):
    """نمونه فعال/بسته‌شده یک قاعده هشدار (برای Deduplication و Recovery)."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_state_rule", "state", "rule_id"),)
    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True
    )
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(16), default="server")
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="firing", index=True)  # firing | resolved
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    title: Mapped[str] = mapped_column(String(190))
    message: Mapped[str] = mapped_column(Text, default="")
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    breach_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base, UUIDPk, Timestamps):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_read_created", "read", "created_at"),)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(190))
    body: Mapped[str] = mapped_column(Text, default="")
    target_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
