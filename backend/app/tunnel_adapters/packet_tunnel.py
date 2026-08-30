"""Adapter تونل Packet Tunnel (منبع: Repository گیت)."""
from __future__ import annotations

from app.tunnel_adapters.base import AdapterMetadata
from app.tunnel_adapters.repo_based import RepositoryAdapter


class PacketTunnelAdapter(RepositoryAdapter):
    metadata = AdapterMetadata(
        key="packet_tunnel",
        display_name="Packet Tunnel",
        display_name_fa="پکت تانل",
        source_kind="repository",
        summary_fa="تونل سطح پکت؛ از Repository نصب یا Build می‌شود.",
        requires=["systemd", "iptables"],
        capabilities=["install", "start", "stop", "restart", "status", "logs", "health", "metrics"],
        env_keys=["PACKET_TUNNEL_REPOSITORY", "PACKET_TUNNEL_REF"],
        docs_fa="docs/tunnel-adapters.md#packet-tunnel",
    )

    @staticmethod
    def describe() -> AdapterMetadata:
        return PacketTunnelAdapter.metadata
