"""Adapter تونل Premium Backhaul (منبع: Binary اختصاصی کاربر).

CLI و فرمت config این برنامه در دسترس ما نیست، بنابراین هیچ آرگومانی حدس زده
نشده است. مسیر Binary از تنظیمات (PREMIUM_BACKHAUL_BINARY) خوانده می‌شود و
آرگومان‌ها/قالب config توسط کاربر در همان صفحه وارد می‌شوند.
"""
from __future__ import annotations

from app.tunnel_adapters.base import AdapterMetadata, ConfigField, TunnelAdapter


class PremiumBackhaulAdapter(TunnelAdapter):
    metadata = AdapterMetadata(
        key="premium_backhaul",
        display_name="Premium Backhaul",
        display_name_fa="پریمیوم بک‌هال",
        source_kind="binary",
        summary_fa="تونل بک‌هال با Binary اختصاصی. Binary را در پنل بارگذاری یا مسیر آن را وارد کنید.",
        requires=["systemd"],
        architectures=["amd64"],
        capabilities=["install", "start", "stop", "restart", "status", "logs", "health", "metrics"],
        env_keys=["PREMIUM_BACKHAUL_BINARY"],
        docs_fa="docs/tunnel-adapters.md#premium-backhaul",
    )
    extra_fields = [
        ConfigField("binary_path_override", "مسیر Binary (اختیاری)", "string", False, None,
                    "اگر خالی باشد از مقدار تنظیمات پنل استفاده می‌شود", advanced=True),
        ConfigField("config_file_name", "نام فایل config", "string", False, "config.toml",
                    "نام فایلی که Binary انتظار دارد", advanced=True),
    ]

    @staticmethod
    def describe() -> AdapterMetadata:
        return PremiumBackhaulAdapter.metadata

    def build_payload(self, tunnel, config: dict, secrets: dict | None = None) -> dict:
        payload = super().build_payload(tunnel, config, secrets)
        override = config.get("binary_path_override")
        if override:
            payload["source"]["binary_path"] = override
        payload["config_file_name"] = config.get("config_file_name") or "config.toml"
        return payload
