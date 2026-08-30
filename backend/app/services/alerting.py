"""ارزیابی قواعد هشدار با Deduplication، Cooldown و اعلان Recovery."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.monitoring import Alert, AlertRule
from app.db.models.server import Server
from app.db.models.tunnel import Tunnel
from app.services import metrics_service, settings_service
from app.services.audit import record_event
from app.services.notifiers import dispatch

OPERATORS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: abs(a - b) < 1e-9,
}

SERVER_METRICS = {"cpu_percent", "ram_percent", "disk_percent", "load_1", "rx_rate", "tx_rate"}
TUNNEL_METRICS = {"latency_ms", "packet_loss", "jitter_ms"}


def fingerprint(rule_id: str, target_type: str, target_id: str | None) -> str:
    return hashlib.sha256(f"{rule_id}:{target_type}:{target_id}".encode()).hexdigest()[:32]


async def _server_value(db: AsyncSession, server: Server, metric: str) -> float | None:
    if metric == "status_offline":
        return 1.0 if server.status == "offline" else 0.0
    latest = await metrics_service.latest_metric(db, server.id)
    if latest is None:
        return None
    mapping = {
        "cpu_percent": latest.cpu_percent,
        "ram_percent": metrics_service.percent(latest.ram_used, latest.ram_total),
        "disk_percent": metrics_service.percent(latest.disk_used, latest.disk_total),
        "load_1": latest.load_1,
        "rx_rate": latest.net_rx_rate,
        "tx_rate": latest.net_tx_rate,
    }
    return mapping.get(metric)


def _tunnel_value(tunnel: Tunnel, metric: str) -> float | None:
    if metric == "tunnel_down":
        return 1.0 if tunnel.health == "down" else 0.0
    return {
        "latency_ms": tunnel.latency_ms,
        "packet_loss": tunnel.packet_loss,
        "jitter_ms": tunnel.jitter_ms,
    }.get(metric)


async def evaluate(db: AsyncSession) -> int:
    """همه قواعد فعال را ارزیابی می‌کند. خروجی: تعداد هشدارهای تغییر وضعیت داده."""
    rules = (await db.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))).scalars().all()
    if not rules:
        return 0
    servers = (await db.execute(select(Server))).scalars().all()
    tunnels = (await db.execute(select(Tunnel))).scalars().all()
    now = datetime.now(timezone.utc)
    changes = 0

    for rule in rules:
        targets: list[tuple[str, object]] = []
        if rule.target_type in ("server", "any"):
            targets += [("server", s) for s in servers if rule.target_id in (None, "", s.id)]
        if rule.target_type in ("tunnel", "any"):
            targets += [("tunnel", t) for t in tunnels if rule.target_id in (None, "", t.id)]

        for target_type, target in targets:
            if target_type == "server":
                if rule.metric not in SERVER_METRICS | {"status_offline"}:
                    continue
                if target.maintenance:
                    continue
                value = await _server_value(db, target, rule.metric)
                label = target.name
            else:
                if rule.metric not in TUNNEL_METRICS | {"tunnel_down"}:
                    continue
                if target.maintenance:
                    continue
                value = _tunnel_value(target, rule.metric)
                label = target.name
            if value is None:
                continue

            breached = OPERATORS[rule.operator](float(value), float(rule.threshold))
            fp = fingerprint(rule.id, target_type, target.id)
            alert = (
                await db.execute(
                    select(Alert).where(Alert.fingerprint == fp, Alert.state == "firing").limit(1)
                )
            ).scalar_one_or_none()

            if breached:
                if alert is None:
                    alert = Alert(
                        rule_id=rule.id,
                        fingerprint=fp,
                        target_type=target_type,
                        target_id=target.id,
                        state="firing",
                        severity=rule.severity,
                        title=f"{rule.name} — {label}",
                        message=f"مقدار {rule.metric} برابر {round(float(value), 2)} است "
                        f"(حد آستانه {rule.operator} {rule.threshold}).",
                        value=float(value),
                        breach_since=now,
                    )
                    db.add(alert)
                    await db.flush()
                    changes += 1
                else:
                    alert.value = float(value)
                # فقط بعد از سپری شدن duration و با رعایت cooldown اعلان بفرست
                elapsed = (now - (alert.breach_since or now)).total_seconds()
                cooled = (
                    alert.last_notified_at is None
                    or (now - alert.last_notified_at).total_seconds() >= rule.cooldown_seconds
                )
                if elapsed >= rule.duration_seconds and cooled:
                    await dispatch(
                        db,
                        title=alert.title,
                        body=alert.message,
                        severity=rule.severity,
                        channels=rule.channels or ["inapp"],
                        kind="alert",
                        target_type=target_type,
                        target_id=target.id,
                    )
                    alert.last_notified_at = now
                    await record_event(
                        db,
                        target_type=target_type,
                        target_id=target.id,
                        kind="alert_fired",
                        title=alert.title,
                        detail=alert.message,
                        severity=rule.severity,
                    )
            elif alert is not None:
                alert.state = "resolved"
                alert.resolved_at = now
                changes += 1
                await dispatch(
                    db,
                    title=f"رفع شد: {alert.title}",
                    body="مقدار به محدوده مجاز بازگشت.",
                    severity="info",
                    channels=rule.channels or ["inapp"],
                    kind="alert_recovered",
                    target_type=target_type,
                    target_id=target.id,
                )
    await db.flush()
    return changes


async def default_rules(db: AsyncSession) -> None:
    """قواعد پیش‌فرض منطقی (فقط اگر هیچ قاعده‌ای وجود نداشته باشد)."""
    count = len((await db.execute(select(AlertRule))).scalars().all())
    if count:
        return
    presets = [
        ("مصرف بالای CPU", "cpu_percent", ">", 90, 300, "warning"),
        ("مصرف بالای RAM", "ram_percent", ">", 90, 300, "warning"),
        ("پرشدن دیسک", "disk_percent", ">", 85, 600, "critical"),
        ("سرور آفلاین", "status_offline", "==", 1, 0, "critical"),
    ]
    for name, metric, op, threshold, duration, severity in presets:
        db.add(
            AlertRule(
                name=name,
                metric=metric,
                operator=op,
                threshold=threshold,
                duration_seconds=duration,
                target_type="server",
                severity=severity,
                channels=await settings_service.get(db, "notify_channels", ["inapp"]),
            )
        )
    db.add(
        AlertRule(
            name="تونل قطع شده",
            metric="tunnel_down",
            operator="==",
            threshold=1,
            duration_seconds=60,
            target_type="tunnel",
            severity="critical",
            channels=["inapp"],
        )
    )
    await db.flush()


async def cleanup_resolved(db: AsyncSession, days: int = 30) -> int:
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    res = await db.execute(delete(Alert).where(Alert.state == "resolved", Alert.resolved_at < cutoff))
    return res.rowcount or 0
