"""ایندکس‌های تکمیلی برای کوئری‌های سنگین

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_metrics_ts_only", "metrics", "ts DESC"),
    ("ix_traffic_bucket_scope", "traffic_records", "bucket, scope"),
    ("ix_tunnels_health_state", "tunnels", "health, state"),
    ("ix_audit_user_created", "audit_logs", "user_id, created_at DESC"),
    ("ix_logs_level_ts", "log_entries", "level, ts DESC"),
    ("ix_notifications_user_read", "notifications", "user_id, read"),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")


def downgrade() -> None:
    for name, _table, _columns in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
