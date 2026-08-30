"""Adapter تونل Rathole 2 بر پایه Repository ارائه‌شده."""
from __future__ import annotations

from app.tunnel_adapters.base import AdapterMetadata
from app.tunnel_adapters.repo_based import RepositoryAdapter


class Rathole2Adapter(RepositoryAdapter):
    metadata = AdapterMetadata(
        key="rathole2",
        display_name="Rathole 2",
        display_name_fa="رت‌هول ۲",
        source_kind="repository",
        summary_fa="Rathole v2 با پشتیبانی چند سرویس و چند سرور.",
        requires=["systemd"],
        capabilities=["install", "start", "stop", "restart", "status", "logs", "health", "metrics"],
        architectures=["amd64"],
        env_keys=["RATHOLE_REPOSITORY", "RATHOLE_REF"],
        docs_fa="docs/tunnel-adapters.md#rathole-2",
    )

    @staticmethod
    def describe() -> AdapterMetadata:
        return Rathole2Adapter.metadata

    def source_spec(self) -> dict:
        spec = super().source_spec()
        spec.update({
            "binary_name_hint": "rathole",
            "asset_url_by_arch": {
                "amd64": "https://github.com/Musixal/rathole-tunnel/raw/main/core/rathole.zip",
            },
        })
        # Let the Agent use the supplied repository's known core for amd64.
        spec["kind"] = "direct_asset"
        return spec

    def build_payload(self, tunnel, config: dict, secrets: dict | None = None) -> dict:
        cfg = dict(config)
        token = str((secrets or {}).get("auth_token") or cfg.get("auth_token") or "")
        peer_ip = str(cfg.get("peer_ip") or "")
        listen = int(cfg.get("listen_port") or 0)
        remote = int(cfg.get("remote_port") or cfg.get("local_port") or listen)
        protocol = str(cfg.get("protocol") or "tcp")
        role = str(cfg.get("role") or "client").lower()
        if not cfg.get("config_template") and listen and token:
            if role == "server":
                cfg["config_template"] = (
                    "[server]\n"
                    f"bind_addr = \"0.0.0.0:{listen}\"\n"
                    f"default_token = \"$auth_token\"\n\n"
                    "[server.transport]\n"
                    "type = \"tcp\"\n\n"
                    f"[server.services.{remote}]\n"
                    f"type = \"{protocol if protocol in ('tcp','udp') else 'tcp'}\"\n"
                    f"bind_addr = \"0.0.0.0:{remote}\"\n"
                )
            elif peer_ip:
                cfg["config_template"] = (
                    "[client]\n"
                    f"remote_addr = \"{peer_ip}:{listen}\"\n"
                    f"default_token = \"$auth_token\"\n"
                    "retry_interval = 1\n\n"
                    "[client.transport]\n"
                    "type = \"tcp\"\n\n"
                    f"[client.services.{remote}]\n"
                    f"type = \"{protocol if protocol in ('tcp','udp') else 'tcp'}\"\n"
                    f"local_addr = \"127.0.0.1:{remote}\"\n"
                )
        payload = super().build_payload(tunnel, cfg, secrets)
        payload["args"] = ["${config_file}"] if False else payload["args"]
        # Rathole accepts the config path as its positional argument. The Agent
        # writes it to the tunnel directory and substitutes it below.
        payload["args"] = ["$CONFIG_PATH"]
        return payload
