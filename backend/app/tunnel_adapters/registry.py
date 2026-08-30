"""Registry آداپترها. افزودن تونل جدید = ساخت Adapter + ثبت در همین لیست."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import NotFound
from app.db.models.tunnel import TunnelType
from app.tunnel_adapters.backpack import BackPackAdapter
from app.tunnel_adapters.base import AdapterMetadata, TunnelAdapter
from app.tunnel_adapters.broken_node import BrokenNodeAdapter
from app.tunnel_adapters.packet_tunnel import PacketTunnelAdapter
from app.tunnel_adapters.ping_tunnel import PingTunnelAdapter
from app.tunnel_adapters.premium_backhaul import PremiumBackhaulAdapter
from app.tunnel_adapters.rathole2 import Rathole2Adapter

ADAPTERS: dict[str, type[TunnelAdapter]] = {
    PremiumBackhaulAdapter.metadata.key: PremiumBackhaulAdapter,
    BrokenNodeAdapter.metadata.key: BrokenNodeAdapter,
    PacketTunnelAdapter.metadata.key: PacketTunnelAdapter,
    BackPackAdapter.metadata.key: BackPackAdapter,
    PingTunnelAdapter.metadata.key: PingTunnelAdapter,
    Rathole2Adapter.metadata.key: Rathole2Adapter,
}

# مقادیر پیش‌فرض منابع از .env (اگر کاربر آن‌ها را پر کرده باشد)
ENV_DEFAULTS: dict[str, dict[str, str]] = {
    "premium_backhaul": {"binary_path": settings.PREMIUM_BACKHAUL_BINARY or "/opt/alfa/tunnel-binaries/backhaul_premium"},
    "broken_node": {"binary_path": settings.BROKEN_NODE_BINARY or "/opt/alfa/tunnel-binaries/brokennode"},
    "packet_tunnel": {
        "repository_url": settings.PACKET_TUNNEL_REPOSITORY,
        "repository_ref": settings.PACKET_TUNNEL_REF,
    },
    "backpack": {
        "repository_url": settings.BACKPACK_REPOSITORY,
        "repository_ref": settings.BACKPACK_REF,
    },
    "ping_tunnel": {
        "repository_url": settings.PING_TUNNEL_REPOSITORY,
        "repository_ref": settings.PING_TUNNEL_REF,
    },
    "rathole2": {
        "repository_url": settings.RATHOLE_REPOSITORY,
        "repository_ref": settings.RATHOLE_REF,
    },
}


def metadata_list() -> list[AdapterMetadata]:
    return [cls.describe() for cls in ADAPTERS.values()]


def adapter_class(key: str) -> type[TunnelAdapter]:
    cls = ADAPTERS.get(key)
    if not cls:
        raise NotFound(f"نوع تونل «{key}» شناخته نشد.")
    return cls


async def get_type_row(db: AsyncSession, key: str) -> TunnelType:
    row = (await db.execute(select(TunnelType).where(TunnelType.key == key))).scalar_one_or_none()
    if not row:
        raise NotFound(f"نوع تونل «{key}» در دیتابیس ثبت نشده است.")
    return row


async def build_adapter(db: AsyncSession, key: str, agent_client) -> TunnelAdapter:
    row = await get_type_row(db, key)
    return adapter_class(key)(agent_client, row)


async def sync_registry(db: AsyncSession) -> None:
    """Adapterهای کد را با جدول tunnel_types همگام می‌کند (idempotent)."""
    existing = {r.key: r for r in (await db.execute(select(TunnelType))).scalars()}
    for key, cls in ADAPTERS.items():
        meta = cls.describe()
        defaults = ENV_DEFAULTS.get(key, {})
        row = existing.get(key)
        if row is None:
            row = TunnelType(
                key=key,
                display_name=meta.display_name,
                display_name_fa=meta.display_name_fa,
                source_kind=meta.source_kind,
                architectures=meta.architectures,
                notes_fa=meta.summary_fa,
                binary_path=defaults.get("binary_path", ""),
                repository_url=defaults.get("repository_url", ""),
                repository_ref=defaults.get("repository_ref", ""),
            )
            db.add(row)
        else:
            row.display_name = meta.display_name
            row.display_name_fa = meta.display_name_fa
            row.source_kind = meta.source_kind
            row.architectures = meta.architectures
            if not row.binary_path and defaults.get("binary_path"):
                row.binary_path = defaults["binary_path"]
            if not row.repository_url and defaults.get("repository_url"):
                row.repository_url = defaults["repository_url"]
            if not row.repository_ref and defaults.get("repository_ref"):
                row.repository_ref = defaults["repository_ref"]
        row.configured = bool(row.binary_path if meta.source_kind == "binary" else row.repository_url)
    await db.flush()
