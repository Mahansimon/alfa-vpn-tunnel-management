"""ساخت اولیه کل Schema پنل

Revision ID: 0001
Revises:
Create Date: 2026-01-01

این migration کل جداول پایه را از روی متادیتای مدل‌ها می‌سازد. به این ترتیب
هیچ اختلافی بین مدل‌ها و دیتابیس در نصب تازه وجود ندارد. تغییرات بعدی باید
به صورت migrationهای جداگانه و صریح اضافه شوند.
"""
from __future__ import annotations

from alembic import op

from app.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES = [
    "roles",
    "permissions",
    "role_permissions",
    "users",
    "sessions",
    "api_tokens",
    "security_events",
    "server_groups",
    "servers",
    "server_agents",
    "events",
    "tunnel_types",
    "tunnels",
    "tunnel_configs",
    "tunnel_templates",
    "metrics",
    "metric_aggregates",
    "traffic_records",
    "alert_rules",
    "alerts",
    "notifications",
    "audit_logs",
    "deployments",
    "deployment_logs",
    "jobs",
    "settings",
    "backups",
    "log_entries",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
