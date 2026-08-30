"""Adapter تونل Broken Node (منبع: Binary اختصاصی کاربر)."""
from __future__ import annotations

from app.tunnel_adapters.base import AdapterMetadata, ConfigField, TunnelAdapter


class BrokenNodeAdapter(TunnelAdapter):
    metadata = AdapterMetadata(
        key="broken_node",
        display_name="Broken Node",
        display_name_fa="بروکن نود",
        source_kind="binary",
        summary_fa="تونل با Binary اختصاصی Broken Node. مسیر Binary در تنظیمات پنل تعریف می‌شود.",
        requires=["systemd"],
        capabilities=["install", "start", "stop", "restart", "status", "logs", "health"],
        env_keys=["BROKEN_NODE_BINARY"],
        docs_fa="docs/tunnel-adapters.md#broken-node",
    )
    extra_fields = [
        ConfigField("binary_path_override", "مسیر Binary (اختیاری)", "string", False, None, advanced=True),
        ConfigField("config_file_name", "نام فایل config", "string", False, "config.json", advanced=True),
    ]

    @staticmethod
    def describe() -> AdapterMetadata:
        return BrokenNodeAdapter.metadata

    def build_payload(self, tunnel, config: dict, secrets: dict | None = None) -> dict:
        payload = super().build_payload(tunnel, config, secrets)
        if config.get("binary_path_override"):
            payload["source"]["binary_path"] = config["binary_path_override"]
        payload["config_file_name"] = config.get("config_file_name") or "config.json"
        return payload
