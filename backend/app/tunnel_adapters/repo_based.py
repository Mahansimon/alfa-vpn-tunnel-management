"""پایه Adapterهایی که منبع‌شان یک Repository گیت است.

Agent هنگام نصب، نوع پروژه را تشخیص می‌دهد (Release Artifact، Dockerfile،
Makefile، Go، Rust، Python) و بر همان اساس نصب/Build می‌کند. هیچ فرضی درباره
ساختار Repository در کد پنل وجود ندارد.
"""
from __future__ import annotations

from app.tunnel_adapters.base import AdapterMetadata, ConfigField, TunnelAdapter

REPO_FIELDS = [
    ConfigField("repository_override", "آدرس Repository (اختیاری)", "string", False, None,
                "اگر خالی باشد از تنظیمات پنل استفاده می‌شود", advanced=True),
    ConfigField("repository_ref_override", "نسخه/Tag/Branch", "string", False, None,
                "برای pin کردن نسخه؛ خالی یعنی مقدار تنظیمات پنل", advanced=True),
    ConfigField("prefer_release_asset", "ترجیح استفاده از Release Artifact", "bool", False, True,
                "اگر Release موجود باشد به جای Build از artifact استفاده می‌شود", advanced=True),
    ConfigField("build_in_container", "Build داخل کانتینر", "bool", False, True,
                "در صورت وجود Docker، Build جدا و ایزوله انجام می‌شود", advanced=True),
    ConfigField("binary_name_hint", "نام Binary خروجی (اختیاری)", "string", False, None,
                "اگر نام فایل اجرایی نهایی را می‌دانید وارد کنید", advanced=True),
    ConfigField("config_file_name", "نام فایل config", "string", False, "config.toml", advanced=True),
]


class RepositoryAdapter(TunnelAdapter):
    """Adapter پایه برای تونل‌های مبتنی بر Repository."""

    extra_fields = REPO_FIELDS

    @staticmethod
    def describe() -> AdapterMetadata:  # pragma: no cover - در زیرکلاس‌ها بازنویسی می‌شود
        raise NotImplementedError

    def build_payload(self, tunnel, config: dict, secrets: dict | None = None) -> dict:
        payload = super().build_payload(tunnel, config, secrets)
        source = payload["source"]
        if config.get("repository_override"):
            source["repository_url"] = config["repository_override"]
        if config.get("repository_ref_override"):
            source["repository_ref"] = config["repository_ref_override"]
        source["prefer_release_asset"] = bool(config.get("prefer_release_asset", True))
        source["build_in_container"] = bool(config.get("build_in_container", True))
        source["binary_name_hint"] = config.get("binary_name_hint") or ""
        payload["config_file_name"] = config.get("config_file_name") or "config.toml"
        return payload
