"""Mock/Demo Mode: فقط در Development یا Testing فعال می‌شود.

هدف: بتوانید بدون داشتن سرور واقعی، UI را کامل تست کنید. در Production این
ماژول هیچ داده‌ای تولید نمی‌کند (قانون «هیچ متریک جعلی در Production»).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.monitoring import Metric
from app.db.models.server import Server, ServerAgent
from app.db.models.tunnel import Tunnel
from app.services import traffic_service
from app.services.audit import add_log, push_notification

log = get_logger("mock")

DEMO_SERVERS = [
    ("سرور ایران - تهران", "185.10.20.30", "Iran", "IR", "Asiatech", 35.7, 51.4),
    ("سرور آلمان - فرانکفورت", "88.99.100.11", "Germany", "DE", "Hetzner", 50.1, 8.6),
    ("سرور هلند - آمستردام", "45.61.72.83", "Netherlands", "NL", "Serverius", 52.3, 4.9),
    ("سرور ترکیه - استانبول", "31.44.55.66", "Turkey", "TR", "Radore", 41.0, 28.9),
]


def enabled() -> bool:
    return bool(settings.MOCK_MODE and not settings.is_production)


async def seed_demo(db: AsyncSession) -> None:
    """ساخت سرور و تونل نمونه برای محیط توسعه."""
    if not enabled():
        return
    existing = (await db.execute(select(Server))).scalars().first()
    if existing:
        return
    servers: list[Server] = []
    for name, ip, country, code, provider, lat, lon in DEMO_SERVERS:
        server = Server(
            name=name,
            ip_address=ip,
            country=country,
            country_code=code,
            provider=provider,
            operating_system="Ubuntu 24.04 LTS",
            kernel="6.8.0-generic",
            architecture="amd64",
            hostname=name.split(" - ")[-1].lower(),
            status="online",
            cpu_cores=random.choice([2, 4, 8]),
            cpu_model="AMD EPYC 7003",
            ram_total_bytes=random.choice([4, 8, 16]) * 1024**3,
            disk_total_bytes=random.choice([80, 160, 320]) * 1024**3,
            uptime_seconds=random.randint(10**5, 10**6),
            last_seen_at=datetime.now(timezone.utc),
            tags=["demo", country.lower()],
            latitude=lat,
            longitude=lon,
            health_score=random.uniform(78, 98),
        )
        db.add(server)
        servers.append(server)
    await db.flush()
    for server in servers:
        db.add(ServerAgent(server_id=server.id, enrollment_token_hash="demo", enrolled=True, version="1.0.0"))
    tunnel_types = ["premium_backhaul", "rathole2", "packet_tunnel", "backpack"]
    for idx, type_key in enumerate(tunnel_types):
        tunnel = Tunnel(
            name=f"تونل نمونه {idx + 1}",
            type_key=type_key,
            source_server_id=servers[0].id,
            destination_server_id=servers[(idx % (len(servers) - 1)) + 1].id,
            state="deployed",
            health=["up", "up", "degraded", "down"][idx % 4],
            latency_ms=round(random.uniform(35, 180), 1),
            packet_loss=round(random.uniform(0, 3), 2),
            jitter_ms=round(random.uniform(1, 20), 1),
            uptime_seconds=random.randint(3600, 10**6),
            service_name=f"alfa-tunnel-demo{idx}",
            tags=["demo"],
        )
        db.add(tunnel)
    await db.flush()
    await push_notification(
        db,
        kind="demo",
        title="داده نمونه ساخته شد",
        body="حالت Mock فعال است؛ این داده‌ها واقعی نیستند.",
        severity="info",
    )
    log.info("demo_seeded", servers=len(servers))


async def tick(db: AsyncSession) -> None:
    """یک نمونه متریک/ترافیک شبیه‌سازی‌شده برای همه سرورها تولید می‌کند."""
    if not enabled():
        return
    now = datetime.now(timezone.utc)
    servers = (await db.execute(select(Server))).scalars().all()
    phase = now.timestamp() / 90
    for index, server in enumerate(servers):
        base = 25 + 20 * math.sin(phase + index)
        cpu = max(2.0, min(97.0, base + random.uniform(-6, 8)))
        ram_total = server.ram_total_bytes or 8 * 1024**3
        disk_total = server.disk_total_bytes or 160 * 1024**3
        rx_rate = max(0.0, (12 + 9 * math.sin(phase * 1.7 + index)) * 1024**2)
        tx_rate = max(0.0, (8 + 6 * math.cos(phase * 1.3 + index)) * 1024**2)
        db.add(
            Metric(
                server_id=server.id,
                ts=now,
                cpu_percent=round(cpu, 2),
                load_1=round(cpu / 25, 2),
                load_5=round(cpu / 30, 2),
                load_15=round(cpu / 35, 2),
                ram_total=ram_total,
                ram_used=int(ram_total * random.uniform(0.35, 0.82)),
                swap_total=2 * 1024**3,
                swap_used=int(2 * 1024**3 * random.uniform(0, 0.3)),
                disk_total=disk_total,
                disk_used=int(disk_total * random.uniform(0.3, 0.78)),
                net_rx_bytes=random.randint(10**9, 10**12),
                net_tx_bytes=random.randint(10**9, 10**12),
                net_rx_rate=rx_rate,
                net_tx_rate=tx_rate,
                packets_rx_rate=rx_rate / 1200,
                packets_tx_rate=tx_rate / 1200,
                uptime_seconds=(server.uptime_seconds or 0) + 20,
            )
        )
        server.status = "online"
        server.last_seen_at = now
        await traffic_service.add_usage(db, "server", server.id, int(rx_rate * 20), int(tx_rate * 20), now)
    tunnels = (await db.execute(select(Tunnel))).scalars().all()
    for tunnel in tunnels:
        tunnel.latency_ms = round(max(8.0, (tunnel.latency_ms or 60) + random.uniform(-6, 6)), 1)
        tunnel.packet_loss = round(max(0.0, random.uniform(0, 2.5)), 2)
        tunnel.jitter_ms = round(max(0.5, random.uniform(1, 18)), 1)
        tunnel.last_health_at = now
        await traffic_service.add_usage(
            db, "tunnel", tunnel.id, random.randint(10**7, 10**9), random.randint(10**7, 10**9), now
        )
    if random.random() < 0.05 and servers:
        await add_log(
            db,
            source="agent",
            message="نمونه لاگ حالت Mock: بازخوانی پیکربندی انجام شد.",
            server_id=servers[0].id,
        )
    await db.flush()
