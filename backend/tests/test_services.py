"""تست سرویس‌ها: ترافیک، متریک، هشدار و Mock."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models.server import Server
from app.services import alerting, metrics_service, traffic_service
from app.services.audit import add_log, record_audit


def test_human_bytes():
    assert traffic_service.human_bytes(0) == "0.0 B"
    assert traffic_service.human_bytes(1024) == "1.0 KB"
    assert traffic_service.human_bytes(1024**3) == "1.0 GB"
    assert traffic_service.human_bytes(1.5 * 1024**4) == "1.5 TB"


def test_percent():
    assert metrics_service.percent(50, 100) == 50.0
    assert metrics_service.percent(0, 0) == 0.0
    assert metrics_service.percent(200, 100) == 100.0


def test_range_resolution():
    since, until = traffic_service.resolve_range("today")
    assert since <= until
    since7, _ = traffic_service.resolve_range("7d")
    assert (until - since7) >= timedelta(days=6)


@pytest.mark.asyncio
async def test_traffic_accounting(db):
    server = Server(name="s1", ip_address="10.0.0.1")
    db.add(server)
    await db.flush()
    now = datetime.now(timezone.utc)
    await traffic_service.add_usage(db, "server", server.id, 1000, 2000, now)
    await traffic_service.add_usage(db, "server", server.id, 500, 500, now)
    summary = await traffic_service.summary(db, "server", server.id, "today")
    assert summary["bytes_rx"] == 1500
    assert summary["bytes_tx"] == 2500
    assert summary["bytes_total"] == 4000
    # مقادیر منفی نادیده گرفته می‌شوند
    await traffic_service.add_usage(db, "server", server.id, -100, -100, now)
    summary2 = await traffic_service.summary(db, "server", server.id, "today")
    assert summary2["bytes_total"] == 4000


@pytest.mark.asyncio
async def test_health_score_penalises_offline(db):
    server = Server(name="s2", ip_address="10.0.0.2", status="offline")
    db.add(server)
    await db.flush()
    assert await metrics_service.compute_health_score(db, server) == 0.0
    server.status = "online"
    score = await metrics_service.compute_health_score(db, server)
    assert 0 < score <= 100


@pytest.mark.asyncio
async def test_alert_rule_defaults_created_once(db):
    await alerting.default_rules(db)
    from sqlalchemy import func, select

    from app.db.models.monitoring import AlertRule

    count = (await db.execute(select(func.count()).select_from(AlertRule))).scalar()
    await alerting.default_rules(db)
    count2 = (await db.execute(select(func.count()).select_from(AlertRule))).scalar()
    assert count == count2 > 0


@pytest.mark.asyncio
async def test_audit_masks_secrets(db):
    entry = await record_audit(
        db, action="test", username="tester", payload={"password": "abc", "nested": {"api_token": "xyz"}}
    )
    assert entry.payload["password"] == "***"
    assert entry.payload["nested"]["api_token"] == "***"


@pytest.mark.asyncio
async def test_add_log(db):
    await add_log(db, source="panel", message="پیام تست")
    from sqlalchemy import select

    from app.db.models.ops import LogEntry

    rows = (await db.execute(select(LogEntry))).scalars().all()
    assert rows and rows[0].message == "پیام تست"


def test_mock_disabled_in_production(monkeypatch):
    from app.core.config import Settings

    production = Settings(ENVIRONMENT="production", MOCK_MODE=True, SECRET_KEY="x" * 20)
    assert production.MOCK_MODE is False
    dev = Settings(ENVIRONMENT="development", MOCK_MODE=True, SECRET_KEY="x" * 20)
    assert dev.MOCK_MODE is True
