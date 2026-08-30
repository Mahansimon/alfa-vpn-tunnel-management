"""Adapter تونل Ping Tunnel بر پایه اسکریپت pPouria و Binary رسمی PingTunnel."""
from __future__ import annotations

from app.tunnel_adapters.base import AdapterMetadata, ConfigField
from app.tunnel_adapters.repo_based import RepositoryAdapter


class PingTunnelAdapter(RepositoryAdapter):
    metadata = AdapterMetadata(
        key="ping_tunnel",
        display_name="Ping Tunnel",
        display_name_fa="پینگ تانل",
        source_kind="repository",
        summary_fa="تونل مبتنی بر ICMP؛ Binary از Release رسمی PingTunnel تهیه می‌شود و سرویس systemd ساخته می‌شود.",
        requires=["systemd", "cap_net_raw", "sysctl"],
        capabilities=["install", "start", "stop", "restart", "status", "logs", "health"],
        env_keys=["PING_TUNNEL_REPOSITORY", "PING_TUNNEL_REF"],
        docs_fa="docs/tunnel-adapters.md#ping-tunnel",
    )
    extra_fields = [
        *RepositoryAdapter.extra_fields,
        ConfigField("ping_mode", "نقش PingTunnel", "select", False, "client",
                    "در سمت مبدأ client و در سمت مقصد server استفاده می‌شود.", ["client", "server"]),
    ]

    @staticmethod
    def describe() -> AdapterMetadata:
        return PingTunnelAdapter.metadata

    def source_spec(self) -> dict:
        spec = super().source_spec()
        spec.update({
            "kind": "direct_asset",
            "binary_name_hint": "pingtunnel",
            "asset_url_by_arch": {
                "amd64": "https://github.com/esrrhs/pingtunnel/releases/download/2.8/pingtunnel_linux_amd64.zip",
                "arm64": "https://github.com/esrrhs/pingtunnel/releases/download/2.8/pingtunnel_linux_arm64.zip",
            },
        })
        return spec

    def build_payload(self, tunnel, config: dict, secrets: dict | None = None) -> dict:
        payload = super().build_payload(tunnel, config, secrets)
        role = str(config.get("role") or config.get("ping_mode") or "client").lower()
        if role == "client":
            port = config.get("listen_port") or config.get("local_port")
            target = config.get("local_port") or port
            peer_ip = config.get("peer_ip") or ""
            if not peer_ip:
                # Validation will report the missing peer IP before deployment.
                peer_ip = "0.0.0.0"
            payload["args"] = ["-type", "client", "-l", f":{port}", "-s", str(peer_ip), "-t", f"127.0.0.1:{target}", "-tcp", "1"]
        else:
            payload["args"] = ["-type", "server"]
        payload["config_file"] = ""
        return payload
